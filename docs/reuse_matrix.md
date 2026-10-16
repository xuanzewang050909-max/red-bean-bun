# RetinaFPGA 技术复用矩阵

## 2026-10-14 Q4 C5实际增量实现

用户授权[折中实验](q4_c5_experiment_decision.md)后，已完成实际HLS/RTL与100MHz布局布线。`retina_refined_base.cpp`仅由原`retina_quality_hls.cpp`改顶层函数名并移除四条嵌套顶层接口pragma，原运算体逐字保留；原C2支持源码未改。新增19×19多尺度双侧证据和7×7有限连接直接复用未修改的2017.4 Filter2D/filter_opr/Window。PS7/DDR/AXI DMA/FIFO/GPIO/reset与原A4标准IP参数核对一致，RQ51帧参数/周期观测派生原guard。封装/综合/实现98份RTL/ROM配对通过。24,630 LUT/80 BRAM/1 DSP、WNS0.517ns是实际实现结果，非HLS估算。`pynq_q4`/`ui_q4`复用原W4a单工作者、官方DMA、只读快照、PNG与四面板绘图；旧179生产/发布文件原字节不变。实体板仍NOT_RUN，详细证据位于`results/q4_refined_2017_4_r1`。

## 2026-10-14 Q4 D1增量审查

[响应诊断](../results/q4_profile_audit_2026-10-14/training_review.md)复用原训练灰度/冻结FOV、OpenCV filter2D、NumPy统计及既有独立空间求和验证。新增项目整数Gaussian暗线/导数系数、配对与统计，非完整论文复现；不复制原论文代码。硬件仍为已测W2/C2，D1未生成RTL。后续若联合判定通过原门槛，优先复用本机2017.4厂商Filter2D/LineBuffer/Window、原PS/DDR/DMA/guard/官方驱动；必须先估算多方向滤波的乘加/行缓存和吞吐代价，再决定共享结构。不能把离线库可用当作Z2资源/时序已通过。下文矩阵的“未完成W2/Q3”等均为历史阶段描述。


## 当前复用决策（2026-10-13）

实验/最终均以 [浏览器架构](vivado_architecture.md) 为准，HDMI已正式取消。直接从已测A4最小算法工程复用，不重做基础通路或为删HDMI重建B。下面历史矩阵和早期“最终B/FPS待验证”不表示当前阶段未做过历史B验证，也不是继续视频开发的指令。

|模块/能力|实际复用|必要增量|当前边界|
|---|---|---|---|
|PYNQ-Z2基础|TUL preset/原理图，PS/DDR/MIO/FCLK/reset、板载以太网、PYNQ3.0.1|服务启动前核对实测环境|不写DDR/网络底层、不引入其他板约束|
|医学算法|A4已测Gaussian/LUT/背景/Threshold/零边界morp_opr/Filter2D/FOV|新派生阈值参数与帧快照、观测，不改原算法/安装库|原阈值28固定，模式1–3是算法A阶段，方向B未移植|
|DMA/缓存|官方DMA/allocate/等待/flush/invalidate及已测帧guard/FIFO|单工作者调度/只读CPU结果快照|原生缓冲/缓存策略不重写|
|性能/像素观测|标准AXI GPIO读接口、候选官方计时/监测IP|项目帧周期/停顿/参数/优先像素计数，接口经新验证|原A4只有帧计数，没有核心周期；候选未经实施不记PASS|
|网页/网络服务|已测W1 PYNQ Python/Tornado标准HTTP、单工作者与任务API、四面板|后续新ABI、阈值/算法绑定与已生效参数展示|24真实任务已核验，前台20帧FPS待补；不包装CPU滤波Demo为PL|
|亮区误检增量|A4增强/响应/后处理、厂商Window/LineBuffer/Filter2D候选、现有DMA/DDR/浏览器|新增C2双侧支持与饱和惩罚，在PL阈值前插入；共享窗口/中心对齐及有限FIFO重新验证|2026-10-14 Q1训练候选已冻结；见[Q2规格](q2_quality_pl_spec.md)。新PL/资源/时序/板测未完成，不改原厂头文件或原A28路径|
|评价|原预处理/独立M0/metrics/AH+VK规则|对当前真实PL输出生成指标/导出|GT和CPU参考与生产后端隔离|
|VDMA/HDMI|原始Base/B工程和实测归档|无新增；实验/最终无依赖|停止专用模块、画布/帧复制优化|

