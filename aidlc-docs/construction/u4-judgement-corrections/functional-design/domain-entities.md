# U4 판단·보정 — Domain Entities

기술과 무관한 논리 모델이다. 실제 열 이름과 파일 형식은 코드 생성에서 확정한다.
근거: U4 Functional Design 답변 Q1=A(122개 전부), Q2=A(눈가림), Q3=B(벽 색·지붕 모양), Q4=A(high만 사진이 이김), Q5=A(대장 높이는 범위 안일 때), Q6=B(U2에 높이와 벽 색), Q7=A(값만 보정), Q8=A(전체 비교 쌍), 기본값 D-U4-1~16.

## 관계 한눈에 보기

```text
buildings (U1: 대장 층수·높이, OSM 참고값) ---------+
building_views, captures (U3: 크롭, 파노라마 위치) --+--> [눈가림 묶음 이미지] --> Claude가 사진을 보고 판단
                                                    |                                    |
                                                    |                          estimates (판단, 건물당 1행)
                                                    |                                    |
overrides (보정, 건물·필드당 1행) -------------------+--> effective_building (순수 함수) --+--> EffectiveBuilding
                                                                                          |
                          +---------------------------------------------------------------+
                          v                              v                                v
              U2 build_luau (높이, 벽 색,        확인 목록(ReviewFlag)            비교 쌍(ViewPair): Studio 캡처 + 크롭
              속성 HeightBasis·Review)                                             사용자와 같이 보고 어긋나면 overrides.set
                                                                                          |
overrides/<칸ID>.json  <---- 내보내기 (보정 + 판단, git) <------------------------------------+
```

## 입력 (읽기 전용)

- **`buildings`** (U1): 칸 소유 건물. 쓰는 열은 `building_id`, `cell_id`, `status`, `name`, `outline`, `centroid`, `floors_above`, `height_m`와 참고용 `osm_height_m`, `osm_levels`. **눈가림 단계(판단하기 전)에는 `floors_above`, `height_m`, `osm_*`, `floors_below`, `usability_code`, `building_area`를 보여 주지 않는다**(BR-1.3).
- **`building_views`, `captures`** (U3): 크롭 경로와 순위, 파노라마 위치·방향, 크롭의 `yaw_deg`, `fov_deg`, `pitch_deg`, 학교 면 사진의 `face_deg`.
- **설정**: 층고 3.4 m, 기본 높이 10 m(U2·U3와 같은 값), 층당 높이 허용 범위(2.5~5 m, 새 설정), 비교 묶음 크기 12(새 설정), 벽 색표.

## Judgement (`estimates` 테이블)
건물 하나당 한 행. Claude가 사진을 보고 기록한 판단이며 **대장 값과 비교한 결과는 저장하지 않는다**(비교는 `effective_building`이 매번 계산한다).

| 필드 | 의미 |
|---|---|
| `building_id` | 대상 건물 (기본키) |
| `cell_id` | 건물이 속한 칸 (내보내기와 고아 보고용, 기록할 때 건물에서 복사) |
| `floors_seen` | 사진에서 센 지상층수(1~100). 가려서 못 세면 비움(모름) |
| `confidence` | `high`(또렷이 셈), `medium`(일부 가림), `low`(추측). `floors_seen`이나 `height_est_m`가 있을 때만 필수 |
| `height_est_m` | 층수를 못 센 경우의 사진 기하 추정 높이(2~500 m). `floors_seen`이 있으면 쓰지 않는다 |
| `wall_color` | 벽 색 팔레트 키, 모르면 비움 |
| `roof_shape` | `flat`, `gable`, `hip`, `shed`, `other`, 모르면 비움 |
| `views_used` | 판단에 쓴 `building_views`의 순위 목록 (숫자만, 파일 경로를 쓰지 않는다) |
| `note` | 짧은 외관 메모(300자 이하). 사람·차량 번호판·개인 정보를 쓰지 않는다 (BR-8.8) |
| `judged_at` | 기록 시각. 내용이 같은 판단을 다시 기록하면 시각도 바꾸지 않는다 |

근거 코드는 저장하지 않고 값에서 정해진다: `floors_seen`이 있으면 층수 근거는 `photo_count`, `height_est_m`만 있으면 높이 근거는 `photo_geometry`.

## Override (`overrides` 테이블)
건물·필드 하나당 한 행. 사용자와 Claude가 같이 보고 고친 값이며 어떤 재실행도 지우지 않는다.

| 필드 | 의미 |
|---|---|
| `building_id`, `field` | 기본키. `field`는 `floors_above`, `height_m`, `wall_color`, `roof_shape` 넷뿐이다 (Q7=A) |
| `cell_id` | 건물이 속한 칸 (내보내기용, 건물이 DB에서 사라져도 칸 파일에 남도록 보정할 때 복사) |
| `value` | 필드에 맞는 값 (정수, 소수, 팔레트 키, 지붕 모양) |
| `reason` | 사유(필수, 1~500자). 출처를 적는다: 누가 어느 사진이나 화면을 보고 정했는지 |
| `set_at` | 기록 시각. 값과 사유가 같은 보정을 다시 넣으면 시각도 바꾸지 않는다 |

