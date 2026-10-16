# 官方Demo验证计划与记录规范

## 当前实验验证入口（2026-10-13）

按 [用户方案变更](requirements_update_2026-10-13.md)，实验和最终展示均采用PYNQ-Z2+以太网+Windows浏览器。HDMI显示器、HDMI输入源及B03/B04视频回归不再是当前条件，不再运行显示专用Notebook或继续优化720p画布；旧证据保留。原计划完整字节另存 [previous_demo_validation_plan.md](../results/browser_transition_2026-10-13/previous_demo_validation_plan.md)。

已有启动/PYNQ3.0.1/Jupyter/GPIO、A0–A4及B的板测不重复作为到板前置。当前直接复用已测A4精简包和官方驱动；新应用仍核对实际bit/HWH/SHA、DMA/GPIO地址/驱动/缓冲/配置，不把旧PASS转移给新服务。

新的分阶段操作是：W1真实DMA输出→浏览器四图/帧证据；W2派生可调阈值/参数快照/周期并新仿真/实现/板测；W3完整交互导出；W4原精度/CPU/分段性能实验；W5长时稳定和完整交付。每次给用户完整可执行步骤并保存执行Notebook/原JSON/数组/客户端时序/截图/失败，不先要求HDMI输出。详见 [计划](browser_development_plan.md)、[API](browser_api_contract.md)、[验收](browser_acceptance.md)及 [机器状态](browser_contract.json)。

PL核心/传输/推理/浏览器时间分别原样采集，缺项null；DMA/PL重叠、PS/PC时钟域及rAF近似写清。精度保持M0默认28和STARE划分，GT只读真实掩膜后评价；生产无CPU计算回退。原A4尚不支持可调阈值/周期，W1不能使相关最终验收通过。

## 早期官方Demo计划与历史记录（非当前HDMI开发要求）

以下保留原参考内容；其中要求显示器/HDMI及“尚未完成”的阶段状态只代表原计划时间，不用于当前实验前置或当前阶段判断。

**当前状态：启动、PYNQ3.0.1、Jupyter/Base、GPIO、HDMI及输出100帧已在用户板上验证并归档。** PCB修订仍待核对。独立DMA A0已用2017.4生成bit/HWH并通过主机时序/元数据检查，r2板测17字短包及完整70次已通过，执行Notebook/JSON已归档复核；见 [A0验证步骤](a0_dma_validation_steps.md)。本文是验收规范，真实证据与机器状态见 [demo_status.json](../results/audit/demo_status.json)。上游Notebook自带输出不能当作本机执行结果。

## 1. 到板后先采集版本

检查实体板丝印/PCB修订、DDR颗粒、启动/供电跳线，按原手册确认SD启动；记录电源、USB UART/JTAG、网线、HDMI OUT显示器和可选HDMI IN输入源。使用实际发现的主机名/IP，不扫描或猜测设备。

在板端Python执行以下只读采集，不加载bitstream：

```bash
python3 collect_board_environment.py --output board_environment.json
```

脚本位置：[collect_board_environment.py](../scripts/collect_board_environment.py)。记录`pynq.__version__`、Python/Linux、设备树、安装Base bit/HWH/Tcl哈希、当前PL元数据。PCB修订必须从实体板确认，软件报告留空。环境采集成功不代表HDMI/GPIO/DMA测试通过。

依据实测镜像固定对应Tag/工具版本。优先使用**板端该镜像自带Base bit和配套元数据/驱动**跑原Demo；不要先替换为本机2017.4重新生成的设计。v2.2.1快照有上游`base.bit`，它仅是原始参考，不是本项目生成物，也不是较新镜像的通用替代品。

## 2. 官方Notebook与运行条件

|测试|原始Notebook/依据|条件|必须保留的证据|
|---|---|---|---|
|B00启动|TUL User Manual、匹配镜像启动|板、电源、SD、UART|PCB照片记录、启动日志、镜像/版本|
|B01 Jupyter/Base访问|镜像内BaseOverlay，官方board/video Notebook|网络可访问|Jupyter访问记录、版本、bit/HWH哈希、IP清单|
|B02 GPIO|`boards/Pynq-Z2/base/notebooks/board/board_btns_leds.ipynb`|实体LED/按钮/开关|实际LED状态、按键/开关读数、时间戳、执行后Notebook|
|B03 HDMI输出|`video/hdmi_introduction.ipynb`输出部分|显示器接HDMI OUT|模式/像素格式、显示照片或现场记录、异常/无输入项|
|B04帧缓存|同Notebook的newframe/writeframe；`hdmi_video_pipeline.ipynb`|输出至少需要显示器；完整RX还需要输入源|多帧顺序、图案、缓冲物理地址/stride、超时/状态|
|B05双向DMA|PYNQ `docs/source/pynq_libraries/dma.rst` 的loopback；标准DMA+FIFO|A0 bit/配套元数据、实体板|输入输出哈希、逐元素比对、长度、重复次数、DMA状态/耗时|

对应原文件已按Tag保存。v2.2.1的Z2目录部分Notebook是官方指向共享Z1 Notebook的symlink，Windows快照保留原链接文本及目标文件；运行镜像原Notebook或manifest的`canonical_source`，不要把链接文本当JSON。共享Notebook不表示使用Z1硬件配置。

