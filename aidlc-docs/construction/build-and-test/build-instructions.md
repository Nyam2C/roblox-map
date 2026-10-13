# Build Instructions

이 프로젝트는 컴파일하는 빌드가 없다. 빌드는 "스크립트가 실행 가능한 환경을 만드는 것"이다. (U1 기준, 이후 유닛이 이 문서에 추가한다.)

## Prerequisites
- **도구**: `uv` 0.11.28 (CI와 같은 버전). Python은 `uv`가 관리한다(개발 환경은 3.14.6, `tomllib` 때문에 3.11 이상 필요).
- **의존성**: 스크립트마다 인라인(PEP 723)에 고정. `h3==4.5.0`, `shapely==2.2.0`. 테스트는 `tests/requirements.txt`(`pytest==9.1.1`, `hypothesis==6.169.0` 추가). 전이 의존성(`numpy` 등)은 고정하지 않는다.
- **환경변수** (`.env`, git 제외): `VWORLD_KEY`(필수, `register.py`), `DATA_GO_KR_KEY`(U1에서는 쓰지 않음). 예시는 `.env.example`.
- **시스템**: macOS 또는 Linux, 디스크 수 MB(DB 약 0.4 MB/칸 수준), 외부 HTTPS 접속(Overpass, V-World).

## Build Steps

### 1. 의존성 설치
`uv run`이 처음 실행할 때 자동으로 설치한다. 별도 설치 명령이 없다.

### 2. 환경 설정
```bash
cp .env.example .env     # 그리고 VWORLD_KEY= 뒤에 키를 넣는다 (앞뒤 공백은 코드가 지우지만 붙여넣을 때 조심)
```
`config.toml`의 조정값은 기본값으로 충분하다.

### 3. 검증 (빌드 대신)
```bash
python3 -m py_compile src/*.py tests/*.py
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/ --collect-only -q
```

### 4. 성공 확인
- **기대 출력**: 컴파일 오류 없음, `93 tests collected`.
- **산출물**: 없음. 실행하면 `data/map.db`, `data/logs/*.jsonl`, `data/backups/`가 생긴다(모두 git 제외).
- **허용되는 경고**: 없음.

## Troubleshooting

### `INVALID_KEY` (등록되지 않은 인증키)
- **원인**: 키가 틀렸거나 앞뒤에 공백이 있었다(실제로 클립보드 붙여넣기에서 앞 공백이 들어간 적이 있다).
- **해결**: `.env`의 `VWORLD_KEY=` 뒤 값을 확인한다. 코드는 읽을 때 공백을 지운다. 그래도 안 되면 V-World 인증키 관리 화면에서 만료일(개발키 6개월)을 확인한다.

### Overpass가 504를 계속 낸다
- **원인**: 공개 서버가 바쁘다.
- **해결**: 코드가 10초, 30초, 60초 간격으로 재시도한다. 그래도 실패하면 그 칸은 이전 상태로 남고 `collection_runs`에 실패 이유가 기록된다. 시간을 두고 다시 실행한다. 첫 칸 실제 실행에서는 504가 세 번 나고 네 번째에 성공했다.

## U3 거리뷰 캡처 (2026-10-13)

### Prerequisites
- **Python**: `capture.py`는 3.13 이상이다(`numpy` 2.5.4가 3.12 이상을 요구하고, 3.12는 고정 없는 `typing-extensions`를 끌어온다). `uv`가 알아서 받는다.
- **의존성**: `capture.py` 인라인에 22개 전부 정확한 버전으로 고정(`streetlevel` 0.12.12 + 전이 의존성 20개 + `h3`). `[tool.uv] exclude-dependencies`로 `torch` 등 8개를 뺀다. 설치는 `uv run`이 처음 실행할 때 자동으로 한다(시스템 패키지 설치 불필요).
- **환경변수**: 없다(비밀값을 쓰지 않는다).
- **시스템**: 디스크는 칸당 약 400 MB(파노라마 약 320 MB, 크롭 약 65 MB), 네이버(`map.naver.com`, `panorama.map.naver.com`, `panorama.pstatic.net`)로 HTTPS 접속.

