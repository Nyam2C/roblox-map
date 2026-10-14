-- Paraglider (2026-10-15, user: "공중에서 f 누르면 패러글라이딩"). Script in ServerScriptService, installed by data/build/install-u6.luau.
-- The rider's client flies (ParagliderClient); this script only shows the canopy to everyone: on ReplicatedStorage/Paraglide(true)
-- it welds a curved canopy with four lines over the character, on Paraglide(false) or death it takes it away.
-- Canopy size from a public glider measured in MCP_Test and deleted (asset 13272421038: span about 22 studs): 7 cells, 21 studs
-- span, 6 studs chord, 11 studs above the root.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local remote = ReplicatedStorage:WaitForChild("Paraglide")
local CELLS, SPAN, CHORD, RISE = 7, 21, 6, 11
local COLORS = { Color3.fromRGB(235, 90, 60), Color3.fromRGB(250, 200, 70) }

local function remove(char)
	local old = char and char:FindFirstChild("Paraglider")
	if old then
		old:Destroy()
	end
end

local function canopy(char)
	local root = char:FindFirstChild("HumanoidRootPart")
	if not root or char:FindFirstChild("Paraglider") then
		return
	end
	local model = Instance.new("Model")
	model.Name = "Paraglider"
	local function part(name, size, cf, color, material)
		local p = Instance.new("Part")
		p.Name = name
		p.Size = size
		p.CFrame = root.CFrame * cf
		p.Color = color
		p.Material = material or Enum.Material.Fabric
		p.CanCollide, p.CanQuery, p.CanTouch, p.Massless = false, false, false, true
		p.CastShadow = true
		p.TopSurface, p.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
		local w = Instance.new("WeldConstraint")
		w.Part0, w.Part1 = root, p
		w.Parent = p
		p.Parent = model
		return p
	end
	-- the cells on an arc: the middle highest, the ends bent down
	local radius = SPAN / 2 / math.sin(math.rad(55))
	local tips = {}
	for i = 1, CELLS do
		local t = (i - (CELLS + 1) / 2) / ((CELLS - 1) / 2) -- -1 .. 1
		local a = math.rad(55) * t
		local x = math.sin(a) * radius
		local y = RISE - (1 - math.cos(a)) * radius
		local w = SPAN / CELLS * 1.08
		part("Cell" .. i, Vector3.new(w, 0.5, CHORD), CFrame.new(x, y, -0.5) * CFrame.Angles(0, 0, -a), COLORS[i % 2 + 1])
		if i == 1 or i == CELLS then
			table.insert(tips, Vector3.new(x, y, 0))
		end
	end
	-- four lines from the wing to the shoulders
	for _, top in ipairs({ tips[1], Vector3.new(-SPAN * 0.18, RISE - 0.3, 0), Vector3.new(SPAN * 0.18, RISE - 0.3, 0), tips[2] }) do
		local bottom = Vector3.new(math.sign(top.X) * 0.8, 1.6, 0)
		local mid, len = (top + bottom) / 2, (top - bottom).Magnitude
		part("Line", Vector3.new(0.08, len, 0.08), CFrame.lookAt(mid, mid + Vector3.zAxis, (top - bottom).Unit), Color3.fromRGB(40, 40, 44), Enum.Material.SmoothPlastic)
	end
	model.Parent = char
end

local last = {}
remote.OnServerEvent:Connect(function(player, open)
	local char = player.Character
	if not char or type(open) ~= "boolean" then
		return
	end
	local now = os.clock()
	if open and last[player] and now - last[player] < 0.3 then
		return
	end
	last[player] = now
	if open then
		canopy(char)
	else
		remove(char)
	end
end)

Players.PlayerAdded:Connect(function(player)
	player.CharacterAdded:Connect(function(char)
		local hum = char:WaitForChild("Humanoid")
		hum.Died:Connect(function()
			remove(char)
		end)
	end)
end)
Players.PlayerRemoving:Connect(function(player)
	last[player] = nil
end)
