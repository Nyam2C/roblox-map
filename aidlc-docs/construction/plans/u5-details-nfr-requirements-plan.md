# U5 디테일 — NFR Requirements Plan

대상: U5 기능 설계(승인, 2026-10-13)의 비기능 요구사항과 기술 선택. 이전 결정(U1~U4 NFR)을 이어서 적용하고 U5에서 달라지는 것만 정한다. 상시 승인(사용자, 2026-10-13: "자동승인으로 하고 질문있으면 권고하고 u5 끝까지 진행해")에 따라 아래 질문은 Claude가 추천안으로 답하고 그 사실을 `audit.md`에 적는다.

## 계획 (체크리스트)

- [x] U5 기능 설계 읽기(규칙 BR-1~17, 속성 P5-1~19, Studio 확인 S-7~S-16)와 U2·U4 NFR 문서(이어서 적용할 것) 읽기
- [x] 가능성 시험: S-7(쐐기 축), S-8(`Brick` 타일 크기), S-10(한글 간판 1장)은 2026-10-13에 끝났고 결과가 `audit.md`에 있다(모두 설계대로)
- [x] 아래 질문 6개에 답(추천안, 상시 승인)
- [x] 답변 분석: 모호함 없음(전부 추천안)
- [x] `construction/u5-details/nfr-requirements/nfr-requirements.md` 생성
- [x] `construction/u5-details/nfr-requirements/tech-stack-decisions.md` 생성
- [x] 완료 메시지 제시, 승인(상시 승인)

## Question 1 — 프레임 수 기준과 조절 사다리 (NFR-1)
첫 칸이 약 163부품에서 약 6,000부품으로 늘고 3칸은 약 17,000부품이 된다.

A) U2 기준 그대로(걷는 동안 평균 ≥ 60 FPS, 순간 최저 ≥ 30, 1초 넘는 멈춤 없음, Studio 창 앞). 미달이면 정해진 순서로 깎는다: ① `window_faces = "front"` ② `car_spacing_m` 8 → 12 ③ `tree_spacing_m` 7 → 10 ④ 그다음에야 `StreamingEnabled`(반경은 3칸 폭 약 2,000 stud보다 크게). 첫 칸에서 재고 3칸에서 최종 확인

B) 기준을 평균 ≥ 45로 낮춘다(부품을 깎지 않아도 된다)

C) 기준은 A, 사다리 대신 처음부터 `StreamingEnabled`

X) Other

추천: A.

[Answer]: A

## Question 2 — 덩어리 크기와 Studio 호출
항목 리터럴은 평균 약 140 B다. 첫 칸 약 6,000항목.

A) `chunk_size` 80, 경고선 15 KB로 시작(호출 약 75회/칸, 호출당 약 11 KB). S-11에서 250항목(약 35 KB) 덩어리의 `Builder.add` 시간을 재어 100 ms 미만이면 250 / 40 KB로 올린다(약 24회/칸)

B) U2의 50 / 10 KB 유지(약 120회/칸)

X) Other

추천: A.

[Answer]: A

## Question 3 — 세부 판단과 Manual 작업의 커밋 시점 (NFR-6)
되돌릴 수 없는 것은 `details`(판단 116건)와 `Manual` 학교다.

A) 세부 판단을 다 기록했을 때 한 번 커밋·푸시, Build and Test에서는 묶음(생성·검증·Manual·측정)마다 커밋·푸시. `details/<칸ID>.json`은 변경 직후 갱신된다(U4-NFR-A2 방식). `.rbxl` 복사본은 사용자 몫이고 사용자가 자리에 없으면 Claude가 Studio의 "Roblox에 저장"(키 입력 도구, Cmd+S)으로 클라우드 Version History에 남긴다

B) 30건마다 커밋

X) Other

추천: A.

[Answer]: A

## Question 4 — Luau 검사
`Builder.luau`가 약 100줄 늘어난다(모양·재질·반사율·소유자·그림자·충돌·간판 GUI·kind별 Skipped·verify).

A) U2·U4와 같다: CI에서 Luau를 검사하지 않고 `tests/test_versions.py`의 금지 토큰·`:Destroy()` 한 곳 검사를 유지하며, Studio에서 `MCP_Test` 덩어리(S-7 다시 실행)와 `verify`로 확인한다

