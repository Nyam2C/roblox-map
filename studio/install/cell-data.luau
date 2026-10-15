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
	-- the folder stays: its m1, m2, ... (the hand-made places) belong to ManualCodec.export, and a packed cell has no other copy
	-- (2026-10-15: destroying the folder here lost every packed cell's places). Only the chunk values "1", "2", ... are replaced.
	local f = data:FindFirstChild(id) or Instance.new("Folder")
	f.Name = id
	for _, v in ipairs(f:GetChildren()) do
		if v:IsA("StringValue") and v.Name:match("^%d+$") then v:Destroy() end
	end
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
		if p:IsA("Model") then
			p.ModelStreamingMode = Enum.ModelStreamingMode.Persistent -- every client keeps the far view (LiteSwap hides the near ones)
		elseif p:IsA("BasePart") then
			p.CanCollide = false; p.CanTouch = false; p.CanQuery = false
			local b = p:GetAttribute("BuildingId")
			if b and manual[b] then p:Destroy() end
		end
	end
	n += 1
	task.wait()
end
local notInIndex = 0
for _, f in ipairs(data:GetChildren()) do
	if f:IsA("Folder") and not index[f.Name] then notInIndex += 1 end -- kept: a cell missing from cellindex.json loses nothing here
end

-- the hand-made places of the cells built in Edit, by cell (ServerStorage/ManualCodec)
local r = require(SS:WaitForChild("ManualCodec")).export(data, workspace.Manual, workspace.Auto)
return string.format("cells %d, data %.1f MB base64, manual %d cells %d units (%d left to packed cells) %.1f MB, http=%s", n,
	bytes / 1e6, r.cells, r.units, r.strays, r.bytes / 1e6, tostring(HS.HttpEnabled))
