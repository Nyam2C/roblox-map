-- Manual school parts for the first cell, v3 (U5 S-14, BR-12). Built from the street-view crops and the satellite photo of 2026-10-13.
-- Creates only; never destroys or clears anything. Running it again when Manual/School exists does nothing.
-- Numbers: data/build/8930e0af13bffff boxes gis:11185213#b0..b3 and gis:11185281, config.toml school_polygons, scale 3.6 stud/m.
local ws = workspace
local manual = ws:FindFirstChild("Manual")
if not manual then manual = Instance.new("Folder") manual.Name = "Manual" manual.Parent = ws end
if manual:FindFirstChild("School") then return "Manual/School exists; nothing done" end
local school = Instance.new("Folder") school.Name = "School" school.Parent = manual
local made = 0
local function folder(n) local f = Instance.new("Folder") f.Name = n f.Parent = school return f end
local function part(parent, name, cf, size, material, color, extra)
	local p = Instance.new("Part")
	p.Name = name p.Anchored = true p.Shape = Enum.PartType.Block
	p.TopSurface = Enum.SurfaceType.Smooth p.BottomSurface = Enum.SurfaceType.Smooth
	p.Size = size p.CFrame = cf p.Material = material p.Color = Color3.fromRGB(color[1], color[2], color[3])
	if extra then for k, v in pairs(extra) do p[k] = v end end
	p.Parent = parent made += 1
	return p
end
local function textOn(p, text, face, color, maxDist)
	local gui = Instance.new("SurfaceGui") gui.Face = face gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud gui.PixelsPerStud = 50 gui.LightInfluence = 1 gui.MaxDistance = maxDist or 200 gui.Parent = p
	local label = Instance.new("TextLabel") label.Size = UDim2.new(1, 0, 1, 0) label.BackgroundTransparency = 1 label.TextScaled = true label.Text = text label.TextColor3 = color label.FontFace = Font.fromEnum(Enum.Font.SourceSansBold) label.Parent = gui
end
local yaw = function(deg) return CFrame.Angles(0, math.rad(deg), 0) end
local WHITE, GREEN, GRANITE, BRICK, GLASS = {240, 240, 238}, {40, 80, 50}, {175, 175, 170}, {155, 75, 60}, {90, 120, 150}

-- sports ground: sand, lines, goals
local g = folder("Ground")
part(g, "Field", CFrame.new(-57.5, 0.3, 60), Vector3.new(385, 0.4, 220), Enum.Material.Sand, {196, 178, 140})
for _, l in ipairs({ {-57.5, -40, 345, 0.5}, {-57.5, 160, 345, 0.5}, {-230, 60, 0.5, 200}, {115, 60, 0.5, 200}, {-57.5, 60, 0.5, 200} }) do
	part(g, "Line", CFrame.new(l[1], 0.53, l[2]), Vector3.new(l[3], 0.06, l[4]), Enum.Material.SmoothPlastic, {240, 240, 235}, { CanCollide = false })
end
for _, gx in ipairs({-150, 113}) do
	part(g, "GoalPost", CFrame.new(gx, 4.9, 60 - 13.2), Vector3.new(0.4, 8.8, 0.4), Enum.Material.SmoothPlastic, WHITE)
	part(g, "GoalPost", CFrame.new(gx, 4.9, 60 + 13.2), Vector3.new(0.4, 8.8, 0.4), Enum.Material.SmoothPlastic, WHITE)
	part(g, "GoalBar", CFrame.new(gx, 9.1, 60), Vector3.new(0.4, 0.4, 26.8), Enum.Material.SmoothPlastic, WHITE)
end
-- green shade shelters (steel posts, green roof, benches) along the north and west edges of the ground
local sh = folder("Shelters")
local function shelter(x0, z0, x1, z1, depthDir)
	local dx, dz = x1 - x0, z1 - z0
	local len = math.sqrt(dx * dx + dz * dz)
	local ux, uz = dx / len, dz / len
	local nx, nz = depthDir[1], depthDir[2]
	local bays = math.floor(len / 14.4)
	for k = 0, bays do
		local px, pz = x0 + ux * k * 14.4, z0 + uz * k * 14.4
		for _, side in ipairs({0, 1}) do
			part(sh, "Post", CFrame.new(px + nx * side * 8.5, 4.7, pz + nz * side * 8.5), Vector3.new(0.35, 9.4, 0.35), Enum.Material.Metal, {120, 120, 125})
		end
	end
	local cx, cz = (x0 + x1) / 2 + nx * 4.25, (z0 + z1) / 2 + nz * 4.25
	local y = math.deg(math.atan2(-uz, ux))
	part(sh, "Roof", CFrame.new(cx, 9.6, cz) * yaw(y), Vector3.new(len + 1, 0.3, 9.6), Enum.Material.Metal, {70, 140, 90})
	part(sh, "Bench", CFrame.new(cx, 1.6, cz) * yaw(y), Vector3.new(len - 2, 0.3, 1.6), Enum.Material.Wood, {150, 110, 70})
