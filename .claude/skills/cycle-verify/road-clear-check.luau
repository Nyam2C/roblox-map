-- Things standing on a carriageway, read off the real parts (U8 G1 Studio, 2026-10-17). Change CELLS, run with execute_luau (Edit),
-- save the returned JSON and give it to `uv run src/gate.py studio --cell <cell> --file <json>`.
-- gate.py g1 checks the chunks; this checks what Studio really holds, Workspace/Manual included (facilities, parks, plazas), which
-- the chunks never see. For every road piece of CELLS (Auto/<cell>/Base/Roads), every other part of Workspace.Auto and
-- Workspace.Manual whose footprint lies on the piece (less EDGE at its sides) and that reaches into the clear space above it
-- (LOW to HIGH studs over the road's own top) is a hit. Markings, kickers, bridge girders and walls, piers, wires, pole arms and
-- crowns belong over a road. A tree counts by its centre (the trunk), not by its crown. Hits are grouped by what owns the part:
-- auto:<building or road id>, manual:<first two folders under Manual>. Not run in the cloud session that wrote it: check the first
-- answer by eye (cycle-verify G1).
local CELLS = { "<cell id>" }
local EDGE, LOW, HIGH = 1.08, 1.0, 9.0 -- studs: gate.toml g1.edge_m, clear_low_m, clear_high_m at 3.6 studs/m
local M2 = 12.96 -- stud² in a m²
local SKIP = { "^cl%d", "^dash%d", "^cw%d", "^sl%d", "^bw%d", "^pier%d", "^wire%d", "^larm%d", "^lhead%d", "^arm%d", "^zs%d",
	"^ramp", "^deck", "^crown" }

local HttpService = game:GetService("HttpService")

local function tailOf(name)
	return string.match(name, "#([^#]*)$") or name
end

local function skipped(part)
	if part.Transparency >= 1 or part:IsA("SpawnLocation") then
		return true
	end
	local t = tailOf(part.Name)
	for _, p in SKIP do
		if string.match(t, p) then
			return true
		end
	end
	return false
end

local function isTree(part) -- Auto trees are <..>#tree; hand-made ones are named by people (Tree, PineTree, tree3 ...), not "Street"
	local name = part.Name
	return string.match(tailOf(name), "^tree") ~= nil or string.find(name, "Tree") ~= nil or string.find(name, "%f[%a]tree") ~= nil
		or string.find(string.lower(name), "pine", 1, true) ~= nil
end

local AUTO = workspace:FindFirstChild("Auto")
local function inBase(part) -- a cell's own ground, roads, paths and sidewalks (Auto/<cell>/Base), never a candidate
	local base = part:FindFirstAncestor("Base")
	return base ~= nil and base.Parent ~= nil and base.Parent.Parent == AUTO
end

-- what owns a part: auto:<model or root id> or manual:<A>/<B>
local function ownerOf(part)
	local chain = {}
	local node = part
	while node and node ~= workspace do
		table.insert(chain, 1, node)
		node = node.Parent
	end
	if chain[1] and chain[1].Name == "Manual" then
		local a = chain[2] and chain[2].Name or "?"
		local b = chain[3] and chain[3] ~= part and ("/" .. chain[3].Name) or ""
		return "manual:" .. a .. b
	end
	-- Auto/<cell>/Buildings/<model>/... or Auto/<cell>/<Folder>/<part>
	if chain[3] and chain[3].Name == "Buildings" and chain[4] then
		return "auto:" .. chain[4].Name
	end
	return "auto:" .. (string.match(part.Name, "^([^#]+)") or part.Name)
end

local function corners(cf, size)
	local out = {}
	for _, sx in { -0.5, 0.5 } do
		for _, sy in { -0.5, 0.5 } do
			for _, sz in { -0.5, 0.5 } do
				table.insert(out, cf:PointToWorldSpace(Vector3.new(sx * size.X, sy * size.Y, sz * size.Z)))
			end
		end
	end
	return out
end

-- convex hull of 2D points (monotone chain), counterclockwise
local function hull(pts)
	table.sort(pts, function(a, b)
		return a[1] < b[1] or (a[1] == b[1] and a[2] < b[2])
	end)
	local function cross(o, a, b)
		return (a[1] - o[1]) * (b[2] - o[2]) - (a[2] - o[2]) * (b[1] - o[1])
	end
	local lower, upper = {}, {}
	for _, p in pts do
		while #lower >= 2 and cross(lower[#lower - 1], lower[#lower], p) <= 0 do
			table.remove(lower)
		end
		table.insert(lower, p)
	end
	for i = #pts, 1, -1 do
		local p = pts[i]
		while #upper >= 2 and cross(upper[#upper - 1], upper[#upper], p) <= 0 do
			table.remove(upper)
		end
		table.insert(upper, p)
	end
	table.remove(lower)
	table.remove(upper)
	for _, p in upper do
		table.insert(lower, p)
	end
	return lower
end

-- area of a convex polygon inside the rectangle |u| <= hx, |w| <= hz (Sutherland-Hodgman)
local function clippedArea(poly, hx, hz)
	local function clip(pts, inside, cut)
		local out = {}
		for i = 1, #pts do
			local a, b = pts[i], pts[i % #pts + 1]
			local ia, ib = inside(a), inside(b)
			if ia then
				table.insert(out, a)
			end
			if ia ~= ib then
				table.insert(out, cut(a, b))
			end
		end
		return out
	end
	local function lerpAt(a, b, k, v)
		local t = (v - a[k]) / (b[k] - a[k])
		return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t }
	end
	local pts = poly
	for _, e in { { 1, hx, 1 }, { 1, -hx, -1 }, { 2, hz, 1 }, { 2, -hz, -1 } } do
		local k, v, s = e[1], e[2], e[3]
		pts = clip(pts, function(p)
			return s * p[k] <= s * v
		end, function(a, b)
			return lerpAt(a, b, k, v)
		end)
		if #pts < 3 then
			return 0
		end
	end
	local area = 0
	for i = 1, #pts do
		local a, b = pts[i], pts[i % #pts + 1]
		area += a[1] * b[2] - b[1] * a[2]
	end
	return math.abs(area) / 2
end

-- every candidate part with its world corners, in a 64-stud grid by footprint
local GRID = 64
local grid, parts = {}, 0
local function key(i, j)
	return i .. ":" .. j
end
local roots = { AUTO, workspace:FindFirstChild("Manual") }
local seen = 0
for _, top in roots do
	for _, p in (top and top:GetDescendants() or {}) do
		if p:IsA("BasePart") and not inBase(p) and not skipped(p) then
			local cs = corners(p.CFrame, p.Size)
			local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
			for _, c in cs do
				x0, x1, z0, z1 = math.min(x0, c.X), math.max(x1, c.X), math.min(z0, c.Z), math.max(z1, c.Z)
			end
			local rec = { part = p, corners = cs, tree = isTree(p) }
			for i = math.floor(x0 / GRID), math.floor(x1 / GRID) do
				for j = math.floor(z0 / GRID), math.floor(z1 / GRID) do
					local k = key(i, j)
					grid[k] = grid[k] or {}
					table.insert(grid[k], rec)
				end
			end
			parts += 1
		end
		seen += 1
		if seen % 4000 == 0 then
			task.wait()
		end
	end
end

local best, roads = {}, 0
for _, CELL in CELLS do
	local cell = AUTO and AUTO:FindFirstChild(CELL) -- a packed place has no Auto cells: unpack the cell first (cycle-build 5c)
	local folder = cell and cell:FindFirstChild("Base") and cell.Base:FindFirstChild("Roads")
	for _, r in (folder and folder:GetChildren() or {}) do
		if r:IsA("BasePart") then
			roads += 1
			local hx, hz, top = r.Size.X / 2, r.Size.Z / 2 - EDGE, r.Size.Y / 2
			if hz > 0 then
				local x0, x1, z0, z1 = math.huge, -math.huge, math.huge, -math.huge
				for _, c in corners(r.CFrame, r.Size) do
					x0, x1, z0, z1 = math.min(x0, c.X), math.max(x1, c.X), math.min(z0, c.Z), math.max(z1, c.Z)
				end
				local done = {}
				for i = math.floor(x0 / GRID), math.floor(x1 / GRID) do
					for j = math.floor(z0 / GRID), math.floor(z1 / GRID) do
						for _, rec in (grid[key(i, j)] or {}) do
							if not done[rec] then
								done[rec] = true
								local pts, vlo, vhi = {}, math.huge, -math.huge
								for _, c in rec.corners do
									local l = r.CFrame:PointToObjectSpace(c)
									table.insert(pts, { l.X, l.Z })
									vlo, vhi = math.min(vlo, l.Y - top), math.max(vhi, l.Y - top)
								end
								if vhi > LOW and vlo < HIGH then
									local area
									if rec.tree then -- by the centre: a crown may hang over the road
										local c = r.CFrame:PointToObjectSpace(rec.part.Position)
										area = (math.abs(c.X) <= hx and math.abs(c.Z) <= hz) and M2 or 0
									else
										area = clippedArea(hull(pts), hx, hz)
									end
									if area > 0 then
										local owner = ownerOf(rec.part)
										local m2 = area / M2
										if not best[owner] or m2 > best[owner].m2 then
											local at = rec.part.Position
											best[owner] = { owner = owner, m2 = math.floor(m2 * 100 + 0.5) / 100, part = rec.part:GetFullName(),
												road = r.Name, at = { math.floor(at.X + 0.5), math.floor(at.Z + 0.5) } }
										end
									end
								end
							end
						end
					end
				end
			end
		end
	end
	task.wait()
end

local hits = {}
for _, h in best do
	table.insert(hits, h)
end
table.sort(hits, function(a, b)
	return a.m2 > b.m2
end)
return HttpService:JSONEncode({ cells = CELLS, roads = roads, parts = parts, hits = hits })
