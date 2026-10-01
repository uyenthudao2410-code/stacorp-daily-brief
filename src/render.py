from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"

APPROVED_LAYOUT_VERSION = "STACORP_EDITORIAL_3PAGE_FINAL_V3_REGIONAL_8NEWS"
APPROVED_PAGE1 = TEMPLATES / "editorial_page1.html"
APPROVED_PAGE2 = TEMPLATES / "editorial_page2.html"
APPROVED_PAGE3 = TEMPLATES / "editorial_page3.html"
APPROVED_STYLE = TEMPLATES / "approved-editorial-style.css"
APPROVED_PAGE1_BLOB_SHA = "153527d2dcc1005a54d616053ad0756d8db69129"
APPROVED_PAGE2_BLOB_SHA = "7e999267059f3f536c728908440537c96f3af971"
APPROVED_PAGE3_BLOB_SHA = "d83a4c48536593aa582b783a791c4a4b0fbaadaf"
APPROVED_STYLE_BLOB_SHA = "4956aa57da4f82902fcee5175e2362a6b4ba8681"

APPROVED_LOGO = ASSETS / "stacorp-logo.png"
APPROVED_LOGO_GIT_BLOB_SHA = "2ffd30fd4c8774bdebb461f157ed6b41c04172be"
APPROVED_LOGO_SHA256 = "4fc97e9245c4513b9334a9659690e886aa4563ad892d3fe49f3d6322ba55046d"

OUT_DIR = Path("/tmp/stacorp-daily-brief")
PAGE1 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_1.png"
PAGE2 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_2.png"
PAGE3 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_3.png"
CSS_SIZE = (1080, 1620)
TEAMS_SIZE = (1200, 1800)
RENDER_SCALE = 2
TEAMS_DIR = OUT_DIR / "teams"

LOCKED_GEOMETRY = {
    "editorial_page1.html": {
        ".page": {"width": 1080, "height": 1620},
        ".masthead": {"height": 164},
        ".logo": {"width": 92, "height": 92},
        ".hero-image-wrap": {"height": 350},
        ".p1-news-row": {"height": 180},
        ".footer": {"height": 98},
    },
    "editorial_page2.html": {
        ".page": {"width": 1080, "height": 1620},
        ".masthead": {"height": 164},
        ".logo": {"width": 92, "height": 92},
        ".page2-kicker": {"height": 62},
        ".news-grid-card": {"height": 570},
        ".footer": {"height": 98},
    },
    "editorial_page3.html": {
        ".page": {"width": 1080, "height": 1620},
        ".masthead": {"height": 164},
        ".logo": {"width": 92, "height": 92},
        ".summary-title-row": {"height": 88},
        ".department-card": {"height": 216},
        ".watch-card": {"height": 154},
        ".footer": {"height": 98},
    },
}


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def _verify_layout_lock() -> None:
    expected = {
        APPROVED_PAGE1: APPROVED_PAGE1_BLOB_SHA,
        APPROVED_PAGE2: APPROVED_PAGE2_BLOB_SHA,
        APPROVED_PAGE3: APPROVED_PAGE3_BLOB_SHA,
        APPROVED_STYLE: APPROVED_STYLE_BLOB_SHA,
    }
    for path, sha in expected.items():
        if not path.exists():
            raise RuntimeError(f"Approved layout asset is missing: {path.name}")
        actual = _git_blob_sha(path)
        if actual != sha:
            raise RuntimeError(
                f"Approved layout lock failed for {path.name}: "
                f"{actual} != {sha}. Production render is blocked."
            )


def _verify_brand_asset() -> None:
    if not APPROVED_LOGO.exists():
        raise RuntimeError("Approved STACORP logo asset is missing.")

    data = APPROVED_LOGO.read_bytes()
    git_blob = b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data

    if hashlib.sha1(git_blob).hexdigest() != APPROVED_LOGO_GIT_BLOB_SHA:
        raise RuntimeError("STACORP logo git-blob integrity check failed.")
    if hashlib.sha256(data).hexdigest() != APPROVED_LOGO_SHA256:
        raise RuntimeError("STACORP logo SHA256 integrity check failed.")


def _clean_note(value: str) -> str:
    return re.sub(
        r"^STACORP\s+cần\s+lưu\s+ý\s*:\s*",
        "",
        str(value or "").strip(),
        flags=re.IGNORECASE,
    )


def _clip_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    clipped = text[: max(1, limit - 1)].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return clipped + "…"