end
shelter(-200, -58, 95, -58, {0, 1})      -- in front of the main block (north edge of the ground), roof toward the ground
shelter(-248, -30, -248, 110, {1, 0})    -- west edge
-- basketball cage at the west end of the ground: green mesh walls
local cg = folder("Cage")
local cx0, cx1, cz0, cz1 = -236, -166, -36, 54
for _, w in ipairs({ {(cx0 + cx1) / 2, cz0, cx1 - cx0, 0.1}, {(cx0 + cx1) / 2, cz1, cx1 - cx0, 0.1}, {cx0, (cz0 + cz1) / 2, 0.1, cz1 - cz0}, {cx1, (cz0 + cz1) / 2, 0.1, cz1 - cz0} }) do
	part(cg, "Mesh", CFrame.new(w[1], 7.2, w[2]), Vector3.new(w[3], 14.4, w[4]), Enum.Material.Fabric, {60, 160, 80}, { Transparency = 0.55, CanCollide = false })
end
for _, c in ipairs({ {cx0, cz0}, {cx1, cz0}, {cx0, cz1}, {cx1, cz1}, {(cx0 + cx1) / 2, cz0}, {(cx0 + cx1) / 2, cz1} }) do
	part(cg, "Post", CFrame.new(c[1], 7.2, c[2]), Vector3.new(0.3, 14.4, 0.3), Enum.Material.Metal, {40, 110, 60})
end

