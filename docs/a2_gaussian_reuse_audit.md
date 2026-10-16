# A2 高斯滤波复用审查与实现边界

日期：2026-10-12。A1实体板17帧已通过；A2现已完成37帧实体板测试并独立核验，4份真实STARE输出数组655360字逐字匹配。原始执行记录与数值证据见[A2板测报告](../results/a2_gaussian_2017_4/board_execution_2026-10-12/verification_report.md)。发布清单保留发布时NOT_RUN，不改写历史。

## 先查已有功能，再确定实现

已检查本机Vivado HLS 2017.4的GaussianBlur、Filter2D、Mat、LineBuffer/Window，以及固定Commit的xfOpenCV 2017.4_release。官方Base视频Notebook的OpenCV调用运行在PS，不能当作现成PL滤波模块。

选用未修改的 `hls::Filter2D<hls::BORDER_REPLICATE>`、Mat、LineBuffer/Window和厂商AXIS接口生成器。项目只提供固定权重、数据拆合、中心G/FOV对齐和帧控制。滤波主体由现有库生成Verilog，不重新设计卷积行缓存。复用前置资料见[复用矩阵](reuse_matrix.md)、[算法规范](algorithm_reference.md)和[来源许可](third_party_notice.md)。

现有GaussianBlur/xfOpenCV候选根据sigma产生量化权重，不能直接假定等于本项目的固定整数核。Filter2D显式指定整数核及复制边界，能够与M0参考逐字一致，因此采用它，并保留完整的C仿真及生成RTL数值验证。

HLS真正编译的头文件位于 `E:/vivado/Vivado/2017.4/common/technology/autopilot/`，不是仅凭最初审查的include目录推测。两处的imgproc/mem头哈希不同；发布清单分别保存两组哈希，实际预处理记录确认所用路径。没有修改安装头文件，也没有将专有库源码复制到仓库。

## 数值与帧接口

核为 `[1 2 1; 2 4 2; 1 2 1]`；先完整累加到uint16，再仅一次执行 `(sum+8)>>4`。边界按最近像素复制，包含四角和最后一行/列。LUT仍是M0的 `min(255,(g*255+96)//192)`，硬件使用256项固定表。

输入为256×256或512×512的完整32位帧：B、G、R各占一字节，高字节是从RGB生成的FOV。数据不含血管人工标注。真实STARE im0001先保比例缩放、黑色补边，几何和原RGB成员哈希记录在vector_manifest中。

|模式|输出含义|用途|
|---|---|---|
|0|完整32位原输入|旁路诊断|
|1|low=G，byte1=G，byte2=0，high=中心FOV|原绿色对齐诊断|
|2|low=G，byte1=Gaussian(G)，byte2=0，high=中心FOV|精确高斯诊断|
|3|low=G，byte1=LUT(Gaussian(G))，byte2=0，high=中心FOV|预处理组合诊断|

这不是最终分割输出包格式。所有模式均经过同一个滤波帧引擎，模式0/1不用于宣称性能。

HLS内部AXIS仅有TDATA/TVALID/TREADY；外层帧适配器沿用A1已验证的配置锁存、状态计数和弹性握手结构，检查输入TKEEP/TLAST，按锁存尺寸重新生成输出帧TKEEP/TLAST。首输入锁存配置，保留原G/FOV的2048字FIFO覆盖厂商滤波启动延迟。START保持到厂商ap_ready，完成后才接收下一帧。

完整长度的错误TLAST/TKEEP在主机仿真被检测；板端只发合法完整帧。无法收齐的帧需要明确复位恢复，不能将畸形短帧当作正式接口支持。

## 最小硬件改动

保留已在实体板通过的A1 PS7、512MB DDR/HP0、AXI互连、AXI DMA7.1、AXIS FIFO、AXI GPIO2.0、100MHz时钟和proc_sys_reset5.0。仅将点运算位置改为帧适配器与厂商滤波IP，增加HLS的控制/握手连接。无新增板级PL端口，无新增XDC，无自写DDR/DMA或GPIO底层驱动。

数据通路：PS准备RGB/FOV → DDR → DMA MM2S → 帧适配器 → Filter2D/Gaussian/LUT → 帧适配器 → 原AXIS FIFO → DMA S2MM → DDR。标准PYNQ DMA/AxiGPIO驱动负责缓存和寄存器访问。

