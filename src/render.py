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
PAGE1 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_1.png"
PAGE2 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_2.png"
CSS_SIZE = (1120, 1400)
RENDER_SCALE = 2


def _verify_brand_asset() -> None:
    if not APPROVED_LOGO.exists():
        raise RuntimeError("Approved STACORP logo asset is missing.")

    data = APPROVED_LOGO.read_bytes()
    git_blob = b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data
    digest = hashlib.sha1(git_blob).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    if (
        digest != APPROVED_LOGO_GIT_BLOB_SHA
        or sha256 != APPROVED_LOGO_SHA256
    ):
        raise RuntimeError(
            "STACORP logo integrity check failed. "
            "Refusing to render with an unapproved or modified logo."
        )


def _metrics(items: list[dict]) -> list[dict]:
    specs = [
        (
            "CƠ HỘI",
            "Dự án, khách hàng tiềm năng",
            "opportunity",
            lambda x: "Cơ hội" in x.get("category", ""),
        ),
        (
            "THỊ TRƯỜNG",
            "Xu hướng, chính sách, dòng vốn",
            "market",
            lambda x: "Thị trường" in x.get("category", ""),
        ),
        (
            "CHI PHÍ",
            "Vật liệu, giá cả, dòng tiền",
            "cost",
            lambda x: "Chi phí" in x.get("category", "")
            or "Tài chính" in x.get("category", ""),
        ),
        (
            "CÔNG TRƯỜNG",
            "Tiến độ, an toàn, con người",
            "site",
            lambda x: "Công trường" in x.get("category", "")
            or "Con người" in x.get("category", ""),
        ),
    ]
    return [
        {
            "label": label,
            "hint": hint,
            "tone": tone,
            "value": str(sum(1 for item in items if pred(item))),
        }
        for label, hint, tone, pred in specs
    ]


