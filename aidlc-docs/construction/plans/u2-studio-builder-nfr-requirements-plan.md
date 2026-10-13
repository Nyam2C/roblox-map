# U2 Studio 생성기 — NFR Requirements Plan

대상: C6 `build_luau.py`(Python)와 `studio/Builder.luau`(Studio 모듈). 실행 환경은 U1·U3과 같다(사용자 Mac, `uv run`, SQLite). Studio는 Studio 내장 MCP 서버로 연결한다.
U1·U3에서 정한 도구와 규칙(`uv`, 의존성 고정, `pytest` + `Hypothesis`, JSON 로그, `config.toml`, GitHub Actions, `pip-audit`, 백업, 복구 런북)은 이어서 쓴다. 여기서는 U2에만 해당하는 것을 정한다. 계획상 이 단계는 "이어서 적용(성능 기준)"이다.

각 질문의 `[Answer]:` 뒤에 알파벳을 적어 줘(채팅으로 "A A A A"처럼 답해도 내가 옮겨 적는다). 맞는 보기가 없으면 X를 고르고 설명을 적는다.

## 계획 (체크리스트)

- [x] U2 Functional Design 읽기, 확장 규칙 이 단계 항목 확인
- [x] Studio MCP 가능성 시험(아래 "시험 결과"). 시험 부품은 `MCP_Test` 안에서만 만들고 모두 지웠다
- [x] 아래 질문 4개에 답 받기 (사용자가 채팅으로 "A A A A"라고 답했고 이 파일에 그대로 옮겨 적음)
- [x] 답변 분석: 모두 추천이고 알파벳 하나로 명확하며 서로 모순이 없다. 후속 질문 없음. Q2=A와 Q3=A는 첫 생성 때 할 일이 생긴다(스트리밍 끄기는 Claude, `.rbxl` 복사본은 사용자)
- [x] `construction/u2-studio-builder/nfr-requirements/nfr-requirements.md` 생성
- [x] `construction/u2-studio-builder/nfr-requirements/tech-stack-decisions.md` 생성
- [x] 확장 규칙 준수 요약 작성 (Security, Resiliency, PBT)

## 시험 결과 (2026-10-13, Studio 0.742, 편집 모드)

기능 설계가 "코드 생성에서 확인"으로 남긴 항목들을 먼저 시험했다. 시험 부품은 `Workspace.MCP_Test` 안에서만 만들었고 끝난 뒤 모두 지웠다(`MCP_Test`는 `TestBase`, `TestBuilding` 두 개만 남은 처음 상태, `ServerStorage`는 비어 있음).

| 항목 | 결과 |
|---|---|
| 회전 방향(BR-1.4) | **맞다.** `CFrame.Angles(0, rad(30), 0)`의 오른쪽 축이 `(0.866, 0, −0.5)`다. 양수 yaw가 동쪽에서 북쪽(−Z)으로 돈다. 실제 건물 값으로 만든 부품(yaw 159.1°)을 읽어 보니 오른쪽 축이 `(−0.934, 0, −0.357)`로 계산과 같다 |
| `ModuleScript`에 소스 쓰기(D-3) | **된다.** `Source`에 2,124자를 쓰고 바로 `require`했다. 덩어리 파일에 Builder를 같이 넣는 대안은 필요 없다 |
| 실제 덩어리로 실행 | 첫 칸 건물 50개의 덩어리 데이터는 **3.7 KB**(건물당 약 75바이트). 호출이 성공했고 부품 49개 생성에 **4.6 ms**, 비우기와 다시 만들기까지 합쳐 8 ms다 |
| 수작업 우선(BR-2.8) | `Manual`에 같은 `BuildingId`를 가진 부품을 두었더니 49개를 만들고 1개를 건너뛰었다. 재생성 뒤에도 `Manual`의 부품은 그대로다 |
| 재생성(BR-6.2) | 같은 칸을 다시 `begin`하면 `Auto/<칸ID>`가 비워지고 같은 결과(Buildings 49)로 다시 만들어진다. `BuildComplete`는 `begin`에서 false, `finish`에서 true였다 |
| 대량 생성 속도 | 부품 200개를 컨테이너에서 만들어 한 번에 넣는 데 13 ms, 지우는 데 0.7 ms |
| 재질과 스폰 | `Grass`, `Asphalt`, `Pavement`, `Concrete`가 모두 있다. `SpawnLocation`의 기본 `Duration`이 10이라 BR-5.3대로 0을 명시해야 한다 |
| 규모 추정 | 첫 칸 전체(약 163개)의 데이터는 약 12 KB로 **추정**한다(건물 50개의 실측 3.7 KB에서 항목당 약 75바이트로 곱함, 도로와 인도 항목은 아직 안 만들어서 실측 아님). `chunk_size` 50이면 호출당 약 4~6 KB |
| `StreamingEnabled` | 이 장소는 **켜져 있다**(새 장소 기본값). 질문 2 참고 |

