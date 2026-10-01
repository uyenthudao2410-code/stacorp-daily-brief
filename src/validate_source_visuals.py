from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming" / "current"
OUT_DIR = Path("/tmp/stacorp-daily-brief")
OUT_VISUALS = OUT_DIR / "visuals"
QUALITY_REPORT = OUT_VISUALS / "source-quality.json"
RAW_URL_MANIFEST = INCOMING / "visual_sources.json"

ALLOWED_LOCAL_SUFFIXES = (".png", ".jpg", ".jpeg")
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG"}
RAW_HOST_SUFFIX = "oaiusercontent.com"

MIN_LONG_EDGE = 1400
MIN_SHORT_EDGE = 900
MIN_SOURCE_BYTES = 250_000
MIN_SHARPNESS = 18.0
MAX_SHARPNESS_SAMPLE_EDGE = 1024


def _sharpness_score(image: Image.Image) -> float:
    gray = image.convert("L")
    width, height = gray.size
    longest = max(width, height)
    if longest > MAX_SHARPNESS_SAMPLE_EDGE:
        ratio = MAX_SHARPNESS_SAMPLE_EDGE / float(longest)
        gray = gray.resize(
            (max(1, round(width * ratio)), max(1, round(height * ratio))),
            Image.Resampling.LANCZOS,
        )

    laplacian = gray.filter(
        ImageFilter.Kernel(
            size=(3, 3),
            kernel=(-1, -1, -1, -1, 8, -1, -1, -1, -1),
            scale=1,
            offset=128,
        )
    )
    if laplacian.width > 4 and laplacian.height > 4:
        laplacian = laplacian.crop(
            (2, 2, laplacian.width - 2, laplacian.height - 2)
        )
    return float(ImageStat.Stat(laplacian).var[0])


def _validate_image_bytes(data: bytes, label: str) -> tuple[Image.Image, dict]:
    source_bytes = len(data)
    if source_bytes < MIN_SOURCE_BYTES:
        raise RuntimeError(
            f"{label} is too small: {source_bytes} bytes; "
            f"require >= {MIN_SOURCE_BYTES}. "
            "Likely preview/thumbnail/compressed delivery."
        )

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise RuntimeError(f"{label} is not a readable image: {exc}") from exc

    image_format = str(image.format or "").upper()
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise RuntimeError(
            f"{label} has unsupported source format {image_format or 'UNKNOWN'}; "
            "production accepts original PNG/JPEG only. WEBP previews are blocked."
        )

    width, height = image.size
    if max(width, height) < MIN_LONG_EDGE or min(width, height) < MIN_SHORT_EDGE:
        raise RuntimeError(
            f"{label} resolution too low: {width}x{height}; "
            f"require long edge >= {MIN_LONG_EDGE} and short edge >= {MIN_SHORT_EDGE}."
        )

    sharpness = _sharpness_score(image)
    if sharpness < MIN_SHARPNESS:
        raise RuntimeError(
            f"{label} is too soft/blurry: sharpness={sharpness:.2f}; "
            f"require >= {MIN_SHARPNESS:.2f}."
        )

    report = {
        "format": image_format,
        "width": width,
        "height": height,
        "source_bytes": source_bytes,
        "sharpness": round(sharpness, 2),
    }
    return image.convert("RGB"), report


def _read_local_source(index: int) -> tuple[bytes, str] | None:
    matches = [
        INCOMING / f"story-{index}{suffix}"
        for suffix in ALLOWED_LOCAL_SUFFIXES
        if (INCOMING / f"story-{index}{suffix}").exists()
    ]
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise RuntimeError(
            f"Story {index} has multiple source images: {names}. "
            "Keep exactly one original PNG/JPEG."
        )
    if not matches:
        return None

    path = matches[0]
    return path.read_bytes(), f"local:{path.name}"


