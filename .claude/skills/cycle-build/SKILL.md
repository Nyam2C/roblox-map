---
name: cycle-build
description: roblox-map 세션 흐름의 3단계 "구현". 칸 하나를 데이터 수집부터 Studio 생성까지 만들 때, 사용자가 "구현", "이 칸 만들어", "사이클 돌려", "생성", "Studio에 넣어"라고 할 때 쓴다. 칸 추가 절차를 단계별로 실행하고 멈춘 곳에서 이어간다.
---

# 구현 (세션 흐름 3/5)

인지·메모리가 끝난 뒤. 단계가 끝날 때마다 메모리의 "진행"에 한 줄 덧붙인다. 이미 끝난 단계(인지에서 확인)는 건너뛴다. 모든 명령은 저장소 루트에서. 주의점은 `aidlc-docs/lessons.md`.

## 단계

자동 확장(U8, `aidlc-docs/construction/plans/u8-auto-expand-plan.md`)에서는 메인 세션이 이 단계들을 에이전트에게 나눠 맡긴다(`cell-prep` 0~3b·4, `cell-judge` 4-2, `cell-facility` 0b-4·7b, `cell-build` 6·7, `cell-fix` 8). 그때는 사용자에게 묻지 않고(`.rbxl` 복사본 부탁 생략, 모두 데이터에서 다시 만들 수 있음), 업로드는 하지 않으며, 검증은 cycle-verify의 "자동 확장 게이트"로 한다.

### 0. 구역과 등급
칸이 어느 `regions/<구역>/region.toml`의 `cells`에도 없으면 넣는다(새 동네면 구역 폴더와 `region.toml`을 만든다: `name`, `cells`, 있으면 `school_polygons`, `spawn_*`, `[road_lanes_by_name]`). 칸별 판단 파일은 `regions/<구역>/cells/<칸>/`에 생긴다.
```bash
uv run src/tiers.py classify --cells <칸>      # -> regions/<구역>/tiers.json. 고칠 때: tiers.py set --cell <칸> --tier N --reason "..."
```
등급: 1급은 아래 모두, 2급·3급은 3·4단계(거리뷰·판단)를 건너뛴다(2급 기본값 분포는 첫 2급 칸에서 만든다).

### 0b. 중요 시설 후보 묻기 (사용자 승인)
수집(1단계) 뒤, 생성(6단계) 전에 칸마다 그 구간을 대표하는 시설 후보를 고른다: 역·출구, 백화점·큰 상가, 15층 이상 랜드마크, 이름 있는 광장·공원, 학교, 큰 공공·종교시설, 위성에만 있는 큰 시설. 근거는 OSM 태그·이름, 대장 층수·면적, 위성.
1. 후보를 칸별로 짧은 표(이름, 무엇, 왜)로 **채팅에서** 묻는다. 칸당 0~3개, 애매하면 빼고 적는다.
2. 사용자가 승인한 것만 7b(웹 사진)와 수작업(Manual, `src/<이름>.py` 생성기 + `manual.json` 등록)으로 상세하게 만든다. 승인 안 한 것은 자동 생성 그대로.
3. 기다리는 동안 다른 단계(거리뷰·판단·생성)는 계속한다. 후보와 답은 audit에.
4. 사용자가 "칸당 N곳"처럼 개수를 정해 맡기면(2026-10-16~) 묻지 않고 Claude가 고른다. **상시 기준(사용자 결정 2026-10-17): 칸마다 4~5곳**(후보가 모자라면 더 적게, 이유를 audit에). 별도 승인 없이 만든다. 스펙은 칸마다 서브에이전트 하나에 `facility-spec.md`(이 폴더)를 지침으로 주어 `{"facilities": [...]}` JSON을 받고, `key`·`building_ids`를 넣어 `regions/<구역>/facilities.json`에 합친 뒤(`cell`, `build` = building_ids) `uv run src/facilities.py`. 위성 겹쳐 보기에서 대지 안에 마당·주차장이 비어 있으면 `courtyard_m`(날개 깊이), 높이가 다른 동은 `split`/`per_building`으로 고친다. 높은 탑(20층 이상)은 높이 650 수직 캡처로는 안 보이니 비스듬히 높게 본다.

### 1. 수집
```bash
uv run --env-file .env src/cells.py --cells <칸>
uv run --env-file .env src/register.py --cells <칸>
```
확인: `done: 1 ok`, 건물 수.

