# C7 可重复启动展示版

状态：OFFLINE_DEMO_READY_FOR_MANUAL_DEPLOYMENT。源码提交 72406576187331566a209ffa9ab43911fe3e5148，父版本 deef7cf，分支 c7-demo-repeatable。

交付目录：D:/PLD/review_packages/C7_Demo_r1_release。上传 C7_Demo_r1.zip 与 C7_Demo_r1.ipynb，按照展示操作.md运行。

本次只增加独立生命周期包装。原 C7_Web_FourImage_r4 的180个产物和原清单，共181个文件逐字节相同。模型、算法、位流、HWH、驱动、阈值、网页均未修改；四面板、四张专项图先原版后改进版及隐藏nogt的行为直接继承原封存网页。

支持离线安装格重复运行、正在服务时重复启动返回已有地址、正常导出结束后原内核新建会话、下次开机从同一Notebook再次启动。每轮有独立会话和导出副本；不会删除历史。Linux boot_id及进程锁用于阻止同一次开机中未知旧会话的重新加载，不提供强制重试；故障保留原内核和缓冲。旧启动失败文件在跨开机后原字节转存并记录路径/SHA，避免原launch固定文件名覆盖证据。

13项主机测试通过，执行实际封存的launch、HTTP服务、Manager及ZIP导出流程；硬件prepare/open、Linux锁和boot_id使用明确的测试替身，图像帧执行0。覆盖正常重复、并发/重复启动、端口占用、忙碌/故障保护、异常导出、内核身份丢失、新开机身份、文件身份和历史保存。日志中最后一项是Notebook语法与包身份检查，其测试函数旧名称包含first_cell_twice；真正的离线单元格重复执行另由verify_release.py完成并记录在notebook_verification.json。源码只修正了该测试函数名称，未改变断言。

实际最终发布Notebook第一格连续执行两次通过，返回同一Python实例，不创建启动attempt或claim，不导入pynq/launch；默认第二格AUTHORIZED=False会阻止启动。最终ZIP CRC、全部181个继承文件及安装身份均通过。

本机未连接板卡、未执行MMIO/DMA/位流加载、模型前向或重新评价。WEB_LIFECYCLE_BOARD_STATUS=NOT_RUN；历史算法实板证据保持原状态。重复启动的真实板端验证仍需用户按Notebook手动执行。此版不加速专项补标，正常关服务不是Linux关机；LATENCY_TARGET_UNSET。

封存顺序：关闭测试输出→写本报告/状态→来源与文件清单→逐项验证→外部最终回执。ZIP不包含自身SHA、最终回执或活动控制台；执行期记录不打入发布ZIP。原r4、旧板测包和历史故障证据全部保留。
