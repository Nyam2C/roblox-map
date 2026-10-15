--[[
	MapBuilder: builds one cell of the map in Studio from the chunk files that src/build_luau.py writes.
	Source of truth is studio/ServerStorage/MapBuilder.luau in the repository; Claude puts it here through the Studio MCP
	(replace the module instance: new ModuleScript with the Source, Destroy the old one, because require caches per instance).

	It does no geometry. Every position, size and angle arrives computed (see layout.py and layout_details.py); this module
	only makes parts. It never runs received text as code (no loadstring) and only ever destroys Workspace/Auto/<cell id>.

	Layout:   Workspace/Auto/<cell id>/Base (Model, Persistent)/{Ground, Roads, Paths, Sidewalks}
	          Workspace/Auto/<cell id>/Buildings/<building id> (Model, Atomic): every part a building owns (box, roof, facade,
	          sign, yard)
	          Workspace/Auto/<cell id>/{Props, Spawn}                                 street props, spawn
	          Workspace/Manual                                                       never changed, only read
	          Counts per kind are cell attributes Made_<kind> (verify reads them). Models: a building streams whole (U7 E).
	Item keys: k kind, n name, x y z center, w h d size along the part's own X, Y, Z, r yaw in degrees (counterclockwise from
	          east, seen from above); buildings s source, e height in m, q fit ratio, f floors, b height basis, a floors basis,
	          c wall color name, v review flags. U5 (optional, only when they differ from the defaults): i owner building id,
	          p shape (Wedge, CornerWedge, Cylinder standing with size = height, diameter, diameter, Ball), m material,
	          c color name of any kind (its RGB is in looks.walls), o ink color name, t sign text, u="LR" two-sided sign,
	          md sign MaxDistance, im sign image asset id (SI-7), j reflectance, g 0/1 cast shadow, l 0/1 collide.
	          U7: kt kit mesh, a clone of ServerStorage/Kits/<kt> (a MeshPart) instead of a new Part.
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
local BASE_KINDS = { ground = true, road = true, path = true, sidewalk = true } -- in the Persistent Base model (BR-I15.3)
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
	if Builder.manualSkip then -- CellStreamer (2026-10-15): the hand-made places are built by cell, so the ids come as a list
		return Builder.manualSkip
	end
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
	local ground = Instance.new("Model")
	ground.Name = "Base"
	ground.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	ground.Parent = cell
	for kind, name in pairs(FOLDER_OF) do
		if BASE_KINDS[kind] then
			ensure(ground, name)
		elseif kind == "prop" or kind == "spawn" or kind == "building" then
			ensure(cell, name)
		end
		cell:SetAttribute("Skipped_" .. kind, 0)
		cell:SetAttribute("Made_" .. kind, 0)
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
	-- text tops out at 100 px, so a tall plate (an apartment block number) gets fewer pixels per stud to fill it
	gui.PixelsPerStud = part.Size.Y > 6 and 110 / part.Size.Y or 50
	-- a tall narrow face (a vertical shop sign) stacks the letters one per line
	local across = (face == Enum.NormalId.Left or face == Enum.NormalId.Right) and part.Size.Z or part.Size.X
	local text = it.t
	if part.Size.Y > 2.5 * across and not it.im then
		local chars = {}
		for _, code in utf8.codes(it.t) do
			table.insert(chars, utf8.char(code))
		end
		text = table.concat(chars, "\n")
		gui.PixelsPerStud = math.min(50, 95 / math.min(across, part.Size.Y / math.max(1, #chars)))
	end
	gui.LightInfluence = 1
	gui.AlwaysOnTop = false
	gui.MaxDistance = it.md or 200
	local asset = tonumber(it.im)
	if asset and asset > 0 and asset == math.floor(asset) then
		-- a generated sign image (SI-7): the asset id is a number, never text, and the text stays in `t` as the fallback
		local image = Instance.new("ImageLabel")
		image.Size = UDim2.fromScale(1, 1)
		image.BackgroundTransparency = 1
		image.ScaleType = Enum.ScaleType.Stretch
		image.Image = "rbxassetid://" .. string.format("%d", asset)
		image.Parent = gui
	else
		local label = Instance.new("TextLabel")
		label.Size = UDim2.fromScale(1, 1)
		label.BackgroundTransparency = 1
		label.TextScaled = true
		label.TextColor3 = colorOf(looks, { "", 20, 20, 20 }, it.o)
		label.FontFace = Font.fromEnum(Enum.Font.SourceSansBold)
		label.Text = text -- data only: the text never becomes code
		label.Parent = gui
	end
	gui.Parent = part
end

-- Makes the parts of one chunk. looks[kind] = {material name, r, g, b}; looks.walls[color name] = {r, g, b} for every color
-- name the chunk uses. Returns what this chunk made and skipped.
function Builder.add(cellId, items, looks, root)
	checkCell(cellId)
	local cell = cellFolder(cellId, root)
	local manual = manualIds(root)
	local staged, skipped, made = {}, {}, {}
	local function holder(it, owner)
		if owner then
			local model = cell.Buildings:FindFirstChild(owner)
			if not model then
				model = Instance.new("Model")
				model.Name = owner
				model.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
				-- a stand-in mesh beyond the streaming radius: the skyline stays (architecture 6.2). Only Studio (plugin) code may set it;
				-- a game script (CellStreamer, 2026-10-15) skips it and the far view is the lite cells
				pcall(function()
					model.LevelOfDetail = Enum.ModelLevelOfDetail.StreamingMesh
				end)
				model.Parent = cell.Buildings
			end
			return model
		end
		if BASE_KINDS[it.k] then
			return cell.Base[FOLDER_OF[it.k]]
		end
		return cell:FindFirstChild(FOLDER_OF[it.k]) or ensure(cell, FOLDER_OF[it.k])
	end
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
			local part
			if it.kt then -- U7 H: a kit mesh, cloned from ServerStorage/Kits (installed once, cycle-build 7)
				local kitsFolder = game:GetService("ServerStorage"):FindFirstChild("Kits")
				local template = kitsFolder and kitsFolder:FindFirstChild(it.kt)
				if not template then
					error("MapBuilder: kit " .. tostring(it.kt) .. " is not in ServerStorage/Kits", 2)
				end
				part = template:Clone()
			else
				part = Instance.new(it.k == "spawn" and "SpawnLocation" or "Part")
			end
			part.Name = it.n
			part.Anchored = true
			part.TopSurface = Enum.SurfaceType.Smooth
			part.BottomSurface = Enum.SurfaceType.Smooth
			if it.p and not it.kt then
				local shape = SHAPES[it.p]
				if not shape then
					error("MapBuilder: unknown shape " .. tostring(it.p), 2)
				end
				part.Shape = shape
			end
			part.Size = Vector3.new(it.w, it.h, it.d)
			local cf = CFrame.new(it.x, it.y, it.z) * CFrame.Angles(0, math.rad(it.r), 0)
			if it.ax or it.az then -- a flat piece lying on sloping ground (terrain.py, 2026-10-15)
				cf = cf * CFrame.Angles(math.rad(it.ax or 0), 0, math.rad(it.az or 0))
			end
			if it.p == "Cylinder" then
				cf = cf * CFrame.Angles(0, 0, math.rad(90)) -- a cylinder's length runs along X: stand it up (U5 BR-14.3)
			end
			part.CFrame = cf
			part.Material = Enum.Material[it.m or look[1]]
			part.Color = colorOf(looks, look, it.c)
			if it.j then
				part.Reflectance = it.j
			end
			if it.tr then
				part.Transparency = it.tr -- glass you see through (subway entrance walls, 2026-10-14)
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
			table.insert(staged, { part = part, folder = holder(it, owner) })
			made[it.k] = (made[it.k] or 0) + 1
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
	for kind, n in pairs(made) do
		cell:SetAttribute("Made_" .. kind, (cell:GetAttribute("Made_" .. kind) or 0) + n)
	end
	cell:SetAttribute("Created", cell:GetAttribute("Created") + #staged)
	cell:SetAttribute("SkippedManual", cell:GetAttribute("SkippedManual") + skippedTotal)
	return { created = #staged, skipped_manual = skippedTotal }
end

-- parts made per kind (by folder name, as before), from the Made_<kind> attributes
local function counts(cell)
	local out = {}
	for kind, name in pairs(FOLDER_OF) do
		out[name] = cell:GetAttribute("Made_" .. kind) or 0
	end
	return out
end

local function partCount(cell)
	local n = 0
	for _, d in ipairs(cell:GetDescendants()) do
		if d:IsA("BasePart") then
			n += 1
		end
	end
	return n
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
	local parts = partCount(cell)
	if parts ~= cell:GetAttribute("Created") then
		table.insert(problems, string.format("parts in the cell %d, made %d", parts, cell:GetAttribute("Created")))
	end
	local skipped = cell:GetAttribute("SkippedManual")
	for kind, folderName in pairs(FOLDER_OF) do
		local want = expected["items_" .. kind] or 0
		local skippedKind = cell:GetAttribute("Skipped_" .. kind) or 0
		local have = (found[folderName] or 0) + skippedKind
		if want ~= have then
			table.insert(problems, string.format("%s: manifest %s, Studio %d (+%d skipped)", kind, tostring(want), found[folderName] or 0, skippedKind))
		end
	end
	if expected.labels ~= nil then
		local labels = 0
		for _, d in ipairs(cell:GetDescendants()) do
			if d:IsA("TextLabel") or d:IsA("ImageLabel") then
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
		local part = cell:FindFirstChild(name, true)
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

-- Fills Terrain to the ground heights of a cell (chunks.json "terrain": x0, z0, step, nx, nz, h row-major by z), 2026-10-15.
-- The surface sits SINK studs under the heights so the road and sidewalk parts on them stay on top: measured (2026-10-15) the terrain
-- surface stands 1 to 2.5 studs above the written occupancy (it steps by 2 studs), so 3 keeps it 0.5 to 2 under the parts. Voxels
-- below are Concrete in the old slab colour, above is Air. Neighbouring cells write the same heights where they overlap.
local VOXEL, SINK, DEPTH = 4, 3, 16
function Builder.terrain(land)
	local T = workspace.Terrain
	T:SetMaterialColor(Enum.Material.Concrete, Color3.fromRGB(130, 128, 125))
	local nx, nz, step, hs = land.nx, land.nz, land.step, land.h
	local function h(x, z)
		local fx = math.clamp((x - land.x0) / step, 0, nx - 1)
		local fz = math.clamp((z - land.z0) / step, 0, nz - 1)
		local i, j = math.min(math.floor(fx), nx - 2), math.min(math.floor(fz), nz - 2)
		local tx, tz = fx - i, fz - j
		local a, b = hs[j * nx + i + 1], hs[j * nx + i + 2]
		local c, d = hs[(j + 1) * nx + i + 1], hs[(j + 1) * nx + i + 2]
		return (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz
	end
	local lo, hi = math.huge, -math.huge
	for _, v in hs do
		lo, hi = math.min(lo, v), math.max(hi, v)
	end
	local x0 = math.floor(land.x0 / VOXEL) * VOXEL
	local x1 = math.ceil((land.x0 + (nx - 1) * step) / VOXEL) * VOXEL
	local z0 = math.floor(land.z0 / VOXEL) * VOXEL
	local z1 = math.ceil((land.z0 + (nz - 1) * step) / VOXEL) * VOXEL
	local y0 = math.floor((lo - SINK - DEPTH) / VOXEL) * VOXEL
	local y1 = math.ceil((hi + VOXEL) / VOXEL) * VOXEL
	local cx, cy = (x1 - x0) / VOXEL, (y1 - y0) / VOXEL
	local written = 0
	local ROWS = 24
	for zs = z0, z1 - VOXEL, ROWS * VOXEL do
		local ze = math.min(zs + ROWS * VOXEL, z1)
		local cz = (ze - zs) / VOXEL
		local mats, occs = table.create(cx), table.create(cx)
		for ix = 1, cx do
			local mx, ox = table.create(cy), table.create(cy)
			for iy = 1, cy do
				mx[iy], ox[iy] = table.create(cz), table.create(cz)
			end
			local x = x0 + (ix - 0.5) * VOXEL
			for iz = 1, cz do
				local top = h(x, zs + (iz - 0.5) * VOXEL) - SINK
				for iy = 1, cy do
					local bottom = y0 + (iy - 1) * VOXEL
					local occ = math.clamp((top - bottom) / VOXEL, 0, 1)
					mx[iy][iz] = occ > 0 and Enum.Material.Concrete or Enum.Material.Air
					ox[iy][iz] = occ
				end
			end
			mats[ix], occs[ix] = mx, ox
		end
		T:WriteVoxels(Region3.new(Vector3.new(x0, y0, zs), Vector3.new(x1, y1, ze)), VOXEL, mats, occs)
		written += cx * cy * cz
		task.wait()
	end
	return { voxels = written, low = lo, high = hi }
end

-- Moves the hand-made places (Workspace/Manual) onto the ground (2026-10-15). A Model (a tower, a pavilion, a dong) moves as one by
-- the lowest ground under its footing parts; a loose part (plaza pavers, park tiles) by the ground at its middle. The offset applied is kept
-- in the attribute GroundLift, so running this again (or with new heights) moves only by the difference.
local FOOT = 2 -- studs above a model's lowest bottom that still count as its footing (a step, a plinth's edge)
function Builder.settleManual(land, root)
	local base = rootOf(root)
	local manual = base:FindFirstChild("Manual")
	if not manual then
		return { moved = 0 }
	end
	local nx, nz, step, hs = land.nx, land.nz, land.step, land.h
	local function h(x, z)
		local fx = math.clamp((x - land.x0) / step, 0, nx - 1)
		local fz = math.clamp((z - land.z0) / step, 0, nz - 1)
		local i, j = math.min(math.floor(fx), nx - 2), math.min(math.floor(fz), nz - 2)
		local tx, tz = fx - i, fz - j
		local a, b = hs[j * nx + i + 1], hs[j * nx + i + 2]
		local c, d = hs[(j + 1) * nx + i + 1], hs[(j + 1) * nx + i + 2]
		return (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz
	end
	local moved = 0
	local function move(obj, want)
		local had = obj:GetAttribute("GroundLift") or 0
		local dy = want - had
		if math.abs(dy) > 1e-3 then
			if obj:IsA("Model") then
				obj:PivotTo(obj:GetPivot() + Vector3.new(0, dy, 0))
			else
				obj.CFrame += Vector3.new(0, dy, 0)
			end
			moved += 1
		end
		obj:SetAttribute("GroundLift", want)
	end
	local function walk(container)
		for _, child in container:GetChildren() do
			if child:IsA("Model") then
				-- a building stands on the lowest ground under the bottom corners of its footing parts (those within FOOT of the
				-- model's lowest bottom), like terrain.lift's boxes; the bounding box's corners fell outside long or L-shaped
				-- buildings onto lower roads (2026-10-15, gis:11796845, 11180532). A flat ground piece (Settle = "high", e.g. a court
				-- on a deep slab) on its highest.
				local high = child:GetAttribute("Settle") == "high"
				local feet, low = {}, math.huge
				for _, p in child:GetDescendants() do
					if p:IsA("BasePart") then
						local pts = {}
						for _, d in ipairs({ { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, 1 }, { 0, 0 } }) do
							table.insert(pts, p.CFrame:PointToWorldSpace(Vector3.new(d[1] * p.Size.X / 2, -p.Size.Y / 2, d[2] * p.Size.Z / 2)))
						end
						local y = math.min(pts[1].Y, pts[2].Y, pts[3].Y, pts[4].Y)
						table.insert(feet, { y, pts })
						low = math.min(low, y)
					end
				end
				local pick = high and -math.huge or math.huge
				for _, f in feet do
					if f[1] <= low + FOOT then
						for _, q in f[2] do
							pick = high and math.max(pick, h(q.X, q.Z)) or math.min(pick, h(q.X, q.Z))
						end
					end
				end
				if #feet > 0 then
					move(child, pick)
				end
			elseif child:IsA("BasePart") then
				move(child, h(child.Position.X, child.Position.Z))
			elseif child:IsA("Folder") then
				walk(child)
			end
		end
	end
	walk(manual)
	return { moved = moved }
end

return Builder
