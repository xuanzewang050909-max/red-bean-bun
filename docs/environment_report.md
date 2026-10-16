# RetinaFPGA 开发环境实测报告

**当前A4增量（2026-10-12）：同一Windows/Vivado HLS与Vivado2017.4完成完整固定分割的主机与实体板61帧验证。** 正确第二次实现100MHz，WNS1.170/WHS0.020/WPWS3.750ns，6636 LUT/7293 FF/36 BRAM Tile/1 DSP；Csim16完整帧/实际生成RTL17完整用例/标准复位/HWH/87项主机回归/16项组装包校验通过。十二文件包在build/deploy/a4_segmentation_2017_4_r1；实测PYNQ3.0.1已运行61帧9,895,936字；六份真实输出983,040字及Notebook/二值预览独立核验通过，26项归档检查通过；原时间保留，发布NOT_RUN作为历史值不改。见[A4板测报告](../results/a4_segmentation_2017_4/board_execution_2026-10-12/verification_report.md)。无需主机Linux或新Vivado。详见[A4真实报告](../results/a4_segmentation_2017_4/build_report.md)与[操作步骤](a4_segmentation_validation_steps.md)。A3已完成45帧板测，最终B仍待整合。

**A1阶段历史（2026-10-12）：继续使用Windows/Vivado2017.4，A1单级诊断Overlay已完成实体板17帧验证；无需本阶段安装Linux或2022.1。** 主机CPU参考使用项目`.venv`：Python3.12.14、NumPy2.5.4、Pillow12.3.0、OpenCV5.0.0（headless发行包5.0.0.93），固定安装版本见requirements.txt；板端Python3.10.4及镜像依赖保持原样。r1构建时19项主机测试通过，r2校验修复后25项通过；板级结果另见[A1板测报告](../results/a1_point_2017_4_r2/board_execution_2026-10-12/verification_report.md)，原[A1主机报告](../results/a1_point_2017_4/build_report.md)保留。

**A0板测历史（2026-10-11）：A0 r2完成17字短包及70次完整DMA回环；执行Notebook与原始JSON已逐字节归档，源码/交付配对、收发字节数及71次图案哈希复核通过。** [板测归档报告](../results/a0_dma_2017_4_r2/board_execution_2026-10-11/verification_report.md)。首次失败证据另行保留；此A0历史记录不验证医学算法、最终HDMI整合及实时性能。

更新日期：2026-10-12（Asia/Shanghai）。本报告区分主机工具检查、用户现场板级执行和尚未完成的开发任务；最初工具审查记录保留原日期。

**主机工具结论：只有 Vivado/Vivado HLS 2017.4 已确认可用。** XC7Z020 主机综合、布局布线与 xsim 小型探针通过；PYNQ v2.2.1 官方 Z2 Base 的工作副本 BD 重建通过，完整 Base bitstream 未构建。运行中的 PYNQ 3.0.1 官方 Base 对应 Vivado 2022.1，本机尚未检测到该版本，预构建镜像测试通过不代表跨版本重建兼容。

**当前开发路线：用户同意优先使用2017.4，暂缓2022.1安装。** A0基于TUL Z2 preset、本机标准DMA/FIFO和板上3.0.1官方驱动；B候选从v2.2.1 Base派生并独立验证驱动适配。PYNQ运行版本不直接限定生成bitstream的Vivado版本，工程/IP版本和bit/HWH/驱动配套需要验证。A0当前状态见 [构建报告](../results/a0_dma_2017_4_r2/build_report.md)。

**当前板级结论：Linux 串口、PYNQ 3.0.1、Jupyter/Base、GPIO、HDMI 与输出侧连续 100 帧提交通过。** UART 是 COM9，Jupyter 为 http://192.168.2.99:9090/tree；独立 DMA 已通过；PCB 修订待核对；完整环境 JSON 已归档，四个 Base Tcl 哈希匹配固定 v3.0.1 源码。详见 [板级汇总](../results/board/2026-10-11/board_validation_summary.md)。下表保留最初主机检测的硬件参数；连接状态更新列注明后续证据。

## 当前板端环境（用户 Notebook 输出）

|项目|实测输出|
|---|---|
|PYNQ|3.0.1|
|板端 Python|3.10.4，GCC 11.2.0|
|内核|5.15.19-xilinx-v2022.1|
|MemTotal|505428 kB；这是操作系统报告内存，不是对 DDR 颗粒容量的直接测量|
|当前软件可见 PL IP|21 个；不是完整 Vivado BD 的所有 IP 数|
|Base 文件|六个文件的大小和 SHA256 已归档；四个 Tcl 与固定 v3.0.1 源码一致|
|设备树 model|采集结果 None；PCB 修订和该字段读取路径仍待核对|

