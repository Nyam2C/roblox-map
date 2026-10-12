# U3 거리뷰 캡처 — Domain Entities

기술과 무관한 논리 모델이다. 실제 열 이름과 파일 형식은 코드 생성에서 확정한다.
근거: U3 Functional Design 답변 Q1=C(`streetlevel` 기본), Q2=B(건물마다 방향이 다른 파노라마 최대 3장), Q3=C(120 m), Q4=A(zoom 1), Q5=A(U3가 건물별 크롭 생성), Q6=A(Playwright 대비책은 지금 만들지 않음), 기본값 D-U3-1~12.

## 관계 한눈에 보기

```text
Building 1 --- * BuildingView * --- 1 Panorama
                     |                  |
                crop 파일(건물 칸 폴더)   이미지 파일(파노라마 칸 폴더)
Cell 1 --- * CollectionRun (unit = C3)
```

## Panorama (`captures` 테이블)
파노라마 한 장당 한 행. 여러 건물이 같은 파노라마를 쓴다.

| 필드 | 의미 |
|---|---|
| `pano_id` | 네이버 파노라마 ID(문자열, 유일) |
| `cell_id` | 파노라마 위치가 속한 H3 칸 |
| `lat`, `lon` | 파노라마 위치 |
| `heading_deg` | 파노라마 정면 방향(북쪽 0, 시계 방향, 0 이상 360 미만). 원천은 라디안이고 도로 바꿔 저장한다 |
| `captured_at` | 촬영일(UTC) |
| `is_latest` | 그 위치에서 가장 최근 촬영본인지 |
| `zoom`, `width`, `height` | 받은 해상도(zoom 1이면 6144×1024) |
| `file_path` | `captures/` 기준 상대 경로 |
| `status` | `found`(메타데이터만 확인), `downloaded`(이미지 저장됨), `failed` |
| `downloaded_at` | 내려받은 시각 |

## BuildingView (`building_views` 테이블)
건물과 파노라마의 짝. 건물마다 최대 3행(순위 1~3)이거나 "사진 없음" 한 행이다.

| 필드 | 의미 |
|---|---|
| `building_id` | 대상 건물(`buildings`) |
| `rank` | 선택 순서(1이 가장 가까운 것) |
| `pano_id` | 짝이 된 파노라마(`no_photo`면 비어 있음) |
| `distance_m` | 건물 중심점에서 파노라마까지 거리(m) |
| `bearing_deg` | 파노라마에서 건물 중심점을 보는 방위각(북쪽 0, 시계 방향) |
| `yaw_deg` | 파노라마 정면 기준 상대 방향, −180 이상 180 미만 |
| `fov_deg`, `pitch_deg` | 크롭의 시야각과 위쪽 각도 |
| `crop_path` | 크롭 파일의 상대 경로(건물이 속한 칸 폴더) |
| `status` | `planned`(짝만 정함), `cropped`(크롭 저장됨), `failed`, `no_photo`(거리 제한 안에 파노라마가 없음) |

- "사진 없음"도 한 행으로 남긴다. 그래야 다시 실행할 때 같은 건물을 또 조회하지 않는다.

## CaptureRun
기존 `collection_runs`를 쓴다(`unit = 'C3'`). `counts`에 들어가는 값: 조회한 건물 수, 찾은 파노라마 수, 새로 내려받은 수, 이미 있어서 건너뛴 수, 크롭 수, 사진 없는 건물 수, 실패 수, 멈춘 이유(`done`, `cap`, `blocked`, `failures`).

## 일시적 값 (저장하지 않음)
- **Candidate**: 건물 하나에 대해 거리 제한 안에서 찾은 파노라마 후보(`pano_id`, 위치, `distance_m`, `bearing_deg`).

## 파일 배치 (git 제외, 사람 얼굴과 번호판이 찍힐 수 있다)

```text
captures/
  <파노라마 위치의 칸 ID>/<파노라마 ID>/zoom1.jpg, meta.json
  <건물이 속한 칸 ID>/crops/<건물 ID(콜론은 밑줄로)>__<파노라마 ID>.jpg
```

## 이 유닛이 다루지 않는 것
- 층수와 외관 판단은 U4가 한다. U3은 사진과 짝(`building_views`)만 준다.
- 파노라마 이외의 이미지(위성, 항공)는 쓰지 않는다.
