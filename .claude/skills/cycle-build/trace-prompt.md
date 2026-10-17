# Facade tracing: read one unfolded street-view facade into pieces

Repository: the roblox-map checkout you run in (a Roblox map of a real Korean neighbourhood in 부천). A street-view photo of
each building has been unfolded onto its front wall (`src/facade.py unfold`): the facade is straightened as in an elevation
drawing and laid on a 1 m grid. You trace it: every window, door, band, railing, stair tower and sign as a rectangle in metres.
The map builds exactly what you write, so the positions are what matters.

## Input
One list file (given by the caller): `{"items": [{"building_id", "image", "outline", "L_m", "H_m", "floors"}], "output": path}`.
- `image`: the unfolded facade. Thin cyan lines every 1 m, yellow numbers are metres (u along the bottom from the left, y up
  the left side from the ground). The magenta rectangle is the wall: u = 0 .. L_m, y = 0 .. H_m; the magenta lines inside are
  floor lines (H_m / floors apart). Anything outside the rectangle (left of 0, right of L_m, above H_m) is a neighbour or the sky,
  except a rooftop room or a stair tower rising above the roof.
- `outline`: the original photo with the wall's outline in magenta. Open it only if the unfolded image looks wrong.

## Blind rule
Open the list file and its images with the Read tool, nothing else. Do not read `regions/`, `data/build/`, `data/map.db`, `src/`
or other answers, and do not run the project's scripts.

## When the unfolded wall is wrong or unusable
**Check this first, for every building.** Compare the building with the magenta rectangle: its roof line or eave against
H_m, its left and right walls against 0 and L_m, its floor slabs against the magenta floor lines. If the eave is more than 1 m
from H_m, a side wall more than 0.5 m from 0 or L_m, or the slabs drift off the floor lines, the grid is wrong and every height
you read off it will be wrong too (a 2026-10-18 test traced a 13.6 m villa as 11.5 m this way): you must give `corners_px`.
- The magenta wall clearly misses the building (the building's edges or floor slabs are well off the magenta rectangle): give
  `corners_px` = the wall's four corners in **outline photo pixels** (bottom-left, bottom-right, top-right, top-left as seen) and
  `top_m` = the height above ground of your top two corners (the eave is usually H_m). Trace the pieces anyway from what you see,
  using the floor slabs to place heights; the caller unfolds again with your corners.
- The facade is mostly hidden (trees, a truck), too far, or it is the wrong building: write `{"building_id", "unusable": "<why, short>"}`
  and no pieces. The map then borrows a traced neighbour. If the photo shows **no building at all** where the wall should be
  (an empty lot, a parking lot, only trees), write `"unusable": "no building"` exactly.

## Pieces
`{"kind", "u0", "u1", "y0", "y1"}` in metres to one decimal (0.05 where you can see it), plus optional fields:

| kind | what | optional fields |
|---|---|---|
| `window` | one window opening (glass + frame) | `mullions_u`: sash/pane frame positions (u); `mullions_y`; `bars`: `{"du": bar spacing m, "y": [rail heights]}` for a grille |
| `door` | entrance glass or door | `mullions_u`, `mullions_y` (leaves, transom) |
| `glass_stair` | glass strip of a stair tower | `out_m` (on the pier's face), `mullions_y` (landing frames) |
| `brick_stair` | stair pier or pilaster sticking out of the wall | `depth_m` (default 0.6) |
| `slab` | floor slab / band / eave / step that sticks out | `depth_m` (0.25 band, 0.4 slab, 1.0 eave or step) |
| `band`, `panel` | flush band; a panel of another colour (two-tone wall, dark recess) | |
| `fence_iron` | balcony or window railing (posts and rails) | `out_m` (0.15-0.3), `du` (post spacing, 0.12 default, 0.08 dense) |
| `awning` | awning / canopy | `depth_m` |
| `sign` | shop sign board (position and size only, no text) | |
| `shopfront` | shop glass | `mullions_u` |
| `ac_unit` | air conditioner box | |
| `rooftop_box` | rooftop room above H_m | `out_m` = -(its depth + setback), `depth_m` (default 3) |

Do not write colours: they are measured from the photo afterwards. Do write the wall material once per building as `finish`:
`brick` (red or brown brick), `stone` (granite or stone cladding), `tile` (small ceramic tiles), `paint` (rendered and painted),
`panel` (metal or composite panels), `glass` (curtain wall) — the main wall, not the stair tower or the base.

**Repeats save writing**: a piece that recurs at the same u on several floors is written once with `repeat_dy`: the extra
height offsets, e.g. `{"kind": "window", "u0": 0.4, "u1": 2.6, "y0": 3.7, "y1": 6.0, "repeat_dy": [3.4, 6.8]}` is three windows.
Use it only when position and size are really the same.

Tips: read heights off the slabs and the floor lines first, then windows between them. Split-level villas (stair in the middle)
have the two wings half a floor apart: trace each wing on its own. Grilles (방범창) and railings are worth writing: they define
the look. Skip what you cannot see (behind a car, under a tree) rather than guessing; list it as `occluded` rectangles.

## Output
Write ONE JSON file to `output`:

```json
{"buildings": [{"building_id": "gis:N", "corners_px": null, "top_m": null, "finish": "brick",
  "pieces": [{"kind": "brick_stair", "u0": 2.8, "u1": 5.8, "y0": 5.0, "y1": 16.3, "depth_m": 0.4}, ...],
  "occluded": [{"u0": 0.0, "u1": 1.2, "y0": 0.0, "y1": 2.2}],
  "note": "short English: what the facade is"},
 {"building_id": "gis:M", "unusable": "facade behind a tree"}]}
```

Never write people, faces, licence plates, phone numbers or shop names in `note`. Then reply with only: the number of buildings
traced, the number unusable, and the number with `corners_px`.
