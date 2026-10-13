# U4 판단·보정 — Code Generation Plan

**이 문서가 코드 생성의 유일한 기준이다.** 생성 단계에서는 여기 적힌 순서와 내용만 한다. 승인 뒤에 단계마다 `[x]`로 표시한다.

## 유닛 맥락

- **유닛**: U4 판단·보정. 컴포넌트는 C4 `estimate.py`, C5 `overrides.py`, C7(`db.py`)의 U4 테이블과 최종값 합치기, 이 유닛이 새로 만드는 순수 모듈 `judgement.py`(검증, 최종값, 확인 목록, 내보내기 형식)와 `review.py`(눈가림 항목, 순서, 비교 묶음, 카메라 값, 일치율), 그리고 U2 코드 변경(`layout.py`, `build_luau.py`, `studio/Builder.luau`).
- **프로젝트 종류**: 기존 코드가 있는 프로젝트(brownfield). 작업 위치는 저장소 루트 `/Users/taehyeonpark/Desktop/dev/roblox-map`. 코드는 `aidlc-docs/`에 두지 않는다.
- **기존 파일 처리**: `src/db.py`(U4 테이블과 함수 추가, 머리말 고침), `src/common.py`와 `config.toml`(U4 설정), `src/layout.py`, `src/build_luau.py`, `studio/Builder.luau`, `tests/generators.py`, `tests/test_common.py`, `tests/test_layout.py`, `tests/test_build_luau.py`, `tests/test_versions.py`, `CLAUDE.md`는 고친다. 복사본을 만들지 않는다.
- **의존하는 유닛**: U1의 `buildings`, `db.py`, `common.py`, `geo.py`. U3의 `building_views`, `captures`와 `captures/` 크롭. U2의 `layout.py`(좌표 변환, 박스), `build_luau.py`, `Builder.luau`.
- **설계 입력**: `construction/u4-judgement-corrections/functional-design/`(엔티티, BR-1~BR-10, 속성 P4-1~P4-16), `.../nfr-requirements/`(N-U4-1~15, U4-NFR 항목, 기술 선택), U1~U3의 NFR 결정.
- **이 유닛이 소유한 것**: DB 테이블 `estimates`, `overrides`, `overrides/<칸ID>.json`(git 포함), `captures/<칸ID>/sheets/`, `captures/<칸ID>/review/`, `data/build/<칸ID>/review.json`(git 제외). `collection_runs`에 `unit = 'C4'`, `'C5'` 기록을 남긴다.
- **이 계획의 범위 밖(Build and Test)**: 첫 칸 122개를 실제로 판단하는 일, 일치율 보고, Studio의 `ServerStorage/MapBuilder` 갱신과 첫 칸 재생성, 비교 쌍 만들기와 사용자 확인, 보정, 복구 연습, 프레임 측정. 코드 생성 중 Studio 시험은 `Workspace.MCP_Test` 안에서만 하고, 진짜 `MapBuilder`는 건드리지 않는다.
- **눈가림 주의**: 이 단계에서 첫 칸 실제 DB에는 읽기 전용으로만 접근하고, 건물별 대장 층수·높이를 출력하지 않는다(건수와 "같다/다르다"만 출력). `report`와 `plan`을 첫 칸 실제 DB에 돌리는 것은 판단이 끝난 뒤(Build and Test)다. 이미 눈가림이 깨진 건물은 `gis:11081057` 하나다.

## 요구사항·규칙 추적

| 요구사항·규칙 | 구현 단계 |
|---|---|
| FR-8 (외관 판단: 벽 색, 지붕 모양) | 단계 2, 3, 6, 7 |
| FR-9 (층수·높이 판정, 근거 기록, 보정) | 단계 2, 4, 5, 6 |
| FR-11 (재생성해도 보정 보존) | 단계 4, 5 |
| NFR-3 (재현성) | 단계 2~5, 9 |
| NFR-4 (사진은 로컬에만) | 단계 7 (눈가림 묶음, 비교 쌍은 `captures/`) |
| NFR-6 (보정 내보내기·복구) | 단계 4, 5, 6 |
| NFR-7 (고정 의존성, 입력 검증) | 단계 1, 2, 4, 7, 11 |
| NFR-8 (속성 기반 테스트) | 단계 5, 8 |
| BR-1~BR-10 | 단계 2~9 (각 단계에 명시) |
| P4-1~P4-16 | 단계 5, 8 (표 아래) |
| U4 NFR (P1~P6, SEC2~SEC7, R1~R6, M1~M6, U1~U4) | 단계 1, 4, 6, 7, 9, 11 |

