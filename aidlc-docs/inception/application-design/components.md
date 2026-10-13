# Components

깊이: 최소. 컴포넌트 경계와 책임만 정한다. 규칙의 세부는 Functional Design에서 정한다.

결정 근거: Q1=C, Q2=A(역할별 스크립트), Q3=C+Q7=A(SQLite가 중심), Q4=B, Q5=A, Q6=C, Q8=B.

## 구성 원칙
- 역할마다 스크립트 하나. 각각 `uv run`으로 실행하고 의존성은 PEP 723 인라인에 버전을 고정한다(NFR-7).
- 스크립트끼리 직접 부르지 않는다. 데이터는 SQLite DB(`data/map.db`)로만 주고받는다.
- 모든 단계는 칸 단위로 다시 실행해도 같은 결과가 나온다(upsert). 수동 보정 테이블은 어떤 단계도 덮어쓰지 않는다(NFR-3, FR-11).

## 컴포넌트

### C1. 칸 수집기 — `cells.py` (기존 스크립트 확장)
- **목적**: 구역 지정, H3 칸 채우기, OSM 데이터 수집
- **책임**:
  - 위경도 점들 또는 칸 ID 목록으로 H3 해상도 9 칸을 정한다(FR-1). 작은 부지는 칸 ID를 직접 준다
  - 칸마다 Overpass에서 건물 외곽선과 태그(높이, 층수, 용도)를 받아 원천 테이블 `osm_buildings`에 저장한다. 건물 소유 칸은 중심점(면적 무게중심)이 속한 칸 하나다(FR-2)
  - 칸마다 도로, 인도, 가로시설(나무, 가로등, 벤치, 횡단보도)을 받는다(FR-3)
  - 결과를 DB에 쓴다. 더 이상 `cells/*.json`을 만들지 않는다. 최종 `buildings`는 C2가 조립한다
  - Overpass 응답은 쓰기 전에 검증한다(NFR-7)
- **인터페이스**: 입력은 해상도와 위경도 점들(또는 칸 ID 목록), 출력은 DB의 `cells`, `osm_buildings`, `street_features`

### C2. 건물 조립기 — `register.py`
- **목적**: V-World 건물통합정보를 기본 건물로 삼고 OSM 이름·태그를 붙여 칸의 최종 건물 목록을 조립한다 (Q1=B, 2026-10-13 재확인)
- **책임**:
  - 칸 범위(버퍼 포함)의 V-World 건물통합정보(`LT_C_BLDGINFO`: 외곽선, 지상·지하 층수, 높이, 건물명, 용도 코드, 사용승인일)를 페이지를 넘겨 `gis_buildings`에 받는다
  - V-World 건물을 기본 외곽선으로 쓰고, 겹침 비율로 이어진 OSM 건물의 이름과 태그를 붙여 `buildings`를 만든다. V-World와 겹치지 않는 OSM 건물은 독립 건물로 남긴다. 규칙은 U1 Business Rules 4장
  - 응답을 검증하고 인증키(`VWORLD_KEY`)는 환경변수로만 읽는다(NFR-7)
- **인터페이스**: 입력은 칸 ID, 출력은 DB의 `gis_buildings`, `buildings`
- **확인됨**: V-World 데이터 API로 호출이 되고 외곽선, 층수, 높이를 받는다(2026-10-13 시험). 호출이 실패하면 그 칸은 저장하지 않는다(필수 원천)

### C3. 거리뷰 캡처기 — `capture.py`
- **목적**: 건물마다 근처 거리뷰 파노라마를 받아 건물 방향 크롭을 만든다 (Q6=C, FR-8, U3 Functional Design)
- **책임**:
  - 건물 중심점 근처의 파노라마를 `streetlevel` 라이브러리로 찾고, 가까운 순으로 방위각이 60° 이상 다른 것을 최대 3장 고른다(거리 제한 120 m)
  - 파노라마(zoom 1)를 한 번만 받아 `captures/<파노라마 위치의 칸 ID>/<파노라마 ID>/`에 저장한다(git 제외, 재사용)
  - 건물 방향을 향한 크롭(1024×768)을 `captures/<건물 칸 ID>/crops/`에 만든다
  - 호출 간격 1초, 실행당 새 다운로드 100장 상한. 차단 신호가 나오면 다른 방식으로 바꾸지 않고 즉시 멈춘다(NFR-5)
  - 파노라마는 `captures`, 건물과의 짝과 크롭은 `building_views`에 기록한다
- **인터페이스**: 입력은 칸 ID(또는 `--replan`), 출력은 이미지 파일과 `captures`, `building_views` 레코드
- **한계**: 거리 제한 안에 파노라마가 없는 건물은 `no_photo`다(D-4). 네이버 내부 통신을 쓰는 라이브러리라 바뀌면 깨질 수 있다(그때 Playwright는 새 작업)

