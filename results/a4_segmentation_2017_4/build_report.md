# A4 完整固定分割算法 A：主机构建报告

板测更新（2026-10-12）：实体板61帧已完成；9,895,936字记录哈希与六份真实STARE输出983,040字独立核验一致，Notebook/二值预览及26项归档检查通过。见[独立板测报告](board_execution_2026-10-12/verification_report.md)。下文保留发布时的主机状态与NOT_RUN历史，固定发布清单不回写。

日期：2026-10-12（Asia/Shanghai）。**主机验证通过，A4 实体板状态 NOT_RUN。** 已接入阈值、十字闭运算、邻域孤点过滤与最终 FOV，组成冻结的 M0 算法 A。最终算法与 HDMI 同时运行的 B 工程尚未整合，没有测量真机 FPS。本报告不把数值一致性等同于医学质量。

## 复用范围与固定算法

基线为实体板已通过的 A3 r1，来源提交 `cd0ad6a58fabf8968ef1a1893f31500ad9136c4c`。Windows 上继续使用 Vivado/Vivado HLS 2017.4，器件 `xc7z020clg400-1`；板端目标保持实测 PYNQ 3.0.1。未安装新工具或主机 Linux。

原样沿用 TUL Z2 PS preset、DDR/HP0、AXI DMA 7.1、AXIS FIFO、AXI GPIO 2.0、标准互连、100 MHz、proc_sys_reset、帧 guard 和官方 PYNQ DMA/内存驱动。发布检查将新 HWH 中十个复用模块的 VLNV、参数、端口和总线接口与已测 A3 逐项比较；仅六个 HLS 数据连接的信号别名发生变化，连接端点相同。未新增板级引脚。

算法顺序：绿色通道 → 3×3 高斯复制边界及一次整数取整 → 固定 LUT → 15×15 复制边界均值 → 饱和暗结构响应 → `response>=28` 与初始 FOV → 3×3 CROSS 膨胀 → CROSS 腐蚀 → 3×3 复制边界邻域计数 → 保留 closed 且计数≥2 且最终 FOV 的像素。邻域计数包含中心。

窗口和行缓存使用未修改的本机厂商库：Filter2D、BoxFilter、Threshold 和 morp_opr。Threshold 的严格大于语义通过 threshold=27/maxval=1 实现 ≥28；形态学使用 BORDER_CONSTANT/单次迭代，图像外为零。便捷 Dilate/Erode 固定复制边界，未直接采用。项目新增的是算法组合、中心诊断对齐和有限 FIFO 容量，不重写通用形态学基础设施。见[开发前复用审查](../../docs/a4_segmentation_reuse_audit.md)。

模式 0 原样旁路 B/G/R/FOV；模式 1/2/3 的输出字节依次为原 G、增强、初始/闭运算/最终掩膜、响应。掩膜字节只为 0 或 255。全部模式运行完整内部流水线。阈值与处理顺序沿用 M0 的训练选择，未根据测试图或人工标注调参。

## 实际验证结果

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 独立 HLS C 仿真 | 16 完整帧、2,031,616 字逐字一致；阈值边界和零边界腐蚀原语检查通过 | hls_attempt_02.log |
| 实际生成 RTL | 17 完整用例、1,900,544 输出字一致：15 有效帧、1 畸形完整帧、1 在途复位后恢复帧 | segmentation_xsim.log、vector_manifest.json |
| 流协议 | 256/512、四种模式、真实 STARE、随机背压、阻塞时数据/keep/last 稳定、配置锁存、错误标志、连续帧与复位恢复 | axis_tb_used.sv、axis_simulation_tool_02.log |
| HLS 导出及来源 | 57 个生成 Verilog/ROM 在综合输出与实际 IP 包内完全同哈希；项目逻辑与真实预处理源对应；六份实际编译库头未变 | release_manifest.json、ip_packaging_fixed_02.log |
| 实际标准复位 IP | PS 复位及辅助复位极性、故障复现与正确解除通过 | vendor_reset_simulate.log、reset_simulation_tool_02.log |
| 完整 100 MHz 布局布线 | WNS 1.170 ns、WHS 0.020 ns、WPWS 3.750 ns；setup/hold/pulse 失败端点均为零，无无时钟寄存器或组合环 | timing_summary.rpt、clocks.rpt、vivado_build_02.log |
| 实际整机资源 | 6,636 LUT / 7,293 FF / 36 BRAM Tile / 1 DSP | utilization.rpt；不是 HLS 单 IP 估算 |
| HWH 与复用连接 | 原样使用官方 PYNQ 3.0.1 解析器，仅主机架构常量使用替身；DMA 0x40400000、GPIO 0x41200000、32 位流、23 位 DMA 长度、DDR 窗口/100 MHz/低有效辅助复位核对通过；十个模块与 A3 一致 | hwh_host_check.json、release_manifest.json |
| 主机软件回归 | 87 项通过，含独立 M0 逐字参考、精确阈值、FOV/边角/孤点、故障缓冲保留、预览和可保存 Notebook 契约 | host_runner_tests_release.log、final_host_test_sources.json |
| 最终派生源复现 | 17 组 A3 原件加受控 diff 精确重现当前 A4 字节 | final_derivation_02/evidence.json、final_derivation_02/verification.json |
| 组装包校验 | 16 项通过；允许 Notebook 保存输出/元数据，拒绝代码及固定 bit/HWH/辅助程序/真实输入/说明更改 | assembled_package_validation.json、release_integrity.json |
| Git 与交付来源 | 29 份来源配对通过；继承 A0 脚本仅允许已声明 CRLF→LF，其他均逐字节相同 | git_source_attestation.json |
| A4 实体板 | 尚未执行；套件预期 61 完整帧、9,895,936 输出字 | 交付 Notebook 待用户运行，不计入板测 PASS |

