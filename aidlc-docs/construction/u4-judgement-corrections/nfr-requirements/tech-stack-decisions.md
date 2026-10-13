# U4 판단·보정 — Tech Stack Decisions

U1~U3의 선택(Python, `uv run`, `h3`, `shapely`, `pillow`, `sqlite3`, 표준 `logging`, `config.toml`, `pytest` + `Hypothesis`, GitHub Actions)은 그대로 쓴다. 아래는 U4에서 추가하거나 정한 것이다. 새로 들어오는 의존성은 없다.

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어 | Python(3.11 이상). Studio 쪽은 U2의 `Builder.luau`에 색과 속성 처리만 더한다 | 기능 설계 BR-9 |
| `estimate.py` 의존성 | `pillow==12.3.0`, `h3==4.5.0`, `shapely==2.2.0`(`capture.py`, `build_luau.py`와 같은 고정). `projection.py`(numpy)는 가져오지 않는다 | N-U4-1. 묶음 이미지와 쌍 합성(`pillow`), 박스 크기와 stud 변환을 위한 `layout.py`·`geo.py`(`h3`, `shapely`) |
| `overrides.py` 의존성 | 표준 라이브러리와 `common`, `db`만. 인라인 의존성 없음 | 보정은 DB와 JSON 파일뿐이다 |
| 순수 모듈 | 입출력 없는 Python 모듈에 최종값 합치기, 상태 분류, 검증, 내보내기 형식, 비교 묶음 계획, 카메라 값(시야각 변환, 방위)을 둔다(파일 이름은 코드 생성에서). `db.py`는 DB 읽기·쓰기를 맡고 `effective_building`은 이 순수 모듈의 함수를 쓴다 | N-U4-2, 속성 P4-1~P4-16 |
| 데이터 저장 | `estimates`, `overrides` 테이블(`sqlite3`, 매개변수 바인딩, 트랜잭션) + `overrides/<칸ID>.json` 내보내기(표준 `json`, 키 정렬, 임시 파일 + `os.replace`) | 기능 설계 BR-8, NFR-6 |
| 이미지 | `pillow`로 묶음 이미지(타일 512×384, JPEG 품질 85)와 비교 쌍(4:3 가운데 자르기, 1280×480)을 만든다. `Image.MAX_IMAGE_PIXELS`를 5,000만으로 명시한다 | 시험: 묶음 122개 1.8초, 쌍 합성 22 ms. N-U4-7 |
| Studio 연결 | Studio 내장 MCP 서버. 쓰는 도구: `screen_capture`(`camera_position`, `look_at_position`을 항상 줌), `execute_luau`(편집 모드, 시야각 설정과 카메라 읽기·되돌리기), `search_game_tree`, `inspect_instance`(속성 확인) | A-1(내장 서버 사용). 시험으로 캡처, 시야각 반영, 캡처 파일 저장을 확인했다 |
| Studio 시야각 | 세로 83.58°(가로 100°, 4:3)로 한 번 정하고 쌍마다 `screen_capture` 한 번. 더 좁은 크롭은 가운데를 잘라 맞춘다 | N-U4-4 |
| 사진 판단 | 이 세션의 내가 묶음 이미지를 직접 보고 한다. 이미지 판독 코드, 외부 AI 호출, 하위 에이전트를 쓰지 않는다 | Q1=A, C4 설계 |
| 비교 쌍 표시 | 건물마다 파일 한 장(1280×480)을 `captures/<칸ID>/review/`에 만들고 이 앱의 파일 창으로 연다. 묶음 이미지와 외부 페이지는 쓰지 않는다 | Q2=A, NFR-4 |
| 테스트 | 기존 `pytest` + `Hypothesis`. 속성 P4-1~P4-16, 이미지는 예시 기반. Luau는 CI에서 돌리지 않는다 | N-U4-13 |
| CI | 변경 없음(`pytest`, `pip-audit`, `capture.py --selftest`). `tests/test_versions.py`가 `estimate.py`의 고정도 자동으로 점검한다 | N-U4-15 |
| 설정 | `config.toml`에 `floor_height_min_m`, `floor_height_max_m`, `review_batch_size`, `sheet_tile_w`, `sheet_tile_h`, `sheet_jpeg_quality`, 벽 색표, `blind_broken` 추가. 범위 검증은 `common.py` | N-U4-12 |
| 커밋 | 판단 122개를 다 기록했을 때 한 번, 그 뒤 비교 3묶음마다 내가 제안하고 사용자가 허락하면 커밋·푸시 | Q3=A |

## 쓰지 않기로 한 것
- 얼굴·번호판 자동 가림이나 이미지 분석 라이브러리(`opencv`, 딥러닝 모델)와 외부 AI 호출. 판단은 사진을 내가 직접 본다.
- 하위 에이전트 병렬 판단(Q1=A).
- 묶음 이미지(쌍 6개를 한 장에)와 외부 페이지·Artifact로 비교 쌍을 보여 주는 방식(Q2=A, NFR-4).
- `luau-analyze`와 CI의 Luau 검사(U2 결정 유지).
- 판단 결과의 병렬 저장소나 별도 데이터베이스. `estimates`는 기존 SQLite 한 곳이다.

## 알려진 위험
- Studio와 내장 MCP 서버는 Roblox가 올리는 버전에 따라 바뀔 수 있다. 캡처 시험은 편집 모드에서 한 번 했고 여러 장을 이어서 찍는 속도는 재지 않았다(Build and Test에서 잰다).
- 인자 없는 `screen_capture`는 다른 시점을 찍고 `CurrentCamera`를 바꿨다. 항상 인자를 주고 시작 전 카메라 값을 되돌린다.
- Studio 창이 4:3보다 좁거나 뒤에 있을 때의 캡처는 시험하지 못했다. 처음 한 묶음에서 확인한다.
- 박스와 사진은 위치 오차(NFR-2)와 단순화 때문에 겹치지 않는다. 비교는 높이·너비·위치를 눈으로 대조하는 용도다.
- 눈가림은 약속이다. 판단 중에 DB를 열면 깨지고, 시험에서 이미 깨진 건물 하나(`gis:11081057`)는 통계에서 뺀다.
