# U4 판단·보정 — NFR Requirements

근거: U4 NFR Requirements 계획서 답변 Q1~Q3(A A A), 기본값 N-U4-1~N-U4-15, Studio 카메라 캡처 가능성 시험 결과(2026-10-13), U4 Functional Design(승인), U1~U3의 NFR 결정(이어서 적용).
실행 환경은 U1~U3과 같다(사용자 Mac, `uv run`, SQLite). Studio는 내장 MCP 서버로 연결한다. U4에는 비밀값이 없다.

## 1. 확장성
- **U4-NFR-S1** 첫 칸 건물 122개, 비교 쌍 약 136개(건물 114개 × 1 + 면 사진을 쓴 학교 건물 8개의 22장)가 목표다. 나머지 두 칸은 첫 칸을 끝낸 뒤 같은 흐름으로 한다(D-U4-13).
- **U4-NFR-S2** 판단·보정·내보내기는 칸 단위다(`overrides/<칸ID>.json` 칸마다 파일 하나). 건물이 늘면 처리 시간이 건물 수에 비례해서 늘어난다(이미지 묶음, 합치기 모두 건물마다 독립).
- **U4-NFR-S3 판단 비용(참고값)** 눈가림 묶음 이미지 한 장은 이미지 입력 약 1,000토큰이다. 칸 하나는 이미지 입력 십수만 토큰에 기록 출력이 더해진다. 칸이 늘면 비용도 칸 수에 비례한다.

## 2. 성능
- **U4-NFR-P1 묶음 이미지 만들기** 첫 칸 122개를 10초 이내(시험에서 크롭 읽기·축소·붙이기가 1.8초).
- **U4-NFR-P2 비교 쌍 합성** 한 쌍 1초 이내(시험에서 22 ms).
- **U4-NFR-P3 최종값 합치기와 보고** 칸 하나의 `effective_buildings`는 1초 이내, `report`는 2초 이내(DB 행 수백 개 규모).
- **U4-NFR-P4 판단과 비교의 소요** 사진을 보고 판단하는 일(Q1=A)과 Studio 캡처 호출이 시간을 차지한다. 처음 한 묶음(10개 판단, 12쌍 캡처)으로 걸린 시간을 재서 알려 주고, 그것으로 나머지를 예측한다. 상한 수치는 정하지 않는다.
- **U4-NFR-P5 걸을 때 프레임 수 (NFR-1)** U2 기준 그대로다(평균 60 FPS 이상, 순간 최저 30 FPS 이상, 1초 이상 끊기지 않을 것). U4는 부품 수를 늘리지 않고 색과 속성만 바꾸므로 Build and Test에서 다시 한 번 잰다.
- **U4-NFR-P6 Studio 캡처 (N-U4-4)** 쌍마다 `screen_capture` 한 번이다. 시야각은 세로 83.58°(가로 100°, 4:3)로 한 번 정하고, 크롭의 시야각 `f`가 더 좁으면 캡처를 가운데에서 `tan(f/2) ÷ tan(50°)` 비율로 잘라 맞춘다. 캡처는 4:3으로 가운데를 자른다.

## 3. 가용성과 복구
- **U4-NFR-A1** 복구 목표는 RTO/RPO 수 시간(요구사항). 되돌릴 수 없는 것은 `estimates`(판단)와 `overrides`(보정)다.
- **U4-NFR-A2 커밋 시점 (Q3=A)** 판단 122개를 다 기록했을 때 한 번, 그 뒤 비교 3묶음(쌍 약 36개)마다 내가 "지금까지 커밋할까?"를 제안하고 사용자가 허락하면 커밋·푸시한다. 내보내기 파일(`overrides/<칸ID>.json`)은 매 변경 직후 갱신되지만 DB와 같은 디스크이므로 git에 올려야 보호된다(RPO 수 시간).
- **U4-NFR-A3 DB 백업** U1의 백업(칸 재수집 직전)은 그대로다. 판단·보정은 변경마다 내보내기 파일로 따로 보호되므로 별도 백업을 추가하지 않는다.
- **U4-NFR-A4 Studio 맵** 이 유닛은 `Auto/<칸ID>`만 다시 만들고 `Manual`은 읽기만 한다(`Manual`은 지금 비어 있다). 추가 `.rbxl` 복사본은 `Manual` 작업이 쌓이는 U5부터 필요하다(U2 NFR A2).
- **U4-NFR-A5 복구 런북 추가** (U1 R-1~R-6, U3 R-7~R-9, U2 R-10~R-12에 이어서):
  - **R-13 DB를 잃었다**: 새 DB에 S1(`cells.py`, `register.py`)을 다시 돌리고 `overrides.py import`를 한다(보정과 판단이 같이 돌아온다, BR-8.6). 사진은 U3를 다시 돌려야 한다.
  - **R-14 판단을 잘못 기록했다**: 같은 건물을 `estimate.py record`로 다시 기록한다(덮어쓴다).
  - **R-15 보정을 잘못 넣었다**: `overrides.py unset`이나 `set`으로 되돌린다. git 이력에서도 되돌릴 수 있다.
