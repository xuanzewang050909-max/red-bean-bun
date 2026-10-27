# C7四图网页：先原版、后改进版

只改新发布中的网页适配与目标分派，原C7位流/时钟/DMA/控制驱动不变。用户方案名始终C7。

三图板测返回包已用原three_repair/verify_download.py验证；6例含三配置小工作区和三实际图逐字一致，真实PL来源及访问账本通过。三图处理为512/final/T112，profile=0/1/2。im0324沿用原单图50MHz位流，无profile寄存器写入。输入按真实RGB/FOV字节SHA匹配，名字仅显示；三图profile只选择有限参数，不包含mask答案。

四张目标图运行顺序：①独立运行原100MHz C7并显示；②用户点击改进版，绑定同一会话的已完成原版record/输入/输出SHA，再把原RGB/FOV和该次C7 mask交给原50MHz PL。第二步不重跑C7。两步完成后，查看原版/改进版只读取这两个已保存结果。切换图像清除当前对比引用，防止串图。im0324现在也按这两步运行，单图补标算法和位流保持不变。

PS只调度、核验、解包和显示，发布代码不加载参考mask返回。20次算子与全部中间工作区SHA对照；失败停机保留缓冲。原C7、三图与im0324位流、算子、参数和数值输出不修改。旧两图亮区清理不包含在本版本。第一步与第二步独立计时，复用的C7计数不再算作第二步新执行。

新源文件在c7_web/。build_web.py从原四图网页ZIP及冻结PL发布构造全新目录、逐项验SHA；package_web.py沿用旧ZIP+外部Notebook/SHA封存流程。test_web.py和host_preview.py仅本机测试，不进入网页发布。verify_download.py独立检查未来网页导出；--host-test显式标记替身证据，不能宣称板测通过。

本机命令（不连接板卡）：

```powershell
$env:PYTHONPATH='D:/PLD/retina_fpga/.venv/Lib/site-packages'
& D:/PLD/retina_c7_structured_refine/.venv/Scripts/python.exe -X utf8 -B three_web/build_web.py --output <全新发布目录>
$env:C7_WEB_PACKAGE='<全新发布目录>'
& D:/PLD/retina_c7_structured_refine/.venv/Scripts/python.exe -X utf8 -B three_web/test_web.py
& D:/PLD/retina_c7_structured_refine/.venv/Scripts/python.exe -X utf8 -B three_web/package_web.py --root <全新发布目录> --output <全新交付目录> --revision r4
```

不重新训练、不跑模型、不运行综合布线，不改原图/原mask/阈值。新增发布待用户手动上传启动，见更新步骤.md。原网页布局保持四个画面，没有增加下方两个对比图。