## 2026-10-12及以前的复用审查历史

**当前A4进展（2026-10-12）：完整冻结算法A已完成主机及实体板验证。** 阈值直接复用厂商Threshold，十字闭运算复用零边界morp_opr，邻域计数复用Filter2D；PS/DDR/DMA/GPIO/FIFO/guard/时钟复位原样沿用已测A3。Csim16帧、实际生成RTL17完整用例、100MHz实现和87项主机回归通过；A4实体板61帧9,895,936字与六份真实输出983,040字独立核验一致，26项归档检查通过；固定发布中的NOT_RUN保留历史值，见[A4板测报告](../results/a4_segmentation_2017_4/board_execution_2026-10-12/verification_report.md)。见[A4审查](a4_segmentation_reuse_audit.md)、[构建证据](../results/a4_segmentation_2017_4/build_report.md)和[上板步骤](a4_segmentation_validation_steps.md)。A3实体板45帧已归档，最终B与真机FPS仍未验证。

**A2阶段历史（2026-10-12）：M0真实CPU A/B评价完成，按训练规则选择A；A1点运算实体板17帧已归档；A2高斯直接复用厂商Filter2D/行缓存，Csim/生成RTL/完整2017.4实现及实体板37帧通过，4份真实输出数组655360字独立逐字匹配。** [M0评价](../results/m0_stare_2026-10-11/evaluation_report.md)、[定点与候选复用说明](algorithm_reference.md)、[A1板测报告](../results/a1_point_2017_4_r2/board_execution_2026-10-12/verification_report.md)、[A2审查](a2_gaussian_reuse_audit.md)、[A2板测报告](../results/a2_gaussian_2017_4/board_execution_2026-10-12/verification_report.md)。截至A2阶段尚未实现完整分割；当前A4主机进展见上文，最终B待实现。

**A0板测历史（2026-10-11）：A0 r2完成17字短包及70次完整DMA回环；执行Notebook与原始JSON已逐字节归档，源码/交付配对、收发字节数及71次图案哈希复核通过。** [板测归档报告](../results/a0_dma_2017_4_r2/board_execution_2026-10-11/verification_report.md)。首次失败证据另行保留；医学算法、最终HDMI整合及实时性能尚未验证。

**当前板级进展：启动、PYNQ 3.0.1、Jupyter/Base、GPIO、HDMI 和输出侧 100 帧提交已验证，原始执行Notebook及板端JSON已归档。** 独立DMA以现有2017.4构建，主机构建状态见 [A0报告](../results/a0_dma_2017_4_r2/build_report.md)，首版失败记录保留；修正版r2板测通过并归档；2022.1安装暂缓。

审查日期：2026-10-11，进展更新至2026-10-12。列含义：✓表示该类别成立；△表示有条件/部分成立；—表示不适用。“可以直接复用”仍要求匹配工具、镜像、PCB及配套驱动，**不表示本机或板端已经通过**。板级输出基线与A0/A1/A2已验证，Retina完整分割及最终B链路尚未验证；到板操作见[详细验证步骤](board_bringup_steps.md)。

补充资料审查：用户提供的《Pynq资料（含实验指导书等）》包内三份板卡配置XML及Master XDC与本项目原厂文件逐字节一致，可以复用；PYNQ教材可辅助入门，但其JTAG实验和9090网页地址需按当前任务与镜像区别处理。EES-A7板级配置不能复用，包内没有启动镜像、完整HDMI/DMA工程或医学模块。详细清单及证据见[资料包审查](vendor_package_review.md)。

