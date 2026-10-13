# U4 판단·보정 — Code Summary

코드 생성 계획 12단계를 모두 실행했다(2026-10-13). 마크다운 요약만 두고 코드는 저장소 루트의 `src/`, `studio/`, `tests/`에 있다.

## 만든 파일

| 파일 | 내용 |
|---|---|
| `src/judgement.py` | 입출력 없음. 판단·보정 검증(`validate_judgement`, `validate_override`), 최종값 `effective_building`(층수 표 BR-3, 높이 BR-4, 외관 BR-5, 확인 목록 사유 BR-7.1), `wall_rgb`, 내보내기 형식 `export_payload`와 `parse_export` |
| `src/review.py` | 입출력 없음. 눈가림 항목 `blind_item`, 판단 순서 `pending_order`, 비교 묶음 `review_batches`, 방위 `camera_bearing`, 시야각 변환 `h_to_v_fov`, 카메라 값 `camera_for_view`, 캡처 자르기 상자 `capture_crop_box`, 일치율 `agreement` |
| `src/estimate.py` | C4 명령줄: `pending`, `record`, `report`, `plan`, `compose`, `--selftest`. 인라인 의존성 `pillow==12.3.0`, `h3==4.5.0`, `shapely==2.2.0` |
| `src/overrides.py` | C5 명령줄: `set`, `unset`, `list`, `export`, `import`, `--selftest`. 인라인 의존성 없음 |
| `tests/test_judgement.py` | P4-1, P4-2, P4-3, P4-7, P4-8, P4-9, P4-12 (순수 모듈) |
| `tests/test_review.py` | P4-10, P4-11, P4-13, P4-14, P4-15, 캡처 자르기 상자 |
| `tests/test_u4_db.py` | P4-3, P4-4, P4-5, P4-6, P4-7, P4-9(원자성), P4-16, 내보내기와 불러오기 파일 규칙 |
| `tests/test_estimate.py`, `tests/test_overrides.py` | 명령줄 수준 예시 테스트(합성 DB와 합성 이미지), 복구 연습 |

## 고친 파일

| 파일 | 바뀐 것 |
|---|---|
| `src/db.py` | 테이블 `estimates`, `overrides`와 함수 `record_judgements`, `set_override`, `unset_override`, `estimates_in_cell`, `overrides_in_cell`, `overrides_by_building`, `views_with_heading`, `effective_buildings`, `export_cell`, `import_file`, `building_cell` |
| `src/common.py`, `config.toml` | 설정 `floor_height_min_m`, `floor_height_max_m`, `review_batch_size`, `sheet_tile_w`, `sheet_tile_h`, `sheet_jpeg_quality`, `overrides_dir`, `blind_broken`, 벽 색표 `wall_colors` |
| `src/layout.py` | `building_item(..., eff=None)`: 최종값으로 높이·층수·벽 색을 정하고 속성 `HeightBasis`, `FloorsBasis`, `WallColor`, `Review`를 단다 |
| `src/build_luau.py` | `plan_cell(..., estimates, overrides)`가 건물마다 최종값을 쓴다. 항목 키 `b`, `a`, `c`, `v`. 덩어리마다 쓰인 벽 색의 RGB를 `LOOKS.walls`로 한 번 보낸다. 새 글자도 `SAFE_TEXT` 검사(`TEXT_ATTRS`). manifest에 `judged`, `flagged` |
| `studio/Builder.luau` | 벽 색(`it.c`)과 새 속성을 처리한다. 다른 동작은 그대로 |
| `tests/generators.py`, `tests/test_common.py`, `tests/test_db.py`(예전 가짜 `overrides` 표 대신 진짜 표 사용), `tests/test_layout.py`, `tests/test_build_luau.py`, `tests/test_versions.py` | 생성기, 새 설정, 진짜 `overrides` 테이블, 최종값 입력, 새 스크립트의 고정 검사 |
| `CLAUDE.md` | 명령, 눈가림 주의, 현재 상태, 다음 할 일 |

## Claude용 절차

