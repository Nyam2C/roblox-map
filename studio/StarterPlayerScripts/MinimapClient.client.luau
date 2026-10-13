-- U6 minimap and big map. LocalScript in StarterPlayer/StarterPlayerScripts, installed by data/build/install-u6.luau (src/minimap.py).
-- Reads ReplicatedStorage/MinimapData: rectangles {look, x, z, width, depth, rotation} in Studio studs (east +X, north -Z), drawn once as Frames
-- whose Offset is in studs; a UIScale zooms them and one Position keeps the player at the centre. North is always up; only the arrow turns.
-- M key or the map button opens the big map (the whole built area, place names). Rules: aidlc-docs/construction/plans/u6-minimap-scooter-plan.md
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local StarterGui = game:GetService("StarterGui")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local MINI_ZOOM = 0.25 -- pixels per stud on the minimap (200 px = 800 studs = 220 m)
local LAND = Color3.fromRGB(231, 227, 216)
local LOOKS = { -- [look] = {colour, ZIndex}
	[1] = { Color3.fromRGB(184, 214, 160), 2 }, -- park
	[2] = { Color3.fromRGB(226, 208, 160), 2 }, -- sports ground
	[3] = { Color3.fromRGB(150, 180, 215), 2 }, -- court
	[4] = { Color3.fromRGB(255, 255, 255), 3 }, -- road
	[5] = { Color3.fromRGB(246, 240, 225), 3 }, -- path
	[6] = { Color3.fromRGB(176, 176, 186), 4 }, -- building
}

-- a missing or broken data module gives an empty map, not an error
local ok, Data = pcall(function()
	return require(ReplicatedStorage:WaitForChild("MinimapData", 10))
end)
if not ok or type(Data) ~= "table" then
	Data = { bounds = { 0, 0, 1, 1 }, rects = {}, labels = {} }
end
local bounds = Data.bounds or { 0, 0, 1, 1 }

-- the player list sits in the same corner; the map takes its place (the core scripts may not be ready yet: try a few times)
task.spawn(function()
	for _ = 1, 10 do
		if pcall(StarterGui.SetCoreGuiEnabled, StarterGui, Enum.CoreGuiType.PlayerList, false) then
			return
		end
		task.wait(0.5)
	end
end)

local gui = Instance.new("ScreenGui")
gui.Name = "MapGui"
gui.ResetOnSpawn = false
gui.DisplayOrder = 5
gui.Parent = player:WaitForChild("PlayerGui")

local function miniSize()
	local vp = workspace.CurrentCamera.ViewportSize
	return math.clamp(math.floor(math.min(vp.X, vp.Y) * 0.3), 110, 200)
end

local function round(frame, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius)
	c.Parent = frame
end

local function outline(frame, thickness)
	local s = Instance.new("UIStroke")
	s.Color = Color3.fromRGB(45, 45, 52)
	s.Thickness = thickness
	s.Parent = frame
end

-- the one world: rectangles and place names
local world = Instance.new("Frame")
world.Name = "World"
world.BackgroundTransparency = 1
world.Size = UDim2.fromOffset(0, 0)
local zoomScale = Instance.new("UIScale")
zoomScale.Parent = world
for _, r in ipairs(Data.rects or {}) do
	local look = type(r) == "table" and LOOKS[r[1]]
	if look and #r >= 6 then
		local f = Instance.new("Frame")
		f.AnchorPoint = Vector2.new(0.5, 0.5)
		f.Position = UDim2.fromOffset(r[2], r[3])
		f.Size = UDim2.fromOffset(r[4], r[5])
		f.Rotation = -r[6] -- a yaw counterclockwise from east is a negative UI rotation (UI turns clockwise)
		f.BackgroundColor3 = look[1]
		f.BorderSizePixel = 0
		f.ZIndex = look[2]
		f.Parent = world
	end
end
local labels = {}
for _, l in ipairs(Data.labels or {}) do
	local t = Instance.new("TextLabel")
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = UDim2.fromOffset(l[2], l[3])
	t.Size = UDim2.fromOffset(600, 80)
	t.BackgroundTransparency = 1
	t.Text = l[1]
	t.Font = Enum.Font.GothamBold
	t.TextColor3 = Color3.fromRGB(30, 30, 38)
	t.TextStrokeColor3 = Color3.fromRGB(255, 255, 255)
	t.TextStrokeTransparency = 0.2
	t.ZIndex = 8
	t.Visible = false
	t.Parent = world
	table.insert(labels, t)
end

-- the small map, top right
local size = miniSize()
local mini = Instance.new("Frame")
mini.Name = "Mini"
mini.AnchorPoint = Vector2.new(1, 0)
mini.Position = UDim2.new(1, -12, 0, 12)
mini.Size = UDim2.fromOffset(size, size)
mini.BackgroundColor3 = LAND
mini.BorderSizePixel = 0
mini.ClipsDescendants = true
mini.Parent = gui
round(mini, 10)
outline(mini, 2)

