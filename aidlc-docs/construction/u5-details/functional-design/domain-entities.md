# U5 디테일 — Domain Entities

기술과 무관한 논리 모델이다. 실제 이름과 파일 형식은 코드 생성에서 확정한다.
근거: U5 Functional Design 답변 Q1=A(세부 판단), Q2=A(다중 박스), Q3=A(학교 몸체는 Auto), Q4=A(주차 차량), Q5=A(포장 땅), Q6=A(한글 그대로), Q7=A(공공 기관 실명), Q8=A(Realistic 조명), Q9=A(작은 물체 전부), 기본값 D-U5-1~25와 그 개정(계획서 "답변에서 따라온 조정"). 규칙의 세부는 `business-rules.md`.

## 관계 한눈에 보기

```text
buildings (U1) + estimates/overrides (U4) + details (U5, 새 표) + street_features (U1) + 설정
    -> [Python: 중복 제거 -> 원형 -> 박스(들) -> 도로 쪽 면 -> 지붕/띠/창/외장/1층/마당/간판 -> 교차점 -> 가로 슬롯]
    -> BuildItem 목록 (kind: ground, road, path, sidewalk, building, roof, facade, sign, prop, spawn)
    -> Chunk 여러 개 -> chunk-NNN.luau + manifest.json
    -> Claude가 execute_luau로 Studio에서 실행
    -> Workspace/Auto/<칸ID>/{Ground, Roads, Paths, Sidewalks, Buildings, Roofs, Facades, Signs, Props, Spawn}
       Workspace/Manual/School (운동장, 담장, 교문, 탑, 2색 외벽, 정원: Claude가 Build and Test에서 손으로)
Claude가 묶음 이미지를 보고 세부를 기록 -> details 표 -> details/<칸ID>.json (git)
```

## 입력 (읽기 전용)

- **`buildings`** (U1): `building_id`, `cell_id`, `outline`, `centroid`, `name`, `usability_code`, `building_area`, `floors_above`, `height_m`, `status`.
- **최종값** (U4 `effective_building`): `floors_above`, `height_m`, `wall_color`, `roof_shape`, 근거와 확인 사유. U5는 이 값을 읽기만 한다.
- **`estimates.note`** (U4): 자유 문장. 세부 행이 없을 때 가게·계단실·돌출창·발코니·차고·옥상·지붕 색의 신호로 단어 경계 검색만 한다(BR-7.3).
- **`street_features`** (U1): `kind`(road, path), `highway_class`, `geometry`, `tags`(`oneway`, `sidewalk`, `sidewalk:both/left/right`). 도로 조각은 U2 BR-3.2의 칸 소유 구간으로, 도로 쪽 면은 행 전체 기하로 계산한다.
- **설정**: U2·U4의 키와 새 키 `pole_spacing_m`, `lamp_spacing_m`, `tree_spacing_m`, `car_spacing_m`, `school_zone_m`, `roof_pitch_deg`, `window_faces`, `details_dir`, `school_polygons`(심원고 + 코드 생성에서 부흥중 추가).
- **묶음 이미지** (`captures/<칸ID>/sheets/<safe_name(건물 ID)>.jpg`, U4): 세부 판단의 입력. 파일은 로컬에만.

## Detail (세부, 새 표 `details`)
건물 하나에 한 행. 사람(Claude)이 사진을 보고 기록한 외관 사실이다. 어떤 재수집도 지우지 않는다(`db.TABLES` 밖, `db.orphans`에 포함).

| 필드 | 어휘 | 뜻 |
|---|---|---|
| `building_id` | 건물 ID | 키 |
| `cell_id` | 칸 ID | 내보내기 단위 |
| `finish` | `brick`, `stone`, `tile`, `paint`, `panel`, `glass`, 비움 | 벽 마감(재질을 정한다) |
| `ground_use` | `house`, `shop`, `garage`, 비움 | 1층 용도(전면·문·셔터·마당을 정한다) |
| `stair` | `none`, `glass`, `brick`, `round`, 비움 | 계단실 모양 |
| `bay` | 0, 1, 비움 | 돌출창 |
| `balcony` | 0, 1, 비움 | 발코니 |
| `roof_color` | `dark`, `red`, `green`, `brown`, `blue`, `pink`, 비움 | 지붕 재질·색 |
| `rooftop` | `none`, `box`, `railing`, `tank`, 비움 | 옥상 물체 또는 난간 |
| `note` | ≤ 300자, 선택 | 메모(개인 정보 금지) |
| `judged_at` | ISO 시각 | 기록 시각(`record`가 시계로 채움, 같은 내용 재기록은 무변화) |

