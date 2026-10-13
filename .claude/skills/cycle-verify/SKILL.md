---
name: cycle-verify
description: roblox-map 세션 흐름의 4단계 "검증". 칸을 Studio에 만든 뒤, 규칙을 고친 뒤, 사용자가 "검증", "확인해", "위성이랑 비교", "거리뷰랑 비교", "FPS 재"라고 할 때 쓴다. 테스트·verify·위성 겹쳐 보기·거리뷰 대조·FPS를 기준과 비교하고, 못 넘으면 구현으로 돌려보낸다.
---

# 검증 (세션 흐름 4/5)

각 항목의 기준을 넘는지 본다. 하나라도 못 넘으면 원인을 적고 `cycle-build`(8단계: 공통 문제는 규칙으로)로 돌아간다. 결과는 마지막에 표로 보고한다.

## 1. 코드
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/ -q
```
기준: 전부 통과. 속성 테스트가 새 예시로 실패하면 규칙 문제인지 테스트 상한 문제인지 가른다(예산 상한을 올릴 때는 이유를 주석에).

## 2. 생성 결과
- `data/build/<칸>/manifest.json`: `warnings`를 읽고 하나씩 원인을 안다(예: 가게 앞면을 놓을 자리가 없음).
- Studio 생성 결과(studio-build.luau의 반환): `verify=true`, `problems` 없음, `sunk_cylinders=0`, `http=false`, 가장 느린 덩어리 10 ms 이하.

## 3. 위성 겹쳐 보기 (모든 칸)
1. 칸 중심 위 높이 650에서 바로 아래로 `screen_capture`(`camera_position = {x, 650, z}`, `look_at_position = {x, 0, z - 1}`). 70° 시야각, 1631 × 882 창이면 0.974 px/stud.
2. ```bash
   uv run --env-file .env src/satellite.py compare <캡처.jpg> <x> <z> 0.974 data/compare/<칸>
   ```
3. `<칸>_side_by_side.jpg`, `<칸>_blend.jpg`를 보고 확인: 큰길 폭, 건물 위치·모양, 데이터에 없는 시설(운동장, 체육관, 주차장), 건물로 잘못 잡힌 시설, 나무 띠, 높은 건물은 원근으로 커 보인다는 점.
4. 사용자에게 겹친 그림을 보낸다(`SendUserFile`).

## 4. 거리뷰 대조 (1급 칸)
1. `uv run src/estimate.py plan --cells <칸>` → `data/build/<칸>/review.json`.
2. Studio 시야각 83.58로 바꾼다. 쌍 8~12개를 골라(랜드마크, 처음 보는 유형, 확인 목록, 고르게 섞어) **하나씩** `screen_capture`(카메라 위치·바라보는 점은 review.json 그대로).
3. 캡처 경로를 `{쌍 키: 경로}` JSON으로 → `uv run src/estimate.py compose --cells <칸> --captures <json>` → `captures/<칸>/review/`.
4. 쌍을 세로로 이어 붙여 보고, 사용자에게 보낸다.
5. 자주 나온 문제(lessons 참고): 창 크기·수, 난간, 나무가 가림, 가게 앞면, 계단실 색, 건물 유형(아파트·교회·공장), 간판 글자(만든 직후 비어 보이면 1분 뒤 다시).
6. 끝나면 카메라 `Fixed`, 시야각 70으로 되돌린다.

## 5. 성능
- 사용자가 Studio 창을 앞에 두고 Play → Client에서 `RenderStepped` 30~75초 기록(평균, 1초 최저, 가장 느린 프레임). 15 고정이면 창이 뒤에 있는 것(무효).
- 측정 위치: 칸에서 가장 빽빽한 곳(상가 거리, 아파트, 주택 밀집).
- 기준(architecture.md 5절): PC 평균 60, 1초 최저 55 이상. 부품 수는 칸당 예산과 비교.
- 사용자가 Play 중일 때는 캐릭터를 움직이지 말고 기록만.

## 6. 보고

| 항목 | 기준 | 결과 |
|---|---|---|
| 테스트 | 전부 통과 | |
| verify / sunk / http | ok / 0 / false | |
| 경고 | 원인 앎 | |
| 위성 | 큰 차이 없음 | |
| 거리뷰 | 공통 문제 없음 | |
| FPS | 60 / 55 | |

못 넘은 항목과 다음 조치(규칙 수정 / 보정 / 수작업 / 나중)를 적고, 다 넘으면 `cycle-record`로 간다.
