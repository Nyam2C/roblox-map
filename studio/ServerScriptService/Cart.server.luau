-- Rocket shopping cart, server side (2026-10-16, user "쇼핑 카트 뒤에 부스터 달린거 하자 드리프트 부스터 가속 다 있는거"). Script in
-- ServerScriptService, installed by data/build/install-u6.luau (src/minimap.py). Works like the scooter (Scooter.server.luau):
-- CartToggle gets on (at most once per COOLDOWN seconds) or off; on: the cart (unanchored parts welded to the HumanoidRootPart, no
-- collision, no mass) is made around the character, the character sits SEAT studs lower, and the attributes Carting and CartMaxSpeed are
-- set; CartClient then sits the rider and drives. Not while on the scooter (Riding) or sitting on a seat.
-- CartFx: the rider's client says what its cart shows ("" / "boost" / "turbo" / "d1" "d2" "d3" = drift sparks by charge); the server checks
-- it and puts it in the character's CartFx attribute, and every client lights that cart's flames and sparks from it.
-- Rules: aidlc-docs/construction/plans/cart-plan.md
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local MAX_SPEED = 80 -- studs per second (shown as km/h); boost and turbo go past it (CartClient)
local SEAT = 0.8 -- studs: the rider sits this much lower than he stands
local COOLDOWN = 0.6

local function remoteNamed(name)
	local r = ReplicatedStorage:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = ReplicatedStorage
	end
	return r
end
local toggle = remoteNamed("CartToggle")
local fxRemote = remoteNamed("CartFx")

local SILVER, RED, DARK = Color3.fromRGB(190, 195, 202), Color3.fromRGB(200, 40, 40), Color3.fromRGB(40, 40, 45)
-- name, size, x, height of the centre above the ground, z (forward is -Z), colour, material, transparency, shape ("cyl" = axis along X,
-- "cylz" = axis along Z)
local PARTS = {
	{ "Floor", Vector3.new(3.4, 0.15, 4.4), 0, 1.5, -0.6, SILVER, Enum.Material.DiamondPlate, 0, nil },
	{ "WallL", Vector3.new(0.12, 2.0, 4.4), -1.7, 2.5, -0.6, SILVER, Enum.Material.Metal, 0.45, nil },
	{ "WallR", Vector3.new(0.12, 2.0, 4.4), 1.7, 2.5, -0.6, SILVER, Enum.Material.Metal, 0.45, nil },
	{ "WallF", Vector3.new(3.4, 2.0, 0.12), 0, 2.5, -2.8, SILVER, Enum.Material.Metal, 0.45, nil },
	{ "WallB", Vector3.new(3.4, 2.0, 0.12), 0, 2.5, 1.6, SILVER, Enum.Material.Metal, 0.45, nil },
	{ "RimL", Vector3.new(0.2, 0.2, 4.6), -1.75, 3.5, -0.6, SILVER, Enum.Material.Metal, 0, nil },
	{ "RimR", Vector3.new(0.2, 0.2, 4.6), 1.75, 3.5, -0.6, SILVER, Enum.Material.Metal, 0, nil },
	{ "RimF", Vector3.new(3.7, 0.2, 0.2), 0, 3.5, -2.85, RED, Enum.Material.SmoothPlastic, 0, nil },
	{ "RimB", Vector3.new(3.7, 0.2, 0.2), 0, 3.5, 1.65, SILVER, Enum.Material.Metal, 0, nil },
	{ "PostL", Vector3.new(0.18, 1.2, 0.18), -1.55, 4.0, 2.0, SILVER, Enum.Material.Metal, 0, nil },
	{ "PostR", Vector3.new(0.18, 1.2, 0.18), 1.55, 4.0, 2.0, SILVER, Enum.Material.Metal, 0, nil },
	{ "Handle", Vector3.new(3.5, 0.32, 0.32), 0, 4.6, 2.15, RED, Enum.Material.SmoothPlastic, 0, "cyl" },
	{ "Frame", Vector3.new(2.8, 0.18, 4.6), 0, 0.95, -0.6, SILVER, Enum.Material.Metal, 0, nil },
	{ "WheelFL", Vector3.new(0.35, 0.9, 0.9), -1.35, 0.45, -2.5, DARK, Enum.Material.SmoothPlastic, 0, "cyl" },
	{ "WheelFR", Vector3.new(0.35, 0.9, 0.9), 1.35, 0.45, -2.5, DARK, Enum.Material.SmoothPlastic, 0, "cyl" },
	{ "WheelBL", Vector3.new(0.35, 0.9, 0.9), -1.35, 0.45, 1.3, DARK, Enum.Material.SmoothPlastic, 0, "cyl" },
	{ "WheelBR", Vector3.new(0.35, 0.9, 0.9), 1.35, 0.45, 1.3, DARK, Enum.Material.SmoothPlastic, 0, "cyl" },
	{ "BoosterL", Vector3.new(1.7, 0.8, 0.8), -0.9, 1.95, 2.45, DARK, Enum.Material.Metal, 0, "cylz" },
	{ "BoosterR", Vector3.new(1.7, 0.8, 0.8), 0.9, 1.95, 2.45, DARK, Enum.Material.Metal, 0, "cylz" },
	{ "NozzleL", Vector3.new(0.3, 0.95, 0.95), -0.9, 1.95, 3.35, Color3.fromRGB(230, 120, 30), Enum.Material.Metal, 0, "cylz" },
	{ "NozzleR", Vector3.new(0.3, 0.95, 0.95), 0.9, 1.95, 3.35, Color3.fromRGB(230, 120, 30), Enum.Material.Metal, 0, "cylz" },
}

