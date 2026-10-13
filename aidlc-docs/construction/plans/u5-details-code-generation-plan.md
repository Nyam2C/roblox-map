# U5 디테일 — Code Generation Plan

이 계획이 코드 생성의 단일 기준이다. 대상: U5 Functional Design(규칙 BR-1~17, 속성 P5-1~19)과 NFR Requirements(승인, 2026-10-13). 브라운필드이므로 기존 파일은 제자리에서 고친다(복사본 없음). 코드는 저장소 루트(`src/`, `studio/`, `tests/`, `config.toml`), 문서는 `aidlc-docs/construction/u5-details/code/`. 상시 승인(사용자, 2026-10-13)에 따라 계획 승인과 코드 승인은 Claude가 기록한다.

## 유닛 문맥
- 구현하는 요구사항: FR-3(가로시설 생성), FR-4(지붕, 층 구분, 창·문, 간판, 대표 건물 수작업), FR-5(재질), FR-6(가상 이름), FR-7(주거 건물), NFR-1(프레임 수), NFR-3(같은 결과), NFR-4(사진은 로컬), NFR-8(속성 테스트).
- 의존: U1 `buildings`·`street_features`, U4 최종값·메모, U2 `layout.py`·`build_luau.py`·`Builder.luau`.
- 이 유닛이 소유하는 데이터: 표 `details`, 파일 `details/<칸ID>.json`, `data/build/<칸ID>/`의 새 manifest 필드.
- 인터페이스 약속: `layout.Item`에 필드 추가(기본값 있음, 기존 호출 그대로), `build_luau.plan_cell(..., details=None)`, `db.details_*`, `Builder.add`의 새 키는 전부 선택.

## 단계

- [x] **1. 설정과 공용 모듈** — `src/common.py`: `DEFAULTS`·`RANGES`에 `pole_spacing_m 30`, `lamp_spacing_m 30`, `tree_spacing_m 7`, `car_spacing_m 8`, `school_zone_m 50`, `roof_pitch_deg 25`, `window_faces "all"`, `details_dir "details"`, `chunk_size` 80; 검증(`window_faces ∈ {all, front}`, `details_dir` 비어 있지 않음). `config.toml` 같은 값. `tests/test_common.py` 기본값 일치·틀린 예시 추가. (BR-14.9, N-U5-8)
- [x] **2. 데이터 계층** — `src/db.py`: 표 `details`(`db.TABLES` 밖), `record_details`(전건 검증, 원자성, 같은 내용 재기록 무변화), `details_in_cell`, `details_by_building`, `export_details`(임시 파일 + 바꿔치기), `import_details`(전체 검증, 고아 보고), `orphans`에 `details` 추가. (BR-7.4·7.5)
- [x] **3. 순수 규칙 모듈** — `src/details_rules.py`(표준 라이브러리만): 어휘·검증(`validate_detail`), 내보내기 형식(`export_details_payload`, `parse_details_export`), 메모 검색(`from_note`), 합치기(`merged_details`: 세부 > 메모 > 기본값), 원형(`archetype`), 공공 기관(`is_public_name`), `SIGN_TEXT`·`sign_string`, 이름 생성(`sign_name`, 접두어 40, 풀 6, `REAL_BRANDS`, 지명 금지), `PALETTE`, `MATERIALS`(45), `SHAPES`, `DIMS`, 재질 표(`wall_material`), 색 파생(`band_color`), 해시(`pick`). (BR-1.5·1.6, 3.1, 7, 10)
- [x] **4. 기하 모듈** — `src/layout.py`: `Item` 필드(`owner`, `shape`, `color_name`, `text`, `ink`, `faces`, `reflectance`, `shadow`, `collide`), `LOOKS`·`ORDER`·`TOPS` 확장과 땅·인도 색 개정, `dedupe_buildings`, `outline_to_boxes`, `is_body`·`floors_and_fh`, `facing_of`(행 전체 기하, `setback_s`, `along`), `occluded_faces`, `free_spans`, `roof_items`, `body_items`(띠·난간벽·난간·기단·창·띠창·옥상), `front_items`(계단실·돌출창·발코니·문·캐노피·셔터·실외기·가스관·전면·처마), `yard_items`, `sign_items`, `junctions`, `split_sidewalks`(+연석), `marking_items`, `crosswalk_items`, `street_prop_items`(전봇대·전선·가로등·가로수·차·스쿨존·볼라드·함), `sidewalk_sides` 개정(`sidewalk:*`, residential). 쐐기 축 상수. (BR-1~6, 8~11, 14)
- [x] **5. 덩어리 생성** — `src/build_luau.py`: `item_literal` 새 키(`i p m c o t u j g l`), `sign_string`, `TEXT_ATTRS`, 색표(`walls`에 모든 색 이름), `plan_cell(..., details)` 흐름(중복 제거 → 몸체·원형 → 박스 → 도로 조각·교차점·인도 끊기 → 도로 쪽 면 → 세부 합치기 → 항목들 → 정렬 → 덩어리), manifest 새 필드, `build_cell`이 `details`를 읽음. (BR-14.2·14.6·14.7·14.8)
- [x] **6. Studio 모듈** — `studio/Builder.luau`: 폴더 4개, `Skipped_<kind>`, 모양·재질·반사율·소유자·그림자·충돌, 세운 원통 roll, 간판 GUI(양면), `verify`(kind별, `labels`, `building_ids`로 Manual 미사용 ID). `:Destroy()` 한 곳, 기하 없음. (BR-14.4·14.5, 12.5)
- [x] **7. 세부 명령** — `src/details.py`(의존성 없음): `pending`(묶음 경로, `--redo`), `record`(파일 또는 표준 입력, 2 MB), `list`, `export`, `import`, `--selftest`; 실행 기록 `C7`. (BR-7.4·7.5, N-U5-9)
- [x] **8. 테스트** — `tests/generators.py` `# --- U5 details ---`(세부 행, 원형별 건물 행, 교차 도로망, 간판 글자, 메모); `tests/test_details_rules.py`(P5-8, P5-10, P5-16 형식, P5-17 팔레트, 예시); `tests/test_layout_u5.py`(P5-2~7, 9, 11~13, 15, 18, 19, 예시); `tests/test_build_luau.py` 갱신(P5-1, P5-14, 기존 테스트 조정); `tests/test_u5_db.py`(P5-16 DB, 원자성, 고아); `tests/test_details.py`(명령 예시); `tests/test_versions.py`(`details.py` 의존성 없음, `details_rules.py` 표준 라이브러리만, Builder 검사 유지). 시드 1, 7, 42, 2026, 99999.
- [x] **9. 문서** — `aidlc-docs/construction/u5-details/code/code-summary.md`, `CLAUDE.md`(명령·현재 상태), `aidlc-docs/inception/application-design/components.md`에 C6 확장 한 줄.
- [x] **10. 첫 칸 적용(읽기 전용 확인)** — `details.py record`로 116건 기록, `build_luau.py --cells 8930e0af13bffff` 돌려 manifest 수치와 덩어리 크기 확인(Studio 실행은 Build and Test).