-- fences: white leaf fence (posts, rails, translucent lattice panel) on the road sides, dark green bars on the west side
local f = folder("Fence")
local posts = {{-342.3,106.5,125.35,1},{-345.42,102.1,125.35,1},{-348.55,97.69,125.35,1},{-327.21,-62.79,80.59,1},{-326.33,-68.12,80.59,1},{-325.44,-73.45,80.59,1},{-324.56,-78.78,80.59,1},{-323.68,-84.1,80.59,1},{-322.8,-89.43,80.59,1},{-321.91,-94.76,80.59,1},{-321.03,-100.09,80.59,1},{-320.15,-105.41,80.59,1},{-319.27,-110.74,80.59,1},{-318.38,-116.07,80.59,1},{-317.5,-121.4,80.59,1},{-316.62,-126.72,80.59,1},{-315.74,-132.05,80.59,1},{-315.0,-136.5,80.68,1},{-314.13,-141.83,80.68,1},{-313.25,-147.16,80.68,1},{-312.38,-152.49,80.68,1},{-311.5,-157.81,80.68,1},{-310.63,-163.14,80.68,1},{-309.75,-168.47,80.68,1},{-308.88,-173.8,80.68,1},{-308.0,-179.13,80.68,1},{-307.13,-184.46,80.68,1},{-306.25,-189.79,80.68,1},{-305.38,-195.12,80.68,1},{-304.5,-200.44,80.68,1},{-303.63,-205.77,80.68,1},{-302.75,-211.1,80.68,1},{-301.88,-216.43,80.68,1},{-301.01,-221.76,80.68,1},{-300.13,-227.09,80.68,1},{-299.26,-232.42,80.68,1},{-298.38,-237.75,80.68,1},{-297.51,-243.07,80.68,1},{-296.63,-248.4,80.68,1},{-295.76,-253.73,80.68,1},{-294.88,-259.06,80.68,1},{-294.01,-264.39,80.68,1},{-293.13,-269.72,80.68,1},{-292.26,-275.05,80.68,1},{-291.38,-280.37,80.68,1},{-290.51,-285.7,80.68,1},{-289.64,-291.03,80.68,1},{-288.76,-296.36,80.68,1},{-287.89,-301.69,80.68,1},{-287.01,-307.02,80.68,1},{-286.14,-312.35,80.68,1},{-279.14,-354.98,80.68,1},{-278.26,-360.31,80.68,1},{-277.39,-365.63,80.68,1},{-276.52,-370.96,80.68,1},{-275.64,-376.29,80.68,1},{-274.77,-381.62,80.68,1},{-273.89,-386.95,80.68,1},{-273.02,-392.28,80.68,1},{-272.14,-397.61,80.68,1},{-271.27,-402.93,80.68,1},{-270.39,-408.26,80.68,1},{-269.52,-413.59,80.68,1},{-268.64,-418.92,80.68,1},{-267.77,-424.25,80.68,1},{-266.89,-429.58,80.68,1},{-266.02,-434.91,80.68,1},{-265.2,-439.9,-37.35,0},{-256.61,-433.35,-37.35,0},{-248.03,-426.79,-37.35,0},{-239.44,-420.24,-37.35,0},{-213.69,-400.58,-37.35,0},{-205.1,-394.03,-37.35,0},{-196.52,-387.48,-37.35,0},{-187.93,-380.93,-37.35,0},{-179.35,-374.37,-37.35,0},{-170.76,-367.82,-37.35,0},{-162.18,-361.27,-37.35,0},{-153.59,-354.72,-37.35,0},{-145.01,-348.16,-37.35,0},{-136.42,-341.61,-37.35,0},{-127.84,-335.06,-37.35,0},{-119.25,-328.51,-37.35,0},{-110.67,-321.95,-37.35,0},{-102.08,-315.4,-37.35,0},{-93.5,-308.85,-37.35,0},{-84.91,-302.3,-37.35,0},{-76.33,-295.74,-37.35,0},{-67.74,-289.19,-37.35,0},{-59.16,-282.64,-37.35,0},{-50.57,-276.09,-37.35,0},{-41.99,-269.53,-37.35,0},{-33.4,-262.98,-37.35,0},{-24.82,-256.43,-37.35,0},{9.52,-230.22,-37.35,0},{18.11,-223.67,-37.35,0},{26.69,-217.11,-37.35,0},{35.28,-210.56,-37.35,0},{43.86,-204.01,-37.35,0},{52.45,-197.46,-37.35,0},{61.04,-190.9,-37.35,0},{69.62,-184.35,-37.35,0},{78.21,-177.8,-37.35,0},{86.79,-171.25,-37.35,0},{95.38,-164.69,-37.35,0},{103.96,-158.14,-37.35,0},{112.55,-151.59,-37.35,0},{121.13,-145.04,-37.35,0},{129.72,-138.48,-37.35,0},{138.3,-131.93,-37.35,0},{146.89,-125.38,-37.35,0},{155.47,-118.83,-37.35,0},{155.9,-118.5,-63.97,0},{160.64,-108.8,-63.97,0},{165.38,-99.09,-63.97,0},{168.6,-92.5,-90.13,0},{168.58,-81.7,-90.13,0},{168.55,-70.9,-90.13,0},{168.53,-60.1,-90.13,0},{168.5,-49.3,-90.13,0},{168.48,-38.5,-90.13,0},{168.46,-27.7,-90.13,0},{168.43,-16.9,-90.13,0},{168.41,-6.1,-90.13,0},{168.38,4.7,-90.13,0},{168.36,15.5,-90.13,0},{168.34,26.3,-90.13,0},{168.31,37.1,-90.13,0},{168.29,47.9,-90.13,0},{168.26,58.7,-90.13,0},{168.24,69.5,-90.13,0},{168.22,80.3,-90.13,0},{168.19,91.1,-90.13,0},{168.17,101.9,-90.13,0},{168.14,112.7,-90.13,0},{168.12,123.5,-90.13,0},{168.1,134.3,-90.13,0},{168.07,145.1,-90.13,0},{168.05,155.9,-90.13,0},{168.02,166.7,-90.13,0},{168.0,177.3,-139.74,0},{159.76,184.28,-139.74,0},{154.3,188.9,170.58,0},{143.65,187.13,170.58,0},{132.99,185.36,170.58,0},{90.37,178.29,170.58,0},{79.72,176.53,170.58,0},{69.07,174.76,170.58,0},{58.41,172.99,170.58,0},{47.76,171.22,170.58,0},{37.1,169.45,170.58,0},{26.45,167.69,170.58,0},{15.79,165.92,170.58,0},{5.14,164.15,170.58,0},{-5.51,162.38,170.58,0},{-16.17,160.61,170.58,0},{-26.82,158.85,170.58,0},{-37.48,157.08,170.58,0},{-48.13,155.31,170.58,0},{-58.79,153.54,170.58,0},{-69.44,151.78,170.58,0},{-80.1,150.01,170.58,0},{-90.75,148.24,170.58,0},{-101.4,146.47,170.58,0},{-112.06,144.7,170.58,0},{-122.71,142.94,170.58,0},{-133.37,141.17,170.58,0},{-144.02,139.4,170.58,0},{-154.68,137.63,170.58,0},{-165.33,135.86,170.58,0},{-175.98,134.1,170.58,0},{-186.64,132.33,170.58,0},{-197.29,130.56,170.58,0},{-207.95,128.79,170.58,0},{-218.6,127.03,170.58,0},{-229.26,125.26,170.58,0},{-239.91,123.49,170.58,0},{-250.56,121.72,170.58,0},{-261.22,119.95,170.58,0},{-271.87,118.19,170.58,0},{-282.53,116.42,170.58,0},{-293.18,114.65,170.58,0},{-303.84,112.88,170.58,0},{-314.49,111.11,170.58,0},{-325.14,109.35,170.58,0},{-335.8,107.58,170.58,0}}
local rails = {{-343.86,104.3,125.35,5.4,1},{-346.99,99.89,125.35,5.4,1},{-326.77,-65.46,80.59,5.4,1},{-325.89,-70.79,80.59,5.4,1},{-325.0,-76.11,80.59,5.4,1},{-324.12,-81.44,80.59,5.4,1},{-323.24,-86.77,80.59,5.4,1},{-322.36,-92.1,80.59,5.4,1},{-321.47,-97.42,80.59,5.4,1},{-320.59,-102.75,80.59,5.4,1},{-319.71,-108.08,80.59,5.4,1},{-318.83,-113.41,80.59,5.4,1},{-317.94,-118.73,80.59,5.4,1},{-317.06,-124.06,80.59,5.4,1},{-316.18,-129.39,80.59,5.4,1},{-314.56,-139.16,80.68,5.4,1},{-313.69,-144.49,80.68,5.4,1},{-312.81,-149.82,80.68,5.4,1},{-311.94,-155.15,80.68,5.4,1},{-311.06,-160.48,80.68,5.4,1},{-310.19,-165.81,80.68,5.4,1},{-309.31,-171.14,80.68,5.4,1},{-308.44,-176.47,80.68,5.4,1},{-307.57,-181.79,80.68,5.4,1},{-306.69,-187.12,80.68,5.4,1},{-305.82,-192.45,80.68,5.4,1},{-304.94,-197.78,80.68,5.4,1},{-304.07,-203.11,80.68,5.4,1},{-303.19,-208.44,80.68,5.4,1},{-302.32,-213.77,80.68,5.4,1},{-301.44,-219.09,80.68,5.4,1},{-300.57,-224.42,80.68,5.4,1},{-299.69,-229.75,80.68,5.4,1},{-298.82,-235.08,80.68,5.4,1},{-297.94,-240.41,80.68,5.4,1},{-297.07,-245.74,80.68,5.4,1},{-296.2,-251.07,80.68,5.4,1},{-295.32,-256.4,80.68,5.4,1},{-294.45,-261.72,80.68,5.4,1},{-293.57,-267.05,80.68,5.4,1},{-292.7,-272.38,80.68,5.4,1},{-291.82,-277.71,80.68,5.4,1},{-290.95,-283.04,80.68,5.4,1},{-290.07,-288.37,80.68,5.4,1},{-289.2,-293.7,80.68,5.4,1},{-288.32,-299.03,80.68,5.4,1},{-287.45,-304.35,80.68,5.4,1},{-286.57,-309.68,80.68,5.4,1},{-278.7,-357.64,80.68,5.4,1},{-277.83,-362.97,80.68,5.4,1},{-276.95,-368.3,80.68,5.4,1},{-276.08,-373.63,80.68,5.4,1},{-275.2,-378.96,80.68,5.4,1},{-274.33,-384.28,80.68,5.4,1},{-273.45,-389.61,80.68,5.4,1},{-272.58,-394.94,80.68,5.4,1},{-271.7,-400.27,80.68,5.4,1},{-270.83,-405.6,80.68,5.4,1},{-269.96,-410.93,80.68,5.4,1},{-269.08,-416.26,80.68,5.4,1},{-268.21,-421.59,80.68,5.4,1},{-267.33,-426.91,80.68,5.4,1},{-266.46,-432.24,80.68,5.4,1},{-260.91,-436.62,-37.35,10.8,0},{-252.32,-430.07,-37.35,10.8,0},{-243.74,-423.52,-37.35,10.8,0},{-209.4,-397.31,-37.35,10.8,0},{-200.81,-390.76,-37.35,10.8,0},{-192.23,-384.2,-37.35,10.8,0},{-183.64,-377.65,-37.35,10.8,0},{-175.06,-371.1,-37.35,10.8,0},{-166.47,-364.55,-37.35,10.8,0},{-157.89,-357.99,-37.35,10.8,0},{-149.3,-351.44,-37.35,10.8,0},{-140.72,-344.89,-37.35,10.8,0},{-132.13,-338.34,-37.35,10.8,0},{-123.55,-331.78,-37.35,10.8,0},{-114.96,-325.23,-37.35,10.8,0},{-106.37,-318.68,-37.35,10.8,0},{-97.79,-312.13,-37.35,10.8,0},{-89.2,-305.57,-37.35,10.8,0},{-80.62,-299.02,-37.35,10.8,0},{-72.03,-292.47,-37.35,10.8,0},{-63.45,-285.92,-37.35,10.8,0},{-54.86,-279.36,-37.35,10.8,0},{-46.28,-272.81,-37.35,10.8,0},{-37.69,-266.26,-37.35,10.8,0},{-29.11,-259.71,-37.35,10.8,0},{13.82,-226.94,-37.35,10.8,0},{22.4,-220.39,-37.35,10.8,0},{30.99,-213.84,-37.35,10.8,0},{39.57,-207.29,-37.35,10.8,0},{48.16,-200.73,-37.35,10.8,0},{56.74,-194.18,-37.35,10.8,0},{65.33,-187.63,-37.35,10.8,0},{73.91,-181.08,-37.35,10.8,0},{82.5,-174.52,-37.35,10.8,0},{91.08,-167.97,-37.35,10.8,0},{99.67,-161.42,-37.35,10.8,0},{108.25,-154.87,-37.35,10.8,0},{116.84,-148.31,-37.35,10.8,0},{125.42,-141.76,-37.35,10.8,0},{134.01,-135.21,-37.35,10.8,0},{142.59,-128.66,-37.35,10.8,0},{151.18,-122.1,-37.35,10.8,0},{158.27,-113.65,-63.97,10.8,0},{163.01,-103.94,-63.97,10.8,0},{168.59,-87.1,-90.13,10.8,0},{168.56,-76.3,-90.13,10.8,0},{168.54,-65.5,-90.13,10.8,0},{168.52,-54.7,-90.13,10.8,0},{168.49,-43.9,-90.13,10.8,0},{168.47,-33.1,-90.13,10.8,0},{168.44,-22.3,-90.13,10.8,0},{168.42,-11.5,-90.13,10.8,0},{168.4,-0.7,-90.13,10.8,0},{168.37,10.1,-90.13,10.8,0},{168.35,20.9,-90.13,10.8,0},{168.32,31.7,-90.13,10.8,0},{168.3,42.5,-90.13,10.8,0},{168.28,53.3,-90.13,10.8,0},{168.25,64.1,-90.13,10.8,0},{168.23,74.9,-90.13,10.8,0},{168.2,85.7,-90.13,10.8,0},{168.18,96.5,-90.13,10.8,0},{168.16,107.3,-90.13,10.8,0},{168.13,118.1,-90.13,10.8,0},{168.11,128.9,-90.13,10.8,0},{168.08,139.7,-90.13,10.8,0},{168.06,150.5,-90.13,10.8,0},{168.04,161.3,-90.13,10.8,0},{163.88,180.79,-139.74,10.8,0},{148.97,188.02,170.58,10.8,0},{138.32,186.25,170.58,10.8,0},{85.05,177.41,170.58,10.8,0},{74.39,175.64,170.58,10.8,0},{63.74,173.87,170.58,10.8,0},{53.08,172.11,170.58,10.8,0},{42.43,170.34,170.58,10.8,0},{31.78,168.57,170.58,10.8,0},{21.12,166.8,170.58,10.8,0},{10.47,165.03,170.58,10.8,0},{-0.19,163.27,170.58,10.8,0},{-10.84,161.5,170.58,10.8,0},{-21.5,159.73,170.58,10.8,0},{-32.15,157.96,170.58,10.8,0},{-42.81,156.19,170.58,10.8,0},{-53.46,154.43,170.58,10.8,0},{-64.11,152.66,170.58,10.8,0},{-74.77,150.89,170.58,10.8,0},{-85.42,149.12,170.58,10.8,0},{-96.08,147.36,170.58,10.8,0},{-106.73,145.59,170.58,10.8,0},{-117.39,143.82,170.58,10.8,0},{-128.04,142.05,170.58,10.8,0},{-138.69,140.28,170.58,10.8,0},{-149.35,138.52,170.58,10.8,0},{-160.0,136.75,170.58,10.8,0},{-170.66,134.98,170.58,10.8,0},{-181.31,133.21,170.58,10.8,0},{-191.97,131.44,170.58,10.8,0},{-202.62,129.68,170.58,10.8,0},{-213.27,127.91,170.58,10.8,0},{-223.93,126.14,170.58,10.8,0},{-234.58,124.37,170.58,10.8,0},{-245.24,122.61,170.58,10.8,0},{-255.89,120.84,170.58,10.8,0},{-266.55,119.07,170.58,10.8,0},{-277.2,117.3,170.58,10.8,0},{-287.85,115.53,170.58,10.8,0},{-298.51,113.77,170.58,10.8,0},{-309.16,112.0,170.58,10.8,0},{-319.82,110.23,170.58,10.8,0},{-330.47,108.46,170.58,10.8,0}}
for _, p in ipairs(posts) do
	local green = p[4] == 1
	part(f, "Post", CFrame.new(p[1], green and 2.7 or 2.3, p[2]) * yaw(p[3]), green and Vector3.new(0.22, 5.4, 0.22) or Vector3.new(0.25, 4.6, 0.25), Enum.Material.Metal, green and GREEN or WHITE)
