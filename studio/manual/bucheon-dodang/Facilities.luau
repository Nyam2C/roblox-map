-- Manual facilities the user approved (2026-10-15), built from data/build/manual/facilities.json (src/facilities.py).
-- Run with execute_luau after putting the JSON text in DATA (the runner fetches it from the local server). One Folder per facility
-- under Manual/Facilities; a Configuration per claimed building id carries BuildingId so the Auto building steps aside. A facility
-- of several buildings has one Model per building (the part names' "gis:N" before "#"), so settleManual sets each building on
-- its own ground (2026-10-15: one Model for the whole facility sank its uphill buildings up to 2 m).
-- Makes a facility only when its Model is missing; to redo one, delete Manual/Facilities/<key> and run again.
return function(DATA)
	local HS = game:GetService("HttpService")
	local data = HS:JSONDecode(DATA)
	local manual = workspace:FindFirstChild("Manual") or Instance.new("Folder", workspace)
	manual.Name = "Manual"
	local root = manual:FindFirstChild("Facilities") or Instance.new("Folder")
	root.Name = "Facilities"
	root.Parent = manual
	local SHAPES = { Wedge = Enum.PartType.Wedge, Cylinder = Enum.PartType.Cylinder, Ball = Enum.PartType.Ball }
	local FACES = { F = Enum.NormalId.Front, T = Enum.NormalId.Top }
	local made = {}
	for _, f in ipairs(data.facilities) do
		if root:FindFirstChild(f.key) then
			table.insert(made, f.key .. " kept")
			continue
		end
		-- a park is a Folder of loose parts: settleManual lifts each part onto the ground under it (안중근공원, 2026-10-15)
		local model = Instance.new("Folder")
		model.Name = f.key
		local groups = {}
		local function holder(name)
			if f.folder then return model end
			local key = string.match(name, "^([^#]+)#") or name
			if not groups[key] then
				local g = Instance.new("Model")
				g.Name = key
				g.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
				g.Parent = model
				groups[key] = g
			end
			return groups[key]
		end
		for _, id in ipairs(f.claims) do
			local c = Instance.new("Configuration")
			c.Name = "Claim"
			c:SetAttribute("BuildingId", id)
			c.Parent = model
		end
		for i, it in ipairs(f.parts) do
			local p = Instance.new("Part")
			p.Name = it.n
			p.Anchored = true
			p.TopSurface, p.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
			p.Material = Enum.Material[it.m] or Enum.Material.Concrete
			p.Color = Color3.fromRGB(it.c[1], it.c[2], it.c[3])
			p.CanCollide = it.l == 1
			p.Transparency = it.tr or 0
			p.Reflectance = it.rf or 0
			local cf = CFrame.new(it.x, it.y, it.z) * CFrame.Angles(0, math.rad(it.r), 0)
			if it.p == "Disc" then -- a round piece on a wall: its axis out of the wall
				p.Shape = Enum.PartType.Cylinder
				p.Size = Vector3.new(it.d, it.h, it.w)
				cf = cf * CFrame.Angles(0, math.rad(90), 0)
			elseif it.p == "Cylinder" then -- standing: the length runs along X
				p.Shape = Enum.PartType.Cylinder
				p.Size = Vector3.new(it.w, it.h, it.d)
				cf = cf * CFrame.Angles(0, 0, math.rad(90))
			else
				if SHAPES[it.p] then p.Shape = SHAPES[it.p] end
				p.Size = Vector3.new(it.w, it.h, it.d)
			end
			p.CFrame = cf
			if it.t then
				local gui = Instance.new("SurfaceGui")
				gui.Face = FACES[it.f] or Enum.NormalId.Front
				gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
				gui.PixelsPerStud = math.min(50, 95 / math.max(1, (it.f == "T") and it.d or it.h))
				gui.MaxDistance = it.md or 300
				gui.LightInfluence = 1
				local label = Instance.new("TextLabel")
				label.Size = UDim2.fromScale(1, 1)
				label.BackgroundTransparency = 1
				label.TextScaled = true
				label.FontFace = Font.fromEnum(Enum.Font.SourceSansBold)
				label.TextColor3 = Color3.fromRGB(it.ink[1], it.ink[2], it.ink[3])
				label.Text = it.t -- data only
				label.Parent = gui
				gui.Parent = p
			end
			p.Parent = holder(it.n)
			if i % 400 == 0 then task.wait() end
		end
		model.Parent = root
		table.insert(made, string.format("%s %d parts", f.key, #f.parts))
		task.wait()
	end
	return table.concat(made, ", ")
end
