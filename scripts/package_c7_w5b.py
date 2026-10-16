"""Independent W5b release; original C7 hardware/arrays and published W5a unchanged."""
import argparse
import copy
import json
import shutil
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from system_bench.common import info,write_json,require,BASELINE_MANIFEST_SHA
from scripts.package_c7_w5a import notebook as old_notebook
from w5b_board import planned_cases,manual_cases
REVISION='c7_w5b_interaction_r1'


def notebook(digest):
    nb=old_notebook(digest)
    extract=''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source'])
    extract=extract.replace('c7_w5a_stability_r1',REVISION).replace('w5a_manifest.json','w5b_manifest.json').replace('W5A_PACKAGE_PASS','W5B_PACKAGE_PASS')
    steps=[('1. 配对包校验','新目录上传两个文件，不手动解压，不覆盖旧记录。',extract),
    ('2. 环境检查','至少1GiB空闲；原8090服务必须已安全结束。不加载PL。',
     "from w5b_board import prepare_w5b, start, automatic_w5b, manual_ready_w5b, close_w5b, export_w5b\nif 'browser_context' in globals():\n    raise RuntimeError('Already prepared; do not repeat')\nbrowser_context = prepare_w5b(w4_root)\n"),
    ('3. 加载一次','保留原C7，不重建硬件。',
     'print(await start(browser_context))\n'),
    ('4. 自动35帧与接口检查','不要同时打开网页提交任务。预期HTTP422/队列Busy是指定非法请求测试，程序会核对并继续；若代码框红色异常则停下，保留现场。',
     'await automatic_w5b(browser_context)\n'),
    ('5. 网页七次操作','先运行此框。打开http://192.168.2.99:8090/并Ctrl+F5确认W5b。全部512、快速PNG：①im0001/C7/最终/T112；②im0324_nogt/C7/最终/T112（Dice/IoU应无数据）；③im0324/C7/旁路/T112（仅原图）；④im0001/C2/初始候选模式1/T28；⑤同图C2/闭运算模式2/T28；⑥同图C2/最终模式3/T28。每次运行后等图像及浏览器延迟显示完成，保留截图。第六次完成后Ctrl+F5刷新，重新选⑦im0001/C7/最终/T112运行。期间不拔网线、不重启、不关电。预期completed=42，加载仍为1。',
     'print(manual_ready_w5b(browser_context))\n'),
    ('6. 核对并安全关闭','完成七次操作后再运行；检查同一会话、两页面身份、逐帧参数/计数、无GT与安全状态。',
     'await close_w5b(browser_context)\n'),
    ('7. 导出并下载','出现W5B_RESULTS_READY后Ctrl+S，下载本Notebook及同目录c7_w5b_results.zip。保留板端结果。',
     'w5b_bundle = await export_w5b(browser_context)\n')]
    nb['cells']=[dict(cell_type='markdown',metadata={},source=['# W5b：C7接口、模式及网页刷新验证\n\nBOARD_NOT_RUN。无新算法、无CPU分割回退。局部HTTP客户端关闭和网页刷新不等于物理断网/断电恢复。不注入硬件DMA故障。任何非预期错误/60秒无进展停止，不自动重试。\n'])]
    for title,description,code in steps:
        nb['cells'] += [dict(cell_type='markdown',metadata={},source=[f'## {title}\n\n{description}\n']),
                       dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=code.splitlines(True))]
    return nb


def build(baseline,destination):
    require(not destination.exists(),'Use a fresh destination')
    old=json.loads((baseline/'q4d_manifest.json').read_bytes())
    require(info(baseline/'q4d_manifest.json')['sha256']==BASELINE_MANIFEST_SHA,'Wrong baseline')
    require(all(info(baseline/n)==v for n,v in old['artifacts'].items()),'Baseline bytes changed')
    package=destination/'package';upload=destination/'upload'
    package.mkdir(parents=True);upload.mkdir()
    m=json.loads((baseline/'browser_manifest.json').read_bytes())
    for name in m['artifacts']:
        if name.startswith(('pynq_q4d/','ui/')):continue
        target=package/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(baseline/name,target)
    shutil.copytree(ROOT/'pynq_w5b',package/'pynq_w5b',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'ui_w5b',package/'ui')
    m['revision']=REVISION
    m['images']['im0324_nogt']=copy.deepcopy(m['images']['im0324'])
    for entry in m['images']['im0324_nogt'].values():entry['evaluation_only']={}
    m['artifacts']={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()}
    write_json(package/'browser_manifest.json',m)
    shutil.copy2(ROOT/'scripts/w5b_board.py',package/'w5b_board.py')
    manifest=dict(revision=REVISION,board_status='BOARD_NOT_RUN',baseline_manifest_sha256=BASELINE_MANIFEST_SHA,
        automatic=planned_cases(),manual=manual_cases(),no_gt_scope='Alias of im0324 same input, labels deliberately omitted for UI contract only; not external data',
        artifacts={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()})
    write_json(package/'w5b_manifest.json',manifest)
    zpath=upload/(REVISION+'.zip')
    with zipfile.ZipFile(zpath,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(package))
    write_json(upload/'c7_w5b_interaction.ipynb',notebook(info(zpath)['sha256']))
    write_json(destination/'release.json',dict(status='HOST_PACKAGE_BOARD_NOT_RUN',files={p.name:info(p) for p in upload.iterdir()},embedded_files=len(manifest['artifacts'])+1))
    print('W5B_PACKAGE_READY',upload)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();build(a.baseline,a.destination)