- **U4-NFR-A6 생성 파일** `captures/<칸ID>/sheets/`, `captures/<칸ID>/review/`, `data/build/<칸ID>/review.json`은 DB와 사진에서 언제든 다시 만들 수 있어서 백업하지 않는다(git 제외).

## 4. 보안
- **U4-NFR-SEC1 비밀값** 키나 로그인 정보를 쓰지 않는다. 외부 호출이 없다(Studio MCP는 로컬 연결).
- **U4-NFR-SEC2 입력 검증 (SECURITY-05)** 판단·보정 값은 기능 설계 BR-2.2와 BR-6.1~6.3으로 검증한다. 건물 ID는 허용 문자(영문자, 숫자, `:` `#` `_` `-` `.`)만 통과시키고 파일 이름에는 `:`을 `_`로 바꿔서 쓴다(경로 이동 문자 불가). 불러오기 파일은 5 MB 이하, 알려진 키만, 형식 검증을 통과해야 한다(하나라도 틀리면 아무것도 쓰지 않는다, BR-8.5). 합성할 캡처 파일은 일반 파일이고 20 MB 이하, 픽셀 수 5,000만 이하(Pillow의 폭탄 이미지 한도를 명시적으로 설정)다.
- **U4-NFR-SEC3 Studio로 가는 값 (코드 주입 방지)** `note`, `reason` 같은 자유 문장은 Studio로 보내지 않는다. Studio 속성으로 가는 것은 코드 단어(근거 코드, 팔레트 키, 확인 목록 사유)와 숫자뿐이며 U2의 허용 문자 검사(SEC2)를 거친다. `Builder.luau`는 받은 문자열을 코드로 실행하지 않는다.
- **U4-NFR-SEC4 사진과 개인 정보 (NFR-4)** 판단하는 동안 내가 묶음 이미지를 보는 순간 그 이미지는 대화로 전송된다(기능 설계에서 정한 방식, FR-8). 이미지는 `captures/`(git 제외)에만 있고 저장소, Artifact, 외부 서비스에 올리지 않는다. 묶음 타일은 512×384로 줄여서 원본보다 덜 선명하다. 추가 가림 처리는 하지 않는다. `note`와 `reason`은 public 저장소에 올라가므로 사람·번호판·얼굴·상호 같은 개인 정보를 쓰지 않는다(BR-8.8).
- **U4-NFR-SEC5 Studio 변경 범위** 비교 쌍을 만들 때 바뀌는 것은 뷰포트 카메라뿐이고 시작 전 값을 읽어 두었다가 끝나면 되돌린다(N-U4-5). `Auto/<칸ID>`는 U2의 재생성으로만 바뀌고 `Manual`은 읽기만 한다.
- **U4-NFR-SEC6 MCP** Studio 내장 MCP 서버는 열린 맵을 읽고 수정할 수 있다. 신뢰하는 클라이언트(이 Claude 세션)만 연결한다.
- **U4-NFR-SEC7 공급망 (SECURITY-10)** 새 의존성이 없다. `estimate.py`는 `pillow==12.3.0`, `h3==4.5.0`, `shapely==2.2.0`을 정확한 버전으로 적고, `tests/test_versions.py`와 CI의 `pip-audit`가 점검한다.

