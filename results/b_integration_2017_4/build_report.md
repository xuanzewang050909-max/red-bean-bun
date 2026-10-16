# B 同工程整合：真实主机构建报告

2026-10-12。状态 **主机通过；实体板 NOT_RUN**。用户同意后继续使用现有 Windows / Vivado 2017.4，没有安装新工具。正确工程 `build/b_integration_05`，发布目录 `build/deploy/b_integration_2017_4_r1`，共十三文件。

同一 bitstream 保留固定 PYNQ v2.2.1 Z2 Base 的完整 video、PS/DDR、四组板载GPIO和系统中断，接入已完成61帧板测的A4冻结M0算法。删除音频/IOP/Trace并同步删端口/约束/PS外设；保留原视频驱动层次。算法100MHz/HP2，视频DDR原FCLK1实际142.857MHz/HP0；GP0原M03/M06接算法配置GPIO和DMA。地址为GPIO `0x43C80000`、DMA `0x40400000`，原开关 `0x41200000`、VDMA `0x43000000`不变。

|检查|实际结果|
|---|---|
|完整布局布线/bitstream|实际生成 `system_wrapper.bit`，与发布bit原字节一致|
|时序|WNS **0.341 ns**，WHS **0.008 ns**，WPWS0.000ns；失败端点均0|
|内部时序覆盖|无无时钟寄存器、未约束内部最大延迟端点、组合环|
|资源|15,823 Slice LUT、24,316 FF、46 BRAM Tile、19 DSP|
|DRC|无错误/关键警告；保留50项具体警告/建议，原报告归档|
|外部时钟源|真实MMCM SerialClk500MHz、BUFR PixelClk100MHz默认配置，SerialClk master为FCLK0；运行时720p60由原官方驱动配置，尚未实测|
|Video BD对照|41对象标准语义一致；另一对象准确核验标准生成的冗余协议适配器删除及全部连接|
|A4模块|九模块功能参数一致，除实例名和GPIO地址；guard原字节一致|
|源文件对照|实际编译57份A4 RTL/ROM、8份官方HLS视频RTL、30份RGB/DVI/动态时钟/颜色交换RTL及约束，合计95份逐字节一致|
|参考原件|v2.2.1的1417文件、v3.0.1的958文件SHA复核未改；准备Base原BD未改|
|真实reset仿真|`b_reset_sim_03` 三个实际生成厂商模块通过；复位、算法辅助复位隔离和恢复通过，18001ns结束|
|主机测试|20项通过，包含收发故障、显示缓冲所有权、切换Overlay拒绝、计时样本、370帧完整假硬件流程和约束/时序拒绝；假硬件不是板测证据|
|组装包|十三文件精确哈希，九代码单元无输出；自动保存输出改变可接受，代码/固定文件变更拒绝|

官方XDC保留36个GPIO/HDMI管脚；精简过程仅删不用的音频/IOP等约束，名义RX120MHz改精确周期8.333333ns，避免599.952MHz VCO取整违规。官方rgb2dvi XDC无条件从PixelClk派生SerialClk，与原Base外部MMCM/BUFR结构不符；仅在本项目禁用这一个不适用文件的综合/实现使用，未改IP源码或其他XDC。时钟关系由真实工具自动派生，未添加泛化false_path或降低警告等级。

总线skew报告保留官方异步视频FIFO的Gray同步约束；各项slack非负。11个未指定输入延迟的异步GPIO/HDMI DDC输入和17个未指定输出延迟的GPIO/HPD/TMDS输出沿用官方约束；不将内部完整时序报告当作外部显示观察。DRC的DPIP/DPOP建议限定在原A4常量除法和两个未修改的官方颜色矩阵；RTSTAT与RAM模式建议也保留，没有据此改冻结算法或成熟视频RTL。

首次完整 `_04` 的bit已拒绝发布，虽然其报表显示时序满足，但残留音频端口约束、RX VCO取整和错误的外部SerialClk来源仍需修复。早期项目设置失败、主动停止、主机粗粒度计时和假测试上下文失败全部见 `failure_record.json`；不将失败覆盖成PASS。

实体板下一步：单次B加载与官方驱动绑定→算法首帧→显示彩条/位置照片→同工程61分割帧→真实医疗图照片→三组3预热+100计时，合计370帧70,647,808字。照片、原数组、同工程记录和速度独立复核。程序记录单调高精度perf_counter_ns的完成事务速度与完整循环速度；不是PL周期吞吐率，不把720p60配置当算法FPS。B真实显示、吞吐与医学质量没有新PASS。

来源及操作分别见 [复用审查](../../docs/b_integration_reuse_audit.md)和[上板步骤](../../docs/b_integration_validation_steps.md)。主要原始证据为 `build_05.log`、`timing_summary.rpt`、`drc.rpt`、`clocks.rpt`、`clock_interaction.rpt`、`bus_skew.rpt`、`vendor_reset_simulate.log`、`host_tests_release.log`、`host_metadata_final.json`、`compiled_source_reuse.json`、`release_manifest.json` 和 `release_integrity.json`。
