---
name: cell-record
description: roblox-map 자동 확장(U8)의 기록. 메인이 칸 ID와 이번 칸의 보고 요약을 주면 cycle-record대로 lessons·스킬·audit·CLAUDE.md 현재 상태를 쓰고 자기 파일만 커밋·푸시한다. Studio를 쓰지 않는다.
model: sonnet
disallowedTools: Agent
effort: medium
---

`.claude/skills/cycle-record/SKILL.md`를 그대로 한다. 메인이 준 요약(준비·생성·게이트 결과, 고친 것)과 `data/gate/<칸>/gate.json`을 근거로 쓴다. 코드만 봐서는 모르는 것만 lessons에 날짜·칸과 함께 남기고, 사이클이 바뀌어야 하면 해당 `cycle-*` 스킬을 고친다(게이트 문서와 `gate.toml`은 메인 몫이라 고치지 않는다). CLAUDE.md "현재 상태"에 이 칸 한 줄(칸, 건물 수, 대표 시설, 게이트 결과). 커밋은 자기 파일만(`git add -A`, `git stash` 금지), 메시지 끝에 저장소 규칙의 attribution, `git push`.

보고(마지막 답): `{"cell": "<칸>", "commit": "<sha>", "lessons": 0, "skills_changed": []}`
