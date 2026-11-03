# hetbahn_studio MCP 서버 명세 (mcp-builder 스킬로 구현)

목적: Gemini API(이미지·영상·음악)를 MCP 도구로 감싸서, 모든 생성에 LOCK 문장을 자동으로 붙이고 공모전 증빙 원장을 자동으로 기록한다.
스택: Python FastMCP, stdio, 키는 환경변수 GEMINI_API_KEY만 사용(파일·로그·응답에 절대 출력 금지).

도구
- hb_still(shot_id, prompt, lock=["PRODUCT","S","N","STYLE"], refs=[파일경로], n=3, aspect="1:1"|"9:16"|"4:5")
  → LOCK 문장을 locks.json에서 읽어 프롬프트 앞뒤에 그대로 붙여 생성, work/stills/<shot_id>_tN.png 저장
- hb_clip(shot_id, first_frame, prompt, end_frame=None, seconds=5, takes=3)
  → 영상 모델 호출, 할당량 초과(429)면 대기 후 재개 시각을 반환, work/clips/<shot_id>_tN.mp4
- hb_music(brief, seconds, bpm) → work/audio/music_*.wav
- hb_contact_sheet(path, every=0.2) → ffmpeg로 타임코드 contact sheet 생성
- hb_logo_composite(video_or_image, logo_paths, layout) → assets/의 공식 PNG만 합성. 로고 파일이 없으면 오류로 중단
- hb_ledger_export() → proof/생성원장.jsonl과 사람이 읽는 proof/생성원장.txt(시각·서비스·모델·프롬프트 전문·seed·job id·결과 파일)

원칙(mcp-builder): 도구 이름은 hb_ 접두사, 설명은 짧고 행동형, 오류 메시지에 다음 행동을 적는다(예: "할당량 초과: 14:20 이후 재시도").
