# U5 feasibility and performance review (Roblox skeptic)

Scope: the three Functional Design proposals vs. the ROBLOX FACTS report, Creator-Hub docs and DevForum (searched today), the project code (`src/layout.py`, `src/build_luau.py`, `studio/Builder.luau`, `config.toml`) and `data/map.db` (read-only). No project file changed, no Studio tool called (only the `execute_luau` tool schema was read).

Anchors re-checked: `layout.LOOKS/ORDER` `src/layout.py:25-29`, `MAX_PART_STUDS = 2048` L21; `SAFE_TEXT`/`TEXT_ATTRS`/`CHUNK_WARN_BYTES` `src/build_luau.py:35-37`; part creation `studio/Builder.luau:104-116` (plain `Part`, no `Shape`, no `CastShadow`), `manualIds` L56-65 (scans all descendants), the single `Destroy` L75; `overlap_threshold = 0.5` `config.toml:3`, `chunk_size = 50` L53. DB counts match DATA SIGNALS exactly (122 ok rows; 01000: 2F×4, 3F×84, 4F×1; 19 rows with area 0/null; streets 6 living_street, 5 service, 4 residential, 1 tertiary, 1 link, 1 pedestrian).

## 0. Facts established today (beyond the ROBLOX FACTS report)

| # | Fact | Status | Consequence |
|---|---|---|---|
| F1 | `Enum.PartType` = Ball, Block, Cylinder, **Wedge (3), CornerWedge (4)**; `Part.Shape = Enum.PartType.Wedge` works since the 2023 "Improvements to Part Shape & Size" release; Studio's Insert now creates wedges as `Part`+`Shape` | [DOC]+[STAFF] | P3's `Shape` route and P1/P2's `WedgePart`/`CornerWedgePart` classes both valid; geometry equivalence still unmeasured |
| F2 | Minimum `BasePart.Size` is **0.001 stud** per axis (lowered from 0.05 in 2021); collision geometry stays ≥ 0.05 | [STAFF] | P1 N.11 ("최소 0.05 stud") is outdated; 0.02-stud markings render fine, physics irrelevant (`CanCollide=false`) |
| F3 | Beam curve: control point 1 = `Attachment0.WorldPosition + Attachment0.RightVector × CurveSize0` (docs code sample); sag only if the attachment's X axis points vertically | [DOC] | P2's `CurveSize −1.5` sags only because the pole part is rolled 90° (its X = world up) and the Attachment is unrotated; must be written down, else wires bow sideways. `Beam.Color` is a `ColorSequence`, not Color3 |
| F4 | `StreamingTargetRadius`/`StreamingMinRadius` are **Not Scriptable** (Workspace class page); default 1024 / 64; **no documented maximum** | [DOC] | P2's "≥ 2,400 studs" cannot be verified until typed into Properties; P1's "1200" leaves the far cell unloaded (3 cells ≈ 2,000 studs) |
| F5 | `Lighting.LightingStyle` is "modifiable only in the Properties window"; scripts get `LightingStyle is not a valid member of Lighting` | [DOC]+[FORUM] | P1 §I/K-7 ("Claude가 execute_luau로") is wrong for this one property; P2/P3 are right (hand step) |
| F6 | Glass: "At Transparency 0, glass is completely opaque"; refraction only at high quality and **not on mobile**; whether an opaque Glass part takes the cheap opaque path is **not documented** | [STAFF]/silent | P3's 10k+ opaque-Glass window plates are the largest unverified cost in P3 → A/B test (§4 T2) |
| F7 | Texture tiling "starts at the corner of regular parts" (which corner: undocumented); `StudsPerTileU/V` tile size, `OffsetStudsU/V` shift | [DOC]+[FORUM] | P2's exact-fit tiling (`StudsPerTileU = face/n`, body height = F·fh) is origin-independent, OK; still needs the one-part check they plan (N1) |
| F8 | Pending-moderation image visibility to the uploader in Studio: forum reports conflict (visible "immediately… only to the uploader" vs. "not until reviewed"); assets have been stuck for days/weeks in known incidents | [FORUM] | P2's `texture_ids = 0` fallback is mandatory, not optional; schedule uploads on day 1 |
| F9 | Cylinder `Part`: length along **X**, diameter = `min(Size.Y, Size.Z)`; forum-only, not in docs | [FORUM] | P1 "Pole" and P3 "vertical cylinder = roll 90°" are consistent with it; P2 never states a roll (§2) |
| F10 | Batching: old staff posts — parts share a draw call with same geometry type + material + texture; CFrame/Size/Color/Reflectance do not split batches; static (anchored) clusters pack densely, dynamic ≤ 72/batch; no 2023+ statement found | [STAFF, old] | "same shape+material batch" (P1 J, P3 J) is plausible and old; the real cost drivers for 20k small parts are triangles, shadow pass and cluster memory, not draw calls |
| F11 | `execute_luau` schema: no payload size limit stated; guidance is `task.wait()` per ~1000 instances and small `.Parent` subtrees | [SCHEMA] | 25 KB / 250-item chunks are untested but inside the guidance; Builder already parents one part at a time (L139-144) |