B) CI에 `luau-analyze`를 더한다(새 도구, 핀 고정 필요)

X) Other

추천: A.

[Answer]: A

## Question 5 — 의존성
다중 박스 절단은 shapely의 `split`·`minimum_rotated_rectangle`로 충분하다.

A) 새 의존성 없음. `details.py`는 표준 라이브러리와 자체 모듈만(`overrides.py`와 같다), `details_rules.py`는 표준 라이브러리만, `layout.py`는 지금의 `h3`·`shapely` 그대로. `tests/requirements.txt`도 그대로

B) 직각 다각형 분해 라이브러리를 더한다

X) Other

추천: A.

[Answer]: A

## Question 6 — 세부 판단의 재현성 표시
사진 판단은 Claude의 의견이라 같은 사진을 다시 봐도 같다는 보장이 없다(U4 N-U4-10과 같다).

A) U4와 같이: 판단을 저장하고 그 뒤 계산만 결정적이다. `pending --redo` 없이는 바꾸지 않고, 같은 내용 재기록은 시각까지 무변화다. 판단 시점에 쓴 어휘(BR-7.1)는 바꾸지 않는다

B) 판단 2회 교차 확인(불일치만 다시 본다): 시간이 2배

X) Other

추천: A.

[Answer]: A

## 기본값 (질문은 안 함)

| # | 내용 |
|---|---|
| N-U5-1 | 실행 환경·도구는 U1~U4와 같다(사용자 Mac, `uv run`, SQLite, Studio 내장 MCP). 비밀값 없음 |
| N-U5-2 | Python 시간: 첫 칸 `build_luau.py` 30초 이내(다중 박스·가림·교차점 계산 포함), `details.py pending` 10초 이내, `record` 2초 이내 |
| N-U5-3 | Studio 호출: 덩어리 하나 100 ms 이내(S-11에서 측정), 호출 사이에 Studio가 멈추지 않는다 |
| N-U5-4 | 간판 글리프: `MaxDistance` 300/200/400으로 한 화면의 간판을 제한한다. S-10에서 길주로 캡처로 60 FPS 확인 |
| N-U5-5 | 보안: `SIGN_TEXT`(간판 글자), `SAFE_TEXT`(그 밖), 세부 `record`·`import` 전체 검증, Manual 스크립트는 `Workspace/Manual/School` 아래에만 생성·`Destroy` 금지, `.env` 없음, `pip-audit` 유지 |
| N-U5-6 | 신뢰성: `record`·`import`는 한 트랜잭션, 내보내기는 임시 파일 + 바꿔치기, 같은 입력 같은 덩어리(P5-1), 실행 기록 `collection_runs`(`C6`에 새 수치, 세부는 `C7`) |
| N-U5-7 | 유지보수: 순수 모듈 `details_rules.py`·`layout.py`, CLI `details.py`; 속성 P5-1~19를 Hypothesis로, 생성기는 `tests/generators.py`의 `# --- U5 details ---` 절; 시드 1, 7, 42, 2026, 99999; 코드 망가뜨리기 ≥ 12가지; `tests/test_versions.py`에 `details.py` 의존성 없음 검사 추가 |
| N-U5-8 | 설정 키 8개(BR-14.9)는 `DEFAULTS`·`RANGES`·`config.toml`·틀린 예시·manifest `config`에 함께 |
| N-U5-9 | 사용성: `uv run src/details.py pending|record|list|export|import --cells <칸ID>`, `build_luau.py`는 그대로. 끝에 건수 요약. `CLAUDE.md`에 명령 추가 |
| N-U5-10 | Studio MCP: `execute_luau`(덩어리, Manual, 측정), `screen_capture`(항상 카메라 인자), `search_game_tree`·`inspect_instance`(확인), `rbx-perf-profiling` 스킬 또는 RenderStepped 측정(U4 방식), `user_keyboard_input`(사용자 부재 시 저장). Studio 창을 앞에 두는 일은 사용자 몫이고 부재 시 `osascript`로 활성화를 시도한다 |
| N-U5-11 | 저장: `details/<칸ID>.json`(git 포함), `data/build/<칸ID>/`(git 제외), `captures/`(로컬만, NFR-4) |
