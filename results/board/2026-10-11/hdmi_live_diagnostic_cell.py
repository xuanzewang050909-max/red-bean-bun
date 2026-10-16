# Run in the existing HDMI output notebook kernel, before closing HDMI.
print("Mode:", hdmi_out.mode)
f = hdmi_out.newframe()
print("Shape:", f.shape)
print("Type:", f.dtype, "Strides:", f.strides)
f[:] = [0, 0, 255]
hdmi_out.writeframe(f)
print("Red frame submitted; check the display.")