end
for _, r in ipairs(rails) do
	local green = r[5] == 1
	if green then
		for _, h in ipairs({1.2, 3.0, 4.9}) do
			part(f, "Rail", CFrame.new(r[1], h, r[2]) * yaw(r[3]), Vector3.new(r[4], 0.14, 0.14), Enum.Material.Metal, GREEN, { CanCollide = false })
		end
		part(f, "Base", CFrame.new(r[1], 0.5, r[2]) * yaw(r[3]), Vector3.new(r[4], 1.0, 0.6), Enum.Material.Slate, {95, 90, 88})
	else
		for _, h in ipairs({1.0, 4.4}) do
			part(f, "Rail", CFrame.new(r[1], h, r[2]) * yaw(r[3]), Vector3.new(r[4], 0.12, 0.12), Enum.Material.Metal, WHITE, { CanCollide = false })
		end
		part(f, "Lattice", CFrame.new(r[1], 2.7, r[2]) * yaw(r[3]), Vector3.new(r[4], 3.3, 0.05), Enum.Material.SmoothPlastic, {245, 245, 245}, { Transparency = 0.6, CanCollide = false })
		part(f, "Base", CFrame.new(r[1], 0.3, r[2]) * yaw(r[3]), Vector3.new(r[4], 0.6, 0.5), Enum.Material.Concrete, {150, 150, 148})
	end
