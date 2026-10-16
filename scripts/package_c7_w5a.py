"""Separate W5a package around byte-identical trusted C7 hardware and data."""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from system_bench.common import info,write_json,require,BASELINE_MANIFEST_SHA
from scripts.package_c7_w4_processing import notebook as previous_notebook

REVISION='c7_w5a_stability_r1'


def notebook(digest):
    nb=previous_notebook(digest)
    extract=''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source'])
    extract=extract.replace('c7_w4_processing_r1',REVISION).replace('w4_manifest.json','w5a_manifest.json').replace('W4_PACKAGE_PASS','W5A_PACKAGE_PASS')
    steps=[('1. 校验与解压','全新目录上传两文件；不覆盖旧记录。',extract),
       ('2. 检查环境与存储','至少1.5 GiB空闲；验证硬链接和配对文件，尚未加载PL。',
        "from w5a_board import prepare_w5a, start, ready_w5a, summarize_w5a, close_w5a, export_w5a\nif 'browser_context' in globals():\n    raise RuntimeError('Already prepared; do not repeat')\nbrowser_context = prepare_w5a(w4_root)\n"),
       ('3. 加载C7一次','原可信C7 bit/HWH/驱动；此时无图像收发。',
        'browser_status = await start(browser_context)\nprint(browser_status)\n'),
       ('4. 前台1000帧','先运行本框；打开 http://192.168.2.99:8090/ 并Ctrl+F5，页眉W5a。点击开始1000帧一次。保持前台、关闭自动休眠，不切页/刷新/锁屏。每10帧切图/参数，20图、256/512、C7最终模式T96/112/128，每帧起点间隔至少2秒，不是最高FPS。约35～50分钟，看到W5A_BROWSER_COMPLETE后截图，再返回本Notebook。',
        'print(ready_w5a(browser_context))\n'),
       ('5. 核对完整稳定组','需要1000任务、两端时钟至少30分钟、逐帧前台/计数/内存记录；通过后仍待下载独立核验。',
        'w5a_summary = summarize_w5a(browser_context)\n'),
       ('6. 安全关闭','有故障/在途任务/保留缓冲则拒绝，不自动重置。',
        'await close_w5a(browser_context)\n'),
       ('7. 导出并下载','出现W5A_RESULTS_READY后Ctrl+S，下载运行后的c7_w5a_stability.ipynb及同级c7_w5a_results.zip。ZIP按内容去重，每帧原始数组/图像可由引用完整还原。',
        'w5a_bundle = await export_w5a(browser_context)\n')]
    nb['cells']=[dict(cell_type='markdown',metadata={},source=['# W5a：可信C7前台稳定性\n\nBOARD_NOT_RUN。没有新算法/HDMI/CPU分割回退。功耗无仪器未测；W5b断连/队列/模式等另轮，不能称完整W5通过。\n\n红色报错、页面隐藏/中止或60秒无新任务：停止保留内核/输出，不自动重试、复位或重载。\n'])]
    for title,description,code in steps:
        nb['cells'] += [dict(cell_type='markdown',metadata={},source=[f'## {title}\n\n{description}\n']),
            dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=code.splitlines(True))]
    return nb


def build(baseline,destination):
    require(not destination.exists(),'Fresh destination required')
    require(info(baseline/'q4d_manifest.json')['sha256']==BASELINE_MANIFEST_SHA,'Wrong trusted baseline')
    old=json.loads((baseline/'q4d_manifest.json').read_bytes())
    require(all(info(baseline/n)==v for n,v in old['artifacts'].items()),'Trusted C7 source bytes changed')
    package=destination/'package';upload=destination/'upload'
    package.mkdir(parents=True);upload.mkdir()
    m=json.loads((baseline/'browser_manifest.json').read_bytes())
    for name in m['artifacts']:
        if name.startswith(('pynq_q4d/','ui/')):continue
        target=package/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(baseline/name,target)
    shutil.copytree(ROOT/'pynq_w5a',package/'pynq_w5a',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'ui_w5a',package/'ui')
    m['revision']=REVISION
    m['artifacts']={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()}
    write_json(package/'browser_manifest.json',m)
    shutil.copy2(ROOT/'scripts/w5a_board.py',package/'w5a_board.py')
    manifest=dict(revision=REVISION,board_status='BOARD_NOT_RUN',baseline_manifest_sha256=BASELINE_MANIFEST_SHA,
        protocol=dict(tasks=1000,minimum_seconds=1800,block=10,images=sorted(m['images']),thresholds=[96,112,128],
                      start_interval_ms=2000,memory_growth_after_100_limit_bytes=96*1024**2,min_available_bytes=48*1024**2,
                      scope='W5a only; no W5b recovery, power or clinical acceptance'),
        artifacts={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()})
    write_json(package/'w5a_manifest.json',manifest)
    zpath=upload/(REVISION+'.zip')
    with zipfile.ZipFile(zpath,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(package))
    write_json(upload/'c7_w5a_stability.ipynb',notebook(info(zpath)['sha256']))
    write_json(destination/'release.json',dict(status='HOST_PACKAGE_BOARD_NOT_RUN',files={p.name:info(p) for p in upload.iterdir()},
        embedded_files=len(manifest['artifacts'])+1))
    print('W5A_PACKAGE_READY',upload)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();build(a.baseline,a.destination)
