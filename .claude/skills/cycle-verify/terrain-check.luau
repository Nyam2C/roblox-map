-- Ground over roads check (cycle-verify 2b, 2026-10-15). Change CELLS, run with execute_luau (Edit).
-- On each road, path and sidewalk piece of a cell, a grid of points (every 4 studs, 1 stud in from the edges) is looked at from
-- 50 studs above: the first thing a ray hits among the cell's Base parts must not be a ground tile. Counts the points where the
-- ground shows over the way (the sloping ground covering a road, user 2026-10-15). Expect covered=0.
local CELLS = { "<cell id>" }
local out = {}
for _, CELL in ipairs(CELLS) do
	local base = workspace.Auto[CELL].Base
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = { base }
	local rays, covered, worst = 0, 0, nil
	for _, folder in ipairs({ base:FindFirstChild("Roads"), base:FindFirstChild("Paths"), base:FindFirstChild("Sidewalks") }) do
		for _, p in (folder and folder:GetChildren() or {}) do
			if p:IsA("BasePart") then
				local hx, hz = p.Size.X / 2 - 1, p.Size.Z / 2 - 1
				for u = -hx, hx, 4 do
					for w = -hz, hz, 4 do
						local top = p.CFrame:PointToWorldSpace(Vector3.new(u, p.Size.Y / 2, w))
						local hit = workspace:Raycast(top + Vector3.new(0, 50, 0), Vector3.new(0, -60, 0), params)
						rays += 1
						if hit and hit.Instance:IsDescendantOf(base.Ground) and hit.Position.Y > top.Y + 0.05 then
							covered += 1
							worst = worst or string.format("%s at (%.0f, %.0f)", p.Name, top.X, top.Z)
						end
					end
				end
			end
		end
		task.wait()
	end
	table.insert(out, string.format("%s rays=%d covered=%d %s", CELL, rays, covered, worst or ""))
end
return table.concat(out, "\n")
