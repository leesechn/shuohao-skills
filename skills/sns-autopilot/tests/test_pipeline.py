"""오프라인 E2E 테스트 (API 키·네트워크 불필요): python -m unittest discover -s tests"""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from autopilot.agents import apply_feedback, load_playbook  # noqa: E402
from autopilot.pipeline import Autopilot  # noqa: E402


def make(tmp: Path, **over) -> Autopilot:
    shutil.copytree(ROOT / "playbooks", tmp / "playbooks")
    shutil.copy(ROOT / "examples/samples.json", tmp / "samples.json")
    shutil.copy(ROOT / "facts.example.json", tmp / "facts.json")
    shutil.copy(ROOT / "cta.example.json", tmp / "cta.json")
    cfg = json.loads((ROOT / "config.example.json").read_text("utf-8"))
    cfg.update(samples_file="samples.json", playbooks="playbooks", llm="mock", **over)
    return Autopilot(cfg, tmp)


class E2E(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ap = make(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_threads_filter_and_continuation(self):
        self.assertEqual(self.ap.collect_threads(), 2)          # t1, t3 (t2는 좋아요 12 → 제외)
        t1 = self.ap.db.one("SELECT text FROM sources WHERE ext_id='t1'")["text"]
        self.assertIn("続き", t1)

    def test_full_day(self):
        m = self.ap.run_morning()
        self.assertEqual(m["x_sources"], 3)
        self.assertTrue(m["patterns"])
        today = self.ap.today()
        filled = self.ap.fill_slots(today)
        self.assertEqual(len(filled), 3, filled)
        q = self.ap.db.q("SELECT id FROM drafts WHERE status='scheduled'")
        for r in q:
            self.ap.decide(r["id"], True)
        self.ap.slot_due = lambda *_: True
        tick = self.ap.run_tick()
        self.assertEqual(len([p for p in tick["published"] if p.startswith("x:")]), 3)
        self.assertEqual(len([p for p in tick["published"] if p.startswith("threads:")]), 3)
        self.assertTrue(tick["cta"], "1만 임프 넘은 글에 유도가 붙어야 함")
        self.assertTrue(all("#광고" in s["text"] for s in self.ap.x.sent if s["reply_to"] and "http" in s["text"]))
        self.assertTrue(tick["replies"])
        skipped = self.ap.db.one("SELECT count(*) c FROM replies_handled WHERE answered_with='SKIP:link'")["c"]
        self.assertGreater(skipped, 0)
        cmp_ = self.ap.compare()
        self.assertTrue(any("threads_vs_x_impr" in r for r in cmp_))
        attr = self.ap.attribution()
        self.assertTrue(attr and attr[0]["profile_clicks"] >= attr[-1]["profile_clicks"])
        self.assertEqual({r["platform"] for r in attr}, {"x"})  # Threads는 게시물별 프로필 유입 미제공

    def test_fact_check(self):
        facts = self.ap.facts
        self.assertTrue(self.ap.doubter.fact_check("한 달 만에 월 500만원 벌었다", facts))
        self.assertFalse(self.ap.doubter.fact_check("팔로워 3,200명 됐습니다", facts))

    def test_topic_dedupe_30days(self):
        self.ap.db.x("INSERT INTO posts(platform,ext_id,text,topic,posted_at) VALUES ('x','old','부업 이야기','부업',?)",
                     self.ap.today().isoformat())
        self.assertIsNotNone(self.ap.is_duplicate_topic("부업", "완전히 다른 본문"))
        self.assertIsNone(self.ap.is_duplicate_topic("요리", "완전히 다른 본문"))

    def test_image_ledger(self):
        comp = {"subject": "a", "angle": "정면", "layout": "중앙", "palette": "블루", "text_position": "상단",
                "background": "단색"}
        self.ap.db.x("INSERT INTO image_ledger(composition,signature,created_at) VALUES (?,?,?)",
                     json.dumps(comp), "s", "2026-01-01")
        self.assertFalse(self.ap.check_image(dict(comp, subject="b")))
        self.assertTrue(self.ap.check_image({**comp, "angle": "부감", "layout": "그리드", "palette": "모노"}))

    def test_feedback_applies_next_day(self):
        self.ap.add_feedback("이모지 남발 금지")
        today = self.ap.today()
        self.assertEqual(apply_feedback(self.ap.db, today.isoformat(), self.tmp / "playbooks"), 0)
        tomorrow = (today + timedelta(days=1)).isoformat()
        self.assertEqual(apply_feedback(self.ap.db, tomorrow, self.tmp / "playbooks"), 1)
        for role in ("collector", "writer", "doubter"):
            self.assertIn("이모지 남발 금지", load_playbook(role, self.tmp / "playbooks"))

    def test_off_trend_refresh(self):
        self.ap.run_morning()
        self.ap.fill_slots(self.ap.today())
        self.ap.db.x("UPDATE patterns SET active=0")
        self.assertEqual(self.ap.refresh_off_trend(), 0)        # 활성 型 없으면 안전하게 건너뜀
        self.ap.db.x("INSERT INTO patterns(name,template,active,updated_at) VALUES ('신型','훅→목록',1,?)",
                     self.ap.today().isoformat())
        self.assertGreater(self.ap.refresh_off_trend(), 0)
        new_pid = self.ap.db.one("SELECT id FROM patterns WHERE name='신型'")["id"]
        self.assertTrue(self.ap.db.q("SELECT 1 FROM drafts WHERE pattern_id=?", new_pid))


if __name__ == "__main__":
    unittest.main()
