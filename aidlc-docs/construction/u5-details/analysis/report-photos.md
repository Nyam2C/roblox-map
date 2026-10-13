# U5 visual survey — cell 8930e0af13bffff (중3동, 심원고 일대)

Source: `captures/8930e0af13bffff/sheets/*.jpg` (122 sheets, 1024×768, 2–4 crops each, no `__1` second sheets exist). Sample viewed: 50 sheets = all 13 buildings with `floors_above >= 5` (incl. 2 zero-area duplicates), all 16 `floors_above IS NULL`, 15 three-floor villas (every 7th of 84 + 3 light-colored ones), all 1/2/4-floor buildings except 3. DB facts (`data/map.db`, read-only): 122 buildings; floors 3 = 84, NULL = 16, 2 = 6, 7 = 6, 5 = 3, 10 = 2, 1/4/8/9 = 1–2 each; `usability_code` 01000 (single-family) = 89, 10000 (education) = 7, NULL = 19, 14000/09000 = 2 each. Existing blind judgements (`overrides/8930e0af13bffff.json`, table `estimates`): wall_color red_brick 37 / brown 31 / light_gray 28 / beige 8 / orange 3 / dark_gray 3 / white 2 / pink 1 / none 9; roof flat 45 / hip 27 / gable 5 / shed 1 / none 44. Street features in cell: `tertiary` 길주로 (oneway) + 1 tertiary_link, `residential` ×4 (계남로, 계남로242번길, 옥산로109번길), `living_street` ×6, `service` ×5, `pedestrian` path 신흥로238번길. Widths come from `config.toml [road_widths_m]` (tertiary 10, residential 6, living_street 5, service 4, pedestrian 2.5). No OSM street furniture nodes were collected (only `road`/`path` kinds in `street_features`), so everything in section 4 is a rule.

## 1. Archetypes (count estimates, ids seen)

| # | Archetype | Est. count | Seen |
|---|---|---|---|
| A | 3-floor brick 단독/다가구 house, 1994–2001, ~90–115 m² footprint, hip or flat roof, walled front yard with gate, no pilotis | ~55 of the 84 three-floor (red_brick+brown+orange judgements = ~62) | 11192647, 11198845, 11203830, 11208985, 11216743, 11216783, 11185950, 11186644, 11178530, 11081057 |
| B | 3-floor stone-veneer house (white/cream rubble granite, tan stacked stone, sandstone), same massing and era, often a round or square stair tower, gable/mansard dark roof | ~25 of 84 (light_gray 28 + beige 8 judgements minus tile-clad) | 11190349, 11214904, 11216699, 11174023, 11177783 (4F) |
| C | 3-floor gray/white ceramic-tile corner building with shop on GF, ribbon windows, flat roof | ~6–8 | 11170718, 11180755 (also judged: 11178810, 11188106) |
| D | 2-floor brick house with roof terrace railing | 5 (floors=2, 01000) | 11177608 |
| E | 7–10 floor 근린상가/officetel on 길주로, stone or tile cladding, band signs every floor, GF shops, parking under or beside | 8 (6 physical + 2 zero-area dupes 16501307, 18692828) | 11184538 (10F), 11201645 (10F officetel), 11188641 (9F), 12403717 (8F hospital), 11171255 (7F), 11171885 (7F), 11185986, 11185995 (7F) |
| F | School block 5F red brick, 1995–2002, long bar, strip windows, glazed stair tower, cantilevered concrete landings | 3 + 3 NULL entries | 11185213, 11185281 (심원고), 11036833 (부흥중), 14944897, 15358826, 16821018 |
| G | Public 2F: 중3동 행정복지센터 white tile + glass stair cylinder + X seismic bracing, car park in front | 1 (+ dupe 17639013) | 11188308 |
| H | Park facilities in the neighborhood park N of 부흥중: senior center (pink hip roof), octagonal white toilet, gazebo (정자), playground | 3 (11192750 옥산경로당 1F + NULL 11201615, 11201639) | 11192750, 11201615, 11201639 |
| I | 4F brick kindergarten-style with castellated parapet (중동샛별, usability 10000) | 1 | 11196895 |
| J | Old 5F salmon-pink apartment/school with hip roof visible N of the park (outside cell, backdrop) | 0 in cell | seen in 11201615 #1E, 11201639 #3E |

