# U2 Studio 생성기 — Tech Stack Decisions

U1·U3의 선택(Python, `uv run`, `h3`, `shapely`, `sqlite3`, 표준 `logging`, `config.toml`, `pytest` + `Hypothesis`, GitHub Actions)은 그대로 쓴다. 아래는 U2에서 추가하거나 정한 것이다. 새로 들어오는 의존성은 없다.

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어 | 계산과 파일 쓰기는 Python(3.11 이상), Studio 쪽은 Luau | 기능 설계 BR-7.5(계산은 Python, Luau는 부품만 만든다) |
| Python 의존성 | `h3==4.5.0`, `shapely==2.2.0`(`register.py`와 같은 고정) | 칸 경계와 칸 소유 판정(`h3`), 최소 면적 회전 직사각형(`shapely`). 새 의존성 없음 |
| Studio 연결 | Studio 내장 MCP 서버. 쓰는 도구: `execute_luau`(편집 모드), `search_game_tree`, `inspect_instance`, `screen_capture`, 걸어 보기 확인용으로 `start_stop_play`와 `character_navigation` | A-1(내장 서버 사용). 시험으로 소스 쓰기, `require`, 덩어리 실행을 확인했다(Studio 0.742) |
| Studio 모듈 | `studio/Builder.luau`(git 포함) → Claude가 `execute_luau`로 `ServerStorage/MapBuilder`의 `ModuleScript.Source`에 넣는다. 함수: `begin`, `add`, `finish`, `verify` | D-3. 시험에서 `Source` 쓰기와 바로 `require`가 됐다. 덩어리 파일에 Builder를 같이 넣는 대안은 쓰지 않는다 |
| 데이터 전달 | 덩어리마다 Luau 코드 파일(`data/build/<칸ID>/chunk-NNN.luau`)과 `manifest.json`. 덩어리는 항목 50개, 호출당 수 KB | 시험한 크기(3.7 KB)에서 8 ms. 10 KB를 넘으면 경고 |
| 순수 모듈 | 입출력 없는 Python 모듈에 좌표 변환, 박스 맞춤, 도로·인도 조각, 땅, 덩어리를 둔다(파일 이름은 코드 생성에서) | N-U2-1, 속성 P2-1~P2-9 |
| 확인 | Studio에서 `Builder.verify`(폴더별 부품 수, 건너뛴 수, 부품 몇 개의 위치·크기·회전)와 S-1~S-6 | Q4=A, 시험 결과 |
| 테스트 | 기존 `pytest` + `Hypothesis`. 덩어리와 manifest는 예시 기반. Luau는 CI에서 돌리지 않는다 | Q4=A |
| CI | 변경 없음(`pytest`, `pip-audit`, `capture.py --selftest`). `tests/test_versions.py`가 `build_luau.py`의 고정도 자동으로 점검한다 | N-U2-10 |
| 설정 | `config.toml`에 U2 항목 추가(`origin_*`, `studs_per_m`, `poor_fit_ratio`, `ground_margin_m`, `sidewalk_width_m`, 도로 폭 표, `chunk_size`, `spawn_*`) | N-U2-9 |
| Studio 장소 설정 | 첫 생성 때 Claude가 한 번: `StreamingEnabled = false`, `Baseplate` 투명·충돌 끔, 기본 `SpawnLocation` 비활성 | Q2=A, Q7=B |
| 백업 | 첫 생성 전 사용자의 `.rbxl` 복사본 한 번, 이후 Version History, U5부터 큰 변경 전 복사본 | Q3=A |

## 쓰지 않기로 한 것
- `luau-analyze`, `selene` 같은 Luau 검사 도구와 그 CI 단계(Q4=A). U5에서 코드가 커지면 다시 정한다.
- `Rojo`, `wally` 같은 Roblox 외부 도구와 `.rbxl`을 git으로 다루는 방식. Studio 쪽은 MCP로만 다룬다.
- 지형(Terrain)과 `EditableMesh`(Q3=A에서 Part로 정했다).
- `StreamingEnabled` 켜기(Q2=A). U5 이후 다시 정한다.
- 이어서 만들기(재개) 기능과 Studio 쪽 영구 상태 저장. 칸 하나를 처음부터 다시 만드는 것이 8 ms라 필요 없다(N-U2-7).

## 알려진 위험
- Studio와 내장 MCP 서버는 Roblox가 올리는 버전에 따라 바뀔 수 있다. 시험은 Studio 0.742에서 했다. 바뀌면 `begin`, `add`, `finish`, `verify`와 S-1~S-6으로 다시 확인한다.
- `Source`를 쓰는 방식은 `execute_luau`의 권한에 기대고 있다. 안 되면 Builder 함수를 덩어리 파일에 같이 넣는 방식으로 되돌릴 수 있다(코드는 같다).
- Luau 코드는 CI에서 검사하지 않는다. 오류는 Studio에서 실행할 때 나타나고, `BuildComplete = false`와 `verify`가 미완성을 알려 준다.
- 호출 한 번의 최대 크기는 시험하지 못했다(시험한 것은 3.7 KB). 첫 칸은 호출당 수 KB라 필요 없지만, 큰 칸을 만들 때는 `chunk_size`를 줄이는 방향으로 조정한다.
