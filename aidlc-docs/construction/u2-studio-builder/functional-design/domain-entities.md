# U2 Studio 생성기 — Domain Entities

기술과 무관한 논리 모델이다. 실제 이름과 파일 형식은 코드 생성에서 확정한다.
근거: U2 Functional Design 답변 Q1=A(원점은 세 칸이 만나는 꼭짓점), Q2=A(건물 박스 1개), Q3=A(땅·도로는 Part), Q4=B(큰 도로 인도), Q5=A(가로시설은 U5), Q6=B(스폰은 제안 후 확정), Q7=B(기본 물체는 끄기), 기본값 D-U2-1~10.

## 관계 한눈에 보기

```text
buildings (U1) ----+
street_features (U1) +--> [Python: 변환과 맞춤] --> BuildItem 목록 --> Chunk 여러 개 --> chunk-NNN.luau 파일 + manifest
설정(원점, 스케일, 폭 표...) +                                              |
                                                                  Claude가 execute_luau로 Studio에서 실행
                                                                            v
                                          Workspace/Auto/<칸ID>/{Ground, Roads, Paths, Sidewalks, Buildings, Spawn}
                                          Workspace/Manual   (건드리지 않는다)
```

## 입력 (읽기 전용)

- **`buildings`** (U1): 칸 소유 건물. 쓰는 열은 `building_id`, `cell_id`, `source`, `outline`, `centroid`, `floors_above`, `height_m`, `status`.
- **`street_features`** (U1): `kind`가 `road`나 `path`인 줄 모양 요소. `feature_id`, `highway_class`, `geometry`(위경도 점 목록), `tags`(`width`, `sidewalk`). 도로는 걸치는 모든 칸에 **전체 모양**으로 저장되어 있다.
- **설정**: 원점, 스케일, 도로 폭 표, 인도 폭, 땅 여백, 덩어리 크기, 스폰 위치. 층고와 기본 높이는 U3와 같은 값을 쓴다.
- U2는 DB에 쓰지 않는다. 이 유닛이 만드는 것은 파일과 Studio 안의 부품이다.

## WorldFrame (좌표계)
프로젝트에 하나. 칸마다 바뀌지 않는다.

| 필드 | 의미 |
|---|---|
| `origin_lat`, `origin_lon` | Studio (0, 0, 0)에 해당하는 위경도. 기본 `(37.504169, 126.779628)`(세 칸이 만나는 꼭짓점) |
| `studs_per_m` | 1 m당 stud 수. 기본 3.6 |
| 축 | 동쪽 +X, 북쪽 −Z, 위 +Y. 땅 윗면은 Y = 0 |

## BuildItem (Studio에 만들 부품 하나)
모든 항목은 같은 모양이다. 길이 단위는 stud이고 소수 셋째 자리까지 쓴다.

| 필드 | 의미 |
|---|---|
| `kind` | `ground`, `road`, `path`, `sidewalk`, `building`, `spawn` |
| `name` | 부품 이름. 건물은 건물 ID, 도로 조각은 `<피처 ID>#<구간 번호>`, 인도는 `<피처 ID>#<구간 번호>L` 또는 `R`, 땅은 `Ground`, 스폰은 `Spawn` |
| `cx`, `cy`, `cz` | 중심 위치 |
| `sx`, `sy`, `sz` | 크기(로컬 X, Y, Z 방향) |
| `yaw_deg` | Y축 둘레 회전. 0이면 로컬 +X가 동쪽, 양수는 위에서 볼 때 동쪽에서 북쪽으로 반시계 방향 |
| `material`, `color` | Roblox 재질 이름, RGB |
| `attrs` | 건물만: `BuildingId`, `CellId`, `Source`, `Floors`, `HeightM`, `FitRatio` |

## 항목 종류별 의미

