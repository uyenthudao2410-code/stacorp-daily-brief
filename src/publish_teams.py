from __future__ import annotations

import base64
import html
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

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


def _endpoint() -> str:
    target_type = os.getenv("TEAMS_TARGET_TYPE", "channel").strip().lower()
    if target_type != "channel":
        raise RuntimeError(
            "Production STACORP delivery requires TEAMS_TARGET_TYPE=channel."
        )

    team_id = _required("TEAMS_TEAM_ID")
    channel_id = _required("TEAMS_CHANNEL_ID")
    print(f"TEAMS_TARGET_TYPE={target_type}")
    print(f"TEAMS_TEAM_ID={team_id}")
    print(f"TEAMS_CHANNEL_ID={channel_id}")

    return f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages"


MAX_HOSTED_CONTENT_BYTES = 4 * 1024 * 1024
MAX_TEAMS_PAGE_BYTES = 850_000
MAX_TEAMS_BINARY_TOTAL = 2_550_000
TEAMS_MASTER_SIZE = (1200, 1800)
TEAMS_JPEG_QUALITIES = (97, 96, 95, 94, 93, 92, 90)


def _prepare_teams_jpeg(path: Path, index: int) -> Path:
    source = (
        Path("/tmp/stacorp-daily-brief")
        / "teams"
        / f"{path.stem}_TEAMS.png"
    )
    if not source.exists():
        raise RuntimeError(
            f"Missing high-density Teams master for page {index}: {source}"
        )

    with Image.open(source) as image:
        if image.size != TEAMS_MASTER_SIZE:
            raise RuntimeError(
                f"Teams page {index} has invalid dimensions: "
                f"{image.size[0]}x{image.size[1]}; "
                f"expected {TEAMS_MASTER_SIZE[0]}x{TEAMS_MASTER_SIZE[1]}."
            )
        image = image.convert("RGB")

        target = (
            Path("/tmp/stacorp-daily-brief")
            / f"teams-page-{index}.jpg"
        )

        selected_quality = None
        selected_size = None
        for quality in TEAMS_JPEG_QUALITIES:
            image.save(
                target,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=False,
                subsampling=0,
            )
            size = target.stat().st_size
            if size <= MAX_TEAMS_PAGE_BYTES:
                selected_quality = quality
                selected_size = size
                break

    if selected_quality is None or selected_size is None:
        raise RuntimeError(
            f"Teams page {index} cannot fit deterministic payload budget "
            f"of {MAX_TEAMS_PAGE_BYTES} bytes without dropping below quality 90."
        )

    if selected_size > MAX_HOSTED_CONTENT_BYTES:
        raise RuntimeError(
            f"Teams page {index} exceeds Graph hostedContent limit: "
            f"{selected_size} > {MAX_HOSTED_CONTENT_BYTES} bytes."
        )

    print(f"TEAMS_JPEG_PAGE_{index}={selected_size}")
    print(f"TEAMS_JPEG_QUALITY_{index}={selected_quality}")
    print(
        f"TEAMS_JPEG_DIMENSIONS_{index}="
        f"{TEAMS_MASTER_SIZE[0]}x{TEAMS_MASTER_SIZE[1]}"
    )
    return target

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


def _sources_html(brief: dict) -> str:
    parts = ["<b>Nguồn đọc thêm:</b>"]

    for index, item in enumerate(brief.get("items", []), start=1):
        source = html.escape(str(item.get("source", "")).strip())
        url = _safe_url(item.get("url", ""))

        if not source:
            continue

        if url:
            parts.append(f'<br>{index:02d}. <a href="{url}">{source}</a>')
        else:
            parts.append(f"<br>{index:02d}. {source}")

    action = _clip(brief.get("action_today", ""), 220)
    if action:
        parts.append(f"<br><br><b>Ưu tiên hôm nay:</b> {html.escape(action)}")

    return "".join(parts)


def publish_inline_images(
    page1: Path,
    page2: Path,
    page3: Path,
    brief: dict,
) -> str:
    teams_pages = [
        _prepare_teams_jpeg(page1, 1),
        _prepare_teams_jpeg(page2, 2),
        _prepare_teams_jpeg(page3, 3),
    ]

    total_binary = sum(page.stat().st_size for page in teams_pages)
    if total_binary > MAX_TEAMS_BINARY_TOTAL:
        raise RuntimeError(
            f"Teams payload exceeds deterministic binary budget: "
            f"{total_binary} > {MAX_TEAMS_BINARY_TOTAL} bytes."
        )
    print(f"TEAMS_BINARY_TOTAL={total_binary}")

    date = html.escape(str(brief.get("date", "")).strip())
    body = (
        f"<b>{date} • ĐIỂM TIN CHO DOANH NGHIỆP STACORP</b>"
        "<br><br>"
        '<img src="../hostedContents/1/$value" width="900" '
        'alt="STACORP Daily Brief - Page 1">'
        "<br><br>"
        '<img src="../hostedContents/2/$value" width="900" '
        'alt="STACORP Daily Brief - Page 2">'
        "<br><br>"
        '<img src="../hostedContents/3/$value" width="900" '
        'alt="STACORP Daily Brief - Page 3">'
        "<br><br>"
        + _sources_html(brief)
    )

    payload = {
        "body": {"contentType": "html", "content": body},
        "hostedContents": [
            {
                "@microsoft.graph.temporaryId": "1",
                "contentBytes": _b64(teams_pages[0]),
                "contentType": "image/jpeg",
            },
            {
                "@microsoft.graph.temporaryId": "2",
                "contentBytes": _b64(teams_pages[1]),
                "contentType": "image/jpeg",
            },
            {
                "@microsoft.graph.temporaryId": "3",
                "contentBytes": _b64(teams_pages[2]),
                "contentType": "image/jpeg",
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
