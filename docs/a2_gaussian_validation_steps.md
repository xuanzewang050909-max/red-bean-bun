# A2 高斯滤波验证：可自行按顺序执行

2026-10-12状态：本次用户已完成全部步骤并下载原始文件；37帧与4份真实输出数组已独立核验归档，见[A2板测报告](../results/a2_gaussian_2017_4/board_execution_2026-10-12/verification_report.md)。本指南保留供新目录复现；当前已通过的Notebook无需重新运行。

电脑继续使用Windows；板端仍用PYNQ3.0.1。原A0/A1通过记录保留，A2放在新目录。板卡供电、MicroUSB及网线保持连接，PuTTY仍为COM9/115200，Jupyter为 `http://192.168.2.99:9090/tree`。

## 1. 结束旧测试内核

确认A1通过记录已下载。旧A1 Notebook菜单 File → Close and Halt；如果已关闭网页标签，可在Jupyter首页 Running 页找到旧A1，点其旁的Shutdown。不要重新运行旧A0/HDMI/A1 Notebook。本操作适用于之前已经顺利完成、DMA空闲的状态。

## 2. 创建新文件夹、上传全部文件

Jupyter文件列表右上角 New → Folder。勾选新目录，Rename改为 `retina_a2_r1`，进入目录。点Upload，在电脑文件资源管理器地址栏输入：

`D:\PLD\retina_fpga\build\deploy\a2_gaussian_2017_4_r1`

选择里面全部10个文件。列表出现待上传条目后，逐条点其Upload按钮完成上传；不要只选择Notebook。

- a2_gaussian.bit、a2_gaussian.hwh：配套FPGA文件。
- a2_manifest.json：版本和配对校验清单。
- a2_gaussian_check.ipynb：本次操作Notebook。
- a2_gaussian_board_test.py：本阶段测试脚本。
- a1_point_board_test.py、a0_dma_board_test.py：复用校验/等待/错误处理辅助函数；导入不会加载旧Overlay。
- stare_im0001_256.npy、stare_im0001_512.npy：仅从真实RGB生成的输入和FOV，不含血管标注。
- 使用说明.txt。

## 3. 逐框运行

打开 `a2_gaussian_check.ipynb`，每次点一个代码框，按Shift+Enter。当前框左侧从 `In [*]` 变成 `In [数字]` 且无红色报错，才进入下一框。

|代码框|完成标志|
|---|---|
|1. 准备函数|In [数字]，无报错；没有PASS打印是正常的|
|2. 检查文件|A2_PRECHECK_PASS；尚未加载FPGA|
|3. 加载|A2_LOAD_PASS；显示器可能无信号|
|4. 首帧验证|A2_SMOKE_PASS；确认网页正常、PuTTY回车仍有提示符|
|5. 完整验证|连续输出GAUSSIAN_FRAME_PASS，最终 `A2 GAUSSIAN PASS: 37 complete frames matched`|
|6. 查看FPGA结果并打包|显示三幅眼底灰度图并打印 A2_RESULTS_READY|

第5框含256/512、旁路/绿色/高斯/高斯+LUT、二维渐变/随机/棋盘/边角脉冲/黑白/STARE，共首帧加36帧。每帧逐字比较真实DMA返回结果，并校对收发字节数、FPGA输入/输出计数和错误标志。第6框只对已通过的真实FPGA输出进行展示和打包，不在PS上代替FPGA做高斯处理。

若出现红色报错，或一分钟没有新的输出，停在当前框并保留截图；不要反复点击、释放缓冲、切换Overlay或重启内核。先反馈PuTTY是否仍响应。软件轮询的时限只在硬件总线访问能返回时有效。

## 4. 下载执行证据

按Ctrl+S。File → Download as → Notebook，下载执行后的Notebook到电脑。回同目录文件列表，勾选并下载 `a2_results_bundle.zip`。包中含原始JSON、4个实际STARE输出数组及预览图。反馈下载完成后，项目将核对数值、清单和原始数组再归档。

当前完整医学链的输出格式尚未在此阶段使用。A2模式0原32位输入旁路；模式1/2/3低字节均为原始G，次字节分别为G、Gaussian(G)、LUT(Gaussian(G))，bits[23:16]为0，高字节为延迟对齐的中心FOV。全部模式都经过同一个厂商滤波帧引擎；模式0/1用于诊断，不能拿来估算最终算法性能。

配置和状态仍由官方AXI GPIO0x41200000提供，DMA仍为0x40400000、100MHz。配置bits[1:0]为模式0–3，bit2为256/512选择，首个输入被接受时锁存。输入TLAST位置/TKEEP检查错误记入状态bits[28]/[29]，额外输出错误为bit30；输入/输出计数仍在bits[13:0]/[27:14]。A2按完整尺寸计输入帧并重新生成输出帧TLAST；畸形帧只用于主机仿真，板测只发送合法完整帧。

本阶段主机通过不等于板测通过；板测通过也仅证明高斯、LUT、G/FOV对齐和DMA通路。局部背景、血管阈值/形态学、最终HDMI B整合及真机FPS仍需后续验证。

## 5. 开发库来源与附带声明

PYNQ官方API/驱动来自固定v3.0.1，版权和BSD 3-Clause原件保存在项目references中；本包的测试包装脚本为项目新增。PS/DMA/GPIO/FIFO/reset及HLS生成物受本机AMD/Xilinx工具/IP条款约束，安装库源码未随包分发。STARE原RGB来源为Clemson STARE im0001，仅作本地研究验证；本包不含血管人工标注。

Filter2D所用厂商hls_video_imgproc.h注明部分代码源自OpenCV。以下保留其嵌入的版权、条件及免责声明：

```text
Copyright (C) 2000-2008, Intel Corporation, all rights reserved.
Copyright (C) 2009, Willow Garage Inc., all rights reserved.
Third party copyrights are property of their respective owners.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

  * Redistribution's of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.

  * Redistribution's in binary form must reproduce the above copyright notice,
    this list of conditions and the following disclaimer in the documentation
    and/or other materials provided with the distribution.

  * The name of the copyright holders may not be used to endorse or promote products
    derived from this software without specific prior written permission.

This software is provided by the copyright holders and contributors "as is" and
any express or implied warranties, including, but not limited to, the implied
warranties of merchantability and fitness for a particular purpose are disclaimed.
In no event shall the Intel Corporation or contributors be liable for any direct,
indirect, incidental, special, exemplary, or consequential damages
(including, but not limited to, procurement of substitute goods or services;
loss of use, data, or profits; or business interruption) however caused
and on any theory of liability, whether in contract, strict liability,
or tort (including negligence or otherwise) arising in any way out of
the use of this software, even if advised of the possibility of such damage.
```
