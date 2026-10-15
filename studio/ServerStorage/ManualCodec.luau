-- The hand-made places as data (2026-10-15): studio/install/cell-data.luau writes Workspace/Manual into ServerStorage/CellData by
-- cell, and ServerScriptService/CellStreamer builds a cell's share when it builds the cell. ModuleScript in ServerStorage.
--
-- A unit is a Model or a part whose ancestors up to Manual are folders; it goes to the cell nearest its centre, with the folder
-- path to rebuild. Only the classes and properties below are kept (Workspace/Manual held nothing else on 2026-10-15); a kit
-- MeshPart (attribute Kit) is cloned from ServerStorage/Kits, since a game script cannot set a MeshId.
local Codec = {}

local BASE_PART = { "Name", "Size", "CFrame", "Color", "Material", "Transparency", "Reflectance", "Anchored", "CanCollide",
	"CanTouch", "CanQuery", "CastShadow" }
local PROPS = {
	Part = { "Shape", "TopSurface", "BottomSurface" },
	MeshPart = {},
	Model = { "Name", "ModelStreamingMode" },
	Folder = { "Name" },
	Configuration = { "Name" },
	SurfaceGui = { "Name", "Face", "SizingMode", "PixelsPerStud", "CanvasSize", "LightInfluence", "AlwaysOnTop", "MaxDistance",
		"ZOffset", "Brightness" },
	TextLabel = { "Name", "Text", "TextColor3", "TextSize", "FontFace", "TextScaled", "TextWrapped", "Size", "Position",
		"AnchorPoint", "Rotation", "BackgroundTransparency", "BackgroundColor3", "TextStrokeTransparency", "TextStrokeColor3",
		"TextXAlignment", "TextYAlignment", "BorderSizePixel", "TextTransparency", "RichText" },
	PointLight = { "Name", "Brightness", "Range", "Color", "Shadows", "Enabled" },
}
for _, cls in ipairs({ "Part", "MeshPart" }) do
	table.move(BASE_PART, 1, #BASE_PART, #PROPS[cls] + 1, PROPS[cls])
end
Codec.PROPS = PROPS

local function enc(v)
	local t = typeof(v)
	if t == "Vector3" then
		return { "v3", v.X, v.Y, v.Z }
	elseif t == "CFrame" then
		return { "cf", v:GetComponents() }
	elseif t == "Color3" then
		return { "c3", v.R, v.G, v.B }
	elseif t == "EnumItem" then
		return { "e", tostring(v.EnumType), v.Name }
	elseif t == "UDim2" then
		return { "u2", v.X.Scale, v.X.Offset, v.Y.Scale, v.Y.Offset }
	elseif t == "Vector2" then
		return { "v2", v.X, v.Y }
	elseif t == "Font" then
		return { "f", v.Family, v.Weight.Name, v.Style.Name }
	end
	return v -- string, number, boolean
end

local function dec(v)
	if type(v) ~= "table" then
		return v
	end
	local k = v[1]
	if k == "v3" then
		return Vector3.new(v[2], v[3], v[4])
	elseif k == "cf" then
		return CFrame.new(table.unpack(v, 2, 13))
	elseif k == "c3" then
		return Color3.new(v[2], v[3], v[4])
	elseif k == "e" then
		return Enum[v[2]][v[3]]
	elseif k == "u2" then
		return UDim2.new(v[2], v[3], v[4], v[5])
	elseif k == "v2" then
		return Vector2.new(v[2], v[3])
	elseif k == "f" then
		return Font.new(v[2], Enum.FontWeight[v[3]], Enum.FontStyle[v[4]])
	end
	return nil
end

function Codec.encode(inst)
	local props = PROPS[inst.ClassName]
	if not props then
		return nil
	end
	local node = { c = inst.ClassName, p = {}, a = {}, k = {} }
	for _, name in ipairs(props) do
		local ok, v = pcall(function()
			return inst[name]
		end)
		if ok then
			node.p[name] = enc(v)
		end
	end
	for name, v in pairs(inst:GetAttributes()) do
		node.a[name] = enc(v)
	end
	for _, c in ipairs(inst:GetChildren()) do
		local n = Codec.encode(c)
		if n then
			table.insert(node.k, n)
		end
	end
	return node
end

-- builds a node (and its children) unparented; kits: ServerStorage/Kits
function Codec.decode(node, kits)
	local inst
	local kit = node.a.Kit and kits and kits:FindFirstChild(node.a.Kit)
	if node.c == "MeshPart" then
		inst = kit and kit:Clone() or Instance.new("Part")
	else
		inst = Instance.new(node.c)
	end
	for name, v in pairs(node.p) do
		pcall(function()
			inst[name] = dec(v)
		end)
	end
	for name, v in pairs(node.a) do
		inst:SetAttribute(name, dec(v))
	end
	for _, k in ipairs(node.k) do
		Codec.decode(k, kits).Parent = inst
	end
	return inst
end

-- the units of a Manual tree: { path = {folder names below Manual}, inst = Model or BasePart }
function Codec.units(manual, keep)
	local out = {}
	local function walk(f, path)
		for _, c in ipairs(f:GetChildren()) do
			if c:IsA("Model") or c:IsA("BasePart") then
				table.insert(out, { path = path, inst = c })
			elseif c:IsA("Folder") and not (#path == 0 and keep[c.Name]) then
				local p = table.clone(path)
				table.insert(p, c.Name)
				walk(c, p)
			end
		end
	end
	walk(manual, {})
	return out
end

function Codec.centre(inst)
	if inst:IsA("BasePart") then
		return inst.Position
	end
	return (inst:GetBoundingBox()).Position
end

Codec.KEEP = { Landmark = true } -- places that stay in Workspace/Manual (the landmark towers are the skyline)
local PART = 190000 -- a StringValue takes under 200,000 characters

-- base64 zstd JSON in StringValues <prefix>1, <prefix>2, ... of a folder; nil when there are none
function Codec.read(folder, prefix)
	local HS, ES = game:GetService("HttpService"), game:GetService("EncodingService")
	local parts, k = {}, 1
	while folder:FindFirstChild(prefix .. k) do
		table.insert(parts, folder[prefix .. k].Value)
		k += 1
	end
	if #parts == 0 then
		return nil
	end
	local raw = ES:DecompressBuffer(ES:Base64Decode(buffer.fromstring(table.concat(parts))), Enum.CompressionAlgorithm.Zstd)
	return HS:JSONDecode(buffer.tostring(raw))
end

function Codec.write(folder, prefix, value)
	local HS, ES = game:GetService("HttpService"), game:GetService("EncodingService")
	for _, v in ipairs(folder:GetChildren()) do
		if v:IsA("StringValue") and v.Name:match("^" .. prefix .. "%d+$") then
			v:Destroy()
		end
	end
	if value == nil then
		return 0
	end
	local packed = buffer.tostring(ES:Base64Encode(ES:CompressBuffer(buffer.fromstring(HS:JSONEncode(value)),
		Enum.CompressionAlgorithm.Zstd, 9)))
	for k = 1, math.ceil(#packed / PART) do
		local v = Instance.new("StringValue")
		v.Name = prefix .. k
		v.Value = string.sub(packed, (k - 1) * PART + 1, k * PART)
		v.Parent = folder
	end
	return #packed
end

-- (Edit) the hand-made places of the cells built in Edit (Workspace/Auto/<cell> present) into CellData/<cell>/m1, ...: each unit to
-- the cell nearest its centre. A cell not built in Edit (packed) keeps its data: its places are not in Workspace/Manual to write.
-- ManualIds keeps the ids it had and adds the ones seen.
function Codec.export(data, manual, auto)
	local present, cells = {}, {}
	for _, c in ipairs(auto:GetChildren()) do
		present[c.Name] = true
	end
	for _, f in ipairs(data:GetChildren()) do
		if f:IsA("Folder") then
			table.insert(cells, { f, f:GetAttribute("x"), f:GetAttribute("z") })
		end
	end
	local ids = {}
	for _, b in ipairs(string.split(data:GetAttribute("ManualIds") or "", ",")) do
		if b ~= "" then
			ids[b] = true
		end
	end
	for _, d in ipairs(manual:GetDescendants()) do
		local b = d:GetAttribute("BuildingId")
		if b then
			ids[b] = true
		end
	end
	local byCell, units, strays = {}, 0, 0
	for _, u in ipairs(Codec.units(manual, Codec.KEEP)) do
		local c = Codec.centre(u.inst)
		local best, bd
		for _, row in ipairs(cells) do
			local d = (row[2] - c.X) ^ 2 + (row[3] - c.Z) ^ 2
			if not bd or d < bd then
				best, bd = row[1], d
			end
		end
		if best and present[best.Name] then
			local list = byCell[best] or { units = {}, parts = 0 }
			byCell[best] = list
			table.insert(list.units, { path = u.path, node = Codec.encode(u.inst) })
			list.parts += (u.inst:IsA("BasePart") and 1 or 0) + #u.inst:GetDescendants()
			units += 1
		else
			strays += 1 -- its cell is packed: unpack the cell before editing its places
		end
	end
	local bytes, written = 0, 0
	for _, row in ipairs(cells) do
		local f = row[1]
		if present[f.Name] then
			local list = byCell[f]
			f:SetAttribute("manualParts", list and list.parts or 0)
			bytes += Codec.write(f, "m", list and list.units)
			written += 1
		end
	end
	local idList = {}
	for b in pairs(ids) do
		table.insert(idList, b)
	end
	table.sort(idList)
	data:SetAttribute("ManualIds", table.concat(idList, ","))
	local keep = {}
	for k in pairs(Codec.KEEP) do
		table.insert(keep, k)
	end
	data:SetAttribute("ManualKeep", table.concat(keep, ","))
	return { cells = written, units = units, strays = strays, bytes = bytes }
end

return Codec
