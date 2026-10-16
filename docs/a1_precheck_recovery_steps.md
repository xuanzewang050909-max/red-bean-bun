# A1 文件检查报错修复：保留原 Notebook，更新两个文件

截图报错为 `ValueError: Package mismatch: a1_point_check.ipynb`，发生在“检查文件”，尚未加载 FPGA、启动 DMA。这是 r1 测试包的校验缺陷：Jupyter 保存执行次数、输出与元数据后，Notebook 的完整文件哈希就会改变。

r2 对 Notebook 的有序代码单元进行规范化哈希校验，允许正常保存输出和元数据；测试代码发生改变仍报错。bit/HWH、测试脚本、复用辅助脚本和原使用说明继续逐字节 SHA256 校验。电脑上 25 项回归测试通过，也在实际 r2 包上模拟保存并通过检查。**这些是主机验证，A1 真机测试仍待完成。**

## 按顺序执行

1. 在 Windows 文件资源管理器地址栏粘贴 `D:\PLD\retina_fpga\build\deploy\a1_point_precheck_fix_r2`，按回车。里面只有 `a1_point_board_test.py` 和 `a1_manifest.json` 两个文件。
2. 在 Jupyter 网页切换到 `retina_a1_r1` 的文件列表。若当前在 Notebook，可点左上角 Jupyter 标志回列表，再进入这个文件夹。
3. 点右上角 Upload，选择上述两个文件。文件列表出现待上传条目后，再点各条目的 Upload；询问是否替换同名文件时，确认替换。两个文件都要传完。
4. 回到 `a1_point_check.ipynb`。点菜单 Kernel → Restart，确认重启，等待右上角内核状态恢复空心圆。此步让 Python 重新读取修正脚本；仅刷新网页不足以重新导入脚本。此处重启适用于截图的文件检查失败、尚未加载 FPGA 的状态。
5. 点“1. 准备函数”下面的代码框，按 Shift+Enter。左侧变成 `In [数字]` 且没有红色报错，就是完成。
6. 点“2. 检查文件”的代码框，按 Shift+Enter。应出现 `A1_PRECHECK_PASS`。若出现红色报错，停在此处，保留截图；不要运行加载框。
7. 检查通过后，运行“3. 加载”的代码框，应出现 `A1_LOAD_PASS`。
8. 运行首帧验证框，应出现 `A1_SMOKE_PASS`。确认网页正常，PuTTY 按回车仍有提示符。
9. 运行连续验证框。最终应出现 `A1 POINT PASS: 17 complete frames matched; no segmentation/HDMI PASS`。仅此时可提交 A1 板级通过证据。
10. Ctrl+S 保存。File → Download as → Notebook 下载运行后的 Notebook；回到同目录文件列表，下载 `a1_point_result.json`，保留完成截图。

加载 A1 后，显示器可能无信号，因为 A1 只做点运算与 DMA 验证。红色报错或一分钟无进展时，保留最后输出、暂停操作，不反复运行、不释放在途缓冲、不切换 Overlay，反馈网页及串口是否仍有响应。

如果出现 `Use a new folder; preserve earlier board result`，保留已有结果并反馈；不要删除结果后重复测试。

## 交付和复现记录

- 两文件修正包：`build/deploy/a1_point_precheck_fix_r2`，用于已经上传 r1 的板端文件夹。
- 完整七文件 r2 包：`build/deploy/a1_point_2017_4_r2`，用于首次上传到全新文件夹。
- 原 r1 文件、清单和 Git 构建记录完整保留；bitstream、HWH、Notebook 原件及旧使用说明未改动。完整 r2 包沿用旧使用说明，上传前以本文的修复步骤与 r2 路径为准。
- 新记录：`results/a1_point_2017_4_r2/release_manifest.json`、`package_validation.json` 和 `host_regression_tests.log`。
- 修正包复现：项目 Python 运行 `scripts/package_a1_precheck_fix.py`，依次传入原 r1 包、尚不存在的完整包目录、尚不存在的两文件包目录及含通过日志的结果目录。脚本验证历史清单、原硬件文件和构建源码，拒绝覆盖已有发布记录。

本次仅修正测试软件；原 Vivado2017.4 A1 硬件与复位/时序证据逐字节复用。不是新一轮 FPGA 构建或板级 PASS，也不代表完整血管分割或 HDMI 整合通过。