### 2. 위성 모자이크와 나무
```bash
uv run --env-file .env src/satellite.py cell <칸>
uv run src/trees.py --cells <칸>
uv run src/fields.py --cells <칸>        # 학교 운동장 키트(U7 J): OSM 학교 영역 + 위성 -> regions/<구역>/cells/<칸>/fields.json
uv run src/roofs.py --cells <칸>         # 평지붕 윗면 색(7층 이하): 위성 -> regions/<구역>/cells/<칸>/roofs.json
```
`roofs.py`는 7층 이하만 읽는다(높은 건물은 위성에서 기울어 보임). 8층 이상 지붕 색은 `roofs.py`가 그리는 `data/compare/<칸>-tall-roofs.jpg`(높은 외곽선과 "gis 번호 층수")를 보고 `roofs.json`의 `"hand"`에 손으로 적는다(다시 돌려도 유지, 높을수록 지붕이 외곽선에서 비껴 보임). 수작업이 위성 나무 자리에 있거나 위성이 포장 광장·물놀이터를 수관으로 읽으면(겹쳐 보기에서 나무가 광장을 덮음) 그 사각형을 `cells/<칸>/courts.json`의 `clear`에 둔다(`courts.py` 참고, build_luau가 그 안 나무를 뺀다). `fields.py` 출력에 학교마다 `way:... sand|turf W x D studs`가 나오는지 본다(Overpass 504가 이어지면 결과가 그대로 남는다). 수작업이 있는 학교는 `manual.json`의 `osm`으로 `made_by: manual`이 되어 생성하지 않는다. 새 학교는 위성 겹쳐 보기(cycle-verify)에서 운동장 사각형을 확인한다.

### 2c. 지하철 출구 맞추기 (역이 칸 안이나 옆에 있을 때, 2026-10-15)
1. 이 칸과 이웃의 OSM 출구를 역별로 센다:
   ```bash
   sqlite3 data/map.db "select distinct json_extract(tags,'$.description'), json_extract(tags,'$.ref'), geometry from street_features where kind='subway_entrance' order by 1"
   ```
2. 그 역의 출구 수를 웹(나무위키 "<역>" 문서의 출구 목록 등)으로 확인하고 번호를 비교한다. 출구가 칸 경계 밖(이웃 칸)에 있을 수 있으니 이웃까지 본다.
3. 빠진 번호는 위성 모자이크(유리 지붕 사각형)와 거리뷰(번호판)로 위치를 읽어 `regions/<구역>/exits.json`에 적는다: `{"exits": [{"id": "exit:<역 영문>-<번호>", "ref": "6", "lat": ..., "lon": ..., "seen": "위성 유리 지붕 + 거리뷰 번호판"}]}`. `build_luau`가 OSM 출구처럼 유리 출입구를 만든다(자기 칸 것만). 출처는 audit에.
4. 다 맞으면 파일을 만들지 않고 audit에 "<역> 출구 N/N"만 남긴다.

### 3. 거리뷰 (1급 칸만)
`uv run src/capture.py --cells <칸>`을 `cell done`이 나올 때까지 반복(실행당 새 파노라마 100장 상한). 백그라운드로 돌리고 끝나면 확인. 403/429·형식 이상으로 `stopped`면 **우회하지 말고 멈추고** 사용자에게 알린다.

### 3b. 높이 (모든 칸, 2026-10-15)
땅 높이는 거리뷰 카메라 고도로 만든다(`regions/<구역>/elevation.json`, 생성할 때 build_luau가 자동으로 쓴다).
```bash
uv run src/elevation.py collect --region <구역>                 # 1급: 3단계에서 받은 파노라마의 고도
uv run src/elevation.py probe --region <구역> --cells <칸...>   # 모든 새 칸(2·3급은 이것만): 칸당 위치 조회 7번, 이미지 없음
```
collect는 `stopped: done`이 나올 때까지 반복. 그다음 다시 만들 칸 목록은 커밋된 고도와 비교해 한 번에 낸다:
```bash
uv run src/elevation.py moved --region <구역>                   # rebuild (... since HEAD): <칸...>
```
여기 나온 **이미 만든 칸도 unpack해서 6~7단계에서 같이 다시 만든다**(빠뜨리면 칸 경계에 턱). 차단(`blocked`)이면 멈추고 알린다. 칸 목록을 셸 변수로 넘길 때는 bash로(zsh는 `$C`를 낱말로 안 나눈다).

