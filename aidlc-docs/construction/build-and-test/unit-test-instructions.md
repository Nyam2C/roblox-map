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

## U2 Studio 생성기 (2026-10-13)

### 실행
기존과 같다. CI와 같게 고정 일치 검사까지 돌리려면 `CAPTURE_RESOLVED`를 준다(U3 참고).
- **기대**: 248개 통과(`CAPTURE_RESOLVED`가 없으면 247개 통과, 1개 생략).

### 이번 실행 결과
- 248개 통과(U1 93 + U3 59 + U2 96). 시드 1, 7, 42, 2026, 99999에서 모두 통과, 약 5초.
- 파일별 U2: `test_layout.py` 48(P2-1~P2-7, P2-9와 예시), `test_build_luau.py` 43(코드 주입 방지, 계획, 항목 순서, P2-8, 파일, DB, 실행 기록), `test_common.py` +3(새 설정 검증, 도로 폭 표 병합, 스폰 쌍), `test_versions.py` +2(`build_luau.py` 고정, `Builder.luau` 안전 검사).
- **테스트가 실제로 잡는지** 규칙 12곳을 일부러 깨뜨려 확인했다(`layout` 5, `build_luau` 5, `Builder.luau` 2). 모두 잡혔고, 정렬 변이는 처음엔 살아남아 항목 순서 테스트를 더했다.
- 생성 중 속성 테스트가 알려 준 것: 삼각형과 마름모 같은 대칭 사각형은 최소 면적 박스가 하나로 정해지지 않는다(설계 BR-2.2에 기록).

---

# U4 판단·보정 (2026-10-13)

## 실행
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/test_judgement.py tests/test_review.py tests/test_u4_db.py tests/test_estimate.py tests/test_overrides.py   # U4만
```

## 결과
- **전체**: 412개 통과, 1개 생략(`CAPTURE_RESOLVED`가 없을 때만 건너뛰는 `capture.py` 고정 일치 검사). 시드 1, 7, 42, 2026, 99999, 20261013 모두 같은 결과, 약 8초. CI(GitHub Actions)는 U4 푸시 3번 모두 통과(약 30~45초).
- **U4 파일**: `test_judgement.py` 54, `test_review.py` 17, `test_u4_db.py` 29, `test_estimate.py` 16, `test_overrides.py` 10 = 126개. 기존 파일에도 U4 시험을 더했다(`test_common.py`, `test_layout.py`, `test_build_luau.py`, `test_versions.py`, `test_db.py`).
- **속성 P4-1~P4-16**: 층수 표와 높이 규칙과 보정 우선과 확인 목록과 검증과 내보내기 형식(P4-1, 2, 3, 7, 8, 9, 12)은 `test_judgement.py`, 눈가림과 순서와 시야각과 방위와 일치율(P4-10, 11, 13, 14, 15)은 `test_review.py`, 보정 되돌리기와 교환과 멱등과 왕복과 원자성과 고아(P4-3~P4-7, P4-9, P4-16)는 `test_u4_db.py`.
- **테스트가 실제로 잡는지**: 규칙 12곳(층수 표 한 칸, 높이 보정 무시, 층수가 바뀌었는데 대장 높이 유지, 눈가림 필드 노출, 내보내기 행 정렬, `record` 일부만 저장, `set_override` 멱등 깨짐, 눈가림 깨진 건물 통계 포함, 새 글자 검사 제거, `Review` 구분자를 쉼표로, 내보내기를 제자리에 쓰기, 사진 없는 건물을 계획에 넣기)을 일부러 깨뜨려서 모두 실패로 잡히는 것을 확인했다.
- **생성 중에 테스트가 알려 준 것**: 시야각이 아주 작을 때 4:3 자르기가 반올림으로 어긋난다(실제 크롭은 60~100°라 해당 없음, 속성 범위를 20~100°로 좁힘). 전역 Pillow 픽셀 한도가 `capture.py` 설정과 한 프로세스에서 부딪쳐서 `estimate.py`는 이미지를 열 때 크기를 먼저 보는 방식으로 바꿨다.

---

# U5 디테일 (2026-10-13)

## 실행
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/test_details_rules.py tests/test_u5_db.py tests/test_details.py tests/test_layout_u5.py   # U5만
```

## 결과
- **전체**: 548개 통과, 1개 생략(`CAPTURE_RESOLVED`). 시드 1, 7, 42, 2026, 99999 모두 같은 결과, 약 11초.
- **U5 파일**: `test_details_rules.py`(어휘, 비고 규칙, 이름 풀과 `pick`의 섞임, 간판 글자, 재질 표), `test_u5_db.py`(`details` 표의 원자성·멱등·내보내기·불러오기), `test_details.py`(`pending`/`record`/`list`/`export`/`import` 명령줄), `test_layout_u5.py`(속성 P5-2~7, 9, 11~13, 15, 18, 19와 예시 48개). 기존 파일의 U2 가정(격자 땅, 주거 도로 인도, 덩어리 50개)은 U5 규칙으로 바꿨다.
- **처음 돌렸을 때**: `test_layout_u5.py`가 몇 분을 돌아도 끝나지 않았다. 원인은 코드였다. `_slots`가 간격 0.0001 m 같은 값에서 수백만 자리를 만들었다(속성 테스트가 0~60 m 실수를 넣음). 1 m 미만은 "없음"으로 바꿨다. 그 뒤 12개가 실패했는데 모두 테스트 쪽이었다: shapely `Polygon`을 점 하나로 만든 도우미, 위경도→m가 0.1 % 비등방이라 생긴 `abs=0.01` 허용치, 항목 이름 형식(`rb0f0-0`), 공공기관 이름 고정값, `Item` 정렬 키, 옥상 간판 기둥(`facade`)이 간판 목록에 섞인 것. 고치고 나니 **코드 결함 하나가 더 드러났다**: 외곽선 꼭짓점을 지나는 절단선이 0.005 m² 조각을 남겨 L자 건물이 한 박스로 남았다(`_pieces_sorted`가 0.01 m² 미만을 버리고 절단 위치를 반올림 전 값으로 씀). 이 수정으로 첫 칸 부흥중학교의 박스가 32×11 m에서 24×11 m로 바뀌었다(항목 4,893 → 4,881).
- **테스트가 실제로 잡는지(코드 망가뜨리기 16곳)**: 처음 11곳이 잡혔다. 안 잡힌 5곳 중 4곳(뒷면 yaw 0, 겹침 0.6 기준 무시, 창이 문을 덮음, 간판 `md` 키를 `x`로)에 테스트를 더해 잡히게 했다(다시 돌려 4곳 모두 잡힘). 남은 1곳(`_pieces_sorted`의 0.01 m² 조각 버리기를 1e-9로 되돌림)은 절단 위치를 반올림 전 값으로 쓰는 수정이 같은 결함을 먼저 막아서 테스트로 구분되지 않는다(안전띠로 둔다). 목록: `aidlc-docs/construction/plans/u5-details-code-generation-plan.md`.
