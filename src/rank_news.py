from __future__ import annotations

import json
import os
import re
from pathlib import Path

from openai import OpenAI

from .models import Candidate

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "published_hashes.json"

SYSTEM_PROMPT = """Bạn là biên tập viên intelligence cho doanh nghiệp xây dựng công nghiệp STACORP.

Chỉ sử dụng thông tin có trong danh sách candidate được cung cấp. Không tự bịa dữ kiện,
số liệu, ngày, nguồn, nghĩa vụ pháp lý hoặc chế tài.

Quy trình biên tập:
1. Lọc NEW -> RELEVANT -> MATERIAL -> DISTINCT.
2. Tự chấm điểm 0-10 và shortlist 12-18 tin mạnh nhất trước khi chọn final.
3. Final phải đúng 5 tin và tất cả phải >= 7/10.
4. Nếu không đủ 5 tin đạt chuẩn, trả publish=false và items=[].
5. Không chọn candidate có id trong previous_ids.

Cân bằng mong muốn:
- 1-2 Cơ hội & Khách hàng
- 1 Thị trường & Kinh doanh
- 1 Chi phí & Chuỗi cung ứng hoặc Tài chính & Dòng tiền
- 1 Công trường & Con người
Có thể thay bằng Công nghệ & Năng suất hoặc Pháp lý & Rủi ro nếu tác động cao.
Thông thường tối đa 2-3 tin impact=CAO.

Mỗi tin:
- đúng 2 facts ngắn, đều phải được title/summary candidate hỗ trợ;
- headline rõ, không giật tít;
- note là ý nghĩa thực tế cho STACORP;
- departments đúng 2-5 bộ phận thực sự liên quan, không dùng "Toàn công ty";
- impact chỉ: CAO, TRUNG BÌNH, THEO DÕI.

Pháp lý & Rủi ro:
- candidate bắt buộc official=true;
- nếu title/summary không hỗ trợ rõ ngày hiệu lực, nghĩa vụ hoặc chế tài liên quan thì loại.

action_today:
- chỉ điền khi có hành động rõ ràng phát sinh từ ít nhất một tin CAO;
- nếu không có hành động rõ ràng thì để chuỗi rỗng.

Trả JSON thuần, không markdown:
{
  "publish": true,
  "action_today": "",
  "items": [
    {
      "candidate_id": "...",
      "score": 8.2,
      "category": "...",
      "impact": "CAO",
      "headline": "...",
      "facts": ["...", "..."],
      "note": "...",
      "departments": ["...", "..."]
    }
  ]
}
"""


def _load_previous_ids() -> list[str]:
    if not STATE_PATH.exists():
        return []
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return [x["id"] for x in data.get("items", [])]


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", text)
    text = re.sub(r"\s*\x60\x60\x60$", "", text)
    return json.loads(text)


def select_brief(candidates: list[Candidate]) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live-news selection.")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"

    payload = {
        "previous_ids": _load_previous_ids(),
        "candidates": [c.asdict() for c in candidates],
    }

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Dữ liệu candidate:\n" + json.dumps(payload, ensure_ascii=False),
            },
        ],
    )
    result = _extract_json(response.output_text)

    if not result.get("publish"):
        return {"publish": False, "items": [], "action_today": ""}

    items = result.get("items", [])
    if len(items) != 5:
        raise RuntimeError(f"Model returned {len(items)} items; exactly 5 required.")

    by_id = {c.id: c for c in candidates}
    hydrated = []

    for item in items:
        cid = item["candidate_id"]
        if cid not in by_id:
            raise RuntimeError(f"Unknown candidate_id returned by model: {cid}")
        if float(item.get("score", 0)) < 7:
            raise RuntimeError("Model returned an item below score threshold 7/10.")

        departments = item.get("departments", [])
        if not 2 <= len(departments) <= 5:
            raise RuntimeError("Each item must have 2-5 relevant departments.")
        if any(str(x).strip().lower() == "toàn công ty" for x in departments):
            raise RuntimeError('Department list must not default to "Toàn công ty".')

        c = by_id[cid]
        if item.get("category") == "Pháp lý & Rủi ro" and not c.official:
            raise RuntimeError("Legal/risk item is not marked as official-source candidate.")

        facts = item.get("facts", [])
        if len(facts) != 2:
            raise RuntimeError("Each final item must contain exactly two facts.")

        hydrated.append(
            {
                **item,
                "source": c.source,
                "source_date": c.published_at,
                "url": c.url,
            }
        )

    high_count = sum(1 for x in hydrated if x.get("impact") == "CAO")
    if high_count > 3:
        raise RuntimeError("Too many HIGH-impact items; maximum is 3.")

    return {
        "publish": True,
        "action_today": result.get("action_today", ""),
        "items": hydrated,
    }
