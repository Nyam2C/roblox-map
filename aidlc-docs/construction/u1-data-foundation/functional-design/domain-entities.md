# U1 데이터 기반 — Domain Entities

기술과 무관한 논리 모델이다. 실제 컬럼 이름은 코드 생성 단계에서 확정한다. 2026-10-13 V-World 시험 결과와 재확인 답변(Q1=B, Q2=B)을 반영해 다시 썼다.

## 관계 한눈에 보기

```text
Cell 1 --- * OsmBuilding (원천)        Cell 1 --- * StreetFeature
Cell 1 --- * GisBuilding (원천)        Cell 1 --- * CollectionRun
GisBuilding 1 --- 0..1 OsmBuilding  (이름·태그를 붙임)
Building (조립 결과) <- GisBuilding 또는 OsmBuilding
Building 1 --- 0..1 Estimate / Override (U4)
```

## 원천 데이터 (수집한 그대로, 합치지 않음)

### Cell
| 필드 | 의미 |
|---|---|
| `cell_id` | H3 칸 ID (해상도 9) |
| `res` | 해상도 |
| `center`, `boundary` | 중심 좌표, 경계 꼭짓점 |

### GisBuilding (V-World 건물통합정보 `LT_C_BLDGINFO`)
| 필드 | 의미 |
|---|---|
| `gis_key` | V-World 건물의 식별자(응답의 고유 키. 코드 생성 때 확정) |
| `cell_id` | 중심점(면적 무게중심)이 속한 칸 |
| `outline` | 외곽선 (MultiPolygon은 면적이 가장 큰 폴리곤 하나로 줄인다, 아래 참고) |
| `floors_above`, `floors_below` | 지상 `grnd_flr`, 지하 `ugrnd_flr` 층수(없으면 비어 있음) |
| `height_m` | 높이 `height`(0이거나 비어 있으면 없음) |
| `name` | 건물명 `bld_nm` |
| `usability_code` | 용도 코드 `usability`(해석하지 않고 그대로 보관) |
| `approval_date` | 사용승인일 `useapr_day` |
| `building_area` | 건축면적 `archarea` |
| `valid` | 외곽선이 쓸 만한지(Business Rules 3장) |

MultiPolygon에 폴리곤이 여러 개인 건물은 이번에는 가장 큰 폴리곤만 쓰고 나머지 개수를 기록한다. 시험 응답은 첫 항목이 MultiPolygon이었고, 한 건물이 여러 폴리곤인 경우가 얼마나 흔한지는 확인하지 못했다.

### OsmBuilding
| 필드 | 의미 |
|---|---|
| `osm_id` | OSM way ID (칸과 무관하게 유일) |
| `cell_id` | 중심점이 속한 칸 |
| `outline` | 외곽선 꼭짓점 목록 |
| `tags` | OSM 태그 원본 |
| `height_m`, `levels` | 태그에서 정규화한 값(없으면 비어 있음, 참고용) |
| `valid` | 외곽선이 쓸 만한지 |

### StreetFeature
| 필드 | 의미 |
|---|---|
| `feature_id` | OSM ID |
| `cell_id` | 걸친 칸. 도로처럼 칸을 넘는 것은 걸친 모든 칸에 저장한다(소유 칸 없음) |
| `kind` | `road`, `path`(인도·보행로), `crossing`, `tree`, `street_lamp`, `bench` |
| `highway_class` | OSM `highway` 값 |
| `geometry` | 선 또는 점 좌표 |
| `tags` | OSM 태그 원본(`width`, `lanes` 포함) |

### CollectionRun
| 필드 | 의미 |
|---|---|
| `cell_id`, `unit` | 칸, 실행한 컴포넌트(C1 또는 C2) |
| `started_at`, `finished_at`, `status` | 시작·종료 시각, `ok` 또는 `failed` |
| `source_stamp` | 원천 기준 시점(OSM 응답 시각, V-World 응답의 기준 시점이 있으면 그것) |
| `counts`, `error` | 건수(V-World `total`과 받은 수 포함), 실패 이유 |

## 조립 결과 (U2~U5가 읽는 건물)

### Building
`register_matches` 테이블은 없앴다. V-World 속성이 곧 건물 속성이라서 `Building`에 같이 둔다.

| 필드 | 의미 |
|---|---|
| `building_id` | `gis:<gis_key>` 또는 `osm:<osm_id>`. 칸이 바뀌어도 변하지 않는다 |
| `cell_id` | 이 건물 자신의 중심점이 속한 칸 |
| `source` | 외곽선의 출처: `gis`(기본) 또는 `osm`(V-World와 겹치지 않는 OSM 건물) |
| `outline`, `centroid` | 외곽선, 면적 무게중심 |
| `gis_key`, `osm_id` | 연결된 원천 ID(없으면 비어 있음) |
| `name` | 건물명: OSM 이름이 있으면 그것, 없으면 V-World 건물명 |
| `osm_tags` | 붙은 OSM 태그(지붕 형태 등, `source=gis`에 OSM이 붙은 경우와 `source=osm`) |
| `floors_above`, `floors_below`, `height_m` | V-World 값(`source=osm`이면 비어 있음) |
| `usability_code`, `approval_date`, `building_area` | V-World 값 |
| `osm_height_m`, `osm_levels` | OSM 태그에서 정규화한 참고값(출처별로 따로 저장) |
| `status` | `ok` 또는 `invalid`(이후 단계가 건너뜀) |

## 이 유닛이 다루지 않는 것
- `estimates`, `overrides`, `captures`는 U3, U4의 몫이다. U1의 재수집이 `overrides`를 건드리지 않고 고아를 알리는 규칙은 Business Rules 6장에 있다.
- 건축HUB API는 U1에서 쓰지 않는다(Q2=B).
