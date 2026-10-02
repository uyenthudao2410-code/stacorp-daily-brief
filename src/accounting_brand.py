from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND_CONFIG = ROOT / "config" / "brand.json"
CANONICAL_LOGO = ROOT / "assets" / "stacorp-logo.png"
TEMPLATES = (
    ROOT / "templates" / "accounting_page1.html",
    ROOT / "templates" / "accounting_page2.html",
    ROOT / "templates" / "accounting_page3.html",
)


def _git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def verify_accounting_brand_lock() -> None:
    if not BRAND_CONFIG.exists():
        raise RuntimeError("STACORP brand config is missing.")

    brand = json.loads(BRAND_CONFIG.read_text(encoding="utf-8"))
    rules = brand.get("render_rules", {})

    if brand.get("canonical_logo_path") != "assets/stacorp-logo.png":
        raise RuntimeError("Canonical STACORP logo path changed.")
    if rules.get("allow_ai_generated_logo") is not False:
        raise RuntimeError("AI-generated STACORP logo must remain disabled.")
    if rules.get("allow_story_image_logo") is not False:
        raise RuntimeError("STACORP logo must not appear in story visuals.")
    if rules.get("fail_if_missing_or_modified") is not True:
        raise RuntimeError("STACORP brand lock must fail closed.")

    if not CANONICAL_LOGO.exists():
        raise RuntimeError("Canonical STACORP logo asset is missing.")

    data = CANONICAL_LOGO.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    actual_blob = _git_blob_sha(data)
    expected_sha256 = str(brand.get("production_asset_sha256", "")).strip()
    expected_blob = str(brand.get("production_git_blob_sha1", "")).strip()

    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"STACORP logo SHA256 mismatch: {actual_sha256} != {expected_sha256}"
        )
    if actual_blob != expected_blob:
        raise RuntimeError(
            f"STACORP logo git blob mismatch: {actual_blob} != {expected_blob}"
        )

    required_ref = 'src="stacorp-logo.png"'
    for template in TEMPLATES:
        if not template.exists():
            raise RuntimeError(f"Accounting template missing: {template.name}")
        source = template.read_text(encoding="utf-8")
        if source.count(required_ref) != 1:
            raise RuntimeError(
                f"{template.name} must reference canonical stacorp-logo.png exactly once."
            )

    print(f"ACCOUNTING_LOGO_SHA256={actual_sha256}")
    print(f"ACCOUNTING_LOGO_GIT_BLOB_SHA1={actual_blob}")
    print("ACCOUNTING_BRAND_GATE=PASS")


if __name__ == "__main__":
    verify_accounting_brand_lock()
