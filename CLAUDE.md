# roblox-map

실제 동네를 Roblox 롤플레이/타운 맵으로 만든다. 구역은 H3 칸으로 나누고, 칸 하나씩 채우고 반복한다.

## AI-DLC

개발 요청은 `.aidlc-rule-details/core-workflow.md`를 먼저 읽고 따른다(v1.0.1, `aidlc-workflows`에서 복사). 질문은 채팅이 아니라 `aidlc-docs/` 안의 질문 파일에 `[Answer]:` 형식으로 둔다. 진행 상태는 `aidlc-docs/aidlc-state.md`, 입력 기록은 `aidlc-docs/audit.md`(덮어쓰지 말고 추가만).

## 파이프라인

1. 구역 지정: 위경도 4점 → `cells.py`가 H3 칸으로 채움 (해상도 9 ≈ 변 170m, 10 ≈ 65m)
2. 칸마다 OpenStreetMap 건물 외곽선·높이를 받아 `cells/<칸ID>.json`에 저장
3. 칸 하나를 Studio에 건물 박스로 생성 (Roblox Studio MCP 서버로 Luau 실행)
4. 눈에 띄는 건물만 네이버 거리뷰를 참고해 색, 간판, 지붕을 다듬음
5. 다음 칸으로 반복

## 결정 사항

- 형태는 데이터(OSM)로, 거리뷰는 외관 참고용으로만 쓴다. 사진을 텍스처로 복사하지 않는다. 네이버지도 약관상 자동 수집이 막혀 있을 수 있으니 확인 전까지 대량 수집 금지.
- 스킬/하네스를 새로 만들지 않는다. 필요한 건 Roblox Studio MCP 서버(https://github.com/Roblox/studio-rust-mcp-server) 하나. 설치 전 README에서 폐기·대체 여부 확인.
- Git은 스크립트와 `aidlc-docs/`만 관리한다(`main` 브랜치). 맵 원본 `.rbxl`은 바이너리라 diff가 안 되므로 `.gitignore`로 제외. 맵 백업은 Studio 클라우드 저장(Version History) + 큰 작업 전 `.rbxl` 복사본. `cells/`는 OSM에서 재생성 가능한 데이터라 제외.
- 건물은 외곽선 전체가 아니라 단순화한 박스로 시작한다. 비정형 외곽선은 필요한 건물만 나중에.

## 실행

```bash
uv run cells.py RES lat,lon lat,lon lat,lon [lat,lon ...]
# 예: uv run cells.py 9 37.5643,126.9754 37.5643,126.9804 37.5683,126.9804 37.5683,126.9754
```

- Overpass 공개 서버가 504/429를 자주 내서 재시도가 들어 있음(10s, 30s, 60s). 큰 영역은 느리다.
- 건물은 중심점이 속한 칸에만 저장되므로 칸 사이 중복이 없다.

## 현재 상태

- `cells.py` 동작 확인. 서울시청 근처로 임시 테스트: 칸 3개, 건물 128개.
- 건물 128개 중 height/building:levels 태그가 있는 것은 26개. 나머지는 기본 높이 또는 V-World 등 다른 데이터로 보완 필요(V-World 제공 범위는 미확인).
- 실제로 만들 동네는 아직 미정. 테스트 위치는 임시다.
- Roblox Studio 미설치(`/Applications`에 없음). 사용자가 직접 설치해야 함.

## 다음 할 일

1. 사용자가 만들 동네(4점 또는 장소명) 확정
2. Studio 설치 후 MCP 서버 연결 (`claude mcp add --transport stdio Roblox_Studio -- <rbx-studio-mcp 경로> --stdio`)
3. `cells/*.json` 한 칸을 읽어 Studio에 건물 박스로 생성하는 Luau 작성
4. 높이 없는 건물의 기본 높이 규칙 정하기
5. 거리뷰가 브라우저 패널에서 실제로 열리고 이동되는지 확인

## 주의

- MCP 서버는 열린 맵을 읽고 수정할 수 있다. 신뢰하는 클라이언트만 연결하고 큰 작업 전 백업.
- 이 프로젝트에서 Claude는 Studio 화면을 직접 캡처하지 못한다. 외관 확인은 사용자가 Studio에서 본다.
