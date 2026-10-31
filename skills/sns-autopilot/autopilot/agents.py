"""AI 사원 3명: 수집 담당(Collector) · 작성 담당(Writer) · 의심 담당(Doubter).

- 지켜야 할 규칙은 playbooks/*.md 수순서에 있고, **호출할 때마다 파일을 다시 읽는다** (캐시 금지).
- 지적 사항(feedback)은 다음 날 아침 apply_feedback()이 전원의 수순서(learned.md)에 추가한다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .db import DB, iso
from .textutil import extract_numbers

PLAYBOOK_DIR = Path(__file__).resolve().parent.parent / "playbooks"


def load_playbook(role: str, pdir: Path = PLAYBOOK_DIR) -> str:
    parts = []
    for name in ("common.md", f"{role}.md", "learned.md"):
        p = pdir / name
        if p.exists():
            parts.append(f"<!-- {name} -->\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def apply_feedback(db: DB, today_local: str, pdir: Path = PLAYBOOK_DIR) -> int:
    """어제까지 받은 지적을 learned.md에 반영. 당일 지적은 '다음 날부터' 원칙대로 보류."""
    rows = db.q("SELECT * FROM feedback WHERE applied_at IS NULL AND substr(created_at,1,10) < ?", today_local)
    if not rows:
        return 0
    path = pdir / "learned.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# 누적 지적 사항 (전원 적용)\n"
    for r in rows:
        text += f"\n- [{r['created_at'][:10]}] ({r['roles']}) {r['note']}"
        db.x("UPDATE feedback SET applied_at=? WHERE id=?", iso(), r["id"])
    path.write_text(text + "\n", encoding="utf-8")
    return len(rows)


class Agent:
    role = ""
    effort = "medium"

    def __init__(self, llm, pdir: Path = PLAYBOOK_DIR):
        self.llm, self.pdir = llm, pdir

    def ask(self, task: str, payload: dict):
        system = load_playbook(self.role, self.pdir)          # 매번 다시 읽음
        return self.llm.json(task, system, json.dumps(payload, ensure_ascii=False), effort=self.effort)


class Collector(Agent):
    role, effort = "collector", "low"

    def extract_patterns(self, posts: list[dict]) -> list[dict]:
        return self.ask("extract_patterns", {"instruction": "성과 상위 글에서 구조(型)만 추출하고 이름을 붙여라. "
                                             "문장·고유 표현은 복제 금지.", "posts": posts})["patterns"]


class Writer(Agent):
    role = "writer"

    def draft(self, topic: str, pattern: dict, avoid_topics: list[str], avoid_images: list[dict]) -> dict:
        return self.ask("write_draft", {"topic": topic, "pattern": pattern, "avoid_topics": avoid_topics,
                                        "avoid_image_compositions": avoid_images})

    def reply(self, post_text: str, reply_text: str) -> dict:
        return self.ask("reply", {"my_post": post_text, "their_reply": reply_text})

    def choose_cta(self, post_text: str, ctas: list[dict]) -> dict:
        return self.ask("choose_cta", {"post": post_text, "ctas": ctas})


class Doubter(Agent):
    role, effort = "doubter", "high"

    def fact_check(self, text: str, facts: list[dict], tolerance: float = 0.02) -> list[str]:
        """실적 숫자가 facts 장부(증빙 있는 실제 수치)에 있는지 기계적으로 검증."""
        issues = []
        for n in extract_numbers(text):
            ok = any(abs(n["value"] - f["value"]) <= abs(f["value"]) * tolerance
                     and (f.get("unit") in (None, n["unit"]) or n["unit"] is None) for f in facts)
            if not ok:
                issues.append(f"검증 불가 숫자 '{n['raw']}' — facts.json에 증빙된 값이 없음")
        return issues

    def review(self, draft: dict, facts: list[dict], recent_topics: list[str]) -> dict:
        issues = self.fact_check(draft["text"], facts)
        llm = self.ask("review_draft", {"draft": draft, "recent_topics": recent_topics})
        issues += llm.get("issues", [])
        return {"ok": not issues and llm.get("ok", False), "issues": issues, "risk": llm.get("risk", "unknown"),
                "checked_at": datetime.now().isoformat(timespec="seconds")}
