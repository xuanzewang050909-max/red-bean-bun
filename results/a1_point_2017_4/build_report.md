# A1 r1：绿色通道/LUT 单级 Overlay 主机报告

日期：2026-10-11。**完整bitstream已生成，主机检查通过；A1实体板尚未运行。** 现有Vivado2017.4、XC7Z020CLG400-1、TUL PYNQ-Z2 preset、目标运行时PYNQ3.0.1。不要求安装Linux或2022.1。

## 架构与复用

从已板测的A0 r2脚本派生，原脚本、bit/HWH及板测记录保留。可审查差异见[a0_to_a1.diff](a0_to_a1.diff)，派生工具为scripts/derive_a1_tcl.py。

DDR → 标准AXI DMA MM2S → retina_point_axis → 原AXIS FIFO → 标准S2MM → DDR。GP0控制DMA和新增axi_gpio2.0；HP0访问DDR；统一FCLK100MHz与原厂商proc_sys_reset。GPIO不连接板外引脚，因此不增加或编造XDC脚号。

AXI DMA保持0x40400000；GPIO0x41200000双32位通道。功能仅为32位旁路、G字节提取、直接LUT(G)与帧诊断。没有Gaussian、背景响应、分割或HDMI。完整算法A仍以M0参考规范逐级实现。

## 实際执行的验证

- Verilog-2001编译与xsim通过。逐字核对655365输出，输入655366字，其中1字在输出受阻时被有意复位丢弃。覆盖全部256灰度、256/512、多帧、随机READY、等待时稳定输出、帧中配置切换、65536连续时钟收字、复位恢复、TKEEP/早晚及缺失TLAST/保留模式错误状态。原始日志见point_xsim.log。
- 19项主机测试通过：包括A0故障处理、M0定点与GT隔离、A1数据损坏/长度/计数错误保留缓冲及禁止错误后继续测试；fake DMA仅验证测试器，不能代表硬件。见host_runner_tests.log。
- HWH由固定官方PYNQ3.0.1解析器读取；DMA地址/参数、HPDDR窗口、100MHz、辅助复位接constant-one检查通过。另逐项验证GPIO地址/参数、point_stage的5个AXIS信号、32位配置/状态、时钟和reset实际连接，package_a1.py在打包前强制检查。
- 对A1实际生成的proc_sys_reset重新仿真，复用A0测试台，仅修改生成IP实例名。复现旧tie-low故障，并验证tie-high释放、PS复位与恢复。原始reset_simulate.log及适配后的reset_tb_used.sv均保留。
- **完整PS/AXI/DMA/点处理工程**综合、布局布线、bitstream生成完成。setup WNS=1.536ns、hold WHS=0.030ns；setup/hold/pulse失败端点均0；无未约束内部最大延迟端点，无无时钟寄存器。见timing_summary.rpt。
- 完整资源：2999 LUT（5.64%）、4139 FF（3.89%）、4 BRAM Tile（2.86%）、0 DSP。不是仅自定义模块资源。没有实测算法FPS或功耗。

## 保留的失败与告警

第一轮module_ref拒绝SystemVerilog顶层（2017.4限制），失败日志failed_sv_module_reference.log保留；改为原生Verilog-2001后重做仿真及构建，没有删除版本检查或升级IP。

BD脚本继承A0对辅助reset POLARITY属性的setter，该属性在此工具中只读，产生一条已核对的Critical Warning。打包只允许这条精确告警；实际派生参数C_AUX_RESET_HIGH=0、constant-one接线及厂商复位仿真分别检查，并非靠setter成功来保证连接。其他未知Critical Warning会阻止打包。标准GPIO标量连接覆盖自动GPIO接口告警符合本设计内部32位控制连接，无外部GPIO。

最终DRC没有Error/Critical Warning，保留RTSTAT-10（厂商FIFO无负载内部信号）及REQP-165/181（厂商DMA BRAM WRITE_FIRST）提示；未改动成熟IP来消除这些提示。首版板级单帧/连续帧需要验证完整通路和标准IP运行。

早期单模块OOC在build/point_ooc_02生成过估算报告，有OOC接口路由及HD.CLK_SRC未指定告警，不能用于完整时序签核；当前交付依据上述含真实PS时钟的完整A1实现，未把OOC估算当成板测性能。

## 交付与下一步

工程：build/a1_point_02。七文件包：build/deploy/a1_point_2017_4_r1。release_manifest.json记录配对文件与源码哈希，board_status=NOT_RUN；[操作说明](../../docs/a1_point_validation_steps.md)和notebooks/a1_point_check.ipynb引导先检查、再加载、首帧、完整17帧及保存原始记录。

没有在本次主机开发中自动下载到板卡。运行完配套Notebook后，依据真实JSON、输出哈希、字节数和计数确认，不能将A0板级PASS转移到A1。A1通过后再接入Gaussian等空间滤波；最终B须同时含完整医学算法与官方HDMI通路。
