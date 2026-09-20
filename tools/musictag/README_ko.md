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
python3 musictag.py https://youtu.be/dQw4w9WgXcQ
```

(뒤의 `dQw4w9WgXcQ` 자리에 **본인이 복사한 진짜 링크**를 넣으세요.)

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
python3 musictag.py https://youtu.be/dQw4w9WgXcQ --ask
```

### 링크 넣는 3가지 방법

`xxxxxxxx`는 **예시입니다. 그대로 치면 안 됩니다.** 유튜브 영상 ID는 11글자입니다.
(예시를 그대로 넣으면 `'xxxxxxxx'는 실제 영상 주소가 아닙니다`라고 막아 줍니다.)

**① 붙여넣기** — 유튜브 앱에서 `공유 → 복사` 후, a-Shell에서
`python3 musictag.py ` 까지 치고 한 칸 띄운 뒤 화면을 길게 눌러 **붙여넣기** → `Enter`.

**② 클립보드를 파일로** — 터미널에 긴 주소를 붙이기 싫을 때. a-Shell에는 `pbpaste`가 있습니다.

```bash
pbpaste > link.txt
python3 musictag.py link.txt
```

**③ 바로 넘기기** — a-Shell이 `$(...)`를 지원하면 한 줄로 끝납니다. (기기에 따라 안 될 수 있습니다)

```bash
python3 musictag.py "$(pbpaste)"
```

진짜 링크는 이런 모양입니다.

```text
https://youtu.be/dQw4w9WgXcQ
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```


## 3. 웹앱으로 쓰기 — 복붙 없이

터미널을 매번 만지기 싫을 때 쓰는 방식입니다. **a-Shell에서 서버를 한 번 켜 두면,
그 뒤로는 브라우저에서 버튼만 누릅니다.**

### 꼭 지켜야 하는 것 하나 — Split View

iOS는 **화면에 없는 앱의 CPU를 정지시킵니다.** a-Shell이 화면에서 사라지면 서버가 멈춰
페이지가 무한히 로딩만 돕니다. 그래서 **a-Shell과 브라우저를 한 화면에 나란히** 둬야 합니다.

1. a-Shell을 엽니다.
2. 화면 맨 아래에서 위로 살짝 쓸어 **Dock**을 띄웁니다.
3. Dock에서 **Safari 아이콘을 길게 눌러 화면 오른쪽 끝까지 끌어다 놓습니다.**
   두 앱이 **반반으로 나뉘면** 성공입니다. (오른쪽에 떠 있기만 한 Slide Over는 안 됩니다.
   가운데 경계선을 끌어 반반으로 만드세요.)

> **홈 화면 아이콘으로 여는 방식은 동작하지 않습니다.** 그러면 a-Shell이 뒤로 밀립니다.
> 이전에 겪으신 "30분 로딩"이 바로 이 상황입니다.
> 이제는 무한정 기다리지 않고 15초 안에 원인을 알려 줍니다.

### 쓰는 순서

**① a-Shell 쪽 (세션당 한 번)**

```bash
cd ~/Documents
python3 musictag_app.py
```

화면에 나오는 주소를 **`?k=...`까지 통째로** 복사합니다.

**② Safari 쪽 (한 번)**

주소를 붙여넣고 이동합니다. 이 탭을 그대로 열어 두세요.

**③ 곡을 받을 때마다 (여기부터는 복붙 없음)**

1. 유튜브 앱이나 Safari에서 영상 → **공유 → 링크 복사**
2. musictag 화면에서 **`클립보드에서 붙여넣고 시작`** 한 번 누르기
3. 곡 후보 고르고 → **저장**

터미널을 다시 만질 일이 없습니다. a-Shell은 옆에서 돌기만 하면 됩니다.

### 단축어(Shortcuts)로 더 줄이기 — 선택

주소에 `&url=`을 붙이면 링크를 미리 채우고 **자동으로 시작**합니다.

```text
http://127.0.0.1:8080/?k=내키&url=https%3A%2F%2Fyoutu.be%2FdQw4w9WgXcQ
```

단축어 앱에서 이렇게 만들면 공유 시트에서 바로 넘길 수 있습니다.

1. 단축어 → 새 단축어 → **공유 시트에 표시** 켜기 (입력 형식: URL)
2. 동작 **텍스트**: `http://127.0.0.1:8080/?k=내키&url=`
3. 동작 **URL 인코딩** (입력: 단축어 입력) → **텍스트 결합**
4. 동작 **URL 열기**

Split View가 켜져 있어야 동작하는 것은 똑같습니다.

### 다른 기기에서 조작하기 — `--lan`

노트북이나 폰의 큰 화면에서 조작하고 싶으면 이쪽이 더 편합니다.
iPad는 a-Shell만 띄워 두면 되니 Split View도 필요 없습니다.

```bash
python3 musictag_app.py --lan
# → http://192.168.0.17:8080/?k=Xk3nQ8vTb2wQ
```

- `?k=` 키를 아는 기기만 들어올 수 있습니다.
- **http라 암호화되지 않습니다.** 집·회사 와이파이에서만 쓰세요.
- 옵션 없이 실행하면 `127.0.0.1`에만 묶입니다(기본값).
- 포트가 겹치면 `--port 8081`.

### 화면에서 할 수 있는 것

| 탭 | 하는 일 |
| --- | --- |
| **추가** | 링크 붙여넣기 → 곡 후보 선택 → 정보·가사·커버 확인 → 저장 |
| **보관함** | 저장한 곡 목록, 태그 수정, 커버 교체, 삭제 |

커버는 **앨범 아트 / 유튜브 썸네일 / 사진 앱에서 고르기 / 없음** 중에서 고릅니다.
가사는 직접 준비한 텍스트를 붙여넣는 칸이 있습니다(자동 검색 기능은 없습니다).

음원을 다 받을 때까지 기다리지 않습니다. 제목을 알게 되는 순간 곡 정보 검색이 돌아가서,
**후보를 고르고 태그를 손보는 동안 음원이 뒤에서 계속 내려옵니다.** 진행률은 막대로 보이고,
다 받기 전에는 저장 버튼이 `저장 (받는 중 62%)`로 잠깁니다.

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
| `musictag.py link.txt` | 없음 | `pbpaste > link.txt` 로 넣었을 때 |
| `musictag.py <링크> --ask` | 후보 선택 + 항목별 확인 | 검색이 엉뚱한 곡을 잡았을 때 |
| `musictag.py` | 링크부터 물어봄 | 링크를 나중에 붙여넣고 싶을 때 |
| `musictag.py edit 곡.m4a` | 항목별 확인 | 저장한 파일을 고칠 때 |
| `musictag.py show 곡.m4a` | 없음 | 태그만 확인할 때 |

### `--ask` 흐름

```bash
python3 musictag.py https://youtu.be/dQw4w9WgXcQ --ask
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
