from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from PIL import Image, ImageDraw
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from .accounting_brand import CANONICAL_LOGO, verify_accounting_brand_lock
from .publish_accounting_brief import _clean, _load_config, _validate_brief

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
BRAND_CONFIG = ROOT / "config" / "brand.json"
CANONICAL_LOGO = ASSETS / "stacorp-logo.png"
INCOMING = ROOT / "incoming" / "accounting" / "current"
OUT = Path("/tmp/stacorp-daily-brief")
TEAMS = OUT / "teams"
VISUALS = OUT / "accounting-visuals"

CSS_SIZE = (1080, 1620)
TEAMS_SIZE = (1200, 1800)
SCALE = 2
LAYOUT_VERSION = "STACORP_ACCOUNTING_VISUAL_V2"
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ALLOWED_REMOTE_VISUAL_HOSTS = {"images.pexels.com"}

PAGES = (
    OUT / "STACORP_ACCOUNTING_BRIEF_PAGE_1.png",
    OUT / "STACORP_ACCOUNTING_BRIEF_PAGE_2.png",
    OUT / "STACORP_ACCOUNTING_BRIEF_PAGE_3.png",
)

ACCOUNTING_TEMPLATES = (
    TEMPLATES / "accounting_page1.html",
    TEMPLATES / "accounting_page2.html",
    TEMPLATES / "accounting_page3.html",
)


def _git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def verify_accounting_brand_lock() -> None:
    if not BRAND_CONFIG.exists():
        raise RuntimeError("STACORP brand config is missing.")
    brand = json.loads(BRAND_CONFIG.read_text(encoding="utf-8"))

    if brand.get("canonical_logo_path") != "assets/stacorp-logo.png":
        raise RuntimeError("Canonical STACORP logo path changed; accounting publish blocked.")
    if brand.get("render_rules", {}).get("allow_ai_generated_logo") is not False:
        raise RuntimeError("AI-generated STACORP logo must remain disabled.")
    if brand.get("render_rules", {}).get("allow_story_image_logo") is not False:
        raise RuntimeError("STACORP logo must not appear inside story visuals.")
    if brand.get("render_rules", {}).get("fail_if_missing_or_modified") is not True:
        raise RuntimeError("STACORP brand lock must fail closed.")

    if not CANONICAL_LOGO.exists():
        raise RuntimeError("Canonical STACORP logo asset is missing.")

    data = CANONICAL_LOGO.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    actual_blob = _git_blob_sha(data)
    expected_sha256 = str(brand.get("production_asset_sha256", "")).strip()
    expected_blob = str(brand.get("production_git_blob_sha1", "")).strip()

    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"STACORP logo SHA256 integrity failed: {actual_sha256} != {expected_sha256}"
        )
    if actual_blob != expected_blob:
        raise RuntimeError(
            f"STACORP logo git-blob integrity failed: {actual_blob} != {expected_blob}"
        )

    required_ref = 'src="stacorp-logo.png"'
    for template in ACCOUNTING_TEMPLATES:
        if not template.exists():
            raise RuntimeError(f"Accounting template is missing: {template.name}")
        source = template.read_text(encoding="utf-8")
        if source.count(required_ref) != 1:
            raise RuntimeError(
                f"{template.name} must reference canonical stacorp-logo.png exactly once."
            )
        lowered = source.lower()
        for token in ("logo.svg", "logo.jpg", "logo.jpeg", "logo.webp", "logo_brand"):
            if token in lowered:
                raise RuntimeError(
                    f"Non-canonical logo reference found in {template.name}: {token}"
                )

    print(f"ACCOUNTING_LOGO_SHA256={actual_sha256}")
    print(f"ACCOUNTING_LOGO_GIT_BLOB_SHA1={actual_blob}")
    print("ACCOUNTING_BRAND_GATE=PASS")


def _downsample(src: Path, dst: Path, size: tuple[int, int]) -> None:
    with Image.open(src) as image:
        image = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        image.save(dst, format="PNG", optimize=True)


def _resolve_visual(path_text: str) -> Path:
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"Unsafe accounting visual path: {path_text!r}")
    source = (INCOMING / relative).resolve()
    incoming_root = INCOMING.resolve()
    if incoming_root not in source.parents:
        raise RuntimeError(f"Accounting visual escapes incoming folder: {path_text!r}")
    return source