속성 ↔ 테스트: P4-1, P4-2, P4-12 → `tests/test_judgement.py`(단계 5), P4-3, P4-4, P4-5, P4-6, P4-7, P4-9, P4-16 → `tests/test_judgement.py`와 `tests/test_u4_db.py`(단계 5), P4-8 → 둘 다, P4-10, P4-11, P4-13, P4-14, P4-15 → `tests/test_review.py`(단계 5).

## 단계

### 단계 1. 설정 — N-U4-12, U4-NFR-M5
- [x] `config.toml`과 `src/common.py`(`DEFAULTS`, 범위 검증)에 U4 항목을 추가한다: `floor_height_min_m`(2.5), `floor_height_max_m`(5.0), `review_batch_size`(12), `sheet_tile_w`(512), `sheet_tile_h`(384), `sheet_jpeg_quality`(85), `overrides_dir`("overrides"), `blind_broken`(문자열 목록, 기본 `["gis:11081057"]`), `wall_colors`(키 → `[r, g, b]` 표, 기능 설계 Palette의 12색). 검증: 층고 범위는 `0 < min < max`, 색표는 `light_gray`를 포함하고 값이 0~255 정수 셋이어야 한다, 키는 영문 소문자와 `_`만(Studio로 가는 코드 단어이므로). 설정 이름은 `building_height_m`의 `floor_height_m`(3.4)과 `default_height_m`(10)을 그대로 쓴다.
- [x] `tests/test_common.py`가 기본값 일치(`config.toml`과 `DEFAULTS`)와 새 항목 검증(범위 밖, 색표에 `light_gray` 없음, 값이 잘못된 색, `min ≥ max`, 잘못된 `blind_broken`)을 확인하도록 고친다. 기존 테스트가 그대로 통과하는지 확인한다.

### 단계 2. `src/judgement.py` — 검증, 최종값, 확인 목록, 내보내기 형식 (입출력 없음) — BR-2.2, BR-3, BR-4, BR-5, BR-6, BR-7.1, BR-8.3, BR-8.5, P4-1, P4-2, P4-3, P4-6~P4-9, P4-12
- [x] 상수: `FIELDS`(`floors_above`, `height_m`, `wall_color`, `roof_shape`), `ROOF_SHAPES`, `CONFIDENCES`, `FLAGS`(고정 순서), 근거 코드. 한도: 층수 1~100, 높이 2~500.
- [x] 검증: `validate_judgement(judgement, cfg, valid_ranks)`가 BR-2.2를 그대로 적용해 정규화된 행을 돌려주고 틀리면 어느 건물의 어느 항목인지 담은 `ValueError`를 낸다(제어문자, 길이, 확신도 필수 조건, `height_est_m`는 `floors_seen`이 없을 때만). `validate_override(field, value, reason, cfg)`가 BR-6.1~6.2를 적용한다(필드 넷, 값의 형식과 범위, 사유 1~500자 제어문자 없음, 층수는 정수, 불리언 거부). 건물 ID 허용 문자 검사(N-U4-7)도 여기에 둔다.
- [x] 최종값: `effective_building(building, estimate, overrides, cfg)`가 `EffectiveBuilding`(변경 불가 데이터 클래스: 층수·높이·벽 색·지붕 모양과 근거, `floors_status`, `flags`, 참고값)을 돌려준다. 층수는 BR-3 표 전체, 높이는 BR-4.1~4.8, 외관은 BR-5, 확인 목록 사유는 BR-7.1(보정이 있는 필드는 그 필드의 사유를 올리지 않는다, `unjudged`는 판단 행이 없으면 항상). 벽 색 RGB는 `wall_rgb(key, cfg)`(`other`는 `light_gray`).
- [x] 내보내기 형식: `export_payload(cell_id, overrides, estimates)`가 정렬된 JSON 글자(`version` 1, 키 정렬, 들여쓰기 2칸, UTF-8, 끝에 줄바꿈 한 개)를 만들고, `parse_export(text, cfg)`가 크기·형식·행을 모두 검증해 `(cell_id, overrides, estimates)`를 돌려준다(하나라도 틀리면 `ValueError`, BR-8.5).

