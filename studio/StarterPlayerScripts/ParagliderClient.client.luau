-- Paraglider (2026-10-15, user: "공중에서 f 누르면 패러글라이딩 있어서 날라다닐 수 있게"). LocalScript in StarterPlayerScripts.
-- F while falling (not on the kick scooter, at least MIN_HEIGHT over the ground): the canopy opens (the server shows it to all) and
-- the character glides: forward at GLIDE studs/s toward where you steer (WASD / stick, camera-relative; no input keeps the heading),
-- sinking SINK studs/s, turning at most TURN degrees a second. F again closes it and you fall; reaching the ground (or a roof) closes it.
-- The client owns its character, so a LinearVelocity on the root here moves it for everyone.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local GLIDE, SINK, TURN, MIN_HEIGHT = 55, 7, 120, 8
local player = Players.LocalPlayer
local remote = ReplicatedStorage:WaitForChild("Paraglide", 10)

local state -- {att, lv, heading, conn} while gliding

local function stop()
	if not state then
		return
	end
	state.conn:Disconnect()
	state.lv:Destroy()
	state.att:Destroy()
	state = nil
	if remote then
		remote:FireServer(false)
	end
end

local function heightOver(root, char)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { char }
	params.RespectCanCollide = true
	local hit = workspace:Raycast(root.Position, Vector3.new(0, -500, 0), params)
	return hit and (root.Position.Y - hit.Position.Y) or math.huge
end

local function start()
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if state or not hum or not root or hum.Health <= 0 or char:GetAttribute("Riding") == true then
		return
	end
	if heightOver(root, char) < MIN_HEIGHT then -- a ray, not FloorMaterial: that one lags a frame or more after a teleport
		return
	end
	local standing = hum.HipHeight + root.Size.Y / 2 + 0.6
	local att = Instance.new("Attachment")
	att.Name = "GlideAttachment"
	att.Parent = root
	local lv = Instance.new("LinearVelocity")
	lv.Name = "Glide"
	lv.Attachment0 = att
	lv.RelativeTo = Enum.ActuatorRelativeTo.World
	lv.VelocityConstraintMode = Enum.VelocityConstraintMode.Vector
	lv.MaxForce = 1e6
	lv.Parent = root
	local look = root.CFrame.LookVector
	local heading = Vector3.new(look.X, 0, look.Z)
	heading = heading.Magnitude > 1e-3 and heading.Unit or Vector3.zAxis * -1
	state = { att = att, lv = lv, heading = heading }
	state.conn = RunService.Heartbeat:Connect(function(dt)
		if not char.Parent or hum.Health <= 0 or heightOver(root, char) <= standing then -- down on the ground or a roof
			stop()
			return
		end
		local want = hum.MoveDirection
		want = Vector3.new(want.X, 0, want.Z)
		if want.Magnitude > 0.1 then -- turn toward the input, not faster than TURN deg/s
			want = want.Unit
			local cur = state.heading
			local angle = math.acos(math.clamp(cur:Dot(want), -1, 1))
			local maxStep = math.rad(TURN) * dt
			if angle > maxStep then
				local side = cur:Cross(want).Y >= 0 and 1 or -1
				state.heading = (CFrame.Angles(0, side * maxStep, 0) * cur).Unit
			else
				state.heading = want
			end
		end
		lv.VectorVelocity = state.heading * GLIDE + Vector3.new(0, -SINK, 0)
		root.CFrame = CFrame.lookAt(root.Position, root.Position + state.heading)
	end)
	if remote then
		remote:FireServer(true)
	end
end

UserInputService.InputBegan:Connect(function(input, processed)
	if processed or input.KeyCode ~= Enum.KeyCode.F then
		return
	end
	if state then
		stop()
	else
		start()
	end
end)

player.CharacterAdded:Connect(function()
	state = nil
end)
