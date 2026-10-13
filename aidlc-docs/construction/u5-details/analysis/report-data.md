# U5 data inventory — cell 8930e0af13bffff (read-only)

Sources: `data/map.db` (sqlite3 `mode=ro`), `overrides/8930e0af13bffff.json` (122 estimates, 0 overrides, version 1), `data/build/8930e0af13bffff/manifest.json`, `config.toml`. Geometry computed with the project's own functions (`src/layout.py` `outline_to_box` L138-152, `road_width_m` L193-200, `_segments` L203-215, `sidewalk_sides` L232-240; `src/judgement.py` `effective_building` L147-222) from a scratch script `/private/tmp/claude-501/-Users-taehyeonpark-Desktop-dev-roblox-map/a97a372b-6ac1-4267-8088-e24ff9f52520/scratchpad/inv.py` run with `uv run --python 3.13 --with shapely==2.2.0 --with h3==4.5.0`. No project file was modified, no Studio call was made.

## 1. `usability_code` meaning

Provenance: V-World WFS `LT_C_BLDGINFO` property `usability` → `src/geo.py:277` (`usability_code=text("usability")`), alongside `bld_nm`, `grnd_flr`, `ugrnd_flr`, `height`, `useapr_day`, `archarea`. It is the 건축물대장 주용도코드 (세움터 공통코드, `mainPurpsCd` in 건축HUB), a 5-digit code whose first two digits are the item number of 건축법 시행령 별표 1 (용도별 건축물의 종류) and whose last three digits are the sub-type (000 = category level).

| code | 별표1 item | meaning | web confirmation | count in cell (buildings) |
|---|---|---|---|---|
| 01000 | 1 | 단독주택 = 가.단독주택, 나.다중주택, 다.**다가구주택**, 라.공관 (01003 = 다가구주택) | 01000/01003 in 2002 건설교통부 코드변환 자료; 01000 in 건물공간정보 데이터모델 (field named `USABILITY`/`MAIN_PURPS_CD`) | 89 |
| 02000 | 2 | 공동주택 (아파트·연립·다세대·기숙사) | both sources | 0 |
| 03000 | 3 | 제1종근린생활시설 (지역자치센터·파출소·소매점 <1000 m²…) | 건물공간정보 데이터모델 | 1 (gis:11188308 중3동행정복지센터) |
| 04000 | 4 | 제2종근린생활시설 (일반음식점·학원 <500 m²·사무소 <500 m²…) | 2002 코드변환 자료 | 1 (gis:11171885 뉴월드 프라자) |
| 09000 | 9 | 의료시설 (병원) | inferred from 별표1 numbering; consistent with estimate note "hospital block" on gis:12403717 | 2 (gis:11188641 골든타워, gis:12403717) |
| 10000 | 10 | 교육연구시설 (학교·학원 ≥500 m²·연구소) | 별표1 item 10 confirmed; code inferred | 7 |
| 11000 | 11 | 노유자시설 (어린이집·경로당·복지시설) | 별표1 item 11 confirmed; code inferred | 1 (gis:11185986 뉴월드타운) |
| 14000 | 14 | 업무시설 (오피스텔 포함) | 건물공간정보 데이터모델 | 2 (gis:11184538 블래스랜드, gis:11201645 리치타운 오피스텔) |
| (empty) | – | record without register attributes (area 0, no code; 4 of 19 still have floors) | – | 19 |

Why 01000 for 3-floor villas: 다가구주택 is legally a 단독주택 sub-type (one owner, units not separately registered). Conditions (주택법 시행령/건축법 시행령 별표1 1-다, quoted on Korean Wikipedia): 주택으로 쓰는 층수 ≤ 3 (지하층 제외), 1개 동 주택 바닥면적 합계 ≤ 660 m², ≤ 19 세대, and a 1st floor used as pilotis parking with non-residential remainder is not counted as a housing floor. A 다세대주택 with the same look would be 02000; none exists in this cell. Register profile of the 89 × 01000: floors 2 → 4, 3 → 84, 4 → 1; 사용승인 1990s 84, 2000s 5; building_area median 100.3 m² (p25 92.2, p75 106.4, max 115.8); 1 basement floor on 50 of 122 buildings overall (0 → 66, 2 → 4, 3 → 2 — the 2–3 basements are the 7–10-floor blocks). So the typical unit is a 1990s 3-floor brick 다가구 villa of ~100 m² footprint, roughly 12 × 10.5 m, often with a 반지하.

Register oddities to remember: 옥산경로당 gis:11192750 is coded 10000 (would be 11000 by name); 로얄프라자 and 중동샛별 are 10000 (학원-type use plausible); 뉴월드타운 gis:11185986 is 11000 and its twin gis:11185995 is 10000.

