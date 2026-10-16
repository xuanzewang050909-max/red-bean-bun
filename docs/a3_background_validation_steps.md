# A3 局部背景与血管响应：按顺序执行

电脑继续使用Windows；板卡使用已经验证的PYNQ3.0.1。MicroUSB供电与网线保持连接，PuTTY为COM9/115200，网页为 `http://192.168.2.99:9090/tree`。A2通过记录已经归档，无需再运行。

## 1. 结束已完成的旧测试

在旧A2 Notebook菜单选择 File → Close and Halt。如果网页已关闭，在Jupyter首页的Running页找到旧A2，点Shutdown。此操作适用于上一轮已经完成、DMA空闲的状态。不要重新运行旧A0/A1/A2或HDMI测试。

## 2. 建文件夹、上传文件

回到Jupyter文件列表，右上角 New → Folder。勾选新目录，点Rename，改名为 `retina_a3_r1`，进入该目录。点Upload，在Windows文件选择窗口的地址栏粘贴：

`D:\PLD\retina_fpga\build\deploy\a3_background_2017_4_r1`

选择全部11个文件。文件出现于网页待上传列表后，逐条点Upload完成上传。不要只上传Notebook。

|文件|用途|
|---|---|
|a3_background.bit、a3_background.hwh|配套FPGA配置与硬件说明|
|a3_manifest.json|版本与文件校验清单|
|a3_background_check.ipynb|本次操作页面|
|a3_background_board_test.py|本阶段测试程序|
|a2_gaussian_board_test.py、a1_point_board_test.py、a0_dma_board_test.py|复用参考比对、等待和错误保留；导入这些文件不会加载旧工程|
|stare_im0001_256.npy、stare_im0001_512.npy|真实RGB生成的输入和FOV，不含血管人工标注|
|使用说明.txt|本指南及许可声明|

## 3. 打开Notebook，逐框运行

点击 `a3_background_check.ipynb`。每次点击一个代码框，按Shift+Enter。当前框左边 `In [*]` 表示运行中；变成 `In [数字]` 且没有红色报错才表示结束。不要点击Run All。

|代码框|完成标志|
|---|---|
|1. 准备函数|In [数字]，无红色报错；没有PASS打印也正常|
|2. 检查文件|`A3_PRECHECK_PASS`；FPGA未改变|
|3. 加载|`A3_LOAD_PASS`；显示器可能无信号|
|4. 首帧验证|`A3_SMOKE_PASS`；网页正常，PuTTY按回车仍出现提示符|
|5. 完整验证|不断出现`BACKGROUND_FRAME_PASS`，最后出现`A3 BACKGROUND PASS: 45 complete frames matched`|
|6. 查看FPGA结果并打包|显示四幅眼底图，出现`A3_RESULTS_READY`|

第5框包含首帧之外的44帧，每帧检查实际DMA数据、收发字节数、输入/输出帧计数与错误标志。测试包含256/512尺寸、多模式、随机/渐变/黑白/棋盘/边角脉冲/暗条纹/取整和真实眼底输入。

第6框从实际FPGA返回并已经比对通过的512×512数组提取四个字节，依次显示原始绿色、亮度增强、15×15背景、暗结构响应。响应图中血管等较暗结构通常变亮；它尚未经过阈值、形态学和FOV最终过滤，因此不是完整分割。网页显示无需HDMI；下一阶段再加入剩余算法。

若出现红色报错，或一分钟没有新输出，停在当前框并保留截图。不要重复运行、重启内核、释放缓冲或切换Overlay。反馈当前报错与PuTTY是否响应；软件等待限时只在硬件总线访问能返回时有效。

## 4. 保存并下载两份记录

按Ctrl+S保存。菜单 File → Download as → Notebook，下载执行后的 `a3_background_check.ipynb`。回到同一目录文件列表，下载 `a3_results_bundle.zip`。ZIP含原JSON、四份真实STARE输出数组与预览图。两份文件均下载到电脑后反馈“已下载”，项目会独立核验并归档。

测试前发布清单中的板级状态保留NOT_RUN；主机仿真、实现通过与实体板运行通过分开记录。本套件没有测FPS，也没有包含最终HDMI整合。

## 输出诊断规格

输入32位字从低到高为B/G/R/FOV；GPIO配置bits[1:0]为模式，bit2选择256（1）或512（0）。模式0返回原输入；模式1返回原G/增强/0/FOV，等同A2模式3；模式2返回原G/增强/背景/FOV；模式3返回原G/增强/背景/响应。模式3高字节不再表示FOV，保持与CPU特征定义相同。

背景为复制边界的225样本总和一次取整 `(sum+112)//225`；响应为 `clip(4*(background-enhanced),0,255)`。帧适配、标准DMA与官方驱动原样复用。

## 许可与本地数据

PYNQ官方API/驱动版权和BSD 3-Clause原件保存在项目references中；本包的测试包装脚本为项目新增。PS/DMA/GPIO/FIFO/reset及HLS生成物受本机AMD/Xilinx工具/IP条款约束，安装库源码未随包分发。STARE原RGB来源为Clemson STARE im0001，仅作本地研究验证；数据与输入包不公开提交，未假定其公开再分发许可。本包不含血管人工标注。

Filter2D/BoxFilter所用厂商hls_video_imgproc.h注明部分代码源自OpenCV。以下保留其嵌入的版权、条件及免责声明：

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
