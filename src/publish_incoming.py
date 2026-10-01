from __future__ import annotations

import json
from pathlib import Path

from .publish_teams import publish_inline_images
from .render import render_brief
from .validate import validate_png
from .validate_source_visuals import prepare_source_visuals

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "current"


def _load_payload() -> dict:
    brief_path = INCOMING / "brief.json"
    if not brief_path.exists():
        raise RuntimeError("Missing incoming/current/brief.json")

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    items = brief.get("items", [])
    if len(items) != 8:
        raise RuntimeError("Incoming ChatGPT brief must contain exactly eight items.")

    return prepare_source_visuals(brief)


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
