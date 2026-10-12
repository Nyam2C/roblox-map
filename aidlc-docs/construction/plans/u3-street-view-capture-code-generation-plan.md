# U3 거리뷰 캡처 — Code Generation Plan

**이 문서가 코드 생성의 유일한 기준이다.** 생성 단계에서는 여기 적힌 순서와 내용만 한다. 승인 뒤에 단계마다 `[x]`로 표시한다.

## 유닛 맥락

- **유닛**: U3 거리뷰 캡처. 컴포넌트는 C3 `capture.py`와 이 유닛이 새로 만드는 `projection.py`(순수), `panorama_source.py`(어댑터).
- **프로젝트 종류**: 기존 코드가 있는 프로젝트(brownfield). 작업 위치는 저장소 루트 `/Users/taehyeonpark/Desktop/dev/roblox-map`. 코드는 `aidlc-docs/`에 두지 않는다.
- **기존 파일 처리**: `src/db.py`(새 테이블과 함수 추가), `src/common.py`와 `config.toml`(U3 설정 추가), `tests/` 일부, `.github/workflows/ci.yml`, `CLAUDE.md`는 고친다. 복사본을 만들지 않는다.
- **의존하는 유닛**: U1의 `buildings`(외곽선, 중심점, 높이, 층수)와 `db.py`, `common.py`, `config.toml`. 이 유닛이 U4에게 `captures`, `building_views`와 크롭 이미지를 준다.
- **설계 입력**: `construction/u3-street-view-capture/functional-design/`(엔티티, BR-1~BR-6, 속성 P3-1~P3-8), `.../nfr-requirements/`(21개 고정, CI, 어댑터), U1의 NFR Design(패턴, 로그, 설정, 런북).
- **이 유닛이 소유한 데이터**: `captures`, `building_views` 테이블, `captures/` 폴더. `buildings` 등 U1 테이블은 읽기만 한다.

## 요구사항·규칙 추적

| 요구사항·규칙 | 구현 단계 |
|---|---|
| FR-8 (거리뷰 수집, 건물별 사진) | 단계 4~7 |
| NFR-4 (사진은 로컬에만) | 단계 6, 8 (`captures/`는 이미 git 제외) |
| NFR-5 (호출 간격, 상한, 차단 시 우회 없이 중단) | 단계 5, 6 |
| NFR-7 (고정 의존성, 응답 검증) | 단계 2, 5, 8 |
| NFR-8 (속성 기반 테스트) | 단계 3, 4, 6 |
| BR-1~6, P3-1~P3-8 | 단계 3~7 (각 단계에 명시) |
| U3 NFR (SEC2~SEC6, M3~M5) | 단계 5, 7, 8 |

## 단계

### 단계 1. 사전 확인: 큐브 맵 면 순서와 정면 방향 (실험, 저장소에는 결과 문서만)
- [x] 파노라마 한 장(zoom 1, 6144×1024)을 임시 폴더로 내려받아 한 줄 이미지를 면 6개로 나눈다(면 하나는 1024 px). 면을 눈으로 보고 앞, 오른쪽, 뒤, 왼쪽, 위, 아래 순서와 방향(회전이나 뒤집기)을 정한다.
- [x] `heading`이 앞면의 방향인지 확인한다. 건물 하나를 골라 그 방위각으로 크롭을 만들어 보고 그 건물이 가운데에 보이는지 눈으로 확인한다. 안 맞으면 오프셋을 찾아 기록한다. (외곽선 겹쳐 그리기로 확인: 정면 = ID 조회 heading + 180°. 건물 방향 크롭 확인은 단계 3에서 덧붙인다)
- [x] 결과를 `aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md`에 적는다(면 순서, 방향 변환, heading 의미). 임시 이미지는 저장소에 넣지 않는다.
- [x] 면 순서를 못 알아내거나 heading 의미가 불명확하면 멈추고 사용자에게 알린다. (해당 없음: 모두 알아냄)

