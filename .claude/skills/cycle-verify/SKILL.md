---
name: cycle-verify
description: roblox-map 세션 흐름의 4단계 "검증". 칸을 Studio에 만든 뒤, 규칙을 고친 뒤, 사용자가 "검증", "확인해", "위성이랑 비교", "거리뷰랑 비교", "FPS 재"라고 할 때 쓴다. 테스트·verify·위성 겹쳐 보기·거리뷰 대조·FPS를 기준과 비교하고, 못 넘으면 구현으로 돌려보낸다.
---

# 검증 (세션 흐름 4/5)

각 항목의 기준을 넘는지 본다. 하나라도 못 넘으면 원인을 적고 `cycle-build`(8단계: 공통 문제는 규칙으로)로 돌아간다. 결과는 마지막에 표로 보고한다.
**작업(칸 생성, 규칙 수정, 키트 추가)이 끝날 때마다 모든 항목을 끝까지 한다**(사용자, 2026-10-14). 일부만 보고 "검증 끝"이라고 하지 않는다. 못 한 항목은 표에 ❌로 남긴다.

## 1. 코드
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/ -q
```
기준: 전부 통과. 속성 테스트가 새 예시로 실패하면 규칙 문제인지 테스트 상한 문제인지 가른다(예산 상한을 올릴 때는 이유를 주석에).

## 2. 생성 결과
- `data/build/<칸>/manifest.json`: `warnings`를 읽고 하나씩 원인을 안다(예: 가게 앞면을 놓을 자리가 없음).
- Studio 생성 결과(studio-build.luau의 반환): `verify=true`, `problems` 없음, `http=false`, 가장 느린 덩어리 10 ms 이하(2026-10-15 지금 12~14 ms인 칸이 있음, 덩어리 크기를 50으로 줄여도 그대로라 70 유지). 땅에 묻힌 기둥 검사(`sunk_cylinders`)는 지형 높이 때문에 뺐다.

## 2b. 땅이 길을 덮는지 (모든 칸, 지형)
`terrain-check.luau`(이 폴더)를 `CELLS`만 바꿔 `execute_luau`(Edit)로. 새 칸과 3b단계 `rebuild`에 나온 칸 모두. 기준: `covered=0`(경사 땅 조각이 도로·인도·보행로 위로 올라온 점). 넘으면 `terrain.py`의 `BEND`·`TILE_UNDER`를 본다.

## 3. 위성 겹쳐 보기 (모든 칸)
1. 칸 중심 위 높이 650에서 바로 아래로 `screen_capture`(`camera_position = {x, 650, z}`, `look_at_position = {x, 0, z - 1}`). 70° 시야각이면 px/stud = 캡처 세로 px ÷ 910(= 2·650·tan 35°). 1631 × 882 창이면 0.974, 1528 × 689면 0.757. 캡처 크기를 보고 계산한다.
2. ```bash
   uv run --env-file .env src/satellite.py compare <캡처.jpg> <x> <z> <px/stud> data/compare/<칸>
   ```
3. `<칸>_side_by_side.jpg`, `<칸>_blend.jpg`를 보고 확인: 큰길 폭, 건물 위치·모양, 데이터에 없는 시설(운동장, 체육관, 주차장), 건물로 잘못 잡힌 시설, 나무 띠, 높은 건물은 원근으로 커 보인다는 점.
4. 사용자에게 겹친 그림을 보낸다(`SendUserFile`).

## 3b. 도로·인도 겹침 (모든 칸, 특히 볼 것)
사용자가 가장 지저분하다고 짚은 곳(2026-10-14). 칸의 교차로마다(특히 상하행이 나뉜 큰길, 회전 차로, 대각선 길, 교통섬) 높이 200~260에서 바로 아래로 `screen_capture`(하나씩). 확인:
- 인도·연석이 다른 도로의 차로 위나 중앙분리대 안에 있는가
- 횡단보도가 교차로 한가운데나 다른 도로 위에 있는가, 횡단보도가 겹쳐 두 겹인가
- 가로등·전봇대·나무가 차로 위에 있는가
- 칸 경계에서 도로·인도가 어긋나는가
- 위성 나무가 차도 위에 서 있는가(특히 `road_lanes_by_name`으로 넓힌 큰길)
규칙(`streets.sidewalk_pieces`의 차로 겹침 자르기, `_on_other_road`, 횡단보도 `on_other`)으로 고치고 `tests/test_layout_u5.py`에 사례를 더한다.

## 3c. 도로 위 건물 (모든 칸)
```bash
uv run src/road_overlaps.py --cells <칸...>
```
기준: 칸마다 0~1동(남는 것은 0.3~1 m² 모서리 닿음). 많으면 원인을 가른다: 도로가 실제보다 넓음(`layout.fit_road_widths`가 건물까지 좁힘, 대장 이름 차로 수는 큰길만), OSM 선이 건물을 지남(`driveways_off_buildings`가 작은 길을 건물 안에서 자름, 지하 진입로 tunnel은 뺌), 단순화 상자가 외곽선보다 큼(`layout_details.clip_to_roads`). 사용자 지적(2026-10-16): "도로에 건물이 걸치는 경우가 꽤 있어".

## 4. 거리뷰 대조 (1급 칸)
1. `uv run --with numpy==2.5.4 --with scipy==1.18.1 src/estimate.py plan --cells <칸>` → `data/build/<칸>/review.json`(numpy·scipy가 있어야 카메라가 지형 높이만큼 올라간다. 없으면 평지 높이라 경사 칸에서 땅속에 들어감).
2. Studio 시야각 83.58로 바꾼다. 쌍 8~12개를 골라(캡처는 **한 번에 하나씩, 병렬 호출 금지**: 동시에 보내면 시간 초과)(랜드마크, 처음 보는 유형, 확인 목록, 고르게 섞어) **하나씩** `screen_capture`(카메라 위치·바라보는 점은 review.json 그대로).
3. 캡처 경로를 `{쌍 키: 경로}` JSON으로 → `uv run src/estimate.py compose --cells <칸> --captures <json>` → `captures/<칸>/review/`.
4. 쌍을 세로로 이어 붙여 보고, 사용자에게 보낸다.
5. 자주 나온 문제(lessons 참고): 창 크기·수, 난간, 나무가 가림, 가게 앞면, 계단실 색, 건물 유형(아파트·교회·공장), 간판 글자(만든 직후 비어 보이면 1분 뒤 다시), 처음 보는 유형(백화점 → `store`), 고층 복합 건물(외곽선은 기단 전체: 기단 높이로 보정 + 탑은 Manual), manifest의 `underground facility` 경고(역사·지하주차장이 빠졌는지).
6. 끝나면 카메라 `Fixed`, 시야각 70으로 되돌린다.

## 4b. 중요한 장소 (웹 사진)
cycle-build 7b에서 본 사진과 Studio 캡처(같은 방향, 땅 높이)를 나란히 놓고 바닥·화단·시설물·색이 맞는지 본다. 사진을 못 찾은 장소는 표에 "웹 사진 없음".

## 5. 성능
- 사용자가 Studio 창을 앞에 두고 Play → Client에서 `RenderStepped` 30~75초 기록(평균, 1초 최저, 가장 느린 프레임). 15 고정이면 창이 뒤에 있는 것(무효).
- 40초 중 1초만 떨어지면(처음 가는 곳의 이미지·메시 첫 로딩) 같은 길을 한 번 더 걸어 본다. 두 번째에 기준을 넘으면 통과로 적는다.
- 사용자가 채팅에 답하면 Claude 창이 앞으로 와서 Studio가 15로 묶인다. 측정 코드는 **20초 기다린 뒤** 40초를 재고(그 사이 사용자가 Studio를 클릭해 맨 앞에 둠), **1초마다** FPS를 남겨 정확히 15인 초(창이 뒤)는 빼고 평균·최저를 낸다(2026-10-14).
- 사용자가 자리에 없으면 측정 직전에 `osascript -e 'tell application "RobloxStudio" to activate'`로 Studio를 앞에 둔다. 서버 쪽 무게(장소 메모리)를 볼 때는 Play의 서버에서 칸을 복제해 늘어난 메모리를 잰다(부품당 약 6.1 KB, 서버 한도 약 6 GB; 2026-10-15).
- 측정 위치: 칸에서 가장 빽빽한 곳(상가 거리, 아파트, 주택 밀집).
- 기준(architecture.md 5절): PC 평균 60, 1초 최저 55 이상. 부품 수는 칸당 예산과 비교.
- 사용자가 Play 중일 때는 캐릭터를 움직이지 말고 기록만.

## 6. 보고

| 항목 | 기준 | 결과 |
|---|---|---|
| 테스트 | 전부 통과 | |
| verify / http | ok / false | |
| 땅이 길 덮음 | covered 0 | |
| 경고 | 원인 앎 | |
| 위성 | 큰 차이 없음 | |
| 도로·인도 겹침 | 차로 위 인도·연석·횡단보도·가로등 0 | |
| 거리뷰 | 공통 문제 없음 | |
| 중요한 장소 | 웹 사진과 맞음(또는 없음) | |
| FPS | 60 / 55 | |

못 넘은 항목과 다음 조치(규칙 수정 / 보정 / 수작업 / 나중)를 적고, 다 넘으면 `cycle-record`로 간다.

## 자동 확장 게이트 (U8, 2026-10-17)

자동 확장(`aidlc-docs/construction/plans/u8-auto-expand-plan.md`)에서는 위 항목을 기계 판정으로 바꾼 게이트를 `cell-verify` 에이전트가 돌린다. 결과는 `data/gate/<칸>/`에, 기준은 `gate.toml`(메인만 고침), 허용 목록은 `regions/<구역>/cells/<칸>/gate-allow.json`(메인만). 사람이 직접 검증할 때도 같은 명령을 쓴다.

1. **G1 배치(3b·3c 대신)**: `uv run src/gate.py g1 --cells <칸>`. 차도 위 건물·나무 줄기·가로시설, 다른 도로 차도 위 인도·연석·보행로, 길 밖·두 겹 횡단보도, 칸 경계 양쪽 폭. 이웃 칸 도로도 보고 고가는 높이로 가른다.
2. **G1 Studio**: `road-clear-check.luau`(이 폴더)를 `CELLS`만 바꿔 `execute_luau`(Edit) → 답을 파일로 → `uv run src/gate.py studio --cell <칸> --file <답>`. `Workspace/Manual`까지 실제 부품으로 본다.
3. **G2 위성(3 대신)**: 3단계처럼 수직 캡처와 `satellite.py compare` → `uv run src/gate.py tiles --cell <칸> --satellite <out>_satellite.jpg --capture <캡처>` → 조각 9장을 보고 `{"tiles": [{"tile": "A1", "issues": [{"type", "severity": "major|minor", "note"}]}]}` → `uv run src/gate.py g2 --cell <칸> --file <답>`.
4. **트레이싱 검사(G3 대신, 1급 트레이싱 칸, 사용자 결정 2026-10-18 "과감하게 3빼자")**: `uv run src/facade.py check --cells <칸>` → `data/gate/<칸>/trace.json`. 건물마다 조각 테두리가 펼친 사진의 경계선 위에 있는 비율(`support`), 지붕 아래 조각이 벽 꼭대기 가까이 닿는지(`top`, 눌린 격자 잡기), 부품 수(Union 키트는 1개). 기준은 `gate.toml [trace]`. `gate.py summary`는 칸에 `facade.json`이 있으면 `g3` 대신 `trace`를 본다. 캡처·묶음·채점 에이전트 없음. 사용자가 보고 싶다고 하면 `facade.py compare`(같은 카메라 캡처 한 장)로 사진·렌더 묶음.
   **G3 외관 닮음(트레이싱 전 칸만, 1급, 쌍 전부)**: `estimate.py plan` → `uv run src/lookalike.py plan --cells <칸>` → 시야각 83.58로 plan의 캡처를 **하나씩**(찍힌 것이 그 건물인지 확인) → `{키: 경로}` → `uv run src/lookalike.py sheets --cells <칸> --captures <json>` → 채점은 **묶음만 보는 다른 에이전트**(`cell-score`, `lookalike-rubric.md`) → `uv run src/lookalike.py score --cells <칸> --file <답>`. 묶음을 만든 쪽은 `slots.json`(카나리아 위치)을 열지 않는다. 묶음을 둘 이상으로 나눌 때(16~20장씩) 중복 카나리아와 그 원본 쌍은 반드시 같은 채점자에게 준다(메인이 `slots.json`으로 나눔; 갈리면 총점 차로 채점이 무효).
5. **G4 FPS(5, 3칸마다)**: 걷기 기록 → `uv run src/gate.py fps --cell <칸> --avg <평균> --low <1초 최저>`.
6. **판정**: `uv run src/gate.py summary --cells <칸> [--need fps]` → `data/gate/<칸>/gate.json`. 1급은 G3까지, FPS는 차례일 때만 필요. `uv run src/gate.py status`로 전체.

게이트가 맞는데 걸린 것(실제 교통섬 나무 등)은 고치지 말고 근거와 함께 메인에 알린다. 게이트 파일(`gate.toml`, `gate-allow.json`, `src/gate.py`, `src/lookalike.py`, 이 폴더의 `lookalike-rubric.md`·`road-clear-check.luau`)은 메인만 고친다.
