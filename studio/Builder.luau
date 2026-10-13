--[[
	MapBuilder: builds one cell of the map in Studio from the chunk files that src/build_luau.py writes.
	Source of truth is studio/Builder.luau in the repository; Claude puts it here through the Studio MCP
	(replace the module instance: new ModuleScript with the Source, Destroy the old one, because require caches per instance).

	It does no geometry. Every position, size and angle arrives computed (see layout.py and layout_details.py); this module
	only makes parts. It never runs received text as code (no loadstring) and only ever destroys Workspace/Auto/<cell id>.

	Layout:   Workspace/Auto/<cell id>/{Ground, Roads, Paths, Sidewalks, Buildings, Roofs, Facades, Signs, Props, Spawn}
	          Workspace/Manual                                                       never changed, only read
	Item keys: k kind, n name, x y z center, w h d size along the part's own X, Y, Z, r yaw in degrees (counterclockwise from
	          east, seen from above); buildings s source, e height in m, q fit ratio, f floors, b height basis, a floors basis,
	          c wall color name, v review flags. U5 (optional, only when they differ from the defaults): i owner building id,
	          p shape (Wedge, CornerWedge, Cylinder standing with size = height, diameter, diameter, Ball), m material,
	          c color name of any kind (its RGB is in looks.walls), o ink color name, t sign text, u="LR" two-sided sign,
	          md sign MaxDistance, j reflectance, g 0/1 cast shadow, l 0/1 collide.
	Rules:    aidlc-docs/construction/u2-studio-builder/functional-design/business-rules.md (BR-2.8, BR-6, BR-7.5)
	          aidlc-docs/construction/u5-details/functional-design/business-rules.md (BR-10.5, BR-12.5, BR-14.1, BR-14.3 to BR-14.5)
]]

local Builder = {}

-- Set this to build somewhere other than Workspace (used to test inside a scratch folder).
Builder.root = nil

local FOLDER_OF = {
	ground = "Ground", road = "Roads", path = "Paths", sidewalk = "Sidewalks", building = "Buildings",
	roof = "Roofs", facade = "Facades", sign = "Signs", prop = "Props", spawn = "Spawn",
}
-- (casts a shadow, collides) by kind; an item sends g / l only when it differs (U5 BR-14.1)
local KIND_DEFAULTS = {
	ground = { true, true }, road = { true, true }, path = { true, true }, sidewalk = { true, true }, building = { true, true },
	roof = { true, true }, facade = { false, false }, sign = { false, false }, prop = { false, true }, spawn = { false, false },
}
local SHAPES = { Block = Enum.PartType.Block, Wedge = Enum.PartType.Wedge, CornerWedge = Enum.PartType.CornerWedge,
	Cylinder = Enum.PartType.Cylinder, Ball = Enum.PartType.Ball }

local function rootOf(root)
	return root or Builder.root or workspace
end

local function checkCell(cellId)
	-- an H3 index at resolution 9 is 15 hex digits; anything else must never reach a Destroy call
	if type(cellId) ~= "string" or #cellId ~= 15 or not string.match(cellId, "^%x+$") then
		error("MapBuilder: not an H3 cell id: " .. tostring(cellId), 3)
	end
end

local function ensure(parent, name)
	local child = parent:FindFirstChild(name)
	if not child then
		child = Instance.new("Folder")
		child.Name = name
		child.Parent = parent
	end
	return child
end

local function cellFolder(cellId, root)
	local auto = rootOf(root):FindFirstChild("Auto")
	local cell = auto and auto:FindFirstChild(cellId)
	if not cell then
		error("MapBuilder: no Auto/" .. cellId .. ", call begin first", 3)
	end
	return cell
end

-- ids of buildings someone built by hand: a part or model under Manual with a BuildingId attribute
local function manualIds(root)
	local ids = {}
	for _, d in ipairs(ensure(rootOf(root), "Manual"):GetDescendants()) do
		local id = d:GetAttribute("BuildingId")
		if id ~= nil then
			ids[id] = true
		end
	end
	return ids
end