비운 필드는 "모름"이고 메모 검색(검색 규칙이 있는 필드) → 규칙 기본값 순으로 채운다. 세부는 U4의 보정(`overrides`) 대상이 아니다(세부 자체가 사람의 판단이고 고치려면 다시 기록한다).

## Archetype (원형)
몸체마다 하나. `school` → `commercial` → `public` → `villa` 순으로 첫 일치(BR-1.5). 몸체가 아닌 레코드(`structure`)는 박스만 있다. 원형이 정하는 것: 창 종류(낱창/띠창), 가게 여부, 기단·마당·문·현판, 간판 풀, 지붕 상한(학교는 평지붕), 다중 박스 상한.

## Body (몸체)와 Box 목록
- 건물 하나는 박스 1~3개(학교 ≤ 6)다. 박스는 U2의 `Box`(중심, 긴 변 `w`, 짧은 변 `d`, yaw, 조각 fit)이고 모두 같은 높이·재질·색이다.
- 이름: 하나면 건물 ID, 여럿이면 `<건물 ID>#b0..N`(중심 동·북 순). **소유자** = 건물 ID.
- **앞 박스**: 도로 쪽 면의 `setback`이 가장 작은 박스. 문·전면·간판·마당·실외기·가스관은 앞 박스에만.
- 층수 `F ≥ 1`와 층고 `fh = height_m / F`. 모든 층 경계 `k·fh`가 박스 꼭대기와 맞는다. `fh < 2.0`이면 창이 없다(경고).

## Facing (도로 쪽 면)
박스마다 하나 또는 없음. `side`(f/b/l/r), `L`(면 길이), `setback`(면에서 도로 판 가장자리까지, m), `setback_s`(그 쪽에 인도가 있으면 인도 폭을 뺀 값), `road`(가장 가까운 피처). 60 m 안에 도로가 없으면 없음(`no_facing`), 8 m 넘게 떨어지면 `far_facing`. 면 좌표 `along = (p − c)·(up × n̂)`: 도로에서 면을 보아 왼쪽이 음수. 면마다 **가려짐**(바깥으로 민 점이 다른 박스 안: 형제 0.3 m, 다른 건물 2.5 m) 여부가 있고 가려진 면에는 창·실외기·간판이 없다. 도로 쪽 면의 **빈 구간** = 계단실·돌출창이 차지하지 않는 `along` 구간; 창·전면·띠간판·실외기·현판은 빈 구간 안에만 놓인다.

## BuildItem 확장 (U2 BuildItem에 더하는 필드)

| 필드 | 뜻 |
|---|---|
| `kind` | 기존 6종 + `roof`, `facade`, `sign`, `prop` |
| `owner` | 부속 항목이 속한 건물 ID(없으면 비움). `Manual`에 같은 ID가 있으면 몸체와 부속이 모두 생략된다 |
| `shape` | `Block`(기본), `Wedge`, `CornerWedge`, `Cylinder`(세움: 크기 = 높이, 지름, 지름), `Ball` |
| `material` | 재질 이름(상수 집합 `MATERIALS` 안). kind 기본과 다를 때만 보낸다 |
| `color_name` | 색 이름(`PALETTE` ∪ `cfg["wall_colors"]` ∪ `<벽 색>_band`). 덩어리 머리의 색표가 RGB를 준다 |
| `reflectance` | 0이 아닐 때만 보낸다(창 0.25, 가게 전면 0.3, 유리 마감 0.2) |
| `text`, `ink`, `faces` | 간판만: 글자(`SIGN_TEXT`), 글자 색 이름, `Front` 또는 `LR`(양면 = SurfaceGui 2개, TextLabel 2개) |
| `shadow`, `collide` | kind 기본과 다를 때만 보낸다. 기본: building 있음·있음, roof 있음·있음, facade 없음·없음(마당 부품은 충돌 있음), sign 없음·없음, prop 없음·있음(노면·전선·울타리 판은 충돌 없음). 충돌하는 부속은 마당 부품과 주차 차량뿐이다 |