def _validate_visual(source: Path, cfg: dict, index: int) -> None:
    visual_cfg = cfg["visuals"]
    if not source.exists():
        raise RuntimeError(f"Missing accounting story visual {index}: {source}")

    suffix = source.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise RuntimeError(
            f"Accounting story visual {index} must be PNG/JPEG, got {suffix or 'no extension'}."
        )

    size_bytes = source.stat().st_size
    if size_bytes < int(visual_cfg["min_source_bytes"]):
        raise RuntimeError(
            f"Accounting story visual {index} is too small: "
            f"{size_bytes} < {visual_cfg['min_source_bytes']} bytes."
        )

    with Image.open(source) as image:
        width, height = image.size

    if max(width, height) < int(visual_cfg["min_long_edge"]):
        raise RuntimeError(
            f"Accounting story visual {index} long edge too small: {width}x{height}."
        )
    if min(width, height) < int(visual_cfg["min_short_edge"]):
        raise RuntimeError(
            f"Accounting story visual {index} short edge too small: {width}x{height}."
        )

    print(f"ACCOUNTING_VISUAL_{index}_DIMENSIONS={width}x{height}")
    print(f"ACCOUNTING_VISUAL_{index}_BYTES={size_bytes}")


def _pick_visual(items: list[dict], area: str, fallback_index: int) -> str:
    lower = area.lower()
    wanted = None
    if any(k in lower for k in ("kế toán", "tài chính", "chi phí", "dòng tiền")):
        wanted = "KẾ TOÁN · THUẾ · TÀI CHÍNH"
    elif any(k in lower for k in ("pháp lý", "đầu tư", "bất động sản")):
        wanted = "PHÁP LÝ · CHÍNH SÁCH DOANH NGHIỆP"
    elif any(k in lower for k in ("nhân sự", "lao động")):
        wanted = "NHÂN SỰ · THỊ TRƯỜNG LAO ĐỘNG"

    if wanted:
        for item in items:
            if item.get("category") == wanted:
                return item["render_visual_src"]

    return items[fallback_index % len(items)]["render_visual_src"]


def _impact_tag(area: str) -> str:
    lower = area.lower()
    if any(k in lower for k in ("kế toán", "thuế")):
        return "QUẢN TRỊ RỦI RO"
    if any(k in lower for k in ("chi phí", "dòng tiền", "tài chính")):
        return "TỐI ƯU CHI PHÍ"
    if any(k in lower for k in ("pháp lý", "đầu tư", "bất động sản")):
        return "NẮM BẮT CƠ HỘI"
    if any(k in lower for k in ("nhân sự", "lao động")):
        return "PHÁT TRIỂN NGUỒN LỰC"
    return "HỖ TRỢ QUYẾT ĐỊNH"