def _load_raw_urls() -> list[str] | None:
    if not RAW_URL_MANIFEST.exists():
        return None

    payload = json.loads(RAW_URL_MANIFEST.read_text(encoding="utf-8"))
    urls = payload.get("story_urls")
    if not isinstance(urls, list) or len(urls) != 5:
        raise RuntimeError(
            "incoming/current/visual_sources.json must contain exactly five "
            "story_urls."
        )

    cleaned: list[str] = []
    for index, value in enumerate(urls, start=1):
        url = str(value or "").strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not host
            or not host.endswith(RAW_HOST_SUFFIX)
            or "/raw" not in parsed.path
        ):
            raise RuntimeError(
                f"Story {index} raw URL is invalid. Expected an HTTPS "
                f"oaiusercontent.com original /raw URL, got: {url}"
            )
        cleaned.append(url)
    return cleaned


def _download_raw_source(client: httpx.Client, url: str, index: int) -> tuple[bytes, str]:
    response = client.get(url)
    response.raise_for_status()
    data = response.content
    if not data:
        raise RuntimeError(f"Story {index} raw URL returned an empty body.")
    return data, f"raw-url:{urlparse(url).hostname}"


def _prepared_report_is_usable() -> bool:
    if not QUALITY_REPORT.exists():
        return False
    try:
        report = json.loads(QUALITY_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return False
    if report.get("gate") != "PASS" or len(report.get("stories", [])) != 5:
        return False
    return all((OUT_VISUALS / f"story-{index}.png").exists() for index in range(1, 6))


def prepare_source_visuals(brief: dict) -> dict:
    items = brief.get("items", [])
    if len(items) != 5:
        raise RuntimeError("Source visual gate requires exactly five brief items.")

    OUT_VISUALS.mkdir(parents=True, exist_ok=True)

    if _prepared_report_is_usable():
        enriched = []
        for index, item in enumerate(items, start=1):
            item = dict(item)
            item["visual_src"] = f"visuals/story-{index}.png"
            enriched.append(item)
        result = dict(brief)
        result["items"] = enriched
        print("SOURCE_VISUAL_QUALITY_GATE=PASS (reused prepared originals)")
        return result

    raw_urls = _load_raw_urls()
    reports: list[dict] = []
    enriched: list[dict] = []

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for index, item in enumerate(items, start=1):
            local = _read_local_source(index)
            if local is not None:
                data, source_kind = local
            elif raw_urls is not None:
                data, source_kind = _download_raw_source(
                    client, raw_urls[index - 1], index
                )
            else:
                raise RuntimeError(
                    f"Missing original visual for story {index}. "
                    "Provide story-N.png/jpg/jpeg or visual_sources.json with "
                    "five original ChatGPT Images /raw URLs. WEBP preview files "
                    "are intentionally rejected."
                )

            image, report = _validate_image_bytes(data, f"story-{index}")
            target = OUT_VISUALS / f"story-{index}.png"
            image.save(target, format="PNG", optimize=True)

            report.update(
                {
                    "index": index,
                    "source_kind": source_kind,
                    "renderer_file": str(target),
                    "renderer_bytes": target.stat().st_size,
                }
            )
            reports.append(report)

            print(f"SOURCE_VISUAL_{index}_FORMAT={report['format']}")
            print(
                f"SOURCE_VISUAL_{index}_DIMENSIONS="
                f"{report['width']}x{report['height']}"
            )
            print(f"SOURCE_VISUAL_{index}_BYTES={report['source_bytes']}")
            print(f"SOURCE_VISUAL_{index}_SHARPNESS={report['sharpness']:.2f}")
            print(f"SOURCE_VISUAL_{index}_MODE={source_kind}")

            item = dict(item)
            item["visual_src"] = f"visuals/story-{index}.png"
            enriched.append(item)

    quality = {
        "gate": "PASS",
        "minimums": {
            "long_edge": MIN_LONG_EDGE,
            "short_edge": MIN_SHORT_EDGE,
            "source_bytes": MIN_SOURCE_BYTES,
            "sharpness": MIN_SHARPNESS,
        },
        "stories": reports,
    }
    QUALITY_REPORT.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = dict(brief)
    result["items"] = enriched
    print("SOURCE_VISUAL_QUALITY_GATE=PASS")
    return result


def main() -> int:
    brief_path = INCOMING / "brief.json"
    if not brief_path.exists():
        raise RuntimeError("Missing incoming/current/brief.json")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    prepare_source_visuals(brief)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
