# 파이프라인·구현 메모

CLAUDE.md에서 옮김(2026-10-16, /doctor: 항상 읽히는 파일을 줄이려고). 명령은 `cycle-build`·`cycle-verify` 스킬과 각 스크립트 `--help`에도 있다.

### 파이프라인

1. 구역 지정: 위경도 4점 또는 칸 ID → `src/cells.py`가 H3 칸으로 채움 (해상도 9 ≈ 변 200m·넓이 0.105km², 10 ≈ 변 76m)
2. 칸마다 V-World 건물통합정보(외곽선·층수·높이)와 OSM(이름·태그, 도로·가로시설)을 받아 `data/map.db`(SQLite)에 저장, `src/register.py`가 건물을 조립
3. 칸 하나를 Studio에 건물 박스로 생성 (Roblox Studio MCP 서버로 Luau 실행)
4. 칸 안 모든 건물을 네이버 거리뷰 자동 수집(`streetlevel` 라이브러리, 건물마다 파노라마 최대 3장과 건물 방향 크롭)으로 높이·색·지붕 등을 판단해 다듬음 (사용자 결정, 아래 결정 사항 참고)
5. 다음 칸으로 반복


## 실행(명령 목록)


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

# U8 검증 게이트 (자동 확장, cycle-verify "자동 확장 게이트"). 결과는 data/gate/<칸>/, 기준은 gate.toml
uv run src/gate.py g1 --cells 8930e0af13bffff                  # 배치: 차도 위 건물·나무·가로시설, 다른 도로 위 인도, 횡단보도, 칸 경계 폭
uv run src/gate.py summary --cells 8930e0af13bffff [--need fps] # data/gate/<칸>/gate.json (studio·tiles·g2·fps 하위 명령은 cycle-verify)
uv run src/lookalike.py plan --cells 8930e0af13bffff            # G3 외관 닮음: 캡처 목록 -> sheets -> (채점 에이전트) -> score -> walls --apply
uv run src/lookalike.py gaps --min 10                           # 지도가 아직 못 보여 주는 외관을 칸을 넘어 센다(새 규칙 후보)

