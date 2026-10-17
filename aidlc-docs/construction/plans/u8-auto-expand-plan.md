# U8 부천역까지 자동 확장과 검증 게이트

사용자 목표(2026-10-17): "한개 세션에 계속 에이전트를 호출해서 지금 상황에서 부천역까지 내 개입없이 확장", 그때 검증 장치를 강화한다(도로가 이상함, 도로 위 건물·나무, 건물 외관이 사진과 안 닮음이 계속 나온다). 높이와 차지하는 크기는 문제가 없고, 사진과 닮았는지가 문제다(사용자).

이 문서는 Studio가 있는 Mac의 **메인 세션**이 그대로 따르는 절차서다. 코드는 2026-10-17 클라우드 세션이 만들었고 실제 데이터와 Studio에서는 아직 돌려 보지 않았다(8절).

## 1. 사용자 결정 (2026-10-17)

| 질문 | 답 | 반영 |
|---|---|---|
| 세션 흐름을 "메인 세션 하나 + 칸마다 에이전트"로 | 사용자가 그 세션에 직접 전달 | CLAUDE.md 세션 흐름은 그대로, 이 문서가 자동 확장 모드의 절차 |
| 에이전트 정의를 둘지 | 만든다 | `.claude/agents/cell-*.md` 8개 |
| 외관 채점 보정 표시를 사람이 할지 | 사용자는 안 본다 | 사람 표시 없이 카나리아(바꿔 끼운 쌍, 중복 쌍)로 채점자를 감시, 기준은 기존 칸 기준선으로 |
| 사진에서 잰 벽 색을 생성에 써도 되는지 | 써도 된다 | `walls.json` → `build_luau.py`(색만, 사진을 텍스처로 쓰지 않음) |
| 자동 중 규칙 수정 | 허용 | 테스트와 회귀(G5) 통과가 조건 |
| 걷기 FPS | 3칸마다 | `gate.toml [fps] every_cells = 3` |
| 대표 시설 | 칸마다 4~5곳 상시(같은 날 결정) | cycle-build 0b-4 |

## 2. 구조

메인 세션은 지도 상태(`regions/bucheon-dodang/expansion.json`, `data/gate/<칸>/gate.json`)와 에이전트의 짧은 보고만 본다. 사진과 캡처는 보지 않는다(메인 컨텍스트가 길게 가도록). 칸 일은 모두 에이전트가 한다.

| 에이전트(`.claude/agents/`) | 하는 일 | Studio | 비고 |
|---|---|---|---|
| `cell-prep` | 0 등급, 1 수집, 2 거리뷰 캡처(끝날 때까지 반복), 4 위성·나무·운동장·지붕, 판단 목록 만들기 | 안 씀 | 거리뷰 차단이면 바로 멈추고 보고 |
| `cell-judge` | 눈가림 판단 한 묶음(`judge-prompt.md`) | 안 씀 | 도구 Read·Write만. 묶음마다 하나, 동시에 4개까지 |
| `cell-facility` | 대표 시설 4~5곳 고르기와 스펙(`facility-spec.md`, 웹 사진) | 안 씀 | 칸마다 하나 |
| `cell-build` | 시설 스펙 합치기, 생성, 수작업 설치, 칸 데이터, 미니맵, 이웃 칸, 정리 | 씀 | |
| `cell-verify` | G1(계산·Studio), G2 조각과 답, G3 전수 캡처와 묶음, (차례면) FPS | 씀 | 코드·데이터를 고치지 않는다 |
| `cell-score` | G3 묶음 채점(`lookalike-rubric.md`) | 안 씀 | 도구 Read·Write만, 칸 정보 없이 묶음만 |
| `cell-fix` | 게이트 실패 처리(규칙·판단·벽 색·시설 스펙), 다시 생성, 회귀 | 씀 | 게이트 파일은 못 고친다 |
| `cell-record` | lessons·스킬·audit·CLAUDE.md 현재 상태, 자기 파일만 커밋·푸시 | 안 씀 | |

Studio를 쓰는 에이전트는 한 번에 하나만 돌린다(캡처를 동시에 보내면 다른 카메라가 찍힌다, lessons 2026-10-14). 판단·시설·채점 에이전트는 Studio를 안 쓰니 동시에 돌려도 된다. 서브에이전트가 다시 서브에이전트를 부르는 데 기대지 않는다: 판단과 시설 에이전트는 메인이 직접 부른다.

