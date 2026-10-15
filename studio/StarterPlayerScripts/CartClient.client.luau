-- Rocket shopping cart, client side (2026-10-16). LocalScript in StarterPlayer/StarterPlayerScripts, installed by data/build/install-u6.luau
-- (src/minimap.py). C or the on-screen button asks the server (ReplicatedStorage/CartToggle) to get in or out; the server makes the cart and
-- sets Carting (and CartMaxSpeed) on the character, and this script then sits the rider and drives while Carting is true, the way
-- ScooterClient drives the scooter (WalkSpeed and our own move direction, so steps, slopes and walls behave as always). No balance, no falls.
--   DRIVE: kart controls, not the camera's: W/S (stick up/down) = throttle, brake, then reverse; A/D (stick sideways) = steer. No push =
--     roll to a stop. A chase camera sits behind the cart while driving.
--   DRIFT: Space (phone: 드리프트) held while steering at speed: the back slides out, the cart turns harder (steer in = tighter, out =
--     wider) and the travel lags the heading. The longer it holds, the sparks go blue, orange, purple; letting go fires a TURBO for that long
--     and fills the booster gauge.
--   BOOST: E (phone: 부스터) held while the gauge lasts: the rockets light and the cart runs past its top speed.
--   RAMPS: the scooter's trick ramps throw the cart up too (same height rule).
--   HITS: running into something fast bounces the cart back; nobody falls (user default 2026-10-16).
-- What each cart shows (flames, sparks, light) comes from the character's CartFx attribute (set by the server from the rider's CartFx
-- remote), so everybody sees every cart. Rules: aidlc-docs/construction/plans/cart-plan.md
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local ContextActionService = game:GetService("ContextActionService")

local player = Players.LocalPlayer
local toggle = ReplicatedStorage:WaitForChild("CartToggle")
local fxRemote = ReplicatedStorage:WaitForChild("CartFx")

-- studs per second (80 studs/s is shown as 80 km/h), per second squared, degrees per second
local MAX_DEFAULT = 80
local ACCEL = 30 -- 0 to 80 in about 2.7 s
local BRAKE = 70
local REVERSE_MAX, REVERSE_ACCEL = 22, 20
local COAST_BASE, COAST_DRAG = 6, 0.1
local TURN_LOW, TURN_REF = 150, 30 -- turning rate up to TURN_REF studs/s, then it falls off as (TURN_REF / v)^0.5
local GRIP_TAU = 0.08 -- seconds: not drifting, the travel follows the heading this fast
local SPIN_RATE = 90 -- degrees per second of steering when nearly stopped
-- chase camera: behind and above the cart, catching up with it at CAM_RATE (1/s)
local CAM_BACK, CAM_UP, CAM_AHEAD, CAM_RATE = 16, 6.5, 8, 6
-- drift
local DRIFT_MIN_SPEED, DRIFT_KEEP_SPEED = 25, 15
local DRIFT_TURN = 1.3 -- times the turning rate
local DRIFT_SLIP_TAU = 0.3 -- seconds: drifting, the travel follows the heading this slowly (the slide)
local DRIFT_DRAG = 6
local DRIFT_TIERS = { 0.6, 1.4, 2.4 } -- seconds held for blue, orange, purple
local TURBO_TIME = { 0.6, 1.0, 1.5 }
local TURBO_GAUGE = 0.12 -- gauge filled per tier
local SPARK_COLOURS = { Color3.fromRGB(90, 170, 255), Color3.fromRGB(255, 150, 40), Color3.fromRGB(200, 90, 255) }
-- boost
local BOOST_TOP, TURBO_TOP = 1.5, 1.35 -- times the top speed
local BOOST_ACCEL, TURBO_ACCEL = 60, 70
local BOOST_USE, GAUGE_REFILL = 0.33, 0.04 -- gauge per second (full = 1)
local OVER_DECEL = 25 -- above the top speed with nothing pushing: slows by this
-- hits
local HIT_SPEED, HIT_DROP, HIT_BACK = 30, 25, 0.25
-- ramps (as ScooterClient)
local LAUNCH_HEIGHT = 0.25 * 3.6
local AIR_G = 0.5
local MIN_LAUNCH = 15

-- the rolling sound is the scooter's (somebody else's Creator Store upload; silent if it is ever taken down)
local ROLL_SOUND = "rbxassetid://99838569349900"

