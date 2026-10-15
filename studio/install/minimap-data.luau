-- Edit install of the minimap data (cycle-build 7.5, 2026-10-15). Serve data/build on 127.0.0.1 (minimap.luau, minimap/index.json,
-- minimap/<k>.luau, written by src/minimap.py) and run this with execute_luau. ReplicatedStorage/MinimapData gets minimap.luau and
-- its child ModuleScripts "1", "2", ... the parts (each under Studio's 200,000-character Source limit); a new MinimapData instance
-- replaces the old one so no require cache keeps the old data. Only HttpEnabled while fetching.
local HS = game:GetService("HttpService")
local BASE = "http://127.0.0.1:8766/" -- the cell cycle port (cycle-build 7.3)
local function get(path)
	HS.HttpEnabled = true
	local ok, body = pcall(function() return HS:GetAsync(BASE .. path) end)
	HS.HttpEnabled = false
	if not ok then error("fetch " .. path .. ": " .. tostring(body)) end
	return body
end
local n = HS:JSONDecode(get("minimap/index.json")).parts
local data = Instance.new("ModuleScript")
data.Name = "MinimapData"
data.Source = get("minimap.luau")
local chars = 0
for k = 1, n do
	local part = Instance.new("ModuleScript")
	part.Name = tostring(k)
	part.Source = get("minimap/" .. k .. ".luau")
	part.Parent = data
	chars = math.max(chars, #part.Source)
end
local RS = game:GetService("ReplicatedStorage")
local old = RS:FindFirstChild("MinimapData")
if old then old:Destroy() end
data.Parent = RS
local t = require(data)
return string.format("MinimapData: %d parts (largest %d characters), %d rects, %d labels, %d hexes, http=%s", n, chars, #t.rects, #t.labels,
	#t.hexes, tostring(HS.HttpEnabled))
