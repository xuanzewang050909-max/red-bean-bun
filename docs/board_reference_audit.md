# RetinaFPGA / PYNQ-Z2 官方资源复用审查报告

**当前阶段（2026-10-12）：A3实体板45帧已独立核验；A4完整冻结分割已完成主机及实体板61帧验证。** A4继续使用已测A3的PS/DDR/DMA/GPIO/FIFO/100MHz/reset和帧guard，未增加板级引脚。原厂Threshold、零边界CROSS形态学、邻域Filter2D直接复用，安装库未改；十个复用BD模块与已测A3逐项一致。正确第二次Csim/真实生成RTL/复位/HWH/布局布线/87项回归通过。见[A4复用审查](a4_segmentation_reuse_audit.md)、[真实构建报告](../results/a4_segmentation_2017_4/build_report.md)和[板测步骤](a4_segmentation_validation_steps.md)。PCB修订仍未知，最终B另行整合；A4板测记录与六份真实输出已独立核验归档，见[板测报告](../results/a4_segmentation_2017_4/board_execution_2026-10-12/verification_report.md)；最终B/FPS仍未验证。

**A1阶段历史（2026-10-12）：M0定点A/B参考完成真实STARE评价；按训练规则选择A，质量仍有限。A1复用A0 PS/DDR/标准DMA/FIFO/reset，新增官方AXI GPIO与绿色/LUT诊断RTL，完整2017.4主机构建及实体板17帧验证通过，真实Notebook/JSON与独立哈希核对已归档。** 见[M0报告](../results/m0_stare_2026-10-11/evaluation_report.md)、[A1主机报告](../results/a1_point_2017_4/build_report.md)、[A1板测报告](../results/a1_point_2017_4_r2/board_execution_2026-10-12/verification_report.md)。截至A1阶段未验证Gaussian/完整分割/B；后续A2/A3已板测，当前A4主机及板测通过。

**A0板测历史（2026-10-11）：A0 r2完成17字短包及70次完整DMA回环；执行Notebook与原始JSON已逐字节归档，源码/交付配对、收发字节数及71次图案哈希复核通过。** [板测归档报告](../results/a0_dma_2017_4_r2/board_execution_2026-10-11/verification_report.md)。首次失败证据另行保留；此A0历史记录不验证医学算法、最终HDMI整合及实时性能。

更新日期：2026-10-12（Asia/Shanghai）。项目路径：`D:\PLD\retina_fpga`。官方资料与主机工具审查完成；已在用户现场验证启动、Jupyter/Base、GPIO、HDMI和输出帧缓存。A0至A3的板级记录与原始失败分别保留；A4完整医学分割已有真实RTL/实现及实体板61帧证据，最终B与速度尚未验证。

**复用结论：保留官方 PS/DDR/时钟复位及 VDMA/HDMI 显示，新建独立 Simple AXI DMA 医学计算通路。** 当前运行 PYNQ 3.0.1 已由串口命令确认，Jupyter 实际端口为 9090，PCB 修订版仍待核对。主机只有 Vivado 2017.4，官方 v3.0.1 Base 对应 2022.1；现成 Base 在板上运行通过不表示主机具备匹配的重建环境。v2.2.1/2017.4 的主机 BD 验证属于另一个已固定版本的参考检查。

**用户决定先用现有2017.4，2022.1安装暂缓。** 当前A0复用TUL Z2 preset、2017.4标准IP和PYNQ3.0.1 DMA驱动；B以官方v2.2.1 Base为派生候选，逐项验证当前运行时适配。已验证的v3.0.1 Base仍保留作板级回归基线，不能将其PASS转移给新工程。

最新状态与证据见 [板级验证汇总](../results/board/2026-10-11/board_validation_summary.md)、[机器可读状态](../results/audit/demo_status.json)。HDMI 实际执行 Notebook 已逐字节归档，含 100 帧与 close 输出；板端生成 JSON 和完整环境报告也已逐字节归档，指导代码、截图及用户反馈也已保存。历史失败和异常保留于逐项记录。

## 1. 已获取的板卡资料与原理图版本