local gui = Instance.new("ScreenGui")
gui.Name = "CartGui"
gui.ResetOnSpawn = false
gui.DisplayOrder = 5
gui.Parent = player:WaitForChild("PlayerGui")
local function rounded(frame, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius)
	c.Parent = frame
end
local button = Instance.new("TextButton")
button.Name = "CartButton"
button.AnchorPoint = Vector2.new(1, 1)
button.Position = UDim2.new(1, -128, 1, -150) -- left of the scooter button
button.Size = UDim2.fromOffset(104, 46)
button.BackgroundColor3 = Color3.fromRGB(200, 40, 40)
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.Font = Enum.Font.GothamBold
button.TextSize = 15
button.Text = "카트 (C)"
button.Parent = gui
rounded(button, 10)
local hud = Instance.new("Frame")
hud.Name = "CartHud"
hud.AnchorPoint = Vector2.new(0.5, 1)
hud.Position = UDim2.new(0.5, 0, 1, -24)
hud.Size = UDim2.fromOffset(240, 58)
hud.BackgroundTransparency = 1
hud.Visible = false
hud.Parent = gui
local meter = Instance.new("TextLabel")
meter.Size = UDim2.new(1, 0, 0, 30)
meter.BackgroundTransparency = 1
meter.TextColor3 = Color3.fromRGB(255, 255, 255)
meter.TextStrokeTransparency = 0.4
meter.Font = Enum.Font.GothamBold
meter.TextSize = 24
meter.Text = ""
meter.Parent = hud
local bar = Instance.new("Frame")
bar.Position = UDim2.fromOffset(0, 36)
bar.Size = UDim2.new(1, 0, 0, 12)
bar.BackgroundColor3 = Color3.fromRGB(30, 30, 36)
bar.BackgroundTransparency = 0.2
bar.BorderSizePixel = 0
bar.Parent = hud
rounded(bar, 6)
local fill = Instance.new("Frame")
fill.Size = UDim2.fromScale(1, 1)
fill.BackgroundColor3 = Color3.fromRGB(255, 140, 40)
fill.BorderSizePixel = 0
fill.Parent = bar
rounded(fill, 6)

local lastPress = 0
local function request()
	local now = os.clock()
	if now - lastPress < 0.4 then
		return
	end
	lastPress = now
	toggle:FireServer()
end
button.Activated:Connect(request)
UserInputService.InputBegan:Connect(function(input, processed)
	if not processed and input.KeyCode == Enum.KeyCode.C then
		request()
	end
end)

local function signedAngle(a, b) -- radians, + = to the left seen from above
	return math.atan2(a.Z * b.X - a.X * b.Z, a:Dot(b))
end
local function rotate(dir, angle)
	local c, s = math.cos(angle), math.sin(angle)
	return Vector3.new(dir.X * c + dir.Z * s, 0, -dir.X * s + dir.Z * c)
end
local function turnRate(v) -- radians per second
	v = math.abs(v)
	return math.rad(v <= TURN_REF and TURN_LOW or TURN_LOW * (TURN_REF / v) ^ 0.5)
end

-- ---- what a cart shows, from its rider's CartFx: every cart this client can see ------------------------------------------------------
local function showFx(char, fx)
	local cart = char:FindFirstChild("Cart")
	local floor = cart and cart:FindFirstChild("Floor")
	if not floor then
		return
	end
	local flame = fx == "boost" or fx == "turbo"
	local tier = tonumber(string.match(fx or "", "^d(%d)$"))
	for _, name in ipairs({ "FlameL", "FlameR" }) do
		local att = floor:FindFirstChild(name)
		local e = att and att:FindFirstChildOfClass("ParticleEmitter")
		if e then
			e.Enabled = flame
			e.Rate = fx == "turbo" and 60 or 90
		end
	end
	for _, name in ipairs({ "SparkL", "SparkR" }) do
		local att = floor:FindFirstChild(name)
		local e = att and att:FindFirstChildOfClass("ParticleEmitter")
		if e then
			e.Enabled = tier ~= nil
			if tier then
				e.Color = ColorSequence.new(SPARK_COLOURS[tier])
			end
		end
	end
	local glow = floor:FindFirstChild("BoostLight")
	if glow then
		glow.Enabled = flame
	end
end

