-- The server builds only the cells near players (user decision 2026-10-15: each player's H3 cell and two rings, 19 cells, 5 players
-- a server; test: aidlc-docs/construction/plans/b-cell-streaming-test.md). Script in ServerScriptService.
--
-- Data (installed in Edit by studio/install/cell-data.luau): ServerStorage/CellData/<cell> holds the cell's chunks.json, zstd
-- compressed and base64, in StringValues "1", "2", ... (a StringValue takes under 200,000 characters and no binary); the folder's
-- attributes x, z (centre in studs), ring1 and ring2 (comma-separated cell ids, data/build/cellindex.json) place it. The far view:
-- ServerStorage/Lite/Auto/<cell> (lite.py), shown while the full cell is not built.
--
-- At start the cells saved in the place (Workspace/Auto, for editing) are removed; from then on a cell is built when a player's
-- two rings take it in and removed UNLOAD_AFTER seconds after none does. Over GUARD_MB of server memory the rings shrink to one
-- (the documented server limit is about 6 GB). ServerStorage/CellPrepare(x, z) builds the cell nearest a point first (teleports,
-- spawning) and keeps it PIN seconds; ReplicatedStorage/CellLoading tells a client to cover the screen while that runs.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local HttpService = game:GetService("HttpService")
local EncodingService = game:GetService("EncodingService")
local Stats = game:GetService("Stats")

local BUDGET_MS = 8 -- a frame's building while players move (the B test: 21 ms chunks made 34-64 ms server frames)
local PREPARE_BUDGET_MS = 12 -- behind the loading screen (the B test: the target cell in under a second)
local UNLOAD_AFTER = 8
local PIN = 10
local GUARD_MB = 5500

local dataFolder = ServerStorage:FindFirstChild("CellData")
if not dataFolder then
	warn("CellStreamer: no ServerStorage/CellData, the cells saved in the place stay as they are")
	return
end
local Builder = require(ServerStorage:WaitForChild("MapBuilder"))
local index = {}
for _, f in ipairs(dataFolder:GetChildren()) do
	if f:IsA("Folder") then
		index[f.Name] = { x = f:GetAttribute("x"), z = f:GetAttribute("z"),
			ring1 = string.split(f:GetAttribute("ring1"), ","), ring2 = string.split(f:GetAttribute("ring2"), ",") }
	end
end
local auto = workspace:WaitForChild("Auto")
local liteRoot = ServerStorage:FindFirstChild("Lite")
local liteAuto = liteRoot and liteRoot:FindFirstChild("Auto")
local liteView = Instance.new("Folder")
liteView.Name = "Lite"
liteView.Parent = workspace

local loaded, building, lastWanted, pinned, failed = {}, {}, {}, {}, {}
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

local function showLite(id, on)
	if not liteAuto then
		return
	end
	local m = on and liteAuto:FindFirstChild(id) or liteView:FindFirstChild(id)
	if m then
		m.Parent = on and liteView or liteAuto
	end
end

local function cellData(id)
	local folder = dataFolder:FindFirstChild(id)
	local parts = {}
	for k = 1, #folder:GetChildren() do
		table.insert(parts, folder[tostring(k)].Value)
	end
	local raw = EncodingService:DecompressBuffer(EncodingService:Base64Decode(buffer.fromstring(table.concat(parts))),
		Enum.CompressionAlgorithm.Zstd)
	return HttpService:JSONDecode(buffer.tostring(raw))
end

local function build(id, budgetMs)
	building[id] = true
	local ok, err = pcall(function()
		local data = cellData(id)
		Builder.begin(id)
		local t0 = os.clock()
		for _, ch in ipairs(data.chunks) do
			Builder.add(id, ch.items, ch.looks)
			t0 = frameWait(budgetMs, t0)
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
		showLite(id, false)
	else
		failed[id] = os.clock() + 30 -- not again for a while (one warning, not one a frame)
		warn("CellStreamer: " .. id .. ": " .. tostring(err))
		local f = auto:FindFirstChild(id)
		if f then
			f:Destroy()
		end
	end
end

local function unload(id)
	loaded[id] = nil
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
	showLite(id, true)
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

local function wanted()
	-- in Studio the figure is the whole Studio process (8-9 GB with the editor), so the guard only runs on a live server
	local rings = not RunService:IsStudio() and Stats:GetTotalMemoryUsageMb() > GUARD_MB and "ring1" or "ring2"
	local want, near = {}, {}
	for _, p in ipairs(Players:GetPlayers()) do
		local root = p.Character and p.Character:FindFirstChild("HumanoidRootPart")
		if root then
			local id = nearestCell(root.Position.X, root.Position.Z)
			if id then
				for _, n in ipairs(index[id][rings]) do
					want[n] = true
					local c = index[n]
					local d = (c.x - root.Position.X) ^ 2 + (c.z - root.Position.Z) ^ 2
					near[n] = math.min(near[n] or math.huge, d)
				end
			end
		end
	end
	return want, near
end

-- start: the far view everywhere, then the cells saved in the place go (they stay in the place file for editing)
if liteAuto then
	for _, m in ipairs(liteAuto:GetChildren()) do
		m.Parent = liteView
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
		local want, near = wanted()
		local now = os.clock()
		for id in pairs(want) do
			lastWanted[id] = now
		end
		-- the nearest wanted cell not built yet, one at a time
		local best, bd = nil, math.huge
		for id, d in pairs(near) do
			if not loaded[id] and not building[id] and (failed[id] or 0) < os.clock() and d < bd then
				best, bd = id, d
			end
		end
		if best then
			build(best, BUDGET_MS)
		end
		for id in pairs(loaded) do
			if not want[id] and not building[id] and now - (lastWanted[id] or 0) > UNLOAD_AFTER and (pinned[id] or 0) < now then
				unload(id)
			end
		end
		local n = 0
		for _ in pairs(loaded) do
			n += 1
		end
		stats:SetAttribute("Loaded", n)
		stats:SetAttribute("MemoryMb", math.floor(Stats:GetTotalMemoryUsageMb()))
		if not best then
			task.wait(0.5)
		end
	end
end)
