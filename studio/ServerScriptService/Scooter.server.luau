-- U6 kick scooter, server side. Script in ServerScriptService, installed by data/build/install-u6.luau (src/minimap.py).
-- ScooterToggle: the server looks at the character itself and decides. Getting on (at most once per COOLDOWN seconds per player):
--   both feet are brought together (the hips are turned by changing the joints' fixed frames, which replicate to everybody) and the attribute
--   Mounting tells the client to stand in its riding animation; POSE_WAIT seconds later the handlebar's place is worked out from the rig (the
--   grip: where both hands can hold on, from the shoulders and the arm lengths) and the scooter is made to fit it: five unanchored parts welded
--   to the HumanoidRootPart (no collision, no mass), the character lifted LIFT studs so the feet stand on the deck, and the attributes Riding,
--   ScooterMaxSpeed and ScooterGrip (y, z of the grip in the root part's frame) on the character. The rider's own client bends the arms to it.
-- Getting off is always allowed. The one optional argument true means "fell off": the client lost its balance (see ScooterClient) and the
-- player may not get on again for FALL_LOCKOUT seconds. The speed, the balance and the falling are worked out by that player's
-- ScooterClient because the character's physics belong to the client. Everything done here is undone when the character is removed,
-- dies, or the player leaves. Limit: a client can always move its own character as it likes (speed hacks, never falling); nothing here
-- can stop that, the server only decides who is riding and shows the scooter to everyone.
-- Rules: aidlc-docs/construction/plans/u6-minimap-scooter-plan.md
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local MAX_SPEED = 120 -- studs per second (raised from 80 by the user, 2026-10-14) (shown as km/h); handed to the client as the attribute ScooterMaxSpeed
local LIFT = 0.5 -- studs: the deck top is where the feet stand
local COOLDOWN = 0.6
local FALL_LOCKOUT = 2.5
local POSE_WAIT = 0.4 -- seconds for the standing pose to reach the server before the scooter is made
local REACH = 0.9 -- the grip is this share of the full arm length from the shoulder, so the elbows stay a little bent
local GRIP_ANGLE = math.rad(52) -- the grip lies this far forward of straight below the shoulder
local GRIP_LIFT = 0.4 -- studs: measured, the bent arm's hand ends about 0.5 above the point it is aimed at, so the bar goes up to meet it

local remote = ReplicatedStorage:FindFirstChild("ScooterToggle")
if not remote then
	remote = Instance.new("RemoteEvent")
	remote.Name = "ScooterToggle"
	remote.Parent = ReplicatedStorage
end

-- the parts, from the measured deck width, handlebar width, handlebar height above the ground and handlebar z (forward is -Z)
-- name, size, x, height of the centre above the ground, z, colour, material, cylinder
local function partsFor(deckWidth, barWidth, barHeight, barZ)
	local stem = math.max(barHeight - 0.5, 1)
	return {
		{ "Deck", Vector3.new(deckWidth, 0.3, 2 * math.max(2.1, 0.4 - barZ)), 0, 0.35, 0, Color3.fromRGB(45, 110, 200), Enum.Material.SmoothPlastic, false },
		{ "Stem", Vector3.new(0.25, stem, 0.25), 0, 0.5 + stem / 2, barZ, Color3.fromRGB(60, 60, 65), Enum.Material.Metal, false },
		{ "Bar", Vector3.new(barWidth, 0.22, 0.22), 0, barHeight, barZ, Color3.fromRGB(40, 40, 45), Enum.Material.Metal, false },
		{ "WheelFront", Vector3.new(0.3, 1.0, 1.0), 0, 0.5, barZ + 0.1, Color3.fromRGB(25, 25, 28), Enum.Material.SmoothPlastic, true },
		{ "WheelBack", Vector3.new(0.3, 1.0, 1.0), 0, 0.5, 1.7, Color3.fromRGB(25, 25, 28), Enum.Material.SmoothPlastic, true },
	}
end

-- A joint's fixed frame on the torso side turns the whole limb below it: the Attachment0 of an AnimationConstraint, the C0 of a Motor6D.
-- turnJoint changes it and remembers the old value in `undo` ({ object, property, value } rows). It works for the legs (the standing
-- animation does not fight it) but not for the arms, whose pose the animation sets every frame (the client bends those, see ScooterClient).
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
local function turnJoint(undo, char, name, rotation)
	local joint = jointOf(char, name)
	if not joint then
		return false
	end
	local object, property = joint, "C0"
	if not joint:IsA("Motor6D") then
		object, property = joint.Attachment0, "CFrame"
	end
	if not object then
		return false
	end
	table.insert(undo, { object, property, object[property] })
	object[property] = object[property] * rotation
	return true
end

-- Feet together: the standing animation puts them a shoulder width apart. Returns the width the feet cover afterwards.
local function narrowStance(undo, char, root)
	local left, right = char:FindFirstChild("LeftFoot"), char:FindFirstChild("RightFoot")
	if not (left and right) then
		return 2.6
	end
	local a, b = root.CFrame:PointToObjectSpace(left.Position), root.CFrame:PointToObjectSpace(right.Position)
	local apart, footWidth = math.abs(a.X - b.X), left.Size.X
	local want = footWidth + 0.15
	if apart <= want then
		return apart + footWidth
	end
	local legLength = math.max(math.abs(a.Y) - 0.5, 1) -- from about the hip to the sole
	local theta = math.min(math.atan((apart - want) / 2 / legLength), math.rad(25))
	local ok = turnJoint(undo, char, "LeftHip", CFrame.Angles(0, 0, theta)) -- the left leg hangs at -X: a turn about the front axis moves its foot to +X
	ok = turnJoint(undo, char, "RightHip", CFrame.Angles(0, 0, -theta)) and ok
	return ok and (want + footWidth) or (apart + footWidth)
end

-- The grip, in the root part's frame: the arm (shoulder -> elbow -> hand) is measured while it hangs, and the grip is put REACH of its full
-- length from the shoulder, GRIP_ANGLE forward of straight down. Returns half the span of the hanging hands, the grip's y and z, or nil.
local function gripOf(char, root)
	local shoulder, elbow, hand = jointOf(char, "LeftShoulder"), jointOf(char, "LeftElbow"), char:FindFirstChild("LeftHand")
	if not (shoulder and elbow and hand) then
		return nil
	end
	local s, e = pivotOf(shoulder), pivotOf(elbow)
	if not (s and e) then
		return nil
	end
	local length = (e - s).Magnitude + (hand.Position - e).Magnitude
	local reach = REACH * length
	local ls = root.CFrame:PointToObjectSpace(s)
	-- the hands hang a little outside the shoulder pivots: the handlebar is as wide as they are apart
	return math.abs(root.CFrame:PointToObjectSpace(hand.Position).X), ls.Y - reach * math.cos(GRIP_ANGLE), ls.Z - reach * math.sin(GRIP_ANGLE)
end

local state = {} -- [Player] = { model, humanoid, hip, undo }
local lastRequest = {} -- [Player] = os.clock()

local function stop(player)
	local s = state[player]
	if not s then
		return
	end
	state[player] = nil
	if s.model then
		s.model:Destroy()
	end
	for i = #s.undo, 1, -1 do -- the joints go back to where they were
		local row = s.undo[i]
		pcall(function()
			row[1][row[2]] = row[3]
		end)
	end
	if s.humanoid and s.humanoid.Parent then
		s.humanoid.HipHeight = s.hip
	end
	local char = player.Character
	if char then
		char:SetAttribute("Mounting", nil)
		char:SetAttribute("Riding", false)
		char:SetAttribute("ScooterMaxSpeed", nil)
		char:SetAttribute("ScooterGrip", nil)
	end
end

local function start(player, char, humanoid, root)
	local mine = { humanoid = humanoid, hip = humanoid.HipHeight, undo = {} }
	state[player] = mine
	local feetSpan = narrowStance(mine.undo, char, root)
	char:SetAttribute("Mounting", true) -- the client switches to the standing animation now
	task.wait(POSE_WAIT)
	if state[player] ~= mine or not char.Parent or humanoid.Health <= 0 or not root.Parent then
		return -- got off, fell or died meanwhile: stop() has already undone what it knew of
	end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { char }
	local hit = workspace:Raycast(root.Position, Vector3.new(0, -12, 0), params)
	local drop = (hit and hit.Distance or (humanoid.HipHeight + root.Size.Y / 2)) + LIFT -- root centre to the ground once lifted
	-- where both hands can hold on; the handlebar goes there
	local halfSpan, gripY, gripZ = gripOf(char, root)
	local barWidth, barHeight, barZ = feetSpan + 1.0, 3.9, -1.9 -- without arms in the rig: a handlebar in front of the chest
	if gripY then
		barWidth = math.clamp(2 * halfSpan + 0.4, 1.6, 5)
		barHeight = math.clamp(drop + gripY - 0.1 + GRIP_LIFT, 2.2, 5.5)
		barZ = math.clamp(gripZ, -3.2, -1.0)
		char:SetAttribute("ScooterGrip", Vector3.new(0, gripY - 0.1, barZ)) -- the rider's client bends the arms to the bar's top
	end
	local model = Instance.new("Model")
	model.Name = "Scooter"
	for _, p in ipairs(partsFor(math.clamp(feetSpan + 0.5, 1.4, 4), barWidth, barHeight, barZ)) do
		local part = Instance.new("Part")
		part.Name = p[1]
		part.Size = p[2]
		part.Color = p[6]
		part.Material = p[7]
		if p[8] then
			part.Shape = Enum.PartType.Cylinder
		end
		part.Massless = true
		part.CanCollide = false
		part.CanQuery = false
		part.CanTouch = false
		part.CFrame = root.CFrame * CFrame.new(p[3], p[4] - drop, p[5])
		part.Parent = model
		local weld = Instance.new("WeldConstraint")
		weld.Part0 = root
		weld.Part1 = part
		weld.Parent = part
	end
	model.Parent = char
	mine.model = model
	humanoid.HipHeight = mine.hip + LIFT
	char:SetAttribute("ScooterMaxSpeed", MAX_SPEED)
	char:SetAttribute("Riding", true) -- the client starts driving when it sees this
	char:SetAttribute("Mounting", nil)
end

remote.OnServerEvent:Connect(function(player, fell)
	local now = os.clock()
	if state[player] then -- getting off is always allowed (also while the pose is still coming)
		stop(player)
		lastRequest[player] = now + (fell == true and FALL_LOCKOUT or 0)
		return
	end
	if (lastRequest[player] or -math.huge) + COOLDOWN > now then
		return
	end
	lastRequest[player] = now
	local char = player.Character
	local humanoid = char and char:FindFirstChildOfClass("Humanoid")
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not humanoid or not root or humanoid.Health <= 0 or humanoid.SeatPart or char:GetAttribute("Carting") == true then
		return -- not out of the shopping cart (Cart.server.luau)
	end
	start(player, char, humanoid, root)
end)

local function watch(player)
	player.CharacterRemoving:Connect(function()
		stop(player)
	end)
	player.CharacterAdded:Connect(function(char)
		local humanoid = char:WaitForChild("Humanoid")
		humanoid.Died:Connect(function()
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

-- tricks (2026-10-14): a rider's client plays its own tailwhip and tells the server; the server checks and passes it on, and every other
-- client plays the same deck spin on that rider's scooter (a spin of welded parts is only drawn, it is not physics, so it is not replicated)
local trick = ReplicatedStorage:FindFirstChild("ScooterTrick")
if not trick then
	trick = Instance.new("RemoteEvent")
	trick.Name = "ScooterTrick"
	trick.Parent = ReplicatedStorage
end
local lastTrick = {}
trick.OnServerEvent:Connect(function(player, name)
	if name ~= "tailwhip" then
		return
	end
	local char = player.Character
	if not char or char:GetAttribute("Riding") ~= true then
		return
	end
	local now = os.clock()
	if (lastTrick[player] or -math.huge) + 0.3 > now then
		return
	end
	lastTrick[player] = now
	for _, other in ipairs(Players:GetPlayers()) do
		if other ~= player then
			trick:FireClient(other, char, name)
		end
	end
end)
Players.PlayerRemoving:Connect(function(player)
	lastTrick[player] = nil
end)
