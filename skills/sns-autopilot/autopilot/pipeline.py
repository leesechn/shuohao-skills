"""20개 항목을 단계 함수로 구현. 각 함수 docstring의 [X1] 등은 원문 트윗 번호."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .agents import Collector, Doubter, Writer, apply_feedback
from .clients import FakeClient, ThreadsClient, XClient
from .db import DB, days_ago, iso, now
from .llm import make_llm
from .textutil import composition_signature, composition_similarity, jaccard

SLOTS = ("morning", "noon", "night")


class Autopilot:
    def __init__(self, cfg: dict, base: Path):
        self.cfg, self.base = cfg, base
        self.tz = ZoneInfo(cfg.get("timezone", "Asia/Seoul"))
        self.db = DB(str(base / cfg.get("db", "autopilot.db")))
        llm = make_llm(cfg)
        pdir = base / cfg["playbooks"] if cfg.get("playbooks") else None
        kw = {"pdir": pdir} if pdir else {}
        self.collector, self.writer, self.doubter = Collector(llm, **kw), Writer(llm, **kw), Doubter(llm, **kw)
        if cfg.get("dry_run"):
            samples = json.loads((base / cfg.get("samples_file", "examples/samples.json")).read_text("utf-8"))
            self.x, self.th = FakeClient("x", samples), FakeClient("threads", samples)
        else:
            self.x, self.th = XClient(), ThreadsClient() if cfg.get("threads_enabled", True) else None
        self.facts = self._load_json(cfg.get("facts_file", "facts.json"), [])
        self.ctas = self._load_json(cfg.get("cta_file", "cta.json"), [])

    def _load_json(self, name, default):
        p = self.base / name
        return json.loads(p.read_text("utf-8")) if p.exists() else default

    def today(self) -> date:
        return now().astimezone(self.tz).date()

    # ─────────────── 《X発信》 ───────────────
    def collect_reference(self) -> int:
        """[X1] 참고 계정 게시물을 매일 아침 수집."""
        n = 0
        for acc in self.cfg.get("reference_accounts", []):
            for p in self.x.user_posts(acc, days_ago(1)):
                n += self._save_source("x", p)
        self.db.log("collect_reference", n)
        return n

    def _save_source(self, platform: str, p: dict) -> int:
        cur = self.db.conn.execute(
            "INSERT OR IGNORE INTO sources(platform,ext_id,author,text,likes,reposts,replies,views,posted_at,collected_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)", (platform, p["ext_id"], p.get("author"), p["text"], p.get("likes") or 0,
                                              p.get("reposts", 0), p.get("replies", 0), p.get("views", 0),
                                              p.get("posted_at"), iso()))
        self.db.conn.commit()
        return cur.rowcount

    def rebuild_patterns(self) -> list[str]:
        """[X1][T4] 최근 7일 수집물로 '유행 型'을 다시 쓰고 이름을 붙인다. 7일 내 재확인 안 된 型은 비활성."""
        win = self.cfg.get("pattern_window_days", 7)
        rows = self.db.q("SELECT * FROM sources WHERE collected_at >= ? "
                         "ORDER BY (likes + 3*reposts + 2*replies) DESC LIMIT 40", days_ago(win))
        if not rows:
            return []
        posts = [{"id": r["id"], "platform": r["platform"], "text": r["text"], "likes": r["likes"]} for r in rows]
        names = []
        for p in self.collector.extract_patterns(posts):
            ids = p.get("example_ids", [])
            score = sum(r["likes"] for r in rows if r["id"] in ids)
            self.db.x("INSERT INTO patterns(name,template,example_ids,score,active,updated_at) VALUES (?,?,?,?,1,?) "
                      "ON CONFLICT(name) DO UPDATE SET template=excluded.template, example_ids=excluded.example_ids,"
                      " score=excluded.score, active=1, updated_at=excluded.updated_at",
                      p["name"], p["template"], json.dumps(ids), score, iso())
            pid = self.db.one("SELECT id FROM patterns WHERE name=?", p["name"])["id"]
            for sid in ids:
                self.db.x("UPDATE sources SET pattern_id=? WHERE id=?", pid, sid)
            names.append(p["name"])
        self.db.x("UPDATE patterns SET active=0 WHERE updated_at < ?", days_ago(win))
        self.db.log("rebuild_patterns", names)
        return names

    def refresh_off_trend(self) -> int:
        """[X2] 유행에서 벗어난(비활성 型) 초안을 전날 밤에 다시 쓴다."""
        rows = self.db.q("SELECT d.* FROM drafts d LEFT JOIN patterns p ON p.id=d.pattern_id "
                         "WHERE d.status IN ('stock','scheduled','approved') AND (p.active IS NULL OR p.active=0)")
        if rows and not self._active_patterns():
            self.db.log("refresh_off_trend_skip", "활성 型 없음 — 아침 수집/型 재작성 실패 여부 확인")
            return 0
        for d in rows:
            new = self.generate_draft(d["topic"], replace_id=d["id"])
            self.db.log("refresh_off_trend", {"draft": d["id"], "ok": bool(new)})
        return len(rows)

    def _active_patterns(self):
        return self.db.q("SELECT * FROM patterns WHERE active=1 ORDER BY score DESC")

    def is_duplicate_topic(self, topic: str, text: str, exclude_draft: int | None = None) -> str | None:
        """[X4] 같은 주제가 30일 이내 게시/예약됐는지."""
        days, th = self.cfg.get("topic_dedupe_days", 30), self.cfg.get("topic_similarity", 0.5)
        since = days_ago(days)
        pool = [(r["topic"], r["text"], f"post#{r['id']}") for r in
                self.db.q("SELECT id,topic,text FROM posts WHERE platform='x' AND posted_at>=?", since)]
        pool += [(r["topic"], r["text"], f"draft#{r['id']}") for r in
                 self.db.q("SELECT id,topic,text FROM drafts WHERE status IN ('scheduled','approved') AND id!=?",
                           exclude_draft or -1)]
        for t, body, ref in pool:
            if (t or "").strip().lower() == topic.strip().lower() or jaccard(t or "", topic, 2) >= 0.7 \
                    or jaccard(body, text) >= th:
                return ref
        return None

    def check_image(self, comp: dict | None) -> bool:
        """[AI4] 구도 대장과 비교해 같은 그림을 막는다."""
        if not comp:
            return True
        lim = self.cfg.get("image_similarity_max", 0.67)
        for r in self.db.q("SELECT composition FROM image_ledger"):
            if composition_similarity(comp, json.loads(r["composition"])) >= lim:
                return False
        return True

    def generate_draft(self, topic: str, pattern_name: str | None = None, replace_id: int | None = None):
        """[T4] 型 이름으로 호출해 초안 작성 → [AI4] 구도 검사 → [A3] 숫자 검증 + 의심 담당 리뷰."""
        pats = self._active_patterns()
        if pattern_name:
            pats = [p for p in pats if p["name"] == pattern_name] or pats
        if not pats:
            raise RuntimeError("활성 型 없음: 먼저 collect → patterns 실행")
        pat = dict(pats[0])
        recent = [r["topic"] for r in self.db.q("SELECT topic FROM posts WHERE posted_at>=?", days_ago(30))]
        avoid_img = [json.loads(r["composition"]) for r in
                     self.db.q("SELECT composition FROM image_ledger ORDER BY id DESC LIMIT 30")]
        d = None
        for _ in range(3):
            d = self.writer.draft(topic, {"name": pat["name"], "template": pat["template"]}, recent, avoid_img)
            if self.check_image(d.get("image")):
                break
            avoid_img.append(d["image"])
        else:
            d["image"] = None                                     # 3회 연속 중복이면 이미지 없이
        dup = self.is_duplicate_topic(d.get("topic", topic), d["text"], replace_id)
        review = self.doubter.review(d, self.facts, recent)
        if dup:
            review["ok"] = False
            review["issues"].append(f"30일 내 동일 주제: {dup}")
        status = "stock" if review["ok"] else "review_failed"
        vals = (d["text"], d.get("topic", topic), json.dumps(d.get("tags", []), ensure_ascii=False), pat["id"],
                json.dumps(review, ensure_ascii=False), json.dumps(d.get("image"), ensure_ascii=False))
        if replace_id:
            self.db.x("UPDATE drafts SET text=?,topic=?,tags=?,pattern_id=?,review=?,image_spec=?,updated_at=?,"
                      "status=CASE WHEN ? THEN (CASE WHEN status='approved' THEN 'scheduled' ELSE status END)"
                      " ELSE 'review_failed' END WHERE id=?", *vals, iso(), review["ok"], replace_id)
            did = replace_id
        else:
            did = self.db.x("INSERT INTO drafts(text,topic,tags,pattern_id,review,image_spec,status,created_at,"
                            "updated_at) VALUES (?,?,?,?,?,?,?,?,?)", *vals, status, iso(), iso())
        if d.get("image") and review["ok"]:
            self.db.x("INSERT INTO image_ledger(draft_id,composition,signature,created_at) VALUES (?,?,?,?)",
                      did, json.dumps(d["image"], ensure_ascii=False), composition_signature(d["image"]), iso())
        return did if review["ok"] else None

    def fill_slots(self, day: date | None = None) -> list[str]:
        """[X3] 아침·점심·밤 슬롯이 비면 재고에서 자동 보충, 재고 부족하면 생성."""
        day = day or self.today() + timedelta(days=1)
        filled = []
        for slot in SLOTS:
            if self.db.one("SELECT 1 FROM drafts WHERE slot_date=? AND slot=? AND status IN ('scheduled','approved',"
                           "'posted')", day.isoformat(), slot):
                continue
            cand = None
            for d in self.db.q("SELECT * FROM drafts WHERE status='stock' ORDER BY created_at"):
                if not self.is_duplicate_topic(d["topic"], d["text"], d["id"]):
                    cand = d
                    break
            if not cand:
                topics = self.cfg.get("topics", ["자동화"])
                for t in topics:
                    did = self.generate_draft(t)
                    if did:
                        cand = self.db.one("SELECT * FROM drafts WHERE id=?", did)
                        break
            if not cand:
                self.db.log("fill_slots_empty", {"day": str(day), "slot": slot})
                continue
            nxt = "scheduled" if self.cfg.get("require_approval", True) else "approved"
            self.db.x("UPDATE drafts SET status=?, slot_date=?, slot=?, updated_at=? WHERE id=?",
                      nxt, day.isoformat(), slot, iso(), cand["id"])
            filled.append(f"{day} {slot} ← draft#{cand['id']}")
        self.top_up_stock()
        return filled

    def top_up_stock(self) -> int:
        need = self.cfg.get("stock_min", 6) - self.db.one("SELECT count(*) c FROM drafts WHERE status='stock'")["c"]
        made = 0
        topics = self.cfg.get("topics", ["자동화"])
        for i in range(max(0, need) * 2):                         # 실패 대비 2배까지 시도
            if made >= need:
                break
            made += bool(self.generate_draft(topics[i % len(topics)]))
        return made

    # [AI5] 사람이 하는 일은 '낸다/안 낸다' 결정뿐
    def decide(self, draft_id: int, publish: bool, note: str | None = None) -> None:
        self.db.x("UPDATE drafts SET status=?, updated_at=? WHERE id=? AND status='scheduled'",
                  "approved" if publish else "rejected", iso(), draft_id)
        if note:
            self.add_feedback(note)

    def add_feedback(self, note: str, roles: str = "all") -> None:
        """[AI3] 지적 사항 기록 → 다음 날 apply_feedback()이 전원 수순서에 반영."""
        self.db.x("INSERT INTO feedback(note,roles,created_at) VALUES (?,?,?)", note, roles,
                  now().astimezone(self.tz).isoformat(timespec="seconds"))

    def slot_due(self, slot_date: str, slot: str) -> bool:
        hh, mm = map(int, self.cfg.get("slots", {}).get(slot, {"morning": "07:30", "noon": "12:10",
                                                               "night": "21:00"}[slot]).split(":"))
        t = datetime.fromisoformat(slot_date).replace(hour=hh, minute=mm, tzinfo=self.tz)
        return now() >= t

    def publish_due(self) -> list[str]:
        """[X5] 시간이 되면 자동 게시 + [T3] Threads 자동 전재."""
        out = []
        for d in self.db.q("SELECT * FROM drafts WHERE status='approved' AND slot_date IS NOT NULL"):
            if not self.slot_due(d["slot_date"], d["slot"]):
                continue
            xid = self.x.post(d["text"])
            self._record_post(d, "x", xid)
            out.append(f"x:{xid}")
            if self.th and self.cfg.get("crosspost_threads", True):
                try:
                    tid = self.th.post(d["text"][:500])          # Threads 본문 500자 제한
                    self._record_post(d, "threads", tid)
                    out.append(f"threads:{tid}")
                except Exception as e:                            # Threads 실패가 X 게시를 막지 않게
                    self.db.log("crosspost_error", str(e))
            self.db.x("UPDATE drafts SET status='posted', updated_at=? WHERE id=?", iso(), d["id"])
        return out

    def _record_post(self, d, platform, ext_id):
        self.db.x("INSERT INTO posts(draft_id,platform,ext_id,slot,text,topic,posted_at) VALUES (?,?,?,?,?,?,?)",
                  d["id"], platform, ext_id, d["slot"], d["text"], d["topic"], iso())

    # ─────────────── 《Threads挑戦》 ───────────────
    def collect_threads(self) -> int:
        """[T1] Threads 인기글 검색, 좋아요 200+만. [T2] 작성자 본인 답글(続き)까지 합본."""
        th, n = self.th, 0
        if not th:
            return 0
        min_likes = self.cfg.get("threads_min_likes", 200)
        for q in self.cfg.get("threads_queries", []):
            for p in th.search(q, days_ago(7)):
                if p.get("likes") is None or p["likes"] < min_likes:   # 좋아요 수 미확인 글은 제외
                    continue
                cont = th.self_thread(p["ext_id"], p["author"])
                if cont:
                    p["text"] = p["text"] + "\n\n" + "\n\n".join(cont)
                n += self._save_source("threads", p)
        self.db.log("collect_threads", n)
        return n

    def pull_metrics(self) -> int:
        n = 0
        for p in self.db.q("SELECT * FROM posts WHERE posted_at >= ?", days_ago(30)):
            cli = self.x if p["platform"] == "x" else self.th
            if not cli:
                continue
            try:
                m = cli.metrics(p["ext_id"])
            except Exception as e:
                self.db.log("metrics_error", {"post": p["id"], "err": str(e)})
                continue
            self.db.x("INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?,?)", p["id"], iso(), m["impressions"],
                      m["likes"], m["reposts"], m["replies"], m["profile_clicks"])
            n += 1
        return n

    def _latest(self, post_id):
        return self.db.one("SELECT * FROM metrics WHERE post_id=? ORDER BY fetched_at DESC LIMIT 1", post_id)

    def compare(self) -> list[dict]:
        """[T5] 같은 글이 X와 Threads에서 어떻게 성장했는지 비교."""
        out = []
        for d in self.db.q("SELECT DISTINCT draft_id FROM posts WHERE draft_id IS NOT NULL"):
            row = {"draft_id": d["draft_id"]}
            for p in self.db.q("SELECT * FROM posts WHERE draft_id=?", d["draft_id"]):
                m = self._latest(p["id"])
                row[p["platform"]] = dict(m) if m else None
                row["topic"] = p["topic"]
            x, t = row.get("x"), row.get("threads")
            if x and t and x["impressions"]:
                row["threads_vs_x_impr"] = round(t["impressions"] / x["impressions"], 2)
                row["engagement_x"] = round((x["likes"] + x["reposts"]) / max(1, x["impressions"]), 4)
                row["engagement_threads"] = round((t["likes"] + t["reposts"]) / max(1, t["impressions"]), 4)
            out.append(row)
        return out

    # ─────────────── 《アフィの裏側》 ───────────────
    def pick_cta(self, post) -> dict | None:
        """[A2] 게시물 주제·태그와 맞는 유도문 선택 (태그 일치 우선, 없으면 작성 담당이 판단)."""
        if not self.ctas:
            return None
        d = self.db.one("SELECT tags FROM drafts WHERE id=?", post["draft_id"]) if post["draft_id"] else None
        tags = set(json.loads(d["tags"])) if d else set()
        tags.add(post["topic"] or "")
        scored = sorted(self.ctas, key=lambda c: -len(tags & set(c.get("tags", []))))
        if tags & set(scored[0].get("tags", [])):
            return scored[0]
        pick = self.writer.choose_cta(post["text"], self.ctas).get("cta_id")
        return next((c for c in self.ctas if c["id"] == pick), None)

    def attach_cta(self) -> list[str]:
        """[A1] 1만 임프레션을 넘은 글에만 나중에 유도 답글을 단다 (광고 표기 자동 부착)."""
        th, out = self.cfg.get("cta_impression_threshold", 10000), []
        for p in self.db.q("SELECT * FROM posts WHERE platform='x' AND cta_attached=0"):
            m = self._latest(p["id"])
            if not m or m["impressions"] < th:
                continue
            cta = self.pick_cta(p)
            if not cta:
                continue
            disclosure = self.cfg.get("ad_disclosure", "#광고")
            rid = self.x.post(f"{cta['text']}\n{cta['url']}\n{disclosure}", reply_to=p["ext_id"])
            self.db.x("UPDATE posts SET cta_attached=1 WHERE id=?", p["id"])
            out.append(f"post#{p['id']} ← {cta['id']} ({rid})")
        return out

    def auto_reply(self) -> list[str]:
        """[A4] 아침 게시물에 달린 답글에 자동 응답 (링크·스팸 제외, 1회 상한)."""
        conf = self.cfg.get("auto_reply", {})
        slot, cap = conf.get("slot", "morning"), conf.get("max_per_run", 10)
        out = []
        for p in self.db.q("SELECT * FROM posts WHERE slot=? AND posted_at>=?", slot, days_ago(1)):
            cli = self.x if p["platform"] == "x" else self.th
            if not cli:
                continue
            for r in cli.replies_to(p["ext_id"]):
                if len(out) >= cap:
                    return out
                if self.db.one("SELECT 1 FROM replies_handled WHERE platform=? AND ext_id=?", p["platform"],
                               r["ext_id"]):
                    continue
                if "http" in r["text"] and conf.get("skip_if_link", True):
                    self.db.x("INSERT INTO replies_handled VALUES (?,?,?,?)", p["platform"], r["ext_id"],
                              "SKIP:link", iso())
                    continue
                ans = self.writer.reply(p["text"], r["text"])
                if ans.get("skip"):
                    txt = "SKIP"
                else:
                    cli.post(ans["reply"], reply_to=r["ext_id"])
                    txt = ans["reply"]
                    out.append(f"{p['platform']}:{r['ext_id']}")
                self.db.x("INSERT INTO replies_handled VALUES (?,?,?,?)", p["platform"], r["ext_id"], txt, iso())
        return out

    def attribution(self, days: int = 30) -> list[dict]:
        """[A5] 어느 글에서 프로필로 왔는지 집계 (X: user_profile_clicks)."""
        rows = []
        for p in self.db.q("SELECT * FROM posts WHERE posted_at>=?", days_ago(days)):
            m = self._latest(p["id"])
            if m and m["profile_clicks"] is not None:
                rows.append({"post_id": p["id"], "platform": p["platform"], "topic": p["topic"],
                             "profile_clicks": m["profile_clicks"], "impressions": m["impressions"],
                             "rate": round(m["profile_clicks"] / max(1, m["impressions"]), 4)})
        total = sum(r["profile_clicks"] for r in rows) or 1
        for r in rows:
            r["share"] = round(r["profile_clicks"] / total, 3)
        return sorted(rows, key=lambda r: -r["profile_clicks"])

    # ─────────────── 스케줄 묶음 ───────────────
    def run_morning(self) -> dict:
        return {"feedback_applied": apply_feedback(self.db, self.today().isoformat(), self.writer.pdir),
                "x_sources": self.collect_reference(), "threads_sources": self.collect_threads(),
                "patterns": self.rebuild_patterns(), "metrics": self.pull_metrics()}

    def run_night(self) -> dict:
        return {"refreshed": self.refresh_off_trend(), "filled": self.fill_slots()}

    def run_tick(self) -> dict:
        """10~15분마다: 게시 → 지표 → 유도 → 자동응답."""
        return {"published": self.publish_due(), "metrics": self.pull_metrics(), "cta": self.attach_cta(),
                "replies": self.auto_reply()}
