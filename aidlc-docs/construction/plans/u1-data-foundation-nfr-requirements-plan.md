# U1 데이터 기반 — NFR Requirements Plan

대상: C7 `db.py`, C1 `cells.py`, C2 `register.py` (로컬에서 `uv run`으로 실행하는 Python 스크립트와 SQLite).
이 단계는 비기능 요구와 기술 선택을 정한다. 이 유닛에서 정한 도구와 규칙은 U3, U2, U4, U5도 이어서 쓴다.

각 질문의 `[Answer]:` 뒤에 알파벳을 적어 줘. 맞는 보기가 없으면 X를 고르고 설명을 적는다.

## 계획 (체크리스트)

- [x] U1 Functional Design 읽기, 확장 규칙(Security, Resiliency, PBT) 이 단계 항목 확인
- [x] 아래 질문 7개에 답 받기 (사용자가 채팅으로 답했고 이 파일에 그대로 옮겨 적음)
- [x] 답변 분석: 모든 답이 알파벳 하나로 명확하고 서로 모순이 없다. 단, Q2(테스트 도구)와 Q4(스크립트별 인라인 의존성) 사이의 빈틈은 질문 대신 기본값 N-8, N-9로 메웠다(아래 문서 참고)
- [x] `construction/u1-data-foundation/nfr-requirements/nfr-requirements.md` 생성
- [x] `construction/u1-data-foundation/nfr-requirements/tech-stack-decisions.md` 생성
- [x] 확장 규칙 준수 요약 작성 (Security, Resiliency, PBT-09)

## 이미 정해진 것 (질문 안 함)

| 항목 | 내용 | 근거 |
|---|---|---|
| 복구 목표 | RTO/RPO 수 시간, 백업 후 복구. DB 보호는 `overrides` 텍스트 내보내기(설계 Q8=B)로 만족한다 | NFR-6, RESILIENCY-02 |
| 실행 환경 | 사용자 Mac 로컬. 서버, 클라우드, 사용자 인증 없음 | 요구사항 |
| 데이터 민감도 | 공개 데이터(OSM, GIS건물통합정보, 건축물대장 표제부)만 DB에 둔다. 개인정보와 사진은 DB에 없다 | 설계 D-5, 도메인 엔티티 |
| 인증키 | 환경변수 `DATA_GO_KR_KEY`로만 읽는다. 코드와 저장소에 넣지 않는다 | NFR-7 |

## 설계 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| N-1 | `.env`는 `uv run --env-file .env src/cells.py ...`로 읽는다. 별도 라이브러리 없이 uv 기능을 쓴다 | 의존성을 늘리지 않으려는 것 |
| N-2 | SQLite는 표준 라이브러리 `sqlite3`를 쓴다. 모든 질의는 매개변수 바인딩만 쓰고 문자열을 이어 붙이지 않는다. 외래 키 제약을 켠다 | SECURITY-05 (주입 방지) |
| N-3 | HTTPS 인증서 검증을 끄지 않는다. 응답은 쓰기 전에 검증한다(U1 Business Rules BR-7.4) | SECURITY-01(전송 중 암호화), 응답 검증 |
| N-4 | 각 스크립트의 진입점에 최상위 오류 처리를 둔다. 오류가 나면 작업을 멈추고 로그에 남기고 0이 아닌 코드로 끝낸다. 메시지에 키와 내부 경로를 넣지 않는다 | SECURITY-15 |
| N-5 | 저장 시 암호화(SECURITY-01)는 이 유닛에서 별도 구성하지 않는다. 공개 데이터만 두고, 디스크 암호화는 Mac 자체 설정(FileVault)에 맡긴다. FileVault가 켜져 있는지는 확인하지 못했다 | 개인정보 없음, 로컬 파일 |
| N-6 | 칸 하나를 수집·조립하는 데 수 분 이내를 목표로 한다. Overpass 호출 사이에는 지금처럼 간격을 둔다 | NFR-1 성능은 Studio 쪽 기준이고 이 유닛은 수집 속도만 해당 |
| N-7 | 사용자 인터페이스는 명령줄뿐이다. 접근성 요구는 없다. 출력은 칸 ID별 진행 상황과 건수, 실패 이유가 한눈에 보이게 한다 | 사용성 |

## Question 1 — 기하 계산 라이브러리
겹침 비율, 면적 무게중심, 자기 교차 검사에는 다각형 교집합 계산이 필요하다. 어떻게 할까?

A) `shapely`를 쓴다 (검증된 기하 라이브러리, 의존성 1개 추가)

B) 표준 라이브러리만으로 직접 구현한다 (의존성은 없지만 교집합 면적은 직접 짜야 한다)

X) Other (please describe after [Answer]: tag below)

참고: 교집합 면적과 자기 교차 판정은 직접 구현하면 경계 사례에서 틀리기 쉽다. 위경도는 칸 크기에서 작은 영역이라 지역 평면 좌표로 바꿔 계산하는 걸 기본으로 한다.

[Answer]: A

## Question 2 — 테스트 도구 (PBT-09)
속성 기반 테스트를 쓰려면 프레임워크가 필요하다. 요구되는 기능은 사용자 정의 생성기, 자동 축소, 시드 재현이다. 어떻게 할까?

A) `pytest` + `Hypothesis`

B) 표준 `unittest` + `Hypothesis`

X) Other (please describe after [Answer]: tag below)

참고: Hypothesis가 Python의 표준적인 선택이다. pytest가 설정과 출력이 간단하다. 테스트는 `tests/`에 두고, 실패 시 시드가 출력되게 설정한다(PBT-08).

