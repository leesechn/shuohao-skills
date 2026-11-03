# Claude Code 마스터 프롬프트 v3 — 「햇반 같이밥: 혼자선 안 열리는 햇반」 (햇반 30주년 '갓 지은 AI디어')

v3 핵심 변경: 아이디어의 중심을 '멀리서 같이 먹기'(이미 본 원격 식사)에서 **'혼자선 안 열리는 햇반'**이라는 제품 장치로 옮겼다. 원격 식탁은 아이디어가 아니라 결말(보상)이 된다.
- 세상에 없는 햇반: 두 개가 한 쌍인 '같이밥 페어'. 짝과 같은 순간 데워야 필름이 열린다(실제 4중 차단 필름 위 다섯 번째 '링크층' 콘셉트).
- 낭비 없는 장치: 햇반의 실제 실온 보관 기간 9개월을 '약속 기한'으로 쓴다. 9개월이 지나면 혼자서도 열리고 뚜껑에 "다음엔 꼭"이 뜬다.
- 미래 일상: 빈말 대신 '페어를 보내는' 문화. 기숙사와 고향, 할머니와 손주, 야근 사무실과 친구로 번진다.
- 웃음 장치: 혼자 열려다 탭이 '톡' 하고 다시 붙는 순간(두 도시에서 같은 박자로).
v2에서 고친 것(유지): 실제 둥근 20각 용기 고정, KV 톤, 인기투표 대응, cook-loop 게이트, mcp-builder, taste skill, 이 프로젝트 한정 전체 허용 설정.

## 0. 사전 준비 (아이폰·아이패드 기준)
1. 첨부 `햇반같이밥_ClaudeCode_프로젝트키트.zip`을 파일 앱에서 탭해 압축을 풀고, GitHub 새 비공개 레포에 폴더 내용 전체를 올린다(github.com → Add file → Upload files). 들어 있는 것: `CLAUDE.md`, `.claude/settings.json`(이 레포 한정 전체 허용), `.mcp.json`(자체 MCP), `refs/`(공모전 포스터·햇반 용기 사진 4장), `tools/hetbahn_studio/SPEC.md`.
   - 숨김 파일(.claude, .mcp.json)이 업로드에서 빠지면, 아래 프롬프트의 0단계가 직접 다시 만든다.
2. `assets/`에 공식 로고 PNG 2개를 넣는다: `logo_hetbahn.png`, `logo_hetbahn30.png`(@hetbahn.30years DM 또는 구글폼 안내 파일).
3. claude.ai/code에서 이 레포로 세션을 연다(프로젝트 스레드가 아닌 단일 레포 세션이어야 `.claude/settings.json` 권한이 적용됨). 환경 설정의 환경변수에 `GEMINI_API_KEY`(새로 발급한 키)를 넣는다. 이전 대화에 노출된 키는 폐기.
4. 완전 무확인 실행이 필요하면 그 세션만 권한 모드를 bypass로 바꾼다. 공식 문서상 bypassPermissions는 프로젝트 파일에서 켤 수 없고 세션 단위로만 가능하다. 프로젝트 파일에는 모든 도구 허용 + 파일 편집 자동 승인(acceptEdits)을 넣어 두었다.

## 1. 붙여넣을 프롬프트

