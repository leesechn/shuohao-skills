# musictag.py — iPad a-Shell 음원 다운로드·태깅

유튜브 링크 하나로 **다운로드 → 곡 정보 검색 → 커버·태그·가사 삽입 → 정리된 파일명 저장**까지
한 번에 끝내는 단일 파일 스크립트입니다. PC 없이 iPad(a-Shell)만으로 동작합니다.

- `subprocess` / `os.system` / 셸 호출 없음 (a-Shell에서 불안정)
- ffmpeg 후처리 없음 — `bestaudio[ext=m4a]` 원본을 그대로 저장
- 컴파일이 필요한 패키지(Pillow 등) 사용 안 함
- `python3 musictag.py <링크>` 한 줄이면 질문 없이 파일이 나옵니다

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

## 2. 가장 빠른 방법 — 링크 한 줄

```bash
cd ~/Documents
python3 musictag.py https://youtu.be/xxxxxxxx
```

**질문이 하나도 없습니다.** 받고, iTunes 첫 번째 결과로 태그하고, 커버 붙이고,
`~/Documents/music/아티스트_-_제목.m4a`로 저장한 뒤 끝납니다. 받는 동안 진행률이 보입니다.

```text
다운로드 중...
받는 중 82%
영상: [MV] YOASOBI - 夜に駆ける (Official) / Ayase
[JP] YOASOBI - 夜に駆ける (THE BOOK)
저장 완료: /private/var/.../Documents/music/YOASOBI_-_夜に駆ける.m4a
```

곡 정보를 직접 확인하고 싶으면 `--ask`를 붙이세요. 후보 5개를 보여주고 항목별로 물어봅니다.

```bash
python3 musictag.py https://youtu.be/xxxxxxxx --ask
```

> **a-Shell에서 링크 붙여넣기**: `python3 musictag.py ` 까지 치고 한 칸 띄운 뒤,
> 화면을 길게 눌러 **붙여넣기** → `Enter`. 따옴표는 붙여도 되고 안 붙여도 됩니다.

## 3. 앱으로 쓰기 (다른 기기에서 조작할 때만)

> ### 먼저 읽으세요 — iPad 한 대만 쓴다면 이 모드는 권장하지 않습니다
>
> iOS는 화면에 없는 앱의 **CPU를 정지시킵니다.** Safari로 넘어가는 순간 a-Shell이
> 멈춰서 서버가 응답하지 않고, 페이지가 몇 분~수십 분씩 로딩만 돕니다.
> Split View로 나란히 둬도 기기·상황에 따라 정지될 수 있습니다.
> **iPad 한 대로 쓸 거면 위의 `python3 musictag.py <링크>`가 훨씬 빠릅니다.**
>
> 이 모드가 제값을 하는 경우는 하나입니다: **`--lan`으로 띄워 놓고 노트북이나 폰에서
> 조작할 때.** 그때는 iPad에서 a-Shell이 계속 화면에 떠 있으니 정지되지 않습니다.

a-Shell이 iPad 안에서 로컬 서버를 띄우고 브라우저가 그 화면을 보여줍니다.

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

### 기다리지 않게 하는 구조

음원을 다 받을 때까지 기다리지 않습니다. 제목을 알게 되는 순간(다운로드 시작 직후)
곡 정보 검색이 바로 돌아가서, **후보를 고르고 태그를 손보는 동안 음원이 뒤에서 계속 내려옵니다.**
진행률은 막대로 보이고, 다 받기 전에는 저장 버튼이 `저장 (받는 중 62%)`로 잠깁니다.

iTunes 검색도 JP → KR → US를 하나씩 기다리지 않고 **셋을 동시에** 던진 뒤 우선순위대로
고릅니다. 앞 국가에서 결과가 없을 때 걸리던 추가 왕복이 사라집니다.

### 앱 모드에서 꼭 알아야 할 것

- **a-Shell이 화면에서 사라지면 서버가 멈춥니다.** 홈 화면 아이콘만 눌러 열면 a-Shell이
  뒤로 밀려 응답이 없습니다. a-Shell을 화면에 띄워 둔 채로만 동작합니다.
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

## 4. "인터넷 주소만 치면 되는 웹사이트"로는 왜 안 되나

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


## 5. 명령줄 전체 사용법

### 모드 정리

| 명령 | 질문 | 쓰는 때 |
| --- | --- | --- |
| `musictag.py <링크>` | 없음 | 평소. 가장 빠릅니다 |
| `musictag.py <링크> --ask` | 후보 선택 + 항목별 확인 | 검색이 엉뚱한 곡을 잡았을 때 |
| `musictag.py` | 링크부터 물어봄 | 링크를 나중에 붙여넣고 싶을 때 |
| `musictag.py edit 곡.m4a` | 항목별 확인 | 저장한 파일을 고칠 때 |
| `musictag.py show 곡.m4a` | 없음 | 태그만 확인할 때 |

### `--ask` 흐름

```bash
python3 musictag.py https://youtu.be/xxxxxxxx --ask
```

1. 앞뒤 공백, 휘어진 따옴표(`“ ” ‘ ’`), `?si=` 같은 추적 파라미터는 자동으로 제거됩니다.
   (링크를 생략하면 링크부터 물어봅니다.)
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

## 6. 커버와 가사 넣는 법

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

## 7. 저장되는 파일 이름

`아티스트 - 제목.m4a` 형태를 iPad 파일 앱에 맞게 정리합니다.

- `/ \ : * ? " < > |` 제거
- 공백은 `_`로
- 80자 제한
- 같은 이름이 있으면 `_2`, `_3`

예: `Artist / Name` + `Song: Part 1` → `Artist_Name_-_Song_Part_1.m4a`

## 8. 자주 나는 오류 3가지

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

## 9. 폴더 구조

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

## 10. 개발자용: 테스트

실제 다운로드와 iTunes 호출은 전부 mock 처리되어 있습니다. 네트워크 없이 돌아갑니다.

```bash
pip install pytest mutagen
python3 -m pytest tests/ -q
```

테스트는 ffmpeg 없이 만든 짧은 무음 m4a 픽스처로 태그 읽기/쓰기를 검증하고,
`subprocess` 계열 호출이 코드에 들어오지 않았는지도 검사합니다.
