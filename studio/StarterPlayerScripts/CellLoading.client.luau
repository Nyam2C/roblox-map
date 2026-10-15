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

local fade = TweenInfo.new(0.25)
remote.OnClientEvent:Connect(function(on)
	TweenService:Create(cover, fade, { BackgroundTransparency = on and 0 or 1 }):Play()
	TweenService:Create(label, fade, { TextTransparency = on and 0 or 1 }):Play()
end)
