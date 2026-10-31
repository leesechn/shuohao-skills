"""SQLite 저장소. 모든 단계의 상태(수집물·型·초안·재고·발행·지표·대장)를 한 파일에 둔다."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (          -- 참고 계정 / Threads 인기글 수집물
  id INTEGER PRIMARY KEY,
  platform TEXT NOT NULL,                     -- x | threads
  ext_id TEXT NOT NULL,
  author TEXT,
  text TEXT NOT NULL,                         -- 본문 + 자기 답글 이어쓰기(続き) 합본
  likes INTEGER DEFAULT 0,
  reposts INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  views INTEGER DEFAULT 0,
  posted_at TEXT,
  collected_at TEXT NOT NULL,
  pattern_id INTEGER,
  UNIQUE(platform, ext_id)
);
CREATE TABLE IF NOT EXISTS patterns (         -- 이름 붙인 '型'
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  template TEXT NOT NULL,                     -- 구조 설명(훅/전개/마무리/길이)
  example_ids TEXT DEFAULT '[]',
  score REAL DEFAULT 0,                       -- 최근 7일 가중 성과
  active INTEGER DEFAULT 1,                   -- 7일 창에서 유행 중인지
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  topic TEXT NOT NULL,
  tags TEXT DEFAULT '[]',
  pattern_id INTEGER,
  status TEXT NOT NULL DEFAULT 'stock',       -- stock | review_failed | scheduled | approved | rejected | posted
  review TEXT,                                -- 의심 담당 결과 JSON
  slot_date TEXT, slot TEXT,                  -- morning | noon | night
  image_spec TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (            -- 내가 실제로 낸 글 (X 원본 + Threads 전재)
  id INTEGER PRIMARY KEY,
  draft_id INTEGER,
  platform TEXT NOT NULL,
  ext_id TEXT NOT NULL,
  slot TEXT,
  text TEXT NOT NULL,
  topic TEXT,
  posted_at TEXT NOT NULL,
  cta_attached INTEGER DEFAULT 0,
  UNIQUE(platform, ext_id)
);
CREATE TABLE IF NOT EXISTS metrics (
  post_id INTEGER NOT NULL,
  fetched_at TEXT NOT NULL,
  impressions INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  reposts INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  profile_clicks INTEGER,                     -- NULL = 플랫폼이 제공하지 않음
  PRIMARY KEY(post_id, fetched_at)
);
CREATE TABLE IF NOT EXISTS replies_handled (
  platform TEXT NOT NULL, ext_id TEXT NOT NULL, answered_with TEXT, handled_at TEXT NOT NULL,
  PRIMARY KEY(platform, ext_id)
);
CREATE TABLE IF NOT EXISTS image_ledger (     -- 구도 대장
  id INTEGER PRIMARY KEY,
  draft_id INTEGER,
  composition TEXT NOT NULL,                  -- JSON: subject/angle/layout/palette/text_position
  signature TEXT NOT NULL,
  dhash TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (         -- 지적 사항 → 다음 날 전원 수순서에 반영
  id INTEGER PRIMARY KEY,
  note TEXT NOT NULL,
  roles TEXT NOT NULL DEFAULT 'all',
  created_at TEXT NOT NULL,
  applied_at TEXT
);
CREATE TABLE IF NOT EXISTS runlog (id INTEGER PRIMARY KEY, step TEXT, detail TEXT, at TEXT);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def days_ago(n: int) -> str:
    return iso(now() - timedelta(days=n))


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def q(self, sql: str, *args):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, *args):
        return self.conn.execute(sql, args).fetchone()

    def x(self, sql: str, *args) -> int:
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.lastrowid

    def log(self, step: str, detail) -> None:
        self.x("INSERT INTO runlog(step, detail, at) VALUES (?,?,?)", step,
               json.dumps(detail, ensure_ascii=False), iso())
