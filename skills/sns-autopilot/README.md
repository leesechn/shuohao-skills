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

## 실제로 켜는 법 (서버 없이 GitHub Actions, 약 30분)

1. **이 브랜치를 `main`에 병합** — GitHub 예약 실행은 기본 브랜치에 있는 워크플로만 돈다.
   포크 저장소라면 Actions 탭에서 "I understand… enable" 눌러 활성화.
2. **X 키 4개** — developer.x.com → 앱 생성 → User authentication settings에서 권한 *Read and write* →
   Keys and tokens에서 API Key/Secret, Access Token/Secret 발급 (권한 바꾼 뒤 Access Token은 **재발급**).
   종량제 크레딧 충전 필요.
3. **Threads 토큰** — developers.facebook.com → 앱 생성(Threads API 사용 사례) → 권한
   `threads_basic, threads_content_publish, threads_manage_replies, threads_read_replies, threads_manage_insights, threads_keyword_search`
   → 장기 토큰(60일) 발급. *60일마다 재발급해서 Secret 교체 필요.*
4. **Claude 키** — platform.claude.com → API Keys.
5. 저장소 **Settings → Secrets and variables → Actions**
   - Secrets: `X_API_KEY` `X_API_SECRET` `X_ACCESS_TOKEN` `X_ACCESS_SECRET` `THREADS_TOKEN` `ANTHROPIC_API_KEY`
   - Variables: `AUTOPILOT_ENABLED` = `true` (끄려면 `false`)
6. `config.live.json`에서 `reference_accounts`(참고 계정 @아이디), `topics`, `threads_queries` 수정.
   `facts.live.json`에 **증빙 있는 실제 숫자**, `cta.live.json`에 유도문·링크 입력.
7. Actions → sns-autopilot → **Run workflow** → `cmd=morning` → 이어서 `cmd=night` 한 번씩 수동 실행.

이후 매일 자동:

| KST | 동작 |
|---|---|
| 06:05 | 지적 반영 → 참고계정·Threads 수집 → 型 재작성 → 지표 |
| 22:40 | 유행 이탈 초안 재작성 → 내일 3슬롯 채움 → **실행 결과 화면에 승인 대기표** |
| 07:30 / 12:10 / 21:00 | 승인된 글 X 게시 + Threads 전재 |
| 매시 47분 | 지표 갱신 · 1만 임프 넘은 글에 유도(#광고) · 아침 글 답글 자동응답 |

**사람이 하는 일 = 매일 밤 1번**: Actions → Run workflow → `cmd=approve`, `args=3` (안 낼 글은 `reject`, `args=3 --note "과장"`).
승인 없이 전부 자동으로 내려면 `config.live.json`의 `require_approval`을 `false`로.

주의: 공개 저장소면 `autopilot-state` 브랜치(초안·DB)도 공개된다. 비공개 저장소 권장(Actions 무료 2,000분/월 안에서 약 900분 사용 예상).

## 알려진 한계 (솔직하게)

- **X 비용**: 종량제 기준 게시 $0.015/건, **URL 포함 게시 $0.20/건**, 타인 글 읽기 $0.005/건. 유도 답글(링크)이 가장 비쌈 → A1 임계값을 낮추지 말 것.
- **X 인증**: OAuth 1.0a(만료 없음)로 해결. 서명은 X 공식 문서 예제값으로 테스트 검증.
- **Threads 토큰**: 60일 만료 → 수동 재발급 필요.
- **GitHub 예약 실행 지연**: 혼잡 시 수~수십 분 늦을 수 있음(게시는 늦게라도 반드시 나감).
- **Threads 타인 글 좋아요 수**: `keyword_search` 결과에 `like_count` 필드가 제공되는지 공개 문서로 확인 못 함(불확실). 안 주면 T1은 0건 → 이 경우 수동 CSV 투입 필요.
- **Threads 게시물별 프로필 유입**: API 미제공 → A5는 X만. Threads는 UTM 링크 클릭으로 대체해야 함.
- **자동 답글(A4)**: X 자동화 규칙상 대량·무차별 자동 답글은 정지 사유. 본인 글에 온 답글만, 상한 10건으로 제한.
- 型 추출 품질은 LLM 의존. Mock 모드 결과는 동작 확인용일 뿐 콘텐츠 품질이 아님.