## 2. Facade vocabulary per archetype

**A. Brick villa (3F, 9.3–11.6 m, 1 floor ≈ 3.2 m; 1F sill ~0.8 m above a 0.3–0.5 m plinth)**
- Wall: clay brick, two families: dark brown/chocolate (RGB ~ 95,60,50; many with a slight purple cast) and red/orange brick (~ 170,90,60). Mortar visible at 1:1 view; use a brick material in Roblox (`Brick` with those colors). Red stripes/bands of soldier-course brick at each floor line are common (11201637, 11196895). ~20% have a stone or granite plinth band 0.5–1 m (gray 150,150,145).
- Windows per facade: 2 per floor on a 8–10 m frontage, each 1.5–2.0 m wide × 1.3–1.5 m tall, sill at 0.9 m, dark gray/bronze aluminum frames (window glass 60,80,80 tinted green). 1F windows carry white or gray steel burglar bars (방범창). Roughly 40% have a bay/bow window: a curved or boxed projection 0.4 m deep, often painted white or clad in gray panels (11216743, 11203830, 11216783). Round porthole windows ~0.6 m appear on ~15% (11185950, 11216699).
- Balconies: shallow (0.5–0.8 m) with black or dark green wrought-iron railing on 2F/3F for ~50% (11192647, 11208985, 11216783). Roof terrace with white tubular railing on 2F houses (11177608, 11186644).
- Stair/elevator: a vertical glazed strip the full height (0.8–1.5 m wide, green-tinted glass, gray mullions), straight or quarter-round, on ~40% of villas; sometimes a square brick tower rising 1 m above roof (11198845).
- Roof: hip in dark gray/charcoal (60,60,65) asphalt shingle or concrete tile on ~35%; flat with 0.6–1.0 m parapet on ~45%; a few gable/mansard with dormers. Eave overhang 0.4 m, dark fascia. Solar water heater on ~10% of roofs (11203830). Rooftop railing on flat roofs, occasional small 옥탑 (1 seen).
- Ground: no pilotis in this cell (older than the pilotis era). Instead: a front yard 2–4 m deep behind a 1.2–1.6 m wall (brick with a steel-rail top, or stone with iron grill), two brick gate posts 0.5×0.5×1.8 m with a round globe lamp, black ornamental iron gate 2.5–3 m (double leaf, often gold motifs), blue enamel address plate on the post. Yard: 1–2 round topiary shrubs (1.5 m), a pine, rose bushes climbing the fence (very frequent in the photos), potted plants, 1 car parked inside under a cover.
- Services: 1–3 AC outdoor units on the front wall per building; a red-painted gas pipe running horizontally at 1F ceiling height and up the facade (11198845, 11201621); stainless exhaust duct up the side of GF restaurants (11081057, 11174023); overhead wires attached to the facade.
- Entrance: recessed door with a small gray-shingle or arched canopy (11216743, 11216699).

