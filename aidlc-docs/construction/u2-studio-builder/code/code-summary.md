# U2 Studio 생성기 — Code Summary

생성 위치는 저장소 루트다(코드는 `aidlc-docs/`에 없다). 설계 기준은 `functional-design/`, `nfr-requirements/`, 계획서는 `construction/plans/u2-studio-builder-code-generation-plan.md`.

## 만든 파일

| 파일 | 내용 |
|---|---|
| `src/layout.py` (신규) | 순수 계산. `Frame`(원점과 스케일), `to_meters`, `to_studs`, `from_studs`, `fmt`, `Item`, `outline_to_box`, `building_item`, `road_width_m`, `road_items`, `sidewalk_sides`, `sidewalk_items`, `ground_item`, `spawn_item`, `order_items`, `chunk_items`. `h3`, `shapely`, `common`, `geo`만 쓴다 |
| `src/build_luau.py` (신규) | C6. `luau_string`, `luau_number`, `item_literal`, `render_chunk`, `plan_cell`(DB와 파일 없이 덩어리와 manifest 글자를 만든다), `write_plan`, `build_cell`, `parse_args`, `main`. `--cells`, `--selftest` |
| `studio/Builder.luau` (신규) | Studio에 넣는 모듈. `begin`, `add`, `finish`, `verify`. 계산하지 않고 `loadstring`을 쓰지 않으며 `Auto/<칸ID>`만 지운다 |
| `tests/test_layout.py` (신규) | P2-1~P2-9 속성 테스트와 예시 (48개) |
| `tests/test_build_luau.py` (신규) | Luau 글자와 코드 주입 방지(SEC2), 계획, 항목 순서, 같은 입력은 같은 글자(P2-8), 파일, DB, 실행 기록 (43개) |

## 고친 파일

| 파일 | 바뀐 점 |
|---|---|
| `src/common.py`, `config.toml` | U2 설정(원점, 스케일, `poor_fit_ratio`, 땅 여백, 인도 폭, 도로 폭 표, `chunk_size`, 스폰 점)과 검증. `building_height_m`을 여기로 옮겼다 |
| `src/projection.py` | `building_height_m`을 `common`에서 다시 내보낸다(U3 동작 그대로). `build_luau.py`가 `numpy`, `pillow` 없이 쓰게 하려는 것 |
| `tests/generators.py` | `road_features` 생성기(꼭짓점 2~8개, 종류와 태그) |
| `tests/test_common.py`, `tests/test_versions.py` | 새 설정 검증, `build_luau.py` 고정 일치, `Builder.luau`가 `loadstring` 등을 쓰지 않는지 검사 |
| `CLAUDE.md` | 실행 명령, 현재 상태, 다음 할 일 |

## 테스트

속성 P2-1~P2-9를 속성 기반 테스트로 만들었다(파일은 `test_layout.py`, P2-8의 파일 단위는 `test_build_luau.py`). 규칙을 일부러 깨뜨려 테스트가 잡는지 확인했다: `layout` 5곳(인도 좌우, 칸 소유 규칙, 건물 중심 높이, 이음새 여유, 북쪽 부호), `build_luau` 5곳(문자열 검사, 항목 정렬, 오래된 덩어리 삭제, `begin`, 칸 확인), `Builder.luau` 2곳(`loadstring`, 두 번째 `Destroy`). 모두 실패로 잡혔고 코드는 되돌렸다. 정렬 변이는 처음엔 살아남아서 항목 순서 테스트를 더했다.

## Studio에서 실행하는 순서 (Claude용)

1. **처음 한 번만, 사용자의 `.rbxl` 복사본을 확인한 뒤**: 장소 설정을 바꾼다(`StreamingEnabled = false`, `Baseplate`를 `Transparency = 1`과 `CanCollide = false`로, 기본 `SpawnLocation`을 `Enabled = false`로). 지우지 않는다.
2. `ServerStorage`에 `ModuleScript` `MapBuilder`를 만들고 `Source`에 `studio/Builder.luau`를 쓴다(`execute_luau`, 편집 모드). 소스를 바꾸면 같은 방법으로 다시 쓴다.
3. `uv run src/build_luau.py --cells <칸ID>`로 `data/build/<칸ID>/`를 만든다. 콘솔의 경고(안 맞는 건물, 스폰 미설정 등)를 읽는다.
4. `chunk-001.luau`부터 순서대로 파일 내용을 그대로 `execute_luau`의 코드로 실행한다. 마지막 덩어리가 `Builder.finish`의 결과(만든 수, 건너뛴 수, 폴더별 수)를 돌려준다.
5. `Builder.verify("<칸ID>", <manifest의 counts>, {"<부품 이름>", ...})`를 실행해 `ok`와 읽어 온 위치·크기·회전축을 덩어리 파일의 값과 비교한다. `screen_capture`로 눈으로 보고, 스폰에서 걸어 본다.
6. 스폰 점이 정해지면 `config.toml`에 `spawn_lat`, `spawn_lon`, `spawn_yaw_deg`를 적고 3번부터 다시 한다(재생성은 8 ms 수준).

