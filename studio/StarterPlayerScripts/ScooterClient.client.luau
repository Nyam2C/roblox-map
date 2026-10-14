-- U6 kick scooter, client side. LocalScript in StarterPlayer/StarterPlayerScripts, installed by data/build/install-u6.luau (src/minimap.py).
-- K or the on-screen button asks the server (ReplicatedStorage/ScooterToggle) to get on or off. The server decides, shows the pose and the scooter,
-- and sets the character's Riding attribute (and ScooterMaxSpeed); this script then drives the local character while Riding is true:
--   SPEED: worked out here every frame: push forward = accelerate, no input = coast, push against the way you roll = brake to a stop, push
--   sideways = steer (slower turning the faster you go). Fed to the Humanoid as WalkSpeed and as our own move direction, so steps, slopes and
--   walls behave as always. The Animate script is disabled and the idle "standing" animation plays, so the rider stands instead of walking.
--   BALANCE: a lean angle w (radians, + = to the right). Nearly stopped it tips by itself, at ordinary speeds it rights itself, above about 50
--   studs/s it wobbles and then grows by itself (speed wobble), and bumps push it about. Steering toward the lean (push the way it leans) puts
--   it right, steering away makes it worse. The rider leans into turns and with the wobble (shown, and a gauge). |w| past W_FALL, a turn too
--   hard for the speed (sideways acceleration over SKID_LIMIT g), or running into something fast makes the rider FALL: the body goes limp
--   (Humanoid Ragdoll), the server is told (ScooterToggle with true) and takes the scooter away; he gets up after FALL_RECOVER seconds.
--   SOUND: the footsteps are muted and a rolling-wheels sound plays instead, louder and higher with speed. Every client does this for every
--   rider it can see, from the rider's replicated velocity, so everybody hears the same scooter.
--   ARMS: bent to the grip the server worked out (see armsOf); only the rider's own screen shows it, Transform is not replicated.
--   TRICKS (2026-10-14; the manual was taken out again by the user the same day): RAMP: running up the curved side of a trick ramp and off its lip (<road>#rampup, one per
--   cell, made by streets.ramp_items) and off its lip throws the rider up to a height in proportion to the speed (LAUNCH_HEIGHT) and lightens gravity to AIR_G
--   until he lands. TAILWHIP: in that air, Q (phone: the 테일윕 button) spins the deck and the back wheel once round the stem in WHIP_TIME;
--   landing before it is round is a fall. A success shows no message (user 2026-10-14); a fall still says why. The spin is drawn on clones (the welded parts cannot turn), on every client: ours at once, the
--   others when the server passes on ScooterTrick.
-- Rules: aidlc-docs/construction/plans/u6-minimap-scooter-plan.md. The numbers were chosen with a simulation (a player with 0.3 s reaction who pushes
-- the way it leans keeps balance at 60 to 80; with no steering input the rider falls at 70 after about 7 s and at 80 after about 4.6 s; 60 and below are safe).
-- Since 2026-10-14 those speeds scale with the top speed: at 120 read 90 to 120, 105 and 120, and 90 and below safe.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local ContextActionService = game:GetService("ContextActionService")

local player = Players.LocalPlayer
local remote = ReplicatedStorage:WaitForChild("ScooterToggle")
local trickRemote = ReplicatedStorage:WaitForChild("ScooterTrick", 10)

