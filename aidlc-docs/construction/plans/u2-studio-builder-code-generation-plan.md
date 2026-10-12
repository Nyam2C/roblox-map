# U2 Studio 생성기 — Code Generation Plan

**이 문서가 코드 생성의 유일한 기준이다.** 생성 단계에서는 여기 적힌 순서와 내용만 한다. 승인 뒤에 단계마다 `[x]`로 표시한다.

## 유닛 맥락

- **유닛**: U2 Studio 생성기. 컴포넌트는 C6 `build_luau.py`와 이 유닛이 새로 만드는 `layout.py`(순수 계산), `studio/Builder.luau`(Studio 모듈).
- **프로젝트 종류**: 기존 코드가 있는 프로젝트(brownfield). 작업 위치는 저장소 루트 `/Users/taehyeonpark/Desktop/dev/roblox-map`. 코드는 `aidlc-docs/`에 두지 않는다.
- **기존 파일 처리**: `src/common.py`와 `config.toml`(U2 설정과 공용 높이 함수), `src/projection.py`(높이 함수를 `common.py`로 옮기고 이름은 다시 내보냄), `tests/` 일부, `CLAUDE.md`는 고친다. 복사본을 만들지 않는다.
- **의존하는 유닛**: U1의 `buildings`, `street_features`와 `db.py`, `common.py`, `config.toml`. U3와는 서로 의존하지 않고 높이 규칙만 공유한다.
- **설계 입력**: `construction/u2-studio-builder/functional-design/`(엔티티, BR-1~BR-7, S-1~S-6, 속성 P2-1~P2-9), `.../nfr-requirements/`(성능, 보안, 신뢰성, 테스트), U1·U3의 NFR 결정.
- **이 유닛이 소유한 것**: `data/build/<칸ID>/`(파일), Studio의 `Workspace/Auto/<칸ID>`. 이 유닛은 DB 테이블에 쓰지 않는다(`collection_runs`에 실행 기록만 남긴다).
- **이 계획의 범위 밖(Build and Test)**: Studio에 첫 칸을 실제로 만드는 일, 장소 설정 변경(스트리밍 끄기, 기본 물체 끄기), 스케일 확정, 스폰 점 제안, 플레이 테스트 프레임 측정. 첫 생성 전에 사용자의 `.rbxl` 복사본이 필요하다(NFR A2). 코드 생성 중 Studio 시험은 `Workspace.MCP_Test` 안에서만 한다.

## 요구사항·규칙 추적

| 요구사항·규칙 | 구현 단계 |
|---|---|
| FR-3 (도로·인도) | 단계 4, 7 |
| FR-4 (건물 박스) | 단계 3, 7, 9 |
| FR-10 (스케일) | 단계 1, 2 |
| FR-11 (자동·수작업 레이어) | 단계 9 |
| FR-12 (Studio MCP로 생성) | 단계 7, 9 |
| FR-13 (스폰) | 단계 5, 9 |
| NFR-2, NFR-3 (위치 정확도, 재현성) | 단계 2, 3, 6, 8 |
| NFR-7 (고정 의존성, 입력 검증) | 단계 7, 10 |
| NFR-8 (속성 기반 테스트) | 단계 6, 8 |
| BR-1~BR-7, P2-1~P2-9 | 단계 2~8 (각 단계에 명시) |
| U2 NFR (P1~P5, SEC2, SEC3, SEC6, R1~R4, M1~M6) | 단계 1, 7, 8, 9, 10 |

## 단계

### 단계 1. 설정과 공용 높이 함수 — N-U2-9, M5, BR-2.4
- [ ] `config.toml`과 `src/common.py`(`DEFAULTS`, 범위 검증)에 U2 항목을 추가한다: `origin_lat`(37.504169), `origin_lon`(126.779628), `studs_per_m`(3.6), `poor_fit_ratio`(0.8), `ground_margin_m`(20), `sidewalk_width_m`(1.5), 도로 폭 표 `road_widths_m`(BR-3.4의 종류별 값, TOML 표), `chunk_size`(50), `spawn_lat`·`spawn_lon`·`spawn_yaw_deg`(기본값 없음=스폰을 만들지 않음). 스폰 위도·경도는 둘 다 있거나 둘 다 없어야 하고 위경도 범위 안이어야 한다.
- [ ] `building_height_m`(V-World 높이 → 층수 × 층고 → 기본값)를 `projection.py`에서 `common.py`로 옮기고, `projection.py`는 같은 이름으로 다시 내보낸다. `build_luau.py`가 `numpy`와 `pillow` 없이 쓸 수 있게 하려는 것이고 U3의 동작은 바뀌지 않는다.
- [ ] `tests/test_common.py`가 기본값 일치와 새 항목 검증(범위 밖 값, 스폰 한쪽만 있음, 도로 폭 표의 잘못된 값 거부)을 확인하도록 고친다. 기존 `tests/test_projection.py`와 `capture.py`가 그대로 통과하는지 확인한다.