def _validate_copy(brief: dict) -> None:
    items = brief.get("items", [])
    if len(items) != 8:
        raise RuntimeError("Approved V3 layout requires exactly eight news items.")

    if sum(1 for item in items if item.get("impact") == "CAO") > 3:
        raise RuntimeError("Approved layout allows at most three CAO items.")

    allowed_impact = {"CAO", "TRUNG BÌNH", "THEO DÕI"}
    allowed_region = {"MIỀN BẮC", "MIỀN TRUNG", "TOÀN QUỐC"}

    north = 0
    central = 0
    national = 0

    for index, item in enumerate(items, start=1):
        if item.get("impact") not in allowed_impact:
            raise RuntimeError(f"Story {index} has invalid impact.")
        if item.get("region") not in allowed_region:
            raise RuntimeError(
                f"Story {index} region must be MIỀN BẮC, MIỀN TRUNG or TOÀN QUỐC."
            )
        if item.get("region") == "MIỀN BẮC":
            north += 1
        elif item.get("region") == "MIỀN TRUNG":
            central += 1
        else:
            national += 1

        if len(item.get("facts", [])) != 2:
            raise RuntimeError(f"Story {index} must contain exactly two facts.")
        if not 2 <= len(item.get("departments", [])) <= 5:
            raise RuntimeError(f"Story {index} must contain 2-5 departments.")
        if not str(item.get("headline", "")).strip():
            raise RuntimeError(f"Story {index} headline is empty.")

    if north < 3 or central < 3 or national > 2:
        raise RuntimeError(
            "Regional balance failed: require >=3 MIỀN BẮC, >=3 MIỀN TRUNG "
            "and <=2 TOÀN QUỐC items."
        )

    lede = str(brief.get("summary_lede", "")).strip()
    if not 140 <= len(lede) <= 240:
        raise RuntimeError("summary_lede must contain 140-240 characters.")

    department_digest = brief.get("department_digest", [])
    if len(department_digest) != 4:
        raise RuntimeError("department_digest must contain exactly four groups.")
    for index, digest in enumerate(department_digest, start=1):
        if not str(digest.get("group", "")).strip():
            raise RuntimeError(f"department_digest {index} group is empty.")
        if not str(digest.get("title", "")).strip():
            raise RuntimeError(f"department_digest {index} title is empty.")
        if not str(digest.get("detail", "")).strip():
            raise RuntimeError(f"department_digest {index} detail is empty.")
        if not digest.get("departments"):
            raise RuntimeError(f"department_digest {index} departments is empty.")

    regional_pulse = brief.get("regional_pulse", [])
    if len(regional_pulse) != 2:
        raise RuntimeError("regional_pulse must contain exactly MIỀN BẮC and MIỀN TRUNG.")
    pulse_regions = {str(x.get("region", "")).strip() for x in regional_pulse}
    if pulse_regions != {"MIỀN BẮC", "MIỀN TRUNG"}:
        raise RuntimeError("regional_pulse must contain MIỀN BẮC and MIỀN TRUNG.")

    watchpoints = brief.get("watchpoints", [])
    if len(watchpoints) != 3:
        raise RuntimeError("watchpoints must contain exactly three items.")
    for index, point in enumerate(watchpoints, start=1):
        if not all(str(point.get(k, "")).strip() for k in ("label", "title", "detail")):
            raise RuntimeError(f"watchpoint {index} is incomplete.")


def _ensure_demo_visuals(items: list[dict]) -> None:
    visuals_dir = OUT_DIR / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    palette = [
        (218, 234, 251),
        (225, 239, 248),
        (232, 241, 250),
        (221, 235, 247),
        (227, 238, 246),
        (219, 233, 245),
        (230, 240, 248),
        (223, 236, 247),
    ]
    for index, item in enumerate(items, start=1):
        if str(item.get("visual_src", "")).strip():
            continue
        target = visuals_dir / f"story-{index}-demo.png"
        Image.new("RGB", (1600, 1000), palette[index - 1]).save(target)
        item["visual_src"] = f"visuals/{target.name}"


def _verify_visual_resolution(items: list[dict]) -> None:
    for index, item in enumerate(items, start=1):
        src = str(item.get("visual_src", "")).strip()
        if not src:
            raise RuntimeError(f"Story {index} is missing visual_src.")

        path = OUT_DIR / src
        if not path.exists():
            raise RuntimeError(f"Story {index} visual is missing: {src}")

        with Image.open(path) as image:
            width, height = image.size

        if max(width, height) < 1400 or min(width, height) < 900:
            raise RuntimeError(
                f"Story {index} visual below production minimum: "
                f"{width}x{height}; require long edge >=1400 and short edge >=900."
            )


def _derive_summary_lede(brief: dict) -> str:
    return _clip_text(str(brief.get("summary_lede", "")).strip(), 240)


def _derive_department_digest(brief: dict) -> list[dict]:
    result = []
    for item in brief["department_digest"]:
        departments = item.get("departments", [])
        if isinstance(departments, list):
            departments_text = " • ".join(str(x).strip() for x in departments if str(x).strip())
        else:
            departments_text = str(departments).strip()
        result.append(
            {
                "group": _clip_text(item.get("group", ""), 52),
                "title": _clip_text(item.get("title", ""), 62),
                "detail": _clip_text(item.get("detail", ""), 170),
                "departments": _clip_text(departments_text, 72),
            }
        )
    return result


def _derive_regional_pulse(brief: dict) -> list[dict]:
    counts = {
        "MIỀN BẮC": sum(1 for item in brief["items"] if item.get("region") == "MIỀN BẮC"),
        "MIỀN TRUNG": sum(1 for item in brief["items"] if item.get("region") == "MIỀN TRUNG"),
    }
    result = []
    for pulse in brief["regional_pulse"]:
        region = str(pulse.get("region", "")).strip()
        result.append(
            {
                "region": region,
                "count": counts.get(region, 0),
                "title": _clip_text(pulse.get("title", ""), 72),
                "detail": _clip_text(pulse.get("detail", ""), 150),
            }
        )
    return result


