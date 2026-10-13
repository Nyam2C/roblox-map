--[[
	MapBuilder: builds one cell of the map in Studio from the chunk files that src/build_luau.py writes.
	Source of truth is this file; Claude puts it into ServerStorage/MapBuilder (a ModuleScript) through the Studio MCP.

	It does no geometry. Every position, size and angle arrives computed (see layout.py); this module only makes parts.
	It never runs received text as code (no loadstring) and only ever destroys Workspace/Auto/<cell id>.

	Layout:   Workspace/Auto/<cell id>/{Ground, Roads, Paths, Sidewalks, Buildings, Spawn}    rebuilt on every run
	          Workspace/Manual                                                                  never changed, only read
	Item keys: k kind, n name, x y z center, w h d size along the part's own X, Y, Z, r yaw in degrees (counterclockwise from
	          east, seen from above), and for buildings s source, e height in m, q fit ratio, f floors.
	Rules:    aidlc-docs/construction/u2-studio-builder/functional-design/business-rules.md (BR-2.8, BR-6, BR-7.5)
]]

local Builder = {}

-- Set this to build somewhere other than Workspace (used to test inside a scratch folder).
Builder.root = nil

local FOLDER_OF = {
	ground = "Ground", road = "Roads", path = "Paths", sidewalk = "Sidewalks", building = "Buildings", spawn = "Spawn",
}

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
	for _, name in pairs(FOLDER_OF) do
		ensure(cell, name)
	end
	cell.Parent = auto
end

-- Makes the parts of one chunk. looks[kind] = {material name, r, g, b}. Returns what this chunk made and skipped.
function Builder.add(cellId, items, looks, root)
	checkCell(cellId)
	local cell = cellFolder(cellId, root)
	local manual = manualIds(root)
	local staged, skipped = {}, 0
	for _, it in ipairs(items) do
		local folder = FOLDER_OF[it.k]
		local look = looks[it.k]
		if not folder or not look then
			error("MapBuilder: unknown kind " .. tostring(it.k), 2)
		end
		if it.k == "building" and manual[it.n] then
			skipped += 1 -- a hand-made building wins (BR-2.8)
		else
			local part = Instance.new(it.k == "spawn" and "SpawnLocation" or "Part")
			part.Name = it.n
			part.Anchored = true
			part.TopSurface = Enum.SurfaceType.Smooth
			part.BottomSurface = Enum.SurfaceType.Smooth
			part.Size = Vector3.new(it.w, it.h, it.d)
			part.CFrame = CFrame.new(it.x, it.y, it.z) * CFrame.Angles(0, math.rad(it.r), 0)
			part.Material = Enum.Material[look[1]]
			part.Color = Color3.fromRGB(look[2], look[3], look[4])
			if it.k == "building" then
				part:SetAttribute("BuildingId", it.n)
				part:SetAttribute("CellId", cellId)
				part:SetAttribute("Source", it.s)
				part:SetAttribute("HeightM", it.e)
				part:SetAttribute("FitRatio", it.q)
				if it.f then
					part:SetAttribute("Floors", it.f)
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
	cell:SetAttribute("Created", cell:GetAttribute("Created") + #staged)
	cell:SetAttribute("SkippedManual", cell:GetAttribute("SkippedManual") + skipped)
	return { created = #staged, skipped_manual = skipped }
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

-- Checks a finished cell against the manifest's counts (S-1) and reads back some parts (S-2).
-- expected: the manifest's counts table (items_ground, items_road, ...). sampleNames: part names to read back.
function Builder.verify(cellId, expected, sampleNames, root)
	checkCell(cellId)
	local cell = cellFolder(cellId, root)
	local found, problems = counts(cell), {}
	if cell:GetAttribute("BuildComplete") ~= true then
		table.insert(problems, "BuildComplete is not true")
	end
	local skipped = cell:GetAttribute("SkippedManual")
	for kind, folderName in pairs(FOLDER_OF) do
		local want = expected["items_" .. kind]
		local have = (found[folderName] or 0) + (kind == "building" and skipped or 0)
		if want ~= have then
			table.insert(problems, string.format("%s: manifest %s, Studio %d (+%d skipped)", kind, tostring(want), found[folderName] or 0, kind == "building" and skipped or 0))
		end
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
	return { ok = #problems == 0, problems = problems, folders = found, skipped_manual = skipped, samples = samples }
end

return Builder
