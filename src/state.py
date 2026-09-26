from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "published_hashes.json"


def remember_published(items: list[dict]) -> None:
    existing = {"items": []}
    if STATE_PATH.exists():
        existing = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    today = date.today()
    cutoff = today - timedelta(days=120)
    kept = []

    for item in existing.get("items", []):
        try:
            if date.fromisoformat(item.get("date", "")) >= cutoff:
                kept.append(item)
        except ValueError:
            continue

    known = {x["id"] for x in kept}
    for item in items:
        cid = item["candidate_id"]
        if cid not in known:
            kept.append({"id": cid, "date": today.isoformat()})
            known.add(cid)

    STATE_PATH.write_text(
        json.dumps({"items": kept}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
