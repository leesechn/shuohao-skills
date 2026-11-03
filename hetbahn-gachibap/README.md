# 햇반 같이밥: 혼자선 안 열리는 햇반

햇반 30주년 AI 공모전 '갓 지은 AI디어' 출품 프로젝트입니다. 접수 마감은 2026-11-13 23:59 KST입니다.

| 출품 | 파일 | 규격 |
|---|---|---|
| A 실사안 (주제②) | `out/A_같이밥_실사_final.mp4` | 9:16, 1080x1920, 30fps, 33.0초, AAC 48kHz |
| A 미니어처안 (주제②) | `out/A_같이밥_미니어처_final.mp4` | 위와 같음, 화면만 12fps 스톱모션 |
| B 캐러셀 (주제①) | `out/B_캐러셀_4x5/` 5장, `out/B_캐러셀_4x5.zip` | 4:5, 1080x1350 PNG |
| 썸네일 | `out/썸네일_9x16.png` | 영상 첫 프레임 |
| 캡션 | `out/캡션.txt` | 태그와 투표 기간 안내 포함 |
| 비교표 | `out/비교표.md` | 실사안과 미니어처안 비교 |
| 증빙 | `proof/` | 생성원장, 원본 스틸, QA 측정값, 컨택트 시트 |

## 다시 만들기 (명령 한 줄)

```bash
python3 tools/pipeline/assets.py            # 실제 햇반 사진 컷아웃과 로고 준비
python3 tools/pipeline/build.py all         # 영상 2종 렌더, 4코어 기준 약 11분
python3 tools/pipeline/carousel.py          # 캐러셀 5장과 zip
python3 tools/pipeline/qa.py out/A_같이밥_실사_final.mp4 real   # 측정
```

**공식 로고 PNG 교체:** `assets/logo_hetbahn.png`와 `assets/logo_hetbahn30.png`를 넣고 위 명령을 다시 실행하면 됩니다. 그러면 공식 KV에서 잘라 쓰던 로고가 공식 파일로 자동 교체됩니다(`tools/pipeline/assets.py`의 `resolve_logos`).

## 구조

- `tools/pipeline/film.py`: 15컷 타임라인입니다. 90 BPM 박자에 맞춰 컷을 나눴고, 프레임마다 `(버전, t)`만으로 그려집니다.
- `tools/pipeline/fx.py`: 공통 그래픽 요소입니다. 하프톤 KV, 금빛 궤적, 김 파티클, 링크 마크, 스프링 애니메이션, 필름 질감이 들어 있습니다.
- `tools/pipeline/audio.py`: 음악과 효과음을 합성합니다. -14 LUFS, 트루피크 -1 dBTP 이하로 맞춥니다.
- `tools/pipeline/qa.py`: 정지 화면, 음량, 대비, 안전영역을 측정합니다.
- `tools/hetbahn_studio/server.py`: 자체 MCP 서버입니다(Gemini 생성 + LOCK 자동 삽입 + 증빙 원장). 테스트는 `test_server.py`입니다.

## 원칙

- 제품은 refs/의 실제 햇반 사진만 컷아웃해서 합성합니다. AI로 생성한 제품 컷은 0입니다.
- 로고, 글자, 숫자는 모두 코드로 넣습니다. AI가 만든 글자는 없습니다.
- 미래 기능(링크층, 감온 마크, 같이 열림)은 화면에 '미래 햇반 콘셉트 · AI 활용 제작'으로 표기합니다. 사실로 쓴 것은 실제 정보인 4중 차단 필름, 3중 차단 용기, 20각 내압 구조, 9개월 실온 보관뿐입니다.
