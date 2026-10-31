"""LLM 호출 계층.

- ANTHROPIC_API_KEY(또는 `ant auth login` 프로필)와 `anthropic` 패키지가 있으면 Claude API 호출
- 없으면 MockLLM(결정적 더미 응답)으로 전체 파이프라인을 오프라인 리허설
"""
from __future__ import annotations

import json
import os
import re

DEFAULT_MODEL = "claude-opus-5-5"


class LLMError(RuntimeError):
    pass


def _parse_json(text: str):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    body = m.group(1) if m else text
    start = min([i for i in (body.find("{"), body.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError(f"JSON 없음: {text[:200]}")
    return json.loads(body[start:body.rfind("}" if body[start] == "{" else "]") + 1])


class ClaudeLLM:
    def __init__(self, model: str = DEFAULT_MODEL):
        import anthropic  # 선택 의존성
        self.client = anthropic.Anthropic()
        self.model = model

    def json(self, task: str, system: str, user: str, effort: str = "medium"):
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            # 안전 분류기 거절 시 서버 측 자동 폴백 + effort 지정
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default", "output_config": {"effort": effort}},
        )
        if resp.stop_reason == "refusal":
            raise LLMError(f"[{task}] 모델 거절: {getattr(resp, 'stop_details', None)}")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return _parse_json(text)


class MockLLM:
    """API 키 없이 파이프라인 전 과정을 검증하기 위한 결정적 응답기."""

    def json(self, task: str, system: str, user: str, effort: str = "medium"):
        payload = _parse_json(user) if "{" in user else {}
        if task == "extract_patterns":
            items = payload.get("posts", [])
            out = []
            for i, p in enumerate(items[:3]):
                first = p["text"].splitlines()[0][:20]
                out.append({"name": f"型{i + 1}-{'숫자훅' if any(c.isdigit() for c in first) else '단언훅'}",
                            "template": "1행: 결론/숫자 훅 → 2~5행: ①②③ 목록 → 마지막: 한 줄 교훈",
                            "example_ids": [p["id"]]})
            return {"patterns": out}
        if task == "write_draft":
            pat = payload.get("pattern", {}).get("name", "기본형")
            topic = payload.get("topic", "자동화")
            k = sum(map(ord, topic))
            bodies = [f"{topic}에서 시간을 버는 3단계\n①아침에 모으고\n②밤에 고치고\n③사람은 승인만 한다",
                      f"{topic} 시작 전 꼭 알아둘 것\n- 처음 1주는 기록만\n- 2주차부터 패턴 비교\n- 한 달 뒤 정리",
                      f"솔직히 {topic}는 도구보다 습관 문제\n매일 같은 시간, 같은 순서로 반복하는 게 전부",
                      f"{topic} 실패담 공개\n욕심내서 한 번에 바꾸다 전부 멈췄다\n하나씩 바꾸니 굴러갔다"]
            n = len(payload.get("avoid_image_compositions", []))
            angles, layouts, palettes = ["정면", "부감", "측면", "클로즈업"], ["좌우분할", "중앙", "그리드", "풀블리드"], \
                ["블루", "옐로", "모노", "그린"]
            return {"text": bodies[k % 4] + f"\n({pat})", "topic": topic, "tags": [topic],
                    "image": {"subject": topic, "angle": angles[(k + n) % 4], "layout": layouts[(k + 2 * n) % 4],
                              "palette": palettes[(k + 3 * n) % 4], "text_position": ["상단", "하단"][n % 2],
                              "background": ["단색", "사진"][(k + n) % 2]}}
        if task == "review_draft":
            return {"ok": True, "issues": [], "risk": "low"}
        if task == "choose_cta":
            ctas = payload.get("ctas", [])
            return {"cta_id": ctas[0]["id"] if ctas else None, "reason": "태그 일치"}
        if task == "reply":
            return {"reply": "읽어주셔서 감사합니다! 궁금한 점은 편하게 물어보세요.", "skip": False}
        if task == "classify_topic":
            return {"topic": payload.get("text", "")[:12] or "기타"}
        raise LLMError(f"MockLLM: 알 수 없는 task {task}")


def make_llm(cfg: dict):
    if cfg.get("dry_run") or cfg.get("llm") == "mock":
        return MockLLM()
    try:
        return ClaudeLLM(cfg.get("model", DEFAULT_MODEL))
    except ImportError:
        if os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError("ANTHROPIC_API_KEY는 있으나 anthropic 패키지가 없습니다: pip install anthropic")
        return MockLLM()