def _impact_summary(items: list[dict]) -> list[dict]:
    summary: list[dict] = []
    seen: set[str] = set()

    for item in items:
        category = item.get("category", "")
        key = category.split("&")[0].strip()
        if key in seen:
            continue
        seen.add(key)
        summary.append(
            {
                "category": key,
                "note": item.get("note", ""),
                "impact": item.get("impact", "THEO DÕI"),
            }
        )
        if len(summary) == 3:
            break

    return summary


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
    value = str(value or "").strip()
    return re.sub(
        r"^STACORP\s+cần\s+lưu\s+ý\s*:\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )


def _headline_size(value: str, kind: str) -> str:
    n = len(str(value or "").strip())

    if kind == "hero":
        return "lg" if n <= 65 else ("md" if n <= 80 else "sm")

    if kind == "compact":
        return "lg" if n <= 60 else ("md" if n <= 78 else "sm")

    return "lg" if n <= 62 else ("md" if n <= 82 else "sm")


def _action_departments(items: list[dict]) -> list[str]:
    priority: list[str] = []
    seen: set[str] = set()

    for item in items:
        if item.get("impact") != "CAO":
            continue

        for department in item.get("departments", []):
            if department not in seen:
                seen.add(department)
                priority.append(department)

            if len(priority) == 5:
                return priority

    return priority


def _validate_copy(items: list[dict]) -> None:
    if len(items) != 5:
        raise RuntimeError("V4 layout requires exactly five news items.")

    if sum(1 for item in items if item.get("impact") == "CAO") > 3:
        raise RuntimeError("V4 layout allows at most three CAO items.")

    for index, item in enumerate(items, start=1):
        headline = str(item.get("headline", "")).strip()
        facts = item.get("facts", [])
        note = str(item.get("note", "")).strip()
        departments = item.get("departments", [])

        if len(facts) != 2:
            raise RuntimeError(f"Story {index} must contain exactly two facts.")

        if not 2 <= len(departments) <= 5:
            raise RuntimeError(
                f"Story {index} must contain 2-5 departments."
            )

        limits = {
            1: (95, 190, 220),
            2: (90, 175, 190),
            3: (90, 175, 190),
            4: (100, 220, 230),
            5: (100, 220, 230),
        }[index]

        headline_limit, fact_limit, note_limit = limits

        if len(headline) > headline_limit:
            raise RuntimeError(
                f"Story {index} headline is too long for V4 "
                f"({len(headline)}>{headline_limit})."
            )

        for fact_index, fact in enumerate(facts, start=1):
            fact_text = str(fact)
            if len(fact_text) > fact_limit:
                raise RuntimeError(
                    f"Story {index} fact {fact_index} is too long for V4 "
                    f"({len(fact_text)}>{fact_limit})."
                )

        if len(note) > note_limit:
            raise RuntimeError(
                f"Story {index} note is too long for V4 "
                f"({len(note)}>{note_limit})."
            )


def _ensure_demo_visuals(items: list[dict]) -> None:
    """Provide deterministic placeholders only for demo/sample renders.

    Production delivery already fails earlier in publish_incoming.py when any
    story visual is missing, so this compatibility path is only reached by
    the repository's deterministic CI demo payload.
    """
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
        Image.new("RGB", (1400, 900), palette[index - 1]).save(
            target,
            format="PNG",
            optimize=True,
        )
        item["visual_src"] = f"visuals/{target.name}"


def _verify_visual_resolution(items: list[dict]) -> None:
    for index, item in enumerate(items, start=1):
        src = str(item.get("visual_src", "")).strip()
        if not src:
            raise RuntimeError(f"Story {index} is missing visual_src.")

        path = OUT_DIR / src
        if not path.exists():
            raise RuntimeError(f"Story {index} visual is missing: {src}")

        with Image.open(path) as img:
            width, height = img.size

        long_edge = max(width, height)
        short_edge = min(width, height)

        if long_edge < 1100 or short_edge < 650:
            raise RuntimeError(
                f"Story {index} visual is below V4 minimum resolution: "
                f"{width}x{height}; require long edge >=1100 "
                "and short edge >=650."
            )


def _downsample(src: Path, dst: Path) -> None:
    with Image.open(src) as img:
        img = img.convert("RGB")
        img = img.resize(CSS_SIZE, Image.Resampling.LANCZOS)
        img.save(dst, format="PNG", optimize=True)


def render_brief(brief: dict) -> tuple[Path, Path]:
    items = brief.get("items", [])

    _validate_copy(items)
    _verify_brand_asset()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_demo_visuals(items)
    _verify_visual_resolution(items)
    shutil.copyfile(TEMPLATES / "style.css", OUT_DIR / "style.css")
    shutil.copyfile(APPROVED_LOGO, OUT_DIR / "stacorp-logo.png")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["source_date"] = _source_date
    env.filters["clean_note"] = _clean_note
    env.filters["headline_size"] = _headline_size

    brief = dict(brief)
    brief.setdefault("metrics", _metrics(items))
    brief.setdefault(
        "title",
        "ĐIỂM TIN CHO DOANH NGHIỆP STACORP",
    )
    brief.setdefault(
        "subtitle",
        "Thị trường • Dự án • Chi phí • Con người",
    )
    brief.setdefault("impact_summary", _impact_summary(items))
    brief.setdefault(
        "action_departments",
        _action_departments(items),
    )

    pages = [
        (
            "page1.html",
            OUT_DIR / "page1.html",
            PAGE1,
            items[:3],
        ),
        (
            "page2.html",
            OUT_DIR / "page2.html",
            PAGE2,
            items[3:],
        ),
    ]

    for template_name, html_path, _, page_items in pages:
        html = env.get_template(template_name).render(
            brief=brief,
            items=page_items,
        )
        html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={
                "width": CSS_SIZE[0],
                "height": CSS_SIZE[1],
            },
            device_scale_factor=RENDER_SCALE,
        )

        for _, html_path, png_path, _ in pages:
            page.goto(
                html_path.as_uri(),
                wait_until="networkidle",
            )

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
            if (
                overflow["w"] > CSS_SIZE[0]
                or overflow["h"] > CSS_SIZE[1]
            ):
                browser.close()
                raise RuntimeError(
                    f"Layout overflow in {html_path.name}: {overflow}"
                )

            hi_res = png_path.with_name(
                png_path.stem + "_2X.png"
            )
            page.screenshot(
                path=str(hi_res),
                full_page=False,
            )
            _downsample(hi_res, png_path)
            hi_res.unlink(missing_ok=True)

        browser.close()

    return PAGE1, PAGE2
