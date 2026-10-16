# A4 实际告警与布局布线审查

日期：2026-10-12。真实工程为 `build/a4_segmentation_02`，Vivado 2017.4，xc7z020clg400-1，100 MHz。此次审查仅支持主机发布；A4 板测仍为 NOT_RUN。

## 布线后 DRC

drc.rpt 共七个 violation：四个 Warning 和三个 Advisory，没有 Error 或 Critical Warning。

| 规则 | 数量与范围 | 审查依据 |
|---|---|---|
| DPIP-1 | 1；response_carrier 内唯一 DSP 的输入流水提示 | 用于精确局部均值常数除法 225；保留生成数值逻辑，实际 100 MHz 完整时序通过 |
| DPOP-1 | 1；同一 DSP，PREG=0 | 输出寄存器优化建议，依据相同布线后结果接受；没有验证更高频率或功耗 |
| DPOP-2 | 1；同一 DSP，MREG=0 | 乘法级寄存器优化建议；未修改库或生成 RTL 来消除文案 |
| RTSTAT-10 | 1 组；标准 FIFO/互连未使用状态信号 | 不是新增数据、时钟或复位悬空；保留原厂标准 IP |
| REQP-165 | 1 Advisory；标准 DMA FIFO | 厂商 WRITE_FIRST 同步 RAM 建议，原样沿用已测 A3 配置；新的 A4 DMA 实测仍待执行 |
| REQP-181 | 2 Advisory；标准 DMA FIFO | 同上；不把警告消失或 CPU DMA 替身视为板端内存验证 |

三个 DSP 提示都来自 `a4_segmentation_i/segmentation_filter/inst/response_carrier_U0/retina_segmentatiyd2_U84/retina_segmentatiyd2_DSP48_0_U/in00`。门槛限制为这些具体位置和四种 Warning，新增规则或新的 DSP 范围会拒绝发布。

真实 timing_summary.rpt：WNS 1.170 ns、WHS 0.020 ns、WPWS 3.750 ns；三个失败端点数为零。无无时钟寄存器、组合环或发布门槛检测到的未约束延时。实际整机为 6,636 LUT、7,293 FF、36 BRAM Tile、1 DSP；这些是布线后数值。

## 构建日志的 Critical Warning

DRC 报告无 Critical Warning 不表示整次构建日志没有 Critical Warning。vivado_build_02.log 的以下二十一条全部保留，并按完整文字及次数检查：

| 规则 | 内容 | 出现次数 | 依据 |
|---|---|---|---|
| PSU-1 | PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_0=-0.051 | 5 | TUL Z2 preset 原值，与已测 A3 的完整 PS 参数一致 |
| PSU-2 | PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_1=-0.006 | 5 | 同上 |
| PSU-3 | PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_2=-0.009 | 5 | 同上 |
| PSU-4 | PCW_UIPARAM_DDR_DQS_TO_CLK_DELAY_3=-0.033 | 5 | 同上 |
| BD 41-737 | reset_100m/aux_reset_in 的 POLARITY 为只读 | 1 | HWH 实际 C_AUX_RESET_HIGH=0、const_one 连接及真实厂商复位仿真另外核实 |

没有屏蔽 Critical Warning，也没有为消除文案将板级 DDR 时序参数改成正值。十个复用模块与 A3 的参数/端口/总线逐项一致，见 release_manifest.json。A3 的真机证据支持延续其既有板级配置，但不能代替 A4 的新板测。

## HLS 警告和失败

实际 morp_opr 模板选择 CROSS/ITERATIONS=1/BORDER_CONSTANT。旧编译器仍对未执行的 ITERATIONS>=2 分支内部 internal[-1] 报警；常量选择的单次 filter_opr 分支不访问该索引。原语 C 仿真及完整 C/生成 RTL 的零边界结果逐字通过。编译头只读，哈希与预处理来源保留；未把专有头复制或修改进项目。

首次有限 FIFO 死锁与旧工具日期 Revision 导出失败没有归类为可忽略警告；原失败撤回保留。仅正确的第二次完整生成 RTL、实现、复位和配对验证支持此发布。详见[构建报告](build_report.md)和[failure_record.json](failure_record.json)。
