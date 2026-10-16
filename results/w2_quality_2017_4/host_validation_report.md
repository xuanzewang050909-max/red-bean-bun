# W2 + Q2 主机验证与板测交付

2026-10-14。**主机验证与新包交付完成；实体板 NOT_RUN。** 主线仍为 W1 → Q1 → W2+Q2 → W3 → W4+Q3 → W5。原 A4/W1 与已归档板测不变，取消 HDMI 的要求继续有效。

## 实现与依据

原 A4 派生新 `retina_quality_hls`，加入冻结候选 C2 的4方向9点线、侧距1…5双侧差≥9支持及无支持时饱和减28。保留原 Gaussian/LUT/Box15/FOV/闭运算/邻域计数与 A28 对照。C2惩罚28和可调分割阈值T独立。

新 `retina_quality_guard` 首输入握手锁存整帧算法、stage、尺寸、T和16位任务标记；复用官方AXI GPIO增加RQ21观测页。实际核心输入/末输出首次有效/末输出接受、输入空等和输出背压计数具有32位饱和与溢出拒绝。完成快照和任务帧号绑定，PS读回参数，禁止用提交值冒充生效值。接口见[ABI](../../docs/w2_guard_abi.md)。

原PS、DDR、AXI DMA、FIFO、GPIO和reset配置逐参数一致；新增观测GPIO为0x41210000，原DMA0x40400000、控制GPIO0x41200000不改。官方PYNQ3.0.1 HWH解析通过。实现RTL/ROM、HLS生成源、导出IP逐字节配对，未改安装头文件。

## 已完成主机证据

|项目|真实结果与边界|
|---|---|
|完整HLS Csim（独立阶段）|24整帧、2,949,120字，见[Q2流水线报告](../q2_pipeline_2017_4/host_validation_report.md)|
|新guard + 实际HLS RTL|17整帧、2,490,368字，256/512、A/C2、全部stage、T1/27/28/29/255；有限FIFO/背压/帧中改参/异常TLAST和TKEEP/在途复位后恢复均通过|
|观测guard单元|6帧589,824字，精确边沿计数、原子快照、8位测试计数器饱和、非法配置；使用替身核心，只作单元证据|
|Python|28项不同检查：观察器10、板测流程/故障保留7、包与预检查8、下载复核3；假DMA与合成时间只用于主机测试|
|完整Vivado 2017.4实现|XC7Z020，100MHz；11835 LUT、11591 FF、57.5 BRAM Tile、1 DSP；WNS0.909ns、WHS0.009ns，无时序违例|
|复位/DRC|实际生成的厂商reset仿真通过；DRC无Error/Critical Warning，原DSP流水建议、标准FIFO/BRAM建议及原TUL DDR偏斜警告原样保存并审查|

原始日志、失败/中断、源码快照、资源/时序、受控diff及配对清单在[host_release_01](host_release_01/verification.json)。axis_01在向量目录预检查失败；axis_02因已发现的发送端中断后信号清理问题主动停止，9帧部分通过不计整套PASS；修正测试发送端后的axis_03全套通过。板测脚本第一次主机预览负例缺IPython测试替身也保留。HLS2017日期Revision溢出复用既有元数据修正，未改RTL/ROM。

## 交付与下一步

`build/deploy/w2_quality_2017_4_r1` 共11文件；[七框板测步骤](../../docs/w2_quality_board_steps.md)。先预检查、只加载、单帧，再61帧原A28和19帧C2/切换/阈值，合计80帧13,303,808字。预计算参考只用于核验；预览和导出只使用完成DMA后的普通CPU快照，所有80份真实输出保存。

收到运行Notebook和 `w2_results_bundle.zip` 后，以 `scripts/verify_w2_board_results.py` 独立核验完整字数组、实际参数/计数、计时边界、预览像素、版本和执行代码。新算法浏览器整合在W3，旧8090仍是A28。本轮尚无新板测图像、核心时间或质量/FPS收益；正式20图×两尺寸×AH/VK、四类时间、CPU/功耗与长时稳定验证仍保留。
