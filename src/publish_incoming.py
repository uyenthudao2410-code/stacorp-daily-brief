from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageFilter

from .publish_teams import publish_inline_images
from .render import render_brief
from .validate import validate_png

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "current"
OUT_VISUALS = Path("/tmp/stacorp-daily-brief/visuals")
LEGACY_TEST_MARKER = INCOMING / ".legacy_test_upscale"


def _prepare_visual(source: Path, target: Path, *, allow_test_upscale: bool) -> None:
    if not allow_test_upscale:
        shutil.copyfile(source, target)
        return

    with Image.open(source) as image:
        width, height = image.size
        long_edge = max(width, height)
        short_edge = min(width, height)

        if long_edge >= 1100 and short_edge >= 650:
            shutil.copyfile(source, target)
            return

        scale = max(1280 / long_edge, 650 / short_edge)
        new_size = (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )

        prepared = image.convert("RGB").resize(
            new_size,
            Image.Resampling.LANCZOS,
        )
        prepared = prepared.filter(
            ImageFilter.UnsharpMask(radius=1.15, percent=125, threshold=3)
        )

        suffix = target.suffix.lower()
        if suffix == ".webp":
            prepared.save(target, format="WEBP", quality=88, method=6)
        elif suffix in {".jpg", ".jpeg"}:
            prepared.save(target, format="JPEG", quality=92, optimize=True)
        else:
            prepared.save(target, format="PNG", optimize=True)

        print(
            "LEGACY_TEST_UPSCALE "
            f"{source.name}: {width}x{height} -> "
            f"{new_size[0]}x{new_size[1]}"
        )


def _load_payload() -> dict:
    brief_path = INCOMING / "brief.json"
    if not brief_path.exists():
        raise RuntimeError("Missing incoming/current/brief.json")

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    items = brief.get("items", [])
    if len(items) != 5:
        raise RuntimeError("Incoming ChatGPT brief must contain exactly five items.")

    OUT_VISUALS.mkdir(parents=True, exist_ok=True)
    allow_test_upscale = LEGACY_TEST_MARKER.exists()
    if allow_test_upscale:
        print(
            "TEST-ONLY legacy visual upscale is enabled by "
            "incoming/current/.legacy_test_upscale"
        )

    enriched = []
    for index, item in enumerate(items, start=1):
        item = dict(item)
        candidates = [
            INCOMING / f"story-{index}.jpg",
            INCOMING / f"story-{index}.jpeg",
            INCOMING / f"story-{index}.png",
            INCOMING / f"story-{index}.webp",
        ]
        source = next((p for p in candidates if p.exists()), None)
        if source is None:
            raise RuntimeError(f"Missing visual for story {index}.")

        ext = source.suffix.lower()
        target = OUT_VISUALS / f"story-{index}{ext}"
        _prepare_visual(
            source,
            target,
            allow_test_upscale=allow_test_upscale,
        )
        item["visual_src"] = f"visuals/{target.name}"
        enriched.append(item)

    brief["items"] = enriched
    return brief


def main() -> int:
    brief = _load_payload()

    page1, page2 = render_brief(brief)
    validate_png(page1)
    validate_png(page2)

    print(f"Rendered: {page1} ({page1.stat().st_size} bytes)")
    print(f"Rendered: {page2} ({page2.stat().st_size} bytes)")

    message_id = publish_inline_images(page1, page2, brief)
    print(f"TEAMS_MESSAGE_ID={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
