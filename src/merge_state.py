from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "published_hashes.json"


def _item_id(item: dict) -> str:
    existing = str(item.get("candidate_id", "")).strip()
    if existing:
        return existing

    raw = " | ".join(
        [
            str(item.get("headline", "")),
            str(item.get("source", "")),
            str(item.get("url", "")),
        ]
    ).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m src.merge_state <brief-json>")

    brief = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
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
    for item in brief.get("items", []):
        iid = _item_id(item)
        if iid in known:
            continue

        kept.append(
            {
                "id": iid,
                "date": today.isoformat(),
                "headline": str(item.get("headline", ""))[:300],
                "source": str(item.get("source", ""))[:120],
                "url": str(item.get("url", ""))[:1000],
            }
        )
        known.add(iid)

    STATE_PATH.write_text(
        json.dumps({"items": kept}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
