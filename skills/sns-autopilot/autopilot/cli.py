"""CLI. 예) python -m autopilot -c config.json morning"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .pipeline import Autopilot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="autopilot")
    ap.add_argument("-c", "--config", default="config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, h in [("morning", "아침: 지적 반영·수집·型 재작성·지표"), ("night", "밤: 유행 이탈 초안 재작성·슬롯 보충"),
                    ("tick", "10~15분 주기: 게시·전재·지표·유도·자동응답"), ("collect", "X 참고계정 + Threads 수집"),
                    ("patterns", "型 재작성"), ("compare", "X vs Threads 비교"), ("attribution", "프로필 유입 집계"),
                    ("queue", "승인 대기 목록")]:
        sub.add_parser(name, help=h)
    f = sub.add_parser("fill", help="슬롯 보충");  f.add_argument("--day")
    w = sub.add_parser("write", help="型 이름으로 초안 작성"); w.add_argument("topic"); w.add_argument("--pattern")
    for n in ("approve", "reject"):
        s = sub.add_parser(n); s.add_argument("draft_id", type=int); s.add_argument("--note")
    fb = sub.add_parser("feedback", help="지적 사항 → 다음 날부터 전원 수순서에 반영")
    fb.add_argument("note"); fb.add_argument("--roles", default="all")
    a = ap.parse_args(argv)

    cfg_path = Path(a.config).resolve()
    ap_ = Autopilot(json.loads(cfg_path.read_text("utf-8")), cfg_path.parent)
    c = a.cmd
    if c == "morning":   res = ap_.run_morning()
    elif c == "night":   res = ap_.run_night()
    elif c == "tick":    res = ap_.run_tick()
    elif c == "collect": res = {"x": ap_.collect_reference(), "threads": ap_.collect_threads()}
    elif c == "patterns": res = ap_.rebuild_patterns()
    elif c == "fill":    res = ap_.fill_slots(date.fromisoformat(a.day) if a.day else None)
    elif c == "write":   res = ap_.generate_draft(a.topic, a.pattern)
    elif c in ("approve", "reject"):
        ap_.decide(a.draft_id, c == "approve", a.note); res = "ok"
    elif c == "feedback": ap_.add_feedback(a.note, a.roles); res = "다음 날 아침 morning 실행 시 반영"
    elif c == "compare": res = ap_.compare()
    elif c == "attribution": res = ap_.attribution()
    elif c == "queue":
        res = [{"id": r["id"], "slot": f"{r['slot_date']} {r['slot']}", "text": r["text"],
                "review": json.loads(r["review"] or "{}")}
               for r in ap_.db.q("SELECT * FROM drafts WHERE status='scheduled' ORDER BY slot_date, slot")]
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    return 0
