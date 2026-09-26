from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Candidate:
    id: str
    category: str
    title: str
    summary: str
    source: str
    published_at: str
    url: str
    official: bool = False

    def asdict(self) -> dict[str, Any]:
        return asdict(self)