### 4. 판단 (눈가림)
1. `uv run src/estimate.py pending --cells <칸> --limit 200` 출력의 JSON 줄을 모아 70개 안팎으로 나눈다(200 넘으면 기록 뒤 다시 pending).
2. 묶음마다 서브에이전트 하나: `judge-prompt.md`(이 폴더)를 지침으로, 목록 파일과 출력 경로를 준다. 서브에이전트는 목록과 묶음 이미지만 읽는다(DB·overrides·details 금지).
3. 출력의 `judgements`와 `details`를 **각각 맨 바깥이 리스트인 파일로** 나눠(`{"judgements": [...]}` 그대로는 거부) `uv run src/estimate.py record --file <j.json>`, `uv run src/details.py record --file <d.json>`.
4. 메모에 개인 정보(사람, 번호판, 실제 상호)나 술·담배·도박 어휘가 없는지 훑는다(정규식 `\b(bar|pub|beer|soju|wine|liquor|tobacco|cigar\w*|casino|lotto|plate|face|person|people)\b`, 나오면 고쳐서 기록).
   - 대장 층수가 비고 사진도 못 센 고층은 위성에서 같은 넓이·지붕의 쌍둥이 동을 찾아 `overrides.py set`(사유에 근거).
5. `uv run src/estimate.py report --cells <칸>` → **확신 high인데 대장과 다른 건물은 묶음 이미지를 직접 다시 본다.** 판단이 틀렸으면 `uv run src/overrides.py set --building <id> --field floors_above --value <대장값> --reason "..."`(사유에 개인 정보 금지).

### 4T. 트레이싱 (4 대신, 사용자 결정 2026-10-18; 첫 칸은 시험이라 별로면 4로 되돌림)
CLAUDE.md "트레이싱으로 교체"·"G3 제거". 원리는 `aidlc-docs/construction/plans/facade-trace-experiment.md`, 에이전트 `cell-trace`(Sonnet, effort medium), 지침 `trace-prompt.md`(이 폴더), 코드 `src/facade.py`(사진)·`src/facade_parts.py`(조각 → 부품). 1급 칸만(2·3급은 사진이 없어 규칙 생성).
1. 상자와 카메라: `uv run src/build_luau.py --cells <칸>`(규칙 생성 한 번: `chunks.json`의 상자를 쓴다) → `uv run src/estimate.py plan --cells <칸>`(`review.json`).
2. `uv run src/facade.py cell --cells <칸>` → 사진 있는 건물마다 펼친 정면(80 px/m)·윤곽 그림, 목록 `data/facade/<칸>/trace-NN.json`(10동씩, 이전 목록·답은 지움). 목록마다 `cell-trace` 하나(동시에 4개까지), 답은 목록의 `output`(`trace-NN.out.json`).
3. 답의 `note` 개인 정보·술담배도박 어휘 검사 → `uv run src/facade.py record --cells <칸>`: 모서리를 준 건물은 다시 펴고, 조각 색과 맨 벽 색을 잰다(벽 색은 `walls.json`에 합침), `"unusable": "no building"`은 빈 땅(생성 안 함), 그 밖의 못 쓴 건물과 사진 없는 건물은 같은 칸의 층수·벽 길이가 가까운 트레이싱 건물 정면을 빌린다(길 쪽 벽, 벽돌 기둥은 자기 벽 색; 7층 이상·25 m 넘는 벽·한 층 넘게 차이 나면 규칙 생성). → `regions/<구역>/cells/<칸>/facade.json`(git).
4. `uv run src/build_luau.py --cells <칸> <이웃>`: `facade.json`의 건물은 가장 큰 상자의 규칙 정면 대신 조각(옆·뒤는 정면에서 두름, 지붕 덮개·기단·뒷마당은 남김), 벽 재질은 트레이서의 `finish`. 창·문·난간은 Union 키트(`kt=fu-<해시>`)이고 목록이 `data/build/<칸>/facade-kits.json`. counts의 `traced`·`facade_kits`를 본다.
5. Studio는 7단계에서 `facade-kits.luau`를 `studio-build.luau`보다 먼저.

