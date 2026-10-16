# Run in the same live HDMI notebook kernel before closing HDMI.
import time
import json
from pathlib import Path

height, width = hdmi_out.mode.height, hdmi_out.mode.width
submitted = 0
for n in range(100):
    f = hdmi_out.newframe()
    f[:] = [40, 40, 40]
    x = n * (width - 64) // 99
    f[60:height - 60, x:x + 64, :] = [255, 255, 255]
    hdmi_out.writeframe(f)
    submitted += 1
    time.sleep(0.05)

Path("hdmi_framebuffer_100_frames.json").write_text(
    json.dumps({"submitted_frames": submitted, "width": width,
                "height": height, "screen_observation": "PENDING_USER_CONFIRMATION"}, indent=2)
)
print("Submitted", submitted, "frames.")
