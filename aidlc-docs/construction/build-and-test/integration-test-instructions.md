# Integration Test Instructions

## Purpose
U1 안에서 C1(`cells.py`) → DB → C2(`register.py`)의 연결과, 실제 외부 서비스(Overpass, V-World)와의 동작을 확인한다. 다른 유닛과의 통합은 해당 유닛을 만들 때 추가한다(U3, U2는 `buildings`, `street_features`를 읽는다).

## 자동화된 통합 테스트 (외부 호출 없음)
`tests/test_parse.py`가 가짜 HTTP로 한다.
- `collect_cell`을 두 번 돌려도 DB 상태가 같다(P-8, end to end), 백업 파일이 생긴다.
- `assemble_cell`이 칸 소유 건물만 저장하고 두 번 돌려도 같다.
- `fetch_vworld`가 모든 페이지를 따라가고 키를 요청에 쓰되 오류 메시지에 노출하지 않는다.

## 실제 서비스 통합 확인 (수동, 키 필요)

### Scenario 1: 첫 칸 수집과 조립
- **Setup**: `.env`에 `VWORLD_KEY`. 깨끗한 DB(`rm -f data/map.db`).
- **Test Steps**:
  ```bash
  uv run --env-file .env src/cells.py --cells 8930e0af13bffff
  uv run --env-file .env src/register.py --cells 8930e0af13bffff
  ```
- **Expected Results**: 두 실행 모두 `1 ok, 0 failed`. `collection_runs`에 C1, C2 한 줄씩 `ok`.
- **Cleanup**: 필요하면 `rm -f data/map.db`. 백업과 로그는 `data/`에 남는다.

### Scenario 2: 같은 입력으로 재실행
- **Test Steps**: `register.py`를 한 번 더 돌리고 DB 상태의 해시를 비교한다.
- **Expected Results**: 해시가 같다(재수집은 같은 결과, NFR-3).

### Scenario 3: 로그와 파일에 키가 없다
- **Test Steps**: `data/logs/*.jsonl`과 저장소의 모든 파일에서 `.env`의 키 값을 검색한다.
- **Expected Results**: 없음.

## 이번 실행 결과 (2026-10-13)
- Scenario 1: 성공. C1은 Overpass가 504를 세 번 내서 재시도 후 약 131초, C2는 약 4초.
- Scenario 2: 재실행 전후 DB 해시가 같았다(`cd65eb629317dfeb`).
- Scenario 3: 로그 2개 파일과 모든 추적 파일에 키 없음.

## U3 거리뷰 캡처 (2026-10-13)

### 자동화된 통합 테스트 (네이버 호출 없음)
`tests/test_capture.py`가 가짜 네이버와 합성 큐브 맵으로 한다: 상한과 재개(상한 때문에 멈춘 실행을 이어 돌린 결과가 한 번에 돌린 결과와 같음, 파일 바이트까지), 차단 뒤 호출이 없음, 다시 계획, 파노라마 하나가 실패해도 계속, 크롭 실패 기록, 설정이 바뀌면 바뀐 크롭만 다시 만듦, 저장 경로.

### 실제 서비스 통합 확인 (수동, 키 없음)

#### Scenario 1: 첫 칸 캡처
- **Setup**: `data/map.db`에 `buildings`가 있을 것(U1). 시작 전 `cp data/map.db data/backups/pre-u3-map.db`.
- **Test Steps**: `uv run src/capture.py --cells 8930e0af13bffff`를 `stopped_reason=done`이 나올 때까지 되풀이한다.
- **Expected Results**: 상한(100장)에서 멈추면 같은 명령으로 이어서 끝난다. 모든 `building_views`가 `cropped`, 모든 `captures`가 `downloaded`.
- **Cleanup**: `captures/`를 지우고 `building_views`, `captures` 행을 지우면 처음부터 다시 할 수 있다(또는 `--replan`).

#### Scenario 2: 같은 입력으로 재실행
- **Expected Results**: 네이버를 부르지 않고 크롭을 새로 만들지 않는다(`new_downloads=0`, `crops=0`, `crops_kept=363`).

#### Scenario 3: 로그와 사진 파일에 비밀값이 없다
- **Expected Results**: `data/logs/capture-*.jsonl`과 `captures/*/*/meta.json` 227개 파일에서 `.env` 값을 찾지 못한다. `captures/`는 git 제외.

### 이번 실행 결과 (첫 칸 `8930e0af13bffff`)
- Scenario 1: 3번 만에 끝났다(100장에서 멈춤, 100장에서 멈춤, 26장으로 완료). 차단, 재시도, 실패 모두 0.
- Scenario 2: 1초, 네이버 호출 없음, `crops_kept=363`.
- Scenario 3: 227개 파일에서 비밀값 없음.
- 정합성: DB에 적힌 모든 파일이 있다(0개 누락). 크롭 363개 전부 1024×768, 확인한 파노라마 전부 6144×1024.
- 눈으로 확인: 무작위 32장 + 건물 5장. 대부분 건물이 가운데에 온다(아래 요약의 "발견한 것" 참고).

#### Scenario 4: 크롭 규칙을 바꾼 뒤 재실행 (BR-4.5)
- **Test Steps**: 위쪽 각도·시야각 규칙을 바꾼 뒤 `uv run src/capture.py --cells 8930e0af13bffff`.
- **Expected Results**: 네이버를 부르지 않고(`new_downloads=0`), 값이 바뀐 크롭만 다시 만든다.
- **이번 결과**: 크롭 360개를 다시 만들고 3개는 그대로(73초, 실패 0). 지붕과 지면이 모두 들어오는 크롭이 241개(66%) → 312개(86%), 건물 단위 114/122 → 121/122.
