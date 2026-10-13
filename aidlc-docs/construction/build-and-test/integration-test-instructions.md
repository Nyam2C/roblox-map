# Integration Test Instructions

## Purpose
U1 안에서 C1(`cells.py`) → DB → C2(`register.py`)의 연결과, 실제 외부 서비스(Overpass, V-World)와의 동작을 확인한다. 다른 유닛과의 통합은 해당 유닛을 만들 때 추가한다(U3, U2는 `buildings`, `street_features`를 읽는다).

## 자동화된 통합 테스트 (외부 호출 없음)
`tests/test_parse.py`가 가짜 HTTP로 한다.
- `collect_cell`을 두 번 돌려도 DB 상태가 같다(P-8, end to end), 백업 파일이 생긴다.
- `assemble_cell`이 칸 소유 건물만 저장하고 두 번 돌려도 같다.
- `fetch_vworld`가 모든 페이지를 따라가고 키를 요청에 쓰되 오류 메시지에 노출하지 않는다.

## 실제 서비스 통합 확인 (수동, 키 필요)

### Scenario 1: 첫 칸 수집과 조립
- **Setup**: `.env`에 `VWORLD_KEY`. 깨끗한 DB(`rm -f data/map.db`).
- **Test Steps**:
  ```bash
  uv run --env-file .env src/cells.py --cells 8930e0af13bffff
  uv run --env-file .env src/register.py --cells 8930e0af13bffff
  ```
- **Expected Results**: 두 실행 모두 `1 ok, 0 failed`. `collection_runs`에 C1, C2 한 줄씩 `ok`.
- **Cleanup**: 필요하면 `rm -f data/map.db`. 백업과 로그는 `data/`에 남는다.

### Scenario 2: 같은 입력으로 재실행
- **Test Steps**: `register.py`를 한 번 더 돌리고 DB 상태의 해시를 비교한다.
- **Expected Results**: 해시가 같다(재수집은 같은 결과, NFR-3).

### Scenario 3: 로그와 파일에 키가 없다
- **Test Steps**: `data/logs/*.jsonl`과 저장소의 모든 파일에서 `.env`의 키 값을 검색한다.
- **Expected Results**: 없음.

## 이번 실행 결과 (2026-10-13)
- Scenario 1: 성공. C1은 Overpass가 504를 세 번 내서 재시도 후 약 131초, C2는 약 4초.
- Scenario 2: 재실행 전후 DB 해시가 같았다(`cd65eb629317dfeb`).
- Scenario 3: 로그 2개 파일과 모든 추적 파일에 키 없음.

## U3 거리뷰 캡처 (2026-10-13)

### 자동화된 통합 테스트 (네이버 호출 없음)
`tests/test_capture.py`가 가짜 네이버와 합성 큐브 맵으로 한다: 상한과 재개(상한 때문에 멈춘 실행을 이어 돌린 결과가 한 번에 돌린 결과와 같음, 파일 바이트까지), 차단 뒤 호출이 없음, 다시 계획, 파노라마 하나가 실패해도 계속, 크롭 실패 기록, 설정이 바뀌면 바뀐 크롭만 다시 만듦, 저장 경로.

### 실제 서비스 통합 확인 (수동, 키 없음)

#### Scenario 1: 첫 칸 캡처
- **Setup**: `data/map.db`에 `buildings`가 있을 것(U1). 시작 전 `cp data/map.db data/backups/pre-u3-map.db`.
- **Test Steps**: `uv run src/capture.py --cells 8930e0af13bffff`를 `stopped_reason=done`이 나올 때까지 되풀이한다.
- **Expected Results**: 상한(100장)에서 멈추면 같은 명령으로 이어서 끝난다. 모든 `building_views`가 `cropped`, 모든 `captures`가 `downloaded`.
- **Cleanup**: `captures/`를 지우고 `building_views`, `captures` 행을 지우면 처음부터 다시 할 수 있다(또는 `--replan`).

#### Scenario 2: 같은 입력으로 재실행
- **Expected Results**: 네이버를 부르지 않고 크롭을 새로 만들지 않는다(`new_downloads=0`, `crops=0`, `crops_kept=363`).

#### Scenario 3: 로그와 사진 파일에 비밀값이 없다
- **Expected Results**: `data/logs/capture-*.jsonl`과 `captures/*/*/meta.json` 227개 파일에서 `.env` 값을 찾지 못한다. `captures/`는 git 제외.