### kind별 의미

| kind | 무엇 | 소유자 | 폴더 |
|---|---|---|---|
| `building` | 몸체 박스(들) | 자기 자신 | `Buildings` |
| `roof` | 쐐기·모서리 쐐기·피라미드 | 있음 | `Roofs` |
| `facade` | 띠, 난간벽, 난간, 기단, 창, 띠창, 계단실, 돌출창과 그 창, 발코니 판·난간, 문, 캐노피, 셔터, 실외기, 가스관, 가게 전면·문·처마, 옥탑·물탱크, 옥상 글자 틀 기둥 | 있음 | `Facades` |
| `sign` | 띠간판, 층별 띠간판, 돌출간판(양면), 옥상 글자 틀 판, 현판(부품 + SurfaceGui + TextLabel) | 있음 | `Signs` |
| `prop` | 마당 담·되돌림·기둥·대문·등·관목(소유자 있음); 연석, 중앙선·차선, 횡단보도·정지선, 전봇대·가로대·변압기·전선, 가로등, 가로수, 주차 차량, 스쿨존 울타리·기둥·표지, 볼라드, 함(소유자 없음, group = 피처 ID 또는 교차점 이름) | 마당만 | `Props` |

이름: 소유 항목은 `<소유자>#<꼬리>`(BR-14.1 표), 가로는 `<피처 ID>#<구간>#<요소><번호>`, 교차점 소품은 `jct:<lat6>_<lon6>#<요소><번호>`.

## Sign (간판)과 Name (이름)
- 간판 = 부품 1 + 글자. 종류: 띠간판(가게 단위마다), 층별 띠간판(상가 2~6층), 돌출간판(양면), 옥상 글자 틀(7층 이상 상가), 현판(`public`). 자리·크기·`MaxDistance`는 BR-10.1. manifest `signs` = 항목 수, `labels` = 글자 면 수.
- 이름 = 접두어(40개, 자연·추상어) + 업종어(원형·층의 풀). 해시 `(소유자, 자리)`로 정해지고 다른 건물에 의존하지 않는다. 2~9자. 금지: 지명, 프랜차이즈·체인(`REAL_BRANDS`), 사진 속 실제 상호. 공공 기관(이름이 학교·행정복지센터·주민센터·경로당으로 끝남)은 대장 이름 그대로; 그 밖의 `public`은 `care` 풀.
- 글자는 `SIGN_TEXT = [가-힣A-Za-z0-9 ]{1,12}`를 통과한 한글 그대로 Luau 리터럴에 들어간다(Q6=A). 그 밖의 모든 글자는 U2 `SAFE_TEXT`.

## Junction (교차점)과 Slot (가로 슬롯)
- 교차점 = 둘 이상의 도로·보행로 피처가 공유하는 꼭짓점(위경도 6자리 반올림). 소품은 속한 칸이 만들고 인도 끊기는 어느 칸 소유든 적용한다. 팔 = 교차점에서 나가는 구간(피처 ID, 구간 번호 순), 종류별로 횡단보도·정지선·스쿨존 기둥·볼라드·함이 붙는다. 인도 조각은 교차점에서 `다른 폭 + 1 m`를 비우고 나뉜다(같은 도로의 이어짐은 제외).
- 슬롯 = 칸 소유 구간 위의 위치(`spacing/2 + j·spacing`, 번호 0부터), 쪽(L/R), 옆 거리. 요소(전봇대, 전선, 가로등, 가로수, 차)마다 종류·간격·쪽·옆 거리 규칙이 있다(BR-11). 교차점 6 m 안은 비운다.

## Manifest 확장

