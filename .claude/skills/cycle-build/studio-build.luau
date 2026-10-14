-- Studio (Edit) build of one or more cells from data/build/<cell>/chunks.json served on 127.0.0.1:8765 (cycle-build step 7).
-- Change CELLS, run with execute_luau (Edit). HttpEnabled is on only while fetching. Verify keys are items_<kind>.
local CELLS = { "<cell id>" }
local HS = game:GetService("HttpService")
local Builder = require(game:GetService("ServerStorage"):WaitForChild("MapBuilder"))
local out = {}
for _, CELL in ipairs(CELLS) do
	local was = HS.HttpEnabled
	HS.HttpEnabled = true
	local ok, body = pcall(function() return HS:GetAsync("http://127.0.0.1:8765/" .. CELL .. "/chunks.json") end)
	HS.HttpEnabled = was
	if not ok then return "fetch failed: " .. tostring(body) end
	local data = HS:JSONDecode(body)
	Builder.begin(CELL)
	local created, skipped, slowest = 0, 0, 0
	for _, ch in ipairs(data.chunks) do
		local t0 = os.clock()
		local r = Builder.add(CELL, ch.items, ch.looks)
		slowest = math.max(slowest, os.clock() - t0)
		created += r.created
		skipped += r.skipped_manual
		task.wait()
	end
	Builder.finish(CELL)
	local exp = {}
	for k, v in data.counts do exp["items_" .. k] = v end
	if not exp.items_spawn then exp.items_spawn = 0 end
	local v = Builder.verify(CELL, exp)
	local sunk = 0
	for _, p in workspace.Auto[CELL]:GetDescendants() do
		if p:IsA("Part") and p.Shape == Enum.PartType.Cylinder and p.Parent.Name ~= "Signs" and p.Position.Y - p.Size.X / 2 < -0.5 then sunk += 1 end
	end
	table.insert(out, string.format("%s created=%d skipped_manual=%d slowest=%.1fms verify=%s %s sunk_cylinders=%d",
		CELL, created, skipped, slowest * 1000, tostring(v.ok), HS:JSONEncode(v.problems), sunk))
end
-- the hand-made places onto the ground too (data/build/terrain.json, written by build_luau.py)
HS.HttpEnabled = true
local okT, land = pcall(function() return HS:GetAsync("http://127.0.0.1:8765/terrain.json") end)
HS.HttpEnabled = false
if okT then
	table.insert(out, "manual moved " .. Builder.settleManual(HS:JSONDecode(land)).moved)
end
return "http=" .. tostring(HS.HttpEnabled) .. "\n" .. table.concat(out, "\n")
