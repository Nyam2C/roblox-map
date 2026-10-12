# U3 거리뷰 캡처 — NFR Requirements Plan

대상: C3 `capture.py`와 이 유닛이 새로 만드는 모듈. 실행 환경은 U1과 같다(사용자 Mac, `uv run`, SQLite).
U1에서 정한 도구와 규칙(`pytest` + `Hypothesis`, `urllib` 대신 라이브러리 사용 여부는 이번에, JSON 로그, `config.toml`, GitHub Actions, 백업, 복구 런북)은 이어서 쓴다. 여기서는 U3에만 해당하는 것을 정한다.

각 질문의 `[Answer]:` 뒤에 알파벳을 적어 줘. 맞는 보기가 없으면 X를 고르고 설명을 적는다.

## 계획 (체크리스트)

- [x] U3 Functional Design 읽기, 확장 규칙 이 단계 항목 확인
- [x] `streetlevel` 의존성 시험(아래 "시험 결과")
- [x] 아래 질문 4개에 답 받기 (사용자가 채팅으로 답했고 이 파일에 그대로 옮겨 적음)
- [x] 답변 분석: 모든 답이 알파벳 하나로 명확하고 서로 모순이 없다. Q3=B의 세부(자체 점검 진입점, 감사 입력)는 질문 대신 기본값 N-U3-9, N-U3-10으로 메웠다
- [x] `construction/u3-street-view-capture/nfr-requirements/nfr-requirements.md` 생성
- [x] `construction/u3-street-view-capture/nfr-requirements/tech-stack-decisions.md` 생성
- [x] 확장 규칙 준수 요약 작성 (Security, Resiliency, PBT)

## 시험 결과 (2026-10-13)

앞서 `streetlevel`을 그대로 설치하면 패키지가 42개이고 `torch`가 들어오며, 이 Mac에서는 `pyexiv2`가 시스템 라이브러리(`inih`)가 없어 `import`에 실패한다고 했다. 이걸 줄일 수 있는지 시험했다.

| 방법 | 결과 |
|---|---|
| 스크립트 안에 `[tool.uv] exclude-dependencies`로 `torch`, `pyequilib`, `pyexiv2`, `pytest`, `pytest-asyncio`, `cython`, `pycryptodome`, `pyfrpc`를 뺀다 | **패키지 21개**로 줄었고 `torch`가 없다. 파노라마 조회와 zoom 1 이미지 내려받기(6144×1024)가 모두 된다. Python 3.14에서 확인했다 |
| `pyexiv2` 문제 | `streetlevel`은 `import`할 때 `pyexiv2`가 있어야 한다. 이미지에 EXIF를 쓸 때만 실제로 쓰므로(D-U3-6에서 안 쓰기로 했다), 불러오기 전에 빈 모듈을 끼워 넣으면 해결된다 |
| 줄인 21개 묶음의 취약점 점검(`pip-audit`) | 알려진 취약점 없음 |
| 라이선스 | `streetlevel`은 MIT |

필요한 21개: `streetlevel` 0.12.12와 `aiohttp`, `aiohappyeyeballs`, `aiosignal`, `attrs`, `bd09convertor`, `certifi`, `charset-normalizer`, `coordinatesconverter`, `frozenlist`, `idna`, `multidict`, `numpy`, `pillow`, `propcache`, `protobuf`, `pyproj`, `requests`, `scipy`, `urllib3`, `yarl`. 버전은 시험한 환경의 값이다.

## 이미 정해진 것 (질문 안 함)

| 항목 | 내용 | 근거 |
|---|---|---|
| 복구 목표 | RTO/RPO 수 시간. 사진은 다시 받을 수 있다(단, 네이버가 그 사이 새로 촬영하면 같은 사진이 아닐 수 있다. 촬영일을 기록한다) | NFR-6, 기능 설계 |
| 비밀값 | 이 유닛은 키나 로그인 정보를 쓰지 않는다 | 기능 설계 BR-3.6 |
| 사진 | 로컬에만 둔다. 사람 얼굴과 번호판이 찍힐 수 있고 저장소가 public이다. 이 Mac의 데스크톱은 iCloud 동기화가 꺼져 있는 것으로 보인다(Finder 설정값 0, 확신은 못 한다) | NFR-4 |
| 디스크 여유 | 지금 약 608 GB | 확인함 |