### 단계 3. `src/review.py` — 눈가림 항목, 순서, 비교 묶음, 카메라, 일치율 (입출력 없음) — BR-1, BR-7.2~7.4, S4-2, P4-10, P4-11, P4-13, P4-14, P4-15
- [x] `HIDDEN_FIELDS`와 `blind_item(building, views, frame)`: 허용 키(건물 ID, 이름, 위치, 박스 크기(m), 크롭 순위와 보는 방위의 8방위)만 담은 항목을 만든다. 숨기는 필드는 BR-1.3의 일곱 개. `camera_bearing(heading_deg, yaw_deg)`(0 이상 360 미만).
- [x] 순서와 묶음: `pending_order(buildings, school_ids)`(대장에 층수도 높이도 없는 건물 → 면 사진이 있는 학교 건물 → 나머지, 각 묶음 안은 건물 ID 순, BR-1.2)와 `review_batches(effective_list, school_ids, size)`(사유가 있는 건물 → 학교 건물 → 나머지, 묶음당 `size`, BR-7.2).
- [x] 카메라: `h_to_v_fov(h, aspect)`, `v_to_h_fov`(4:3 기본), `camera_for_view(frame, pano_lat, pano_lon, heading_deg, yaw_deg, pitch_deg, camera_height_m)`가 위치(stud), 바라볼 점(위치에서 100 stud 앞), 방위를 돌려준다(BR-7.4, `layout.to_studs` 재사용). `capture_crop_box(width, height, fov_h_deg)`는 Studio 캡처(세로 시야각 83.58°)에서 4:3 가운데를 잘라 크롭의 시야각에 맞춘 상자를 돌려준다(N-U4-4, 4:3보다 좁으면 `ValueError`).
- [x] 일치율: `agreement(rows, broken_ids)`가 대장 층수와 사진 층수가 모두 있는 건물만 세고(`broken_ids`는 뺀다) 확신도별·전체의 비교 수, 일치 수, 일치율을 돌려준다(P4-15).

### 단계 4. `src/db.py` — U4 테이블과 함수 — BR-2.3, BR-6.3~6.5, BR-8, U4-NFR-R1, P4-6, P4-7, P4-9, P4-16
- [x] `SCHEMA`에 `estimates`(건물 ID 기본키, 칸 ID, 층수, 확신도, 추정 높이, 벽 색, 지붕 모양, 쓴 순위 목록(JSON 글자), 메모, 시각)와 `overrides`((건물 ID, 필드) 기본키, 칸 ID, 값(JSON 글자), 사유, 시각)를 더한다. 머리말 문서를 고친다(이제 U4 테이블을 이 모듈이 쓴다). 기존 `replace_cell_rows`는 두 테이블을 건드리지 않고 `orphans`는 그대로 동작한다.
- [x] 쓰기(모두 한 트랜잭션, 하나라도 틀리면 아무것도 쓰지 않음): `record_judgements(conn, cfg, judgements, now)`(건물이 있고 `status=ok`이며 칸 ID를 건물에서 가져오고, `views_used`가 그 건물의 `cropped` 순위 부분집합인지 확인, 내용이 같으면 행과 시각을 그대로 둠), `set_override(conn, cfg, building_id, field, value, reason, now)`(건물이 DB에 있어야 함, 같은 값·사유면 변경 없음), `unset_override(conn, building_id, field) -> bool`.
- [x] 읽기: `estimates_in_cell`, `overrides_in_cell`, `overrides_by_building`, `views_with_heading(conn, cell_id)`(`building_views` + `captures`), `effective_buildings(conn, cfg, cell_id)`(`status=ok` 건물 전부, 건물 ID 순).
- [x] 내보내기와 불러오기: `export_cell(conn, cell_id, directory) -> Path | None`(BR-8.3: 판단·보정이 없고 파일도 없으면 만들지 않음, 있던 파일은 빈 상태로 다시 씀, 임시 파일 + `os.replace`), `import_file(conn, cfg, path)`(5 MB 이하, `parse_export`로 전체 검증 뒤 한 트랜잭션, (건물 ID, 필드)·건물 ID 기준 덮어쓰기, 파일에 없는 기존 행은 둠, 건수와 고아 목록을 돌려줌).

