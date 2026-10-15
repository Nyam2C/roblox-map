-- The far view on this client (2026-10-15): Workspace/Lite (lite.py: building boxes, roofs, coarse ground; persistent, so every
-- client has it all) stays shown, and a building's lite parts hide while the building itself is on this client:
-- - a full cell's building, Workspace/Auto/<cell>/Buildings/<id> (an atomic model, streamed in whole);
-- - a hand-made place that owns the building (BuildingId on a part or on a model above it in Workspace/Manual): hidden while
--   any of its parts is streamed in. Near the player the building shows; past the streaming radius, its box.
local lite = workspace:WaitForChild("Lite", 60)
local auto = workspace:WaitForChild("Auto", 60)
local manual = workspace:WaitForChild("Manual", 60)
if not lite or not auto then
	return
end

local parts = {} -- building id -> its lite parts
local here = {} -- building id -> full models or hand-made parts of it on this client

local function apply(id)
	local hide = (here[id] or 0) > 0
	for _, p in ipairs(parts[id] or {}) do
		p.LocalTransparencyModifier = hide and 1 or 0
	end
end

local function count(id, by)
	here[id] = math.max(0, (here[id] or 0) + by)
	apply(id)
end

local function addLite(d)
	if d:IsA("BasePart") then
		local id = d:GetAttribute("BuildingId")
		if id then
			parts[id] = parts[id] or {}
			table.insert(parts[id], d)
			d.LocalTransparencyModifier = (here[id] or 0) > 0 and 1 or 0
		end
	end
end

local function isFull(m)
	return m:IsA("Model") and m.Parent ~= nil and m.Parent.Name == "Buildings"
end

-- the building a hand-made part stands for: its own BuildingId or the nearest one above it
local function ownerOf(d)
	local x = d
	while x and x ~= manual do
		local id = x:GetAttribute("BuildingId")
		if id then
			return id
		end
		x = x.Parent
	end
	return nil
end

local manualOwner = {} -- hand-made part -> the id it was counted for (a part can leave after its model)
auto.DescendantAdded:Connect(function(m)
	if isFull(m) then
		count(m.Name, 1)
	end
end)
auto.DescendantRemoving:Connect(function(m)
	if isFull(m) then
		count(m.Name, -1)
	end
end)
for _, m in ipairs(auto:GetDescendants()) do
	if isFull(m) then
		here[m.Name] = (here[m.Name] or 0) + 1
	end
end
if manual then
	local function addManual(d)
		if d:IsA("BasePart") and not manualOwner[d] then
			local id = ownerOf(d)
			if id then
				manualOwner[d] = id
				count(id, 1)
			end
		end
	end
	manual.DescendantAdded:Connect(addManual)
	manual.DescendantRemoving:Connect(function(d)
		local id = manualOwner[d]
		if id then
			manualOwner[d] = nil
			count(id, -1)
		end
	end)
	for _, d in ipairs(manual:GetDescendants()) do
		addManual(d)
	end
end
lite.DescendantAdded:Connect(addLite)
for _, d in ipairs(lite:GetDescendants()) do
	addLite(d)
end
