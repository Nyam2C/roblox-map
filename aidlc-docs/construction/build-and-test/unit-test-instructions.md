# Unit Test Execution

## Run Unit Tests

### 1. 모든 테스트 실행
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
# 속성 기반 테스트를 같은 시드로 재현하려면:
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/ --hypothesis-seed=<시드>
```

### 2. 결과 확인
- **기대**: 93개 통과, 실패 0 (U1 기준).
- **커버리지**: 측정 도구는 도입하지 않았다(NFR-M5). 대신 설계 문서의 속성 P-1~P-10 전부와 BR 규칙의 예시를 테스트가 직접 대응한다.
- **리포트 위치**: 콘솔 출력. 실패하면 Hypothesis가 최소 반례와 재현 방법(blob)을 출력한다(PBT-08).

### 3. 실패했을 때
1. 실패한 테스트 이름과 출력된 최소 반례를 본다.
2. 속성 테스트라면 출력된 `@reproduce_failure` 또는 시드로 같은 입력을 다시 만든다.
3. 코드(또는 틀린 테스트)를 고치고 다시 돌린다. 간헐적으로 실패하는 속성 테스트는 무시하지 말고 원인을 찾는다.

## 이번 실행 결과 (2026-10-13)
- 시드 20261013: 93개 통과, 약 4초.
- 생성 중에 시드 1, 7, 42, 2026, 99999, 3, 11로도 통과했다. 시드 7에서 한 번 생성기 필터 건강 검사에 걸렸고 필터를 없애 해결했다.
- 파일별: `test_geo.py` 38, `test_db.py` 10, `test_common.py` 21(콘솔 건수 표시 확인 포함), `test_parse.py` 20, `test_versions.py` 4.

## U3 거리뷰 캡처 (2026-10-13)

### 실행
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
# CI와 같게 고정 일치 검사까지 돌리려면(해석 목록을 먼저 만든다):
uv export --script src/capture.py --no-hashes --no-annotate --no-header > /tmp/capture-resolved.txt
CAPTURE_RESOLVED=/tmp/capture-resolved.txt uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
```
- **기대**: 152개 통과. `CAPTURE_RESOLVED`가 없으면 `test_capture_pins_cover_the_whole_resolved_set` 한 개만 건너뛰어 151개 통과, 1개 생략.

### 이번 실행 결과
- 152개 통과(U1 93개 + U3 59개). 시드 1, 7, 42, 2026, 99999, 20261013, 3 모두 통과, 약 4초. 위쪽 각도 규칙을 바꾼 뒤 테스트 4개를 더했다(가장 가까운 벽 거리 2개, 지붕과 지면이 들어오는 속성 1개, 벽 기준으로 조준하는 예시 1개).
- 파일별: `test_projection.py` 19(P3-1, P3-2, P3-4, P3-5), `test_capture.py` 34(P3-3, P3-6, P3-7, P3-8, 실패 규칙, 어댑터), `test_db.py` 13(+3), `test_versions.py` 7(+3), `test_common.py` 21, `test_geo.py` 38, `test_parse.py` 20.
- **테스트가 실제로 잡는지** 규칙 6곳(상한 검사, 차단 뒤 계속 두 곳, 가까운 순 정렬, 방위각 간격, 크롭 실패 기록, `no_photo` 행)과 새 크롭 규칙 3곳(중심점 거리로 되돌리기, 세로 시야 확대 빼기, 지붕으로 조준)을 일부러 깨뜨려 확인했다. 모두 실패로 잡혔다.
- 생성 중에 테스트가 알려 준 것: 가까운 큰 건물의 시야각이 상한 100°에 걸려서, 상한을 올리면 그 크롭만 다시 만들어진다(BR-4.5가 의도한 동작). 테스트 기대값을 "저장된 값이 바뀐 크롭만"으로 바로잡았다.
