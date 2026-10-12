# U1 데이터 기반 — Code Generation Plan

**이 문서가 코드 생성의 유일한 기준이다.** 생성 단계에서는 여기 적힌 순서와 내용만 한다. 승인 뒤에 단계마다 `[x]`로 표시한다.

## 유닛 맥락

- **유닛**: U1 데이터 기반. 컴포넌트는 C7 `db.py`, C1 `cells.py`, C2 `register.py`, 공용 `geo.py`와 `common.py`.
- **프로젝트 종류**: 기존 코드가 있는 프로젝트(brownfield). 작업 위치는 저장소 루트 `/Users/taehyeonpark/Desktop/dev/roblox-map`. 코드는 `aidlc-docs/`에 두지 않는다.
- **기존 파일 처리**: 루트의 `cells.py`는 `git mv`로 `src/cells.py`로 옮기고 그 파일을 고친다(복사본을 만들지 않는다).
- **의존하는 유닛**: 없음. 이 유닛이 다른 유닛(U3, U2, U4)에게 `buildings`, `street_features`를 준다.
- **설계 입력**: `construction/u1-data-foundation/functional-design/`(엔티티, BR-1~BR-8, 속성 P-1~P-10), `.../nfr-requirements/`, `.../nfr-design/`, `inception/application-design/`.
- **인터페이스(다른 유닛과의 약속)**: DB 테이블 `cells`, `osm_buildings`, `gis_buildings`, `buildings`, `street_features`, `collection_runs`(도메인 엔티티 참고).
- **이 유닛이 소유한 데이터**: 위 6개 테이블. `estimates`, `overrides`는 U4가 소유하고 U1은 건드리지 않는다.

## 생성 중 확인한 사실 (2026-10-13)

- V-World 건물통합정보 응답에는 건물 고유 키 필드가 속성에 없고, 각 feature의 `id`(`LT_C_BLDGINFO.11172810`)가 있다. `gis_key`는 이 `id`의 숫자 부분으로 한다. 서비스가 데이터를 다시 올리면 이 번호가 바뀔 수 있다. 그러면 건물 ID가 바뀌어 보정이 고아가 되는데, 고아 보고(BR-6.3)가 이를 알려 준다.
- 응답에 페이지 정보가 있다: `response.page = {total, current, size}`, `response.record = {total, current}`. 페이지를 `page` 파라미터로 넘긴다.
- 속성 필드: `bld_nm`, `dong_nm`, `usability`, `grnd_flr`, `ugrnd_flr`, `archarea`, `height`, `vl_rat`, `bc_rat`, `totalarea`, `platarea`, `useapr_day`, `strct_cd`. 좌표는 EPSG:4326, 경도 위도 순서의 MultiPolygon이다.
- 실행 환경: Python 3.14.6, `uv` 0.11.28. `tomllib`을 쓸 수 있다.

## 요구사항·규칙 추적

| 요구사항 | 구현 단계 |
|---|---|
| FR-1 (칸 지정) | 단계 9 |
| FR-2 (건물·태그 수집과 저장) | 단계 9, 10 |
| FR-3 (도로·가로시설 수집) | 단계 9 |
| FR-9 (V-World 층수·높이 확보) | 단계 10 |
| NFR-2 (위치 정확도, 원천 그대로 저장) | 단계 3, 9, 10 |
| NFR-3 (재실행 시 같은 결과) | 단계 5, 6 |
| NFR-7 (키, 고정 의존성, 응답 검증) | 단계 1, 2, 7, 9, 10, 12 |
| NFR-8 (속성 기반 테스트) | 단계 4, 6, 8, 11 |
| NFR-9 (`data/` 등 git 제외) | 단계 2 |
| BR-1~BR-8, P-1~P-10 | 단계 3~11 (각 단계에 명시) |

## 단계

