# B：冻结算法与官方 HDMI 的同工程整合审查

审查日期：2026-10-12（北京时间）。用户已同意继续。当前 A4 的实体板 61 帧与六份原数组已归档；B 的板测仍未运行。

来源：PYNQ v2.2.1，Commit `3d2641653c6d1a5ea55c4c41e15f9dd9a2e32ab3`。采用已在本机 Vivado 2017.4 原样重建并验证的 Base BD，工作副本 `build/official_v2.2.1`。不可修改该副本或 `references/`。新工程复制 BD 后执行显式功能组删除，保存前后 BD、删除清单与生成脚本。A4 来自 `b3d4ef316db044e027593d4567a94f637fc15545` 的正确 `a4_hls_02` 导出 IP 和原 guard；A4 发布包及原实测记录不变。

保留整个 `video` 层次：双向 VDMA 6.3、HP0 的 142 MHz 内存互连、两套颜色转换与打包、VTC、动态像素时钟、RGB/TMDS、HDMI 输入及其 200 MHz 延迟参考。保留原控制地址、层次名、时钟/复位及视频中断路径。保留原板载四组 GPIO、系统中断控制器和 GP0 八路控制互连。

完整构建 `_04` 暴露三项约束问题，该版本不发布，原日志、时序和 DRC 保留：误留的音频 XDC 引用了已删除端口；原 RX 时钟 8.334 ns 取整导致 MMCM FVCO 599.952 MHz，低于器件下限 600；原 `rgb2dvi_clocks.xdc` 无条件把 PixelClk 作为 SerialClk 的生成源，而官方 Base 的 `kGenerateSerialClk=false` 使用外部动态 MMCM 和 divide-by-5 BUFR，两输入之间没有该逻辑路径。新工作工程删音频约束、保留名义 RX 120 MHz 并将周期精度改为 8.333333 ns、仅在本项目的综合/实现中排除这一个不适用的 RGB 时钟文件。IP 源码及其他 XDC 不变；输出时钟由实际 MMCM/BUFR 自动派生，必须检查 SerialClk/PixelClk 和 FCLK0 的真实源关系及所有路径时序、总线 skew。不能以降级或隐藏警告替代修复。

未修改全部 42 个官方 video BD 对象的功能；41 个标准语义完全一致，另一个是工具生成的控制互连适配器：删除音频这个 AXI4 外设后，全体 GP0 下级外设为 AXI4LITE，工具按原接口参数删冗余 AXI4→AXI4LITE `auto_pc`，寄存器 slice、时钟、复位和 M_AXI 连接仍逐项核验。算法九个原 A4 模块参数完全一致，除实例名称和配置 GPIO 地址；原厂 reset 默认低有效并以实际参数和仿真核验，不再写只读 pin POLARITY。

删除音频、四组 MicroBlaze IOP、两组 Trace、IOP 的 S_AXI_GP0 DDR 互连、Trace 的 HP2 互连、对应接口、引脚约束、EMIO GPIO/IIC 和 GP1。中断 concat 的 Trace/IOP 槽位以原位、原宽度常零替换，其余编号不改。DDR/MIO/以太网/SD/UART 配置不改；PS 参数差异必须限定在已删除外设及 HP2 时钟来源。

算法使用原 AXI DMA 7.1、GPIO 2.0、FIFO 1.1、proc_sys_reset 5.0、guard 和已测 HLS。算法及 HP2 都接 FCLK0/100 MHz，视频 HP0/FCLK1 不变。DMA 控制地址仍为 `0x40400000`；原 Base 开关 GPIO 已占用 `0x41200000`，所以算法配置 GPIO 使用空闲 `0x43C80000`。GP0 的 M03（原音频）和 M06（原 IOP 下级互连）分别供配置 GPIO 和算法 DMA。由标准互连完成 S2MM 32→HP2 64 位适配。

软件复用板上原 PYNQ 3.0.1 的 `Overlay`、`DMA`、`AxiGPIO`、`HDMIWrapper`、`VideoOut`、`AxiVDMA`、`PixelPacker`、`ColorConverter` 与 `_video._display`。使用通用 Overlay，避免原 BaseOverlay 对已删音频/IOP 的依赖。不修改驱动或放宽版本检查：VDMA 6.3、HLS pack/unpack/convert 1.0 正在原驱动 bindto 列表中，frontend 依据原层次及 VTC/动态时钟地址绑定。旧 VTC 6.1 与 C 库寄存器配置仍需真实显示验证，主机分析不能替代板测。

输出固定 1280×720、60 Hz、BGR24；医疗计算全部在已冻结的 PL 算法中。PS 只负责帧分配、官方 DMA 调用、图像排版和提交显示。保留算法整帧 TLAST 与视频逐行 TLAST 的 DDR 分界，不直接接两条 AXIS。每次程序只下载一个配对的 B bit/HWH。

验证顺序：主机元数据/来源/时钟/地址与原官方视频比较，真实生成 reset IP 仿真，完整实现/时序/DRC，再发布 NOT_RUN 套件。实体板按预检查→单次加载→算法短测→HDMI 色序/位置→同工程真实分割显示→性能计时分阶段执行。显示只打印 SUBMITTED；照片及用户观察另行归档。速度分别报告算法 DMA 和包括排版/显示提交的循环，不把显示 60 Hz 当算法 60 FPS。继续采用固定 M0 参数，不从当前 STARE 图调整算法。
