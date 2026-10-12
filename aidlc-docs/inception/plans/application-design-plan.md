# Application Design Plan — roblox-map

깊이: **최소(minimal)**. 컴포넌트 경계와 인터페이스만 정한다. 비즈니스 규칙(좌표 변환식, 높이 보정식 등)은 Functional Design에서 정한다.

각 질문의 `[Answer]:` 뒤에 알파벳을 적어 줘. 맞는 보기가 없으면 마지막 보기(X, Other)를 고르고 설명을 적는다. "참고"는 내 의견이고 답을 정해 주는 건 아니다.

## 설계 계획 (체크리스트)

- [x] 요구사항 분석 (`requirements.md`)
- [x] 아래 질문 6개에 답 받기 (사용자가 채팅으로 답했고 이 파일에 그대로 옮겨 적음)
- [x] 답변 분석 → 모순 1건 발견, 후속 질문 2개 추가
- [x] 후속 질문 답 받기 (Q7=A, Q8=B, 모순 해소)
- [x] `application-design/components.md` 생성 (컴포넌트 정의와 책임)
- [x] `application-design/component-methods.md` 생성 (메서드 시그니처, 규칙 상세는 Functional Design)
- [x] `application-design/services.md` 생성 (서비스 정의와 오케스트레이션)
- [x] `application-design/component-dependency.md` 생성 (의존 관계, 데이터 흐름)
- [x] `application-design/application-design.md` 생성 (위 문서를 하나로 통합)
- [x] 설계의 완전성과 일관성 검증 (컴포넌트 7개 모두 책임, 메서드, 의존이 문서에 있고 순환 의존 없음)

## 현재 이해한 컴포넌트 후보

| 후보 | 책임 | 근거 |
|---|---|---|
| 칸 수집기 (`cells.py` 확장) | 구역 → H3 칸, OSM 건물·도로·가로시설 수집 | FR-1, 2, 3 |
| 건축물대장 연결기 | 건물 ↔ 건축물대장 층수 연결 | FR-2, 9, A-7 |
| 거리뷰 캡처기 | Playwright 360도 캡처, 속도 제한, 차단 시 중단 | FR-8, NFR-5 |
| 높이·외관 판단 | 층수 검증, 대장 없는 건물 추정, 외관 속성, 근거 기록 | FR-8, 9 |
| Studio 생성기 | 좌표 → stud, 박스·도로 생성, 레이어 분리 | FR-4, 10, 11, 12 |
| 확인·보정 루프 | Studio 캡처와 거리뷰 비교, 사용자와 같이 보정, 보정값 보존 | FR-9, FR-11 |

## Question 1 — 건물과 건축물대장 연결 방법
건축물대장 API는 법정동코드+번지로 조회하는데, OSM 건물 외곽선에는 번지가 없는 경우가 많다. 건물을 대장에 어떻게 연결할까?

A) OSM에 있는 주소 태그(`addr:*`)를 쓰고, 없는 건물은 연결하지 않는다

B) 건물 중심점이 속한 필지(지번)를 찾아서(V-World 연속지적도 등, 별도 인증키 필요) 그 지번으로 대장을 조회한다

C) 건물 도형에 대장 속성이 이미 붙어 있는 GIS건물통합정보를 받아 OSM 건물과 위치가 겹치는 것끼리 매칭한다

D) 3칸 규모이니 사용자와 Claude가 지도를 보며 수동으로 매칭한다

E) 위 방법 중 하나를 먼저 쓰고, 실패한 건물만 수동으로 매칭한다 (먼저 쓸 방법은 Other에 적기)

X) Other (please describe after [Answer]: tag below)

참고: 확인된 건 대장 API가 키로 호출된다는 것까지다. B와 C는 해당 서비스에서 실제로 되는지 구현 단계에서 먼저 시험해야 한다. 동네를 확장할 계획이라 처음부터 수동(D)만 쓰기엔 부담이 크다.

[Answer]: C

## Question 2 — 코드 구조
컴포넌트를 코드로 어떻게 나눌까?

A) 역할별 스크립트 여러 개(`cells.py`, `register.py`, `capture.py`, `estimate.py`, `build_luau.py` 등). 각각 `uv run`으로 실행하고 칸 JSON 파일로 주고받는다