```
너는 이 레포의 총괄 감독 겸 엔지니어다. CLAUDE.md를 먼저 읽고 그대로 따른다.
목표: CJ제일제당 햇반 30주년 AI 공모전 '갓 지은 AI디어'에서 대상을 노리는 출품작 2개를 2026-11-13 23:59 KST 전에 완성한다.
 · 출품 A: 주제② "햇반이 지을 미래를 보여줘밥" 9:16 1080x1920 30~33초 영상 「햇반 같이밥」. 실사안과 미니어처안 둘 다.
 · 출품 B: 주제① "미래의 햇반을 만들어밥" 4:5 1080x1350 캐러셀 5장 「세상에 없는 햇반, 같이밥」.

━━ 0. 환경 부트스트랩 ━━
- CLAUDE.md, .claude/settings.json, .mcp.json, tools/hetbahn_studio/SPEC.md가 없으면 첨부 키트 내용대로 만들고 커밋한다. 권한 설정은 다음 세션부터 적용된다는 점을 한 줄로 알린다.
- 스킬: .claude/skills/에 design-video-suite, cook-loop, cinematic-aesthetics, design-taste-frontend, wan3-prompts, remotion-best-practices, ffmpeg-skill이 있는지 확인. 없으면 claude.ai 동기화 스킬 목록을 확인하고, 그래도 없으면 레포의 design-video-suite.zip을 풀어 넣는다.
- mcp-builder: git clone --depth 1 https://github.com/anthropics/skills /tmp/as && cp -r /tmp/as/skills/mcp-builder .claude/skills/ 후 SKILL.md를 읽고 tools/hetbahn_studio/SPEC.md대로 Python FastMCP stdio 서버를 구현·테스트한다(키 없이 실행하면 친절한 오류를 내는지까지).
- /mcp에서 claude.ai 커넥터(Runway·Higgsfield·Krea·Canva·Figma)와 hetbahn_studio가 연결됐는지 확인하고 실제 도구 이름 접두사를 기록한다. settings.json의 mcp__claude_ai_* 허용 규칙과 다르면 실제 이름으로 고친다.

━━ 1. 공모 의도 분석 (모든 판단의 기준) ━━
공고 핵심 문장: "아직 세상에 없는 새로운 햇반부터, 햇반이 바꿔놓을 미래의 일상까지", 주제②는 "음식을 넘어 일상 곳곳으로 확장된 햇반의 미래 라이프스타일". 제목 '갓 지은 AI디어'는 '밥을 짓다' 말장난.
출품 A는 아래 네 질문에 소리 없이 답해야 한다.
 Q1 세상에 없는 햇반인가 → '같이밥 페어': 두 개가 한 쌍, 짝과 같은 순간 데워야 열린다. 혼자 당기면 탭이 다시 붙는다.
 Q2 미래의 일상인가 → "언제 밥 한번 먹자"를 보내는 대신 페어를 보낸다. 받은 사람과 보낸 사람이 같은 순간 열면 김을 따라 두 식탁이 하나로 이어진다.
 Q3 음식을 넘어 일상 곳곳으로 확장됐나 → 햇반이 '약속을 지키게 만드는 물건'이 된다(기숙사↔고향 집, 할머니↔손주, 야근 사무실↔친구).
 Q4 햇반이어야만 하나 → 실제 햇반의 사실 세 개가 장치의 근거: 9개월 실온 보관 = 약속 기한, 4중 차단 필름 = 링크층을 얹을 자리, 전자레인지 한 번이면 되는 즉석밥 = '지금 당장' 가능한 약속. 다른 제품으로 바꾸면 성립하지 않는다.
브랜드 정렬: 햇반 30년 = 갓 지은 밥을 언제 어디서나. 용기 인쇄 문구 '언제나 맛있는 집밥'(refs/04). 해외 60여 개국 K푸드 확장(뉴욕 친구). 다음 30년의 햇반 = 밥뿐 아니라 '같이'를 언제 어디서나.
카피 구조: 대표 빈말 "언제 밥 한번 먹자"의 '언제'가 햇반의 '언제나'로. 제품 카피 "혼자선 안 열립니다." 엔드 카피 "빈말을 진짜로 짓다."(짓다 = 밥을 짓다).
인기투표 대응: 첫 프레임이 썸네일, 3초 안에 "내 얘기다" 공감, 7초 안에 '안 열리는 햇반' 웃음, 엔딩에서 친구를 태그하고 싶게(캡션 "혼자선 안 열리는 햇반, 누구랑 열래?").

━━ 2. 지난 회차 실패 → 하드 제약 ━━
1) 제품이 컷마다 다른 모양으로 변함, 실제 햇반과 다른 네모 용기 → PRODUCT LOCK 문장 고정 + refs/02~04를 이미지 레퍼런스로 매번 첨부 + 실루엣 검사(아래 6).
2) 얼굴의 AI티 → 손·뒷모습·3/4 측면 위주, 정면 클로즈업 1컷 이하. 미니어처안을 대조군으로.
3) 원인과 결과가 다른 화면 → 모든 핵심 사건은 한 화면 안에서.
4) 정지 이미지로 때움 → 사람이 움직이는 컷은 실제 I2V 클립. 실패하면 재생성.
5) 신파 → KV 포스터의 팝·말장난 톤. 웃음 3회(혼자 열려다 탭이 다시 붙음, 두 도시에서 같은 박자로 / 숟가락이 빛 경계에서 부딪힘).
7) 익숙한 원격 식사 연출 → 화상통화 화면·홀로그램·VR 고글 금지. 연결은 오직 제품(페어·링크 마크·김)으로만 일어난다.
6) 로고 누락 → 로고 PNG 없으면 export 중단.

━━ 3. 레퍼런스 기준표 (cook-loop 1단계, 먼저 작성해 work/reference_table.md로 저장) ━━
refs/01 KV: 배경 레드 #B52A23(스크린샷 샘플), 하프톤 도트, 손글씨풍 두툼한 레터링, 노랑 #FFFC87, 금빛 궤적선, 4각 반짝이, 정면 제품 컷, 정중앙 구도.
refs/02 정면: 따뜻한 확산광, 미색 배경, 뚜껑 왼쪽 빨간 원형 배지(로고 레드 사진 샘플 #BB1A1F), 오른쪽 밥공기 사진 인쇄, 풀탭 왼쪽 아래.
refs/03 기술: 4중 차단 필름(인쇄·강도보강·산소차단·접착), 3중 차단 용기, 20각 용기(외력·음압 분산), 내압 구조.
refs/04 용기: 둥근 얕은 용기, 바깥 20각 세로 면, 넓은 림, 안쪽 바닥 둥근 홈.
표에는 각 장의 빛 방향·색온도·주조색 HEX·재질·구도·카메라 높이를 적는다. 이후 모든 비교의 기준.
합격선: 제품 실루엣 일치 98% 이상(아래 6의 마스크 IoU 0.90 이상과 육안 검수 둘 다), 컷 점수 10점 중 9.0 이상, 자기 점수는 15%p 깎아서 보고.

━━ 4. 아트 디렉션 (7축 수치, 감독 이름은 생성 프롬프트에 쓰지 않음) ━━
두 개의 결: 실사 본편은 밝고 차분한 생활 영화, 타이포 카드는 KV처럼 팝. 이 대비가 리듬이다.
구도: 정중앙 대칭. 9:16을 위(서울 21:00)·아래(뉴욕 08:00)로 나눈 거울 구도, 소품 위치를 수평축 대칭으로 맞춤. 주연 피사체는 프레임의 60~85%.
색(본편): 쌀백 #F8F7F2, 서울 밤 #1C2733 + 텅스텐 #E9A85B, 뉴욕 아침 #DDE7EC + 데이라이트 #A9C2D1, 잉크 #1A1A1A. 채도 높은 색은 햇반 레드뿐. 베이지 배경 금지.
색(타이포 카드): KV 레드 풀필드 #B52A23 + 하프톤 도트 그러데이션 + 노랑 #FFFC87은 한 단어만 + 금빛 궤적선과 4각 반짝이. 빛나는 구슬·충격파 링 금지.
조명: 서울 2700K 펜던트 1등 + 창밖 아파트 불빛 / 뉴욕 6500K 낮은 아침 햇살이 오른쪽에서 사선 / 합쳐진 식탁은 왼쪽 반 텅스텐·오른쪽 반 데이라이트가 중앙선에서 섞임.
렌즈·질감: 35mm, f/2.8, 부드러운 필름 입자, 하이라이트에 약한 halation, 밝게. 어두운 오프닝 금지.
타이포(OFL, 코드 렌더): 카드 제목 Black Han Sans + 하프톤 드롭섀도, 채팅·설명 Gowun Dodum, 엔드 카피 Gowun Batang. 시스템 기본 글꼴 금지.
taste skill: design-taste-frontend의 draw.mjs를 --sector food --keep palette,type로 돌려 타이포 카드·캐러셀 구성안 3개를 받고, 브리프 인벤토리(4중 필름, 20각, 9개월, 언제나 맛있는 집밥, 김, 풀탭)에서 가장 이 브랜드다운 안을 고른다. inspect.mjs로 금지 요소 검사.
편집: 실측 BPM 박자에 모든 컷 정렬, 엔드카드 외 0.6초 넘게 멈춘 화면 금지, 컷마다 크기 변화(매크로→와이드→오버헤드→UI→타이포).
미니어처안: 같은 콘티를 양모 펠트 인물·골판지 도시·솜 김·셀로판 창으로. 12fps 투스, 인형의 집 단면. 햇반 용기는 실물 그대로(미니어처 세계 속 진짜 햇반이 주인공).

━━ 5. LOCK 문장 (매 생성에 글자 하나 바꾸지 않고 복사, hetbahn_studio가 자동 삽입) ━━
PRODUCT LOCK: "A Korean instant rice bowl exactly like the reference photos: a palm-sized round shallow white polypropylene bowl whose outer wall is made of 20 flat vertical facets, a flat wide rim, sealed with a white matte film lid that has a small rounded pull-tab sticking out of the rim at the front-left; on the left half of the lid a solid red circle badge with nothing written in it, on the right half a soft printed photo of a rice bowl; next to the red circle a small embossed rice-grain mark that can glow warm amber. When opened: glossy, separate, pearly white rice grains. No letters, numbers, barcodes or logos anywhere."
STYLE LOCK(실사): "Photoreal, 35mm lens look, f/2.8, soft natural film grain, bright clean exposure with nothing crushed to black, gentle halation on highlights. No text, no letters, no logos, no watermark."
STYLE LOCK(미니어처): "Handmade stop-motion miniature set: needle-felted wool figures, corrugated cardboard buildings, cotton-wool steam, cellophane windows, tilt-shift shallow focus, warm practical lights. The rice bowl is a real full-size product photographed in the miniature set. No text, no logos."
CAST S(서울): "Korean woman in her late 20s, shoulder-length straight black hair tucked behind the right ear, oversized oatmeal knit cardigan, thin silver ring on the right index finger."
CAST N(뉴욕): "Korean man in his late 20s, short black hair, navy crewneck sweatshirt, black digital watch on the left wrist."
→ Higgsfield manage_reference_elements로 PRODUCT(refs/02·04 업로드)·S·N을 Element로 고정. 빨간 원에는 후처리로 공식 햇반 로고를 트래킹 합성(정지·느린 컷만), 큰 움직임 컷은 빈 빨간 원 유지.

━━ 6. 물리·현상 명세 (형용사 대신 메커니즘) ━━
- 가열: 필름 뚜껑이 증기압으로 살짝 부풂(3~4mm 돔). 링크 마크가 데워질수록 아이보리 → 호박빛으로 변함(감온 잉크 개념).
- 잠김(혼자일 때): 풀탭을 당기면 필름이 림에서 2mm만 들렸다가 고무줄처럼 탄성 있게 제자리로 '톡' 붙고, 링크 마크가 짝이 있는 방향으로 두 번 깜빡인다. 힘으로 뜯는 느낌이 아니라 '아직 아니야' 하는 느낌.
- 페어 박스: 같은 햇반 두 개가 맞물린 투명 슬리브에 들어 있고, 꺼내면 각 뚜껑의 링크 마크가 서로를 향해 한 번 점등.
- 개봉: 짝과 같은 순간 데운 뒤 풀탭을 당기면 필름이 원통처럼 말리며(말림 반경 점점 감소) 림에서 떨어지고, 필름 안쪽 응결 물방울이 빛을 받아 반짝임.
- 김: 0.4초 분출 → 층류 기둥 → 위로 갈수록 옅어지고 가장자리에서 말림, 역광에서 전방산란으로 밝게. 연기처럼 회색·탁하면 실패.
- 밥: 윤기 있는 낱알, 반투명 진주빛, 하이라이트 반짝임, 살짝 뭉친 덩어리.
- 코드 이펙트(Remotion + @remotion/three, 전부 타임라인 시간의 순수 함수): ①경계 녹임 = fbm 노이즈 임계 마스크가 분할선 중앙에서 바깥으로 번지고 경계에 따뜻한 흰빛, 김 밀도로 구동 ②김 오버레이 = 시드 고정 파티클, 위치 = p0 + 상승·나이 + curl(p0·s, 나이)·진폭·나이 ③채팅 = 스프링(강성 300, 감쇠 30) 말풍선 ④빛 입자 = 김을 따라 위아래 화면을 오가는 미세 입자(구슬처럼 빛나게 하지 말 것).
- 제품 실루엣 검사: 모든 제품 컷 스틸에서 용기 마스크를 따고 refs/04 측면 실루엣과 IoU 계산, 0.90 미만 폐기.

━━ 7. 스토리보드 (실측 BPM 박자로 미세조정) ━━
S01 0.0–2.6  채팅 UI 매크로(코드). 프레임 0부터 완성된 화면. "언제 밥 한번 먹자"가 2016부터 2026까지 날짜와 함께 쌓이고, 답은 늘 "ㅇㅇ 언제 한번 ㅋㅋ". 썸네일 겸 훅.
S02 2.6–3.8  KV 카드: "10년째 빈말." '빈말'만 노랑.
S03 3.8–6.0  S가 또 "언제 밥 한번 먹자"를 치다가 지우고 입력창의 '같이밥 보내기'를 누른다(코드 UI) → 페어 박스가 열리며 햇반 하나는 서울에 남고 하나는 아래 뉴욕으로 떨어지고, 그 궤적이 화면 분할선이 된다(코드 3D).
S04 6.0–8.4  위아래 거울 분할: 서울 21:00 S / 뉴욕 08:00 N이 각자 혼자 데운 햇반을 열려는데 탭이 '톡' 다시 붙음(I2V, 손 위주, 두 도시 같은 박자).
S05 8.4–10.0 두 사람이 동시에 폰을 봄. 채팅 "지금?" / "지금."(코드).
S06 10.0–12.0 두 전자레인지가 같은 박자로 3·2·1(숫자는 코드 합성).
S07 12.0–13.4 동시에 '띵'. 두 링크 마크가 같은 프레임에 호박빛으로 켜짐.
S08 13.4–16.0 오버헤드 매크로: 두 손이 동시에 풀탭을 당기고 이번엔 열림. 김 분출. 히어로 컷.
S09 16.0–18.6 서명 변환①: 두 김 기둥이 분할선으로 모여 선을 녹임(코드 마스크 + 빛 입자).
S10 18.6–21.4 서명 변환②: 한 식탁 와이드. 왼쪽 반 텅스텐, 오른쪽 반 아침빛, 마주 앉은 S와 N이 웃음(Kling start=분할 프레임, end=식탁 프레임).
S11 21.4–22.8 숟가락 건배 매크로. 두 빛이 만나는 중앙선에서 정확히 부딪힘.
S12 22.8–25.0 일상 곳곳 몽타주: 3분할(기숙사 ↔ 고향 집 부엌 / 할머니 ↔ 손주 / 야근 사무실 ↔ 친구 원룸). 혼자 안 열리던 햇반이 같은 박자에 함께 열리며 세 분할선이 김으로 녹음.
S13 25.0–27.8 KV 카드 + 제품: 페어 햇반과 뚜껑 분해도(실제 4중 차단 필름 + 다섯 번째 링크층). 두 줄: "혼자선 안 열립니다." / "약속 기한 9개월, 지나면 혼자서도 열려요."
S14 27.8–29.6 서명 변환③(코드): 첫 장면 채팅 "언제 밥 한번 먹자"에서 '한번'이 지워지고 '언제' 뒤에 노란 '나'가 붙어 "언제나 같이 밥 먹자".
S15 29.6–33.0 엔드 KV: "빈말을 진짜로 짓다." + "햇반 같이밥" + 공식 로고 2종 + "미래 햇반 콘셉트 · AI 활용 제작". 1.5초 이상 정지 가독.
릴스 안전영역(상단 250px·하단 340px)에는 글자·로고 금지.

━━ 8. 도구 역할 (고르게 쓰되 역할 중복 금지) ━━
- hetbahn_studio(Gemini): 첫 프레임 스틸 1순위(컷당 3안) · 음악(Lyria 계열, 88~92 BPM, 나일론 기타 플럭·마림바·가벼운 핸드클랩, '띵'에서 리프트, 엔드카드에서 정확히 끝나게 백타이밍) · 원장 기록 · contact sheet · 로고 합성.
- Higgsfield: seedance_2_5 I2V(draft:true 480p로 3테이크 비교 → 선택분만 draft_job_id로 1080p 확정), kling3_0 start/end frame(S10), Element 고정, virality_predictor(완성본 훅 점검), upscale_video.
- Runway: 스틸 2순위, generate_sound_effect(전자레인지 험, 두 곳 동시 '띵', 필름 뜯김, 김 쉬익, 숟가락 클링).
- Krea: 서울·뉴욕·식탁 무드보드(create_moodboard), 선택 스틸 enhance_image.
- Figma: 제품 LOCK 시트(정면·측면·위·개봉 4뷰)와 13컷 스토리보드를 한 파일로(아이패드 검토용).
- Canva: 출품 B 캐러셀 편집본 업로드(아이패드에서 문구·로고 위치 수정용).
- Agent(서브에이전트): 독립 비평가.

━━ 9. 컷별 프롬프트 ━━
아래 "## 3. 컷별 완성 프롬프트"(이 md 하단)의 문장을 그대로 쓴다. 규칙: 스틸 = 장면 + LOCK + STYLE LOCK + "negative space reserved for type where noted". I2V = 장면 묘사 반복 금지, 카메라 4슬롯 1문장 + 행동 1동작 + 오디오 + "Preserve the bowl geometry and faces exactly. No morphing. No text." 클립 4~6초, 테이크 3개, 기하 왜곡 테이크 폐기.

━━ 10. cook-loop 라운드와 품질 게이트 ━━
라운드 1: 레퍼런스 기준표 + 스틸 전 컷(실사·미니어처) → contact sheet → 사용자에게 SendUserFile로 전송, 아래 형식으로 보고하고 승인 대기(유일한 정지 지점).
[라운드 N] 바꾼 것 / 스틸 / 기준표 대비 일치율(구도·색·재질·디테일·종합) / 남은 차이 TOP3 / 다음 계획
라운드 2 이후: 승인된 스틸로 I2V → 조립 → Gauntlet(스토리보드 critic → 컴포넌트 critic → 전체 critic → 검증 critic). 비평가는 매번 새 Agent이며 렌더·이 프롬프트 1·4·5절만 본다. 빌더는 자기 작업을 채점하지 않는다.
루브릭(각 10점): 무음 3초 이해 / 햇반 제품 식별 / 세상에 없는 햇반이 보이는가 / 처음 보는 아이디어인가(원격 식사 광고와 구별되는가) / 미래 일상이 보이는가 / 음식 너머 확장이 보이는가 / AI티 컷 수 / 팝·재치 톤 / 측정 품질. 평균 9.0 미만이거나 어느 항목이든 8.0 미만이면 다음 라운드.
측정: frozen-time(0.6초 초과 정지 0), loudness(−14 LUFS, 트루피크 −1 dBFS 이하, LRA 3 이상), 텍스트 대비 WCAG AA, 안전영역 침범 0, 실루엣 IoU 0.90 이상.
외부 채점: 사용자에게 줄 문구를 out/외부채점_문구.txt로 저장 — "아래 레퍼런스와 결과물 스크린샷을 비교해 10점 만점으로 냉정하게 채점해. 만든 사람 사정은 고려하지 마. 9.2 미만이면 감점 이유를 구체적으로 5개(위치·색·시간 포함) 적어."
A안(실사) vs 미니어처안: 같은 루브릭 critic 2명 + virality_predictor → 비교표. 최종 선택은 사용자.

━━ 11. 출품 B 캐러셀 (4:5, 5장, 장마다 다른 구도) ━━
1 히어로(정중앙 1점 투시): KV 레드 필드 위 맞물린 '같이밥 페어' 두 개, 링크 마크가 서로를 향해 점등. "혼자선 안 열리는 햇반".
2 분해도(측면 등각): 실제 4중 차단 필름(인쇄·강도보강·산소차단·접착) + 다섯 번째 '같이밥 링크층'(감온 잉크와 근거리 통신 칩, 콘셉트 표기) + 20각 내압 용기.
3 사용법(세로 3단, 김 곡선이 단을 잇는 시각 문법): 빈말 대신 페어를 보낸다 → 짝과 같은 순간 데운다 → 같이 열린다.
4 약속 기한(9칸 달력 시각 문법): 햇반의 실제 실온 보관 9개월 = 약속 기한. 지나면 혼자서도 열리고 뚜껑에 "다음엔 꼭". 버려지는 밥 없음.
5 엔드(여백 타이포): "빈말을 진짜로 짓다." + 로고 2종 + 콘셉트 표기.

━━ 12. 예산·보안 ━━
- 모든 유료 생성 전 get_cost·견적 조회. 총액이 [사용자 설정 한도]를 넘기 전에 멈추고 표로 보고. Gemini 영상 일일 한도에 걸리면 재개 시각을 기록하고 다른 컷을 먼저 진행.
- 키는 환경변수만. 커밋 전 git grep으로 키 패턴 검사.

━━ 13. 산출물 ━━
out/A_같이밥_실사_final.mp4, out/A_같이밥_미니어처_final.mp4, out/B_캐러셀_4x5/(png 5장 + zip), out/썸네일_9x16.png, out/비교표.md, out/캡션.txt(첫 줄 "혼자선 안 열리는 햇반, 누구랑 열래? 10년째 '언제 밥 한번 먹자'만 보낸 친구 태그해" + 투표 기간 11.23~11.26 안내 + @hetbahn.30years #햇반 #햇반AI공모전 #갓지은아이디어), proof/(스틸·원본 클립·생성원장·사용 AI 서비스 목록·프롬프트 전문), out/contact_sheet.jpg. 완성 파일은 SendUserFile로 보낸다.
끝나면 한 줄 상태 + 남은 위험(불확실 표시) + 사용자가 지금 할 일 한 줄.
```

