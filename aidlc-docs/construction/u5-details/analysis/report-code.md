# U5 extension-point map of the builder code (read-only survey, 2026-10-13)

Scope read: `src/layout.py`, `src/build_luau.py`, `studio/Builder.luau`, `src/judgement.py`, `src/common.py`, `src/db.py`, `config.toml`, `tests/test_layout.py`, `tests/test_build_luau.py`, `tests/test_versions.py`, `tests/generators.py`, `tests/test_common.py` (config part), `data/build/8930e0af13bffff/manifest.json`, `overrides/8930e0af13bffff.json`, U2/U4 business rules, U4 code summary, U2 NFR requirements, `src/cells.py` (street-furniture parsing), inception unit docs. DB queried with sqlite3 and a scratch shapely script. No project file was modified; no Studio tool was called (only tool schemas were loaded).

---

## 1. Current pipeline: Item → Luau literal → Part

### 1.1 `layout.Item` (`src/layout.py` L87–103)
Frozen dataclass: `kind, name, group, seq, cx, cy, cz, sx, sy, sz, yaw_deg, material, color, attrs`. `group`/`seq` exist only for ordering. `_item()` L106–111 is the single constructor: looks up `LOOKS[kind]` (KeyError for an unknown kind), applies `fmt()` (3 decimals, no −0, L36–39) to every number, copies `attrs`.

- `LOOKS` L25–28: 6 kinds → `(material, rgb)`: building Concrete (200,200,205), road Asphalt, path Pavement, sidewalk Concrete, ground Grass, spawn SmoothPlastic.
- `ORDER` L29: `ground 0, road 1, path 2, sidewalk 3, building 4, spawn 5`. `order_items` L114–116 sorts by `(ORDER[kind], group, seq, name)`. `TOPS` L23 slab top heights (0.2/0.3/0.4 stud).
- `chunk_items` L119–123: slices in order, `size ≥ 1`, no empty chunk.
- Producers: `building_item` L155–188 (one box, attrs `BuildingId, CellId, Source, HeightM, FitRatio, [Floors], [HeightBasis, WallColor, FloorsBasis, Review]`; color = `judgement.wall_rgb(eff.wall_color)` L174), `road_items` L218–229 (returns `[]` for kinds other than road/path, L220), `sidewalk_items` L243–259, `ground_item` L264–273, `spawn_item` L285–295.

### 1.2 Luau literal (`src/build_luau.py`)
- `SAFE_TEXT` L36 `[A-Za-z0-9:#_.\-]{1,100}`; `luau_string` L42–46 refuses anything else (no escaping ever); `luau_number` L49–54 fixed 3-decimal notation. `TEXT_ATTRS` L37 `("name","Source","HeightBasis","FloorsBasis","WallColor","Review")` is re-checked in `plan_cell` L121–122 (building dropped with a warning), feature ids at L133–135.
- `item_literal` L57–74: keys `k n x y z w h d r`; buildings add `s e q [f] [b a c v]`; L66–67 asserts `attrs.CellId == cell` and `attrs.BuildingId == item.name`. Measured sizes in the real files: building literal **164 B avg** (176 B with all U4 keys), road 89, sidewalk 94, path 87, ground 79, spawn 69.
- `render_chunk` L77–92: header = sorted `LOOKS` + per-chunk `walls={[name]={r,g,b}}` (L80–82, keys through `luau_string`), `require(ServerStorage.MapBuilder)`, `CELL`, `ITEMS`; chunk 1 emits `Builder.begin(CELL)` L88–89; every chunk `Builder.add(CELL, ITEMS, LOOKS)` L90; last chunk `return Builder.finish(CELL)` L91. Header+footer ≈ 580–650 B.
- Chunking: `cfg["chunk_size"]` (default 50, `common.RANGES` L100 int 1..1000), `CHUNK_WARN_BYTES = 10_000` L35, warning at L148–150. **Headroom today: chunk-002/003 are 9,020/8,999 B** (manifest L34–35) — roughly 20 B per building before the warning fires. Any new building key hits this first.
- `plan_cell` L106–164: buildings sorted by id, `effective_building` per building L119, features sorted by id, roads/paths then sidewalks, spawn, `order_items`, chunks, manifest counts L151–158 (`items_<kind>` iterates `layout.ORDER`, so a new kind appears automatically), `poor_fit` list L152–153, manifest `config` subset L161–162.

