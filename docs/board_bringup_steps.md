# PYNQ-Z2 到板后的详细验证步骤

用户已确认板卡到手；PCB修订、SD镜像、网络及显示器连接尚未确认。本文提供操作步骤，所有真机结果仍待执行和记录。当前本机工具是Vivado 2017.4；这一轮使用板端镜像自带的官方Base Overlay，先确认实际PYNQ版本，再决定派生工程的工具和Tag。

现场后续：原卡启动失败且包含不匹配的Zynq-7015配置，已转为准备官方PYNQ-Z2 v3.0.1预构建镜像；用户要求先备份原卡。当前准备文件、备份状态与写卡边界见[写卡前准备记录](sd_image_preparation.md)，尚未写卡或成功启动。

执行副本：[board_validation.ipynb](../notebooks/board_validation.ipynb)。将它与环境采集脚本上传到板端同一目录，在Jupyter中按顺序逐单元执行，Markdown中的接线/观察步骤也需要完成。Notebook没有预填运行结果，不能使用Run All跳过观察；最后的停止单元要在完成屏幕记录后执行。

## 1. 准备与接线

需要：PYNQ-Z2、带PYNQ-Z2镜像的MicroSD卡、可传数据的MicroUSB线、网线、Windows电脑。HDMI测试另需HDMI线和带HDMI输入的显示器/电视；笔记本常见HDMI口是输出口，不能直接充当显示器输入。

先关闭板上电源开关，再操作跳线和SD卡：

1. 记录板上型号及PCB修订丝印；软件无法确认实体PCB修订。
2. Boot启动跳线按板上丝印选 **SD**。
3. 使用MicroUSB供电时，Power跳线选 **USB**；MicroUSB连接 **PROG-UART** 口。选择有数据功能的线。
4. 使用符合手册的外接电源时，Power跳线选 **REG**。手册推荐12V、中心正极，先核对电源标签及接口规格。
5. 插入已有PYNQ-Z2镜像的MicroSD卡；已有镜像先保留，先尝试启动。
6. 网线接板卡和路由器LAN口，或接电脑的以太网口。
7. HDMI线接板卡 **HDMI OUT** → 显示器HDMI输入，并在显示器菜单选对应输入。

没有显示器时先完成启动、网络和GPIO；HDMI相关项记录“等待显示器”。此轮不需要HDMI IN输入源。