### 단계 5. 테스트: 순수 모듈과 DB — P4-1~P4-16, PBT-07
- [x] `tests/generators.py`에 건물 행(층수·높이 있음/없음/0, OSM 참고값), 판단(층수 있음/모름, 확신도 세 가지, `height_est_m`, 색, 지붕), 보정 필드 값, 한 건물에 대한 (건물, 판단 또는 없음, 보정들) 묶음, 크롭 순위 부분집합 생성기를 추가한다(공용).
- [x] `tests/test_judgement.py`: P4-1(층수 표의 모든 칸을 예시로, 임의 입력에서 값·근거·상태가 표와 같고 상태가 하나로 나뉨, 대장과 같으면 확신과 관계없이 대장), P4-2(높이가 항상 0보다 큼, 대장 높이를 쓰는 때, 층수가 하나 늘면 3.4 m 늘어남, 모두 없으면 10 m, 대장 층수가 있고 최종 층수가 다르면 대장 높이가 영향 없음), P4-3(보정이 최종값과 근거를 정함, 다른 건물에 영향 없음), P4-12(확인 목록 사유가 상태·근거와 맞음), P4-9의 검증 부분(허용 밖 필드·값·빈 사유·범위 밖 순위가 모두 거부됨), P4-8의 내보내기 형식(행 순서를 섞어도 글자까지 같음, 키 정렬), P4-7의 형식 왕복(`parse_export(export_payload(x)) == x`, 다시 내보내면 같음). 잘못된 파일(크기, 알 수 없는 키, 잘못된 값, 다른 칸)이 거부됨.
- [x] `tests/test_review.py`: P4-10(숨기는 필드를 어떻게 바꿔도 항목 내용이 같음. 단 순서는 "층수·높이가 모두 없음"인지에 따라서만 바뀜, 항목에 숨기는 키가 없음), P4-11(입력 순서를 섞어도 같고 모든 건물이 정확히 한 번, 묶음 크기 한도, 빈 묶음 없음), P4-13(시야각 변환 왕복, 단조, 세로 < 가로), P4-14(방위 정의, 360 불변, 단위 벡터), P4-15(합계, 0~1, 눈가림 깨진 건물 제외), 캡처 자르기 상자(이미지 안, 4:3, 가운데 유지, 시야각이 좁을수록 작아짐).
- [x] `tests/test_u4_db.py`: 합성 DB(메모리)로 P4-3·P4-4(`set` 뒤 `unset`하면 최종값이 `set` 전과 같음)·P4-5(다른 필드의 `set`은 순서 불변)·P4-6(같은 판단·보정을 두 번 넣어도 한 번과 같음, 시각 포함)·P4-7(내보내기 → 빈 DB에 불러오기 → 행이 같음, 다시 내보내면 파일이 같음)·P4-9의 원자성(여러 건 중 하나가 틀리면 DB와 파일이 그대로)·P4-16(고아 목록, `replace_cell_rows`가 두 테이블을 안 바꿈)을 확인한다. 예시 테스트: 건물이 없는 칸의 `set` 거부, 빈 판단·보정 칸의 파일 규칙, 파일 쓰기 실패 시 DB 유지, 5 MB 초과 파일 거부, 고아도 불러오되 보고.

### 단계 6. `src/overrides.py` — 보정 관리자 (C5) — BR-6, BR-8, N-U4-15
- [x] 인라인 의존성 없음(표준 라이브러리와 `common`, `db`), Python 3.11 이상. 진입점은 `common.run_cli`로 감싼다. 하위 명령: `set --building ID --field F --value V --reason TEXT`(값은 JSON으로 읽고 안 되면 글자), `unset --building ID --field F`, `list --cells ID`, `export --cells ID`, `import --file PATH`. `set`과 `unset`은 DB 변경이 성공하면 그 칸의 파일을 다시 쓴다(`db.export_cell`). `collection_runs`에 `unit = 'C5'`로 건수를 남기고 `reason`은 로그에 쓰지 않는다. `--selftest`는 import만 확인한다.

