from software import *
import shutil
dst=Path(__file__).parent/'board'
shutil.copy2(Path(__file__).with_name('board_run.py'),dst/'board_run.py')
parent=Path('D:/PLD/review_packages/C7_AtomicBridge_Guard50_Board_r1/trusted_c7/capture_contract.json')
runtime=json.loads(parent.read_text())['runtime_driver_sources']
(dst/'runtime_contract.json').write_text(json.dumps({k:runtime[k] for k in ['Overlay','allocate']},indent=2))
(OUT/'board_runtime_source.json').write_text(json.dumps(dict(parent=str(parent),sha256=hashlib.sha256(parent.read_bytes()).hexdigest(),selected=['Overlay','allocate'],new_board_checks_executed=False),indent=2))
cells=[]
def md(text):cells.append(dict(cell_type='markdown',metadata={},source=text.splitlines(True)))
def code(text):cells.append(dict(cell_type='code',metadata={},source=text.splitlines(True),outputs=[],execution_count=None))
md('# 单张眼底图补标：人工板测\n\n只处理 im0324 的既有 512 输入。此包不运行旧 C7、不读取旧 DDR 地址、不恢复历史流程。旧板卡现场须先自行确认已保存且可安全切换；本 Notebook 不自动清场或释放旧缓冲。\n\n本页打开和第一格均不访问硬件。**不要 Run All。** 第二格会加载本次新 50MHz overlay，先小工作区，再本图。任何错误或断连立即停止，不重复点击，不重启内核。')
code("from pathlib import Path\nimport sys\nroot=Path.cwd()/'payload'\nsys.path.insert(0,str(root))\nimport board_run\nmanifest=board_run.verify(root)\nprint('OFFLINE_PACKAGE_VERIFIED',manifest['algorithm'],manifest['processing_shape'])\n")
md('## 人工确认后才执行这一格\n\n确认板卡空闲、旧现场已经保存，并已获准进行本次新板测后，手动将 `AUTHORIZED` 改为 `True`。保持当前 Notebook 打开，只执行一次。正常需要几十秒到数分钟；没有完成时不要重复运行。')
code("AUTHORIZED=False\nassert AUTHORIZED, '尚未人工确认本次板测；保持此处不执行'\nresult=board_run.start(root,Path.cwd()/'board_results_r1',\n    operator_confirmation='I_AUTHORIZE_SINGLE_IMAGE_BOARD_TEST_ONCE')\nprint(result)\n")
md('## 仅成功后显示真实板端结果\n\n以下只从刚保存的 PL 输出绘图；不会把预期输出传给硬件。')
code("from PIL import Image\nfrom IPython.display import display\nimage_path=board_run.render_saved(root,Path.cwd()/'board_results_r1')\ndisplay(Image.open(image_path))\nprint('原图 / 旧标注 / 真实PL结果：绿=旧，青=新增；仍待独立主机核验')\n")
md('## 导出\n\n正常完成或出现错误、且内核仍响应时，执行下面一格一次并下载 ZIP。网页断连或内核忙时，不追加执行硬件单元，不强制重启；先保留当前记录。')
code("from IPython.display import FileLink,display\nreceipt=board_run.export_results(Path.cwd()/'single_image_board_results_r1.zip')\nprint(receipt)\ndisplay(FileLink('single_image_board_results_r1.zip'))\n")
nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')),nbformat=4,nbformat_minor=4)
(dst.parent/'Single_Image_Repair_Operator.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2))
print('BOARD_ASSETS_READY_NO_BOARD_ACCESS')
