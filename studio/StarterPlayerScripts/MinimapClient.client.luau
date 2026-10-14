-- U6 minimap and big map. LocalScript in StarterPlayer/StarterPlayerScripts, installed by data/build/install-u6.luau (src/minimap.py).
-- Reads ReplicatedStorage/MinimapData: rectangles {look, x, z, width, depth, rotation} in Studio studs (east +X, north -Z), drawn once as Frames
-- whose Offset is in studs; a UIScale zooms them and one Position keeps the player at the centre. North is always up; only the arrow turns.
-- M key or the map button opens the big map (the whole built area, place names). Rules: aidlc-docs/construction/plans/u6-minimap-scooter-plan.md
-- Teleport by hexagon (2026-10-14): the built cells are drawn as hexagons; a tap on one in the big map selects it and the button sends its index
-- to the server (ServerScriptService/HexTeleport), which moves the character to the cell's landing point.
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
-- the built cells: six edges each, a faint line under the roads and buildings (the map comes first, 2026-10-14 user); the picked cell
-- is drawn on top in orange. Widths are screen pixels whatever the zoom
local HEX_LINE, HEX_PICK = Color3.fromRGB(150, 155, 175), Color3.fromRGB(240, 120, 30)
local hexes = {}
for i, h in ipairs(Data.hexes or {}) do
	if type(h) == "table" and #h >= 15 then
		local pts, edges = {}, {}
		for k = 0, 5 do
			table.insert(pts, { h[4 + 2 * k], h[5 + 2 * k] })
		end
		for k = 1, 6 do
			local a, b = pts[k], pts[k % 6 + 1]
			local e = Instance.new("Frame")
			e.AnchorPoint = Vector2.new(0.5, 0.5)
			e.Position = UDim2.fromOffset((a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
			e.Rotation = math.deg(math.atan2(b[2] - a[2], b[1] - a[1]))
			e.BackgroundColor3 = HEX_LINE
			e.BackgroundTransparency = 0.45
			e.BorderSizePixel = 0
			e.ZIndex = 1
			e.Parent = world
			table.insert(edges, { f = e, len = math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2) })
		end
		table.insert(hexes, { index = i, name = h[1], pts = pts, edges = edges })
	end
end
local function inHex(hx, x, z) -- the cell is convex: the point is on the same side of every edge
	local sign = 0
	for k = 1, 6 do
		local a, b = hx.pts[k], hx.pts[k % 6 + 1]
		local c = (b[1] - a[1]) * (z - a[2]) - (b[2] - a[2]) * (x - a[1])
		if c ~= 0 then
			if sign ~= 0 and (c > 0) ~= (sign > 0) then
				return false
			end
			sign = c
		end
	end
	return true
end

-- place names {text, x, z, level, kind, rotation} (U6 map detail Q1 = A+B+C+D, Q2 = A): level 1 also on the small map, 2 on the big map,
-- 3 when the big map is zoomed in (ZOOM_DETAIL). Kinds 1 dong, 2 road, 3 facility, 4 building; px is the size on screen whatever the zoom
local KIND = {
	[1] = { px = 22, font = Enum.Font.GothamBlack, color = Color3.fromRGB(70, 80, 105) },
	[2] = { px = 12, font = Enum.Font.Gotham, color = Color3.fromRGB(95, 95, 105) },
	[3] = { px = 13, font = Enum.Font.GothamBold, color = Color3.fromRGB(25, 70, 150) },
	[4] = { px = 11, font = Enum.Font.GothamMedium, color = Color3.fromRGB(45, 45, 55) },
}
local ZOOM_DETAIL = 2
local labels = {}
for _, l in ipairs(Data.labels or {}) do
	local style = KIND[l[5] or 4] or KIND[4]
	local t = Instance.new("TextLabel")
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = UDim2.fromOffset(l[2], l[3])
	t.BackgroundTransparency = 1
	t.Text = l[1]
	t.Font = style.font
	t.TextColor3 = style.color
	t.TextStrokeColor3 = Color3.fromRGB(255, 255, 255)
	t.TextStrokeTransparency = 0.15
	t.Rotation = l[6] or 0
	t.ZIndex = (l[5] == 1) and 7 or 8
	t.Visible = false
	t.Parent = world
	table.insert(labels, { t = t, level = l[4] or 2, kind = l[5] or 4, x = l[2], z = l[3], px = style.px, chars = utf8.len(l[1]) or #l[1] })
end
-- the drawing order when names collide: dong, then level, facility before road before building, then the longer name
table.sort(labels, function(a, b)
	local ka, kb = a.kind == 1 and 0 or a.level, b.kind == 1 and 0 or b.level
	if ka ~= kb then return ka < kb end
	local ra, rb = ({ 0, 2, 1, 3 })[a.kind], ({ 0, 2, 1, 3 })[b.kind]
	if ra ~= rb then return ra < rb end
	return a.chars > b.chars
end)

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
-- data sources, always on the big map (U6 Q3 = A, 2026-10-14)
local credit = Instance.new("TextLabel")
credit.Name = "Credit"
credit.AnchorPoint = Vector2.new(1, 1)
credit.Position = UDim2.new(1, -10, 1, -6)
credit.Size = UDim2.fromOffset(420, 18)
credit.BackgroundTransparency = 1
credit.Text = "© OpenStreetMap contributors, 국토교통부 V-World"
credit.Font = Enum.Font.Gotham
credit.TextSize = 13
credit.TextXAlignment = Enum.TextXAlignment.Right
credit.TextColor3 = Color3.fromRGB(60, 60, 70)
credit.TextStrokeColor3 = Color3.fromRGB(255, 255, 255)
credit.TextStrokeTransparency = 0.4
credit.ZIndex = 15
credit.Parent = big

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

-- the big map zooms (mouse wheel, pinch, + and - buttons) and pans (drag); it opens on the whole built area
local userZoom, panX, panZ = 1, (bounds[1] + bounds[3]) / 2, (bounds[2] + bounds[4]) / 2
local function zoomBy(f)
	userZoom = math.clamp(userZoom * f, 1, 8)
end
for i, b in ipairs({ { "+", 1.5 }, { "-", 1 / 1.5 } }) do
	local btn = Instance.new("TextButton")
	btn.Name = "Zoom" .. i
	btn.AnchorPoint = Vector2.new(0, 1)
	btn.Position = UDim2.new(0, 10, 1, -10 - (2 - i) * 44)
	btn.Size = UDim2.fromOffset(38, 38)
	btn.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
	btn.Text = b[1]
	btn.Font = Enum.Font.GothamBold
	btn.TextSize = 24
	btn.TextColor3 = Color3.fromRGB(40, 40, 48)
	btn.ZIndex = 16
	btn.Parent = big
	round(btn, 8)
	btn.Activated:Connect(function()
		zoomBy(b[2])
	end)
end

-- the teleport button: shows the selected cell
local selected = nil
local go = Instance.new("TextButton")
go.Name = "Teleport"
go.AnchorPoint = Vector2.new(0.5, 1)
go.Position = UDim2.new(0.5, 0, 1, -12)
go.Size = UDim2.fromOffset(240, 40)
go.BackgroundColor3 = HEX_PICK
go.TextColor3 = Color3.fromRGB(255, 255, 255)
go.Font = Enum.Font.GothamBold
go.TextSize = 17
go.Visible = false
go.ZIndex = 16
go.Parent = big
round(go, 10)
local hint = Instance.new("TextLabel")
hint.AnchorPoint = Vector2.new(0.5, 0)
hint.Position = UDim2.new(0.5, 0, 0, 10)
hint.Size = UDim2.fromOffset(320, 22)
hint.BackgroundTransparency = 1
hint.Text = "육각형 칸을 누르면 그 칸으로 이동할 수 있어요"
hint.Font = Enum.Font.GothamMedium
hint.TextSize = 14
hint.TextColor3 = Color3.fromRGB(60, 60, 70)
hint.TextStrokeColor3 = Color3.fromRGB(255, 255, 255)
hint.TextStrokeTransparency = 0.3
hint.ZIndex = 15
hint.Parent = big
local lastZoom
local function paintHexes(zoom)
	for _, hx in ipairs(hexes) do
		local on = hx == selected
		for _, e in ipairs(hx.edges) do
			e.f.BackgroundColor3 = on and HEX_PICK or HEX_LINE
			e.f.BackgroundTransparency = on and 0 or 0.45
			e.f.ZIndex = on and 6 or 1
			e.f.Size = UDim2.fromOffset(e.len, (on and 3 or 1.5) / math.max(zoom or 1, 0.01))
		end
	end
end
local function pickHex(hx)
	selected = hx
	go.Visible = hx ~= nil
	go.Text = hx and (hx.name .. " 칸으로 이동") or ""
	paintHexes(lastZoom)
end
local teleportRemote = ReplicatedStorage:WaitForChild("HexTeleport", 10)

local isBig = false
local function showLabels(zoom)
	-- a name that would cover one already shown is left out at this zoom (screen boxes, the rotation ignored)
	local shown = {}
	for _, l in ipairs(labels) do
		local on = (isBig and (l.level <= 2 or userZoom >= ZOOM_DETAIL)) or (not isBig and l.level == 1)
		if on and zoom then
			local hw, hh = l.px * (l.chars + 1) * 0.5 * 0.9, l.px * 0.7
			local sx, sy = l.x * zoom, l.z * zoom
			for _, o in ipairs(shown) do
				if math.abs(sx - o[1]) < hw + o[3] and math.abs(sy - o[2]) < hh + o[4] then
					on = false
					break
				end
			end
			if on then
				table.insert(shown, { sx, sy, hw, hh })
			end
		end
		l.t.Visible = on
	end
end
local function setBig(on)
	isBig = on
	mini.Visible = not on
	big.Visible = on
	world.Parent = on and big or mini
	marker.Parent = on and big or mini
	if on then
		userZoom, panX, panZ = 1, (bounds[1] + bounds[3]) / 2, (bounds[2] + bounds[4]) / 2
	end
	pickHex(nil)
	showLabels()
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
local dragging, lastPos, downPos = false, nil, nil
local tapView = { zoom = 1, cx = 0, cz = 0 } -- the big map's last zoom and centre, to turn a tap into studs
big.InputBegan:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		dragging, lastPos, downPos = true, input.Position, input.Position
	end
end)
big.InputEnded:Connect(function(input)
	-- a tap (not a drag) picks the hexagon under it
	if not isBig or not downPos or not (input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch) then
		return
	end
	local moved = (Vector2.new(input.Position.X, input.Position.Y) - Vector2.new(downPos.X, downPos.Y)).Magnitude
	downPos = nil
	if moved > 6 then
		return
	end
	local vp, at = big.AbsoluteSize, big.AbsolutePosition
	local x = tapView.cx + (input.Position.X - at.X - vp.X / 2) / tapView.zoom
	local z = tapView.cz + (input.Position.Y - at.Y - vp.Y / 2) / tapView.zoom
	local hit = nil
	for _, hx in ipairs(hexes) do
		if inHex(hx, x, z) then
			hit = hx
			break
		end
	end
	pickHex(hit)
end)
go.Activated:Connect(function()
	if selected and teleportRemote then
		teleportRemote:FireServer(selected.index)
		setBig(false)
	end
end)
UserInputService.InputEnded:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		dragging = false
	end
end)
UserInputService.InputChanged:Connect(function(input)
	if not isBig then
		return
	end
	if input.UserInputType == Enum.UserInputType.MouseWheel then
		zoomBy(input.Position.Z > 0 and 1.25 or 1 / 1.25)
	elseif dragging and lastPos and (input.UserInputType == Enum.UserInputType.MouseMovement or input.UserInputType == Enum.UserInputType.Touch) then
		local d = input.Position - lastPos
		lastPos = input.Position
		local vp = big.AbsoluteSize
		local fit = math.min(vp.X / math.max(bounds[3] - bounds[1], 1), vp.Y / math.max(bounds[4] - bounds[2], 1))
		panX = math.clamp(panX - d.X / (fit * userZoom), bounds[1], bounds[3])
		panZ = math.clamp(panZ - d.Y / (fit * userZoom), bounds[2], bounds[4])
	end
end)
UserInputService.TouchPinch:Connect(function(_, scale, _, state)
	if isBig and state == Enum.UserInputState.Change then
		zoomBy(math.clamp(scale, 0.9, 1.1))
	end
end)
workspace.CurrentCamera:GetPropertyChangedSignal("ViewportSize"):Connect(function()
	size = miniSize()
	mini.Size = UDim2.fromOffset(size, size)
	mapButton.Position = UDim2.new(1, -12, 0, 12 + size + 6)
end)

local lastBig = nil
RunService.RenderStepped:Connect(function()
	local view = isBig and big or mini
	local vp = view.AbsoluteSize
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart")
	local zoom, cx, cz
	if isBig then -- the whole built area fits the view at zoom 1; the arrow moves
		local w, h = math.max(bounds[3] - bounds[1], 1), math.max(bounds[4] - bounds[2], 1)
		zoom = math.min(vp.X / w, vp.Y / h) * userZoom
		cx, cz = panX, panZ
	elseif root then -- the player stays in the middle; the map moves
		zoom = MINI_ZOOM
		cx, cz = root.Position.X, root.Position.Z
	else
		return
	end
	zoomScale.Scale = zoom
	if isBig then
		tapView.zoom, tapView.cx, tapView.cz = zoom, cx, cz
	end
	-- positions as a share of the view: an Offset is a whole number of pixels, a Scale moves smoothly
	world.Position = UDim2.fromScale((vp.X / 2 - cx * zoom) / vp.X, (vp.Y / 2 - cz * zoom) / vp.Y)
	if zoom ~= lastZoom or isBig ~= lastBig then -- names keep their size on screen: the world is scaled, so the text is not
		lastZoom, lastBig = zoom, isBig
		showLabels(zoom)
		paintHexes(zoom)
		for _, l in ipairs(labels) do
			local ts = math.min(l.px / zoom, 100)
			l.t.TextSize = ts
			l.t.Size = UDim2.fromOffset(ts * (l.chars + 1), ts * 1.4)
		end
	end
	if root then
		marker.Position = UDim2.fromScale(0.5 + (root.Position.X - cx) * zoom / vp.X, 0.5 + (root.Position.Z - cz) * zoom / vp.Y)
		local look = workspace.CurrentCamera.CFrame.LookVector
		marker.Rotation = math.deg(math.atan2(look.X, -look.Z)) -- clockwise from north
	end
end)
