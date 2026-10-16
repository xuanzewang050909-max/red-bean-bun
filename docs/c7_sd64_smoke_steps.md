# 64GB新卡短轮验证

新卡整盘写入并读回SHA256匹配，已启动并扩容。截图显示根文件系统58G、空闲44G、使用率21%。这是迁移与文件系统证据；新卡PL验证仍BOARD_NOT_RUN。旧卡和整盘镜像保留。

使用原始发布build/deploy/c7_showcase_r1/upload中的c7_showcase.ipynb、c7_showcase_r1.zip（哈希已复核），不使用下载的已执行Notebook。板端新建retina_c7_sd64_check_r1并上传，不手动解压。Notebook第1～4框依次运行，打开8090页面并在提交任务前Ctrl+F5。

本轮仅6次，每次等显示完成：
1. 全部20张，im0001，512，C7最终T112，运行。
2. 下一张并运行，确认im0002和新任务号。
3. 上一张并运行，确认im0001和新任务号。
4. im0001切256，C7最终T112，运行。
5. 功能演示，im0324，512，C7旁路T112，运行（只有原图，其他栏旁路无输出）。
6. 同图恢复C7最终T112，运行（分割输出恢复）。

保持前台，不启动逐张列表，不录像。结束后Notebook第5框安全关闭SHOWCASE_CLOSED_IDLE，第6框导出SHOWCASE_RESULTS_READY，第7框确认CLOSED/IDLE、pending=0、error=None。Ctrl+S下载执行Notebook和c7_showcase_results.zip；同名自动编号保留。次数可多于6但均需核验，不限制固定次数。

错误或超时停止保留现场、不自动重试。回收使用scripts/verify_c7_showcase.py，另建sd64结果目录；按本轮短测覆盖解释，缺少20图/无标注/C2不是要求重跑旧全覆盖。仍需确认本轮旁路=true、两尺寸、全部前台观测、一次加载正常关闭。W4/W5无需重跑。
