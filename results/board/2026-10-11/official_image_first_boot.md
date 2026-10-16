# 官方镜像首次启动证据

记录日期：2026-10-11，Asia/Shanghai。

用户在写入并检查官方 PYNQ-Z2 v3.0.1 镜像后提供 PuTTY 截图：窗口标题为 `COM9 - PuTTY`，终端显示两行 `xilinx@pynq:~$` 提示符。

结论：板卡 Linux 已启动并进入可交互的串口命令行，启动检查记为 PASS（用户现场截图证据）。没有取得完整启动日志，也没有远程执行板端命令。

已写入镜像的版本标识为 v3.0.1；运行中的 PYNQ 包版本、内核版本、PCB 修订版和板端网络地址仍待采集。截图中的主机名是 pynq，不能据此推断可用 IP 或网络连接状态。

Jupyter/Base Overlay、GPIO LED、HDMI、视频帧缓冲和独立 DMA 均尚未验证。

证据：[串口提示符截图](pynq_uart_shell_user_photo.png)。前期串口空白和原卡不匹配是历史失败，保留于 [首次启动排查](first_boot_check.md)。新卡写入比对结果见 [校验差异说明](../../../docs/sd_verification_diagnosis.md)。

## 运行版本和地址确认

用户随后提供命令执行截图：第一次因属性名拼写错误得到 AttributeError，改为 `pynq.__version__` 后输出 `3.0.1`；`hostname -I` 输出 `192.168.2.99`。因此运行中的 PYNQ 包版本确认是 3.0.1，板端当前报告的 IPv4 地址是 192.168.2.99。错误已更正，不代表安装损坏。该地址输出不证明网线连接或网页可达。

主机当前检测到 Realtek PCIe GbE Family Controller，接口名称“以太网”，状态 Disconnected；WLAN 在线。用户确认有网线，下一步选择官方支持的电脑网口直连方案。尚未修改主机网络设置，也未访问 Jupyter。证据：[版本和地址截图](pynq_version_ip_user_photo.png)。