end

-- gates: granite pillars and a folding steel gate (a white lattice across the opening), the name plate at the main gate
local gt = folder("Gate")
local function gate(name, cx, cz, edgeYaw, nx, nz, plateYaw, halfWidth, text)
	local gc = Vector3.new(cx, 0, cz)
	local along = yaw(edgeYaw).RightVector
	for _, s in ipairs({-1, 1}) do
		part(gt, name .. "Pillar", CFrame.new(gc + along * (s * halfWidth) + Vector3.new(0, 4.5, 0)) * yaw(edgeYaw), Vector3.new(3.6, 9, 3.6), Enum.Material.Granite, GRANITE)
		part(gt, name .. "PillarCap", CFrame.new(gc + along * (s * halfWidth) + Vector3.new(0, 9.15, 0)) * yaw(edgeYaw), Vector3.new(4.0, 0.3, 4.0), Enum.Material.Granite, {120, 120, 118})
	end
	part(gt, name .. "FoldingGate", CFrame.new(gc + Vector3.new(0, 2.6, 0)) * yaw(edgeYaw), Vector3.new(halfWidth * 2 - 3.6, 5.0, 0.15), Enum.Material.Metal, {225, 225, 228}, { Transparency = 0.45, CanCollide = false })
	if text then
		local outN = Vector3.new(nx, 0, nz)
		local plate = part(gt, name .. "Plate", CFrame.new(gc + along * -halfWidth + outN * 1.95 + Vector3.new(0, 6.2, 0)) * yaw(plateYaw), Vector3.new(3.2, 1.2, 0.3), Enum.Material.SmoothPlastic, {60, 60, 65}, { CanCollide = false })
		textOn(plate, text, Enum.NormalId.Front, Color3.new(1, 1, 1))
	end