### 단계 2. `src/layout.py` — 좌표 변환 (BR-1, P2-1)
- [ ] `to_studs(lat, lon, frame)`, `from_studs(x, z, frame)`: 평면 근사(원점 위도의 코사인 하나), `x = e × s`, `z = −n × s`, 지구 반지름 6,371,008.8 m. `frame`은 원점과 `studs_per_m`을 담는 작은 불변 객체이고 설정에서 만든다.
- [ ] 모든 수치 출력 서식(소수 셋째 자리 반올림, 음수 0 정리)을 한 함수로 둔다(BR-7.4).

### 단계 3. `src/layout.py` — 건물 박스 (BR-2, P2-2, P2-3)
- [ ] `outline_to_box(outline, frame)`: 외곽선을 원점 기준 미터 평면으로 바꾼 뒤 최소 면적 회전 직사각형(`shapely`)을 구하고, 긴 변 `width`, 짧은 변 `depth`, `yaw_deg`(0 이상 180 미만, 변 길이가 같으면 작은 쪽), 중심, `fit_ratio`를 돌려준다. 가로 크기는 1 stud 미만이면 1 stud로 올린다.
- [ ] `building_item(building, frame, cfg)`: 높이는 `common.building_height_m`, `cy = sy/2`, 재질과 색(BR-2.7), 속성 `BuildingId`, `CellId`, `Source`, `Floors`, `HeightM`, `FitRatio`(BR-2.6)를 담은 항목을 만든다. 외곽선 점이 3개 미만이거나 좌표가 유한하지 않으면 건너뛴다는 결과(경고 사유)를 돌려준다(BR-2.9).

### 단계 4. `src/layout.py` — 도로·보행로·인도 (BR-3, P2-4, P2-5, P2-9)
- [ ] `road_items(feature, frame, cell_id, res, cfg)`: 줄 모양 요소를 구간으로 나누고, 구간 중점이 속한 H3 칸이 `cell_id`일 때만 조각을 만든다(BR-3.2). 길이 = 구간 길이 + 폭, 폭은 `width` 태그(1~30 m로 자름) 또는 종류별 표(BR-3.4), `yaw_deg`는 구간 방향(180 법), 윗면 높이 0.2(도로) 또는 0.3(보행로), 재질과 색(BR-3.5, 3.6). 길이 1 mm 미만 구간은 건너뛴다. 이름은 `<피처 ID>#<구간 번호>`.
- [ ] `sidewalk_items(...)`: `sidewalk` 태그(`both`, `left`, `right`, `no`·`none`, 그 밖은 없음)를 먼저 따르고, 태그가 없으면 큰 도로(`trunk`, `primary`, `secondary`, `tertiary`와 각 `_link`)만 양쪽, 보행로는 없음(BR-3.7). 조각은 구간 수직으로 `도로 폭/2 + 인도 폭/2` 옆, 길이 = 구간 길이 + 인도 폭, 윗면 높이 0.4(BR-3.8). `left`는 그려진 방향의 왼쪽이다. 이름은 `<피처 ID>#<구간 번호>L` 또는 `R`. 칸 소유는 옆으로 옮기기 전의 구간 중점으로 정한다.

