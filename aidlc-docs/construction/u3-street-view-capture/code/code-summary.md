# U3 거리뷰 캡처 — Code Summary

생성 위치는 저장소 루트다(코드는 `aidlc-docs/`에 없다). 설계 기준은 `functional-design/`, `nfr-requirements/`, 계획서는 `construction/plans/u3-street-view-capture-code-generation-plan.md`. 큐브 맵 배치 실험 결과는 `layout-notes.md`.

## 만든 파일

| 파일 | 내용 |
|---|---|
| `src/projection.py` (신규) | 순수 함수. `distance_m`, `bearing_deg`, `yaw_deg`, `building_extent_deg`, `nearest_wall_m`, `building_height_m`, `crop_params`, `split_faces`, `render_crop`. `numpy`와 `pillow`만 쓴다 |
| `src/panorama_source.py` (신규) | 어댑터. `PanoramaSource`(`find_nearby`, `get_metadata`, `download_strip`), `classify`, 오류 4종(`BlockedError`, `TransientError`, `SourceError`, `SourceUnavailable`), `Candidate`, `PanoMeta`. 네이버와 말하는 유일한 곳 |
| `src/capture.py` (신규) | C3. `safe_name`, `pano_file`, `crop_file`, `select_panoramas`, `view_params`, `Capture`(`run_cell`), `parse_args`, `main`. `--cells`, `--replan`, `--selftest` |
| `tests/test_projection.py` (신규) | P3-1, P3-2, P3-4, P3-5 (16개) |
| `tests/test_capture.py` (신규) | P3-3, P3-6, P3-7, P3-8, 실패 규칙, 어댑터의 오류 분류·재시도·간격·응답 검증 (33개) |
| `aidlc-docs/construction/u3-street-view-capture/code/layout-notes.md` (신규) | 면 순서, 위·아래 면 방향, 정면 방향 규칙, 크롭 확인, 라이브러리 동작 |

## 고친 파일

| 파일 | 바뀐 점 |
|---|---|
| `src/db.py` | `captures`, `building_views` 테이블과 `upsert_captures`, `upsert_building_views`, `all_captures`, `views_for_cell`, `delete_views_for_cell`, `orphan_views`. U1 테이블과 함수는 그대로 |
| `src/common.py`, `config.toml` | U3 설정 15개(`captures_dir`, `pano_*`, `max_new_panos`, `crop_*`, `fov_*`, `pitch_max_deg`, `camera_height_m`, `floor_height_m`, `default_height_m`)와 범위 검증 |
| `tests/generators.py` | 위치, 방위각, 후보 목록 생성기 |
| `tests/test_db.py`, `tests/test_common.py`, `tests/test_versions.py` | 새 테이블 테스트 3개, 새 설정 검증, `capture.py` 고정 일치 검사 2개 |
| `tests/requirements.txt` | `numpy==2.5.4`, `pillow==12.3.0` |
| `.github/workflows/ci.yml` | `uv export --script`로 해석 목록 만들기, 그 목록의 `pip-audit`, `capture.py --selftest` |
| `CLAUDE.md` | 실행 명령, 현재 상태, 다음 할 일 |

## 테스트

전체 152개(U1 93개 + 59개). 시드 1, 7, 42, 2026, 99999에서 모두 통과했다(Build and Test에서 위쪽 각도 규칙을 바꾸며 4개를 더했다).

| 속성 | 파일 |
|---|---|
| P3-1, P3-2, P3-4, P3-5 | `tests/test_projection.py` |
| P3-3, P3-6, P3-7, P3-8 | `tests/test_capture.py` |
| `building_views` 교체, 다시 계획 때 U1 표와 `overrides` 유지, 고아 보고 | `tests/test_db.py` |

P3-5는 면마다 색이 다른 합성 큐브 맵으로 옆 4면과 위·아래 면의 색을 확인하고, 면 안의 기울기 이미지로 위·아래 면의 방향 규칙(`layout-notes.md`의 값)을 고정한다.
테스트가 실제로 잡는지 확인하려고 규칙 6곳을 일부러 깨뜨려 봤다(상한 검사, 차단 뒤 계속, 가까운 순 정렬, 방위각 간격, 크롭 실패 기록, `no_photo` 행). 모두 실패로 잡혔고 코드는 원래대로 되돌렸다.

## 설계 대비 차이와 결정

