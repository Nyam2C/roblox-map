-- The far view on this client (2026-10-15): Workspace/Lite (lite.py: building boxes, roofs, coarse ground; persistent, so every
-- client has it all) stays shown, and a building's lite parts hide while that building of the full cell is on this client
-- (Workspace/Auto/<cell>/Buildings/<id>, streamed in). Near the player the full building shows; past the streaming radius, its box.
local lite = workspace:WaitForChild("Lite", 60)
local auto = workspace:WaitForChild("Auto", 60)
if not lite or not auto then
	return
end

local parts = {} -- building id -> its lite parts
local here = {} -- building id -> full models of it on this client

local function apply(id)
	local hide = (here[id] or 0) > 0
	for _, p in ipairs(parts[id] or {}) do
		p.LocalTransparencyModifier = hide and 1 or 0
	end
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

auto.DescendantAdded:Connect(function(m)
	if isFull(m) then
		here[m.Name] = (here[m.Name] or 0) + 1
		apply(m.Name)
	end
end)
auto.DescendantRemoving:Connect(function(m)
	if isFull(m) then
		here[m.Name] = math.max(0, (here[m.Name] or 1) - 1)
		apply(m.Name)
	end
end)
for _, m in ipairs(auto:GetDescendants()) do
	if isFull(m) then
		here[m.Name] = (here[m.Name] or 0) + 1
	end
end
lite.DescendantAdded:Connect(addLite)
for _, d in ipairs(lite:GetDescendants()) do
	addLite(d)
end