알아 둘 것: 같은 창은 어느 건물에 있어도 같은 키트다(창·문·난간은 늘리지 않고 옮기기만). 7필드가 없으니 층수·높이는 대장 값, 벽 색은 맨 벽 측정(없으면 대장 기본), 빈 땅 판단은 트레이서의 "no building". 시험(2026-10-18, 6d3 5동, Sonnet): 3동 트레이싱·2동 못 씀, 약 3.5만 토큰·33초. 상자가 어긋난 건물에서 모서리를 안 줘 높이가 눌린 채 읽힌 적이 있어 지침에 먼저 확인하라고 넣었고 검사(`top`)가 잡는다.

### 5. 간판 이미지
새로 만들지 않고 이미 올린 이미지를 재사용한다(사용자 결정 2026-10-14, U7 K가 끝나기 전에는 글자 간판). 새 이미지는 정말 큰 랜드마크만, 칸당 최대 2장: 사용자에게 어떤 건물인지 알리고, 술·담배·도박 어휘·아이콘이 없는지 본 뒤 `signs.py generate` → 업로드 → `record`. 막히면(`403 User is moderated`) 재시도하지 않고 멈춘다.

### 6. 생성
활처럼 휜 동(위성·외곽선)은 `region.toml`의 `[arc_buildings]`에 `"gis:N" = 쐐기 수`(4~6)를 넣는다(자동 분할은 곡선을 못 따름, 2026-10-16). 먼저 새 칸의 이름 있는 큰길(secondary·tertiary 이상)에 `lanes` 태그가 없고 `region.toml`의 `[road_lanes_by_name]`에도 없으면, 위성에서 차로를 세어 넣는다(없으면 기본 폭이라 10차로 큰길이 2차로로 나온다; 2026-10-15 송내대로).
```bash
sqlite3 data/map.db "select distinct json_extract(tags,'$.name') from street_features where cell_id='<칸>' and kind='road' and json_extract(tags,'$.highway') in ('primary','secondary','tertiary') and json_extract(tags,'$.lanes') is null"
```
```bash
uv run src/build_luau.py --cells <칸>      # 덩어리 파일, chunks.json, manifest.json
```
경고(`warnings`)를 읽는다.

### 7. Studio 반영
1. `get_studio_state` → Edit인지. Play면 멈추고 기다린다.
2. 큰 변경 전이면 사용자에게 `.rbxl` 복사본을 부탁한다.
3. `cd data/build && python3 -m http.server 8766 --bind 127.0.0.1`(백그라운드). 포트는 칸 사이클 8766, 키트·스트리밍 세션 8765(2026-10-15 두 세션 합의, 동시에 돌아도 안 겹치게).
   - **MapBuilder 갱신**(`studio/ServerStorage/MapBuilder.luau`가 바뀐 뒤 처음): 저장소 `studio` 폴더를 8767에 띄우고(`python3 -m http.server 8767 --bind 127.0.0.1 --directory studio`) `execute_luau`로 `ServerStorage.MapBuilder.Source = HttpService:GetAsync("http://127.0.0.1:8767/ServerStorage/MapBuilder.luau")`(받는 동안만 HttpEnabled). 2026-10-18 판은 Union 키트에 재질·색을 덮어쓰지 않는다.
   - **트레이싱 칸**: `studio/install/facade-kits.luau`(`CELLS`만 바꿔)로 Union 키트를 먼저 만든다(`failed 0` 확인; 이미 있는 키는 건너뜀, 장소와 함께 저장되어 Play는 복제만).
