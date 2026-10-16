# A3 局部背景与血管响应：复用前置审查

2026-10-12。A2实体板37帧与4份原数组已通过；本报告在开发前冻结A3的选择与数值规格，现补充主机真实检查。**A3实体板45帧已通过并独立核验归档。** 发布时NOT_RUN历史值保留，真实记录见[A3板测报告](../results/a3_background_2017_4/board_execution_2026-10-12/verification_report.md)。

## 已查候选和选择

已读取本机Vivado HLS2017.4实际编译目录`common/technology/autopilot/hls/hls_video_imgproc.h`的BoxFilter、Box_kernel_1d、SepFilter2D及sepfilter_opr。BoxFilter可显式选择15×15、NORMALIZE=false和BORDER_REPLICATE；内部调用已有的可分离滤波、厂商LineBuffer/Window。非归一化分支使用整数1系数，垂直和水平两次累加，中间不作8位均值取整，输出uint16完整225像素总和。

选择`hls::BoxFilter<15,15,false,hls::BORDER_REPLICATE>`，输出`HLS_16UC1`，项目只在其后执行`(sum+112)/225`。sum最大57375，加112最大57487，uint16足够。默认归一化版使用定点近似1/225，不能直接假定与M0整数除法完全一致；因此关闭该功能并显式一次取整。

已查固定xfOpenCV2017.4_release的box候选：仅3/5/7尺寸和constant边界路线，不满足本次15×15/replicate要求。通用二维Filter2D同样可用，但225个点的直接二维加法没有采用厂商现成可分离BoxFilter的必要。没有修改或分发安装库头文件，不开发替代行缓存。

高斯阶段保留A2的固定整数3×3核和Filter2D/BORDER_REPLICATE；LUT继续使用已验证的固定表。新增医疗逻辑仅为`clip(4*(background-enhanced),0,255)`、诊断字节布局及中心数据延迟。采用M0已经选定的算法A，本阶段没有增加未选择的四方向算法B。

## 结构与诊断模式

PS/DDR/HP0、AXI DMA7.1、AXIS FIFO、AXI GPIO2.0、100MHz和厂商reset均由已测A2派生；帧适配器`retina_gaussian_guard`原样复用，只替换其内的HLS计算IP。无新增板级端口、XDC、DDR/DMA/HDMI底层。GPIO0x41200000与DMA0x40400000继续使用官方PYNQ3.0.1驱动。

输入为完整256²/512²帧，低至高字节为B/G/R/FOV(0或1)。算法链为G→固定高斯→固定LUT→厂商BoxFilter整数总和→精确均值→血管响应。原始G/FOV随中心像素对齐，增强值也延迟到相应背景像素。FIFO选型为高斯原数据2048字、背景中心原字8192字及增强字节8192字，覆盖最大512列、15×15启动延迟；实际生成RTL的背压/多帧测试已通过。

配置bits[1:0]为模式，bit2为256/512，与A2相同。首个被接受的像素锁存全帧配置。高斯和背景在所有诊断模式均消费完整帧，不用旁路估算算法性能。

|模式|输出低→高四字节|意义|
|---|---|---|
|0|原B、G、R、FOV|完整输入旁路|
|1|原G、LUT(Gaussian(G))、0、中心FOV|与A2模式3逐位一致的预处理诊断|
|2|原G、增强值、背景均值、中心FOV|背景和FOV对齐诊断|
|3|原G、增强值、背景均值、响应|完整A3响应诊断；高字节已不再是FOV|

模式3响应尚未按FOV屏蔽，与M0特征定义相同，供后续阈值/最终过滤使用。这里的byte2是背景，不是最终mask；没有声称完整血管分割。

## 发布前检查门槛

先进行独立C仿真，再对实际生成厂商RTL检查256/512、多模式、随机背压、配置锁存、全黑/白、边角、连续帧、真实STARE、畸形完整帧标志及在途复位。重点检查15×15复制边界、一次取整、中心对齐和8192字FIFO不会形成死锁。随后完成Vivado布局布线、100MHz时序、资源、DRC、HWH/地址/时钟复位核验及官方驱动包装的错误保留检查。

板测依然分为准备、文件预检、加载、首帧、完整套件、真实数组预览打包；主机通过不能提升为板测通过。发布配套bit/HWH/固定脚本/代码单元哈希，保存原始失败日志和新构建目录，不覆盖A0/A1/A2。

## 来源与许可

基础IP和HLS算法来自安装的AMD/Xilinx Vivado/HLS2017.4，受本机工具/IP条款约束；库头文件中保留的OpenCV版权/条件沿用[A2附带声明](a2_gaussian_validation_steps.md)。Python接口复用固定PYNQ3.0.1及BSD 3-Clause许可。STARE仅使用本地已验证RGB输入与其FOV，GT只作离线质量评价，不进FPGA；数据管理规则见`data/README.md`。

## 真实主机结果与技术边界

12帧Csim1,376,256字、实际生成RTL13完整用例1,441,792字、厂商复位、完整100MHz布局布线及58项主机回归已通过。全部安装库头保持原哈希，35份生成RTL/ROM与实际IP配对；A2 guard和三个板测辅助程序原字节复用。背景采用完整225样本总和一次取整，响应按有符号差值饱和，没有PS替代滤波。

实际整机资源为5,344 LUT/5,960 FF/25.5 BRAM Tile/1 DSP，WNS1.461/WHS0.035/WPWS3.750ns；这是完整Vivado实现，不是HLS估计。新增DSP流水优化提示已逐项审查，未改生成逻辑；原始失败、日志、来源及门槛见[A3构建报告](../results/a3_background_2017_4/build_report.md)。最终B增加显示通路后必须重新检查资源与时序，尚不能推断真机FPS。

11文件板测包位于`build/deploy/a3_background_2017_4_r1`，分六个代码框执行45帧逐字比对并保存四份真实STARE输出。具体见[A3操作指南](a3_background_validation_steps.md)。实体板45帧7,274,496字记录哈希已独立复算一致，四份实际STARE背景/响应输出655,360字逐字匹配；Notebook与四幅预览来源核验通过，归档工具20项检查通过。第三幅15×15背景平滑属于预期中间结果，未作为最终分割图。下一阶段先审查阈值、形态学和最终FOV过滤候选，完整分割/最终B/FPS仍待验证。
