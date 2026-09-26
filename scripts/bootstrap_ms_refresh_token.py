from __future__ import annotations

import argparse
import sys
import time

import httpx

DEFAULT_SCOPES = (
    "openid profile offline_access "
    "https://graph.microsoft.com/ChatMessage.Send "
    "https://graph.microsoft.com/ChannelMessage.Send"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-time device-code sign-in to obtain a Microsoft refresh token."
        )
    )
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--scope", default=DEFAULT_SCOPES)
    args = parser.parse_args()

    base = f"https://login.microsoftonline.com/{args.tenant}/oauth2/v2.0"

    with httpx.Client(timeout=30) as client:
        dc = client.post(
            f"{base}/devicecode",
            data={
                "client_id": args.client_id,
                "scope": args.scope,
            },
        )
        dc.raise_for_status()
        device = dc.json()

        print(device["message"])
        print("\nWaiting for sign-in approval...")

        interval = int(device.get("interval", 5))
        deadline = time.time() + int(device["expires_in"])

        while time.time() < deadline:
            time.sleep(interval)
            token = client.post(
                f"{base}/token",
                data={
                    "grant_type": (
                        "urn:ietf:params:oauth:grant-type:device_code"
                    ),
                    "client_id": args.client_id,
                    "device_code": device["device_code"],
                },
            )

            if token.status_code == 200:
                data = token.json()
                refresh = data.get("refresh_token")
                if not refresh:
                    print(
                        "Sign-in succeeded but no refresh_token was returned.",
                        file=sys.stderr,
                    )
                    return 2

                print(
                    "\nSUCCESS. Store the value below immediately as "
                    "GitHub secret MS_REFRESH_TOKEN."
                )
                print("Do not commit it to the repository.\n")
                print(refresh)
                return 0

            payload = token.json()
            error = payload.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue

            raise RuntimeError(payload)

    print(
        "Device code expired before authorization completed.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
