# A3 布线后DRC审查

真实报告：`build/a3_background_01/drc.rpt`，Vivado2017.4，2026-10-12。初次发布门槛沿用A2仅允许RTSTAT-10，因新增DSP优化建议而拒绝；这是审查阻止发布，不是算法数值错误。未绕过时序或DRC，逐项核对后收紧为以下固定范围。

|项|位置/数量|处置理由|
|---|---|---|
|DPIP-1|join_words的同一个DSP，1项|输入未使用DSP内部流水寄存器；属于性能/功耗优化建议。该DSP用于精确常数除法，实际整机100MHz布线后WNS1.461ns，未出现负setup/hold/pulse余量。保留已逐字验证的生成逻辑。|
|DPOP-1|同一个DSP，1项|PREG=0输出流水优化建议，依据同一完整时序结果接受；未声称功耗或更高时钟已验证。|
|DPOP-2|同一个DSP，1项|MREG=0乘法级流水优化建议；依据同一完整时序结果接受，不修改厂商库或生成RTL。|
|RTSTAT-10|标准FIFO/AXI转换器内未使用的状态信号，19根|与A2相同类别，非AXI数据/时钟/复位悬空。保留成熟标准IP。|
|REQP-165/REQP-181 Advisory|标准DMA FIFO，分别1/2项|WRITE_FIRST同步双端口RAM提示；与A2的标准DMA缓存设计一致。未重写DMA；A3实体板DDR/DMA验证仍待45帧套件。|

DRC没有Error/Critical Warning。发布门槛核对四个Warning规则的顺序、DSP三个建议只来自同一个已审查join_words位置，并要求setup/hold/pulse余量均非负、无未约束延时/无时钟寄存器/组合环。任何新类别或新DSP范围继续拒绝。

BD中的单项read-only辅助复位POLARITY提示沿用A2；实际HWH的C_AUX_RESET_HIGH=0且接const_one，厂商复位仿真通过。没有仅依靠警告文案推断复位正确。
