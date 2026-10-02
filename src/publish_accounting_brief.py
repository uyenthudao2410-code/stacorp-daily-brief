from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .publish_teams import refresh_access_token

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "accounting_brief.json"
INCOMING = ROOT / "incoming" / "accounting" / "current" / "brief.json"
GRAPH = "https://graph.microsoft.com/v1.0"

LOCKED_TEAM_ID = "0bff3781-b351-4ff5-a611-94cbe315f4b0"
LOCKED_CHANNEL_ID = (
    "19:OEyXLFXSzP7bezGLJ-mlRecQ3FcMLdK9vfoCA7Iqq141@thread.tacv2"
)

GROUPS = (
    "KẾ TOÁN · THUẾ · TÀI CHÍNH",
    "PHÁP LÝ · CHÍNH SÁCH DOANH NGHIỆP",
    "NHÂN SỰ · THỊ TRƯỜNG LAO ĐỘNG",
)


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_url(value: object) -> str:
    url = _clean(value)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Invalid source URL: {url!r}")
    return html.escape(url, quote=True)


def _load_config() -> dict:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    delivery = cfg.get("delivery", {})
    if delivery.get("email_enabled") is not False:
        raise RuntimeError("Accounting brief must remain Teams-only; email is disabled.")
    if delivery.get("teams_enabled") is not True:
        raise RuntimeError("Teams delivery must remain enabled.")
    if delivery.get("team_id") != LOCKED_TEAM_ID:
        raise RuntimeError("Accounting brief team_id does not match locked target.")
    if delivery.get("channel_id") != LOCKED_CHANNEL_ID:
        raise RuntimeError("Accounting brief channel_id does not match locked target.")
    return cfg


def _validate_date(value: object) -> str:
    text = _clean(value)
    try:
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError as exc:
        raise RuntimeError("brief.date must use dd.mm.yyyy") from exc
    return text


def _validate_brief(brief: dict, cfg: dict) -> None:
    editorial = cfg["editorial"]
    items = brief.get("items", [])
    highlights = brief.get("highlights", [])
    impacts = brief.get("impacts", [])
    actions = brief.get("actions", [])

    _validate_date(brief.get("date"))
    if not _clean(brief.get("window")):
        raise RuntimeError("brief.window is required.")
    if not _clean(brief.get("summary")):
        raise RuntimeError("brief.summary is required.")

    min_items = int(editorial["target_items_min"])
    max_items = int(editorial["target_items_max"])
    if not min_items <= len(items) <= max_items:
        raise RuntimeError(f"Accounting brief requires {min_items}-{max_items} items.")

    if len(highlights) != int(editorial["highlights_count"]):
        raise RuntimeError("Accounting brief requires exactly 3 highlights.")

    if not (
        int(editorial["impact_items_min"])
        <= len(impacts)
        <= int(editorial["impact_items_max"])
    ):
        raise RuntimeError("Accounting brief requires 4-6 STACORP impact bullets.")

    if not (
        int(editorial["actions_items_min"])
        <= len(actions)
        <= int(editorial["actions_items_max"])
    ):
        raise RuntimeError("Accounting brief requires 1-5 action bullets.")

    for index, item in enumerate(items, start=1):
        category = _clean(item.get("category"))
        if category not in GROUPS:
            raise RuntimeError(f"Item {index} has unsupported category: {category!r}")

        title = _clean(item.get("title"))
        if not title:
            raise RuntimeError(f"Item {index} is missing title.")

        visual_src = _clean(item.get("visual_src"))
        qa_mode = os.getenv("ACCOUNTING_TARGET_MODE", "").strip().upper() == "QA_GENERAL"
        if not visual_src and not qa_mode:
            raise RuntimeError(f"Item {index} is missing visual_src.")
        if visual_src:
            visual_path = Path(visual_src)
            if visual_path.is_absolute() or ".." in visual_path.parts:
                raise RuntimeError(f"Item {index} has unsafe visual_src: {visual_src!r}.")

        facts = item.get("facts", [])
        if not 2 <= len(facts) <= 3:
            raise RuntimeError(f"Item {index} must contain 2-3 facts.")

        sources = item.get("sources", [])
        if not 1 <= len(sources) <= 2:
            raise RuntimeError(f"Item {index} must contain 1-2 source links.")

        for source in sources:
            if not _clean(source.get("name")):
                raise RuntimeError(f"Item {index} has a source without a name.")
            _safe_url(source.get("url"))

        joined = " ".join(
            [
                title,
                *[_clean(x) for x in facts],
                _clean(item.get("label")),
            ]
        ).lower()
        forbidden = (
            "tác động stacorp",
            "ảnh hưởng",
            "khuyến nghị",
            "việc cần làm",
        )
        if any(term in joined for term in forbidden):
            raise RuntimeError(
                f"Item {index} mixes news facts with internal impact/action analysis."
            )


