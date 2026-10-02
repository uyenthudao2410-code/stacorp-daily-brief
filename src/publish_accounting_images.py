from __future__ import annotations

import base64
import html
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .publish_accounting_brief import _clean, _load_config, _validate_brief
from .publish_teams import _prepare_teams_jpeg, refresh_access_token
from .render_accounting import render_accounting_brief

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "accounting" / "current" / "brief.json"
GRAPH = "https://graph.microsoft.com/v1.0"

QA_TEAM_ID = "c5bfff4c-a940-464e-a199-db0a169d230b"
QA_CHANNEL_ID = "19:YNeQ_V26FnwoIYtdH_W6imrVXAxwRWXpUfPi2W76CnQ1@thread.tacv2"


def _target(cfg: dict) -> tuple[str, str, str]:
    mode = os.getenv("ACCOUNTING_TARGET_MODE", "PRODUCTION").strip().upper()
    if mode == "QA_GENERAL":
        return QA_TEAM_ID, QA_CHANNEL_ID, "QA_GENERAL"
    delivery = cfg["delivery"]
    return delivery["team_id"], delivery["channel_id"], "PRODUCTION"


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _sources_html(brief: dict) -> str:
    rows = []
    for index, item in enumerate(brief.get("items", []), start=1):
        links = []
        for source in item.get("sources", []):
            name = html.escape(_clean(source.get("name")))
            url = html.escape(_clean(source.get("url")), quote=True)
            links.append(f'<a href="{url}">{name}</a>')
        if links:
            rows.append(f"<li><strong>{index:02d}.</strong> " + " · ".join(links) + "</li>")
    return "<h3>Nguồn tham khảo</h3><ul>" + "".join(rows) + "</ul>"


def publish_images(brief: dict) -> str:
    cfg = _load_config()
    _validate_brief(brief, cfg)
    team_id, channel_id, mode = _target(cfg)
    pages = render_accounting_brief(brief)
    teams_pages = [
        _prepare_teams_jpeg(page, index)
        for index, page in enumerate(pages, start=1)
    ]

    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    subject = f"ĐIỂM TIN ĐIỀU HÀNH STACORP | {now.strftime('%d.%m.%Y')}"
    print(f"ACCOUNTING_TEAMS_SUBJECT_DATE={now.strftime('%d.%m.%Y')}")
    print(f"ACCOUNTING_TEAMS_SUBJECT_TIME={now.strftime('%H:%M')}")
    body = (
        f"<h2>{html.escape(subject)}</h2>"
        '<img src="../hostedContents/1/$value" width="900" alt="Trang 1"><br><br>'
        '<img src="../hostedContents/2/$value" width="900" alt="Trang 2"><br><br>'
        '<img src="../hostedContents/3/$value" width="900" alt="Trang 3"><br><br>'
        + _sources_html(brief)
    )
    payload = {
        "subject": subject,
        "body": {"contentType": "html", "content": body},
        "hostedContents": [
            {
                "@microsoft.graph.temporaryId": str(i),
                "contentBytes": _b64(page),
                "contentType": "image/jpeg",
            }
            for i, page in enumerate(teams_pages, start=1)
        ],
    }
    headers = {
        "Authorization": f"Bearer {refresh_access_token()}",
        "Content-Type": "application/json",
    }
    endpoint = f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages"
    with httpx.Client(timeout=90) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    message_id = _clean(data.get("id"))
    if not message_id:
        raise RuntimeError("Teams post succeeded without returning a message id.")

    print(f"ACCOUNTING_TARGET_MODE={mode}")
    print(f"ACCOUNTING_TEAM_ID={team_id}")
    print(f"ACCOUNTING_CHANNEL_ID={channel_id}")
    print(f"ACCOUNTING_BRIEF_TEAMS_MESSAGE_ID={message_id}")
    return message_id


def main() -> int:
    if not INCOMING.exists():
        raise RuntimeError("Missing incoming/accounting/current/brief.json")
    import json
    brief = json.loads(INCOMING.read_text(encoding="utf-8"))
    publish_images(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
