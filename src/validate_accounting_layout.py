from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

from .render_accounting import render_accounting_brief

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample" / "accounting_brief.sample.json"
INCOMING = ROOT / "incoming" / "accounting" / "current"
VISUALS = INCOMING / "visuals"


def _make_visual(path: Path, index: int) -> None:
    random.seed(index)
    image = Image.new("RGB", (1600, 1000), (230, 237, 245))
    draw = ImageDraw.Draw(image)

    for _ in range(8000):
        x = random.randrange(1600)
        y = random.randrange(1000)
        radius = random.randrange(2, 9)
        color = (
            random.randrange(125, 230),
            random.randrange(145, 235),
            random.randrange(165, 245),
        )
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=color,
        )

    draw.rectangle((70, 70, 1530, 930), outline=(13, 48, 94), width=10)
    draw.rectangle((100, 760, 1500, 900), fill=(13, 48, 94))
    image.save(path, format="JPEG", quality=96, subsampling=0)

    if path.stat().st_size < 180000:
        raise RuntimeError(f"Demo visual {index} unexpectedly too small.")


def main() -> int:
    brief = json.loads(SAMPLE.read_text(encoding="utf-8"))
    VISUALS.mkdir(parents=True, exist_ok=True)

    for index, item in enumerate(brief["items"], start=1):
        target = VISUALS / f"story-{index}.jpg"
        _make_visual(target, index)
        item["visual_src"] = f"visuals/story-{index}.jpg"

    INCOMING.mkdir(parents=True, exist_ok=True)
    (INCOMING / "brief.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    pages = render_accounting_brief(brief)
    if len(pages) != 3:
        raise RuntimeError(f"Expected 3 pages, got {len(pages)}")

    for page in pages:
        if not page.exists() or page.stat().st_size < 100000:
            raise RuntimeError(f"Accounting QA page invalid: {page}")

    print("ACCOUNTING_VISUAL_V2_QA=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