|资料|本地保存位置|识别结果|
|---|---|---|
|TUL原理图|`references/board/TUL_PYNQ_Schematic_R12.pdf`|15页；文件名R12，内部图签R10，日期2018-01-09，PDF标题含r11，不能据文件名宣称实体板R12|
|TUL User Manual|`references/board/pynqz2_user_manual_v1_0.pdf`|v1.0，31页，2018-05-17|
|TUL Master XDC|`references/board/pynq-z2_v1.0.xdc/PYNQ-Z2 v1.0.xdc`|完整官方模板，约束默认注释；不能整份盲目启用|
|TUL Board Files|`references/board/pynq-z2/pynq-z2/A.0/`|board.xml、part0_pins.xml、preset.xml；逻辑Board Part版本1.0，目录A.0不等于已核对实体PCB A.0|
|PYNQ Z2 Base / notebooks / drivers / IP|`references/PYNQ/v2.2.1/`、`v3.0.1/`、`v3.1.2/`|固定Commit原始快照，SHA256清单；未追踪master|
|可复用滤波候选|`references/xfopencv/2017.4_release/`|厂商BSD源码、152个参考文件；未构建/未板测|

原理图第3页按钮/LED，第5页Ethernet/SD，第6页HDMI，第7页USB，第8页JTAG/UART，第9页配置，第10页DDR/MIO，第11页PL Banks，第12页Bank供电，第13页DDR器件，第14–15页电源已针对使用外设研究。图纸修订历史也已查看。

资料中的DDR颗粒型号/512MB描述、TX HPD电路/官方GPIO方向存在不一致，已保留而未猜测修正。具体网络→封装脚→Vivado端口→驱动及这些疑点见[管脚对应表](board_pin_mapping.md)。板卡已到手，PCB修订与颗粒丝印仍待现场核对；A4没有新增PL外部引脚。

## 2. 当前PYNQ系统版本

**运行中的 PYNQ 包版本已实测为 3.0.1。** 已写入镜像标识为官方 PYNQ-Z2 v3.0.1，串口截图证实主机名 pynq、用户 xilinx 及 Linux shell 可用。串口 `hostname -I` 报告地址 192.168.2.99，网页登录与官方 Base 加载/GPIO 已验证，HDMI 输出及 100 帧提交已验证。完整启动日志及PCB 修订版仍待取得；独立 DMA 已通过并归档；实际 Base 哈希和 IP 地址清单已归档；运行版本依据命令输出，而非仅镜像文件名。

[只读板端环境采集脚本](../scripts/collect_board_environment.py)已由用户在板端运行，原始JSON已归档，包含版本、设备树、当前PL信息和已安装Base文件哈希。独立DMA按 [A0验证步骤](a0_dma_validation_steps.md)运行并单独记录。

## 3. Vivado环境与兼容性

实测可执行程序：`E:\vivado\Vivado\2017.4\bin\vivado.bat`，SW2086221、IP2085800。对`xc7z020clg400-1`完成小型OOC综合、布局布线与256向量xsim自检，许可证正常。详见[环境报告](environment_report.md)。

官方v2.2.1脚本声明2017.4，匹配本机；3.0.1脚本声明2022.1；3.1.2声明2024.1，本机没有后两者。PYNQ v4移除了Zynq-7000/Z2支持，不能默认最新/master可用。当前保留3.0.1镜像，选2017.4构建A0并验证兼容性；这是受控适配路线，而非原样降级v3.0.1 Base工程。配套bit/HWH、IP参数与驱动绑定均需要真实检查。

2017.4原始HLS导出发生日期溢出；本次仅在`build/`工作副本的**生成包装元数据**中改Revision，官方源码和安装目录不改。5个模块打包通过后，159-IP原Base BD重建/验证通过，有原始警告。完整Base综合/实现/bitstream生成尚未执行，3.x参考构建尚未执行。

## 4. 固定官方仓库Tag/Commit

|来源|固定Tag|Commit|用途|
|---|---|---|---|
|Xilinx/PYNQ|v2.2.1|`3d2641653c6d1a5ea55c4c41e15f9dd9a2e32ab3`|匹配2017.4的BD基线及B派生候选|
|Xilinx/PYNQ|v3.0.1|`93ddd21ab623883590a8c8b07f0b157b2855da4b`|实测运行镜像/Base和当前Python驱动参考|
|Xilinx/PYNQ|v3.1.2|`3c77124d86bab65ac7bb6beb0aa66e13c83508f2`|3.1镜像候选，2024.1结构比较|
|Xilinx/xfopencv|2017.4_release|`6e6953c20dc12de828693d6ae34bbb9a9a55ac37`|通用图像算子候选审查|

这是候选与离线参考，不是已冻结的实际镜像/工具组合。每个PYNQ快照的`SOURCE_MANIFEST.json`保留URL、Commit、时间和逐文件SHA256。共3334个已保存PYNQ文件已校验；旧Z2 Notebook使用的官方共享Z1 Notebook链接目标一并保存，**没有采用Z1的PS配置、XDC或硬件工程**。Windows上原始symlink文本保留，目标路径记录在manifest。

## 5. 官方Demo及运行状态

