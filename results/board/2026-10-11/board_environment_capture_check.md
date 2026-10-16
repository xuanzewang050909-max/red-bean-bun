# 板端环境采集执行记录

日期：2026-10-11，Asia/Shanghai。

用户提供环境采集 Notebook 完成输出截图：PYNQ 3.0.1、Python 3.10.4（GCC 11.2.0）、内核 5.15.19-xilinx-v2022.1、MemTotal 505428 kB、软件可见 PL IP 21 个，末尾 `Saved: board_environment.json`。可见 Base bit/HWH/Tcl 等六个文件的大小和 SHA256。完整哈希等待原始 JSON 下载，不从换行截图拼接填入。

采集脚本把无法读到的 /proc/device-tree/model 字段输出为 None。因此 Board: None 表示这个采集字段为空，不能据此判定错误开发板或硬件故障；PCB 修订版仍需实体丝印。软件可见 IP 数不是 Vivado BD 所有层级 IP 数。

当前有执行成功截图，完整 board_environment.json 尚未取得；hdmi_framebuffer_100_frames.json 也尚未取得。用户接下来从同一 base/board 文件列表下载这两个生成文件，保留原始字节供归档和分析。未重新加载 FPGA 或执行新 DMA 测试。

证据：[环境采集完成输出](board_environment_capture_user_screenshot.png)、[截图可读字段](board_environment_screenshot_observations.json)。
