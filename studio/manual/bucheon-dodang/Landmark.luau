-- Manual towers of 신중동역 랜드마크 푸르지오 시티 (gis:11778185, cell 8930e0af10fffff), v1 (2026-10-14). The Auto building is only the
-- 6-floor shop podium (override 30 m): the V-World outline is the whole 133 x 69 m podium. Two 49-floor towers (160 m, B7-49F: shops to
-- 5F, offices 7-18F, officetels 20-49F) stand on it. Where: the two helipad roofs on the V-World satellite z19, moved back north-west
-- by the photo's lean (about 14 m east, 24 m south at the roof, read from the visible west faces). Sizes are rough (about 30 x 28 m and
-- 28 x 34 m). Look: street view gis:11778185 #1 E and #3 NE: dark grey towers with red-brick vertical stripes and a window line per floor.
-- Numbers: the anchors prelude (A.frame = the outline's rectangle, local X along its long side), so a new box split moves nothing.
-- Each top folder is made only when Manual/Landmark does not have it yet; to redo one, delete that folder and run this again.
-- Creates only; never destroys anything.
local ws = workspace
local manual = ws:FindFirstChild("Manual")
if not manual then manual = Instance.new("Folder") manual.Name = "Manual" manual.Parent = ws end
local root = manual:FindFirstChild("Landmark")
if not root then root = Instance.new("Folder") root.Name = "Landmark" root.Parent = manual end
local made = 0
-- a tower is a Persistent Model: a landmark seen from the whole map even with streaming on (architecture 6.2)
local function folder(n)
	local f = Instance.new("Model") f.Name = n f.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	if not root:FindFirstChild(n) then f.Parent = root end
	return f
end
local function part(parent, name, cf, size, material, color, extra)
	local p = Instance.new("Part")
	p.Name = name p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth p.BottomSurface = Enum.SurfaceType.Smooth
	p.Size = size p.CFrame = cf p.Material = material p.Color = Color3.fromRGB(color[1], color[2], color[3])
	if extra then for k, v in pairs(extra) do p[k] = v end end
	p.Parent = parent if parent.Parent then made += 1 end
	return p
end

local ID = "gis:11778185"
local F, a = A.frame(ID)
local S = 3.6                                       -- studs per metre
local BASE = a.roof                                 -- walkable podium top (above the flat-roof cap)
local TOP = 160 * S                                 -- 160 m above the ground
local BODY, BRICK, GLASS, CROWN = {58, 58, 62}, {150, 72, 58}, {34, 36, 40}, {72, 72, 76}

-- local X along the podium's long side, local Z across it (values when written: anchor (-1364.753, 22.447) yaw 80.379)
local TOWERS = {
	{ name = "TowerA", x = -33.0, z = 35.1, w = 30 * S, d = 28 * S },
	{ name = "TowerB", x = -178.9, z = -61.2, w = 28 * S, d = 34 * S },
}

for _, t in ipairs(TOWERS) do
	local f = folder(t.name)
	local h = TOP - BASE
	local c = F * CFrame.new(t.x, BASE + h / 2, t.z)
	part(f, "Body", c, Vector3.new(t.w, h, t.d), Enum.Material.Concrete, BODY)
	-- a window line per floor wrapping all four faces: one part a little larger than the body (43 floors from 7F to 49F)
	local floors = 43
	local fh = h / floors
	for i = 0, floors - 1 do
		part(f, "Win" .. i, F * CFrame.new(t.x, BASE + fh * (i + 0.55), t.z), Vector3.new(t.w + 0.6, fh * 0.45, t.d + 0.6),
			Enum.Material.SmoothPlastic, GLASS, { CastShadow = false })   -- not Glass: it mirrors the sky and turns navy (lessons)
	end
	-- brick-red pilasters, full height, standing out past the window lines: four on each long face, three on each short face
	for _, side in ipairs({ -1, 1 }) do
		for k = 1, 4 do
			local u = (k - 2.5) * t.w / 4.4
			part(f, "Pil", F * CFrame.new(t.x + u, BASE + h / 2, t.z + side * (t.d / 2 + 0.5)), Vector3.new(7, h, 1.6),
				Enum.Material.Brick, BRICK, { CastShadow = false })
		end
		for k = 1, 3 do
			local u = (k - 2) * t.d / 3.3
			part(f, "Pil", F * CFrame.new(t.x + side * (t.w / 2 + 0.5), BASE + h / 2, t.z + u), Vector3.new(1.6, h, 7),
				Enum.Material.Brick, BRICK, { CastShadow = false })
		end
	end
	-- crown band, roof slab and the helipad (green plate, white ring) seen on the satellite
	part(f, "Crown", F * CFrame.new(t.x, TOP + 4, t.z), Vector3.new(t.w + 1.2, 8, t.d + 1.2), Enum.Material.Concrete, CROWN)
	part(f, "Pad", F * CFrame.new(t.x, TOP + 8.2, t.z), Vector3.new(t.w * 0.7, 0.4, t.d * 0.7), Enum.Material.SmoothPlastic, {70, 140, 100})
	part(f, "Ring", F * CFrame.new(t.x, TOP + 8.5, t.z) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(0.2, t.d * 0.5, t.d * 0.5),
		Enum.Material.SmoothPlastic, {235, 235, 235}, { Shape = Enum.PartType.Cylinder })
	part(f, "RingIn", F * CFrame.new(t.x, TOP + 8.6, t.z) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(0.2, t.d * 0.44, t.d * 0.44),
		Enum.Material.SmoothPlastic, {70, 140, 100}, { Shape = Enum.PartType.Cylinder })
end

return "made " .. made
