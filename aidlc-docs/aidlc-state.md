# AI-DLC State Tracking

## Project Information
- **Project Type**: Brownfield (minimal: 50-line prototype script)
- **Start Date**: 2026-10-12T12:47:25Z
- **Current Stage**: CONSTRUCTION - U3 Code Generation Part 1 (Planning). U1 is complete
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
- **Next Stage**: U3 Code Generation (plan in progress), then Build and Test. U3 NFR Design is skipped as planned
- **Unit Order**: U1 data foundation -> U3 street-view capture -> U2 Studio builder -> U4 estimate and corrections -> U5 details, first cell 8930e0af13bffff, then repeat for the other two cells
- **Design Decisions**: GIS integrated building data matched to OSM (Q1=C), role-based scripts (Q2=A), SQLite as hub (Q3=C, Q7=A), Luau ModuleScript in Studio (Q4=B), Auto/Manual folders (Q5=A), per-cell 360 panorama capture (Q6=C), overrides exported to text for git (Q8=B)
- **Key Decisions**: H3 res 9 kept for future expansion; heights: floors from building register (건축물대장) first, verified by street view, street-view estimate as fallback, reviewed together by user and Claude; spawn at school front gate road
