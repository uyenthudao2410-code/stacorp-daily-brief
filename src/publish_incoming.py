from __future__ import annotations

import json
from pathlib import Path

import httpx
from PIL import Image

from .publish_teams import publish_inline_images
from .render import render_brief
from .validate import validate_png

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "current"
OUT_VISUALS = Path("/tmp/stacorp-daily-brief/visuals")


def main() -> int:
    brief = json.loads((INCOMING / "brief.json").read_text(encoding="utf-8"))
    cfg = json.loads((INCOMING / "approved-test.json").read_text(encoding="utf-8"))

    OUT_VISUALS.mkdir(parents=True, exist_ok=True)
    enriched = []

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        for index, (item, url) in enumerate(
            zip(brief["items"], cfg["story_urls"], strict=True),
            start=1,
        ):
            target = OUT_VISUALS / f"story-{index}.png"
            response = client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)

            with Image.open(target) as image:
                print(
                    f"FINAL_LOCK_TEST_SOURCE story-{index}: "
                    f"{image.width}x{image.height} "
                    f"{target.stat().st_size} bytes"
                )

            item = dict(item)
            item["visual_src"] = f"visuals/{target.name}"
            enriched.append(item)

    brief["items"] = enriched
    pages = render_brief(brief)

    for page in pages:
        validate_png(page)
        print(f"Rendered: {page} ({page.stat().st_size} bytes)")

    message_id = publish_inline_images(*pages, brief)
    print(f"TEAMS_MESSAGE_ID={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