### 검증
```bash
python3 -m py_compile src/*.py tests/*.py
uv run src/capture.py --selftest        # 라이브러리 import만 확인, 네트워크 없음
uv export --script src/capture.py --no-hashes --no-annotate --no-header   # 22개가 인라인 고정과 같은지
```
- **기대 출력**: 컴파일 오류 없음, `selftest ok: streetlevel, numpy, pillow and h3 import`, `Resolved 22 packages`, `152 tests collected`.

### Troubleshooting
- **`streetlevel is not installed`**: `python src/capture.py`로 직접 돌렸을 때 나온다. `uv run src/capture.py ...`로 돌린다.
- **`uv export`가 `numpy`를 풀지 못한다**: `requires-python`이 3.13 미만이 됐을 때 나온다. 인라인 헤더의 `requires-python = ">=3.13"`을 되돌리지 않는다.
- **`stopped (cap)`**: 실행당 새 파노라마 100장 상한에 닿은 것이고 오류가 아니다. 같은 명령을 다시 돌리면 이어간다.
- **`stopped (blocked)` 또는 `(failures)`**: 네이버가 막았거나 같은 실패가 연속 3번 났다. 우회하지 않는다. 시간을 두고 다시 돌리고, 계속되면 사용자와 방법을 다시 정한다(런북 R-8).

## U2 Studio 생성기 (2026-10-13)

### Prerequisites
- **도구**: `uv`(Python 3.11 이상, `build_luau.py`). Roblox Studio와 내장 MCP 서버(시험은 Studio 0.742). 비밀값과 환경변수는 없다.
- **의존성**: `build_luau.py` 인라인에 `h3==4.5.0`, `shapely==2.2.0`(`register.py`와 같음). 새 의존성 없음.
- **먼저 할 일(처음 한 번, 되돌릴 수 있음)**: ① 사용자가 장소의 `.rbxl` 복사본을 만든다(Studio 파일 메뉴의 "Download a Copy"). ② Claude가 장소 설정을 바꾼다: `StreamingEnabled = false`, `Baseplate`는 `Transparency = 1`과 `CanCollide = false`, 기본 `SpawnLocation`은 `Enabled = false`. ③ `ServerStorage/MapBuilder`(ModuleScript)에 `studio/Builder.luau`를 넣는다.

### 빌드
```bash
uv run src/build_luau.py --selftest
uv run src/build_luau.py --cells 8930e0af13bffff        # data/build/<칸ID>/chunk-NNN.luau 와 manifest.json
```
- **기대 출력**: `selftest ok: h3 and shapely import`, 첫 칸은 `items=163 chunks=4 ... warnings=0`(스폰 설정 뒤).
- **Studio에서**: 덩어리 파일을 순서대로 `execute_luau`(편집 모드)로 실행하고 `Builder.verify`로 manifest와 비교한다(`code-summary.md`의 순서).

### Troubleshooting
- **`no spawn point configured`**: `config.toml`의 `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`가 없다는 경고다. 스폰 없이도 만들어진다.
- **`spawn point is not on a road or path`**: 스폰 점이 도로·보행로 중심선에서 폭의 절반 + 1 m보다 멀다. 점을 도로 위로 옮긴다.
- **`not a valid ... H3 cell`**: 칸 ID가 해상도 9 형식이 아니다.
- **Studio 연결 ID가 바뀌었다(`studio_id ... is not connected`)**: `list_roblox_studios`로 같은 장소(`placeId`)의 새 ID를 찾아 이어서 한다. 이번에 한 번 있었고 장소 안의 변경은 그대로 남아 있었다.
- **`MapBuilder` 소스를 바꿨다**: 같은 방법으로 `Source`를 다시 쓴다. 한 칸의 재생성은 약 5 ms다.