[Answer]: A

## Question 3 — HTTP 클라이언트
Overpass, GIS건물통합정보, 건축HUB를 호출할 때 무엇을 쓸까?

A) 표준 라이브러리 `urllib`을 계속 쓴다 (지금 `cells.py`가 쓰는 방식, 의존성 없음)

B) `httpx` 또는 `requests`를 쓴다 (재시도, 시간 제한, 오류 처리가 편하다)

X) Other (please describe after [Answer]: tag below)

참고: 재시도는 이미 직접 구현돼 있고 호출 대상이 3곳뿐이라 A로 충분하다. B는 시간 제한과 재시도 정책을 쓰기 편하지만 의존성이 늘어난다.

[Answer]: A

## Question 4 — 의존성 관리와 취약점 점검 (SECURITY-10)
의존성은 정확한 버전으로 고정해야 하고, 취약점 점검 방법을 문서화해야 한다. 어떻게 관리할까?

A) 각 스크립트의 인라인 의존성(PEP 723)에 `==`로 버전을 고정한다. 취약점 점검은 `pip-audit`를 수동으로 돌리는 절차를 문서에 적는다

B) 루트에 `pyproject.toml`과 `uv.lock`을 두고 한 곳에서 관리한다(테스트 도구는 개발용 그룹). 취약점 점검은 `pip-audit` 절차를 문서에 적는다

X) Other (please describe after [Answer]: tag below)

참고: A는 설계(스크립트마다 `uv run`으로 단독 실행)와 맞지만 의존성이 스크립트마다 흩어진다. B는 한 곳에서 보이고 테스트 의존성도 정리되지만 `uv run src/cells.py`가 프로젝트 환경을 쓰게 되어 지금 방식에서 조금 바뀐다.

[Answer]: A

## Question 5 — 로그
스크립트 실행 기록을 어떻게 남길까? 로그에는 시각, 수준, 칸 ID, 메시지를 넣고 키는 넣지 않는다.

A) 표준 `logging`으로 콘솔에 출력하고 `data/logs/`에 파일로도 저장한다 (git 제외)

B) 콘솔에만 출력한다. 실행 결과는 DB의 `collection_runs`가 기록한다

X) Other (please describe after [Answer]: tag below)

참고: 규칙의 중앙 로그 서비스와 90일 보관은 배포된 서비스를 위한 것이라 이 로컬 도구에는 해당하지 않는다고 본다. A는 실패 원인을 나중에 볼 수 있다.

[Answer]: A

## Question 6 — 가까운 시일의 규모
이 유닛을 몇 칸까지 돌릴 계획인가? 건축HUB 호출 상한과 칸 간격 같은 수치를 정하는 데 필요하다.

A) 심원고 3칸만

B) 심원고와 주변 칸을 합쳐 10칸 안팎

C) 동네 단위로 수십 칸

X) Other (please describe after [Answer]: tag below)

참고: 확장 계획이 있다고 했지만 첫 확장이 어느 정도인지는 모른다. A면 호출 상한이 단순하다. 하루 호출 한도는 확인하지 못했다.

[Answer]: A

## Question 7 — GIS건물통합정보 활용신청 상태
Q1=C(OSM 우선, 빈 곳은 GIS로 채움)에는 GIS건물통합정보가 필요하다. 공공데이터포털(데이터 15123970)에서 활용신청은 어떻게 됐나?

A) 신청을 마쳤고 승인된 키가 있다

B) 아직 안 했다. 코드를 짜기 전에 신청하겠다

C) 신청하지 않는다. 당분간 OSM 건물만으로 진행한다 (설계 F-8)

X) Other (please describe after [Answer]: tag below)

참고: 키는 건축HUB와 다를 수 있다. 어느 쪽이든 진행은 가능하지만, B나 C를 고르면 U1 코드 생성의 첫 시험이 달라진다.

[Answer]: B (이후 V-World 개발키를 발급받았다는 스크린샷을 보냄, 2026-10-13)

---

## 답변 분석 후 추가한 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| N-8 | 테스트는 `uv run --with-requirements tests/requirements.txt pytest tests/`로 돌린다. 이 파일에 `pytest`, `hypothesis`, `shapely`, `h3`를 `==`로 고정하고 스크립트 인라인 의존성과 같은 버전을 쓴다. 두 곳이 어긋나면 알려 주는 테스트를 하나 둔다 | Q2(테스트 도구)와 Q4(스크립트별 인라인 의존성)가 만나는 곳의 빈틈 |
| N-9 | 공용 순수 함수(무게중심, 칸 배정, 유효성, 겹침 비율)는 `src/geo.py`에 둔다. C1과 C2가 가져다 쓴다 | `cells.py`와 `register.py`가 같은 계산을 쓰는데 컴포넌트끼리 직접 호출하지 않는다는 설계 원칙을 지키려는 것 |
| N-10 | 건축HUB 호출 상한은 한 실행당 100건으로 시작한다. 포털의 하루 한도를 확인한 뒤 조정한다 | Q6=A(3칸)에 맞춘 값, 한도는 확인하지 못했다 |

> **2026-10-13 갱신:** V-World 시험과 재확인(Q1=B 단순화, Q2=B 건축HUB 제외) 결과 N-10(건축HUB 호출 상한)은 폐기했다. 다른 기본값(N-1~N-9)은 그대로다. Q7(GIS 활용신청)은 V-World 키 발급으로 대체됐고 데이터 포털 활용신청은 필요 없다.
