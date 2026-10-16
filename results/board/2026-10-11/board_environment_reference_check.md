# 已归档板端环境与 Base 版本核对

接收日期：2026-10-11，Asia/Shanghai。原始 JSON 均逐字节复制，源文件及归档 SHA256 一致。

|字段|原报告结果|
|---|---|
|板型配置 BOARD|Pynq-Z2；这不是 PCB 修订读取|
|PYNQ|3.0.1|
|Python|3.10.4，GCC 11.2.0|
|内核|5.15.19-xilinx-v2022.1|
|系统|PynqLinux 3.0，基于 Ubuntu 22.04|
|架构|armv7l|
|MemTotal|505428 kB|
|软件可见 PL IP|21|
|当前 bitfile|/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit|

## 官方源码匹配

板端 base.tcl、build_bitstream.tcl、build_ip.tcl、check_timing.tcl 的 SHA256 均与固定 v3.0.1 / 93ddd21ab623883590a8c8b07f0b157b2855da4b 的 Pynq-Z2 原件一致。base.tcl 声明工具为 Vivado 2022.1。base.bit 和 base.hwh 的板端哈希已保存，但这两个生成文件不在本地源码快照，不能声称已与发布方的独立二进制哈希比较。

|Base 文件|字节数|板端 SHA256|
|---|---:|---|
|base.bit|4045672|ecabdcb5d483c75335ab6f043824a2386971c7b0ffd6e3315f24860bf5088eb6|
|base.hwh|4558197|cbd90c84f3a46d1eba95dff7ba7d0079812f7e46641a08e2318c9928cd36ce8f|
|base.tcl|250857|e88b88b4b3e2a9c4d0856c37a26ef8550303a3f9ccddfd5c521e3f9d5d8bc8ff|
|build_bitstream.tcl|1656|6c42c887af247dd0408acc4feb71e0291e6a5edb445fa5f3a32df45078ef831d|
|build_ip.tcl|2167|72f904ef433041227375df88377b3e4fcae335b6bbb951cb21c2ac68551e1fd6|
|check_timing.tcl|560|5d26280da8cf07539313884d01f61a44c29be40c00829298acac9ecacae4ab9c|


## IP 地址基线

下面地址来自采集的 PL.ip_dict，仅属于当前官方 Base；新 A0 地址仍需实际 Tcl/BD/HWH 验证。

|IP|VLNV|地址|
|---|---|---|
|switches_gpio|xilinx.com:ip:axi_gpio:2.0|0x41200000|
|btns_gpio|xilinx.com:ip:axi_gpio:2.0|0x41210000|
|video/hdmi_in/frontend/axi_gpio_hdmiin|xilinx.com:ip:axi_gpio:2.0|0x41220000|
|video/hdmi_out/frontend/hdmi_out_hpd_video|xilinx.com:ip:axi_gpio:2.0|0x41230000|
|rgbleds_gpio|xilinx.com:ip:axi_gpio:2.0|0x41240000|
|leds_gpio|xilinx.com:ip:axi_gpio:2.0|0x41250000|
|system_interrupts|xilinx.com:ip:axi_intc:4.1|0x41800000|
|video/axi_vdma|xilinx.com:ip:axi_vdma:6.3|0x43000000|
|audio_codec_ctrl_0|xilinx.com:user:audio_codec_ctrl:1.0|0x43c00000|
|video/hdmi_out/frontend/axi_dynclk|digilentinc.com:ip:axi_dynclk:1.0|0x43c10000|
|video/hdmi_out/frontend/vtc_out|xilinx.com:ip:v_tc:6.2|0x43c20000|
|video/hdmi_in/frontend/vtc_in|xilinx.com:ip:v_tc:6.2|0x43c30000|
|video/hdmi_in/pixel_pack|xilinx.com:hls:pixel_pack:1.0|0x43c40000|
|video/hdmi_in/color_convert|xilinx.com:hls:color_convert:1.0|0x43c50000|
|video/hdmi_out/color_convert|xilinx.com:hls:color_convert:1.0|0x43c60000|
|video/hdmi_out/pixel_unpack|xilinx.com:hls:pixel_unpack:1.0|0x43c70000|
|trace_analyzer_pmodb/axi_dma_0|xilinx.com:ip:axi_dma:7.1|0x80420000|
|trace_analyzer_pi/axi_dma_0|xilinx.com:ip:axi_dma:7.1|0x80430000|
|trace_analyzer_pi/trace_cntrl_64_0|xilinx.com:hls:trace_cntrl_64:1.4|0x83c10000|
|trace_analyzer_pmodb/trace_cntrl_32_0|xilinx.com:hls:trace_cntrl_32:1.4|0x83c20000|
|ps7_0|xilinx.com:ip:processing_system7:5.5|不适用|


## 证据边界与后续

原始 captured_utc 是 2022-10-22T00:18:38.324441+00:00，板端时钟尚未同步到当前日期；保留原值，接收时间单独记录为 2026-10-11，不用板端旧时钟推断真实测试日期。

原始 100 帧 JSON 的 screen_observation 仍是 PENDING_USER_CONFIRMATION，这是指导代码写入的占位值；用户随后已通过聊天确认“都很正常”，真实观察另记在 HDMI 验证记录，不能修改原始 JSON 来补造结果。

独立 AXI DMA 仍未构建/未测试。当前 Base 有两个 Trace DMA 实例，静态设计仅支持 S2MM，不能代替拟议双向 loopback。当前 21 个软件可见实例也不能直接等同于 Vivado BD 中所有 IP。

PCB 修订仍未知；后续新工具先进行 Windows 主机运行验证，再构建 A0，医学算法 RTL 尚未进入开发。

原始报告：[board_environment.json](board_environment.json)、[hdmi_framebuffer_100_frames.json](hdmi_framebuffer_100_frames.json)。文件清单与对比：[board_report_archive_manifest.json](board_report_archive_manifest.json)。