### 1.3 `studio/Builder.luau`
- `FOLDER_OF` L21–23 kind → folder name; `checkCell` L29–34 (15 hex chars); `manualIds` L56–65 collects `BuildingId` attributes from **all descendants** of `Workspace/Manual` (parts or models).
- `begin` L68–86: the only `:Destroy()` in the file (`old:Destroy()` L75) removes `Auto/<cell>`; creates the six folders and attributes `BuildComplete/Created/SkippedManual`.
- `add` L90–148: per item, `FOLDER_OF[it.k]` and `looks[it.k]` must both exist else `error("unknown kind")` L96–100; **Manual wins** at L101–102 (`it.k == "building" and manual[it.n]` → `skipped += 1`, nothing built); L104 `Instance.new(it.k == "spawn" and "SpawnLocation" or "Part")`; L106–110 Anchored, smooth surfaces, `Size = (w,h,d)`, `CFrame.new(x,y,z) * CFrame.Angles(0, rad(r), 0)`; L111 `Enum.Material[look[1]]`; L112–117 color from `looks.walls[it.c]` else kind color; L118–131 building attributes; L132–137 spawn props; L139–144 stage then parent (one `.Parent` per part); L145–147 counters.
- `counts` L150–156 = `#folder:GetChildren()` for every child folder; `verify` L172–205 compares `expected["items_"..kind]` with `found[folder] (+ skipped for building)` for every kind in `FOLDER_OF` (L180–186), reads back `position/size/right` for sample names found by `FindFirstChild` in any folder (L187–203).
- Guarded by `tests/test_versions.py` L102–108: no `loadstring/HttpService/RequestAsync/GetAsync/PostAsync/getfenv/setfenv`, and **exactly one `:Destroy()`**, which must be `old:Destroy()`.

---

## 2. What a building carries today

### 2.1 Final values — `judgement.EffectiveBuilding` (`src/judgement.py` L122–140)
`building_id, floors_above, floors_basis (override|register|photo_count|None), floors_status, height_m, height_basis (override|register|from_floors|photo_geometry|default), wall_color (12 names + other), wall_basis, roof_shape (flat|gable|hip|shed|other, L15), roof_basis, flags (tuple ⊂ FLAGS L17), register_floors, register_height_m, photo_floors, photo_confidence, osm_height_m, osm_levels`. Priority override > photo > register > default (L147–222). `wall_rgb` L225–228 maps names to RGB from `cfg["wall_colors"]` (unknown/other → light_gray). Only `height_m`, `floors_above`, `wall_color` reach Luau today; `roof_shape` is computed but **not emitted** (U4 BR-5.3 "U5 uses it").

### 2.2 Building row (`db.TABLES["buildings"]` L31–35)
`building_id, cell_id, source, outline (JSON [[lat,lon],...]), centroid (JSON), gis_key, osm_id, name, osm_tags (JSON), floors_above, floors_below, height_m, usability_code, approval_date, building_area, osm_height_m, osm_levels, status`. `rows_in_cells` L157–168 decodes JSON columns.

First cell (122 ok buildings, all `source=gis`):
- Outline vertices: min 4, max 44, mean 6.9; 63 have ≤ 5, 13 have > 8.
- `usability_code` (V-World use code, standard building-use order; verify labels before relying on them): `01000` ×89 (detached housing), empty ×19, `10000` ×7 (education), `14000` ×2 (office), `09000` ×2, `11000`, `04000`, `03000` ×1 each. → ground-floor-shop vs house can be driven by code + estimate notes.
- `name` non-empty: 20. `osm_tags` present: 10 (7 with `building:levels`, 2 `amenity`, 0 `shop`, 0 `roof:*`). `approval_date` present: 102 (1990s 87, 2000s 14, 2010s 1). `building_area` null/0: 19.
- Floors: None 16, 1:1, 2:6, **3:84**, 4:2, 5:3, 7:6, 8:1, 9:1, 10:2.
- Streets in cell: road 17 (living_street 6, service 5, residential 4, tertiary 1, tertiary_link 1), path 1 (pedestrian). **Zero `crossing/tree/street_lamp/bench` rows** although `cells.py` requests and keeps them (NODE_KINDS L36–37, `parse_osm` L179–184, Overpass query L113–115): OSM has none in this bbox. U5 street furniture must therefore be **rule-generated along road pieces**, not read from data.