-- the big map, centred
local big = Instance.new("Frame")
big.Name = "Big"
big.AnchorPoint = Vector2.new(0.5, 0.5)
big.Position = UDim2.fromScale(0.5, 0.5)
big.Size = UDim2.fromScale(0.82, 0.82)
big.BackgroundColor3 = LAND
big.BorderSizePixel = 0
big.ClipsDescendants = true
big.Visible = false
big.ZIndex = 1
big.Parent = gui
round(big, 12)
outline(big, 3)

-- the player: a red dot with a pointer that turns with the camera
local marker = Instance.new("Frame")
marker.Name = "Marker"
marker.AnchorPoint = Vector2.new(0.5, 0.5)
marker.Size = UDim2.fromOffset(22, 22)
marker.BackgroundTransparency = 1
marker.ZIndex = 10
local pointer = Instance.new("Frame")
pointer.AnchorPoint = Vector2.new(0.5, 0.5)
pointer.Position = UDim2.new(0.5, 0, 0, 3)
pointer.Size = UDim2.fromOffset(8, 8)
pointer.Rotation = 45
pointer.BackgroundColor3 = Color3.fromRGB(225, 45, 45)
pointer.BorderSizePixel = 0
pointer.ZIndex = 10
pointer.Parent = marker
local dot = Instance.new("Frame")
dot.AnchorPoint = Vector2.new(0.5, 0.5)
dot.Position = UDim2.fromScale(0.5, 0.55)
dot.Size = UDim2.fromOffset(12, 12)
dot.BackgroundColor3 = Color3.fromRGB(225, 45, 45)
dot.BorderSizePixel = 0
dot.ZIndex = 11
dot.Parent = marker
round(dot, 6)
local ring = Instance.new("UIStroke")
ring.Color = Color3.fromRGB(255, 255, 255)
ring.Thickness = 2
ring.Parent = dot

local mapButton = Instance.new("TextButton")
mapButton.Name = "MapButton"
mapButton.AnchorPoint = Vector2.new(1, 0)
mapButton.Position = UDim2.new(1, -12, 0, 12 + size + 6)
mapButton.Size = UDim2.fromOffset(86, 28)
mapButton.BackgroundColor3 = Color3.fromRGB(40, 44, 54)
mapButton.TextColor3 = Color3.fromRGB(255, 255, 255)
mapButton.Font = Enum.Font.GothamBold
mapButton.TextSize = 14
mapButton.Text = "지도 (M)"
mapButton.AutoButtonColor = true
mapButton.ZIndex = 20 -- above the big map even on a narrow screen
mapButton.Parent = gui
round(mapButton, 8)

local isBig = false
local function setBig(on)
	isBig = on
	mini.Visible = not on
	big.Visible = on
	world.Parent = on and big or mini
	marker.Parent = on and big or mini
	for _, t in ipairs(labels) do
		t.Visible = on
	end
	mapButton.Text = on and "닫기 (M)" or "지도 (M)"
end
setBig(false)

mapButton.Activated:Connect(function()
	setBig(not isBig)
end)
UserInputService.InputBegan:Connect(function(input, processed)
	if not processed and input.KeyCode == Enum.KeyCode.M then
		setBig(not isBig)
	end
end)
workspace.CurrentCamera:GetPropertyChangedSignal("ViewportSize"):Connect(function()
	size = miniSize()
	mini.Size = UDim2.fromOffset(size, size)
	mapButton.Position = UDim2.new(1, -12, 0, 12 + size + 6)
end)

RunService.RenderStepped:Connect(function()
	local view = isBig and big or mini
	local vp = view.AbsoluteSize
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	local zoom, cx, cz
	if isBig then -- the whole built area fits the view; the arrow moves
		local w, h = math.max(bounds[3] - bounds[1], 1), math.max(bounds[4] - bounds[2], 1)
		zoom = math.min(vp.X / w, vp.Y / h)
		cx, cz = (bounds[1] + bounds[3]) / 2, (bounds[2] + bounds[4]) / 2
	elseif root then -- the player stays in the middle; the map moves
		zoom = MINI_ZOOM
		cx, cz = root.Position.X, root.Position.Z
	else
		return
	end
	zoomScale.Scale = zoom
	-- positions as a share of the view: an Offset is a whole number of pixels, a Scale moves smoothly
	world.Position = UDim2.fromScale((vp.X / 2 - cx * zoom) / vp.X, (vp.Y / 2 - cz * zoom) / vp.Y)
	if isBig then
		local textSize = math.clamp(math.floor(15 / zoom), 8, 100)
		for _, t in ipairs(labels) do
			t.TextSize = textSize
		end
	end
	if root then
		marker.Position = UDim2.fromScale(0.5 + (root.Position.X - cx) * zoom / vp.X, 0.5 + (root.Position.Z - cz) * zoom / vp.Y)
		local look = workspace.CurrentCamera.CFrame.LookVector
		marker.Rotation = math.deg(math.atan2(look.X, -look.Z)) -- clockwise from north
	end
end)
