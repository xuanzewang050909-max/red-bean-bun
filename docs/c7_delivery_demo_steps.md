# C7正常重启与交付演示：七框说明

本轮新调度为BOARD_NOT_RUN，原硬件/服务/网页/数据全部复用W5b真实已验ZIP，不重复35自动测试、1000帧或CPU测速。预留约10～15分钟操作；如果录视频建议一并完成。

1. W5b原下载已独立核验、服务正常关闭。保存文件，在Jupyter Running关闭已完成内核。终端运行`sudo shutdown -h now`，等待系统结束（约30秒），再断电、重新接电。不要在DMA任务执行时断电。不需要拔SD卡。若上一次关闭有异常，保留现场，不继续本流程。
2. 打开`http://192.168.2.99:9090/tree`。新建**retina_c7_demo_r1**目录，上传`build/deploy/c7_delivery_demo_r1/upload`中的**c7_delivery_demo.ipynb**和**c7_w5b_interaction_r1.zip**。ZIP有意沿用原名字，不手动解压，不打开旧W5b Notebook。
3. 打开新Notebook，依次Shift+Enter第1～3框：应出现W5B_PACKAGE_PASS、DEMO_PRECHECK_PASS（boot_id与uptime）、BROWSER_SERVICE_READY。遇红色异常停下，不连续运行后续框、不修改校验。
4. 第4框出现DEMO_MANUAL_READY后打开`http://192.168.2.99:8090/`并Ctrl+F5。页面仍标W5b，因界面原样复用；**本轮按此表，仅运行七次，不执行旧35自动任务**。全部512、快速无损PNG，每次等图和浏览器延迟显示完整再下一次。

| 次数 | 图像 | 算法 | 模式 | 阈值 | 观察 |
|---|---|---|---|---|---|
| 1 | im0001 | C7 | 最终3 | 112 | 四图、面积、AH/VK、真实新任务 |
| 2 | im0324_nogt | C7 | 最终3 | 112 | 无标注显示“未评价” |
| 3 | im0324 | C7 | 旁路0 | 112 | 仅原图，分割输出清空 |
| 4 | im0001 | C2 | 初始候选1 | 28 | 中间阶段展示 |
| 5 | im0001 | C2 | 闭运算候选2 | 28 | 中间阶段展示 |
| 6 | im0001 | C2 | 最终3 | 28 | 最终候选 |
| 7 | im0001 | C7 | 最终3 | 112 | **第6次完整显示后Ctrl+F5，再选本行运行** |

5. 返回Notebook运行第5框，预期DEMO_CLOSED_IDLE，completed=accepted=7、overlay_downloads=1、pending=0、error=None、retained_buffer_count=0。不凑数、不删除额外任务；次数不符直接保留反馈。
6. 运行第6框，预期DEMO_RESULTS_READY，生成同目录c7_demo_results.zip。运行第7框，预期DEMO_FINISHED和CLOSED/IDLE。
7. Ctrl+S，下载运行后的c7_delivery_demo.ipynb与c7_demo_results.zip到电脑Downloads。视频/七次截图一并保留。之后可关闭已完成内核。

视频建议记录真实板卡及网线、重启后Jupyter启动、一次C7四图、无标注、旁路、中间模式、刷新回C7、最终关闭/导出。可分段录制并明确分段，勿把预存图片剪成实时推理。boot_id只证明当前启动身份，实际断电重启需人工/视频佐证；本轮不称在途断电恢复。

非预期错误或60秒无进展：停止后续点击，保留Notebook和会话目录，不自动重试/重载/重置。原W5b可信ZIP仍在；回滚时先安全结束当前会话，再用原配对包在新目录启动，不能覆盖故障现场或旧结果。