## 3. 게이트 (기준값은 `gate.toml`, 메인만 고친다)

칸 하나는 `data/gate/<칸>/gate.json`의 `pass`가 true여야 끝난다(`uv run src/gate.py summary --cells <칸> [--need fps]`).

| 게이트 | 무엇 | 명령 | 통과 |
|---|---|---|---|
| G1 배치(계산) | 차도 위 건물(0.3 m² 넘는 동 1개까지, 1 m² 넘는 동 0)·나무 줄기·가로시설, 다른 도로 차도 위 인도·연석·보행로, 길 밖·두 겹 횡단보도, 칸 경계 양쪽 같은 길의 폭 | `gate.py g1 --cells <칸>` (이웃 칸의 도로도 본다, 고가는 높이로 가른다) | 모두 0 |
| G1 배치(Studio) | 실제 부품 중 차도 위 빈 공간(0.28~2.5 m)을 막는 것, `Workspace/Manual` 포함 | `road-clear-check.luau` → `gate.py studio` | 0.3 m² 넘는 것 0 |
| G2 위성 | 3×3 조각마다 없는 길·없어야 할 길·폭·빠진 건물·차도 위 나무·빠진 시설 | `satellite.py compare` → `gate.py tiles` → 검증 에이전트 답 → `gate.py g2` | 큰 차이 0 |
| G3 외관 닮음(1급) | 사진 있는 건물 전부: 6항목(색·마감·창·1층·돌출물·지붕) 0~2점, 같은 건물로 보이는지 | `estimate.py plan` → `lookalike.py plan` → 하나씩 캡처 → `lookalike.py sheets` → `cell-score` → `lookalike.py score` | 실패 건물 비율 ≤ 0.2, 대표 시설 실패 0, 카나리아 통과, 사진 있는 건물의 90% 이상이 묶음에 오름 |
| G4 FPS | 걷기 평균·1초 최저(3칸마다) | 걷기 기록 → `gate.py fps` | 59 / 55 |
| G5 회귀 | 규칙을 고친 뒤 다른 칸이 나빠졌나 | `build_luau.py`로 만든 칸 전부 다시 → `gate.py g1 --cells <전부>` | 실패 수가 고치기 전보다 늘지 않음 |

G3 판정: 건물 하나는 총점 7점 미만(대표 시설은 9점), 색·마감·1층 중 하나가 0점, 또는 같은 건물로 안 보이면 실패. 한 건물의 사진이 여러 장(학교 면)이면 평균. 바꿔 끼운 쌍이 4점을 넘거나 같은 건물이라고 하면, 또는 중복 쌍의 총점이 2점 넘게 다르면 그 채점은 무효(`scorer_invalid`)라 새 `cell-score`로 다시 채점한다(두 번 연속 무효면 멈춤).

허용 목록(`regions/<구역>/cells/<칸>/gate-allow.json`, `{"allow": [{"check", "id", "reason"}]}`): 실제로 맞는데 걸리는 것(예: 실제로 차도 한가운데 있는 교통섬 나무)만, 검증 에이전트가 근거(위성·거리뷰 키)와 함께 제안하면 메인이 넣는다. 일꾼은 이 파일을 못 고친다.

## 4. 실패에서 고치기까지

| 실패 | 고치는 길(`cell-fix`) |
|---|---|
| G1 건물·나무·가로시설·인도 | 규칙(`streets.py`, `layout.py`, `layout_details.py`)과 그 사례를 테스트에 추가, 또는 데이터(`road_lanes_by_name`, `driveways`) |
| G1 Studio의 수작업 | 그 시설의 생성기 스펙(`facilities.json` 등)을 차도에서 뗀다 |
| G2 | 위성에 맞춰 데이터·규칙·수작업 |
| G3 `detail` | 사진과 렌더를 같이 보고 `details.py record`(그 건물만) |
| G3 `color` | `lookalike.py walls --cells <칸> --apply` → walls.json → 다시 생성 |
| G3 `rule` | `uv run src/lookalike.py gaps --min 10`이 칸을 넘어 센다. 같은 종류가 10동을 넘으면 새 규칙(공개 레퍼런스 먼저, 테스트, G5) |
| G3 `facility` | 시설 스펙(정면 방향 `front`, 재질; lessons 사례) |

