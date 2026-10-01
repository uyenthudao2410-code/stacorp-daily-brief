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

APPROVED_LAYOUT_VERSION = "STACORP_EDITORIAL_3PAGE_FINAL_V2"
APPROVED_PAGE1 = TEMPLATES / "editorial_page1.html"
APPROVED_PAGE2 = TEMPLATES / "editorial_page2.html"
APPROVED_PAGE3 = TEMPLATES / "editorial_page3.html"
APPROVED_STYLE = TEMPLATES / "approved-editorial-style.css"
APPROVED_PAGE1_BLOB_SHA = "ce1d85f45184653ad349aa1efac5160d93256af2"
APPROVED_PAGE2_BLOB_SHA = "058b2f0f721e11577807515622a97ce2b72a2422"
APPROVED_PAGE3_BLOB_SHA = "7927990f492de9597043fc65b95d094f9aefcccf"
APPROVED_STYLE_BLOB_SHA = "c6f870dcaa7071b817757d1f125c7c25669742f8"

APPROVED_LOGO = ASSETS / "stacorp-logo.png"
APPROVED_LOGO_GIT_BLOB_SHA = "2ffd30fd4c8774bdebb461f157ed6b41c04172be"
APPROVED_LOGO_SHA256 = "4fc97e9245c4513b9334a9659690e886aa4563ad892d3fe49f3d6322ba55046d"

OUT_DIR = Path("/tmp/stacorp-daily-brief")
PAGE1 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_1.png"
PAGE2 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_2.png"
PAGE3 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_3.png"
CSS_SIZE = (1080, 1620)
TEAMS_SIZE = (1440, 2160)
RENDER_SCALE = 2
TEAMS_DIR = OUT_DIR / "teams"

LOCKED_GEOMETRY = {
    "editorial_page1.html": {
        ".page": {"width": 1080, "height": 1620},
        ".masthead": {"height": 164},
        ".logo": {"width": 92, "height": 92},
        ".hero-image-wrap": {"height": 430},
        ".mini-card": {"height": 455},
        ".footer": {"height": 98},
    },
    "editorial_page2.html": {
        ".page": {"width": 1080, "height": 1620},
        ".masthead": {"height": 164},
        ".logo": {"width": 92, "height": 92},
        ".wide-image-wrap": {"height": 385},
        ".split-main": {"height": 390},
        ".footer": {"height": 98},
    },
    "editorial_page3.html": {
        ".page": {"width": 1080, "height": 1620},
        ".masthead": {"height": 164},
        ".logo": {"width": 92, "height": 92},
        ".summary-title-row": {"height": 88},
        ".highlight-card": {"height": 122},
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
    if len(items) != 5:
        raise RuntimeError("Approved layout requires exactly five news items.")

    if sum(1 for item in items if item.get("impact") == "CAO") > 3:
        raise RuntimeError("Approved layout allows at most three CAO items.")

    allowed = {"CAO", "TRUNG BÌNH", "THEO DÕI"}
    for index, item in enumerate(items, start=1):
        if item.get("impact") not in allowed:
            raise RuntimeError(f"Story {index} has invalid impact.")
        if len(item.get("facts", [])) != 2:
            raise RuntimeError(f"Story {index} must contain exactly two facts.")
        if not 2 <= len(item.get("departments", [])) <= 5:
            raise RuntimeError(f"Story {index} must contain 2-5 departments.")
        if not str(item.get("headline", "")).strip():
            raise RuntimeError(f"Story {index} headline is empty.")

    executive_actions = brief.get("executive_actions", [])
    if executive_actions and len(executive_actions) != 3:
        raise RuntimeError(
            "executive_actions must contain exactly three items when provided."
        )


def _ensure_demo_visuals(items: list[dict]) -> None:
    visuals_dir = OUT_DIR / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    palette = [
        (218, 234, 251),
        (225, 239, 248),
        (232, 241, 250),
        (221, 235, 247),
        (227, 238, 246),
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


def _derive_executive_actions(brief: dict) -> list[dict]:
    supplied = brief.get("executive_actions", [])
    if supplied:
        return [
            {
                "title": _clip_text(str(item.get("title", "")).strip(), 74),
                "detail": _clip_text(str(item.get("detail", "")).strip(), 135),
            }
            for item in supplied[:3]
        ]

    items = brief["items"]
    fallbacks = [
        (
            "Bám sát cơ hội đầu tư và khách hàng mới",
            _clean_note(items[0].get("note", "")),
        ),
        (
            "Chủ động chi phí, tiến độ và chuỗi cung ứng",
            _clean_note(items[3].get("note", "")),
        ),
        (
            "Siết quản trị rủi ro và an toàn công trường",
            _clean_note(items[4].get("note", "")),
        ),
    ]
    return [
        {"title": title, "detail": _clip_text(detail, 135)}
        for title, detail in fallbacks
    ]


def _derive_summary_lede(brief: dict) -> str:
    supplied = str(brief.get("summary_lede", "")).strip()
    if supplied:
        return _clip_text(supplied, 210)

    return (
        f"Từ 5 diễn biến nổi bật ngày {brief.get('date', '')}, STACORP cập nhật "
        "những thông tin chính, giúp doanh nghiệp nắm bắt cơ hội và chủ động "
        "ứng phó rủi ro."
    )


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
        "executive_actions": _derive_executive_actions(brief),
        "layout_version": APPROVED_LAYOUT_VERSION,
    }

    pages = [
        ("editorial_page1.html", OUT_DIR / "editorial_page1.html", PAGE1, items[:3]),
        ("editorial_page2.html", OUT_DIR / "editorial_page2.html", PAGE2, items[3:]),
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