## 1. Claim audit — Proposal 1 (realism)

| Section | Claim | Verdict | What the facts say |
|---|---|---|---|
| I, K-7 | `LightingStyle=Realistic` set by Claude with `execute_luau` | **Wrong** | F5: Properties window only. Everything else in §I (ClockTime, Atmosphere, Bloom, DOF.Enabled) is scriptable |
| B hip | WedgePart 2 × `(Lx−Wz+2o, H', Wz/2+o)` + 4 CornerWedgePart `(Wz/2+o, H', Wz/2+o)` | **Wrong geometry** | Plan length = Lx−Wz+2o + 2(Wz/2+o) = **Lx+4o**: 0.8 m overshoot (or overlap) per hip roof. With an overhang the ridge stays Lx−Wz (facts §4 recipe; P3 B gets it right). P5-3 "발자국 ⊆ 박스+o" would catch it if written as stated |
| B shed | pitch 25° over full width Wz, H'' = tan25°·Wz | Risky | 10 m deep → 4.66 m rise, above their own 3.5 m cap; real sheds 5–12° (P2 uses 12°) |
| N.11 | "부품 최소 크기 0.05 stud" → raise markings to 0.05 | Outdated | F2: 0.001 stud renders; only collision is 0.05. Harmless (0.05 is still the sane thickness), and "전선 0.08 stud < 0.05" is an arithmetic slip |
| C.1 | windows 0.02 stud in front of the wall plane | Risky | 0.02 stud = 6 mm; depth precision at 50–100 m makes near-coplanar faces shimmer. P3's 0.05 m (0.18 stud) protrusion is the safe number |
| J | "같은 모양·재질끼리 배치(사실 §7)" for 20k+ parts | Unverified | F10: only old staff posts; facts §7 says basic-part instancing was "will take a while" in 2017. Plausible, not a budget argument |
| J | `CastShadow=false` because "GlobalShadows 복셀 4 stud" | Reason wrong, action right | 4-stud voxels are the Voxel/ShadowMap legacy; under Realistic the sun is shadow-mapped; `CastShadow=false` still cuts shadow-pass work (docs) |
| J | `StreamingEnabled` off; fallback radius 1200 | Risky | F4: Not Scriptable, hand-set; 1200 < 2,000-stud span → far cell unloads |
| E.2/E.3 | ≈ 255 signs/cell, `MaxDistance 300`, `TextScaled` | Risky | Facts §1: the lever is glyphs on screen; on 길주로 8 tall blocks × ~36 panels sit inside 83 m of each other → 200+ GUIs in range, not "a few". Use 150–200 for upper-floor bands |
| F | wires = 3 Cylinders/span (138/cell) | OK, costly | Cylinders are ~100 tris each vs 12 for a Block; P3's 2 Blocks/span is cheaper and identical from 10 m |
| K.4 | `Pole` = Cylinder + `Angles(0,yaw,0)*Angles(0,0,90°)` | Consistent with F9 | Forum convention; one-part check needed |
| A.4 | `Cobblestone`, `CeramicTiles`, `Plaster`, `Granite`, `RoofShingles`, `ClayRoofTiles`, `LeafyGrass`, `Fabric`, `Sand` | Correct | All in the measured `Enum.Material` list (facts §5) |
| K-3, D.1 | no `Texture`, no `Glass` (hides SurfaceGuis) | Correct | Facts §1/§2 |
| J | chunk 250 / 20–25 KB, warn line raised to 25 KB | Unmeasured, test planned | F11 |
| B | wedge axis conventions | Matches facts §4 | Measured, not documented — the one-roof test is right |
| E.4 | hex codepoints + `utf8.char` | Correct | Facts §3 |

