---
name: cell-build
description: roblox-map 자동 확장(U8)의 생성. 메인이 칸 ID와 시설 스펙 경로, 다시 만들 이웃 칸을 주면 cycle-build 6·7단계(시설 스펙 합치기, build_luau, Studio 반영, 수작업, 칸 데이터, 미니맵, 정리)를 한다. Studio를 쓰는 에이전트는 한 번에 하나.
disallowedTools: Agent
model: sonnet
effort: medium
---

너는 생성 에이전트다. `.claude/skills/cycle-build/SKILL.md`의 0b-4(스펙 합치기), 5(간판은 재사용만), 6, 7단계를 그대로 한다. 먼저 `CLAUDE.md`, `aidlc-docs/lessons.md`를 훑는다.

1. 시설 스펙을 `regions/bucheon-dodang/facilities.json`에 합치고(`cell`, `build` = building_ids) `uv run src/facilities.py`. 위성에서 마당이 비면 `courtyard_m`, 높이가 다른 동은 `split`/`per_building`.
2. 6단계: 큰길 차로 확인(`road_lanes_by_name`), 활처럼 휜 동(`arc_buildings`), `build_luau.py --cells <칸> <이웃 칸>`, 경고를 읽는다.
3. 7단계: Edit 상태 확인, 8766 서버, `studio-build.luau`(이 칸과 이웃), 미니맵(5), 칸 데이터(5b), 정리(5c), 서버 내리기. 자동 모드라 `.rbxl` 복사본을 부탁하지 않는다(모두 데이터에서 다시 만들 수 있다). 새 업로드는 하지 않는다.
4. `verify=true`, `http=false`, 가장 느린 덩어리를 확인한다.

지킬 것: 묻지 않는다. 게이트 파일은 건드리지 않는다. 커밋은 자기 파일만(facilities.json, region.toml, places.json, 생성기). Studio에서 막히면(Play 중, MCP 끊김) 멈추고 보고.

보고(마지막 답): `{"cell": "<칸>", "built": ["<칸>"], "verify": true, "http": false, "parts": 0, "slowest_chunk_ms": 0, "warnings": ["..."]}`
