from __future__ import annotations

import json
import shutil
from pathlib import Path

from .render import render_brief
from .validate import validate_png
from .validate_source_visuals import prepare_source_visuals

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "current"
TMP_ROOT = Path("/tmp/stacorp-daily-brief")
QA_OUT = ROOT / "qa" / "output"


def main() -> int:
    brief_path = INCOMING / "brief.json"
    if not brief_path.exists():
        raise RuntimeError("Missing incoming/current/brief.json")

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    brief = prepare_source_visuals(brief)
    pages = render_brief(brief)

    QA_OUT.mkdir(parents=True, exist_ok=True)

    for index, page in enumerate(pages, start=1):
        validate_png(page)
        source = TMP_ROOT / "teams" / f"{page.stem}_TEAMS.png"
        if not source.exists():
            raise RuntimeError(f"Missing QA master: {source}")
        target = QA_OUT / f"STACORP_V3_QA_PAGE_{index}.png"
        shutil.copyfile(source, target)
        print(f"QA_PAGE_{index}={target} ({target.stat().st_size} bytes)")

    (QA_OUT / "brief.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("QA_RENDER_ONLY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
