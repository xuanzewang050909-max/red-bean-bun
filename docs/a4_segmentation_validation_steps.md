# A4完整固定分割算法：零基础板卡验证步骤

本套件适用已验证的PYNQ-Z2、PYNQ 3.0.1及本次Vivado 2017.4生成工程。Windows电脑无需安装Linux。现在验证阈值、闭运算、孤点过滤和最终眼底区域过滤，与A3已验证的高斯/增强/背景/响应组成完整固定算法A。

## 1. 结束旧测试

保持板卡供电和网线连接，PuTTY仍用COM9、115200。旧A3的Notebook和ZIP已经下载后，在浏览器打开 `http://192.168.2.99:9090/tree`，点首页的 **Running** 标签，找到已完成的A3 Notebook，点其 **Shutdown**。仅关闭浏览器标签不会关闭内核。完成的旧A0/A1/A2测试内核若仍运行，也在这里关闭；保留原文件。不要点击页面右上方Quit。

此处只适用于已经顺利完成、没有正在传输数据的旧测试；若旧测试还报错或卡住，请保留现场并反馈。

## 2. 创建新文件夹并上传12个文件

1. 回到 **Files** 标签，点 **New → Folder**。
2. 勾选新建文件夹，点 **Rename**，改为 `retina_a4_r1`。如果已有这个名称，使用一个新名称，例如 `retina_a4_r1_2`，避免覆盖旧结果。
3. 点击文件夹名称进入。Windows文件资源管理器打开 `D:\PLD\retina_fpga\build\deploy\a4_segmentation_2017_4_r1`。
4. 浏览器点 **Upload**，选择该目录内全部12个文件。每个文件右侧出现蓝色 **Upload** 按钮时，分别点击完成上传。

上传后应有以下文件，文件名保持原样：

```text
a4_segmentation.bit
a4_segmentation.hwh
a4_segmentation_board_test.py
a3_background_board_test.py
a2_gaussian_board_test.py
a1_point_board_test.py
a0_dma_board_test.py
a4_segmentation_check.ipynb
a4_manifest.json
stare_im0001_256.npy
stare_im0001_512.npy
使用说明.txt
```

五个Python文件都有依赖用途，请全部上传。两份眼底输入只有原RGB和FOV，不含血管人工标注。

## 3. 依次运行六个代码框

点击 `a4_segmentation_check.ipynb`。等右上角Python 3内核启动完毕。只选灰色代码框，按 **Shift+Enter**。每框左侧从 `In [*]` 回到 `In [数字]`、无红色报错，并满足下表标志后再选下一框。不要选择Run All，也不要重复运行已经完成的框。

| 代码框 | 完成时应看到 | 接下来 |
|---|---|---|
| 1. 准备函数 | `In [数字]`，没有红色报错；不打印PASS正常 | 运行第2框 |
| 2. 检查文件 | `A4_PRECHECK_PASS` | 运行第3框 |
| 3. 加载 | `A4_LOAD_PASS` | 运行第4框 |
| 4. 首帧验证 | `A4_SMOKE_PASS` | 切到PuTTY按回车，仍有提示符后运行第5框 |
| 5. 完整验证 | 连续出现 `SEGMENTATION_FRAME_PASS`，最终 `A4 SEGMENTATION PASS: 61 complete frames matched` | 等左侧恢复数字后运行第6框 |
| 6. 查看结果并打包 | 四张图及 `A4_RESULTS_READY` | 保存、下载记录 |

第5框会继续验证60帧，与第4框合计61帧、9,895,936个32位输出字；包含256×256和512×512、四种模式、随机/渐变/黑白/条纹/边角/精确阈值/FOV/孤点/断线及真实眼底图。

四幅预览依次为原始绿色通道、亮度增强、**黑白血管候选掩膜**、灰度响应。第三图采用最近邻缩放，保持二值；第四图仍是灰度中间结果。网页预览由已逐字核对的真实DMA返回数组生成。

加载A4后HDMI显示器可能提示无信号，本阶段在网页查看结果。最终同时包含算法与HDMI的B工程另行整合。

若红色报错，或一分钟没有新进展，停在当前框，保留输出并反馈。不要重复运行、释放缓冲、重启这个内核或切换Overlay。软件超时只有在硬件总线访问能返回时才有效。

## 4. 保存并下载两份文件

1. 在Notebook按 **Ctrl+S**。
2. 菜单 **File → Download as → Notebook**，将运行后的 `a4_segmentation_check.ipynb` 下载到Windows电脑。
3. 回到该文件夹的文件列表，勾选新生成的 `a4_results_bundle.zip`，点 **Download**。ZIP包含原JSON、六份实际STARE输出数组和预览图。
4. 两份文件下载完成后反馈“已下载”。项目会独立核验返回数据、记录和发布版本，再记录板测状态。

发布清单中的板测状态保持NOT_RUN，只有真实板卡运行且归档复核完成，才记录算法A板测通过。数值一致性通过不等于医学分割质量达到要求；本次未测最终B工程和FPS。板上日期未校准，原始时间保留。

## 固定算法及诊断规格

输入32位字从低到高为B/G/R/FOV，FOV仅为0或1。GPIO bits[1:0]为模式，bit2选择256（1）或512（0）。模式0返回原输入；模式1输出原G/增强/初始掩膜/响应；模式2输出原G/增强/闭运算掩膜/响应；模式3输出原G/增强/最终掩膜/响应。每个掩膜字节只为0或255。

Gaussian 3×3复制边界、`(sum+8)>>4`；固定LUT；15×15复制边界均值`(sum+112)//225`；响应`clip(4*(background-enhanced),0,255)`；阈值`response>=28`并初始FOV过滤；3×3 CROSS先膨胀再腐蚀，边界外填0；3×3复制边界邻域计数含中心，保留计数≥2的闭运算像素；最终再与FOV相与。阈值和处理顺序沿用已冻结M0选择，不通过看测试图改参数。

PS/DDR/DMA/FIFO/GPIO/100MHz/reset、帧适配器、官方PYNQ驱动沿用已验证A3。阈值、形态学、邻域窗口复用本机未修改的厂商库。本包仅作本地研发数值验证。

## 许可与本地数据

PYNQ官方API/驱动版权和BSD 3-Clause原件保存在项目references中；本包测试包装脚本为项目新增。PS/DMA/GPIO/FIFO/reset及HLS生成物受本机AMD/Xilinx工具/IP条款约束，安装库源码未随包分发。STARE原RGB来源为Clemson STARE im0001，仅作本地研究验证；数据与输入包不公开提交，未假定其公开再分发许可。本包不含人工血管标注。

Filter2D/BoxFilter/morp_opr所用厂商hls_video_imgproc.h注明部分代码源自OpenCV。以下保留其嵌入的版权、条件及免责声明：

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