**B. Stone-veneer villa (same massing)**
- Wall: white/cream irregular rubble granite (215,210,195) with dark joints (11190349, 11216699), or tan stacked ledgestone (190,160,110) (11214904 neighbor, 11177608 entrance), or sandstone cut block (200,175,130) (11201637 neighbor). Base often large round boulders (cobble wall) with white iron fence on top (11216699).
- Roof: dark gray/black mansard or steep gable with dormers, slate/shingle texture; round corner tower with conical or flat cap (11214904 #2SE, 11216699).
- Windows: same size as A; 1174023 has a Korean dark-gray tile eave strip (기와 처마, 0.4 m) at every floor line.

**C. Gray tile corner shop building (3F)**
- Wall: pale gray/white ceramic tile (205,205,200) with visible grid; ribbon windows 1.2 m tall, continuous across the facade on 2F/3F with dark frames; curved glass corner on ~half; flat roof with 0.8 m parapet; GF = shop (restaurant, real-estate), white or black band sign across the whole frontage; parking lot stripes beside.

**D. School block (F) — see section 5.**

**E. 7–10F commercial (길주로 side)**
- Wall: light gray granite panel cladding (190,190,185; 11184538, 11188641) or beige/cream tile (215,205,185; 12403717, 11171885) or white painted concrete (11201645). Floor-to-floor 3.3–3.6 m (31–35 m for 9–10F). Windows: every floor a continuous ribbon 1.6–1.8 m tall of green-tinted (60,90,85) or dark gray glass, mullions every ~1.5 m; spandrel 1.5 m of cladding. Rounded corners (11171885).
- Band signs: a 0.8–1.0 m sign band under every floor's window line on the street facade (section 3). Rooftop building-name letters on a frame.
- GF: shops with full glass fronts 3.5–4 m high, dark canopy/eyebrow 0.6 m, roll shutters (gray) when closed, "임대" posters on empty ones. Pharmacy (red cross on white) on two corners.
- Parking: a 3.5–4 m high drive-through opening under the building (11201645 #1S, 12403717 #2S, 11185986 #1S) or a ramp with a yellow/black striped barrier.
- Rooftop: stair/elevator penthouse 3 m, water tank, mechanical boxes, rooftop sign frame. AC units in rows on side walls (11171255 #1S), vertical hanging signs 3–4 stacked on the side wall.

**G. 행정복지센터**: white 10 cm ceramic tile, 2F, glass stair cylinder 4 m dia., blue banner across the top, gray X steel braces on side, asphalt car park with yellow/black parking blocks.

**H. Park buildings**: pink (225,170,170) 1F senior center with salmon-pink hip tile roof; octagonal toilet with white panel walls and brown hip roof; 6-post gazebo with brown tile hip roof; playground with red/blue/yellow equipment on rubber tiles (green/teal).

## 3. Signs

- **띠간판 (GF band)**: on every building with a shop: full frontage width × 0.8–1.0 m, bottom at 3.0–3.5 m. Colors: white bg + black text (most GF restaurants/cafes), black bg + white/red (restaurants), red/yellow (real estate, chicken), blue + white/yellow (real estate, clinic). One per shop unit; 2–4 units per 7F commercial frontage, 1–2 per villa-with-shop.
- **Per-floor band signs (commercial E)**: one strip per floor under the window line, 0.8 m tall, split into 2–4 panels per floor, each a different color; 7F building shows ~15–25 panels on the street face (11171255 #2NE). Palette: white, yellow (240,200,40), blue (30,70,160), green (40,120,60), pink/magenta, orange, light blue. Vertical stacked signs on side walls: 0.6 m × 3–4 m, yellow/white/red.
- **돌출간판**: 0.5–0.6 m × 0.8–1.0 m projecting 0.7 m from the wall at 2F–3F height, 1–3 per facade on commercial, mostly real estate (round "부동산" sign on a pole 2.5 m high at the curb is distinctive), pharmacy cross, church cross on rooftop frames.
- **Banners**: vinyl 0.9 × 5 m hung on fences and school facades (campaigns), pink/white; 3–6 along school fences.
- **Awnings**: red corrugated-metal awning on 1F restaurants (11174023, 11081057 neighbor), yellow fabric awning (11184538 #1S).
- Business categories seen (no names): real estate, pharmacy, cafe, bakery, convenience store, chicken, pizza, Japanese noodle/udon, Korean restaurant, noodle, nursing hospital, dental, oriental medicine clinic, child development center, academy (English/math), tailor, hair salon, nail, fitness, church, law/tax office, senior care, kindergarten.

## 4. Street

- **Road classes**: 길주로 (tertiary, 4 lanes, median trees? no, 2+2 with yellow double center line, brick-paved 4–6 m sidewalk with street trees every 6–8 m); 계남로/계남로242번길/옥산로109번길 (residential, 2 lanes, 6–7 m, yellow double center line, white dashed lane edges, "50" speed, "천천히" in white at crosswalks); living_street lanes between villas (5–6 m, no markings, no sidewalk, cars parked nose-to-tail on one side, 1 car per 5–6 m, occasionally both sides); service alleys 3–4 m.
- **Markings**: yellow double center (235,190,40), white dashed lanes, white zebra crosswalks 4–5 m wide with stop line, white diamond before crosswalks, "천천히"/"50" text, yellow crosswalk + yellow edge line in school zone (11177608 #3NW, 11186644 #3E), blue painted handicap parking (15839722 #1SW), white parking bays along 계남로 (11185213 #3W).
- **School zone kit** around 부흥중/심원고: yellow traffic-light and sign poles (11201639 #2NW), gray pedestrian guard fence with light-blue/gray ornamental wave panels (1.0 m, segments 2 m, along all school-side sidewalks), blue direction signs on cantilever poles ("Gilju-ro 150 m"), red/yellow flexible bollards in the lane center (11177783 #3E), red steel bollards at park entrance (11192750 #1N).
- **Utility poles**: gray concrete 10–12 m with transformer and 3–6 wire bundles crossing lanes (11188641 #3N, 11201637, 11198845); lane crossings every ~30 m; wires stapled on facades.
- **Trees**: street trees on 길주로/계남로 are zelkova/plane 10–14 m, trunk 0.3–0.5 m, spacing 6–8 m, in 1×1 m soil pits; school and park: pines (dark, 10–15 m, 11185281 #2E) and pollarded planes (bare stubby crowns 5–6 m, 11215390 #1N); villa yards: round topiary junipers 1.5–2 m, roses on fences.
- **Lamps**: gray steel 8–10 m single-arm street lamps on roads; park: dark-gray 4 m post lamps; villa gate posts: globe lamps.
- **Sidewalk**: brick pavers in gray + pink/red mix (sidewalk 2–4 m), gray granite curb 0.15 m, yellow tactile tiles at crossings and the school gate, grass verge strip on 길주로 (11201645 #2N).
- **Fences/walls**: villa boundary 1.2–1.6 m brick + rail; school: dark steel pickets 1.8 m on a dark checker-brick low wall (부흥중), white tubular fence with leaf-motif panels 1.2 m (심원고 ground side), bright green pickets 2 m (80,160,60) along the sports ground (11201622 #2N).
- **Furniture**: bus stop sign posts (BUS) and a taxi stand sign; green KT telecom cabinets 1.2 m; dark gray utility cabinets; blue recycling bins and clear-bag trash piles at corners (11171255 #3SW); bike racks with 10–20 bikes at the school wall; yellow/blue shared bikes leaning on fences; subway entrance glass box with elevator (신중동역, 11185986 #2N/#3E) on 길주로; park benches, exercise machines, drinking fountain; flower beds with shrubs; parked cars white/gray/black dominate (70% white/silver).
- Not seen: speed bumps, manholes (not resolvable), bike lanes, retaining walls (flat ground).

## 5. Schools

- **심원고 main (11185213, 5F, 20.5 m, 2542 m²)**: long bar ~80 m, two-tone — south face white/light-gray painted concrete (200,200,205) with red-brick vertical strips, north/west faces red brick (170,80,60). Per floor one continuous strip of windows 1.5 m tall, white frames, blue-tinted glass, spandrel 1.8 m. Central bay with 3-storey glazed stair tower and a vertical banner. Blue trim/roof edge line. Roof flat with low parapet and a few boxes.
- **심원고 annex (11185281, 5F, 598 m²)**: red brick with a cream cantilevered balcony/landing stack (1.5 m deep, 1 m high boxes) on the end, diamond motifs in darker brick on the blank end wall (3 columns × 2), tall arched glass stair tower (blue/teal glass, white frame) 1.5× floor height at top. Pollarded trees in front, white leaf fence.
- **Low wings (15358826 area)**: 2–3F cream/white blocks with salmon/orange trim roofs and continuous windows; a metal-roof pergola/bike shelter 2.5 m high runs along the ground edge; green net backstop 8 m on poles.
- **Ground**: dirt/sand (210,190,150) ~90×60 m, goal posts, white-and-pine edge; small garden (pines, hexagonal gazebo, shrubs, benches) between annex and main.
- **Gate (south)**: two gray granite pillars 0.8×0.8×2.5 m, white accordion sliding gate 6 m, gray guard booth 2×2 m, white fence, yellow tactile strip, crosswalk.
- **부흥중 (11036833, 5F, 18 m)**: red brick with white-framed windows 1.5×1.4 m in rows (not strips), gray-panel stair tower with blue glass, green small shed, red gas pipe on wall, bike racks, blue handicap bays, gate = 2 pillars (light-gray granite base + dark-gray band) + white accordion gate + banner; green picket fence on the ground side, dark picket on the street side; gym/auditorium with light-gray panels and arched blue-framed windows (11201621 #3W).

## 6. Top-12 "I'm in 중3동" features, ranked

1. Dense dark-brown/red brick 3F villas with walled yards, brick gate posts, black iron gates — **data** (floors=3, usability 01000, wall_color) + rule for gate/wall.
2. Glazed vertical stair strips and bay windows on those villas — rule (40%/40% deterministic by id hash).
3. 길주로 7–10F commercial wall with per-floor colored band signs and GF glass shops — data (floors ≥ 7, usability 09000/14000/04000) + rule for sign stacking.
4. Red-brick school bars with strip windows, glazed stair tower, white/green fences, sand ground — hand-built (`Workspace/Manual`), school_polygons already in config.
5. Cars parked in a continuous line on every living_street/residential lane — rule from `highway_class` (density 1 per 6 m, one side on living_street, both on residential).
6. Utility poles with wire bundles crossing the lanes — rule, every ~30 m on living_street/residential.
7. Street trees (zelkova) 6–8 m apart on tertiary/residential sidewalks + brick pavers + gray curb — rule from `highway_class` (sidewalk exists only for tertiary/residential).
8. Yellow double center line, white crosswalks, "천천히", yellow school-zone poles and gray wave guard fences near schools — rule from highway_class + distance to school_polygons.
9. AC outdoor units (1–3), red gas pipe, stainless ducts on facades — rule (count by floors/usability).
10. Hip dark-gray roofs vs flat parapets — data (roof_shape in estimates: hip 27 / flat 45; default flat).
11. Stone-veneer (white rubble / tan ledgestone) variant villas with dark mansard roofs — data (wall_color light_gray/beige → stone material).
12. Greenery: rose bushes on villa fences, round topiary, pines in school/park, pollarded planes — rule/default (park and school areas from polygons; villa yards 1–2 shrubs).

Texture/material mapping suggestion: brick → Roblox `Brick` material with the two brick RGBs; stone villa → `Slate`/`Cobblestone`; tile/granite commercial → `Concrete`/`Marble` light gray; glass strips → `Glass` with 60,90,85 and 0.3 transparency; roofs → `Slate` 60,60,65; sidewalk → `Brick`-like pavers in 150,140,135 / 170,110,100 checker; road asphalt → `Asphalt` 70,70,72; sand ground → `Sand` 210,190,150; green fence → 80,160,60 `Metal`.

Hooks in code: final values enter at `src/layout.py:174–181` (height, floors, wall_color → `WallColor` attribute), road class/width at `src/layout.py:198–200` and `:239`, text attrs limited at `src/build_luau.py:37`; estimates fields at `src/judgement.py:14,31`; palette in `config.toml:89–101` (needs stone/tile/glass entries if U5 keys material on wall_color).