### C4. 높이·외관 판단 — `estimate.py`
- **목적**: 건물별 층수, 높이, 외관 속성과 그 근거를 정한다 (FR-8, FR-9)
- **책임**:
  - 건물별로 층수를 정한다. 대장 값을 1순위로 쓰고 사진으로 검증한다. 대장에 없거나 어긋나는 건물만 거리뷰 기하 추정으로 채운다
  - 높이는 층수와 층고로 계산한다. OSM 태그는 참고로만 기록한다
  - 색, 지붕 형태 같은 외관 속성을 기록한다
  - 값마다 근거(대장, 사진 확인, 사진 추정, OSM 태그)와 사용한 사진을 남긴다
  - 사진을 보는 판단은 Claude가 Claude Code 세션에서 하고, 이 스크립트가 결과를 DB에 기록한다
- **인터페이스**: 입력은 칸 ID, 출력은 DB의 `estimates`. 판단이 필요한 건물 목록을 뽑는 명령과 판단을 기록하는 명령이 있다

### C5. 보정 관리자 — `overrides.py`
- **목적**: 사용자와 Claude가 같이 확인해서 고친 값을 안전하게 보관한다 (FR-9, FR-11, Q8=B)
- **책임**:
  - 건물별 보정값과 사유를 DB의 `overrides`에 기록한다
  - `overrides`를 텍스트(JSON)로 내보내 `overrides/<칸ID>.json`에 둔다. 이 파일은 git에 올린다
  - 내보낸 파일에서 DB로 다시 불러온다. DB가 사라져도 보정값은 복구된다(NFR-6)
- **인터페이스**: `overrides` ↔ `overrides/<칸ID>.json`

### C6. Studio 생성기 — `build_luau.py` + `studio/Builder.luau`
- **목적**: 칸 하나를 Studio에 건물 박스와 도로로 만든다 (FR-4, FR-10, FR-12, Q4=B, Q5=A)
- **책임**:
  - DB에서 건물별 최종값(기본값 ← 판단 ← 보정 순)을 읽는다
  - 위경도를 stud로 바꾸고(스케일은 설정값, FR-10) 외곽선을 박스로 단순화한다
  - 건물을 작은 덩어리로 나눠 `Builder.luau`에 넘길 데이터를 만든다
  - `studio/Builder.luau`는 저장소에 두고, Claude가 `execute_luau`로 Studio의 ModuleScript에 넣거나 갱신한다(D-3)
  - Studio 쪽은 `Workspace/Auto/<칸ID>` 폴더를 비우고 다시 만든다. `Workspace/Manual`은 건드리지 않는다
- **인터페이스**: 입력은 칸 ID와 덩어리 크기, 출력은 Luau 호출 데이터. 실행은 Claude가 Studio MCP로 한다
- **U5 확장(2026-10-13)**: `details_rules.py`(세부 어휘·이름·팔레트·치수), `layout_details.py`(지붕·외장·간판·마당·가로 기하), `details.py`(세부 판단 명령, 표 `details`, `details/<칸ID>.json`)가 더해졌다. 세부 판단은 Claude가 묶음 이미지를 보고 기록한다

### C7. 데이터 계층 — `db.py`
- **목적**: 모든 스크립트가 공유하는 SQLite 접근과 스키마
- **책임**:
  - 스키마 생성과 마이그레이션, 칸 단위 upsert
  - 건물별 최종값을 합치는 함수(보정 > 판단 > 대장 > 기본값, 순서 세부는 Functional Design)
  - 보정 테이블은 다른 테이블 재생성과 분리해서 다룬다
- **주요 테이블**: `cells`, `osm_buildings`, `gis_buildings`, `buildings`, `street_features`, `collection_runs`, `captures`, `estimates`, `overrides` (U1 테이블 정의는 `construction/u1-data-foundation/functional-design/domain-entities.md`)
- **파일 위치**: `data/map.db`(git 제외)

## Studio 쪽 구조 (Q5=A)

```text
Workspace
  Auto/<칸ID>   스크립트가 만든 건물, 재생성하면 이 폴더만 비우고 다시 만든다
  Manual        직접 만든 건물과 고친 건물, 재생성이 건드리지 않는다
```
자동 건물을 직접 고치려면 `Manual`로 옮기고 해당 건물의 보정은 `overrides`에 사유와 함께 남긴다.

## 파일 위치 요약

| 경로 | 내용 | git |
|---|---|---|
| `data/map.db` | SQLite 중심 데이터 | 제외 |
| `overrides/<칸ID>.json` | 수동 보정 내보내기 | 포함 |
| `captures/<칸ID>/<지점ID>/` | 거리뷰 사진 | 제외 |
| `studio/Builder.luau` | Studio 생성 모듈 소스 | 포함 |
| `.env` | 인증키(`DATA_GO_KR_KEY`) | 제외 |
| `src/cells.py`, `src/register.py`, `src/capture.py`, `src/estimate.py`, `src/overrides.py`, `src/build_luau.py`, `src/db.py` | 스크립트 | 포함 |
