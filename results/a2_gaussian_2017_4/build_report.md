# A2 修正版主机构建报告

接收/构建日期：2026-10-12。本阶段实体板尚未运行，状态NOT_RUN。

复用Vivado HLS2017.4未修改的Filter2D/BORDER_REPLICATE/Mat/LineBuffer，采用明确整数3×3核及单次取整。A1中已通过板测的PS/DDR/HP0/DMA/FIFO/GPIO/时钟复位结构保留。详细选择、接口与许可证见[A2复用审查](../../docs/a2_gaussian_reuse_audit.md)。

|证据|真实结果|
|---|---|
|hls_attempt_03.log|Csim8完整帧、917504字一致；综合完成；原导出日期元数据溢出失败保留|
|ip_packaging_fixed_03.log及packaging_revision.patch|仅生成Tcl的Revision改为1，后续IP导出完成|
|gaussian_xsim.log|实际生成厂商RTL，11完成用例、1114112字一致，包含真实STARE、背压及复位恢复|
|vendor_reset_simulate.log|实际A2厂商reset IP验证辅助极性与PS复位|
|hwh_host_check.json与严格发布门槛|固定PYNQ3.0.1原解析器及实际PS/DDR/DMA/GPIO、四个AXIS与HLS START/READY接线通过|
|vivado_build_02.log|build/a2_gaussian_02布局布线及bit/HWH生成完成|
|timing_summary.rpt|100MHz，WNS1.517ns/WHS0.032ns/WPWS3.750ns，0失败端点/无时钟寄存器/未约束内部最大延迟|
|utilization.rpt|3517 LUT、4829 FF、8 BRAM36等价Tile、0 DSP|
|drc.rpt|无Error/Critical Warning；已审查RTSTAT-10及标准DMA BRAM advisory|
|host_runner_tests_final.log|32项主机测试通过；FakeDMA不作为实体板证据|
|release_manifest.json/release_integrity.json|配套十文件及代码/固定文件校验通过，模拟Notebook保存不误报|

发布目录：`D:/PLD/retina_fpga/build/deploy/a2_gaussian_2017_4_r1`。板端操作见[完整步骤](../../docs/a2_gaussian_validation_steps.md)。先首帧完整256图，再36帧测试；逐字比较、字节数、硬件帧计数与错误标志；4个真实STARE输出数组及预览/JSON保存在结果ZIP中。

19个HLS生成Verilog/ROM文件与打包IP逐一哈希相同；当前项目算法与实际预处理文本一致；当前帧适配器与完整构建快照相同。两处厂商头目录不同哈希分别记录，不混淆include审查和实际autopilot编译来源。

首个build/a2_gaussian_01含START握手缺陷，已撤回，未交付/未在板上运行。第一次仿真的缺少ROM初始化与输入停住原日志保留。此次仅交付修正版02。

通过范围为高斯/G/FOV/LUT和该A2主机通路；不表示完整血管分割、最终同bitstream的HDMI、板级FPS或医学质量通过。
