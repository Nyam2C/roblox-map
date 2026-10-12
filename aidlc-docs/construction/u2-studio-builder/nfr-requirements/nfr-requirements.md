# U2 Studio 생성기 — NFR Requirements

근거: U2 NFR Requirements 계획서 답변 Q1~Q4(A A A A), 기본값 N-U2-1~N-U2-11, 가능성 시험 결과(2026-10-13), U2 Functional Design, U1·U3의 NFR 결정(이어서 적용).
실행 환경은 U1·U3과 같다(사용자 Mac, `uv run`, SQLite). Studio는 내장 MCP 서버로 연결한다. U2에는 비밀값이 없다.

## 1. 확장성
- **U2-NFR-S1** 심원고 3칸이 목표다. 칸 단위로 만들고(`Auto/<칸ID>`), 이웃 칸을 더해도 같은 원점과 스케일을 쓴다(BR-1.1).
- **U2-NFR-S2** 칸이 늘어도 중복이 없다. 도로는 구간 중점이 속한 칸에서만 만들고(BR-3.2), 땅은 이웃 칸과 겹쳐도 같은 높이와 색이라 보이지 않는다(BR-4.3).
- **U2-NFR-S3 부품 수 예산(참고값)** U2 단계에서 칸당 1,000개 이하(첫 칸 예상 약 163개), U5까지 포함해 3칸 합계 30,000개 이하. 플레이 테스트에서 프레임 수를 재서 조정한다.

## 2. 성능
- **U2-NFR-P1 만드는 시간(Python)** 첫 칸의 덩어리 파일과 manifest를 쓰는 데 5초 이내(대부분이 건물 박스 맞춤).
- **U2-NFR-P2 Studio 호출** 호출 한 번은 1초 이내. 시험에서 건물 50개 덩어리가 8 ms였다. 한 호출이 Studio를 멈추지 않게 하려는 기준이다.
- **U2-NFR-P3 덩어리 크기** `chunk_size` 기본 50(호출당 수 KB, 시험한 덩어리는 3.7 KB). 덩어리 파일 하나가 10 KB를 넘으면 `build_luau.py`가 경고하고 `chunk_size`를 줄이라고 안내한다.
- **U2-NFR-P4 걸을 때 프레임 수 (NFR-1, Q1=A)** 사용자 Mac의 Studio 플레이 테스트에서 걷는 동안 **평균 60 FPS 이상, 순간 최저 30 FPS 이상, 1초 이상 끊기지 않을 것**. U2 끝에서는 첫 칸으로, 최종은 U5 끝에서 칸 3개로 확인한다. 측정 방법은 코드 생성에서 정한다.
- **U2-NFR-P5 스트리밍 (Q2=A)** `StreamingEnabled`를 끈다. 부품이 수백~수천 개인 동안은 전부 불러와도 부담이 적고 멀리까지 보인다. U5 이후 부품이 수만 개가 되거나 P4를 못 지키면 다시 정한다. 이 설정은 Claude가 첫 생성 때 한 번 바꾼다(기본 물체를 끄는 것과 같은 때, BR-6.5).

## 3. 가용성과 복구
- **U2-NFR-A1** 복구 목표는 RTO/RPO 수 시간(요구사항). `Auto/<칸ID>`는 언제든 다시 만들 수 있고, 보호할 것은 `Manual`이다.
- **U2-NFR-A2 Studio 맵 백업 (Q3=A)** 첫 생성 전에 **사용자가 `.rbxl` 복사본을 한 번** 만든다(파일 > 다른 이름으로 저장). 그 뒤에는 Studio의 Version History에 맡기고, `Manual` 작업이 쌓인 뒤(U5부터)의 큰 변경 전마다 복사본을 만든다. 첫 생성 전에 이 복사본이 있다는 확인을 받고 시작한다. `.rbxl`은 git에 올리지 않는다(`.gitignore`에 있다).
- **U2-NFR-A3 복구 런북 추가** (U1 R-1~R-6, U3 R-7~R-9에 이어서):
  - **R-10 칸이 반쯤 만들어졌거나 Studio 연결이 끊겼다**: `Auto/<칸ID>`의 `BuildComplete`가 `false`다. 같은 칸을 다시 실행한다(`begin`이 비우고 다시 만든다).
  - **R-11 자동 건물을 잘못 지웠거나 바꿨다**: 같은 칸을 다시 실행한다. `Auto`는 항상 다시 만든다.
  - **R-12 `Manual` 작업이 사라졌다**: Studio의 Version History 또는 `.rbxl` 복사본에서 복구한다. 생성기는 `Manual`을 읽기만 한다.
- **U2-NFR-A4 생성 파일** `data/build/<칸ID>/`는 DB에서 언제든 다시 만들 수 있어서 백업하지 않는다(`data/`는 git 제외).