B) 하나의 CLI 도구에 하위 명령으로 묶는다 (`mapctl cells|register|capture|...`)

C) 지금 `cells.py`에 계속 기능을 추가한다

X) Other (please describe after [Answer]: tag below)

참고: 칸 단위로 단계를 다시 돌릴 수 있어야 해서(NFR-3) 단계마다 파일이 입출력인 A가 가장 단순하다. B는 확장이 늘면 나중에 A에서 합쳐도 된다.

[Answer]: A

## Question 3 — 데이터 파일 구조와 보정값 보존
칸 데이터와 판단 결과, 사용자와 Claude가 보정한 값을 어떻게 저장할까?

A) 칸마다 JSON 하나(`cells/<칸ID>.json`)에 건물별 필드를 계속 추가한다

B) 단계별로 파일을 나눈다: 원천 데이터(OSM, 대장), 판단 결과(거리뷰 추정), **수동 보정(오버라이드)**. 재생성해도 수동 보정 파일은 건드리지 않고 마지막에 덮어쓰는 순서로 합친다

C) 데이터베이스(SQLite 등)를 쓴다

X) Other (please describe after [Answer]: tag below)

참고: `cells/`는 git에서 제외한다(재생성 가능). 그런데 수동 보정은 재생성이 안 되는 값이라 따로 보관해야 한다. 보정 파일을 git에 올릴지는 Functional Design에서 정한다.

[Answer]: C

## Question 4 — Studio 생성 방식
Python은 MCP를 직접 호출할 수 없고, Claude가 `execute_luau`로 실행해야 한다. 건물을 Studio에 어떻게 만들까?

A) Python이 칸 JSON을 Luau 코드로 바꿔 주고, Claude가 건물 수십 개씩 나눠 `execute_luau`로 실행한다

B) Studio 안에 생성용 ModuleScript를 한 번 넣어 두고, Claude가 칸 데이터(JSON)만 넘겨 실행한다. 코드는 Studio에 남는다

C) 처음엔 A로 시작하고 반복이 불편해지면 B로 바꾼다

X) Other (please describe after [Answer]: tag below)

참고: `execute_luau`는 실행 중 Studio가 멈추고 연결이 끊길 수 있어서 작은 덩어리로 나눠야 한다(도구 설명). B는 로직을 Studio 안에서 고칠 수 있지만 버전 관리가 Git 밖이 된다.

[Answer]: B

## Question 5 — 자동 생성과 수작업 레이어 구조
FR-11대로 재생성해도 수작업이 남아야 한다. Studio 안에서 어떻게 나눌까?

A) `Workspace` 아래에 `Auto/<칸ID>` 폴더와 `Manual` 폴더를 따로 둔다. 재생성은 `Auto/<칸ID>`만 지우고 다시 만든다. 자동 건물을 직접 고치려면 `Manual`로 옮긴다

B) 모든 건물을 같은 폴더에 두고 건물마다 속성(`source=auto/manual`)을 달아 구분한다. 재생성은 `auto` 건물만 갱신한다

X) Other (please describe after [Answer]: tag below)

참고: A가 단순하고 실수로 수작업을 지울 일이 적다. B는 건물 단위로 섞어 쓰기 편하다.

[Answer]: A

## Question 6 — 거리뷰 캡처 지점과 방식
네이버 거리뷰는 도로를 따라 놓인 파노라마 지점에서 본다. 건물마다 어떻게 찍을까? (구체적인 URL·조작 방법은 약관 확인 후 구현 단계에서 확인한다)

A) 건물마다 가장 가까운 거리뷰 지점 1곳에서 건물 쪽을 보는 사진을 여러 각도(정면 위주)로 찍는다

B) 건물마다 가까운 지점 2~3곳에서 각각 건물 쪽 사진을 찍는다. 차량 등에 가려도 다른 사진으로 보완한다

C) 칸마다 지점을 몇 곳 정해 360도 파노라마를 찍고, 건물별로 그 사진에서 해당 방향을 골라 쓴다

X) Other (please describe after [Answer]: tag below)

