from __future__ import annotations

import json
import shutil
from pathlib import Path

from .publish_teams import publish_inline_images
from .render import render_brief
from .validate import validate_png

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "current"
OUT_VISUALS = Path("/tmp/stacorp-daily-brief/visuals")


def _load_payload() -> dict:
    brief_path = INCOMING / "brief.json"
    if not brief_path.exists():
        raise RuntimeError("Missing incoming/current/brief.json")

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    items = brief.get("items", [])
    if len(items) != 5:
        raise RuntimeError("Incoming ChatGPT brief must contain exactly five items.")

    OUT_VISUALS.mkdir(parents=True, exist_ok=True)
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
        shutil.copyfile(source, target)
        item["visual_src"] = f"visuals/{target.name}"
        enriched.append(item)

    brief["items"] = enriched
    return brief


def main() -> int:
    brief = _load_payload()
    pages = render_brief(brief)

    for page in pages:
        validate_png(page)
        print(f"Rendered: {page} ({page.stat().st_size} bytes)")

    message_id = publish_inline_images(*pages, brief)
    print(f"TEAMS_MESSAGE_ID={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
