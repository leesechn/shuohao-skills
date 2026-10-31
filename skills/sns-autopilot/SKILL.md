---
name: sns-autopilot
version: 0.1.0
description: |
  X(트위터)·Threads 운영 자동화. 참고 계정/Threads 인기글(좋아요 200+, 작성자 이어쓰기 포함) 수집 →
  7일 창으로 유행 型 재작성·명명 → 型 이름으로 초안 작성 → 의심 담당이 숫자 실적·30일 주제중복·구도중복 검증 →
  사람은 낸다/안 낸다만 결정 → 아침·점심·밤 슬롯 자동 보충·자동 게시 → Threads 자동 전재 →
  1만 임프 넘은 글에만 주제 맞춤 유도(#광고 자동 표기) → 아침 글 답글 자동 응답 → X/Threads 성과 비교·프로필 유입 집계.
  Use when asked to SNS 자동화, X 자동 게시, Threads 전재, 型 분석, 제휴 유도, AI 사원 운영.
allowed-tools: [Read, Write, Bash]
triggers: [sns-autopilot, X 자동화, 트위터 자동화, Threads 자동화, 쓰레드 자동화, X発信, Threads挑戦, AI社員]
metadata:
  license: Apache-2.0
  requires:
    bins: [python3]        # >= 3.10, 표준 라이브러리만
    optional: [anthropic]  # pip install anthropic — 없으면 Mock으로 리허설
  runtimes: [claude-code, codex]
---

## sns-autopilot

에이전트가 이 스킬을 받으면:

1. `config.json`이 없으면 `config.example.json`을 복사하고 사용자에게 참고 계정·주제·슬롯 시간만 묻는다.
   `facts.example.json`→`facts.json`(증빙 있는 실제 수치), `cta.example.json`→`cta.json`(유도문)도 같이.
2. 처음엔 `"dry_run": true`로 `python3 -m autopilot -c config.json morning && ... night && ... queue` 실행해 결과를 보여준다.
3. 사용자가 승인하면 `X_USER_TOKEN`, `THREADS_TOKEN`, `ANTHROPIC_API_KEY`를 환경변수로 넣고 `dry_run: false`.
4. `deploy/crontab.example`을 설치한다. 승인은 `queue` → `approve <id>` / `reject <id> --note "이유"`.
5. 지적 사항은 `feedback "..."` — 다음 날 아침 `morning`이 `playbooks/learned.md`에 넣어 전원에게 적용.

검증: `python3 -m unittest discover -s tests` (네트워크·키 불필요).
