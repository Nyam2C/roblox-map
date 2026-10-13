# roblox-map

실제 동네를 Roblox 롤플레이/타운 맵으로 만든다. 구역은 H3 칸으로 나누고, 칸 하나씩 채우고 반복한다.

## AI-DLC

개발 요청은 `.aidlc-rule-details/core-workflow.md`를 먼저 읽고 따른다(v1.0.1, `aidlc-workflows`에서 복사). 질문은 채팅이 아니라 `aidlc-docs/` 안의 질문 파일에 `[Answer]:` 형식으로 둔다. 진행 상태는 `aidlc-docs/aidlc-state.md`, 입력 기록은 `aidlc-docs/audit.md`(덮어쓰지 말고 추가만).

## 파이프라인

1. 구역 지정: 위경도 4점 또는 칸 ID → `src/cells.py`가 H3 칸으로 채움 (해상도 9 ≈ 변 200m·넓이 0.105km², 10 ≈ 변 76m)
2. 칸마다 V-World 건물통합정보(외곽선·층수·높이)와 OSM(이름·태그, 도로·가로시설)을 받아 `data/map.db`(SQLite)에 저장, `src/register.py`가 건물을 조립
3. 칸 하나를 Studio에 건물 박스로 생성 (Roblox Studio MCP 서버로 Luau 실행)
4. 칸 안 모든 건물을 네이버 거리뷰 자동 수집(`streetlevel` 라이브러리, 건물마다 파노라마 최대 3장과 건물 방향 크롭)으로 높이·색·지붕 등을 판단해 다듬음 (사용자 결정, 아래 결정 사항 참고)
5. 다음 칸으로 반복

## 결정 사항

