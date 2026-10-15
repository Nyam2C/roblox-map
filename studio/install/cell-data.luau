-- Edit install of the cell data for ServerScriptService/CellStreamer (2026-10-15, cycle-build 7). Serve data/build on 127.0.0.1
-- (BASE below: cellindex.json, <cell>/chunks.json, <cell>/lite.json, all written by build_luau.py) and run this with execute_luau.
-- Writes ServerStorage/CellData/<cell> (zstd + base64 in StringValues under 200,000 characters; attributes x, z, ring1, ring2) and
-- rebuilds ServerStorage/Lite/Auto/<cell> from lite.json (no collision; buildings a Manual place owns are left out). The scripts
-- come with install-u6.luau (minimap.py); the hand-made places go in by cell too (ManualCodec). Only HttpEnabled while fetching.
local HS = game:GetService("HttpService")
local ES = game:GetService("EncodingService")
local SS = game:GetService("ServerStorage")
local BASE = "http://127.0.0.1:8766/" -- the cell cycle port (cycle-build 7.3)
local PART = 190000
local function get(path)
	HS.HttpEnabled = true
	local ok, body = pcall(function() return HS:GetAsync(BASE .. path) end)
	HS.HttpEnabled = false
	if not ok then error("fetch " .. path .. ": " .. tostring(body)) end
	return body
end
local index = HS:JSONDecode(get("cellindex.json")).cells
local data = SS:FindFirstChild("CellData") or Instance.new("Folder")
data.Name = "CellData"
data.Parent = SS
local liteRoot = SS:FindFirstChild("Lite") or Instance.new("Folder")
liteRoot.Name = "Lite"
liteRoot.Parent = SS
local manual = {}
for _, d in ipairs(workspace.Manual:GetDescendants()) do
	local id = d:GetAttribute("BuildingId")
	if id then manual[id] = true end
end
local Builder = require(SS.MapBuilder)
local n, bytes = 0, 0
for id, row in pairs(index) do
	local raw = get(id .. "/chunks.json")
	local packed = buffer.tostring(ES:Base64Encode(ES:CompressBuffer(buffer.fromstring(raw), Enum.CompressionAlgorithm.Zstd, 9)))
	local old = data:FindFirstChild(id)
	if old then old:Destroy() end
	local f = Instance.new("Folder")
	f.Name = id
	for k = 1, math.ceil(#packed / PART) do
		local v = Instance.new("StringValue")
		v.Name = tostring(k)
		v.Value = string.sub(packed, (k - 1) * PART + 1, k * PART)
		v.Parent = f
	end
	f:SetAttribute("x", row.x)
	f:SetAttribute("z", row.z)
	f:SetAttribute("ring1", table.concat(row.ring1, ","))
	f:SetAttribute("ring2", table.concat(row.ring2, ","))
	f:SetAttribute("parts", row.parts)
	f.Parent = data
	bytes += #packed
	local lite = HS:JSONDecode(get(id .. "/lite.json"))
	Builder.begin(id, liteRoot)
	for _, ch in ipairs(lite.chunks) do Builder.add(id, ch.items, ch.looks, liteRoot) end
	Builder.finish(id, liteRoot)
	for _, p in ipairs(liteRoot.Auto[id]:GetDescendants()) do
		if p:IsA("BasePart") then
			p.CanCollide = false; p.CanTouch = false; p.CanQuery = false
			local b = p:GetAttribute("BuildingId")
			if b and manual[b] then p:Destroy() end
		end
	end
	n += 1
	task.wait()
end
for _, f in ipairs(data:GetChildren()) do
	if not index[f.Name] then f:Destroy() end
end

-- the hand-made places by cell (ServerStorage/ManualCodec): each unit to the cell nearest its centre, in StringValues m1, m2, ...
-- of the cell's folder; the places in KEEP stay in Workspace/Manual (the landmark towers are the skyline)
local KEEP = { Landmark = true }
local Codec = require(SS:WaitForChild("ManualCodec"))
local cells = {}
for _, f in ipairs(data:GetChildren()) do
	table.insert(cells, { f, f:GetAttribute("x"), f:GetAttribute("z") })
end
local byCell, ids, unitCount = {}, {}, 0
for _, d in ipairs(workspace.Manual:GetDescendants()) do
	local b = d:GetAttribute("BuildingId")
	if b then ids[b] = true end
end
for _, u in ipairs(Codec.units(workspace.Manual, KEEP)) do
	local c = Codec.centre(u.inst)
	local best, bd
	for _, row in ipairs(cells) do
		local d = (row[2] - c.X) ^ 2 + (row[3] - c.Z) ^ 2
		if not bd or d < bd then best, bd = row[1], d end
	end
	local list = byCell[best] or { units = {}, parts = 0 }
	byCell[best] = list
	table.insert(list.units, { path = u.path, node = Codec.encode(u.inst) })
	list.parts += (u.inst:IsA("BasePart") and 1 or 0) + #u.inst:GetDescendants()
	unitCount += 1
end
local mbytes = 0
for _, f in ipairs(data:GetChildren()) do
	for _, v in ipairs(f:GetChildren()) do
		if v.Name:match("^m%d+$") then v:Destroy() end
	end
	local list = byCell[f]
	f:SetAttribute("manualParts", list and list.parts or 0)
	if list then
		local packed = buffer.tostring(ES:Base64Encode(ES:CompressBuffer(buffer.fromstring(HS:JSONEncode(list.units)),
			Enum.CompressionAlgorithm.Zstd, 9)))
		for k = 1, math.ceil(#packed / PART) do
			local v = Instance.new("StringValue")
			v.Name = "m" .. k
			v.Value = string.sub(packed, (k - 1) * PART + 1, k * PART)
			v.Parent = f
		end
		mbytes += #packed
	end
end
local idList = {}
for b in pairs(ids) do table.insert(idList, b) end
table.sort(idList)
data:SetAttribute("ManualIds", table.concat(idList, ","))
local keepList = {}
for k in pairs(KEEP) do table.insert(keepList, k) end
data:SetAttribute("ManualKeep", table.concat(keepList, ","))
return string.format("cells %d, data %.1f MB base64, manual %d units %.1f MB, http=%s", n, bytes / 1e6, unitCount, mbytes / 1e6, tostring(HS.HttpEnabled))
