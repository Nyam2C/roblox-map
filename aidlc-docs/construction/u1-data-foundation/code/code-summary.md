# U1 데이터 기반 — Code Summary

생성 위치는 저장소 루트다(코드는 `aidlc-docs/`에 없다). 설계 기준은 `functional-design/`, `nfr-requirements/`, `nfr-design/`.

## 만든 파일

| 파일 | 내용 |
|---|---|
| `src/geo.py` (신규) | 순수 계산. `centroid`, `assign_cell`, `is_valid_outline`, `outline_from_geojson`, `overlap_ratio`, 정규화(`normalize_height`, `normalize_levels`, `normalize_floors_above`, `normalize_floors_below`), 빌더(`new_osm_building`, `new_gis_building`), `assemble` |
| `src/db.py` (신규) | `connect`, `to_rows`, `replace_cell_rows`, `rows_in_cells`, `all_cell_ids`, `orphans`, `backup`, `record_run` |
| `src/common.py` (신규) | `load_config`, `resolve`, `get_secret`, `mask`, `setup_logging`, `log`, `now_iso`, `http_get_json`, `run`, `run_cli` |
| `src/cells.py` (이동 후 개작) | C1. `fill_cells`, `check_cells`, `parse_args`, `cell_bbox`, `overpass_query`, `parse_osm`, `cells_touched`, `street_rows_for_cell`, `collect_cell`, `main` |
| `src/register.py` (신규) | C2. `parse_vworld_page`, `merge_pages`, `fetch_vworld`, `assemble_cell`, `parse_args`, `main` |
| `config.toml` (신규) | 조정값 |
| `tests/` (신규) | `conftest.py`, `generators.py`, `test_geo.py`, `test_db.py`, `test_common.py`, `test_parse.py`, `test_versions.py`, `fixtures/`(실제 응답을 줄여 저장), `requirements.txt` |
| `.github/workflows/ci.yml` (신규) | 푸시와 PR마다 `pytest`(시드 = 실행 번호)와 `pip-audit` |
| `.gitignore` (수정) | `data/` 추가 |
| `CLAUDE.md` (수정) | 실행·테스트 명령, 현재 상태 |

기존 루트의 `cells.py`는 `git mv`로 `src/cells.py`로 옮겼고 복사본은 남기지 않았다.

## 테스트

속성 P-1~P-10은 모두 속성 기반 테스트로 구현했다. 파일과 대응:

| 속성 | 파일 |
|---|---|
| P-1~P-7 | `tests/test_geo.py` |
| P-8, P-9 | `tests/test_db.py` (P-8은 `test_parse.py`의 end-to-end 시험에서도 확인) |
| P-10 | `tests/test_parse.py` |

예시 기반 테스트는 설계 문서의 조립 예시 4개, 재시도 대기 열, 비밀값 가리기, 응답 샘플 파싱, 설정 검증, 의존성 일치 검사 등이다. 생성기는 `tests/generators.py`에 한 번만 정의했다(PBT-07).

생성 중에 확인용으로 한 번 돌려서 93개가 통과했다(시드 1, 7, 42, 2026, 99999). 본 실행은 Build and Test에서 한다.

## 설계 대비 차이와 결정

- `normalize_vworld_height`는 따로 만들지 않았다. `normalize_height`가 `'18.15'`와 `'12 m'`를 모두 읽는다.
- `register.py`는 `gis_key`를 응답 feature의 `id`(`LT_C_BLDGINFO.<숫자>`)에서 가져온다. V-World가 데이터를 다시 올리면 번호가 바뀔 수 있다. 그러면 건물 ID가 바뀌어 `overrides`가 고아가 되고, `db.orphans`가 알린다.
- 테스트가 발견한 문제 두 가지를 고쳤다: ①`--cells`와 영역 점을 함께 주면 argparse가 점까지 칸 ID로 읽어 일반 오류가 났다. 이제 사용법 오류(종료 코드 2)로 끝난다. ②Hypothesis 생성기의 `.filter()`가 시드에 따라 건강 검사에 걸렸다. 필터를 없앴다(시드 5개로 재확인).
- 도로는 걸치는 모든 칸에 저장한다(`cells_touched`가 25 m 간격으로 표본을 잡는다). 폭은 U2가 정한다.
- 건물 relation은 수집하지 않는다(설계 F-2).
- V-World 응답이 `NOT_FOUND`이면 빈 영역으로 보고 오류로 보지 않는다(실제 응답으로 확인).

## 아직 안 한 것 (Build and Test)
- 실제 Overpass와 V-World로 첫 칸 `8930e0af13bffff`를 수집하고 조립해 건물 수, 층수·높이 비율을 확인한다.
- 겹침 기준 0.5와 버퍼 150 m를 첫 칸 결과로 점검한다.
- CI를 GitHub에서 실제로 돌려 본다(푸시가 필요하다).
- `pip-audit`를 실제로 한 번 돌린다.