|主要功能|官方已有|第三方已有|可以直接复用|需要修改|必须自主开发|尚未验证|采用方案/理由|
|---|---|---|---|---|---|---|---|
|PYNQ-Z2板级配置/PS DDR|✓|—|✓|△|—|板级|TUL Z2 preset、PS硬DDR控制器；新增HP连接仅必要修改|
|HDMI TMDS编码/发送|Base集成|Digilent rgb2dvi|✓|—|—|板级|保留匹配版本rgb2dvi，不从零写TMDS|
|HDMI接收/EDID|Base集成|Digilent dvi2rgb|✓|△|—|板级|首版保留官方RX，后按资源需求成组删除|
|HDMI像素/串行时钟|Base集成|Digilent axi_dynclk|✓|—|—|板级|沿用官方动态时钟驱动及约束|
|HDMI HPD/电平转换|✓|—|△|待修订核对|—|板级/方向|TX图纸与GPIO输出预设方向有疑点；不得未经核对主动驱动高电平|
|视频时序/AXIS→视频|✓|—|✓|△|—|板级|VTC和AXIS Video Out，先用支持的720p显示|
|通用帧缓存/VDMA|✓|—|✓|△|—|派生设计；Base输出100帧已通过|官方axi_vdma:6.3与Python视频DMA；首版保持4帧配置|
|标准算法双向DMA|AMD IP + PYNQ驱动/文档|教程可参考|IP/驱动✓|✓|—|算法阶段；A0 r2回环已验证|A0复用本机axi_dma7.1+axis_data_fifo1.1和3.0.1官方DMA驱动；Simple双向、长度23位，主机检查与板测分开记录|
|AXI路由/CDC/FIFO|✓|—|✓|△|—|最终实现|标准互连/Clock Converter/AXIS FIFO；连接按A/B定制|
|AXI-Lite接口模板|✓|—|✓|✓|寄存器语义✓|完整算法寄存器；A1配置/状态板测通过|A1直接复用axi_gpio2.0双32位通道作配置/状态，不自写AXI-Lite控制器；完整算法后扩充语义|
|PYNQ内存分配/缓存维护|✓|—|✓|版本适配|—|板级|allocate或Xlnk随镜像版本；检查地址窗口与所有权|
|Zynq底层/PL加载|✓|—|✓|—|—|板级|匹配镜像/PYNQ Overlay，不自写PS底层驱动|
|SD卡文件访问|✓|—|✓|应用逻辑|—|板级|Linux文件系统+Python，SDIO0 preset保留|
|Ethernet/Jupyter/文件输入|✓|—|✓|应用逻辑|—|板级|官方镜像/Linux协议栈，后续UI自定义|
|USB/UART/JTAG|✓|—|✓|—|—|板级|板载桥/PS/Linux驱动，不重写底层|
|按钮/LED/开关|✓|—|✓|交互绑定|—|开关/派生设计；Base按钮与LED已通过|保留AXI GPIO及Base管脚，精简Overlay包装|
|像素打包/颜色矩阵|✓|—|✓|配置✓|—|板级|官方pixel_pack/unpack、color_convert、color_swap|
|3×3 Gaussian|HLS Video / xfOpenCV|—|Filter2D/LineBuffer✓|固定整数核/一次取整/中心G与FOV对齐/帧协议|项目帧适配|完整链、FPS；A2板测已通过|同版未修改Filter2D的replicate边界；Csim917504字、生成RTL1114112字、完整100MHz实现、实体板37帧及4份原数组复核通过|
|局部背景box/Filter2D|HLS Video / xfOpenCV / Vitis Vision|—|BoxFilter/SepFilter2D/LineBuffer✓|15×15非归一化整数总和/一次取整/中心对齐|均值组合✓|完整链/FPS；A3实体板已通过|原样复用2017.4 BoxFilter<15,15,false,BORDER_REPLICATE>；12帧Csim、生成RTL13用例、完整100MHz实现及实体板45帧/四份原数组独立核验通过；旧xfOpenCV3/5/7 constant路线不适用|
|灰度/LUT/阈值|HLS/xfOpenCV/Vitis候选|—|Threshold✓、固定LUT沿用|项目字节布局/参数|少量医疗控制|最终B/FPS；A1/A2/A4相关板测通过|A4未修改Threshold二值严格大于接口，阈值27/maxval1精确实现response>=28；主机C/实际RTL通过|
|腐蚀/膨胀|HLS Video / xfOpenCV|—|morp_opr✓|结构元素/常量零边界/阶段对齐|组合与对齐✓|最终B/FPS；A4板测通过|同版未修改dilate_kernel/erode_kernel，CROSS3、ITERATIONS1、BORDER_CONSTANT=0；便捷Dilate/Erode的固定replicate边界不适用；主机数值/时序通过|
|邻域孤点过滤|HLS Filter2D|—|Filter2D/行缓存✓|3×3全1核、复制边界、诊断对齐|closed且count>=2且FOV组合✓|医学质量/最终B/FPS；A4板测通过|0/1输入，计数0..9含中心；保留冻结M0语义，主机独立参考及实际生成RTL通过|
|通用行缓存/窗口|厂商HLS模板/BRAM/FIFO|—|✓|阶段数/宽度/帧复位|医疗流适配△|最终B/FPS；A4多帧板测与主机背压通过|存储原语复用；项目中心延迟FIFO，首次512有限FIFO死锁已撤回，正确2048容量重新完成实际RTL验证|
|医学FOV过滤/数据打包|通用bitwise等零件|—|零件△|✓|医疗组合✓|最终B；A4板测通过|FOV只由RGB生成，初始/最终过滤及诊断字节对齐通过主机检查；GT仅离线评价|
|局部血管增强/方向响应|通用卷积零件|—|零件✓|✓|医疗响应/诊断字节✓|完整分割/质量/FPS；A3响应板测通过|M0选算法A，A3实现clip(4*(背景-增强),0,255)，主机及实体板背景/响应逐字验证通过；未加入阈值/形态学/FOV最终过滤，也未实现未选的方向算法B|
|32位帧包多阶段控制|基础AXIS/FIFO|—|零件✓|✓|帧状态/验证✓|算法阶段|TLAST、计数、复位、背压、连续多帧，避免与视频行包混接|
|医学可视化/结果叠加|官方视频显示框架|OpenCV显示零件|框架✓|✓|交互布局✓|端到端|PS只做展示合成/文字，医学预处理与分析由PL完成|
|CPU bit-accurate参考/质量评估|通用Python/NumPy|公开数据工具|零件△|✓|项目参考与评价✓|完整PL记录及六份原数组已一致；医学质量/最终B/FPS待验收|M0固定训练/留出；A4完整Csim/实际生成RTL与独立参考逐字通过，实体板61帧通过，未取得新质量结论|
|性能计数/端到端记录|基础计时/AXI|—|零件△|✓|算法周期/帧计数✓|真机|分开算法FPS、显示Hz和端到端延迟，不生成假数据|
|精简Base后的Python入口|Overlay/视频/GPIO驱动|—|底层✓|✓|小型RetinaOverlay✓|板级绑定|不原样使用访问已删IOP/音频的BaseOverlay|

