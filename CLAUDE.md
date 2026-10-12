# roblox-map

실제 동네를 Roblox 롤플레이/타운 맵으로 만든다. 구역은 H3 칸으로 나누고, 칸 하나씩 채우고 반복한다.

## AI-DLC

개발 요청은 `.aidlc-rule-details/core-workflow.md`를 먼저 읽고 따른다(v1.0.1, `aidlc-workflows`에서 복사). 질문은 채팅이 아니라 `aidlc-docs/` 안의 질문 파일에 `[Answer]:` 형식으로 둔다. 진행 상태는 `aidlc-docs/aidlc-state.md`, 입력 기록은 `aidlc-docs/audit.md`(덮어쓰지 말고 추가만).

## 파이프라인

1. 구역 지정: 위경도 4점 → `cells.py`가 H3 칸으로 채움 (해상도 9 ≈ 변 200m·넓이 0.105km², 10 ≈ 변 76m)
2. 칸마다 OpenStreetMap 건물 외곽선·높이를 받아 `cells/<칸ID>.json`에 저장
3. 칸 하나를 Studio에 건물 박스로 생성 (Roblox Studio MCP 서버로 Luau 실행)
4. 칸 안 모든 건물을 네이버 거리뷰 자동 캡처(Playwright)로 높이·색·지붕 등을 판단해 다듬음 (사용자 결정, 아래 결정 사항 참고)
5. 다음 칸으로 반복

## 결정 사항

- 형태는 데이터(OSM)로, 거리뷰는 외관 판단용으로만 쓴다. 사진을 텍스처로 복사하지 않는다(텍스처는 일반 재질로 현실감을 냄).
- 거리뷰 자동 캡처: 사용자가 칸 안 모든 건물에 대해 Playwright 자동 캡처로 진행하기로 결정(2026-10-12). 네이버지도 약관은 확인하지 않고 진행하기로 사용자가 결정했다(2026-10-13). 약관 위반으로 생길 수 있는 차단 등의 위험은 사용자가 감수한다. 안전장치: 요청 속도 제한 / CAPTCHA·봇 차단이 나오면 우회하지 말고 중단 / 캡처 이미지는 로컬에만 두고 `captures/`로 git 제외(저장소가 public이고 이미지에 사람 얼굴·차량 번호가 있을 수 있음).
- 스킬/하네스를 새로 만들지 않는다. 필요한 건 **Studio 내장 MCP 서버**(https://create.roblox.com/docs/studio/mcp) 하나. 별도 저장소(`Roblox/studio-rust-mcp-server`)는 2026-04 아카이브되었고 Roblox가 내장 서버를 권장한다.
- Git은 스크립트와 `aidlc-docs/`만 관리한다(`main` 브랜치). 맵 원본 `.rbxl`은 바이너리라 diff가 안 되므로 `.gitignore`로 제외. 맵 백업은 Studio 클라우드 저장(Version History) + 큰 작업 전 `.rbxl` 복사본. `cells/`는 OSM에서 재생성 가능한 데이터라 제외.
- 건물은 외곽선 전체가 아니라 단순화한 박스로 시작한다. 비정형 외곽선은 필요한 건물만 나중에.
- 첫 대상은 부천 심원고등학교(H3 해상도 9 칸 3개). 경험과 데이터가 쌓이면 같은 H3 칸 방식으로 다른 동네로 확장한다(사용자 결정, 2026-10-12).
- 높이: 층수는 V-World 건물통합정보(건축물대장 계열 속성) 1순위, 거리뷰로 층수와 비율을 검증, 값이 없거나 어긋나는 건물만 거리뷰 기하 추정. OSM 높이·층수 태그는 참고로 기록만 한다. 만든 뒤 사용자와 Claude가 같이 보고 현실 스케일에 맞는지 확인해서 보정한다(순서는 AI 추천, 거리뷰 기본으로 되돌릴 수 있음). 건물 외곽선과 층수·높이는 V-World 건물통합정보(`LT_C_BLDGINFO`, 개발키 `VWORLD_KEY`, 만료 2027-04-13)로 받는다(2026-10-13 시험: 심원고 3칸 건물 약 85~203개/칸, 층수 88~93%, 높이 45~62%, OSM은 5~10개/칸). 건축HUB API는 호출만 확인했고 U1에서는 쓰지 않는다. 인증키는 `.env`(`VWORLD_KEY`, `DATA_GO_KR_KEY`, git 제외)로만 쓴다.

## 실행

```bash
uv run cells.py RES lat,lon lat,lon lat,lon [lat,lon ...]
# 예: uv run cells.py 9 37.5643,126.9754 37.5643,126.9804 37.5683,126.9804 37.5683,126.9754
```

- Overpass 공개 서버가 504/429를 자주 내서 재시도가 들어 있음(10s, 30s, 60s). 큰 영역은 느리다.
- 건물은 중심점이 속한 칸에만 저장되므로 칸 사이 중복이 없다.

## 현재 상태

- `cells.py` 동작 확인. 서울시청 근처로 임시 테스트: 칸 3개, 건물 128개.
- 건물 128개 중 height/building:levels 태그가 있는 것은 26개(서울시청 테스트 기준). OSM 태그는 부족하므로 V-World 건물통합정보의 층수와 거리뷰로 보완한다.
- 서울시청 칸은 임시 테스트였다. 실제 대상은 심원고 3칸(`8930e0af13bffff`, `8930e0af123ffff`, `8930e0af12bffff`)이고 아직 데이터를 받지 않았다.
- Roblox Studio 설치와 내장 MCP 연결 완료, 동작 확인(2026-10-12). `execute_luau`로 생성, `screen_capture`로 캡처가 된다. 열린 장소에 테스트용 `MCP_Test` 폴더가 남아 있다.
- AI-DLC: Requirements 승인, User Stories 건너뜀, Workflow Planning 계획서(`aidlc-docs/inception/plans/execution-plan.md`) 승인 대기.

## 다음 할 일

1. 실행 계획서 승인 → Application Design → Units Generation → Construction 순서(`aidlc-state.md` 참고)
2. `cells/*.json` 한 칸을 읽어 Studio에 건물 박스로 생성하는 Luau 작성
3. 거리뷰가 브라우저 패널에서 실제로 열리고 이동되는지 확인(U1 다음에 바로 시험, 유닛 순서는 U1 → U3 → U2 → U4 → U5)

## 주의

- MCP 서버는 열린 맵을 읽고 수정할 수 있다. 신뢰하는 클라이언트만 연결하고 큰 작업 전 백업.
- 내장 MCP 서버는 `screen_capture`(뷰포트 캡처), `execute_luau`, `search_game_tree`, `start_stop_play`, `get_console_output` 등을 제공한다. `execute_luau`는 `studio_id`와 `datamodel_type`(Edit)이 필수다. 외관은 Claude가 직접 캡처해서 확인하고, 최종 판단은 사용자가 한다.