end
gate("Main", 111.68, 181.83, 170.58, -0.1637, 0.9865, 170.58, 14.4, "심원고등학교")
gate("Back", -5.51, -241.69, -37.35, 0.6067, -0.7949, -37.35, 10.8, "심원고등학교")

-- main block gis:11185213#b0 (light gray, 5 floors): red gable roof (satellite photo)
local m = folder("Main")
local b0 = CFrame.new(-206.147, 36.81, -241.257) * yaw(79.919)        -- size 185.558 x 73.62 x 124.397
local hw0, hd0, H0 = 92.779, 62.1985, 73.62
local half = hd0 + 1.8
local rise = math.tan(math.rad(18)) * half
for _, s in ipairs({-1, 1}) do
	local turn = (s == 1) and CFrame.Angles(0, math.pi, 0) or CFrame.new()
	part(m, "Roof", b0 * CFrame.new(0, H0 / 2 + rise / 2, s * half / 2) * turn, Vector3.new(hw0 * 2 + 3.6, rise, half), Enum.Material.Slate, {160, 62, 48}, { Shape = Enum.PartType.Wedge })
end

-- south wing gis:11185213#b3 (5 floors, 56 m, faces the sports ground; local -Z is south, local -X is east):
-- entrance canopy with steps, the name over it and a clock on the south face; the stair tower on the north face near the east end;
-- the east end block in red brick with the school name in white letters and a glass stair strip (street view 2026-10-13)
local b3 = CFrame.new(-58.609, 36.81, -140.39) * yaw(169.919)        -- size 201.433 x 73.62 x 38.587
local hw3, hd3, H3 = 100.7165, 19.2935, 73.62
local cy = -H3 / 2
part(m, "Canopy", b3 * CFrame.new(0, cy + 13.0, -(hd3 + 4.5)), Vector3.new(25.2, 1.1, 9.0), Enum.Material.Concrete, {215, 215, 212})
for _, s in ipairs({-1, 1}) do
	part(m, "Column", b3 * CFrame.new(s * 10.8, cy + 6.2, -(hd3 + 8.3)) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(12.4, 1.1, 1.1), Enum.Material.Concrete, {215, 215, 212}, { Shape = Enum.PartType.Cylinder })
end
for k = 1, 3 do
	part(m, "Step", b3 * CFrame.new(0, cy + (4 - k) * 0.54 - 0.27, -(hd3 + 1.3 * k - 0.4)), Vector3.new(27.2, 0.54, 1.3), Enum.Material.Concrete, {190, 190, 188})
end
local nameplate = part(m, "EntranceSign", b3 * CFrame.new(0, cy + 15.6, -(hd3 + 0.35)), Vector3.new(16.0, 2.2, 0.3), Enum.Material.SmoothPlastic, {30, 60, 110}, { CanCollide = false })
textOn(nameplate, "심원고등학교", Enum.NormalId.Front, Color3.new(1, 1, 1), 300)
part(m, "ClockRim", b3 * CFrame.new(0, cy + 52.0, -(hd3 + 0.3)) * CFrame.Angles(0, math.rad(90), 0), Vector3.new(0.5, 6.4, 6.4), Enum.Material.SmoothPlastic, {40, 40, 45}, { Shape = Enum.PartType.Cylinder, CanCollide = false })
part(m, "ClockFace", b3 * CFrame.new(0, cy + 52.0, -(hd3 + 0.6)) * CFrame.Angles(0, math.rad(90), 0), Vector3.new(0.3, 5.6, 5.6), Enum.Material.SmoothPlastic, {250, 250, 245}, { Shape = Enum.PartType.Cylinder, CanCollide = false })
part(m, "ClockHand", b3 * CFrame.new(0, cy + 52.9, -(hd3 + 0.85)), Vector3.new(0.35, 2.2, 0.2), Enum.Material.SmoothPlastic, {30, 30, 35}, { CanCollide = false })
part(m, "StairTower", b3 * CFrame.new(-(hw3 - 40), (H3 + 9.0) / 2 - H3 / 2, hd3 + 5.0), Vector3.new(18.0, H3 + 9.0, 10.8), Enum.Material.Plaster, {205, 205, 208})

