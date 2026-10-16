# 重启后重新运行展示（2026-10-16）

用户已确认重启并授权新会话。旧故障证据保留，原因未定，不称已修复。上传包为原发布逐字节副本，C7及硬件不变；本轮BOARD_NOT_RUN。无需录像。

1. 打开 http://192.168.2.99:9090/tree，新建 `retina_c7_showcase_restart_r2`。上传 `build/deploy/c7_showcase_restart_r2/upload/` 中 `c7_showcase.ipynb`、`c7_showcase_r1.zip`；不要手动解压或使用旧目录。
2. 打开新Notebook，运行第1框，确认SHOWCASE_PACKAGE_PASS；运行第2框，确认SHOWCASE_PRECHECK_PASS（至少1GiB空闲）。每框成功后不重复执行。
3. 运行第3框至BROWSER_SERVICE_READY，再运行第4框。打开 http://192.168.2.99:8090/，此时Ctrl+F5更新网页，之后运行期间保持前台，不刷新。
4. 全部20张、512、C7最终T112：逐张运行到20/20；上一张、下一张各一次；256运行一张后恢复512；讲解样例运行8/8。功能演示中分别运行im0324_nogt/C7最终112、im0324/C7旁路112、im0001/C2模式1/28、im0001/C2模式2/28。约35次，允许额外操作，不要求固定次数，最多100次。每张实际提交PL。
5. 所有任务结束后回Notebook运行第5框，确认SHOWCASE_CLOSED_IDLE。
6. 运行第6框，确认SHOWCASE_RESULTS_READY，导出本轮ZIP。
7. 运行第7框，确认CLOSED/IDLE、pending=0、error=None；Ctrl+S，下载本轮执行后的Notebook及c7_showcase_results.zip到电脑Downloads。保留同名下载的自动编号，勿覆盖旧证据。

若再次错误或超时，停止后续操作，保留截图和原目录，不重复启动或重载FPGA。旧轮未通过结论不因新轮重启而改变。回收仍使用scripts/verify_c7_showcase.py及原发布配对文件，另建结果目录。
