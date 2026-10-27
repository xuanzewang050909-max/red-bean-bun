# 人工首帧板测说明（本轮仅准备，未执行）

当前状态：READY_FOR_BOARD_AUTHORIZATION / BOARD_NOT_RUN。下面是下一次获得板测授权后使用的步骤；本轮没有连接板卡、读取寄存器、加载位流或改变旧内核/缓冲。

1. **先确认旧现场已经封存且板卡允许安全切换。** 不在有未知事务的旧内核上运行，不把关闭网页当作停机。本包不负责清场，不复位、不释放旧缓冲；旧现场未确认安全时不要执行第3步。
2. 在 Jupyter 新建目录 `single_image_repair_r1`，上传并解压本次 `C7_SingleImage_Repair_Board_r1.zip`。目录中应直接看到 `Single_Image_Repair_Operator.ipynb`、`payload/` 和本说明。用新的 Python 3 Notebook 内核打开该文件，不选择 Run All。
3. 先只运行第一格：应显示 `OFFLINE_PACKAGE_VERIFIED`、`single-image-vessel-valley-v1`、`[512,512]`。这一格只检查文件，不访问硬件。任何SHA或文件错误都停止，不改清单。
4. 在取得本次板测授权、旧现场已安全保留后，才将第二格的 `AUTHORIZED=False` 手动改为 `True` 并执行一次。这会加载本包50MHz独立overlay，先运行32×32空输入，再运行唯一的im0324/512原输入。PL完成平滑、线响应、筛选、传播和合并；PS不生成新增mask。可信C7旧位流不被改写，也不重跑C7。
5. 不要重复点击第二格。原生帧RTL仿真约25.79秒；这是仿真而非整机保证，实际还包括加载、内存、轮询和保存。每阶段软件轮询上限120秒；Python无法中断已阻塞的底层MMIO。无响应/断连/异常时停止追加操作，保留内核和缓冲，不自动重试、重载或断电。
6. 只有第二格返回 `BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW`，才运行第三格显示对比：原图、旧绿色标注、真实PL结果（绿色旧、青色新增）。它会核验保存文件后绘制，**不显示软件预期图冒充板端输出**。该格只执行一次，避免覆盖图片。
7. 运行最后一格导出 `single_image_board_results_r1.zip` 并下载。第二格若抛错但内核仍响应，也只运行导出格保存现场。不要启动第二次测试。
8. 下载后在开发电脑上运行包内 `verify_download.py`，指定下载ZIP与本包的 `payload` 目录；该程序检查全部工作区字、输入身份、时钟、来源和SHA，生成独立主机回执。未完成此核验前，不报告板测通过。

示例（开发电脑，不是板端命令；替换下载文件路径）：

```powershell
& D:/PLD/retina_c7_structured_refine/.venv/Scripts/python.exe -X utf8 -B D:/PLD/review_packages/C7_SingleImage_Repair_Board_r1/verify_download.py C:/Users/Gabriel/Downloads/single_image_board_results_r1.zip --payload D:/PLD/review_packages/C7_SingleImage_Repair_Board_r1/payload --output D:/PLD/single_image_board_verification_r1.json
```

结果文件包括会话、运行库与启动身份、50MHz寄存器推导读数、逐次控制访问记录、小工作区和原生帧的全部6平面及保护字。所有输出须与匹配的整数参考一致。预期数组只用于主机比对，绝不传入PL作为新增mask。此包不连接历史4帧流程，不打开任何锁定图。

限制：单图目视修补，无独立GT准确率结论；淡末梢/交汇区域仍可能遗漏；DDR BRESP没有独立软件错误状态，完整数值与保护字核验不可省略。LATENCY_TARGET_UNSET。