### 단계 7. `src/estimate.py` — 높이·외관 판단 (C4) — BR-1, BR-2, BR-7, BR-8.3, N-U4-3~7, U4-NFR-P1~P2, SEC2, SEC4
- [x] 인라인 의존성 `pillow==12.3.0`, `h3==4.5.0`, `shapely==2.2.0`, Python 3.11 이상. `projection.py`는 가져오지 않는다. `Image.MAX_IMAGE_PIXELS`를 5,000만으로 정한다. 진입점은 `common.run_cli`. 하위 명령과 `--selftest`(import만).
- [x] `pending --cells ID [--limit N] [--redo ID ...]`: 기본 10개. `review.pending_order`로 판단 안 한 건물(크롭이 있는 것)을 고르고 `review.blind_item`을 JSON 한 줄씩 인쇄한다. 묶음 이미지는 건물의 크롭 최대 6장을 2열 격자(타일 512×384, 순위와 8방위 표시, JPEG 품질 85)로 `captures/<칸ID>/sheets/<건물 ID(:→_)>.jpg`에 쓴다. 남은 건수와 `no_photo` 건물 수를 알린다. 이미지 파일을 못 읽으면 그 칸을 비우고 경고(크롭이 하나도 없으면 사진 없는 건물처럼).
- [x] `record --file PATH` (또는 `-`로 표준 입력): JSON 목록을 `db.record_judgements`로 기록하고 칸마다 파일을 다시 쓴다. 출력은 기록한 건수뿐이다(BR-2.4: 대장·OSM 값을 읽지도 비교하지도 않음).
- [x] `report --cells ID`: 층수 상태별 수, 확인 목록 사유별 수와 건물 목록(사유 포함), 사진-대장 일치율(전체와 확신도별, 눈가림 깨진 건물을 뺀 수), `no_photo`와 `unjudged` 수를 인쇄한다.
- [x] `plan --cells ID`: `review.review_batches`로 묶고 쌍마다 카메라 값과 크롭의 시야각, 크롭 경로, 출력 파일 이름, 라벨(건물 ID, 최종 층수·높이와 근거, 벽 색, 확인 목록 사유)을 `data/build/<칸ID>/review.json`에 쓴다(정렬된 JSON). 학교 건물은 면 사진마다 하나, 그 밖은 가장 낮은 순위 크롭 하나(BR-7.3). Studio 시야각 상수와 Claude가 따를 절차는 코드 요약 문서에 쓴다.
- [x] `compose --cells ID --captures FILE.json` (`{"<건물 ID>__<순위>": "<캡처 경로>"}`): 캡처 파일을 검사하고(일반 파일, 20 MB 이하, 이미지, 4:3 이상으로 넓음) `review.capture_crop_box`로 잘라 크롭과 나란히 붙여 `captures/<칸ID>/review/<건물 ID(:→_)>__<순위>.jpg`로 쓴다(타일 640×480, 위에 라벨 띠 56 px). 못 만든 쌍은 이유와 함께 건너뛴다. 합친 건수를 알린다.
- [x] 모든 하위 명령은 `collection_runs`에 `unit = 'C4'`로 건수를 남기고 `note`는 로그에 쓰지 않는다.

### 단계 8. 테스트: estimate와 overrides CLI — 예시 기반, SEC2, P4-10
- [x] `tests/test_estimate.py`: 합성 DB와 합성 크롭 이미지로 `pending`(묶음 이미지가 만들어짐, 항목에 숨기는 값이 없음, 순서, 크롭이 없는 건물, `--limit`, `--redo`), `record`(기록되고 파일이 만들어짐, 한 건이 틀리면 전체 거부, 출력에 대장·OSM 값이 없음), `report`(상태·일치율 숫자가 만든 입력과 맞음, 눈가림 깨진 건물 제외), `plan`(묶음 크기, 학교 건물 쌍 수, 카메라 값이 `review`의 값과 같음, 같은 입력이면 파일이 같음), `compose`(쌍 이미지 크기, 4:3보다 좁은 캡처 거부, 크기·형식이 잘못된 파일 거부, 경로 이동 문자가 든 ID 거부)를 확인한다.
- [x] `tests/test_overrides.py`: `set`·`unset`·`list`·`export`·`import`의 명령줄 수준(값 읽기, 잘못된 입력의 오류 출력, 파일이 갱신됨, 복구 연습: 새 DB에 불러와 같은 최종값).