### 단계 1. 환경 확인과 의존성 버전 결정
- [x] PyPI에서 `h3`, `shapely`, `pytest`, `hypothesis`, `pip-audit`의 최신 안정 버전을 확인한다.
- [x] Python 3.14.6에서 설치되는지 임시 환경에서 `import`로 확인한다. 설치가 안 되는 패키지가 있으면 멈추고 사용자에게 알린다.
- [x] 결정한 정확한 버전을 `nfr-requirements/tech-stack-decisions.md`에 기록한다.

### 단계 2. 프로젝트 설정
- [x] `.gitignore`에 `data/`를 추가한다(DB, 로그, 백업).
- [x] `config.toml`을 만든다(키와 기본값은 nfr-design-patterns 3장).
- [x] `tests/requirements.txt`를 만든다(`pytest`, `hypothesis`, `shapely`, `h3`를 `==`로 고정).
- [x] `tests/conftest.py`를 만든다(`src/`를 import 경로에 추가, Hypothesis 프로필에 실패 시 재현 정보 출력).
- [x] `src/`, `tests/`, `tests/fixtures/` 폴더를 만든다.

### 단계 3. `src/geo.py` (순수 함수) — BR-2, 3, 4, 5, NFR-M3
- [x] 도메인 값 타입: `OsmBuilding`, `GisBuilding`, `Building`(불변 데이터 클래스, 도메인 엔티티 필드 그대로).
- [x] 지역 평면 좌표 변환(위경도 → 미터, 입력 외곽선의 평균 위도 기준)과 역변환.
- [x] `centroid(outline)`: 면적 무게중심, 면적 0이면 꼭짓점 평균(BR-2.1).
- [x] `assign_cell(centroid, res)`: H3 칸 ID(BR-2.2).
- [x] `is_valid_outline(outline)`: 서로 다른 점 3개 이상, 면적 0 초과, 자기 교차 없음(BR-3.1).
- [x] `largest_polygon(multipolygon)`: MultiPolygon에서 가장 큰 폴리곤과 버린 개수(BR-3.3).
- [x] `overlap_ratio(a, b)`: 교집합 면적 ÷ 작은 면적(BR-4.1).
- [x] 정규화: `normalize_height`, `normalize_levels`, `normalize_floors_above`, `normalize_floors_below`, `normalize_vworld_height`(BR-5.1~5.3).
- [x] `assemble(osm, gis, threshold)`: V-World 건물이 기본, 겹치는 OSM의 이름·태그 붙이기, 겹치지 않는 OSM은 독립 건물, 덮인 OSM은 버림(BR-4.3~4.7). 결과는 입력 순서와 무관하게 같고 ID는 유일하다.

### 단계 4. 속성 기반 테스트: geo — P-1~P-7, PBT-07
- [x] `tests/generators.py`: 단순 다각형 외곽선(칸 안 좌표), 겹치는 외곽선 쌍, OSM 태그 문자열, V-World 속성 문자열, OSM·V-World 건물 목록 생성기(공용).
- [x] `tests/test_geo.py`: P-1(칸 배정), P-2(무게중심), P-3(겹침 비율), P-4(조립 규칙과 순서 불변), P-5(칸 나눔 일관성), P-6(정규화), P-7(유효성). 설계 문서의 조립 예시 4개는 예시 기반 테스트로 둔다.

### 단계 5. `src/db.py` — BR-6, BR-7.1, NFR-SEC3, NFR-A, D-N6
- [x] `connect(path)`: 외래 키 켬, 스키마가 없으면 만든다(`cells`, `osm_buildings`, `gis_buildings`, `buildings`, `street_features`, `collection_runs`). JSON 값은 텍스트 열에 둔다.
- [x] `replace_cell_rows(conn, cell_id, tables)`: 한 트랜잭션에서 칸 소유 행을 지우고 새로 넣는다. 중간에 실패하면 되돌린다. 모든 질의는 매개변수 바인딩만 쓴다.
- [x] `orphans(conn)`: `overrides`, `estimates` 테이블이 있을 때만 `buildings`에 없는 `building_id`를 찾는다(테이블이 없으면 빈 목록).
- [x] `backup(conn, dir, keep)`: `sqlite3` 백업 기능으로 `map-<날짜시각>.db`에 복사하고 최근 `keep`개만 남긴다.
- [x] `record_run(conn, ...)`: `collection_runs`에 시작, 종료, 상태, 건수, 실패 이유를 기록한다.