def _download_remote_visual(url: str, index: int, cfg: dict) -> Path:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_REMOTE_VISUAL_HOSTS:
        raise RuntimeError(
            f"Accounting visual URL {index} must use HTTPS on an approved image host."
        )

    with httpx.Client(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": "STACORP-Accounting-Brief/1.0"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "image/" not in content_type:
            raise RuntimeError(
                f"Accounting visual URL {index} returned non-image content: {content_type}"
            )
        data = response.content

    suffix = ".png" if "png" in content_type else ".jpg"
    target = VISUALS / f"story-{index}-remote{suffix}"
    target.write_bytes(data)
    _validate_visual(target, cfg, index)
    print(f"ACCOUNTING_REMOTE_VISUAL_{index}={host}")
    return target


def _apply_runtime_stamp(brief: dict) -> dict:
    now = datetime.now(LOCAL_TZ)
    window_hours = 48 if now.weekday() in {0, 6} else 24
    brief["display_date"] = now.strftime("%d.%m.%Y")
    brief["display_window"] = (
        f"{window_hours} giờ gần nhất • cập nhật {now.strftime('%H:%M')}"
    )
    print(f"ACCOUNTING_DISPLAY_DATE={brief['display_date']}")
    print(f"ACCOUNTING_DISPLAY_TIME={now.strftime('%H:%M')}")
    return brief


def _qa_demo_visual(index: int, item: dict) -> Path:
    VISUALS.mkdir(parents=True, exist_ok=True)
    target = VISUALS / f"story-{index}-qa.jpg"

    width, height = 1600, 1000
    palettes = [
        ((232, 241, 251), (30, 83, 137), (207, 153, 44)),
        ((244, 238, 222), (15, 67, 119), (224, 155, 31)),
        ((230, 242, 238), (34, 100, 83), (205, 155, 55)),
        ((239, 242, 249), (39, 79, 128), (207, 151, 42)),
        ((237, 243, 250), (34, 92, 148), (187, 139, 41)),
        ((232, 241, 246), (22, 77, 125), (218, 162, 53)),
        ((239, 244, 248), (42, 92, 126), (202, 148, 37)),
        ((236, 242, 249), (44, 80, 132), (214, 158, 45)),
    ]
    bg, primary, gold = palettes[(index - 1) % len(palettes)]

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(bg[0] * (1 - ratio) + 248 * ratio)
        g = int(bg[1] * (1 - ratio) + 250 * ratio)
        b = int(bg[2] * (1 - ratio) + 252 * ratio)
        draw.line((0, y, width, y), fill=(r, g, b))

    draw.ellipse((1080, -180, 1700, 440), fill=(*gold,))
    draw.ellipse((1160, -100, 1660, 400), fill=(244, 224, 174))
    draw.rounded_rectangle((90, 110, 940, 840), radius=42, fill=(255, 255, 255), outline=(215, 224, 234), width=4)

    kind = index % 6
    if kind == 1:
        draw.rounded_rectangle((170, 210, 770, 720), radius=28, fill=(247, 249, 252), outline=primary, width=8)
        for yy in (310, 410, 510, 610):
            draw.line((240, yy, 690, yy), fill=(183, 199, 216), width=12)
        draw.rounded_rectangle((1030, 500, 1430, 800), radius=30, fill=primary)
        for col in range(4):
            for row in range(3):
                x=1080+col*82; y=550+row*74
                draw.rounded_rectangle((x,y,x+52,y+45),radius=8,fill=(242,246,250))
    elif kind == 2:
        draw.rounded_rectangle((180, 570, 760, 760), radius=30, fill=primary)
        draw.rectangle((250, 450, 480, 610), fill=(255,255,255), outline=primary, width=8)
        draw.line((480, 520, 620, 520), fill=primary, width=18)
        draw.arc((600, 420, 820, 650), start=220, end=345, fill=gold, width=24)
        draw.ellipse((760, 585, 850, 675), fill=gold)
        draw.rectangle((1020, 490, 1440, 720), fill=(74, 102, 133))
        draw.rectangle((1110, 400, 1330, 520), fill=(238,244,248))
        draw.ellipse((1080, 690, 1190, 800), fill=(42,48,56))
        draw.ellipse((1320, 690, 1430, 800), fill=(42,48,56))
    elif kind == 3:
        base_y=770
        for i,h in enumerate((420,560,650,500,590,450)):
            x=160+i*125
            draw.rectangle((x,base_y-h,x+90,base_y),fill=primary)
            for wy in range(base_y-h+45,base_y-30,70):
                draw.rectangle((x+22,wy,x+68,wy+30),fill=(218,231,243))
        draw.rectangle((1010, 520, 1450, 760), fill=(250,250,248), outline=gold, width=8)
        draw.line((1090, 700, 1370, 580), fill=gold, width=16)
        draw.line((1090, 600, 1370, 700), fill=primary, width=16)
    elif kind == 4:
        for i,x in enumerate((160,420,680)):
            draw.rectangle((x,470,x+210,770),fill=(246,248,251),outline=primary,width=7)
            draw.polygon(((x-20,470),(x+105,350),(x+230,470)),fill=gold)
            draw.rectangle((x+75,620,x+135,770),fill=primary)
        draw.rounded_rectangle((1050, 420, 1450, 790),radius=28,fill=(255,255,255),outline=(190,204,220),width=5)
        draw.ellipse((1160, 500, 1340, 680),fill=primary)
        draw.rectangle((1230, 660, 1270, 760),fill=gold)
    elif kind == 5:
        draw.ellipse((220, 220, 520, 520), fill=primary)
        draw.ellipse((300, 290, 440, 430), fill=(238,244,250))
        for x in (180,420,660):
            draw.ellipse((x, 540, x+150, 690), fill=gold)
            draw.rounded_rectangle((x+20,650,x+130,810),radius=35,fill=primary)
        draw.polygon(((1120,220),(1390,300),(1360,650),(1255,780),(1150,650)),fill=primary)
        draw.ellipse((1200,350,1310,460),fill=(244,248,251))
    else:
        draw.rectangle((120, 500, 910, 780), fill=(213,225,236))
        draw.line((180,500,360,260),fill=primary,width=24)
        draw.line((360,260,610,500),fill=primary,width=24)
        draw.line((610,500,800,220),fill=primary,width=24)
        for x in (260,520,780):
            draw.ellipse((x-55,510,x+55,620),fill=gold)
            draw.rounded_rectangle((x-70,600,x+70,810),radius=35,fill=primary)
        draw.ellipse((1110,300,1430,620),fill=(246,248,251),outline=gold,width=16)
        draw.line((1270,330,1270,590),fill=primary,width=24)
        draw.line((1140,460,1400,460),fill=primary,width=24)

    image.save(target, "JPEG", quality=94, subsampling=0)
    print(f"ACCOUNTING_QA_VISUAL_{index}={target.name}")
    return target


def _prepare_visuals(brief: dict, cfg: dict) -> dict:
    prepared = copy.deepcopy(brief)
    VISUALS.mkdir(parents=True, exist_ok=True)

    qa_mode = os.getenv("ACCOUNTING_TARGET_MODE", "").strip().upper() == "QA_GENERAL"

    for index, item in enumerate(prepared["items"], start=1):
        visual_src = _clean(item.get("visual_src"))
        visual_url = _clean(item.get("visual_url"))

        if visual_src:
            source = _resolve_visual(visual_src)
            _validate_visual(source, cfg, index)
            suffix = source.suffix.lower()
            target = VISUALS / f"story-{index}{suffix}"
            shutil.copyfile(source, target)
            item["render_visual_src"] = f"accounting-visuals/{target.name}"
            continue

        if visual_url:
            target = _download_remote_visual(visual_url, index, cfg)
            item["render_visual_src"] = f"accounting-visuals/{target.name}"
            continue

        if qa_mode:
            target = _qa_demo_visual(index, item)
            item["render_visual_src"] = f"accounting-visuals/{target.name}"
            continue

        raise RuntimeError(f"Story {index} is missing a usable visual.")

    prepared["hero_visual_src"] = prepared["items"][0]["render_visual_src"]
    prepared = _apply_runtime_stamp(prepared)

    for index, impact in enumerate(prepared.get("impacts", [])):
        area = _clean(impact.get("area"))
        impact["render_visual_src"] = _pick_visual(prepared["items"], area, index)
        impact["tag"] = _impact_tag(area)

    return prepared


def render_accounting_brief(brief: dict) -> tuple[Path, Path, Path]:
    cfg = _load_config()
    _validate_brief(brief, cfg)
    verify_accounting_brand_lock()

    if cfg.get("layout", {}).get("version") != LAYOUT_VERSION:
        raise RuntimeError(
            f"Accounting layout version mismatch: "
            f"{cfg.get('layout', {}).get('version')!r} != {LAYOUT_VERSION!r}"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    TEAMS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATES / "accounting-style.css", OUT / "accounting-style.css")
    shutil.copyfile(CANONICAL_LOGO, OUT / "stacorp-logo.png")

    brief = _prepare_visuals(brief, cfg)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )

    remaining = brief["items"][3:]
    specs = [
        ("accounting_page1.html", PAGES[0], {"items": brief["items"][:3]}),
        (
            "accounting_page2.html",
            PAGES[1],
            {
                "items": remaining[:3],
                "extras": remaining[3:],
                "offset": 3,
            },
        ),
        ("accounting_page3.html", PAGES[2], {}),
    ]

    html_paths: list[tuple[Path, Path]] = []
    for index, (template, png, extra) in enumerate(specs, start=1):
        html_path = OUT / f"accounting_page{index}.html"
        html_path.write_text(
            env.get_template(template).render(brief=brief, **extra),
            encoding="utf-8",
        )
        html_paths.append((html_path, png))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": CSS_SIZE[0], "height": CSS_SIZE[1]},
            device_scale_factor=SCALE,
        )

        for html_path, png_path in html_paths:
            page.goto(html_path.as_uri(), wait_until="networkidle")

            broken = page.evaluate(
                """() => Array.from(document.images)
                  .filter(img => !img.complete || img.naturalWidth === 0)
                  .map(img => img.getAttribute('src'))"""
            )
            if broken:
                browser.close()
                raise RuntimeError(f"Broken image assets in {html_path.name}: {broken}")

            overflow = page.evaluate(
                """() => ({
                  w: document.documentElement.scrollWidth,
                  h: document.documentElement.scrollHeight
                })"""
            )
            if overflow["w"] > CSS_SIZE[0] or overflow["h"] > CSS_SIZE[1]:
                browser.close()
                raise RuntimeError(
                    f"Accounting layout overflow in {html_path.name}: {overflow}"
                )

            high = png_path.with_name(png_path.stem + "_2X.png")
            page.screenshot(path=str(high), full_page=False)
            _downsample(high, png_path, CSS_SIZE)

            teams_path = TEAMS / f"{png_path.stem}_TEAMS.png"
            _downsample(high, teams_path, TEAMS_SIZE)
            high.unlink(missing_ok=True)

            print(
                f"ACCOUNTING_RENDER={png_path.name} "
                f"{CSS_SIZE[0]}x{CSS_SIZE[1]} "
                f"TEAMS={TEAMS_SIZE[0]}x{TEAMS_SIZE[1]}"
            )

        browser.close()

    print(f"ACCOUNTING_LAYOUT_VERSION={LAYOUT_VERSION}")
    print("ACCOUNTING_VISUAL_GATE=PASS")
    return PAGES