### 단계 5. `src/layout.py` — 땅, 스폰, 정렬, 덩어리 (BR-4, 5, 7.1, 7.2, P2-6, P2-7)
- [ ] `ground_item(cell_id, frame, cfg)`: 칸 경계(`h3.cell_to_boundary`)의 모든 꼭짓점과 여백을 덮는 축 정렬 판 1개(윗면 Y = 0, 두께 4 stud, 재질·색 BR-4.1). 한 변이 2048 stud를 넘으면 오류(BR-4.2).
- [ ] `spawn_item(frame, cfg, cell_id, road_items)`: 설정된 점이 이 칸에 있을 때만 `SpawnLocation` 항목(BR-5.3), 그렇지 않으면 없음. 가장 가까운 도로·보행로 중심선까지 거리가 `폭/2 + 1 m`를 넘으면 경고(BR-5.4).
- [ ] `order_items(items)`(땅 → 도로 → 보행로 → 인도 → 건물 → 스폰, 피처·건물 ID 순, BR-7.1)와 `chunk_items(items, size)`(BR-7.2).

### 단계 6. 속성 기반 테스트: layout — P2-1~P2-9, PBT-07
- [ ] `tests/generators.py`에 원점 근처 위경도, 도로 선(꼭짓점 2~8개, 종류와 태그 포함), 입력 행 순서를 섞는 생성기를 추가한다(공용). 기존 외곽선 생성기를 쓴다.
- [ ] `tests/test_layout.py`: P2-1(원점, 방향, 왕복, 거리, 스케일 2배), P2-2(박스가 외곽선을 덮음, 면적 관계, `sx ≥ sz`, yaw 범위, 직사각형이면 `fit_ratio` 1, 꼭짓점 시작·순서 불변, 평면 회전), P2-3(높이와 `cy`), P2-4(조각 수, 구간을 덮음, 길이·폭), P2-5(인도 태그 규칙, 대칭, 중심선 거리, left·right 반대), P2-6(땅이 칸 경계를 덮음, 윗면 0, 크기 한도), P2-7(덩어리), P2-9(여러 칸에서 만들어도 구간마다 정확히 한 번). 정렬 불변은 P2-8과 단계 8에서 함께 확인한다.

### 단계 7. `src/build_luau.py` — N-U2-1~7, SEC2, SEC3, SEC6, BR-7.3~7.6
- [ ] 인라인 의존성은 `h3==4.5.0`, `shapely==2.2.0`(`register.py`와 같음), Python 3.11 이상. 진입점은 U1의 `run_cli`로 감싼다. `--cells <칸ID>...`(필수)와 `--selftest`(의존성 import 확인, DB와 파일을 건드리지 않음)를 받는다. 칸 ID는 H3 형식과 해상도를 검사한다.
- [ ] 흐름: 설정 검증(BR-7.6) → DB에서 칸의 `buildings`(`status=ok`)와 `street_features`(`kind`가 `road`, `path`) 읽기 → 항목 만들기(`layout`) → 정렬과 덩어리 → Luau 코드 파일과 manifest 쓰기 → 실행 기록(`collection_runs`, `unit = 'C6'`) → 콘솔 요약과 "Studio에서 실행할 순서". 칸에 건물이 없으면 오류로 멈춘다(BR-2.9). 칸 하나가 실패해도 다른 칸은 이어서 한다.
- [ ] Luau 코드 만들기 `render_chunk(...)`: 문자열은 허용 문자(영문자, 숫자, `:` `#` `_` `-` `.`)만 통과시키고 Luau 문자열 리터럴로 이스케이프한다. 허용 밖 문자가 있는 항목은 건너뛰고 경고한다. 숫자는 유한한 값만, 서식은 단계 2의 함수로. 첫 덩어리는 `begin`, 마지막은 `finish`를 호출하고 결과를 돌려준다(BR-7.3). 덩어리 파일이 10 KB를 넘으면 경고하고 `chunk_size`를 줄이라고 안내한다(P3).
- [ ] manifest(BR-7.4와 도메인 엔티티의 필드): 칸 ID, 설정 스냅샷, 항목 수(종류별), 덩어리 수, 입력 요약, `poor_fit` 목록, 경고. 같은 입력이면 파일이 글자까지 같게 쓴다(P2-8).

