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