### 2.3 Estimates in `overrides/8930e0af13bffff.json` (122 estimates, 0 overrides)
- `roof_shape`: flat 45, hip 27, gable 5, shed 1, null 44. `wall_color`: red_brick 37, brown 31, light_gray 28, beige 8, orange 3, dark_gray 3, white 2, pink 1, null 9. `confidence`: medium 82, low 33, high 5, null 2. `floors_seen` null 6; `height_est_m` set 4.
- `note` (free text, all 122 non-empty) keyword counts: house/detached 68, brick/tile 84, shop/commercial/restaurant 28, stair tower 28, glass 27, roof 21, window/bay 20, tree 16, school 14, fence/yard 12, awning/canopy 4, sign 3, apartment 1, balcony 1; **pilotis/필로티 0, rooftop/옥탑 0, parking/주차 0, band 0**. Notes contain spaces → cannot pass `SAFE_TEXT`; they are hints for a human/Claude to turn into structured U5 fields, not machine input.

---

## 3. Three ways to extend, with cost

Common ground: today 163 parts/cell at 60 FPS; U2-NFR-S3 budget ≤ 30,000 parts for 3 cells; U2-NFR-P2 one call < 1 s (9 KB chunk measured 2–4 ms); `execute_luau` guidance: `task.wait()` per ~1000 instances, one small `.Parent` per chunk — current chunks are far below that.

### (a) New item kinds, one Part each (roof wedge, band, door, sign, lamp, tree, crossing, curb, …)
- `layout.py`: add kinds to `LOOKS` and `ORDER` (plus `TOPS` for slabs); new pure producers, e.g. `roof_items(box, eff, frame, cfg)`, `band_items(...)`, `lamp_items(road_pieces, cfg)`, each returning `Item`s with `group = building_id` (or feature id), `seq` for in-group order. A `shape` is needed for wedges: either a new `Item` field (default `"Block"`) → literal key `p` → Builder `Instance.new("Part")` + `Shape = Enum.PartType[p]` (Block/Wedge/CornerWedge/Cylinder/Ball), or kind → class table like the spawn special case at Builder L104.
- `build_luau.py`: `item_literal` unchanged for non-building kinds (sub-items should **not** carry `s/e/q` so L64 branch stays building-only); `plan_cell` appends the new producers; `by_kind` picks them up via `ORDER`.
- `Builder.luau`: `FOLDER_OF` entries (`Roofs, Facades, Signs, Furniture`…), optional `Shape`, attribute `BuildingId` on sub-parts (new key `i=`), Manual check extended to `manual[it.i or it.n]` so a hand-built building also suppresses its roof/sign.
- `verify`: counts per folder automatically correct (`items_<kind>` from `ORDER`); add nothing.
- Bytes: ~70–95 B per item; a chunk of 50 mixed items ≈ 4–5 KB. Items per cell explode: ≈ 130 bldg × (1 box + ~2.5 roof + ~3 bands + 1 door + 1 sign) ≈ 1,100 + streets/lamps ≈ 1,250 → 25 chunks/cell at 50, ~13 at `chunk_size = 100` (≈ 9 KB). 3 cells ≈ 4,000–5,000 parts ≪ 30,000.
- Tests: one P5-x per producer in `test_layout.py` (coverage of the box footprint, roof apex height = f(depth, pitch), band Y positions = floor index × floor height, lamps spacing ≤ cfg), order/determinism reuse `test_p2_8_*`.
- Determinism: pure; only risk is any "variety" choice — must hash `building_id` with `zlib.crc32`/`hashlib`, never `hash()` (salted per process) or `random` without a fixed seed.
- Roof part counts with primitives: gable = 2 wedges; hip = 2 wedges + 4 corner wedges (6); shed = 1 wedge; flat = 0 or 1 parapet slab. Windows as parts would be 3-floor × 3 × 4 faces ≈ 36/bldg → 14k parts — **do not**; use tiled `Texture` instances (see b).

