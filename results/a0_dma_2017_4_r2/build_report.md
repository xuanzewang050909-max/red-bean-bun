# A0 r2：辅助复位修正与分步板测

2026-10-11。状态：**主机验证通过；修正版17字短包及70次完整板测通过，原始执行Notebook/JSON已归档并复核。** 用户已断电恢复串口提示符，主机ping亦恢复。保留Windows/Vivado2017.4和板上PYNQ3.0.1，不重新写SD卡。

## 变更及边界

首版辅助复位低有效却接常数0，已撤回。r2保持厂商PS、DDR、AXI DMA、互连和FIFO，仅将aux复位显式标注ACTIVE_LOW并接常数1。外部复位仍来自PS FCLK_RESET0_N，debug接0、dcm_locked接1，时钟仍100MHz。没有重写厂商模块。该缺陷已被真实厂商IP仿真复现；首次板上卡住的指令未捕获，不能声称这是唯一故障根因。

测试Notebook拆为：函数定义 → 文件/版本/元数据检查 → 只加载FPGA → 官方驱动+一次17字收发 → 完整70次。每个硬件阶段前落盘状态，异常保留在途缓冲。软件超时不能恢复卡住的AXI MMIO或官方驱动构造过程。

## 实测主机结果

|检查|结果|
|---|---|
|工具/器件|Vivado2017.4，xc7z020clg400-1，TUL Z2 board preset|
|构建|build/a0_dma_2017_4_04，BD/综合/布局布线/bitstream完成|
|时序|WNS1.346ns，WHS0.020ns，WPWS3.750ns；三类失败端点均0|
|资源|LUT2648/53200，FF3443/106400，BRAM4/140，DSP0/220|
|元数据|固定官方PYNQ3.0.1 HWH parser解析通过；DMA、地址、频率、reset及FIFO检查|
|旧文件拒绝|旧HWH被新辅助复位连接断言拒绝，历史结果不覆盖|
|厂商复位仿真|proc_sys_reset5.0 rev12，旧aux=0持续复位，aux=1释放，PS复位断言/释放通过|
|测试脚本|6项主机替身/故障注入检查通过；数据损坏、长度、超时、缓冲保留、分步前置状态验证|
|Notebook|未执行、无预填输出、全部代码可编译；首单元与源脚本一致|
|板测|真实执行Notebook/JSON验证通过；70次完整收发+1次短包，配对/字节数/71个图案哈希复核一致|

生成的同次bit/HWH与Notebook/manifest打包到 `build/deploy/a0_dma_2017_4_r2`。包记录源码Commit和SHA256；旧包、首次死机截图、原始日志和测试台初版失败记录均保留。

## 复现与记录

```powershell
& 'E:\vivado\Vivado\2017.4\bin\vivado.bat' -mode batch -log build/a0_next.log -source vivado/scripts/build_minimal_dma.tcl -tclargs build/a0_next full
& 'E:\vivado\Vivado\2017.4\bin\vivado.bat' -mode batch -log build/reset_next.log -source scripts/simulate_a0_reset.tcl -tclargs build/a0_next build/reset_next
```

输出目录必须为新目录。仿真Tcl要求日志包含RESET_SIM_PASS且没有Fatal，不能仅依据模拟器进程退出码判断通过。旧测试台变量仅在声明时赋0导致2017.4混合语言边界内部值为U；改为time>0显式驱动后通过，保留失败与探针记录。

原始成功仿真：[reset_simulate.log](reset_simulate.log)、[reset_simulation_check.json](reset_simulation_check.json)。失败及恢复：[首次记录](../a0_dma_2017_4/reset_failure_2026-10-11/failure_record.md)。用户操作：[分步验证说明](../../docs/a0_dma_validation_steps.md)。真实板端JSON和执行Notebook已在board_execution_2026-10-11中归档并复核。

板测最新证据：[完整测试截图与记录](board_full_2026-10-11/record.json)。仅验证A0双向DMA/FIFO/DDR回环，不代表算法或最终显示整合通过。

最终板测归档：[verification_report.md](board_execution_2026-10-11/verification_report.md)。原始下载文件、逐文件哈希和独立图案复核均完成。
