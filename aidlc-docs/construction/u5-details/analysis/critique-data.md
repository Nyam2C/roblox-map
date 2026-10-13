# U5 skeptic review — data, determinism, minimalism (ponytail)

Read-only. Verified against `src/layout.py`, `src/build_luau.py`, `studio/Builder.luau`, `src/judgement.py`, `src/common.py`, `config.toml`, `tests/test_build_luau.py`, `tests/test_versions.py`, and three scratch scripts over `data/map.db` (`mode=ro`): `scratchpad/jx.py` (junction topology), `scratchpad/shop.py` (shop rule vs notes), the earlier `inv.md` master table. No project file changed, no Studio call.

## 0. Three measurements the proposals did not make

| # | Claim in a proposal | Measured | Consequence |
|---|---|---|---|
| M1 | P3 D: `is_shop = 01000 and setback < 2.0 m` ("20/24 storefront notes are alley villas with no yard") | 89 villas; 21 have a shop noted in the blind judgement (word-bounded regex). Rule hits **5**, misses **16**, false-positives **13**. Noted-shop setbacks spread 0.1–9.5 m (median 2.9). Threshold 3.0 → 12 hit / 9 miss / 36 false; 5.0 → 17 / 4 / 56. | No setback threshold separates shops from houses. The rule is noise; drop it. The only shop signal we have is the note text. |
| M2 | P2 §0.1: shop flag = regex `shop\|store\|restaurant\|cafe\|convenience\|flower\|pharmacy\|office` over `estimates.note` | `store` matches **"storey"** → gis:11192753 and gis:11210173 (2-floor houses, "two storey ... house") become shops. `office` matches only non-01000 rows (fine). | Regex must be word-bounded: `\bshop\|\bstore\b\|restaurant\|cafe\|convenience\|flower\|pharmacy`. Word-bounded count = 21 villas; `stair` 25, `bay` 9, `balcon` 10 among villas. |
| M3 | P3 G: junctions = "segment endpoints clustered within 0.5 m, ≥ 3 legs or 2 legs of different features at > 30°" | 19 in-cell junction vertices; **17** are a vertex that some way passes *through* (interior vertex of e.g. way:222842946, way:222140575), not an endpoint. | Endpoint clustering misses 17/19 junctions. OSM ways share nodes, so P1's rule (equal `(round(lat,6), round(lon,6))` across ≥ 2 features, any vertex) is both the simplest and the correct one; `scratchpad/junctions.py` already reproduces 19. |

## 1. Rules that need data we do not have

Common ground (all three handle it correctly): 0 OSM trees/lamps/crossings/benches → everything on streets is a rule of `highway_class` + owned segments; `roof_shape` null for 44 → `DEFAULT_ROOF = flat` (`judgement.py:24`) is already the contract, no new rule needed; `sidewalk:both=yes` on way:222842945 is ignored by `sidewalk_sides` (`layout.py:232-240`) — a 1-line U2 fix, not a U5 feature.

**Proposal 1**
- K-2 `details` table: 11 new fields × 122 buildings = ~1,300 judgements that do not exist, then ~280 more for cells 2–3 before those cells get anything beyond boxes. The fields `ground_use ∈ {garage, pilotis, parking_arch}`, `awning`, `rooftop ∈ {box, railing, tank}` describe 0–4 buildings each in the notes (pilotis 0, parking 3, awning 4, rooftop 0). Data we would have to *create* to feed rules that touch ≤ 3 % of buildings.
- A.1 `school` = `usability 10000 and (in polygon or area ≥ 800 m²)`: 10000 is an *inferred* label (DATA §1 says the code table pages were unreachable); 옥산경로당 and 중동샛별 are 10000 too. Polygon membership alone is the reliable signal.
- E.1 `villa_gf`/`com_gf`/`com_upper` buckets and "pharmacy on two corners": the DB has no `shop=*` tag anywhere; which unit is a pharmacy is invented data. Acceptable only because every name is fictional anyway — but then the per-bucket vocabularies (3 × 12–16 words) are variety, not data.
- F parking-bay lines on 계남로, taxi/bus, KT cabinets, pole signs: none in data; pure invention per junction.
- A.2 dedupe uses `usability_code` non-empty OR `building_area > 0` — fine, both columns exist.

