from __future__ import annotations

import base64
import os
from pathlib import Path

from openai import OpenAI

OUT_DIR = Path("/tmp/stacorp-daily-brief")
VISUAL_DIR = OUT_DIR / "visuals"


def _prompt_for(item: dict) -> str:
    category = item.get("category", "")
    headline = item.get("headline", "")
    facts = " ".join(item.get("facts", [])[:2])

    return f"""
Create one refined editorial photograph for an executive corporate daily brief in Vietnam.

Subject/category: {category}
Story: {headline}
Context: {facts}

Visual direction:
- photorealistic, premium corporate editorial photography
- calm, bright natural light, clean blue-neutral color palette
- construction, industrial, infrastructure, logistics, materials, workplace or business context as appropriate
- professional, credible, modern, uncluttered
- composition should crop well to a 16:9 or 4:3 card thumbnail
- no dramatic disaster imagery, no sensationalism

STRICT BRAND SAFETY:
- NO text, NO letters, NO numbers, NO readable documents, NO signage
- NO logos, NO trademarks, NO corporate marks, NO watermarks
- NO STACORP logo or anything resembling it
- clothing, PPE, helmets, vehicles, machinery and buildings must be completely unbranded
- do not invent badges, emblems or company marks
- if people appear, show them naturally and professionally, preferably from a moderate distance
""".strip()


def generate_visuals(brief: dict) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when --visuals is enabled.")

    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare").strip()
    if not model:
        model = "gpt-image-2.5-flare"

    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    enriched = dict(brief)
    items = [dict(item) for item in brief["items"]]

    for index, item in enumerate(items, start=1):
        response = client.images.generate(
            model=model,
            prompt=_prompt_for(item),
            size="1024x1024",
            quality="low",
            output_format="jpeg",
            output_compression=72,
            n=1,
        )

        image_data = response.data[0].b64_json
        if not image_data:
            raise RuntimeError(f"Image generation returned no data for story {index}.")

        filename = f"story-{index}.jpg"
        path = VISUAL_DIR / filename
        path.write_bytes(base64.b64decode(image_data))
        item["visual_src"] = f"visuals/{filename}"

    enriched["items"] = items
    return enriched
