# U1 데이터 기반 — Tech Stack Decisions

이 선택은 U3, U2, U4, U5도 이어서 쓴다. 정확한 버전은 코드 생성 때 설치되는 최신 안정 버전을 확인해서 `==`로 고정한다(여기서 숫자를 미리 정하지 않는다).

| 영역 | 선택 | 근거 | 결정 |
|---|---|---|---|
| 언어, 실행 | Python, `uv run` | 기존 `cells.py`와 같다 | 기존 |
| 의존성 관리 | 스크립트별 인라인 의존성(PEP 723)에 `==` 고정 | Q4=A. 스크립트가 단독 실행되는 설계와 맞다 | 사용자 |
| 취약점 점검 | `pip-audit` 수동 실행, 절차는 문서화 | Q4=A, SECURITY-10 | 사용자 |
| H3 칸 | `h3` | 기존 | 기존 |
| 기하 계산 | `shapely` | Q1=A. 교집합 면적, 무게중심, 자기 교차 판정. 작은 영역은 지역 평면 좌표로 변환해 계산한다 | 사용자 |
| HTTP | 표준 `urllib` | Q3=A. 호출 대상이 3곳뿐이고 의존성이 없다 | 사용자 |
| 데이터 저장 | 표준 `sqlite3`, 매개변수 바인딩, 외래 키 켬 | 설계 Q3=C, N-2 | 사용자 + 기본값 |
| 환경변수 | `uv run --env-file .env` | N-1. 별도 라이브러리 없음 | 기본값 |
| 로그 | 표준 `logging`, 콘솔 + `data/logs/` 파일 | Q5=A | 사용자 |
| 테스트 | `pytest` + `Hypothesis` | Q2=A, PBT-09 | 사용자 |
| 테스트 의존성 | `tests/requirements.txt`에 `==` 고정, 스크립트의 인라인 버전과 일치 검사 테스트 하나 | N-8 (Q2와 Q4 사이의 빈틈을 메움) | 기본값 |
| 공용 순수 함수 | `src/geo.py` (좌표·외곽선 계산, 칸 배정, 유효성, 겹침 비율), 건물 조립은 `register.py`에서 이 함수들을 사용 | N-9, 컴포넌트끼리 직접 호출하지 않는다는 설계와 맞춘다 | 기본값 |
| 파일 위치 | `src/` 아래 스크립트, `tests/`, `data/`(DB와 로그, git 제외) | 유닛 Q4=B | 사용자 |

## 새로 추가되는 의존성 (U1)
- `h3`(기존), `shapely`(신규). 테스트용으로 `pytest`, `hypothesis`.
- 표준 라이브러리: `sqlite3`, `urllib`, `logging`, `json`, `argparse`.

## 쓰지 않기로 한 것
- `httpx`, `requests`: 호출 대상이 적고 재시도가 이미 구현돼 있다(Q3=A).
- `python-dotenv`: `uv run --env-file`로 대체한다.
- ORM, 마이그레이션 도구: 테이블이 적어 SQL을 직접 쓴다.
- 공간 인덱스(R-tree 등): 칸당 건물이 수십~수백 개라 필요 없다. 규모가 커지면 도입한다.
- `pyproject.toml`, `uv.lock`: Q4=A를 따랐다. 의존성이 스크립트마다 흩어지는 비용은 `tests/requirements.txt` 일치 검사로 줄인다.

## 다음 유닛에 미치는 영향
- U3(거리뷰 캡처)는 `streetlevel` 라이브러리를 쓴다(U3 Functional Design Q1=C). 의존성이 무거워서(`torch` 포함 42개) 설치와 `pyexiv2` 문제는 U3 NFR Requirements에서 정한다.
- U2(Studio 생성기)는 `geo.py`의 좌표 변환 함수를 재사용할 수 있다.

## NFR Design에서 추가된 선택
| 영역 | 선택 | 근거 |
|---|---|---|
| 로그 형식 | 파일은 JSON 한 줄(`.jsonl`), 콘솔은 사람이 읽는 요약 | Q8=B, D-N5 |
| 설정 | `config.toml`을 표준 `tomllib`으로 읽음(Python 3.11 이상) | Q9=B, D-N8 |
| CI | GitHub Actions(`pytest` + `pip-audit`), 쓰는 액션과 `uv` 버전은 고정 | Q2=B, D-N7 |
| 백업 | `sqlite3` 백업 기능으로 칸 재수집 직전에 복사, 최근 5개 보관 | Q5=B, D-N6 |
| 공용 도우미 | `src/common.py`(로깅, 설정, 환경변수, HTTP 재시도, 최상위 실행기) | D-N2 |

## 확정한 정확한 버전 (2026-10-13, 코드 생성 단계 1)
PyPI의 최신 안정 버전이고 Python 3.14.6(`uv` 0.11.28)에서 설치와 `import`가 되는 것을 확인했다.

| 패키지 | 버전 | 용도 |
|---|---|---|
| `h3` | 4.5.0 | 칸 |
| `shapely` | 2.2.0 | 기하 계산 (전이 의존성으로 `numpy`가 따라온다) |
| `pytest` | 9.1.1 | 테스트 |
| `hypothesis` | 6.169.0 | 속성 기반 테스트 |
| `pip-audit` | 2.10.1 | 취약점 점검(CI) |

전이 의존성(`numpy` 등)은 이번에 고정하지 않는다. `pip-audit`가 설치된 전체 목록을 점검하고, 고정이 필요해지면 `uv.lock` 도입을 다시 검토한다(Q4=A의 한계).