|检查项目|当前结果|证据范围|
|---|---|---|
|PYNQ-Z2启动|通过|COM9 Linux shell 截图|
|Jupyter/Python访问官方Base|通过|网页登录截图；用户确认 Base GPIO 实际响应|
|官方HDMI输出|通过|720p60 BGR24 软件配置，正确色条/白框/十字照片及 30 秒稳定反馈|
|官方LED/GPIO|通过|官方 Notebook 副本，用户确认按钮/LED 行为|
|官方视频帧缓存|通过（输出侧）|100 帧完成输出截图及白条移动正常反馈；不是逐帧完整性回读|
|独立双向AXI DMA|通过（r2）|17字短包与完整70次回环通过；执行Notebook/原始JSON及独立复核归档，首版失败记录保留|

Notebook原文件及现有输出仅作为上游参考保留，**不算本项目执行结果**。有些HDMI Notebook单元需要HDMI输入源；只做输出时选择官方输出单元，不能没有输入源仍写“pipeline全部通过”。Trace DMA只有S2MM，不能替代完整双向loopback结果。代码、步骤和记录模板见[Demo验证计划](demo_validation_plan.md)，机器可读状态见[demo_status.json](../results/audit/demo_status.json)。

## 6. Base Overlay硬件结构

完整分析见[base_overlay_analysis.md](base_overlay_analysis.md)，每个IP见[base_ip_inventory.md](base_ip_inventory.md)。核心为PS硬DDR、GP控制互连、HP0视频DDR访问、双向VDMA、HDMI RX/TX、GPIO、4个MicroBlaze IOP和两个Trace子系统。时钟来自PS FCLK，TX采用官方可编程像素时钟。较新版本新增部分外设互连/地址转换，不能直接按旧Base删相同根名字来假定连接相同。

PS HP0用于视频、HP2用于Trace。官方v2.2.1有159个IP，3.x有187个IP，后者仅静态统计。派生设计资源节省须通过同一工具版本实际综合前后比较，不能用IP个数估算LUT百分比。

## 7. 拟保留IP清单

首个B整合版本保留`ps7_0`的Z2 DDR/MIO配置、必要AXI互连与proc_sys_reset、HP0视频内存互连、`video/axi_vdma`、`hdmi_out`全部输出链（pixel_unpack、color_convert、register_slice、AXIS Video Out、VTC、color_swap、axi_dynclk、rgb2dvi）、GPIO交互及必要中断逻辑。首版也保留HDMI RX，使外层视频驱动结构完整。

新增算法支路复用标准AXI DMA 7.1、互连/FIFO/复位IP和PYNQ DMA驱动。各IP的实际时钟/接口、版本、是否需要修改及未测资源见逐IP表。

## 8. 拟删除IP清单

在原Base板级基线通过后，整组删除音频控制及音频时钟/辅助连接、`iop_pmoda/pmodb/arduino/rpi`及其LMB/BRAM/SPI/I2C/timer/UART/debug、`trace_analyzer_pi/pmodb`及Trace FIFO/DMA/拼接与无用共享IO控制。缩减AXI端口/地址/中断并删除对应顶层端口和XDC。

HDMI RX不是STARE文件输入所必需，但首版暂保留；实测资源需要进一步节约时再成组删除RX、S2MM相关连接及RX reset/DDC/HPD。此时必须适配视频驱动绑定，不能原样使用期望完整VideoIn/Out的VideoWrapper。精简设计也不能原样调用访问音频/IOP的BaseOverlay初始化。

## 9. 需要新增的医学模块

先进入CPU/定点规格与滤波候选验证：G通道、3×3固定高斯、LUT、局部背景增强、阈值/形态学/FOV；方向稀疏核作为质量评估后的候选。项目新增的是医疗数据布局、FOV/旁路对齐、血管响应和多模式组合、32位帧包控制、参数/状态/周期计数、bit-accurate参考及医学结果展示。

通用滤波、linebuffer和AXIS/BRAM已有候选，不直接认定所有算法零件必须从零实现。已有候选与任务书核系数、replicate边界、定点舍入和帧TLAST存在差异，先验证再复用/改造；必须采用专用RTL时记录具体原因。见[reuse_matrix.md](reuse_matrix.md)。

## 10. 基础数据通路复用方案

A最小验证：Z2 PS/DDR→标准双向Simple DMA→成熟FIFO loopback，随后接算法IP→DMA回DDR；控制用GP0+AXI-Lite。

B最终整合：从匹配Tag的Base复制工作副本，保留HP0→VDMA→官方HDMI；释放Trace后将A算法支路接HP2。PS加载图像、参数和显示画布，PL做医学计算，结果经DDR交给官方显示。B同时具备分析与显示，不能靠两次加载不同bitstream伪装实时整合。

