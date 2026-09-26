from __future__ import annotations

import hashlib
import shutil
from email.utils import parsedate_to_datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
APPROVED_LOGO = ASSETS / "stacorp-logo.png"
APPROVED_LOGO_GIT_BLOB_SHA = "c650caf3be5b8e927a269602b5d66c1f366aea20"

OUT_DIR = Path("/tmp/stacorp-daily-brief")
PAGE1 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_1.png"
PAGE2 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_2.png"


def _verify_brand_asset() -> None:
    if not APPROVED_LOGO.exists():
        raise RuntimeError("Approved STACORP logo asset is missing.")

    data = APPROVED_LOGO.read_bytes()
    git_blob = b"blob " + str(len(data)).encode("ascii") + b"\\x00" + data
    digest = hashlib.sha1(git_blob).hexdigest()
    if digest != APPROVED_LOGO_GIT_BLOB_SHA:
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
    try:
        return parsedate_to_datetime(value).strftime("%d.%m.%Y")
    except Exception:
        return value[:24]


def render_brief(brief: dict) -> tuple[Path, Path]:
    if len(brief.get("items", [])) != 5:
        raise RuntimeError("V3 layout requires exactly five news items.")

    _verify_brand_asset()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATES / "style.css", OUT_DIR / "style.css")
    shutil.copyfile(APPROVED_LOGO, OUT_DIR / "stacorp-logo.png")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["source_date"] = _source_date

    brief = dict(brief)
    brief.setdefault("metrics", _metrics(brief["items"]))
    brief.setdefault("title", "ĐIỂM TIN CHO DOANH NGHIỆP STACORP")
    brief.setdefault("subtitle", "Thị trường • Dự án • Chi phí • Con người")
    brief.setdefault("impact_summary", _impact_summary(brief["items"]))

    pages = [
        ("page1.html", OUT_DIR / "page1.html", PAGE1, brief["items"][:3]),
        ("page2.html", OUT_DIR / "page2.html", PAGE2, brief["items"][3:]),
    ]

    for template_name, html_path, _, items in pages:
        html = env.get_template(template_name).render(brief=brief, items=items)
        html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1120, "height": 1400},
            device_scale_factor=1,
        )

        for _, html_path, png_path, _ in pages:
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
            if overflow["w"] > 1120 or overflow["h"] > 1400:
                browser.close()
                raise RuntimeError(f"Layout overflow in {html_path.name}: {overflow}")

            page.screenshot(path=str(png_path), full_page=False)

        browser.close()

    return PAGE1, PAGE2