### 단계 2. 설정과 의존성
- [x] `config.toml`과 `src/common.py`(`DEFAULTS`, 검증)에 U3 항목을 추가한다: `captures_dir`, `pano_limit_m`(120), `pano_separation_deg`(60), `pano_max_views`(3), `pano_pause_s`(1), `max_new_panos`(100), 크롭 크기와 품질(1024×768, 85), 시야각 범위(60~100), 위쪽 각도 최대(40), `camera_height_m`(2.5), `floor_height_m`(3.4), `default_height_m`(10).
- [x] `tests/requirements.txt`에 `numpy==2.5.4`, `pillow==12.3.0`을 추가한다. 이 버전과 `shapely` 2.2.0이 함께 설치되고 기존 93개 테스트가 통과하는지 확인한다. 안 되면 멈추고 알린다.
- [x] `tests/test_common.py`가 기본값 일치와 새 항목 검증(범위 밖 값 거부)을 확인하도록 고친다.

### 단계 3. `src/projection.py` (순수 함수) — BR-2.2, 2.3, 4.1~4.3, P3-1, P3-2, P3-4, P3-5
- [x] `distance_m(a, b)`, `bearing_deg(a, b)`(0 이상 360 미만), `yaw_deg(bearing, heading)`(−180 이상 180 미만).
- [x] `building_extent_deg(outline, pano_pos)`: 파노라마에서 건물 외곽선이 차지하는 각도 범위.
- [x] `crop_params(...)`: 시야각(60~100°, 건물 각도 범위 + 20° 여유), 위쪽 각도(0~40°, 건물 높이 규칙 BR-4.3).
- [x] `render_crop(faces, yaw, pitch, fov, size)`: 단계 1에서 확인한 면 순서로 큐브 맵에서 직선 투영 크롭을 만든다(`numpy`, `pillow`).

### 단계 4. 속성 기반 테스트: projection — P3-1, P3-2, P3-4, P3-5, PBT-07
- [x] `tests/generators.py`에 위치 쌍, 방위각, 후보 목록, 건물 높이·각도 범위 생성기를 추가한다(공용). (후보 목록 생성기는 `Candidate` 타입이 생기는 단계 5 뒤, 단계 7에서 추가한다)
- [x] `tests/test_projection.py`: P3-1(거리·방위각), P3-2(상대 방향), P3-4(크롭 값 범위와 각도 범위 포함), P3-5(면마다 색이 다른 합성 큐브 맵에서 yaw 0, 90, 180, −90의 중심 색). 단계 1에서 확인한 면 순서가 그대로 기대값이다.

### 단계 5. `src/panorama_source.py` (어댑터) — Q1=C, U3 NFR (SEC3, SEC5, SEC6), N-U3-1, BR-5
- [x] `streetlevel`을 이 모듈 안에서 늦게 불러온다. 불러오기 전에 `pyexiv2` 빈 모듈을 `sys.modules`에 끼워 넣는다(이유를 주석으로).
- [x] `find_nearby(lat, lon)`: 가장 가까운 파노라마와 이웃(차량만)의 `Candidate`(ID, 위치)를 돌려준다. `other` 종류는 뺀다.
- [x] `get_metadata(pano_id)`: 방향(도), 촬영일, 최신 여부, 사용 가능한 해상도.
- [x] `download_faces(pano_id, zoom=1)`: 이미지를 받아 크기와 형식을 검증하고(SEC3, `Pillow` 한도 명시) 면 6개로 돌려준다.
- [x] 오류 분류: 403, 429, 응답 형식 이상은 `BlockedError`, 시간 초과는 `TransientError`로 재시도 대기(설정값)를 따른다, 그 밖은 `SourceError`. 호출 간격과 대기 함수는 주입할 수 있게 한다.
- [x] 라이브러리를 불러오지 못하면 시작하지 않고 이유를 알린다(BR-5.3).