local ride -- { char, humanoid, root, ... }
local sentFx = nil
local function sendFx(fx)
	if fx ~= sentFx and ride then
		sentFx = fx
		fxRemote:FireServer(fx)
		showFx(ride.char, fx) -- ours at once; the others see it when the attribute arrives
	end
end

local function stopRide()
	local r = ride
	if not r then
		return
	end
	ride = nil
	sentFx = nil
	if r.driving then
		RunService:UnbindFromRenderStep("CartDrive")
		RunService:UnbindFromRenderStep("CartCamera")
		ContextActionService:UnbindAction("CartDrift")
		ContextActionService:UnbindAction("CartBoost")
	end
	if r.lift then
		r.lift:Destroy()
	end
	if r.sit then
		r.sit:Stop(0.2)
		r.sit:Destroy()
	end
	if r.animate and r.animate.Parent then
		r.animate.Disabled = false
	end
	if r.humanoid.Parent then
		r.humanoid.WalkSpeed = r.walk
		r.humanoid.AutoRotate = r.autoRotate
		r.humanoid.JumpPower, r.humanoid.JumpHeight = r.jumpPower, r.jumpHeight
		r.humanoid:Move(Vector3.zero, false)
	end
	local camera = workspace.CurrentCamera
	camera.CameraType = Enum.CameraType.Custom -- the game's camera (the chase camera was Scriptable)
	camera.CameraSubject = r.humanoid
	hud.Visible = false
	button.Text = "카트 (C)"
	button.BackgroundColor3 = Color3.fromRGB(200, 40, 40)
end

local function startRide(char)
	stopRide()
	local humanoid = char:FindFirstChildOfClass("Humanoid")
	local root = char:FindFirstChild("HumanoidRootPart")
	local animator = humanoid and humanoid:FindFirstChildOfClass("Animator")
	if not humanoid or not root or not animator then
		return
	end
	-- sit, do not walk: no Animate script, every running track stopped, that script's sit animation played on its own
	local animate = char:FindFirstChild("Animate")
	local sitSource = animate and animate:FindFirstChild("sit") and animate.sit:FindFirstChildOfClass("Animation")
	local sit
	if animate then
		animate.Disabled = true
		for _, track in ipairs(animator:GetPlayingAnimationTracks()) do
			track:Stop(0.1)
		end
		if sitSource then
			sit = animator:LoadAnimation(sitSource)
			sit.Priority = Enum.AnimationPriority.Action
			sit.Looped = true
			sit:Play(0.2)
		end
	end
	local look = root.CFrame.LookVector
	local dir = Vector3.new(look.X, 0, look.Z).Unit
	local r = {
		char = char, humanoid = humanoid, root = root, animate = animate, sit = sit,
		walk = humanoid.WalkSpeed, autoRotate = humanoid.AutoRotate, jumpPower = humanoid.JumpPower, jumpHeight = humanoid.JumpHeight,
		v = 0, heading = dir, travel = dir, drifting = false, side = 0, driftT = 0, tier = 0, turboT = 0, gauge = 1,
		driftHeld = false, boostHeld = false, launched = false, airT = 0, kicker = nil,
	}
	ride = r
	humanoid.AutoRotate = false
	humanoid.JumpPower, humanoid.JumpHeight = 0, 0 -- Space is the drift
	hud.Visible = true
	button.Text = "내리기 (C)"
	button.BackgroundColor3 = Color3.fromRGB(90, 90, 100)
end

