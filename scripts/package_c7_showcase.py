"""Create a separate 20-image demo release from verified C7/W5b data."""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from pynq_showcase.protocol import file_info, write_json, require, validate_package
from w5b_board import validate_w5b
from showcase_board import EXAMPLES, validate_showcase
from package_c7_w5b import notebook as old_notebook
REVISION = 'c7_showcase_r1'


def notebook(digest):
    old = old_notebook(digest)
    extract = ''.join(next(c for c in old['cells'] if c['cell_type']=='code')['source'])
    extract = extract.replace('c7_w5b_interaction_r1', REVISION).replace('w5b_manifest.json','showcase_manifest.json').replace('W5B_PACKAGE_PASS','SHOWCASE_PACKAGE_PASS')
    steps = [
        ('1. 校验并解压配对包', '新建 retina_c7_showcase_r1，上传本Notebook和c7_showcase_r1.zip；不手动解压。', extract),
        ('2. 检查环境', '旧8090服务须已安全关闭，至少1GiB空闲；本框不加载PL。', "from showcase_board import prepare_showcase, start, summary_showcase, close_showcase, export_showcase\nif 'browser_context' in globals():\n    raise RuntimeError('Already prepared; continue to next cell')\nbrowser_context = prepare_showcase(w4_root)\n"),
        ('3. 加载一次并启动', '仍使用可信C7原bitstream；错误停止保留现场，不自动重试。', 'print(await start(browser_context))\n'),
        ('4. 自由展示', '打开8090并Ctrl+F5确认DEMO R1。全部20张/讲解8张可选，上一张和下一张均新运行PL；逐张运行从当前列表第一张开始。建议先20张逐张运行，再试上一张/下一张，切换256运行一张。功能演示中单独试im0324_nogt/C7最终112、im0324/C7旁路112、im0001/C2模式1和2/T28，再返回讲解8张运行。允许额外操作，最多100次；不是最大FPS测量。本轮不录视频。', "print('SHOWCASE_MANUAL_READY: variable count, real PL per frame; video deferred')\n"),
        ('5. 核对并安全关闭', '等当前任务和图像绘制完成后运行。无需恰好七次；未观察帧如实列出，不冒充完整展示。硬件FAULT不得强制关闭。', 'print(summary_showcase(browser_context))\nawait close_showcase(browser_context)\n'),
        ('6. 导出本轮记录', '导出所有真实原始数组/PNG/回读/观测。保留旧会话。', 'showcase_bundle = await export_showcase(browser_context)\n'),
        ('7. 保存并下载', 'Ctrl+S，下载执行后的c7_showcase.ipynb及c7_showcase_results.zip至电脑Downloads。无需录像。', "print('SHOWCASE_FINISHED:', browser_context['manager'].status())\n")]
    old['cells'] = [dict(cell_type='markdown', metadata={}, source=['# C7 · 20张图自由展示\n\n新展示流程 BOARD_NOT_RUN，C7算法/bit/HWH不变；本轮不录视频。异常或超时停止保存现场，不自动重载。\n'])]
    for title, description, code in steps:
        old['cells'] += [dict(cell_type='markdown', metadata={}, source=[f'## {title}\n\n{description}\n']),
                         dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=code.splitlines(True))]
    return old


def build(baseline, destination):
    require(not destination.exists(), 'Fresh destination required')
    old = validate_w5b(baseline)
    package = destination/'package'; upload = destination/'upload'
    package.mkdir(parents=True); upload.mkdir()
    m = json.loads((baseline/'browser_manifest.json').read_bytes())
    for name in m['artifacts']:
        if name.startswith(('pynq_w5b/','ui/')): continue
        target = package/name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(baseline/name,target)
    shutil.copytree(ROOT/'pynq_showcase', package/'pynq_showcase', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT/'ui_showcase', package/'ui')
    m['revision'] = REVISION
    m['artifacts'] = {p.relative_to(package).as_posix():file_info(p) for p in sorted(package.rglob('*')) if p.is_file()}
    write_json(package/'browser_manifest.json',m)
    shutil.copy2(ROOT/'scripts/showcase_board.py',package/'showcase_board.py')
    manifest = dict(revision=REVISION, board_status='BOARD_NOT_RUN', examples=EXAMPLES,
        video='DEFERRED_BY_USER', session_limit=100, baseline_manifest_sha256=old['baseline_manifest_sha256'],
        artifacts={p.relative_to(package).as_posix():file_info(p) for p in sorted(package.rglob('*')) if p.is_file()})
    write_json(package/'showcase_manifest.json',manifest)
    validate_showcase(package)
    zpath = upload/(REVISION+'.zip')
    with zipfile.ZipFile(zpath,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(package))
    write_json(upload/'c7_showcase.ipynb',notebook(file_info(zpath)['sha256']))
    write_json(destination/'release.json',dict(status='HOST_PACKAGE_BOARD_NOT_RUN', files={p.name:file_info(p) for p in upload.iterdir()}))
    print('SHOWCASE_PACKAGE_READY',upload)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('baseline',type=Path); p.add_argument('destination',type=Path)
    a=p.parse_args(); build(a.baseline,a.destination)
