-- Manual parts for 부흥중학교 (gis:11036833, first cell), v2 (2026-10-13). The Auto building body stays. Sources: street view of
-- gis:11036833 #1 SW (pano at (-397, -585), the gate) and #3 W; the V-World satellite z19 laid over a straight-down Studio capture
-- (data/compare/now_blend.jpg, 0.974 px per stud), which shows what the building data does not have: the teal roof with solar panels,
-- the sand ground, the basketball court, the gym with its two-storey annex and the covered walkway (no V-World or OSM records).
-- Each top folder is made only when Manual/Buheung does not have it yet; to redo one, delete that folder and run this again.
-- Creates only; never destroys anything.
local ws = workspace
local manual = ws:FindFirstChild("Manual")
if not manual then manual = Instance.new("Folder") manual.Name = "Manual" manual.Parent = ws end
local root = manual:FindFirstChild("Buheung")
if not root then root = Instance.new("Folder") root.Name = "Buheung" root.Parent = manual end
local made = 0
-- a folder that already exists gets a detached stand-in, so its parts are made and thrown away
local function folder(n) local f = Instance.new("Folder") f.Name = n if not root:FindFirstChild(n) then f.Parent = root end return f end
local function part(parent, name, cf, size, material, color, extra)
	local p = Instance.new("Part")
	p.Name = name p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth p.BottomSurface = Enum.SurfaceType.Smooth
	p.Size = size p.CFrame = cf p.Material = material p.Color = Color3.fromRGB(color[1], color[2], color[3])
	if extra then for k, v in pairs(extra) do p[k] = v end end
	p.Parent = parent if parent.Parent then made += 1 end
	return p
end
local function textOn(p, text, face)
	local gui = Instance.new("SurfaceGui") gui.Face = face gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud gui.PixelsPerStud = 50 gui.LightInfluence = 1 gui.MaxDistance = 200 gui.Parent = p
	local label = Instance.new("TextLabel") label.Size = UDim2.new(1, 0, 1, 0) label.BackgroundTransparency = 1 label.TextScaled = true label.Text = text label.TextColor3 = Color3.new(1, 1, 1) label.FontFace = Font.fromEnum(Enum.Font.SourceSansBold) label.Parent = gui
end
local yaw = function(deg) return CFrame.Angles(0, math.rad(deg), 0) end
local GRID = 170.762                                -- the school's grid: gis:11036833#b1 yaw

-- the fence along 계남로 way:219848661 (yaw 143), 46 studs off its centre line on the school side, from just past the building's
-- north-east corner (u = -25) to u = 300: a low dark brick wall with dark steel pickets; the gate at u 89.5 to 113.5
local fe = folder("Fence")
local O = Vector3.new(-312, 0, -529)               -- a point on the 계남로 centre line
local d = Vector3.new(-0.799, 0, -0.602)           -- along the road (the part X axis at yaw 143)
local n = Vector3.new(-0.602, 0, 0.799)            -- toward the school; the parts' local +Z faces the road
local function at(u, y) return CFrame.new(O + d * u + n * 46 + Vector3.new(0, y, 0)) * yaw(143) end
local WALL, STEEL, GRANITE, BAND = {95, 82, 78}, {45, 45, 48}, {190, 190, 185}, {70, 70, 72}
local gate0, gate1 = 89.5, 113.5
local function fence(u0, u1)
	local count = math.max(1, math.floor((u1 - u0) / 10.8 + 0.5))
	local len = (u1 - u0) / count
	for k = 0, count - 1 do
		local c = u0 + (k + 0.5) * len
		part(fe, "Wall", at(c, 1.1), Vector3.new(len, 2.2, 1.2), Enum.Material.Brick, WALL)
		part(fe, "Pickets", at(c, 4.35), Vector3.new(len, 4.3, 0.15), Enum.Material.Metal, STEEL, { Transparency = 0.45, CanCollide = false })
		part(fe, "Rail", at(c, 6.4), Vector3.new(len, 0.25, 0.25), Enum.Material.Metal, STEEL)
		part(fe, "Post", at(u0 + k * len, 3.4), Vector3.new(0.3, 6.8, 0.3), Enum.Material.Metal, STEEL)
	end
	part(fe, "Post", at(u1, 3.4), Vector3.new(0.3, 6.8, 0.3), Enum.Material.Metal, STEEL)
end
fence(-25, gate0 - 1.8)
fence(gate1 + 1.8, 300)
for _, u in ipairs({ gate0, gate1 }) do
	part(fe, "GatePillar", at(u, 5.0), Vector3.new(3.6, 10.0, 3.6), Enum.Material.Granite, GRANITE)
	part(fe, "GateBand", at(u, 10.7), Vector3.new(3.8, 1.4, 3.8), Enum.Material.Granite, BAND)
