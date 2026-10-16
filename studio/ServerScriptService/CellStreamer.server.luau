-- The server builds only the cells near players (user decision 2026-10-15: each player's H3 cell and two rings, 19 cells, 5 players
-- a server; test: aidlc-docs/construction/plans/b-cell-streaming-test.md). Script in ServerScriptService.
--
-- Data (installed in Edit by studio/install/cell-data.luau): ServerStorage/CellData/<cell> holds the cell's chunks.json, zstd
-- compressed and base64, in StringValues "1", "2", ... (a StringValue takes under 200,000 characters and no binary); the folder's
-- attributes x, z (centre in studs), ring1 and ring2 (comma-separated cell ids, data/build/cellindex.json) place it. The far view:
-- Past the clients' streaming radius nothing of a full cell shows but its ground (user 2026-10-15: no far boxes). The hand-made places (ServerStorage/ManualCodec):
-- the cell's units in StringValues m1, m2, ... are built with the cell and go with it; the folder's ManualIds attribute lists the
-- buildings they own (the Builder leaves those out), ManualKeep the places that stay in Workspace/Manual.
--
-- At start the cells saved in the place (Workspace/Auto, for editing) are removed. Then, every half second (user 2026-10-15: all four):
-- 1 choose: every player's cell and ring 1 first, then the other cells by distance from all players at once (the nearest player's
--   position now or LOOKAHEAD s ahead), so players together share cells and the saved budget reaches farther;
-- 2 the budget is parts (BUDGET_PARTS, about 3 GB at 6.1 KB a part on the server), not cells: a dense cell costs more;
-- 3 a built cell stays while there is room; only when a chosen cell needs room do the farthest unchosen cells go;
-- 4 the next cell built is the chosen one the players reach soonest (distance / speed).
-- Over GUARD_MB of memory on a live server the budget drops by a fifth (the documented limit is about 6 GB).
-- ServerStorage/CellPrepare(x, z) builds the cell nearest a point first (teleports, spawning) and keeps it PIN seconds;
-- ReplicatedStorage/CellLoading tells a client to cover the screen while that runs.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local HttpService = game:GetService("HttpService")
local EncodingService = game:GetService("EncodingService")
local Stats = game:GetService("Stats")

local BUDGET_MS = 8 -- a frame's building while players move (the B test: 21 ms chunks made 34-64 ms server frames)
local PREPARE_BUDGET_MS = 12 -- behind the loading screen (the B test: the target cell in under a second)
local SLICE = 25 -- items per Builder.add call, so a frame's building stays near the budget
local PIN = 10
local GUARD_MB = 5500
local BUDGET_PARTS = 500000 -- 5 GB target: about 1.1 GB fixed (server, cell data), the rest for full cells
local LOOKAHEAD = 6 -- seconds of travel the chooser looks ahead
local MIN_SPEED, MAX_SPEED = 16, 120 -- studs/s: walking, and a cap for the look-ahead (a teleport is not a speed)

local dataFolder = ServerStorage:FindFirstChild("CellData")
if not dataFolder then
	warn("CellStreamer: no ServerStorage/CellData, the cells saved in the place stay as they are")
	return
end
local Builder = require(ServerStorage:WaitForChild("MapBuilder"))
local Codec = require(ServerStorage:WaitForChild("ManualCodec"))
local kits = ServerStorage:FindFirstChild("Kits")
local manualOn = dataFolder:GetAttribute("ManualIds") ~= nil
local index = {}
for _, f in ipairs(dataFolder:GetChildren()) do
	if f:IsA("Folder") then
		index[f.Name] = { x = f:GetAttribute("x"), z = f:GetAttribute("z"),
			parts = (f:GetAttribute("parts") or 8000) + (manualOn and f:GetAttribute("manualParts") or 0),
			ring1 = string.split(f:GetAttribute("ring1"), ","), ring2 = string.split(f:GetAttribute("ring2"), ",") }
	end
end
local auto = workspace:WaitForChild("Auto")

local loaded, building, pinned, failed, manualRoots = {}, {}, {}, {}, {}
local loadedParts = 0
local stats = Instance.new("Folder")
stats.Name = "CellStreamerStats"
stats.Parent = ServerStorage

local function frameWait(budgetMs, t0)
	if (os.clock() - t0) * 1000 >= budgetMs then
		RunService.Heartbeat:Wait()
		return os.clock()
	end
	return t0
end

local unpack = Codec.read

local function cellData(id)
	return unpack(dataFolder:FindFirstChild(id), "")
end

local function manualFolder(path)
	local f = workspace:FindFirstChild("Manual") or Instance.new("Folder")
	f.Name = "Manual"
	f.Parent = workspace
	for _, name in ipairs(path) do
		local nxt = f:FindFirstChild(name)
		if not nxt then
			nxt = Instance.new("Folder")
			nxt.Name = name
			nxt.Parent = f
		end
		f = nxt
	end
	return f