### (b) Building item carrying a sub-part list, Builder composes under a Model
- `layout.py`: `Item` gains `parts: tuple[SubPart, ...] = ()` (SubPart: `shape, dx, dy, dz, sx, sy, sz, [material], [color], [texture_id], [text]`, local to the box frame). Python still computes every number (BR-7.5 kept).
- `build_luau.py`: `item_literal` emits `p={{...},{...}}` nested tables. Test L156 counts `{k="` as items, L164 regex `\{k="(\w+)",n="([^"]+)"` — nested tables must use a different first key (e.g. `t=`), else those tests change.
- `Builder.luau`: when `it.p` exists create a `Model` named `it.n` holding the box (PrimaryPart) and children; attributes and Manual check stay on the Model; `verify` still counts one child per building → `items_building` unchanged; add attribute `Parts = #it.p + 1` and a verify sum if sub-part count must be checked. `Texture` children: `Texture = "rbxassetid://" .. id` built in Luau from a **numeric** id (`/` is not in `SAFE_TEXT`, so the full URL can never be sent). Sign: `Part + SurfaceGui + TextLabel` (3 instances, 1 part).
- Bytes: box 164 + ~60–80 B per sub-part; roof 2–6 + bands 3 + door + sign + 4 textures ≈ 12 sub-parts → **~900–1,100 B per building**; 50 per chunk ≈ 50 KB → either `chunk_size` ≈ 9 (config.toml and `DEFAULTS` must match, `test_common` L150–156) or raise `CHUNK_WARN_BYTES` with an NFR note (measured 9 KB → 2–4 ms; 50 KB is plausibly < 50 ms but unmeasured). Chunk count per cell stays ≈ 15–20.
- Determinism: same as (a); sub-part order fixed in Python.
- Cost: medium. One nested literal format, one Model path in Builder, `item_literal`/order tests adjusted.

### (c) Recipe: Python sends parameters, Luau composes geometry
- Literal grows only ~40–80 B per building (`o="hip"`, `f=3`, `g=1` ground-floor shop, `t="BAKERY-12"`, `w="3x2"`): chunk-002 goes from 9.0 to ~11–12 KB, still needs `chunk_size` 40.
- But geometry moves into Luau: breaks BR-7.5 (and the Builder header L4–5 "It does no geometry"), has no CI (U2-NFR-M3: Luau is not analysed), property tests cannot cover roof/window placement, and the `require`-cache trap (CLAUDE.md) means a stale module silently produces different parts for identical chunks → BR-6.4 "same result" becomes unverifiable from Python. `verify` would need the expected sub-part count computed by a second copy of the recipe in Python. Only defensible for purely cosmetic non-geometry (`Texture` tiling on a face, `SurfaceGui` text), where Python passes "which face, which texture id, tile size".

**Recommendation for the functional design**: (a) for everything that is not a building (lamps, trees, crossings, curbs, intersection patches) because `verify`/manifest/order already handle new kinds for free; (b) for buildings, with the box as PrimaryPart of a Model so `BuildingId`, Manual priority and `items_building` do not change; windows via tiled `Texture` (not parts); (c) only in the cosmetic sense above. Expect ≈ 8–10 parts + ≈ 6 non-part instances per building, ≈ 4–5k parts for 3 cells.

---

## 4. Multi-box footprints for `poor_fit`

Current: `outline_to_box` L138–152 = `MultiPoint(...).minimum_rotated_rectangle`, `fit_ratio = area/rect.area`, flagged below `poor_fit_ratio = 0.8` (config L50), box still built (BR-2.5).

