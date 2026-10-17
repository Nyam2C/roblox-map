# Look-alike scoring: street-view photo against the Studio building (U8 G3)

Repository: the roblox-map checkout you run in (a Roblox map of a real Korean neighbourhood in 부천). Heights and footprints are
already checked elsewhere. Your job is only this: **does the building in Studio look like the building in the photo?**

You get one list file (`data/gate/<cell>/g3/score-list.json`): `sheets` (image paths, each with its `slots`) and `output` (where
to write your answer). Every sheet holds a few slots under one another. Each slot is one row: its id (`S001` ...) in the header,
the street-view photo on the **left**, the Studio capture from the same camera on the **right**. The building in question is
outlined in magenta in both images. The outline is computed from the map data, so it can be off by a few pixels or partly cover a
nearer building; judge the building it mostly outlines.

## Blind rule (important)
Open the list file and the sheet images with the Read tool, nothing else. Do NOT read `slots.json`, `colours.json`, `regions/`,
`data/build/`, `data/map.db`, `src/`, logs or earlier answers, and do not run the project's scripts. Score each slot on what you
see in it. Some slots show a photo and a render of two different buildings on purpose, and some pairs appear twice: score every
slot honestly on its own.

## Six looks, each 0, 1 or 2
Studio is simplified (boxes, flat colours, no people or cars, no texture photos). Do not take points off for that. Take points
off when a person who knows the street would say "that is not how it looks".

| look | 2 | 1 | 0 |
|---|---|---|---|
| `color` | main wall colour and lightness match | same colour family but clearly lighter, darker or more saturated; or a second wall colour (two-tone, a base of another colour) is missing | a different colour |
| `finish` | wall material reads the same (brick, tile, stone, painted render, metal panel, glass curtain wall) | close (tile against paint of the same colour) | different (brick against panel, glass against masonry) |
| `windows` | window type, size and rhythm match (punched or ribbon, count per floor, tall or square, frames) | same type, count or size clearly off | different type, or windows where the photo has a blank wall (or the reverse) |
| `ground` | ground floor matches (shopfronts with signs, open parking on columns, house door, lobby glass, blank wall) | same use, layout off (shop glass on the wrong face, no awning) | a different use (shops against parking, a door against a shopfront) |
| `extras` | the defining projections match: balconies and railings, bay windows, a glass or brick stair column, air-conditioner units, awnings | some present, some missing or extra | a defining one is missing or wrong (a glass stair strip, a full balcony stack) |
| `roof` | roof shape and colour, parapet, rooftop boxes or railings, the top sign band match | partly | different (a red gable against a flat grey roof) |

`same_building`: `true` when the right image could be taken for this same building, `false` when it shows a different building
(or the outline is clearly on another building in one of the images).

If something is hidden in the photo (trees, a truck, too far), score what you can see; give `1` to a look you cannot see at all
and say `hidden: <look>` in the note.

## Fixes for every look scored 0 or 1
Add `{"attr": <look>, "route": <route>, "want": <short English, at most 80 characters, what the photo shows>}`:

- `detail`: one of the judged fields is wrong and the map can show the right one (finish, ground floor use shop/house/garage,
  stair none/glass/brick/round, bay window, balcony, roof colour, rooftop box/railing/tank).
- `color`: the wall colour is wrong (the gate measures it and corrects it).
- `rule`: the map has no way to show it (a two-tone facade, a stone base, window grid size, dense vertical signs, a curtain wall
  with mullions). These are counted over cells and become new rules.
- `facility`: a representative facility (a big landmark built by hand) is wrong in its spec.
- `none`: nothing to fix (use it rather than leaving a low look unexplained).

Never write people, faces, licence plates or real shop or brand names in `want` or `note`, and no alcohol, tobacco or gambling
words (call such a shop "restaurant" or "shop").

## Output
Write ONE JSON file to `output`:

```json
{"slots": [{"slot": "S001", "attrs": {"color": 2, "finish": 1, "windows": 2, "ground": 0, "extras": 1, "roof": 2},
            "same_building": true,
            "fix": [{"attr": "ground", "route": "detail", "want": "ground floor is open parking on columns"},
                    {"attr": "finish", "route": "rule", "want": "beige tile with dark brown tile bands every floor"}],
            "note": "short English, optional"}]}
```

Exactly one entry per slot of every sheet you could open, valid JSON (no comments, no trailing commas), every look an integer. Then reply with
only: the number of slots written, how many you called `same_building: false`, and any sheet you could not open. **A sheet that will not open (e.g. "request limit") is never guessed: write no entry for its slots, stop, and list the sheets you did not reach.** The caller merges answers and sends the missing sheets to a new scorer.