end

-- the cell's share of the hand-made places, built before the cell so the Builder already sees nothing to leave out
local function buildManual(id, budgetMs)
	local units = manualOn and unpack(dataFolder:FindFirstChild(id), "m")
	local made = {}
	manualRoots[id] = made
	if not units then
		return
	end
	local t0 = os.clock()
	for _, u in ipairs(units) do
		local inst = Codec.decode(u.node, kits)
		inst.Parent = manualFolder(u.path)
		table.insert(made, inst)
		t0 = frameWait(budgetMs, t0)
	end
end

local function build(id, budgetMs)
	building[id] = true
	local ok, err = pcall(function()
		buildManual(id, budgetMs)
		local data = cellData(id)
		Builder.begin(id)
		local t0 = os.clock()
		for _, ch in ipairs(data.chunks) do -- a slice at a time: a whole chunk took 50-130 ms (2026-10-17), far over the frame budget
			for i = 1, #ch.items, SLICE do
				Builder.add(id, table.move(ch.items, i, math.min(i + SLICE - 1, #ch.items), 1, {}), ch.looks)
				t0 = frameWait(budgetMs, t0)
			end
		end
		Builder.finish(id)
		for _, d in ipairs(auto[id]:GetDescendants()) do -- the spawn kept at start stays the only one
			if d:IsA("SpawnLocation") then
				d:Destroy()
			end
		end
	end)
	building[id] = nil
	if ok then
		loaded[id] = true
		loadedParts += index[id].parts
	else
		failed[id] = os.clock() + 30 -- not again for a while (one warning, not one a frame)
		for _, inst in ipairs(manualRoots[id] or {}) do
			inst:Destroy()
		end
		manualRoots[id] = nil
		warn("CellStreamer: " .. id .. ": " .. tostring(err))
		local f = auto:FindFirstChild(id)
		if f then
			f:Destroy()
		end
	end
end

local function unload(id)
	loaded[id] = nil
	loadedParts -= index[id].parts
	for _, inst in ipairs(manualRoots[id] or {}) do
		inst:Destroy()
	end
	manualRoots[id] = nil
	local f = auto:FindFirstChild(id)
	if f then
		local t0 = os.clock()
		for _, sub in ipairs({ "Buildings", "Props", "Signs", "Base" }) do
			local x = f:FindFirstChild(sub)
			if x then
				for _, c in ipairs(x:GetChildren()) do
					c:Destroy()
					t0 = frameWait(BUDGET_MS, t0)
				end
			end
		end
		f:Destroy()
	end
end

local function nearestCell(x, z)
	local best, bd = nil, math.huge
	for id, c in pairs(index) do
		local d = (c.x - x) ^ 2 + (c.z - z) ^ 2
		if d < bd then
			best, bd = id, d
		end
	end
	return best, math.sqrt(bd)
end

local function plan()
	local ps = {}
	for _, p in ipairs(Players:GetPlayers()) do
		local root = p.Character and p.Character:FindFirstChild("HumanoidRootPart")
		if root then
			local v = root.AssemblyLinearVelocity
			local flat = Vector3.new(v.X, 0, v.Z)
			local speed = math.min(flat.Magnitude, MAX_SPEED)
			local ahead = speed > 1 and root.Position + flat.Unit * speed * LOOKAHEAD or root.Position
			table.insert(ps, { x = root.Position.X, z = root.Position.Z, ax = ahead.X, az = ahead.Z, speed = math.max(speed, MIN_SPEED),
				cell = nearestCell(root.Position.X, root.Position.Z) })
		end
	end
	-- in Studio the memory figure is the whole Studio process (8-9 GB with the editor), so the guard only runs on a live server
	local budget = (dataFolder:GetAttribute("BudgetParts") or BUDGET_PARTS) * ((not RunService:IsStudio() and Stats:GetTotalMemoryUsageMb() > GUARD_MB) and 0.8 or 1)
	local score, eta = {}, {}
	for id, c in pairs(index) do
		local best, t = math.huge, math.huge
		for _, p in ipairs(ps) do
			local d = math.min(math.sqrt((c.x - p.x) ^ 2 + (c.z - p.z) ^ 2), math.sqrt((c.x - p.ax) ^ 2 + (c.z - p.az) ^ 2))
			best = math.min(best, d)
			t = math.min(t, d / p.speed)
		end
		score[id], eta[id] = best, t
	end
	local chosen, used = {}, 0
	for _, p in ipairs(ps) do
		for _, n in ipairs(p.cell and index[p.cell].ring1 or {}) do
			if not chosen[n] then
				chosen[n], used = 2, used + index[n].parts -- 2: required, built even over the budget
			end
		end
	end
	local order = {}
	for id in pairs(index) do
		if not chosen[id] then
			table.insert(order, id)
		end
	end
	table.sort(order, function(a, b)
		return score[a] < score[b]
	end)
	for _, id in ipairs(order) do
		if used + index[id].parts > budget then
			break -- the first that does not fit ends the choice, so the chosen area stays a whole disc round the players
		end
		chosen[id], used = true, used + index[id].parts
	end
	return chosen, eta, score, budget
end

-- the farthest built cells not chosen go until `room` more parts fit under the budget
local function evict(chosen, score, budget, room)
	local victims = {}
	for id in pairs(loaded) do
		if not chosen[id] and not building[id] and (pinned[id] or 0) < os.clock() then
			table.insert(victims, id)
		end
	end
	table.sort(victims, function(a, b)
		return (score[a] or 0) > (score[b] or 0)
	end)
	for _, id in ipairs(victims) do
		if loadedParts + room <= budget then
			break
		end
		unload(id)
	end
end

-- start: the cells saved in the place go (they stay in the place file for editing), and the
-- hand-made places but the kept ones (they come back with their cells)
if manualOn then
	local skip = {}
	for _, b in ipairs(string.split(dataFolder:GetAttribute("ManualIds"), ",")) do
		skip[b] = true
	end
	Builder.manualSkip = skip
	local keep = {}
	for _, k in ipairs(string.split(dataFolder:GetAttribute("ManualKeep") or "", ",")) do
		keep[k] = true
	end
	local manual = workspace:FindFirstChild("Manual")
	if manual then
		for _, u in ipairs(Codec.units(manual, keep)) do
			u.inst:Destroy()
		end
	end
end
for _, c in ipairs(auto:GetChildren()) do
	if index[c.Name] then
		for _, d in ipairs(c:GetDescendants()) do -- the configured spawn (config.toml spawn_*) is kept out of its cell
			if d:IsA("SpawnLocation") then
				d.Parent = workspace
			end
		end
		c:Destroy()
		RunService.Heartbeat:Wait()
	end
end

local prepare = Instance.new("BindableFunction")
prepare.Name = "CellPrepare"
prepare.OnInvoke = function(x, z)
	local id = nearestCell(x, z)
	if not id then
		return nil
	end
	pinned[id] = os.clock() + PIN
	while building[id] do
		RunService.Heartbeat:Wait()
	end
	if not loaded[id] then
		local chosen, _, score, budget = plan()
		chosen[id] = true
		evict(chosen, score, budget, index[id].parts)
		build(id, PREPARE_BUDGET_MS)
	end
	pinned[id] = os.clock() + PIN
	return id
end
prepare.Parent = ServerStorage

local loading = Instance.new("RemoteEvent")
loading.Name = "CellLoading"
loading.Parent = ReplicatedStorage

-- a character waits, anchored, until the cell under it is built (spawn, respawn)
local function onCharacter(player, char)
	local root = char:WaitForChild("HumanoidRootPart", 10)
	if not root then
		return
	end
	root.Anchored = true
	loading:FireClient(player, true)
	prepare:Invoke(root.Position.X, root.Position.Z)
	loading:FireClient(player, false)
	root.Anchored = false
end
local function onPlayer(player)
	player.CharacterAdded:Connect(function(char)
		onCharacter(player, char)
	end)
	if player.Character then
		task.spawn(onCharacter, player, player.Character)
	end
end
Players.PlayerAdded:Connect(onPlayer)
for _, p in ipairs(Players:GetPlayers()) do
	onPlayer(p)
end

task.spawn(function()
	while true do
		local chosen, eta, score, budget = plan()
		local now = os.clock()
		local best, bt = nil, math.huge
		for id, kind in pairs(chosen) do
			local t = kind == 2 and -1 or eta[id] -- required cells first
			if not loaded[id] and not building[id] and (failed[id] or 0) < now and t < bt then
				best, bt = id, t
			end
		end
		evict(chosen, score, budget, best and index[best].parts or 0)
		if best and (loadedParts + index[best].parts <= budget or chosen[best] == 2) then
			build(best, BUDGET_MS)
		else
			best = nil
		end
		local n, c = 0, 0
		for _ in pairs(loaded) do
			n += 1
		end
		for _ in pairs(chosen) do
			c += 1
		end
		stats:SetAttribute("Loaded", n)
		stats:SetAttribute("Chosen", c)
		stats:SetAttribute("LoadedParts", loadedParts)
		stats:SetAttribute("Budget", budget)
		stats:SetAttribute("MemoryMb", math.floor(Stats:GetTotalMemoryUsageMb()))
		if not best then
			task.wait(0.5)
		end
	end
end)