-- Starts a cell: makes Auto and Manual if missing, throws away Auto/<cell id> and makes it again, empty.
function Builder.begin(cellId, root)
	checkCell(cellId)
	local base = rootOf(root)
	local auto = ensure(base, "Auto")
	ensure(base, "Manual")
	local old = auto:FindFirstChild(cellId)
	if old then
		old:Destroy()
	end
	local cell = Instance.new("Folder")
	cell.Name = cellId
	cell:SetAttribute("BuildComplete", false)
	cell:SetAttribute("Created", 0)
	cell:SetAttribute("SkippedManual", 0)
	for kind, name in pairs(FOLDER_OF) do
		ensure(cell, name)
		cell:SetAttribute("Skipped_" .. kind, 0)
	end
	cell.Parent = auto
end

local function colorOf(looks, look, name)
	local c = name and looks.walls and looks.walls[name]
	if c then
		return Color3.fromRGB(c[1], c[2], c[3])
	end
	return Color3.fromRGB(look[2], look[3], look[4])
end

local function addSignGui(part, it, looks, face)
	local gui = Instance.new("SurfaceGui")
	gui.Face = face
	gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	gui.PixelsPerStud = 50
	gui.LightInfluence = 1
	gui.AlwaysOnTop = false
	gui.MaxDistance = it.md or 200
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.TextScaled = true
	label.TextColor3 = colorOf(looks, { "", 20, 20, 20 }, it.o)
	label.FontFace = Font.fromEnum(Enum.Font.SourceSansBold)
	label.Text = it.t -- data only: the text never becomes code
	label.Parent = gui
	gui.Parent = part
end

