from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image
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


def _prepare_visuals(brief: dict, cfg: dict) -> dict:
    prepared = copy.deepcopy(brief)
    VISUALS.mkdir(parents=True, exist_ok=True)

    for index, item in enumerate(prepared["items"], start=1):
        source = _resolve_visual(_clean(item.get("visual_src")))
        _validate_visual(source, cfg, index)
        suffix = source.suffix.lower()
        target = VISUALS / f"story-{index}{suffix}"
        shutil.copyfile(source, target)
        item["render_visual_src"] = f"accounting-visuals/{target.name}"

    prepared["hero_visual_src"] = prepared["items"][0]["render_visual_src"]

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
