# A0 DMA / Vivado 2017.4 主机构建报告

**撤回通知：本报告对应首版A0，已在首次板级尝试后发现功能缺陷。** 用户Notebook显示内核断连、保存失败，串口无响应，主机网络探测超时。`aux_reset_in`为低有效但接常数0，持续复位；此前的时序通过不证明复位功能正确。旧交付包不可再次运行。用户断电重启后已恢复串口；故障证据见 [failure_record.md](reset_failure_2026-10-11/failure_record.md)。下文保留首版主机构建的历史事实；修正版另在 `results/a0_dma_2017_4_r2` 记录。

日期：2026-10-11。**最终版本已完成 BD 验证、综合、布局布线及 bitstream 生成；板级 DMA 尚未运行。** 用户同意优先使用现有2017.4，保留板端PYNQ3.0.1，暂缓2022.1安装。A0只含标准DMA/FIFO回环，无医学算法或HDMI。

## 实际构建结果

|项目|结果|
|---|---|
|工具|Vivado2017.4，SW2086221/IP2085800，本机Windows执行|
|板级来源|固定TUL PYNQ-Z2 board/preset，`tul.com.tw:pynq-z2:part0:1.0`|
|器件|`xc7z020clg400-1`，PCB实体修订仍未知|
|最终工作目录|`build/a0_dma_2017_4_03`；前两轮和参数检查保留，未覆盖|
|BD/综合/实现/bitstream|完成；构建日志明确输出 `A0_BITSTREAM_GENERATED_TIMING_CHECKED`|
|FCLK0/AXI|100MHz；全部 PL 通路同一时钟，复位来自FCLK_RESET0_N，经proc_sys_reset|
|时序|WNS1.346ns，WHS0.020ns，WPWS3.750ns；建立/保持/脉宽失败端点均0|
|约束完整性|无时钟寄存器0、未约束内部最大延迟端点0；报告所有用户时序约束满足|
|资源|2648 LUT（4.98%），3443寄存器（3.24%）；完整资源见utilization.rpt|
|DRC|0 Error/0 Critical Warning；1项Warning、3项Advisory，保留原报告|
|PYNQ3.0.1 HWH解析器|主机架构常量替身下解析原始HWH通过；DMA参数/地址、FCLK/AXI频率、FIFO TKEEP/TLAST、复位检查通过|
|板端加载/DMA/缓存一致性|**NOT_RUN**；主机解析并不等于Overlay或实际DMA通过|
|测试运行器故障检查|4项主机测试通过：成功后的释放、数据损坏保留缓冲、长度错误保留缓冲、超时/硬件错误；使用模拟DMA，不计板级PASS|

## 复用与必要修改

直接复用processing_system7:5.5、axi_dma:7.1、axis_data_fifo:1.1、axi_interconnect:2.1、proc_sys_reset:5.0及xlconstant:1.1。未编写自定义DMA/FIFO/DDR控制器，未复制其他型号板级配置。A0无需HLS，不触发旧HLS日期导出问题。

PS由TUL Z2 preset创建，保留DDR/MIO，只启用GP0控制、64位HP0及100MHz FCLK0。GPIO、HDMI、音频/IOP不包含在A0；最终B另从官方Base派生，不能用切换bitstream代替整合。

DMA Simple，SG=0、Micro=0，MM2S/S2MM都启用，长度23位（最大8,388,607字节）。流32位并保留TKEEP/TLAST，FIFO1024拍。DMA内存MM2S64位，S2MM32位，由2017.4自身BD传播规则推导，再由标准互连宽度转换器接64位HP0。统一要求8字节地址对齐。DMA控制`0x40400000/64KiB`，两个内存口访问`0x00000000–0x1FFFFFFF`；测试只允许连续缓冲落在`0x00100000–0x1FFFFFFF`。

原始preset把GP0/HP0频率派生字段锁为USER10MHz。工作脚本仅解除这两项字段的VALUE_SRC锁定，让工具按实际100MHz连线自动传播，未改原厂XML。复位极性和S2MM宽度也由工具传播，验证后显式断言值。

## 原始警告及处理

1. 第一轮尝试手动设置派生只读参数，工具给出BD41-737；第二轮两项频率仍为10MHz。两次虽生成bitstream，均不作为交付版本。原始日志保留于`attempt_01.log`和`attempt_02.log`；最终源只用已验证传播方法。
2. 最终日志仍有PSU1–4负DDR DQS skew警告，数值来自未经修改的TUL preset。没有生成或执行ps7_init，没有重新训练或覆盖当前Linux的DDR初始化；Overlay仅用于PL与FCLK。不因日志告警随意修改板级DDR时序，板级内存收发仍须实际验证。
3. BD41-235为标准AXI4→AXI3协议转换器与PS HP0的ID宽度差异（1位与6位），源端为标准DMA单ID通路，接收方向使用低位，输出方向按生成连接补齐。未自行改标准IP；真实并发传输由70次双向回环验证，当前未运行。
4. 综合中有厂商源代码返回值、自动生成/优化层级端口等警告。最终内部时钟约束检查为0缺失；DRC RTSTAT10涉及标准FIFO优化后无负载状态网，REQP165/181为标准DMA内部BRAM WRITE_FIRST advisory。未隐藏或将警告称为零，未自行改成熟FIFO实现。

## 交付与实测

交付位置：`D:\PLD\retina_fpga\build\deploy\a0_dma_2017_4`，包含配套bit/HWH、哈希及源码清单、未执行Notebook。当前源码通过Git提交保存，构建脚本逐字节快照与当前源码一致。详见 [a0_manifest.json](a0_manifest.json)。

用户操作见 [逐步验证说明](../../docs/a0_dma_validation_steps.md)。70次收发包括短包、256²和512²帧、递增与随机数据，每次逐字比较、字节数检查和超时检查；故障不释放正在访问的缓冲。板端生成原始`a0_dma_result.json`并导出执行Notebook后才能更新板级状态。

此结果不证明旧版官方Base的HDMI/Python适配、不证明算法FPS或医学指标、不证明最终B已构建。
