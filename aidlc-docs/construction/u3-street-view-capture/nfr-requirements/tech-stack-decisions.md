# U3 거리뷰 캡처 — Tech Stack Decisions

U1의 선택(Python, `uv run`, `h3`, `shapely`, `sqlite3`, 표준 `logging`, `config.toml`, `pytest` + `Hypothesis`, GitHub Actions)은 그대로 쓴다. 아래는 U3에서 추가하거나 정한 것이다.

| 영역 | 선택 | 근거 |
|---|---|---|
| 파노라마 접근 | `streetlevel` 0.12.12 (MIT). 네이버 모듈만 쓴다 | 기능 설계 Q1=C. 브라우저 없이 좌표 → 파노라마 → 이미지가 된다(시험 확인) |
| 설치 방식 | 줄인 방식: 스크립트 안 `[tool.uv] exclude-dependencies`로 무거운 패키지를 뺀다 | Q1=A. 패키지 42개 → 21개, `torch` 없음, 시스템 설치 불필요 |
| 뺄 패키지 | `torch`, `pyequilib`, `pyexiv2`, `pytest`, `pytest-asyncio`, `cython`, `pycryptodome`, `pyfrpc` | 시험에서 조회와 내려받기에 필요 없었다 |
| `pyexiv2` | 어댑터가 불러오기 전에 빈 모듈을 끼워 넣는다 | EXIF를 쓰지 않는다(D-U3-6) |
| 고정 범위 | 21개 전부 정확한 버전(아래 표) | Q2=A |
| 이미지와 투영 | `pillow`(이미지 읽기·저장), `numpy`(큐브 맵 투영) | 둘 다 줄인 묶음에 이미 들어 있고 테스트에서도 쓴다 |
| 어댑터 | `src/panorama_source.py`: `streetlevel` 늦게 불러오기, 오류를 차단과 일시 오류로 분류 | N-U3-1 |
| 순수 모듈 | `src/projection.py`: 방위각, 상대 방향, 크롭 값, 큐브 맵 투영 | N-U3-2 |
| 테스트 | 기존 `pytest` + `Hypothesis`. 어댑터는 가짜로 대체, 합성 큐브 맵 이미지 | Q3=B, M2 |
| CI | 기존에 더해 `capture.py --selftest`(줄인 묶음 설치와 `import` 확인, 네트워크 호출 없음)와 그 묶음의 `pip-audit` | Q3=B |
| 설정 | `config.toml`에 U3 항목 추가(거리 제한 120, 방위각 간격 60, 장수 3, 호출 간격 1, 새 파노라마 상한 100, 크롭 크기와 품질, `captures_dir`) | N-U3-3, N-U3-7 |
| 저장 공간 | 한도 없음, 실제 크기를 재서 보고 | Q4=A |

## 고정할 21개 (`capture.py`의 인라인 의존성, 시험한 환경의 버전)

| 패키지 | 버전 | 패키지 | 버전 |
|---|---|---|---|
| `streetlevel` | 0.12.12 | `multidict` | 7.1.0 |
| `aiohappyeyeballs` | 2.7.1 | `numpy` | 2.5.4 |
| `aiohttp` | 3.14.5 | `pillow` | 12.3.0 |
| `aiosignal` | 1.4.0 | `propcache` | 0.5.4 |
| `attrs` | 26.1.0 | `protobuf` | 7.36.2 |
| `bd09convertor` | 0.0.3 | `pyproj` | 3.8.0 |
| `certifi` | 2026.7.22 | `requests` | 2.34.2 |
| `charset-normalizer` | 3.5.2 | `scipy` | 1.18.1 |
| `coordinatesconverter` | 0.1.5 | `urllib3` | 2.8.0 |
| `frozenlist` | 1.8.0 | `yarl` | 1.25.1 |
| `idna` | 3.20 | | |

`tests/requirements.txt`에는 `numpy==2.5.4`, `pillow==12.3.0`을 추가한다(투영 테스트용, `capture.py`의 고정과 같은 버전). 코드 생성에서 이 버전들이 `shapely` 2.2.0과 함께 설치되고 기존 93개 테스트가 통과하는지 확인한다.

## 쓰지 않기로 한 것
- `torch`, `pyequilib`, `pyexiv2`: 큐브 맵 투영은 `numpy`로 직접 하고 EXIF는 쓰지 않는다.
- Playwright와 브라우저 다운로드: 기능 설계 Q6=A. `streetlevel`이 기술적으로 고장 날 때 새 작업으로 시작한다.
- `brew install inih` 같은 시스템 설치: 줄인 방식이 필요 없게 한다(Q1=A).
- 용량 한도 코드: Q4=A.

## 알려진 위험
- `streetlevel`은 네이버의 내부 통신에 기대고 있어서 네이버가 바꾸면 깨질 수 있다. 영향은 어댑터 한 곳에 모인다.
- `pyexiv2` 빈 모듈 우회는 이 라이브러리 버전에서만 안전하다고 확인했다(0.12.12). 버전을 올리면 다시 확인한다.
- 줄인 묶음의 버전은 시험한 환경의 값이다. 의존성 해석이 이 목록과 다르게 되는 경우를 `capture.py --selftest`가 CI에서 잡는다.