## 2. /goal 압축판 (4,000자 이하)

```
/goal CLAUDE.md를 따라 햇반 30주년 공모전 출품작 완성. A: 주제② 9:16 1080x1920 30~33초 영상「햇반 같이밥: 혼자선 안 열리는 햇반」(실사안+미니어처안), B: 주제① 4:5 캐러셀 5장. 마감 2026-11-13 23:59, 인기투표 11.23~26.
아이디어: 세상에 없는 햇반 '같이밥 페어'(두 개 한 쌍, 짝과 같은 순간 데워야 필름이 열림, 실제 4중 필름 위 다섯 번째 링크층 콘셉트, 실제 실온 보관 9개월=약속 기한·지나면 혼자서도 열림) + 미래 일상(빈말 대신 페어를 보내는 문화, 같이 열면 김을 따라 두 식탁이 하나로) + 일상 곳곳 확장(기숙사↔고향·할머니↔손주·야근↔친구). 카피 "혼자선 안 열립니다." / '언제 밥 한번'→'언제나 같이 밥 먹자' / 엔드 "빈말을 진짜로 짓다." 화상통화·홀로그램·VR 금지, 연결은 제품으로만.
스킬: design-video-suite→cook-loop→cinematic-aesthetics→business-motion-film→wan3-prompts→design-taste-frontend→remotion→ffmpeg-skill→mcp-builder(github anthropics/skills, tools/hetbahn_studio/SPEC.md대로 Gemini 생성·LOCK 자동삽입·증빙원장 MCP 구현).
용기(refs/02~04, 틀리면 실패): 둥근 얕은 흰 용기, 바깥 20각, 넓은 림, 흰 필름 뚜껑, 앞 왼쪽 둥근 풀탭, 빈 빨간 원(공식 로고 후합성), 옆에 호박빛 쌀알 링크 마크. 실루엣 IoU 0.90 미만 폐기. 잠김: 탭이 2mm 들렸다 탄성 있게 '톡' 붙고 마크 두 번 깜빡.
LOCK: md 5절 PRODUCT·STYLE·CAST 문장 그대로, Higgsfield Element 고정.
15컷: 채팅 훅(2016~2026 "언제 밥 한번 먹자")→"10년째 빈말."→'같이밥 보내기'로 페어가 서울·뉴욕으로 나뉨→거울분할 서울21:00/뉴욕08:00 혼자 열려다 탭이 '톡'→채팅 "지금?" "지금."→숫자 3·2·1→동시 '띵'·마크 점등→손 풀탭 동시, 이번엔 열림→김이 분할선 녹임→한 식탁(왼쪽 텅스텐·오른쪽 아침빛, Kling start/end)→숟가락이 빛 경계에서 건배→몽타주 3쌍 동시 개봉→페어·분해도 "혼자선 안 열립니다."→'언제나 같이 밥 먹자'→엔드 KV+로고2종+"미래 햇반 콘셉트 · AI 활용 제작".
아트: 본편 밝은 생활 영화, 정중앙 대칭, 주연 60~85%, 35mm f/2.8 필름 입자, 채도색은 햇반 레드뿐. 카드: KV 레드 #B52A23·하프톤·노랑 #FFFC87 한 단어·금빛 궤적. 글꼴 Black Han Sans·Gowun Dodum·Gowun Batang. 엠대시·영문 대문자 라벨·빛나는 구슬·충격파 링·베이지 배경 금지. 박자 컷, 0.6초 초과 정지 금지, 안전영역(상250·하340px) 비움.
도구: 스틸 hetbahn_studio(Gemini, 3안)·대체 Runway / I2V Higgsfield seedance_2_5 draft 3테이크→1080p 확정, S10 kling3_0 / 효과음 Runway / 음악 Gemini 88~92BPM 백타이밍 / 무드보드 Krea / LOCK시트·콘티 Figma / 캐러셀 편집본 Canva / 훅 virality_predictor.
cook-loop: 기준표→전 컷 스틸·contact sheet를 SendUserFile로 보내고 승인 대기(유일한 정지)→I2V→조립→새 Agent 비평가 Gauntlet. 루브릭 9항목(독창성 포함) 평균 9.0 이상·전 항목 8.0 이상, 자기점수 15%p 차감 보고. 측정: frozen-time, −14 LUFS·TP≤−1, WCAG AA.
규칙: 로고는 assets/ 공식 PNG 2종만 합성, 없으면 export 중단. 유료 생성 전 비용 조회·한도 전 보고. 키는 환경변수만, 커밋 전 grep.
산출: out/ 실사·미니어처 mp4, 캐러셀 5장, 썸네일, 비교표, 캡션("혼자선 안 열리는 햇반, 누구랑 열래?"+친구 태그·투표 안내·필수 태그), proof/ 원장. 끝에 위험(불확실)과 사용자 할 일 한 줄.
```

