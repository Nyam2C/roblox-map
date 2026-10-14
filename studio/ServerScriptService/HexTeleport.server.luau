-- Teleport by hexagon (2026-10-14). Script in ServerScriptService, installed by data/build/install-u6.luau (src/minimap.py).
-- The big map (MinimapClient) sends the index of a built cell in ReplicatedStorage/MinimapData.hexes; the server checks it, waits out a
-- cooldown, streams the place in and moves the character to the cell's landing point (a sidewalk near the cell centre) on the ground.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local COOLDOWN = 3 -- seconds between two jumps of one player
local remote = ReplicatedStorage:WaitForChild("HexTeleport")
local ok, Data = pcall(function()
	return require(ReplicatedStorage:WaitForChild("MinimapData", 10))
end)
local hexes = (ok and type(Data) == "table" and Data.hexes) or {}

local last = {}

local function groundAt(x, z, char)
	-- the top of whatever a player can stand on (crowns, glass and signs do not collide), else the slab top at Y = 0
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { char }
	params.RespectCanCollide = true
	local hit = workspace:Raycast(Vector3.new(x, 600, z), Vector3.new(0, -700, 0), params)
	return hit and hit.Position.Y or 0
end

remote.OnServerEvent:Connect(function(player, index)
	if type(index) ~= "number" or index % 1 ~= 0 then
		return
	end
	local hex = hexes[index]
	if type(hex) ~= "table" or #hex < 3 then
		return
	end
	local now = os.clock()
	if last[player] and now - last[player] < COOLDOWN then
		return
	end
	local char = player.Character
	local humanoid = char and char:FindFirstChildOfClass("Humanoid")
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not humanoid or not root or humanoid.Health <= 0 then
		return
	end
	last[player] = now
	local x, z = hex[2], hex[3]
	pcall(function() -- streaming: send the place to the player before the character arrives
		player:RequestStreamAroundAsync(Vector3.new(x, 0, z), 5)
	end)
	if humanoid.SeatPart then
		humanoid.Sit = false
	end
	local y = groundAt(x, z, char) + humanoid.HipHeight + root.Size.Y / 2 + 0.5
	char:PivotTo(CFrame.new(x, y, z) * root.CFrame.Rotation)
end)

-- H (2026-10-15): the roof of the tallest tower of Manual/Landmark (the towers by the department store), same cooldown
local landmarkRemote = ReplicatedStorage:WaitForChild("LandmarkTeleport")
landmarkRemote.OnServerEvent:Connect(function(player)
	local now = os.clock()
	if last[player] and now - last[player] < COOLDOWN then
		return
	end
	local manual = workspace:FindFirstChild("Manual")
	local landmark = manual and manual:FindFirstChild("Landmark")
	local char = player.Character
	local humanoid = char and char:FindFirstChildOfClass("Humanoid")
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not landmark or not humanoid or not root or humanoid.Health <= 0 then
		return
	end
	local best, bestTop
	for _, m in landmark:GetChildren() do
		if m:IsA("Model") then
			local cf, size = m:GetBoundingBox()
			local top = cf.Position.Y + size.Y / 2
			if not bestTop or top > bestTop then
				best, bestTop = cf.Position, top
			end
		end
	end
	if not best then
		return
	end
	last[player] = now
	pcall(function()
		player:RequestStreamAroundAsync(Vector3.new(best.X, bestTop, best.Z), 5)
	end)
	if humanoid.SeatPart then
		humanoid.Sit = false
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { char }
	params.RespectCanCollide = true
	local hit = workspace:Raycast(Vector3.new(best.X, bestTop + 40, best.Z), Vector3.new(0, -80, 0), params)
	local y = (hit and hit.Position.Y or bestTop) + humanoid.HipHeight + root.Size.Y / 2 + 0.5
	char:PivotTo(CFrame.new(best.X, y, best.Z) * root.CFrame.Rotation)
end)

Players.PlayerRemoving:Connect(function(player)
	last[player] = nil
end)
