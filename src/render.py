from __future__ import annotations

import hashlib
import re
import shutil
from email.utils import parsedate_to_datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
APPROVED_LOGO = ASSETS / "stacorp-logo.png"
APPROVED_LOGO_GIT_BLOB_SHA = "2ffd30fd4c8774bdebb461f157ed6b41c04172be"
APPROVED_LOGO_SHA256 = "4fc97e9245c4513b9334a9659690e886aa4563ad892d3fe49f3d6322ba55046d"

OUT_DIR = Path("/tmp/stacorp-daily-brief")
PAGE = OUT_DIR / "STACORP_DAILY_BRIEF.png"
CSS_SIZE = (1080, 1350)
RENDER_SCALE = 2


def _verify_brand_asset() -> None:
    if not APPROVED_LOGO.exists():
        raise RuntimeError("Approved STACORP logo asset is missing.")
    data = APPROVED_LOGO.read_bytes()
    git_blob = b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data
    if hashlib.sha1(git_blob).hexdigest() != APPROVED_LOGO_GIT_BLOB_SHA:
        raise RuntimeError("STACORP logo git-blob integrity check failed.")
    if hashlib.sha256(data).hexdigest() != APPROVED_LOGO_SHA256:
        raise RuntimeError("STACORP logo SHA256 integrity check failed.")


def _source_date(value: str) -> str:
    if not value:
        return ""
    from datetime import datetime
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d.%m.%Y")
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(value).strftime("%d.%m.%Y")
    except Exception:
        return value[:24]


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


def _validate_copy(items: list[dict]) -> None:
    if len(items) != 5:
        raise RuntimeError("V8 requires exactly five news items.")
    if sum(1 for item in items if item.get("impact") == "CAO") > 3:
        raise RuntimeError("V8 allows at most three CAO items.")
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
        Image.new("RGB", (1536, 1024), palette[index - 1]).save(target)
        item["visual_src"] = f"visuals/{target.name}"


def _verify_visuals(items: list[dict]) -> None:
    for index, item in enumerate(items, start=1):
        path = OUT_DIR / str(item.get("visual_src", ""))
        if not path.exists():
            raise RuntimeError(f"Story {index} visual is missing.")
        with Image.open(path) as image:
            width, height = image.size
        if max(width, height) < 1400 or min(width, height) < 900:
            raise RuntimeError(
                f"Story {index} visual below V8 minimum: {width}x{height}; "
                "require long edge >=1400 and short edge >=900."
            )


def render_brief(brief: dict) -> tuple[Path]:
    items = brief.get("items", [])
    _validate_copy(items)
    _verify_brand_asset()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_demo_visuals(items)
    _verify_visuals(items)

    shutil.copyfile(TEMPLATES / "style-v8.css", OUT_DIR / "style-v8.css")
    shutil.copyfile(APPROVED_LOGO, OUT_DIR / "stacorp-logo.png")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["source_date"] = _source_date
    env.filters["clean_note"] = _clean_note
    env.filters["clip_text"] = _clip_text

    html_path = OUT_DIR / "cover_v8.html"
    html = env.get_template("cover_v8.html").render(brief=brief)
    html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": CSS_SIZE[0], "height": CSS_SIZE[1]},
            device_scale_factor=RENDER_SCALE,
        )
        page.goto(html_path.as_uri(), wait_until="networkidle")

        broken = page.evaluate(
            """() => Array.from(document.images)
                .filter(img => !img.complete || img.naturalWidth === 0)
                .map(img => img.getAttribute('src'))"""
        )
        if broken:
            browser.close()
            raise RuntimeError(f"Broken image assets: {broken}")

        overflow = page.evaluate(
            """() => ({
                w: document.documentElement.scrollWidth,
                h: document.documentElement.scrollHeight
            })"""
        )
        if overflow["w"] > CSS_SIZE[0] or overflow["h"] > CSS_SIZE[1]:
            browser.close()
            raise RuntimeError(f"Layout overflow: {overflow}")

        hi_res = PAGE.with_name(PAGE.stem + "_2X.png")
        page.screenshot(path=str(hi_res), full_page=False)
        browser.close()

    with Image.open(hi_res) as image:
        image = image.convert("RGB").resize(CSS_SIZE, Image.Resampling.LANCZOS)
        image.save(PAGE, format="PNG", optimize=True)
    hi_res.unlink(missing_ok=True)

    return (PAGE,)
