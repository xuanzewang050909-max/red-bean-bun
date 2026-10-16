"""Pair the trusted A0 r2 hardware with new timing-only instrumentation."""
import argparse
import ast
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dma_bench.common import HARDWARE, HELPER_SHA, PROTOCOL, REVISION, info, require, write_json
from scripts.package_c7_w4_processing import notebook as original_notebook


def notebook(digest):
    nb = original_notebook(digest)
    extract = ''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source'])
    extract = extract.replace('c7_w4_processing_r1', REVISION).replace('w4_manifest.json', 'w4c_manifest.json').replace('W4_PACKAGE_PASS', 'W4C_PACKAGE_PASS')
    sections = [
      ('1. 校验并解压', '新建retina_c7_w4_dma_r1，只上传配对Notebook和ZIP，不手动解压。断电后也使用全新文件夹，保留旧结果。', extract),
      ('2. 检查环境', '原8090服务必须已安全结束，并在Running关闭成功完成的旧内核。本步骤不加载FPGA；需要至少2GiB剩余空间。',
       "from dma_bench.board import prepare, load, smoke, measure, finish_export\nif 'dma_context' in globals():\n    raise RuntimeError('Already prepared; continue to next cell')\ndma_context = prepare(w4_root)\n"),
      ('3. 加载一次', '加载可信A0 r2独立回环。没有C7算法，不启动8090显示服务。', 'load(dma_context)\n'),
      ('4. 短包验证', '17个32位字逐字核对、官方缓存同步和收发长度核对。', 'smoke(dma_context)\n'),
      ('5. 256正式计时', '3轮，每轮3次预热＋100次计时。每次使用不同输入并保存完整输出；309次。', 'measure(dma_context, 256)\n'),
      ('6. 512正式计时', '同样3轮×103次。加上短包共619次。不要同时运行其他板上任务。', 'measure(dma_context, 512)\n'),
      ('7. 安全关闭并导出', '先验证IDLE并停止已完成的DMA，再打包；导出可能几十秒。看到W4C_RESULTS_READY后Ctrl+S，下载本Notebook和同目录c7_w4_dma_results.zip。', 'dma_bundle = finish_export(dma_context)\n')]
    nb['cells'] = [dict(cell_type='markdown', metadata={}, source=[
        '# C7系统 W4c：独立纯DMA回环测量\n\nBOARD_NOT_RUN。无医学算法，无HDMI，不修改C7。\n\n红色错误或超过一分钟无新进度时停止，保留内核、输出、缓冲；不重复运行、不重置、不重载。不得用本轮代替C7端到端性能。\n'])]
    for title, text, code in sections:
        ast.parse(code, feature_version=(3,10))
        nb['cells'] += [dict(cell_type='markdown', metadata={}, source=[f'## {title}\n\n{text}\n']),
            dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=code.splitlines(True))]
    return nb


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    require(not a.destination.exists(), 'Fresh release directory required')
    for name, sha in HARDWARE.items():
        require(info(a.baseline/name)['sha256']==sha, 'Trusted A0 r2 changed')
    nbpath=a.baseline/'a0_dma_loopback.ipynb'
    require(info(nbpath)['sha256']=='199c5820f650aa310b56e27cdb7629fb6a917844333499c4f7bd83040199a023', 'Original notebook changed')
    helper=''.join(next(c for c in json.loads(nbpath.read_bytes())['cells'] if c['cell_type']=='code')['source']).encode()
    require(hashlib.sha256(helper).hexdigest()==HELPER_SHA, 'Original embedded A0 helper changed')
    package=a.destination/'package';upload=a.destination/'upload'
    package.mkdir(parents=True);upload.mkdir()
    for name in (*HARDWARE, 'a0_manifest.json'):
        shutil.copy2(a.baseline/name, package/name)
    (package/'a0_dma_board_test.py').write_bytes(helper)
    shutil.copytree(ROOT/'dma_bench',package/'dma_bench',ignore=shutil.ignore_patterns('__pycache__'))
    m=dict(revision=REVISION, protocol=PROTOCOL, board_status='BOARD_NOT_RUN',
        reuse='Unchanged trusted A0 r2 bit/HWH and exact embedded board helper from original notebook. Manifest historical Windows source bytes differ only by LF normalization in notebook.',
        artifacts={p.relative_to(package).as_posix():info(p) for p in sorted(package.rglob('*')) if p.is_file()})
    write_json(package/'w4c_manifest.json',m)
    archive=upload/(REVISION+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(package))
    write_json(upload/'c7_w4_dma.ipynb',notebook(info(archive)['sha256']))
    write_json(a.destination/'release.json',dict(status='HOST_PACKAGE_BOARD_NOT_RUN',embedded_files=len(m['artifacts'])+1,
        files={p.name:info(p) for p in upload.iterdir()}))
    print('W4C_PACKAGE_READY',upload)


if __name__=='__main__':main()
