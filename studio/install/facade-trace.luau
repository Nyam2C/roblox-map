-- Edit (2026-10-18, facade tracing experiment): build one traced building from src/facade.py trace (<building>.trace.json served
-- on 127.0.0.1:8767 from data/facade). The building's rule facade parts are hidden (TraceHidden keeps their transparency; the
-- roof cap, plinth and yard stay, a yard part in front of the traced face is hidden too) and the traced parts go to
-- Workspace/FacadeTrace. A window, door or railing unit is one UnionOperation; the first union of a shape is kept in
-- ServerStorage/Kits/FacadeUnits/<key> and later units of that shape are clones of it (no mesh upload).
-- Undo: set UNDO = true.
local URL = "http://127.0.0.1:8767/8930e0ac6d3ffff/gis_11217026.trace.json"
local UNION = true
local UNDO = false
local HS = game:GetService("HttpService")
local SS = game:GetService("ServerStorage")

if UNDO then
	local n = 0
	for _, d in workspace:GetDescendants() do
		if d:IsA("BasePart") and d:GetAttribute("TraceHidden") ~= nil then
			d.Transparency = d:GetAttribute("TraceHidden")
			d:SetAttribute("TraceHidden", nil)
			n += 1
		end
	end
	local f = workspace:FindFirstChild("FacadeTrace")
	if f then
		f:Destroy()
	end
	return "restored " .. n
end

HS.HttpEnabled = true
local ok, body = pcall(HS.GetAsync, HS, URL)
HS.HttpEnabled = false
if not ok then
	return "fetch failed: " .. tostring(body)
end
local d = HS:JSONDecode(body)

local keep = {}
for _, k in d.keep do
	keep[k] = true
end
local O, N = Vector3.new(table.unpack(d.front_o)), Vector3.new(table.unpack(d.front_n))
local hidden = 0
for _, p in workspace:GetDescendants() do
	if p:IsA("BasePart") and string.sub(p.Name, 1, #d.id + 1) == d.id .. "#" and p:GetAttribute("TraceHidden") == nil then
		local tail = string.match(p.Name, "#(%a+)") or ""
		local yard = string.sub(tail, 1, 1) == "y"
		local front = (p.Position - O):Dot(N) > -0.5
		if not (keep[tail] or yard) or (yard and front) then
			p:SetAttribute("TraceHidden", p.Transparency)
			p.Transparency = 1
			hidden += 1
		end
	end
end

local old = workspace:FindFirstChild("FacadeTrace")
if old then
	old:Destroy()
end
local kits = SS:FindFirstChild("Kits") or Instance.new("Folder", SS)
kits.Name = "Kits"
local units = kits:FindFirstChild("FacadeUnits") or Instance.new("Folder", kits)
units.Name = "FacadeUnits"
local f = Instance.new("Folder")
f.Name = "FacadeTrace"
f.Parent = workspace

local T = {}
for i, t in d.t do
	T[i] = Vector3.new(table.unpack(t))
end
local groups, order = {}, {}
for i, r in d.rows do
	local p = Instance.new("Part")
	p.Anchored = true
	p.CanCollide = false
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Name = d.id .. "#tp" .. i
	p.Size = Vector3.new(r[4], r[5], r[6])
	p.CFrame = CFrame.fromMatrix(Vector3.new(r[1], r[2], r[3]), T[r[13]], Vector3.yAxis)
	p.Material = Enum.Material[r[7]]
	p.Transparency = r[8]
	p.Color = Color3.fromRGB(r[9], r[10], r[11])
	p.Reflectance = r[12]
	p.Parent = f
	if UNION and r[14] > 0 then
		local g = groups[r[14]]
		if not g then
			g = { key = r[15], parts = {} }
			groups[r[14]] = g
			table.insert(order, r[14])
		end
		table.insert(g.parts, p)
	end
	if i % 200 == 0 then
		task.wait()
	end
end

local made, reused, failed = 0, 0, 0
for n, gi in order do
	local g = groups[gi]
	local main = g.parts[1]
	local kit = units:FindFirstChild(g.key)
	if kit then
		local u = kit:Clone()
		u.CFrame = main.CFrame * kit:GetAttribute("Offset")
		u.Name = d.id .. "#tu" .. gi
		u.Parent = f
		for _, p in g.parts do
			p:Destroy()
		end
		reused += 1
	elseif #g.parts > 1 then
		local rest = table.move(g.parts, 2, #g.parts, 1, {})
		local okU, u = pcall(main.UnionAsync, main, rest)
		if okU then
			u.UsePartColor = false
			u.Anchored = true
			u.CanCollide = false
			u.Name = d.id .. "#tu" .. gi
			u:SetAttribute("Offset", main.CFrame:ToObjectSpace(u.CFrame))
			u.Parent = f
			local copy = u:Clone()
			copy.Name = g.key
			copy.Parent = units
			for _, p in g.parts do
				p:Destroy()
			end
			made += 1
		else
			failed += 1
			if failed == 1 then
				warn("union failed: " .. tostring(u))
			end
		end
	end
	if n % 10 == 0 then
		task.wait()
	end
end
return string.format("hidden %d, instances %d (unions made %d, cloned %d, failed %d)", hidden, #f:GetChildren(), made, reused, failed)