**Proposal 2**
- C3 `texture_ids` for 3 PNGs: assets that do not exist, need drawing, upload, moderation ("pending assets may be invisible"). The pipeline is defined to run with `texture_ids = 0` → the default output has *no windows at all*. That is a design that works only after an external, non-reproducible step.
- D4 drive-through = `floors_below ≥ 2 and facing width ≥ 25 m`: evaluates true for 로얄프라자 (71.4 m, +2) and gis:12403717 (37.1 m, +2); false for 리치타운 (24.3 m) and 뉴월드타운 11185986 (23.1 m). The photo survey saw the opening on 12403717, 11201645, 11185986 → the rule hits 1 of 3 and adds 1 wrong. Dead data.
- D5 pilotis = `approval_date ≥ 2005 and floors ≥ 3`: 0 buildings in cell 1 (only 2010s record is the officetel, which is commercial). A rule for nothing.
- B8/E4 rooftop name frames, B9 solar (10 % hash) — invented.
- §0.1 sub-flags from notes: good use of existing data, but see M2 (regex bug) and note that `estimates.note` has no vocabulary contract (`judgement.py` validates only length/control chars); a re-judgement silently changes facades. Acceptable if written into the BR as "notes are the U5 facade signal".

**Proposal 3**
- D shop rule: see M1 — the one data-driven rule in the proposal is wrong on 29 of 34 decisions.
- C `stair_tower_pct 35 / bay_pct 40 / balcony_pct 50 / rooftop_pct 15` hash lottery ignores the 25/9/10 observations already in the notes; a house noted "with balconies" has a 50 % chance of none.
- G junction rule: see M3.
- A1 dedupe reuses `overlap_threshold` (0.5, `config.toml:3`, consumed by `register.py:151` for OSM↔V-World assembly): semantic coupling of two unrelated decisions through one key. Pairs are 0.76–0.95 and the twins 0.0, so any constant in [0.3, 0.75] works — make it a module constant.

## 2. Determinism (BR-6.4) risks per proposal

All three correctly ban `hash()`/`random` and use `zlib.crc32`. Remaining risks:

| Proposal | Risk | Why it breaks "same text" |
|---|---|---|
| P1 E.1 | Name uniqueness by "linear probe through the sorted sign list" | A building's name becomes a function of *other* buildings' collisions. P1's own P5-6 ("another building's details change, this name stays") is then false. Local rule only: name = f(id, unit); accept rare duplicates (two 한빛부동산 in a town is realistic). |
| P1 K.2 | `details/<cell>.json` → DB → `plan_cell` | Fine only if `plan_cell` takes a mapping and sorts; the export must reuse `export_payload`'s sort (`judgement.py:232-240`). |
| P1 K.1 | 14 kinds, each with LOOKS/ORDER/FOLDER_OF/KIND_PROPS entries | Not a determinism risk but 4 parallel tables that must agree → P1 proposes a regex test over the Luau file to keep them aligned. Three kinds need no such test. |
| P2 G2 | `unary_union` of "other roads' slabs" | Deterministic only if the input list is sorted; a `set` of feature ids iterates in `PYTHONHASHSEED` order. Must say "sorted by feature_id" in the BR. |
| P2 F5 | Beam wires found by pole *name* in Studio across chunks | Output of chunk N depends on chunk N−1 having been applied; `verify` cannot count Beams by folder (`counts()` is `#folder:GetChildren()`, Builder.luau:150-156). Thin Block per span (P1/P3) is a pure item. |
| P2 H | `Builder.model()` then "Claude hand-adds" | By definition not reproducible; fine for Manual, but the generated `manual-*.luau` files in `data/build/` imply reproducibility they do not have. |
| P2 C3 | `texture_ids = 0` toggles instance count | Deterministic given config, but the manifest `config` subset must include it or two runs with different ids produce the same manifest for different places. |
| P3 G | Greedy 0.5 m clustering + angle test | Greedy clustering depends on processing order unless canonicalized; and it is wrong (M3). Vertex equality has no order. |
| P3 A6 | `<wall>_band = wall RGB × 0.72` names added to the chunk palette | Fine (pure), but the palette table must be `sorted()` like `walls` today (`build_luau.py:80-82`). |
| All | Multi-box recursive split with "first-wins ties" | Correct only if candidate cuts are a sorted list and the comparison uses `fmt()`-rounded areas; raw float ties flip with vertex order. P2-2's start-vertex invariance test would catch it only if extended. |
| All | `floors = round(height / 3.4)` fallback | Python `round` is banker's rounding (2.5 → 2); say `int(height / fh + 0.5)` or accept and test it. |

Nothing in any proposal introduces time, env, or network into `plan_cell`. The `# no ISO date` grep (test_build_luau.py:209) keeps working.

