from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import feedparser

from .models import Candidate

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "news_queries.json"


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _norm_title(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _age_hours(entry) -> float | None:
    parsed = getattr(entry, "published_parsed", None)
    if not parsed:
        return None
    dt = datetime(*parsed[:6], tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def collect_candidates() -> list[Candidate]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    target = int(cfg.get("target_candidates", 80))
    max_age = int(cfg.get("max_age_hours", 72))
    official_markers = [x.lower() for x in cfg.get("official_source_markers", [])]

    candidates: list[Candidate] = []
    seen: set[str] = set()

    for spec in cfg["queries"]:
        query = quote_plus(spec["q"])
        url = f"https://news.google.com/rss/search?q={query}&hl=vi&gl=VN&ceid=VN:vi"
        feed = feedparser.parse(url)

        for entry in feed.entries[:20]:
            age = _age_hours(entry)
            if age is not None and age > max_age:
                continue

            title = _clean_html(getattr(entry, "title", ""))
            if not title:
                continue

            norm = _norm_title(title)
            if norm in seen:
                continue
            seen.add(norm)

            source_obj = getattr(entry, "source", None)
            source = ""
            if source_obj:
                source = getattr(source_obj, "title", "") or source_obj.get("title", "")
            source = source or "Nguồn báo chí"

            summary = _clean_html(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")
            official = any(marker in source.lower() for marker in official_markers)

            cid = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
            candidates.append(
                Candidate(
                    id=cid,
                    category=spec["category"],
                    title=title,
                    summary=summary[:900],
                    source=source,
                    published_at=published,
                    url=link,
                    official=official,
                )
            )

            if len(candidates) >= target:
                return candidates

    return candidates