真实 RTL 日志在 2026-10-12 03:23:44 完成，完整 Vivado 实现在 03:24:48 完成。RTL 仿真时间是仿真覆盖记录，不作为算法 FPS。主机软件的 DMA 替身用于故障路径测试，不作为板端数据证据。

DRC 无 Error/Critical Warning，但构建日志包含原厂 PS DDR 负 DQS 参数及只读复位参数的 Critical Warning。它们没有隐藏或改成正值；参数与已测 A3 一致，发生次数由发布门槛精确核对。DRC 四类 Warning、标准 DMA FIFO 两类 Advisory 和 HLS 模板警告的依据见[drc_review.md](drc_review.md)。

## 保留的失败及修复

1. 两次旧工具 HLS 原始导出都因日期 Revision 超出 signed core_revision 范围而失败，尽管 native exit code 为 0。C 仿真和综合结果不能替代成功导出。修复仅针对生成包装 Tcl 的 Revision=1；原脚本、diff 与成功日志保存在 ip_export_01/02，安装库、接口和生成 RTL 未改。
2. 首次 RTL 在第一幅 512 帧停于输入 7476、输出 0。实际诊断显示 aligned_closed 深度 1024 已满，而邻域 Filter2D 尚未产出。C 仿真的无界流没有暴露有限 FIFO 死锁。该硬件撤回；仅将项目 aligned_closed 扩至 2048，重新运行完整 HLS/RTL/实现/复位链。原失败源码、探针、日志和首次实现报告保留，首次 bitstream 不交付。
3. 发布程序首次因局部变量 values 被 XML 比较覆盖而拒绝打包，没有生成发布。改为 architecture_values 后重新执行全部发布门槛。该修复不修改硬件。

[failure_record.json](failure_record.json)记录这些失败。rejected_build_01 为撤回实现的报告；根目录较早 derivation_evidence/verification 与 initial_working_diffs 仅为开发过程记录。**最终发布的派生证明使用 final_derivation_02，不能用早期 diff 替代。**

## 发布与上板

只交付 `build/deploy/a4_segmentation_2017_4_r1` 的十二文件；实际来源为 `build/a4_hls_02`、`build/a4_axis_sim_02`、`build/a4_segmentation_02`、`build/a4_reset_sim_02`。bit 为 4,045,683 字节，HWH 为 350,105 字节。SHA256、已检查代码、输入、工具和依赖配对保存在[发布清单](release_manifest.json)。发布时 board_status=NOT_RUN 永久保留，板端实测另行归档。

板测顺序为准备函数 → 检查文件 → 加载 → 256² 首帧 → 另外 60 帧 → 真实输出预览及打包。六份 STARE 实际输出应合计 983,040 字，按两个尺寸、模式 1/2/3 保存。第三幅预览是最终二值候选掩膜，以最近邻缩放；A3 的背景模糊保留在内部算法中。预览只能从已逐字检查的 DMA 返回数组产生。

用户需要下载执行后的 a4_segmentation_check.ipynb 和 a4_results_bundle.zip，再独立核验版本、每帧记录、原数组与图像。完整操作见[零基础步骤](../../docs/a4_segmentation_validation_steps.md)。如果报错或无进展，保留现场及在途缓冲；软件超时不能保证从硬件总线死锁中恢复。

## 复现入口

以下为入口示例，重建需使用新目录，不能覆盖本次证据：

```powershell
& 'E:\vivado\Vivado\2017.4\bin\vivado_hls.bat' -f vivado/scripts/build_a4_hls.tcl -tclargs D:/PLD/retina_fpga/build/a4_hls_new
.\.venv\Scripts\python.exe scripts/repack_a4_ip.py build/a4_hls_new results/a4_export_new
# 在新 HLS solution1/impl/ip 目录运行生成的 run_ippack_a4meta.tcl，并核对导出日志。
.\scripts\run_segmentation_simulation.ps1 -OutputDirectory D:/PLD/retina_fpga/build/a4_axis_new -HlsBuild D:/PLD/retina_fpga/build/a4_hls_new
```

build_a4_segmentation.tcl 当前固定引用本次正确的 a4_hls_02。若换新 HLS，先保存派生 Tcl 副本和 diff，再修改该路径，运行 full 综合实现。标准复位入口为 simulate_a4_reset.tcl。当前实际打包命令已成功完成：

```powershell
.\.venv\Scripts\python.exe scripts/package_a4.py build/a4_segmentation_02 build/a4_hls_02 build/a4_axis_sim_02 build/a4_reset_sim_02 build/deploy/a4_segmentation_2017_4_r1 --results results/a4_segmentation_2017_4 --derivation results/a4_segmentation_2017_4/final_derivation_02/verification.json
```

再运行会拒绝覆盖。新发布须生成新的完整证据链；不能直接复用当前最终证明来给已修改源代码签核。

## 质量与分发

M0 固定算法 A 的既有 512 留出 AH macro Dice=0.538470、IoU=0.377561，质量有限。A4 验证的是该固定算法的硬件数值实现，没有取得新的医学质量结论。真机速度、长期稳定性、最终 B 的资源/时序/显示和端到端效果均待独立验证。

`references/`、旧发布包和安装库未改。STARE 仅传入原 RGB 及由其产生的 FOV，不含人工血管 GT。厂商库源码、bitstream 和医学输入数组不公开提交；本地包保留工具/IP条款边界、PYNQ 来源及厂商头中嵌入的 OpenCV 版权与免责声明。
