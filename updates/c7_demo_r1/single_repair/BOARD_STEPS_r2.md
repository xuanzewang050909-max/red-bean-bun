# 单图补标 r2：复位连接修正版人工板测

这是新的复位连接修正版，算法与补标结果不变。旧 r1 的第一次控制访问没有完成记录，旧文件及 `ATTEMPT_STARTED.json` 必须保留。不要删除标记、改旧目录名称后重跑旧包。用户已确认旧尝试后重启/断电，旧物理地址和内存状态不可恢复，本包不会读取它们。

本包准备完成不代表板测通过。开发电脑没有连接或操作板卡。以下硬件步骤由用户手动进行一次。

1. 确认现在板卡空闲，没有其他运行中的 Notebook 或未知硬件事务。保留原 `single_image_repair_r1` 目录。若无法确认空闲，停在离线检查，不强制中断或重载。
2. 在 Jupyter 新建 **`single_image_repair_r2`**。上传并解压 **`C7_SingleImage_Repair_Board_r2.zip`**。该目录中应直接出现 `Single_Image_Repair_Operator_r2.ipynb`、`payload/`、本说明。不要把新文件混进 r1 的 payload。
3. 用新的 Python 3 内核打开 `Single_Image_Repair_Operator_r2.ipynb`，不要选择 Run All。运行第一格，必须显示 **`OFFLINE_PACKAGE_VERIFIED`** 和 **`RESET_FIXED_R2`**。它只读文件和检查 SHA，不操作硬件。任何校验错误都停止，不改清单。
4. 人工确认本次新测试后，把第二格的 `AUTHORIZED=False` 改成 `True`，按一次 Shift+Enter。它加载新 50MHz overlay，先做 32×32 空输入及控制/DDR核对，再执行唯一的 512×512 原图。无需先运行任何 PuTTY 命令。PS只传输输入和核验结果，新增识别、筛选和合并均由PL执行。
5. 等第二格结束，通常需要几十秒到数分钟。不要重复点击或另开内核执行。只有返回 **`BOARD_NUMERIC_MATCH_PENDING_HOST_REVIEW`**，才运行第三格；第三格显示本次真实PL输出的原图/旧标注/新结果对比，绿=旧、青=新增。
6. 运行最后一格一次，点击下载 **`single_image_board_results_r2.zip`**，把这个ZIP发回做独立主机核验。

如果出现报错、断连或长时间没有结束：停止追加操作，不重跑第二格、不删除标记、不重启/断电。若已明确抛错且内核仍可用，只运行最后的导出格；若仍是 `In [*]` 或无法连接，不排队运行任何代码，保留最后画面与文件并反馈。轮询的120秒超时无法中断底层阻塞MMIO，不能把没有抛错解释为仍然正常。

主机核验命令（开发电脑，板端不运行）：

```powershell
& D:/PLD/retina_c7_structured_refine/.venv/Scripts/python.exe -X utf8 -B D:/PLD/review_packages/C7_SingleImage_Repair_Board_r2/verify_download.py C:/Users/Gabriel/Downloads/single_image_board_results_r2.zip --payload D:/PLD/review_packages/C7_SingleImage_Repair_Board_r2/payload --output D:/PLD/single_image_board_verification_r2.json
```

核验全部工作区整数、输入和会话身份、保护字、时钟和SHA。参考数组只用于比对，不传入PL。单图效果仍有不确定的细末梢与交汇区域；没有独立GT准确率结论。`LATENCY_TARGET_UNSET`，新修正版 `BOARD_NOT_RUN`，旧失败不改写为成功。
