# U5 디테일 — NFR Requirements

근거: U5 NFR Requirements 계획서 답변 Q1~Q6(A A A A A A, 상시 승인에 따라 Claude가 추천안으로 답함), 기본값 N-U5-1~11, U5 Functional Design(승인), 가능성 시험 S-7·S-8·S-10(2026-10-13), U1~U4의 NFR 결정(이어서 적용).
실행 환경은 U1~U4와 같다(사용자 Mac, `uv run`, SQLite). Studio는 내장 MCP 서버로 연결한다. U5에는 비밀값이 없다.

## 1. 확장성
- **U5-NFR-S1** 첫 칸 몸체 약 111동, 항목 약 6,000개, 간판 약 300개가 목표다. 나머지 두 칸(V-World 172·68건)은 같은 규칙으로 만들고 3칸 합계 약 17,000부품을 예상한다(U2-NFR-S3 상한 30,000 안).
- **U5-NFR-S2** 생성·세부 판단·내보내기는 칸 단위다(`details/<칸ID>.json` 칸마다 파일 하나). 처리 시간은 건물 수와 도로 길이에 비례한다.
- **U5-NFR-S3 판단 비용(참고값)** 묶음 이미지 한 장은 이미지 입력 약 1,000토큰이고 첫 칸 116장은 Functional Design 중에 99장까지 기록했다(건당 수십 초).

## 2. 성능
- **U5-NFR-P1 Python 시간** 첫 칸 `build_luau.py` 30초 이내(다중 박스·가림·교차점·슬롯 계산 포함), `details.py pending` 10초 이내, `record` 2초 이내, 세부 합치기는 건물마다 독립이라 선형이다.
- **U5-NFR-P2 Studio 호출 (Q2=A)** `chunk_size` 80, 경고선 15 KB로 시작한다(호출당 약 11 KB, 첫 칸 약 75회). S-11에서 250항목(약 35 KB) 덩어리의 `Builder.add` 시간을 재어 100 ms 미만이면 250 / 40 KB로 올린다(약 24회/칸). 한 호출은 U2-NFR-P2의 1초 안이어야 한다.
- **U5-NFR-P3 걸을 때 프레임 수 (NFR-1, Q1=A)** U2 기준 그대로: 걷는 동안 **평균 ≥ 60 FPS, 순간 최저 ≥ 30 FPS, 1초 넘는 멈춤 없음**(Studio 창 앞). 첫 칸(약 6,000부품)에서 재고 3칸에서 최종 확인한다. 미달이면 이 순서로 깎는다: ① `window_faces = "front"`(창 약 −25%) ② `car_spacing_m` 8 → 12 ③ `tree_spacing_m` 7 → 10 ④ 그다음에야 `StreamingEnabled`(반경은 3칸 폭 약 2,000 stud보다 크게, 속성 창에서). 측정은 U4 방식(RenderStepped 프레임 시간, 5초 정지 + 걷기 60초)이고 `rbx-perf-profiling` 스킬로 GPU/CPU 어느 쪽인지 본다.
- **U5-NFR-P4 간판 글리프** `MaxDistance` 띠간판 300, 층별·돌출·현판 200, 옥상 400으로 한 화면의 간판을 묶는다. S-10에서 길주로 상가 앞 캡처로 60 FPS를 확인하고 미달이면 150으로.
- **U5-NFR-P5 창 재질** S-9에서 불투명 `Glass`와 `SmoothPlastic`(반사율 0.25)의 프레임 시간을 비교해 1.1배 이내면 어느 쪽이든 쓴다(기본 `SmoothPlastic`).

## 3. 가용성과 복구
- **U5-NFR-A1** 복구 목표는 RTO/RPO 수 시간(요구사항). 되돌릴 수 없는 것은 `details`(판단)와 `Manual` 학교다.
- **U5-NFR-A2 커밋 시점 (Q3=A)** 세부 판단을 다 기록했을 때 한 번 커밋·푸시, Build and Test에서는 묶음(생성·검증·Manual·측정)마다 커밋·푸시. `details/<칸ID>.json`은 변경 직후 갱신된다(U4-NFR-A2 방식).
- **U5-NFR-A3 Studio 맵 (BR-15.1)** 첫 U5 생성 전과 Manual 학교 작업 직후에 `.rbxl` 복사본(사용자). 사용자가 자리에 없으면 Claude가 Studio의 "Roblox에 저장"(키 입력 도구, Cmd+S)으로 클라우드 Version History에 남기고 기록에 적는다.
- **U5-NFR-A4 복구 런북 추가** R-16 DB를 잃었다: S1 → `overrides.py import` → `details.py import`(S-16 연습). R-17 세부를 잘못 기록했다: 같은 건물을 `record`로 다시 기록. R-18 Manual 학교가 사라졌다: Version History 또는 `.rbxl` 복사본.
- **U5-NFR-A5 생성 파일** `data/build/<칸ID>/`는 DB에서 언제든 다시 만들 수 있어서 백업하지 않는다.

