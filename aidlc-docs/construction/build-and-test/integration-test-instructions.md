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
