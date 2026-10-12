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