## 2. Claim audit — Proposal 2 (budget)

| Section | Claim | Verdict | What the facts say |
|---|---|---|---|
| F5–F9, B7 | vertical Cylinders (poles 11 m, lamps 9 m, trunks, bollards, tank) with only yaw `r` in the literal | **Unspecified** | F9: Cylinder length is X → every pole lies flat unless Python emits a roll or Builder applies one. K says "class by shape" and nothing about a roll. Adopt P3's rule (Size = (h, dia, dia), fixed 90° roll) |
| F5 | Beams: `CurveSize0/1 = −1.5` for sag, `Color (35,35,35)` | Risky / wrong type | F3: sag direction = Attachment RightVector; works only with the attachment unrotated on the rolled pole — undocumented in the design. `Beam.Color` must be `ColorSequence.new(...)`. Undocumented on-screen beam cap (facts §9); 68/cell, ~200 for 3 cells |
| C3 | windows = `Texture` with alpha, 3 PNGs uploaded once | Risky | Docs: decals/textures "don't batch well and introduce additional draw calls" → 279 Textures/cell (my count), ≈ 960 over 3 cells, against the docs' 1,000-draw-call example budget (visible subset counts, but a 길주로 vista sees 100–200 textured faces + ~150 sign GUIs). F8: moderation visibility conflicting; the 3 PNGs must be hand-drawn (no tool makes them — facts §2 `generate_texture` can't) |
| C3/N1 | tiling exact-fit, `Face` mapping Front=−Z … | Correct | F7; origin corner irrelevant because tiles divide the face exactly and body height = F·fh |
| J/K, Q9 | "StreamingTargetRadius ≥ 2,400" | Unverifiable | F4: no documented max, Not Scriptable |
| Q2 fallback | "SurfaceGui grid of dark Frames" | Wrong fallback | Facts §2: world-space GUI grid is the anecdotal failure case; the fallback is opaque window parts (P1/P3) |
| B hip | 2 WedgePart `(Lx−Wz, H', Wz/2)` + 4 Corner `(Wz/2, H', Wz/2)` with H' = overhang-adjusted rise | Minor | Ridge length right; H' over run Wz/2 steepens hips vs gables (no overhang on hips) |
| F6 | lamp head `Neon` | Aesthetic risk | Docs: Neon "appears to glow", Bloom (0.3) amplifies → lamps look lit at 15:00; use SmoothPlastic (P1) |
| E8 | `Font.fromEnum(Enum.Font.GothamBold)`, `SurfaceGui` settings, `MaxDistance 300` | Correct | Facts §3 (Hangul always Noto CJK fallback) |
| A3 | `Sandstone`, `Slate`, `CeramicTiles`, `Plaster`, `Granite` | Correct | Facts §5 |
| H | 심원고 Manual ≤ 2,000 parts, 부흥중 ≤ 500 | Over-allocated | A 4-box main block + Textures + bands + fence/trees is ≈ 300–500; 2,500 is 15 % of the whole 3-cell plan |
| C7 | opaque "glass" = `SmoothPlastic` + `Reflectance 0.25` | Correct | Reflectance is a BasePart property, any material |
| K | `Builder.model` with no destroy; one `:Destroy()` kept | Correct | test_versions L102-108 stays green |
| F2 | markings 0.02 m (0.072 stud) thick | Correct | ≥ old 0.05 minimum anyway |

## 3. Claim audit — Proposal 3 (data)

