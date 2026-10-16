# 使用现有 Vivado 2017.4 验证 PYNQ-Z2 DMA

2026-10-11：用户同意先用现有 2017.4。板上 PYNQ 3.0.1 和官方 Base 保留；不需要重新写 SD 卡，也不需要安装 Linux。首版 A0 板级尝试导致系统无响应，已撤回；断电后串口恢复。复位缺陷已通过厂商 IP 仿真确认，修正版主机验证见 [r2 报告](../results/a0_dma_2017_4_r2/build_report.md)。具体停滞指令仍未知，板级结果必须由下述真实运行取得。

## 1. 先结束已有测试

1. 板卡保持供电，网线保持连接。
2. 浏览器打开 `http://192.168.2.99:9090/tree`。
3. 如果 HDMI 测试还在运行，回到 `hdmi_output_check`，执行 `hdmi_out.close()` 的单元，保存，再点 **File → Close and Halt**。如果已经成功关闭，不必重复运行。
4. GPIO 演示若还在等待按钮，按板上 **BTN3** 结束。保存后点 **File → Close and Halt**。
5. 在主页的 **Running** 页检查这些测试的 Notebook 内核已结束。A0 运行时不要让其他 Notebook 加载 FPGA。

## 2. 上传四个文件

电脑文件夹：`D:\PLD\retina_fpga\build\deploy\a0_dma_2017_4_r2`。

|文件|用途|
|---|---|
|`a0_dma.bit`|本次 FPGA 配置|
|`a0_dma.hwh`|同一次构建的硬件描述，供 PYNQ 读取|
|`a0_manifest.json`|文件哈希、工具和源码记录|
|`a0_dma_loopback.ipynb`|中文测试 Notebook，未预填运行结果|

1. 回到 Jupyter **Files** 页，点 **New → Folder**。
2. 勾选新出现的 `Untitled Folder`，点 **Rename**，改为 `retina_a0_r2`，再点文件夹名称进入。
3. 点右上角 **Upload**，在电脑上选择上面的四个文件；可以按住 Ctrl 多选。
4. 页面列出待上传文件后，逐个点文件旁的蓝色 **Upload** 按钮。
5. 确认四个文件都在同一个文件夹内，没有变成带 `(1)` 的文件名。

## 3. 分步运行，禁止 Run All

1. 打开新文件夹内的 `a0_dma_loopback.ipynb`，等待内核就绪。
2. 运行“1. 准备函数”代码单元，仅定义函数。
3. 运行“2. 检查文件与环境”代码单元。应出现 `PRECHECK_PASS`；此时 FPGA 尚未改变。先反馈该结果。
4. 确认检查通过后，单独运行“3. 只加载 FPGA”。应出现 `LOAD_PASS`。确认串口和网页仍正常，再反馈加载结果。
5. 确认加载后，运行“4. 一次短包收发”。应出现 `SMOKE_PASS`，说明一次 17 字收发与字节数比较成功。反馈此结果后再继续完整验证。
6. 运行“5. 完整收发验证”。仅真实完成 70 次并出现 `A0 DMA PASS` 才算完整板测通过。

每个硬件阶段之前保存 JSON 状态；失败记录保留最后完成阶段。若浏览器再次断连，只截图最后显示的文字并停止，不重试旧版或重新写卡。

A0 不包含 HDMI，加载它后显示器可能黑屏或无信号，这是预期现象；通过网页查看结果。不要在 A0 测试中打开官方 GPIO/HDMI 示例，否则会替换当前 FPGA 配置。

测试检查短包、256×256 和 512×512 数据包，递增及随机图案，共 70 次收发。每个返回字和收发字节数都比较。测试的是标准 DMA/FIFO/DDR 和当前 Python 驱动，尚无医学算法。

## 4. 保存结果

1. Notebook 内按 **Ctrl+S**。
2. **File → Download as → Notebook (.ipynb)** 下载执行记录。
3. 回到 `retina_a0_r2` 文件列表，勾选 `a0_dma_result.json`，点 **Download**。
4. 把最终输出截图或报错截图提供给项目审查，原始 JSON 和执行 Notebook 一同归档。

出现红色报错、或超过一分钟无进展时暂停，不要连续重试、释放缓冲或关闭该测试内核。脚本故意保留失败时的缓冲，以免硬件访问已经释放的内存；软件轮询的超时不能保证卡住的 AXI MMIO 返回；先保留报错和 JSON，再按诊断决定复位或重新加载。没有真实输出就不能记录板级 PASS。

## 构建及复用说明

脚本入口 `vivado/scripts/build_minimal_dma.tcl`，只接受 2017.4 和新的输出目录。Windows 示例：

```powershell
& 'E:\vivado\Vivado\2017.4\bin\vivado.bat' -mode batch -nojournal -log build/a0_new.log -source vivado/scripts/build_minimal_dma.tcl -tclargs build/a0_new full
```

板级来源为固定 TUL PYNQ-Z2 board/preset；PS 硬 DDR 和 MIO 原配置复用，仅按 A0 需要启用 GP0、HP0 和 100MHz FCLK0。DMA、AXI 互连、AXIS FIFO、同步复位全部是本机厂商 IP。PYNQ 运行时使用板上 3.0.1 官方 `Overlay`、`allocate`、`DMA`；不拷贝旧版 Xlnk/底层驱动。

DMA Simple、双向、长度23位、流32位。2017.4 自动将 S2MM 内存口推导为32位，通过标准互连转换至64位 HP0；MM2S 内存口64位。两种缓冲都按8字节对齐验证。DMA控制地址 `0x40400000/64KiB`，HP0地址窗口 `0x00000000–0x1FFFFFFF`，均由本次 BD/HWH 检查。两个旧 preset 的 AXI 频率字段解除 USER 锁定，让工具自动推导为100MHz；未修改原厂文件。

A0 是独立调试工程；之后再从匹配 2017.4 的官方 v2.2.1 Base 工作副本验证 HDMI 与 PYNQ 3.0.1 的适配。最终 B 必须包含算法和 HDMI，不能用两个 bitstream 来回切换代替整合。

辅助复位修正：`C_AUX_RESET_HIGH=0` 时 `aux_reset_in` 接常数1；保留PS `FCLK_RESET0_N`、厂商同步复位及100MHz时钟结构。仿真复现旧接线持续复位并验证修正与PS复位释放；仿真通过不等于板级DMA通过。
