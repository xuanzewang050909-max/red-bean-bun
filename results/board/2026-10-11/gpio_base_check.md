# 官方 Base Overlay / GPIO 验证

日期：2026-10-11，Asia/Shanghai。

用户打开板端官方 `base/board/board_btns_leds.ipynb` 并创建 `board_btns_leds-Copy1.ipynb`。创建副本截图保留为 gpio_notebook_copy_user_photo.png，截图时显示内核正在启动；其中已有的 In [1] 不能单独证明本次执行。

随后指导用户执行官方代码并依次测试：加载 BaseOverlay("base.bit")，LD0-3 亮起，BTN0 改变彩色 LED，BTN1/BTN2 使四灯向相反方向变化，BTN3 结束并关灯。用户明确反馈：**“确实按上述方式变化”**。

据现场操作反馈，官方 BaseOverlay 加载及 GPIO LED/按钮控制记为 PASS_USER_REPORTED。没有远程执行代码；未取得程序结束输出的截图、精确执行时间、板端日志文件或性能数据。不能把副本截图中的历史执行计数作为通过依据。

Jupyter 登录另有首页截图证据。HDMI、视频帧缓冲和独立 DMA 尚未验证。用户随后确认显示器或电视、HDMI 线都有，准备继续输出测试；没有声称 HDMI 已接线或已显示。

来源：固定 v3.0.1 参考中的 Pynq-Z2/base/notebooks/board/board_btns_leds.ipynb 官方相对链接及其共用目标。使用板端 Z2 Base，不采用其他板卡的硬件配置。