# 테스트 (속성 기반 테스트 포함)
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
```

## 구현 메모(U2~U5, 2026-10-13~14)

- 설정 값(겹침 기준, 버퍼, 호출 간격, 원점 등 공통)은 `config.toml`, 구역 설정(학교 필지 `school_polygons`, 스폰 `spawn_*`, 이름별 차로 수 `road_lanes_by_name`, 칸 목록 `cells`)은 `regions/<구역>/region.toml`(U7 B, 지금 구역 하나 `bucheon-dodang`), 칸별 판단 파일(details, overrides, signs, trees, walls(U8 잰 벽 색), gate-allow(U8 허용 목록))은 `regions/<구역>/cells/<칸>/<종류>.json`(git 포함), Studio 소스는 위치별로 `studio/ServerStorage/MapBuilder.luau`(Builder)와 `studio/manual/<구역>/{School,Buheung,Park,Landmark}.luau`(수작업). 아래 기록에 나오는 예전 경로(`overrides/<칸ID>.json`, `details/`, `signs/`, `trees/`, `studio/Builder.luau`, `studio/Manual*.luau`, `config.toml`의 학교 필지·스폰)는 2026-10-14에 이렇게 옮겨졌다. 비밀값은 `.env`(`VWORLD_KEY`, `DATA_GO_KR_KEY`, git 제외).
- Overpass와 V-World는 429/502/504와 시간 초과에서 재시도한다(10s, 30s, 60s). 칸 하나가 실패해도 이전 데이터는 유지된다.
- `build_luau.py`는 칸의 건물과 도로로 `data/build/<칸ID>/chunk-NNN.luau`(항목 70개씩), Studio가 받는 `chunks.json`(덩어리 파일을 데이터로), `manifest.json`을 만든다. 가로·나무 계산은 `streets.py`(U7 B에서 `layout_details.py`에서 떼어 냄). 모든 좌표·박스 계산은 Python(`layout.py`), `studio/Builder.luau`는 부품만 만든다. 건물은 최소 면적 회전 직사각형 박스 1개(맞춤 0.8 미만은 manifest의 `poor_fit`), 원점은 세 칸이 만나는 꼭짓점, 스케일 3.6 stud/m(첫 칸을 만든 뒤 확정). Studio 쪽은 `Workspace/Auto/<칸ID>`만 비우고 다시 만들고 `Workspace/Manual`은 읽기만 한다. 스폰은 `config.toml`의 `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`를 정하면 만들어진다.
- 학교 건물(`config.toml`의 `school_polygons` 필지 안, 지금은 심원고 필지)은 가까운 순이 아니라 **면마다 파노라마 하나**(최대 6면, 가림 없는 것)를 골라 면의 가운데를 향한 크롭을 만든다. 첫 칸의 학교 건물 8동에 면 사진 22장(본관은 남·북·동·서 네 면). 나무와 차량은 가림으로 판단하지 않아서 서쪽 면 같은 곳은 약하다. 자세한 내용은 `aidlc-docs/construction/u3-street-view-capture/code/school-faces-change.md`.
- `capture.py`는 건물마다 파노라마를 최대 3장(120 m 안, 방위각 60° 이상 차이) 골라 `captures/`에 저장하고 건물 방향 크롭(1024×768)을 만든다. 호출 간격 1초, 실행당 새 파노라마 100장 상한. 403/429가 재시도 뒤에도 계속되거나 응답 형식이 이상하면 우회하지 않고 멈춘다(`collection_runs`의 `stopped_reason`). `captures/`는 git 제외.
- U4(`judgement.py`, `review.py`, `estimate.py`, `overrides.py`): 층수·높이·벽 색·지붕 모양의 최종값은 **보정 > 사진 판단 > 대장 > 기본값**이다(OSM 값은 참고만). 사진 판단은 Claude가 묶음 이미지(`captures/<칸ID>/sheets/`)를 대장·OSM 숫자 없이(**눈가림**) 보고 `estimates`에 기록하고 대장과의 비교는 `report`가 한다. 사진이 대장과 다르면 확신 high일 때만 사진 값, 그 밖은 대장 유지와 확인 목록. 대장 높이는 층수가 같고 층당 2.5~5 m일 때만 쓰고 아니면 층수 × 3.4 m. 판단과 보정은 `overrides/<칸ID>.json`(git 포함)으로 즉시 내보낸다. 그 파일에 올라가는 `note`와 `reason`에는 사람·번호판·상호 같은 개인 정보를 쓰지 않는다. `build_luau.py`가 최종값을 읽어 건물 부품에 높이·벽 색을 반영하고 속성 `HeightBasis`, `FloorsBasis`, `WallColor`, `Review`(사유를 `-`로 이음)를 단다. 비교 쌍은 Studio 카메라를 크롭 위치에 두고 캡처한다: **`screen_capture`에 항상 `camera_position`과 `look_at_position`을 준다**(인자 없으면 다른 시점이 찍힌다), 세로 시야각 83.58°, Studio 창은 4:3보다 넓게. 설계와 규칙은 `aidlc-docs/construction/u4-judgement-corrections/`.
- U5(`details_rules.py`, `layout_details.py`, `details.py`): 건물마다 세부 판단(`details` 표, `details/<칸ID>.json`) > U4 메모 검색 > 기본값으로 마감·1층 용도·계단실·돌출창·발코니·지붕 색·옥상을 정하고, `build_luau.py`가 지붕(쐐기), 층 띠, 창(불투명 부품), 계단실, 발코니, 문, 가게 전면, 마당 담·대문, 간판(가상 한글 이름, `SurfaceGui`), 가로(연석, 노면, 횡단보도, 전봇대·전선, 가로등, 가로수, 주차 차량, 스쿨존 울타리, 볼라드)를 항목으로 만든다. 같은 건물의 V-World 중복 외곽선은 뺀다. 안 맞는 외곽선은 박스 ≤ 3개(학교 6)로 나눈다. 모든 변화는 `details_rules.pick`(crc32 + 혼합)뿐이다. 외부 자산(텍스처 업로드, 메시, 크리에이터 스토어)은 쓰지 않는다. 간판 글자는 `SIGN_TEXT = [가-힣A-Za-z0-9 ]{1,12}`로만 검사해 그대로 Luau에 넣고, 그 밖의 글자는 `SAFE_TEXT` 그대로다. 리터럴 키 `i p m c o t u md j g l`은 기본과 다를 때만. 규칙은 `aidlc-docs/construction/u5-details/functional-design/business-rules.md`, 코드 차이는 `.../code/code-summary.md`. 수작업 학교는 `studio/ManualSchool.luau`, 부흥중은 `studio/ManualBuheung.luau`를 `execute_luau`(Edit)로 실행한다(맨 위 폴더마다 없을 때만 만들고 지우지 않는다. 한 부분을 다시 만들려면 그 폴더만 지우고 다시 실행; 좌표는 첫 칸 값이라 다른 칸에는 쓰지 않는다).
- **Roblox 업로드 검수(2026-10-13)**: 간판 이미지 37장을 올리던 중 Roblox가 `403 User is moderated`를 냈다. 즉시 멈췄고(재시도·우회 없음) 36장만 기록했다. 원인으로 의심되는 것은 맥주잔 아이콘이 든 "호프" 간판(술은 Roblox 정책 위반)이라 이름 풀에서 "호프"를 빼고 아이콘을 지웠다(가드 테스트 있음). 나머지 108장은 **사용자가 Roblox 계정의 검수 안내를 확인·해결한 뒤**에만 다시 올린다. 업로드 전에는 간판 글자·아이콘에 술·담배·도박 어휘가 없는지 본다.
- 학교 수작업 v4(2026-10-13): `studio/ManualSchool.luau`는 U3 거리뷰 크롭과 사용자가 준 사진 3장으로 다시 만들었다(운동장 쪽 남동 긴 동 `#b3`에 현관 캐노피·계단·교명판·시계, 색 창틀, 크림색 동쪽 끝벽에 파란 "심원고등학교" 글자와 벽돌 모서리, 짙은 지붕 띠, 북쪽 계단탑; 북서 큰 동 `#b0`에 붉은 지붕; 적벽돌 동 `gis:11185281`에 아치 유리창·발코니 스택·짙은 박공; 초록 차양 스탠드, 농구장 철망, 화분 소나무, 흰 잎무늬 울타리(도로 쪽)와 초록 막대 울타리(서쪽), 화강암 교문 기둥과 접이식 문, 서쪽 소공원). 1,093부품. 학교 archetype의 창은 리본 대신 교실 격자(1.8×1.5 m, 2.4 m 간격)다. 본관 동쪽 끝 글자 같은 큰 글씨는 `SurfaceGui.PixelsPerStud`를 10 정도로 낮춰야 보인다(TextSize 상한 100 px). 캡처는 만든 직후에는 SurfaceGui가 비어 보이니 1분 뒤 다시 찍는다.
- 학교 v5·부흥중 v2(2026-10-13): V-World 위성 z19를 Studio 수직 캡처(높이 650에서 0.974 px/stud)에 맞춰 겹쳐 보고(`data/compare/`, 위치 오차 1~2 m) 고쳤다. 운동장은 건물처럼 10° 돌아간 397×192 stud, 초록 철망은 축구장을 감싸는 320×150. `gis:11215390`(U4에서 4층으로 본 것)은 실제로 운동장 북쪽 청록 스탠드 차양이라 `Shelters`가 그 `BuildingId`를 가진다. `gis:11215391`은 철골 퍼걸러, `gis:11215393`은 열린 쉼터. 빨간 박공은 체육관 크기(약 40×28 m)만. 부흥중은 계남로 울타리·정문, 청록 지붕과 태양광, 데이터에 없는 운동장·농구장·체육관(높이 추정)·통로. **Auto 평지붕 위에는 `#cap`(높이 2.88, `CanQuery=false`)이 있어 박스 윗면에 얹은 부품은 가려진다. 지붕을 얹을 때는 cap 위(박스 윗면 + 2.16)에.** 캡처하면 편집 카메라가 `Scriptable`로 바뀌니 끝나면 `Fixed`로 되돌린다.
- 건물은 자기 중심점이 속한 칸에만 저장되므로 칸 사이 중복이 없다. DB는 `data/map.db`, 로그는 `data/logs/*.jsonl`, 칸 재수집 직전 백업은 `data/backups/`(모두 git 제외).
