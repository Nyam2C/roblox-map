"""data/build/<cell>/chunk-NNN.luau -> data/build/<cell>/chunks.json (data only) for the Studio HttpService path.

Usage (repo root, after build_luau.py): python3 .claude/skills/cycle-build/scripts/chunks_json.py <cell>"""
import glob, json, re, sys

cell = sys.argv[1]
PAIR = re.compile(r'(\w+)=("([^"]*)"|-?\d+(?:\.\d+)?)')


def table(body):
    out = {}
    for key, raw, s in PAIR.findall(body):
        out[key] = s if raw.startswith('"') else (float(raw) if "." in raw else int(raw))
    return out


chunks, counts = [], {}
for path in sorted(glob.glob(f"data/build/{cell}/chunk-*.luau")):
    text = open(path, encoding="utf-8").read()
    looks_line = next(l for l in text.splitlines() if l.startswith("local LOOKS = "))
    looks = {}
    for kind, m, r, g, b in re.findall(r'(\w+)=\{"(\w+)",(\d+),(\d+),(\d+)\}', looks_line):
        looks[kind] = [m, int(r), int(g), int(b)]
    walls = {}
    wpart = looks_line.split("walls={", 1)
    if len(wpart) == 2:
        for name, r, g, b in re.findall(r'\["([^"]+)"\]=\{(\d+),(\d+),(\d+)\}', wpart[1]):
            walls[name] = [int(r), int(g), int(b)]
    looks["walls"] = walls
    items = [table(l.strip()[1:-2]) for l in text.splitlines() if l.startswith("\t{")]
    for it in items:
        counts[it["k"]] = counts.get(it["k"], 0) + 1
    chunks.append({"looks": looks, "items": items})
manifest = json.load(open(f"data/build/{cell}/manifest.json"))
json.dump({"cell_id": cell, "chunks": chunks, "counts": counts, "building_ids": manifest.get("building_ids", [])},
          open(f"data/build/{cell}/chunks.json", "w"), ensure_ascii=False)
print(cell, len(chunks), "chunks", sum(counts.values()), "items", counts)