### 이번 실행 결과 (첫 칸 `8930e0af13bffff`)
- Scenario 1: 3번 만에 끝났다(100장에서 멈춤, 100장에서 멈춤, 26장으로 완료). 차단, 재시도, 실패 모두 0.
- Scenario 2: 1초, 네이버 호출 없음, `crops_kept=363`.
- Scenario 3: 227개 파일에서 비밀값 없음.
- 정합성: DB에 적힌 모든 파일이 있다(0개 누락). 크롭 363개 전부 1024×768, 확인한 파노라마 전부 6144×1024.
- 눈으로 확인: 무작위 32장 + 건물 5장. 대부분 건물이 가운데에 온다(아래 요약의 "발견한 것" 참고).

#### Scenario 4: 크롭 규칙을 바꾼 뒤 재실행 (BR-4.5)
- **Test Steps**: 위쪽 각도·시야각 규칙을 바꾼 뒤 `uv run src/capture.py --cells 8930e0af13bffff`.
- **Expected Results**: 네이버를 부르지 않고(`new_downloads=0`), 값이 바뀐 크롭만 다시 만든다.
- **이번 결과**: 크롭 360개를 다시 만들고 3개는 그대로(73초, 실패 0). 지붕과 지면이 모두 들어오는 크롭이 241개(66%) → 312개(86%), 건물 단위 114/122 → 121/122.

## U2 Studio 생성기 (2026-10-13)

### 자동화된 통합 테스트
`tests/test_build_luau.py`가 합성 DB로 한다: 덩어리·manifest 파일, 항목 순서, 같은 입력은 같은 글자(P2-8), 오래된 덩어리 삭제, `main`의 실행 기록, 칸에 건물이 없을 때의 오류.

### 실제 Studio 통합 확인 (수동, 사용자의 `.rbxl` 복사본 필요)

#### Scenario 1: 첫 칸 생성 (S-1, S-2)
- **Setup**: `.rbxl` 복사본, 장소 설정 변경, `ServerStorage/MapBuilder` 설치.
- **Test Steps**: `build_luau.py --cells 8930e0af13bffff` → 덩어리 4개를 차례로 `execute_luau` → `Builder.verify(칸ID, manifest.counts, 샘플 이름)`.
- **Expected Results**: 만든 수 = manifest, 읽어 온 위치·크기·회전이 덩어리 값과 일치.
- **Cleanup**: 필요하면 `Workspace/Auto/<칸ID>`를 지우면 된다(다시 실행하면 비우고 만든다).

#### Scenario 2: 수작업 우선 (S-3)와 재생성 (S-4)
- **Test Steps**: `Workspace/Manual`에 같은 `BuildingId` 속성을 가진 부품을 두고 칸을 다시 만든다. 지우고 다시 한 번 만든다. 다른 칸 폴더를 `Auto`에 두고 확인한다.
- **Expected Results**: 자동 건물 한 개를 건너뛰고 `verify` 정상. 수작업 부품을 지운 뒤 다시 만든 결과가 처음 결과와 같다. 다른 칸 폴더와 `Manual`은 그대로.

#### Scenario 3: 걸어 보기 (S-5)와 눈으로 확인 (S-6)
- **Test Steps**: 플레이 테스트로 스폰에서 시작해 `character_navigation`으로 도로까지 걷는다. `screen_capture`로 위에서와 눈높이에서 본다.

### 이번 결과 (첫 칸 `8930e0af13bffff`)
- **Scenario 1**: 부품 162개(스폰 설정 전), 그다음 163개(스폰 포함)를 만들었다. 만든 수가 manifest와 같았고(`verify` 문제 없음) 읽어 온 값이 덩어리 값과 일치했다(건물 `gis:11185213`, 도로 `way:222140575#2`, 인도, 땅).
- **Scenario 2**: 수작업 부품이 있으면 161개를 만들고 1개를 건너뛰었다(`verify` 정상, 같은 ID의 자동 건물은 만들어지지 않음). 다시 만든 결과가 처음과 같았고(부품 이름, 위치, 크기, 회전, 재질, 색, 층수 속성의 서명이 같음) 다른 칸 폴더가 유지됐다. 시험 물체는 모두 지웠다.
- **Scenario 3**: 플레이에서 스폰 점 `(-323.28, 4.2, -125.7)`에서 태어나 본관 방향(`0.88, -0.47`)을 보았다. 도로까지 걸어서 도착했고(`(-440.3, 4.1, 100.9)`), 심원고 본관 박스 안으로 가는 길은 "경로 없음"으로 막혔다.
- 중간에 Studio 연결 ID가 한 번 바뀌었다. 같은 장소(`placeId`)였고 장소 안의 변경은 그대로 남아 있었다.

