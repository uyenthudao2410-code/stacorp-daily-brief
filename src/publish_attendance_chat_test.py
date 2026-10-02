from __future__ import annotations

import base64
import html
import os
from pathlib import Path
from urllib.parse import quote

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"
TEST_CHAT_ID = "19:0e02d613cded448892f27d74cff19d63@thread.v2"
MAX_HOSTED_CONTENT_BYTES = 4 * 1024 * 1024

REPORTS = (
    {
        "slot": "CA SÁNG",
        "date": "Thứ Sáu, 02/10/2026",
        "files": (
            "TEST_V3_Morning_Overview_2026-10-02.png",
            "TEST_V3_Morning_Detail_2026-10-02.png",
        ),
        "alts": (
            "Tổng quan chấm công ca sáng 02/10/2026",
            "Chi tiết chấm công ca sáng 02/10/2026",
        ),
    },
    {
        "slot": "CẢ NGÀY",
        "date": "Thứ Năm, 01/10/2026",
        "files": (
            "TEST_V3_Daily_Overview_2026-10-01.png",
            "TEST_V3_Daily_Detail_2026-10-01.png",
        ),
        "alts": (
            "Tổng quan chấm công cả ngày 01/10/2026",
            "Chi tiết chấm công cả ngày 01/10/2026",
        ),
    },
)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _access_token() -> str:
    tenant = _required("MS_TENANT_ID")
    client_id = _required("MS_CLIENT_ID")
    refresh_token = _required("MS_REFRESH_TOKEN")
    form = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": (
            "offline_access "
            "https://graph.microsoft.com/ChatMessage.Send "
            "https://graph.microsoft.com/Files.Read"
        ),
    }
    secret = os.getenv("MS_CLIENT_SECRET", "").strip()
    if secret:
        form["client_secret"] = secret

    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data=form,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                "Microsoft token refresh failed: "
                f"HTTP {response.status_code} {response.text[:500]}"
            )
        token = str(response.json().get("access_token", "")).strip()

    if not token:
        raise RuntimeError("Microsoft token response did not contain access_token")
    return token


def _download_onedrive_png(token: str, filename: str) -> bytes:
    encoded = quote(filename, safe="")
    url = f"{GRAPH}/me/drive/root:/{encoded}:/content"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OneDrive image read failed for {filename}: "
                f"HTTP {response.status_code} {response.text[:500]}"
            )
        payload = response.content

    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"OneDrive file is not PNG: {filename}")
    if not 0 < len(payload) <= MAX_HOSTED_CONTENT_BYTES:
        raise RuntimeError(
            f"PNG violates Teams hosted-content limit: {filename} {len(payload)} bytes"
        )
    return payload


def _post_report(token: str, report: dict, images: tuple[bytes, bytes]) -> str:
    slot = html.escape(report["slot"])
    date = html.escape(report["date"])
    alt_1 = html.escape(report["alts"][0], quote=True)
    alt_2 = html.escape(report["alts"][1], quote=True)

    body = (
        f"<b>[TEST] BÁO CÁO CHẤM CÔNG — {slot}</b>"
        f"<br><b>{date}</b>"
        "<br>Tổng hợp từ hệ thống chấm công để đối soát."
        "<br><br>"
        f'<img src="../hostedContents/1/$value" width="900" alt="{alt_1}">'
        "<br><br>"
        f'<img src="../hostedContents/2/$value" width="900" alt="{alt_2}">'
    )
    payload = {
        "body": {"contentType": "html", "content": body},
        "hostedContents": [
            {
                "@microsoft.graph.temporaryId": str(index + 1),
                "contentBytes": base64.b64encode(image).decode("ascii"),
                "contentType": "image/png",
            }
            for index, image in enumerate(images)
        ],
    }
    endpoint = f"{GRAPH}/chats/{quote(TEST_CHAT_ID, safe='')}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=90) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Teams hosted-content post failed: "
                f"HTTP {response.status_code} {response.text[:1000]}"
            )
        message_id = str(response.json().get("id", "")).strip()

    if not message_id:
        raise RuntimeError("Teams post succeeded without message id")
    print(
        f"ATTENDANCE_V3_TEST_POST slot={report['slot']} "
        f"files={','.join(report['files'])} "
        f"bytes={len(images[0])}+{len(images[1])} "
        f"message_id={message_id}"
    )
    return message_id


def main() -> int:
    trigger = Path(".github/attendance-hosted-chat-test-trigger.json")
    if not trigger.exists():
        raise RuntimeError("Missing attendance hosted-chat test trigger")
    token = _access_token()
    ids = []
    for report in REPORTS:
        images = tuple(_download_onedrive_png(token, f) for f in report["files"])
        if len(images) != 2:
            raise RuntimeError("V3 test requires exactly two images per report")
        ids.append(_post_report(token, report, images))
    print("ATTENDANCE_V3_TEST_MESSAGE_IDS=" + ",".join(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
