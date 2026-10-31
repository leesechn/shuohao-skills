"""X API v2 / Threads Graph API 클라이언트 + 오프라인 Fake.

인증:
  X (권장) : X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET  (OAuth 1.0a — 만료 없음)
  X (대안) : X_USER_TOKEN   (OAuth 2.0 사용자 토큰 — 2시간 만료, 외부 갱신 필요)
  Threads  : THREADS_TOKEN  (scope: threads_basic, threads_content_publish, threads_manage_replies,
                             threads_read_replies, threads_manage_insights, threads_keyword_search)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import secrets
import time
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


class APIError(RuntimeError):
    pass


def _q(s: str) -> str:
    return urllib.parse.quote(str(s), safe="~")


class OAuth1:
    """OAuth 1.0a HMAC-SHA1 서명 (RFC 5849). JSON 본문은 서명 대상이 아님."""

    def __init__(self, ck, cs, tk, ts):
        self.ck, self.cs, self.tk, self.ts = ck, cs, tk, ts

    def header(self, method: str, url: str, query: dict) -> str:
        oa = {"oauth_consumer_key": self.ck, "oauth_nonce": secrets.token_hex(16),
              "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
              "oauth_token": self.tk, "oauth_version": "1.0"}
        allp = {**{k: str(v) for k, v in query.items()}, **oa}
        norm = "&".join(f"{k}={v}" for k, v in sorted((_q(k), _q(v)) for k, v in allp.items()))
        base = "&".join([method.upper(), _q(url), _q(norm)])
        key = f"{_q(self.cs)}&{_q(self.ts)}".encode()
        oa["oauth_signature"] = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
        return "OAuth " + ", ".join(f'{_q(k)}="{_q(v)}"' for k, v in sorted(oa.items()))


def _http(method: str, url: str, token, params: dict | None = None, body: dict | None = None):
    params = {k: v for k, v in (params or {}).items() if v is not None}
    auth = token.header(method, url, params) if isinstance(token, OAuth1) else f"Bearer {token}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise APIError(f"{method} {url.split('?')[0]} → {e.code}: {e.read()[:300]!r}") from e


# ───────────────────────────── X ─────────────────────────────
class XClient:
    BASE = "https://api.x.com/2"
    FIELDS = "created_at,public_metrics,conversation_id,author_id"

    def __init__(self, token=None):
        e = os.environ
        if token is None and all(e.get(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")):
            token = OAuth1(e["X_API_KEY"], e["X_API_SECRET"], e["X_ACCESS_TOKEN"], e["X_ACCESS_SECRET"])
        self.token = token or e["X_USER_TOKEN"]
        self._me = None

    def _get(self, path, **p):
        return _http("GET", self.BASE + path, self.token, p)

    def me(self) -> dict:
        if not self._me:
            self._me = self._get("/users/me", **{"user.fields": "username"})["data"]
        return self._me

    def user_posts(self, username: str, since_iso: str) -> list[dict]:
        uid = self._get(f"/users/by/username/{username}")["data"]["id"]
        res = self._get(f"/users/{uid}/tweets", max_results=100, start_time=since_iso,
                        exclude="retweets,replies", **{"tweet.fields": self.FIELDS})
        out = []
        for t in res.get("data", []):
            m = t["public_metrics"]
            out.append({"ext_id": t["id"], "author": username, "text": t["text"], "likes": m["like_count"],
                        "reposts": m["retweet_count"], "replies": m["reply_count"],
                        "views": m.get("impression_count", 0), "posted_at": t["created_at"]})
        return out

    def post(self, text: str, reply_to: str | None = None) -> str:
        body = {"text": text}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        return _http("POST", self.BASE + "/tweets", self.token, body=body)["data"]["id"]

    def metrics(self, ext_id: str) -> dict:
        # non_public_metrics.user_profile_clicks: 본인 게시물, 게시 후 30일 이내만 제공
        t = self._get("/tweets", ids=ext_id, **{"tweet.fields": "public_metrics,non_public_metrics"})["data"][0]
        pm, npm = t["public_metrics"], t.get("non_public_metrics", {})
        return {"impressions": pm.get("impression_count", 0), "likes": pm["like_count"],
                "reposts": pm["retweet_count"], "replies": pm["reply_count"],
                "profile_clicks": npm.get("user_profile_clicks")}

    def replies_to(self, ext_id: str) -> list[dict]:
        me = self.me()
        res = self._get("/tweets/search/recent", query=f"conversation_id:{ext_id} -from:{me['username']}",
                        max_results=50, **{"tweet.fields": "author_id,in_reply_to_user_id,text"})
        return [{"ext_id": r["id"], "text": r["text"], "author": r["author_id"]}
                for r in res.get("data", []) if r.get("in_reply_to_user_id") == me["id"]]


# ─────────────────────────── Threads ───────────────────────────
class ThreadsClient:
    BASE = "https://graph.threads.net/v1.0"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ["THREADS_TOKEN"]

    def _get(self, path, **p):
        return _http("GET", self.BASE + path, self.token, p)

    def search(self, q: str, since_iso: str | None = None, limit: int = 100) -> list[dict]:
        base = dict(q=q, search_type="TOP", limit=limit,
                    since=int(datetime.fromisoformat(since_iso).timestamp()) if since_iso else None)
        try:   # like_count가 검색 필드로 허용되는지는 공개 문서상 불확실 → 실패 시 필드 축소
            res = self._get("/keyword_search", fields="id,text,username,timestamp,permalink,like_count", **base)
        except APIError:
            res = self._get("/keyword_search", fields="id,text,username,timestamp,permalink", **base)
        return [{"ext_id": r["id"], "author": r.get("username"), "text": r.get("text", ""),
                 "likes": r.get("like_count"), "posted_at": r.get("timestamp")} for r in res.get("data", [])]

    def self_thread(self, ext_id: str, author: str) -> list[str]:
        """본문 뒤에 작성자 본인이 이어 단 답글(続き)만 시간순으로."""
        res = self._get(f"/{ext_id}/conversation", fields="id,text,username,timestamp", reverse="false")
        return [r.get("text", "") for r in res.get("data", []) if r.get("username") == author]

    def post(self, text: str, reply_to: str | None = None) -> str:
        cid = _http("POST", self.BASE + "/me/threads", self.token,
                    {"media_type": "TEXT", "text": text, "reply_to_id": reply_to})["id"]
        time.sleep(self.publish_wait)       # Meta 권장: 컨테이너 생성 후 잠시 대기 뒤 publish
        return _http("POST", self.BASE + "/me/threads_publish", self.token, {"creation_id": cid})["id"]

    publish_wait = 5

    def metrics(self, ext_id: str) -> dict:
        res = self._get(f"/{ext_id}/insights", metric="views,likes,replies,reposts,quotes,shares")
        v = {d["name"]: d["values"][0]["value"] if d.get("values") else d.get("total_value", {}).get("value", 0)
             for d in res.get("data", [])}
        return {"impressions": v.get("views", 0), "likes": v.get("likes", 0), "reposts": v.get("reposts", 0),
                "replies": v.get("replies", 0), "profile_clicks": None}   # 게시물별 프로필 유입 미제공

    def replies_to(self, ext_id: str) -> list[dict]:
        res = self._get(f"/{ext_id}/replies", fields="id,text,username")
        return [{"ext_id": r["id"], "text": r.get("text", ""), "author": r.get("username")}
                for r in res.get("data", [])]


# ─────────────────────────── Fake (dry-run) ───────────────────────────
class FakeClient:
    """샘플 데이터로 동작. 발행은 메모리에만, ID는 순번."""
    _seq = itertools.count(1000)

    def __init__(self, platform: str, samples: dict):
        self.platform, self.samples, self.sent = platform, samples, []

    def user_posts(self, username, since_iso):
        return [p for p in self.samples.get("x", []) if p["author"] == username]

    def search(self, q, since_iso=None, limit=100):
        return [p for p in self.samples.get("threads", []) if q in p["text"]]

    def self_thread(self, ext_id, author):
        return self.samples.get("threads_continuations", {}).get(ext_id, [])

    def post(self, text, reply_to=None):
        pid = f"{self.platform}-{next(self._seq)}"
        self.sent.append({"id": pid, "text": text, "reply_to": reply_to,
                          "at": datetime.now(timezone.utc).isoformat()})
        return pid

    def metrics(self, ext_id):
        n = int(ext_id.split("-")[-1])
        imp = 15000 if n % 2 == 0 else 4000
        return {"impressions": imp if self.platform == "x" else imp // 2, "likes": imp // 100,
                "reposts": imp // 1000, "replies": 2,
                "profile_clicks": imp // 200 if self.platform == "x" else None}

    def replies_to(self, ext_id):
        return [{"ext_id": f"{ext_id}-r1", "text": "이거 어떻게 시작하나요?", "author": "fan1"},
                {"ext_id": f"{ext_id}-r2", "text": "돈 벌기 http://spam.example", "author": "bot9"}]
