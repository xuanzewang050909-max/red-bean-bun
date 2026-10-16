# HDMI 首次显示观察

日期：2026-10-11，Asia/Shanghai。

用户按输出验证流程后提供显示器照片，并反馈“没有报错”。照片可见从左到右为绿、红、蓝、绿四段，左右绿色段较窄。当前测试本预期为蓝、绿、红三个连续区域，因此只确认已有可见彩色画面，不能把完整 HDMI 输出正确性记为 PASS。

未取得本轮 Notebook 实际代码和运行输出截图，不能确认是否有额外修改、实际分辨率、帧步长、显示器缩放或其他 Kernel 修改了 PL。照片不足以确定通道顺序、水平循环偏移或根因；不把推测记录为故障结论。也未取得稳定 30 秒的明确反馈。

下一步在同一输出 Notebook 和 Kernel 中追加纯红帧诊断，打印 mode、shape、dtype、strides，调用原有 hdmi_out.newframe/writeframe。暂不更换 bitstream、不改 XDC、不重写驱动，不重新运行 BaseOverlay 加载。取得网页输出和显示器照片后比较软件提交与实际显示。

证据：[首轮显示照片](hdmi_initial_color_bars_user_photo.jpg)。

## 纯红帧后续观察

用户随后提供显示器照片：可见显示区域为红色，未见前次的其他色条。纯红帧可见颜色符合提交的 BGR [0, 0, 255]，该子项记为 PASS_USER_PHOTO。照片的摩尔纹、反光及亮度变化不能直接当作输出伪影。

纯色填充在空间偏移下仍可能保持纯色，因此不能用此结果判定色条错位已消失，或把完整 HDMI/帧缓冲测试改为 PASS。显示器完整范围、持续稳定时间和网页中 Mode/Shape/Type/Strides 输出尚未取得。下一步先取得诊断代码的网页输出；保持同一 Kernel、同一官方 Base 数据通路。

证据：[纯红画面](hdmi_red_frame_user_photo.jpg)。

## 帧格式输出确认

用户提供同一输出 Notebook 的运行截图，地址为 `http://192.168.2.99:9090/notebooks/base/board/hdmi_output_check.ipynb`。输出为：

- Mode: VideoMode: width=1280 height=720 bpp=24 fps=60
- Shape: (720, 1280, 3)
- Type: uint8 Strides: (3840, 3, 1)
- Red frame submitted; check the display.

上述模式、数组尺寸、类型和内存行步长符合 BGR24 720p60 的软件配置；这不是对显示器实际输入时序或 DMA 寄存器的测量。截图中的色条代码与提供的测试逻辑一致（蓝/绿/红三段），没有发现该代码的颜色或切片改写。色条单元执行计数为 6，纯红诊断为 2，表明部分单元曾按不同于页面顺序的顺序执行；不据此猜测根因或当下屏幕状态。

下一步提交带白色外框和中心十字的三色帧，在同一 Kernel 中仅更新帧，不重新配置 HDMI 或重新加载 Base。此空间标记可以观察纯色帧无法揭示的位置问题。预期左蓝、中绿、右红，外框完整、十字居中；待用户照片确认。

证据：[网页中的实际代码及模式输出](hdmi_mode_strides_user_screenshot.png)。

## 空间标记图后续结果

用户提供显示器照片，可见从左到右为蓝、绿、红，白色外框及中心十字的可见位置符合本次测试图。照片有透视和部分画面边缘出框，不能用它进行逐像素或精确几何测量；足以记录本次静态图颜色及位置观察通过（PASS_USER_PHOTO）。

首轮绿/红/蓝/绿异常在本次图中未复现，未采取时钟、寄存器或 bitstream 修改；根因尚未确认，保留首轮记录。不能宣称通过软件修复了某个硬件错误。

静态显示已取得正确图样证据，持续稳定 30 秒仍需用户确认。下一项是同一 Kernel 内通过官方 newframe/writeframe 连续提交 100 帧，观察白条从左向右移动，保留完成输出。该测试验证输出帧提交和肉眼运动观察，不等同于每帧数据完整性回读、医学算法 FPS、独立 AXI DMA 或 HDMI 输入测试。

证据：[带边框与十字的正确静态图](hdmi_position_pattern_user_photo.jpg)。

## 持续稳定和连续帧提交通过

用户在收到“静态图保持 30 秒、再运行 100 帧白条移动”步骤后反馈“都很正常”，并提供同一 Notebook 的代码与完成输出截图。截图显示本轮单元 In [4] 已完成，输出 `Submitted 100 frames.`，代码通过官方 hdmi_out.newframe/writeframe 提交 100 帧并生成板端 JSON 记录。

因此，720p60/BGR24 配置下的静态 HDMI 输出及持续稳定观察记为 PASS（照片与用户反馈）；官方 VDMA 输出通路的连续 100 帧提交和肉眼白条运动观察记为 PASS（完成输出截图与用户反馈）。这不证明 100 帧逐帧无丢失、DMA 内存回读完整性、HDMI 输入通路或医学处理性能，也不是独立 AXI DMA 双向 loopback。

首轮色条异常保留为历史观察，后续图样和运动测试均通过，根因没有确定。不把它表述为已定位并修复的硬件错误。

截图仍显示 Notebook 更改未保存，最后的 hdmi_out.close() 单元尚未执行。板端生成的 hdmi_framebuffer_100_frames.json 未下载；当前本地保存的是截图和指导代码，没有伪造板端原始日志。下一步由用户运行 close 单元、保存并导出实际执行 Notebook，完成归档。

证据：[100 帧完成输出](hdmi_100_frames_completed_user_screenshot.png)。

## 执行 Notebook 已归档

用户从默认下载目录提供的 hdmi_output_check.ipynb 已逐字节归档为 [实际执行 Notebook](hdmi_output_check_executed.ipynb)。已取得 `HDMI output closed.` 和 `Submitted 100 frames.` 保存输出，没有保存的 error 输出；详情及 SHA256 见 [归档清单](hdmi_notebook_archive_manifest.json)。此前“停止和导出待完成”属于当时状态，板端 JSON 与环境采集仍待导出。
