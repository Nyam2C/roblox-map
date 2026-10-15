-- Every player's map position for the others (2026-10-15): a character far away is not streamed to a client, so the server writes
-- MapX and MapZ (studs) on each Player every half second; Player objects reach every client (StarterPlayerScripts/MinimapClient).
local Players = game:GetService("Players")

while true do
	for _, p in ipairs(Players:GetPlayers()) do
		local root = p.Character and p.Character:FindFirstChild("HumanoidRootPart")
		if root then
			p:SetAttribute("MapX", math.floor(root.Position.X))
			p:SetAttribute("MapZ", math.floor(root.Position.Z))
		end
	end
	task.wait(0.5)
end