## 코드 망가뜨리기 목록(Build and Test에서 ≥ 12)
중복 제거 비교 뒤집기 / 다중 박스 상한 무시 / 모서리 쐐기 yaw 하나 바꾸기 / 띠 y 한 층 어긋남 / 창 창턱 0.9 → 0 / 빈 구간 무시 / 가게 판정에 `storey` 매칭 / 간판 글자 검사 제거 / 접두어 표에 금지어 삽입 / 슬롯 첫 위치 0 / 교차점을 끝점으로만 / 인도 끊기 틈 폭 / 리터럴 `i` 누락 / 색표에서 이름 빠짐 / `record` 일부만 저장 / 내보내기 키 정렬 해제 / `sidewalk:both` 무시.

### Build and Test 결과 (2026-10-13, 16곳)

| # | 망가뜨린 곳 | 처음 | 테스트 추가 뒤 |
|---|---|---|---|
| L1 | `_pieces_sorted` 조각 버리기 0.01 m² → 1e-9 | 안 잡힘 | 안 잡힘(절단 위치를 반올림 전 값으로 쓰는 수정이 먼저 막는다, 안전띠) |
| L2 | 몸체 높이 `>` → `>=` | 잡힘 | |
| L3 | 빈 구간 여유 제거 | 잡힘 | |
| L4 | 낮은 층에도 창 | 잡힘 | |
| L5 | 뒷면 yaw 180 → 0 | 안 잡힘 | 잡힘(`test_every_wall_part_on_every_face_looks_away_from_its_box`) |
| L6 | 교차로 꼭짓점 반올림 6 → 2자리 | 잡힘 | |
| L7 | 가로 자리 시작 반 간격 → 0 | 잡힘 | |
| L8 | 겹침 0.6 기준 → 0 | 안 잡힘 | 잡힘(`test_two_buildings_that_merely_overlap_a_little_are_both_kept`) |
| L9 | 창이 문을 덮음 | 안 잡힘 | 잡힘(`test_a_narrow_front_gives_up_its_only_ground_floor_window_to_the_door`) |
| R1 | `SIGN_TEXT`에 따옴표 허용 | 잡힘 | |
| R2 | `pick` 섞임 제거 | 잡힘 | |
| D1 | 한 호출에 같은 건물 두 번 허용 | 잡힘 | |
| B1 | 간판 `md` 키를 `x`로 | 안 잡힘 | 잡힘(`test_a_sign_literal_carries_its_max_distance_as_md_and_one_x_only`) |
| B2 | 덩어리 경고선 15 KB → 150 KB | 잡힘 | |
| S1 | Builder가 두 번 `Destroy` | 잡힘 | |
| C1 | `chunk_size` 기본 70 → 50 | 잡힘 | |

15 / 16. 방법: 트리를 복사해 한 곳씩 바꾸고 `pytest tests/ -x --hypothesis-seed=1`.