## 已检查的滤波候选

- 本机Vivado HLS 2017.4：`include/hls/hls_video_imgproc.h`含GaussianBlur、Filter2D、Erode、Dilate及LineBuffer/Window；专有工具库，不能把安装头文件当作项目开源资产发布。
- [xfOpenCV 2017.4_release](https://github.com/Xilinx/xfopencv/tree/6e6953c20dc12de828693d6ae34bbb9a9a55ac37)：固定Commit `6e6953c20dc12de828693d6ae34bbb9a9a55ac37`，已保存头文件、相关例程、README和BSD许可证；未综合/未在Z2上验证。README要求SDSoC2017.4，Windows支持标记Beta；不能把自带示例平台视作Z2配置。
- [Vitis Vision 2022.1官方文档](https://xilinx.github.io/Vitis_Libraries/vision/2022.1/index.html)：提供Gaussian、box、LUT、threshold、erode/dilate等，适合匹配2022.x/2024.x工具后重新评估；本次只审查功能与版本路线，未导入。
- 官方视频Notebook中`cv2.GaussianBlur/Sobel/erode`属于CPU处理示例，复用显示和API用法，不能宣称是既有FPGA滤波RTL。

每次新增模块前以本矩阵为入口，补充“已查候选、能否逐位一致、修改理由、许可、版本、验证证据”。“必须自主开发”仅针对项目缺失的医疗逻辑/控制/参考，不包含用户禁止重复开发的基础设施。

2026-10-12 A2决策：直接复用本机2017.4的Filter2D/BORDER_REPLICATE、Mat、LineBuffer/Window和HLS AXIS生成器；项目提供整数核、一次取整、原G/FOV对齐、固定LUT及帧适配。标准PS/DDR/DMA/FIFO/GPIO/时钟复位沿用已在板上通过的A1。Csim、实际生成RTL、完整实现及A2实体板37帧已通过；4份STARE原数组与M0独立参考逐字匹配。GaussianBlur/xfOpenCV现有sigma权重路径未直接采用，理由为精确定点与边界一致性；详见[A2复用审查](a2_gaussian_reuse_audit.md)及[A2板测报告](../results/a2_gaussian_2017_4/board_execution_2026-10-12/verification_report.md)。局部背景和形态学已有库候选，医疗特有判定仍需开发，最终视频通路继续复用官方设计。

2026-10-11 A0更新：首版板测无响应已通过断电恢复，旧包撤回。r2使用同一2017.4厂商IP体系，修正辅助复位接线并通过真实厂商复位仿真；新构建/硬件描述检查完成。请见 [r2记录](../results/a0_dma_2017_4_r2/build_report.md)，r2板级PASS已有独立原始记录；不能将A0 PASS转移到医学算法或最终B。

2026-10-12 A3增量：PS/DDR/DMA/FIFO/GPIO/reset/已测guard与PYNQ驱动原样沿用A2，仅替换内部计算IP。厂商BoxFilter15×15非归一化总和与replicate边界直接复用，项目新增精确均值、饱和响应和诊断对齐。12帧Csim1376256字、实际生成RTL13用例1441792字、厂商复位/HWH/完整100MHz实现、58项主机回归及15项组装包检查通过；实体板45帧7,274,496字记录哈希与四份实际输出655,360字独立核验通过；归档工具20项检查通过。真实证据见[A3板测报告](../results/a3_background_2017_4/board_execution_2026-10-12/verification_report.md)，发布时NOT_RUN保留历史值。见[A3审查](a3_background_reuse_audit.md)、[A3构建报告](../results/a3_background_2017_4/build_report.md)和[操作指南](a3_background_validation_steps.md)。A3的后续功能现由A4完成主机和实体板验证；不能把A3结果转记为完整分割/最终B/FPS。

2026-10-12 B增量：本机2017.4从固定v2.2.1官方Z2 Base派生，同一bitstream含已测A4算法和原VDMA/HDMI。正确b_integration_05完整布局布线时序通过，WNS0.341/WHS0.008ns；15,823 LUT/24,316 FF/46 BRAM Tile/19 DSP，DRC零错误/关键警告。三个实际生成reset IP仿真、20项主机检查、95份实际RTL/ROM/约束来源字节核验通过。36个GPIO/HDMI管脚不变；仅修复RX周期取整、删音频约束并在工作工程排除不适用的RGB生成时钟约束，真实MMCM/BUFR自动派生关系已检查。十三文件包build/deploy/b_integration_2017_4_r1发布为NOT_RUN；不改固定A4和参考源码，不安装新工具，不宣称板测/显示/FPS/新医学质量通过。见[B审查](b_integration_reuse_audit.md)、[上板步骤](b_integration_validation_steps.md)及[实际构建报告](../results/b_integration_2017_4/build_report.md)。

2026-10-12 B实体板增量：软件r2经修正官方视频子模块导入后完成单次加载，真实绑定PYNQ3.0.1 DMA/GPIO/HDMIWrapper/VideoOut/AxiVDMA；370帧70,647,808字记录独立复算一致，六份STARE原数组983,040字直接逐字通过。真实显示器彩条/定位线、原图与绿色候选照片分别归档；300计时样本核验通过。512算法DMA平均4.866ms/帧，包含核验/排版/显示提交的循环1.601FPS；不是纯PL周期或扫描Hz，不宣称实时性能达标。归档工具29项检查通过，原JSON/板上2022年时间/PENDING/发布NOT_RUN保留历史原值；原件在build/board_results/b_integration_2026-10-12，见[B实体板报告](../results/b_integration_2017_4_r2/board_execution_2026-10-12/verification_report.md)。下一阶段优先分段测核验、排版、分配/复制和提交耗时，保持冻结算法及成熟驱动。

2026-10-15 C7增量：新36特征/8树检测只在PL新增；17×17窗口和复制边界使用2017.4未修改filter_opr，PS/DDR/AXI DMA/GPIO/reset和网页成熟链路沿用。原C5只有派生包装去外部顶层INTERFACE声明，计算逐行保持，旧源文件不改。拟合仅原训练AH；冻结后复用留出/VK揭示im0324等退化，C7仅可选实验。见[q4d复用审查](q4d_c7_reuse_audit.md)、[冻结结果与局限](q4d_c7_frozen_review.md)、[构建与发布检查](q4d_c7_build_audit.md)。实际完整RTL、100MHz路由、49项不同主机检查和最终发布配对已完成，等待实体板验证；不沿用C5的板测PASS。