### 단계 6. 속성 기반·예시 테스트: db — P-8, P-9
- [x] `tests/test_db.py`: P-8(같은 입력으로 두 번 교체해도 상태가 같고 `overrides`는 그대로), P-9(고아 목록 = `overrides` ID − `buildings` ID), 중간 실패 시 롤백, 백업 보관 개수.

### 단계 7. `src/common.py` — NFR-SEC1, SEC6, R4, 설계 패턴 1~2장
- [x] `load_config(path)`: `tomllib`로 읽고 형식과 범위를 검증, 없는 키는 기본값(`config.toml`과 코드 기본값 일치).
- [x] `get_secret(name)`: 환경변수를 읽고 앞뒤 공백을 지운다. 없으면 이름만 알리는 오류(값은 노출하지 않는다).
- [x] 로깅: 파일은 `data/logs/<스크립트>-<날짜>.jsonl`, 콘솔은 사람이 읽는 요약. 비밀값 필터(환경변수에서 읽은 키 값과 URL의 `key=` 값을 `<KEY>`로).
- [x] `http_get_json(url, params, ...)`: `urllib`, HTTPS 인증서 검증 유지, 429/502/504와 시간 초과에 10/30/60초 재시도, 호출 간격 대기. 대기 함수와 열기 함수를 주입할 수 있게 해서 테스트에서 가짜로 바꾼다.
- [x] `run_cli(main)`: 처리되지 않은 오류를 가려서 기록하고 0이 아닌 종료 코드(인터럽트 130)로 끝낸다.

### 단계 8. 테스트: common
- [x] `tests/test_common.py`: 비밀값 가리기(로그 줄과 URL), 앞뒤 공백 제거(앞에 공백이 있는 키), 재시도 대기 열(가짜 응답 429, 502, 200), 재시도 안 하는 오류, 설정 검증, `run_cli` 종료 코드.

### 단계 9. `src/cells.py` — FR-1, 2, 3, BR-1, 2, 3, 6, 7, 8
- [x] `git mv cells.py src/cells.py` 후 고친다. 사용법: `cells.py RES lat,lon ...` 또는 `cells.py --cells ID ...`(BR-1.1).
- [x] `fill_cells(points, res)`와 칸 ID 검증(BR-1, NFR-SEC2).
- [x] `fetch_osm(cell_id, buffer_m)`: 버퍼를 포함한 범위의 건물, 도로·보행로, 횡단보도, 나무, 가로등, 벤치를 Overpass에서 받는다. `http_get_json`의 재시도와 간격을 쓴다.
- [x] `parse_osm(response, cell_id)`(순수): 응답 검증(BR-7.4), 건물은 `OsmBuilding`으로, 길과 노드는 `StreetFeature`로 바꾼다(BR-8). 어긋난 요소는 버리고 건수를 센다.
- [x] 쓰기 전 `db.backup`, 칸 단위 `replace_cell_rows`, `record_run`, 고아 보고를 한다.
- [x] 진입점은 `run_cli`로 감싼다. 의존성은 인라인(PEP 723)에 정확한 버전으로 둔다.

