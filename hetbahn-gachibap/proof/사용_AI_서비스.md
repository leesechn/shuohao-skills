# 사용 AI 서비스 및 도구 (증빙)

| 용도 | 서비스 / 모델 | 결과물 | 비고 |
|---|---|---|---|
| 인물·공간 스틸 13장 (실사 6, 미니어처 7) | Figma AI `generate_image` / gemini-3.1-flash-lite-image | proof/stills/*.png | 프롬프트 전문: proof/생성원장.txt |
| 한 식탁 와이드 스틸 1장 | Runway `generate_image` / nano-banana-2-lite (task 52e77dbf-…) | proof/stills/S10_real.jpg | Runway 크레딧 4 사용 |
| 시도했으나 생성 0건 | Higgsfield gpt_image_2_5, nano_banana_2_lite | - | 무료 플랜이라 '베이직 이상 필요'로 거절됨, 과금 없음 |
| 영상 I2V | 사용 안 함 | - | Higgsfield 무료 플랜, Runway 영상은 유료 플랜 필요, Krea 크레딧 0 |
| 제품 | 실제 햇반 사진(refs/01·02·04) 컷아웃 합성 | work/assets → 영상·캐러셀 | AI로 생성한 제품 0컷 |
| 로고 | 공식 KV(refs/01)에서 추출한 흰색 로고 | work/assets/logo_*_kv.png | assets/에 공식 PNG를 넣으면 자동 교체 |
| 모션·타이포·효과·편집 | 자체 코드 (Python, NumPy, OpenCV, Pillow, FFmpeg) | tools/pipeline/ | 모든 효과는 타임라인 시간 t의 순수 함수 |
| 음악·효과음 | 자체 합성 (Karplus-Strong 기타, 가산 합성 마림바·벨, 노이즈 SFX) | work/audio/mix.wav | 90 BPM, -14 LUFS |
| 자체 MCP | tools/hetbahn_studio (Gemini 이미지·Veo 영상 래퍼, LOCK 자동 삽입, 원장) | - | GEMINI_API_KEY가 없어 이번 결과물 생성에는 쓰지 않음, stdio 테스트 통과 |
| 독립 비평 | Claude 서브에이전트 3회 (매번 새 에이전트) | 이 문서 하단 비교표 | 빌더는 자기 작업을 채점하지 않음 |