-- east end of b3 (photo 2026): cream end wall with the school name in blue letters on the top floor, a red-brick corner band,
-- a dark brown roof band all round, colored window surrounds on the south face, a glass stair strip near the middle
local e = folder("EastWing")
local t = 0.144
part(e, "CreamEnd", b3 * CFrame.new(-(hw3 + t / 2), 0, 0), Vector3.new(t, H3, hd3 * 2 + 2 * t), Enum.Material.Plaster, {232, 226, 212}, { CanCollide = false })
part(e, "BrickCorner", b3 * CFrame.new(-(hw3 + 0.3), 0, -(hd3 - 3.0)), Vector3.new(0.6, H3, 7.2), Enum.Material.Brick, BRICK, { CanCollide = false })
part(e, "BrickCornerS", b3 * CFrame.new(-(hw3 - 3.0), 0, -(hd3 + 0.3)), Vector3.new(7.2, H3, 0.6), Enum.Material.Brick, BRICK, { CanCollide = false })
local letters = part(e, "NameLetters", b3 * CFrame.new(-(hw3 + 0.35), H3 / 2 - 7.5, 0) * yaw(90), Vector3.new(hd3 * 2 - 4, 7.0, 0.2), Enum.Material.SmoothPlastic, {232, 226, 212}, { Transparency = 1, CanCollide = false })
textOn(letters, "심원고등학교", Enum.NormalId.Front, Color3.fromRGB(30, 60, 150), 400)
for _, side in ipairs({-1, 1}) do
	part(e, "RoofBand", b3 * CFrame.new(0, H3 / 2 - 1.2, side * (hd3 + 0.4)), Vector3.new(hw3 * 2 + 1.0, 2.4, 0.5), Enum.Material.Slate, {70, 55, 50}, { CanCollide = false })
end
part(e, "RoofBandEnd", b3 * CFrame.new(-(hw3 + 0.4), H3 / 2 - 1.2, 0), Vector3.new(0.5, 2.4, hd3 * 2 + 1.0), Enum.Material.Slate, {70, 55, 50}, { CanCollide = false })
part(e, "MidGlass", b3 * CFrame.new(-28.8, 0, -(hd3 + 0.25)), Vector3.new(5.4, H3 - 1.0, 0.3), Enum.Material.Glass, GLASS, { Reflectance = 0.3, CanCollide = false })
-- colored window surrounds (green, red, blue, lime) on floors 2 to 4 at four bays, around the Auto windows (pitch 2.4 m, sill 0.9 m, 1.8 x 1.5 m)
local fh3 = H3 / 5
local L3 = hw3 * 2 / 3.6
local nWin = math.floor((L3 - 1) / 2.4)
local colors = { {60, 150, 70}, {200, 50, 50}, {50, 110, 190}, {160, 190, 60} }
for i, j in ipairs({ 6, 10, 14, 18 }) do
	local along = (L3 * (j + 0.5) / nWin - L3 / 2) * 3.6
	for k = 1, 3 do
		part(e, "Surround", b3 * CFrame.new(-along, -H3 / 2 + k * fh3 + (0.9 + 0.75) * 3.6, -(hd3 + 0.07)), Vector3.new(2.4 * 3.6, 2.1 * 3.6, 0.1), Enum.Material.SmoothPlastic, colors[i], { CanCollide = false })
	end
end

-- gis:11185281 (red brick, 5 floors): white balcony stack at the south end, arched stair window on the east face
local a = folder("BrickBlock")
local bb = CFrame.new(-308.119, 30.6, 5.311) * yaw(80.16)        -- size 181.815 x 61.2 x 48.853; local -X is south, local +Z is east
local hwb, hdb, Hb = 90.9075, 24.4265, 61.2
local fh = Hb / 5
for k = 0, 4 do
	local fy = k * fh - Hb / 2
	part(a, "Balcony", bb * CFrame.new(-(hwb + 2.9), fy + 0.3, hdb - 4.7), Vector3.new(5.8, 0.6, 9.4), Enum.Material.Concrete, {225, 222, 215})
	part(a, "BalconyFront", bb * CFrame.new(-(hwb + 5.6), fy + 2.3, hdb - 4.7), Vector3.new(0.4, 4.0, 9.4), Enum.Material.Concrete, {225, 222, 215}, { CanCollide = false })
	part(a, "BalconySide", bb * CFrame.new(-(hwb + 2.9), fy + 2.3, hdb - 0.2), Vector3.new(5.8, 4.0, 0.4), Enum.Material.Concrete, {225, 222, 215}, { CanCollide = false })
