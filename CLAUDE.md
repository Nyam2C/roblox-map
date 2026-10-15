# roblox-map

실제 동네를 Roblox 롤플레이/타운 맵으로 만든다. 구역은 H3 칸으로 나누고, 칸 하나씩 채우고 반복한다.

## AI-DLC

개발 요청은 `.aidlc-rule-details/core-workflow.md`를 먼저 읽고 따른다(v1.0.1, `aidlc-workflows`에서 복사). 질문은 채팅이 아니라 `aidlc-docs/` 안의 질문 파일에 `[Answer]:` 형식으로 둔다. 진행 상태는 `aidlc-docs/aidlc-state.md`, 입력 기록은 `aidlc-docs/audit.md`(덮어쓰지 말고 추가만).

구조·폴더·성능 예산·대규모 맵 최적화 방안은 `aidlc-docs/architecture.md`. 새 유닛을 시작하기 전에 그 문서와 맞는지 본다.

## 세션 흐름 (사용자 결정, 2026-10-14)

세션은 동시에 하나만 쓴다. 칸 하나에 세션 하나. 세션마다 이 순서로 간다. 단계마다 같은 이름의 프로젝트 스킬이 있다(인지 `cycle-recognize`, 메모리 `cycle-memory`, 구현 `cycle-build`, 검증 `cycle-verify`, 기록 `cycle-record`).

1. **인지**: `CLAUDE.md`, `aidlc-docs/lessons.md`(이전 세션이 알게 된 것), `aidlc-docs/aidlc-state.md`, 이 칸의 상태(`git log`, `data/build/<칸>/manifest.json`, Studio 상태)를 읽고 지금 어디까지 됐는지 파악한다.
2. **메모리**: 이번 세션의 칸·목표·시작 상태를 Claude 메모리에 적는다(세션이 끊겨도 다음 세션이 이어받게). 지난 세션 메모리 중 끝난 것은 정리한다.
3. **구현**: 칸 추가 절차(사이클)를 돈다.
4. **검증**: `verify`, 위성 겹쳐 보기, 거리뷰 대조, 테스트, FPS. 확인 기준을 못 넘으면 3으로.
5. **기록**: 핵심은 **개발 중 알게 된 것(코드만 봐서는 모르는 것, 다시 겪으면 시간이 드는 것)을 `aidlc-docs/lessons.md`에** 날짜·칸과 함께 남기고, **그 때문에 사이클 자체가 바뀌어야 하면 스킬(`.claude/skills/cycle-*`)을 고치는 것**이다(lessons는 알아 둘 것, 스킬은 다음에 그대로 할 것). 결정은 `CLAUDE.md`, 사용자 입력은 `audit.md`. 커밋은 자기 파일만(`git add -A`, `git stash` 쓰지 않음).

## 파이프라인

1. 구역 지정: 위경도 4점 또는 칸 ID → `src/cells.py`가 H3 칸으로 채움 (해상도 9 ≈ 변 200m·넓이 0.105km², 10 ≈ 변 76m)
2. 칸마다 V-World 건물통합정보(외곽선·층수·높이)와 OSM(이름·태그, 도로·가로시설)을 받아 `data/map.db`(SQLite)에 저장, `src/register.py`가 건물을 조립
3. 칸 하나를 Studio에 건물 박스로 생성 (Roblox Studio MCP 서버로 Luau 실행)
4. 칸 안 모든 건물을 네이버 거리뷰 자동 수집(`streetlevel` 라이브러리, 건물마다 파노라마 최대 3장과 건물 방향 크롭)으로 높이·색·지붕 등을 판단해 다듬음 (사용자 결정, 아래 결정 사항 참고)
5. 다음 칸으로 반복

## 결정 사항

