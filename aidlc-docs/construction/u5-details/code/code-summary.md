# U5 디테일 — Code Summary

코드 생성 계획 10단계를 실행했다(2026-10-13). 마크다운 요약만 두고 코드는 저장소 루트의 `src/`, `studio/`, `tests/`에 있다.

## 만든 파일

| 파일 | 내용 |
|---|---|
| `src/details_rules.py` | 입출력 없음, 표준 라이브러리만. 세부 어휘와 검증(`validate_detail`), 내보내기 형식(`export_details_payload`, `parse_details_export`), 메모 검색(`from_note`, 단어 경계), 합치기(`merged_details`: 세부 > 메모 > 기본값), 원형(`archetype`), 공공 기관(`is_public_name`), 간판 글자(`SIGN_TEXT`, `sign_string`), 가상 이름(`sign_name`, 접두어 40, 풀 6, `REAL_BRANDS`, `PLACE_NAMES`), 해시(`pick`), `PALETTE`, `MATERIALS`(45), `SHAPES`, 지붕 재질표, `wall_material`, `band_color`, 치수 상수 `DIMS` |
| `src/layout_details.py` | 입출력 없음(h3·shapely). 중복 제거(`dedupe_buildings`), 다중 박스(`outline_to_boxes`), 몸체(`make_body`, `Body`), 도로 쪽 면·가림(`facing_of`, `occluded_faces`, `resolve_body`), 빈 구간(`free_spans`), 지붕(`roof_items`), 띠·난간벽·난간·기단·창·띠창·옥상(`body_items`), 외장·전면(`front_items`), 마당(`yard_items`), 간판(`sign_items`), 박스 항목(`box_items`), 도로(`streets_of`, `junctions`, `sidewalk_pieces`, `street_items`: 인도 조각·연석·노면·횡단보도·정지선·전봇대·전선·가로등·가로수·차·스쿨존·볼라드·함) |
| `src/details.py` | C6 명령줄(의존성 없음): `pending`, `record`, `list`, `export`, `import`, `--selftest`. 실행 기록 `C7` |
| `tests/test_details_rules.py` | P5-8, P5-10, P5-16(형식), P5-17과 예시(어휘, 메모, 원형, 글자, 이름표, 팔레트) |
| `tests/test_layout_u5.py` | P5-2~P5-7, P5-9, P5-11~P5-13, P5-15, P5-18, P5-19와 예시(12×10 빌라, 모임지붕 치수, 100 m residential, 교차점, 인도 끊기) |
| `tests/test_u5_db.py` | 세부 기록의 원자성·멱등(P5-16), 내보내기·불러오기 왕복, 고아, 재수집 안전 |
| `tests/test_details.py` | 명령줄 예시(`pending`·`record`·`list`·`export`·`import`, 거부) |
| `details/8930e0af13bffff.json` | 첫 칸 세부 판단 116건(git 포함) |

## 고친 파일

| 파일 | 바뀐 것 |
|---|---|
| `src/layout.py` | `Item`에 `owner`, `shape`, `color_name`, `text`, `ink`, `faces`, `reflectance`, `shadow`, `collide`(기본값 있음)와 `casts_shadow`·`collides`; `LOOKS`에 `roof`·`facade`·`sign`·`prop`, 땅 `Concrete`, 인도 `Brick`; `ORDER` 10단계; `KIND_DEFAULTS`; `box_of_points`(다중 박스가 재사용); `sidewalk_sides`가 `sidewalk:both/left/right`와 `residential` 양쪽을 읽음; `building_item`이 `color_name`을 실음 |
| `src/build_luau.py` | `item_literal` 새 키 `i p m c o t u md j g l`(기본과 다를 때만), 색표에 모든 색 이름, `plan_cell(..., details)`의 U5 흐름(중복 제거 → 몸체·원형 → 박스 → 도로 쪽 면·가림 → 항목들 → 도로·교차점·가로 → 정렬 → 덩어리), manifest에 `buildings_built`, `boxes`, `building_ids`, `duplicates_dropped`, `details_used`, `no_facing`, `far_facing`, `signs`, `labels`, `parts_total`, `junctions`와 새 설정 키; `build_cell`이 `details`를 읽음; 경고선 15 KB |
| `studio/Builder.luau` | 폴더 10개, `Skipped_<kind>`, 모양(`Shape`)·재질·색표·반사율·소유자(`BuildingId`)·그림자·충돌, 세운 원통 90° roll, 간판 `SurfaceGui`+`TextLabel`(양면), `verify`(kind별, `labels`, `building_ids`로 Manual 미사용 ID). `:Destroy()` 한 곳, 기하 없음 |
| `src/db.py` | 표 `details`(`db.TABLES` 밖), `record_details`, `details_in_cell`, `details_by_building`, `export_details`, `import_details`, `orphans`에 `details` |
| `src/common.py`, `config.toml` | `pole_spacing_m`, `lamp_spacing_m`, `tree_spacing_m`, `car_spacing_m`, `school_zone_m`, `roof_pitch_deg`, `window_faces`, `details_dir`; `chunk_size` 50 → 70 |
| `tests/generators.py` | `# --- U5 details ---`: `notes`, `detail_rows`, `body_cases`, `SIGN_TEXTS` |
| `tests/test_build_luau.py`, `tests/test_layout.py`, `tests/test_common.py`, `tests/test_versions.py` | U5 규칙대로 바뀐 기대값(항목 수, 순서, 색표, residential 인도, 땅 재질), 새 설정 키의 틀린 예시, `details.py` 의존성 없음·`details_rules.py` 표준 라이브러리 검사 |
| `CLAUDE.md` | 명령, 현재 상태, 다음 할 일 |

