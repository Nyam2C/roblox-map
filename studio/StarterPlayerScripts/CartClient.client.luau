-- Rocket shopping cart, client side (2026-10-16). LocalScript in StarterPlayer/StarterPlayerScripts, installed by data/build/install-u6.luau
-- (src/minimap.py). C or the on-screen button asks the server (ReplicatedStorage/CartToggle) to get in or out; the server makes the cart and
-- sets Carting (and CartMaxSpeed) on the character, and this script then sits the rider and drives while Carting is true, the way
-- ScooterClient drives the scooter (WalkSpeed and our own move direction, so steps, slopes and walls behave as always). No balance, no falls.
--   DRIVE: kart controls, not the camera's: W/S (stick up/down) = throttle, brake, then reverse; A/D (stick sideways) = steer. No push =
--     roll to a stop. A chase camera sits behind the cart while driving.
--   HANDLING: KartRider's kind (user 2026-10-16: its structure, our own numbers): a two-axle body on linear tyres, stepped every 5 ms.
--     The wheels turn less the faster it goes, so at speed corners want a drift.
--   DRIFT: Space (phone: 드리프트) pressed while steering at speed kicks the back out and the grip drops; it lasts while the key is held or
--     the cart still slides. A short press is a shallow drift, a long one a deep one; steering against it straightens up. Sliding fills the
--     gauge; a full gauge is a booster (two at most).
--   INSTANT BOOST: let go of W during a drift and press it again within half a second of the drift's end: a short boost.
--   BOOST: E (phone: 부스터) uses a booster: the push is half again for a while; letting go of W ends it.
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