DMA仍为0x40400000，控制/状态GPIO仍为0x41200000；全部计算、控制和DDR通路采用原100MHz/低有效复位。最终B需把已验证的算法与官方VDMA/HDMI放入同一设计；A2不包含HDMI，不能切换两套Overlay代替最终整合。

## 已完成的真实主机检查

|检查|证据/结果|范围|
|---|---|---|
|HLS C仿真|8完整帧、917504输出字一致|独立九点整数参考、复制边界/取整/G/FOV/模式|
|生成厂商Verilog的AXIS仿真|11完成用例、1114112输出字一致|256/512、所有模式、二维/随机/棋盘/边角/真实STARE、随机背压、配置锁存、异常标志、复位后无残留|
|厂商proc_sys_reset仿真|RESET_SIM_PASS|直接使用A2构建的实际复位IP，再现aux=0错误，验证aux=1及PS复位|
|HWH检查|固定PYNQ3.0.1原解析器通过|只stub架构常量；核对时钟/DDR/DMA/GPIO、AXIS四接口及START/READY接线|
|完整实现|build/a2_gaussian_02生成bit/HWH|布局布线、setup/hold/pulse-width全部满足，非板测|
|主机参考/测试脚本回归|32项通过|错误数据/字节数/计数保留缓冲，阶段阻断，Notebook保存兼容，真实输出文件打包保护|

实际完整工程：3517 LUT（6.61%）、4829寄存器（4.54%）、8个BRAM36等价Tile（5.71%）、0 DSP。100MHz实现WNS=1.517ns、WHS=0.032ns、WPWS=3.750ns；没有无时钟寄存器或未约束内部最大延迟路径。HLS独立估算与整个工程的布局布线资源不同，不能直接相加作为最终B资源预测。

继承的只读aux_reset_in极性setter警告已通过实际HWH和厂商复位仿真核验。DRC仅有RTSTAT-10未使用内部FIFO状态网络警告，以及标准DMA BRAM的WRITE_FIRST advisory；未增加DRC错误。完整报告保留；该修正版已完成37帧实际收发。

## 失败记录与发布选择

- hls_attempt_01/02是旧工具参数和绝对工程名处理问题，后续脚本已适配真实2017.4行为；原失败日志保留。
- hls_attempt_03的C仿真、综合已完成，导出遇到2026日期生成core_revision整数溢出。仅在生成的包装Tcl副本中将Revision改为1；逐行证明只有此元数据变化，安装库、算法和RTL未改。
- axis_simulation_attempt_01缺少ROM初始化文件，并且单周期START未满足厂商DATAFLOW握手，输入停住。随后复制生成的.dat并将START保持至READY，axis_simulation_attempt_02通过。
- build/a2_gaussian_01虽产生bitstream，但仍含上述START缺陷，明确撤回，未交付或进行板测。只选择修正版build/a2_gaussian_02。

发布脚本会核对当前帧适配器与构建快照相同、项目算法与HLS实际预处理文本相同、19个生成Verilog/ROM文件与打包IP相同，以及上述报告与配套bit/HWH。执行后Notebook的输出、计数和保存元数据可改变，代码单元及固定文件继续按严格哈希检查。

## 下一步与风险

板测按[分步操作指南](a2_gaussian_validation_steps.md)完成首帧及36帧完整验证，记录5963776字。板端逐字比较通过，本机用M0九点int32参考独立复算37帧哈希、字节数及计数；4份下载的STARE输出655360字直接逐字匹配，预览和Notebook中的图像与原数组一致。原ZIP/Notebook/NPY/PNG在本地build/board_results保存，原JSON与复核清单独立归档；不是CPU替代FPGA生成的展示结果。

当前A2真机已确认PYNQ3.0.1与2017.4生成的空间滤波、标准DMA/GPIO驱动及中心G/FOV对齐。M0的完整医学分割质量有限，空间滤波通过也不能证明分割质量、现场HDMI或实时FPS。下一阶段按已选择的算法A审查15×15局部背景的定点、复制边界和资源，再接入血管响应、阈值及形态学；最终B保留官方视频数据通路。

Windows和现有Vivado继续使用，不需要给电脑安装Linux。HLS源、派生Tcl和失败/通过日志均保留在本地Git；生成工程位于build目录。上游参考目录保持不变。