## 3. 컷별 완성 프롬프트 (cook-loop 기준표 + wan3 출력 순서)

공통: 스틸 = [장면] + PRODUCT LOCK(제품 등장 시) + CAST(인물 등장 시) + STYLE LOCK. I2V = 카메라 4슬롯 + 행동 + 오디오 + 고정 꼬리문 "Preserve the bowl geometry and faces exactly. No morphing. No text."
미니어처안은 STYLE LOCK만 미니어처 문장으로 바꾸고 인물 묘사 앞에 "needle-felted wool figure of"를 붙인다.

S03 페어 박스(코드 3D, AI 아님): 같은 햇반 두 개가 투명 슬리브에 맞물려 있다가 슬리브가 미끄러져 열리고, 하나는 위 서울에 남고 하나는 아래로 떨어지며 그 궤적이 분할선이 된다. 두 링크 마크가 서로를 향해 한 번 점등.
S04a 서울 첫 프레임(1:1): "A compact Seoul officetel kitchenette at 9 pm: white square tile backsplash, a single warm 2700K pendant light, a window behind showing apartment blocks with lit windows. CAST S stands at the counter in three-quarter back view holding the just-heated rice bowl, fingers on its pull-tab. Camera at chest height, symmetrical framing, the bowl clearly visible in the lower center."
S04a I2V: "Camera, Movement: locked-off / Speed: none / Framing: medium, unchanged / End: she tilts her head, puzzled. Action: she pulls the tab, the white film lifts a few millimeters then springs back flat with a tiny snap, the small mark beside the red circle blinks twice. Audio: a soft rubbery snap, a short surprised exhale."
S04b 뉴욕 첫 프레임(1:1, S04a의 거울): "A narrow New York prewar apartment kitchen at 8 am: white subway tile, a black-framed window with a fire escape outside, low cool 6500K morning sun raking in from the right. CAST N stands at the counter in three-quarter back view holding the just-heated rice bowl, fingers on its pull-tab. Mirrored composition of the Seoul frame."
S04b I2V: S04a 문장에서 she → he, End를 "he laughs and looks at his phone"으로.
S07 제품 매크로 첫 프레임(1:1, 서울·뉴욕 두 장): "Macro, 45-degree top view of the sealed rice bowl just taken out of a microwave, the white film lid slightly domed by steam, the small rice-grain mark next to the red circle glowing warm amber, faint steam at the rim. Seoul version: warm tungsten light. New York version: cool morning light."
S07 I2V: "Camera, Movement: slow push-in / Speed: very slow, about 2 cm / Framing: bowl fills 70% of frame / End: tighter on the glowing mark. Action: the mark brightens from ivory to amber in one breath. Audio: a clean two-tone microwave ding."
S08 손 개봉 첫 프레임(1:1): "Overhead macro of the rice bowl filling 70% of frame, a hand pinching the rounded pull-tab at the front-left. Seoul: silver ring on the right index finger, warm light. New York: black digital watch on the left wrist, cool light."
S08 I2V: "Camera, Movement: locked-off / Speed: none / Framing: overhead macro / End: lid fully peeled back. Action: this time the film releases; the hand peels it back in one smooth pull, the film curls into a roll, droplets on its underside sparkle, a surge of bright steam rises then settles into a soft column over glossy rice. Audio: soft film crackle, steam hiss."
S10 식탁 end frame(9:16): "One wooden dining table seen from the side at seated eye level, dead-center symmetry. CAST S sits on the left facing right, CAST N sits on the right facing left, each with an opened rice bowl and a spoon. The left half of the room is a Seoul night lit by a warm 2700K pendant, the right half is a New York morning lit by cool daylight from a window, the two lights blending softly along the table's center line. Both laughing."
S10 I2V(Kling, start = S09 마지막 프레임, end = 위 이미지): "Camera, Movement: slow dolly-out / Speed: slow / Framing: from the melting seam to the symmetric wide table / End: matches the end frame exactly. Action: the two halves slide together as steam clears, both look up and laugh. Audio: steam fading, a warm music lift."
S11 숟가락 건배: "Camera, Movement: locked-off / Speed: none / Framing: macro on the table center line where warm and cool light meet / End: spoons touching exactly on the line. Action: two spoons with rice tap together once. Audio: a bright spoon clink."
S12 몽타주 스틸 3장(1:1, 각각 위아래 분할): ①"a university dorm desk at night ↔ a hometown kitchen with a mother's hands" ②"a grandmother's kitchen table ↔ a grandchild's desk" ③"a late-night office desk ↔ a friend's small studio apartment". 모두 같은 햇반, 두 손이 같은 순간 풀탭을 당기기 직전. I2V는 각 1.5초 "both films release at the same moment and steam rises in both halves".
S13 페어·분해도: 코드(Three.js) 렌더. 필름 5층이 위로 떠오르며 펼쳐지고 맨 위 링크층만 호박빛. 옆에 9칸 달력이 채워지는 '약속 기한 9개월' 그래픽.
