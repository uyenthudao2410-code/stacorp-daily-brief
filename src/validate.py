from __future__ import annotations

from pathlib import Path

from PIL import Image

MAX_BYTES = 3_600_000
EXPECTED_SIZE = (1080, 1350)


def validate_png(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing rendered page: {path}")

    size = path.stat().st_size
    if size <= 50_000:
        raise RuntimeError(
            f"Rendered page is suspiciously small: {path} ({size} bytes)"
        )
    if size >= MAX_BYTES:
        raise RuntimeError(
            f"Rendered page exceeds inline-image safety limit: "
            f"{path} ({size} bytes)"
        )

    with Image.open(path) as image:
        if image.size != EXPECTED_SIZE:
            raise RuntimeError(
                f"Unexpected image size for {path}: {image.size}"
            )
        if image.format != "PNG":
            raise RuntimeError(f"Expected PNG for {path}, got {image.format}")