### 단계 9. U2 연동 — BR-9, U2 BR-2.4·2.7
- [x] `src/layout.py`: `building_item(building, frame, cfg, eff=None)`. `eff`가 있으면 높이·층수·벽 색을 그것으로 정하고 속성 `HeightBasis`, `FloorsBasis`(층수가 없으면 없음), `WallColor`, `Review`(사유를 `-`로 이은 글자, 없으면 없음; Luau 허용 문자에 쉼표가 없어서 기능 설계의 쉼표 대신 `-`)를 더한다. `eff`가 없으면 U2의 기존 값이 나온다(`building_height_m`, 색 `LOOKS["building"]`). `Item.color`는 벽 색의 RGB다.
- [x] `src/build_luau.py`: `plan_cell(..., estimates=None, overrides=None)`가 건물마다 `judgement.effective_building`을 불러 `building_item`에 넘긴다. `item_literal`은 `b`(높이 근거), `a`(층수 근거), `c`(벽 색 키), `v`(확인 목록 사유) 키를 더하고, `render_chunk`는 쓰인 벽 색의 RGB를 `LOOKS.walls = {키 = {r,g,b}}`로 덩어리마다 한 번만 보낸다. 모든 새 글자는 기존 `SAFE_TEXT` 검사를 통과해야 한다. manifest에 `flagged`(확인 목록에 오른 건물 수)와 `judged`(판단 행이 있는 건물 수)를 더한다. `build_cell`이 `db.estimates_in_cell`, `db.overrides_by_building`을 읽는다.
- [x] `studio/Builder.luau`: `it.c`가 있고 `looks.walls[it.c]`가 있으면 그 색으로 칠하고, 속성 `HeightBasis`(`it.b`), `FloorsBasis`(`it.a`), `WallColor`(`it.c`), `Review`(`it.v`)를 있을 때만 단다. 다른 동작은 바꾸지 않는다(`loadstring` 금지 유지).
- [x] `tests/test_layout.py`, `tests/test_build_luau.py`를 고친다: 판단·보정이 없으면 항목의 높이·색이 U2의 기존 값과 같다(BR-9.1, 9.2), 판단·보정이 있으면 높이·색·속성이 바뀐다, 새 글자가 코드 주입 방지를 통과한다(따옴표, 줄바꿈이 든 `Review`나 색 키는 건너뛰어짐), 행 순서를 섞어도 파일이 글자까지 같다(P2-8이 최종값 입력에서도 성립, BR-9.4), manifest의 `flagged`, `judged`. 기존 테스트가 통과하는지 확인한다.
- [x] `Workspace.MCP_Test` 안에서만 시험한다: 새 `Builder`를 `MCP_Test` 아래 `ModuleScript`에 `Source`로 넣고(진짜 `ServerStorage/MapBuilder`는 건드리지 않음) `Builder.root`를 시험용 폴더로 정한 뒤, 판단·보정이 섞인 합성 칸의 덩어리를 실행해 색과 새 속성이 맞는지, 기존 속성과 `verify`가 그대로인지, 재생성 결과가 같은지 읽어 확인한다. 끝나면 시험 물체를 모두 지우고 `MCP_Test`가 처음 상태(`TestBase`, `TestBuilding`)인지 확인한다.

### 단계 10. 실제 데이터 읽기 전용 확인 — 눈가림 유지
- [x] 첫 칸 실제 DB(`data/map.db`)로: ① `build_luau.py`를 돌려 높이와 색이 예전 규칙과 모든 건물에서 같은지(판단·보정이 없는 상태이므로 같아야 한다) 건수만 인쇄해 확인한다. 항목 수와 덩어리 수는 예전과 같아야 한다(162개, 덩어리 4개). ② `estimate.py pending --cells 8930e0af13bffff --limit 3`로 항목 3개와 묶음 이미지 3장이 만들어지는지와 항목에 대장·OSM 값이 없는지만 확인한다(묶음 이미지 내용은 열어 보지 않는다). `report`와 `plan`은 실제 DB에 돌리지 않는다. 어긋나면 멈추고 알린다.

