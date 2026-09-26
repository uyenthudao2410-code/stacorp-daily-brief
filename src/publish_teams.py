from __future__ import annotations

import base64
import html
import os
from pathlib import Path

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"


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


def _target_endpoint() -> str:
    target_type = os.getenv("TEAMS_TARGET_TYPE", "chat").strip().lower()

    if target_type == "chat":
        chat_id = _required("TEAMS_CHAT_ID")
        return f"{GRAPH}/chats/{chat_id}/messages"

    if target_type == "channel":
        team_id = _required("TEAMS_TEAM_ID")
        channel_id = _required("TEAMS_CHANNEL_ID")
        return f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages"

    raise RuntimeError("TEAMS_TARGET_TYPE must be 'chat' or 'channel'.")


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def publish_inline_images(page1: Path, page2: Path, brief: dict) -> str:
    token = refresh_access_token()
    endpoint = _target_endpoint()

    date = html.escape(brief["date"])
    title = html.escape(
        brief.get("title", "ĐIỂM TIN CHO DOANH NGHIỆP STACORP")
    )

    body_html = (
        f"<b>{date} | {title}</b><br><br>"
        '<img src="../hostedContents/1/$value"><br><br>'
        '<img src="../hostedContents/2/$value">'
    )

    payload = {
        "body": {"contentType": "html", "content": body_html},
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
        ],
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    message_id = str(data.get("id", "")).strip()
    if not message_id:
        raise RuntimeError("Teams post succeeded without returning a message id.")

    return message_id