| Section | Claim | Verdict | What the facts say |
|---|---|---|---|
| C | windows = `Glass` at Transparency 0, "no transparency cost, nothing behind it" | **Unverified (biggest risk in P3)** | F6: opaque by definition, but whether it takes the opaque batching path is not documented; Glass also has strong sun specular (bug threads "extreme sun reflections") and no refraction on mobile (irrelevant here). One A/B test decides; fallback is one table entry (`SmoothPlastic` + Reflectance) |
| B | `Part.Shape = Enum.PartType.Wedge/CornerWedge` equals `WedgePart`/`CornerWedgePart` geometry | Plausible, unmeasured | F1: enum exists; same-mesh assumption follows from Studio's Insert behaviour; their test 1 covers it |
| B | corner-wedge yaw table (+X,−Z)=180°, (+X,+Z)=90°, (−X,−Z)=270°, (−X,+Z)=0° | **Verified by rotation math** against the facts §4 apex (+X,+Y,−Z)/slopes toward −X,+Z: each apex lands on its ridge end, slopes face outward | Only the underlying measurement is unofficial |
| F | "Cylinder ⇒ axis vertical, Size (h, dia, dia), fixed 90° roll" | Consistent with F9 | Means no horizontal cylinders ever; P3 is self-consistent (wires are Blocks) |
| F | markings 0.02 stud thick at `TOPS.road + 0.011` | Renders (F2), z-fight risk | Top face 0.021 stud above the slab → shimmer at 50 m+. Use 0.05 thick, centre +0.03 (P1 N.11 numbers) |
| J | "≈ 750 signs total, MaxDistance 300 → ~50 on screen" | Underestimate | 8 tall blocks × 21 GUIs within 83 m of each other on 길주로 = ~170 in range at one spot + GF bands; set 150–200 for per-floor bands |
| J | "batched by shape+material (color does not break batching)" | Old staff post | F10 — same caveat as P1 |
| J | trees 280 parts/cell | Data overcount | Sidewalks exist only on 길주로 + 계남로 (`sidewalk_sides`) → 64 trees × 2 = 128 parts; poles/wires 210 → ~166; markings 70 → ~32 (4 residential ways + 길주로 dashes). Street total ≈ 900, not 1,180 |
| A7 | parapet = 0.30 m cap ring, "reads the same" | Aesthetic | From a 1.7 m eye a 3F roofline is 10 m up: a 0.8 m ring is the same 1 part and matches photos; keep 1 ring, make it 0.8 m |
| I | `LightingStyle` by hand, delete DepthOfField | Correct | F5, facts §8 |
| E | `SourceSansBold`, hex codepoints, `SurfaceGui` settings | Correct | Facts §3 |
| K | chunk 250 / 30 KB after one timing test | Unmeasured, test planned | F11 |
| F | crowns `Grass` material | Minor | `LeafyGrass` is the volumetric-looking one; same cost |

## 4. Independent part / instance estimate

Archetype mix I used for cell 1 (116 bodies after dropping the 6 zero-area duplicates): villa-house 69, villa-shop 20 (storefront notes), tall commercial 7–10F 8 (11171255, 11171885, 11184538, 11188641, 12403717, 11185986, 11185995, 11201645), low public 2 (주민센터 2F, 중동샛별 4F), park/small 1F 4, fence/booth structures 5, school-yard structures 4 (11215390/91/93, 11214902), unknown 11201923 1, schools 3 (심원고 main, wing, 부흥중). Roof mix: flat 73 %, hip 22 %, gable 4 %, shed 1 %. Streets: living 440 m, residential 437 m, service 598 m, tertiary 127 m, pedestrian 111 m; sidewalks on 길주로 + 계남로 only (223 m × 2 sides); 49 utility-pole slots at 30 m; 19 in-cell junctions. Three-cell scaling: raw V-World rows are 122 / 172 / 68 → **362 records (~340 bodies)**; the proposals' "400" is the upper bound — both shown.

