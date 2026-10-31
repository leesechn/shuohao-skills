# sns-autopilot

원문 트윗 4개(《X発信》《Threads挑戦》《アフィの裏側》《AI社員で1人会社》) 20개 항목을 **그대로 코드로** 옮긴 운영 자동화.
Python 표준 라이브러리만 사용, Claude API는 선택(`pip install anthropic`).

## 20개 항목 ↔ 구현 위치

| # | 원문 | 구현 (`autopilot/pipeline.py`) |
|---|---|---|
| X1 | 참고 계정 글 매일 아침 수집, 7일분으로 유행 型 재작성 | `collect_reference` + `rebuild_patterns` (7일 미확인 型 비활성) |
| X2 | 유행 이탈 초안은 전날 밤 재작성 | `refresh_off_trend` (night) |
| X3 | 아침·점심·밤 슬롯 비면 재고 자동 보충 | `fill_slots` + `top_up_stock` |
| X4 | 같은 주제 30일 내 중복 체크 | `is_duplicate_topic` (주제명 + 본문 3-gram Jaccard) |
| X5 | 시간 되면 자동 게시 | `publish_due` (tick) |
| T1 | Threads 인기글 검색, 좋아요 200+만 | `collect_threads` (좋아요 수 확인 불가 글은 제외) |
| T2 | 본문 + 답글 이어쓰기(続き)까지 | `ThreadsClient.self_thread` (작성자 본인 답글만) |
| T3 | X 글 Threads 자동 전재 | `publish_due` 내부 (Threads 실패가 X를 막지 않음) |
| T4 | 성장한 글 型에 이름 → 다음 초안에서 호출 | `rebuild_patterns` / `write <주제> --pattern <型이름>` |
| T5 | 같은 글 X vs Threads 성장 비교 | `compare` |
| A1 | 1만 임프 넘은 글에만 나중에 유도 | `attach_cta` (자기 답글로 부착) |
| A2 | 유도문은 글 주제에 맞춰 선택 | `pick_cta` (태그 일치 → 없으면 작성 담당 판단) |
| A3 | 초안 속 실적 숫자 진위 자동 체크 | `Doubter.fact_check` (`facts.json` 증빙값 ±2%만 통과) |
| A4 | 아침 글 답글 자동 응답 | `auto_reply` (링크 답글 스킵, 1회 상한, 중복 응답 방지) |
| A5 | 어느 글에서 프로필로 왔는지 집계 | `attribution` (X `user_profile_clicks`) |
| AI1 | 수집·작성·의심 담당 분리 | `agents.py` Collector / Writer / Doubter |
| AI2 | 규칙은 수순서에, 매번 읽힘 | `playbooks/*.md` 호출마다 재로딩 |
| AI3 | 지적 사항 다음 날부터 전원 수순서에 | `feedback` → 다음 날 `apply_feedback` → `learned.md` |
| AI4 | 이미지 구도 대장, 같은 그림 금지 | `image_ledger` + `check_image` (6요소 중 4개↑ 같으면 거절) |
| AI5 | 사람은 낸다/안 낸다만 | `queue` / `approve` / `reject` (`require_approval: true`) |

## 실행

```bash
cp config.example.json config.json; cp facts.example.json facts.json; cp cta.example.json cta.json
python3 -m autopilot -c config.json morning   # 수집·型
python3 -m autopilot -c config.json night     # 내일 슬롯 채우기
python3 -m autopilot -c config.json queue     # 승인 대기
python3 -m autopilot -c config.json approve 3
python3 -m autopilot -c config.json tick      # 게시·전재·유도·응답
python3 -m autopilot -c config.json compare | attribution
```

실전 전환: `dry_run:false` + 환경변수 `X_USER_TOKEN`, `THREADS_TOKEN`, `ANTHROPIC_API_KEY`, 그리고 `deploy/crontab.example` 설치.

## 알려진 한계 (솔직하게)

- **X 비용**: 종량제 기준 게시 $0.015/건, **URL 포함 게시 $0.20/건**, 타인 글 읽기 $0.005/건. 유도 답글(링크)이 가장 비쌈 → A1 임계값을 낮추지 말 것.
- **X 토큰 갱신**: OAuth2 사용자 토큰은 2시간 만료. 리프레시 로직은 미포함(외부에서 갱신해 환경변수 주입).
- **Threads 타인 글 좋아요 수**: `keyword_search` 결과에 `like_count` 필드가 제공되는지 공개 문서로 확인 못 함(불확실). 안 주면 T1은 0건 → 이 경우 수동 CSV 투입 필요.
- **Threads 게시물별 프로필 유입**: API 미제공 → A5는 X만. Threads는 UTM 링크 클릭으로 대체해야 함.
- **자동 답글(A4)**: X 자동화 규칙상 대량·무차별 자동 답글은 정지 사유. 본인 글에 온 답글만, 상한 10건으로 제한.
- 型 추출 품질은 LLM 의존. Mock 모드 결과는 동작 확인용일 뿐 콘텐츠 품질이 아님.
