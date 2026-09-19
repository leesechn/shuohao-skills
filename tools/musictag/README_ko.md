# musictag.py — iPad a-Shell 음원 다운로드·태깅

유튜브 링크 하나로 **다운로드 → 곡 정보 검색 → 커버·태그·가사 삽입 → 정리된 파일명 저장**까지
한 번에 끝내는 단일 파일 스크립트입니다. PC 없이 iPad(a-Shell)만으로 동작합니다.

- `subprocess` / `os.system` / 셸 호출 없음 (a-Shell에서 불안정)
- ffmpeg 후처리 없음 — `bestaudio[ext=m4a]` 원본을 그대로 저장
- 컴파일이 필요한 패키지(Pillow 등) 사용 안 함
- 터미널이 싫으면 **앱 모드**(`musictag_app.py`) — Safari로 열고 홈 화면에 추가

## 1. 설치

a-Shell을 열고 아래를 차례대로 입력합니다.

```bash
pip install -U yt-dlp mutagen
```

`musictag.py`(필수)와 `musictag_app.py`(앱 모드용)를 `~/Documents`에 둡니다.
a-Shell에서 바로 받는 것이 가장 쉽습니다.

```bash
cd ~/Documents
curl -O https://raw.githubusercontent.com/leesechn/shuohao-skills/claude/ipad-ashell-music-tagger-o2ewbw/tools/musictag/musictag.py
curl -O https://raw.githubusercontent.com/leesechn/shuohao-skills/claude/ipad-ashell-music-tagger-o2ewbw/tools/musictag/musictag_app.py
```

직접 옮기려면 둘 중 하나입니다.

- **파일 앱**: `musictag.py`를 "나의 iPad → a-Shell" 폴더에 복사
- **a-Shell 안에서 직접 작성**:

```bash
cd ~/Documents
vim musictag.py
```

`vim`에서 `i`를 눌러 입력 모드로 바꾸고 코드를 붙여넣은 뒤, `Esc` → `:wq` → `Enter`로 저장합니다.

설치 확인:

```bash
cd ~/Documents
python3 musictag.py show 아무파일.m4a
```

## 2. 앱으로 쓰기 (권장)

터미널 입력이 번거로우면 **웹 앱 모드**를 쓰세요. a-Shell이 iPad 안에서 로컬 서버를 띄우고,
Safari가 그 화면을 보여줍니다. 홈 화면에 추가하면 아이콘·전체화면까지 앱처럼 동작합니다.

```bash
cd ~/Documents
python3 musictag_app.py
```

실행하면 아래 같은 주소가 나옵니다. **`?k=...`까지 통째로** 복사하세요.

```text
http://127.0.0.1:8080/?k=Xk3nQ8vTb2wQ
```

1. Safari 주소창에 붙여넣고 이동
2. 공유 버튼 → **홈 화면에 추가** → 이름을 `musictag`로
3. 다음부터는 홈 화면 아이콘만 누르면 됩니다

화면에서 할 수 있는 것:

| 탭 | 하는 일 |
| --- | --- |
| **추가** | 링크 붙여넣기 → 곡 후보 선택 → 정보·가사·커버 확인 → 저장 |
| **보관함** | 저장한 곡 목록, 태그 수정, 커버 교체, 삭제 |

커버는 **앨범 아트 / 유튜브 썸네일 / 사진 앱에서 고르기 / 없음** 중에서 탭으로 고릅니다.
가사는 직접 준비한 텍스트를 붙여넣는 칸이 있습니다(자동 검색 기능은 없습니다).

### 앱 모드에서 꼭 알아야 할 것

- **a-Shell을 닫으면 서버도 멈춥니다.** Safari와 a-Shell을 **Split View**로 나란히 두세요.
  a-Shell이 백그라운드로 완전히 내려가면 iOS가 프로세스를 정지시켜 화면이 멈춥니다.
- 주소의 `?k=...`는 **접속 키**입니다. 같은 기기의 다른 앱이 서버를 건드리지 못하게 막습니다.
  키는 `~/Documents/.musictag_key`에 저장되며 바꾸고 싶으면 그 파일을 지우면 새로 만들어집니다.
- 서버는 `127.0.0.1`에만 묶여 있어 같은 와이파이의 다른 기기에서는 접속되지 않습니다.
- 포트가 겹치면 `python3 musictag_app.py --port 8081`.