1. **정면 방향(BR-4.1).** 설계는 "heading이 앞면의 방향"이라고 가정했다. 실험에서 ID 조회의 heading은 앞면 방향에서 180° 어긋나 있었다(파노라마 3장). 어댑터가 180°를 더해 `heading_deg`로 돌려주고, 이 보정을 확인한 3D 파노라마(ID 조회 `panorama_type` 15)만 쓴다. 그 밖은 추측하지 않고 쓸 수 없는 후보로 건너뛴다. 몇 장이 건너뛰어지는지는 Build and Test에서 센다.
2. **`pyexiv2` 빈 모듈.** `ImageData` 이름이 있는 스텁이다(`exif.py`가 타입 표기에 쓴다).
3. **`download_faces` 대신 `download_strip`.** 저장 파일이 한 줄 이미지(`zoom1.jpg`)라서 어댑터는 그 한 줄 이미지를 검증해 돌려주고, 6면으로 나누는 일은 `projection.split_faces`가 한다.
4. **의존성 22개, Python 3.13 이상.** 설계는 21개였다. `captures.cell_id`와 폴더 이름을 구하려면 `h3`가 필요해서 `h3==4.5.0`을 더했다. `geo.py`를 가져오면 `shapely`가 따라오므로 가져오지 않는다(`projection.py`도 자체 상수를 쓴다). `requires-python`은 `>=3.13`이다: `numpy` 2.5.4가 3.12 이상을 요구하고, 3.12는 `typing-extensions`가 고정 없이 따라온다. `uv export --script`가 22개 모두 같은 버전으로 해석됨을 확인했고, CI가 이 일치를 매번 검사한다(`tests/test_versions.py`).
5. **라이브러리가 시간 제한도 상태 코드 검사도 하지 않는다.** 어댑터가 `requests.Session`을 만들어 시간 제한 30초와 `raise_for_status`를 건다. 타일 내려받기(`aiohttp`)는 세션을 받지 않아 라이브러리 기본 시간 제한을 따른다(`ponytail:` 주석으로 한계를 적었다).
6. **403/429는 재시도 대기 뒤에도 계속될 때만 차단.** BR-5.2 그대로다(계획서의 "403, 429는 BlockedError"를 재시도 뒤로 풀어 쓴 것). 응답 형식 이상은 재시도 없이 차단으로 본다.
7. **크롭 이름과 안전 이름.** 이름이 바뀐 경우(콜론 밖의 문자, 빈 이름, 점으로 시작)에는 원래 이름의 해시 8자리를 붙여 서로 다른 ID가 같은 이름이 되지 않게 했다. 콜론만 밑줄로 바뀌는 건물 ID(`gis:123` → `gis_123`)에는 해시가 붙지 않는다(BR-4.4).
8. **재실행 상태.** `planned`와 `failed`인 짝은 다음 실행에서 이어서 처리한다. `cropped`인데 파일이 없거나 값(yaw, 시야각, 위쪽 각도)이 바뀌었으면 다시 만든다(BR-4.5, 런북 R-7). 파노라마 내려받기 실패는 그 실행 안에서는 다시 시도하지 않고 짝은 `planned`로 남긴다.
9. **상한은 내려받기 시도 횟수 기준.** 실패한 시도도 센다(네이버 호출이기 때문). 상한에 닿으면 실행 전체를 멈춘다. 계획 단계(후보 조회)는 상한과 무관하다.
10. **메타데이터 확인 결과는 실행 안에서만 재사용.** 고른 파노라마의 행만 `captures`에 `found`로 저장한다. 쓸 수 없다고 한 파노라마는 다음 실행에서 다시 조회한다.
11. **`tests/generators.py`의 후보 목록 생성기**는 `Candidate`가 생긴 뒤에 추가했다(계획 단계 4의 항목 중 일부를 7 직전에 한 셈).
12. **크롭 규칙 변경(Build and Test, 사용자 요청 2026-10-13).** BR-4.3이 위쪽 각도를 중심점 거리로 계산해서 첫 칸 크롭의 32%가 지붕을 놓쳤다. `projection.nearest_wall_m`(가장 가까운 벽까지 거리)을 더하고 `crop_params(extent, wall_m, height, cfg)`가 지붕과 지면선이 세로 시야에 들어오게 위쪽 각도와 시야각을 정한다. `capture.view_params`가 벽 거리를 계산해 넘긴다. 저장하는 `distance_m`은 그대로 중심점 거리다(U4가 읽는다). 설계 문서의 BR-4.3과 P3-4를 고쳤고, 효과는 `build-and-test-summary.md`에 있다.

## 알려진 한계

- 촬영일 시간대: 네이버가 준 값 그대로 저장한다(시간대 표시 없음). 설계 문서의 "UTC"는 확인하지 못했다.
- 가까운 큰 건물은 각도 범위가 시야각 상한 100°를 넘어 건물 전체가 한 장에 안 들어온다(BR-4.2 그대로). 방위각이 다른 파노라마를 최대 3장 쓰는 설계가 보완한다.
- 후보 조회는 건물마다 한 번이라 호출이 많다(칸당 건물 약 120개 → 조회 120회 + 메타데이터 + 내려받기). 호출 간격 1초 때문에 첫 칸은 계획만 몇 분 걸린다.
- 쓸 수 없다고 건너뛴 후보 수는 `panos_skipped`로 센다(Build and Test에서 추가). 이유(최신 아님, 3D 아님 등)별로는 나누지 않는다.

## 아직 안 한 것 (Build and Test)

- 실제 네이버로 첫 칸 `8930e0af13bffff`를 돌려 파노라마와 크롭 만들기. 건너뛰어진 후보 비율, 사진 없는 건물 수, 저장량(MB)을 잰다.
- 크롭 몇 장을 눈으로 확인한다(건물이 가운데에 오는지, 가림이 얼마나 심한지).
- 호출 간격 1초가 충분한지 본다. 차단 신호가 나오면 멈추고 사용자와 방법을 다시 정한다.
- CI를 GitHub에서 실제로 돌려 `uv export --script`, `pip-audit`, `--selftest`를 확인한다(푸시가 필요하다).
