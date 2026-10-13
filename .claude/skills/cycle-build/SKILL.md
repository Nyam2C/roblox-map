---
name: cycle-build
description: roblox-map 세션 흐름의 3단계 "구현". 칸 하나를 데이터 수집부터 Studio 생성까지 만들 때, 사용자가 "구현", "이 칸 만들어", "사이클 돌려", "생성", "Studio에 넣어"라고 할 때 쓴다. 칸 추가 절차를 단계별로 실행하고 멈춘 곳에서 이어간다.
---

# 구현 (세션 흐름 3/5)

인지·메모리가 끝난 뒤. 단계가 끝날 때마다 메모리의 "진행"에 한 줄 덧붙인다. 이미 끝난 단계(인지에서 확인)는 건너뛴다. 모든 명령은 저장소 루트에서. 주의점은 `aidlc-docs/lessons.md`.

## 단계

### 1. 수집
```bash
uv run --env-file .env src/cells.py --cells <칸>
uv run --env-file .env src/register.py --cells <칸>
```
확인: `done: 1 ok`, 건물 수.

### 2. 위성 모자이크와 나무
```bash
uv run --env-file .env --with h3 --with pillow python .claude/skills/cycle-build/scripts/satellite_cell.py <칸>
uv run src/trees.py --cells <칸>
```

### 3. 거리뷰 (1급 칸만, 등급이 생기기 전까지는 모든 칸)
`uv run src/capture.py --cells <칸>`을 `cell done`이 나올 때까지 반복(실행당 새 파노라마 100장 상한). 백그라운드로 돌리고 끝나면 확인. 403/429·형식 이상으로 `stopped`면 **우회하지 말고 멈추고** 사용자에게 알린다.

### 4. 판단 (눈가림)
1. `uv run src/estimate.py pending --cells <칸> --limit 200` 출력의 JSON 줄을 모아 70개 안팎으로 나눈다(200 넘으면 기록 뒤 다시 pending).
2. 묶음마다 서브에이전트 하나: `judge-prompt.md`(이 폴더)를 지침으로, 목록 파일과 출력 경로를 준다. 서브에이전트는 목록과 묶음 이미지만 읽는다(DB·overrides·details 금지).
3. 출력의 `judgements`와 `details`를 나눠 `uv run src/estimate.py record --file <j.json>`, `uv run src/details.py record --file <d.json>`.
4. 메모에 개인 정보(사람, 번호판, 실제 상호)나 술·담배·도박 어휘가 없는지 훑는다.
5. `uv run src/estimate.py report --cells <칸>` → **확신 high인데 대장과 다른 건물은 묶음 이미지를 직접 다시 본다.** 판단이 틀렸으면 `uv run src/overrides.py set --building <id> --field floors_above --value <대장값> --reason "..."`(사유에 개인 정보 금지).

### 5. 간판 (지금은 멈춤 상태)
간판 이미지는 사용자가 멈춰 두었다(2026-10-14). 다시 하라는 말이 없으면 건너뛰고 글자 간판으로 만든다. 다시 할 때는 CLAUDE.md "간판 이미지" 절과 lessons의 검수 항목을 따른다.

### 6. 생성
```bash
uv run src/build_luau.py --cells <칸>
python3 .claude/skills/cycle-build/scripts/chunks_json.py <칸>
```
경고(`warnings`)를 읽는다.

### 7. Studio 반영
1. `get_studio_state` → Edit인지. Play면 멈추고 기다린다.
2. 큰 변경 전이면 사용자에게 `.rbxl` 복사본을 부탁한다.
3. `cd data/build && python3 -m http.server 8765 --bind 127.0.0.1`(백그라운드).
4. `execute_luau`(Edit)로 `studio-build.luau`(이 폴더)의 내용을 `CELLS` 값만 바꿔 실행. `HttpEnabled`는 받는 동안만 켜고 결과의 `http=false`를 확인한다.
5. 서버를 내린다: `pkill -f "http.server 8765"`.
6. Builder를 바꿨다면 먼저 `ServerStorage/MapBuilder`를 Clone 후 원본 Destroy로 교체(require 캐시).

### 8. 규칙을 고칠 때
검증에서 여러 건물에 공통인 문제가 나오면 `src/details_rules.py`·`src/layout_details.py`(또는 해당 모듈)를 고치고 테스트를 고치거나 더한 뒤:
```bash
uv run --python 3.14 --with-requirements tests/requirements.txt pytest tests/ -q
```
통과하면 이미 만든 칸들도 6~7단계로 다시 만든다(결정적 생성이라 그대로 반영된다). 한 건물만의 문제는 `overrides.py`나 수작업(Manual).

그다음 `cycle-verify`로 간다.