| | P1 realism | P2 budget | P3 data | Hybrid (§5) |
|---|---|---|---|---|
| villa-house parts | 51 (details-driven: stair 23 %, bay 8 %, balcony 9 % from notes; windows 29 on 4 faces; yard 8.3) | 20 (+2.8 Textures) | 40 (24 windows) | 30 (15 windows, 2.5 faces) |
| villa-shop parts | 46 | 15 (+3 GUI/3 TL) | 35 (+3 signs) | 27 (+3 signs) |
| tall commercial parts | 103 (36 sign parts) | 26 (+3 Tex, 14.5 GUI, 25 TL, 6 UIList) | 69 (21 signs) | 60 (18 signs) |
| low public / small 1F / structure / yard / unknown | 45 / 10 / 5 / 5 / 5 | 15 / 10 / 1 / Manual / 10 | 17 / 11 / 1.5 / 12.5 / 30 | 15 / 10 / 1.5 / 12 / 20 |
| schools | Auto 3 × 105 + Manual 290 | Manual 2,500 (budget) | Manual ≈ 500 (generated 300 + hand 200) | Manual ≈ 500 |
| **cell 1 building parts (Auto)** | **5,760** | **1,970** | **4,180** | **3,300** |
| cell 1 street parts | 1,390 | 905 | ≈ 900 (their 1,180) | ≈ 1,000 |
| slabs (existing) | 41 | 41 | 41 | 41 |
| **cell 1 parts incl. Manual** | **≈ 7,480** | **≈ 5,420** | **≈ 5,620** | **≈ 4,840** |
| cell 1 non-part instances | ≈ 660 (330 signs) | ≈ 975 (279 Tex + 180 GUI + 264 TL + 48 UIList + 68 Beam + 136 Att) | ≈ 460 (230 signs) | ≈ 480 |
| **cell 1 instances** | **≈ 8,140** | **≈ 6,400** | **≈ 6,080** | **≈ 5,320** |
| 3 cells, 362 records | ≈ 21,400 parts / 23,300 inst. | ≈ 11,900 parts / 14,700 inst. | ≈ 16,400 parts / 17,800 inst. | ≈ 13,800 parts / 15,200 inst. |
| 3 cells, 400 records | ≈ 24,500 parts / 26,500 inst. | ≈ 12,200 parts / 15,100 inst. | ≈ 18,000 parts / 19,600 inst. | ≈ 15,000 parts / 16,500 inst. |
| non-batching instances, 3 cells | ≈ 2,000 (signs) | ≈ 960 Textures + ≈ 620 SurfaceGui + ≈ 200 Beams | ≈ 1,400 (signs) | ≈ 1,400 (signs) |
| execute_luau calls, 3 cells (their chunking) | ≈ 93 (250/chunk) | ≈ 120 (100/chunk) | ≈ 66 (250/chunk) | ≈ 60–150 |

Own-arithmetic check: P1's J (7,600/cell, 22–24k) and P3's J (5,500/cell, 17k) hold; P2's 17.5k holds (my 15k is lower only because of the 362-record scaling). P3's street line overcounts trees/poles by ~280.

