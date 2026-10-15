-- Edit (2026-10-15): bring cells back from ServerStorage/CellData for editing (the place is saved packed, pack.luau): the full
-- cell into Workspace/Auto/<cell> and its hand-made places into Workspace/Manual. Set CELLS to the cells to edit (and their
-- neighbours to look at), or { "all" }. Pack again before saving.
local CELLS = { "all" }
local SS = game:GetService("ServerStorage")
local data = SS.CellData
local Codec = require(SS:WaitForChild("ManualCodec"))
local Builder = require(SS:WaitForChild("MapBuilder"))
local kits = SS:FindFirstChild("Kits")
local list = {}
if CELLS[1] == "all" then
	for _, f in ipairs(data:GetChildren()) do
		if f:IsA("Folder") then
			table.insert(list, f.Name)
		end
	end
else
	list = CELLS
end
local skip = {}
for _, b in ipairs(string.split(data:GetAttribute("ManualIds") or "", ",")) do
	skip[b] = true
end
local function folderAt(path)
	local f = workspace:FindFirstChild("Manual") or Instance.new("Folder", workspace)
	f.Name = "Manual"
	for _, name in ipairs(path) do
		local nxt = f:FindFirstChild(name)
		if not nxt then
			nxt = Instance.new("Folder")
			nxt.Name = name
			nxt.Parent = f
		end
		f = nxt
	end
	return f
end
local out, units = {}, 0
for _, id in ipairs(list) do
	local f = data:FindFirstChild(id)
	if not f then
		table.insert(out, id .. ": no data")
	elseif workspace.Auto:FindFirstChild(id) then
		table.insert(out, id .. ": already out")
	else
		for _, u in ipairs(Codec.read(f, "m") or {}) do
			Codec.decode(u.node, kits).Parent = folderAt(u.path)
			units += 1
		end
		local cell = Codec.read(f, "")
		Builder.manualSkip = skip
		Builder.begin(id)
		for _, ch in ipairs(cell.chunks) do
			Builder.add(id, ch.items, ch.looks)
		end
		Builder.finish(id)
		Builder.manualSkip = nil
		if workspace:FindFirstChild("Spawn") then -- the spawn kept by pack stays the only one
			for _, d in ipairs(workspace.Auto[id]:GetDescendants()) do
				if d:IsA("SpawnLocation") then
					d:Destroy()
				end
			end
		end
		table.insert(out, id:sub(8, 11))
	end
	task.wait()
end
return string.format("unpacked %d cells, %d hand-made units: %s", #list, units, table.concat(out, " "))