시험하지 못한 것: 수십 KB가 넘는 호출의 한도(첫 칸은 호출당 6 KB 이하라 필요 없다), 플레이 테스트의 프레임 수(아직 만들 것이 없다. Build and Test와 U5에서 잰다).

## 이미 정해진 것 (질문 안 함)

| 항목 | 내용 | 근거 |
|---|---|---|
| 복구 목표 | RTO/RPO 수 시간. Studio 결과는 `Auto`를 다시 만들면 되고, 수작업(`Manual`)이 보호 대상이다 | NFR-6 |
| 비밀값 | 이 유닛은 키나 로그인 정보를 쓰지 않는다. MCP는 로컬 연결이다 | 기능 설계 |
| 대상 기기 | PC(사용자 Mac의 Studio 플레이 테스트) | NFR-1(Q13=A) |
| 도구 | `uv`, `pytest` + `Hypothesis`, `config.toml`, JSON 로그, GitHub Actions, `pip-audit` | U1 NFR Design |

## 설계 기본값 (질문은 안 하지만 틀리면 말해 줘)

| # | 내용 | 이유 |
|---|---|---|
| N-U2-1 | `build_luau.py`는 `h3==4.5.0`, `shapely==2.2.0`만 쓴다(`register.py`와 같은 고정). 새 의존성이 없다. Python 3.11 이상. 순수 계산(좌표 변환, 박스 맞춤, 도로·인도 조각, 땅, 덩어리)은 입출력 없는 모듈로 따로 둬서 속성 P2-1~P2-9가 대응한다 | 속성 기반 테스트 대상, U3의 `projection.py`와 같은 방식 |
| N-U2-2 | 성능 목표: ① Python이 첫 칸의 덩어리 파일과 manifest를 쓰는 데 5초 이내(건물 박스 맞춤이 대부분) ② Studio 호출 한 번은 1초 이내(시험에서 8 ms). 이 목표들은 한 번의 호출이 Studio를 멈추지 않게 하려는 것이다 | 시험 결과, Studio MCP 도구 설명(무거운 호출은 쪼갤 것) |
| N-U2-3 | `chunk_size` 기본값은 50 그대로 둔다(호출당 약 4~6 KB, 칸당 4번). 시험한 크기(3.7 KB)보다 크게 늘리지 않는다. 설정값이라 나중에 바꿀 수 있다 | 시험하지 않은 크기를 기본값으로 쓰지 않는다 |
| N-U2-4 | Luau 코드에 들어가는 문자열(건물 ID, 도로 ID, 칸 ID, `Source`)은 허용 문자(영문자, 숫자, `:` `#` `_` `-` `.`)만 통과시키고 Luau 문자열 리터럴로 이스케이프한다. 허용 문자 밖이면 그 항목은 건너뛰고 경고한다. 숫자는 유한한 값만 쓴다. 칸 ID는 H3 형식(15자리 16진수)인지 확인한다. `begin`이 지우는 대상은 `Auto/<칸ID>` 하나뿐이다 | 외부 API(V-World, OSM) 데이터가 실행되는 코드에 들어가므로 코드 주입을 막는다(SECURITY-05) |
| N-U2-5 | `Builder.luau`에 `verify(칸ID)`를 둔다. 폴더별 부품 수와 건너뛴 수를 돌려주고 manifest와 비교해서 S-1을 자동으로 확인한다. 부품 몇 개의 위치·크기·회전을 읽는 S-2도 같은 방식으로 한다 | 사람이 세지 않아도 되게 |
| N-U2-6 | 실행 기록: `build_luau.py`는 실행마다 `collection_runs`에 `unit = 'C6'`로 항목 수(종류별), 덩어리 수, `poor_fit` 수, 경고 수를 남긴다. 콘솔에는 한눈에 보이는 요약과 "Studio에서 실행할 순서"를 인쇄한다. Studio 쪽 결과(만든 수, 건너뛴 수)는 manifest와 비교한 결과를 Claude가 보고한다 | U1·U3과 같은 방식 |
| N-U2-7 | 칸 하나를 만드는 일은 처음부터 다시 하는 것이 가장 단순하다(8 ms). 호출이 실패하거나 연결이 끊기면 그 칸을 `begin`부터 다시 한다(`BuildComplete = false`로 남은 칸은 미완성). 이어서 하는 기능은 만들지 않는다 | 기능 설계 BR-6.3, 시험 결과 |
| N-U2-8 | 부품 수 예산(참고값): U2 단계에서 칸당 1,000개 이하(첫 칸 예상 약 163개), U5까지 포함해 3칸 합계 30,000개 이하. 플레이 테스트에서 프레임 수를 재서 조정한다 | NFR-1 수치화(질문 1과 같이 쓴다) |
| N-U2-9 | 설정값(`config.toml`)에 추가: `origin_lat`, `origin_lon`, `studs_per_m`, `poor_fit_ratio`, `ground_margin_m`, `sidewalk_width_m`, 도로 폭 표, `chunk_size`, `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`. 범위 검증은 U3처럼 `common.py`에서 한다 | U1·U3의 설정 방식 |
| N-U2-10 | 테스트: Python 순수 함수는 속성 기반 테스트(P2-1~P2-9), 덩어리 파일과 manifest는 예시 기반 테스트. Luau 쪽은 Studio에서 S-1~S-6과 `verify`로 확인한다(CI에서 Studio를 돌리지 않는다) | PBT-01, 질문 4 |
| N-U2-11 | 복구 런북 추가(U1 R-1~R-6, U3 R-7~R-9에 이어서): **R-10** 칸이 반쯤 만들어졌거나 Studio 연결이 끊김 → 같은 칸을 다시 실행. **R-11** 자동 건물을 잘못 지움 → 다시 실행(`Auto`는 항상 다시 만든다). **R-12** `Manual` 작업이 사라짐 → Studio의 Version History 또는 `.rbxl` 복사본에서 복구 | NFR-6 |

