"""Satellite (V-World z19) resampled onto the pixel grid of a straight-down Studio capture; side by side and blended.

Usage (repo root): uv run --env-file .env --with h3 --with shapely --with pillow python .claude/skills/cycle-verify/scripts/satellite_compare.py
  <studio capture.jpg> <centre x stud> <centre z stud> <px per stud> [out prefix, default data/compare/now]
A capture from height 650 looking straight down with the default 70 degree field of view is 0.974 px per stud (1631 x 882 window).
Tiles are cached in data/satellite/tiles/ (git ignored)."""
import io, math, os, sys, time, tomllib, urllib.request
sys.path.insert(0, "src")
import layout
from PIL import Image, ImageDraw
cap = Image.open(sys.argv[1]).convert("RGB")
cx, cz, ppx = float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
OUT = sys.argv[5] if len(sys.argv) > 5 else "data/compare/now"   # stud at image centre, px per stud
W, H = cap.size
fr = layout.Frame.from_cfg(tomllib.load(open("config.toml", "rb")))
Z = 19
def tile(lat, lon):
    n = 2 ** Z
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
def stud(px, py): return cx + (px - W / 2) / ppx, cz + (py - H / 2) / ppx
corners = [tile(*layout.from_studs(fr, *stud(px, py))) for px in (0, W) for py in (0, H)]
tx0, tx1 = int(min(c[0] for c in corners)), int(max(c[0] for c in corners))
ty0, ty1 = int(min(c[1] for c in corners)), int(max(c[1] for c in corners))
key = os.environ["VWORLD_KEY"]
mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (40, 40, 40))
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
                except (TimeoutError, OSError):
                    if attempt == 3: raise
                    time.sleep(5)
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            open(cache, "wb").write(data)
        mosaic.paste(Image.open(cache).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
# the mapping is affine to well under a pixel over 1 km: fit it from three corners and let PIL resample
def src(px, py):
    x, y = tile(*layout.from_studs(fr, *stud(px, py)))
    return (x - tx0) * 256, (y - ty0) * 256
(x00, y00), (x10, y10), (x01, y01) = src(0, 0), src(W, 0), src(0, H)
sat = mosaic.transform((W, H), Image.AFFINE, ((x10 - x00) / W, (x01 - x00) / H, x00, (y10 - y00) / W, (y01 - y00) / H, y00), Image.BICUBIC)
out = Image.new("RGB", (W * 2 + 10, H), (255, 255, 255))
out.paste(sat, (0, 0)); out.paste(cap, (W + 10, 0))
d = ImageDraw.Draw(out)
d.text((10, 10), "V-World satellite z19", fill=(255, 255, 0)); d.text((W + 20, 10), "Studio top view (same area, north up)", fill=(255, 255, 0))
out.save(f"{OUT}_side_by_side.jpg", quality=88)
Image.blend(sat, cap, 0.5).save(f"{OUT}_blend.jpg", quality=88)
sat.save(f"{OUT}_satellite.jpg", quality=88)
print("tiles", (tx1 - tx0 + 1) * (ty1 - ty0 + 1))
