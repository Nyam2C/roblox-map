-- B test (2026-10-15): the server builds the cells near players from compressed chunk data and destroys far ones.
-- Play-only: runs on the server DataModel copy, nothing is saved.
local HS = game:GetService("HttpService")
local ES = game:GetService("EncodingService")
local RS = game:GetService("RunService")
local St = game:GetService("Stats")
local SS = game:GetService("ServerStorage")
local B = require(SS.MapBuilder)

local CENTERS = ...
local R_LOAD, R_UNLOAD = 1500, 2000
local stats = {cells = {}, hb_worst = 0, hb_slow = 0, hb_n = 0, mem = {}, loaded_max = 0, errors = {}}
local out = Instance.new("StringValue"); out.Name = "StreamStats"; out.Parent = SS

-- the place would hold these blobs; here they come once from 127.0.0.1 and are compressed in memory
local blob = {}
for id in pairs(CENTERS) do
  local body = HS:GetAsync("http://127.0.0.1:8765/" .. id .. ".json")
  blob[id] = ES:CompressBuffer(buffer.fromstring(body), Enum.CompressionAlgorithm.Zstd, 9)
end
for _, c in ipairs(workspace.Auto:GetChildren()) do c:Destroy(); RS.Heartbeat:Wait() end

local loaded, state = {}, {}
RS.Heartbeat:Connect(function(dt)
  stats.hb_n += 1
  if dt > stats.hb_worst then stats.hb_worst = dt end
  if dt > 1 / 30 then stats.hb_slow += 1 end
end)

local function build(id)
  local s = {id = id}
  local t0 = os.clock()
  local data = HS:JSONDecode(buffer.tostring(ES:DecompressBuffer(blob[id], Enum.CompressionAlgorithm.Zstd)))
  s.decode_ms = (os.clock() - t0) * 1000
  local w0 = os.clock()
  B.begin(id)
  local worst = 0
  for _, ch in ipairs(data.chunks) do
    local a = os.clock()
    B.add(id, ch.items, ch.looks)
    worst = math.max(worst, os.clock() - a)
    RS.Heartbeat:Wait()
  end
  B.finish(id)
  s.chunks = #data.chunks
  s.add_worst_ms = worst * 1000
  s.wall_s = os.clock() - w0
  table.insert(stats.cells, s)
end

local function unload(id)
  local f = workspace.Auto:FindFirstChild(id)
  if not f then return end
  local t0, worst = os.clock(), 0
  for _, sub in ipairs({"Buildings", "Props", "Signs", "Base"}) do
    local x = f:FindFirstChild(sub)
    if x then
      for _, c in ipairs(x:GetChildren()) do
        local a = os.clock(); c:Destroy(); worst = math.max(worst, os.clock() - a)
        if os.clock() - a > 0.002 then RS.Heartbeat:Wait() end
      end
      RS.Heartbeat:Wait()
    end
  end
  f:Destroy()
  table.insert(stats.cells, {id = id, unload_s = os.clock() - t0, destroy_worst_ms = worst * 1000})
end

task.spawn(function()
  while true do
    local want = {}
    for _, p in ipairs(game.Players:GetPlayers()) do
      local hrp = p.Character and p.Character:FindFirstChild("HumanoidRootPart")
      if hrp then
        for id, c in pairs(CENTERS) do
          local d = (Vector3.new(c[1], 0, c[2]) - Vector3.new(hrp.Position.X, 0, hrp.Position.Z)).Magnitude
          if d < R_LOAD then want[id] = "load" elseif d < R_UNLOAD and want[id] == nil then want[id] = "keep" end
        end
      end
    end
    -- nearest first would be better; one cell at a time keeps the frame cost of one chunk
    for id, w in pairs(want) do
      if w == "load" and not loaded[id] then
        local ok, e = pcall(build, id)
        if not ok then table.insert(stats.errors, id .. ": " .. tostring(e)) end
        loaded[id] = true
      end
    end
    for id in pairs(loaded) do
      if not want[id] then unload(id); loaded[id] = nil end
    end
    local n = 0
    for _ in pairs(loaded) do n += 1 end
    stats.loaded_max = math.max(stats.loaded_max, n)
    table.insert(stats.mem, {math.floor(os.clock()), n, math.floor(St:GetTotalMemoryUsageMb())})
    out.Value = HS:JSONEncode(stats)
    task.wait(0.5)
  end
end)
return "streamer running, cells " .. (function() local n = 0 for _ in pairs(CENTERS) do n += 1 end return n end)()