참고: 요청 수를 줄이는 쪽(NFR-5)은 C, 건물별 정확도는 B가 유리하다. 심원고는 부지 안쪽 건물이 많아 도로에서 안 보일 수 있다는 점도 같이 고려해 줘.

[Answer]: C (어차피 칸별로 채울거면 이게 좋을 듯 사진도 그거에 맞게 분리해서 저장 또 쓸수 있으니)

---

# 후속 질문 (답변 분석 결과)

Question 2 = A와 Question 3 = C가 서로 부딪힌다. Question 2의 A는 "칸 JSON 파일로 주고받는다"는 전제였는데, Question 3에서 SQLite를 골랐다. 스크립트끼리 무엇으로 데이터를 주고받는지, SQLite 파일을 어떻게 보호하는지 정해야 한다.

## Question 7 — 스크립트가 주고받는 매체 (Q2 A와 Q3 C 사이)
역할별 스크립트가 서로 데이터를 넘기는 중심은 무엇인가?

A) SQLite DB 하나가 중심이다. 모든 스크립트가 DB를 읽고 쓰고, `cells.py`도 DB에 쓰도록 바꾼다. `cells/*.json`은 더 만들지 않는다

B) `cells.py`는 지금처럼 `cells/<칸ID>.json`을 만든다(원천 캐시). 다음 단계가 이 JSON을 DB에 적재하고, 이후 단계는 DB만 쓴다

X) Other (please describe after [Answer]: tag below)

참고: A가 흐름이 하나라 단순하다. B는 `cells.py`를 고치지 않아도 되고 OSM 원본이 파일로 남아 DB가 깨져도 다시 적재할 수 있다.

[Answer]: A

## Question 8 — DB 파일 보호 (NFR-6, RPO 수 시간)
SQLite에는 재생성이 안 되는 값(사용자와 Claude가 보정한 높이·외관)이 들어간다. 이 값을 어떻게 지킬까? 사진은 DB에 넣지 않고 `captures/<칸ID>/`에 로컬로만 둔다(저장소가 public이라 git 제외).

A) DB 파일을 통째로 git에 올린다(바이너리라 diff는 안 되지만 단순하다)

B) DB 파일은 git에서 제외하고, 수동 보정 테이블만 텍스트(JSON 또는 SQL 덤프)로 내보내 git에 올린다(diff가 되고 복구도 된다)

C) DB 파일은 git에서 제외하고, 큰 작업 전에 파일을 복사해 두는 것으로 백업한다

X) Other (please describe after [Answer]: tag below)

참고: 이 저장소는 public이다. 건물 원천 데이터(OSM, 공공 데이터)까지 DB째로 올리면 용량과 라이선스 표기 부담이 생기는데, B는 보정값만 올려서 그 문제가 없다.

[Answer]: B

---

## 설계에 반영할 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| D-1 | Q1=C(GIS건물통합정보 매칭)가 시험에서 안 되면 자동으로 다른 방법으로 바꾸지 않고, 이 결정을 다시 연다 | 확인된 건 건축HUB API뿐이고 GIS건물통합정보의 실제 조회 방법은 구현 단계 첫 시험으로 확인한다 |
| D-2 | 건축HUB API(`getBrTitleInfo`)는 GIS건물통합정보에 없는 필드나 누락 건물을 메우는 보조로 둔다. 이미 키가 있다 | Q1=C에서 이 API의 역할이 정해지지 않았다 |
| D-3 | Q4=B의 생성 모듈 Luau 소스는 저장소(`studio/`)에 두고, Claude가 `execute_luau`로 Studio의 ModuleScript에 넣거나 갱신한다 | 코드가 Studio 안에만 있으면 Git 관리 밖이 된다 |
| D-4 | Q6=C로는 도로에서 안 보이는 부지 안쪽 건물에 사진이 없을 수 있다. 그런 건물은 층수를 대장 값으로만 정하고 사용자와 Claude가 같이 확인한다 | 사진 없는 건물의 처리를 Functional Design(캡처 유닛)에서 구체화한다 |
| D-5 | 사진은 `captures/<칸ID>/<지점ID>/` 아래에 칸별로 나눠 저장하고 DB에는 경로와 메타데이터만 둔다. 같은 사진을 다른 건물 판단에 다시 쓴다 | Q6 답변의 의도 |

