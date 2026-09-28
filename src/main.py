from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .collect_news import collect_candidates
from .generate_visuals import generate_visuals
from .publish_teams import publish_inline_images
from .rank_news import select_brief
from .render import render_brief
from .state import remember_published
from .validate import validate_png

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "sample" / "brief.sample.json"


def _today_label() -> str:
    return datetime.now().strftime("%d.%m.%Y")


def _load_demo() -> dict:
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    data["date"] = _today_label()
    return data


def _live_brief() -> dict:
    candidates = collect_candidates()
    print(f"Collected {len(candidates)} unique candidates.")
    if len(candidates) < 20:
        raise RuntimeError("Too few news candidates; refusing to publish.")

    selection = select_brief(candidates)
    if not selection.get("publish"):
        print("Editorial gate: fewer than five strong items. Nothing published.")
        return {"publish": False}

    return {
        "publish": True,
        "date": _today_label(),
        "title": "ĐIỂM TIN CHO DOANH NGHIỆP STACORP",
        "subtitle": "Thị trường • Dự án • Chi phí • Con người",
        "action_today": selection.get("action_today", ""),
        "items": selection["items"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--visuals", action="store_true")
    args = parser.parse_args()

    brief = _load_demo() if args.demo else _live_brief()
    if brief.get("publish") is False:
        return 0

    if args.visuals:
        brief = generate_visuals(brief)

    pages = render_brief(brief)
    for page in pages:
        validate_png(page)
        print(f"Rendered: {page} ({page.stat().st_size} bytes)")

    if args.publish:
        message_id = publish_inline_images(*pages, brief)
        print(f"TEAMS_MESSAGE_ID={message_id}")
        if not args.demo:
            remember_published(brief["items"])
    else:
        print("Dry run complete. Nothing was posted to Teams.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