如果SD卡为空：从[官方板卡镜像页面](https://www.pynq.io/boards.html)的 **PYNQ-Z2** 条目选择镜像，记录版本、下载链接及镜像文件哈希。当前页面Z2在Previous downloads下列出v3.1.1/v3.0.1；不能把其他型号或PYNQ v4镜像写入Z2。解压后使用镜像写入工具将整个镜像写到SD卡并校验，不是把img复制为普通文件。写入会覆盖该卡全部内容，先备份，并按容量/盘符确认目标是MicroSD卡。Windows写完提示格式化Linux分区时选择取消。选用新镜像会影响后续Vivado版本选择，不要因为本机已有2017.4而把新镜像假定为兼容。

接线依据：[PYNQ-Z2官方启动指南](https://pynq.readthedocs.io/en/v2.6.1/getting_started/pynq_z2_setup.html)、[本地TUL手册](../references/board/pynqz2_user_manual_v1_0.pdf)。启动指南版本仅用于通用接线；实际软件以板端为准。

## 2. B00：上电与串口

接线完成后开启板上电源开关，等待约1–2分钟。先观察电源灯，随后观察DONE灯；启动动画因镜像而异。电源/DONE灯不能单独证明Linux、网络或HDMI已经正常。

Windows打开“设备管理器 → 端口(COM和LPT)”，观察连接前后新增的USB Serial Port及COM号。若出现两个FTDI接口，选择串口接口；没有输出时检查另一个新增串口及线材，不猜固定COM号。用PuTTY/Tera Term等串口终端连接：

|设置|值|
|---|---|
|连接类型|Serial|
|串口|设备管理器实际显示的COM号|
|波特率|115200|
|数据位/停止位|8 / 1|
|校验/流控|None / None|

按Enter查看登录提示。未经修改的官方镜像通常使用用户名`xilinx`、密码`xilinx`；输入密码时不显示字符。卖家定制镜像按其实际账号。要记录完整启动日志，可在正常关机后打开终端日志，再重新上电。

登录后在**板端串口终端**执行：

```bash
hostname
hostname -I
ip -4 addr show
cat /etc/os-release
uname -a
free -m
```

记录有线网口的IPv4地址，避免误用localhost或其他网口地址。可在同一终端查看监听端口：

```bash
sudo ss -ltnp
```

通过标准：实际进入Linux并能运行命令；保留启动日志及IP。`free -m`可用内存会低于DDR标称容量，不据此改PS DDR配置。无电源灯检查供电/Power跳线/开关；有电源灯而无启动日志检查数据线、COM接口、SD启动跳线及SD镜像。

## 3. B01：网络与Jupyter

### 方法A：路由器连接（优先）

板卡网线接路由器LAN口，电脑接同一路由器的Wi-Fi或LAN。在串口`ip -4 addr show`或路由器DHCP租约页查看板卡实际IP，电脑浏览器访问`http://实际IP`。部分旧镜像用`http://实际IP:9090`；最终以板端服务监听和镜像文档为准。

Windows PowerShell可检查网络，先将示例变量改为实际IP：

```powershell
$boardAddress = '192.168.1.123' # 示例；替换成串口查到的板卡IP
ping $boardAddress
Test-NetConnection -ComputerName $boardAddress -Port 80
Test-NetConnection -ComputerName $boardAddress -Port 9090
```

### 方法B：电脑与板卡网线直连

仅在板端确认仍使用官方默认静态地址`192.168.2.99`时，才按以下地址操作：

1. Windows按Win+R，输入`ncpa.cpl`。
2. 找到接板卡的以太网/USB网卡，先记录其原来的IPv4设置。
3. 打开“属性 → Internet协议版本4”，电脑IP设`192.168.2.1`，子网掩码`255.255.255.0`；这条直连网卡的网关和DNS留空。
4. 访问`http://192.168.2.99`；旧镜像可能为`http://192.168.2.99:9090`。
5. 测试完成后，按记录恢复这张网卡原设置；不要改Wi-Fi或其他网卡。网段冲突时先核对路由，不盲目关闭全部网络。

MicroUSB提供串口/JTAG和相应供电；本步骤的浏览器网络连接走Ethernet。直连没有互联网也可运行镜像内的官方Demo。

Jupyter登录使用镜像实际凭据，未经修改的官方镜像常为`xilinx`。新建Python 3 Notebook，命名`retina_board_check.ipynb`。以下Python代码均在**板端Jupyter Notebook**分单元执行，Shift+Enter运行；不要在Windows Python执行。

```python
import os
import sys
import platform
import pynq

print("PYNQ:", pynq.__version__)
print("Python:", sys.version)
print("Linux:", platform.platform())
print("BOARD:", os.environ.get("BOARD"))
```

将电脑上的[collect_board_environment.py](../scripts/collect_board_environment.py)通过Jupyter Upload上传到该Notebook所在文件夹，在独立单元执行：

```python
%run collect_board_environment.py --output board_environment.json
```

下载生成的`board_environment.json`到电脑，补充实体PCB丝印。此脚本采集安装Base文件哈希、版本等信息，不加载Overlay。BOARD环境变量为空时进一步核对SD镜像来源及板端设备树，不能只凭变量推断板型。

通过标准：Jupyter能执行板端Python并输出实际PYNQ版本、生成环境报告。如果ping通而网页不通，查看`ss -ltnp`的80/9090监听及服务日志；如果只有主机名不通则使用实际IP。先保留报错，不运行全系统/全部包升级来尝试修复。

## 4. 加载官方Base并保存IP元数据

先关闭其他会控制PL的Notebook：停止其硬件任务并关闭对应Kernel。整个测试使用一个Notebook，避免另一个Kernel重新下载Overlay后使旧对象失效。

```python
from pynq.overlays.base import BaseOverlay
base = BaseOverlay("base.bit")
print("Loaded:", base.is_loaded())
print("Bitstream:", base.bitfile_name)
print("IPs:", sorted(base.ip_dict.keys()))
```

`base.bit`由板端BaseOverlay类解析镜像内配套文件；无需上传电脑参考目录里的bitstream。

```python
import json
from pathlib import Path
Path("base_ip_dict.json").write_text(
    json.dumps(base.ip_dict, indent=2, default=str), encoding="utf-8"
)
```

通过标准：`Loaded: True`且无异常，保存实际bitstream路径、IP清单、Notebook。v2.2.1可能使用Tcl元数据，较新版本通常使用HWH；不要混用文件。若报BaseOverlay导入错误或元数据/IP缺失，先记录完整报错和版本，检查原镜像配套文件。

## 5. B02：LED、按钮、开关

先执行流水灯，观察4个普通用户LED逐个亮灭（不包括电源灯、DONE灯和两个RGB灯）：

```python
import time

for i in range(4):
    base.leds[i].off()
for cycle in range(2):
    for i in range(4):
        base.leds[i].on()
        print("LED", i, "ON")
        time.sleep(0.7)
        base.leds[i].off()
print("LED sequence finished; verify physical observations")
```

按钮/开关读数在另一个单元反复运行：

```python
print("Buttons:", [base.buttons[i].read() for i in range(4)])
print("Switches:", [base.switches[i].read() for i in range(2)])
```

先不按任何按钮记基线，再按住一个用户按钮运行单元，逐个检查对应位置变化及释放恢复；逐个切换两个拨码开关。不要把电源开关或复位按钮当作用户输入。

通过标准：4个用户LED均可控制，4个按钮和2个开关均有对应变化。打印“ON”仅证明代码运行，必须记录现场亮灭。也可复制镜像内`base/board/board_btns_leds.ipynb`逐单元运行，保存原始副本及执行副本；运行其他Notebook前先关闭本Kernel。

## 6. B03：HDMI静态色条

确认显示器接HDMI OUT并选对输入。继续使用同一Notebook里的`base`，以720p60、24bit BGR配置：

```python
from pynq.lib.video import VideoMode, PIXEL_BGR

hdmi_out = base.video.hdmi_out
mode = VideoMode(1280, 720, 24)
hdmi_out.configure(mode, PIXEL_BGR)
hdmi_out.start()

frame = hdmi_out.newframe()
print("Shape:", frame.shape, "dtype:", frame.dtype,
      "strides:", frame.strides,
      "physical_address:", getattr(frame, "physical_address", None))
frame[:, :426, :] = [255, 0, 0]    # BGR: 蓝
frame[:, 426:853, :] = [0, 255, 0]  # 绿
frame[:, 853:, :] = [0, 0, 255]    # 红
hdmi_out.writeframe(frame)
```

观察至少30秒，正常画面从左到右为蓝、绿、红三条。保存显示器实际画面和其识别到的模式。该单元不要立即调用`stop()`，下一步连续帧测试还要使用输出。驱动接收`writeframe`的缓冲所有权，提交后不要修改或手动释放该帧。

通过标准：实际屏幕稳定显示正确色条，无反复断信号、明显闪烁或错色。仅代码无异常不能记HDMI PASS。

如果720p无信号，先检查HDMI OUT、显示器输入、线材及是否有另一Kernel加载PL。记录失败后，在独立单元`hdmi_out.stop()`，把原色条单元的`mode = VideoMode(1280, 720, 24)`改为`mode = VideoMode(640, 480, 24)`，色条分界426/853改为213/426，然后重新运行色条单元。这样下一步尺寸也沿用新模式。若只有640×480通过，分别记录模式结果，不把720p也记通过。

调用长时间无返回时，记录卡在哪一行及Kernel状态，先尝试Kernel Interrupt；保存日志后若无法恢复，可串口正常关机、重新启动并从Base加载开始。不要反复在忙碌Kernel叠加HDMI start/下载Overlay。

API依据：[官方HDMI输出层](https://github.com/Xilinx/PYNQ/blob/v3.0.1/pynq/lib/video/hierarchies.py)、[官方VDMA帧缓存驱动](https://github.com/Xilinx/PYNQ/blob/v3.0.1/pynq/lib/video/dma.py)。本项目也已审查旧v2.2.1 API；实际执行以板端匹配版本为准。

## 7. B04：连续100帧与DDR帧缓存

静态色条通过后，在同一Notebook另一个单元执行。若已经停止输出，先重新配置并start；以下默认沿用上一步正在运行的模式：

```python
from datetime import datetime, timezone

submitted = []
started = time.monotonic()
height, width = mode.height, mode.width
for n in range(100):
    f = hdmi_out.newframe()
    f[:] = [((n // 10) % 3) * 80, 40, 40]
    x = int(n * (width - 64) / 99)
    f[:, x:x+64, :] = [255, 255, 255]
    # 底部7个方块用二进制编码帧序号，方便区分连续帧
    for bit in range(7):
        f[-40:, bit*40:(bit+1)*40, :] = 255 if ((n >> bit) & 1) else 0
    submitted.append({
        "n": n, "shape": list(f.shape), "strides": list(f.strides),
        "physical_address": getattr(f, "physical_address", None)
    })
    hdmi_out.writeframe(f)
    time.sleep(0.05)

elapsed = time.monotonic() - started
Path("framebuffer_submit_log.json").write_text(json.dumps({
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "submitted_frames": len(submitted), "elapsed_seconds": elapsed,
    "screen_observation": "TO_BE_RECORDED_BY_OPERATOR",
    "frames": submitted
}, indent=2, default=str), encoding="utf-8")
print("Submitted:", len(submitted), "frames; seconds:", elapsed)
```

通过标准：100帧提交完成，屏幕白条从左向右移动，背景/底部序号图案变化，结束后最后一帧稳定；无花屏、异常或长期卡住，保留提交日志及现场观察。缓冲地址重复可能是官方驱动正常复用，不是错误。日志只记录软件提交，不能替代屏幕观察，也不能证明每个扫描帧都无丢失。

这是官方PS→DDR→VDMA→HDMI输出通路验证，含主动限速；计时不是医学算法FPS，也不是独立AXI DMA双向测试。没有HDMI输入源时，RX/tie/pipeline测试保持“等待输入源”。

完成观察后，在**单独单元**清理：

```python
hdmi_out.stop()
for i in range(4):
    base.leds[i].off()
```

## 8. B05：独立AXI DMA，等待A0构建

目前项目没有可运行的A0 bitstream/配套元数据；已有Base Trace DMA关闭了MM2S，不能拿它宣称双向loopback通过。本项当前写 **WAITING_A0_BUILD**，收到板端环境报告后再匹配版本构建。

后续A0路径：官方Z2 PS/DDR → 标准AXI DMA(MM2S) → AXIS FIFO → DMA(S2MM) → DDR，独立于HDMI。构建验证完成后交付确切文件、IP实例名与对应版本运行Notebook；测试按以下顺序：

1. 核对Simple模式、MM2S/S2MM、32bit流、足够长度寄存器和正确TLAST。
2. 用匹配版本`allocate`或旧`Xlnk`分配连续缓冲，先启动接收再发送。
3. 先5个uint32递增值，再常量/固定种子随机数据，逐元素比较。
4. 验证256×256、512×512个uint32；后者为1,048,576字节。
5. 重复至少100包/帧，记录字节数、输入/输出哈希、DMA状态及超时。
6. 保留失败、恢复和重新加载记录。只有真实返回且比对一致才能通过。

## 9. 保存证据、结果与正常关机

保存并下载执行过的Notebook、`board_environment.json`、`base_ip_dict.json`、`framebuffer_submit_log.json`、启动日志、PCB丝印记录及显示照片。电脑侧建议存到项目`results/board/<实际日期>/`，原始官方Notebook保留一份，执行副本另存。

|项目|填写结果|
|---|---|
|PCB修订/SD镜像来源|实际丝印/来源；未知项写未知|
|板端PYNQ版本/IP|实际输出|
|B00启动|PASS/FAIL/NOT_EXECUTED + 日志|
|B01 Jupyter/Base|PASS/FAIL/NOT_EXECUTED + Notebook/环境JSON|
|B02 LED/按钮/开关|逐项现场观察及读数|
|B03 HDMI|各分辨率结果；无显示器写WAITING_DISPLAY|
|B04连续帧|提交日志 + 实际屏幕观察|
|B05独立DMA|目前WAITING_A0_BUILD|

全部观察结束，先stop HDMI、保存Notebook，再在板端串口/Jupyter终端执行`sudo shutdown -h now`。等待系统关机停止访问SD，再关闭板上电源；不要在运行中拔SD卡。

需要反馈的最小集合：PYNQ版本、PCB丝印、板卡IP、Base是否加载、LED/按钮/开关结果、HDMI色条与100帧结果；失败时提供完整报错和卡住的步骤。收到真实记录后再更新[demo_status.json](../results/audit/demo_status.json)，不根据“板卡到手”自动将任何测试标PASS。