- 형태는 데이터(OSM)로, 거리뷰는 외관 판단용으로만 쓴다. 사진을 텍스처로 복사하지 않는다(텍스처는 일반 재질로 현실감을 냄).
- 거리뷰 자동 캡처: 사용자가 칸 안 모든 건물에 대해 자동 캡처로 진행하기로 결정(2026-10-12). 2026-10-13에 브라우저 없이 되는 `streetlevel` 방식을 시험해서 이것을 기본으로 정했고 Playwright는 기술적 고장이 났을 때 새 작업으로 시작한다. 차단되면 다른 방식으로 바꾸지 않고 멈춘다. 네이버지도 약관은 확인하지 않고 진행하기로 사용자가 결정했다(2026-10-13). 약관 위반으로 생길 수 있는 차단 등의 위험은 사용자가 감수한다. 안전장치: 요청 속도 제한 / CAPTCHA·봇 차단이 나오면 우회하지 말고 중단 / 캡처 이미지는 로컬에만 두고 `captures/`로 git 제외(저장소가 public이고 이미지에 사람 얼굴·차량 번호가 있을 수 있음).
- 스킬/하네스를 새로 만들지 않는다. 필요한 건 **Studio 내장 MCP 서버**(https://create.roblox.com/docs/studio/mcp) 하나. 별도 저장소(`Roblox/studio-rust-mcp-server`)는 2026-04 아카이브되었고 Roblox가 내장 서버를 권장한다.
- Git은 스크립트와 `aidlc-docs/`만 관리한다(`main` 브랜치). 맵 원본 `.rbxl`은 바이너리라 diff가 안 되므로 `.gitignore`로 제외. 맵 백업은 Studio 클라우드 저장(Version History) + 큰 작업 전 `.rbxl` 복사본. `cells/`는 OSM에서 재생성 가능한 데이터라 제외.
- 건물은 외곽선 전체가 아니라 단순화한 박스로 시작한다. 비정형 외곽선은 필요한 건물만 나중에.
- 첫 대상은 부천 심원고등학교(H3 해상도 9 칸 3개). 경험과 데이터가 쌓이면 같은 H3 칸 방식으로 다른 동네로 확장한다(사용자 결정, 2026-10-12).
- 높이: 층수는 V-World 건물통합정보(건축물대장 계열 속성) 1순위, 거리뷰로 층수와 비율을 검증, 값이 없거나 어긋나는 건물만 거리뷰 기하 추정. OSM 높이·층수 태그는 참고로 기록만 한다. 만든 뒤 사용자와 Claude가 같이 보고 현실 스케일에 맞는지 확인해서 보정한다(순서는 AI 추천, 거리뷰 기본으로 되돌릴 수 있음). 건물 외곽선과 층수·높이는 V-World 건물통합정보(`LT_C_BLDGINFO`, 개발키 `VWORLD_KEY`, 만료 2027-04-13)로 받는다(2026-10-13 시험: 심원고 3칸 건물 약 85~203개/칸, 층수 88~93%, 높이 45~62%, OSM은 5~10개/칸). 건축HUB API는 호출만 확인했고 U1에서는 쓰지 않는다. 인증키는 `.env`(`VWORLD_KEY`, `DATA_GO_KR_KEY`, git 제외)로만 쓴다.

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

# 4) Studio에 올릴 Luau 덩어리 파일 만들기 (비밀값·네트워크 없음). Studio 실행은 Claude가 execute_luau로 한다
uv run src/build_luau.py --cells 8930e0af13bffff
# uv run src/build_luau.py --selftest                       (import만 확인)

# 테스트 (속성 기반 테스트 포함)
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
```

- 설정 값(겹침 기준, 버퍼, 호출 간격 등)은 `config.toml`, 비밀값은 `.env`(`VWORLD_KEY`, `DATA_GO_KR_KEY`, git 제외).
- Overpass와 V-World는 429/502/504와 시간 초과에서 재시도한다(10s, 30s, 60s). 칸 하나가 실패해도 이전 데이터는 유지된다.
- `build_luau.py`는 칸의 건물과 도로로 `data/build/<칸ID>/chunk-NNN.luau`(항목 50개씩)와 `manifest.json`을 만든다. 모든 좌표·박스 계산은 Python(`layout.py`), `studio/Builder.luau`는 부품만 만든다. 건물은 최소 면적 회전 직사각형 박스 1개(맞춤 0.8 미만은 manifest의 `poor_fit`), 원점은 세 칸이 만나는 꼭짓점, 스케일 3.6 stud/m(첫 칸을 만든 뒤 확정). Studio 쪽은 `Workspace/Auto/<칸ID>`만 비우고 다시 만들고 `Workspace/Manual`은 읽기만 한다. 스폰은 `config.toml`의 `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`를 정하면 만들어진다.
- 학교 건물(`config.toml`의 `school_polygons` 필지 안, 지금은 심원고 필지)은 가까운 순이 아니라 **면마다 파노라마 하나**(최대 6면, 가림 없는 것)를 골라 면의 가운데를 향한 크롭을 만든다. 첫 칸의 학교 건물 8동에 면 사진 22장(본관은 남·북·동·서 네 면). 나무와 차량은 가림으로 판단하지 않아서 서쪽 면 같은 곳은 약하다. 자세한 내용은 `aidlc-docs/construction/u3-street-view-capture/code/school-faces-change.md`.
- `capture.py`는 건물마다 파노라마를 최대 3장(120 m 안, 방위각 60° 이상 차이) 골라 `captures/`에 저장하고 건물 방향 크롭(1024×768)을 만든다. 호출 간격 1초, 실행당 새 파노라마 100장 상한. 403/429가 재시도 뒤에도 계속되거나 응답 형식이 이상하면 우회하지 않고 멈춘다(`collection_runs`의 `stopped_reason`). `captures/`는 git 제외.
- 건물은 자기 중심점이 속한 칸에만 저장되므로 칸 사이 중복이 없다. DB는 `data/map.db`, 로그는 `data/logs/*.jsonl`, 칸 재수집 직전 백업은 `data/backups/`(모두 git 제외).

## 현재 상태

- U1(데이터 기반)은 끝났다. 첫 칸 `8930e0af13bffff`는 수집과 조립이 끝나 `data/map.db`에 건물 122개가 있다. 나머지 두 칸(`8930e0af123ffff`, `8930e0af12bffff`)은 아직 데이터를 받지 않았다.
- OSM 태그는 부족하므로(서울시청 시험에서 건물 128개 중 높이·층수 태그 26개) V-World 건물통합정보의 층수와 거리뷰로 보완한다.
- U2 첫 칸이 Studio에 만들어졌다(2026-10-13): 부품 163개(땅 1, 도로 29, 보행로 2, 인도 8, 건물 122, 스폰 1), 스케일 3.6 stud/m 확정, 스폰은 신흥로238번길 보행로 `(37.504483, 126.77861)` yaw −62°(`config.toml`). Studio에는 사용자가 저장했다(Roblox에 저장, 2026-10-13). 복사본 `10122026_1-before-U2.rbxl`은 U2 이전 상태다. 걸을 때 60 FPS(Studio 창이 앞에 있을 때; 뒤에 있으면 15 FPS로 제한됨).
- U2 코드(`src/layout.py`, `build_luau.py`, `studio/Builder.luau`)를 만들었다(2026-10-13). 첫 칸 계획: 항목 162개(땅 1, 도로 29, 보행로 2, 인도 8, 건물 122), 덩어리 4개(6.6 KB 이하), 안 맞는 건물 9개. Studio 시험은 `MCP_Test` 안에서만 했고(실제 덩어리 파일 실행, `Manual` 우선, 재생성 확인) 지웠다. 실제 첫 칸 생성, 장소 설정 변경, 스케일 확정, 스폰 점 제안은 Build and Test에서 하고, 그 전에 사용자의 `.rbxl` 복사본이 필요하다.
- U3 코드(`src/projection.py`, `panorama_source.py`, `capture.py`)를 만들고 첫 칸을 실제로 돌렸다(2026-10-13). 테스트 152개. 첫 칸 결과: 건물 122개에 파노라마 226장과 크롭 363개(384 MB), 사진 없는 건물 0, 차단·재시도·실패 0, 약 13분(3번에 나눠서). 크롭의 32%가 지붕을 놓쳐서 위쪽 각도·시야각 규칙을 벽 기준으로 바꿨다(지붕과 지면이 다 들어오는 크롭 66% → 86%).
- 큐브 맵 규칙(`aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md`): 면 순서 앞·오른쪽·뒤·왼쪽·위·아래, 앞면이 보는 방위각 = ID 조회 `heading` + 180°(설계의 가정과 180° 다르다. 파노라마 3장에서 외곽선을 겹쳐 확인).
- 파이썬 3.13 이상이 필요하다(`capture.py`가 `numpy` 2.5.4를 쓴다). `uv`가 알아서 받는다.
- Roblox Studio 설치와 내장 MCP 연결 완료, 동작 확인(2026-10-12). `execute_luau`로 생성, `screen_capture`로 캡처가 된다. 열린 장소에 테스트용 `MCP_Test` 폴더가 남아 있다.
- AI-DLC: Inception 완료, U1 완료, U3 Functional Design·NFR Requirements·Code Generation 승인, U3 완료(Build and Test 승인). U2 Studio 생성기는 Functional Design·NFR Requirements·Code Generation 계획 승인, Code Generation·Build and Test 승인으로 완료. 다음은 U4(사용자가 시작하라고 하면).

## 다음 할 일

1. U4 판단·보정 → U5 디테일(학교 건물 수작업, 가로시설, 교차로) (`aidlc-state.md` 참고)
2. U4 완료 때 복구 연습(DB를 지우고 S1 재실행, `overrides` 불러오기)

## 주의

- MCP 서버는 열린 맵을 읽고 수정할 수 있다. 신뢰하는 클라이언트만 연결하고 큰 작업 전 백업.
- 내장 MCP 서버는 `screen_capture`(뷰포트 캡처), `execute_luau`, `search_game_tree`, `start_stop_play`, `get_console_output` 등을 제공한다. `execute_luau`는 `studio_id`와 `datamodel_type`(Edit)이 필수다. 외관은 Claude가 직접 캡처해서 확인하고, 최종 판단은 사용자가 한다.