## 4. 보안
- **U2-NFR-SEC1 비밀값** 키나 로그인 정보를 쓰지 않는다. MCP 연결은 로컬이다.
- **U2-NFR-SEC2 코드 주입 방지(SECURITY-05)** DB의 값(V-World와 OSM에서 온 건물 ID, 도로 ID, `Source`)이 Studio에서 실행되는 코드에 들어간다. 문자열은 허용 문자(영문자, 숫자, `:` `#` `_` `-` `.`)만 통과시키고 Luau 문자열 리터럴로 이스케이프한다. 허용 문자 밖이면 그 항목을 건너뛰고 경고한다. 숫자는 유한한 값만 쓴다. `Builder.luau`는 데이터만 받고 받은 문자열을 코드로 실행하지 않는다(`loadstring` 금지).
- **U2-NFR-SEC3 Studio 변경 범위** `begin`이 지우는 것은 `Auto/<칸ID>` 하나뿐이다. 칸 ID는 H3 형식(15자리 16진수)인지 확인한 뒤에만 쓴다. `Manual`은 `BuildingId` 속성을 읽기만 한다. 기본 물체(`Baseplate`, 기본 `SpawnLocation`)와 `StreamingEnabled`는 Claude가 첫 생성 때 한 번만 바꾸고(BR-6.5, Q2=A), 이후 재생성은 `Auto/<칸ID>` 밖을 건드리지 않는다.
- **U2-NFR-SEC4 MCP** Studio 내장 MCP 서버는 열린 맵을 읽고 수정할 수 있다. 신뢰하는 클라이언트(이 Claude 세션)만 연결하고, 큰 작업 전에는 백업한다(A2).
- **U2-NFR-SEC5 공급망(SECURITY-10)** 새 의존성이 없다. `build_luau.py`는 `h3==4.5.0`, `shapely==2.2.0`을 정확한 버전으로 인라인에 적고(`register.py`와 같다), `tests/test_versions.py`와 CI의 `pip-audit`가 그대로 점검한다.
- **U2-NFR-SEC6 입력 검증** DB에서 읽은 값(외곽선 점 수, 좌표 범위, 높이)과 설정(양수, 위경도 범위)을 검증하고, 어긋나면 그 항목을 건너뛰거나 시작하지 않는다(BR-2.9, BR-7.6).

## 5. 신뢰성
- **U2-NFR-R1** 호출이 실패하거나 연결이 끊기면 그 칸을 `begin`부터 다시 한다(8 ms라 가장 단순하다). 이어서 하는 기능은 만들지 않는다(N-U2-7).
- **U2-NFR-R2** 같은 입력과 설정으로 다시 만들면 결과가 같다. 입력 행의 순서에 상관없다(P2-8, BR-6.4).
- **U2-NFR-R3** `Auto/<칸ID>`의 `BuildComplete`가 만들기가 끝났는지를 나타낸다(BR-6.3).
- **U2-NFR-R4** 실행마다 `collection_runs`에 `unit = 'C6'`으로 항목 수(종류별), 덩어리 수, `poor_fit` 수, 경고 수를 기록한다. 로그는 U1과 같은 JSON 파일과 콘솔 요약이다.

## 6. 유지보수성과 테스트
- **U2-NFR-M1 테스트 도구** U1과 같다(`pytest` + `Hypothesis`, 실패 시 시드 출력, CI에서 시드 고정).
- **U2-NFR-M2 테스트 범위** 속성 P2-1~P2-9를 속성 기반 테스트로 만든다. 덩어리 파일과 manifest는 예시 기반 테스트로 확인한다. 생성기(좌표, 외곽선, 도로)는 `tests/generators.py`에 한 번만 정의한다(PBT-07).
- **U2-NFR-M3 Luau 쪽 확인 (Q4=A)** CI에서 Luau를 검사하지 않는다(`luau-analyze`는 쓰지 않는다). Studio에서 `Builder.verify`(폴더별 부품 수와 건너뛴 수, 부품 몇 개의 위치·크기·회전)와 S-1~S-6으로 매번 확인한다. 코드가 커지는 U5에서 다시 정한다.
- **U2-NFR-M4 모듈 분리** 순수 계산(좌표 변환, 박스 맞춤, 도로·인도 조각, 땅, 덩어리)은 입출력 없는 모듈로 두고, `build_luau.py`는 DB 읽기, 파일 쓰기, 설정, 명령줄만 맡는다. `studio/Builder.luau`는 계산하지 않고 부품만 만든다(BR-7.5).
- **U2-NFR-M5 설정값** `config.toml`에 `origin_lat`, `origin_lon`, `studs_per_m`, `poor_fit_ratio`, `ground_margin_m`, `sidewalk_width_m`, 도로 폭 표, `chunk_size`, `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`를 추가하고 범위 검증은 `common.py`에서 한다.
- **U2-NFR-M6 버전 일치 검사** `tests/test_versions.py`가 `build_luau.py`의 인라인 고정이 `==`인지, `tests/requirements.txt`와 겹치는 패키지(`h3`, `shapely`)의 버전이 같은지 확인한다(스크립트를 자동으로 찾으므로 코드 변경은 필요 없을 수 있다).

