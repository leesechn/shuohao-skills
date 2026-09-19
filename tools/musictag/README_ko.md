# musictag.py — iPad a-Shell 음원 다운로드·태깅

유튜브 링크 하나로 **다운로드 → 곡 정보 검색 → 커버·태그·가사 삽입 → 정리된 파일명 저장**까지
한 번에 끝내는 단일 파일 스크립트입니다. PC 없이 iPad(a-Shell)만으로 동작합니다.

- `subprocess` / `os.system` / 셸 호출 없음 (a-Shell에서 불안정)
- ffmpeg 후처리 없음 — `bestaudio[ext=m4a]` 원본을 그대로 저장
- 컴파일이 필요한 패키지(Pillow 등) 사용 안 함

## 1. 설치

a-Shell을 열고 아래를 차례대로 입력합니다.

```bash
pip install -U yt-dlp mutagen
```

`musictag.py`를 `~/Documents`에 둡니다. 방법은 둘 중 하나입니다.

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

## 2. 사용법

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

## 3. 커버와 가사 넣는 법

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

## 4. 저장되는 파일 이름

`아티스트 - 제목.m4a` 형태를 iPad 파일 앱에 맞게 정리합니다.

- `/ \ : * ? " < > |` 제거
- 공백은 `_`로
- 80자 제한
- 같은 이름이 있으면 `_2`, `_3`

예: `Artist / Name` + `Song: Part 1` → `Artist_Name_-_Song_Part_1.m4a`

## 5. 자주 나는 오류 3가지

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

## 6. 폴더 구조

```text
~/Documents/
├── musictag.py
├── cover.jpg          (선택) 직접 넣을 커버
├── lyrics.txt         (선택) 직접 넣을 가사 → 사용 후 lyrics_used.txt
├── musictagtmp/       임시 폴더 (자동 정리)
└── music/             결과물
    └── Artist_-_Song.m4a
```

## 7. 개발자용: 테스트

실제 다운로드와 iTunes 호출은 전부 mock 처리되어 있습니다. 네트워크 없이 돌아갑니다.

```bash
pip install pytest mutagen
python3 -m pytest tests/ -q
```

테스트는 ffmpeg 없이 만든 짧은 무음 m4a 픽스처로 태그 읽기/쓰기를 검증하고,
`subprocess` 계열 호출이 코드에 들어오지 않았는지도 검사합니다.
