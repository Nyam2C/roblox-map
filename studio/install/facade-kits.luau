-- Edit, before building a traced cell (2026-10-18, cycle-build 4T/7): the Union kits of its traced windows, doors and railings.
-- Serve data/build on 127.0.0.1:8766 (cycle-build 7.3) and set CELLS; reads <cell>/facade-kits.json (build_luau.py) and makes
-- every kit not yet in ServerStorage/Kits: the unit's parts around the origin, unioned (UsePartColor false keeps each part's
-- colour and material), named by its key. MapBuilder clones Kits/<key> for an item with kt = key; the kits are saved with the
-- place, so Play (CellStreamer) never unions. No mesh upload. Only HttpEnabled while fetching.
local CELLS = { "8930e0ac6d3ffff" }
local BASE = "http://127.0.0.1:8766/"
local HS = game:GetService("HttpService")
local SS = game:GetService("ServerStorage")
local kits = SS:FindFirstChild("Kits") or Instance.new("Folder", SS)
kits.Name = "Kits"
local old = kits:FindFirstChild("FacadeUnits") -- the 2026-10-18 experiment's folder: those keys are not the build's keys
if old then
	old:Destroy()
end
local made, have, failed, missing = 0, 0, 0, {}
for _, cell in CELLS do
	HS.HttpEnabled = true
	local ok, body = pcall(HS.GetAsync, HS, BASE .. cell .. "/facade-kits.json")
	HS.HttpEnabled = false
	if not ok then
		table.insert(missing, cell)
		continue
	end
	for key, rows in HS:JSONDecode(body).kits do
		if kits:FindFirstChild(key) then
			have += 1
			continue
		end
		local stage = Instance.new("Folder")
		stage.Name = "FacadeKitStage"
		stage.Parent = workspace
		local parts = {}
		for _, r in rows do -- x, y, z, sx, sy, sz, material, r, g, b, reflectance, transparency
			local p = Instance.new("Part")
			p.Anchored = true
			p.TopSurface = Enum.SurfaceType.Smooth
			p.BottomSurface = Enum.SurfaceType.Smooth
			p.Size = Vector3.new(r[4], r[5], r[6])
			p.CFrame = CFrame.new(r[1], r[2], r[3])
			p.Material = Enum.Material[r[7]]
			p.Color = Color3.fromRGB(r[8], r[9], r[10])
			p.Reflectance = r[11]
			p.Transparency = r[12]
			p.Parent = stage
			table.insert(parts, p)
		end
		local okU, u = pcall(parts[1].UnionAsync, parts[1], table.move(parts, 2, #parts, 1, {}))
		if okU then
			u.UsePartColor = false
			u.Anchored = true
			u.CanCollide = false
			u.CanTouch = false
			u.CanQuery = false
			u.CastShadow = false
			u.Name = key
			u.Parent = kits
			made += 1
		else
			failed += 1
			warn("facade kit " .. key .. ": " .. tostring(u))
		end
		stage:Destroy()
		if (made + failed) % 10 == 0 then
			task.wait()
		end
	end
end
return string.format("facade kits: made %d, already %d, failed %d, no file %s", made, have, failed,
	#missing > 0 and table.concat(missing, " ") or "-")