## Claude용 절차

### 세부 판단 (BR-7)
1. `uv run src/details.py pending --cells <칸ID> --limit 10`: 세부 행이 없는 건물과 묶음 이미지 경로(`captures/<칸ID>/sheets/gis_….jpg`, U4가 만든 것).
2. 묶음 이미지를 읽고 7개 필드(`finish`, `ground_use`, `stair`, `bay`, `balcony`, `roof_color`, `rooftop`)를 어휘대로 적는다. 안 보이면 비운다. 메모에 사람·번호판·실제 상호 금지.
3. `details.json`(목록)을 쓰고 `uv run src/details.py record --file details.json`. 하나라도 틀리면 전부 거부. 기록하면 `details/<칸ID>.json`이 갱신된다.

### 생성과 확인
1. `uv run src/build_luau.py --cells <칸ID>` → `data/build/<칸ID>/chunk-NNN.luau`(첫 칸 70개)와 manifest.
2. `ServerStorage/MapBuilder`가 `studio/Builder.luau`와 같은지 길이로 확인(교체는 새 ModuleScript + 원본 Destroy).
3. 덩어리를 순서대로 `execute_luau`(Edit). 마지막 덩어리가 `Builder.finish`를 돌려준다.
4. `Builder.verify(cell, manifest.counts, [표본 이름], manifest.building_ids)`: `ok`, `problems`, `unknown_manual`.
5. Manual 학교는 `Workspace/Manual/School` 아래에만 만든다(BR-12.2).

## 설계·계획 대비 차이

1. U5 기하를 `src/layout.py`에 더하지 않고 새 모듈 `src/layout_details.py`에 두었다(`layout.py`는 `Item`·`LOOKS`·`ORDER`·`sidewalk_sides`·`box_of_points`만 바뀜). 파일 하나가 1,100줄이 되는 것을 피하려는 선택이고 규칙은 같다.
2. 간판 `MaxDistance`는 리터럴 키 `md`로 보낸다(BR-14.2에는 없던 키; `x`는 위치라 한 글자 키가 남지 않았다). Builder는 `it.md or 200`.
3. `pick`은 crc32 뒤에 정수 혼합 단계를 둔다. crc32는 선형이라 같은 소유자의 `p0`·`w0` 해시가 상수 XOR 차이로 묶여 접두어×업종어 480쌍 중 120쌍만 나왔다(혼합 뒤 480/480). 결정성은 그대로다.
4. `chunk_size` 기본값은 80이 아니라 70이다. 80에서 건물 상자가 많은 덩어리가 15.1 KB로 경고선을 넘었다(70은 최대 13.3 KB).
5. 중복 제거는 겹치는 상대가 여럿이면 ID가 가장 작은 쪽을 "남긴 ID"로 적는다(BR-1.2). 옥상 물체는 박스가 6×5 m 이상일 때만 만들고 물탱크는 박스 안에 들어갈 때만 만든다(작은 평지붕에 옥탑이 걸리지 않게; BR-4.4에 없던 보호 조건).
6. 주차 차량은 교차점 6 m뿐 아니라 그 도로에 붙은 교차점의 횡단보도 띠(`w_max/2 + 5`)에서 2 m 안도 비운다(BR-11.5의 "횡단보도 2 m 안" 구현).
7. 인도 조각이 교차점에서 끊기지 않은 통째 조각일 때만 U2처럼 길이에 인도 폭을 더한다(이음새 메움). 끊긴 조각은 정확한 길이다.
8. `details.py pending`은 묶음 이미지를 새로 만들지 않는다(U4 `estimate.py pending`이 만든 것을 쓴다).
9. 첫 칸 결과: 항목 4,888(건물 상자 127 = 116동 + 다중 박스 11, 지붕 161, 외장 2,895, 간판 210(글자 면 257), 가로 1,442, 인도 20), 덩어리 70(최대 13.3 KB), 중복 제거 6, 세부 적용 111(몸체 아님 5 제외), 도로 쪽 면 없음 0, 8 m 넘게 떨어진 몸체 16, 경고 0. 계획 추정(약 6,000)보다 적다.

## 확인한 것

- 테스트: 기존 묶음 500개 통과(U5 규칙대로 기대값을 고친 7개 포함). 새 U5 테스트는 Build and Test 요약에 수치를 적는다.
- Studio(`MCP_Test/U5_T2`, 지움): 새 Builder로 항목 16개(건물 2, 지붕 6, 외장 3, 간판 2, 가로 3)를 만들어 `verify` 통과, Manual의 `gis:2`가 몸체와 창을 함께 건너뜀(`Skipped_building 1`, `Skipped_facade 1`), 오타 ID `gis:999`가 `unknown_manual`에 보고됨, 세운 원통의 길이축이 Y, 간판 글자 "소망부동산"·`MaxDistance 300`·양면 간판 GUI 2개, 창 반사율 0.25·그림자 없음·충돌 없음, 띠 재질 `Brick`, 모서리 쐐기 모양, 소유자 속성.
- `ServerStorage/MapBuilder`는 `studio/Builder.luau`와 같다(11,459바이트).