## 4. 보안
- **U5-NFR-SEC1 비밀값** 없음. 외부 호출 없음(Studio MCP는 로컬).
- **U5-NFR-SEC2 입력 검증 (SECURITY-05)** 세부 `record`·`import`는 BR-7.4·7.5의 열거된 검증을 전부 통과해야 쓴다(하나라도 틀리면 아무것도 쓰지 않음). 간판 글자는 `SIGN_TEXT`(BR-10.4), 그 밖의 모든 글자는 U2 `SAFE_TEXT`, 재질·모양·색 이름은 상수 집합. 설정 새 키는 범위 검증(BR-14.9).
- **U5-NFR-SEC3 Studio로 가는 값 (코드 주입 방지)** `note`는 Studio로 가지 않는다. 가는 것은 코드 단어, 숫자, 그리고 `SIGN_TEXT`를 통과한 간판 글자뿐이며 `Builder.luau`는 받은 문자열을 코드로 실행하지 않는다(`label.Text`에만 넣는다).
- **U5-NFR-SEC4 Manual 스크립트의 권한 (SECURITY-11)** `Workspace/Manual/School` 아래에만 `Instance.new`하고 `Destroy`·`ClearAllChildren`을 부르지 않는다(BR-12.2). Builder가 지우는 것은 U2대로 `Auto/<칸ID>` 하나뿐이다.
- **U5-NFR-SEC5 사진과 개인 정보 (NFR-4)** 세부 판단 때 묶음 이미지가 대화로 전송된다(U4와 같다). 이미지는 `captures/`(git 제외)에만 있고 어디에도 올리지 않는다. `note`·간판 이름·Studio 속성에 사람·번호판·실제 상호를 쓰지 않는다(BR-7.6, BR-10.3).
- **U5-NFR-SEC6 공급망 (SECURITY-10, Q5=A)** 새 의존성 없음. `details.py`는 의존성 없음(`overrides.py`와 같다), `build_luau.py`는 `h3==4.5.0`, `shapely==2.2.0` 그대로. `tests/test_versions.py`에 `details.py`·`details_rules.py`가 표준 라이브러리와 자체 모듈만 쓰는지 검사를 더한다.

## 5. 신뢰성
- **U5-NFR-R1 원자성** `record`·`import`는 한 트랜잭션. 내보내기는 임시 파일 뒤 `os.replace`. 파일 쓰기가 실패하면 크게 알리고 DB 변경은 유지된다(U4 BR-8.4).
- **U5-NFR-R2 같은 결과** 같은 DB 상태에서 덩어리 파일·manifest·내보내기 파일이 글자까지 같다(P5-1, P5-16). 변화는 `zlib.crc32`뿐이다.
- **U5-NFR-R3 판단의 비결정성 (Q6=A)** 사진 판단은 Claude의 의견이라 같은 사진을 다시 봐도 같다는 보장이 없다. NFR-3은 판단을 `details`에 저장하고 그 뒤의 계산이 같은 입력에서 같은 결과를 내는 것으로 지킨다. `--redo` 없이는 바꾸지 않고 같은 내용 재기록은 시각까지 무변화다.
- **U5-NFR-R4 실행 기록** `build_luau.py`는 `collection_runs`에 `unit = 'C6'`으로 새 수치(`items_<kind>`, `buildings_built`, `duplicates_dropped`, `signs`, `labels`, `parts_total`)를, `details.py`는 `'C7'`로 건수만 남긴다. `note`는 로그에 쓰지 않는다.
- **U5-NFR-R5 호출 실패** 덩어리 호출이 실패하거나 연결이 끊기면 그 칸을 `begin`부터 다시 한다(U2-NFR-R1).