### 단계 11. 버전 일치 검사와 문서 — M6, N-U4-1
- [x] `tests/test_versions.py`가 `estimate.py`(와 `overrides.py`의 빈 의존성)를 포함하도록 확장한다(인라인 고정이 `==`, `pillow`, `h3`, `shapely` 버전이 `tests/requirements.txt`와 같음, 목록이 스크립트 파일과 일치). CI는 바꾸지 않는다.
- [x] `CLAUDE.md`: 실행 명령(`estimate.py pending|record|report|plan|compose`, `overrides.py set|unset|list|export|import`, `--selftest`), 눈가림 주의, 현재 상태, 다음 할 일.
- [x] `aidlc-docs/construction/u4-judgement-corrections/code/code-summary.md`: 만든 파일, 공개 함수, Claude용 절차(판단 흐름: `pending` → 보고 판단 → `record` → `report`, 비교 쌍 흐름: `plan` → Studio 시야각 설정과 카메라 읽기 → 쌍마다 `screen_capture`(항상 `camera_position`, `look_at_position`) → `compose` → 카메라 되돌리기, 보정 흐름, 복구), 설계 대비 차이(`Review` 구분자, `overrides_dir` 설정, 쌍 이미지의 라벨 띠, P4-10의 순서 예외, `compose` 하위 명령)(마크다운만).

### 단계 12. 생성 후 점검 (본 실행은 Build and Test에서)
- [x] 모든 Python 파일이 컴파일되는지 확인한다. 전체 테스트를 여러 시드(1, 7, 42, 2026, 99999)로 돌려 기존 테스트가 그대로 통과하는지 확인한다. 의도적으로 코드를 망가뜨려(예: 층수 표 한 칸, 보정 우선순위, 눈가림 필드, 내보내기 정렬, 원자성) 테스트가 잡아내는지 몇 가지 확인한다.
- [x] 코드와 문서에 인증키나 키처럼 보이는 값이 없는지 검색한다. `captures/`, `data/`가 git에 안 들어가는지, `overrides/`가 들어가는지 확인한다.
- [x] 이 계획과 만든 파일 목록을 대조해 빠진 것과 중복 파일이 없는지 확인한다. 이 계획의 `[x]`를 모두 표시하고 `aidlc-state.md`를 갱신한다.
- 첫 칸의 실제 판단, `MapBuilder` 갱신과 칸 재생성, 비교 쌍과 사용자 확인, 보정, 복구 연습, 프레임 측정은 Build and Test에서 한다.

## 범위 요약
- **새 파일**: `src/judgement.py`, `src/review.py`, `src/estimate.py`, `src/overrides.py`, `tests/test_judgement.py`, `tests/test_review.py`, `tests/test_u4_db.py`, `tests/test_estimate.py`, `tests/test_overrides.py`, 코드 요약 문서.
- **수정 파일**: `src/db.py`, `src/common.py`, `config.toml`, `src/layout.py`, `src/build_luau.py`, `studio/Builder.luau`, `tests/generators.py`, `tests/test_common.py`, `tests/test_layout.py`, `tests/test_build_luau.py`, `tests/test_versions.py`, `CLAUDE.md`.
- **총 12단계**. 단계 9의 Studio 시험은 `MCP_Test` 안으로, 단계 10의 실제 DB 접근은 읽기 전용으로 한정하고, 어긋나면 멈춰서 알린다.

## 기능 설계 대비 조정 (미리 알림)
1. `Review` 속성의 구분자는 쉼표가 아니라 `-`다(Luau 코드에 들어가는 글자의 허용 문자에 쉼표가 없고 코드 주입 방지를 느슨하게 하지 않으려고).
2. `overrides_dir`(기본 `overrides`)를 설정에 둔다. NFR M5의 설정 목록에 없던 항목이다.
3. 비교 쌍 이미지는 타일 640×480 위에 라벨 띠 56 px을 붙인다(기능 설계의 "1280×480과 위에 라벨"을 구체화).
4. P4-10의 "목록 내용이 같다"는 항목 내용에 대한 속성이고, 순서는 BR-1.2대로 "층수·높이가 모두 없음"에 따라 바뀐다.
5. 하위 명령 `compose`를 추가한다(Studio 캡처 파일과 크롭을 합성하는 일; NFR의 명령 목록 `pending|record|report|plan`에 빠져 있었다).
6. 순수 모듈은 `judgement.py`(검증·최종값·내보내기 형식)와 `review.py`(눈가림·순서·카메라·일치율) 둘로 나눈다. `effective_building`은 이 모듈의 함수이고 `db.effective_buildings`가 DB에서 읽어 불러온다.
