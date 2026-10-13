# U5 디테일 — Tech Stack Decisions

| 항목 | 결정 | 이유 |
|---|---|---|
| 언어·실행 | Python 3.13+(`uv run`, PEP 723 인라인 고정)와 Luau(`studio/Builder.luau`) | U1~U4와 같다 |
| 기하 | `shapely==2.2.0`(다중 박스 절단 `split`, 최소 직사각형, 가림 판정, 교차점·거리), `h3==4.5.0`(칸 소유) | 이미 고정된 의존성, 새 라이브러리 없음(Q5=A) |
| 세부 판단 저장 | SQLite 표 `details`(`db.py`, `db.TABLES` 밖), 내보내기 `details/<칸ID>.json` v1 | U4 `estimates`·`overrides`와 같은 패턴, S1 재수집이 못 건드림 |
| 변화의 출처 | `zlib.crc32` 해시(이름, 용도) | 표준 라이브러리, 결정적, 테스트 가능 |
| 간판 글자 | `SurfaceGui` + `TextLabel`(`SourceSansBold`, 한글은 Noto Sans CJK 대체 글꼴), 글자는 `SIGN_TEXT`를 거쳐 그대로 | S-10에서 확인, 디코더 없음(Q6=A) |
| 부품 | anchored 기본 `Part`(Block·Wedge·CornerWedge·Cylinder·Ball)와 내장 재질 45종; `Texture`·`Decal`·`MaterialVariant`·`Beam`·Union·MeshPart·외부 모델 없음 | 업로드·심사·드로우콜을 피한다(BR-14.10), 비용 예측 가능 |
| 창 | 불투명 `SmoothPlastic` + 반사율 0.25(S-9 결과에 따라 불투명 `Glass`로 바꿀 수 있음) | 텍스처 없이 결정적 |
| 조명 | `LightingStyle = Realistic`(사람이 속성 창에서), `DepthOfField` 삭제 | 스크립트로 못 바꾼다 |
| 덩어리 | `chunk_size` 80 / 15 KB → 측정 뒤 250 / 40 KB | U2-NFR-P2 1초 안에서 호출 수를 줄인다 |
| 테스트 | `pytest==9.1.1` + `hypothesis==6.169.0`, 생성기는 `tests/generators.py`, CI는 그대로(Luau는 Studio에서) | U1 결정 승계 |
| Studio 연동 | 내장 MCP `execute_luau`, `screen_capture`, `search_game_tree`, `inspect_instance`, `user_keyboard_input`(부재 시 저장), `rbx-perf-profiling` 스킬 | 이미 쓰는 도구 |
| 안 쓰는 것 | `generate_texture`·`generate_material`·`generate_mesh`·`generate_procedural_model`·`insert_asset`·`upload_image`, Open Cloud 자산 API, `luau-analyze` | 외부 자산 0 원칙, 새 도구 없음(Q4=A) |
