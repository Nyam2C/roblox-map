# Security Test Instructions

## 의존성 취약점
```bash
uv run --python 3.14 --with pip-audit==2.10.1 pip-audit -r tests/requirements.txt
```
CI가 푸시마다 같은 명령을 돌린다. 결과 (2026-10-13): **No known vulnerabilities found.**

## 비밀값
- 키가 코드나 문서에 없는지: `.env`의 값을 `git ls-files -co --exclude-standard`로 나온 모든 파일에서 검색하고 `git log -p`에서도 검색한다. 결과: 없음. (생성 중 `tests/test_common.py`에 실제 키가 들어간 것을 이 검색으로 찾아 커밋 전에 고쳤다.)
- 로그에 키가 새지 않는지: 실제 실행 로그(`data/logs/*.jsonl`)에서 검색. 결과: 없음. 단위 테스트(`test_common.py`)가 마스킹을 직접 검증한다.

## 입력 검증과 안전
- 명령줄 인자(칸 ID, 해상도, 좌표)와 외부 응답 검증은 `test_parse.py`가 확인한다(잘못된 요소는 버리고 건수를 센다, Overpass가 아닌 응답은 오류).
- SQL은 매개변수 바인딩만 쓴다. 테이블과 열 이름은 코드 안의 상수만 쓰고, 실패하면 롤백되는 것을 `test_db.py`가 확인한다.
- HTTPS만 허용하고(`http://`는 오류), JSON만 읽는다(`test_common.py`).
- CI 설정: 액션은 커밋 SHA로, `uv`와 `pip-audit`는 버전으로 고정됐는지 `test_versions.py`가 확인한다.

## 해당 없음
인증·인가, 웹 보안 헤더, 침투 시험은 해당 없다(로컬 단일 사용자 도구).

## U3 거리뷰 캡처 (2026-10-13)

### 의존성 취약점
```bash
uv export --script src/capture.py --no-hashes --no-annotate --no-header > /tmp/capture-resolved.txt
uv run --python 3.14 --with pip-audit==2.10.1 pip-audit -r /tmp/capture-resolved.txt --no-deps --disable-pip
```
CI가 푸시마다 같은 명령을 돌린다. 결과: **No known vulnerabilities found**(22개). GitHub Actions도 통과했다(`e752591`).

### 비밀값과 사진
- 이 유닛은 키나 로그인 정보를 쓰지 않는다. `.env` 값을 `git ls-files -co --exclude-standard`의 모든 파일과 커밋 이력에서 검색했다: 없음.
- 캡처 로그 `data/logs/capture-*.jsonl`과 `captures/*/*/meta.json` 227개: 비밀값 없음.
- 사진(`captures/`)은 `.gitignore`에 있고(`git check-ignore`로 확인) 이 Mac 밖으로 나가지 않는다. 네이버가 얼굴을 흐리게 처리한 것을 확인했다.

### 입력 검증과 안전
- 네이버 응답: 위치 범위와 거리(1 km), ID 형식, 이미지 크기와 형식을 확인하고 어긋나면 버린다(`test_capture.py`). 응답 형식 이상과 403/429는 우회하지 않고 멈춘다(P3-7).
- Pillow의 큰 이미지 방지 한도를 명시했다(8 MP). 파일 이름은 안전한 문자만 쓰고 저장 경로가 `captures/` 밖으로 나가지 못한다(P3-8, `../` 시험 포함).
- 한계: `streetlevel`이 해석하는 내부 통신 응답은 라이브러리에 의존한다(위험으로 기록, 버전 고정).

## U2 Studio 생성기 (2026-10-13)

### 의존성 취약점
`build_luau.py`는 `h3`, `shapely`만 쓰고 둘 다 `tests/requirements.txt`에 있어서 기존 `pip-audit -r tests/requirements.txt`가 점검한다. CI 통과(`48cdd2d`).

### 코드 주입 방지 (SECURITY-05)
- V-World와 OSM에서 온 건물 ID, 도로 ID가 Studio에서 실행되는 코드에 들어간다. `tests/test_build_luau.py`가 확인한다: 허용 문자(영문자, 숫자, `: # _ - .`) 밖의 글자(따옴표, 줄바꿈, 역슬래시, `]]`, 공백, 한글 등)가 든 ID는 건너뛰고 경고하며, 어떤 입력에서도 코드 파일의 모든 따옴표 글자가 허용 문자뿐이고 역슬래시가 없다. 숫자는 유한한 값만 쓴다.
- 칸 ID는 H3 형식인지 `build_luau.py`와 `Builder.luau`가 각각 확인한다(Studio 시험에서 `../Workspace`, 14자리 ID 거부).
- `Builder.luau`: `loadstring`, `HttpService` 등이 없고 `:Destroy()`는 `Auto/<칸ID>`를 지우는 한 곳뿐이다(`tests/test_versions.py`가 검사, 변이 시험으로 확인).

### Studio 변경 범위
- 이번 실행에서 장소에 바꾼 것: 장소 설정 3개(스트리밍 끄기, `Baseplate` 숨기기, 기본 `SpawnLocation` 끄기), `ServerStorage/MapBuilder`, `Workspace/Auto/<칸ID>`, 빈 `Workspace/Manual`. 시험용 부품은 모두 지웠다(`MCP_Test`는 처음 상태).
- 변경 전에 사용자의 `.rbxl` 복사본을 확인했다(Documents에 85 KB 파일).

### 비밀값
이 유닛은 키를 쓰지 않는다. `.env` 값을 모든 추적 파일에서 검색했다: 없음.