| 필드 | 뜻 |
|---|---|
| `items_<kind>` | 새 kind 포함 종류별 개수(자동) |
| `buildings_built`, `boxes`, `building_ids` | 만든 건물 수(소유자), 다중 박스 건물 목록(ID, 박스 수, 합산 fit), 소유자 전부(verify의 Manual 오타 탐지용) |
| `duplicates_dropped`, `buildings_skipped` | 중복 외곽선으로 뺀 `(뺀 ID, 남긴 ID)`; 입력 − 만든 건물 − 중복 |
| `details_used` | 세부 행이 있는 몸체 수 |
| `no_facing`, `far_facing` | 60 m 안에 도로가 없는 몸체; 8 m 넘게 떨어진 몸체 |
| `signs`, `labels`, `parts_total` | 간판 항목 수, 글자 면 수(TextLabel 수와 비교), 부품 총수 |
| `config` | 새 설정 키 포함 |

## 내보내기 파일 `details/<칸ID>.json` (git 포함)

```json
{
  "cell_id": "8930e0af13bffff",
  "details": [
    {"balcony": 0, "bay": 0, "building_id": "gis:11081057", "finish": "brick", "ground_use": "shop",
     "judged_at": "2026-10-13T12:00:00+00:00", "note": null, "roof_color": "dark", "rooftop": "none", "stair": "none"}
  ],
  "version": 1
}
```

행은 건물 ID 순, 키 정렬, 들여쓰기 2, UTF-8. 불러오기는 전체 검증(BR-7.5) 뒤에만 쓴다. U4의 `overrides/<칸ID>.json`(v1)은 바뀌지 않는다.

## Studio 쪽 구조

```text
Workspace
  Auto
    <칸ID>              속성 BuildComplete, Created, Skipped_<kind>
      Ground  Roads  Paths  Sidewalks  Buildings  Roofs  Facades  Signs  Props  Spawn
  Manual
    School              Claude가 손으로 만든 운동장, 담장, 교문·현판, 유리 계단탑, 2색 외벽, 별관 발코니, 정원 (BuildingId 없음; 이 폴더 아래에만 만들고 지우지 않는다)
    (끌어다 둔 박스)      사용자가 Auto에서 옮긴 부품: BuildingId 속성이 있어 Auto가 그 건물과 부속을 건너뛴다
ServerStorage
  MapBuilder            studio/Builder.luau (교체는 Clone 후 Destroy)
Lighting                Realistic, 15:00, Atmosphere, DepthOfField 없음 (사람이 한 번 바꿈)
```

## 파일 배치

```text
src/details_rules.py      입출력 없는 U5 규칙: 세부 합치기, 이름 생성, 글자 검사, 팔레트·치수 상수
src/details.py            세부 판단 명령(pending, record, list, export, import)
src/layout.py             새 순수 함수(중복 제거, 다중 박스, 도로 쪽 면·가림·빈 구간, 지붕·외장·간판·가로 항목, 교차점, 인도 끊기)
src/build_luau.py         리터럴 키 확장, 색표, manifest 확장, 세부 입력
studio/Builder.luau       새 kind, 모양·재질·반사율·소유자·그림자·충돌, 간판 GUI, kind별 Skipped, verify 확장
details/<칸ID>.json       세부 내보내기 (git 포함)
data/build/<칸ID>/        덩어리 파일과 manifest (git 제외)
```

## 이 유닛이 다루지 않는 것
- 건물 내부, 지형 고저차·하천·공원 지형, 롤플레이 기능.
- 사진 텍스처, 이미지 업로드, 크리에이터 스토어 모델, `Texture`·`Decal`·`MaterialVariant`·`Beam`·Union·MeshPart(BR-14.10).
- 필로티, 가게 셔터, 드라이브스루, 과속방지턱, 버스정류장, 벤치, 자전거도로(차고 셔터는 `ground_use = garage`일 때만).
- 층수·높이·벽 색·지붕 모양의 판단과 보정(U4가 계속 담당), 사진 촬영(U3), 데이터 수집(U1).
- 나머지 두 칸의 데이터와 3칸 FPS 최종 확인(U5 Build and Test 뒤의 다음 할 일).