## 설계 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| N-U3-1 | 네이버와 통신하는 부분은 얇은 어댑터 모듈 하나(`src/panorama_source.py`)에 모은다. `streetlevel`은 이 모듈 안에서 늦게 불러오고(`pyexiv2` 빈 모듈 처리 포함), 오류를 "차단"(403, 429)과 "일시 오류"(시간 초과)로 나눠 `capture.py`에 알린다. 나머지 코드와 테스트는 어댑터를 가짜로 바꿔 쓴다 | `streetlevel`이 네이버 내부 통신에 기대고 있어서 바뀌면 이 한 곳만 고치면 된다. 테스트가 무거운 의존성 없이 돈다 |
| N-U3-2 | 크롭 투영과 방향 계산은 입출력 없는 순수 모듈(`src/projection.py`)로 만든다(`numpy`와 `pillow` 사용). 속성 P3-1~P3-5가 여기에 대응한다 | 속성 기반 테스트 대상 |
| N-U3-3 | 호출 간격 1초, 실행당 새 파노라마 100장, 재시도 10초·30초·60초는 `config.toml`에 둔다. 이 값들과 거리 제한(120 m), 방위각 간격(60°), 장수(3), 크롭 크기(1024×768, 품질 85)도 `config.toml`에 추가한다 | U1의 설정 방식 |
| N-U3-4 | 로그는 U1과 같은 방식(JSON 파일 + 콘솔 요약)이다. 차단과 중단 이유는 실행 기록(`collection_runs`)에 남긴다 | U1 NFR Design |
| N-U3-5 | 성능 목표: 파노라마 100장을 내려받는 데 10분 이내(장당 내려받기 약 1초와 간격 1초 포함, 크롭 생성 포함). 메모리: 파노라마 한 장이 압축을 풀면 약 19 MB다. 한 번에 한 장씩 처리한다 | 시험에서 장당 0.8초가 걸렸다 |
| N-U3-6 | 이 유닛의 Python 버전 요구는 U1과 같다(3.11 이상, 3.14에서 확인) | `tomllib` |
| N-U3-7 | `captures/` 폴더 위치는 설정값(`captures_dir`)으로 바꿀 수 있게 한다. 기본값은 저장소 안 `captures/`(git 제외) | 나중에 다른 디스크로 옮기고 싶을 때를 위해 |
| N-U3-8 | `captures/`는 백업하지 않는다. 다시 받을 수 있고 용량이 크다. `captures`와 `building_views` 테이블은 DB 백업(U1)에 포함된다 | RESILIENCY-12를 이 데이터에서는 "재생성 가능"으로 처리 |

## Question 1 — `streetlevel` 의존성 처리
`streetlevel`을 어떻게 설치할까?

A) 줄인 방식: 스크립트의 `[tool.uv] exclude-dependencies`로 무거운 패키지를 빼고(21개) `pyexiv2`는 빈 모듈로 처리한다. 시험으로 확인했다

B) 전체 설치: 42개(`torch` 포함)를 설치하고 `brew install inih`로 시스템 라이브러리를 추가한다. 시스템에 패키지를 새로 설치하는 일이다

X) Other (please describe after [Answer]: tag below)

참고: A는 가볍고 시스템을 건드리지 않는다. 대신 `streetlevel`의 어느 버전이 `pyexiv2`를 읽을 때도 쓰도록 바뀌면 깨질 수 있어서 버전을 고정한다. B는 라이브러리를 그대로 쓰지만 `torch`는 이 유닛에서 쓰지 않는다.

[Answer]: A

## Question 2 — 고정할 범위
줄인 묶음(21개)의 버전을 어디까지 고정할까?

A) 21개 전부 정확한 버전으로 인라인 의존성에 적는다(시험한 환경의 버전). 그대로 `pip-audit`의 입력이 된다

B) `streetlevel`만 고정하고 나머지는 U1처럼 그대로 둔다(전이 의존성은 고정하지 않음)

X) Other (please describe after [Answer]: tag below)

참고: 이 라이브러리는 네이버의 내부 통신을 다뤄서 환경이 달라지면 깨질 가능성이 크다. A가 같은 환경을 언제든 다시 만들 수 있게 해 준다. 단점은 의존성 목록이 길어지는 것이다. U1은 직접 쓰는 패키지만 고정했다.

[Answer]: A

## Question 3 — CI와 테스트에서 `streetlevel` 다루기
GitHub Actions와 테스트를 어떻게 할까?

A) CI에는 `streetlevel`을 설치하지 않는다. 어댑터를 가짜로 바꿔 테스트하고, 실제 네이버 호출은 Build and Test에서 수동으로만 한다

B) A에 더해, CI가 줄인 묶음을 설치해서 `import`만 확인하는 가벼운 시험과 그 묶음에 대한 `pip-audit`를 돌린다(네트워크로 네이버를 부르지는 않는다)

X) Other (please describe after [Answer]: tag below)

참고: A는 CI가 빠르고 단순하다. B는 `streetlevel`이나 의존성이 깨졌을 때 CI가 알려 준다. 둘 다 CI에서 네이버를 호출하지는 않는다(차단 위험을 피하려는 것).

[Answer]: B

## Question 4 — 저장 공간 기준
`captures/`가 얼마까지 커져도 될까? (파노라마는 장당 약 1.3 MB, 크롭은 장당 약 0.1~0.2 MB이고 칸당 장수는 아직 모른다.)

A) 한도 없이 진행하고, 첫 칸 결과로 실제 크기를 재서 Build and Test에서 보고한다

B) 한도를 정한다: 5 GB를 넘으면 새 다운로드를 멈추고 알린다

C) 한도를 정한다: 20 GB를 넘으면 새 다운로드를 멈추고 알린다

X) Other (please describe after [Answer]: tag below)

참고: 디스크 여유는 약 608 GB다. 3칸이면 한도가 걸릴 일은 없을 것 같지만 확장하면 달라진다. 한도를 걸면 위반 시 멈추는 코드와 테스트가 하나 늘어난다.

[Answer]: A

---

## 답변 분석 후 추가한 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| N-U3-9 | CI가 쓸 자체 점검 진입점을 `capture.py --selftest`로 한다. 어댑터를 불러와 `streetlevel`이 `import`되는지만 확인하고 네트워크는 부르지 않는다. 스크립트의 인라인 의존성을 그대로 쓰므로 목록이 두 곳에 중복되지 않는다 | Q3=B의 세부 |
| N-U3-10 | CI의 `pip-audit` 입력은 `capture.py`의 인라인 의존성에서 뽑는다(`uv export --script`가 되면 그것으로, 안 되면 `tests/test_versions.py`의 파서로 목록을 만든다. 코드 생성에서 확인한다) | 감사 대상과 실제 실행 환경이 같아야 한다 |