---

# U4 판단·보정 (2026-10-13)

## 자동화된 통합 테스트 (외부 호출 없음)
`test_estimate.py`(합성 DB와 합성 이미지로 `pending`, `record`, `report`, `plan`, `compose`와 명령줄), `test_overrides.py`(`set`, `unset`, `list`, `export`, `import`와 **복구 연습 시나리오**: 새 DB에 건물을 다시 넣고 불러오면 같은 최종값), `test_u4_db.py`, `test_build_luau.py`의 U4 시험(판단·보정이 덩어리 파일의 높이·색·속성에 들어가고 코드 주입이 막힌다)이 한다.

## 실제 통합 확인 (첫 칸 `8930e0af13bffff`, 수동)

### Scenario 1: 눈가림 판단 → 보고
- **Test Steps**: `estimate.py pending`으로 건물 10개씩 받아 묶음 이미지를 보고 판단해 `record`한다. 122개를 끝낸 뒤 `report`.
- **Expected Results**: 모든 건물이 판단되고 `report`가 상태, 일치율, 확인 목록을 낸다. 판단 전에는 항목에 대장·OSM 숫자가 없다.
- **결과**: 13번(10~12개씩)에 122개를 기록했다. 층수 상태 verified 64, unverified 12, conflict 30, filled 11, none 5. 사진 층수가 대장과 같은 건물 75/104(72%; high 5/5, medium 59/74, low 11/25, 눈가림이 깨진 1개는 제외). 확인 목록 45개. 높이 근거 register 100, from_floors 17, photo_geometry 4, default 1.

### Scenario 2: Studio에 새 값으로 칸 만들기
- **Test Steps**: `build_luau.py`, `MapBuilder` 갱신, 덩어리 4개 실행, `verify`.
- **Expected Results**: 부품 163개, `verify` 문제 없음, 건물 122개에 `HeightBasis`, `FloorsBasis`, `WallColor`, `Review`가 달리고 벽 색이 칠해진다.
- **결과**: 통과(부품 163개, `Review` 45개, 벽 색 8종). 처음에는 속성이 안 달렸다: `require` 캐시 때문(Troubleshooting 참고). 모듈을 새 인스턴스로 바꾸고 다시 만들어 해결.

### Scenario 3: 비교 쌍과 같이 확인하기
- **Test Steps**: `plan`, Studio 카메라를 크롭 위치에 두고 `screen_capture`, `compose`, 쌍을 보고 어긋난 건물을 정한다.
- **결과**: 136쌍 중 74개를 만들고 봤다(1~4번 묶음 62개 전부, 5~11번 묶음은 고정 시드 표본 12개; 사용자 결정으로 Q8의 "전체"를 바꿨다). 보정 0개, 대장 값 122개 유지.

### Scenario 4: 복구 연습
- **결과**: 통과. 새 DB에 `cells.py`, `register.py`를 다시 돌리고 `overrides.py import`하자 건물 122개의 최종값이 연습 전과 모든 필드에서 같았고 `export` 파일이 바이트까지 같았다. 사진 표(`captures`, `building_views`)는 대상이 아니다.

### Scenario 5: 보정 `set`/`unset`과 다시 만들기 (실제 칸)
- **결과**: **실제 칸에서는 해 보지 못했다**(보정이 0개라서). 이 경로는 자동 테스트(`test_u4_db.py`, `test_overrides.py`, `test_build_luau.py`)와 `MCP_Test`의 합성 칸 시험으로만 확인됐다. 첫 보정이 생길 때 한 번 더 확인한다.

---

# U5 디테일 (2026-10-13)

자동 시험은 `test_details.py`(합성 DB로 명령줄 전체), `test_u5_db.py`(기록·내보내기·불러오기 왕복), `test_build_luau.py`의 U5 시험(세부가 덩어리 파일의 재질·간판·속성으로 들어가고 간판 글자와 이름이 검사된다)이 한다. 실제 칸에서 한 시나리오:

### Scenario 1: 세부 판단 116건
`details.py pending`이 U4 묶음 이미지를 재사용해 건물 10개씩 내고, 판단을 `record`로 기록했다(116건, 전부 한 번에 또는 거부). `details/8930e0af13bffff.json`으로 바로 내보내졌고 `list`와 같다. 비고에 숫자·번호판·상호가 없는지 정규식으로 확인(0건).

### Scenario 2: Studio 생성과 `verify`
첫 생성(수정 전 코드): 부품 4,893개, 덩어리 70개, 1.68초, 가장 느린 덩어리 38 ms, `verify ok`. 수정 후 다시 생성(Manual 학교가 있는 상태): 4,880개 생성(1개는 Manual이 가진 건물이라 건너뜀), `verify ok`, `unknown_manual []`, 폴더 Ground 1, Roads 29, Paths 2, Sidewalks 20, Buildings 127, Roofs 161, Facades 2,891, Signs 203, Props 1,445, Spawn 1. `HttpEnabled`는 끝난 뒤 `false`.

### Scenario 3: Manual 학교 (S-14)
`studio/ManualSchool.luau`로 `Workspace/Manual/School`에 501개(운동장 모래판·선·골대, 필지 울타리 기둥 155·가로대 290, 교문 기둥 2와 "심원고등학교" 현판, 본관 남면 유리 계단탑과 띠, 별관 발코니 4층, 소나무 6, 정자) + Auto에서 끌어온 작은 건물 `gis:15839722` 1개. 그 뒤 Auto를 다시 만들었더니 Manual은 그대로(자손 512 → 512), 그 건물은 Auto가 건너뛰었다(`Skipped_building 1`, Auto 안에 0개). 계단탑은 본관 남면 가운데에 지붕 위로 1.5 m 솟아 있다(캡처).

### Scenario 4: 복구 연습 (S-16)
`data/map.db`를 복사해 `estimates`·`overrides`·`details`를 비우고 `overrides.py import`(판단 122, 보정 0) → `details.py import`(116) → `build_luau.py`. 덩어리 70개와 manifest가 원본과 글자까지 같다(`built_at`만 제외). S1(수집)은 네트워크가 필요해 DB 복사로 대신했다.

### Scenario 5: 간판 겹침 (S-10에서 발견)
20 m 캡처에서 1층 띠간판("누리편의점")과 2층 층별 간판("바른치과")이 같은 자리에 겹쳐 글자가 포개졌다. 띠간판을 1층 천장선 아래(`fh - 0.2 - 0.9`)로 내리고(`layout_details.sign_items`) 테스트(띠간판 위 ≤ 층선 ≤ 층별 간판 아래)를 더했다. 다시 만든 뒤 캡처로 확인.

### Scenario 6: 거리 캡처
10 m: 적벽돌 3층 빌라의 층 띠·창·셔터·띠간판·가스관·마당 담·가로등·전선, 떨림 없음. 80 m: 모임지붕·박공 빌라 거리와 상가 블록(층별 간판은 색 띠로만 보임, `MaxDistance` 200 stud = 55 m 의도대로). 60 stud(16.7 m) 정면: 9자 이름이 읽힌다.

## U5 확장: 간판 이미지 (2026-10-13)

### Scenario 7: 올리기 경로와 Builder의 ImageLabel
표본 3장을 127.0.0.1에서 `upload_image`로 올려 `rbxassetid` 3개를 받았고, `MCP_Test/U5_IMG` 안에서 진짜 Builder로 `im`이 있는 간판 3개와 없는 간판 1개를 만들었다: `ImageLabel` 3, `TextLabel` 1, `verify`의 `labels` 4. 28 stud와 65 stud 캡처에서 한글 이름·아이콘이 읽힌다(만든 직후 첫 캡처는 빈 판이었고 1분 뒤에는 보였다). 시험 폴더는 지웠다.

### Scenario 8: 첫 칸 전체
145장 생성·올리기·기록 뒤 `build_luau.py`가 `sign_images=145`를 내고(항목 6,436, 덩어리 92개 ≤ 13.3 KB), Studio 재생성에서 `ImageLabel` 145·`TextLabel` 105(현판·돌출·옥상), `verify ok`, Manual 학교 그대로. 올린 직후 캡처는 색 판만 보이고 1분 뒤 글자·그림이 보인다. 검수 거부된 3장은 Studio에서 빈 판으로 남는다(글자 대체는 자산이 기록에 있는 한 켜지지 않음: 사용자가 ID를 알려 주면 기록에서 빼서 글자로 되돌린다)
