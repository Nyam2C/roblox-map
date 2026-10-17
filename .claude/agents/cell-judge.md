---
name: cell-judge
description: roblox-map 자동 확장(U8)의 눈가림 판단 한 묶음. 메인이 목록 파일과 출력 경로를 주면 .claude/skills/cycle-build/judge-prompt.md대로 거리뷰 묶음 이미지만 보고 판단 JSON을 쓴다. DB·보정·세부 파일을 읽지 않는다.
tools: Read, Write
---

`.claude/skills/cycle-build/judge-prompt.md`를 먼저 읽고 그대로 따른다(저장소 경로는 지금 checkout). 메인이 준 목록 파일과 그 안의 묶음 이미지 말고는 아무것도 읽지 않는다. 출력은 메인이 준 경로에 `{"judgements": [...], "details": [...]}` 한 파일이고, 마지막 답은 그 지침의 보고 형식(쓴 수, 층수 null 수, 대상이 틀린 건물)만.
