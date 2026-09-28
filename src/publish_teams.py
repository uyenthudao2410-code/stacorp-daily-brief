from __future__ import annotations

import base64
import html
import os
from pathlib import Path
from urllib.parse import urlparse

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


def _safe_url(value: str) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return html.escape(value, quote=True)


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text

    clipped = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return clipped + "…"


def _source_footer_html(brief: dict) -> str:
    """
    Keep Teams text intentionally compact.

    The two rendered pages carry the editorial content. This footer exists only
    to make the original reporting easy to open and to surface an action_today
    line when the brief explicitly contains one.
    """
    date = html.escape(str(brief.get("date", "")).strip())
    parts = [
        f"<b>{date} • ĐIỂM TIN STACORP</b>",
        "<br><b>Nguồn đọc thêm:</b>",
    ]

    for index, item in enumerate(brief.get("items", []), start=1):
        source = html.escape(str(item.get("source", "")).strip())
        headline = html.escape(_clip(item.get("headline", ""), 78))
        url = _safe_url(item.get("url", ""))

        label = " — ".join(part for part in (source, headline) if part)
        if not label:
            continue

        if url:
            parts.append(
                f'<br>{index:02d}. <a href="{url}">{label}</a>'
            )
        else:
            parts.append(f"<br>{index:02d}. {label}")

    action = _clip(brief.get("action_today", ""), 220)
    if action:
        parts.extend(
            [
                "<br><br><b>Ưu tiên hôm nay:</b> ",
                html.escape(action),
            ]
        )

    return "".join(parts)


def _post(
    client: httpx.Client,
    endpoint: str,
    headers: dict[str, str],
    payload: dict,
) -> str:
    response = client.post(endpoint, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    message_id = str(data.get("id", "")).strip()
    if not message_id:
        raise RuntimeError("Teams post succeeded without returning a message id.")
    return message_id


def _image_payload(path: Path, caption: str, temporary_id: str) -> dict:
    safe_caption = html.escape(caption)
    return {
        "body": {
            "contentType": "html",
            "content": (
                f"<b>{safe_caption}</b><br><br>"
                f'<img src="../hostedContents/{temporary_id}/$value" '
                'width="900" alt="STACORP Daily Brief">'
            ),
        },
        "hostedContents": [
            {
                "@microsoft.graph.temporaryId": temporary_id,
                "contentBytes": _b64(path),
                "contentType": "image/png",
            }
        ],
    }


def publish_inline_images(page1: Path, page2: Path, brief: dict) -> str:
    """
    Publish the visual brief first, then a short source/link footer.

    This keeps the daily Teams post magazine-led: the images carry the news,
    while the final text message is intentionally short and clickable.
    """
    token = refresh_access_token()
    endpoint = _target_endpoint()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    date = str(brief.get("date", "")).strip()
    page1_payload = _image_payload(
        page1,
        f"{date} • ĐIỂM TIN STACORP • 1/2",
        "1",
    )
    page2_payload = _image_payload(
        page2,
        f"{date} • ĐIỂM TIN STACORP • 2/2",
        "1",
    )
    source_payload = {
        "body": {
            "contentType": "html",
            "content": _source_footer_html(brief),
        }
    }

    with httpx.Client(timeout=60) as client:
        page1_id = _post(client, endpoint, headers, page1_payload)
        page2_id = _post(client, endpoint, headers, page2_payload)
        source_id = _post(client, endpoint, headers, source_payload)

    print(f"TEAMS_PAGE_1_MESSAGE_ID={page1_id}")
    print(f"TEAMS_PAGE_2_MESSAGE_ID={page2_id}")
    print(f"TEAMS_SOURCE_MESSAGE_ID={source_id}")
    return page1_id
