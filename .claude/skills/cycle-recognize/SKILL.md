---
name: cycle-recognize
description: roblox-map 세션 흐름의 1단계 "인지". 세션을 시작할 때, 칸 작업을 이어받을 때, 사용자가 "인지", "상태 파악", "어디까지 됐어", "이 칸 시작"이라고 할 때 쓴다. 기록 문서와 칸·Studio 상태를 읽고 지금 사이클의 어느 단계인지 보고한다. 아무것도 바꾸지 않는다.
---

# 인지 (세션 흐름 1/5)

세션은 동시에 하나, 칸 하나에 세션 하나다(CLAUDE.md "세션 흐름"). 이 단계는 **읽기만** 한다. 파일·DB·Studio를 바꾸지 않는다.

## 1. 기록 읽기 (이 순서)

1. `CLAUDE.md`는 이미 로드되어 있다. "결정 사항", "칸 추가 절차", "다음 할 일"을 다시 본다. 지난 칸들의 진행 기록은 `aidlc-docs/status.md`(새 항목이 맨 위), 명령·구현 메모는 `aidlc-docs/pipeline-notes.md`에서 필요한 만큼 읽는다.
2. `aidlc-docs/lessons.md` 전체. 이전 세션이 겪은 함정과 대처다. 이번 칸에 해당할 항목을 골라 둔다.
3. `aidlc-docs/aidlc-state.md`의 Next Stage와 유닛 줄.
4. 이번 작업이 구조 변경이면 `aidlc-docs/architecture.md`, U7 중이면 `aidlc-docs/construction/plans/u7-real-shapes-interiors-plan.md`.
5. 답을 기다리는 질문 파일(`aidlc-docs/inception/requirements/*-questions.md`에서 빈 `[Answer]:`). **답은 있는데 "구현" 기록이 없는 질문**도 찾는다(정해 놓고 안 만든 것: 2026-10-14 지도 장소 정보).

## 2. 저장소 상태

```bash
git log --oneline -10
git status --short          # 내 것이 아닌 변경이 있으면 건드리지 말고 사용자에게 알린다
```

## 3. 칸 상태 (칸 ID를 사용자에게 받거나 "다음 할 일"에서)

```bash
sqlite3 data/map.db "select cell_id, count(*) from buildings group by cell_id"
sqlite3 data/map.db "select b.cell_id, count(e.building_id), count(d.building_id) from buildings b left join estimates e using(building_id) left join details d using(building_id) group by b.cell_id"
sqlite3 data/map.db "select cell_id, unit, status, finished_at from collection_runs order by finished_at desc limit 10"
ls data/build/<칸>/ regions/*/cells/<칸>/ data/satellite/<칸>-z19.json 2>/dev/null
uv run src/tiers.py list --cells <칸>          # 등급(구역의 tiers.json). 구역에 없는 칸이면 오류
```

`data/build/<칸>/manifest.json`이 있으면 `counts`, `warnings`, `poor_fit`을 본다.

## 4. Studio 상태

`list_roblox_studios`(연결이 바뀌면 `studio_id`가 바뀐다) → `get_studio_state`(Play 중이면 Edit 작업 금지). Edit일 때만 읽기용 Luau로 `Workspace/Auto`의 칸 폴더별 자손 수, `Workspace/Manual`의 폴더, `Lighting.LightingStyle`, `Workspace.StreamingEnabled`를 본다.

## 5. 보고 (채팅, 한글)

짧은 표로:

| 항목 | 상태 |
|---|---|
| 칸 | ID, 등급(있으면), 건물 수 |
| 사이클 단계 | 수집 / 거리뷰 / 판단 / 나무 / 생성 / Studio / 검증 / 기록 중 어디까지 |
| Studio | 연결, 모드, 이 칸 부품 수, 저장 여부(모르면 모른다고) |
| 열린 질문 | 답을 기다리는 것 |
| 이번 칸에 해당하는 lessons | 2~5개 |
| 다음 할 일 | 한 줄 |

그다음 `cycle-memory`로 간다.
