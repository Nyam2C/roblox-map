--[[
	Elevator (U7 BR-I7): every part tagged "Elevator" (MapBuilder sets it on the elevator doors of apartments and tall commercial
	blocks, with the attributes BuildingId, ElevatorFloor 0.., ElevatorFloors) gets ProximityPrompts "위층" / "아래층". The server
	moves the player's character to the door of the next floor of the same building.

	Checks (the server decides; nothing the client sends is used): the character is within REACH of the pressed door, the target
	floor is inside 0 .. ElevatorFloors - 1 and its door exists in the same building, one move per player per COOLDOWN seconds.
	Source of truth: studio/ServerScriptService/Elevator.server.luau.
]]

local CollectionService = game:GetService("CollectionService")
local Players = game:GetService("Players")

local REACH = 14 -- studs from the door
local COOLDOWN = 1.0
local ARRIVE = 1.2 * 3.6 -- studs in front of the target door

local doors = {} -- [buildingId][floor] = part
local last = {} -- [player] = os.clock() of the last move

local function index(part)
	local id, floor = part:GetAttribute("BuildingId"), part:GetAttribute("ElevatorFloor")
	if type(id) ~= "string" or type(floor) ~= "number" then
		return nil
	end
	doors[id] = doors[id] or {}
	doors[id][floor] = part
	return id, floor
end

local function move(player, part, step)
	local now = os.clock()
	if last[player] and now - last[player] < COOLDOWN then
		return
	end
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not root or (root.Position - part.Position).Magnitude > REACH then
		return
	end
	local id, floor, count = part:GetAttribute("BuildingId"), part:GetAttribute("ElevatorFloor"), part:GetAttribute("ElevatorFloors")
	local target = floor + step
	if type(count) ~= "number" or target < 0 or target >= count then
		return
	end
	local door = doors[id] and doors[id][target]
	if not door or not door.Parent then
		return
	end
	last[player] = now
	local front = door.CFrame.LookVector -- the door's Front faces the room
	local feet = door.Position - Vector3.new(0, door.Size.Y / 2, 0)
	local spot = feet + front * ARRIVE + Vector3.new(0, 3, 0)
	char:PivotTo(CFrame.lookAt(spot, spot + front))
end

local function prompt(part, name, text, step)
	local p = Instance.new("ProximityPrompt")
	p.Name = name
	p.ActionText = text
	p.ObjectText = "엘리베이터"
	p.HoldDuration = 0
	p.MaxActivationDistance = 10
	p.RequiresLineOfSight = false
	p.KeyboardKeyCode = step > 0 and Enum.KeyCode.E or Enum.KeyCode.Q
	p.GamepadKeyCode = step > 0 and Enum.KeyCode.ButtonX or Enum.KeyCode.ButtonY -- both on ButtonX would fire together
	p.Triggered:Connect(function(player)
		move(player, part, step)
	end)
	p.Parent = part
end

local function setup(part)
	if not part:IsA("BasePart") or part:FindFirstChild("ElevatorUp") or part:FindFirstChild("ElevatorDown") then
		return
	end
	local id, floor = index(part)
	if not id then
		return
	end
	local count = part:GetAttribute("ElevatorFloors") or 0
	if floor < count - 1 then
		prompt(part, "ElevatorUp", "위층", 1)
	end
	if floor > 0 then
		prompt(part, "ElevatorDown", "아래층", -1)
	end
end

for _, part in ipairs(CollectionService:GetTagged("Elevator")) do
	setup(part)
end
CollectionService:GetInstanceAddedSignal("Elevator"):Connect(setup)
Players.PlayerRemoving:Connect(function(player)
	last[player] = nil
end)