## 3. Where a property-based test cannot be written, and what to do instead

| Thing | Why no PBT | Do instead |
|---|---|---|
| Wedge/CornerWedge axis conventions (measured in Studio, not documented) | The Python oracle would encode the same assumption as the code | One **example** test pinning the 4 corner yaws and ridge/apex equalities (frozen numbers), plus one Studio smoke chunk (1 gable + 1 hip + 1 shed) captured with explicit camera. Confirm `Enum.PartType.CornerWedge` exists in this Studio in the same smoke. |
| Hangul rendering, `TextScaled` fit, Noto fallback, sign legibility at 20/80 m | Rendering | One sign in the smoke chunk. |
| Built-in material tile scale (`Brick` courses per stud at 3.6 stud/m) | Not documented, not computable | One part per candidate material in the smoke; if bricks are giant, fall back to `Concrete` + color — the mapping is a constant table, one edit. |
| FPS gate (U2-NFR-P4) | Measurement | Walk the cell with Studio in front; the only knobs are the three spacings and `window_faces`. |
| Manual school | Hand work | `verify` already reports `skipped_manual`; add one line listing Manual `BuildingId`s that no Auto item claimed (typo detector). |
| Texture tiling alignment (P2 only) | Not in Python | Moot if windows are parts. |
| Luau hex decoder (P1/P2/P3) | No Luau runtime in CI; a Python "mirror" tests the mirror, not the decoder | Moot if sign text is verbatim (§5). |
| Fictional names "look Korean" | Taste | Blocklist test (example) + user reads 20 names once. |

Every geometric rule (bands, windows, roofs, walls, props, crosswalks, sidewalk split, dedupe, facing side) *is* PBT-able with the existing generator style (`tests/generators.py` sections, expected values computed in the test). The property lists of P1 (18) and P3 (16) overlap ~80 %; the hybrid list below is 11.

## 4. YAGNI — what to cut, and the simpler rule that gives 90 % of the look

Ranking the photo survey's top-12 against part cost: items 1 (brick villas), 10 (hip vs flat), 11 (stone/tile variant) are **0 parts** — a material table keyed on `wall_color` + the existing `roof_shape`. That single change is the biggest visual step in U5 and all three proposals bury it under 40–100 parts per building.

Cut list (P = proposal):

| Cut | Why | Keep instead |
|---|---|---|
| P1 `details.py` CLI + table + export v1 + 11 fields | A second U4 for ≤ 3 % coverage; 1,300 judgements | Word-bounded regex over `estimates.note` for 4 flags (shop/stair/bay/balcony). Nothing new persisted. |
| P1 14 kinds, 46 palette names, `KIND_PROPS`, `colors=` rename (breaks test L307-315 for nothing) | 4 parallel tables | 3 kinds: `facade` (owned, no text), `sign` (owned, text), `prop` (unowned). One line in `LOOKS`, `ORDER`, `FOLDER_OF` each. |
| P1 plinth, gas pipe (2 parts), AC units (1–3), canopy, globe lamps, shrubs, awnings, 돌출 signs, pole signs, banners, rooftop boxes/tanks/solar/name frames, bollards, cabinets, parking bay lines, edge lines, stop lines, school-zone poles/fences as rules | 0.3–0.8 m objects, ≈ 1,000 parts/cell, rank ≥ 9 or unranked | Add after the user walks the first cell and names what is missing. |
| P2 window `Texture`s + 3 uploads + `texture_ids` | External, moderated, invisible-by-default; pipeline ships blank walls until approved | Window parts (opaque dark glass color). 24–30/villa is the price; the FPS knob is faces, not technique. |
| P2 Beams + Attachments | Cross-chunk name lookups, uncountable by `verify`, undocumented on-screen cap | 2 thin Blocks per span. |
| P2 `UIListLayout` + 2–4 `TextLabel` per floor band | More GUI instances, more Luau | 1 part + 1 `SurfaceGui` + 1 `TextLabel` per panel, n = clamp(⌊L/8⌋, 1, 3) panels per floor. |
| P2 budget machinery (`building_part_max`, `cell_street_part_budget`, `budget_ok`, `instances_total`, `Archetype`/`Parts` attributes) | Config for assertions nobody tunes | `manifest.counts.items_<kind>` already exists; one `parts_per_building_max` example test. |
| P2 `speed_bumps=false`, `parked_cars=true`, `wall_materials` table, `dup_overlap`, `window_module_m` as config | Config for values that never change | Constants in `layout.py`. |
| P2 D5 pilotis, D4 drive-through, B9 solar, B8 rooftop name | 0–2 buildings, wrong ones (§1) | — |
| P3 `stair/bay/balcony/rooftop_pct` hash lottery + 4 config keys | Ignores recorded observations | Notes regex (M2). |
| P3 shop-by-setback | Measured noise (M1) | Notes regex ∪ commercial codes. |
| P3 `--manual` plan generator in product code, P2 `Builder.model`, P1 `src/manual_school.py` | Product code for a one-off | Run Auto, **drag the school parts from `Auto/<cell>/Buildings` into `Workspace/Manual`** (they already carry `BuildingId`, Builder.luau:119), then edit by hand; the next regeneration skips them. Zero new code. Box coordinates for hand-placed wings come from a scratch script, not `src/`. |
| Multi-box footprints (all three) | After dedupe and Manual schools the beneficiaries are 로얄프라자 (0.62 → 0.90, 3 boxes) and two villas (0.75 → 0.88); ~40 lines + "which faces touch a sibling" logic + `items_building` semantics change | Leave `poor_fit` as is; 로얄프라자 becomes Manual if it bothers the user. |
| P1 parapet 4 slabs / railing 8 pipes | 4–8 parts for a 0.8 m line | P3's 1 cap ring (`w+0.1, 0.3, d+0.1`). |
| P1/P3 street lamps (3 parts × 20–33) | Not in the top-12 | Add when the user asks; 1 line in the prop producer. |
| Eave overhang maths `H'` scaling | 4 lines for a 0.4 m lip | Keep (cheap and visible), as a constant, not config. |