**Budget verdict** (NFR U2-S3 ≤ 30,000 instances; anecdotes: ≤ 13k "no impact", 30–50k "older PC lags"; docs' example 1,000 draw calls / 1M tris):

- All three stay under 30k. Triangles are not the issue for any of them (worst case P1: ~25k Blocks/Wedges ≈ 300k tris + ~700 Balls/Cylinders ≈ 150k tris).
- **P1** lands at 21–25k parts (~15–25 % reserve), almost entirely ≤ 1 m window plates with Reflectance on all four faces, and rests on the unverified batching claim (F10). It is the only proposal that would need the J-ladder cuts before the 3-cell measurement is even run.
- **P2** has the fewest parts (12k) but moves cost into ~960 Textures + ~620 SurfaceGuis + ~200 Beams, which are exactly the instance types the docs say do not batch, and adds an upload/moderation dependency (F8) and the unspecified pole roll (§2).
- **P3** (16–18k parts, nothing external) is the safest on paper **provided** opaque Glass behaves as an opaque material (F6, test T2); with SmoothPlastic windows it is safe unconditionally.
- Safe line I would hold: ≤ 20k parts and ≤ ~300 non-batching instances in any one view. P3 and the hybrid pass; P2 passes on parts but not on the non-batching count without the N3 cut; P1 fails the safe line while still under the NFR.

## 5. Best hybrid

Take P3 as the base (smallest diff, no uploads/Beams/Textures, 4 kinds, `i p m c t o` keys, dedupe via the existing `overlap_threshold`, ≤ 3 boxes, `details.DIMS` constants, Manual via a generated `manual-<id>.luau` run once) and graft:

| Topic | Take from | Change |
|---|---|---|
| Body, dedupe, multi-box, materials by `wall_color`, plinth, bands (1 ring/floor) | P3 A | parapet = P3's single ring but **0.8 m** tall (P1/P2's 4 slabs buy nothing from street level) |
| Roofs | P3 B (ridge = w−d, wedge bottom at wall top, yaw table verified above); material table from P1 B (`RoofShingles`, `ClayRoofTiles` by hash 15 %, P2 B) | add P2's 12° shed pitch; keep pitch/overhang in config as all three agree |
| Windows | P3 C parts, but material **SmoothPlastic + Reflectance 0.25** (P1/P2) until T2 says Glass is free; faces = facing + P2 C4 occlusion rule (skip a face whose 2.5 m outward point is inside another box) → ≈ 15/villa; protrusion 0.05 m (P3) not 0.02 stud (P1) | drop P1's 4-face/29-window count |
| Facade flags (shop/stair/bay/balcony) | P2 §0.1: note-keyword regex + crc32 fallback, **no new `details` table/file/CLI** (P1 K-2 is the largest new code surface in any proposal; add `details/<cell>.json` only if specific houses look wrong) | |
| Ground floor, yard, gate | P3 D (5–6 parts) | P1 D.2's 11-part yard kit (globe lamps, 2 shrubs, return walls) only if FPS headroom remains after cell 3 |
| Signs | P3 E (hex codepoints, 6 palettes, ≤ 5 sign floors × ≤ 3 panels, back-to-back 돌출) + P2 E6 name tables/ban list test | `MaxDistance` 200 for per-floor bands, 300 for GF; skip P1's pole signs/banners/rooftop letters (YAGNI) |
| Streets | P3 F (Blocks for wires, vertical-cylinder rule, car 2 parts) + P2 F6 lamp/tree offset so they alternate + P1 F school-zone guard fence + yellow/white crosswalk inside `school_zone_m` | markings 0.05 stud thick, centre +0.03 (P1 N.11); no Beams, no Neon heads |
| Intersections | P3 G (junction/crosswalk/sidewalk split) + P2 G2 alley-mouth crosswalk | corner radius 0 (all three) |
| School | P3 H + P2 H's generated `manual-<id>.luau` into `Workspace/Manual/<id>` with `BuildingId` on the Model; `Builder.model` with no destroy (P2 K) | budget ≈ 500 parts, not 2,500 |
| Budget enforcement | P2 §0/P5-8: `building_part_max`, `cell_street_part_budget`, manifest `parts_total`/`instances_total`/`budget_ok` | P3 P5-13 bounds become these config keys |
| Chunking | P2 Q7 first (100 items / 15 KB warn), raise to 250 / 30 KB only after T4 | |
| Lighting | P2 §I values, set by hand (F5), recorded in BR like U2 BR-6.5 | `StreamingEnabled` stays off; radius is Not Scriptable, decide after the 3-cell walk |
| Tests | P3 L ids (P5-1…16) + P2 P5-8 budget + P1 P5-18 school zone | |

Expected: ≈ 4.8k parts / 5.3k instances per cell, ≈ 15k parts / 16.5k instances for 3 cells at the 400-record bound (table above), zero external assets, 2 new Builder mechanisms only (`Shape`+roll, sign GUI with the 4-line hex decoder).

## 6. Five Studio tests to run first (all inside `MCP_Test`, Build and Test only, `.rbxl` copy first)