end
part(fe, "GateLintel", at((gate0 + gate1) / 2, 11.0), Vector3.new(gate1 - gate0 + 3.6, 1.6, 2.4), Enum.Material.Granite, GRANITE)
part(fe, "FoldingGate", at((gate0 + gate1) / 2, 2.6), Vector3.new(gate1 - gate0 - 3.6, 5.0, 0.15), Enum.Material.Metal, {225, 225, 228}, { Transparency = 0.45, CanCollide = false })
local plate = part(fe, "NamePlate", at(gate0, 6.2) * CFrame.new(0, 0, 1.95), Vector3.new(3.2, 1.2, 0.3), Enum.Material.SmoothPlastic, {60, 60, 65}, { CanCollide = false })
textOn(plate, "부흥중학교", Enum.NormalId.Back)
-- a blank banner on the fence east of the gate (the real one carries this year's notice; no text is copied)
part(fe, "Banner", at(70, 5.0) * CFrame.new(0, 0, 0.3), Vector3.new(18.0, 2.5, 0.1), Enum.Material.Fabric, {245, 225, 235}, { CanCollide = false })

-- teal roof over the Auto roof caps of b0..b4 (`#cap`, top at 67.5; the caps do not answer ray casts) and two rows of solar panels on b1
local rf = folder("Roof")
local TOP, TEAL = 67.5, {110, 170, 145}
for _, b in ipairs({
	{-570.666, -559.328, 100.105, 65.302, 81.181}, {-452.889, -453.968, 330.798, 70.292, 170.762}, {-398.963, -500.827, 23.738, 11.463, 81.103},
	{-375.627, -487.368, 53.950, 21.317, 144.658}, {-369.629, -480.049, 75.839, 7.927, 170.762} }) do
	part(rf, "Roof", CFrame.new(b[1], TOP + 0.2, b[2]) * yaw(b[5]), Vector3.new(b[3] + 0.4, 0.4, b[4] + 0.4), Enum.Material.Concrete, TEAL)
end
local b1 = CFrame.new(-452.889, TOP, -453.968) * yaw(GRID)        -- local -Z is south
for _, s in ipairs({ {-110, -27, 105, 12}, {92, -26, 55, 10} }) do
	part(rf, "Solar", b1 * CFrame.new(s[1], 0.7, s[2]) * CFrame.Angles(math.rad(-12), 0, 0), Vector3.new(s[3], 0.3, s[4]), Enum.Material.Glass, {40, 55, 90}, { Reflectance = 0.2 })
end

-- the sand ground south of the building, lines and goals (long axis east-west), the basketball court west of it
local gr = folder("Ground")
local gc = CFrame.new(-501, 0, -283) * yaw(GRID)        -- the pitch part of the sand between the court and the gym
local gw, gd = 185, 180
part(gr, "Field", gc * CFrame.new(0, 0.3, 0), Vector3.new(gw, 0.4, gd), Enum.Material.Sand, {196, 178, 140})
for _, l in ipairs({ {0, -gd / 2 + 8, gw - 16, 0.5}, {0, gd / 2 - 8, gw - 16, 0.5}, {-gw / 2 + 8, 0, 0.5, gd - 16}, {gw / 2 - 8, 0, 0.5, gd - 16}, {0, 0, 0.5, gd - 16} }) do
	part(gr, "Line", gc * CFrame.new(l[1], 0.53, l[2]), Vector3.new(l[3], 0.06, l[4]), Enum.Material.SmoothPlastic, {240, 240, 235}, { CanCollide = false })
end
part(gr, "CentreCircle", gc * CFrame.new(0, 0.52, 0) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(0.05, 30, 30), Enum.Material.SmoothPlastic, {240, 240, 235}, { Shape = Enum.PartType.Cylinder, CanCollide = false })
part(gr, "CentreSand", gc * CFrame.new(0, 0.54, 0) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(0.05, 29, 29), Enum.Material.Sand, {196, 178, 140}, { Shape = Enum.PartType.Cylinder, CanCollide = false })
for _, s in ipairs({-1, 1}) do
	local gx = s * (gw / 2 - 9)
	for _, z in ipairs({-13.2, 13.2}) do
		part(gr, "GoalPost", gc * CFrame.new(gx, 4.9, z), Vector3.new(0.4, 8.8, 0.4), Enum.Material.SmoothPlastic, {240, 240, 238})
	end
	part(gr, "GoalBar", gc * CFrame.new(gx, 9.1, 0), Vector3.new(0.4, 0.4, 26.8), Enum.Material.SmoothPlastic, {240, 240, 238})
end
local cc = CFrame.new(-635.5, 0, -292.5) * yaw(GRID)        -- court 77 x 115, long axis north-south
part(gr, "Court", cc * CFrame.new(0, 0.3, 0), Vector3.new(77, 0.4, 115), Enum.Material.SmoothPlastic, {90, 105, 130})
for _, s in ipairs({-1, 1}) do
	part(gr, "HoopPost", cc * CFrame.new(0, 5.5, s * 54), Vector3.new(0.5, 11.0, 0.5), Enum.Material.Metal, {60, 60, 65})
	part(gr, "Backboard", cc * CFrame.new(0, 10.6, s * 51.5), Vector3.new(6.5, 3.8, 0.2), Enum.Material.SmoothPlastic, {245, 245, 245}, { CanCollide = false })
	part(gr, "KeyLine", cc * CFrame.new(0, 0.53, s * 46), Vector3.new(17, 0.06, 0.5), Enum.Material.SmoothPlastic, {240, 240, 235}, { CanCollide = false })
end
part(gr, "HalfLine", cc * CFrame.new(0, 0.53, 0), Vector3.new(77 - 6, 0.06, 0.5), Enum.Material.SmoothPlastic, {240, 240, 235}, { CanCollide = false })

-- the gym east of the ground (light gray metal roof, light gray panel walls, blue-framed window band), its two-storey annex to the
-- north and the covered walkway from the main block; heights are estimates (gym 11 m, annex 2 floors), not data
local gy = folder("Gym")
local GRAY, ROOF = {200, 200, 205}, {185, 190, 195}
local gyc = CFrame.new(-361.6, 0, -259.3) * yaw(GRID)
local GW, GD, GH = 100, 110, 40
part(gy, "Body", gyc * CFrame.new(0, GH / 2, 0), Vector3.new(GW, GH, GD), Enum.Material.Concrete, GRAY)
part(gy, "Roof", gyc * CFrame.new(0, GH + 0.4, 0), Vector3.new(GW + 2, 0.8, GD + 2), Enum.Material.Metal, ROOF)
for _, s in ipairs({-1, 1}) do
	part(gy, "Windows", gyc * CFrame.new(s * (GW / 2 + 0.1), GH - 12, 0), Vector3.new(0.2, 7, GD - 16), Enum.Material.Glass, {80, 110, 160}, { Reflectance = 0.2, CanCollide = false })
	part(gy, "WindowFrame", gyc * CFrame.new(s * (GW / 2 + 0.15), GH - 8.2, 0), Vector3.new(0.3, 0.6, GD - 14), Enum.Material.SmoothPlastic, {40, 80, 170}, { CanCollide = false })
	part(gy, "WindowFrame", gyc * CFrame.new(s * (GW / 2 + 0.15), GH - 15.8, 0), Vector3.new(0.3, 0.6, GD - 14), Enum.Material.SmoothPlastic, {40, 80, 170}, { CanCollide = false })
end
part(gy, "Door", gyc * CFrame.new(-(GW / 2 + 0.1), 5, 30), Vector3.new(0.2, 10, 12), Enum.Material.Glass, {60, 80, 90}, { CanCollide = false })
local an = CFrame.new(-350, 0, -326) * yaw(GRID)
part(gy, "Annex", an * CFrame.new(0, 12, 0), Vector3.new(92, 24, 38), Enum.Material.Concrete, {215, 215, 218})
part(gy, "AnnexRoof", an * CFrame.new(0, 24.3, 0), Vector3.new(93, 0.6, 39), Enum.Material.Concrete, {165, 165, 170})
for k = 0, 1 do
	part(gy, "AnnexWindows", an * CFrame.new(0, 4.2 + k * 12, 19.1), Vector3.new(84, 4.8, 0.2), Enum.Material.Glass, {80, 110, 160}, { Reflectance = 0.2, CanCollide = false })
end
local wk = CFrame.new(-335, 0, -373) * yaw(GRID)        -- walkway 12 x 64, roof at 11
part(gy, "WalkRoof", wk * CFrame.new(0, 11.2, 0), Vector3.new(12, 0.6, 64), Enum.Material.Metal, {235, 235, 238})
for _, z in ipairs({ -28, -9, 10, 28 }) do
	for _, x in ipairs({ -5.4, 5.4 }) do
		part(gy, "WalkPost", wk * CFrame.new(x, 5.5, z), Vector3.new(0.5, 11.0, 0.5), Enum.Material.Metal, {220, 220, 222})
	end
end

return string.format("Manual/Buheung v2: %d parts made (folders already there were left alone)", made)
