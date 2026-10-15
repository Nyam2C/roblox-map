-- Edit, before saving or publishing (2026-10-15): the place keeps only the cell data. The hand-made places of the cells built in
-- Edit are written to ServerStorage/CellData first (ManualCodec.export), then Workspace/Auto and Workspace/Manual (but the kept
-- places, Manual/Landmark) are removed. The configured spawn stays, moved out of its cell. Back for editing: unpack.luau.
-- No HTTP. Stops before removing anything if a built cell has no data (run cell-data.luau first).
local SS = game:GetService("ServerStorage")
local data = SS:FindFirstChild("CellData")
if not data then
	error("pack: no ServerStorage/CellData: run cell-data.luau first")
end
local Codec = require(SS:WaitForChild("ManualCodec"))
local missing = {}
for _, c in ipairs(workspace.Auto:GetChildren()) do
	local f = data:FindFirstChild(c.Name)
	if not f or not f:FindFirstChild("1") then
		table.insert(missing, c.Name)
	end
end
if #missing > 0 then
	error("pack: no cell data for " .. table.concat(missing, ", ") .. ": run cell-data.luau first")
end
local r = Codec.export(data, workspace.Manual, workspace.Auto)
local spawn = workspace:FindFirstChild("Spawn")
local nAuto, nManual = 0, 0
for _, c in ipairs(workspace.Auto:GetChildren()) do
	for _, d in ipairs(c:GetDescendants()) do
		if d:IsA("SpawnLocation") and not spawn then
			d.Parent = workspace
			spawn = d
		end
	end
	nAuto += #c:GetDescendants()
	c:Destroy()
	task.wait()
end
for _, u in ipairs(Codec.units(workspace.Manual, Codec.KEEP)) do
	nManual += 1 + #u.inst:GetDescendants()
	u.inst:Destroy()
end
data:SetAttribute("PackedAt", os.date("!%Y-%m-%dT%H:%M:%SZ"))
return string.format("packed: Auto %d and Manual %d instances removed; manual data of %d cells rewritten (%d units, %d strays); spawn %s",
	nAuto, nManual, r.cells, r.units, r.strays, spawn and spawn:GetFullName() or "none")