-- studs per second (studs_per_m 3.6, so 130 studs/s is 130 km/h), per second squared, all per unit of mass. Tuned in a small simulation
-- (cart-plan.md): 0 to 80 in 0.9 s at the 130 top (user 2026-10-17; 1.5 s at the first 105); a 0.5 s drift at 90 turns the cart about 80 deg.
local MAX_DEFAULT = 130 -- top speed on the throttle: the push equals the drag there
local LIN_DRAG, QUAD_DRAG = 0.04, 0.006 -- drag = (LIN_DRAG + QUAD_DRAG * speed) * velocity, the speed-squared part on the ground only
local ROLL = 3 -- rolling to a stop with no key
local AXLE = 1.2 -- studs from the middle to each axle
local K2 = (2 * AXLE) ^ 2 / 12 -- turning inertia per mass
local GRIP = 300 -- sideways push per radian of tyre slip (firm; a softer 90 slides in corners and spins on long drifts)
local STEER_MAX, STEER_FADE = math.rad(12), 40 -- wheel angle at full lock, falling off as exp(-speed / STEER_FADE)
local SPIN_DAMP = 0.36 -- per second
local CORNER_DRAW = 0.15 -- gripping round a corner pulls forward by this much of the sideways push
local BRAKE, SLIDE_BRAKE = 45, 35 -- braking straight, braking while sliding
local REVERSE_MAX, REVERSE_ACCEL = 22, 20
local SPIN_RATE = 90 -- degrees per second of steering when nearly stopped
local STEP = 0.005 -- seconds
-- chase camera: behind and above the cart, catching up with it at CAM_RATE (1/s)
local CAM_BACK, CAM_UP, CAM_AHEAD, CAM_RATE = 16, 6.5, 8, 6
-- drift
local DRIFT_MIN_SPEED = 20
local KICK, KICK_TIME = 0.3, 0.15 -- the back kicked out at the start (times full lock's push), for this long
local DRIFT_GRIP = 0.25 -- times the grip while drifting
local DRIFT_STEER = 0.35 -- times full lock, with no fall-off, while the key is held
local SLIDE = 1.2 -- sliding: sideways speed over this times the forward speed (about 50 deg); the push is then ESCAPE times
local ESCAPE = 1.15
local GAUGE_PER_STUD = 0.03 -- gauge for each stud slid sideways while drifting (full = 1 = a booster)
local SPARK_COLOURS = { Color3.fromRGB(90, 170, 255), Color3.fromRGB(255, 150, 40), Color3.fromRGB(200, 90, 255) }
-- boost
local BOOST_PUSH = 1.5 -- times the push: the top goes to about 160
local BOOST_TIME, MAX_BOOSTERS = 2.4, 2
local INSTANT_WINDOW, INSTANT_TIME = 0.5, 0.5
-- hits
local HIT_SPEED, HIT_DROP, HIT_BACK = 30, 25, 0.25
local WALL_SLIDE, WALL_BACK = 0.8, 0.5 -- off a wall: keeps this much of the speed along it and comes back at this much of the speed into it
-- for show, on every cart this client sees (nothing the physics sees): the body leans out in corners, more in a drift, squats on
-- pick-up, dips on braking and bobs on landing, turning about the axles; the front wheels show three times the steering angle
-- (KartRider's display), taken from the turning rate
local LEAN, DRIFT_LEAN, PITCH = 0.0012, 0.0035, 0.0008 -- radians per stud/s^2 of sideways or forward pick-up
local LEAN_MAX, PITCH_MAX, WHEEL_MAX = math.rad(9), math.rad(5), math.rad(30)
local SHOW_RATE = 10 -- 1/s: how fast the body follows
local LANDING_DIP = 0.5 -- studs
-- boost: the camera's field of view opens with the speed and more while boosting
local FOV_SPEED, FOV_BOOST, FOV_RATE = 8, 10, 4
-- ramps (as ScooterClient)
local LAUNCH_HEIGHT = 0.25 * 3.6
local AIR_G = 0.5
local MIN_LAUNCH = 15

-- sounds: the rolling one is the scooter's (somebody else's Creator Store upload; silent if it is ever taken down); the rest are from
-- Roblox's licensed library (ProSoundEffects; user 2026-10-16: a go-kart engine)
local ROLL_SOUND = "rbxassetid://99838569349900"
local ENGINE_SOUND = "rbxassetid://9112787430" -- Go Kart Engine Constant 1 (27 s loop): the pitch rises with the speed
local SKID_SOUND = "rbxassetid://9126103903" -- Tire Chirp Engine Car In Short Punchy Skids 1: from a drift's start to its end
local BOOST_SOUND = "rbxassetid://9120009740" -- Thruster Blast 14: a booster or an instant boost lights
local CRASH_SOUND = "rbxassetid://9118064969" -- Rattling Banging Metal Cart 2: a hard stop, louder the harder

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
bar.Size = UDim2.new(1, -44, 0, 12)
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

local slots = {} -- one square per stored booster, right of the gauge
for i = 1, MAX_BOOSTERS do
	local slot = Instance.new("Frame")
	slot.AnchorPoint = Vector2.new(1, 0)
	slot.Position = UDim2.new(1, -(MAX_BOOSTERS - i) * 20, 0, 34)
	slot.Size = UDim2.fromOffset(16, 16)
	slot.BackgroundColor3 = Color3.fromRGB(30, 30, 36)
	slot.BorderSizePixel = 0
	slot.Parent = hud
	rounded(slot, 4)
	slots[i] = slot
end

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

local function rotate(dir, angle) -- + = to the left seen from above
	local c, s = math.cos(angle), math.sin(angle)
	return Vector3.new(dir.X * c + dir.Z * s, 0, -dir.X * s + dir.Z * c)
end

-- one 5 ms step of the body: r.vel (flat), r.heading, r.omega (+ = turning left)
local function step(r, dt, steer, throttle, braking, push, onGround)
	local f = r.heading
	local left = Vector3.new(f.Z, 0, -f.X)
	local v = r.vel
	local vF, vL = v:Dot(f), v:Dot(left)
	local speed = v.Magnitude
	if r.driftPressed and not r.drifting and r.holdT <= 0 and onGround and speed > DRIFT_MIN_SPEED and math.abs(steer) > 0.25 then
		r.drifting, r.kickT, r.holdT, r.instantOk = true, KICK_TIME, 2 * KICK_TIME, vF > 0
	end
	r.driftPressed = false
	if r.drifting and not (r.driftHeld or r.sliding or r.holdT > 0) or not onGround then
		if r.drifting and r.instantOk and onGround then
			r.windowT = INSTANT_WINDOW
		end
		r.drifting, r.kickT, r.instantOk = false, 0, false
	end
	r.holdT = math.max(0, r.holdT - dt)
	local acc, side = Vector3.zero, 0
	if not onGround then
		r.omega -= r.omega * math.min(1, 30 * dt)
	elseif speed < 3 and not r.drifting then -- nearly stopped: no tyres, it turns on the spot
		r.omega = math.rad(SPIN_RATE) * steer * (vF < 0 and -1 or 1)
		v = f * vF
	else
		local fade = r.drifting and r.driftHeld and DRIFT_STEER or math.exp(-math.abs(vF) / STEER_FADE)
		local delta = STEER_MAX * steer * fade * (vF < 0 and -1 or 1) -- reversing turns the other way, as a car does
		local ref = math.max(speed, 10)
		local front = (delta - (vL + r.omega * AXLE) / ref) * GRIP
		local back = -(vL - r.omega * AXLE) / ref * GRIP
		if r.kickT > 0 then
			front, back = 0, -STEER_MAX * steer * KICK * GRIP
			r.kickT -= dt
		end
		if r.drifting then
			front, back = front * DRIFT_GRIP, back * DRIFT_GRIP
		end
		side = front + back
		r.omega += ((front - back) * AXLE / K2 - SPIN_DAMP * r.omega) * dt
		acc = left * side
	end
	if onGround then
		if throttle then
			local boost = (r.boostT > 0 or r.instantT > 0) and BOOST_PUSH or 1
			acc += f * push * (r.sliding and ESCAPE or 1) * boost
			if vF < 0 then -- rolling back: brake first
				acc += f * BRAKE
			end
			if not r.drifting then
				acc += f * math.abs(side) * CORNER_DRAW
			end
		elseif braking then
			if vF > 0.5 then
				acc -= v.Unit * (v.Unit:Dot(f) > 0.8 and BRAKE or SLIDE_BRAKE)
			elseif vF > -REVERSE_MAX then
				acc -= f * REVERSE_ACCEL
			end
		end
	end
	acc -= v * (LIN_DRAG + (onGround and QUAD_DRAG * speed or 0)) -- the road drag only on the ground
	v += acc * dt
	if not throttle and not braking and onGround then
		local s = v.Magnitude
		v = s > ROLL * dt and v * (1 - ROLL * dt / s) or Vector3.zero
	end
	r.vel = Vector3.new(v.X, 0, v.Z)
	r.heading = rotate(f, r.omega * dt)
	vF, vL = r.vel:Dot(r.heading), r.vel:Dot(Vector3.new(r.heading.Z, 0, -r.heading.X))
	r.sliding = math.abs(vL) > SLIDE * math.abs(vF)
	if r.drifting and r.boosters < MAX_BOOSTERS then
		r.gauge += math.abs(vL) * GAUGE_PER_STUD * dt
		if r.gauge >= 1 then
			r.boosters += 1
			r.gauge = r.boosters < MAX_BOOSTERS and r.gauge - 1 or 0
		end
	end
	r.boostT = math.max(0, r.boostT - dt)
	r.instantT = math.max(0, r.instantT - dt)
	r.windowT = math.max(0, r.windowT - dt)
end

-- ---- what a cart shows, from its rider's CartFx: every cart this client can see ------------------------------------------------------
local carts = {} -- [character] = { root, humanoid, sound, engine, skid, boost, fx, footsteps, footstepVolume, fxConnection }
local function showFx(char, fx)
	local c = carts[char]
	if c and (fx or "") ~= c.fx then -- the sounds of a change: a boost lights, a drift starts or ends
		local was, now = c.fx, fx or ""
		c.fx = now
		if (now == "boost" or now == "turbo") and was ~= "boost" and was ~= "turbo" then
			c.boost:Play()
		end
		local drift, wasDrift = now:sub(1, 1) == "d", was:sub(1, 1) == "d"
		if drift and not wasDrift then
			c.skid.TimePosition = 0
			c.skid:Play()
		elseif wasDrift and not drift then
			c.skid:Stop()
		end
	end
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
	for _, name in ipairs({ "SmokeL", "SmokeR" }) do
		local att = floor:FindFirstChild(name)
		local e = att and att:FindFirstChildOfClass("ParticleEmitter")
		if e then
			e.Enabled = tier ~= nil
		end
	end
	for _, name in ipairs({ "WheelBL", "WheelBR" }) do
		local wheel = cart:FindFirstChild(name)
		local mark = wheel and wheel:FindFirstChild("SkidMark")
		if mark then
			mark.Enabled = tier ~= nil
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
	camera.FieldOfView = r.fov
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
		vel = Vector3.zero, heading = dir, omega = 0, drifting = false, sliding = false, kickT = 0, holdT = 0,
		gauge = 0, boosters = 1, boostT = 0, instantT = 0, windowT = 0, instantOk = false,
		driftHeld = false, driftPressed = false, boostPressed = false, throttleWas = false, launched = false, airT = 0, kicker = nil,
	}
	ride = r
	humanoid.AutoRotate = false
	humanoid.JumpPower, humanoid.JumpHeight = 0, 0 -- Space is the drift
	r.fov = workspace.CurrentCamera.FieldOfView
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
		r.driftPressed = r.driftPressed or state == Enum.UserInputState.Begin
		return Enum.ContextActionResult.Sink
	end, true, Enum.KeyCode.Space, Enum.KeyCode.ButtonL2)
	ContextActionService:SetTitle("CartDrift", "드리프트")
	ContextActionService:SetPosition("CartDrift", UDim2.new(1, -230, 1, -220))
	ContextActionService:BindAction("CartBoost", function(_, state)
		r.boostPressed = r.boostPressed or state == Enum.UserInputState.Begin
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
		local max = char:GetAttribute("CartMaxSpeed") or MAX_DEFAULT
		local fov = r.fov + FOV_SPEED * math.clamp(r.vel.Magnitude / max, 0, 1.3) + ((r.boostT > 0 or r.instantT > 0) and FOV_BOOST or 0)
		camera.FieldOfView += (fov - camera.FieldOfView) * (1 - math.exp(-FOV_RATE * math.min(dt, 0.1)))
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
		local throttle, braking = fwd > 0.1, fwd < -0.1
		-- boosters: E uses one; letting go of the throttle ends any boost; pressing it again just after a drift is the instant boost
		if r.boostPressed and r.boosters > 0 and r.boostT <= 0 then
			r.boosters -= 1
			r.boostT = BOOST_TIME
		end
		r.boostPressed = false
		if throttle and not r.throttleWas and r.windowT > 0 then
			r.instantT, r.windowT = INSTANT_TIME, 0
		end
		r.throttleWas = throttle
		if not throttle then
			r.boostT, r.instantT = 0, 0
		end
		local onGround = humanoid.FloorMaterial ~= Enum.Material.Air
		local push = LIN_DRAG * max + QUAD_DRAG * max * max
		local left = dt
		while left > 1e-6 do
			local h = math.min(STEP, left)
			step(r, h, steer, throttle, braking, push, onGround)
			left -= h
		end
		r.heading = r.heading.Unit
		local speed = r.vel.Magnitude
		local travel = speed > 0.2 and r.vel.Unit or r.heading
		-- ramps: up the curved side of a trick ramp and off its lip (looked at first: its steps and lip are not a crash)
		local drop = humanoid.HipHeight + root.Size.Y / 2
		local hit = workspace:Raycast(root.Position, Vector3.new(0, -(drop + 4), 0), rayParams)
		local onRamp = hit ~= nil and string.find(hit.Instance.Name, "#ramp", 1, true) ~= nil
		-- the whole curved side (#rampt steps and the #rampup lip): the lip alone is 1 stud deep, less than a frame's run at speed
		if hit and (string.find(hit.Instance.Name, "#rampt", 1, true) or hit.Instance.Name:sub(-7) == "#rampup") then
			r.kicker = hit.Instance
		elseif r.kicker and not r.launched then
			local climb = -r.kicker.CFrame.LookVector
			climb = Vector3.new(climb.X, 0, climb.Z)
			if climb.Magnitude > 0.1 and climb.Unit:Dot(travel) > 0.5 and speed > MIN_LAUNCH then
				local vy = math.sqrt(2 * workspace.Gravity * AIR_G * LAUNCH_HEIGHT * math.min(speed, max))
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
		-- ran into something: what the body really does caps the speed, and a hard stop bounces back
		local vel = root.AssemblyLinearVelocity
		local flat = Vector3.new(vel.X, 0, vel.Z)
		local actual = flat.Magnitude
		if onRamp or r.launched then -- the ramp throws it: not a crash
		elseif speed > HIT_SPEED and speed - actual > HIT_DROP then
			local wall = workspace:Raycast(root.Position, travel * 6, rayParams)
			local n = wall and Vector3.new(wall.Normal.X, 0, wall.Normal.Z)
			local into = n and n.Magnitude > 0.5 and r.vel:Dot(n.Unit) or 0
			if into < 0 then -- off the wall: along it a little slower, back from it at half the speed in (KartRider's wall)
				n = n.Unit
				r.vel = (r.vel - n * into) * WALL_SLIDE - n * math.max(into, -60) * WALL_BACK
				local along = math.atan2(r.heading.Z * r.vel.X - r.heading.X * r.vel.Z, r.heading:Dot(r.vel))
				if math.abs(along) < math.rad(80) then -- a glancing hit turns the nose along the wall; a straight one just bounces
					r.heading = rotate(r.heading, along * 0.6)
				end
			else
				r.vel = -r.vel.Unit * math.min(15, speed * HIT_BACK)
			end
			r.omega, r.drifting, r.kickT, r.instantOk, r.windowT, r.instantT = 0, false, 0, false, 0, 0
		elseif speed > actual + 8 and onGround then -- held back (a wall, a bump): go the way the body really goes, still pushing a little
			r.vel = flat + r.vel.Unit * 8
		end
		speed = r.vel.Magnitude
		travel = speed > 0.2 and r.vel.Unit or r.heading
		-- drive: the body goes the way it travels, the cart faces its heading
		humanoid.WalkSpeed = speed
		humanoid:Move(speed > 0.2 and travel or Vector3.zero, false)
		root.CFrame = CFrame.new(root.Position) * CFrame.lookAt(Vector3.zero, r.heading)

		-- what the cart shows
		local sparks = r.drifting and (r.sliding and 2 or 1) or nil -- blue drifting, orange sliding deep
		sendFx(r.boostT > 0 and "boost" or (r.instantT > 0 and "turbo" or (sparks and ("d" .. sparks) or "")))
		meter.Text = string.format("%d km/h", math.floor(speed + 0.5))
		for i, slot in ipairs(slots) do
			slot.BackgroundColor3 = r.boosters >= i and Color3.fromRGB(255, 140, 40) or Color3.fromRGB(30, 30, 36)
		end
		meter.TextColor3 = sparks and SPARK_COLOURS[sparks] or Color3.fromRGB(255, 255, 255)
		fill.Size = UDim2.fromScale(r.gauge, 1)
		local slip = speed > 1 and math.deg(math.atan2(r.vel:Dot(Vector3.new(r.heading.Z, 0, -r.heading.X)), r.vel:Dot(r.heading))) or 0
		player:SetAttribute("CartState", string.format("v=%.1f slip=%.0f drift=%s gauge=%.2f boosters=%d boost=%.2f instant=%.2f",
			speed, slip, tostring(r.drifting), r.gauge, r.boosters, r.boostT, r.instantT)) -- for testing
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

-- ---- every cart this client can see: its effects and its sounds ---------------------------------------------------------------------
local function cartSound(root, name, id, looped, volume)
	local sound = Instance.new("Sound")
	sound.Name, sound.SoundId, sound.Looped, sound.Volume = name, id, looped, volume
	sound.RollOffMode = Enum.RollOffMode.Linear
	sound.RollOffMinDistance = 8
	sound.RollOffMaxDistance = 80
	sound.Parent = root
	return sound
end
local function addCart(char)
	if carts[char] then
		return
	end
	local root = char:FindFirstChild("HumanoidRootPart")
	local humanoid = char:FindFirstChildOfClass("Humanoid")
	if not root or not humanoid then
		return
	end
	local footsteps = root:FindFirstChild("Running")
	carts[char] = {
		root = root, humanoid = humanoid, sound = cartSound(root, "CartRolling", ROLL_SOUND, true, 0),
		engine = cartSound(root, "CartEngine", ENGINE_SOUND, true, 0), skid = cartSound(root, "CartSkid", SKID_SOUND, false, 0.5),
		boost = cartSound(root, "CartBoost", BOOST_SOUND, false, 0.6), crash = cartSound(root, "CartCrash", CRASH_SOUND, false, 0.5), fx = "",
		look = root.CFrame.LookVector, speed = 0, accel = 0, roll = 0, pitch = 0, wheel = 0, bob = 0, bobV = 0, air = false,
		footsteps = footsteps, footstepVolume = footsteps and footsteps.Volume or 0,
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
	for _, sound in ipairs({ c.sound, c.engine, c.skid, c.boost, c.crash }) do
		sound:Destroy()
	end
	if c.footsteps and c.footsteps.Parent then
		c.footsteps.Volume = c.footstepVolume
	end
end
-- the body's lean, dip and bob and the front wheels' turn, from how the cart moves (the same for every cart, ours included)
local function showMotion(char, c, speed, dt)
	local cart = char:FindFirstChild("Cart")
	local floor = cart and cart:FindFirstChild("Floor")
	local body = floor and floor:FindFirstChild("CartBody")
	if not body then
		return
	end
	if not c.body then -- the welds as the server made them
		c.body, c.bodyC0 = body, body.C0
		c.wheels = {}
		for _, side in ipairs({ "L", "R" }) do
			local wheel = cart:FindFirstChild("WheelF" .. side)
			local steer = wheel and wheel:FindFirstChild("SteerF" .. side)
			if steer then
				c.wheels[#c.wheels + 1] = { steer, steer.C0 }
			end
		end
	end
	local look = c.root.CFrame.LookVector
	local omega = math.atan2(c.look.Z * look.X - c.look.X * look.Z, c.look:Dot(look)) / dt -- + = turning left
	c.look = look
	c.accel += ((speed - c.speed) / dt - c.accel) * math.min(1, 8 * dt)
	c.speed = speed
	local air = c.humanoid.FloorMaterial == Enum.Material.Air
	if c.air and not air then
		c.bobV = -LANDING_DIP * 12
	end
	c.air = air
	local drifting = c.fx:sub(1, 1) == "d"
	local roll = math.clamp(-(drifting and DRIFT_LEAN or LEAN) * speed * omega, -LEAN_MAX, LEAN_MAX)
	local pitch = math.clamp(PITCH * c.accel, -PITCH_MAX, PITCH_MAX)
	local k = math.min(1, SHOW_RATE * dt)
	c.roll += (roll - c.roll) * k
	c.pitch += (pitch - c.pitch) * k
	c.bobV += (-80 * c.bob - 10 * c.bobV) * dt -- a damped spring
	c.bob += c.bobV * dt
	local pivot = c.bodyC0.Position - Vector3.new(0, 1.05, 0) -- the axles: 1.05 below the Floor's centre
	body.C0 = CFrame.new(0, c.bob, 0) * CFrame.new(pivot) * CFrame.Angles(c.pitch, 0, c.roll) * CFrame.new(-pivot) * c.bodyC0
	c.wheel += (math.clamp(3 * omega * 2 * AXLE / math.max(speed, 5), -WHEEL_MAX, WHEEL_MAX) - c.wheel) * k
	for _, w in ipairs(c.wheels) do
		w[1].C0 = w[2] * CFrame.Angles(0, c.wheel, 0)
	end
end
RunService.Heartbeat:Connect(function(dt)
	dt = math.max(dt, 1e-3)
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
			if c.speed - speed > HIT_DROP and c.speed > HIT_SPEED then -- a hard stop: the crash, louder the harder
				c.crash.Volume = math.clamp((c.speed - speed) / 60, 0.2, 1)
				c.crash:Play()
			end
			showMotion(char, c, speed, dt)
			local e = math.clamp(speed / MAX_DEFAULT, 0, 1.4) -- the engine runs all the time it is ridden, higher with the speed
			c.engine.PlaybackSpeed = 0.7 + 0.6 * e
			c.engine.Volume = 0.15 + 0.2 * math.min(e, 1)
			if not c.engine.IsPlaying then
				c.engine:Play()
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
