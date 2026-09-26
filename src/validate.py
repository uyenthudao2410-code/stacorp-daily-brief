from __future__ import annotations

from pathlib import Path

from PIL import Image

MAX_BYTES = 3_600_000
EXPECTED_SIZE = (1120, 1400)


def validate_png(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing rendered page: {path}")

    size = path.stat().st_size
    if size <= 50_000:
        raise RuntimeError(f"Rendered page is suspiciously small: {path} ({size} bytes)")
    if size >= MAX_BYTES:
        raise RuntimeError(
            f"Rendered page exceeds inline-image safety limit: {path} ({size} bytes)"
        )

    with Image.open(path) as img:
        if img.size != EXPECTED_SIZE:
            raise RuntimeError(f"Unexpected image size for {path}: {img.size}")
        if img.format != "PNG":
            raise RuntimeError(f"Expected PNG for {path}, got {img.format}")