## 7. 사용성
- **U2-NFR-U1** 명령줄 한 줄이다. 끝에 항목 수(종류별), 덩어리 수, 경고(안 맞는 건물, 스폰이 도로 밖일 때 등)와 "Studio에서 실행할 순서"를 인쇄한다. Studio 실행은 Claude가 하고 결과를 manifest와 비교해서 보고한다.

## 8. 외부 연동과 저장
- **U2-NFR-X1 Studio MCP** `execute_luau`(편집 모드)로 덩어리를 실행하고 `Builder` 소스를 `ServerStorage/MapBuilder`에 넣는다. `search_game_tree`, `inspect_instance`, `screen_capture`로 확인한다. 시험으로 소스 쓰기, `require`, 실제 덩어리 실행을 확인했다(Studio 0.742).
- **U2-NFR-X2 저장** 덩어리 파일과 manifest는 `data/build/<칸ID>/`(칸당 수십 KB, git 제외). `studio/Builder.luau`는 git에 포함한다.

## 확장 규칙 준수 요약

### Security Baseline (이 단계)

| 규칙 | 상태 | 근거 |
|---|---|---|
| SECURITY-01 | 전송 중: N/A(로컬 연결). 저장 시: U1과 같은 문서화된 예외(이 Mac의 로컬 파일, 디스크 암호화는 OS 설정) | 생성 파일은 DB에서 다시 만들 수 있고 비밀값이 없다 |
| SECURITY-02, 04, 06, 07, 08, 14 | N/A | 서버, 웹, 접근 제어, 경보 없음 |
| SECURITY-03 | 준수 (U1과 같은 예외) | JSON 로그, 비밀값 없음, 중앙 로그는 해당 없음 |
| SECURITY-05 | 준수 | 외부 API에서 온 값이 코드에 들어가는 점을 입력 허용 문자와 이스케이프로 막는다(SEC2), 설정과 DB 값 검증(SEC6) |
| SECURITY-09, 11, 15 | 준수 | 허용 밖 항목은 건너뛰고 경고(실패해도 코드를 실행하지 않음), 최상위 오류 처리는 U1의 `run_cli`, 지우는 범위 제한(SEC3) |
| SECURITY-10 | 준수 | 새 의존성 없음, 기존 고정과 `pip-audit` 유지, SBOM은 배포가 없어 N/A |
| SECURITY-12 | 준수 | 키 없음 |
| SECURITY-13 | 준수 | manifest와 Studio 결과를 비교해 무결성을 확인한다(`verify`). Studio가 데이터를 코드로 실행하지 않는다 |

차단 항목은 없다. 새 예외도 없다(SECURITY-01 저장 시 암호화는 U1에서 이미 확인받은 예외).

### Resiliency Baseline (이 단계)

| 규칙 | 상태 | 근거 |
|---|---|---|
| RESILIENCY-01, 02 | 준수 | RTO/RPO 수 시간 |
| RESILIENCY-03, 04, 14, 15 | 준수 | U1 NFR Design에서 사용자가 정한 방식을 이어서 쓴다(변경 관리, GitHub Actions, 롤백, 복원력 테스트, 사고 대응). RESILIENCY-15는 U1에서 확인받은 예외 그대로 |
| RESILIENCY-05~10 | N/A | 배포된 서비스, 고가용성 없음 |
| RESILIENCY-11, 13 | 준수 | Backup & Restore(A2), 런북 R-10~R-12 추가 |
| RESILIENCY-12 | 준수 | `Manual`(수작업)은 `.rbxl` 복사본과 Version History로 보호한다. `Auto`와 `data/build/`는 다시 만들 수 있어 백업하지 않는다 |

### Property-Based Testing

| 규칙 | 상태 | 근거 |
|---|---|---|
| PBT-01 | 준수 | 기능 설계의 P2-1~P2-9 |
| PBT-09 | 준수 | U1에서 선택한 `pytest` + `Hypothesis` 그대로 |
| PBT-07, 08 | 코드 생성과 Build and Test에서 확인 | 좌표, 외곽선, 도로 생성기를 `tests/generators.py`에 추가한다. 시드는 CI에서 실행 번호로 고정 |
