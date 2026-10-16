# Run in the same live HDMI notebook kernel before HDMI close.
g = hdmi_out.newframe()
h, w, _ = g.shape
g[:, :w // 3, :] = [255, 0, 0]
g[:, w // 3:2 * w // 3, :] = [0, 255, 0]
g[:, 2 * w // 3:, :] = [0, 0, 255]

g[:12, :, :] = 255
g[-12:, :, :] = 255
g[:, :12, :] = 255
g[:, -12:, :] = 255
g[:, w // 2 - 4:w // 2 + 4, :] = 255
g[h // 2 - 4:h // 2 + 4, :, :] = 255

hdmi_out.writeframe(g)
print("Position test: BLUE | GREEN | RED, white border and centered cross.")
