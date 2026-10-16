# Vivado工程入口与复现说明

## 当前可直接查看的可信工程

- 原工程：`D:/PLD/retina_fpga/build/q4d_detector_full_02/q4d_detector.xpr`。用Vivado **2017.4**打开查看Block Design、实现器件、Timing Summary与Utilization，不升级IP或覆盖原结果。
- 完整构建报告：该目录的`timing_summary.rpt`、`utilization.rpt`、`drc.rpt`、`clocks.rpt`、`ip_status.rpt`。
- 构建时脚本/拓扑：同目录`build_script_used.tcl`、`reconstructed_bd.tcl`、`configuration.txt`。
- 生成的算法RTL：`D:/PLD/retina_fpga/build/q4d_detector_hls_03/solution1/syn/verilog`。
- 实际导出IP：`D:/PLD/retina_fpga/build/q4d_detector_hls_export_02/solution1/impl/ip`。
- 当前受控源：`D:/PLD/retina_c7_system/hls/retina_detector_hls.cpp`、`retina_c7_model.hpp`及相关HLS文件；`rtl/core/retina_detector_guard.v`；`vivado/scripts/build_q4d_detector.tcl`。

本轮只整理与核对，不重跑已经通过的综合/布线。当前打开的原XPR含原路径引用，不宣称复制XPR一个文件即可跨电脑复现。

## 交付快照

`build/delivery/c7_handoff_r2`包含（r1初版保留）；当前整理版包含受控源码快照、真实生成的IP/RTL、配对板包、关键原始报告、初版设计/性能/质量说明及逐文件SHA清单。完整旧构建目录、所有原始板测ZIP和失败证据仍保留在原位置；快照不能替代唯一历史备份。无需把工程快照上传到板卡SD。

## 在新目录重建系统（需要时执行，本轮未运行）

解压源码快照到新目录，使用匹配Vivado2017.4，从已归档生成IP构建，保留原目录：

```powershell
& 'E:/vivado/Vivado/2017.4/bin/vivado.bat' -mode batch -source '<源码目录>/vivado/scripts/build_q4d_detector.tcl' -tclargs '<全新输出目录>' full '<交付目录>/generated_ip'
```

脚本拒绝覆盖既有输出，使用源码相对路径中的板卡preset与守卫逻辑。新生成bitstream必须重新配对检查HWH、资源/时序和实际输出，不能因为源相同就直接继承旧板测通过。不同构建结果SHA未必相同。

从HLS源完全重生时使用`build_q4d_detector_hls.tcl <新HLS目录> synth`，之后在独立副本用`export_q4d_detector_hls.tcl`导出。**原Csim测试台仍引用原绝对向量路径**`D:/PLD/retina_fpga/build/q4d_detector_vectors_01`；迁移机器需先恢复配对向量或在新副本明确改路径并保存diff，不能声称本快照已验证跨路径一键重建。2017.4生成日期Revision溢出使用原`scripts/repack_a4_ip.py`流程，仅修改生成包装Tcl的Revision；不得修改安装库或算法RTL。原流程细节与失败见[q4d_c7_build_audit.md](q4d_c7_build_audit.md)。

实际RTL仿真使用Vivado XSim2017.4。初始化需要已验证的`-maxdeltaid 50000`；这只是允许初始化完成，不表示功能通过。分片脚本依赖原编译快照和向量；完整重仿真需重建这些输入，不把历史日志当成新运行。历史结果和对应SHA在results/q4d_detector_2017_4_r1。

## 答辩时的演示顺序

1. Vivado查看原full_02工程连接：PS、DDR、DMA、算法核、GPIO观测、时钟复位。
2. 展示布线后100MHz时序、资源报告和bit/HWH身份。
3. 展示真实仿真记录及一次输入输出对照，说明主机仿真与实体板测区别。
4. 转到Jupyter加载同一可信硬件，再浏览器实际切图/参数/模式；报告核心、完整推理和网页延迟各自含义。

任何新Vivado截图建议先关闭自动升级提示，不重置runs；视频中的板测必须是真实新任务。
