# W4a 无损 PNG 对照：主机交付验证

状态：**HOST_RELEASE_VERIFIED_BOARD_NOT_RUN**。已具备下一轮真实板测条件；没有新板测 FPS 或提速结论。

## 增量范围与依据

W3 真板 31 任务/7,340,032 字通过，20 帧前台 0.193518 FPS；每帧 PS 图像窗口约 4.42 s，占工作者约 89.4%。因此本轮拆分 PS 数组解包/叠加、PIL 转换、PNG 编码及写入、PNG 哈希与文件清单哈希，保留旧窗口和原始单调纳秒边界。

默认组保持原 `Image.save(format="PNG")` 调用选项；候选只增加 `compress_level=1`。两组均为原尺寸 8 位 L/RGB 无损 PNG，不量化、不改变掩膜、不改变医学计算。依据 [Pillow PNG 文档](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#png) 与板端版本对应的 [Pillow 9.0.1 PNG 插件源码](https://raw.githubusercontent.com/python-pillow/Pillow/9.0.1/src/PIL/PngImagePlugin.py)。PNG 编码段包含滤波、编码和文件写入，不能称纯压缩时间；更快编码可能增加网络字节，须在同一板端/浏览器共同测量。

独立 `pynq_w4a/`、`ui_w4a/` 派生 W3；`hardware.py`、`quality_observer.py`、`evaluation.py`、`__init__.py` 与已板测 W3 原字节一致。W2 bit/HWH/manifest、原 DMA 测试辅助和 W1 输入/评价数据原字节复用，无新综合、无 HDMI、无生产 CPU 参考或预计算输出。原 W1/W2/W3 发布未改。[派生身份](derivation.json)、[受控差异](w3_to_w4a.diff)。

请求增加必需 `png_profile=baseline|fast`，归入配置 ID 以防混组，但不改变 PL 控制字段。每次仍是真实新 DMA/PL 任务；一次加载、单工作者、有界队列、故障引用保留逻辑继续复用。

## 实际主机检查

- 32 项不同 Python 检查，无跳过。原 26 项接口/驱动/错误/导出/计时检查，加 6 项 PNG 与来源检查；原 26 项单独执行和扩展后的 32 项日志分别保留，不能相加称 58 项。
- 下载 W3 的全部 147 PNG 在两个方案重新编码，解码像素逐值一致，原数组未改。baseline 选项与原调用一致，fast 仅增加压缩等级。
- Python 3.10 语法、源文件/包/manifest、26 文件 + manifest 共 27 ZIP 成员、启动 Notebook 固定 SHA 均通过。
- 真实浏览器操作主机替身服务：4 手动组合 + 两组各 3 预热/20 计时 =50 任务。两组均前台、预热不计 FPS；切换配置会清除旧指标和禁止旧任务导出；无前端 error/warn。
- 从浏览器实际下载 HOST_TEST ZIP，再独立检查 13,107,200 输出字、250 PNG/117,964,800 通道值、两组相同医学输出、原始编码分段/字节/序列和预热/连续计时。所有内容始终标注 HOST_TEST_DOUBLE_NOT_BOARD，没有改成板证。主机 FPS 不填进板测字段。

见 [测试原日志](w4a_host_tests_02.log)、[UI 核查](ui_verification.json)、[发布核验](release_validation.json)。完整主机 ZIP 和两张截图仅在 `build/browser_w4a_ui_qa/`，其哈希已记录；页面有醒目主机替身标记。

## 交付与下一实验

只上传 `build/deploy/browser_w4a_upload_r1/` 的两个文件：`browser_w4a_png_r1.zip`、`browser_w4a_start.ipynb`。新目录 `retina_browser_w4a_r1`，六框完整步骤见 [板测说明](../../docs/browser_w4a_board_steps.md)。

4 组合门禁（A/default、A/fast、C2/default、C2/fast），再固定 im0001/512/C2/T28/final，先默认后快速，各 3 预热 +20 计时。50 个新帧一次加载，全部原始数组/PNG/记录保留，客户端下载后独立复核像素等价与分段。真实时间、文件大小与展示 FPS 均待实测，保留无收益结果。

本阶段是正式 W4+Q3 之前的 W4a 小范围定位实验；原全数据质量、三配置/100帧/三复测/同 PS CPU、纯 DMA、资源/功耗以及稳定性要求不减。亮区 C2 在 W3 已真实生效，本轮不重新选参或扩大单图收益结论。