local function driveRide()
	local r = ride
	if not r or r.driving then
		return
	end
	r.driving = true
	local char, humanoid, root = r.char, r.humanoid, r.root
	local att = Instance.new("Attachment")
	att.Name = "CartLiftAttachment"
	att.Parent = root
	r.lift = Instance.new("VectorForce") -- takes part of gravity away while flying off a ramp
	r.lift.Name = "CartLift"
	r.lift.Attachment0 = att
	r.lift.RelativeTo = Enum.ActuatorRelativeTo.World
	r.lift.ApplyAtCenterOfMass = true
	r.lift.Enabled = false
	r.lift.Parent = root
	r.lift.Destroying:Connect(function()
		att:Destroy()
	end)
	local rayParams = RaycastParams.new()
	rayParams.FilterType = Enum.RaycastFilterType.Exclude
	rayParams.FilterDescendantsInstances = { char }
	ContextActionService:BindAction("CartDrift", function(_, state)
		r.driftHeld = state == Enum.UserInputState.Begin or (state == Enum.UserInputState.Change and r.driftHeld)
		return Enum.ContextActionResult.Sink
	end, true, Enum.KeyCode.Space, Enum.KeyCode.ButtonL2)
	ContextActionService:SetTitle("CartDrift", "드리프트")
	ContextActionService:SetPosition("CartDrift", UDim2.new(1, -230, 1, -220))
	ContextActionService:BindAction("CartBoost", function(_, state)
		r.boostHeld = state == Enum.UserInputState.Begin or (state == Enum.UserInputState.Change and r.boostHeld)
		return Enum.ContextActionResult.Sink
	end, true, Enum.KeyCode.E, Enum.KeyCode.ButtonR2)
	ContextActionService:SetTitle("CartBoost", "부스터")
	ContextActionService:SetPosition("CartBoost", UDim2.new(1, -330, 1, -170))
	-- the chase camera, after the camera scripts (which would put it back otherwise)
	RunService:BindToRenderStep("CartCamera", Enum.RenderPriority.Camera.Value + 1, function(dt)
		local camera = workspace.CurrentCamera
		if camera.CameraType ~= Enum.CameraType.Scriptable then
			camera.CameraType = Enum.CameraType.Scriptable
		end
		local eye = root.Position - r.heading * CAM_BACK + Vector3.new(0, CAM_UP, 0)
		local goal = CFrame.lookAt(eye, root.Position + r.heading * CAM_AHEAD + Vector3.new(0, 2, 0))
		camera.CFrame = camera.CFrame:Lerp(goal, 1 - math.exp(-CAM_RATE * math.min(dt, 0.1)))
	end)
	RunService:BindToRenderStep("CartDrive", Enum.RenderPriority.Input.Value + 10, function(dt)
		dt = math.min(dt, 0.1)
		local max = char:GetAttribute("CartMaxSpeed") or MAX_DEFAULT
		-- the push in the camera's frame (the control scripts turn it to the camera; this place has no PlayerModule to ask for the raw
		-- vector): with the chase camera behind the cart, ahead = throttle, sideways = steer
		local move = humanoid.MoveDirection
		local look = workspace.CurrentCamera.CFrame.LookVector
		look = Vector3.new(look.X, 0, look.Z).Magnitude > 1e-3 and Vector3.new(look.X, 0, look.Z).Unit or r.heading
		local right = Vector3.new(-look.Z, 0, look.X)
		local steer, fwd = math.clamp(-move:Dot(right), -1, 1), move:Dot(look) -- steer + = left
		local throttle = fwd > 0.1
		if fwd < -0.1 then -- back: brake, then reverse
			if r.v > 1 then
				r.v -= BRAKE * dt
			else
				r.v = math.max(r.v - REVERSE_ACCEL * dt, -REVERSE_MAX)
			end
		end
		-- drift: starts on the key while steering at speed, holds while the key is held and the cart still runs
		if not r.drifting and r.driftHeld and r.v > DRIFT_MIN_SPEED and math.abs(steer) > 0.25 then
			r.drifting, r.side, r.driftT, r.tier = true, steer > 0 and 1 or -1, 0, 0
		end
		local slip = signedAngle(r.travel, r.heading)
		if r.drifting and (not r.driftHeld or r.v < DRIFT_KEEP_SPEED or math.abs(slip) > math.rad(75)) then
			r.drifting = false
			if r.tier > 0 then -- the turbo for the charge, and some gauge
				r.turboT = TURBO_TIME[r.tier]
				r.gauge = math.min(1, r.gauge + TURBO_GAUGE * r.tier)
			end
			r.tier = 0
		end
		local omega
		if r.drifting then
			omega = turnRate(r.v) * DRIFT_TURN * r.side * (0.55 + 0.45 * math.clamp(steer * r.side, -1, 1))
			r.driftT += dt
			r.tier = r.driftT >= DRIFT_TIERS[3] and 3 or (r.driftT >= DRIFT_TIERS[2] and 2 or (r.driftT >= DRIFT_TIERS[1] and 1 or 0))
			r.v -= DRIFT_DRAG * dt
		elseif math.abs(r.v) < 3 then
			omega = steer * math.rad(SPIN_RATE) * (r.v < 0 and -1 or 1)
		else
			omega = steer * turnRate(r.v) * (r.v < 0 and -1 or 1) -- reversing turns the other way, as a car does
		end
		r.heading = rotate(r.heading, omega * dt)
		r.travel = rotate(r.travel, signedAngle(r.travel, r.heading) * math.min(1, dt / (r.drifting and DRIFT_SLIP_TAU or GRIP_TAU)))
		-- speed: throttle, boost and turbo push; the top grows with them; above it, nothing pushing, it falls back
		local boosting = r.boostHeld and r.gauge > 0
		if boosting then
			r.gauge = math.max(0, r.gauge - BOOST_USE * dt)
		else
			r.gauge = math.min(1, r.gauge + GAUGE_REFILL * dt)
		end
		r.turboT = math.max(0, r.turboT - dt)
		local top = max * (boosting and BOOST_TOP or (r.turboT > 0 and TURBO_TOP or 1))
		if boosting then
			r.v += BOOST_ACCEL * dt
		elseif r.turboT > 0 then
			r.v += TURBO_ACCEL * dt
		elseif throttle then
			r.v += (r.v < 0 and BRAKE or ACCEL) * dt -- forward while rolling back: brake first
		elseif math.abs(fwd) <= 0.1 then
			local slow = (COAST_BASE + COAST_DRAG * math.abs(r.v)) * dt
			r.v = r.v > 0 and math.max(0, r.v - slow) or math.min(0, r.v + slow)
		end
		if r.v > top then
			r.v = math.max(top, r.v - OVER_DECEL * dt - (r.v - top > 30 and 40 * dt or 0))
		end
		-- ran into something: what the body really does caps the speed, and a hard stop bounces back
		local vel = root.AssemblyLinearVelocity
		local actual = Vector3.new(vel.X, 0, vel.Z).Magnitude
		if r.v > HIT_SPEED and r.v - actual > HIT_DROP then
			r.v = -math.min(15, r.v * HIT_BACK)
			r.drifting, r.tier, r.turboT = false, 0, 0
		elseif r.v > 0 then
			r.v = math.min(r.v, actual + 8)
		end
		-- ramps: up the curved side of a trick ramp and off its lip
		local drop = humanoid.HipHeight + root.Size.Y / 2
		local onGround = humanoid.FloorMaterial ~= Enum.Material.Air
		local hit = workspace:Raycast(root.Position, Vector3.new(0, -(drop + 4), 0), rayParams)
		if hit and hit.Instance.Name:sub(-7) == "#rampup" then
			r.kicker = hit.Instance
		elseif r.kicker and not r.launched then
			local climb = -r.kicker.CFrame.LookVector
			climb = Vector3.new(climb.X, 0, climb.Z)
			if climb.Magnitude > 0.1 and climb.Unit:Dot(r.travel) > 0.5 and r.v > MIN_LAUNCH then
				local vy = math.sqrt(2 * workspace.Gravity * AIR_G * LAUNCH_HEIGHT * math.min(r.v, max))
				humanoid:ChangeState(Enum.HumanoidStateType.Freefall)
				local v0 = root.AssemblyLinearVelocity
				root.AssemblyLinearVelocity = Vector3.new(v0.X, math.max(v0.Y, vy), v0.Z)
				r.lift.Force = Vector3.new(0, root.AssemblyMass * workspace.Gravity * (1 - AIR_G), 0)
				r.lift.Enabled = true
				r.launched, r.airT = true, 0
			end
			r.kicker = nil
		end
		if r.launched then
			r.airT += dt
			if onGround and r.airT > 0.15 then
				r.launched = false
				r.lift.Enabled = false
			end
		end
		-- drive: the body goes the way it travels, the cart faces its heading
		humanoid.WalkSpeed = math.abs(r.v)
		humanoid:Move(math.abs(r.v) > 0.2 and r.travel * (r.v >= 0 and 1 or -1) or Vector3.zero, false)
		root.CFrame = CFrame.new(root.Position) * CFrame.lookAt(Vector3.zero, r.heading)

		-- what the cart shows
		sendFx(boosting and "boost" or (r.turboT > 0 and "turbo" or (r.drifting and r.tier > 0 and ("d" .. r.tier) or "")))
		meter.Text = string.format("%d km/h", math.floor(math.abs(r.v) + 0.5))
		meter.TextColor3 = r.drifting and r.tier > 0 and SPARK_COLOURS[r.tier] or Color3.fromRGB(255, 255, 255)
		fill.Size = UDim2.fromScale(r.gauge, 1)
		player:SetAttribute("CartState", string.format("v=%.1f slip=%.0f tier=%d gauge=%.2f turbo=%.2f", r.v, math.deg(slip), r.tier, r.gauge, r.turboT)) -- for testing
	end)