| # | Test | Pass | Fail → |
|---|---|---|---|
| T1 Shapes & axes | One chunk: 12×10 m box with gable, another with hip (P3 yaw table), one shed at 12°, one vertical Cylinder Size (10, 0.3, 0.3) m with the 90° roll, one Ball; read back each part's `CFrame`/`Size` via `execute_luau` and `screen_capture` from azimuth 45° and 225° with explicit `camera_position`/`look_at_position` | Ridge/apex y = y0 + tan(pitch)·(d/2+o) ± 0.05 stud for all 6 hip parts; no visible gap or protrusion at hip corners/eaves in both captures; cylinder's world AABB height = 36 ± 0.1 stud (stands up) | fix the 4 corner yaws / roll sign once in `layout.py`, then P5-3 guards them |
| T2 Window material A/B | Generate 4,000 plates 1.6×1.4×0.1 m on a 100×40 grid twice: `Glass` Transparency 0 vs `SmoothPlastic` Reflectance 0.25; camera sees the whole grid; read frame time with the `rbx-perf-profiling` skill / MicroProfiler, Studio in front | Both ≥ 60 FPS and Glass frame time ≤ 1.1 × SmoothPlastic; no refraction/translucent-queue artefacts | windows stay SmoothPlastic (one table entry) |
| T3 Signs | 21 SurfaceGui signs on a 7F mock (hex-decoded Hangul, `PixelsPerStud 50`, `TextScaled`, `LightInfluence 1`) + 20 GF band signs within 80 m, `MaxDistance` 200/300 | No tofu (U+FFFD boxes) in the capture; 8-char name readable at 20 m; ≥ 60 FPS looking down the strip; signs pop out beyond MaxDistance | `MaxDistance` 150 for bands, names ≤ 8 chars |
| T4 Chunk timing | One synthetic 250-item chunk (≈ 25 KB) through `execute_luau` with `os.clock()` around `Builder.add` | < 100 ms wall time and the MCP call returns; a second 100-item chunk < 40 ms | keep `chunk_size 100`, `CHUNK_WARN_BYTES 15_000` |
| T5 Full-cell FPS + z-fight | Build cell 1 with the hybrid (≈ 4.8k parts), run `verify`, walk 계남로 → 계남로242번길 → 옥산로113번길 → 길주로 for 60 s with Studio in front; captures at 10 m and 80 m of a marking, a window row and a floor band | avg ≥ 60, min ≥ 30, no frame > 1 s (U2-NFR-P4); no shimmering surface in the 80 m captures | ladder: side-face windows off → `car_spacing_m` 12 → `tree_spacing_m` 10, before touching StreamingEnabled |

Sources: [PartType enum](https://create.roblox.com/docs/reference/engine/enums/PartType) · [Improvements to Part Shape & Size](https://devforum.roblox.com/t/improvements-to-part-shape-size/2443389) · [Beams](https://create.roblox.com/docs/effects/beams) · [Beam.CurveSize0](https://create.roblox.com/docs/reference/engine/classes/Beam/CurveSize0) · [Instance streaming](https://create.roblox.com/docs/workspace/streaming) · [Workspace class](https://create.roblox.com/docs/reference/engine/classes/Workspace) · [Reduced Minimum Part Size](https://devforum.roblox.com/t/reduced-minimum-part-size-released-everywhere/1394733) · [Introducing New Material: Glass](https://devforum.roblox.com/t/introducing-new-material-glass/64231) · [Glass lacks refraction on certain devices](https://devforum.roblox.com/t/glass-lacks-refraction-on-certain-devices/3666977) · [Texture class](https://create.roblox.com/docs/reference/engine/classes/Texture) · [Textures and decals](https://create.roblox.com/docs/parts/textures-decals) · [Texture Offsets 2019](https://devforum.roblox.com/t/texture-offsets-2019/314381) · [Decals Get Stuck With Pending Moderation](https://devforum.roblox.com/t/decals-get-stuck-with-pending-moderation-image/206155) · [Decal uploading approvals are frozen](https://devforum.roblox.com/t/decal-uploading-approvals-are-frozen/2998360) · [Light sources (LightingStyle)](https://create.roblox.com/docs/effects/light-sources) · [LightingStyle is not a valid member of Lighting](https://devforum.roblox.com/t/lightingstyle-is-not-a-valid-member-of-lighting/3908044) · [Cylinder radius/height thread](https://devforum.roblox.com/t/how-do-i-get-the-radius-and-height-of-an-existing-cylinder/1843043) · [Part Instancing pre-release](https://devforum.roblox.com/t/part-instancing-pre-release-announcement/130333) · [Transparency and CFrame don't mix (batching)](https://devforum.roblox.com/t/thansparency-and-cframe-at-the-same-time-dont-mix-for-large-amounts-of-parts/12758) · [Improve performance](https://create.roblox.com/docs/performance-optimization/improve)