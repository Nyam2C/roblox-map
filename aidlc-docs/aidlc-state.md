# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (minimal: 50-line prototype script)
- **Start Date**: 2026-10-12T12:47:25Z
- **Current Stage**: CONSTRUCTION - U1, U2, U3 and U4 complete. U5 details complete 2026-10-13 (standing approval): Functional Design, NFR Requirements, Code Generation and Build and Test approved; first cell in Studio with 4,880 Auto parts and the Manual school (512), verify ok, walking 60 FPS. The user still has to set Lighting.LightingStyle to Realistic and save the place. Detail judgements of the first cell: 116/116 in the DB and details/8930e0af13bffff.json
- **AI-DLC Rules Version**: 1.0.1 (local clone of awslabs/aidlc-workflows, copied to `.aidlc-rule-details/`)

## Workspace State
- **Existing Code**: Yes
- **Programming Languages**: Python (PEP 723 inline deps, run with `uv`)
- **Build System**: none (`uv run cells.py`)
- **Project Structure**: Single-script tool + generated data (`cells/*.json`)
- **Reverse Engineering Needed**: No (skipped by user, requirement-verification-questions.md Q1=A)
- **Workspace Root**: repository root

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | Yes | Requirements Analysis (Q16=A, confirmed CQ4=A) |
| Resiliency Baseline | Yes | Requirements Analysis (Q17=A, confirmed CQ4=A) |
| Property-Based Testing | Yes (full) | Requirements Analysis (Q18=A, confirmed CQ4=A) |

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection
- [x] Reverse Engineering (SKIPPED by user, Q1 A)
- [x] Requirements Analysis (approved by user, "yes ㄱㄱ")
- [x] User Stories (SKIPPED, confirmed by user in interview)
- [x] Workflow Planning (approved by user, "승인 ㄱㄱ")
- [x] Application Design (approved by user, "승인 ㄱㄱ")
- [x] Units Generation (approved by user, "승인 ㄱㄱ")

### 🟢 CONSTRUCTION PHASE
- [ ] Functional Design - EXECUTE (per unit with pure logic)
- [ ] NFR Requirements - EXECUTE
- [ ] NFR Design - EXECUTE (minimal)
- [ ] Infrastructure Design - SKIP (no cloud infrastructure)
- [ ] Code Generation - EXECUTE
- [ ] Build and Test - EXECUTE

### 🟡 OPERATIONS PHASE
- [ ] Operations (placeholder)

## Execution Plan Summary
- **Stages to Execute**: Application Design, Units Generation, Functional Design, NFR Requirements, NFR Design, Code Generation, Build and Test
- **Stages to Skip**: Reverse Engineering (user choice), User Stories (single persona), Infrastructure Design (no cloud infrastructure)
- **Next Stage**: see aidlc-docs/handoff-2026-10-13.md: walking frame rate with Studio in front, drop the 2-3 moderation-filtered sign assets, user saves the place and sets LightingStyle; then decide on reference-photo sign generation; then the other two cells
- **U7 (2026-10-14)**: the foundation for repeating: outline-following outside (done), interiors (Q1-Q8 answered), regions, tiers, streaming, Manual anchors, mesh test and the per-cell cycle. Plan: aidlc-docs/construction/plans/u7-real-shapes-interiors-plan.md. Scale decisions answered and the plan approved (2026-10-14). Step 2 done (2026-10-14): regions/bucheon-dodang/ (region.toml, tiers.json, cells/<cell>/*.json), studio/ServerStorage + studio/manual/<region>/, src/satellite.py, src/streets.py, src/tiers.py, chunks.json from build_luau; chunk files of all three cells byte-identical before and after (P7-12). Step 3 done and approved (2026-10-14): Functional Design in aidlc-docs/construction/u7-interiors/functional-design/ (Q1-Q4 = A). Step 4 code and tests done (2026-10-14): src/interiors.py, exterior changes for hollow buildings, MapBuilder (new kinds and keys, a Model per building, Persistent Base), Elevator.server.luau, tests/test_interiors.py; tests 651. MCP_Test has the three test buildings; walking every flight to the roof and the elevator both work. Waiting for the user check of step 4; then step 5 (anchors, school field kit, sign reuse).
- **U6 (2026-10-14)**: minimap (top right), big map (M) and kick scooter (K): Requirements (questions 5 x A by standing approval), plan, code and Build and Test done. Left: walking frame rate with the Studio window in front and the map on, phone and two-player checks, the user listens to the roll sound (aidlc-docs/construction/plans/u6-minimap-scooter-plan.md).
- **Unit Order**: U1 data foundation -> U3 street-view capture -> U2 Studio builder -> U4 estimate and corrections -> U5 details, first cell 8930e0af13bffff, then repeat for the other two cells
- **Design Decisions**: GIS integrated building data matched to OSM (Q1=C), role-based scripts (Q2=A), SQLite as hub (Q3=C, Q7=A), Luau ModuleScript in Studio (Q4=B), Auto/Manual folders (Q5=A), per-cell 360 panorama capture (Q6=C), overrides exported to text for git (Q8=B)
- **Key Decisions**: H3 res 9 kept for future expansion; heights: floors from building register (건축물대장) first, verified by street view, street-view estimate as fallback, reviewed together by user and Claude; spawn at school front gate road