Sources: [건축물대장 코드변환 대사 및 정비요령 2002.12 건설교통부 (codil.or.kr)](https://www.codil.or.kr/filebank/moct2014/200301/MOCT605_1.PDF?nserialno=605) · [건물공간정보 데이터모델 (USABILITY/MAIN_PURPS_CD code list)](http://m.blog.daum.net/jyolee/6) · [건축HUB 건축물대장(표제부) — 주용도코드 "공통코드 참고 xls"](https://www.hub.go.kr/portal/opn/tyb/idx-bdrg-ttlldr.do) · [건축법 시행령 별표 1 용도별 건축물의 종류 (law.go.kr)](https://law.go.kr/flDownload.do?flSeq=93667635) · [다가구주택 — 위키백과 (definition)](https://ko.wikipedia.org/wiki/다가구주택) · [zippoom: 단독주택 = 단독·다중·다가구·공관](https://zippoom.com/%EB%B8%94%EB%A1%9C%EA%B7%B8/%EA%B7%BC%EB%A6%B0%EC%83%9D%ED%99%9C%EC%8B%9C%EC%84%A4-%EC%A3%BC%ED%83%9D-1%EC%A2%85-2%EC%A2%85-%EC%A2%85%EB%A5%98/484) · [국토교통부 GIS건물통합정보 (data.go.kr)](https://www.data.go.kr/data/15144689/fileData.do). Both direct code-table pages were unreachable from this session (DNS / TLS), so 09000/10000/11000 rest on the 별표1 item numbering plus the cell's own names; the user can confirm against the 세움터 공통코드 xls.

## 2. Cross-tab usability × final floors

Final floors = `effective_building` (override > photo when high-confidence conflict > register > photo fill); there are 0 overrides and 0 high-confidence conflicts, so final = register where present, else photo count (11 filled), else none (5).

| use | none | 1 | 2 | 3 | 4 | 5 | 7 | 8 | 9 | 10 | total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 01000 | | | 4 | 84 | 1 | | | | | | 89 |
| (none) | 5 | 7 | 1 | | 2 | 2 | 2 | | | | 19 |
| 10000 | | 1 | | | 1 | 3 | 2 | | | | 7 |
| 14000 | | | | | | | | | | 2 | 2 |
| 09000 | | | | | | | | 1 | 1 | | 2 |
| 04000 | | | | | | | 1 | | | | 1 |
| 11000 | | | | | | | 1 | | | | 1 |
| 03000 | | | 1 | | | | | | | | 1 |

Floors basis: register 106, photo_count 11, none 5. Floors status: verified 64, conflict 30, unverified 12, filled 11, none 5. Height basis: register 100, from_floors 17, photo_geometry 4, default 1 (gis:11201923). Flags: conflict 30, filled 11, low_confidence 8, height_out_of_range 1 (gis:11177783), default_height 1.

Named / OSM-tagged buildings (20 of 122; only 10 have `osm_tags`, there is no `shop=*` tag anywhere in the cell):

| building_id | name | use | reg floors (+below) | reg h m | area m² | OSM tags (non-addr) | 사용승인 |
|---|---|---|---|---|---|---|---|
| gis:11036833 | 부흥중학교 | 10000 | 5 (+1) | 18.15 | 2014.47 | – | 1995 |
| gis:11171255 | 로얄프라자 | 10000 | 7 (+2) | – | 1514.48 | building=commercial, building:levels=6 | 2001 |
| gis:11171885 | 뉴월드 프라자 | 04000 | 7 (+1) | 24.5 | 410.72 | building=commercial, building:levels=6 | 2002 |
| gis:11177783 | 부흥건물 | 01000 | 4 | 9.8 (→13.6, out of range) | 90.25 | – | 2002 |
| gis:11184538 | 블래스랜드 | 14000 | 10 (+3) | 31.05 | 739.26 | building=commercial, building:levels=6 | 2005 |
| gis:11185213 | 심원고등학교 | 10000 | 5 (+1) | 20.45 | 2542.37 | – | – |
| gis:11185281 | 심원고등학교 | 10000 | 5 | – (→17.0) | 597.87 | – | 2002 |
| gis:11185986 | 뉴월드타운 | 11000 | 7 (+1) | 25.25 | 624.19 | – | 2002 |
| gis:11185995 | 뉴월드타운 | 10000 | 7 (+1) | 25.25 | 624.19 | building=commercial, building:levels=6 | 2002 |
| gis:11188308 | 중3동행정복지센터 | 03000 | 2 (+1) | 8.3 | 354.5 | – | 1993 |
| gis:11188641 | 골든타워 | 09000 | 9 (+2) | 34.7 | 751.22 | building=commercial, building:levels=6 | 2003 |
| gis:11192750 | 옥산경로당 | 10000 | 1 | 3.1 | 65.55 | building=yes, amenity=social_facility, social_facility=group_home, social_facility:for=senior, name | 2000 |
| gis:11196895 | 중동샛별 | 10000 | 4 (+2) | 14.0 | 346.46 | – | 1997 |
| gis:11201645 | 리치타운 오피스텔 | 14000 | 10 (+3) | 33.4 | 674.58 | building=apartments, building:levels=10, building:flats=48, height=33, start_date=2010 | 2010 |
| gis:12403717 | – | 09000 | 8 (+2) | 30.4 | 815.79 | building=commercial, building:levels=6 | 2003 |
| gis:14944897 | 심원고등학교 | – | – | – | 0 | – | – |
| gis:15358826 | 심원고등학교 | – | – | – | 0 | – | – |
| gis:16501307 | 뉴월드타운 | – | 7 (+1) | – | 0 | – | – |
| gis:16821018 | 부흥중학교 | – | – | – | 0 | building=school | – |
| gis:17639013 | 중3동 주민센터 | – | 2 (+1) | – | 0 | building=yes, amenity=community_centre, name | – |
| gis:18692828 | 뉴월드 프라자 | – | 7 (+1) | – | 0 | – | – |

OSM `building:levels=6` on five commercial blocks contradicts the register (7–10) and the photos (6–9); OSM levels are unreliable here.

**Duplicate outlines (same building twice in the DB → two overlapping parts in Studio today).** Outline intersection ÷ smaller area: gis:11036833/gis:16821018 부흥중학교 0.92; gis:11171885/gis:18692828 뉴월드 프라자 0.95; gis:11185213/gis:14944897 심원고 main 0.87; gis:11185281/gis:15358826 심원고 wing 0.83; gis:11185995/gis:16501307 뉴월드타운 0.92; gis:11188308/gis:17639013 주민센터 0.76. In every pair one record has register attributes and the other has area 0 and no code (a second V-World polygon). gis:11185986/gis:11185995 (both 624.19 m² in the register) do **not** overlap: adjacent twin blocks. gis:15839722 (34 m² booth) sits 46 % inside the 부흥중 outline.

## 3. Shape stats

Vertex count (closing point removed): 4 → 53, 5 → 10, 6 → 39, 7 → 1, 8 → 6, 9 → 1, 10 → 3, 12 → 1, 13 → 1, 19 → 1, 25 → 1, 26 → 1, 33 → 1, 38 → 1, 39 → 1, 44 → 1. Orthogonal (every corner 90±12° or collinear): 90 yes / 32 no. Minimum-rotated-rectangle (same as the Studio box): long side min 6.5, p25 11.1, median 12.0, p75 13.3, max 92.1 m; short side min 2.2, p25 9.6, median 10.5, p75 11.8, max 54.6 m. Fit ratio (outline area / box area): <0.5 → 4, 0.5–0.8 → 5, 0.8–0.9 → 15, 0.9–0.97 → 62, ≥0.97 → 36. Box yaw (ccw from east, 10° bins): 50° 2, 70° 7, 80° 40, 100° 2, 140° 2, 150° 1, 160° 18, 170° 50 — i.e. the block grid is rotated ~10° (street azimuths ≈ 10°/190° and 100°/280°), with 5 buildings on the 계남로 diagonal (yaw 50–55°, 140–144°). Register `building_area` is 0/null for 19 buildings; for the other 103, computed outline area is on average ~12 % larger than the register 건축면적 (eaves/stairs inside the outline).

Poor-fit list (manifest `poor_fit`, 9; recomputed values identical):

| building_id | name | fit | verts | orthogonal | box w×d m | outline m² | use | final floors |
|---|---|---|---|---|---|---|---|---|
| gis:11036833 | 부흥중학교 | 0.464 | 26 | n | 92.1×47.3 | 2023.7 | 10000 | 5 |
| gis:11171255 | 로얄프라자 | 0.621 | 9 | n | 71.4×34.0 | 1507.3 | 10000 | 7 |
| gis:11171875 | – | 0.751 | 8 | n | 16.4×9.1 | 112.1 | 01000 | 3 |
| gis:11180755 | – | 0.744 | 8 | n | 13.1×12.1 | 117.6 | 01000 | 3 |
| gis:11185213 | 심원고등학교 | 0.540 | 39 | Y | 90.5×51.5 | 2517.1 | 10000 | 5 |
| gis:11215390 | – | 0.220 | 8 | Y | 32.4×18.7 | 133.6 | – | 4 |
| gis:14944897 | 심원고등학교 | 0.438 | 44 | n | 91.3×54.6 | 2181.7 | – | 5 |
| gis:15839722 | – | 0.723 | 13 | n | 9.9×4.8 | 34.1 | – | – |
| gis:16821018 | 부흥중학교 | 0.395 | 38 | n | 91.7×46.8 | 1695.0 | – | 4 |

gis:11215390 (fit 0.22, orthogonal, 8 vertices) is an L/U-shaped school-yard structure whose 32×19 m box is 78 % air; the 4 big school outlines (26–44 vertices) are E/ㄷ-shaped wings around courtyards; their boxes spill 0 m from (i.e. over) the 계남로 road slab (see §6).

## 4. Estimates (122 rows, judged 2026-10-13)

roof_shape: flat 45, hip 27, gable 5, shed 1, null 44 (null → DEFAULT_ROOF `flat`, so final flat 89 / hip 27 / gable 5 / shed 1). wall_color: red_brick 37, brown 31, light_gray 28, beige 8, orange 3, dark_gray 3, white 2, pink 1, null 9 (null → `light_gray`, final light_gray 37). confidence: high 5, medium 82, low 33, null 2. floors_seen: 1 → 8, 2 → 5, 3 → 66, 4 → 22, 5 → 5, 6 → 2, 7 → 5, 8 → 2, 9 → 1, null 6. height_est_m is set on 4 rows only (2.0, 2.0, 2.5 m fences/booths and one more), never on a real building.

Note keyword scan (regex over all 122 notes; notes contain no personal data):

| feature | mentions | representative notes |
|---|---|---|
| brick (red/dark/tan/orange) | 75 | gis:11216703 "red brick house with a round stair tower, three window rows"; gis:11209217 "dark brown brick house with balconies" |
| stair tower / stair slit / stair window (계단실, mostly glass) | 28 | gis:11182332 "dark brick house with a tall glass stair tower"; gis:11190349 "stone faced house with a glass stair slit"; gis:11214369 "white painted brick building with a stair window column" |
| glass (bays, towers, facades) | 27 | gis:11171885 "commercial building with glass bays"; gis:18692828 "glass faced commercial block" |
| storefront: shop/restaurant/cafe/convenience/flower (상가) | 24 | gis:11192064 "grey corner building with a convenience store on the ground floor"; gis:11217145 "dark brick shop house with a flower shop under three window rows"; gis:11200835 "dark brick building with a cafe on the ground floor" |
| roof: pitched/eaves/tiled/metal/shingle/colour | 19 | gis:11184284 "orange brick house with a green tiled roof and an attic"; gis:11174007 "brick house with balconies and a dark metal roof"; gis:11216699 "stone faced house with a dark shingle roof and round windows" |
| hidden by trees / pine | 17 | gis:11216744 "dark brick house partly hidden by pine trees"; gis:11188641 "tall commercial tower seen through street trees, top not visible" |
| tile(d) facade or eaves | 16 | gis:11170718 "grey tiled facade with a restaurant on the ground floor"; gis:11174023 "stone faced house with tiled eaves on every level" |
| fence / wall / gate | 14 | gis:11173851 "dark red brick house with a fenced yard"; gis:11216686 "red brick house behind a patterned wall"; gis:11202584 "looks like a school gate with stone pillars" |
| commercial / office / hospital / public | 12 | gis:11184538 "tall commercial block with signs on the lower floors"; gis:12403717 "hospital block with an open drive-through arch"; gis:11188308 "public office with a glass stair tower and a steel brace frame" |
| round tower / round window / curved bay | 12 | gis:11192751 "dark brick house with a round tower and a roses arch"; gis:11215159 "brick and stone house with curved bays and a glass tower" |
| attic / dormer / roof terrace (옥탑) | 11 | gis:11190876 "attic dormers under a low red roof"; gis:11177608 "tan brick house with balconies and a roof terrace"; gis:12996130 "pale grey shop building with an attic dormer" |
| balcony | 11 | gis:11216743 "dark brick house with white balconies and a tall glass tower" |
| bay window | 10 | gis:11215178 "dark brick house with rounded corners and bay windows" |
| stone facing | 10 | gis:11206216 "stone faced house with brown hip roofs"; gis:11214904 "grey stone covered house behind roses" |
| not a building / target uncertain | 8 | gis:11201621 "long thin fence-like structure along the school road, not a building"; gis:11201622 "long thin green metal fence along the schoolyard" |
| arch (windows, entrance) | 6 | gis:11185950 "dark brick house with a glass stair tower and an entrance arch" |
| awning / canopy | 4 | gis:11190682 "grey tiled shop building with a dark awning"; gis:11216748 "brick house with a blue awning, four rows of windows" |
| signs (간판) | 3 | gis:11171255 "commercial complex with signs on every floor" |
| garage / parking / carport / drive-through | 3 | gis:11216708 "brick house with a garage on the ground floor and a stair tower" |
| solar panels | 3 | gis:11196854 "red brick house with solar panels on the roof" |
| pilotis, shutter, parapet/crenellation | 0, 0, 1 | gis:11196895 "brick building with a crenellated parapet" |

Ground-floor shop mentions by use: 24 storefront notes, of which ~20 are on 01000 villas (brick/grey "shop house"), i.e. corner/alley villas with a 1-floor 근생 unit; no estimate mentions pilotis.

## 5. Streets (`street_features`, cell 8930e0af13bffff: 17 road + 1 path, all OSM ways)

| feature_id | kind | class | name | width used m | sidewalk items | owned segs | owned len m | total len m | other tags |
|---|---|---|---|---|---|---|---|---|---|
| way:783242905 | path | pedestrian | 신흥로238번길 | 2.5 | – | 2 | 111 | 111 | – |
| way:222729116 | road | living_street | 계남로242번길 | 5 | – | 1 | 37 | 132 | – |
| way:222729117 | road | living_street | 계남로 | 5 | – | 1 | 39 | 69 | – |
| way:222729119 | road | living_street | 계남로242번길 | 5 | – | 1 | 118 | 118 | – |
| way:222729120 | road | living_street | 계남로242번길 | 5 | – | 1 | 103 | 103 | – |
| way:222729122 | road | living_street | 계남로242번길 | 5 | – | 2 | 73 | 73 | – |
| way:222729123 | road | living_street | 옥산로109번길 | 5 | – | 1 | 71 | 71 | – |
| way:219848661 | road | residential | 계남로 | 6 | L+R | 2 | 96 | 359 | cycleway=no, foot=yes, oneway=no, sidewalk=both, surface=asphalt |
| way:222842945 | road | residential | (noname=yes) | 6 | – | 1 | 67 | 67 | sidewalk:both=yes, surface=asphalt |
| way:222842946 | road | residential | 옥산로109번길 | 6 | – | 3 | 156 | 326 | oneway=no |
| way:490069622 | road | residential | 계남로242번길 | 6 | – | 2 | 117 | 328 | oneway=no |
| way:222140575 | road | service | 계남로260번길 | 4 | – | 6 | 223 | 271 | oneway=no |
| way:222729121 | road | service | 신흥로238번길 | 4 | – | 2 | 155 | 155 | – |
| way:222729124 | road | service | 옥산로113번길 | 4 | – | 2 | 111 | 274 | – |
| way:222729125 | road | service | (noname=yes) | 4 | – | 1 | 41 | 41 | – |
| way:783242906 | road | service | 옥산로113번길 | 4 | – | 1 | 68 | 68 | – |
| way:295334454 | road | tertiary | 길주로 | 10 | L+R | 2 | 127 | 263 | oneway=yes, surface=asphalt, wikidata=Q12586841 |
| way:1203989957 | road | tertiary_link | – | 6 | – | 0 | 0 | 37 | foot=no, lanes=1, lit=no, maxheight=3.4, maxspeed:type=KR:urban, oneway=yes, sidewalk=no, surface=asphalt |

Totals: 29 owned road segments (1601 m) + 2 path segments (111 m) → the 29 road + 2 path + 8 sidewalk items in the manifest. No feature has `width`, `maxspeed`, `lanes` (except the link), `lit`, or `crossing`; `sidewalk` appears only on 계남로 (`sidewalk=both`) and the link (`no`); `sidewalk:both=yes` on way:222842945 is not read by `layout.sidewalk_sides` (it reads only `sidewalk`), so that street gets no sidewalk today. Sidewalks are built only for 계남로 and 길주로 (tertiary rule). Street furniture: `cells.py` does request `node[highway=crossing]`, `node[natural=tree]`, `node[highway=street_lamp]`, `node[amenity=bench]` and footway crossings (`src/cells.py:36-37, 113-115, 145-146`), but OSM returned none → `distinct kind` = {road, path}; 0 trees, lamps, crossings, benches in the DB. Other cells: 8930e0af123ffff and 8930e0af12bffff have no `cells` row, no `buildings`, no `street_features`, no `estimates`; only buffer-fetch raw rows exist (`gis_buildings` 172 / 68, `osm_buildings` 5 / 9) plus 13 / 4 downloaded panoramas physically located there (used for first-cell buildings). `captures` total 232 panoramas, all 6144×1024 zoom 1, captured 2026-05-27 … 2026-06-01, lat 37.5028–37.5059, lon 126.7759–126.7803.

## 6. Which building touches which road (facade/sign side)

Method: Studio box (min-rotated rectangle) vs the full OSM polyline of each of the 18 features, in the project frame; edge distance = max(0, box→centerline − width/2) with `road_width_m` from `config.toml [road_widths_m]`; facing side = box edge whose midpoint is nearest that road; its outward normal azimuth is reported (0° = N, clockwise). Self-check: for 110/122 the chosen side's normal is within 15° of the direction to the nearest road point (7 within 30°, 5 are courtyard/school structures).

Distance from box edge to road edge: ≤1 m 8, ≤3 m 56, ≤6 m 92, ≤10 m 106, >10 m 16 (max 50.4 m). Box overlaps the road slab (0.0 m): gis:11036833, gis:16821018 (부흥중 boxes over 계남로), gis:11185213, gis:14944897 (심원고 main boxes over 계남로) — a visible defect today. Typical villa setback: median 2.9 m (alley building line), 4–7 m on residential streets.

Facing side: long face 61 / short end 61; road parallel to the long axis (<30°) for 65 buildings, perpendicular (>60°) for 57. Facing octant: N 41, S 29, E 28, W 20, SW 4. Facing side length: <5 m 5, 5–10 m 25, 10–15 m 69, 15–20 m 5, 20–25 m 7, ≥25 m 11 — the sign/entrance facade of a villa is ~10–13 m wide. Buildings per nearest road: 계남로260번길 way:222140575 17, 옥산로109번길 way:222842946 15, 옥산로113번길 way:222729124 14, 계남로 way:219848661 13, 신흥로238번길 way:222729121 10, 계남로242번길 way:222729120 9 / way:222729122 8 / way:222729119 8 / way:490069622 5 / way:222729116 3, 옥산로113번길 way:783242906 6, 신흥로238번길 path way:783242905 5, 옥산로109번길 way:222729123 5, way:222729125 2, 계남로 way:222729117 1, way:222842945 1; 길주로 and the link are nobody's nearest road (the 길주로 frontage blocks are closer to 옥산로109번길/the noname street).

>10 m from any road (16): interior villas gis:11177607 (15.4), gis:11182332 (15.2) — served by an alley OSM lacks; set-back big blocks gis:11184538 (11.3), gis:11185986 (14.0), gis:11185995 (14.1), gis:16501307 (13.4); 옥산경로당 gis:11192750 (10.1); school-yard structures gis:11201621 (35.3), gis:11201622 (16.7), gis:11201637 (15.9), gis:11201923 (50.4), gis:11202584 (15.2), gis:11215390 (14.5), gis:11215393 (47.9), gis:15839722 (42.2), gis:16052777 (32.6).

## 7. School buildings

Inside `config.toml school_polygons` (심원고 필지, centroid test) = 8 buildings; 부흥중학교 = 2 records outside the polygon (face selection not applied).

| building_id | name | use | reg→final floors | h m (basis) | area m² (reg / outline) | box w×d m | yaw | fit | verts | ortho | crops | face views (face_deg) | wall | roof | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gis:11185213 | 심원고등학교 (main) | 10000 | 5→5 | 20.4 (register) | 2542.37 / 2517.1 | 90.5×51.5 | 169.9 | 0.540 | 39 | Y | 4 | 4 (190, 10, 100, 280) | light_gray | flat | school main block, five rows of windows |
| gis:14944897 | 심원고등학교 (dup of main, 0.87) | – | –→5 | 17.0 (from_floors) | 0 / 2181.7 | 91.3×54.6 | 170.4 | 0.438 | 44 | n | 2 | 2 (10, 280) | light_gray | flat | school main block seen from the gate, grey and beige with a brick wing |
| gis:11185281 | 심원고등학교 (wing) | 10000 | 5→5 | 17.0 (from_floors) | 597.87 / 581.0 | 50.5×13.6 | 80.2 | 0.848 | 10 | Y | 4 | 4 (100, 280, 190, 10) | red_brick | flat | brick school wing with balcony stack and arched glass tower |
| gis:15358826 | 심원고등학교 (dup of wing, 0.83) | – | –→5 | 17.0 (from_floors) | 0 / 826.6 | 52.7×16.3 | 82.5 | 0.960 | 4 | Y | 3 | 3 (278, 98, 194) | red_brick | flat | long brick school wing with a blue glass stair tower |
| gis:11215390 | – | – | –→4 (low) | 13.6 (from_floors) | 0 / 133.6 | 32.4×18.7 | 171.2 | 0.220 | 8 | Y | 2 | 2 (191, 279) | light_gray | flat | probably the grey school building across the playground, target not certain |
| gis:11215391 | – | – | –→1 | 3.4 (from_floors) | 0 / 340.8 | 70.0×5.0 | 170.5 | 0.974 | 4 | Y | 2 | 2 (9, 189) | light_gray | flat | long covered walkway beside the playground |
| gis:11215393 | – | – | –→1 (low) | 3.4 (from_floors) | 0 / 184.9 | 15.7×12.0 | 80.5 | 0.977 | 4 | Y | 3 | 3 (279, 100, 187) | light_gray | flat | roofed shelter or canopy beside the playground, target not certain |
| gis:11214902 | – | – | –→1 (low) | 3.4 (from_floors) | 0 / 60.9 | 11.1×5.6 | 172.4 | 0.971 | 4 | Y | 2 | 2 (8, 188) | dark_gray | flat | small dark cabin next to the school fence, target not certain |
| gis:11036833 | 부흥중학교 | 10000 | 5→5 (+1 below) | 18.1 (register) | 2014.47 / 2023.7 | 92.1×47.3 | 170.8 | 0.464 | 26 | n | 3 | 0 | red_brick | flat | brick school across the road, partly hidden by trees |
| gis:16821018 | 부흥중학교 (dup, 0.92) | – | –→4 (low) | 13.6 (from_floors) | 0 / 1695.0 | 91.7×46.8 | 170.1 | 0.395 | 38 | n | 3 | 0 | red_brick | flat | brick school across the road, partly hidden by trees |

Face views total 22 (= `collection_runs` C3 `face_views: 22`); face azimuths cluster at 10/100/190/280 ± 3° (the school is on the same 10°-rotated grid). Nearest roads: main block and its duplicate sit on 계남로 way:219848661 (box over the road, 0.0 m); the wings front the pedestrian 신흥로238번길 way:783242905 (2.1 / 4.5 m); 부흥중 duplicates also at 0.0 m from 계남로. The two 부흥중 records are a 5-floor and a photo-judged 4-floor estimate of the same mass (conflict/low).

## 8. Capture coverage

Crops (`building_views.status='cropped'`, 363 total): 2 crops → 5 buildings (gis:11201923, gis:11214902, gis:11215390, gis:11215391, gis:14944897), 3 → 115, 4 → 2 (심원고 main and wing). View distance 5.4–109.6 m, median 21.8 m. `bearing_deg` is pano→building-center (`capture.py:108`), so a crop sees the facade whose outward normal ≈ bearing+180°; `face_deg` is the face's outward azimuth (`capture.py:394`). Buildings with ≥1 crop within 45° of the road-facing side's normal: 119/122 (same at 60°). The 3 without any crop of the road-facing side: gis:11182332 (interior villa, 15.2 m from 옥산로113번길), gis:11196895 (중동샛별, N face on 신흥로238번길), gis:11214902 (school-yard cabin). Buildings seen from two sides (sees60 = 2): 50 (see master table).

## 9. Master per-building table (122)

Columns: use; register floors → final floors (basis/status); height m (basis); wall/roof = final values (defaults applied); conf; register area; outline vertices; orthogonal; box w×d; yaw (ccw from east); fit; nearest road (class); edge distance m; facing side (box edge, outward azimuth/octant/edge length; `+v/−v` = long faces, `+u/−u` = short ends; SCHOOL = inside school polygon); crops (+Nf = face views); crops seeing the facing side within 45°/60°; OSM tags; review flags.

| building_id | name | use | reg_f→final (basis/status) | h_m (basis) | wall | roof | conf | area m2 | verts | ortho | w×d m | yaw | fit | nearest road (cls) | dist m | facing side az/oct/len | crops | sees45/60 | osm | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gis:11036833 | 부흥중학교 | 10000 | 5→5 (register/conflict) | 18.1 (register) | red_brick | flat | low | 2014.47 | 26 | n | 92.1×47.3 | 170.8 | 0.464 | way:219848661 계남로 (residential) | 0.0 | -u 99°/E/47.3m | 3 | 1/1 |  | conflict |
| gis:11081057 |  | 01000 | 3→3 (register/conflict) | 10.6 (register) | red_brick | gable | medium | 105.04 | 4 | Y | 11.5×10.8 | 171.1 | 0.973 | way:222729121 신흥로238번길 (service) | 2.9 | +v 189°/S/11.5m | 3 | 1/2 |  | conflict |
| gis:11170718 |  | 01000 | 3→3 (register/unverified) | 10.0 (register) | light_gray | flat | low | 93.37 | 4 | Y | 9.5×9.2 | 78.4 | 0.974 | way:222729122 계남로242번길 (living_street) | 3.0 | -u 192°/S/9.2m | 3 | 1/1 |  |  |
| gis:11171255 | 로얄프라자 | 10000 | 7→7 (register/verified) | 23.8 (from_floors) | light_gray | flat | medium | 1514.48 | 9 | n | 71.4×34.0 | 159.1 | 0.621 | way:222842946 옥산로109번길 (residential) | 4.1 | -v 21°/N/71.4m | 3 | 1/2 | building=commercial building:levels=6 |  |
| gis:11171875 |  | 01000 | 3→3 (register/conflict) | 9.9 (register) | brown | gable | medium | 99.8 | 8 | n | 16.4×9.1 | 81.4 | 0.751 | way:490069622 계남로242번길 (residential) | 0.7 | +v 279°/W/16.4m | 3 | 1/1 |  | conflict |
| gis:11171885 | 뉴월드 프라자 | 04000 | 7→7 (register/conflict) | 24.5 (register) | light_gray | flat | low | 410.72 | 19 | n | 27.4×17.1 | 101.7 | 0.917 | way:490069622 계남로242번길 (residential) | 7.4 | -v 78°/E/27.4m | 3 | 1/1 | building=commercial building:levels=6 | conflict |
| gis:11172810 |  | 01000 | 3→3 (register/conflict) | 9.7 (register) | brown | gable | medium | 88.75 | 4 | Y | 10.6×10.0 | 171.6 | 0.962 | way:222729124 옥산로113번길 (service) | 2.3 | +v 188°/S/10.6m | 3 | 1/1 |  | conflict |
| gis:11173851 |  | 01000 | 3→3 (register/verified) | 9.4 (register) | red_brick | flat | medium | 85.56 | 6 | Y | 13.3×7.8 | 169.3 | 0.939 | way:222140575 계남로260번길 (service) | 1.8 | -u 101°/E/7.8m | 3 | 1/1 |  |  |
| gis:11173936 |  | 01000 | 3→3 (register/verified) | 9.4 (register) | brown | flat | medium | 99.15 | 6 | n | 12.7×9.6 | 171.0 | 0.951 | way:222729117 계남로 (living_street) | 2.5 | +u 279°/W/9.6m | 3 | 1/1 |  |  |
| gis:11174007 |  | 01000 | 3→3 (register/verified) | 9.8 (register) | red_brick | hip | medium | 112.0 | 6 | Y | 12.1×11.1 | 170.5 | 0.937 | way:222842946 옥산로109번길 (residential) | 4.9 | +v 189°/S/12.1m | 3 | 1/2 |  |  |
| gis:11174023 |  | 01000 | 3→3 (register/conflict) | 10.5 (register) | beige | hip | low | 91.78 | 6 | Y | 11.7×11.5 | 171.0 | 0.936 | way:222729120 계남로242번길 (living_street) | 3.9 | -v 9°/N/11.7m | 3 | 1/2 |  | conflict |
| gis:11174024 |  | 01000 | 3→3 (register/conflict) | 10.2 (register) | brown | hip | low | 95.2 | 6 | Y | 11.3×9.7 | 172.2 | 0.941 | way:222729119 계남로242번길 (living_street) | 5.0 | -v 8°/N/11.3m | 3 | 1/2 |  | conflict |
| gis:11177607 |  | 01000 | 3→3 (register/verified) | 9.8 (register) | beige | hip | medium | 90.16 | 4 | Y | 10.3×9.0 | 170.8 | 0.987 | way:783242906 옥산로113번길 (service) | 15.4 | -u 99°/E/9.0m | 3 | 1/1 |  |  |
| gis:11177608 |  | 01000 | 2→2 (register/conflict) | 7.8 (register) | beige | flat | medium | 101.91 | 4 | Y | 12.0×10.5 | 171.2 | 0.981 | way:222842946 옥산로109번길 (residential) | 6.1 | +v 189°/S/12.0m | 3 | 1/2 |  | conflict |
| gis:11177783 | 부흥건물 | 01000 | 4→4 (register/verified) | 13.6 (from_floors) | beige | flat | medium | 90.25 | 4 | Y | 11.6×10.5 | 143.6 | 0.965 | way:219848661 계남로 (residential) | 6.6 | +v 216°/SW/11.6m | 3 | 1/1 |  | height_out_of_range |
| gis:11178530 |  | 01000 | 2→2 (register/conflict) | 7.0 (register) | red_brick | hip | medium | 104.04 | 6 | n | 12.0×9.8 | 171.2 | 0.908 | way:222842946 옥산로109번길 (residential) | 6.7 | +v 189°/S/12.0m | 3 | 1/2 |  | conflict |
| gis:11178810 |  | 01000 | 3→3 (register/verified) | 10.4 (register) | light_gray | flat | medium | 101.95 | 5 | n | 12.2×10.7 | 172.2 | 0.944 | way:222729125 (service) | 1.2 | +u 278°/W/10.7m | 3 | 1/1 |  |  |
| gis:11180755 |  | 01000 | 3→3 (register/conflict) | 12.7 (register) | light_gray | flat | medium | 110.81 | 8 | n | 13.1×12.1 | 170.0 | 0.744 | way:490069622 계남로242번길 (residential) | 0.5 | +u 280°/W/12.1m | 3 | 1/1 |  | conflict |
| gis:11181583 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | beige | flat | medium | 104.02 | 4 | Y | 12.8×11.0 | 172.9 | 0.974 | way:222729124 옥산로113번길 (service) | 5.7 | -v 7°/N/12.8m | 3 | 1/1 |  |  |
| gis:11182332 |  | 01000 | 3→3 (register/conflict) | 9.3 (register) | brown | flat | low | 90.996 | 4 | Y | 10.4×9.9 | 171.8 | 0.964 | way:783242906 옥산로113번길 (service) | 15.2 | -u 98°/E/9.9m | 3 | 0/0 |  | conflict |
| gis:11184284 |  | 01000 | 3→3 (register/unverified) | 9.8 (register) | orange | hip | low | 114.58 | 6 | Y | 13.1×11.5 | 171.3 | 0.872 | way:222842946 옥산로109번길 (residential) | 4.5 | +v 189°/S/13.1m | 3 | 1/2 |  |  |
| gis:11184538 | 블래스랜드 | 14000 | 10→10 (register/conflict) | 31.1 (register) | light_gray | flat | medium | 739.26 | 4 | Y | 31.2×22.4 | 81.5 | 0.994 | way:222842946 옥산로109번길 (residential) | 11.3 | +u 8°/N/22.4m | 3 | 1/1 | building=commercial building:levels=6 | conflict |
| gis:11185213 | 심원고등학교 | 10000 | 5→5 (register/verified) | 20.4 (register) | light_gray | flat | medium | 2542.37 | 39 | Y | 90.5×51.5 | 169.9 | 0.54 | way:219848661 계남로 (residential) | 0.0 | -v 10°/N/90.5m SCHOOL | 4+4f | 1/1 |  |  |
| gis:11185238 |  | 01000 | 3→3 (register/verified) | 10.8 (register) | brown | hip | medium | 87.19 | 6 | Y | 12.9×9.9 | 80.2 | 0.954 | way:222140575 계남로260번길 (service) | 2.4 | -v 100°/E/12.9m | 3 | 1/1 |  |  |
| gis:11185281 | 심원고등학교 | 10000 | 5→5 (register/verified) | 17.0 (from_floors) | red_brick | flat | medium | 597.87 | 10 | Y | 50.5×13.6 | 80.2 | 0.848 | way:783242905 신흥로238번길 (pedestrian) | 2.1 | +v 280°/W/50.5m SCHOOL | 4+4f | 1/1 |  |  |
| gis:11185950 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | brown | hip | medium | 102.73 | 8 | Y | 12.2×11.8 | 80.5 | 0.905 | way:222729124 옥산로113번길 (service) | 5.5 | +u 10°/N/11.8m | 3 | 1/2 |  |  |
| gis:11185986 | 뉴월드타운 | 11000 | 7→7 (register/verified) | 25.2 (register) | light_gray | flat | medium | 624.19 | 6 | Y | 29.5×23.1 | 80.4 | 0.872 | way:222842946 옥산로109번길 (residential) | 14.0 | +u 10°/N/23.1m | 3 | 1/1 |  |  |
| gis:11185995 | 뉴월드타운 | 10000 | 7→7 (register/verified) | 25.2 (register) | light_gray | flat | medium | 624.19 | 6 | Y | 29.5×23.1 | 80.5 | 0.872 | way:222842946 옥산로109번길 (residential) | 14.1 | +u 9°/N/23.1m | 3 | 1/2 | building=commercial building:levels=6 |  |
| gis:11186638 |  | 01000 | 3→3 (register/verified) | 9.3 (register) | red_brick | flat | medium | 100.54 | 6 | n | 12.5×11.6 | 171.3 | 0.898 | way:222729122 계남로242번길 (living_street) | 1.8 | +v 189°/S/12.5m | 3 | 1/1 |  |  |
| gis:11186644 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | beige | flat | medium | 95.47 | 4 | Y | 11.8×11.0 | 81.9 | 0.969 | way:222842946 옥산로109번길 (residential) | 4.0 | -u 188°/S/11.0m | 3 | 1/1 |  |  |
| gis:11186925 |  | 01000 | 3→3 (register/unverified) | 9.4 (register) | brown | flat | low | 92.17 | 4 | Y | 11.5×10.5 | 172.4 | 0.95 | way:222729120 계남로242번길 (living_street) | 4.6 | -v 8°/N/11.5m | 3 | 1/1 |  |  |
| gis:11188106 |  | 01000 | 3→3 (register/conflict) | 10.0 (register) | light_gray | flat | medium | 89.88 | 6 | Y | 11.2×10.4 | 54.6 | 0.918 | way:219848661 계남로 (residential) | 6.4 | -u 215°/SW/10.4m | 3 | 1/2 |  | conflict |
| gis:11188308 | 중3동행정복지센터 | 03000 | 2→2 (register/verified) | 8.3 (register) | light_gray | flat | medium | 354.5 | 25 | n | 22.6×17.5 | 80.8 | 0.944 | way:222729124 옥산로113번길 (service) | 4.8 | +u 9°/N/17.5m | 3 | 1/1 |  |  |
| gis:11188641 | 골든타워 | 09000 | 9→9 (register/conflict) | 34.7 (register) | light_gray | flat | low | 751.22 | 5 | n | 37.6×22.3 | 80.2 | 0.964 | way:222842946 옥산로109번길 (residential) | 5.6 | +u 10°/N/22.3m | 3 | 1/1 | building=commercial building:levels=6 | conflict |
| gis:11190349 |  | 01000 | 3→3 (register/verified) | 10.4 (register) | beige | flat | medium | 89.05 | 5 | n | 12.0×9.6 | 169.8 | 0.93 | way:222729123 옥산로109번길 (living_street) | 1.4 | +u 280°/W/9.6m | 3 | 1/1 |  |  |
| gis:11190501 |  | 01000 | 3→3 (register/verified) | 8.4 (register) | red_brick | gable | medium | 91.44 | 4 | Y | 10.8×10.2 | 170.9 | 0.972 | way:222729123 옥산로109번길 (living_street) | 2.7 | +u 279°/W/10.2m | 3 | 1/1 |  |  |
| gis:11190682 |  | 01000 | 3→3 (register/verified) | 10.9 (register) | light_gray | flat | medium | 101.27 | 5 | n | 11.8×10.0 | 173.0 | 0.913 | way:222729125 (service) | 1.4 | +u 277°/W/10.0m | 3 | 1/1 |  |  |
| gis:11190802 |  | 01000 | 3→3 (register/verified) | 9.8 (register) | red_brick | flat | medium | 106.44 | 6 | Y | 12.5×11.9 | 82.1 | 0.937 | way:222729124 옥산로113번길 (service) | 2.5 | -u 188°/S/11.9m | 3 | 1/1 |  |  |
| gis:11190876 |  | 01000 | 3→3 (register/conflict) | 10.7 (register) | red_brick | hip | low | 89.19 | 6 | Y | 10.6×8.7 | 169.7 | 0.954 | way:222140575 계남로260번길 (service) | 1.2 | -u 100°/E/8.7m | 3 | 1/1 |  | conflict |
| gis:11191812 |  | 01000 | 3→3 (register/verified) | 10.7 (register) | red_brick | flat | medium | 89.64 | 6 | Y | 10.5×10.2 | 82.6 | 0.911 | way:222729121 신흥로238번길 (service) | 2.7 | +u 7°/N/10.2m | 3 | 1/2 |  |  |
| gis:11192064 |  | 01000 | 3→3 (register/verified) | 10.2 (register) | light_gray | flat | medium | 111.02 | 4 | Y | 13.2×9.0 | 173.1 | 0.97 | way:222140575 계남로260번길 (service) | 4.5 | +u 277°/W/9.0m | 3 | 1/1 |  |  |
| gis:11192647 |  | 01000 | 3→3 (register/verified) | 10.7 (register) | brown | flat | medium | 105.87 | 4 | Y | 12.0×9.5 | 81.5 | 0.982 | way:222729124 옥산로113번길 (service) | 2.3 | -u 189°/S/9.5m | 3 | 1/1 |  |  |
| gis:11192750 | 옥산경로당 | 10000 | 1→1 (register/verified) | 3.1 (register) | pink | flat | medium | 65.55 | 4 | Y | 14.5×5.9 | 81.1 | 0.964 | way:783242905 신흥로238번길 (pedestrian) | 10.1 | -v 99°/E/14.5m | 3 | 1/1 | building=yes amenity=social_facility name=옥산경로당 |  |
| gis:11192751 |  | 01000 | 3→3 (register/verified) | 10.3 (register) | brown | shed | medium | 110.14 | 7 | n | 13.1×12.5 | 82.2 | 0.917 | way:222729124 옥산로113번길 (service) | 3.3 | +u 8°/N/12.5m | 3 | 1/1 |  |  |
| gis:11192752 |  | 01000 | 3→3 (register/verified) | 9.2 (register) | red_brick | flat | medium | 90.94 | 4 | Y | 10.8×10.7 | 80.7 | 0.98 | way:783242906 옥산로113번길 (service) | 2.8 | -v 99°/E/10.8m | 3 | 1/1 |  |  |
| gis:11192753 |  | 01000 | 2→2 (register/verified) | 7.2 (register) | red_brick | hip | medium | 88.02 | 4 | Y | 11.3×9.7 | 169.6 | 0.973 | way:783242906 옥산로113번길 (service) | 2.6 | -u 100°/E/9.7m | 3 | 1/2 |  |  |
| gis:11192813 |  | 01000 | 3→3 (register/unverified) | 9.5 (register) | light_gray | flat | low | 113.22 | 8 | Y | 12.7×12.2 | 170.6 | 0.923 | way:222729124 옥산로113번길 (service) | 5.6 | -v 9°/N/12.7m | 3 | 1/2 |  |  |
| gis:11192816 |  | 01000 | 3→3 (register/conflict) | 8.2 (register) | orange | hip | low | 115.82 | 6 | Y | 14.0×10.5 | 170.7 | 0.905 | way:222842946 옥산로109번길 (residential) | 6.1 | +v 189°/S/14.0m | 3 | 1/2 |  | conflict |
| gis:11196440 |  | 01000 | 3→3 (register/verified) | 9.7 (register) | orange | flat | medium | 93.92 | 6 | Y | 11.4×10.0 | 170.2 | 0.943 | way:222729119 계남로242번길 (living_street) | 3.2 | +v 190°/S/11.4m | 3 | 1/2 |  |  |
| gis:11196854 |  | 01000 | 3→3 (register/verified) | 10.1 (register) | red_brick | flat | medium | 92.36 | 6 | Y | 10.3×9.9 | 82.7 | 0.941 | way:222729120 계남로242번길 (living_street) | 3.7 | +u 7°/N/9.9m | 3 | 1/2 |  |  |
| gis:11196895 | 중동샛별 | 10000 | 4→4 (register/conflict) | 14.0 (register) | red_brick | flat | medium | 346.46 | 6 | n | 23.9×15.7 | 171.1 | 0.961 | way:222729121 신흥로238번길 (service) | 2.6 | -v 9°/N/23.9m | 3 | 0/0 |  | conflict |
| gis:11198845 |  | 01000 | 3→3 (register/verified) | 9.7 (register) | brown | hip | medium | 92.28 | 6 | Y | 10.8×10.8 | 81.0 | 0.937 | way:222140575 계남로260번길 (service) | 1.7 | -v 99°/E/10.8m | 3 | 2/2 |  |  |
| gis:11198856 |  | 01000 | 3→3 (register/unverified) | 9.4 (register) | red_brick | flat | low | 93.27 | 4 | Y | 10.9×10.5 | 81.4 | 0.975 | way:222140575 계남로260번길 (service) | 1.7 | -v 99°/E/10.9m | 3 | 1/1 |  |  |
| gis:11200829 |  | 01000 | 3→3 (register/verified) | 10.4 (register) | light_gray | flat | medium | 108.42 | 6 | Y | 12.6×11.8 | 83.3 | 0.92 | way:222729121 신흥로238번길 (service) | 2.9 | +u 7°/N/11.8m | 3 | 1/2 |  |  |
| gis:11200835 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | brown | flat | medium | 103.62 | 5 | n | 11.0×10.3 | 82.4 | 0.946 | way:222140575 계남로260번길 (service) | 2.1 | -v 98°/E/11.0m | 3 | 1/1 |  |  |
| gis:11201615 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | light_gray | hip | low | 0.0 | 4 | Y | 9.6×4.9 | 77.1 | 0.935 | way:783242906 옥산로113번길 (service) | 7.2 | +v 283°/W/9.6m | 3 | 1/2 |  | filled-low_confidence |
| gis:11201621 |  |  | -→- (-/none) | 2.0 (photo_geometry) | light_gray | flat | medium | 0.0 | 4 | Y | 38.2×2.2 | 169.8 | 0.996 | way:219848661 계남로 (residential) | 35.3 | -u 100°/E/2.2m | 3 | 1/1 |  |  |
| gis:11201622 |  |  | -→- (-/none) | 2.0 (photo_geometry) | light_gray | flat | medium | 0.0 | 4 | Y | 33.0×2.2 | 169.9 | 1.0 | way:222140575 계남로260번길 (service) | 16.7 | +u 280°/W/2.2m | 3 | 1/1 |  |  |
| gis:11201637 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | light_gray | hip | low | 0.0 | 4 | Y | 6.9×4.3 | 80.5 | 0.984 | way:222140575 계남로260번길 (service) | 15.9 | +v 279°/W/6.9m | 3 | 1/1 |  | filled-low_confidence |
| gis:11201639 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | white | hip | medium | 0.0 | 4 | Y | 8.3×4.8 | 82.8 | 0.946 | way:222729124 옥산로113번길 (service) | 4.2 | -u 187°/S/4.8m | 3 | 1/2 |  | filled |
| gis:11201645 | 리치타운 오피스텔 | 14000 | 10→10 (register/conflict) | 33.4 (register) | light_gray | flat | low | 674.58 | 4 | Y | 38.3×24.3 | 80.6 | 0.999 | way:222842946 옥산로109번길 (residential) | 7.4 | +u 9°/N/24.3m | 3 | 1/1 | building=apartments building:levels=10 building:flats=48 height=33 | conflict |
| gis:11201923 |  |  | -→- (-/none) | 10.0 (default) | light_gray | flat |  | 0.0 | 4 | Y | 9.2×6.1 | 168.9 | 0.999 | way:219848661 계남로 (residential) | 50.4 | -v 11°/N/9.2m | 2 | 1/1 |  | default_height |
| gis:11202584 |  |  | -→- (-/none) | 2.5 (photo_geometry) | light_gray | flat | low | 0.0 | 4 | Y | 6.5×2.5 | 80.3 | 0.976 | way:222140575 계남로260번길 (service) | 15.2 | +v 280°/W/6.5m | 3 | 1/2 |  | low_confidence |
| gis:11202912 |  | 01000 | 3→3 (register/unverified) | 10.7 (register) | brown | flat | low | 95.47 | 6 | n | 12.0×11.0 | 169.4 | 0.881 | way:222729119 계남로242번길 (living_street) | 4.5 | -v 11°/N/12.0m | 3 | 1/1 |  |  |
| gis:11203818 |  | 01000 | 3→3 (register/conflict) | 10.1 (register) | brown | flat | low | 105.62 | 6 | Y | 11.4×11.2 | 80.1 | 0.933 | way:222729121 신흥로238번길 (service) | 2.6 | -u 190°/S/11.2m | 3 | 1/1 |  | conflict |
| gis:11203823 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | red_brick | flat | medium | 100.295 | 6 | Y | 11.3×10.5 | 175.3 | 0.853 | way:222140575 계남로260번길 (service) | 1.6 | -u 95°/E/10.5m | 3 | 1/1 |  |  |
| gis:11203830 |  | 01000 | 3→3 (register/verified) | 9.4 (register) | brown | flat | medium | 96.02 | 6 | Y | 11.8×10.8 | 82.0 | 0.93 | way:222729116 계남로242번길 (living_street) | 2.7 | +u 8°/N/10.8m | 3 | 1/1 |  |  |
| gis:11205134 |  | 01000 | 3→3 (register/unverified) | 10.9 (register) | red_brick | flat | low | 103.33 | 4 | Y | 11.9×10.3 | 170.7 | 0.982 | way:222729121 신흥로238번길 (service) | 2.9 | +v 189°/S/11.9m | 3 | 1/2 |  |  |
| gis:11206215 |  | 01000 | 3→3 (register/unverified) | 10.2 (register) | red_brick | flat | low | 96.35 | 6 | Y | 12.0×11.6 | 79.4 | 0.88 | way:222729116 계남로242번길 (living_street) | 2.6 | +u 11°/N/11.6m | 3 | 1/2 |  |  |
| gis:11206216 |  | 01000 | 3→3 (register/verified) | 10.1 (register) | beige | hip | medium | 105.44 | 4 | Y | 11.2×9.0 | 80.2 | 0.961 | way:222729122 계남로242번길 (living_street) | 4.5 | +v 280°/W/11.2m | 3 | 1/2 |  |  |
| gis:11207089 |  | 01000 | 3→3 (register/verified) | 10.2 (register) | brown | hip | medium | 88.88 | 6 | Y | 13.2×7.6 | 143.9 | 0.916 | way:219848661 계남로 (residential) | 7.3 | +v 216°/SW/13.2m | 3 | 1/2 |  |  |
| gis:11207507 |  | 01000 | 3→3 (register/verified) | 10.7 (register) | brown | flat | medium | 108.78 | 6 | Y | 12.3×11.8 | 168.9 | 0.946 | way:222729121 신흥로238번길 (service) | 1.5 | -v 11°/N/12.3m | 3 | 1/1 |  |  |
| gis:11208812 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | red_brick | hip | medium | 103.35 | 8 | n | 12.2×12.0 | 170.9 | 0.914 | way:222729124 옥산로113번길 (service) | 5.2 | -v 9°/N/12.2m | 3 | 1/2 |  |  |
| gis:11208985 |  | 01000 | 3→3 (register/verified) | 9.3 (register) | red_brick | flat | medium | 101.42 | 6 | Y | 12.5×11.8 | 169.7 | 0.898 | way:222729122 계남로242번길 (living_street) | 1.5 | +v 190°/S/12.5m | 3 | 1/1 |  |  |
| gis:11209217 |  | 01000 | 3→3 (register/verified) | 10.2 (register) | brown | flat | medium | 98.68 | 4 | Y | 11.4×9.9 | 172.1 | 0.982 | way:222140575 계남로260번길 (service) | 2.1 | -u 98°/E/9.9m | 3 | 1/1 |  |  |
| gis:11209616 |  | 01000 | 3→3 (register/verified) | 10.7 (register) | brown | hip | medium | 103.25 | 4 | Y | 11.8×10.6 | 169.4 | 0.948 | way:222729120 계남로242번길 (living_street) | 2.8 | +v 191°/S/11.8m | 3 | 1/2 |  |  |
| gis:11209981 |  | 01000 | 3→3 (register/verified) | 10.4 (register) | red_brick | hip | medium | 93.17 | 4 | Y | 10.7×9.0 | 171.0 | 0.988 | way:783242906 옥산로113번길 (service) | 2.6 | -u 99°/E/9.0m | 3 | 1/1 |  |  |
| gis:11210095 |  | 01000 | 3→3 (register/conflict) | 10.9 (register) | red_brick | flat | low | 106.74 | 5 | n | 11.7×10.2 | 171.0 | 0.972 | way:222729121 신흥로238번길 (service) | 2.4 | -v 9°/N/11.7m | 3 | 1/1 |  | conflict |
| gis:11210173 |  | 01000 | 2→2 (register/verified) | 7.7 (register) | red_brick | hip | medium | 102.46 | 4 | Y | 12.4×10.1 | 171.6 | 0.97 | way:222842946 옥산로109번길 (residential) | 6.8 | +v 188°/S/12.4m | 3 | 1/1 |  |  |
| gis:11211430 |  | 01000 | 3→3 (register/verified) | 9.7 (register) | light_gray | flat | medium | 93.7 | 4 | Y | 10.2×9.9 | 50.9 | 0.971 | way:219848661 계남로 (residential) | 9.5 | -u 219°/SW/9.9m | 3 | 1/2 |  |  |
| gis:11214369 |  | 01000 | 3→3 (register/conflict) | 9.9 (register) | white | flat | medium | 95.52 | 4 | Y | 13.9×7.1 | 170.6 | 0.951 | way:222729123 옥산로109번길 (living_street) | 2.2 | -u 99°/E/7.1m | 3 | 1/2 |  | conflict |
| gis:11214902 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | dark_gray | flat | low | 0.0 | 4 | Y | 11.1×5.6 | 172.4 | 0.971 | way:219848661 계남로 (residential) | 8.4 | -u 98°/E/5.6m SCHOOL | 2+2f | 0/0 |  | filled-low_confidence |
| gis:11214904 |  | 01000 | 3→3 (register/verified) | 10.3 (register) | dark_gray | flat | medium | 112.45 | 5 | n | 13.6×12.8 | 169.7 | 0.918 | way:222729124 옥산로113번길 (service) | 5.0 | -v 10°/N/13.6m | 3 | 1/2 |  |  |
| gis:11215054 |  | 01000 | 3→3 (register/verified) | 9.9 (register) | brown | flat | medium | 105.79 | 4 | Y | 12.1×10.1 | 170.4 | 0.961 | way:222729120 계남로242번길 (living_street) | 3.5 | +v 190°/S/12.1m | 3 | 1/2 |  |  |
| gis:11215159 |  | 01000 | 3→3 (register/verified) | 10.0 (register) | brown | flat | medium | 113.67 | 4 | Y | 12.7×11.9 | 81.4 | 0.971 | way:222729124 옥산로113번길 (service) | 4.8 | +u 9°/N/11.9m | 3 | 1/1 |  |  |
| gis:11215178 |  | 01000 | 3→3 (register/verified) | 11.4 (register) | brown | flat | medium | 88.61 | 6 | Y | 11.1×10.6 | 171.6 | 0.918 | way:222729121 신흥로238번길 (service) | 3.2 | -v 8°/N/11.1m | 3 | 2/2 |  |  |
| gis:11215390 |  |  | -→4 (photo_count/filled) | 13.6 (from_floors) | light_gray | flat | low | 0.0 | 8 | Y | 32.4×18.7 | 171.2 | 0.22 | way:783242905 신흥로238번길 (pedestrian) | 14.5 | +u 279°/W/18.7m SCHOOL | 2+2f | 1/1 |  | filled-low_confidence |
| gis:11215391 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | light_gray | flat | medium | 0.0 | 4 | Y | 70.0×5.0 | 170.5 | 0.974 | way:222729124 옥산로113번길 (service) | 3.9 | +v 189°/S/70.0m SCHOOL | 2+2f | 1/1 |  | filled |
| gis:11215393 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | light_gray | flat | low | 0.0 | 4 | Y | 15.7×12.0 | 80.5 | 0.977 | way:783242905 신흥로238번길 (pedestrian) | 47.9 | +v 279°/W/15.7m SCHOOL | 3+3f | 1/1 |  | filled-low_confidence |
| gis:11216508 |  | 01000 | 3→3 (register/verified) | 10.4 (register) | red_brick | flat | medium | 92.86 | 4 | Y | 11.8×9.8 | 171.3 | 0.972 | way:222729119 계남로242번길 (living_street) | 2.8 | +v 189°/S/11.8m | 3 | 1/1 |  |  |
| gis:11216686 |  | 01000 | 3→3 (register/verified) | 9.8 (register) | red_brick | flat | medium | 88.83 | 10 | n | 13.7×10.6 | 78.7 | 0.819 | way:222729122 계남로242번길 (living_street) | 1.7 | +u 11°/N/10.6m | 3 | 1/1 |  |  |
| gis:11216698 |  | 01000 | 3→3 (register/verified) | 10.9 (register) | brown | flat | medium | 91.0 | 4 | Y | 11.1×8.9 | 171.6 | 0.972 | way:222729123 옥산로109번길 (living_street) | 2.1 | +u 278°/W/8.9m | 3 | 1/2 |  |  |
| gis:11216699 |  | 01000 | 3→3 (register/verified) | 10.0 (register) | light_gray | hip | medium | 89.64 | 12 | n | 12.3×11.9 | 175.1 | 0.823 | way:222729122 계남로242번길 (living_street) | 1.4 | -v 5°/N/12.3m | 3 | 1/1 |  |  |
| gis:11216700 |  | 01000 | 3→3 (register/verified) | 10.3 (register) | brown | hip | medium | 92.84 | 4 | Y | 10.9×9.6 | 81.3 | 0.983 | way:222729122 계남로242번길 (living_street) | 2.5 | +u 9°/N/9.6m | 3 | 1/2 |  |  |
| gis:11216701 |  | 01000 | 3→3 (register/conflict) | 9.5 (register) | red_brick | hip | low | 111.08 | 4 | Y | 16.8×7.9 | 167.5 | 0.942 | way:222729123 옥산로109번길 (living_street) | 3.1 | -u 102°/E/7.9m | 3 | 1/2 |  | conflict |
| gis:11216703 |  | 01000 | 3→3 (register/verified) | 9.2 (register) | red_brick | flat | high | 100.81 | 4 | Y | 10.5×10.4 | 170.7 | 0.953 | way:222729122 계남로242번길 (living_street) | 2.7 | +v 189°/S/10.5m | 3 | 1/2 |  |  |
| gis:11216707 |  | 01000 | 3→3 (register/verified) | 10.5 (register) | brown | hip | medium | 92.44 | 6 | Y | 10.8×10.8 | 79.9 | 0.911 | way:222729120 계남로242번길 (living_street) | 4.1 | +u 10°/N/10.8m | 3 | 1/2 |  |  |
| gis:11216708 |  | 01000 | 3→3 (register/conflict) | 11.0 (register) | red_brick | flat | medium | 92.22 | 4 | Y | 11.1×10.0 | 172.5 | 0.978 | way:222729120 계남로242번길 (living_street) | 1.8 | -v 7°/N/11.1m | 3 | 1/1 |  | conflict |
| gis:11216743 |  | 01000 | 3→3 (register/conflict) | 11.0 (register) | brown | flat | medium | 95.7 | 10 | n | 13.0×11.3 | 82.9 | 0.852 | way:222729119 계남로242번길 (living_street) | 2.9 | +u 7°/N/11.3m | 3 | 1/2 |  | conflict |
| gis:11216744 |  | 01000 | 3→3 (register/unverified) | 10.8 (register) | brown | flat | low | 96.51 | 6 | Y | 11.7×11.7 | 174.0 | 0.922 | way:222729119 계남로242번길 (living_street) | 4.4 | -v 6°/N/11.7m | 3 | 1/2 |  |  |
| gis:11216746 |  | 01000 | 3→3 (register/unverified) | 10.0 (register) | red_brick | flat |  | 95.28 | 4 | Y | 10.6×9.6 | 81.3 | 0.987 | way:222140575 계남로260번길 (service) | 4.0 | -v 99°/E/10.6m | 3 | 1/1 |  |  |
| gis:11216747 |  | 01000 | 3→3 (register/verified) | 9.4 (register) | brown | flat | high | 104.68 | 6 | n | 11.6×10.9 | 169.0 | 0.961 | way:222729120 계남로242번길 (living_street) | 3.0 | +v 191°/S/11.6m | 3 | 1/2 |  |  |
| gis:11216748 |  | 01000 | 3→3 (register/conflict) | 9.7 (register) | red_brick | flat | medium | 103.26 | 4 | Y | 12.7×9.8 | 170.4 | 0.958 | way:222729120 계남로242번길 (living_street) | 3.9 | +v 190°/S/12.7m | 3 | 1/1 |  | conflict |
| gis:11216777 |  | 01000 | 3→3 (register/unverified) | 9.4 (register) | brown | hip | low | 96.24 | 6 | Y | 12.4×11.1 | 82.2 | 0.863 | way:222729116 계남로242번길 (living_street) | 2.4 | +u 8°/N/11.1m | 3 | 1/1 |  |  |
| gis:11216779 |  | 01000 | 3→3 (register/verified) | 10.4 (register) | red_brick | flat | high | 92.43 | 6 | Y | 11.2×9.6 | 170.8 | 0.962 | way:222140575 계남로260번길 (service) | 2.1 | -u 99°/E/9.6m | 3 | 1/2 |  |  |
| gis:11216780 |  | 01000 | 3→3 (register/verified) | 10.0 (register) | brown | flat | medium | 89.41 | 6 | Y | 12.3×10.2 | 168.8 | 0.918 | way:222140575 계남로260번길 (service) | 0.9 | -u 101°/E/10.2m | 3 | 1/1 |  |  |
| gis:11216783 |  | 01000 | 3→3 (register/verified) | 11.6 (register) | red_brick | flat | medium | 92.09 | 4 | Y | 11.4×9.8 | 170.1 | 0.976 | way:222729119 계남로242번길 (living_street) | 3.5 | +v 190°/S/11.4m | 3 | 1/1 |  |  |
| gis:11216784 |  | 01000 | 3→3 (register/verified) | 9.2 (register) | red_brick | flat | medium | 91.93 | 4 | Y | 11.4×10.2 | 170.9 | 0.988 | way:222729119 계남로242번길 (living_street) | 2.9 | +v 189°/S/11.4m | 3 | 1/2 |  |  |
| gis:11217145 |  | 01000 | 3→3 (register/verified) | 11.6 (register) | brown | flat | high | 103.81 | 4 | Y | 10.2×9.8 | 81.1 | 0.959 | way:222729121 신흥로238번길 (service) | 3.1 | -u 189°/S/9.8m | 3 | 1/1 |  |  |
| gis:11217615 |  | 01000 | 3→3 (register/verified) | 10.3 (register) | light_gray | flat | medium | 93.15 | 4 | Y | 10.7×9.1 | 79.8 | 0.969 | way:490069622 계남로242번길 (residential) | 3.4 | +v 280°/W/10.7m | 3 | 1/1 |  |  |
| gis:11217923 |  | 01000 | 3→3 (register/conflict) | 10.5 (register) | red_brick | hip | medium | 102.28 | 6 | Y | 12.4×10.0 | 82.6 | 0.911 | way:222729124 옥산로113번길 (service) | 4.3 | +u 7°/N/10.0m | 3 | 1/2 |  | conflict |
| gis:12403717 |  | 09000 | 8→8 (register/conflict) | 30.4 (register) | light_gray | flat | low | 815.79 | 5 | n | 37.1×23.1 | 81.2 | 0.966 | way:222842945 (residential) | 4.7 | +v 279°/W/37.1m | 3 | 1/1 | building=commercial building:levels=6 | conflict |
| gis:12425559 |  | 01000 | 3→3 (register/conflict) | 10.8 (register) | light_gray | flat | medium | 87.58 | 5 | n | 11.7×10.4 | 168.7 | 0.848 | way:222140575 계남로260번길 (service) | 0.1 | -u 101°/E/10.4m | 3 | 1/1 |  | conflict |
| gis:12996130 |  | 01000 | 3→3 (register/conflict) | 10.8 (register) | light_gray | gable | medium | 101.1 | 5 | n | 11.9×10.7 | 171.1 | 0.927 | way:222140575 계남로260번길 (service) | 2.0 | -u 99°/E/10.7m | 3 | 1/1 |  | conflict |
| gis:14944897 | 심원고등학교 |  | -→5 (photo_count/filled) | 17.0 (from_floors) | light_gray | flat | medium | 0.0 | 44 | n | 91.3×54.6 | 170.4 | 0.438 | way:219848661 계남로 (residential) | 0.0 | -v 10°/N/91.3m SCHOOL | 2+2f | 1/1 |  | filled |
| gis:15358826 | 심원고등학교 |  | -→5 (photo_count/filled) | 17.0 (from_floors) | red_brick | flat | medium | 0.0 | 4 | Y | 52.7×16.3 | 82.5 | 0.96 | way:783242905 신흥로238번길 (pedestrian) | 4.5 | +v 278°/W/52.7m SCHOOL | 3+3f | 1/1 |  | filled |
| gis:15839722 |  |  | -→- (-/none) | 2.5 (photo_geometry) | light_gray | flat | low | 0.0 | 13 | n | 9.9×4.8 | 169.5 | 0.723 | way:219848661 계남로 (residential) | 42.2 | -u 101°/E/4.8m | 3 | 1/1 |  | low_confidence |
| gis:16052777 |  |  | -→1 (photo_count/filled) | 3.4 (from_floors) | dark_gray | flat | medium | 0.0 | 4 | Y | 6.7×3.1 | 79.8 | 0.997 | way:219848661 계남로 (residential) | 32.6 | +u 10°/N/3.1m | 3 | 2/2 |  | filled |
| gis:16501307 | 뉴월드타운 |  | 7→7 (register/unverified) | 23.8 (from_floors) | light_gray | flat | low | 0.0 | 6 | Y | 29.0×21.5 | 80.7 | 0.9 | way:222842946 옥산로109번길 (residential) | 13.4 | +u 9°/N/21.5m | 3 | 1/2 |  |  |
| gis:16821018 | 부흥중학교 |  | -→4 (photo_count/filled) | 13.6 (from_floors) | red_brick | flat | low | 0.0 | 38 | n | 91.7×46.8 | 170.1 | 0.395 | way:219848661 계남로 (residential) | 0.0 | -u 100°/E/46.8m | 3 | 1/1 | building=school | filled-low_confidence |
| gis:17639013 | 중3동 주민센터 |  | 2→2 (register/verified) | 6.8 (from_floors) | light_gray | flat | high | 0.0 | 33 | n | 22.1×17.6 | 80.6 | 0.959 | way:222842946 옥산로109번길 (residential) | 6.2 | -u 189°/S/17.6m | 3 | 1/1 | building=yes amenity=community_centre name=중3동 주민센터 |  |
| gis:18692828 | 뉴월드 프라자 |  | 7→7 (register/conflict) | 23.8 (from_floors) | light_gray | flat | low | 0.0 | 6 | n | 31.4×15.4 | 102.3 | 0.856 | way:490069622 계남로242번길 (residential) | 8.5 | -v 78°/E/31.4m | 3 | 1/2 |  | conflict |

## 10. Signals available vs. missing for U5 rules (facts only)

- Available per building: usability code (8 classes, 89 % one class), final floors/height/wall colour/roof shape with basis and confidence, 사용승인 year (102 of 122), basement count (50 with 1), footprint vertex count + orthogonality + box size + fit, nearest road + edge distance + facing side azimuth and width, a free-text note with recurring facade vocabulary (brick 75, stair tower 28, glass 27, ground-floor shop 24, pitched/tiled roof 19, fence/wall 14, balcony 11, attic/dormer 11, bay window 10, stone 10), crops of the road-facing facade for 119/122.
- Available per street: class, name, oneway (5), surface (4), sidewalk tag (2 incl. `sidewalk:both` which the builder ignores), lanes/lit/maxheight only on the unused link; owned segment count and lengths.
- Absent in data: any `shop`/`amenity` on commercial buildings (sign names must be fictional anyway), OSM trees/lamps/benches/crossings (0 nodes returned), road `width`, interior alleys for 2 villas and the school yard, roof colour as a field (only in notes), floors_below usage, and the per-face vertical structure of the 4 big school outlines (26–44 vertices, fit 0.40–0.54), which today appear as boxes overlapping 계남로 and each other (6 duplicate-outline pairs listed in §2).