규칙은 칸마다 한 건까지 고친다(테스트와 G5 통과). 고친 규칙 때문에 manifest가 바뀐 옛 칸은 `expansion.json`의 `stale`에 넣고 큐가 끝날 때(또는 FPS 차례에) Studio에서 다시 만든다.

## 5. 메인 절차

시작: Mac의 Claude Code에서(Studio 열림, 7절 준비 끝)
```
/loop aidlc-docs/construction/plans/u8-auto-expand-plan.md 5절대로 regions/bucheon-dodang/expansion.json의 다음 단계를 진행해. 칸 일은 .claude/agents의 cell-* 에이전트에게 시키고, 너는 사진을 보지 말고 게이트 결과와 보고만 봐.
```

매 반복(상태는 `expansion.json`만 믿는다, 대화가 요약돼도 이어진다):
1. `git pull`, `expansion.json`에서 첫 칸 중 `state`가 `done`·`held`가 아닌 것을 고른다. 없으면 `stale` 칸 다시 만들기, 그다음 끝 보고.
2. 상태에 따라:
   - `queued` → `cell-prep`(칸 ID). 보고의 `capture_stopped`가 있으면 **전체 멈춤**.
   - `prepped` → 판단 목록마다 `cell-judge`(동시에 4개까지, 출력 `data/auto/<칸>/judge-NN.out.json`) → `cell-prep` 기록 모드(그 출력들; cycle-build 4단계 3~5번, 200개 넘는 칸은 새 목록이 나오면 판단을 한 번 더). 2·3급 칸은 판단을 건너뛴다.
   - `judged` → `cell-facility` → 스펙 JSON 경로를 받는다.
   - `specced` → `cell-build`(칸, 스펙 경로).
   - `built` → `cell-verify`(칸, FPS 차례면 `fps`) → 1급이면 `cell-score`(score-list를 묶음 20장 안팎씩 나눠 여러 에이전트에, 못 연 묶음은 새 에이전트에 다시; 2026-10-17 61b에서 69장을 하나에 맡겨 $35 날림) → 메인이 `lookalike.py score`와 `gate.py summary`.
   - `verified`(pass) → `cell-record` → `state = done`, `since_fps` 증가(FPS를 쟀으면 0).
   - 실패 → `rounds < 3`이면 `cell-fix`(gate.json 경로) → `built`로 돌아가 검증부터. 3번째도 실패면 `state = held`, 이유를 적고 알림.
3. 에이전트가 끝날 때마다 `git diff --name-only HEAD`와 그 에이전트의 커밋을 본다: `gate.toml`, `gate-allow.json`, `src/gate.py`, `src/lookalike.py`, `cycle-verify/lookalike-rubric.md`, `road-clear-check.luau`를 일꾼이 바꿨으면 되돌리고(`git checkout HEAD~1 -- <파일>` 후 커밋) 그 칸을 다시 검증한다.
4. `expansion.json`을 고치고 그 파일만 커밋·푸시한다.

**전체 멈춤**(알림 후 반복 중지): 거리뷰 차단(403·429·CAPTCHA, 우회하지 않는다), Studio MCP 연결 3번 실패, 같은 실패 종류가 두 칸 연속(규칙 문제), 채점 무효 두 번 연속, 테스트를 두 번 고쳐도 못 살림, 디스크 5 GB 미만, Roblox 업로드 검수 오류. 자동 중에는 업로드를 하지 않는다(간판·메시는 재사용만).

**알림**: `held`, 전체 멈춤, 3칸마다 한 줄 진행(칸 수, 실패 건물 비율 추세).

## 6. 칸 큐 (`regions/bucheon-dodang/expansion.json`)

부천역(37.4840, 126.7826, 칸 `8930e0af32fffff`)은 가장 가까운 칸 `8930e0ac613ffff`에서 약 1.2 km(칸 5개)다. 큐는 그 길목 + 역 둘레 두 바퀴 + 빈틈(이웃 4개 이상이 있거나 들어갈 칸) 27칸이고, 지금 지도 가장자리에서 가까운 순(그다음 역에 가까운 순)이라 늘 붙어 있는 칸부터 만든다. 각 칸: `cell`, `state`, `rounds`, `note`. 칸 추가 절차 0단계(region.toml의 cells에 넣기)는 `cell-prep`이 한다.