### 단계 8. 테스트: build_luau — 예시 기반, P2-8, SEC2
- [ ] `tests/test_build_luau.py`: 합성 DB(메모리)로 한 칸을 만들어 덩어리 파일과 manifest를 확인한다(항목 수, 덩어리 수, 첫·마지막 덩어리의 `begin`·`finish`, 순서). P2-8(행 순서를 섞어도 파일이 글자까지 같음, 두 번 만들어도 같음). 코드 주입 방지(따옴표, 줄바꿈, `]]`, `--`, 긴 문자열이 든 ID가 코드로 새지 않고 건너뛰어짐), 숫자가 유한한지, 건물이 없는 칸, 스폰이 설정되지 않은 칸, `poor_fit` 목록, 덩어리 파일 크기 경고, 실행 기록이 남는 것을 확인한다.
- [ ] 첫 칸 실제 DB(`data/map.db`)로 `build_luau.py`를 돌려 항목 수와 파일 크기를 본다(읽기 전용, 네트워크 없음, 결과 파일은 `data/build/`). 합성 시험과 숫자가 어긋나면 멈추고 알린다.

### 단계 9. `studio/Builder.luau` — BR-6, BR-2.8, SEC2, SEC3, M3
- [ ] 모듈 `Builder`: `begin(칸ID, root?)`(칸 ID 형식 확인, `Auto`·`Manual` 없으면 만들기, `Auto/<칸ID>`만 지우고 새로 만들기, 하위 폴더 6개, `BuildComplete = false`, `Manual`의 `BuildingId` 모으기), `add(칸ID, 항목들, 상태, root?)`(컨테이너에 만든 뒤 폴더에 넣기, 수작업 우선이면 건너뛰고 세기, `SpawnLocation`은 `Duration = 0`, `Neutral = true`, 투명, 충돌 끔), `finish(칸ID, 상태, root?)`(`BuildComplete = true`, 만든 수와 건너뛴 수 반환), `verify(칸ID, manifest, root?)`(폴더별 부품 수와 건너뛴 수가 manifest와 맞는지, 부품 몇 개의 위치·크기·회전). `loadstring`을 쓰지 않는다.
- [ ] `Workspace.MCP_Test` 안에서만 시험한다: `ModuleScript`에 `Source`로 넣고, 합성 덩어리(건물, 도로, 인도, 땅, 스폰)로 `begin`·`add`·`finish`·`verify`를 돌려 만든 수, 수작업 우선, 재생성 결과, 읽어 온 값을 확인한다. 끝나면 시험 물체를 모두 지우고 `MCP_Test`가 처음 상태(`TestBase`, `TestBuilding`)인지 확인한다. `ServerStorage`나 장소 설정은 건드리지 않는다.

### 단계 10. 버전 일치 검사와 문서 — M6, N-U2-9
- [ ] `tests/test_versions.py`가 `build_luau.py`를 포함하도록 확장한다(스크립트 목록에 `build_luau.py` 기대, 인라인 고정이 `==`이고 `h3`, `shapely` 버전이 `tests/requirements.txt`와 같음). CI는 바꾸지 않는다.
- [ ] `CLAUDE.md`: 실행 명령(`uv run src/build_luau.py --cells ...`, `--selftest`), 현재 상태, 다음 할 일.
- [ ] `aidlc-docs/construction/u2-studio-builder/code/code-summary.md`: 만든 파일, 공개 함수, Studio에서 실행하는 순서(Claude용 절차: `Builder` 설치, 덩어리 실행, `verify`), 설계 대비 차이(마크다운만).

### 단계 11. 생성 후 점검 (본 실행은 Build and Test에서)
- [ ] 모든 Python 파일이 컴파일되는지 확인한다. 전체 테스트를 여러 시드로 돌려 기존 테스트가 그대로 통과하는지 확인한다.
- [ ] 코드와 문서에 인증키나 키처럼 보이는 값이 없는지 검색한다.
- [ ] 이 계획과 만든 파일 목록을 대조해 빠진 것과 중복 파일이 없는지 확인한다.
- 실제 첫 칸 Studio 생성, 장소 설정 변경, 스케일 확정, 스폰 점 제안, 프레임 측정은 Build and Test에서 한다.

## 범위 요약
- **새 파일**: `src/layout.py`, `src/build_luau.py`, `studio/Builder.luau`, `tests/test_layout.py`, `tests/test_build_luau.py`, 코드 요약 문서.
- **수정 파일**: `src/common.py`, `src/projection.py`, `config.toml`, `tests/generators.py`, `tests/test_common.py`, `tests/test_versions.py`, `CLAUDE.md`.
- **총 11단계**. 단계 8의 첫 칸 실제 DB 실행과 단계 9의 Studio 시험은 읽기 전용 또는 `MCP_Test` 안으로 한정하고, 어긋나면 멈춰서 알린다.