证据见 [板端环境采集记录](../results/board/2026-10-11/board_environment_capture_check.md)。此采集不额外证明独立 DMA 或医学算法通过。

## 1. 实际主机环境

|项目|检测结果|证据|
|---|---|---|
|系统|Windows 11 家庭版中文版，64 位，`10.0.26300`|[environment.json](../results/audit/environment.json)|
|CPU|Intel Core i9-13980HX，24 核 / 32 逻辑处理器|同上|
|磁盘空闲|检测时 C 48.68 GiB、D 69.08 GiB、E 103.02 GiB；随构建变化|同上|
|Vivado|`E:\vivado\Vivado\2017.4\bin\vivado.bat`；SW Build 2086221 / IP Build 2085800|版本实际执行结果|
|Vivado HLS、xvlog、xelab、xsim、hw_server|同一 2017.4 安装目录中存在；HLS 和仿真器已实际执行|[HLS 日志](../results/audit/official_v2.2.1/hls.log)、[仿真日志](../results/audit/simulation/xsim.log)|
|目标器件|`xc7z020clg400-1`，工具可解析|[capabilities.txt](../results/audit/vivado_probe/capabilities.txt)|
|许可证|实际获取 XC7Z020 的 Synthesis、Implementation 许可并完成小型 OOC 自检|[vivado_probe.log](../results/audit/vivado_probe.log)|
|板卡文件|安装中最初没有 PYNQ Board Part；项目内导入 TUL 文件后识别 `tul.com.tw:pynq-z2:part0:1.0`|同上|
|Git|`C:\Program Files\Git\cmd\git.exe`；项目建立本地 Git 历史|项目 Git 状态|
|SSH|Windows OpenSSH 客户端存在；未连接任何推测的板卡地址|environment.json|
|USB/JTAG/UART|后续 Windows 识别 USB Serial Port（COM9），串口 Linux shell 可用；JTAG 未测|[启动证据](../results/board/2026-10-11/official_image_first_boot.md)|
|网络|最初 WLAN 在线、以太网未连接；后续板端 192.168.2.99:9090 Jupyter 网页可访问|environment.json + [网页证据](../results/board/2026-10-11/jupyter_access_check.md)|

Vivado 未加入当前 PATH，脚本使用已验证的绝对路径，并仅在子进程运行期间补充工具 PATH。注册表中的 `D:\vivado`、2017.4/2026.1 项不能证明安装有效：实际目录未找到对应可执行工具，本次没有检测到可用的 Vivado 2026.1。不能据注册表把本机版本写成 2026.1。

## 2. Python 环境