## 11. 关键时钟、复位、AXI和像素格式

- 官方FCLK0/1/2/3分别100/142/200/100MHz；算法先用100MHz，视频保留142MHz及官方像素/5×时钟。
- PS HP0/HP2参数64位；官方VDMA MM2S memory/stream明确32位，互连处理宽度适配；保持版本默认值与验证结果。
- 医学输入低字节起B/G/R/FOV，输出G/增强/mask/响应；均32位帧包。标准DMA帧末TLAST，与视频每行TLAST/TUSER帧首不同。
- 显示明确BGR24，PS形成受支持的720p画布，不能把医学结果32位记录作为RGBA输出。
- AXI-Lite跨100/142MHz的已有控制结构不随意改；新增CDC使用成熟IP，各域复位同步。
- 旧VDMA DDR窗口512MiB，新3.x视频窗口`0x10000000..0x1FFFFFFF`；实际缓冲地址必须落在窗口内。

## 12. 资源预计与已知风险

XC7Z020工具报告容量：53200 LUT、106400 FF、220 DSP48、280 BRAM18（等价140个36Kb块）。实际B工程总资源、算法资源、可达频率和真实FPS均未知，不能填估算百分比冒充结果。

已取得的局部HLS估计：color_convert每个1489 LUT/1153 FF/6 DSP；pixel_unpack874 LUT/394 FF；pixel_pack1771 LUT/1068 FF。这些是2017.4 csynth估计而非最终实现，color_convert仍有uncertainty相关时序警告。删除IOP/Trace预计释放BRAM/LUT/FF及HP2通路，具体节省待同版本前后资源报告。

理论存储量：512×512单向1MiB，往返2MiB；四帧720p BGR约10.55MiB。单个7×7灰度窗口的6条512像素8位行只需3072字节数据，但实际BRAM粒度、端口、阶段数量和FOV对齐存储会增加，不能由此推断整个算法只占一个BRAM。带宽及理想周期推算见推荐架构，真机数值待测。

主要风险及对应动作：版本不匹配→先读实体镜像；图纸修订/DDR/HPD疑点→核对实体和原Demo；旧HLS日期溢出→保留原失败与本地元数据改动；driver依赖被删除模块→小型Overlay包装；DMA/视频TLAST混接→独立DDR通路；缓存或地址窗口错误→物理地址/flush/invalidate检查；精简reset/IRQ断连→每组删除后比较BD；ARM展示成本→分别测PL、DMA、端到端与显示帧率。

## 13. 最终架构选择与原因

选择“两个独立可构建设计，共用医学IP；最终B含分析DMA+官方VDMA/HDMI”。这满足快速算法调试、减少基础设施重复开发和现场完整显示的目标，并保留回退到原Base的路径。详细框图、配置、拟议地址、缓冲所有权和验证顺序见[vivado_architecture.md](vivado_architecture.md)。

静态/主机审查与板级基线已完成；A0至A3独立DMA算法阶段均已归档。M0数据与CPU参考已完成，A4完整固定算法通过现有2017.4主机构建，A4板测已完成并独立归档，下一阶段进行最终B的驱动适配与同一bitstream内HDMI整合。GPIO/HDMI与旧算法通过不能转移为A4或最终Overlay通过；设备树model、PCB修订核对和最终部署配对仍须按真实证据补充，暂缓2022.1安装的用户选择不变。

## 14. 官方资料来源、哈希与许可证

TUL资源由官方PYNQ支持链接指向厂商CDN，本地下载及失败URL均记录在[download_manifest.json](../references/board/download_manifest.json)。