end

local attributeConnection
local function refresh(char)
	if char:GetAttribute("Carting") == true then
		if not ride or ride.char ~= char then
			startRide(char)
		end
		driveRide()
	else
		stopRide()
	end
end
local function watch(char)
	if attributeConnection then
		attributeConnection:Disconnect()
	end
	attributeConnection = char:GetAttributeChangedSignal("Carting"):Connect(function()
		refresh(char)
	end)
	stopRide()
	refresh(char)
end
if player.Character then
	watch(player.Character)
end
player.CharacterAdded:Connect(watch)
player.CharacterRemoving:Connect(stopRide)

-- ---- every cart this client can see: its effects and its rolling sound --------------------------------------------------------------
local carts = {} -- [character] = { root, humanoid, sound, footsteps, footstepVolume, fxConnection }
local function addCart(char)
	if carts[char] then
		return
	end
	local root = char:FindFirstChild("HumanoidRootPart")
	local humanoid = char:FindFirstChildOfClass("Humanoid")
	if not root or not humanoid then
		return
	end
	local sound = Instance.new("Sound")
	sound.Name = "CartRolling"
	sound.SoundId = ROLL_SOUND
	sound.Looped = true
	sound.Volume = 0
	sound.RollOffMode = Enum.RollOffMode.Linear
	sound.RollOffMinDistance = 8
	sound.RollOffMaxDistance = 80
	sound.Parent = root
	local footsteps = root:FindFirstChild("Running")
	carts[char] = {
		root = root, humanoid = humanoid, sound = sound, footsteps = footsteps, footstepVolume = footsteps and footsteps.Volume or 0,
		fxConnection = char:GetAttributeChangedSignal("CartFx"):Connect(function()
			if char ~= player.Character then
				showFx(char, char:GetAttribute("CartFx"))
			end
		end),
	}
	task.defer(function() -- the cart model may arrive a moment after the attribute
		if char ~= player.Character then
			char:WaitForChild("Cart", 5)
			showFx(char, char:GetAttribute("CartFx"))
		end
	end)
