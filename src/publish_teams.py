from __future__ import annotations

import base64
import html
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"
STACORP_TEAMS_TEAM_ID = "c5bfff4c-a940-464e-a199-db0a169d230b"
STACORP_TEAMS_CHANNEL_ID = "19:YNeQ_V26FnwoIYtdH_W6imrVXAxwRWXpUfPi2W76CnQ1@thread.tacv2"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def refresh_access_token() -> str:
    tenant = _required("MS_TENANT_ID")
    client_id = _required("MS_CLIENT_ID")
    refresh_token = _required("MS_REFRESH_TOKEN")
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": (
            "offline_access "
            "https://graph.microsoft.com/ChatMessage.Send "
            "https://graph.microsoft.com/ChannelMessage.Send"
        ),
    }
    secret = os.getenv("MS_CLIENT_SECRET", "").strip()
    if secret:
        data["client_secret"] = secret

    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    with httpx.Client(timeout=30) as client:
        response = client.post(url, data=data)
        response.raise_for_status()
        token = response.json().get("access_token")

    if not token:
        raise RuntimeError("Microsoft token response did not contain access_token.")
    return token


def _endpoint() -> str:
    return (
        f"{GRAPH}/teams/{STACORP_TEAMS_TEAM_ID}/channels/"
        f"{STACORP_TEAMS_CHANNEL_ID}/messages"
    )


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _safe_url(value: str) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return html.escape(value, quote=True)


def _sources_html(brief: dict) -> str:
    parts = ["<b>Nguồn:</b>"]
    for index, item in enumerate(brief.get("items", []), start=1):
        source = html.escape(str(item.get("source", "")).strip())
        url = _safe_url(item.get("url", ""))
        if not source:
            continue
        if url:
            parts.append(f' &nbsp; {index:02d}. <a href="{url}">{source}</a>')
        else:
            parts.append(f" &nbsp; {index:02d}. {source}")
    return "".join(parts)


def publish_inline_images(
    page1: Path,
    page2: Path,
    page3: Path,
    brief: dict,
) -> str:
    date = html.escape(str(brief.get("date", "")).strip())
    body = (
        f"<b>ĐIỂM TIN STACORP | {date}</b>"
        "<br>5 diễn biến cần lưu ý hôm nay"
        "<br><br>"
        '<img src="../hostedContents/1/$value" width="900" alt="STACORP page 1">'
        "<br><br>"
        '<img src="../hostedContents/2/$value" width="900" alt="STACORP page 2">'
        "<br><br>"
        '<img src="../hostedContents/3/$value" width="900" alt="STACORP page 3">'
        "<br><br>"
        + _sources_html(brief)
    )

    payload = {
        "body": {"contentType": "html", "content": body},
        "hostedContents": [
            {
                "@microsoft.graph.temporaryId": "1",
                "contentBytes": _b64(page1),
                "contentType": "image/png",
            },
            {
                "@microsoft.graph.temporaryId": "2",
                "contentBytes": _b64(page2),
                "contentType": "image/png",
            },
            {
                "@microsoft.graph.temporaryId": "3",
                "contentBytes": _b64(page3),
                "contentType": "image/png",
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {refresh_access_token()}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=90) as client:
        response = client.post(_endpoint(), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    message_id = str(data.get("id", "")).strip()
    if not message_id:
        raise RuntimeError("Teams post succeeded without returning a message id.")

    print(f"TEAMS_MESSAGE_ID={message_id}")
    return message_id
