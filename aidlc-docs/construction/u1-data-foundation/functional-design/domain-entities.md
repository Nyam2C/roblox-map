# U1 데이터 기반 — Domain Entities

기술과 무관한 논리 모델이다. 필드 이름은 의미를 나타내는 논리 이름이고, 실제 컬럼 이름과 GIS건물통합정보의 원본 필드 대응은 코드 생성 단계에서 확정한다(원본 필드명은 아직 확인하지 못했다).

## 관계 한눈에 보기

```text
Cell 1 --- * OsmBuilding (원천)          Cell 1 --- * StreetFeature
Cell 1 --- * GisBuilding (원천)          Cell 1 --- * CollectionRun
OsmBuilding * --- * Building <--- * GisBuilding     (조립 결과, Business Rules 4장)
Building 1 --- 0..1 RegisterMatch
Building 1 --- 0..1 Estimate / Override (U4)
```

## 원천 데이터 (수집한 그대로, 합치지 않음)

### Cell
| 필드 | 의미 |
|---|---|
| `cell_id` | H3 칸 ID (해상도 9) |
| `res` | 해상도 |
| `center`, `boundary` | 중심 좌표, 경계 꼭짓점 |

### OsmBuilding
| 필드 | 의미 |
|---|---|
| `osm_id` | OSM way ID (칸과 무관하게 유일) |
| `cell_id` | 중심점(면적 무게중심)이 속한 칸 |
| `outline` | 외곽선 꼭짓점 목록(위도, 경도) |
| `tags` | OSM 태그 원본 |
| `height_m`, `levels` | 태그에서 정규화한 값(없으면 비어 있음). 원본 태그는 `tags`에 그대로 있다 |
| `valid` | 외곽선이 쓸 만한지(Business Rules 3장) |

### GisBuilding
| 필드 | 의미 |
|---|---|
| `gis_key` | GIS건물통합정보의 건물 식별자 |
| `cell_id` | 중심점이 속한 칸 |
| `outline` | 외곽선 |
| `floors_above`, `floors_below` | 지상, 지하 층수(없으면 비어 있음) |
| `height_m` | 높이(0이거나 비어 있으면 없음) |
| `main_use`, `approval_date`, `name` | 주용도, 사용승인일, 건물명 |
| `plat_key` | 법정동코드 + 번지(건축HUB 보조 조회에 쓴다) |
| `valid` | 외곽선이 쓸 만한지 |

### StreetFeature
| 필드 | 의미 |
|---|---|
| `feature_id` | OSM ID |
| `cell_id` | 걸친 칸. 도로처럼 칸을 넘는 것은 걸친 모든 칸에 저장한다(소유 칸 없음) |
| `kind` | `road`, `path`(인도·보행로), `crossing`, `tree`, `street_lamp`, `bench` |
| `highway_class` | OSM `highway` 값(residential, tertiary 등) |
| `geometry` | 선 또는 점 좌표 |
| `tags` | OSM 태그 원본(`width`, `lanes` 포함) |

### CollectionRun
| 필드 | 의미 |
|---|---|
| `cell_id`, `unit` | 칸, 실행한 컴포넌트(C1 또는 C2) |
| `started_at`, `finished_at`, `status` | 시작·종료 시각, `ok` 또는 `failed` |
| `source_stamp` | 원천 기준 시점(OSM 응답 시각, GIS 기준 시점) |
| `counts`, `error` | 건수, 실패 이유 |

## 조립 결과 (U2~U5가 읽는 건물)

### Building
| 필드 | 의미 |
|---|---|
| `building_id` | `osm:<osm_id>` 또는 `gis:<gis_key>`. 칸이 바뀌어도 변하지 않는다 |
| `cell_id` | 이 건물 자신의 중심점이 속한 칸 |
| `source` | 외곽선의 출처: `osm` 또는 `gis` |
| `outline`, `centroid` | 외곽선, 면적 무게중심 |
| `osm_id`, `gis_key` | 연결된 원천 ID(없으면 비어 있음) |
| `osm_tags`, `name` | 연결된 OSM 태그와 이름(OSM과 이어진 건물만) |
| `replaces_osm_id` | `source=gis`가 OSM 건물을 대체한 경우 그 OSM way ID (보정을 옮겨 붙이는 단서) |
| `supplement_missing` | 건축HUB 보조 조회가 실패해서 비어 있다는 표시 |
| `status` | `ok` 또는 `invalid`(이후 단계가 건너뛴다) |

### RegisterMatch
| 필드 | 의미 |
|---|---|
| `building_id` | 대상 건물 |
| `source` | 속성의 출처: `gis` 또는 `hub`(건축HUB 보조) |
| `link` | 연결 방식: `own`(GIS 외곽선 자체), `overlap`(OSM 외곽선과 겹침), `hub` |
| `overlap_ratio` | 겹침 비율(`overlap`일 때) |
| `floors_above`, `floors_below`, `height_m` | 대장 값(없으면 비어 있음, 0은 없음으로 본다) |
| `main_use`, `approval_date` | 주용도, 사용승인일 |

## 이 유닛이 다루지 않는 것
- `estimates`, `overrides`, `captures`는 U3, U4의 몫이다. 단, U1의 재수집이 `overrides`를 건드리지 않고 고아를 알리는 규칙은 Business Rules 6장에 있다.