-- Makes the parts of one chunk. looks[kind] = {material name, r, g, b}; looks.walls[color name] = {r, g, b} for every color
-- name the chunk uses. Returns what this chunk made and skipped.
function Builder.add(cellId, items, looks, root)
	checkCell(cellId)
	local cell = cellFolder(cellId, root)
	local manual = manualIds(root)
	local staged, skipped = {}, {}
	for _, it in ipairs(items) do
		local folder = FOLDER_OF[it.k]
		local look = looks[it.k]
		if not folder or not look then
			error("MapBuilder: unknown kind " .. tostring(it.k), 2)
		end
		local owner = it.i or (it.k == "building" and it.n) or nil
		if owner and manual[owner] then
			skipped[it.k] = (skipped[it.k] or 0) + 1 -- a hand-made building wins, with everything it owns (BR-2.8, U5 BR-14.4)
		else
			local part = Instance.new(it.k == "spawn" and "SpawnLocation" or "Part")
			part.Name = it.n
			part.Anchored = true
			part.TopSurface = Enum.SurfaceType.Smooth
			part.BottomSurface = Enum.SurfaceType.Smooth
			if it.p then
				local shape = SHAPES[it.p]
				if not shape then
					error("MapBuilder: unknown shape " .. tostring(it.p), 2)
				end
				part.Shape = shape
			end
			part.Size = Vector3.new(it.w, it.h, it.d)
			local cf = CFrame.new(it.x, it.y, it.z) * CFrame.Angles(0, math.rad(it.r), 0)
			if it.p == "Cylinder" then
				cf = cf * CFrame.Angles(0, 0, math.rad(90)) -- a cylinder's length runs along X: stand it up (U5 BR-14.3)
			end
			part.CFrame = cf
			part.Material = Enum.Material[it.m or look[1]]
			part.Color = colorOf(looks, look, it.c)
			if it.j then
				part.Reflectance = it.j
			end
			local defaults = KIND_DEFAULTS[it.k]
			local shadow = if it.g ~= nil then it.g == 1 else defaults[1]
			local collide = if it.l ~= nil then it.l == 1 else defaults[2]
			part.CastShadow = shadow
			if not collide then
				part.CanCollide = false
				part.CanTouch = false
				part.CanQuery = false
			end
			if owner then
				part:SetAttribute("BuildingId", owner)
			end
			if it.k == "building" then
				part:SetAttribute("CellId", cellId)
				part:SetAttribute("Source", it.s)
				part:SetAttribute("HeightM", it.e)
				part:SetAttribute("FitRatio", it.q)
				if it.f then
					part:SetAttribute("Floors", it.f)
				end
				for key, attr in pairs({ b = "HeightBasis", a = "FloorsBasis", c = "WallColor", v = "Review" }) do
					if it[key] ~= nil then
						part:SetAttribute(attr, it[key])
					end
				end
			elseif it.k == "sign" then
				if it.u == "LR" then
					addSignGui(part, it, looks, Enum.NormalId.Left)
					addSignGui(part, it, looks, Enum.NormalId.Right)
				else
					addSignGui(part, it, looks, Enum.NormalId.Front)
				end
			elseif it.k == "spawn" then
				part.Transparency = 1
				part.CanCollide = false
				part.Neutral = true
				part.Duration = 0
				part.AllowTeamChangeOnTouch = false
			end
			table.insert(staged, { part = part, folder = cell[folder] })
		end
	end
	for _, s in ipairs(staged) do
		s.part.Parent = s.folder
	end
	local skippedTotal = 0
	for kind, n in pairs(skipped) do
		cell:SetAttribute("Skipped_" .. kind, cell:GetAttribute("Skipped_" .. kind) + n)
		skippedTotal += n
	end
	cell:SetAttribute("Created", cell:GetAttribute("Created") + #staged)
	cell:SetAttribute("SkippedManual", cell:GetAttribute("SkippedManual") + skippedTotal)
	return { created = #staged, skipped_manual = skippedTotal }
end

local function counts(cell)
	local out = {}
	for _, folder in ipairs(cell:GetChildren()) do
		out[folder.Name] = #folder:GetChildren()
	end
	return out
end

-- Ends a cell: marks it complete and reports the totals of all chunks.
function Builder.finish(cellId, root)
	checkCell(cellId)
	local cell = cellFolder(cellId, root)
	cell:SetAttribute("BuildComplete", true)
	return {
		created = cell:GetAttribute("Created"),
		skipped_manual = cell:GetAttribute("SkippedManual"),
		folders = counts(cell),
	}
end

-- Checks a finished cell against the manifest (S-1, U5 BR-14.5) and reads back some parts (S-2).
-- expected: the manifest's counts table (items_ground, items_road, ..., labels). sampleNames: part names to read back.
-- buildingIds (optional): the manifest's building_ids; Manual BuildingId values that are not in it are reported (BR-12.5).
function Builder.verify(cellId, expected, sampleNames, buildingIds, root)
	checkCell(cellId)
	local cell = cellFolder(cellId, root)
	local found, problems = counts(cell), {}
	if cell:GetAttribute("BuildComplete") ~= true then
		table.insert(problems, "BuildComplete is not true")
	end
	local skipped = cell:GetAttribute("SkippedManual")
	for kind, folderName in pairs(FOLDER_OF) do
		local want = expected["items_" .. kind]
		local skippedKind = cell:GetAttribute("Skipped_" .. kind) or 0
		local have = (found[folderName] or 0) + skippedKind
		if want ~= have then
			table.insert(problems, string.format("%s: manifest %s, Studio %d (+%d skipped)", kind, tostring(want), found[folderName] or 0, skippedKind))
		end
	end
	if expected.labels ~= nil then
		local labels = 0
		for _, d in ipairs(cell.Signs:GetDescendants()) do
			if d:IsA("TextLabel") then
				labels += 1
			end
		end
		local skippedSigns = cell:GetAttribute("Skipped_sign") or 0
		if labels ~= expected.labels and skippedSigns == 0 then
			table.insert(problems, string.format("labels: manifest %d, Studio %d", expected.labels, labels))
		end
	end
	local unknownManual = {}
	if buildingIds then
		local known = {}
		for _, id in ipairs(buildingIds) do
			known[id] = true
		end
		for id in pairs(manualIds(root)) do
			if not known[id] then
				table.insert(unknownManual, id)
			end
		end
		table.sort(unknownManual)
	end
	local samples = {}
	for _, name in ipairs(sampleNames or {}) do
		local part
		for _, folder in ipairs(cell:GetChildren()) do
			part = part or folder:FindFirstChild(name)
		end
		if part then
			local right = part.CFrame.RightVector
			samples[name] = {
				position = { part.Position.X, part.Position.Y, part.Position.Z },
				size = { part.Size.X, part.Size.Y, part.Size.Z },
				right = { right.X, right.Y, right.Z },
			}
		else
			samples[name] = false
		end
	end
	return { ok = #problems == 0, problems = problems, folders = found, skipped_manual = skipped, samples = samples, unknown_manual = unknownManual }
end

return Builder
