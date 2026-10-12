# Build and Test Summary

범위: U1 데이터 기반 (2026-10-13). 이후 유닛이 끝날 때마다 이 문서에 해당 유닛의 결과를 추가한다.

## Build Status
- **Build Tool**: `uv` 0.11.28, Python 3.14.6. 컴파일 단계는 없다.
- **Build Status**: 성공 (전체 `py_compile` 통과, 테스트 93개 수집)
- **Build Artifacts**: 없음. 실행하면 `data/map.db`, `data/logs/`, `data/backups/`가 생긴다(git 제외).
- **Build Time**: 해당 없음

## Test Execution Summary

### Unit Tests
- **Total Tests**: 93 (속성 기반 테스트 P-1~P-10 포함)
- **Passed**: 93
- **Failed**: 0
- **Coverage**: 측정 도구 없음. 속성 P-1~P-10과 BR 예시가 테스트에 1:1로 대응
- **Status**: Pass (시드 20261013에서 약 4초, 시드 7개로 재확인)

### Integration Tests
- **Test Scenarios**: 자동 3개(가짜 HTTP), 실제 서비스 3개
- **Passed**: 6 / 6
- **Failed**: 0
- **Status**: Pass
  - 실제 첫 칸 수집과 조립 성공, 재실행해도 DB 상태가 같음, 로그와 파일에 키 없음.

### Performance Tests
- **Response Time**: `cells.py` 약 131초(Overpass 504 재시도 대기 100초 포함), `register.py` 약 4초 (목표: 수 분 이내)
- **Throughput / Error Rate**: 해당 없음
- **Status**: Pass

### Additional Tests
- **Contract Tests**: N/A (공개 API를 소비만 한다)
- **Security Tests**: Pass (`pip-audit` 취약점 없음, 키 검색 통과, 마스킹 검증)
- **E2E Tests**: N/A (이 유닛의 끝은 DB다. Studio까지의 end-to-end는 U2 이후)
- **CI**: GitHub Actions 첫 실행 성공(2026-10-12 push, 32초). `pytest`(시드=실행 번호)와 `pip-audit` 모두 통과

## 첫 칸 `8930e0af13bffff` 실제 결과

| 항목 | 값 |
|---|---|
| V-World 건물(버퍼 포함 수신) | 558 (페이지 1, 버린 것 0, 무효 0) |
| 칸 소유 건물 | **122** (전부 V-World 외곽선, OSM 전용 0) |
| 지상층수 있음 | 106 (87%) |
| 높이 있음 | 101 (83%) |
| 이름 있음 / OSM 태그가 붙음 | 20 / 10 |
| OSM 건물(버퍼 포함) | 68 수신, 59개가 유효하고 칸 근처, 무효 0 |
| OSM과 V-World의 최대 겹침 | 0.9 이상 50개, 0.7~0.9 8개, 0.5~0.7 1개, **0.5 미만 0개** |
| 도로·보행로 | 18 (도로 17, 보행로 1, 횡단보도·나무·가로등·벤치 0) |
| 층당 높이 (높이 ÷ 층수) | 중앙값 3.43 m, 범위 2.45~4.23 m |
| 층수 분포 | 3층 84, 2층 6, 7층 6, 5층 3, 4층 2, 10층 2, 1·8·9층 각 1 |

### 이 결과가 다음 유닛에 주는 정보
- **겹침 기준 0.5는 적절하다.** OSM 건물이 모두 V-World와 0.5 이상 겹쳤고 애매한 구간(0.3~0.5)이 비어 있다. 기준을 바꿀 이유가 없다.
- **버퍼 150 m**: 칸 경계 건물 처리에 문제가 보이지 않았다(무효, 버린 요소 0).
- **U4 입력**: 층당 높이는 대략 3.4 m(범위 2.5~4.2 m)다. 층수만 있고 높이가 없는 건물(약 5%)은 이 값으로 높이를 정하는 것이 출발점이다. 층수도 없는 건물(13%)은 거리뷰 판단이 필요하다.
- **가로시설**: OSM에 나무·가로등·벤치·횡단보도가 없다. U5에서 정해야 한다(계획대로).
- **Overpass**: 이번에도 504가 세 번 났다. 재시도로 해결됐지만 칸을 여러 개 돌릴 때는 시간이 늘어난다.

## Test Findings (생성과 실행 중에 찾은 것)
1. 영역 점과 `--cells`를 함께 주면 argparse가 점까지 칸 ID로 읽었다 → 사용법 오류로 고침.
2. Hypothesis 생성기 필터가 시드 7에서 건강 검사에 걸렸다 → 필터 제거.
3. 실제 키가 테스트 상수로 들어갔다 → 커밋 전에 가짜 값으로 교체, 이력에 없음.
4. 콘솔 로그에 건수가 보이지 않았다(NFR-U1) → 콘솔에 필드를 표시하고 테스트로 고정.

## Overall Status
- **Build**: 성공
- **All Tests**: Pass (93 + 실제 칸 확인)
- **Ready for the next unit (U3)**: 예
- **Ready for Operations**: 해당 없음(아직 U3, U2, U4, U5가 남았다)

## Next Steps
U1의 Build and Test가 끝났다. 승인하면 U3 거리뷰 캡처를 시작한다. 첫 일은 Playwright로 거리뷰가 열리고 이동되는지 시험하는 것이다.