## Question 1 — 성능 기준 (NFR-1)
"3개 칸 규모를 끊김 없이 걸어 다닐 수 있다"를 수치로 어떻게 정할까? 프레임 수는 사용자 Mac의 Studio 플레이 테스트에서 걷는 동안 잰다. U2 끝에서는 첫 칸으로, 최종은 U5 끝에서 칸 3개로 확인한다.

A) 평균 60 FPS 이상, 순간 최저 30 FPS 이상(1초 이상 끊기지 않을 것)

B) 평균 30 FPS 이상

C) 수치 없이 사용자가 걸어 보고 끊기는지 눈으로만 판단한다

X) Other (please describe after [Answer]: tag below)

추천: A. 부품이 수백~수천 개인 지금 규모에서는 쉽게 넘는 값이라 U5에서 디테일이 늘어날 때 기준선이 된다. 측정 방법은 코드 생성에서 정한다.

[Answer]: A

## Question 2 — 스트리밍(`StreamingEnabled`)
이 장소는 지금 스트리밍이 **켜져 있다**(새 장소 기본값). 켜져 있으면 플레이할 때 플레이어 가까이의 부품만 불러오고 멀리 있는 부품은 내려서, 멀리 있는 건물이 안 보이거나 늦게 나타날 수 있다.

A) 끈다. 부품이 수백~수천 개라 전부 한 번에 불러와도 부담이 적고 멀리까지 보인다. U5 이후 부품이 수만 개가 되면 다시 정한다. 이 설정은 Claude가 첫 생성 때 한 번 바꾼다(기본 물체를 끄는 것과 같은 때)

B) 켜 둔 채로 쓴다. 큰 맵에 유리하지만 멀리 있는 건물이 보이지 않아 스케일을 같이 확인하는 일이 불편하다

X) Other (please describe after [Answer]: tag below)

추천: A.

[Answer]: A

## Question 3 — Studio 맵의 백업
수작업(`Manual`)이 쌓이면 그것이 이 프로젝트에서 되돌릴 수 없는 유일한 자산이다. `Auto`는 언제든 다시 만들 수 있다. 이 장소는 클라우드 장소라 Studio의 Version History가 있다.

A) 첫 생성 전에 사용자가 `.rbxl` 복사본을 한 번 만들어 둔다(파일 > 다른 이름으로 저장). 이후에는 Version History에 맡기고, `Manual` 작업이 쌓인 뒤(U5부터)의 큰 변경 전마다 복사본을 만든다

B) 칸을 생성하거나 재생성할 때마다 복사본을 만든다

C) 복사본 없이 Version History만 쓴다

X) Other (please describe after [Answer]: tag below)

추천: A. 재생성은 `Auto/<칸ID>`만 지우고 `Manual`은 읽기만 하며 그 동작은 시험으로 확인했다.

[Answer]: A

## Question 4 — Luau 코드 검사
`studio/Builder.luau`는 약 100줄이 될 것이다. Python 쪽은 CI에서 `pytest`와 `pip-audit`를 돌린다. Luau는?

A) CI에서 검사하지 않는다. Studio에서 `verify`와 S-1~S-6으로 매번 확인한다

B) CI에서 `luau-analyze`로 문법과 타입을 검사한다. 실행 파일을 CI에서 내려받아야 하고(버전과 해시 고정 필요) 새 공급망 항목이 생긴다

X) Other (please describe after [Answer]: tag below)

추천: A. 모듈이 작고 Studio에서 실행해 보는 것이 더 확실한 검사다. 코드가 커지는 U5에서 다시 정할 수 있다.

[Answer]: A