## 6. 유지보수성과 테스트
- **U5-NFR-M1 테스트 도구** U1과 같다(`pytest` + `Hypothesis`, 실패 시 시드 출력, CI에서 시드 고정).
- **U5-NFR-M2 테스트 범위** 속성 P5-1~P5-19를 속성 기반 테스트로 만든다. 생성기(세부 행, 원형별 건물, 교차하는 도로망, 간판 글자)는 `tests/generators.py`의 `# --- U5 details ---` 절에 한 번만 정의한다(PBT-07). 세부 명령은 합성 DB로 예시 테스트. 승인 때 시드 1, 7, 42, 2026, 99999와 코드 망가뜨리기 ≥ 12가지.
- **U5-NFR-M3 Luau (Q4=A)** CI에서 Luau를 검사하지 않는다. `tests/test_versions.py`의 금지 토큰·`:Destroy()` 한 곳 검사를 유지하고, Studio에서 `MCP_Test` 덩어리(S-7 다시 실행)와 `verify`(kind별 개수, `labels`, Manual 미사용 ID)로 매번 확인한다.
- **U5-NFR-M4 모듈 분리** 입출력 없는 규칙은 `src/details_rules.py`(세부 합치기, 이름 생성, 글자 검사, 팔레트·치수 상수)와 `src/layout.py`(기하)에 두고, `details.py`·`build_luau.py`는 DB·파일·명령줄만 맡는다. `studio/Builder.luau`는 계산하지 않는다(U2 BR-7.5).
- **U5-NFR-M5 설정값** `config.toml`에 `pole_spacing_m`, `lamp_spacing_m`, `tree_spacing_m`, `car_spacing_m`, `school_zone_m`, `roof_pitch_deg`, `window_faces`, `details_dir`를 추가하고 `chunk_size` 기본값을 80으로 바꾼다. 범위 검증은 `common.py`에서(U2-NFR-M5 방식).
- **U5-NFR-M6 버전 일치 검사** `tests/test_versions.py`가 `details.py`의 인라인 의존성이 비어 있는지와 `details_rules.py`가 표준 라이브러리만 쓰는지 확인한다.

## 7. 사용성
- **U5-NFR-U1 명령줄** `uv run src/details.py pending|record|list|export|import`, `uv run src/build_luau.py --cells <칸ID>`는 그대로. 끝에 건수 요약을 인쇄한다. `CLAUDE.md`에 명령을 추가한다.
- **U5-NFR-U2 세부 판단 진행** Claude가 직접 묶음 이미지를 보고 10개씩 기록한다(하위 에이전트 없음). 기록한 건물은 목록에서 빠지므로 중간에 멈추고 이어갈 수 있다.
- **U5-NFR-U3 Studio 창** 측정과 캡처 동안 Studio 창을 앞에 둔다(사용자 몫). 부재 시 `osascript`로 Studio 활성화를 시도하고 안 되면 기록에 남긴다.

## 8. 외부 연동과 저장
- **U5-NFR-X1 Studio MCP** 쓰는 도구: `execute_luau`(덩어리, Manual, 측정), `screen_capture`(`camera_position`, `look_at_position`을 항상 줌), `search_game_tree`·`inspect_instance`(확인), `rbx-perf-profiling` 스킬(선택), `user_keyboard_input`(부재 시 저장). `generate_*`·`insert_asset`·`upload_image`는 쓰지 않는다(BR-14.10).
- **U5-NFR-X2 저장** `details/<칸ID>.json`(git 포함), `data/build/<칸ID>/`(git 제외), `captures/`(로컬만).

## 확장 규칙 준수 요약

### Security Baseline (이 단계)

| 규칙 | 상태 | 근거 |
|---|---|---|
| SECURITY-01 | 전송 중 N/A(로컬). 저장 시 U1의 문서화된 예외 | 비밀값·사진이 저장소에 없다 |
| SECURITY-02, 04, 06, 07, 08, 14 | N/A | 서버·웹·접근 제어·경보 없음 |
| SECURITY-03 | 준수 (U1 예외) | JSON 로그, `note` 제외(R4) |
| SECURITY-05 | 준수 | SEC2 |
| SECURITY-09, 11, 15 | 준수 | 한 건 틀리면 전체 거부(R1), Manual 권한 범위(SEC4), 최상위 오류 처리는 U1의 `run_cli` |
| SECURITY-10 | 준수 | 새 의존성 없음(SEC6) |
| SECURITY-12 | 준수 | 키 없음 |
| SECURITY-13 | 준수 | 임시 파일 + 바꿔치기, 불러오기는 전체 검증 뒤에만 |

### Resiliency Baseline (이 단계)

| 규칙 | 상태 | 근거 |
|---|---|---|
| RESILIENCY-01, 02 | 준수 | RTO/RPO 수 시간 |
| RESILIENCY-03, 04, 14, 15 | 준수 | U1 NFR Design 결정 승계 |
| RESILIENCY-05~10 | N/A | 배포 서비스 없음 |
| RESILIENCY-11, 13 | 준수 | 런북 R-16~R-18, 복구 연습 S-16 |
| RESILIENCY-12 | 준수 | `details/*.json` 즉시 갱신 + git, `.rbxl` 복사본 두 시점(A3) |

### Property-Based Testing

| 규칙 | 상태 | 근거 |
|---|---|---|
| PBT-01 | 준수 | 기능 설계 P5-1~P5-19와 속성 없는 구성요소 목록 |
| PBT-09 | 준수 | `pytest` + `Hypothesis` 그대로 |
| PBT-07, 08 | 코드 생성과 Build and Test에서 확인 | 생성기는 `generators.py`, 시드 고정 |

차단 항목은 없다. 새 예외도 없다.