### 건물 박스 (`building`)
- 건물의 외곽선을 덮는 **최소 면적 회전 직사각형** 하나. 긴 변이 `sx`, 짧은 변이 `sz`, `yaw_deg`는 긴 변 방향이다(0 이상 180 미만).
- 높이 `sy`는 건물 높이(m) × 스케일. 바닥은 Y = 0이라 `cy = sy / 2`.
- 맞춤 정도 `fit_ratio = 외곽선 면적 ÷ 박스 면적`. 0.8 미만이면 `poor_fit` 목록에 오른다(만들기는 한다).

### 도로 조각 (`road`), 보행로 조각 (`path`)
- 선 모양 요소의 **구간(꼭짓점 두 개를 잇는 선분) 하나가 박스 하나**다. 길이는 구간 길이에 폭을 더한 값(양 끝에 폭의 절반씩 더해 이음새의 빈틈을 메운다).
- 윗면 높이가 도로 0.2, 보행로 0.3 stud이고 바닥(Y = 0)까지 채운 판이다.

### 인도 조각 (`sidewalk`)
- 큰 도로나 OSM `sidewalk` 태그가 있는 도로의 구간마다 왼쪽·오른쪽 한 개씩. 도로 중심선에서 옆으로 `도로 폭/2 + 인도 폭/2` 떨어진 판. 윗면 높이 0.4 stud.

### 땅 (`ground`)
- 칸마다 1개. 칸 경계의 모든 꼭짓점과 여백을 덮는 축 정렬 직사각형 판. 윗면 Y = 0, 두께 4 stud.

### 스폰 (`spawn`)
- 칸 하나(스폰 점이 속한 칸)에만 1개. 투명한 `SpawnLocation` 판. 스폰 점이 아직 정해지지 않았으면 만들지 않는다.

## Chunk (덩어리)
한 번의 `execute_luau` 호출에 넣는 항목 묶음. 항목 수가 `chunk_size`(기본 50) 이하이고 순서가 정해져 있다. 첫 덩어리는 칸의 `Auto` 폴더를 비우고 시작하며, 마지막 덩어리는 끝났음을 표시한다.

## Manifest (만들 것의 목록)
칸마다 파일 하나. Studio에서 만든 결과를 확인할 때의 기준이다.

| 필드 | 의미 |
|---|---|
| `cell_id`, 설정 스냅샷 | 어떤 설정으로 만들었는지 |
| 항목 수 | 종류별 개수와 합계, 덩어리 수 |
| 입력 요약 | 건물 수, 도로·보행로 요소 수 |
| `poor_fit` | 맞지 않는 건물 목록(건물 ID, 이름, `fit_ratio`) |
| 경고 | 건너뛴 입력(꼭짓점 3개 미만 등), 스폰이 도로 밖일 때 |

## Studio 쪽 구조

```text
Workspace
  Auto
    <칸ID>              속성 BuildComplete = false(만드는 중) / true(끝남)
      Ground  Roads  Paths  Sidewalks  Buildings  Spawn
  Manual                사람이 만든 것. 재생성이 지우거나 바꾸지 않는다
ServerStorage
  MapBuilder            studio/Builder.luau를 넣은 ModuleScript (D-3)
```

- `Workspace/Auto`와 `Workspace/Manual`은 없으면 첫 실행이 빈 폴더로 만든다.
- 이 장소의 기본 물체(`Baseplate`, 기본 `SpawnLocation`)는 Claude가 첫 생성 때 한 번 끈다(Builder는 건드리지 않는다).

## 파일 배치 (git 제외, `data/`)

```text
data/build/<칸ID>/
  manifest.json
  chunk-001.luau, chunk-002.luau, ...
studio/Builder.luau        (git 포함, Studio에 넣는 모듈의 소스)
```

## 이 유닛이 다루지 않는 것
- 지붕 모양, 창문과 문, 간판, 재질과 색의 변화(U5). 층수·높이의 최종값 판단과 보정(U4).
- 가로시설(나무, 가로등, 벤치, 횡단보도)과 교차로 정리(U5, Q5=A).
- 거리뷰 사진(U3와 서로 의존하지 않는다).
- 지형의 고저차와 하천·공원, 건물 내부.