### 다른 기기 브라우저에서 열기

`--lan`을 붙이면 **같은 와이파이에 있는 다른 기기**(노트북, 폰, 다른 태블릿)의 브라우저에서도
열립니다. iPad는 a-Shell만 켜 두고, 조작은 큰 화면에서 하는 식입니다.

```bash
python3 musictag_app.py --lan
# → http://192.168.0.17:8080/?k=Xk3nQ8vTb2wQ
```

- 주소 끝의 `?k=` 키를 아는 기기만 들어올 수 있습니다.
- **http라서 암호화되지 않습니다.** 집·회사 와이파이에서만 쓰고, 공용 와이파이에서는 쓰지 마세요.
- 옵션 없이 실행하면 `127.0.0.1`에만 묶여 다른 기기에서는 아예 접속되지 않습니다(기본값).

## 3. "인터넷 주소만 치면 되는 웹사이트"로는 왜 안 되나

가장 많이 나오는 질문입니다. 결론부터: **다운로드 부분은 브라우저만으로 절대 안 됩니다.**

| 원하는 것 | 브라우저만으로 | 이유 |
| --- | --- | --- |
| 유튜브 링크 → 음원 다운로드 | **불가능** | 브라우저의 동일 출처 정책상 `googlevideo.com`의 스트림을 스크립트로 읽을 수 없습니다. 또 재생 URL은 유튜브 플레이어 JS를 실행해 서명을 풀어야 나옵니다. |
| 태그·커버 수정 | 가능 | 파일을 사용자가 직접 올리면 브라우저 안에서 처리할 수 있습니다. |

그래서 **다운로드에는 반드시 서버가 필요합니다.** 서버를 어디에 두느냐가 선택지입니다.

| 방식 | 비용 | 현실성 |
| --- | --- | --- |
| **A. 내 iPad에서 실행** (이 앱) | 0원 | 권장. a-Shell을 켜 둬야 하는 것이 유일한 제약 |
| **B. 임대 서버(VPS)에 올리기** | 월 5~10달러 | 데이터센터 IP는 유튜브가 자주 차단합니다. 봇 확인 요구가 뜨고, yt-dlp를 매주 갱신해 줘야 합니다 |
| **C. 공개된 온라인 변환 사이트** | 0원 | 권장하지 않음. 광고·악성 스크립트가 흔하고 음질·태그를 통제할 수 없습니다 |

B는 기술적으로 되긴 하지만, **공개 서비스로 열면 안 됩니다.** 유튜브 서비스 약관은 별도 허가 없이
콘텐츠를 내려받는 것을 금지하고, 대부분의 호스팅 업체 이용약관도 이런 서비스를 금지합니다.
본인 권리가 있는 음원에 한해 개인용으로만 쓰세요.


명령줄 방식(`python3 musictag.py`)도 그대로 씁니다. 둘은 같은 로직을 공유합니다.


## 4. 명령줄로 쓰기

### 다운로드 + 태깅 (기본)

```bash
cd ~/Documents
python3 musictag.py
```

1. `유튜브 링크를 붙여넣고 Enter` — 앞뒤 공백, 휘어진 따옴표(`“ ” ‘ ’`), `?si=` 같은 추적
   파라미터는 자동으로 제거됩니다. 그냥 붙여넣으면 됩니다.
2. iTunes에서 곡 후보 5개를 번호로 보여줍니다.
   - `1`~`5` — 해당 곡 선택
   - `0` — 직접 입력
   - `s` — 검색어를 다시 입력
3. 제목·아티스트·앨범·발매일·장르·트랙 번호를 항목마다 확인합니다.
   **`Enter`는 그대로 유지**, 값을 입력하면 수정됩니다. 작곡가·코멘트는 비워도 됩니다.
4. 커버와 가사가 자동으로 붙고, `~/Documents/music/아티스트_-_제목.m4a`로 저장됩니다.

### 기존 파일 수정 / 확인

```bash
python3 musictag.py edit "music/Artist_-_Song.m4a"   # 항목별 수정 (커버·가사 교체 포함)
python3 musictag.py show "music/Artist_-_Song.m4a"   # 태그 요약만 출력
```

### 옵션