|资料|官方来源链接|下载SHA256|
|---|---|---|
|原理图|[TUL PDF](https://dpoauwgwqsy2x.cloudfront.net/Download/TUL_PYNQ_Schematic_R12.pdf)|`2a5c8bd73291901b80bed0d5b178def40e0ac7ca6ca0ea56f7acad1dd4f3c7c9`|
|手册|[User Manual v1.0](https://dpoauwgwqsy2x.cloudfront.net/Download/pynqz2_user_manual_v1_0.pdf)|`47ebd0412126339cac0415a315f8878cb7dd7c138d406476cb4f928ca3c37404`|
|Master XDC|[TUL XDC ZIP](https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2_v1.0.xdc.zip)|`60e6d72e3fd9d8771da60567e038be2e69baf9a95290b627a4955aa89c3048f3`|
|Board Files|[TUL Board Files ZIP](https://dpoauwgwqsy2x.cloudfront.net/Download/pynq-z2.zip)|`6fba4c40db5a0c480ca96b2f41719f57e83728a54ac9823578ac21667b2e4e7f`|

补充来源：[PYNQ官方仓库](https://github.com/Xilinx/PYNQ)、[v2.2.1 Z2 Base](https://github.com/Xilinx/PYNQ/tree/3d2641653c6d1a5ea55c4c41e15f9dd9a2e32ab3/boards/Pynq-Z2/base)、[v3.0.1 Z2 Base](https://github.com/Xilinx/PYNQ/tree/93ddd21ab623883590a8c8b07f0b157b2855da4b/boards/Pynq-Z2/base)、[v3.1.2 Z2 Base](https://github.com/Xilinx/PYNQ/tree/3c77124d86bab65ac7bb6beb0aa66e13c83508f2/boards/Pynq-Z2/base)、[DMA官方文档源码](https://github.com/Xilinx/PYNQ/blob/3c77124d86bab65ac7bb6beb0aa66e13c83508f2/docs/source/pynq_libraries/dma.rst)、[维护者DMA硬件教程](https://discuss.pynq.io/t/tutorial-pynq-dma-part-1-hardware-design/3133)、[xfOpenCV固定版](https://github.com/Xilinx/xfopencv/tree/6e6953c20dc12de828693d6ae34bbb9a9a55ac37)、[Vitis Vision官方文档](https://xilinx.github.io/Vitis_Libraries/vision/2022.1/index.html)。教程只复用标准DMA方法，不复制其他板卡配置。

PYNQ主仓库及xfOpenCV使用BSD 3-Clause，应保留版权、条件及免责声明；PYNQ第三方许可文件说明Digilent视频IP许可，个别旧VHDL头还保留BSD条款，全部原样保存并随分发附带。AMD标准IP受工具/IP许可，不把生成网表宣称为项目自有开源RTL。TUL资料未找到明确再分发许可，当前内部审查保存，公开交付时优先引用官方链接。详细记录见[third_party_notice.md](third_party_notice.md)。

实际 Base 的四个 Tcl 与官方固定 v3.0.1 哈希一致，bit/HWH 板端哈希和 21 个软件可见 IP 的地址详见 [板端参考核对](../results/board/2026-10-11/board_environment_reference_check.md)。

2026-10-12进度：A1点运算17帧实体板记录已独立核验归档；A2空间滤波复用现有2017.4 HLS Filter2D/复制边界/行缓存，C仿真及实际厂商RTL数值、复位、HWH与完整布局布线通过。A2实体板37帧已完成，输入/期望/输出记录哈希独立复算一致，4份真实STARE输出655360字直接逐字匹配，原Notebook/ZIP/JSON/数组/预览已归档；没有复写基础IP或安装库。精确数值、IP/源码配对、实际资源及失败记录见[A2审查](a2_gaussian_reuse_audit.md)，板级记录见[A2板测报告](../results/a2_gaussian_2017_4/board_execution_2026-10-12/verification_report.md)。PCB修订、局部背景/完整医学分割与最终B仍待后续验证。

2026-10-11 A0更新：首版板测无响应已通过断电恢复，旧包撤回。r2使用同一2017.4厂商IP体系，修正辅助复位接线并通过真实厂商复位仿真；新构建/硬件描述检查完成。请见 [r2记录](../results/a0_dma_2017_4_r2/build_report.md)，r2板级PASS已有独立原始记录；不能将A0 PASS转移到医学算法或最终B。

2026-10-12 A3增量：在已验证A2通路内替换HLS算法IP，复用同版厂商15×15 BoxFilter/SepFilter2D/复制边界/行缓存，未修改安装库、帧适配器或PS/DDR/DMA/GPIO/FIFO/100MHz/reset及PYNQ驱动。Csim、实际生成RTL、厂商复位/HWH、完整实现与58项主机回归通过；整机资源5344 LUT/5960 FF/25.5 BRAM Tile/1 DSP，WNS1.461/WHS0.035ns。实体板45帧7,274,496字记录哈希已独立复算一致，四份真实STARE背景/响应输出655,360字逐字匹配，Notebook/预览/版本/字节数/帧计数核验及归档工具20项检查通过；真实记录见[A3板测报告](../results/a3_background_2017_4/board_execution_2026-10-12/verification_report.md)。发布时NOT_RUN作为历史值保留。见[A3复用审查](a3_background_reuse_audit.md)、[构建证据](../results/a3_background_2017_4/build_report.md)、[板测步骤](a3_background_validation_steps.md)。无新增板级引脚，PCB修订仍未知，最终B另行整合。