## 7. 시작 전 준비

사용자(한 번):
- 이 브랜치(`claude/cool-rubin-57y8pg`)를 `main`에 합친다(또는 Mac 세션에 합치게 한다).
- Studio를 열고 MCP 켜기, 창 크기 고정(4:3보다 넓게), 자동 복구 켜기.
- `caffeinate -dims`로 잠자기·화면 잠금 끄기(화면이 꺼지면 캡처가 검게 나올 수 있다).
- Claude Code를 auto 모드로 시작한다(에이전트는 메인의 모드를 물려받는다). 에이전트의 권한 질문은 메인 화면에 뜨고 아무도 답하지 않으면 그 에이전트가 멈추므로, 자주 쓰는 명령은 `.claude/settings.local.json`의 `permissions.allow`에 미리 둔다: `Bash(uv run src/*)`, `Bash(uv run --env-file .env src/*)`, `Bash(uv run --python 3.14 *)`, `Bash(git add *)`·`commit`·`push`·`pull`·`diff`·`status`·`log`, `mcp__<Studio MCP 서버 이름>__*`, `WebSearch`, `WebFetch`. `bypassPermissions`는 쓰지 않는다(설정 파일에 넣어도 듣지 않고, Studio를 지울 수 있는 도구가 열린다).
- 디스크: 칸당 거리뷰 약 0.4 GB.

메인(첫 반복 전에 한 번, 기준선):
1. `uv run src/gate.py g1 --cells <지금 칸 79개>` → 실패 수를 `expansion.json`의 `baseline`에.
2. 1급 칸 3곳(상가 거리, 빌라 동네, 아파트)에 `cell-verify` + `cell-score` → 건물 실패 비율의 기준선. `gate.toml g3.max_fail_rate`를 그 값(넘지 않게 조금 위)으로 맞추고 이유를 주석에(메인만).
3. 기존 칸의 G1 실패 중 규칙 문제(여러 칸에 같은 원인)는 `cell-fix`로 먼저 고친다(새 칸에서도 반복되므로).

## 8. 처음 실제 데이터에서 확인할 것

클라우드 세션에는 `data/`(DB, 캡처, chunks)와 Studio가 없어서 아래는 가짜 데이터의 테스트로만 확인했다.
- `road-clear-check.luau`: 처음 한 칸은 답을 눈으로 확인(소유자 묶음, 나무 판정, 시간).
- G1: 79칸 기준선에서 거짓 경보가 많은 종류가 있으면 원인을 보고 규칙 또는 게이트를 고친다(게이트는 메인이).
- G3: 투영한 윤곽선이 사진의 건물에 얹히는지(카메라 위치 오차 1~2 m), 묶음 한 장을 메인이 아닌 에이전트가 보고 보고.
- FPS 자동 걷기: 지금 cycle-verify 5는 사람이 걷는다. 캐릭터를 스크립트로 걷게 하는 방법은 첫 FPS 차례에 `cell-verify`가 정하고 lessons에 남긴다.

## 9. 단계

- [x] 결정 기록(CLAUDE.md, audit)
- [x] G1 계산 게이트 `src/gate.py`(g1·studio·tiles·g2·fps·summary·status)와 `tests/test_gate.py`
- [x] G1 Studio 검사 `.claude/skills/cycle-verify/road-clear-check.luau`
- [x] G3 `src/lookalike.py`(카메라, 윤곽선, 색 차이, 카나리아, 채점, 벽 색 고침)와 `tests/test_lookalike.py`, 채점 지침 `lookalike-rubric.md`
- [x] 잰 벽 색 생성 반영(`build_luau.load_walls`, `measured_name`)과 테스트
- [x] 에이전트 8개, 이 절차서, 칸 큐, cycle-verify·cycle-build 반영
- [ ] (Mac) 브랜치 합치기와 7절 준비
- [ ] (Mac) 기준선(7절 메인 1~3)
- [ ] (Mac) 자동 확장 시작
