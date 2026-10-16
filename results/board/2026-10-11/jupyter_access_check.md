# Jupyter 网络访问验证

日期：2026-10-11，Asia/Shanghai。证据由用户浏览器截图提供，没有远程执行 Notebook。

截图显示浏览器访问 `http://192.168.2.99:9090/tree?`，Jupyter 已登录的 Files 首页列出 base、common、getting_started、logictools、pynq_peripherals 目录和 Welcome to Pynq.ipynb。

结论：板端 Jupyter 网页访问及登录 PASS（用户截图）。使用现场已成功的 9090 端口；此前依据官方文档建议不带端口的地址，不能替代实际观察。未记录是否发生端口跳转，也不据此推断服务代理结构。

Linux 启动和运行 PYNQ 3.0.1 已有串口证据；本次进一步确认网络可达和网页登录。目录 base 的存在不证明 BaseOverlay 成功加载，组合测试 jupyter_base_overlay 只完成网页部分。GPIO、HDMI、帧缓冲与独立 DMA 仍未实测。

下一步：打开板端 `base/board/board_btns_leds.ipynb`，用 File > Make a Copy 创建运行副本，保留官方原 Notebook。官方 v3.0.1 Pynq-Z2 目录中的该文件通过相对链接复用 Pynq-Z1 的共用示例；只复用官方指定的 Notebook，不采用其他板卡的 bitstream、XDC 或板级配置。该代码加载板端 `pynq.overlays.base.BaseOverlay("base.bit")`，实际执行与 LED/按钮响应需要继续采集证据。代码中的按钮循环需 BTN3 结束，不应把执行中的 `In [*]` 单独判为错误。

证据：[Jupyter 首页](jupyter_home_user_photo.png)。