| 옵션 | 설명 |
| --- | --- |
| `--country KR,JP,US` | iTunes 검색 국가 순서 변경 (기본 `JP,KR,US`) |
| `--debug` | 오류의 traceback까지 출력 |

```bash
python3 musictag.py --country KR,US
```

## 5. 커버와 가사 넣는 법

### 커버 (우선순위 순)

1. `~/Documents/cover.jpg` 또는 `cover.png`가 있으면 그것을 사용
2. 없으면 iTunes 앨범 아트(600×600)
3. 그것도 실패하면 유튜브 썸네일(`maxresdefault` → `hqdefault`)

> webp는 지원하지 않습니다. `cover.webp`가 있으면 안내만 하고 다음 순서로 넘어갑니다.
> 사진 앱에서 "JPEG로 복사"해 저장하세요.

### 가사

`~/Documents/lyrics.txt`에 **UTF-8**로 저장해 두면 자동으로 삽입됩니다.
삽입할 때 제로폭 공백(U+200B 등)과 줄 끝 공백을 정리합니다.

사용한 뒤 파일은 `lyrics_used.txt`로 이름이 바뀝니다. 다음 곡에 엉뚱한 가사가
들어가는 사고를 막기 위한 장치입니다. 가사를 인터넷에서 검색해 오는 기능은 **없습니다.**
직접 준비한 파일만 사용합니다.

## 6. 저장되는 파일 이름

`아티스트 - 제목.m4a` 형태를 iPad 파일 앱에 맞게 정리합니다.

- `/ \ : * ? " < > |` 제거
- 공백은 `_`로
- 80자 제한
- 같은 이름이 있으면 `_2`, `_3`

예: `Artist / Name` + `Song: Part 1` → `Artist_Name_-_Song_Part_1.m4a`

## 7. 자주 나는 오류 3가지

### ① `오류: yt-dlp를 불러오지 못했습니다.`

라이브러리가 없거나 a-Shell 업데이트로 초기화된 경우입니다.

```bash
pip install -U yt-dlp mutagen
```

a-Shell은 앱을 업데이트하면 `pip` 패키지가 사라질 수 있습니다. 그때마다 다시 설치하면 됩니다.

### ② `오류: 다운로드에 실패했습니다.`

가장 흔한 원인은 **yt-dlp 버전이 낡은 것**입니다. 유튜브가 자주 바뀌기 때문에
yt-dlp도 자주 갱신됩니다.

```bash
pip install -U yt-dlp
```

그래도 안 되면:

- 링크가 **비공개·연령 제한·지역 제한** 영상인지 확인 (이 경우 받을 수 없습니다)
- 재생목록 링크(`&list=...`)라면 영상 하나짜리 링크로 바꾸기
- `python3 musictag.py --debug`로 실제 원인 메시지 확인

### ③ `오류: 태그를 쓰지 못했습니다.`

`bestaudio[ext=m4a]`가 없어 webm/opus로 받힌 경우입니다. mutagen의 MP4 태그는
m4a에만 쓸 수 있습니다. 대부분 yt-dlp 업데이트로 해결됩니다.

```bash
pip install -U yt-dlp
```

`~/Documents/musictagtmp/`에 `tmpaudio.webm` 같은 파일이 남아 있으면 m4a를 못 받은 것이
맞습니다. 그 파일은 지워도 됩니다.

## 8. 폴더 구조

```text
~/Documents/
├── musictag.py
├── musictag_app.py    (앱 모드)
├── .musictag_key      앱 접속 키 (자동 생성)
├── cover.jpg          (선택) 직접 넣을 커버
├── lyrics.txt         (선택) 직접 넣을 가사 → 사용 후 lyrics_used.txt
├── musictagtmp/       임시 폴더 (자동 정리)
└── music/             결과물
    └── Artist_-_Song.m4a
```

## 9. 개발자용: 테스트

실제 다운로드와 iTunes 호출은 전부 mock 처리되어 있습니다. 네트워크 없이 돌아갑니다.

```bash
pip install pytest mutagen
python3 -m pytest tests/ -q
```

테스트는 ffmpeg 없이 만든 짧은 무음 m4a 픽스처로 태그 읽기/쓰기를 검증하고,
`subprocess` 계열 호출이 코드에 들어오지 않았는지도 검사합니다.
