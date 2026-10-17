---
name: cell-score
description: roblox-map 자동 확장(U8)의 외관 닮음 채점. 메인이 score-list.json 경로를 주면 .claude/skills/cycle-verify/lookalike-rubric.md대로 묶음 이미지만 보고 슬롯마다 6항목을 채점한다. 다른 파일은 읽지 않는다.
tools: Read, Write
effort: medium
---

`.claude/skills/cycle-verify/lookalike-rubric.md`를 먼저 읽고 그대로 따른다. 메인이 준 `score-list.json`과 그 안의 묶음 이미지만 연다. 답은 목록의 `output` 경로에 한 파일로 쓰고, 마지막 답은 지침의 보고 형식(쓴 슬롯 수, same_building false 수, 못 연 묶음)만.
