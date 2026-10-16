-- The loading cover (2026-10-15): while the server builds the cell a player lands in (spawn, the big map's hexagon jump, H),
-- ServerScriptService/CellStreamer fires ReplicatedStorage/CellLoading (true, then false) and this fades the screen in and out.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local remote = ReplicatedStorage:WaitForChild("CellLoading", 30)
if not remote then
	return
end
local gui = Instance.new("ScreenGui")
gui.Name = "CellLoading"
gui.IgnoreGuiInset = true
gui.ResetOnSpawn = false
gui.DisplayOrder = 100
local cover = Instance.new("Frame")
cover.Size = UDim2.fromScale(1, 1)
cover.BackgroundColor3 = Color3.fromRGB(18, 20, 24)
cover.BackgroundTransparency = 1
cover.Parent = gui
local label = Instance.new("TextLabel")
label.Size = UDim2.fromScale(1, 0.1)
label.Position = UDim2.fromScale(0, 0.45)
label.BackgroundTransparency = 1
label.Text = "불러오는 중"
label.TextColor3 = Color3.fromRGB(235, 235, 235)
label.TextTransparency = 1
label.TextSize = 28
label.Font = Enum.Font.GothamMedium
label.Parent = cover
gui.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")

-- The parts keep coming after the cell is built (2026-10-17, user "A"): a joining client got about 190,000 in its first 12 s (Studio
-- Play, 61 cells built) and ran at 5-9 frames a second meanwhile. So the cover is up from the moment this client starts, and after a
-- join or a jump it lifts only once the character stands free and the parts have nearly stopped (under SETTLE a second), after
-- MIN_COVER s at least and MAX_COVER s at most.
local SETTLE, MIN_COVER, MAX_COVER = 1000, 2, 25
local player = Players.LocalPlayer
local arrived = 0
workspace.DescendantAdded:Connect(function(d)
	if d:IsA("BasePart") then
		arrived += 1
	end
end)

local fade = TweenInfo.new(0.25)
local function show(on)
	TweenService:Create(cover, fade, { BackgroundTransparency = on and 0 or 1 }):Play()
	TweenService:Create(label, fade, { TextTransparency = on and 0 or 1 }):Play()
end
local serverOn, waiting = false, 0 -- waiting: a newer cover cancels an older wait
local function liftWhenSettled()
	waiting += 1
	local mine, t0, last = waiting, os.clock(), arrived
	while os.clock() - t0 < MAX_COVER do
		task.wait(1)
		if mine ~= waiting or serverOn then
			return
		end
		local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
		local rate = arrived - last
		last = arrived
		if root and not root.Anchored and rate < SETTLE and os.clock() - t0 >= MIN_COVER then
			break
		end
	end
	if mine == waiting and not serverOn then
		show(false)
	end
end
remote.OnClientEvent:Connect(function(on)
	serverOn = on
	if on then
		waiting += 1
		show(true)
	else
		task.spawn(liftWhenSettled)
	end
end)
cover.BackgroundTransparency, label.TextTransparency = 0, 0 -- the join: covered at once
task.spawn(liftWhenSettled)
