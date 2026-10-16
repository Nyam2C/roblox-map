# Facility facade spec (research task)

Repository: /Users/taehyeonpark/Desktop/dev/roblox-map, a Roblox map of a real Korean neighbourhood (부천). Some
important buildings get a detailed hand-made model. Your job: for each facility you are given, find out what it really looks like
and write ONE JSON spec per facility. A generator turns the spec into Roblox parts on the building's real outline (V-World boxes),
so you describe the look, not the footprint.

## Sources (use all, in this order)
1. Street-view crops already captured, per building id `gis:N`:
   `captures/<cell>/sheets/gis_N.jpg` (contact sheet) and `captures/<cell>/crops/gis_N__*.jpg` (single crops). Open with Read.
   If a building has no files, use its neighbours' sheets of the same cell that show it.
2. Web search (WebSearch, Korean queries such as "부천세무서 건물", "꿈빛도서관 외관", "중흥초등학교 부천"): read blog / news /
   municipal / namuwiki pages (WebFetch) for facade descriptions, colours, number of floors, notable features. Note the URLs.
   Photos on the web are only looked at / described, never saved.
3. The satellite photo `data/satellite/<cell>-z19.jpg` for roof colour and rooftop features (optional; it is large).

Do NOT write any file except your output file. Do NOT run the project's scripts or touch the database.

## Privacy and content rules
- No people, faces, licence plates, or real shop / brand / company names in any text you write.
- `sign.text` may hold the facility's own public name only (school, library, tax office, police station, church name, or a
  district name). For apartments and commercial towers leave `sign` null (brand names are not allowed).
- No alcohol, tobacco or gambling words.

## Output: one JSON object per facility, all in one file `{"facilities": [ ... ]}`
```
{
  "key": "<given key>",
  "building_ids": ["gis:..."],            // the records that make up this facility (as given; drop duplicates or wrong ones and say why in notes)
  "floors": 5,                             // above-ground floors you can count (photos win over the given value when clear)
  "height_m": null,                        // only if you can tell the height better than floors x 3.5 (e.g. tall ground floor)
  "wall": {"material": "Concrete", "rgb": [220, 214, 200]},
  "base": {"floors": 1, "material": "Granite", "rgb": [120, 118, 112]},      // or null: a different ground/podium skin
  "windows": {"type": "grid", "w_m": 1.8, "h_m": 1.5, "pitch_m": 2.4, "glass_rgb": [70, 100, 120], "frame_rgb": [230, 230, 228]},
                                           // type: grid (punched windows) | ribbon (one band a floor) | curtain (glass wall) | none
  "bands": {"rgb": [180, 176, 168], "every_floor": true},                    // or null: horizontal floor bands
  "accents": [                             // vertical/horizontal features that make it recognisable, up to 8
    {"kind": "glass_strip", "face": "street", "at": -0.3, "width_m": 3.0, "from_floor": 0, "to_floor": 5, "rgb": [90, 140, 170]},
    {"kind": "panel", "face": "all", "at": 0.0, "width_m": 6.0, "from_floor": 2, "to_floor": 4, "material": "Plaster", "rgb": [200, 80, 70]},
    {"kind": "fins", "face": "street", "at": 0.0, "width_m": 20.0, "from_floor": 1, "to_floor": 5, "rgb": [240, 240, 236], "pitch_m": 1.5},
    {"kind": "stripe", "face": "all", "from_floor": 3, "to_floor": 3, "rgb": [40, 90, 160]},
    {"kind": "round_windows", "face": "street", "at": 0.0, "width_m": 12.0, "from_floor": 3, "to_floor": 4, "rgb": [240, 240, 236]},
    {"kind": "arch", "face": "street", "at": 0.0, "width_m": 8.0, "from_floor": 0, "to_floor": 2, "rgb": [...]},
    {"kind": "cross", "face": "roof", "at": 0.3, "width_m": 2.0, "rgb": [...]},             // a church cross on a short tower
    {"kind": "clock", "face": "street", "at": 0.0, "from_floor": 3, "to_floor": 3}
  ],                                       // face: street | back | left | right | all | roof ; at: -0.5..0.5 along the face
  "entrance": {"face": "street", "at": 0.0, "width_m": 4.0, "canopy": true, "canopy_rgb": [...], "steps": true},
  "sign": {"text": "부천세무서", "face": "street", "floor": 1, "bg_rgb": [...], "ink_rgb": [...]},  // or null
  "roof": {"parapet_rgb": [...], "top_rgb": [...], "features": ["stair_box", "solar", "helipad", "crown", "tank", "pitched"],
           "crown": {"height_m": 4.0, "rgb": [...]} },
  "notes": "free text for the builder: shapes the schema cannot say (e.g. orange upper floors, curved granite wall on the corner)",
  "sources": ["https://...", "captures/.../gis_N.jpg"],
  "seen": "one or two sentences: what the photos showed"
}
```
Materials: Concrete, Brick, Granite, Marble, Plaster, SmoothPlastic, Glass, Limestone, Sandstone, Metal, Slate, CeramicTiles.
Colours are what a viewer sees in daylight (not the darkest shadow). Keep to things you actually saw.
The roof `top_rgb` is what the satellite shows from above (a white roof is white even if the walls are dark).

Reply only with: the output path, and per facility one line on confidence and the main sources.