What stays (gives the top-12 at ≈ 35 parts/villa, ≈ 70/commercial, ≈ 4,600 parts/cell, ≈ 14k for 3 cells): material table, floor bands (F−1 rings), roof (flat cap 1 / gable 2 / hip 6 / shed 1), windows, door, storefront + band sign for shops, per-floor sign bands on commercial, yard wall + gate for houses with setback ≥ 1.5 m, stair strip / bay / balcony where noted, curbs, center lines, crosswalks at junction arms of residential/tertiary, sidewalk gaps at alley mouths, poles + wires, trees on sidewalks, parked cars (one side of living_street/residential), ground slab → paved gray, sidewalks → paver color.

## 5. The Korean-text-in-Luau problem

What `SAFE_TEXT` (`build_luau.py:36`) actually protects: a Luau double-quoted literal can only be terminated by `"`, `\` or a raw newline; control characters and `]]` matter only for long strings, which are never emitted. `luau_string` refuses everything outside `[A-Za-z0-9:#_.\-]` (L42-46), and `test_luau_string_returns_only_safe_text…` (test_build_luau.py:52-59) asserts ASCII for *that function*.

| Option | What it adds | Verdict |
|---|---|---|
| Hex code points dot-joined (P1 E.4, P2 E7, P3 E) | Python encoder + Python "mirror" decoder for the round-trip test + 3–4 Luau lines (`gmatch`, `tonumber`, `utf8.char`) + range re-checks in Luau that CI cannot run + a 16-codepoint/79-char cap. Three proposals, three slightly different encodings (P2 says UTF-16 units; same thing for BMP). | Works, but every line of it exists to avoid touching a regex. Tests the mirror, not the Luau. |
| Loosen `SAFE_TEXT` | Breaks L52-59 and lets Hangul into ids, attributes, kinds | No. |
| ASCII romanized names | Zero code | Fails the goal ("HANSOL PHARM" in 중동). |
| **Second regex for the `t` key only** | `SIGN_TEXT = re.compile(r"[가-힣A-Za-z0-9 ]{1,12}")`, a 3-line `sign_string()` next to `luau_string`, Builder does `label.Text = it.t`. One existing test line changes: `test_sec2_hostile_ids_never_reach_the_code` (L119-131) scans every quoted string in the chunk and asserts `SAFE_TEXT`; it becomes `SAFE_TEXT or SIGN_TEXT`. The other two assertions in that test (`"\\" not in text`, even quote count) keep holding. | **Pick this.** Provable: UTF-8 bytes of U+AC00–D7A3 are all ≥ 0x80, so no byte of a syllable can be `"` (0x22), `\` (0x5C) or a newline; the class excludes those and control chars directly. Chunk files are already written UTF-8 (`write_plan`, L12); `execute_luau` is JSON transport. Round-trip property is trivial: `t` in the chunk equals the name string. |

The one honest cost: the Luau chunk files and git diffs contain Hangul. The user already keeps Korean in `config.toml` comments and `overrides/*.json` notes, so this is not new.

## 6. Manual / hand-built school vs regeneration and the BuildingId rule

Today: `manualIds` collects `BuildingId` from **every descendant** of `Workspace/Manual` (Builder.luau:56-65); `add` skips only `it.k == "building" and manual[it.n]` (L101-102); `begin` destroys only `Auto/<cell>` (L75); `verify` adds `SkippedManual` to the building count only (L182).

What U5 must change, regardless of proposal:
1. Every owned item carries `i=<BuildingId>` and Builder skips on `manual[it.i or it.n]` — otherwise a hand-built school gets Auto windows, roof and signs stuck into it. All three say this; it is ~3 Luau lines.
2. `verify` needs the skipped count **per kind** (`Skipped_<kind>` attributes), or the facade/sign folders fail the count whenever anything is Manual. P3's version is the smallest.
3. After dedupe (6 records dropped at plan time) the school has 3 Auto ids (11185213, 11185281, 11036833); no placeholder folders, no dual-id Models (P1 H / P2 H / P3 H all need those only if dedupe is refused).
4. Workflow: run Auto once → drag the three school boxes (and the fence-like rows 11201621/11201622 if wanted) from `Auto/<cell>/Buildings` to `Workspace/Manual/School` → edit by hand → every later regeneration skips them. No `Builder.model`, no `manual-*.luau`, no second `:Destroy()` (test_versions.py:102-108 stays as is).
5. Unowned Auto props (trees, crosswalks, curbs on 계남로) are regenerated every time and are **not** suppressed by Manual — correct: the school-zone fence the user builds under Manual is never touched, and the 계남로 road slab the school boxes overlap today disappears from Auto once the ids are Manual.
6. Failure mode to cover: a Manual part with a mistyped `BuildingId` → Auto rebuilds the box inside the hand-built school. Add to `verify`: list Manual ids not matched by any item this cell (one loop, no new API).
7. The `.rbxl` + Version History is the source of truth for Manual (CLAUDE.md decision); no proposal should pretend otherwise by shipping generator scripts.

## 7. Recommended rule set (the hybrid)

Design stance: anchored `Part`s with `Shape ∈ {Block, Wedge, CornerWedge, Cylinder, Ball}`, built-in materials, constant palette; no uploads, Textures, MaterialVariants, Beams, Unions, Glass-with-things-behind-it. Three new kinds. All variety from `zlib.crc32(f"{owner}|{salt}") % n`.

**BR-U5-1 Dedupe.** Before anything else, among `status=ok` buildings of a cell, a record with `building_area ∈ {0, null}` **and** empty `usability_code` whose outline overlaps another record ≥ `DUP_OVERLAP = 0.6` (intersection ÷ smaller area) is not built; manifest lists `duplicates_dropped` with `(dropped, kept)`. Expected cell 1: 6 pairs, 116 built. Module constant, not config.

**BR-U5-2 Body gate and floors.** `is_body = floors ≥ 1 and height_m ≥ 2.5 and min(w, d) ≥ 3 m`; non-bodies (fences, booths) get only their box. `floors` missing → `int(height_m / floor_height_m + 0.5)` (existing key, 3.4). `fh = height_m / floors`.

**BR-U5-3 Material from wall color (0 parts).** Constant table: `red_brick, brown, orange → Brick`; `beige, cream, yellow → Sandstone`; `white, pink, green, blue → Plaster`; `light_gray, dark_gray, other → Concrete`. Color stays `judgement.wall_rgb`. Literal key `m` only when ≠ the kind default. Confirm tile scale once in Studio; fallback is editing this table.

**BR-U5-4 Archetype.** `commercial` = `usability ∈ {03000, 04000, 09000, 11000, 14000}` or `floors ≥ 5`; `villa` = everything else with `is_body`; no `school` archetype (schools are Manual by id). `shop` = commercial, or villa whose note matches `\bshop|\bstore\b|restaurant|cafe|convenience|flower|pharmacy`. Facade flags from the note: `stair`, `bay`, `balcon`. Notes are read from the `estimates` mapping `plan_cell` already receives (`build_luau.py:112-119`).

**BR-U5-5 Facing side.** The box edge whose midpoint is nearest the nearest owned road/path piece (`_distance_to_center_line`, `layout.py:276`); `setback_m` = edge to road slab edge; no piece within 60 m → no facing (no door, storefront, yard, signs). Faces that "touch" a neighbour (point 2.5 m outside the face midpoint lies inside another built box) get no windows.

**BR-U5-6 Bands and cap.** Floor lines k = 1..F−1: one ring `(w+0.10, 0.12, d+0.10) m` centred at `y = k·fh`, color = wall RGB × 0.72 (name `<wall>_band`). Flat/other/null roof: one cap ring `(w+0.10, 0.30, d+0.10)` at the top, same color.

**BR-U5-7 Roofs.** `pitch = 25°`, overhang `o = 0.4 m` (constants). `D = d/2 + o`, `H = tan(pitch)·D`, parts sunk 0.02 m into the box. gable = 2 Wedges `(w+2o, H, D)` at z ∓D/2, yaw box/box+180; hip = 2 Wedges `(w−d, H, D)` + 4 CornerWedges `(D, H, D)` with yaws (+X,−Z) 180, (+X,+Z) 90, (−X,−Z) 270, (−X,+Z) 0 relative to the box (w−d < 1 m → 4 CornerWedges); shed = 1 Wedge `(w+2o, tan(pitch)·(d+2o), d+2o)`, high face at local +Z. Material `Slate` (60,60,65). The yaw constants are verified once in Studio and pinned by an example test.

**BR-U5-8 Windows.** Villa: per eligible face ≥ 4 m, per floor k: `n = clamp(⌊(L−1)/4⌋, 1, 3)` panes `1.6 × 1.4 × 0.10 m`, sill `k·fh + 0.9`, evenly spaced, centred on the wall plane, `SmoothPlastic` (45,60,60), `Reflectance 0.25`. Commercial: one ribbon `(L−1) × min(1.7, 0.5·fh) × 0.10` at `k·fh + 1.0` per face per floor k ≥ 1. Shop ground floor on the facing face: no panes (storefront instead). `CastShadow=false` on every non-building part (one Luau line).

**BR-U5-9 Facade facts from notes (villa, facing face).** `stair`: strip `1.2 × (height+1.0) × 0.3 m` at along = −L/3, out 0.2 m, glass color. `bay`: block `2.4 × (F−1)·fh × 0.4 m` from `y = fh`, at +L/3, (225,225,222); that slot gets no panes. `balcon`: floors 1..F−1: slab `0.4L × 0.15 × 0.6` + railing `0.4L × 1.0 × 0.05` `Metal` (40,40,45).

**BR-U5-10 Ground floor.** Non-shop body: door `1.0 × 2.1 × 0.08 m` `Wood` (70,50,40) at the facing-face centre. Villa, not shop, `setback ≥ 1.5 m`: wall line at `min(setback, 8) − 0.3 m` out, length `L + 2`, height 1.4, thickness 0.2, two segments around a 2.8 m central gap, 2 posts `0.5 × 1.8 × 0.5`, gate leaf `2.8 × 1.6 × 0.06` `Metal` (40,40,45); wall material = house material if `Brick` else `Concrete` (150,150,145). Shop (facing face, floor 0): `units = 1` for villa, `clamp(⌊L/6⌋, 1, 4)` for commercial; per unit a glass panel `(L/units − 0.4) × (fh − 0.6) × 0.10` from y 0.1 (35,45,50), one door in the first unit, one eyebrow canopy `(L−0.6) × 0.15 × 0.6` at `fh − 0.3`. No pilotis, no shutters, no drive-through (0 data).

**BR-U5-11 Signs.** 띠간판: one per shop unit, `(L/units − 0.4) × 0.9 × 0.15 m`, bottom `min(3.0, fh − 0.4)`, out 0.15. Per-floor bands (commercial, F ≥ 4): floors k = 1..min(F−1, 5), `clamp(⌊L/8⌋, 1, 3)` panels `0.8 m` tall at `k·fh + 0.15`. Part `SmoothPlastic`, color = one of 6 (bg, ink) pairs by `crc32(owner|sign{slot}) % 6`; literal keys `c` (bg name), `o` (ink name), `t` (text). Builder: `SurfaceGui` (Front, `PixelsPerStud` 50, `LightInfluence` 1, `MaxDistance` 300) + one `TextLabel` (`TextScaled`), `label.Text = it.t`. Name = `PREFIX[crc32(owner|p{slot}) % len] + WORD[pool][crc32(owner|w{slot}) % len]`; pools by archetype/floor (villa GF, commercial GF, upper, medical for 09000); ~40 nature/abstract prefixes, no place names, `REAL_BRANDS` blocklist checked by a test; 2–7 Hangul chars; no cross-building uniqueness. Text validated by `SIGN_TEXT = [가-힣A-Za-z0-9 ]{1,12}` and emitted verbatim (§5).

**BR-U5-12 Junctions, crosswalks, sidewalk gaps.** Junction = a `(round(lat,6), round(lon,6))` vertex shared by ≥ 2 road/path features, owned by the cell containing it; arms sorted by `(feature_id, segment index)`. Crosswalk on each arm of class ∈ {tertiary, residential}: stripes `0.45 × 0.05 stud × 4.0 m` at 0.9 m pitch across the road width (`⌊w/0.9⌋`), band starting `w_max/2 + 1.0 m` from the node, white, `y = TOPS.road + 0.03`. Sidewalk pieces get a gap of `other road width + 1.0 m` centred on each junction where another feature meets that segment (`split_along(p, q, breaks)`), names `way:1#0L.0`, `.1`; curbs follow the pieces. No corner radius, no stop lines, no tactile tiles.

**BR-U5-13 Street props** (`prop`, group = feature id, first at `spacing/2` then every `spacing` along each owned segment; `L/R` as in `sidewalk_items`; vertical cylinders = size `(height, dia, dia)` with a fixed 90° roll in Builder):
- Curb per sidewalk piece: `len × 0.5 stud × 0.15 m` `Granite` (150,150,145) on the road-side edge.
- Centre line on residential not `oneway`: 2 × `(len − w) × 0.05 stud × 0.15 m` yellow (235,190,40) at ±0.15 m, `y = TOPS.road + 0.03`, `CanCollide=false`.
- Pole + crossarm on living_street/residential/service every `pole_spacing_m` (30), R side at `w/2 + 0.4`: Cylinder 0.30 × 10 m `Concrete` (150,150,148) + Block `1.6 × 0.1 × 0.1` at 9 m; wires = 2 Blocks `0.04 × 0.04 × span` at 9.0/8.6 m between consecutive poles of the same feature, (30,30,30).
- Tree on every sidewalk-bearing road every `tree_spacing_m` (7), both sides at `w/2 + 0.6`: Cylinder 0.35 × 3.5 `Wood` + Ball 6 m at y 6.5 `Grass` (60,110,50).
- Car on living_street (8 m) and residential (10 m), R side at `w/2 − 1.0`, none within 6 m of a junction: Block `4.4 × 1.45 × 1.8` + cabin `2.2 × 0.5 × 1.6`, `SmoothPlastic`, color by `crc32 % 10` (7 white, silver, black, dark gray), `CanCollide=true`. `spacing = 0` → none.

**BR-U5-14 Looks.** `LOOKS.ground → ("Concrete", (130,128,125))`, `LOOKS.sidewalk → ("Brick", (165,140,135))` (amends U2 BR-4.1/3.6; Q1). Lighting (`Realistic`, 14:30, `DepthOfField` removed, Atmosphere 0.3) is set by hand once and logged, not code.

**BR-U5-15 Literal, Builder, Manual.** New kinds `facade`, `sign`, `prop` in `LOOKS`/`ORDER` (ground 0 … building 4, facade 5, sign 6, prop 7, spawn 8) and `FOLDER_OF` (`Facades, Signs, Props`). Optional literal keys: `i` owner (when ≠ name), `p` shape (≠ Block), `m` material (≠ kind default), `c` color name (existing), `o` ink, `t` text (`sign_string`). Palette per chunk = the existing `walls={…}` table extended to every `c`/`o` name in the chunk, sorted (`test_u4_the_colors_of_a_chunk…` unchanged). Builder: `Shape = Enum.PartType[it.p]`, `Material = Enum.Material[it.m or look[1]]`, `owner = it.i or (it.k == "building" and it.n)`, skip when `manual[owner]`, `Skipped_<kind>` counters, `BuildingId = owner` on owned parts, `CastShadow=false` for `k ≠ building`, sign GUI branch. Still one `:Destroy()`, no geometry, no decoder. Deploy by Clone + Destroy. `chunk_size` 100 → measure one 25 KB chunk → 250 with `CHUNK_WARN_BYTES = 30_000` if < 50 ms.

**Config keys (3 new, all FPS knobs; everything else is a module constant):** `pole_spacing_m 30 (0..200)`, `tree_spacing_m 7 (0..50)`, `car_spacing_m 8 (0..50)` — each with `DEFAULTS`, `RANGES`, `config.toml`, one bad example, manifest `config` subset. (`floor_height_m`, `chunk_size`, `wall_colors`, `school_polygons`, `poor_fit_ratio` already exist.)

**Properties (hybrid P5 list):**

| id | property |
|---|---|
| P5-1 | same input → byte-identical chunk files with every U5 kind present; shuffling rows, features and estimates changes nothing; changing one building's note changes only items whose `owner` is that building; no ISO date |
| P5-2 | dedupe: a record with attributes is never dropped; after dedupe no kept pair overlaps ≥ `DUP_OVERLAP` with one side attribute-less; idempotent; order-free |
| P5-3 | roof (Python model of the measured conventions): ridge/apex `y = top − 0.02 + H`, `H = tan(pitch)·D`; plan extent ⊆ box + overhang; part count ∈ {0 (flat has only the cap), 1, 2, 4, 6} by shape |
| P5-4 | bands exactly at `k·fh`; every pane inside `[k·fh + 0.9, (k+1)·fh − 0.06]`; panes on one face disjoint; count = formula; every facade part within 0.6 m of a box face; non-body → no facade items |
| P5-5 | shop/yard partition: exactly one of {storefront, yard, neither} from (archetype, note, setback); `03000/10000` never shop by code; no facing → neither; forcing `shop` removes the yard and adds exactly `units` band signs |
| P5-6 | sign text: every `t` in a chunk matches `SIGN_TEXT`; hostile text (quotes, `\`, control, non-Hangul letters) is refused and the building skipped; names end with a pool word, contain no `REAL_BRANDS` entry, and `(owner, slot)` is stable |
| P5-7 | junctions = exact count of shared vertices, independent of feature order; stripes `⌊w/0.9⌋`, all inside the slab, band in `[w_max/2 + 1, w_max/2 + 5]` along the arm; only configured classes |
| P5-8 | sidewalk split: pieces ∪ gaps = original, gaps = `other width + 1` centred on mouths, no mouths → identical to P2-5; curbs one per piece |
| P5-9 | props: consecutive items `spacing` apart (±1e-6), first at `spacing/2`, none when segment < spacing or spacing = 0, lateral offset exact, cars ≥ 6 m from junctions; wires join consecutive pole tops (≤ 1e-3) |
| P5-10 | literal/SEC2: optional keys only when non-default; `{k="` count = items; every `c`/`o`/`m`/`p` in a closed set; every used color name appears once in that chunk's palette; `"\\" not in chunk` and even quote count still hold with Hangul |
| P5-11 | ownership: every facade/sign item has `owner` ∈ built buildings; removing a building removes all items with that owner and nothing else; `manifest.items_<kind>` = Σ |

Example tests: 12×10 m 3F villa → 2 bands, 1 cap, 2–3 panes/face/floor, 1 door, 5 yard parts; same with hip → 6 roof parts of the stated sizes; "two storey brick house" note → not a shop; 100 m residential segment → 3 poles, 2 wire runs, 14 trees/side, 10 cars; 계남로×옥산로109번길 vertex → 2 crosswalks; `sign_string("한솔약국")` = `"한솔약국"`, `sign_string('a"b')` raises; the six first-cell duplicate ids dropped. Acceptance as U4: seeds 1/7/42/2026/99999, ≥ 12 deliberate breaks caught.

Studio smoke (one chunk in `MCP_Test`, before anything else): 1 gable, 1 hip, 1 shed, 1 vertical cylinder, 1 `Brick`/`Sandstone`/`Plaster` part each, 1 Hangul sign; then one 25 KB chunk timing; then the full cell + `verify` + walk.

## 8. Questions that truly need the user

1. **Ground slab**: paved gray `Concrete` (+ Manual grass only in the park/school) instead of the current `Grass` — changes U2 BR-4.1; 0 parts, large look change. Default: yes.
2. **Parked cars** on every living_street/residential lane (≈ 100 cars, 200 parts/cell, `CanCollide=true` so the walker goes around; 5 m lanes keep 3.5 m free): yes / no / fewer (`car_spacing_m`). Default: yes at 8/10 m.
3. **Hangul in chunk files**: sign names are emitted verbatim (UTF-8 in `data/build/*.luau` and in git diffs of tests) rather than hex-encoded. Default: verbatim.

Everything else (dedupe of the 6 doubles, three Manual school ids by drag-out, notes as the facade signal, no multi-box, no uploads/Beams/Textures, 3 kinds, constants over config, lighting by hand) is a default the user can overturn after walking the first cell.