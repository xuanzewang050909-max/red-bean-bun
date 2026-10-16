# A3 局部背景与血管响应：主机构建报告

日期：2026-10-12（Asia/Shanghai）。**主机检查PASS，实体板NOT_RUN。** 本次从已经实体板验证的A2派生，完成精确15×15局部背景及暗结构响应；未加入阈值、形态学、FOV最终过滤或HDMI，没有测FPS。

## 实际复用与计算

继续使用本机Windows Vivado/HLS2017.4，目标`xc7z020clg400-1`。不改官方Z2 board preset、PS/DDR/HP0、AXI DMA7.1/FIFO/GPIO2.0、100MHz/标准reset、官方PYNQ3.0.1驱动和已经验证的`retina_gaussian_guard`。只替换内部HLS计算IP为`retinafpga.local:hls:retina_background_hls:1.0`。

安装库的`Filter2D`、`BoxFilter<15,15,false,BORDER_REPLICATE>`、`SepFilter2D`、Mat/LineBuffer/Window及AXIS生成器原样使用。225像素总和保存为uint16，项目执行`(sum+112)//225`一次精确取整，再计算`clip(4*(background-enhanced),0,255)`。高斯、固定LUT和诊断/FOV中心对齐沿用A2。没有自行开发通用行缓存或DMA。

前置选择及字节布局详见[复用审查](../../docs/a3_background_reuse_audit.md)。14组仿真向量只使用RGB与其生成的FOV，不输入GT；mode1与已测A2 mode3逐位一致。预览四个字节均从实际DMA输出提取。

## 真实检查结果

|检查|实际结果|证据|
|---|---|---|
|HLS C仿真|12完整帧、1,376,256字逐字匹配|hls_attempt_01.log；导出在此日志后段失败，不能将其视为导出通过|
|HLS综合与IP配对|35个生成Verilog/ROM与实际打包IP文件完全同哈希；当前项目逻辑与真实预处理源一致；8份审查库头哈希未变|release_manifest.json的hls_provenance；ip_packaging_fixed_02.log|
|实际生成RTL|13完整用例、1,441,792输出字匹配；11有效帧、畸形完整帧标志、在途复位后恢复；随机背压/配置锁存/256与512/真实STARE|background_xsim.log，vector_manifest.json|
|标准复位IP|真实厂商IP复位与解除检查通过|vendor_reset_simulate.log|
|完整布局布线|100MHz；setup WNS1.461ns、hold WHS0.035ns、pulse WPWS3.750ns；对应失败端点均为0|timing_summary.rpt|
|实际整机资源|5,344 LUT / 5,960 FF / 25.5 BRAM Tile / 1 DSP|utilization.rpt；不是HLS单IP估计值|
|HWH/地址/连接|官方PYNQ3.0.1解析器原样使用，仅主机架构常量替身；DMA0x40400000/GPIO0x41200000、32位流、DDR窗口、100MHz、低有效复位、guard/HLS连接通过|hwh_host_check.json，release_manifest.json|
|主机软件回归|58项通过，含7项新增数值/字节布局/缓存保留/重复执行/预览和Notebook校验|host_runner_tests_release.log|
|派生一致性|7个派生源或diff可从A2原件精确重现|derivation_reproduction_publish.json|
|组装包校验|15项通过，含修改bit/HWH/辅助程序/真实输入/Notebook代码等拒绝，正常保存输出/元数据允许|release_negative_checks.json|
|实体板|尚未运行；预期45完整帧、7,274,496字逐字校验|交付Notebook待用户执行，不能提前计入PASS|

HLS估计43 BRAM18K/1 DSP/3,125 FF/8,523 LUT和8.46ns只是HLS估计，最终整机采用上表的Vivado布线后数值。A3比A2增加背景行缓存和中心对齐FIFO；仍有资源余量，但最终B的资源、时序和性能必须重新实现测量。

DRC没有Error/Critical Warning。新增三项DSP内部流水优化提示已按实际100MHz时序和具体join_words位置审查接受；标准FIFO未用状态与WRITE_FIRST建议保留。逐项理由及门槛见[drc_review.md](drc_review.md)。BD只读POLARITY提示沿用A2，但实际HWH和标准复位仿真另行核实，未仅靠消除警告判断成功。

## 发布包与板测

只发布`build/deploy/a3_background_2017_4_r1`，共11个文件，bit/HWH分别为4,045,681/350,129字节。配套脚本、真实RGB生成输入、六阶段Notebook、说明和SHA256清单均已组装校验。发布的board_status保留NOT_RUN；运行后另行独立核验，不回写发布历史。

用户操作见[A3完整步骤](../../docs/a3_background_validation_steps.md)。顺序为准备函数→预检→加载→完整256²暗条纹首帧→另44帧→真实数组四图预览与ZIP。需下载运行后的Notebook和`a3_results_bundle.zip`，再核对四份实际STARE背景/响应数组。此前A2证据不覆盖新A3逻辑。

如果板端红色报错或无进展，保留内核、输出和在途缓冲，按项目流程确认串口状态。软件超时只能在MMIO总线访问可返回时生效；没有声称能从任意AXI死锁自动恢复。

## 复现入口

以下全部使用新目录，脚本拒绝覆盖历史构建或发布：

```powershell
# 先生成A3 HLS，日期元数据修正仅在生成Tcl中进行。
E:\vivado\Vivado\2017.4\bin\vivado_hls.bat -f vivado/scripts/build_a3_hls.tcl -tclargs D:/PLD/retina_fpga/build/a3_hls_new
.\.venv\Scripts\python.exe scripts/repack_a3_ip.py build/a3_hls_new results/a3_new
# 在实际solution1/impl/ip目录运行其run_ippack_a3meta.tcl。
# 本次构建Tcl固定引用a3_hls_01；若采用新HLS目录，先保存新Tcl工作副本并仅修改该路径。
E:\vivado\Vivado\2017.4\bin\vivado.bat -mode batch -source vivado/scripts/build_a3_background.tcl -tclargs D:/PLD/retina_fpga/build/a3_background_new full
```

当前这次构建的实际目录为`build/a3_hls_01`、`build/a3_background_01`、`build/a3_axis_sim_02`、`build/a3_reset_sim_01`。原始命令/输出、使用的Tcl/guard快照、地址/时钟/资源/时序/IP XML都在本目录记录。包生成命令：

```powershell
.\.venv\Scripts\python.exe scripts/package_a3.py build/a3_background_01 build/a3_hls_01 build/a3_axis_sim_02 build/a3_reset_sim_01 build/deploy/a3_background_2017_4_r1 --results results/a3_background_2017_4 --derivation results/a3_background_2017_4/derivation_reproduction_publish.json
```

此命令已完成，再执行会拒绝覆盖。需要新发布时使用新输出与结果目录，并保留完整新验证链。

## 保留的失败与分发边界

[failure_record.json](failure_record.json)记录旧工具日期溢出、第一次导出工作目录错误、动态文件名导致的无效RTL测试和主机显示替身失败。首个RTL仿真中出现的PASS全部撤回，不计入覆盖；第二次固定文件名、未知值检查和完整仿真才有效。首次DRC门槛拒绝保存在hardware_review_probe_01.json，接受理由见审查。

`references/`和安装库未改动；未公开提交厂商库源码、bit、STARE图像、输入数组或板端原图。STARE仅本地研究，GT不进入分析。许可声明随本地包的使用说明保留。原始日志/定点规范/来源/源码和配套哈希跟随Git记录，支持回退。
