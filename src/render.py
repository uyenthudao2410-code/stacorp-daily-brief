from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUT_DIR = Path("/tmp/stacorp-daily-brief")
PAGE1 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_1.png"
PAGE2 = OUT_DIR / "STACORP_DAILY_BRIEF_PAGE_2.png"


def _metrics(items: list[dict]) -> list[dict]:
    buckets = [
        ("CƠ HỘI", lambda x: "Cơ hội" in x.get("category", "")),
        ("THỊ TRƯỜNG", lambda x: "Thị trường" in x.get("category", "")),
        (
            "CHI PHÍ",
            lambda x: "Chi phí" in x.get("category", "")
            or "Tài chính" in x.get("category", ""),
        ),
        ("CÔNG TRƯỜNG", lambda x: "Công trường" in x.get("category", "")),
    ]
    return [
        {"label": label, "value": str(sum(1 for item in items if pred(item)))}
        for label, pred in buckets
    ]


def render_brief(brief: dict) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATES / "style.css", OUT_DIR / "style.css")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )

    brief = dict(brief)
    brief.setdefault("metrics", _metrics(brief["items"]))
    brief.setdefault("title", "ĐIỂM TIN CHO DOANH NGHIỆP STACORP")
    brief.setdefault("subtitle", "Thị trường • Dự án • Chi phí • Con người")

    pages = [
        ("page1.html", OUT_DIR / "page1.html", PAGE1, brief["items"][:2]),
        ("page2.html", OUT_DIR / "page2.html", PAGE2, brief["items"][2:]),
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