## 5. 신뢰성
- **U4-NFR-R1 원자성** DB 변경은 한 트랜잭션이고 한 건이라도 검증에 실패하면 호출 전체가 거부된다(BR-2.2, BR-6.3). 내보내기 파일은 임시 파일에 쓴 뒤 `os.replace`로 바꿔치기한다. 파일 쓰기가 실패하면 크게 알리고 DB 변경은 유지된다(BR-8.4).
- **U4-NFR-R2 같은 결과** 같은 DB 상태에서 최종값, 확인 목록, 비교 묶음, 내보내기 파일, U2 Luau 덩어리가 글자까지 같다. 입력 행의 순서에 상관없다(P4-8, P4-11, BR-9.4).
- **U4-NFR-R3 판단의 비결정성 (N-U4-10)** 사진 판단은 내 의견이라 같은 사진을 다시 봐도 같은 값이 나온다고 보장할 수 없다. NFR-3은 판단을 `estimates`에 저장하고 그 뒤의 계산이 같은 입력에서 같은 결과를 내는 것으로 지킨다. 재실행은 `--redo`를 주지 않는 한 판단을 바꾸지 않는다.
- **U4-NFR-R4 눈가림 통계 (N-U4-9)** `report`는 설정의 `blind_broken` 목록(지금 `gis:11081057` 하나)에 있는 건물을 사진-대장 일치율에서 빼고 몇 개를 뺐는지 알린다.
- **U4-NFR-R5 캡처 규칙** `screen_capture`는 항상 `camera_position`과 `look_at_position`을 준다(인자 없는 캡처는 다른 시점이 찍혔다). 캡처 파일을 못 읽거나 4:3보다 좁으면 그 쌍을 건너뛰고 이유를 알린다.
- **U4-NFR-R6 실행 기록** `estimate.py`는 `collection_runs`에 `unit = 'C4'`, `overrides.py`는 `'C5'`로 건수만 남기고 JSON 로그를 쓴다. `note`와 `reason`은 로그에 쓰지 않는다.

## 6. 유지보수성과 테스트
- **U4-NFR-M1 테스트 도구** U1과 같다(`pytest` + `Hypothesis`, 실패 시 시드 출력, CI에서 시드 고정).
- **U4-NFR-M2 테스트 범위** 속성 P4-1~P4-16을 속성 기반 테스트로 만든다. 생성기(건물, 판단, 보정)는 `tests/generators.py`에 한 번만 정의한다(PBT-07). 묶음 이미지와 쌍 합성은 만든 이미지로 예시 기반 테스트한다.
- **U4-NFR-M3 Luau** `Builder.luau` 변경(색, 속성 `HeightBasis`, `FloorsBasis`, `WallColor`, `Review`)은 U2와 같이 CI에서 검사하지 않고 Studio에서 `verify`와 속성 확인으로 본다(U2 NFR Q4=A).
- **U4-NFR-M4 모듈 분리 (N-U4-2)** 최종값 합치기, 상태 분류, 검증, 내보내기 형식, 비교 묶음 계획, 카메라 값은 입출력 없는 모듈에 둔다. `estimate.py`, `overrides.py`는 DB, 파일, 명령줄만 맡는다.
- **U4-NFR-M5 설정값** `config.toml`에 `floor_height_min_m`(2.5), `floor_height_max_m`(5.0), `review_batch_size`(12), `sheet_tile_w`(512), `sheet_tile_h`(384), `sheet_jpeg_quality`(85), 벽 색표, `blind_broken`을 추가하고 범위 검증은 `common.py`에서 한다.
- **U4-NFR-M6 버전 일치 검사** `tests/test_versions.py`가 `estimate.py`의 인라인 고정이 `==`인지, `tests/requirements.txt`와 겹치는 패키지(`h3`, `shapely`, `pillow`)의 버전이 같은지 자동으로 확인한다.

## 7. 사용성
- **U4-NFR-U1 명령줄 (N-U4-15)** `uv run src/estimate.py pending|record|report|plan --cells <칸 ID>`, `uv run src/overrides.py set|unset|list|export|import`. 끝에 건수 요약을 인쇄한다. `record`는 JSON 파일이나 표준 입력으로 판단 목록을 받는다.
- **U4-NFR-U2 판단 진행 (Q1=A)** 이 세션에서 내가 직접 순서대로 판단한다. 10개씩 나눠 보고 기록하며 하위 에이전트를 쓰지 않는다. 기준(층수 세는 규칙, 확신도)이 하나라서 일치율이 판단 기준 하나에 대한 숫자가 된다. 기록한 건물은 목록에서 빠지므로 중간에 멈추고 이어갈 수 있다(BR-1.5).
- **U4-NFR-U3 비교 쌍 보기 (Q2=A)** 건물마다 파일 한 장을 만든다(1280×480: 왼쪽 Studio 캡처, 오른쪽 크롭, 위에 건물 ID와 최종 층수·높이와 근거, 벽 색, 확인 목록 사유). `captures/<칸ID>/review/<건물 ID>__<순위>.jpg`에 두고 묶음(12개)마다 파일 링크를 준다. 이 앱의 파일 창으로 열어서 본다. 묶음 이미지(6쌍)는 만들지 않는다.
- **U4-NFR-U4 Studio 창** 비교 쌍을 만드는 동안 사용자는 Studio의 뷰포트를 건드리지 않고 창을 앞에 둔다. 시작 전에 알린다(N-U4-5).