### 판단 (눈가림, BR-1, BR-2)
1. `uv run src/estimate.py pending --cells <칸ID> --limit 10`: 항목이 JSON 한 줄씩 나오고 묶음 이미지는 `captures/<칸ID>/sheets/<건물 ID>.jpg`에 만들어진다. 항목에는 건물 ID, 이름, 위치, 박스 크기, 크롭 순위와 방향만 있다.
2. 묶음 이미지를 하나씩 읽어(`Read`) 층수(지상층, 필로티는 세고 옥탑·반지하는 안 센다), 확신도(high/medium/low), 벽 색(색표의 이름), 지붕 모양을 판단한다. 못 세면 `floors_seen`을 비우고(필요하면 `height_est_m`), **판단하는 동안 DB와 `report`, `plan`을 열지 않는다.**
3. `judgements.json`(목록)을 쓰고 `uv run src/estimate.py record --file judgements.json`. 하나라도 틀리면 전부 거부된다. 기록하면 `overrides/<칸ID>.json`이 갱신된다.
4. `pending`에서 남은 건수가 0이 될 때까지 반복한다. 끝나면 `report`로 상태, 일치율(`blind_broken` 제외), 확인 목록을 본다.

### 비교 쌍 (BR-7)
1. `uv run src/estimate.py plan --cells <칸ID>`로 `data/build/<칸ID>/review.json`을 만든다(묶음 12개씩, 쌍마다 카메라 값).
2. Studio에서 뷰포트 카메라(CFrame, FieldOfView)를 읽어 두고 `workspace.CurrentCamera.FieldOfView = 83.58`로 정한다. 사용자는 Studio 창을 앞에 두고 4:3보다 넓게 하며 뷰포트를 건드리지 않는다.
3. 쌍마다 `screen_capture`를 `camera_position`, `look_at_position`(plan의 `camera`)과 함께 부른다. 인자 없는 호출은 다른 시점을 찍는다. 도구 결과의 파일 경로를 모아 `{"<건물 ID>__<순위>": "<경로>"}` JSON을 만든다.
4. `uv run src/estimate.py compose --cells <칸ID> --captures captures.json` → `captures/<칸ID>/review/<건물 ID>__<순위>.jpg`(1280×536). 묶음마다 파일 링크를 사용자에게 준다. 끝나면 카메라를 되돌린다.

### 보정과 재생성
- 사용자가 어긋난 건물을 말하면 사진을 다시 보고 같이 정해 `uv run src/overrides.py set --building ... --field ... --value ... --reason "..."`(사유에 개인 정보 금지). 되돌리려면 `unset`.
- 한 묶음이 끝날 때마다 `uv run src/build_luau.py --cells <칸ID>`로 덩어리를 다시 만들고 Studio에서 `Builder.begin`부터 실행한다(`Manual`은 그대로).
- **`ServerStorage/MapBuilder`의 `Source`를 바꿀 때는 모듈 인스턴스를 새로 만든다(`Clone` 후 원본 `Destroy`).** Studio는 `require` 결과를 인스턴스마다 캐시해서 `Source`만 바꾸면 예전 코드가 계속 실행된다(2026-10-13 Build and Test에서 겪음: `verify`는 통과하는데 새 속성과 벽 색이 안 달렸다). 갱신한 뒤에는 시험용 폴더(`Builder.root`)에 건물 하나를 만들어 색과 속성이 달리는지 먼저 확인하고 덩어리를 실행한다.

### 복구 (BR-8.6)
DB를 복사해 두고 새 DB에 `cells.py`, `register.py`를 다시 돌린 뒤 `uv run src/overrides.py import --file overrides/<칸ID>.json`. 복사해 둔 DB와 최종값(`effective_buildings`)이 같아야 한다. 이 흐름은 `tests/test_overrides.py`에서 합성 데이터로 확인했다.

## 확인한 것

