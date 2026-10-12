# Component Methods

메서드 시그니처와 목적만 적는다. 규칙의 세부(수식, 임계값, 순서)는 Functional Design에서 정한다.

타입은 Python 표기(PEP 604)를 쓴다. `CellId`는 H3 칸 ID 문자열, `BuildingId`는 OSM 건물 ID에 칸 ID를 붙인 문자열이다.

## C7. 데이터 계층 (`db.py`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `connect(path="data/map.db") -> Connection` | 경로 → 연결 | 연결하고 스키마가 없으면 만든다 |
| `upsert_cell(conn, cell: Cell) -> None` | 칸 → 없음 | 칸을 같은 ID로 덮어쓴다 |
| `replace_cell_rows(conn, cell_id: CellId, tables: dict[str, list[Row]]) -> int` | 칸 ID, 테이블별 행 → 저장 개수 | 한 트랜잭션에서 그 칸 소유 원천 행을 지우고 새로 넣는다. `estimates`, `overrides`는 건드리지 않는다 |
| `orphans(conn) -> list[Orphan]` | 없음 → 고아 목록 | `buildings`에 없는 `building_id`를 가진 `overrides`, `estimates`를 찾는다(대체된 건물이면 새 ID도 알려 준다) |
| `effective_building(conn, building_id: BuildingId) -> EffectiveBuilding` | 건물 ID → 최종값 | 보정 > 판단 > 대장 > 기본값 순으로 합쳐 층수, 높이, 외관, 근거를 돌려준다 |
| `effective_buildings(conn, cell_id: CellId) -> list[EffectiveBuilding]` | 칸 ID → 최종값 목록 | 칸 단위 조회 |

## C1. 칸 수집기 (`cells.py`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `fill_cells(points: list[LatLon], res: int) -> list[CellId]` | 점들, 해상도 → 칸 목록 | 다각형을 H3 칸으로 채운다. 칸 ID를 직접 주는 경로도 있다 |
| `fetch_osm_buildings(cell_id: CellId, buffer_m: float) -> list[OsmBuilding]` | 칸 ID, 버퍼 → OSM 건물 | 버퍼를 포함한 범위의 건물 외곽선과 태그를 받고 응답을 검증한다 |
| `centroid(outline: list[LatLon]) -> LatLon` | 외곽선 → 면적 무게중심 | 면적이 0이면 꼭짓점 평균으로 대신한다 |
| `assign_cell(centroid: LatLon, res: int) -> CellId` | 중심점 → 칸 ID | 건물을 중심점이 속한 칸에만 배정한다 |
| `normalize_height(raw: str \| None) -> float \| None` / `normalize_levels(raw: str \| None) -> int \| None` | 태그 문자열 → 값 | 숫자로 읽히지 않거나 0 이하이면 없음으로 본다 |
| `is_valid_outline(outline: list[LatLon]) -> bool` | 외곽선 → 유효 여부 | 점 3개 미만, 면적 0, 자기 교차를 걸러낸다 |
| `fetch_street_features(cell_id: CellId) -> list[StreetFeature]` | 칸 ID → 도로·가로시설 | 도로, 보행로, 횡단보도, 그리고 OSM에 있는 나무·가로등·벤치를 받는다. 도로 폭은 정하지 않는다 |
| `run(res: int, points: list[LatLon] \| None, cells: list[CellId] \| None) -> None` | 입력 → 없음 | 위를 순서대로 실행해 DB에 쓴다(명령줄 진입점) |

## C2. 건물 조립·속성 연결기 (`register.py`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `fetch_integrated(cell_id: CellId, buffer_m: float) -> list[GisBuilding]` | 칸 ID, 버퍼 → 대장 속성이 붙은 건물 도형 | GIS건물통합정보에서 가져오고 응답을 검증한다. 접근 불가면 `None`을 돌려주고 OSM만으로 조립한다 |
| `overlap_ratio(a: Outline, b: Outline) -> float` | 두 외곽선 → 0~1 | 겹치는 면적 ÷ 작은 쪽 면적 |
| `assemble(osm: list[OsmBuilding], gis: list[GisBuilding] \| None) -> Assembly` | 두 목록 → 건물 목록과 속성 연결 | OSM 우선, GIS 둘 이상이 덮이면 GIS로 대체, 겹치지 않는 GIS는 독립 건물로 추가한다(U1 Business Rules 4장) |
| `fetch_title_info(plat: PlatKey) -> RegisterRecord \| None` | 법정동코드와 번지 → 대장 | 건축HUB API로 누락이나 빈 필드를 메운다. 키는 환경변수, 호출 상한이 있다 |
| `run(cell_id: CellId) -> None` | 칸 ID → 없음 | 가져오기, 조립, 보조 조회, DB 저장을 한다 |

## C3. 거리뷰 캡처기 (`capture.py`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `plan_points(cell_id: CellId) -> list[CapturePoint]` | 칸 ID → 캡처 지점 | 칸마다 지점을 몇 곳 정한다 |
| `capture_point(point: CapturePoint) -> list[Path]` | 지점 → 사진 경로 | 360도 사진을 저장한다. 속도를 제한하고 CAPTCHA·차단이 나오면 `BlockedError`를 내고 중단한다 |
| `run(cell_id: CellId) -> None` | 칸 ID → 없음 | 지점 계획, 캡처, `captures` 기록을 순서대로 한다 |

## C4. 높이·외관 판단 (`estimate.py`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `pending(cell_id: CellId) -> list[PendingItem]` | 칸 ID → 판단 대기 건물 | 대장 값이 없거나 사진과 검증이 안 된 건물을 뽑는다 |
| `record(building_id: BuildingId, judgement: Judgement) -> None` | 건물 ID, 판단 → 없음 | 층수, 외관, 근거, 사용한 사진을 `estimates`에 쓴다 |
| `height_from_floors(floors: int, use: str) -> float` | 층수, 용도 → 높이(m) | 층수에 층고를 곱해 높이를 만든다(층고 규칙은 Functional Design) |

## C5. 보정 관리자 (`overrides.py`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `set_override(building_id: BuildingId, field: str, value: Any, reason: str) -> None` | 건물, 필드, 값, 사유 → 없음 | 보정값을 `overrides`에 기록한다 |
| `export_overrides(cell_id: CellId, path: Path) -> None` | 칸 ID, 경로 → 없음 | 보정값을 JSON으로 내보낸다 |
| `import_overrides(path: Path) -> int` | 경로 → 불러온 개수 | JSON에서 DB로 복구한다 |

## C6. Studio 생성기 (`build_luau.py`, `studio/Builder.luau`)

| 메서드 | 입력 → 출력 | 목적 |
|---|---|---|
| `to_studs(point: LatLon, origin: LatLon, scale: float) -> Vec2` | 위경도, 기준점, 스케일 → stud 좌표 | 좌표를 변환한다(FR-10) |
| `outline_to_box(outline: list[LatLon]) -> Box` | 외곽선 → 박스 | 외곽선을 단순화한 박스로 바꾼다 |
| `chunks(cell_id: CellId, size: int) -> Iterator[ChunkData]` | 칸 ID, 덩어리 크기 → 덩어리 | 건물을 작은 덩어리로 나눠 Luau에 넘길 데이터를 만든다 |
| `Builder.buildChunk(cellId, chunk) -> number` (Luau) | 칸 ID, 덩어리 → 만든 개수 | `Workspace/Auto/<칸ID>`에 건물을 만든다 |
| `Builder.clearCell(cellId) -> ()` (Luau) | 칸 ID → 없음 | `Auto/<칸ID>`만 비운다. `Manual`은 건드리지 않는다 |