end
local function removeCart(char)
	local c = carts[char]
	if not c then
		return
	end
	carts[char] = nil
	c.fxConnection:Disconnect()
	c.sound:Destroy()
	if c.footsteps and c.footsteps.Parent then
		c.footsteps.Volume = c.footstepVolume
	end
end
RunService.Heartbeat:Connect(function()
	for char, c in pairs(carts) do
		if not char.Parent or not c.root.Parent then
			removeCart(char)
		else
			if c.footsteps then
				c.footsteps.Volume = 0
			end
			local v = c.root.AssemblyLinearVelocity
			local speed = Vector3.new(v.X, 0, v.Z).Magnitude
			if speed > 0.8 and c.humanoid.FloorMaterial ~= Enum.Material.Air then
				local f = math.clamp(speed / MAX_DEFAULT, 0, 1.5)
				c.sound.PlaybackSpeed = 0.45 + 0.6 * f -- lower than the scooter: a heavier cart
				c.sound.Volume = 0.05 + 0.2 * math.min(f, 1)
				if not c.sound.IsPlaying then
					c.sound:Play()
				end
			elseif c.sound.IsPlaying then
				c.sound:Pause()
			end
		end
	end
end)
local function trackCharacter(char)
	local function update()
		if char:GetAttribute("Carting") == true then
			addCart(char)
		else
			removeCart(char)
		end
	end
	char:GetAttributeChangedSignal("Carting"):Connect(update)
	update()
end
local function trackPlayer(p)
	if p.Character then
		trackCharacter(p.Character)
	end
	p.CharacterAdded:Connect(trackCharacter)
	p.CharacterRemoving:Connect(removeCart)
end
for _, p in ipairs(Players:GetPlayers()) do
	trackPlayer(p)
end
Players.PlayerAdded:Connect(trackPlayer)