## 설계 대비 차이와 결정

1. **덩어리 형식이 설계 문서보다 작다.** 항목 키를 짧게(`k`, `n`, `x y z`, `w h d`, `r`, `s e q f`) 하고, 재질·색 표(`LOOKS`)는 덩어리마다 한 번만 보내고, 건물의 `BuildingId`와 `CellId`는 보내지 않고 Builder가 이름과 칸에서 채운다. 이렇게 해서 항목 50개 덩어리가 5.4~6.6 KB로 10 KB 경고선 아래다(긴 키를 쓰면 항목당 약 250바이트로 추정해 50개에 약 12 KB, 실측은 아니다).
2. **만든 수와 건너뛴 수는 Studio 폴더의 속성에 쌓는다**(`Created`, `SkippedManual`). `execute_luau` 호출이 서로 변수를 공유하지 않는다고 보고 정한 것이라, 마지막 덩어리의 `finish`가 모든 덩어리의 합계를 돌려준다(시험에서 덩어리 3개가 합계 19, 건너뜀 1로 이어졌다).
3. **`building_height_m`을 `common.py`로 옮겼다**(계획 단계 1). `projection.py`가 같은 이름으로 다시 내보내서 U3의 `capture.py`와 테스트는 그대로 쓴다.
4. **삼각형 외곽선은 최소 면적 박스가 하나로 정해지지 않는다**(세 변 중 어느 쪽에 맞춰도 박스 넓이가 같다). 같은 입력이면 항상 같은 하나가 나온다. 설계 문서(BR-2.2)에 이 경우를 적었다. 마름모 같은 대칭 사각형도 같다. 속성 테스트가 알려 준 것이다.
5. **스폰 미설정 경고.** `spawn_lat`이 없으면 실행할 때마다 "no spawn point configured" 경고를 낸다. 스폰 점이 정해질 때까지 계속 나온다.
6. **`spawn_item`의 인자.** 계획은 `spawn_item(frame, cfg, ...)`였고 만든 것은 `spawn_item(cell_id, frame, cfg, road_pieces)`다. 칸 ID와 도로 조각 목록이 있어야 칸 소유와 "도로 위" 확인을 할 수 있다.
7. **`manifest.json`의 경고에는 건너뛴 ID가 글자 그대로 들어간다.** manifest는 데이터(JSON)이고 코드가 아니다. 코드(`.luau`)에는 허용 문자만 들어간다는 것을 테스트가 보장한다.
8. **Luau는 CI에서 검사하지 않는다**(NFR Q4=A). 대신 `tests/test_versions.py`가 `Builder.luau`에 `loadstring`, `HttpService` 등이 없고 `:Destroy()`가 하나뿐인지 검사한다.
9. **Studio 시험용 `Builder` 복사본은 주석을 뺀 것이다.** 시험은 `MCP_Test` 안의 `ModuleScript`로 했고(`ServerStorage`는 건드리지 않았다), 코드는 `studio/Builder.luau`와 같다.

## 알려진 한계

- 도로 이음새는 조각이 겹치고 큰 도로의 인도가 골목 입구를 가로지른다(BR-3.9). 교차로 정리는 U5다.
- 도로 폭은 OSM에 폭 태그가 없어서 종류별 기본값이다. 현실과 다를 수 있다.
- 첫 칸에서 안 맞는 건물 9개(학교 건물 포함)는 박스 하나로 만들어진다. U5에서 수작업(`Manual`)으로 다듬는다.
- `Builder.verify`는 부품 수와 몇 개의 읽어 온 값만 확인한다. 모든 부품의 값을 비교하지는 않는다.
- 호출 한 번의 최대 크기는 시험하지 못했다(시험한 것은 1.2~6.6 KB).

## 아직 안 한 것 (Build and Test)

- 사용자의 `.rbxl` 복사본 확인, 장소 설정 변경(스트리밍 끄기, 기본 물체 끄기), `ServerStorage/MapBuilder` 설치.
- 첫 칸 실제 생성(덩어리 4개)과 `verify`, 화면 캡처로 건물과 도로가 지도에서 맞는 자리에 있는지 확인(NFR-2).
- 스케일 3.6 stud/m 확정(FR-10), 스폰 점 제안과 확정(Q6=B), 걸어 보기와 프레임 측정(평균 60 FPS 이상, 최저 30 FPS 이상).