def _source_links(sources: list[dict]) -> str:
    links: list[str] = []
    for source in sources:
        name = html.escape(_clean(source.get("name")))
        url = _safe_url(source.get("url"))
        links.append(f'<a href="{url}">{name}</a>')
    return " · ".join(links)


def _render_item(item: dict) -> str:
    label = _clean(item.get("label"))
    title = html.escape(_clean(item.get("title")))
    facts = "".join(
        f"<li>{html.escape(_clean(fact))}</li>" for fact in item.get("facts", [])
    )
    sources = _source_links(item.get("sources", []))

    label_html = ""
    if label:
        label_html = f"<p><strong>{html.escape(label)}</strong></p>"

    return (
        f"{label_html}"
        f"<p><strong>{title}</strong></p>"
        f"<ul>{facts}</ul>"
        f"<p>Nguồn: {sources}</p>"
    )


def _render_group(group: str, items: list[dict]) -> str:
    group_items = [x for x in items if _clean(x.get("category")) == group]
    if not group_items:
        return ""

    icon = {
        GROUPS[0]: "💼",
        GROUPS[1]: "⚖️",
        GROUPS[2]: "👥",
    }[group]
    body = "".join(_render_item(item) for item in group_items)
    return f"<h3>{icon} {html.escape(group)}</h3>{body}"


def _render_html(brief: dict) -> tuple[str, str]:
    date = _validate_date(brief.get("date"))
    subject = f"ĐIỂM TIN ĐIỀU HÀNH STACORP | {date}"

    highlights = "".join(
        f"<li>{html.escape(_clean(item))}</li>"
        for item in brief.get("highlights", [])
    )

    groups = "".join(
        _render_group(group, brief.get("items", []))
        for group in GROUPS
    )

    impacts = "".join(
        f"<li><strong>{html.escape(_clean(item.get('area')))}:</strong> "
        f"{html.escape(_clean(item.get('text')))}</li>"
        for item in brief.get("impacts", [])
    )

    actions = "".join(
        f"<li><strong>{html.escape(_clean(item.get('owner')))}:</strong> "
        f"{html.escape(_clean(item.get('text')))}</li>"
        for item in brief.get("actions", [])
    )

    body = (
        "<h2>ĐIỂM TIN ĐIỀU HÀNH STACORP</h2>"
        f"<p><strong>{html.escape(date)}</strong> · "
        f"{html.escape(_clean(brief.get('window')))}</p>"
        f"<p>{html.escape(_clean(brief.get('summary')))}</p>"
        "<hr>"
        "<h3>⭐ 3 ĐIỂM NỔI BẬT</h3>"
        f"<ul>{highlights}</ul>"
        "<hr>"
        "<h3>ĐIỂM TIN</h3>"
        f"{groups}"
        "<hr>"
        "<h3>🎯 TÁC ĐỘNG ĐẾN STACORP</h3>"
        f"<ul>{impacts}</ul>"
        "<hr>"
        "<h3>✅ VIỆC CẦN LÀM HÔM NAY</h3>"
        f"<ul>{actions}</ul>"
    )

    plain = re.sub(r"<[^>]+>", " ", body)
    word_count = len(re.findall(r"\S+", html.unescape(plain)))
    print(f"TEAMS_WORD_COUNT={word_count}")

    return subject, body


def _endpoint() -> str:
    return (
        f"{GRAPH}/teams/{LOCKED_TEAM_ID}/channels/"
        f"{LOCKED_CHANNEL_ID}/messages"
    )


def publish(brief: dict) -> str:
    cfg = _load_config()
    _validate_brief(brief, cfg)
    subject, body = _render_html(brief)

    payload = {
        "subject": subject,
        "body": {
            "contentType": "html",
            "content": body,
        },
    }
    headers = {
        "Authorization": f"Bearer {refresh_access_token()}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=90) as client:
        response = client.post(_endpoint(), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    message_id = _clean(data.get("id"))
    if not message_id:
        raise RuntimeError(
            "Teams returned success without a message id; publication not confirmed."
        )

    print(f"ACCOUNTING_BRIEF_TEAM_ID={LOCKED_TEAM_ID}")
    print(f"ACCOUNTING_BRIEF_CHANNEL_ID={LOCKED_CHANNEL_ID}")
    print(f"ACCOUNTING_BRIEF_SUBJECT={subject}")
    print(f"ACCOUNTING_BRIEF_TEAMS_MESSAGE_ID={message_id}")
    return message_id


def main() -> int:
    if not INCOMING.exists():
        raise RuntimeError(
            "Missing incoming/accounting/current/brief.json"
        )
    brief = json.loads(INCOMING.read_text(encoding="utf-8"))
    message_id = publish(brief)
    print(f"TEAMS_MESSAGE_ID={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