def _derive_watchpoints(brief: dict) -> list[dict]:
    return [
        {
            "label": _clip_text(point.get("label", ""), 24),
            "title": _clip_text(point.get("title", ""), 58),
            "detail": _clip_text(point.get("detail", ""), 130),
        }
        for point in brief["watchpoints"]
    ]


def _assert_locked_geometry(page, html_name: str) -> None:
    rules = LOCKED_GEOMETRY[html_name]
    for selector, expected in rules.items():
        boxes = page.locator(selector).all()
        if not boxes:
            raise RuntimeError(
                f"Locked geometry selector missing in {html_name}: {selector}"
            )

        box = boxes[0].bounding_box()
        if not box:
            raise RuntimeError(
                f"Unable to read locked geometry in {html_name}: {selector}"
            )

        for key, value in expected.items():
            actual = round(box[key])
            if abs(actual - value) > 1:
                raise RuntimeError(
                    f"Locked geometry drift in {html_name} {selector} "
                    f"{key}: {actual} != {value}"
                )

    footer_box = page.locator(".footer").bounding_box()
    if footer_box is None:
        raise RuntimeError(f"Footer missing in {html_name}")
    footer_bottom = round(footer_box["y"] + footer_box["height"])
    if footer_bottom != CSS_SIZE[1]:
        raise RuntimeError(
            f"Footer bottom drift in {html_name}: "
            f"{footer_bottom} != {CSS_SIZE[1]}"
        )


def _downsample(src: Path, dst: Path, size: tuple[int, int]) -> None:
    with Image.open(src) as image:
        image = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        image.save(dst, format="PNG", optimize=True)


def render_brief(brief: dict) -> tuple[Path, Path, Path]:
    _verify_layout_lock()
    _verify_brand_asset()
    _validate_copy(brief)

    items = brief["items"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_demo_visuals(items)
    _verify_visual_resolution(items)

    shutil.copyfile(APPROVED_STYLE, OUT_DIR / "approved-editorial-style.css")
    shutil.copyfile(APPROVED_LOGO, OUT_DIR / "stacorp-logo.png")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["clean_note"] = _clean_note
    env.filters["clip_text"] = _clip_text

    context = {
        "brief": brief,
        "summary_lede": _derive_summary_lede(brief),
        "department_digest": _derive_department_digest(brief),
        "regional_pulse": _derive_regional_pulse(brief),
        "watchpoints": _derive_watchpoints(brief),
        "layout_version": APPROVED_LAYOUT_VERSION,
    }

    pages = [
        ("editorial_page1.html", OUT_DIR / "editorial_page1.html", PAGE1, items[:4]),
        ("editorial_page2.html", OUT_DIR / "editorial_page2.html", PAGE2, items[4:8]),
        ("editorial_page3.html", OUT_DIR / "editorial_page3.html", PAGE3, items),
    ]

    for template_name, html_path, _, page_items in pages:
        html = env.get_template(template_name).render(
            **context,
            items=page_items,
        )
        html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": CSS_SIZE[0], "height": CSS_SIZE[1]},
            device_scale_factor=RENDER_SCALE,
        )

        for template_name, html_path, png_path, _ in pages:
            page.goto(html_path.as_uri(), wait_until="networkidle")

            broken = page.evaluate(
                """() => Array.from(document.images)
                    .filter(img => !img.complete || img.naturalWidth === 0)
                    .map(img => img.getAttribute('src'))"""
            )
            if broken:
                browser.close()
                raise RuntimeError(
                    f"Broken image assets in {html_path.name}: {broken}"
                )

            overflow = page.evaluate(
                """() => ({
                    w: document.documentElement.scrollWidth,
                    h: document.documentElement.scrollHeight
                })"""
            )
            if overflow["w"] > CSS_SIZE[0] or overflow["h"] > CSS_SIZE[1]:
                browser.close()
                raise RuntimeError(
                    f"Layout overflow in {html_path.name}: {overflow}"
                )

            _assert_locked_geometry(page, template_name)

            hi_res = png_path.with_name(png_path.stem + "_2X.png")
            page.screenshot(path=str(hi_res), full_page=False)
            _downsample(hi_res, png_path, CSS_SIZE)
            teams_path = TEAMS_DIR / f"{png_path.stem}_TEAMS.png"
            _downsample(hi_res, teams_path, TEAMS_SIZE)
            print(
                f"Teams master: {teams_path} "
                f"({TEAMS_SIZE[0]}x{TEAMS_SIZE[1]}, {teams_path.stat().st_size} bytes)"
            )
            hi_res.unlink(missing_ok=True)

        browser.close()

    print(f"APPROVED_LAYOUT_VERSION={APPROVED_LAYOUT_VERSION}")
    print("LAYOUT_GEOMETRY_LOCK=PASS")
    return PAGE1, PAGE2, PAGE3