## EffectiveBuilding (저장하지 않음, 매번 계산)
건물 하나의 최종값. 필드마다 값과 근거가 함께 나온다.

| 필드 | 의미 |
|---|---|
| `floors_above` | 최종 지상층수 또는 없음. 근거: `override`, `register`, `photo_count`, 없음 |
| `floors_status` | `override`, `verified`, `unverified`, `changed`, `conflict`, `filled`, `none`, `unjudged` (BR-3) |
| `height_m` | 최종 높이(항상 0보다 큼). 근거: `override`, `register`, `from_floors`, `photo_geometry`, `default` (BR-4) |
| `wall_color` | 최종 팔레트 키. 근거: `override`, `photo`, `default`(밝은 회색) |
| `roof_shape` | 최종 지붕 모양. 근거: `override`, `photo`, `default`(`flat`) |
| `flags` | 확인 목록 사유 (ReviewFlag) |
| 참고값 | 대장 층수·높이, 사진 층수·확신도, OSM 높이·층수. 합치기 순서에 들어가지 않는다 |

## ReviewFlag (확인 목록 사유, 저장하지 않음)
`conflict`(사진과 대장이 어긋나는데 대장을 유지함), `changed`(high 확신 사진 값으로 대장을 바꿈), `filled`(대장에 층수가 없어 사진으로 채움), `low_confidence`(쓰인 사진 값의 확신이 low), `default_height`(근거 없이 기본 높이), `height_out_of_range`(대장 높이가 층수와 같은 층수에서 층당 2.5~5 m를 벗어남), `osm_differs`(기본 높이를 쓰는데 OSM 높이·층수 태그가 있음), `unjudged`(판단 행이 아직 없음).

## Palette (벽 색표, 설정값)
| 키 | RGB | 키 | RGB |
|---|---|---|---|
| `white` | 236, 236, 232 | `brown` | 125, 92, 70 |
| `cream` | 236, 224, 190 | `pink` | 225, 170, 170 |
| `beige` | 214, 192, 156 | `light_gray` (기본) | 200, 200, 205 |
| `yellow` | 232, 205, 110 | `dark_gray` | 110, 112, 118 |
| `orange` | 214, 140, 80 | `green` | 120, 150, 110 |
| `red_brick` | 170, 90, 70 | `blue` | 110, 140, 180 |

`other`는 색표에 없는 색이다. 칠할 때는 `light_gray`와 같이 칠하고 `note`에 색을 적는다. 기본값 `light_gray`는 U2가 지금 모든 건물에 칠하는 색과 같아서, 판단이 없는 건물은 지금과 똑같이 보인다.

## ViewPair (비교 쌍, 저장하지 않음)
건물마다 하나(학교 건물은 면 사진마다 하나, 최대 6): 같은 위치·방향·시야각으로 둔 Studio 카메라 캡처와 U3 크롭을 나란히 놓은 것. 합성 이미지 파일이 가능하면 `captures/<칸ID>/review/<건물 ID(콜론은 밑줄)>__<순위>.jpg`로 만든다(git 제외). 파일로 합칠 수 없으면 캡처와 크롭을 같은 차례에 따로 보여 준다. 쌍마다 건물 ID, 최종 층수·높이와 근거, 벽 색, 확인 목록 사유를 적는다.

## ExportFile (`overrides/<칸ID>.json`, git 포함)
```text
{ "version": 1, "cell_id": "...",
  "overrides": [ {building_id, field, value, reason, set_at}, ... ],   # (building_id, field) 순
  "estimates": [ {building_id, floors_seen, confidence, height_est_m, wall_color, roof_shape, views_used, note, judged_at}, ... ] }  # building_id 순
```
키를 정렬하고 들여쓰기 2칸, UTF-8, 끝에 줄바꿈 한 개. 같은 DB 상태에서는 글자까지 같다.

## 파일 배치
```text
captures/<칸ID>/sheets/<건물 ID(콜론은 밑줄)>.jpg      눈가림 묶음 이미지 (git 제외)
captures/<칸ID>/review/<건물 ID>__<순위>.jpg          비교 쌍 (git 제외)
data/build/<칸ID>/review.json                         비교 묶음 계획과 카메라 값 (git 제외)
overrides/<칸ID>.json                                 보정 + 판단 (git 포함)
```

## 이 유닛이 다루지 않는 것
- 지붕을 모양대로 만들기, 층 구분, 창문·문, 간판, 가로시설은 U5.
- 자동 생성에서 건물 빼기(`skip`)와 외곽선 교체: 질문 Q7에서 값만 보정하기로 했다. 필요하면 U2의 `Manual` 규칙을 쓴다.
- 사진 수집과 크롭은 U3. U4는 `captures`, `building_views`를 읽기만 한다.
