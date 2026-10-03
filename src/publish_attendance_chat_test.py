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
        "date": "Thứ Bảy, 03/10/2026",
        "filename": "AI_FINAL_Morning_2026-10-03.png",
        "alt": "Báo cáo chấm công ca sáng 03/10/2026",
        "note": "Số liệu phục vụ đối soát. Nếu phát hiện sai lệch hoặc có vướng mắc, vui lòng phản hồi P.HC-NS để kiểm tra và điều chỉnh.",
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
        "scope": "offline_access https://graph.microsoft.com/ChatMessage.Send https://graph.microsoft.com/Files.Read",
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
                f"Microsoft token refresh failed: HTTP {response.status_code} {response.text[:500]}"
            )
        token = str(response.json().get("access_token", "")).strip()
    if not token:
        raise RuntimeError("Microsoft token response did not contain access_token")
    return token

def _download_onedrive_png(token: str, filename: str) -> bytes:
    url = f"{GRAPH}/me/drive/root:/{quote(filename, safe='')}:/content"
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            raise RuntimeError(
                f"OneDrive image read failed for {filename}: HTTP {response.status_code} {response.text[:500]}"
            )
        payload = response.content
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"OneDrive file is not PNG: {filename}")
    if not 0 < len(payload) <= MAX_HOSTED_CONTENT_BYTES:
        raise RuntimeError(f"PNG violates Teams hosted-content limit: {filename} {len(payload)} bytes")
    return payload

def _post_report(token: str, report: dict, image: bytes) -> str:
    slot = html.escape(report["slot"])
    date = html.escape(report["date"])
    alt = html.escape(report["alt"], quote=True)
    note = html.escape(report.get("note", ""))
    body = (
        f"<b>BÁO CÁO CHẤM CÔNG — {slot}</b>"
        f"<br><b>{date}</b>"
        + (f"<br><b>{note}</b>" if note else "")
        + "<br><br>"
        + f'<img src="../hostedContents/1/$value" width="900" alt="{alt}">'
    )
    payload = {
        "body": {"contentType": "html", "content": body},
        "hostedContents": [
            {
                "@microsoft.graph.temporaryId": "1",
                "contentBytes": base64.b64encode(image).decode("ascii"),
                "contentType": "image/png",
            }
        ],
    }
    endpoint = f"{GRAPH}/chats/{quote(TEST_CHAT_ID, safe='')}/messages"
    with httpx.Client(timeout=90) as client:
        response = client.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Teams hosted-content post failed: HTTP {response.status_code} {response.text[:1000]}"
            )
        message_id = str(response.json().get("id", "")).strip()
    if not message_id:
        raise RuntimeError("Teams post succeeded without message id")
    print(
        f"ATTENDANCE_MORNING_REPORT_POST slot={report['slot']} "
        f"file={report['filename']} bytes={len(image)} message_id={message_id}"
    )
    return message_id

def main() -> int:
    if not Path(".github/attendance-hosted-chat-test-trigger.json").exists():
        raise RuntimeError("Missing attendance hosted-chat test trigger")
    token = _access_token()
    ids = []
    for report in REPORTS:
        image = _download_onedrive_png(token, report["filename"])
        ids.append(_post_report(token, report, image))
    print("ATTENDANCE_MORNING_REPORT_MESSAGE_IDS=" + ",".join(ids))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