4. `execute_luau`(Edit)로 `studio-build.luau`(이 폴더)의 내용을 `CELLS` 값만 바꿔 실행(칸 → 수작업 `Builder.settleManual`까지 한 번에; 땅은 칸의 기울인 판 조각이라 Terrain은 쓰지 않는다). `HttpEnabled`는 받는 동안만 켜고 결과의 `http=false`를 확인한다.
5. **미니맵·큰 지도 갱신**: Studio에 있는 칸을 모두 적어(`region.toml`의 `cells` 순서) `uv run src/minimap.py --cells <칸...>` → 같은 서버로 `studio/install/minimap-data.luau`를 `execute_luau`(Edit)로 그대로 실행(`ReplicatedStorage/MinimapData` 본체와 조각 모듈 `1`, `2`, …을 새로 넣음; 데이터는 조각마다 15만 자 아래로 나뉘어 Studio `Source` 한도 20만 자를 넘지 않는다, 2026-10-15) → `install-u6.luau`(스크립트만)를 받아 임시 ModuleScript `Source`에 넣고 `require`(칸을 만들거나 박스가 바뀔 때마다. 빠뜨리면 지도에 새 칸이 안 나온다).
   - **새 칸 동 이름**: `minimap.py`가 `regions/<구역>/places.json`에 채운 새 칸의 동을 칸 안 OSM `addr:subdistrict` 다수결(Overpass `nwr["addr:subdistrict"]`, 중심이 칸 안인 것)과 맞춰 보고 다르면 고쳐 다시 `minimap.py`(Nominatim은 칸 중심 한 점이라 자주 틀림: 563·69b·683·16f·45b·687·6a3).
5b. **칸 데이터(서버 근처 칸 만들기, 2026-10-15)**: 같은 서버로 `studio/install/cell-data.luau`를 `execute_luau`(Edit)에 그대로 실행한다. `ServerStorage/CellData/<칸>`(압축 데이터, 부품 수, 이웃 두 바퀴, 그 칸의 수작업 시설 `m1…`)이 갱신된다. 수작업 시설을 만들거나 고친 뒤에도 이 단계를 다시 돌린다(Play는 이 데이터로 만든다, `Manual/Landmark`만 늘 남음). 스크립트(`CellStreamer`, `CellLoading`, `PlayerMap`)는 5의 `install-u6.luau`가 넣는다. Play에서는 `CellStreamer`가 저장된 Auto 칸을 지우고 플레이어 주변 19칸만 만드니, 칸을 새로 만들고 이 단계를 빠뜨리면 Play에서 그 칸이 보이지 않는다.
5c. **정리해서 저장(2026-10-15)**: 장소는 정리된 상태(상세 칸·수작업 없이 칸 데이터만)로 저장한다. 사용자가 저장하기 전에 `studio/install/pack.luau`를 `execute_luau`(Edit)로 돌린다(꺼내 둔 칸의 수작업을 먼저 데이터로 쓰고 Auto·Manual을 비움, 칸 데이터가 없는 칸이 있으면 멈춤). 편집·검수할 칸은 `studio/install/unpack.luau`의 `CELLS`에 적어 꺼낸다. 거리뷰 대조·위성 겹쳐 보기처럼 이웃이 보이는 확인 전에는 그 칸의 이웃 한 바퀴도 꺼낸다. 수작업을 고칠 때는 그 칸을 꺼낸 상태에서 고친다(꺼내지 않은 칸의 수작업은 pack이 덮어쓰지 않음). **정리된 장소에서 시설을 넣을 때는 `Facilities.luau`에 이번 시설만 담은 JSON을 넘긴다**(`data/build/manual/facilities.json`에서 키를 골라 `facilities-new.json`; 통째로 넘기면 Workspace에 없는 다른 칸 시설을 모두 새로 만들어 겹친다). **새 칸은 시설을 넣은 뒤 그 칸을 한 번 더 짓는다**(Auto는 짓는 순간 Manual의 BuildingId만 비켜서므로, 먼저 지은 칸의 Auto 건물이 시설을 덮는다; 다시 지은 결과의 `skipped_manual`이 0보다 큰지 본다).
6. 서버를 내린다: `pkill -f "http.server 8766"`.
7. 키트 메시(U7 H): Builder는 나무 수관을 `ServerStorage/Kits/crown-1`, `crown-2`(MeshPart)에서 복제한다. 없으면 `MapBuilder: kit ... is not in ServerStorage/Kits`로 멈춘다. 새 장소면 `data/kits/*.obj`(`uv run src/kits.py trees`)를 사용자가 홈 탭 Import로 가져오고, Claude가 MeshId가 `kits.MESH_IDS`와 같은지 본 뒤 그 MeshPart를 `ServerStorage/Kits/<이름>`으로 옮긴다. 새 메시를 올려야 하면 사용자에게 먼저 묻는다(검수). 줄 메시 키트(`stk-*`, `uv run src/kits.py stacks` → `data/kits/stacks.obj` 한 파일에 52개)는 `kits.MESH_IDS`에 들어간 것만 `build_luau.py`가 쓰고, 그 MeshPart도 `ServerStorage/Kits/<이름>`에 있어야 한다(충돌 끔, `CollisionFidelity = Box`).
8. Builder(`studio/ServerStorage/MapBuilder.luau`)나 게임 스크립트(`studio/ServerScriptService/*.server.luau`)를 바꿨다면 먼저 교체한다: 그 파일 복사본만 둔 폴더를 같은 서버로 내놓고 Studio에서 `HttpService:GetAsync`로 받아 새 인스턴스의 `Source`에 넣고 원본 Destroy(require 캐시). 수작업은 `studio/manual/<구역>/*.luau`를 바로 실행하지 않고 `uv run src/anchors.py build --region <구역>` → `uv run src/anchors.py script --region <구역> --name <이름>`이 만든 `data/build/manual/<이름>.luau`(기준점 앞부분 + 스크립트)를 같은 서버로 내놓고 ModuleScript `Source`에 넣어 `require`한다. 스크립트에는 박스 좌표를 숫자로 쓰지 않고 `A.box`·`A.frame`·`A.boxes`를 쓴다(U7 F).

