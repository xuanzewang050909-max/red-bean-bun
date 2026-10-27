"""Generate manual-only notebook and source-bound host verifier, no hardware calls."""
from identify import *
def main():
    cells=[]
    def md(s):cells.append(dict(cell_type='markdown',metadata={},source=s.splitlines(True)))
    def code(s):cells.append(dict(cell_type='code',metadata={},source=s.splitlines(True),outputs=[],execution_count=None))
    md('# C7三图专项补标：待另行授权的板测入口\n\n本任务只完成上板前准备。当前不授权加载位流。只处理 im0004、im0291、im0319 的原512输入；旧C7掩膜来自已核验PL归档。新PL从RGB计算新增，不播放参考mask。\n\n不要 Run All。不要在旧故障内核中运行，不释放旧缓冲。本页打开、解压及离线检查不访问硬件；先另行确认旧现场安全保存及本版本板测授权。')
    code("from pathlib import Path\nimport zipfile\narchive=Path.cwd()/'C7_ThreeImage_Completion_Board_r1.zip'\nassert archive.is_file()\nassert not (Path.cwd()/'payload').exists(), '目录已存在；保留原目录，不覆盖解压'\nwith zipfile.ZipFile(archive) as z:\n    root_dir=Path.cwd().resolve()\n    for name in z.namelist():\n        target=(root_dir/name).resolve()\n        assert root_dir in target.parents, '不安全路径'\n    for name in z.namelist():\n        if Path(name).parts and Path(name).parts[0]=='payload':\n            z.extract(name,root_dir)\nprint('仅解压完成，未访问板卡')\n")
    code("import sys\nroot=Path.cwd()/'payload'\nsys.path.insert(0,str(root))\nimport board_run\nmanifest=board_run.verify(root)\nprint('OFFLINE_PACKAGE_VERIFIED',manifest['algorithm'],manifest['case_order'])\nprint('此格只核验文件；尚未执行板测')\n")
    md('## 获得本版本单独板测授权后才可运行\n\n当前保持AUTHORIZED=False。另行授权且人工确认板卡空闲、旧现场安全保存之后，才能手动改为True。此格加载新50MHz精修overlay，先3个小工作区配置测试，再依次执行三张真实图。失败立即停止并保留状态，不自动重试、释放或复位。每张图可能数十秒，总流程可能数分钟；最终实际时间以记录为准。')
    code("AUTHORIZED=False\nassert AUTHORIZED, '当前仅上板前交付；须另行授权并人工确认后执行'\nresult=board_run.start(root,Path.cwd()/'three_image_board_results_r1',\n    operator_confirmation='I_AUTHORIZE_THREE_IMAGE_BOARD_TEST_ONCE')\nprint(result)\n")
    md('## 仅在全部运行成功后显示\n\n下格只读取刚保存的真实PL结果。图片顺序：原图、原C7、原绿/新增青。预期输出仅用于逐字核对，不写入PL。')
    code("from PIL import Image\nfrom IPython.display import display\nfor image_path in board_run.render_saved(root,Path.cwd()/'three_image_board_results_r1'):\n    print(image_path)\n    display(Image.open(image_path))\n")
    md('## 导出记录\n\n完成或报错后、内核仍可响应时，只运行此格导出。若In[*]或页面断连，不追加运行、不重启或断电；先保留当前页面与记录。')
    code("from IPython.display import FileLink,display\np=Path.cwd()/'three_image_board_results_r1.zip'\nprint(board_run.export_results(p))\ndisplay(FileLink(p.name))\n")
    nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3')),nbformat=4,nbformat_minor=4)
    (ROOT/'three_repair/C7_ThreeImage_Operator_r1.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf8')
    print('MANUAL_NOTEBOOK_WRITTEN; no board access')
if __name__=='__main__':main()
