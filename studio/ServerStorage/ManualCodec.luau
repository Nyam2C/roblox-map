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

return Codec
