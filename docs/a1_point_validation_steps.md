# PYNQ-Z2 A1 r1 验证：一步一步操作

本版是绿色通道与 LUT 单级验证，不是完整血管分割。电脑继续使用 Windows，无需装 Linux 或新 Vivado。A0 r2 的已通过文件保留，A1 放到新目录。

## 1. 准备

保持板卡供电、MicroUSB 和网线连接。PuTTY 使用 COM9、115200；板端网页为 `http://192.168.2.99:9090/tree`。先确认串口按回车有提示符、网页能打开。不要继续运行旧 A0 或 HDMI Notebook。

电脑交付文件夹：`D:\PLD\retina_fpga\build\deploy\a1_point_2017_4_r1`。

## 2. 上传七个文件

网页回文件列表，右上角 New → Folder，勾选新文件夹，用 Rename 改名为 `retina_a1_r1`，进入此文件夹。点 Upload，在电脑交付目录中选择全部七个文件；文件列表出现待上传条目后，再逐条点 Upload 完成：

- `a1_point.bit`
- `a1_point.hwh`
- `a1_manifest.json`
- `a1_point_check.ipynb`
- `a1_point_board_test.py`
- `a0_dma_board_test.py`（复用已验证的等待与错误处理函数，不加载 A0）
- `使用说明.txt`

不要只传 Notebook；bit/HWH/manifest 必须成对。

## 3. 运行准备函数与文件检查

打开 `a1_point_check.ipynb`。一次只运行一个代码框：点代码框，按 Shift+Enter。

第一框是准备函数：左侧从 `In [ ]`/`In [*]` 变成 `In [数字]`，且没有红色报错，表示完成。它没有打印 PASS 是正常的。再运行“检查文件”框，应出现 `A1_PRECHECK_PASS`；此时 FPGA 尚未改变。

## 4. 加载与首帧

运行“加载”框，应出现 `A1_LOAD_PASS`。A1 没有 HDMI，显示器变黑或无信号是预期现象。

运行“首帧验证”框，应出现 `A1_SMOKE_PASS`。本版有完整帧长度检查，首帧为 256×256，共65536字；不使用17字短包。确认 PuTTY 和网页仍响应。

## 5. 完整验证

运行“连续验证”框，另有16帧，涵盖256/512、旁路/绿色/LUT、随机/递增/全黑/全白。每帧逐字比较收回数据，并检查收发字节数、RTL帧计数与错误标志。

最终预期：`A1 POINT PASS: 17 complete frames matched; no segmentation/HDMI PASS`。只有真实运行完成后，才能登记 A1 板级通过。

## 6. 保存

Ctrl+S 保存。菜单 File → Download as → Notebook 下载执行后的 Notebook。回到文件列表，下载 `a1_point_result.json`。保留完成输出截图并反馈给项目，便于核验实际文件配对、逐帧输出哈希和状态。

如果出现红色报错或一分钟无进展，保留最后输出，暂停操作；不要反复点运行，不释放在途缓冲，不切换Overlay。先在PuTTY按回车检查响应并反馈。软件超时不能解除已经阻塞的硬件总线访问。

## 检验范围

模式0为32位原样旁路；模式1输出低字节G、次字节G；模式2输出低字节G、次字节LUT(G)。后两种高16位全0，未产生血管掩膜或响应。

AXI GPIO 地址0x41200000：offset0为配置；offset8为状态。配置bits[1:0]模式，bit2选择256（1）/512（0），首个被接受的像素锁存帧配置。状态bits[13:0]输入帧计数、[27:14]输出帧计数（均模16384），[30:28]错误标志。AXI DMA仍为0x40400000，100MHz共同时钟，标准FIFO及A0 r2复位连接保留。

真实 STARE 分割仍在CPU固定点模型中完成。A1通过后才接入Gaussian等空间滤波；最终算法和HDMI会放进同一个B Overlay。本测试不统计最终系统FPS。
