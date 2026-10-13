"""V-World satellite z19 mosaic of one H3 cell (+ pad) -> data/satellite/<cell>-z19.jpg and .json (tile_x0, tile_y0), no drawing.

Usage (repo root): uv run --env-file .env --with h3 --with pillow python .claude/skills/cycle-build/scripts/satellite_cell.py <cell>
Then: uv run src/trees.py --cells <cell>. Tiles are cached in data/satellite/tiles/."""
import json, math, os, sys, time, urllib.request
import h3
from PIL import Image
cell, Z = sys.argv[1], 19
ring = h3.cell_to_boundary(cell)
pad = 0.0008
lat0, lat1 = min(p[0] for p in ring) - pad, max(p[0] for p in ring) + pad
lon0, lon1 = min(p[1] for p in ring) - pad, max(p[1] for p in ring) + pad
def tile(lat, lon):
    n = 2 ** Z
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
x0, y1 = tile(lat0, lon0); x1, y0 = tile(lat1, lon1)
tx0, tx1, ty0, ty1 = int(x0), int(x1), int(y0), int(y1)
key = os.environ["VWORLD_KEY"]
img = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (40, 40, 40))
got = 0
for tx in range(tx0, tx1 + 1):
    for ty in range(ty0, ty1 + 1):
        cache = f"data/satellite/tiles/{Z}_{ty}_{tx}.jpeg"
        if not os.path.exists(cache):
            url = f"https://api.vworld.kr/req/wmts/1.0.0/{key}/Satellite/{Z}/{ty}/{tx}.jpeg"
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "roblox-map"}), timeout=30) as r:
                        data = r.read()
                    break
                except OSError:
                    if attempt == 3: raise
                    time.sleep(5)
            os.makedirs(os.path.dirname(cache), exist_ok=True); open(cache, "wb").write(data); got += 1
            time.sleep(0.1)
        img.paste(Image.open(cache).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
img.save(f"data/satellite/{cell}-z19.jpg", quality=92)
json.dump({"tile_x0": tx0, "tile_y0": ty0, "zoom": Z}, open(f"data/satellite/{cell}-z19.json", "w"))
print(cell, img.size, "new tiles", got)