## 8. 외부 연동과 저장
- **U4-NFR-X1 Studio MCP** 쓰는 도구: `screen_capture`(`camera_position`, `look_at_position`을 항상 줌), `execute_luau`(편집 모드: 시야각 설정, 카메라 값 읽기·되돌리기), `search_game_tree`와 `inspect_instance`(Studio 속성 확인), 칸 재생성은 U2의 `Builder`로 한다. 시험으로 캡처, 시야각 반영, 캡처 파일 저장을 확인했다(Studio 편집 모드).
- **U4-NFR-X2 저장** `captures/<칸ID>/sheets/`, `captures/<칸ID>/review/`(건물별 파일), `data/build/<칸ID>/review.json`은 git 제외다. `overrides/<칸ID>.json`(보정과 판단)은 git에 포함한다.

## 확장 규칙 준수 요약

### Security Baseline (이 단계)

| 규칙 | 상태 | 근거 |
|---|---|---|
| SECURITY-01 | 전송 중: N/A(로컬). 저장 시: U1과 같은 문서화된 예외(이 Mac의 로컬 파일, 디스크 암호화는 OS 설정) | 판단·보정 파일에 사진이나 비밀값이 없다 |
| SECURITY-02, 04, 06, 07, 08, 14 | N/A | 서버, 웹, 접근 제어, 경보 없음 |
| SECURITY-03 | 준수 (U1과 같은 예외) | JSON 로그, 비밀값과 자유 문장 제외(R6), 중앙 로그는 해당 없음 |
| SECURITY-05 | 준수 | 판단·보정·불러오기 파일 검증, 건물 ID 허용 문자, 캡처 이미지 크기·픽셀 한도(SEC2), Studio로 가는 값 제한(SEC3) |
| SECURITY-09, 11, 15 | 준수 | 한 건이라도 틀리면 전체 거부(R1), 최종 값은 항상 0보다 큰 높이 등 안전한 기본값, 최상위 오류 처리는 U1의 `run_cli`, 카메라 외 Studio 변경 없음(SEC5) |
| SECURITY-10 | 준수 | 새 의존성 없음, 기존 고정과 `pip-audit` 유지(SEC7) |
| SECURITY-12 | 준수 | 키 없음 |
| SECURITY-13 | 준수 | 내보내기 파일은 임시 파일 + 바꿔치기, 불러오기는 전체 검증 뒤에만 쓴다(R1, BR-8.5) |

차단 항목은 없다. 새 예외도 없다(SECURITY-01 저장 시 암호화는 U1에서 이미 확인받은 예외).

### Resiliency Baseline (이 단계)

| 규칙 | 상태 | 근거 |
|---|---|---|
| RESILIENCY-01, 02 | 준수 | RTO/RPO 수 시간 |
| RESILIENCY-03, 04, 14, 15 | 준수 | U1 NFR Design에서 사용자가 정한 방식을 이어서 쓴다(변경 관리, GitHub Actions, 롤백, 복원력 테스트, 사고 대응). RESILIENCY-15는 U1에서 확인받은 예외 그대로 |
| RESILIENCY-05~10 | N/A | 배포된 서비스, 고가용성 없음 |
| RESILIENCY-11, 13 | 준수 | Backup & Restore, 런북 R-13~R-15 추가, 복구 연습(BR-8.6, Build and Test S4-5) |
| RESILIENCY-12 | 준수 | 되돌릴 수 없는 값(판단·보정)은 변경 즉시 내보내기 파일로 쓰고 사용자가 허락하는 시점에 git에 올린다(Q3=A). 사진·묶음·비교 파일·Luau 덩어리는 다시 만들 수 있어서 백업하지 않는다 |

### Property-Based Testing

| 규칙 | 상태 | 근거 |
|---|---|---|
| PBT-01 | 준수 | 기능 설계의 P4-1~P4-16 |
| PBT-09 | 준수 | U1에서 선택한 `pytest` + `Hypothesis` 그대로 |
| PBT-07, 08 | 코드 생성과 Build and Test에서 확인 | 건물, 판단, 보정 생성기를 `tests/generators.py`에 추가한다. 시드는 CI에서 실행 번호로 고정 |