end
-- dark gray gable roof along the long axis (photo 2026), 15 degrees, eaves 0.4 m past the walls
local halfb = hdb + 1.4
local riseb = math.tan(math.rad(15)) * halfb
for _, s in ipairs({-1, 1}) do
	local turn = (s == 1) and CFrame.Angles(0, math.pi, 0) or CFrame.new()
	part(a, "Roof", bb * CFrame.new(0, Hb / 2 + riseb / 2, s * halfb / 2) * turn, Vector3.new(hwb * 2 + 2.8, riseb, halfb), Enum.Material.Slate, {75, 70, 72}, { Shape = Enum.PartType.Wedge })
end
part(a, "ArchGlass", bb * CFrame.new(hwb - 30, Hb / 2 - 8.0, hdb + 0.2) * CFrame.Angles(0, math.rad(90), 0), Vector3.new(0.3, 14.4, 14.4), Enum.Material.Glass, GLASS, { Shape = Enum.PartType.Cylinder, Reflectance = 0.3, CanCollide = false })
part(a, "StairStrip", bb * CFrame.new(hwb - 30, -2.0, hdb + 0.2), Vector3.new(5.4, Hb - 12.0, 0.3), Enum.Material.Glass, GLASS, { Reflectance = 0.3, CanCollide = false })

-- potted dwarf pines along the south edge of the ground and a basketball stand at the east end (photo 2026)
local gd = folder("GroundSide")
for _, x in ipairs({ -170, -120, -70, -20, 30, 80, 130 }) do
	part(gd, "Pot", CFrame.new(x, 1.4, 152), Vector3.new(2.8, 2.8, 2.8), Enum.Material.SmoothPlastic, {40, 40, 42}, { Shape = Enum.PartType.Cylinder })
	part(gd, "PotTrunk", CFrame.new(x, 4.5, 152), Vector3.new(0.5, 3.5, 0.5), Enum.Material.Wood, {90, 70, 50})
	part(gd, "PotCrown", CFrame.new(x, 8.2, 152), Vector3.new(4.6, 6.0, 4.6), Enum.Material.Grass, {45, 90, 50}, { Shape = Enum.PartType.Ball, CanCollide = false })
end
part(gd, "HoopPost", CFrame.new(100, 5.5, -44), Vector3.new(0.5, 11.0, 0.5), Enum.Material.Metal, {60, 90, 160})
part(gd, "Backboard", CFrame.new(100, 10.6, -41.5), Vector3.new(6.5, 3.8, 0.2), Enum.Material.SmoothPlastic, {245, 245, 245}, { CanCollide = false })
part(gd, "Hoop", CFrame.new(100, 9.2, -39.5), Vector3.new(1.6, 0.2, 1.6), Enum.Material.Metal, {220, 90, 40}, { Shape = Enum.PartType.Cylinder, CanCollide = false })

-- the small park west of the parcel: grass, pines, a pavilion, benches, a hedge along the path
local pk = folder("Park")
part(pk, "Grass", CFrame.new(-372, 0.25, -20), Vector3.new(56, 0.3, 180), Enum.Material.Grass, {95, 135, 70})
for _, p in ipairs({ {-390, -95}, {-358, -70}, {-392, -35}, {-360, 5}, {-392, 45}, {-362, 62} }) do
	part(pk, "Trunk", CFrame.new(p[1], 9, p[2]) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(18, 1.4, 1.4), Enum.Material.Wood, {90, 70, 50}, { Shape = Enum.PartType.Cylinder })
	for _, c in ipairs({ {12, 10, 7}, {16.5, 8, 6}, {20.5, 5.5, 5} }) do
		part(pk, "Crown", CFrame.new(p[1], c[1], p[2]), Vector3.new(c[2], c[3], c[2]), Enum.Material.Grass, {40, 85, 45}, { Shape = Enum.PartType.Ball, CanCollide = false })
	end
end
part(pk, "PavilionFloor", CFrame.new(-375, 0.6, -20), Vector3.new(14.4, 0.6, 14.4), Enum.Material.Wood, {150, 110, 70})
for _, c in ipairs({ {-6, -6}, {6, -6}, {-6, 6}, {6, 6} }) do
	part(pk, "PavilionPost", CFrame.new(-375 + c[1], 5.6, -20 + c[2]), Vector3.new(0.9, 9.4, 0.9), Enum.Material.Wood, {120, 85, 55})
end
part(pk, "PavilionRoof", CFrame.new(-375, 10.55, -20), Vector3.new(16, 0.5, 16), Enum.Material.Slate, {70, 60, 60})
part(pk, "PavilionRoofTop", CFrame.new(-375, 11.4, -20), Vector3.new(10, 1.2, 10), Enum.Material.Slate, {70, 60, 60})
for _, bz in ipairs({-50, 20}) do
	part(pk, "Bench", CFrame.new(-352, 1.6, bz), Vector3.new(1.6, 0.3, 6.0), Enum.Material.Wood, {150, 110, 70})
end
part(pk, "Hedge", CFrame.new(-346, 1.2, -20), Vector3.new(1.6, 2.2, 176), Enum.Material.Grass, {50, 110, 55}, { CanCollide = false })
return string.format("Manual/School v3 made: %d parts", made)
