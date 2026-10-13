# Blind building judgement from street-view contact sheets

Repository: /Users/taehyeonpark/Desktop/dev/roblox-map (a Roblox map of a real Korean neighborhood, 부천 중동/계남/옥산 area).

You get a list file (JSON lines). Each line is one building: `building_id`, `name` (often empty), `box_m` (size of the box around its
footprint in metres), `sheet` (a contact-sheet image path relative to `captures/`), `views` (crop rank and the direction the camera
faces). For EVERY line, open the sheet with the Read tool (`/Users/taehyeonpark/Desktop/dev/roblox-map/captures/<sheet>`), look at the
crops (labelled `#1 N`, `#2 SW` ... = rank and camera direction; the target building is the one in the middle of each crop), and write
two records for that building.

## Blind rule (important)
Do NOT read `data/map.db`, `regions/`, `data/build/`, any log, or any other file than your list file and the sheet images.
Do not run sqlite or the project's scripts. The point is an independent count from the photos only.

## Record 1: `judgement` (U4)
- `building_id`: copy.
- `floors_seen`: integer count of ABOVE-GROUND floors you can see. Count a pilotis floor (ground floor of columns/parking) as one floor.
  Do NOT count a rooftop penthouse/stair hut, a basement or a half-basement. If you cannot count (hidden, wrong target), use null.
- `confidence`: `high` (all floors clearly visible), `medium` (partly hidden by trees/cars), `low` (a guess). Required when floors_seen
  or height_est_m is given; else null.
- `height_est_m`: only when floors_seen is null and you can still estimate height in metres (2-500); otherwise null.
- `wall_color`: one of white, cream, beige, yellow, orange, red_brick, brown, pink, light_gray, dark_gray, green, blue, other; null if unclear.
- `roof_shape`: one of flat, gable, hip, shed, other; null if unclear.
- `views_used`: list of crop ranks you actually used (subset of the ranks in `views`, at least one).
- `note`: short English, at most ~120 characters: what the building is (villa, shop house, small office, church, school block...),
  ground floor (shop, parking pilotis, house door), visible features (glass stair strip, bay window, balconies, rooftop box/tank/railing,
  solar panels, roof terrace). Use these words literally when they apply: shop/store/restaurant/cafe/convenience/pharmacy, stair,
  bay, balcony, garage/carport, roof terrace, solar. NEVER write people, faces, licence plates or real shop/brand names.

## Record 2: `detail` (U5)
- `building_id`: copy.
- `finish`: brick | stone | tile | paint | panel | glass (main wall finish).
- `ground_use`: house | shop | garage (garage = pilotis parking or shutters on the ground floor).
- `stair`: none | glass (vertical glass stair strip) | brick (a projecting stair column in wall material) | round (a round stair tower).
- `bay`: 0 | 1 (projecting bay window).
- `balcony`: 0 | 1 (balconies with railings on the street face).
- `roof_color`: dark | red | green | brown | blue | pink (what you see of the roof or its edge; dark if flat/unclear).
- `rooftop`: none | box (penthouse / stair hut) | railing | tank.
- `note`: short English, same privacy rule; may repeat the main facts.

## Output
Write ONE JSON file to the output path you are given: `{"judgements": [...], "details": [...]}` with exactly one entry of each kind
per input line, same order, valid JSON (no comments, no trailing commas). Then reply with only: the count written, how many had
floors_seen null, and any building where the crops clearly show the wrong target or no building.

Work steadily through the whole list; do not skip lines. Be honest: if a crop shows trees only, say so with null and low confidence.