-- an emitter on an attachment of the Floor (whose axes are the rider's: +Z is back); off until a client lights it
local function emitter(floor, name, at, props)
	local att = Instance.new("Attachment")
	att.Name = name
	att.Position = at
	att.Parent = floor
	local e = Instance.new("ParticleEmitter")
	e.Name = name
	e.Enabled = false
	for k, v in pairs(props) do
		e[k] = v
	end
	e.Parent = att
	return e
end
local FLAME = {
	EmissionDirection = Enum.NormalId.Back, Rate = 90, Speed = NumberRange.new(14, 20), Lifetime = NumberRange.new(0.12, 0.22),
	SpreadAngle = Vector2.new(8, 8), LightEmission = 1, Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.9), NumberSequenceKeypoint.new(1, 0.1) }),
	Color = ColorSequence.new(Color3.fromRGB(255, 230, 120), Color3.fromRGB(255, 90, 20)),
	Texture = "rbxasset://textures/particles/fire_main.dds",
}
local SPARK = {
	EmissionDirection = Enum.NormalId.Back, Rate = 70, Speed = NumberRange.new(6, 12), Lifetime = NumberRange.new(0.15, 0.3),
	SpreadAngle = Vector2.new(35, 35), LightEmission = 1, Acceleration = Vector3.new(0, -40, 0),
	Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.35), NumberSequenceKeypoint.new(1, 0) }),
	Texture = "rbxasset://textures/particles/sparkles_main.dds",
}

local state = {} -- [Player] = { model, humanoid, hip }
local lastRequest = {}

local function stop(player)
	local s = state[player]
	if not s then
		return
	end
	state[player] = nil
	if s.model then
		s.model:Destroy()
	end
	if s.humanoid and s.humanoid.Parent then
		s.humanoid.HipHeight = s.hip
	end
	local char = player.Character
	if char then
		char:SetAttribute("Carting", false)
		char:SetAttribute("CartMaxSpeed", nil)
		char:SetAttribute("CartFx", nil)
	end
end