### 단계 10. `src/register.py` — FR-2, FR-9, BR-3.3, 4, 5, 7.2
- [x] `fetch_vworld(cell_id, buffer_m)`: `LT_C_BLDGINFO`를 `page`로 넘기며 `total`만큼 받는다(BR-7.2). `VWORLD_KEY`를 `get_secret`로 읽는다.
- [x] `parse_vworld_page(response, cell_id)`(순수): 상태와 키 검증(`INVALID_KEY` 등 오류 코드를 그대로 보고), MultiPolygon 처리, 속성 정규화, `gis_key`는 feature `id`의 숫자 부분(BR-7.4, BR-3.3, BR-5.3).
- [x] `merge_pages(pages)`(순수): 중복을 합치고 받은 수가 `total`과 다르면 오류(P-10).
- [x] DB에서 칸과 버퍼 안의 `osm_buildings`를 읽어 `geo.assemble`을 부르고 `buildings`를 칸 단위로 교체한다(BR-4.8, BR-6.1).
- [x] 진입점은 `run_cli`로 감싼다. 의존성은 인라인(PEP 723)에 정확한 버전으로 둔다.

### 단계 11. 응답 샘플과 테스트: 파싱과 페이지 — P-10
- [x] `tests/fixtures/`에 실제 응답에서 줄여 저장한 샘플(Overpass 한 개, V-World 한 페이지)과 오류 응답(`INVALID_KEY`)을 둔다. 키와 개인정보가 없는지 확인한다.
- [x] `tests/test_parse.py`: `parse_osm`, `parse_vworld_page`, `merge_pages`(P-10: 페이지를 어떻게 나눠도 같은 결과, 받은 수 불일치는 오류), 어긋난 요소 버리기, MultiPolygon, 오류 응답.

### 단계 12. CI와 버전 일치 검사 — NFR-7, D-N7, N-8, PBT-08
- [x] `.github/workflows/ci.yml`: `main` 푸시와 PR에서 `pytest`(Hypothesis 시드를 실행 번호로 고정, 로그에 찍음)와 `pip-audit -r tests/requirements.txt`를 돌린다. 인증키는 쓰지 않는다. 쓰는 액션은 `gh`로 최신 안정 태그의 커밋 SHA를 확인해 SHA로 고정하고, `uv`도 버전을 고정한다.
- [x] `tests/test_versions.py`: 스크립트 인라인 의존성과 `tests/requirements.txt`의 버전이 같은지 확인한다.

### 단계 13. 문서
- [x] `CLAUDE.md`: 실행 명령(`uv run --env-file .env src/cells.py ...`, `register.py`), 테스트 명령, 현재 상태, 다음 할 일을 고친다.
- [x] `aidlc-docs/construction/u1-data-foundation/code/code-summary.md`: 만든 파일 목록, 공개 함수, 설계 대비 차이를 적는다(마크다운만).

### 단계 14. 생성 후 점검 (실행은 Build and Test에서)
- [x] 모든 Python 파일이 문법 오류 없이 컴파일되는지 확인한다.
- [x] `pytest --collect-only`로 테스트가 수집되는지 확인한다.
- [x] 코드에 인증키나 키처럼 보이는 값이 없는지 검색한다. (검색에서 `tests/test_common.py`에 실제 V-World 키가 들어간 것을 발견해 가짜 값으로 바꿨다. 커밋 전이었고 git 이력에는 없다.)
- [x] 이 계획과 만든 파일 목록을 대조해 빠진 것과 중복 파일(`cells.py`가 루트에 남음 등)이 없는지 확인한다.
- 테스트의 본 실행과 실제 칸 수집(첫 칸 `8930e0af13bffff`)은 Build and Test에서 한다.

## 범위 요약
- **새 파일**: `src/geo.py`, `src/db.py`, `src/common.py`, `src/register.py`, `config.toml`, `tests/` 파일 7개(`conftest.py`, `generators.py`, `test_geo.py`, `test_db.py`, `test_common.py`, `test_parse.py`, `test_versions.py`), 응답 샘플, `tests/requirements.txt`, `.github/workflows/ci.yml`, 코드 요약 문서.
- **수정 파일**: `cells.py` → `src/cells.py`(이동 후 개작), `.gitignore`, `CLAUDE.md`, `tech-stack-decisions.md`.
- **총 14단계**.