- 테스트 412개 통과(시드 1, 7, 42, 2026, 99999). 일부러 코드를 망가뜨린 12가지(층수 표 한 칸, 높이 보정 무시, 층수가 바뀌었는데 대장 높이 유지, 눈가림 필드 노출, 내보내기 행 정렬, `record` 일부만 저장, `set_override` 멱등 깨짐, 눈가림 깨진 건물 통계 포함, 새 글자 검사 제거, `Review` 구분자를 쉼표로, 내보내기를 제자리에 쓰기, 사진 없는 건물을 계획에 넣기)를 모두 테스트가 잡았고 원래대로 되돌렸다.
- 새 Builder를 `Workspace.MCP_Test`의 `NewBuilder`(길이 7,405바이트로 파일과 같음)에 넣고 합성 칸 덩어리를 실행했다(`require` 줄과 `Builder.root`만 시험용으로 바꿈): 벽 색 RGB, 속성(`HeightBasis`, `FloorsBasis`, `WallColor`, `Review`)이 의도대로, `other`는 밝은 회색이고 이름은 유지, 판단 없는 속성은 없음, `verify` 문제 없음, 다시 만든 결과가 같음, `Manual`의 같은 `BuildingId`가 이김. 끝난 뒤 시험 물체를 모두 지웠고 `MCP_Test`는 처음 상태(`TestBase`, `TestBuilding`), 진짜 `Auto/8930e0af13bffff`는 169개 그대로, `Manual` 0개, `ServerStorage/MapBuilder`는 건드리지 않았다.
- 첫 칸 실제 DB 읽기 전용: 건물 122개 중 121개는 예전 규칙과 같은 높이, 1개는 층당 높이가 허용 범위 밖이라 층수 × 3.4 m와 `height_out_of_range`(설계 BR-4.2대로). 덩어리 파일 4개 6.0/9.4/9.4/2.7 KB(속성 키가 늘어서 예전 5.4/6.6/6.6/1.9 KB보다 커졌고 10 KB 경고선에 가깝다). `estimate.py pending --limit 3`는 항목 3개와 묶음 이미지 3장을 만들었고(이미지는 열어 보지 않았다) 항목에 대장·OSM 값이 없었다. `report`와 `plan`은 실제 DB에 돌리지 않았다.

## 설계·계획 대비 차이

1. `Review` 속성 구분자는 쉼표가 아니라 `-`(`conflict-filled`). Luau 글자 허용 목록에 쉼표가 없다. (계획에서 미리 알림)
2. `overrides_dir` 설정을 추가했다. 쌍 이미지는 타일 640×480 위에 라벨 띠 56 px(1280×536)이다. 하위 명령 `compose`가 추가됐다. 순수 모듈은 `judgement.py`와 `review.py` 둘이다. P4-10은 항목 내용에 대한 속성이고 순서만 "층수·높이가 모두 없음"에 따라 바뀐다. (계획에서 미리 알림)
3. Pillow의 폭탄 이미지 한도는 전역 `Image.MAX_IMAGE_PIXELS`를 건드리지 않고 `estimate.py`가 이미지를 열 때 크기를 먼저 보고 5,000만 픽셀 넘으면 거부한다(`open_image`). 전역을 바꾸면 같은 프로세스의 `capture.py` 설정(800만)과 부딪쳐서 테스트가 깨졌다. NFR의 "명시적으로 설정"은 이 점검으로 지킨다.
4. `db.unset_override`는 불리언이 아니라 지운 보정의 칸 ID(없으면 `None`)를 돌려준다(명령줄이 그 칸의 파일을 다시 쓰려고).
5. `plan`은 크롭이 없는 건물을 묶음에서 뺀다(비교할 사진이 없다). 칸의 `unjudged` 건물은 판단 전이라 `Review=unjudged`가 붙고 높이는 대장 값이다.
6. `estimate.py`의 `record`는 판단한 건물의 칸마다 내보내기 파일을 다시 쓴다. 판단 내용(메모 포함)과 보정 사유는 로그와 `collection_runs`에 남지 않고 건수만 남는다.

## 남은 일 (Build and Test)

첫 칸 122개를 눈가림으로 판단하고 `report`로 일치율을 본다. `ServerStorage/MapBuilder`를 새 Builder로 갱신해 칸을 다시 만든다. 비교 쌍을 12개씩 같이 확인하고 보정한다. 복구 연습, 프레임 측정, 커밋 시점(Q3=A)은 NFR 문서대로 한다.