|用途|实际路径与版本|已知库状态|
|---|---|---|
|用户 Python|`C:\Users\Gabriel\AppData\Local\Programs\Python\Python312\python.exe`，3.12.5|numpy、Pillow 可用；cv2、pytest、pynq 未安装|
|文档/PDF 审查运行时|`C:\Users\Gabriel\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，3.12.14|numpy 2.3.5、Pillow 12.3.0、pypdf 6.10.0、pdfplumber 0.11.9；cv2、pytest、pynq 未安装|
|板端 Python/PYNQ|Python 3.10.4 / PYNQ 3.0.1|原始 board_environment.json 已归档，与 Windows Python 区分|

本次资源获取、哈希验证和 Tcl/Notebook 清单分析仅依赖 Python 标准库，不需要安装 OpenCV。医学算法 CPU 基线及数据集环境尚未建立。PYNQ 的 PL、内存分配和视频驱动应在板端 Linux 上验证，不以 Windows 安装同名包代替板端运行。

## 3. 版本兼容性与基线选择

|固定资源|官方 Base 脚本声明的 Vivado|与本机关系|当前用途|
|---|---|---|---|
|PYNQ v2.2.1 / `3d2641653c6d1a5ea55c4c41e15f9dd9a2e32ab3`|2017.4|匹配；原始 HLS 导出有日期溢出问题|已完成BD验证；当前B派生候选，跨运行时适配待验证|
|PYNQ v3.0.1 / `93ddd21ab623883590a8c8b07f0b157b2855da4b`|2022.1|本机没有对应工具|已选板端参考；四份 Tcl 哈希匹配；不能直接用 2017.4 重建原 Base|
|PYNQ v3.1.2 / `3c77124d86bab65ac7bb6beb0aa66e13c83508f2`|2024.1|本机没有对应工具|板端若为 3.1 系列时的候选；仅完成源码比较|
|PYNQ v4.0.0|2025.2，发布说明移除 Zynq-7000/Pynq-Z1/Z2 支持|不适合作为 Z2 Base 起点|排除当前默认分支/最新版本策略|

依据：固定版本 `boards/Pynq-Z2/base/base.tcl` 的 `scripts_vivado_version`；[PYNQ 3.0 发布说明](https://github.com/Xilinx/PYNQ/releases/tag/v3.0.0)、[3.1 发布说明](https://github.com/Xilinx/PYNQ/releases/tag/v3.1)、[4.0 发布说明](https://github.com/Xilinx/PYNQ/releases/tag/v4.0.0)。3.1.2 是软件补丁 Tag，不能把它等同于一张新的 3.1.2 SD 镜像。

**已运行的板端Base参考为PYNQ-Z2 v3.0.1 / 93ddd21，其源码构建基线为2022.1；当前自主构建路线为2017.4。** 四个板端Base Tcl哈希匹配固定Tag。A0生成自己的同次bit/HWH，沿用板上3.0.1官方DMA驱动；B先验证2017.4/v2.2.1候选，并记录与3.0.1驱动的差异。不能把不同工程的bit/HWH拼在一起，也不能只修改版本检查就宣称兼容。实体PCB修订仍需读取。

## 4. 已执行的主机检查

|检查|结果|范围与限制|
|---|---|---|
|环境采集 / 版本执行|通过|实际 Windows 工具检测|
|XC7Z020 小型 OOC 综合→优化→布局→布线|通过|8 位寄存器异或自检；不是医学 IP，也不是 Overlay 资源/时序验证|
|xvlog→xelab→xsim，256 个输入向量|通过|自检 RTL；首次缺少 timescale 的失败日志已保留，补齐后通过|
|TUL Board Part 识别|通过|项目内 repoPaths，无全局文件替换|
|官方 5 个 HLS 模块的原始导出|失败|`core_revision=2610110300` 超出旧工具允许范围，`bad lexical cast`|
|相同 HLS 的本地元数据重打包|通过|仅生成包装脚本 `Revision` 改为 1；源 C++/Tcl/RTL不改，安装不改|
|v2.2.1 官方 Base BD 创建与 `validate_bd_design`|通过，存在原始警告|159 个 IP；未做完整 Base 综合/实现；不能等同无警告签核|
|v3.0.1 / v3.1.2 完整 Base 构建|未执行|缺相应 2022.1 / 2024.1 工具|
|资料完整性/管脚交叉核验|通过|3334个PYNQ文件、152个xfOpenCV文件、4个厂商下载；3个版本各36个关键PL管脚；仅静态核验|
|PYNQ 启动/Jupyter/LED/HDMI/VDMA/DMA|板级基线通过；A0/A1/A2/A3已归档|用户已拿到板卡；A4新完整算法待61帧板测，最终B未测|

HLS 失败及工作副本修正记录在 [official_v2.2.1](../results/audit/official_v2.2.1/)。原始包装脚本与修正后脚本都保留，只改变元数据，不改变算法。AMD 官方资料将此类 HLS 导出错误关联到 [Y2K22 问题及 AR 76960](https://xilinx.github.io/vck190-base-trd/2021.1/html/known-issues.html)；AR 网页当前返回 CSS 错误，本次没有下载、安装或宣称应用官方补丁。项目内修正是可回退的审查工作绕过措施，后续生产构建优先使用匹配的已修复工具。

BD 原始警告包含只读 AXI 参数、外设接口逐引脚覆盖、部分 clock/reset/intr 引脚类型、时钟域传播等。全部留在 `bd.log`，最终精简设计需要重新分类和解决。小型 OOC 报告中未定位板级端口的警告也不表示已完成板级时序约束。

审查完整性结果见[verification.json](../results/audit/verification.json)。工具展开后的叶IP共有254个，包含互连内部自动生成逻辑；按已知互连容器归回后与159个源码IP完全对应。5个生成包装脚本逐行比对只修改Revision，差异见[packaging_revision.patch](../results/audit/official_v2.2.1/packaging_revision.patch)。所有文档本地链接已核验。

## 5. 复现入口

在项目目录的 PowerShell 执行：

```powershell
.\scripts\collect_environment.ps1
python .\scripts\analyze_references.py
.\scripts\run_simulator_probe.ps1
& 'E:\vivado\Vivado\2017.4\bin\vivado.bat' -mode batch -nojournal -log results/audit/vivado_probe.log -source scripts/probe_vivado.tcl
```

官方参考工程首次准备与检查：

```powershell
python .\scripts\prepare_reference_build.py
.\scripts\run_official_audit.ps1 -Stage hls
# 若仍出现已记录的日期溢出，使用已审查的工程内元数据修正：
.\scripts\run_official_audit.ps1 -Stage hls-repack
.\scripts\run_official_audit.ps1 -Stage bd
```

当前 `build/official_v2.2.1` 已存在；准备脚本会拒绝覆盖它。`bd` 阶段以首次创建为入口；再次审查时使用新的工作副本或直接打开已保存项目，避免覆盖结果。源码快照只读复用，生成物留在 `build/`，结果日志单独保存。时间戳和空闲磁盘每次执行都会变化。

板端完整环境与实际 Base 地址/哈希见 [原始报告核对](../results/board/2026-10-11/board_environment_reference_check.md)。原始板端日期仍为 2022 年，需后续校时，接收日期单独保留。

2026-10-12增量：继续使用同一Windows/Vivado/HLS2017.4，A1 r2实体板17帧已核验；A2采用同版厂商视频库，修正版build/a2_gaussian_02完整实现通过100MHz时序（WNS1.517/WHS0.032ns）、8 BRAM Tile/3517 LUT/4829 FF/0 DSP。HLS Csim、生成RTL/复位仿真和32项原主机回归通过。现已完成A2实体板37帧5963776字，PYNQ3.0.1/官方DMA/GPIO绑定与帧控制通过，4份真实输出655360字独立逐字匹配；归档工具19项检查通过。旧HLS导出日期溢出仍只修改生成Tcl的Revision元数据；真正编译的autopilot库与最初include审查目录分开记录，不假定两者哈希一致。最终B待执行，详见[A2审查](a2_gaussian_reuse_audit.md)及[A2板测报告](../results/a2_gaussian_2017_4/board_execution_2026-10-12/verification_report.md)。无需给Windows电脑安装Linux。

2026-10-11 A0更新：首版板测无响应已通过断电恢复，旧包撤回。r2使用同一2017.4厂商IP体系，修正辅助复位接线并通过真实厂商复位仿真；新构建/硬件描述检查完成。请见 [r2记录](../results/a0_dma_2017_4_r2/build_report.md)，r2板级PASS已有独立原始记录；不能将A0 PASS转移到医学算法或最终B。

2026-10-12 A3增量：继续使用本机Windows/Vivado/HLS2017.4，板端目标仍为实测PYNQ3.0.1，无新系统安装。完整A3实现100MHz，WNS1.461/WHS0.035/WPWS3.750ns，5344 LUT/5960 FF/25.5 BRAM Tile/1 DSP；12帧Csim/13完整RTL用例/真实复位/HWH/58项主机回归/15项组装包检查通过。11文件发布于build/deploy/a3_background_2017_4_r1；实体板45帧7,274,496字记录哈希已独立复算一致，四份真实输出655,360字逐字匹配，Notebook/四幅预览核验及归档工具20项检查通过。见[A3板测报告](../results/a3_background_2017_4/board_execution_2026-10-12/verification_report.md)。发布时NOT_RUN保留历史值；板端旧时间原样保留，主机核验时间另记。安装库未改动，日期修正只针对生成Revision元数据；实际DSP建议审查、失败和配对证据见[A3报告](../results/a3_background_2017_4/build_report.md)。

2026-10-12 B增量：本机2017.4从固定v2.2.1官方Z2 Base派生，同一bitstream含已测A4算法和原VDMA/HDMI。正确b_integration_05完整布局布线时序通过，WNS0.341/WHS0.008ns；15,823 LUT/24,316 FF/46 BRAM Tile/19 DSP，DRC零错误/关键警告。三个实际生成reset IP仿真、20项主机检查、95份实际RTL/ROM/约束来源字节核验通过。36个GPIO/HDMI管脚不变；仅修复RX周期取整、删音频约束并在工作工程排除不适用的RGB生成时钟约束，真实MMCM/BUFR自动派生关系已检查。十三文件包build/deploy/b_integration_2017_4_r1发布为NOT_RUN；不改固定A4和参考源码，不安装新工具，不宣称板测/显示/FPS/新医学质量通过。见[B审查](b_integration_reuse_audit.md)、[上板步骤](b_integration_validation_steps.md)及[实际构建报告](../results/b_integration_2017_4/build_report.md)。

2026-10-12 B实体板增量：软件r2经修正官方视频子模块导入后完成单次加载，真实绑定PYNQ3.0.1 DMA/GPIO/HDMIWrapper/VideoOut/AxiVDMA；370帧70,647,808字记录独立复算一致，六份STARE原数组983,040字直接逐字通过。真实显示器彩条/定位线、原图与绿色候选照片分别归档；300计时样本核验通过。512算法DMA平均4.866ms/帧，包含核验/排版/显示提交的循环1.601FPS；不是纯PL周期或扫描Hz，不宣称实时性能达标。归档工具29项检查通过，原JSON/板上2022年时间/PENDING/发布NOT_RUN保留历史原值；原件在build/board_results/b_integration_2026-10-12，见[B实体板报告](../results/b_integration_2017_4_r2/board_execution_2026-10-12/verification_report.md)。下一阶段优先分段测核验、排版、分配/复制和提交耗时，保持冻结算法及成熟驱动。