OpenCV filter Notebook中的CPU算法仅验证示例显示/操作，不作为PL医学分析的性能证据。USB webcam示例需要相机；未连接时写“等待相机”，不替换成假视频后宣称原例通过。

## 3. GPIO与显示的最小调用

以下为匹配版本原Base的API使用方式，须在确认板卡、镜像和官方原文件后执行；不是本阶段运行记录。精简后RetinaOverlay不能原样使用此BaseOverlay类。

```python
from pynq.overlays.base import BaseOverlay
base = BaseOverlay("base.bit")
base.leds[0].on()
base.leds[0].off()
print([button.read() for button in base.buttons])
print([switch.read() for switch in base.switches])
```

用原Notebook逐一核对4个LED、4个按钮和2个开关。不直接操作未知PS GPIO编号，不把HPD当LED输出测试。普通LED位于AXI GPIO驱动，RGB按原例颜色次序。

HDMI输出沿用官方API，首选受支持的720p60 BGR模式：

```python
from pynq.lib.video import VideoMode, PIXEL_BGR
hdmi_out = base.video.hdmi_out
hdmi_out.configure(VideoMode(1280, 720, 24), PIXEL_BGR)
hdmi_out.start()
frame = hdmi_out.newframe()
frame[:] = 0
frame[:, :426, :] = [255, 0, 0]      # BGR: 蓝
frame[:, 426:853, :] = [0, 255, 0]   # 绿
frame[:, 853:, :] = [0, 0, 255]      # 红
hdmi_out.writeframe(frame)
```

观察并记录实际色条和稳定画面，完成连续帧验证后，在**独立单元**执行`hdmi_out.stop()`。不要在首次提交色条的同一单元立即停止输出。

若版本API不同，使用对应Tag/板端Notebook，不把新驱动移植到旧镜像强行运行。建议先640×480或720p确认稳定，再评估更高模式。把代码成功执行与显示器实际有画面分开记录。

## 4. 帧缓存专项验证

先静态色条，随后连续写不同灰度/颜色/帧序号测试画面至少100帧，记录实际提交顺序和屏幕稳定性。确认`newframe`尺寸/stride、物理地址和完整范围符合所属版本DDR窗口。确认提交后缓冲归官方驱动管理，不提前释放或覆盖正在显示的帧。

需要HDMI输入时，单独记录输入源分辨率和连接情况，运行官方输入/输出tie及pipeline例。没有输入源只能通过输出帧缓存测试，完整双向pipeline仍“等待输入源”。显示60Hz不代表医学分割60FPS。

## 5. 独立DMA A0的验收

构建内容为Z2 PS、双向Simple AXI DMA、标准AXIS FIFO、AXI-Lite互连与reset，使用本板preset。现成Trace DMA的MM2S关闭，不直接拿它做双向验证。

配置至少包括：SG=0、MM2S/S2MM开启、AXIS32位、PS HP64位、长度23位、按对齐要求分配缓冲。需要测试5个uint32短包、256×256和512×512整帧；512整帧长度是1,048,576字节。

先提交接收缓冲，再提交发送缓冲，避免输出无人接收导致背压。输入使用递增、常量、固定种子随机向量，不用GT。输出逐元素一致，记录双方字节数/CRC或SHA256。至少100连续帧；每次使用或确认正确的TLAST，不能因为第一帧成功就宣称多帧通过。

使用该版本PYNQ官方`allocate`/`Xlnk`及DMA驱动。设置可见超时并记录DMA寄存器/状态；不要永远阻塞在wait。处理cache flush/invalidate并验证物理地址窗口。恢复按官方DMA reset/Overlay重新加载方法；错误日志保留后再重试，不把失败记录覆盖。

A0已完成2017.4主机构建，此项状态为“HOST_BUILD_COMPLETE_WAITING_BOARD_TEST”。板端PYNQ3.0.1执行70次收发，核对全部返回字和收发长度并下载原始JSON/Notebook后再更新。之后算法接入A0时另开测试ID，loopback通过不等于算法通过。

## 6. 原始文件和实测记录

参考原件保持`references/`只读；运行副本放`results/board/<日期>/<测试ID>/`，保存：

```text
environment.json         # 镜像/工具、PCB、设备、bit/元数据哈希
original_notebook.ipynb  # 所用原始副本和来源Tag/Commit
executed_notebook.ipynb  # 本次实际执行输出
test_code.py             # 如果有额外测试，精确保留
run.log                  # 实际开始/结束时间、输出、失败及恢复
test_result.json         # PASS/FAIL/WAITING_HARDWARE/NOT_EXECUTED
display_evidence.*       # 仅真实现场输出证据
```

单个结果JSON至少包含：ID、时间、实际版本、硬件条件、输入/输出大小和哈希、判据、观察结果、状态、日志路径及执行者。PASS必须同时有运行记录和对应判据证据；静态审查、主机仿真或保存上游输出不能转换为板级PASS。

## 7. 当前已执行范围

主机小型综合/实现、xsim、5个官方HLS模块csynth/元数据重打包、v2.2.1 Base BD及A0完整实现已执行。官方现成Base的启动、Jupyter/GPIO/HDMI/输出帧缓存已有现场证据；A0板测、派生Base完整实现和医学算法尚未完成。具体状态见[environment_report.md](environment_report.md)与[A0报告](../results/a0_dma_2017_4/build_report.md)，不需要重复源码调查或已归档的板级基线测试。