-- speed: studs per second (80 studs/s is 80 km/h at 3.6 studs per metre), studs per second squared, degrees per second
local MAX_SPEED_DEFAULT = 120 -- the server sends ScooterMaxSpeed; this is only the fallback (user raised 80 -> 120, 2026-10-14)
local ACCEL = 22 -- pushing forward: 0 to 80 in about 3.6 s
local BRAKE = 60 -- pushing against the way you roll: 80 to 0 in about 1.3 s
local COAST_BASE, COAST_DRAG = 5, 0.08 -- no input: slows by 5 + 0.08 v per second (25 -> 0 in about 4 s, 80 -> 0 in about 10 s)
local TURN_SLOW = 480 -- turning rate when nearly stopped
local TURN_FAST = 130 -- turning rate at 25 studs/s; above that it falls off slowly with speed
local BACK_ANGLE = 110 -- an input this far from the way you roll is a brake, not a turn
-- balance
local W_FALL = 0.55 -- lean (about 31 degrees) at which the rider falls
local G_LOW = 10 -- 1/s^2: tips over by itself when nearly stopped
local D_DAMP = 3 -- 1/s: damping
-- The speed-dependent parts of the balance are set as fractions of the top speed (the server's ScooterMaxSpeed), so the scooter feels the
-- same at any top speed: at 120 it behaves as it did at 80 before the user raised it (2026-10-14).
local K_ASSIST = 20 -- 1/s^2: rights itself at ordinary speeds (fades out between 0.5 and 0.875 of the top speed)
local P_WOBBLE = 2.0 -- 1/s^2: the wobble grows by itself (from 0.625 of the top speed up to it)
local NOISE_AMP = 2.5 -- rad/s^2: bumps and gusts (from 0.375 of the top speed up to it)
local R_CORRECT = 5 -- rad/s^2: what a full push toward or away from the lean does
local SIDE_TAU = 0.12 -- seconds: a key push builds up over this time
local SKID_LIMIT, SKID_TIME = 0.7, 0.45 -- sideways acceleration in g that the tyres hold, and for how long it may be passed; the turning rate cap keeps even the hardest turn near TURN_G, so a sustained hard turn mostly ends in the balance fall (steering away from the lean) and the skid is the last resort
local TURN_G = 0.62 -- the hardest turn at speed, in g (the old curve gave this at 80; above 80 the rate is capped to keep it)
local CRASH_FRAC, CRASH_DROP_FRAC = 0.5, 0.35 -- running into something above this fraction of the top speed and losing this fraction of it at once
local FALL_RECOVER = 2.5 -- seconds limp on the ground
-- tricks
-- the height of the flight above the lip grows with the speed (user 2026-10-14: "높히 떠지는 효과 ... 속도에 비례해서"):
-- metres per km/h, so 30 km/h flies about 7.5 m, 60 about 15 m, 120 about 30 m (the speed is in studs/s, shown as km/h).
-- 0.13 at first, then "효과 더 높혀서" (user, same day)
local LAUNCH_HEIGHT = 0.25 * 3.6 -- studs of height per stud/s of speed
local AIR_G = 0.5 -- share of gravity while flying off a ramp: hang time for a trick (40 km/h gives about 0.5 s, 80 about 1 s)
local MIN_LAUNCH = 15 -- studs/s: slower than this the rider just rolls over the ramp
local WHIP_TIME = 0.38 -- seconds for the deck to go round once

-- "Rolling loop" (small wheels rolling, 5.2 s, Creator Store, by Animatedupload). Somebody else's upload: if it is ever taken down the scooter
-- is just silent. Put your own asset id here to change the sound.
local ROLL_SOUND = "rbxassetid://99838569349900"
local ROLL_VOLUME_MIN, ROLL_VOLUME_MAX = 0.03, 0.2

local gui = Instance.new("ScreenGui")
gui.Name = "ScooterGui"
gui.ResetOnSpawn = false
gui.DisplayOrder = 5
gui.Parent = player:WaitForChild("PlayerGui")

local function rounded(frame, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius)
	c.Parent = frame
end

local button = Instance.new("TextButton")
button.Name = "ScooterButton"
button.AnchorPoint = Vector2.new(1, 1)
button.Position = UDim2.new(1, -16, 1, -150) -- above the jump button on a phone
button.Size = UDim2.fromOffset(104, 46)
button.BackgroundColor3 = Color3.fromRGB(45, 110, 200)
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.Font = Enum.Font.GothamBold
button.TextSize = 15
button.Text = "킥보드 (K)"
button.Parent = gui
rounded(button, 10)

local meter = Instance.new("TextLabel")
meter.Name = "Speed"
meter.AnchorPoint = Vector2.new(1, 1)
meter.Position = UDim2.new(1, -16, 1, -202)
meter.Size = UDim2.fromOffset(104, 26)
meter.BackgroundTransparency = 1
meter.TextColor3 = Color3.fromRGB(255, 255, 255)
meter.TextStrokeTransparency = 0.4
meter.Font = Enum.Font.GothamBold
meter.TextSize = 18
meter.Text = ""
meter.Visible = false
meter.Parent = gui

-- the balance gauge: the marker moves left and right with the lean; the ends are the fall
local gauge = Instance.new("Frame")
gauge.Name = "Balance"
gauge.AnchorPoint = Vector2.new(1, 1)
gauge.Position = UDim2.new(1, -16, 1, -234)
gauge.Size = UDim2.fromOffset(104, 10)
gauge.BackgroundColor3 = Color3.fromRGB(30, 30, 36)
gauge.BackgroundTransparency = 0.2
gauge.BorderSizePixel = 0
gauge.Visible = false
gauge.Parent = gui
rounded(gauge, 5)
local tick = Instance.new("Frame")
tick.AnchorPoint = Vector2.new(0.5, 0.5)
tick.Position = UDim2.fromScale(0.5, 0.5)
tick.Size = UDim2.fromOffset(2, 10)
tick.BackgroundColor3 = Color3.fromRGB(200, 200, 205)
tick.BorderSizePixel = 0
tick.Parent = gauge
local marker = Instance.new("Frame")
marker.AnchorPoint = Vector2.new(0.5, 0.5)
marker.Position = UDim2.fromScale(0.5, 0.5)
marker.Size = UDim2.fromOffset(8, 16)
marker.BackgroundColor3 = Color3.fromRGB(80, 200, 110)
marker.BorderSizePixel = 0
marker.ZIndex = 2
marker.Parent = gauge
rounded(marker, 3)


-- H: go to the top of the tallest tower by the department store (user 2026-10-15: key only, no on-screen button; the trick help
-- panel that H opened is gone)
local landmarkRemote = ReplicatedStorage:WaitForChild("LandmarkTeleport", 10)
local lastLandmark = 0
local function toLandmark()
	local now = os.clock()
	if landmarkRemote and now - lastLandmark > 1 then
		lastLandmark = now
		landmarkRemote:FireServer()
	end
end

local toast = Instance.new("TextLabel")
toast.Name = "Toast"
toast.AnchorPoint = Vector2.new(0.5, 0.5)
toast.Position = UDim2.fromScale(0.5, 0.3)
toast.Size = UDim2.fromOffset(420, 44)
toast.BackgroundTransparency = 1
toast.TextColor3 = Color3.fromRGB(255, 255, 255)
toast.TextStrokeTransparency = 0.2
toast.Font = Enum.Font.GothamBold
toast.TextSize = 30
toast.Text = ""
toast.Visible = false
toast.Parent = gui
local toastToken = 0
local function showToast(text)
	toastToken += 1
	local mine = toastToken
	toast.Text = text
	toast.Visible = true
	task.delay(1.8, function()
		if toastToken == mine then
			toast.Visible = false
		end
	end)
end

local lastPress = 0
local function request()
	local now = os.clock()
	if now - lastPress < 0.4 then
		return
	end
	lastPress = now
	remote:FireServer()
end
button.Activated:Connect(request)
UserInputService.InputBegan:Connect(function(input, processed)
	if not processed and input.KeyCode == Enum.KeyCode.K then
		request()
	elseif not processed and input.KeyCode == Enum.KeyCode.H then
		toLandmark()
	end
end)

-- the angle (radians, positive = to the left seen from above) that turns direction a into direction b
local function signedAngle(a, b)
	return math.atan2(a.Z * b.X - a.X * b.Z, a:Dot(b))
end
local function rotate(dir, angle)
	local c, s = math.cos(angle), math.sin(angle)
	return Vector3.new(dir.X * c + dir.Z * s, 0, -dir.X * s + dir.Z * c)
end
local function turnRate(v) -- degrees per second
	if v <= 25 then
		return TURN_SLOW * (TURN_FAST / TURN_SLOW) ^ (v / 25)
	end
	return math.min(TURN_FAST * (25 / v) ^ 0.35, math.deg(TURN_G * workspace.Gravity / v))
end

-- ---- the arms ------------------------------------------------------------------------------------------------------------------------
-- The animation sets the arms' pose every frame, so a fixed frame change does not stay (it does for the legs, see the server). After the
-- animation has written, the shoulder and elbow rotations are changed so that both hands reach the grip the server worked out: two links
-- (upper arm, forearm) to a point, solved in the side view. Transform is not replicated, so this is what the rider sees of his own arms.
local function jointOf(char, name)
	for _, d in ipairs(char:GetDescendants()) do
		if d.Name == name and (d:IsA("Motor6D") or d.ClassName == "AnimationConstraint") then
			return d
		end
	end
	return nil
end
local function pivotOf(joint) -- where the joint turns, in the world
	if joint:IsA("Motor6D") then
		return (joint.Part0.CFrame * joint.C0).Position
	end
	return joint.Attachment0 and joint.Attachment0.WorldPosition or nil
end
local function armsOf(char)
	local arms = {}
	for _, side in ipairs({ "Left", "Right" }) do
		local shoulder, elbow, hand = jointOf(char, side .. "Shoulder"), jointOf(char, side .. "Elbow"), char:FindFirstChild(side .. "Hand")
		local s, e = shoulder and pivotOf(shoulder), elbow and pivotOf(elbow)
		if s and e and hand then -- the lengths are taken while the arm hangs, before anything is bent
			table.insert(arms, { shoulder = shoulder, elbow = elbow, upper = (e - s).Magnitude, lower = (hand.Position - e).Magnitude })
		end
	end
	return arms
end
-- the shoulder turn and the elbow bend (radians; a turn about +X swings straight-down toward -Z, forward) that put the hand at the grip.
-- `s` is the shoulder, `grip` the grip, both in the root part's frame.
local function reach(arm, s, grip)
	local down, forward = s.Y - grip.Y, s.Z - grip.Z
	local l1, l2 = arm.upper, arm.lower
	local d = math.clamp(math.sqrt(down * down + forward * forward), math.abs(l1 - l2) + 0.05, l1 + l2 - 0.02)
	local flex = math.pi - math.acos(math.clamp((l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2), -1, 1)) -- 0 = straight
	local lift = math.atan2(l2 * math.sin(flex), l1 + l2 * math.cos(flex))
	return math.atan2(forward, down) - lift, flex
end

-- ---- the tailwhip, drawn ----------------------------------------------------------------------------------------------------------
-- The deck and the back wheel are welded to the rider, so they cannot turn. For WHIP_TIME they are hidden on this screen and clones go
-- round the stem's axis in their place, following the scooter; then the clones go and the real parts show again.
local function playWhip(char, duration)
	local scooter = char and char:FindFirstChild("Scooter")
	local stem = scooter and scooter:FindFirstChild("Stem")
	if not stem then
		return nil
	end
	local pairs_ = {}
	for _, name in ipairs({ "Deck", "WheelBack" }) do
		local part = scooter:FindFirstChild(name)
		if part then
			local copy = part:Clone()
			for _, d in ipairs(copy:GetChildren()) do
				d:Destroy()
			end
			copy.Anchored = true
			copy.CanCollide, copy.CanQuery, copy.CanTouch = false, false, false
			copy.Parent = workspace.CurrentCamera
			part.LocalTransparencyModifier = 1
			table.insert(pairs_, { part = part, copy = copy })
		end
	end
	local t0, conn = os.clock(), nil
	local handle = {}
	function handle.stop()
		if conn then
			conn:Disconnect()
			conn = nil
		end
		for _, p in ipairs(pairs_) do
			p.copy:Destroy()
			if p.part.Parent then
				p.part.LocalTransparencyModifier = 0
			end
		end
		pairs_ = {}
	end
	conn = RunService.RenderStepped:Connect(function()
		local t = (os.clock() - t0) / duration
		if t >= 1 or not stem.Parent then
			handle.stop()
			return
		end
		local e = t * t * (3 - 2 * t) -- smoothstep: a kick, a fast spin, a catch
		local pivot = stem.Position
		local spin = CFrame.new(pivot) * CFrame.fromAxisAngle(stem.CFrame.UpVector, -2 * math.pi * e) * CFrame.new(-pivot)
		for _, p in ipairs(pairs_) do
			p.copy.CFrame = spin * p.part.CFrame
		end
	end)
	return handle
end
if trickRemote then
	trickRemote.OnClientEvent:Connect(function(char, name)
		if name == "tailwhip" and typeof(char) == "Instance" and char ~= player.Character then
			playWhip(char, WHIP_TIME)
		end
	end)
end

local ride -- { char, humanoid, root, idle, animate, walk, autoRotate, speed, dir, w, wv, side, skid, offset, seed, tricks... }

local function stopRide(keepBody)
	local r = ride
	if not r then
		return
	end
	ride = nil
	if r.driving then
		RunService:UnbindFromRenderStep("ScooterDrive")
		ContextActionService:UnbindAction("ScooterWhip")
	end
	if r.whip then
		r.whip.stop()
		r.whip = nil
	end
	if r.lift then
		r.lift:Destroy()
	end

	if r.armConnection then
		r.armConnection:Disconnect()
	end
	if r.idle then
		r.idle:Stop(0.2)
		r.idle:Destroy()
	end
	if r.animate and r.animate.Parent then
		r.animate.Disabled = false -- the walking animation script starts again by itself
	end
	if r.humanoid.Parent then
		r.humanoid.WalkSpeed = r.walk
		r.humanoid.AutoRotate = r.autoRotate
		r.humanoid:Move(Vector3.zero, false)
		if not keepBody and r.root.Parent then -- stand up straight again
			r.root.CFrame = CFrame.new(r.root.Position - r.offset) * CFrame.lookAt(Vector3.zero, r.dir)
		end
	end
	meter.Visible = false
	gauge.Visible = false
	button.Text = "킥보드 (K)"
	button.BackgroundColor3 = Color3.fromRGB(45, 110, 200)
end

-- the rider loses his balance: limp on the ground with the speed he had, the server takes the scooter away
local function fall(r, direction, reason, detail) -- direction: +1 to the right, -1 to the left; reason: what the player is told
	local humanoid, root = r.humanoid, r.root
	local look = root.CFrame.LookVector
	local velocity = root.AssemblyLinearVelocity
	stopRide(true)
	remote:FireServer(true)
	showToast(reason)
	player:SetAttribute("ScooterFall", detail) -- for testing: what the numbers were (this client only)
	humanoid:ChangeState(Enum.HumanoidStateType.Ragdoll)
	root.AssemblyLinearVelocity = velocity
	if direction == 0 then -- a loop-out: over the back wheel
		root.AssemblyAngularVelocity = root.CFrame.RightVector * 6
	else
		root.AssemblyAngularVelocity = look * (direction * 6) -- clockwise seen from behind = to the right
	end
	task.delay(FALL_RECOVER, function()
		if humanoid.Parent and humanoid:GetState() == Enum.HumanoidStateType.Ragdoll then
			humanoid:ChangeState(Enum.HumanoidStateType.GettingUp)
		end
	end)
end

local function poseRide(char)
	stopRide()
	local humanoid = char:FindFirstChildOfClass("Humanoid")
	local root = char:FindFirstChild("HumanoidRootPart")
	local animator = humanoid and humanoid:FindFirstChildOfClass("Animator")
	if not humanoid or not root or not animator then
		return
	end
	-- stand, do not walk: no Animate script, every running track stopped, the idle animation of that script played on its own
	local animate = char:FindFirstChild("Animate")
	local idleSource = animate and animate:FindFirstChild("idle") and animate.idle:FindFirstChild("Animation1")
	local idle
	if animate then
		animate.Disabled = true
		for _, track in ipairs(animator:GetPlayingAnimationTracks()) do
			track:Stop(0.1)
		end
		if idleSource then
			idle = animator:LoadAnimation(idleSource)
			idle.Priority = Enum.AnimationPriority.Idle
			idle.Looped = true
			idle:Play(0.2)
		end
	end
	local look = root.CFrame.LookVector
	local r = {
		char = char, humanoid = humanoid, root = root, idle = idle, animate = animate,
		walk = humanoid.WalkSpeed, autoRotate = humanoid.AutoRotate, speed = 0, dir = Vector3.new(look.X, 0, look.Z).Unit,
		w = 0, wv = 0, side = 0, skid = 0, offset = Vector3.zero, seed = math.random() * 100, clock = 0,
		air = false, launched = false, kicker = nil, airT = 0, whip = nil, whipT = 0,
	}
	ride = r
	humanoid.AutoRotate = false -- the facing is ours: the way we roll
	meter.Visible = true
	gauge.Visible = true
	button.Text = "내리기 (K)"
	button.BackgroundColor3 = Color3.fromRGB(200, 70, 60)
end

-- the drive: after the control scripts (RenderPriority.Input) have put the player's push into MoveDirection, take it and put ours in its place
local function driveRide()
	local r = ride
	if not r or r.driving then
		return
	end
	r.driving = true
	local char, humanoid, root = r.char, r.humanoid, r.root
	local arms = armsOf(char)
	local att = Instance.new("Attachment")
	att.Name = "ScooterLiftAttachment"
	att.Parent = root
	r.lift = Instance.new("VectorForce") -- takes part of gravity away while flying off a ramp
	r.lift.Name = "ScooterLift"
	r.lift.Attachment0 = att
	r.lift.RelativeTo = Enum.ActuatorRelativeTo.World
	r.lift.ApplyAtCenterOfMass = true
	r.lift.Enabled = false
	r.lift.Parent = root
	r.lift.Destroying:Connect(function()
		att:Destroy()
	end)
	r.rayParams = RaycastParams.new()
	r.rayParams.FilterType = Enum.RaycastFilterType.Exclude
	r.rayParams.FilterDescendantsInstances = { char }
	ContextActionService:BindAction("ScooterWhip", function(_, state)
		local rr = ride
		-- as many whips as the air time allows, one after another (user, 2026-10-15); not a new one while one is still turning
		if state ~= Enum.UserInputState.Begin or not rr or not rr.launched or not rr.air or rr.whip then
			return Enum.ContextActionResult.Sink
		end
		rr.whip = playWhip(char, WHIP_TIME)
		rr.whipT = 0
		if trickRemote then
			trickRemote:FireServer("tailwhip")
		end
		return Enum.ContextActionResult.Sink
	end, true, Enum.KeyCode.Q, Enum.KeyCode.ButtonR2)
	ContextActionService:SetTitle("ScooterWhip", "테일윕")
	ContextActionService:SetPosition("ScooterWhip", UDim2.new(1, -230, 1, -220))
	r.armConnection = RunService.PreSimulation:Connect(function()
		local grip = char:GetAttribute("ScooterGrip")
		if typeof(grip) ~= "Vector3" then
			return
		end
		for _, arm in ipairs(arms) do
			local pivot = pivotOf(arm.shoulder)
			if pivot then
				local lift, flex = reach(arm, root.CFrame:PointToObjectSpace(pivot), grip)
				arm.shoulder.Transform = CFrame.Angles(lift, 0, 0) * arm.shoulder.Transform
				arm.elbow.Transform = CFrame.Angles(flex, 0, 0) * arm.elbow.Transform
			end
		end
	end)
	RunService:BindToRenderStep("ScooterDrive", Enum.RenderPriority.Input.Value + 10, function(dt)
		dt = math.min(dt, 0.1)
		if char:GetAttribute("Gliding") == true then -- the paraglider flies the rider (2026-10-15); landing is handled as after a ramp
			r.lift.Enabled = false
			r.launched, r.air, r.airT = true, true, math.max(r.airT, 0.2)
			return
		end
		r.clock += dt
		local max = char:GetAttribute("ScooterMaxSpeed") or MAX_SPEED_DEFAULT
		local move = humanoid.MoveDirection -- keys, thumbstick or pad, turned to the camera
		local want = Vector3.new(move.X, 0, move.Z)
		local omega, sideRaw = 0, 0 -- turning rate (rad/s, + = left) and the sideways push (+ = left)
		if want.Magnitude > 0.1 then
			want = want.Unit
			local angle = signedAngle(r.dir, want)
			if r.speed < 1 then -- standing: swing round to face the push, then roll
				local step = math.clamp(angle, -math.rad(TURN_SLOW) * dt, math.rad(TURN_SLOW) * dt)
				r.dir = rotate(r.dir, step)
				omega = step / dt
				if math.abs(angle - step) < math.rad(60) then
					r.speed += ACCEL * dt
				end
			elseif math.abs(angle) > math.rad(BACK_ANGLE) then -- pushing back against the way we roll: brake
				r.speed -= BRAKE * dt
			else -- push forward or to the side: steer and speed up
				local step = math.clamp(angle, -math.rad(turnRate(r.speed)) * dt, math.rad(turnRate(r.speed)) * dt)
				r.dir = rotate(r.dir, step)
				omega = step / dt
				sideRaw = math.sin(angle)
				r.speed += ACCEL * dt
			end
		else
			r.speed -= (COAST_BASE + COAST_DRAG * r.speed) * dt
		end
		-- ran into something: the speed cannot stay above what the body really does, and at speed that is a fall
		local v = root.AssemblyLinearVelocity
		local actual = Vector3.new(v.X, 0, v.Z).Magnitude
		if r.speed > CRASH_FRAC * max and r.speed - actual > CRASH_DROP_FRAC * max then
			fall(r, r.w >= 0 and 1 or -1, "부딪혀서 넘어졌다!", string.format("crash speed=%.1f actual=%.1f", r.speed, actual))
			return
		end
		r.speed = math.clamp(math.min(r.speed, actual + 6), 0, max)
		-- balance
		local speed = r.speed
		r.side += (sideRaw - r.side) * math.min(1, dt / SIDE_TAU)
		if speed < 0.8 then -- standing still: a foot is down
			r.w, r.wv = 0, 0
		else
			local s = math.clamp((speed - 4) / 8, 0, 1) -- 0: nearly stopped, 1: rolling
			local f = speed / max
			local assist = (1 - math.clamp((f - 0.5) / 0.375, 0, 1)) * s
			local wobble = math.clamp((f - 0.625) / 0.375, 0, 1)
			local bumps = math.clamp(math.noise(r.clock * 1.6, r.seed) * 2.2, -1, 1) * NOISE_AMP * math.clamp((f - 0.375) / 0.625, 0, 1)
			local acc = bumps + G_LOW * (1 - s) * r.w + P_WOBBLE * wobble * r.w - K_ASSIST * assist * r.w - D_DAMP * r.wv
				+ R_CORRECT * r.side * math.clamp(speed / 20, 0, 1)
			r.wv += acc * dt
			r.w += r.wv * dt
		end
		local sideways = math.abs(speed * omega) / workspace.Gravity -- in g
		r.skid = sideways > SKID_LIMIT and r.skid + dt or math.max(0, r.skid - dt)
		if math.abs(r.w) >= W_FALL then
			fall(r, r.w > 0 and 1 or -1, "균형을 잃고 넘어졌다!", string.format("balance w=%.3f speed=%.1f clock=%.2f", r.w, speed, r.clock))
			return
		elseif r.skid > SKID_TIME then
			fall(r, omega > 0 and -1 or 1, "너무 빠르게 꺾어서 미끄러졌다!", string.format("skid omega=%.2f speed=%.1f", omega, speed)) -- the tyres let go: down on the inside of the turn
			return
		end
		-- tricks
		local drop = humanoid.HipHeight + root.Size.Y / 2
		local onGround = humanoid.FloorMaterial ~= Enum.Material.Air
		local hit = workspace:Raycast(root.Position, Vector3.new(0, -(drop + 4), 0), r.rayParams)
		if hit and hit.Instance.Name:sub(-7) == "#rampup" then
			r.kicker = hit.Instance
		elseif r.kicker and not r.launched then -- just left the steep side of a ramp: take off if we were going up it
			local climb = -r.kicker.CFrame.LookVector -- a wedge is high at its local +Z end
			climb = Vector3.new(climb.X, 0, climb.Z)
			if climb.Magnitude > 0.1 and climb.Unit:Dot(r.dir) > 0.5 and speed > MIN_LAUNCH then
				local vy = math.sqrt(2 * workspace.Gravity * AIR_G * LAUNCH_HEIGHT * speed) -- reaches LAUNCH_HEIGHT x speed under AIR_G
				humanoid:ChangeState(Enum.HumanoidStateType.Freefall)
				local v0 = root.AssemblyLinearVelocity
				root.AssemblyLinearVelocity = Vector3.new(v0.X, math.max(v0.Y, vy), v0.Z)
				r.lift.Force = Vector3.new(0, root.AssemblyMass * workspace.Gravity * (1 - AIR_G), 0)
				r.lift.Enabled = true
				r.launched, r.air, r.airT = true, true, 0
				player:SetAttribute("ScooterLaunch", string.format("speed=%.1f vy=%.1f", speed, vy)) -- for testing (this client only)
			end
			r.kicker = nil
		end
		if r.launched then
			r.airT += dt
			if r.whip then
				r.whipT += dt
				if r.whipT >= WHIP_TIME then
					r.whip = nil
				end
			end
			if onGround and r.airT > 0.15 then -- down again
				r.launched, r.air = false, false
				r.lift.Enabled = false
				player:SetAttribute("ScooterAirTime", r.airT)
				if r.whip then
					local h = r.whip
					r.whip = nil
					h.stop()
					fall(r, r.w >= 0 and 1 or -1, "테일윕을 다 못 돌리고 떨어졌다!", string.format("whip air=%.2f whip=%.2f", r.airT, r.whipT))
					return
				end
				r.wv += (math.random() - 0.5) * 0.8 -- the landing jolts the balance a little
			end
		end
		-- drive
		humanoid.WalkSpeed = speed
		humanoid:Move(speed > 0.2 and r.dir or Vector3.zero, false)
		-- lean: into the turn and with the wobble, tilted about where the wheels touch the ground
		local roll = math.clamp(-0.6 * math.atan(speed * omega / workspace.Gravity) + r.w, -0.7, 0.7)
		local rot = CFrame.lookAt(Vector3.zero, r.dir) * CFrame.Angles(0, 0, -roll)
		local base = root.Position - r.offset -- where the body is without last frame's lean
		r.offset = rot:VectorToWorldSpace(Vector3.new(0, drop, 0)) - Vector3.new(0, drop, 0)
		root.CFrame = CFrame.new(base + r.offset) * rot
		-- the screen
		meter.Text = string.format("%d km/h", math.floor(speed + 0.5)) -- 80 studs/s is 80 km/h
		local f = math.abs(r.w) / W_FALL
		marker.Position = UDim2.fromScale(0.5 + math.clamp(r.w / W_FALL, -1, 1) * 0.47, 0.5)
		marker.BackgroundColor3 = f < 0.4 and Color3.fromRGB(80, 200, 110) or (f < 0.75 and Color3.fromRGB(240, 170, 50) or Color3.fromRGB(230, 60, 55))
	end)
end

local attributeConnections = {}
local function refresh(char)
	local riding = char:GetAttribute("Riding") == true
	if riding or char:GetAttribute("Mounting") == true then
		if not ride or ride.char ~= char then
			poseRide(char) -- the standing animation first, so the server measures the hands in their final place
		end
		if riding then
			driveRide()
		end
	else
		stopRide()
	end
end
local function watch(char)
	for _, c in ipairs(attributeConnections) do
		c:Disconnect()
	end
	attributeConnections = {
		char:GetAttributeChangedSignal("Riding"):Connect(function() refresh(char) end),
		char:GetAttributeChangedSignal("Mounting"):Connect(function() refresh(char) end),
	}
	stopRide()
	refresh(char)
end
if player.Character then
	watch(player.Character)
end
player.CharacterAdded:Connect(watch)
player.CharacterRemoving:Connect(function()
	stopRide(true)
end)

-- ---- the sound of every rider (this client's own scooter and the others it can see) ----------------------------------------------------
local riders = {} -- [character] = { root, humanoid, sound, footsteps, footstepVolume }

local function addRider(char)
	if riders[char] then
		return
	end
	local root = char:FindFirstChild("HumanoidRootPart")
	local humanoid = char:FindFirstChildOfClass("Humanoid")
	if not root or not humanoid then
		return
	end
	local sound = Instance.new("Sound")
	sound.Name = "ScooterRolling"
	sound.SoundId = ROLL_SOUND
	sound.Looped = true
	sound.Volume = 0
	sound.RollOffMode = Enum.RollOffMode.Linear
	sound.RollOffMinDistance = 8
	sound.RollOffMaxDistance = 70
	sound.Parent = root
	local footsteps = root:FindFirstChild("Running")
	riders[char] = { root = root, humanoid = humanoid, sound = sound, footsteps = footsteps, footstepVolume = footsteps and footsteps.Volume or 0 }
end

local function removeRider(char)
	local r = riders[char]
	if not r then
		return
	end
	riders[char] = nil
	r.sound:Stop()
	r.sound:Destroy()
	if r.footsteps and r.footsteps.Parent then
		r.footsteps.Volume = r.footstepVolume
	end
end

RunService.Heartbeat:Connect(function()
	for char, r in pairs(riders) do
		if not char.Parent or not r.root.Parent then
			removeRider(char)
		else
			if r.footsteps then
				r.footsteps.Volume = 0 -- no steps on a scooter
			end
			local v = r.root.AssemblyLinearVelocity
			local speed = Vector3.new(v.X, 0, v.Z).Magnitude
			local max = char:GetAttribute("ScooterMaxSpeed") or MAX_SPEED_DEFAULT
			local onGround = r.humanoid.FloorMaterial ~= Enum.Material.Air
			if speed > 0.8 and onGround then
				local f = math.clamp(speed / max, 0, 1)
				r.sound.PlaybackSpeed = 0.6 + 0.9 * f
				r.sound.Volume = ROLL_VOLUME_MIN + (ROLL_VOLUME_MAX - ROLL_VOLUME_MIN) * f
				if not r.sound.IsPlaying then
					r.sound:Play()
				end
			elseif r.sound.IsPlaying then
				r.sound:Pause()
			end
		end
	end
end)

local function trackCharacter(char)
	local function refresh()
		if char:GetAttribute("Riding") == true then
			addRider(char)
		else
			removeRider(char)
		end
	end
	char:GetAttributeChangedSignal("Riding"):Connect(refresh)
	refresh()
end
local function trackPlayer(p)
	if p.Character then
		trackCharacter(p.Character)
	end
	p.CharacterAdded:Connect(trackCharacter)
	p.CharacterRemoving:Connect(removeRider)
end
for _, p in ipairs(Players:GetPlayers()) do
	trackPlayer(p)
end
Players.PlayerAdded:Connect(trackPlayer)
