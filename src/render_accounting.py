from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from .publish_accounting_brief import _load_config, _validate_brief

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
OUT = Path("/tmp/stacorp-daily-brief")
TEAMS = OUT / "teams"
CSS_SIZE = (1080, 1620)
TEAMS_SIZE = (1200, 1800)
SCALE = 2

PAGES = (
    OUT / "STACORP_ACCOUNTING_BRIEF_PAGE_1.png",
    OUT / "STACORP_ACCOUNTING_BRIEF_PAGE_2.png",
    OUT / "STACORP_ACCOUNTING_BRIEF_PAGE_3.png",
)


def _downsample(src: Path, dst: Path, size: tuple[int, int]) -> None:
    with Image.open(src) as image:
        image = image.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        image.save(dst, format="PNG", optimize=True)


def render_accounting_brief(brief: dict) -> tuple[Path, Path, Path]:
    cfg = _load_config()
    _validate_brief(brief, cfg)

    OUT.mkdir(parents=True, exist_ok=True)
    TEAMS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATES / "accounting-style.css", OUT / "accounting-style.css")
    shutil.copyfile(ASSETS / "stacorp-logo.png", OUT / "stacorp-logo.png")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
    )

    specs = [
        ("accounting_page1.html", PAGES[0], {"items": brief["items"][:3]}),
        (
            "accounting_page2.html",
            PAGES[1],
            {"items": brief["items"][3:], "offset": 3},
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
                raise RuntimeError(f"Broken image assets in {html_path.name}: {broken}")

            overflow = page.evaluate(
                """() => ({
                  w: document.documentElement.scrollWidth,
                  h: document.documentElement.scrollHeight
                })"""
            )
            if overflow["w"] > CSS_SIZE[0] or overflow["h"] > CSS_SIZE[1]:
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

    return PAGES