local function start(player, char, humanoid, root)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { char }
	local hit = workspace:Raycast(root.Position, Vector3.new(0, -12, 0), params)
	local stand = hit and hit.Distance or (humanoid.HipHeight + root.Size.Y / 2) -- root centre above the ground now
	local sit = stand - SEAT -- and once seated
	local look = root.CFrame.LookVector
	local frame = CFrame.lookAt(root.Position, root.Position + Vector3.new(look.X, 0, look.Z)) -- upright, the way he faces
	local model = Instance.new("Model")
	model.Name = "Cart"
	local floor
	for _, p in ipairs(PARTS) do
		local part = Instance.new("Part")
		part.Name = p[1]
		part.Size = p[2]
		part.Color = p[6]
		part.Material = p[7]
		part.Transparency = p[8]
		part.TopSurface, part.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
		local turn = CFrame.identity
		if p[9] then
			part.Shape = Enum.PartType.Cylinder
			if p[9] == "cylz" then
				turn = CFrame.Angles(0, math.rad(90), 0)
			end
		end
		part.Massless = true
		part.CanCollide, part.CanQuery, part.CanTouch = false, false, false
		part.CastShadow = p[8] == 0
		part.CFrame = frame * CFrame.new(p[3], p[4] - sit, p[5]) * turn -- in place once the root has come down SEAT
		part.Parent = model
		local weld = Instance.new("WeldConstraint")
		weld.Part0 = root
		weld.Part1 = part
		weld.Parent = part
		if p[1] == "Floor" then
			floor = part
		end
	end
	-- floor-relative positions: the Floor's centre is at height 1.5, z -0.6
	emitter(floor, "FlameL", Vector3.new(-0.9, 0.45, 4.1), FLAME)
	emitter(floor, "FlameR", Vector3.new(0.9, 0.45, 4.1), FLAME)
	emitter(floor, "SparkL", Vector3.new(-1.35, -1.4, 2.3), SPARK)
	emitter(floor, "SparkR", Vector3.new(1.35, -1.4, 2.3), SPARK)
	local glow = Instance.new("PointLight")
	glow.Name = "BoostLight"
	glow.Color = Color3.fromRGB(255, 150, 60)
	glow.Range = 14
	glow.Brightness = 3
	glow.Enabled = false
	glow.Parent = floor
	model.Parent = char
	state[player] = { model = model, humanoid = humanoid, hip = humanoid.HipHeight }
	humanoid.HipHeight -= SEAT
	char:SetAttribute("CartMaxSpeed", MAX_SPEED)
	char:SetAttribute("Carting", true) -- the client sits and drives when it sees this
end

toggle.OnServerEvent:Connect(function(player)
	local now = os.clock()
	if state[player] then -- getting off is always allowed
		stop(player)
		lastRequest[player] = now
		return
	end
	if (lastRequest[player] or -math.huge) + COOLDOWN > now then
		return
	end
	lastRequest[player] = now
	local char = player.Character
	local humanoid = char and char:FindFirstChildOfClass("Humanoid")
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not humanoid or not root or humanoid.Health <= 0 or humanoid.SeatPart or char:GetAttribute("Riding") == true
		or char:GetAttribute("Mounting") == true then
		return
	end
	start(player, char, humanoid, root)
end)

local FX = { [""] = true, boost = true, turbo = true, d1 = true, d2 = true, d3 = true }
fxRemote.OnServerEvent:Connect(function(player, fx)
	local char = player.Character
	if type(fx) ~= "string" or not FX[fx] or not state[player] or not char then
		return
	end
	char:SetAttribute("CartFx", fx)
end)

local function watch(player)
	player.CharacterRemoving:Connect(function()
		stop(player)
	end)
	player.CharacterAdded:Connect(function(char)
		char:WaitForChild("Humanoid").Died:Connect(function()
			stop(player)
		end)
	end)
end
Players.PlayerAdded:Connect(watch)
for _, player in ipairs(Players:GetPlayers()) do
	watch(player)
end
Players.PlayerRemoving:Connect(function(player)
	stop(player)
	lastRequest[player] = nil
end)