### 7b. 중요한 장소 사진 (웹)
0b에서 사용자가 승인한 장소(그리고 `manual.json` 후보)마다, 수작업을 만들기 전에:
1. `WebSearch`로 "<동> <장소 이름>", "<장소 이름> 사진/전경/광장/정문"을 찾는다(이름이 없으면 근처 랜드마크 + "뒤/앞 광장"). `WebSearch`는 `blog.naver.com`을 주지 않으니(차단 도메인, 2026-10-17) 네이버 블로그는 네이버 검색 페이지에서 찾는다(아래 2).
2. 사진이 있을 만한 페이지(블로그·뉴스·지자체·나무위키)를 **내장 브라우저**로 열어 사진을 본다(`WebFetch`는 글만 준다). 내장 브라우저가 없으면(키로 띄운 `claude -p`, 에이전트) `uv run src/webshot.py <스크래치 폴더> <URL...>`이 창 없는 크롬으로 열어 스크롤하며 PNG 조각으로 찍으니 `Read`로 보고 다 보면 폴더를 지운다. 네이버 블로그는 `https://m.search.naver.com/search.naver?where=m_blog&query=<장소>`를 찍으면 결과 화면과 `LINK` 줄(글 주소)이 나오고, 그 글 주소를 다시 넘긴다(`blog.naver.com`은 자동으로 `m.blog.naver.com`으로 열어 iframe 없이 사진이 보임). 사진만 훑을 때는 `where=m_image`. 로그인·CAPTCHA가 나오면(`BLOCKED`) 그 페이지는 건너뛰고 우회하지 않는다.
3. 거리뷰 파노라마를 장소 쪽으로 잘라 함께 본다(`projection.render_crop`, 장소 중심 75 m 안).
4. 본 것(바닥 재질, 화단, 시설물, 색, 높이 비율)과 출처 URL을 audit에 적고, 수작업(Manual)이나 규칙에 숫자로만 넣는다. 사진 파일은 저장소에 넣지 않는다.
5. 못 찾으면 "웹 사진 없음"이라고 적고 위성·거리뷰로 진행한다.

### 8. 규칙을 고칠 때
**먼저 공개 레퍼런스를 본다**(CLAUDE.md "공개 레퍼런스 먼저"): 고칠 것(창, 발코니, 지붕 끝, 학교 운동장 등)과 같은 것을 공개 작품에서 찾아 `MCP_Test`에서 재거나(스크립트 즉시 삭제, Play 금지, 다 보면 지움) 스크린샷으로 비율을 본다. 본 것(자산 ID·출처, 잰 값)을 계획서 U7 L이나 설계 문서에 적고, 숫자와 방식만 가져온다. 수작업(Manual)을 새로 만들 때도 같다.

검증에서 여러 건물에 공통인 문제가 나오면 `src/details_rules.py`·`src/layout_details.py`(또는 해당 모듈)를 고치고 테스트를 고치거나 더한 뒤:
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/ -q
```
통과하면 이미 만든 칸들도 6~7단계로 다시 만든다(결정적 생성이라 그대로 반영된다). 한 건물만의 문제는 `overrides.py`나 수작업(Manual).

그다음 `cycle-verify`로 간다.
