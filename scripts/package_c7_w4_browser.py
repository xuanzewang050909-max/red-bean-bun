"""Create immutable formal browser package around the existing trusted C7 bit."""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from system_bench.common import info,write_json,require,BASELINE_MANIFEST_SHA
from scripts.package_c7_w4_processing import notebook as processing_notebook


def notebook(digest):
    # Keep the reviewed fresh-directory hash-first extraction; use this package's names.
    extract=''.join([c for c in processing_notebook(digest)['cells'] if c['cell_type']=='code'][0]['source'])
    extract=extract.replace('c7_w4_processing_r1','c7_w4_browser_r1').replace('w4_manifest.json','w4b_manifest.json').replace('W4_PACKAGE_PASS','W4B_PACKAGE_PASS')
    items=[('1. 校验并解压','全新文件夹上传两文件。断电不会删除SD旧解压目录；不要在旧目录重跑。',extract),
      ('2. 检查环境','保留端口8090。此步不下载FPGA；端口占用/空间不足就停止保留输出。',
       "from w4b_board import prepare_w4b, start, ready_w4b, summarize_w4b, close_w4b, export_w4b\nif 'browser_context' in globals():\n    raise RuntimeError('Already prepared; continue to next cell')\nbrowser_context = prepare_w4b(w4_root)\n"),
      ('3. 加载一次并启动服务','应出现BROWSER_SERVICE_READY，真实C7只加载一次，此时没有图像收发。',
       'browser_status = await start(browser_context)\nprint(browser_status)\n'),
      ('4. 浏览器正式三轮','先运行本框看到W4B_BROWSER_READY，再打开 http://192.168.2.99:8090/ 并Ctrl+F5。页眉W4b，点击“开始3轮”一次。固定im0001/512/C7/T112/模式3/fast，每轮3预热+100计时，总309帧。保持前台，不能切页、刷新、锁屏。看到W4B_BROWSER_COMPLETE、完成309/309后截图，再返回Notebook继续。',
       'print(ready_w4b(browser_context))\n'),
      ('5. 核对三轮统计','只有网页309帧全部完成后才运行。必须每轮100个前台计时样本；预热不计入。',
       'browser_summary = summarize_w4b(browser_context)\n'),
      ('6. 安全关闭','无错误/在途任务/保留缓冲才关闭。', 'await close_w4b(browser_context)\n'),
      ('7. 导出并下载','应出现W4B_RESULTS_READY。Ctrl+S，下载运行后的c7_w4_browser.ipynb以及同级c7_w4_browser_results.zip。',
       'browser_bundle = await export_w4b(browser_context)\n')]
    nb=processing_notebook(digest);nb['cells']=[dict(cell_type='markdown',metadata={},source=[
        '# C7 W4b：浏览器正式性能\n\nBOARD_NOT_RUN。真实PL算法/驱动不变，没有CPU参考或回退。\n\n',
        '任何红色报错、网页中止或60秒无新进展：停止并保留内核与输出，不自动重试/重启/重载。保持页面前台；隐藏或中途停止不能当作正式通过。\n'])]
    for title,text,code in items:
        nb['cells'] += [dict(cell_type='markdown',metadata={},source=[f'## {title}\n\n{text}\n']),
                        dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=code.splitlines(True))]
    return nb


def main():
    parser=argparse.ArgumentParser();parser.add_argument('baseline',type=Path);parser.add_argument('destination',type=Path);a=parser.parse_args()
    require(not a.destination.exists(),'Use fresh release directory')
    require(info(a.baseline/'q4d_manifest.json')['sha256']==BASELINE_MANIFEST_SHA,'Trusted C7 identity differs')
    old=json.loads((a.baseline/'q4d_manifest.json').read_bytes())
    require(all(info(a.baseline/n)==v for n,v in old['artifacts'].items()),'Original C7 release changed')
    package=a.destination/'package';upload=a.destination/'upload';package.mkdir(parents=True);upload.mkdir()
    b=json.loads((a.baseline/'browser_manifest.json').read_bytes())
    for name in b['artifacts']:
        if name.startswith(('pynq_q4d/','ui/')):continue
        dest=package/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.baseline/name,dest)
    shutil.copytree(ROOT/'pynq_w4b',package/'pynq_w4b',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'ui_w4b',package/'ui')
    b['revision']='c7_w4_browser_r1';b['phase']='FORMAL_BROWSER_PERFORMANCE_NOT_QUALITY_ACCEPTANCE'
    b['artifacts']={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()}
    write_json(package/'browser_manifest.json',b)
    shutil.copy2(ROOT/'scripts/w4b_board.py',package/'w4b_board.py')
    manifest=dict(revision='c7_w4_browser_r1',board_status='BOARD_NOT_RUN',
        baseline_manifest_sha256=BASELINE_MANIFEST_SHA,
        protocol=dict(image_id='im0001',side=512,algorithm='C7',threshold=112,mode='final',png_profile='fast',repeats=3,warmup=3,samples=100,total=309),
        artifacts={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()})
    write_json(package/'w4b_manifest.json',manifest)
    zpath=upload/'c7_w4_browser_r1.zip'
    with zipfile.ZipFile(zpath,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(package))
    write_json(upload/'c7_w4_browser.ipynb',notebook(info(zpath)['sha256']))
    write_json(a.destination/'release.json',dict(status='HOST_PACKAGE_BOARD_NOT_RUN',files={p.name:info(p) for p in upload.iterdir()},embedded_files=len(manifest['artifacts'])+1))
    print('W4B_PACKAGE_READY',upload)


if __name__=='__main__':main()