### 단계 6. `src/capture.py` — FR-8, BR-1~BR-6, P3-3, P3-6, P3-7, P3-8
- [x] `src/db.py`에 `captures`, `building_views` 테이블과 함수(`upsert_captures`, `upsert_building_views`, `views_for_cell`, `delete_views_for_cell`, `orphan_views`)를 추가한다. 기존 U1 테이블과 함수는 바꾸지 않는다. (읽기 함수 `all_captures`를 하나 더했다)
- [x] `select_panoramas(cands, separation_deg, max_views, usable)`(순수): 가까운 순, 방위각 차이 60° 이상, 최대 3장(BR-2.4, P3-3).
- [x] 흐름: 칸의 `buildings` 읽기 → 이미 처리된 건물 제외(BR-1.2) → 건물마다 후보 조회와 선택 → `no_photo` 기록(BR-2.6) → 파노라마 내려받기(재사용, 상한 100, 간격 1초, 임시 파일 후 이름 바꾸기, BR-3) → 건물별 크롭(BR-4) → DB 기록과 실행 기록.
- [x] 차단 신호(BR-5.2)는 바로 멈추고 저장한 것을 남긴다. 상한에 닿으면 멈추고 다음 실행에서 이어간다(BR-3.4, 6.1). `--replan`(BR-6.2), 고아 보고(BR-6.3).
- [x] 파일 경로: 파노라마는 위치가 속한 칸 폴더, 크롭은 건물이 속한 칸 폴더, 이름은 안전한 문자만(BR-3.2, 4.4, P3-8).
- [x] 진입점은 U1의 `run_cli`로 감싼다. 인라인 의존성은 21개를 정확한 버전으로 두고 `[tool.uv] exclude-dependencies`를 넣는다(Q1=A, Q2=A). `--selftest`는 어댑터를 불러와 `import`만 확인하고 네트워크를 부르지 않는다(N-U3-9).

### 단계 7. 테스트: capture — P3-3, P3-6, P3-7, P3-8, 통합
- [x] `tests/test_capture.py`: P3-3(선택 규칙, 순서 불변), P3-6(상한과 재개: 상한 때문에 멈춘 뒤 이어 돌린 결과가 한 번에 돌린 결과와 같고, 이미 받은 파노라마는 다시 받지 않음), P3-7(차단 신호 뒤 호출이 더 일어나지 않고 저장분은 남음), P3-8(경로와 이름 안전성). 가짜 어댑터와 합성 이미지, 임시 폴더를 쓴다.
- [x] `tests/test_db.py`에 새 테이블 테스트를 추가한다: `building_views` 교체와 `--replan`이 U1 테이블과 `overrides`를 건드리지 않음, `no_photo` 행 재조회 방지, 고아 보고.

### 단계 8. CI와 버전 일치 검사 — Q3=B, N-U3-9, N-U3-10, U3 NFR M4, M5
- [x] `.github/workflows/ci.yml`에 단계를 추가한다: `capture.py --selftest`(줄인 묶음 설치와 `import` 확인), 인라인 의존성에서 뽑은 목록에 `pip-audit`. `uv export --script`가 되면 그것으로, 안 되면 `tests/test_versions.py`의 파서로 목록을 만든다. CI에서 네이버를 호출하지 않는다.
- [x] `tests/test_versions.py`를 확장한다: `capture.py`의 인라인 21개가 모두 `==`인지, `tests/requirements.txt`와 겹치는 패키지(`numpy`, `pillow`)의 버전이 같은지, `exclude-dependencies`가 들어 있는지.

### 단계 9. 문서
- [x] `CLAUDE.md`: 실행 명령(`uv run --env-file .env src/capture.py --cells ...`, `--replan`, `--selftest`), 현재 상태, 다음 할 일.
- [x] `aidlc-docs/construction/u3-street-view-capture/code/code-summary.md`: 만든 파일, 공개 함수, 설계 대비 차이(마크다운만).

### 단계 10. 생성 후 점검 (본 실행은 Build and Test에서)
- [x] 모든 Python 파일이 컴파일되는지 확인한다. 테스트가 수집되는지 확인한다.
- [x] 코드와 문서에 인증키나 키처럼 보이는 값이 없는지 검색한다(U1 때 테스트 상수에 키가 들어간 일이 있었다).
- [x] 이 계획과 만든 파일 목록을 대조해 빠진 것과 중복 파일이 없는지 확인한다.
- 실제 네이버 호출, 첫 칸의 파노라마와 크롭 생성, 저장량 측정, 크롭을 눈으로 확인하는 일은 Build and Test에서 한다.

## 범위 요약
- **새 파일**: `src/projection.py`, `src/panorama_source.py`, `src/capture.py`, `tests/test_projection.py`, `tests/test_capture.py`, 배치 확인 문서 `layout-notes.md`, 코드 요약 문서.
- **수정 파일**: `src/db.py`, `src/common.py`, `config.toml`, `tests/generators.py`, `tests/test_db.py`, `tests/test_common.py`, `tests/test_versions.py`, `tests/requirements.txt`, `.github/workflows/ci.yml`, `CLAUDE.md`.
- **총 10단계**. 단계 1은 사전 실험이고, 막히면 멈춰서 알린다.