- 형태는 데이터(OSM)로, 거리뷰는 외관 판단용으로만 쓴다. 사진을 텍스처로 복사하지 않는다(텍스처는 일반 재질로 현실감을 냄).
- 거리뷰 자동 캡처: 사용자가 칸 안 모든 건물에 대해 자동 캡처로 진행하기로 결정(2026-10-12). 2026-10-13에 브라우저 없이 되는 `streetlevel` 방식을 시험해서 이것을 기본으로 정했고 Playwright는 기술적 고장이 났을 때 새 작업으로 시작한다. 차단되면 다른 방식으로 바꾸지 않고 멈춘다. 네이버지도 약관은 확인하지 않고 진행하기로 사용자가 결정했다(2026-10-13). 약관 위반으로 생길 수 있는 차단 등의 위험은 사용자가 감수한다. 안전장치: 요청 속도 제한 / CAPTCHA·봇 차단이 나오면 우회하지 말고 중단 / 캡처 이미지는 로컬에만 두고 `captures/`로 git 제외(저장소가 public이고 이미지에 사람 얼굴·차량 번호가 있을 수 있음).
- 하네스는 새로 만들지 않는다. 필요한 건 **Studio 내장 MCP 서버**(https://create.roblox.com/docs/studio/mcp) 하나. 스킬은 세션 흐름 다섯 단계만 프로젝트 스킬로 둔다(`.claude/skills/cycle-recognize`, `cycle-memory`, `cycle-build`, `cycle-verify`, `cycle-record`; 사용자 결정 2026-10-14, 반복 작업이라서). 그 밖의 스킬은 만들지 않는다. 별도 저장소(`Roblox/studio-rust-mcp-server`)는 2026-04 아카이브되었고 Roblox가 내장 서버를 권장한다.
- Git은 스크립트와 `aidlc-docs/`만 관리한다(`main` 브랜치). 맵 원본 `.rbxl`은 바이너리라 diff가 안 되므로 `.gitignore`로 제외. 맵 백업은 Studio 클라우드 저장(Version History) + 큰 작업 전 `.rbxl` 복사본. `cells/`는 OSM에서 재생성 가능한 데이터라 제외.
- 건물은 외곽선 전체가 아니라 단순화한 박스로 시작한다. 비정형 외곽선은 필요한 건물만 나중에.
- **건물 내부는 만들지 않는다(사용자 결정, 2026-10-14)**: "내부 구현은 취소하고 외부 구현 퀄리티에 더 집중하자 다른 맵 탐방해보니 내부 구현은 안한다". U7 단계 3·4(내부 설계·코드)는 취소했고 내부 코드는 지웠다(2026-10-14, 지도 항목은 그대로). 설계 문서 `aidlc-docs/construction/u7-interiors/`는 기록으로 남긴다. 대신 외관 품질에 집중한다(U7 계획서 3절 L).
- 중요 시설은 사용자 승인 후 상세하게(사용자 결정, 2026-10-14: "만들기 전에 중요 시설(구간 대표)이라 판단되는 거는 나에게 물어서 내가 ㅇㅈ하면 더 상세하게 만들게"): 칸을 만들기 전(수집·등급 뒤, 생성 전)에 Claude가 그 구간을 대표하는 시설 후보(역, 백화점·큰 상가, 랜드마크 탑, 이름 있는 광장·공원, 학교, 큰 공공시설·종교시설 등)를 칸마다 고르고 이유(OSM 태그, 크기·층수, 위성)와 함께 채팅으로 묻는다. 사용자가 승인한 것만 수작업(Manual, 웹 사진·거리뷰·위성으로 상세)으로 만들고, 승인 안 한 것은 자동 생성 그대로 둔다. 후보와 답은 audit에 남긴다.
- 중요한 장소는 웹에서 사진 찾기(사용자 결정, 2026-10-14: "중요해보이는 장소는 웹서치로 사진 찾기"): 칸을 만들 때 중요한 장소(OSM 랜드마크·이름 있는 광장·공원·역·학교·백화점·큰 공공시설, 위성에만 있는 큰 시설, 수작업 후보)는 거리뷰·위성만으로 정하지 않고 웹 검색으로 그 장소의 사진(블로그·뉴스·지자체·나무위키 등 공개 페이지)을 찾아 본다. 검색 결과는 글이라 사진은 내장 브라우저로 페이지를 열어 보고, 바닥·화단·시설물·색·재질처럼 거리뷰가 못 보는 것을 확인한다. 사진은 보기만 하고 맵·저장소에 넣지 않는다(저작권·개인 정보). 본 출처 URL과 확인한 것은 audit·계획서에 남긴다. 사진을 못 찾으면 못 찾았다고 적고 거리뷰·위성으로 간다. 사용자가 사진을 주면 그것이 1순위.
- 공개 레퍼런스 먼저(사용자 결정, 2026-10-14): 건물이나 시설을 새로 만들거나 외관 규칙을 고칠 때는 **어떻게 만들지 정하기 전에 다른 사람이 공개한 작품부터 본다**. 볼 곳: 크리에이터 스토어 모델(`search_asset` → `Workspace/MCP_Test`에 넣고 스크립트를 바로 지움, Play 금지 → 치수·부품 구성·부품 수를 재고 캡처 → 지움), 복사 잠금이 풀린 공개 장소, DevForum·영상 등 공개 스크린샷(이미지로 보고 비율·디테일 밀도를 잼). 맵에는 남의 부품·메시·텍스처·이미지를 넣지 않고, 잰 숫자와 규칙만 `details_rules`·`layout_details`·키트·수작업에 들어간다. 복사 잠금 장소를 뜯거나 우회하지 않는다. 무엇을 봤는지(자산 ID·출처)는 계획서 U7 L이나 해당 설계 문서에 남긴다. 레퍼런스는 만드는 방식용이고, 위치·모양·높이는 여전히 데이터(V-World·OSM)와 위성·거리뷰가 정한다.
- 건물은 부품으로 조립한다. 같은 모양이 반복되어 재사용할 만한 조각(나무, 가구, 가로등, 창틀, 울타리 등)만 메시로 만들어 재사용한다. 건물 통째 메시는 하지 않는다(사용자 결정, 2026-10-14). 메시는 업로드 검수를 받으므로 처음 몇 개로 확인하고 자산 ID는 git에 고정한다. 첫 키트(2026-10-14, U7 H): 나무 수관 메시 2개(`src/kits.py`가 만든 `data/kits/crown-*.obj`, 사용자가 Studio Import 3D로 올림, 검수 통과, ID는 `kits.MESH_IDS`). Studio MCP는 이미지만 올릴 수 있어 메시는 사용자가 Import 3D로 올린다. Builder는 `ServerStorage/Kits/<이름>`(MeshPart)을 복제한다(키 `kt`).
- 첫 대상은 부천 심원고등학교(H3 해상도 9 칸 3개). 경험과 데이터가 쌓이면 같은 H3 칸 방식으로 다른 동네로 확장한다(사용자 결정, 2026-10-12).
- 최종 목표는 부천 전체(사용자 결정, 2026-10-14). 좌표 원점은 지금 하나를 부천 전체에 쓴다. 칸은 상세도 1·2·3급으로 나누고 등급은 OSM으로 자동 분류해 필요한 칸만 고친다. 장소는 커지면 행정동 경계로 나눈다. 수작업 장소는 Claude가 기준(OSM 랜드마크, 위성에만 있는 시설, 잘못 잡힌 건물, 거리뷰와 크게 다른 곳)으로 고르고 칸당 상한을 두며, 반복되는 것은 자동 키트로 만든다. 사용자는 결과만 확인한다. 공개 전에 OSM 출처 표시와 V-World 이용 조건 확인. 기준 기기는 PC. 질문과 답: `aidlc-docs/inception/requirements/scale-decisions-questions.md`.
- 높이: 층수는 V-World 건물통합정보(건축물대장 계열 속성) 1순위, 거리뷰로 층수와 비율을 검증, 값이 없거나 어긋나는 건물만 거리뷰 기하 추정. OSM 높이·층수 태그는 참고로 기록만 한다. 만든 뒤 사용자와 Claude가 같이 보고 현실 스케일에 맞는지 확인해서 보정한다(순서는 AI 추천, 거리뷰 기본으로 되돌릴 수 있음). 건물 외곽선과 층수·높이는 V-World 건물통합정보(`LT_C_BLDGINFO`, 개발키 `VWORLD_KEY`, 만료 2027-04-13)로 받는다(2026-10-13 시험: 심원고 3칸 건물 약 85~203개/칸, 층수 88~93%, 높이 45~62%, OSM은 5~10개/칸). 건축HUB API는 호출만 확인했고 U1에서는 쓰지 않는다. 인증키는 `.env`(`VWORLD_KEY`, `DATA_GO_KR_KEY`, git 제외)로만 쓴다.
- 작업마다 전 항목 검수(사용자 결정, 2026-10-14: "매번 작업 끝나면 이렇게 검수하고 특히 도로가 도보랑 도로랑 겹쳐서 지저분 하거든? 이거 잘봐야해"): 칸 생성·규칙 수정·키트 추가가 끝날 때마다 `cycle-verify` 전 항목(거리뷰 8~12쌍 포함)을 끝까지 하고, 도로·인도 겹침(3b)을 따로 본다. 인도·연석·가로등·횡단보도는 다른 도로의 차로 위에 두지 않는다.
- 지하철 출입구는 만든다(사용자 결정, 2026-10-14: "지하철 입구 정도는 만들면 안되나"). 역사·지하주차장 같은 지하 시설은 안 만들고(지하층 ≥ 2 × 지상층), 출입구만 OSM `railway=subway_entrance`에서 유리 상자 키트(번호판 "N번 출구")로 자동 생성한다. 계단은 어두운 우물로 보이게만(내부 없음). 이웃 칸 출구도 받아 역 쪽 방향을 정하고, 만드는 것은 자기 칸 출구만.
- 주차 차량은 만들지 않는다(사용자 결정, 2026-10-13). `config.toml`의 `car_spacing_m = 0`이고, 상자 두 개짜리 차가 어색해서 껐다. 나중에 넣는다면 메시 하나를 복제하는 방식이고 걷기 FPS를 잰 뒤에 한다.
- 나무는 위성 사진에서 읽는다(사용자 결정, 2026-10-13). `src/trees.py`가 V-World 위성 z19의 수관을 찾아 `regions/<구역>/cells/<칸>/trees.json`에 쓰고(첫 칸 371그루), `build_luau.py`가 그 파일이 있으면 규칙 가로수(7 m 간격) 대신 그 나무를 만든다. 옥산공원은 `studio/manual/bucheon-dodang/Park.luau`(Manual/Park, 위성 색으로 가른 흙·자갈·모래 바닥)이고 나무는 Auto의 위성 나무가 맡는다. 다른 칸은 위성 타일을 받고 `.json`(`tile_x0`, `tile_y0`)을 써 두면 같은 방법으로 된다.

## 칸 추가 절차 (확장할 때 이 순서 그대로, 2026-10-14)

칸 하나(또는 다른 동네의 새 칸)를 만들 때. 실행 순서와 명령은 `cycle-build`·`cycle-verify` 스킬에 있고, 아래는 요약이다.

0. 구역·등급: 칸을 `regions/<구역>/region.toml`의 `cells`에 넣고 `tiers.py classify --cells <칸>`(1급만 거리뷰·판단)
1. 수집: `cells.py --cells <칸>` → `register.py --cells <칸>`
2. 거리뷰: `capture.py --cells <칸>`을 `cell done`이 나올 때까지 반복(100장 상한)
3. 판단(눈가림): `estimate.py pending`(200개씩) → 사진만 보고 U4 판단과 U5 세부 판단을 같이 기록(`estimate.py record`, `details.py record`). 서브에이전트에 나눌 때도 DB·overrides·details는 읽지 않게 한다. `report`의 확신 high 불일치는 사진을 다시 보고 틀린 판단이면 `overrides.py set`으로 대장 유지
4. 위성 나무·운동장: `satellite.py cell <칸>`(V-World z19 모자이크 `data/satellite/<칸>-z19.jpg`와 `.json`) → `trees.py --cells <칸>` → `fields.py --cells <칸>`(학교 운동장 키트, U7 J) → `roofs.py --cells <칸>`(평지붕 윗면 색, 7층 이하)
5. 생성: `build_luau.py --cells <칸>` → `data/build/<칸>/chunks.json`(덩어리 파일을 데이터로 바꾼 것)을 127.0.0.1에서 받아 `Builder.begin/add/finish/verify`(검증 키는 `items_<kind>`), `HttpEnabled`는 받는 동안만
6. 위성 겹쳐 보기: Studio 수직 캡처(높이 650, 0.974 px/stud)와 위성을 `satellite.py compare`로 같은 격자에 겹쳐 데이터에 없는 시설(운동장, 체육관, 큰길 폭)과 잘못 잡힌 건물을 찾는다
7. 거리뷰 대조: `estimate.py plan` → 같은 카메라로 `screen_capture`(세로 시야각 83.58, 하나씩) → `compose`. 여러 건물에 공통인 문제는 규칙(`details_rules`, `layout_details`)으로 고치고 테스트, 한 건물만의 문제는 보정이나 Manual
8. 특별한 곳(학교, 공원 등)만 Manual 스크립트(`regions/<구역>/manual.json`에 등록, 박스 좌표 대신 `anchors.py` 기준점). 학교 운동장은 키트가 먼저. 끝나면 걷기 FPS(Studio 창 앞)

외관은 실제 외곽선을 따른다(U7): 박스 최대 6개(학교 8개)로 쪼개 외곽선 일치도 0.93을 목표로 한다. 건물 내부는 만들지 않고 층수는 층 띠와 층별 창으로 보인다.

## 실행

```bash
# 1) OSM 수집 (건물 이름·태그, 도로, 가로시설). 칸 ID를 직접 줄 수도 있다
uv run --env-file .env src/cells.py --cells 8930e0af13bffff 8930e0af123ffff 8930e0af12bffff
# uv run --env-file .env src/cells.py 9 lat,lon lat,lon lat,lon [lat,lon ...]   (점으로 채울 때)

# 2) V-World 건물 수집과 조립 (.env에 VWORLD_KEY 필요)
uv run --env-file .env src/register.py --cells 8930e0af13bffff     # 또는 --all

# 3) 거리뷰 파노라마와 건물별 크롭 (비밀값 없음, 네이버 호출). 상한(100장)에 닿으면 멈추니 같은 명령을 다시 돌려 이어간다
uv run src/capture.py --cells 8930e0af13bffff
# uv run src/capture.py --cells 8930e0af13bffff --replan   (그 칸의 건물별 사진 짝을 지우고 처음부터 계획)
# uv run src/capture.py --cells 8930e0af13bffff --replan-school   (학교 건물만 지우고 면 기준으로 다시 계획)
# uv run src/capture.py --selftest                          (라이브러리 import만 확인, 네트워크 없음. CI가 쓴다)

# 0) 구역과 등급(U7). 칸이 regions/<구역>/region.toml의 cells에 있어야 한다. Overpass 한 번 -> regions/<구역>/tiers.json (git 포함)
uv run src/tiers.py classify --cells 8930e0af13bffff        # set --cell <칸> --tier N --reason "..."로 손으로 고친 값은 다시 분류해도 유지, list로 보기

# 3.4) 칸의 위성 모자이크 (VWORLD_KEY) -> data/satellite/<칸ID>-z19.jpg와 .json. 겹쳐 보기는 satellite.py compare <캡처> <x> <z> 0.974 [출력]
uv run --env-file .env src/satellite.py cell 8930e0af13bffff

# 3.5) 위성 사진에서 나무 위치 읽기 (비밀값·네트워크 없음, data/satellite/<칸ID>-z19.jpg와 .json이 있어야 한다). 결과 regions/<구역>/cells/<칸>/trees.json은 git에 넣고,
#      있으면 build_luau.py가 규칙 가로수 대신 이 나무를 만든다 (첫 칸 371그루)
uv run src/trees.py --cells 8930e0af13bffff

# 4) Studio에 올릴 Luau 덩어리 파일 만들기 (비밀값·네트워크 없음). Studio 실행은 Claude가 execute_luau로 한다
uv run src/build_luau.py --cells 8930e0af13bffff
# uv run src/build_luau.py --selftest                       (import만 확인)

# 5) 높이·외관 판단(U4). 눈가림: 판단하기 전에는 report, plan을 돌리지 않는다. 사진은 Claude가 묶음 이미지로 본다
uv run src/estimate.py pending --cells 8930e0af13bffff            # 판단할 건물 10개(--limit)와 묶음 이미지, 대장·OSM 숫자 없음
uv run src/estimate.py record --file judgements.json              # 판단 기록(여러 건 한 번에, 하나라도 틀리면 전부 거부)
uv run src/estimate.py report --cells 8930e0af13bffff             # 판단이 끝난 뒤: 상태, 사진-대장 일치율, 확인 목록
uv run src/estimate.py plan --cells 8930e0af13bffff               # 비교 쌍의 Studio 카메라 값 -> data/build/<칸ID>/review.json
uv run src/estimate.py compose --cells 8930e0af13bffff --captures captures.json   # Studio 캡처 + 크롭 -> captures/<칸ID>/review/

# 5b) 세부 판단(U5). Claude가 묶음 이미지를 보고 7개 필드(마감, 1층 용도, 계단실, 돌출창, 발코니, 지붕 색, 옥상)를 기록한다
uv run src/details.py pending --cells 8930e0af13bffff --limit 10        # 세부 행이 없는 건물과 묶음 이미지 경로
uv run src/details.py record --file details.json                        # 기록(여러 건 한 번에, 하나라도 틀리면 전부 거부) -> regions/<구역>/cells/<칸>/details.json(git 포함)
# uv run src/details.py list|export|import ...                           (import는 복구용)

# 5c) 간판 이미지(U5 확장, 2026-10-13). 띠간판·층별 간판만 이미지, 나머지는 글자. 키는 .env의 OPENAI_API_KEY, OPENAI_BASE_URL
uv run src/signs.py plan --cells 8930e0af13bffff                                    # 간판 모양 목록 -> data/build/<칸ID>/signs-plan.json
uv run --env-file .env src/signs.py generate --cells 8930e0af13bffff --workers 4     # 없는 이미지만 생성 -> assets/signs/<key>.png (raw는 재사용)
# Claude가 assets/signs를 127.0.0.1에서 서빙하고 Studio MCP upload_image로 올린 뒤:
uv run src/signs.py record --cells 8930e0af13bffff --file upload.json               # {url: "rbxassetid://N"} -> regions/<구역>/cells/<칸>/signs.json(git 포함)
# uv run src/signs.py status --cells ...   그 뒤 build_luau.py가 im=<자산ID>를 붙인다. signs.json이 없으면 글자 간판

# 6) 보정(사용자와 같이 보고 정한 값, 사유 필수). set과 unset은 regions/<구역>/cells/<칸>/overrides.json(git 포함)을 바로 다시 쓴다
uv run src/overrides.py set --building gis:11081057 --field floors_above --value 4 --reason "누가 무엇을 보고 정했는지"
# uv run src/overrides.py unset|list|export|import ...      (import는 복구용: 보정과 판단이 같이 돌아온다)
# uv run src/estimate.py --selftest, uv run src/overrides.py --selftest   (import만 확인)

# 5) 미니맵 데이터와 킥보드·지도 스크립트 설치 파일 (비밀값·네트워크 없음). 지금 Studio에 만든 칸을 모두 적는다.
#    data/build/install-u6.luau를 Studio(Edit)에서 execute_luau로 실행하면 ReplicatedStorage·StarterPlayerScripts·ServerScriptService에 설치/갱신된다
uv run src/minimap.py --cells 8930e0af13bffff 8930e0af12bffff

# 테스트 (속성 기반 테스트 포함)
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
```

- 설정 값(겹침 기준, 버퍼, 호출 간격, 원점 등 공통)은 `config.toml`, 구역 설정(학교 필지 `school_polygons`, 스폰 `spawn_*`, 이름별 차로 수 `road_lanes_by_name`, 칸 목록 `cells`)은 `regions/<구역>/region.toml`(U7 B, 지금 구역 하나 `bucheon-dodang`), 칸별 판단 파일(details, overrides, signs, trees)은 `regions/<구역>/cells/<칸>/<종류>.json`(git 포함), Studio 소스는 위치별로 `studio/ServerStorage/MapBuilder.luau`(Builder)와 `studio/manual/<구역>/{School,Buheung,Park,Landmark}.luau`(수작업). 아래 기록에 나오는 예전 경로(`overrides/<칸ID>.json`, `details/`, `signs/`, `trees/`, `studio/Builder.luau`, `studio/Manual*.luau`, `config.toml`의 학교 필지·스폰)는 2026-10-14에 이렇게 옮겨졌다. 비밀값은 `.env`(`VWORLD_KEY`, `DATA_GO_KR_KEY`, git 제외).
- Overpass와 V-World는 429/502/504와 시간 초과에서 재시도한다(10s, 30s, 60s). 칸 하나가 실패해도 이전 데이터는 유지된다.
- `build_luau.py`는 칸의 건물과 도로로 `data/build/<칸ID>/chunk-NNN.luau`(항목 70개씩), Studio가 받는 `chunks.json`(덩어리 파일을 데이터로), `manifest.json`을 만든다. 가로·나무 계산은 `streets.py`(U7 B에서 `layout_details.py`에서 떼어 냄). 모든 좌표·박스 계산은 Python(`layout.py`), `studio/Builder.luau`는 부품만 만든다. 건물은 최소 면적 회전 직사각형 박스 1개(맞춤 0.8 미만은 manifest의 `poor_fit`), 원점은 세 칸이 만나는 꼭짓점, 스케일 3.6 stud/m(첫 칸을 만든 뒤 확정). Studio 쪽은 `Workspace/Auto/<칸ID>`만 비우고 다시 만들고 `Workspace/Manual`은 읽기만 한다. 스폰은 `config.toml`의 `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`를 정하면 만들어진다.
- 학교 건물(`config.toml`의 `school_polygons` 필지 안, 지금은 심원고 필지)은 가까운 순이 아니라 **면마다 파노라마 하나**(최대 6면, 가림 없는 것)를 골라 면의 가운데를 향한 크롭을 만든다. 첫 칸의 학교 건물 8동에 면 사진 22장(본관은 남·북·동·서 네 면). 나무와 차량은 가림으로 판단하지 않아서 서쪽 면 같은 곳은 약하다. 자세한 내용은 `aidlc-docs/construction/u3-street-view-capture/code/school-faces-change.md`.
- `capture.py`는 건물마다 파노라마를 최대 3장(120 m 안, 방위각 60° 이상 차이) 골라 `captures/`에 저장하고 건물 방향 크롭(1024×768)을 만든다. 호출 간격 1초, 실행당 새 파노라마 100장 상한. 403/429가 재시도 뒤에도 계속되거나 응답 형식이 이상하면 우회하지 않고 멈춘다(`collection_runs`의 `stopped_reason`). `captures/`는 git 제외.
- U4(`judgement.py`, `review.py`, `estimate.py`, `overrides.py`): 층수·높이·벽 색·지붕 모양의 최종값은 **보정 > 사진 판단 > 대장 > 기본값**이다(OSM 값은 참고만). 사진 판단은 Claude가 묶음 이미지(`captures/<칸ID>/sheets/`)를 대장·OSM 숫자 없이(**눈가림**) 보고 `estimates`에 기록하고 대장과의 비교는 `report`가 한다. 사진이 대장과 다르면 확신 high일 때만 사진 값, 그 밖은 대장 유지와 확인 목록. 대장 높이는 층수가 같고 층당 2.5~5 m일 때만 쓰고 아니면 층수 × 3.4 m. 판단과 보정은 `overrides/<칸ID>.json`(git 포함)으로 즉시 내보낸다. 그 파일에 올라가는 `note`와 `reason`에는 사람·번호판·상호 같은 개인 정보를 쓰지 않는다. `build_luau.py`가 최종값을 읽어 건물 부품에 높이·벽 색을 반영하고 속성 `HeightBasis`, `FloorsBasis`, `WallColor`, `Review`(사유를 `-`로 이음)를 단다. 비교 쌍은 Studio 카메라를 크롭 위치에 두고 캡처한다: **`screen_capture`에 항상 `camera_position`과 `look_at_position`을 준다**(인자 없으면 다른 시점이 찍힌다), 세로 시야각 83.58°, Studio 창은 4:3보다 넓게. 설계와 규칙은 `aidlc-docs/construction/u4-judgement-corrections/`.
- U5(`details_rules.py`, `layout_details.py`, `details.py`): 건물마다 세부 판단(`details` 표, `details/<칸ID>.json`) > U4 메모 검색 > 기본값으로 마감·1층 용도·계단실·돌출창·발코니·지붕 색·옥상을 정하고, `build_luau.py`가 지붕(쐐기), 층 띠, 창(불투명 부품), 계단실, 발코니, 문, 가게 전면, 마당 담·대문, 간판(가상 한글 이름, `SurfaceGui`), 가로(연석, 노면, 횡단보도, 전봇대·전선, 가로등, 가로수, 주차 차량, 스쿨존 울타리, 볼라드)를 항목으로 만든다. 같은 건물의 V-World 중복 외곽선은 뺀다. 안 맞는 외곽선은 박스 ≤ 3개(학교 6)로 나눈다. 모든 변화는 `details_rules.pick`(crc32 + 혼합)뿐이다. 외부 자산(텍스처 업로드, 메시, 크리에이터 스토어)은 쓰지 않는다. 간판 글자는 `SIGN_TEXT = [가-힣A-Za-z0-9 ]{1,12}`로만 검사해 그대로 Luau에 넣고, 그 밖의 글자는 `SAFE_TEXT` 그대로다. 리터럴 키 `i p m c o t u md j g l`은 기본과 다를 때만. 규칙은 `aidlc-docs/construction/u5-details/functional-design/business-rules.md`, 코드 차이는 `.../code/code-summary.md`. 수작업 학교는 `studio/ManualSchool.luau`, 부흥중은 `studio/ManualBuheung.luau`를 `execute_luau`(Edit)로 실행한다(맨 위 폴더마다 없을 때만 만들고 지우지 않는다. 한 부분을 다시 만들려면 그 폴더만 지우고 다시 실행; 좌표는 첫 칸 값이라 다른 칸에는 쓰지 않는다).
- **Roblox 업로드 검수(2026-10-13)**: 간판 이미지 37장을 올리던 중 Roblox가 `403 User is moderated`를 냈다. 즉시 멈췄고(재시도·우회 없음) 36장만 기록했다. 원인으로 의심되는 것은 맥주잔 아이콘이 든 "호프" 간판(술은 Roblox 정책 위반)이라 이름 풀에서 "호프"를 빼고 아이콘을 지웠다(가드 테스트 있음). 나머지 108장은 **사용자가 Roblox 계정의 검수 안내를 확인·해결한 뒤**에만 다시 올린다. 업로드 전에는 간판 글자·아이콘에 술·담배·도박 어휘가 없는지 본다.
- 학교 수작업 v4(2026-10-13): `studio/ManualSchool.luau`는 U3 거리뷰 크롭과 사용자가 준 사진 3장으로 다시 만들었다(운동장 쪽 남동 긴 동 `#b3`에 현관 캐노피·계단·교명판·시계, 색 창틀, 크림색 동쪽 끝벽에 파란 "심원고등학교" 글자와 벽돌 모서리, 짙은 지붕 띠, 북쪽 계단탑; 북서 큰 동 `#b0`에 붉은 지붕; 적벽돌 동 `gis:11185281`에 아치 유리창·발코니 스택·짙은 박공; 초록 차양 스탠드, 농구장 철망, 화분 소나무, 흰 잎무늬 울타리(도로 쪽)와 초록 막대 울타리(서쪽), 화강암 교문 기둥과 접이식 문, 서쪽 소공원). 1,093부품. 학교 archetype의 창은 리본 대신 교실 격자(1.8×1.5 m, 2.4 m 간격)다. 본관 동쪽 끝 글자 같은 큰 글씨는 `SurfaceGui.PixelsPerStud`를 10 정도로 낮춰야 보인다(TextSize 상한 100 px). 캡처는 만든 직후에는 SurfaceGui가 비어 보이니 1분 뒤 다시 찍는다.
- 학교 v5·부흥중 v2(2026-10-13): V-World 위성 z19를 Studio 수직 캡처(높이 650에서 0.974 px/stud)에 맞춰 겹쳐 보고(`data/compare/`, 위치 오차 1~2 m) 고쳤다. 운동장은 건물처럼 10° 돌아간 397×192 stud, 초록 철망은 축구장을 감싸는 320×150. `gis:11215390`(U4에서 4층으로 본 것)은 실제로 운동장 북쪽 청록 스탠드 차양이라 `Shelters`가 그 `BuildingId`를 가진다. `gis:11215391`은 철골 퍼걸러, `gis:11215393`은 열린 쉼터. 빨간 박공은 체육관 크기(약 40×28 m)만. 부흥중은 계남로 울타리·정문, 청록 지붕과 태양광, 데이터에 없는 운동장·농구장·체육관(높이 추정)·통로. **Auto 평지붕 위에는 `#cap`(높이 2.88, `CanQuery=false`)이 있어 박스 윗면에 얹은 부품은 가려진다. 지붕을 얹을 때는 cap 위(박스 윗면 + 2.16)에.** 캡처하면 편집 카메라가 `Scriptable`로 바뀌니 끝나면 `Fixed`로 되돌린다.
- **간판 이미지 재사용(사용자 결정, 2026-10-14)**: 새 칸은 간판 이미지를 새로 만들지 않고 이미 올린 이미지(첫 칸 145장, `regions/bucheon-dodang/cells/8930e0af13bffff/signs.json`)를 재사용한다. 새 이미지는 정말 큰 랜드마크(큰 상가 건물 대표 간판, 역, 대형 시설 등)만, 정말 필요할 때 칸당 2장까지. 올리기 전 검수 어휘 점검은 그대로. 재사용 방법(같은 종류·비율·색의 기존 이미지를 건물마다 고정으로 고르고 간판 글자도 그 이미지 글자로 맞춤)은 U7 K.
- **장소 나누기와 메시(사용자 결정, 2026-10-15; 장소 나누기는 아래 B 결정으로 바뀜, 메시 키트는 그대로)**: 부천 전체(752칸, 칸 넓이 여기서 약 0.072 km²)는 구 단위 장소 3개(원미구·소사구·오정구)로 나누고, 구끼리 맞닿는 경계를 지날 때 텔레포트한다. 로딩 몇 초와 다른 구의 사람과 못 만나는 것은 감수(사용자). 좌표 원점은 그대로 하나라 넘어가면 같은 좌표·방향에 선다. 경계 근처 1~2칸은 양쪽 장소에 겹쳐 넣는다. 원미구만 288칸이라 구로 나눠도 지금 칸당 약 8,800부품이면 무거우므로, **지금 디테일을 유지한 채 반복 조각을 메시 키트로 묶어 부품을 줄인다**(창 칸: 유리·창틀 메시를 크기 묶음별로, 가로시설 세트; 벽·간판은 부품 유지). 순서: 빌라 한 동 창 칸 메시 나란히 비교(사용자 확인) → 규모 시험(수십 칸) → 완성 칸에 적용.
- **서버가 근처 칸만 만들기(B, 사용자 결정 2026-10-15)**: "C로 하자, B 시험 먼저 해줘" → 시험 통과 → "그럼 최적화는 항상 개인 칸 기준 두바퀴 칸 보이게 하고 서버 수용 인원 5명으로". 장소 하나에 부천 전체를 넣고 구 경계 텔레포트는 없앤다(2026-10-15의 구 3개 장소 결정을 대신함). 서버는 플레이어마다 그 사람이 있는 H3 칸과 이웃 두 바퀴(1 + 6 + 12 = 19칸)의 상세판을 만들고, 아무도 두 바퀴 안에 없는 칸은 지운다. 서버 최대 인원 5명. 먼 곳의 건물 상자(가벼운 판)는 쓰지 않는다(사용자 2026-10-15: "멀리서 상자 보이는거 그냥 제거해"): 클라이언트 스트리밍 반경 밖에는 땅과 랜드마크만 보인다. 흩어진 5명이면 상세 95칸이라 서버 메모리가 한도(약 6 GB)에 가까우므로 메시 키트가 전제다. 지도 순간 이동은 도착 칸을 먼저 만들고 옮긴다(프레임 예산 12 ms, 로딩 1~2초). 시험: `aidlc-docs/construction/plans/b-cell-streaming-test.md`.
- 남은 결정(사용자 인터뷰, 2026-10-14, `aidlc-docs/inception/requirements/u7-open-decisions-questions.md`): 조명은 그늘만 보정(Realistic 유지, `OutdoorAmbient` 올림, 하늘 반사 낮춤, 해 방향·시간 유지). PBR 벽 질감(SurfaceAppearance·MaterialVariant)은 쓰지 않는다. 간판 이미지는 재사용만(새 업로드는 큰 랜드마크 칸당 2장 예외). 출처 표시는 큰 지도 구석에 항상. P5-3(꼭짓점 순서) 버그는 2번 칸 전에 고쳤다(2026-10-14: 최소 사각형을 직접 재고 같은 넓이면 외곽선 변이 많이 나란한 방향).
- 간판 이미지(U5 확장, `src/signs.py`): 사용자 결정(2026-10-13)으로 띠간판·층별 간판은 Azure OpenAI 이미지 생성(배포 `gpt-image-2.5-sunburst`, `.env`의 `OPENAI_API_KEY`·`OPENAI_BASE_URL`)으로 만든 그림을 Roblox에 올려 `ImageLabel`로 보여 준다. "외부 자산 없음" 결정은 간판 이미지에 한해 풀었다. 열쇠 = sha1(글자|종류|판 색|글자 색|비율 묶음)[:16], 캐시 `assets/signs/`(git 제외, raw 포함), 자산 ID는 `signs/<칸ID>.json`(git 포함)으로 고정되어 덩어리 파일이 결정적이다. 프롬프트에는 가상 이름만 들어간다. 규칙 SI-1~9: `aidlc-docs/construction/u5-details/sign-images/plan.md`.
- 건물은 자기 중심점이 속한 칸에만 저장되므로 칸 사이 중복이 없다. DB는 `data/map.db`, 로그는 `data/logs/*.jsonl`, 칸 재수집 직전 백업은 `data/backups/`(모두 git 제외).

## 현재 상태

- **33~37번 칸 약대동 6·4·3·1 주변(2026-10-15, 사용자 "미니맵 나누기 하고 이번에는 약대동 6 4 3 1 5칸")**: 1bb·1af·18f·137·1a3(건물 634). 미니맵 데이터는 조각 모듈로 나눔(`studio/install/minimap-data.luau`). 대표 시설 4곳: 강남종합시장 아케이드(`src/market.py`), 부천대우테크노파크, 현대골프 연습장(`src/golf.py`), 약대교회(종탑). 37칸, pack까지. 걷기 FPS 아직.
- **30~32번 칸 0a7·1d3·19b(2026-10-15, 사용자 "0a7 이랑 중동 16 약대동 8쪽으로 해서 총 3칸")**: 현대백화점 서쪽 절반·경기예고·부광초·노동부 지청·안중근공원(0a7·1d3)과 덕유마을(19b). 현대백화점은 사용자 "현백 디테일하게 진짜로"로 전용 생성기 `src/hyundai.py`(두 동+아트리움), 공원은 `src/anjunggeun.py`(위성 배치, Folder). 정리된 장소 순서로 넣고 pack까지, 32칸. 미니맵 데이터가 20만 자 한도 바로 아래(다음 확장 전에 나눔). 걷기 FPS 아직.
- **26~29번 칸 부천시청역·중동 10·11 주변(2026-10-15, 다른 세션이 전달한 사용자 요청)**: `8930e0af1c3ffff`(부천시청역·이마트), `8930e0af1d7ffff`(부흥초), `8930e0af18bffff`(중흥고·서부119), `8930e0af1dbffff`(현대백화점 동쪽 절반)를 사이클로(건물 28·30·37·56, 1급). 대표 시설 6곳 Manual/Facilities(사용자 승인). 출구 맞추기 단계(cycle-build 2c, `regions/<구역>/exits.json`): 부천시청역 5/5·신중동역 7/7이라 파일 없음. 지하철 출구 위 작은 V-World 기록은 키트에 맡김. 29칸 Studio·미니맵·cell-data, 5칸 verify ok, 땅이 길 덮음 0. 걷기 FPS 아직.
- **장소는 정리된 상태로 저장(2026-10-15, 637d9b0)**: 저장 전 `studio/install/pack.luau`(칸 데이터만 남김, Workspace 163개), 편집할 칸은 `unpack.luau`로 꺼낸다(cycle-build 5c). 서버 시작 때 상세 칸을 다 불러왔다 지우는 일이 없어져 칸 수 한계(약 100칸)가 풀렸다.
- **수작업 시설도 칸 단위(2026-10-15, 58a1681)**: 칸 데이터 설치(7-5b)가 `Workspace/Manual`을 칸별 데이터로도 넣고(`ManualCodec`), Play에서는 칸과 함께 만들어지고 지워진다. `Manual/Landmark`만 늘 남는다(스카이라인). 수작업을 고치면 5b를 다시 돌려야 Play에 반영된다.
- **칸 고르기 알고리즘(2026-10-15, 2591940, 사용자 "네 가지 다 넣어서")**: 사람마다 자기 칸+한 바퀴는 필수, 나머지는 모든 플레이어에서 동시에 가까운 순(지금·6초 뒤 예상 위치)으로 부품 예산 50만(약 3 GB)까지, 예산이 필요할 때만 가장 먼 칸부터 지움, 도착 시간 짧은 칸부터 만듦. 시험용 예산은 `ServerStorage/CellData` 속성 `BudgetParts`(보통은 비움). 5 GB 기준 동시 상세 약 85칸.
- **서버 근처 칸 만들기 정식판(2026-10-15, 4386cff)**: `ServerScriptService/CellStreamer`가 Play에서 저장된 Auto 칸을 지우고 플레이어마다 자기 칸 + 두 바퀴를 `ServerStorage/CellData`(zstd + base64, 25칸 3.5 MB)에서 만든다(프레임당 8 ms, 8초 지나 아무도 없으면 지움, 실제 서버만 5.5 GB 넘으면 한 바퀴). 바깥은 `ServerStorage/Lite`(가벼운 판). 지도 육각형 이동·H는 도착 칸을 먼저 만들고 로딩 화면(`CellLoading`) 뒤에서 옮긴다(시험 0.3~0.4초). 지도에 다른 사용자 위치(파란 점과 이름, `PlayerMap`). 칸 추가 절차 7-5b에 칸 데이터 설치. 남은 일: 두 명 시험(사용자), 서버 최대 인원 5(사용자가 Game Settings에서), 수작업 시설 칸별 불러오기, 장소 파일에서 Auto 빼기(지금은 편집용으로 저장됨).
- **메시 키트 적용(2026-10-15)**: 줄 메시 52개를 사용자가 올려(`kits.STACK_IDS`) 25칸을 다시 만들었다(땅 판 합치기 87a74cb와 함께). 25칸 186,893 → 140,735부품(-24.7%, 칸당 평균 5,629), Studio Auto 약 20만 2천 → 14만 7천 자손, 25칸 verify ok, 가장 느린 덩어리 5~16 ms(전에 24~37), 같은 카메라 6곳 전후 비교 차이는 가장자리 1픽셀(`data/compare/mesh-kit/before-after-25cells.jpg`), 걷기·킥보드 86초 평균 60·최저 58. 나무 한 메시 8개(`kits.TREE_IDS`, 색 그림 `TREE_TEXTURE_ID`)도 올려 다시 만들었다: 25칸 125,905부품(칸당 5,036), Auto 약 13만 2천 자손, 25칸 verify ok, 줄기 밑이 땅 위로 뜬 나무 0(0.3 m 내림). 가벼운 판은 `ServerStorage/Lite`(25칸).
- **B 시험: 서버가 근처 칸만 만들기(2026-10-15, 사용자 "C로 하자, B 시험 먼저 해줘")**: Play 서버에서 25칸 데이터를 zstd로 압축해 두고(칸당 116 KB), 플레이어 1,500 stud 안의 칸만 만들고 2,000 stud 밖은 지웠다. 킥보드 속도로 왕복 324초: 칸 하나 1.2~3.5초, 클라이언트 평균 59.9 FPS(985 ms 멈춤 한 번, 다시 안 나옴), 서버에는 3~7칸만. 되는 방식이다. 남은 일(먼 경치용 상자판, 데이터를 장소에 넣기, 정식 스크립트, 순간 이동, Manual 칸별로)은 `aidlc-docs/construction/plans/b-cell-streaming-test.md`.
- **메시 키트·규모 시험(2026-10-15 밤, 사용자 "ㄱㄱ 규모 시험까지 해줘")**: 25칸 걷기·킥보드 60 FPS. 줄 메시 키트(`kits.STACKS` 52개, 같은 조각이 층마다 쌓인 줄을 늘인 메시 하나로; 34b5b09)는 ID가 없으면 결과가 그대로이고, 다 올리면 25칸 -22.6%(평균 8,174 → 6,328). Studio에서 업로드 없이(EditableMesh) 나란히 비교했다: `data/compare/mesh-kit/`(git 제외). **규모 시험: 서버는 부품당 6.1 KB, Roblox 서버 한도 약 6 GB라 장소 하나는 약 80만 부품(약 90~110칸)이 한계. 구 3개 장소로는 원미구가 넘는다** → 질문 `aidlc-docs/inception/requirements/place-split-questions.md`(장소 약 100칸씩 vs 서버가 근처 칸만 만들기). 업로드(`data/kits/stacks.obj`, Import 3D 한 번)는 사용자 몫이고 질문의 답을 보고 한다.
- **22~25번 칸 부천중앙공원(2026-10-15, 사용자 "153 1cb 칸도 확장해서 중앙공원까지")**: `8930e0af153ffff`·`8930e0af1cbffff`·`8930e0af027ffff`·`8930e0af037ffff`를 사이클로, `Manual/CentralPark`(src/park.py, 공원이 걸친 6칸으로 자름, 상징탑 포함). trees.py 닫힌 산책로 버그를 고쳐 공원 숲이 생김. 25칸 verify ok, 미니맵 25칸(정수로 줄임, 20만 자 한도 근처). Auto 약 20만 2천 + Manual 2만 6천 자손, 걷기 FPS 아직.
- **19~21번 칸 중동 6·8 주변 + 대표 시설 11곳(2026-10-15, 사용자 "중흥초 본관… 1ab 지식산업센터 다 ㄱㄱ하고 중동8칸이랑 6칸 주변 3칸 확장")**: `8930e0af157ffff`(미리내마을 9xx동·메트로팰리스 상가), `8930e0af1c7ffff`(은하마을 5xx동), `8930e0af1cfffff`(부천시청·47~49층 탑 단지 101·103)를 사이클로(건물 44·34·11, 1급). 대표 시설은 `src/facilities.py` + `regions/bucheon-dodang/facilities.json`(서브에이전트가 거리뷰·웹·위성으로 읽은 외관 스펙; 웹 사진은 어느 곳도 못 찾음) → `Manual/Facilities`. 길주공원은 웹 자료 없음, 위성으로 모래 운동장·농구장·원형 광장·놀이터(`Manual/Courts`). 101·103은 외곽선 하나가 탑 6동 단지라 자동이 120 m 통짜 덩어리가 되어, 사용자 승인으로 기단 + 위성 위치의 탑 6동씩(facilities.json towers list)으로 만들었다. 부천시청도 기단 + 본관. 부천중앙공원은 대부분 아직 없는 칸 153·1cb라 그 칸을 만들 때(src/park.py 준비). 경사 단계가 매 사이클 고정(`elevation.py probe`, `terrain-check.luau`). 21칸 verify ok, 땅이 길 덮음 0, 미니맵 21칸. Auto 약 18만 3천 + Manual 2만 2천 자손. 가장 느린 덩어리가 24~37 ms로 늘었다(부품 총량 탓으로 보임), 걷기 FPS 아직.
- **16~18번 칸 약대동 2·5 주변 + 남은 목록(2026-10-15, 사용자 "이거 다 처리 확장은 약대동 5 2 칸 주변 3칸")**: `8930e0af117ffff`(중흥초·꿈빛도서관·길주공원), `8930e0af11bffff`(길주로 상가·고층), `8930e0af113ffff`(아파트 단지)를 사이클로(건물 30·26·22, 1급으로 set). 규칙: 상가주택 차양·세로 간판·지붕 테두리(난간벽/맨사드)·옥상 계단실·모퉁이 옆면 가게, 아파트 실외기·반투명 난간판, 상가 기단 아파트(광성아파트 외 4동, `podium_items`), 주유소·충전소 캐노피, 고가도로(`src/bridges.py`: 계남고가·신흥고가, 상판·벽·교각, 6.5 m), 8층 이상 지붕 색 손 지정(`roofs.json` `hand`). 수작업 `Manual/Courts`(미리내공원 테니스 3·풋살 1, `src/courts.py`). 18칸 Studio verify ok(Auto 약 16만 3천 자손), 미니맵 18칸. 걷기 FPS 아직, 가장 느린 덩어리 12~14 ms인 칸 있음.
- **13~15번 칸 약대동 쪽 + 백화점(2026-10-14)**: `8930e0af133ffff`(계남로·래미안), `8930e0af1abffff`(신흥로 8차로), `8930e0af103ffff`(중흥마을)를 사이클로(건물 139·85·23). 백화점 원호 동쪽을 `Manual/DeptStore`(생성기 `src/deptstore.py`). 규칙: 큰길 차선(겹선·점선), 나무 밑 빈 외곽선 안 만듦, 종교시설 public. 15칸 Studio verify ok, 미니맵 15칸(데이터와 스크립트 따로 설치). 걷기 FPS 아직.
- **미관광장(2026-10-14, 사용자 요청)**: 백화점 남쪽 광장을 `Manual/Plaza`로(생성기 `src/plaza.py`, 위성 격자·거리뷰·사용자 사진: 블록 화단, 계단식 타원, 흰 기둥 열, 유리 지하 출입구, 1,914부품). 나무는 위성(지하 시설 외곽선을 지붕으로 안 봄).
- **9~12번 칸, 중동 쪽 4칸(2026-10-14)**: `8930e0af17bffff`(계남중·아파트), `8930e0af10bffff`(오피스텔 거리, 1급으로 set), `8930e0af147ffff`(미리내공원·계남초), `8930e0af16bffff`(신흥로 남쪽 상가·33층 쌍둥이 탑)를 사이클로(건물 32·51·22·42). 12칸 Studio verify ok, 미니맵 12칸. 규칙 넷: 차도 위 위성 나무 뺌, 공영주차장 = public + "공영주차장" 판, 사진이 가게로 본 03000 = 상가, OSM 전용 외곽선이 빈 땅이면 안 만듦. 걷기 FPS 아직. 후속: 미리내공원 테니스장·풋살장(데이터 없음, 수작업 후보), 16b 주유소 캐노피.
- **경사 지형(2026-10-15, 사용자)**: 거리뷰 1,961곳의 카메라 고도(`src/elevation.py`, `regions/<구역>/elevation.json`, 고가 위 등 튀는 값은 뺌)로 높이를 만들고(`src/terrain.py`, 기준 37 m), 도로·인도·표시는 땅 따라 기울이고(키 ax·az), 건물은 박스 아래 가장 낮은 땅만큼, 수작업은 `Builder.settleManual`로 올린다. 땅은 48 stud 판 조각을 땅 따라 기울여 깔고, 경사가 휘는 곳은 더 잘게(최소 10 stud, 판 0.3·도로 0.12 stud 넘게 휘면 반으로) 나눠 곡선처럼 보이게 한다(사용자 2026-10-15). 높이는 16 stud 가우시안으로 다듬는다. Studio Terrain은 2 stud 계단과 도로 덮음 때문에 쓰지 않는다(사용자 지적). 북쪽 약대동이 남쪽보다 4~6 m 높다.
- **H = 랜드마크 꼭대기, F = 패러글라이딩(2026-10-15, 사용자)**: H 키로 신중동역 랜드마크 탑 지붕으로 이동(화면 버튼 없음), 공중(땅 위 16 stud 이상, 점프로는 안 됨)에서 F로 패러글라이더를 펴고 WASD로 활공, 킥보드 중이면 내리고 편다(ParagliderClient·Paraglider). 묘기 방법 창은 삭제.
- **킥보드 묘기(2026-10-14, 사용자 결정)**: 테일윕(점프대에서 뜬 동안 Q, 공중에서 연속 가능), 칸마다 도로 가운데 킥커 점프대 최대 4개, 서로 100 m 이상(`streets.ramp_items`, 지도에 주황), 뜨는 높이는 속도에 비례(0.25 m × km/h). 매뉴얼은 뺐다(사용자). 규칙은 `aidlc-docs/construction/plans/u6-minimap-scooter-plan.md` 끝 절.
- **정육각형 칸 순간 이동(2026-10-14, 사용자 요구)**: 큰 지도(M)에 칸을 육각형으로 그리고, 칸을 누르면 "<동> <n> 칸으로 이동" 버튼으로 그 칸 중심 근처 인도로 이동(서버 `HexTeleport`, 3초 쿨다운). 칸 목록은 `minimap.py`가 만들므로 칸을 만들 때마다 미니맵 갱신과 함께 자동으로 늘어난다.
- **8번 칸 163(2026-10-14)**: `8930e0af163ffff`(어울림공원, 35층 주상복합 탑, 업무·오피스텔, 상가 블록, 건물 44)를 사이클로. 보행 육교 6개는 높이 띄운 갑판으로(새 규칙), 신흥로 8차로(구역 설정). Studio 7,380부품 verify ok, 미니맵 8칸, 거리뷰 8쌍·위성·교차로 확인. 걷기 FPS 아직.
- **5~7번 칸(2026-10-14)**: 신중동역 남(`8930e0af177ffff`, 원미경찰서·고층 단지·출구 1·2), 북(`8930e0af107ffff`, 중흥중 인조잔디 운동장), 남서(`8930e0af173ffff`, 상가 거리)를 같은 사이클로 만들었다(건물 33·61·50, 모두 verify ok, 미니맵 7칸). 거리뷰 대조 칸당 8쌍, 위성 겹쳐 보기, 교차로 확인. 규칙 추가: 보행로는 차도 위에 그리지 않음, 볼라드는 차도 밖, 짙은 인조잔디, 운동장 위 위성 나무 없음. 걷기 FPS는 아직(Studio 창이 앞에 있어야 함).
- **4번 칸 신중동역(2026-10-14)**: `8930e0af10fffff`(1번 칸 서쪽, 1급, 건물 20개: 49층 랜드마크 푸르지오 시티, 백화점, 업무·오피스텔)를 사이클로 만들었다. Auto 2,821부품(verify ok) + `Manual/Landmark`(탑 2동 124부품). 새 규칙: 지하 시설(역사·지하주차장)은 안 만듦, 판매시설 5층 이상은 `store` 유형, 지하철 출입구 키트(4번 칸 3·4·5·6번, 1번 칸 7번; 1·2번은 남쪽 칸 `8930e0af177ffff`), Builder 투명도 키 `tr`. 외관 규칙 넷(옆면 가게, 한 업체 건물, 벽돌 기단, 오피스텔 격자)과 도로·인도 겹침 정리를 네 칸에 반영. **스트리밍 켬(2026-10-14)**: `StreamingEnabled`, 건물 Model Atomic + `LevelOfDetail = StreamingMesh`, 랜드마크 탑 Persistent, 반경은 기본값(도구로 못 바꿈). 걷기 FPS는 아직(Studio 창이 앞에 있어야 함).
- **U7 끝(2026-10-14)**: 세 칸 모두 새 사이클로 Studio에 있다(1번 7,169 + 수작업, 2번 8,158, 3번 6,008, 모두 verify, 걷기 60 FPS). 사이클에 들어간 것: 외곽선 따르는 박스(P5-3 고침), 수작업 기준점(`anchors.py`), 학교 운동장 키트(`fields.py`), 간판 재사용, 나무 메시 키트(`ServerStorage/Kits`), 위성 지붕 색(`roofs.py`), 큰 지도 출처 표시, 조명 그늘 보정. 외관 품질(L)은 다른 세션이 계속 다듬는다.
- U7 단계 3·4(내부)는 취소하고 코드를 지웠다(2026-10-14). 남은 것: Builder가 건물마다 Model(Atomic), 칸의 땅·도로는 `Base`(Persistent), 종류별 개수는 칸 속성 `Made_<kind>`(스트리밍 대비). Studio `ServerStorage/MapBuilder`는 단계 4의 Builder(내부 키가 있던 판, 내부 항목이 없으면 같은 동작), 예전 것은 `MapBuilder_U5`로 남김. 실제 지도 칸(1·3번)은 예전 Builder로 만든 그대로(단계 7에 다시 만듦).

- U1(데이터 기반)은 끝났다. 첫 칸 `8930e0af13bffff`는 수집과 조립이 끝나 `data/map.db`에 건물 122개가 있다. 나머지 두 칸(`8930e0af123ffff`, `8930e0af12bffff`)은 아직 데이터를 받지 않았다.
- OSM 태그는 부족하므로(서울시청 시험에서 건물 128개 중 높이·층수 태그 26개) V-World 건물통합정보의 층수와 거리뷰로 보완한다.
- U2 첫 칸이 Studio에 만들어졌다(2026-10-13): 부품 163개(땅 1, 도로 29, 보행로 2, 인도 8, 건물 122, 스폰 1), 스케일 3.6 stud/m 확정, 스폰은 신흥로238번길 보행로 `(37.504483, 126.77861)` yaw −62°(`config.toml`). Studio에는 사용자가 저장했다(Roblox에 저장, 2026-10-13). 복사본 `10122026_1-before-U2.rbxl`은 U2 이전 상태다. 걸을 때 60 FPS(Studio 창이 앞에 있을 때; 뒤에 있으면 15 FPS로 제한됨).
- U2 코드(`src/layout.py`, `build_luau.py`, `studio/Builder.luau`)를 만들었다(2026-10-13). 첫 칸 계획: 항목 162개(땅 1, 도로 29, 보행로 2, 인도 8, 건물 122), 덩어리 4개(6.6 KB 이하), 안 맞는 건물 9개. Studio 시험은 `MCP_Test` 안에서만 했고(실제 덩어리 파일 실행, `Manual` 우선, 재생성 확인) 지웠다. 실제 첫 칸 생성, 장소 설정 변경, 스케일 확정, 스폰 점 제안은 Build and Test에서 하고, 그 전에 사용자의 `.rbxl` 복사본이 필요하다.
- U3 코드(`src/projection.py`, `panorama_source.py`, `capture.py`)를 만들고 첫 칸을 실제로 돌렸다(2026-10-13). 테스트 152개. 첫 칸 결과: 건물 122개에 파노라마 226장과 크롭 363개(384 MB), 사진 없는 건물 0, 차단·재시도·실패 0, 약 13분(3번에 나눠서). 크롭의 32%가 지붕을 놓쳐서 위쪽 각도·시야각 규칙을 벽 기준으로 바꿨다(지붕과 지면이 다 들어오는 크롭 66% → 86%).
- 큐브 맵 규칙(`aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md`): 면 순서 앞·오른쪽·뒤·왼쪽·위·아래, 앞면이 보는 방위각 = ID 조회 `heading` + 180°(설계의 가정과 180° 다르다. 파노라마 3장에서 외곽선을 겹쳐 확인).
- 파이썬 3.13 이상이 필요하다(`capture.py`가 `numpy` 2.5.4를 쓴다). `uv`가 알아서 받는다.
- U4 Build and Test 끝(2026-10-13, 승인): 첫 칸 122개를 눈가림으로 판단했다(`overrides/8930e0af13bffff.json`, 커밋 3fe1802). 사진 층수가 대장과 같은 건물 75/104(72%, high 5/5, medium 59/74, low 11/25), 어긋남 30개(전부 대장 유지, 확인 목록), 대장에 층수 없던 16개는 11개를 사진으로 채움. Studio는 진짜 `MapBuilder`를 새 Builder로 바꾸고 첫 칸을 다시 만들었다(부품 163개, `verify` 통과, 건물 122개에 새 속성과 벽 색). **`MapBuilder.Source`를 바꿀 때는 모듈을 `Clone` 후 원본 `Destroy`로 새 인스턴스로 바꿔야 한다**(`require` 캐시 때문에 `Source`만 바꾸면 예전 코드가 실행된다). 덩어리 9 KB도 Studio 안에서 2~4 ms였다. 비교 쌍 74/136개를 같이 보고(1~4번 묶음 전부 + 표본 12개, 사용자 결정) 대장 값 122개를 모두 유지했다(보정 0개). 복구 연습 성공(새 DB + `overrides.py import`로 최종값 같음). 걸을 때 평균 60.0 FPS(Studio 창이 앞에 있을 때만 유효). 지금 건물은 색칠한 박스 하나(높이·벽 색만 반영, 지붕 모양은 기록만)다. 실제 칸에서 보정 `set`/`unset`은 아직 안 써 봤다.
- Roblox Studio 설치와 내장 MCP 연결 완료, 동작 확인(2026-10-12). `execute_luau`로 생성, `screen_capture`로 캡처가 된다. 열린 장소에 테스트용 `MCP_Test` 폴더가 남아 있다.
- U4 코드(`src/judgement.py`, `review.py`, `estimate.py`, `overrides.py`와 `db.py`의 `estimates`·`overrides`, U2의 `layout.py`·`build_luau.py`·`studio/Builder.luau` 변경)를 만들었다(2026-10-13). 테스트 412개(속성 P4-1~16 포함, 시드 5개로 확인), 일부러 코드를 망가뜨린 12가지를 모두 테스트가 잡았다. Studio 시험은 `MCP_Test` 안에서만 했다(새 Builder의 벽 색, 속성, 재생성, 수작업 우선). 첫 칸 읽기 전용 확인: 건물 122개 중 121개는 예전과 같은 높이, 1개는 층당 높이가 범위 밖이라 층수 × 3.4 m(`height_out_of_range`). 덩어리 파일 4개(6.0/9.4/9.4/2.7 KB, 10 KB 경고선 가까이). 아직 판단한 건물은 없었다(그 뒤 Build and Test에서 122개를 판단했다, 아래).
- AI-DLC: Inception 완료, U1·U2·U3·U4 완료. U5 디테일도 완료(2026-10-13, 사용자가 자리를 비워 상시 승인으로 Functional Design·NFR Requirements·Code Generation·Build and Test를 Claude가 추천안으로 답하고 진행). 다음은 나머지 두 칸.
- U5 Build and Test 끝(2026-10-13): 첫 칸을 U5 Builder로 다시 만들었다(Auto 4,880부품 + Manual이 가진 건물 1개 건너뜀, `verify ok`, 덩어리 70개 ≤ 13.3 KB, 가장 느린 덩어리 3.69 ms). `Workspace/Manual/School`(512 자손: 운동장·울타리·교문 현판·본관 유리 계단탑·별관 발코니·소나무·정자 + 끌어온 박스 `gis:15839722`)은 `studio/ManualSchool.luau`로 만들었고 Auto를 다시 만들어도 그대로다. 걷기 70초 평균 60 FPS(최저 1초 60, 가장 느린 프레임 20 ms, 멈춤 0). 창 재질 A/B는 둘 다 60 FPS 상한이라 SmoothPlastic 유지. 조명 값은 적용했지만 **`Lighting.LightingStyle`은 아직 `Soft`(사용자가 속성 창에서 `Realistic`으로)**. Build and Test 중 찾은 결함 3개(꼭짓점 절단 조각, 1 m 미만 간격 멈춤, 띠간판과 층별 간판 겹침)를 고쳤다. `Builder.add`는 `{created, skipped_manual}` 표를 돌려준다. Build and Test 전달은 `data/build/<칸ID>/chunks.json`(데이터만)을 127.0.0.1 서버로 Studio가 받아 한 번에 만들었고 `HttpEnabled`는 `false`로 되돌렸다. 결과는 `aidlc-docs/construction/build-and-test/*.md`의 U5 절.

## 다음 할 일

U7 = 기반 세팅(사용자 결정 2026-10-14: "u7에서 모든걸 세팅하고 여기서 구축한 사이클로 계속 반복"). 계획 `aidlc-docs/construction/plans/u7-real-shapes-interiors-plan.md`, 구조·최적화 `aidlc-docs/architecture.md`.

1. 사용자: Studio를 Roblox에 저장, `.rbxl` 복사본(`LightingStyle`은 `Realistic` 확인됨, 2026-10-14)
2. U7(계획 승인 2026-10-14): 계획서 5절 순서대로. 단계 2(B 구조, G 등급)·단계 3(내부·성능 Functional Design, 승인) 끝(2026-10-14). 단계 3·4(내부)는 취소(2026-10-14). 다음은 외관 품질(계획서 3절 L, 다른 세션의 "다른 맵의 건물 학습"·"리얼한 건물 제작 방법" 결과로 항목 확정)과 단계 5(F 기준점, J 학교 운동장 키트, K 간판 재사용; 다른 세션이 진행 중).
3. 세 칸을 사이클로 다시 만들었다(U7 단계 5~8 끝, 2026-10-14). 4번 칸(신중동역)도 사이클로 만들었다(2026-10-14, FPS만 남음). 5~7번, 8번(163), 9~12번(중동 쪽 4칸), 13~15번(약대동 쪽) 칸도 만들었다(2026-10-14). 16~18번(117·11b·113)도(2026-10-15). 다음: 사용자가 고른 대표 시설 상세, 걷기 FPS, 이웃 칸. 끝난 후속(2026-10-15): 모퉁이 상가 옆면 가게, 빌라 맨사드, 광성아파트 상가 기단(규칙), 103 청록 지붕, 신흥로 고가, 16b 주유소, 미리내공원 코트. 남은 후속: 117 길주공원 모래 광장(데이터 없음), 4번 칸 후속: 오피스텔 위층 창 격자(U7 L), 랜드마크 기단 창 없는 패널·테라코타 띠, 백화점 둥근 모서리. 남은 후속: 8층 이상 지붕 색(위성에서 기울어 보임), 광성아파트 상가 기단 수작업 후보(`manual.json`), 옥산초 본관 패널 외관, U6 사용자 확인(휴대폰·두 명·바퀴 소리)
4. 간판 이미지는 멈춤 상태(새 13장 캐시, 업로드 없음). 사이클에 넣을지는 U7에서

## 주의

- MCP 서버는 열린 맵을 읽고 수정할 수 있다. 신뢰하는 클라이언트만 연결하고 큰 작업 전 백업.
- 내장 MCP 서버는 `screen_capture`(뷰포트 캡처), `execute_luau`, `search_game_tree`, `start_stop_play`, `get_console_output` 등을 제공한다. `execute_luau`는 `studio_id`와 `datamodel_type`(Edit)이 필수다. 외관은 Claude가 직접 캡처해서 확인하고, 최종 판단은 사용자가 한다.