The 9 poor-fit buildings (DB `json_array_length(outline)`, shapely on the same metre frame; "greedy split" = recursive cut along a rect axis at the vertex projection minimising the children's rect area, ≤ 3 levels, scratch script only):

| building_id | name | verts | area m² | fit | simplify 0.5 / 1.0 m verts | ~90° angles | greedy split parts (union fit, overshoot) |
|---|---|---|---|---|---|---|---|
| gis:11036833 | 부흥중학교 | 26 | 2,024 | 0.46 | 24 / 23 | 20/26 | 5 (0.82, +21 %) |
| gis:11171255 | (7-floor commercial) | 9 | 1,507 | 0.62 | 9 / 9 | 5/9 | 3 (0.90, +11 %) |
| gis:11171875 | – | 8 | 112 | 0.75 | 8 / 6 | 6/8 | 2 (0.88, +13 %) |
| gis:11180755 | – | 8 | 118 | 0.74 | 7 / 7 | 4/8 | 2 (0.90, +11 %) |
| gis:11185213 | 심원고등학교 | 39 | 2,517 | 0.54 | 16 / 12 | 12/39 | 4 (0.96, +5 %) |
| gis:11215390 | – (area 0 in register) | 8 | 134 | 0.22 | 8 / 8 | 8/8 | 2 (0.95, +5 %) |
| gis:14944897 | 심원고등학교 | 44 | 2,182 | 0.44 | 28 / 12 | 12/44 | 3 (0.95, +5 %) |
| gis:15839722 | – | 13 | 34 | 0.72 | 7 / 5 | 10/13 | 3 (0.78, +27 %) |
| gis:16821018 | 부흥중학교 | 38 | 1,695 | 0.39 | 30 / 28 | 29/38 | 4 (0.89, +12 %) |

- Orthogonal rectangular decomposition (sweep on an orthogonal polygon) fits 11215390, 16821018, 11036833 (≥ 77 % right angles) but not the two school buildings (12/39, 12/44 — curved/diagonal vertices) without `simplify(1.0)` + rotation to the dominant axis first; it also yields many thin slivers on 38-vertex outlines.
- The lazy rule that already works on all nine: *if fit < 0.8, split recursively along the min-rect axes at outline-vertex projections, keep the cut that minimises total box area, depth ≤ 2–3, stop when a piece fits ≥ 0.8* (≈ 40 lines of pure shapely in `layout.py`, deterministic given sorted candidate cuts and first-wins ties). Gains: two school blocks 0.54/0.44 → 0.96/0.95 with 3–4 boxes; the L-shaped house 11215390 0.22 → 0.95 with 2. 15839722 (34 m²) is not worth it (union 0.78).
- Item impact: N boxes per building → `items_building` would count boxes. Smallest change: name boxes `gis:123#0..N`, send `i="gis:123"` (BuildingId) when name ≠ id, `item_literal` L66 check becomes `a["BuildingId"] == (it.i or it.n)`, Builder L101/L119 use `it.i or it.n`. Manifest should add `buildings_built` so `verify` keeps comparing parts to parts. Alternative: give every box the same `n` (no Builder change, duplicate part names — `verify` samples by name become ambiguous).
- Property tests to carry over from P2-2: union of boxes covers every outline vertex (tolerance 0.02 stud), Σ box area ≤ single-rect area, box count ≤ max, invariance to vertex start/direction (existing tolerance style), a rectangle still yields exactly one box. Note the two school buildings and 부흥중학교 are the hand-built `Manual` candidates per BR-2.5 anyway; multi-box mainly pays for the five small ones.

---

## 5. Conventions U5 must follow

- **Property ids**: U2 used P2-1..9, U4 P4-1..16, defined first in the unit's `business-rules.md` table ("테스트할 속성") and mirrored verbatim into the code-generation plan; test names `test_p5_N_<sentence>` for properties, `test_<sentence>` for examples, file docstring listing which ids live where (`test_layout.py` L1–2). Expected values are worked out inside the test, not by calling the function under test (L2, L215–221).
- **Generators** (`tests/generators.py`): `@st.composite` strategies with plural names, geometry around `BASE` (first vertex of the cell, L19) via `offset(point, dx_m, dy_m)` L23 and `rect(center, w, h)` L29; per-unit sections (`# --- U2 Studio builder ---` L172, `# --- U4 ... ---` L198); U4 section builds rows then feeds `J.effective_building` (`building_cases` L247–250). U5 adds a `# --- U5 details ---` section (e.g. `effective_buildings()` composing `register_buildings()` + `judgements()` + `override_sets()`, `roof_shapes = st.sampled_from(J.ROOF_SHAPES)`, `road_pieces()` built from `road_features()` through `layout.road_items`).
- **Settings/seeds**: `@settings(max_examples=25..60)` on slow strategies; `CFG = common.DEFAULTS` (or `{**DEFAULTS, "chunk_size": 20}` L22 of test_build_luau); CI runs `--hypothesis-seed=${{ github.run_number }}` (ci.yml L27); acceptance runs seeds 1, 7, 42, 2026, 99999 and a mutation pass (break the code N ways, every break caught — U4 did 12).
- **Pinning** (`tests/test_versions.py`): every `src/*.py` with `# /// script` metadata pins `==` and must match `tests/requirements.txt` (h3 4.5.0, shapely 2.2.0, pytest 9.1.1, hypothesis 6.169.0, numpy 2.5.4, pillow 12.3.0, L29–55); `build_luau.py` header L1–4 pins h3 + shapely only — a new dependency (none should be needed) must go in both places; Builder.luau forbidden tokens and single `:Destroy()` L102–108.
- **Config** (`common.load_config` L115–185): unknown keys are rejected (L122–124), so every new key needs (1) an entry in `DEFAULTS` L25–88 with a comment, (2) a `RANGES` row `(min, max, is_int)` L91–103 for numeric scalars or a bespoke check for tables (merge pattern L126–129 + validation L170–177, e.g. `wall_colors`), (3) the same value in `config.toml` (`test_default_config_file_matches_the_defaults_in_code` L150–156 requires file == DEFAULTS except `spawn_*`/`school_polygons`), (4) a bad example appended to the `for bad in (...)` list L163–170, (5) if it changes the output, the key added to the manifest `config` subset (`build_luau.py` L161–162). Candidates: `roof_pitch_deg`, `band_height_m`, `sign_height_m`, `lamp_spacing_m`, `texture_ids` table, `max_boxes_per_building`.

---

## 6. What U5 must not break

1. **BR-6.4 / P2-8 same text**: `plan_cell` must stay a pure function of (rows, cfg, estimates, overrides); no timestamps (`test_p2_8_row_order…` L209 greps for ISO dates), everything sorted (`sorted(walls.items())` L82, buildings/features by id L118/L130). Any per-building "variety" (fictional sign names, window rhythm, colour jitter) must derive from a stable hash of `building_id` (`zlib.crc32`), never `hash()` or an unseeded RNG.
2. **BR-7.5 geometry only in Python**: Builder header L2–6 and test_versions L102–108 (no loadstring, one `Destroy`). Adding sub-parts/Models is fine; adding a second `:Destroy()` (e.g. to clear a Model) or any geometry maths is not.
3. **SEC2**: all text through `luau_string`; extend `TEXT_ATTRS` L37 for new attrs; keep `test_sec2_hostile_ids_never_reach_the_code` L119–131 and `test_u4_a_hostile_text…` L318–324 green. Consequences: texture references as numeric ids (`/` forbidden), sign text with spaces or Hangul needs a **separate** validated field (`SIGN_TEXT` regex with `[A-Za-z0-9가-힣 _.-]{1,20}`, no `"`/`\`/control chars, even quote count) rather than loosening `SAFE_TEXT` (`test_luau_string_returns_only_safe_text…` L52–59 asserts ASCII). ASCII-only fictional names avoid the new rule entirely.
4. **verify counts**: every kind needs matching `LOOKS`, `ORDER` and `FOLDER_OF` entries (Builder L96–100 errors otherwise; `_item` L108 KeyError); `manifest.counts.items_<kind>` is what `verify` consumes; if a building becomes several parts or a Model, decide explicitly what `items_building` counts and keep `+ skipped_manual` arithmetic (L182).
5. **Manual wins by BuildingId** (L56–65, L101): hand-built school buildings must carry `BuildingId` on the Model or any descendant; every auto sub-part of a building must be suppressed together with its box (hence `i=` key or Model).
6. **Chunk budget**: 20 B/building headroom under `CHUNK_WARN_BYTES`; any new building key forces `chunk_size` ≤ 40 (DEFAULTS + config.toml + the manifest's `config`) or a measured raise of the 10 KB line (U2-NFR-P3).
7. **Existing tests that encode the literal shape**: `{k="` counting L156, `\{k="(\w+)",n="` ordering regex L164, `test_a_building_item_becomes_a_short_table…` L91–98 (starts with `{k="building",n=`, no `CellId/BuildingId` text), `test_u4_the_colors_of_a_chunk…` L307–315 (one `walls=` per chunk).
8. **U4 contracts**: `judgement.FIELDS` L14 (4 override fields), `OVERRIDE_KEYS/ESTIMATE_KEYS` L30–31, `EXPORT_VERSION = 1` and the exact key set in `parse_export` L261 — adding U5 facts (ground-floor use, sign text, texture choice) to `overrides` changes the export schema and P4-7/P4-8 round trips; keep them in a new structure (table or `details/<cell>.json`) unless they are genuine human corrections of the four fields. `effective_building` and `roof_shape` priority (override > photo > default) are already there to consume.
9. **Studio side**: `StreamingEnabled`/place settings are not Builder's (BR-6.5); updating `ServerStorage/MapBuilder` requires Clone + Destroy of the ModuleScript (require cache); performance gate U2-NFR-P4: average ≥ 60 FPS, minimum ≥ 30, no stall > 1 s, re-measured with 3 cells at the end of U5.