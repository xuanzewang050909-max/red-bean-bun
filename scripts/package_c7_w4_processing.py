"""Package a new CPU/PL benchmark around byte-identical verified C7 hardware."""
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
from system_bench.common import REVISION, BASELINE_MANIFEST_SHA, info, require, write_json


def notebook(zip_sha):
    extract = '''from pathlib import Path
import hashlib, json, zipfile, sys
if 'w4_root' in globals():
    raise RuntimeError('Already extracted; continue to next cell')
archive_path = Path('c7_w4_processing_r1.zip')
if hashlib.sha256(archive_path.read_bytes()).hexdigest() != '%s':
    raise ValueError('Wrong package bytes; FPGA untouched')
with zipfile.ZipFile(archive_path) as z:
    entries = z.infolist()
    names = [e.filename for e in entries]
    manifest = json.loads(z.read('w4_manifest.json'))
    if len(names) != len(set(names)) or set(names) != set(manifest['artifacts']) | {'w4_manifest.json'}:
        raise ValueError('Wrong package inventory')
    if len(names) > 220 or sum(e.file_size for e in entries) > 128*1024*1024:
        raise ValueError('Wrong archive size')
    for e in entries:
        p = Path(e.filename)
        if p.is_absolute() or '..' in p.parts or '\\\\' in e.filename or ':' in e.filename or e.is_dir():
            raise ValueError('Unsafe archive member')
        data = z.read(e.filename)
        if e.filename != 'w4_manifest.json' and manifest['artifacts'][e.filename] != {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}:
            raise ValueError('Package mismatch: ' + e.filename)
    w4_root = (Path.cwd() / 'c7_w4_processing_r1').resolve()
    w4_root.mkdir(exist_ok=False)
    for e in entries:
        dest = w4_root / e.filename
        if w4_root not in dest.resolve().parents:
            raise ValueError('Unsafe output path')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(e.filename))
sys.path.insert(0, str(w4_root))
print('W4_PACKAGE_PASS: fresh paired package; FPGA untouched')
''' % zip_sha
    sections = [
        ('1. 校验并解压', '只上传本 Notebook 和配套 ZIP；不手动解压，不从旧 Notebook 中间继续。', extract),
        ('2. 检查环境', '检查完整包、OpenCV/NumPy和旧服务端口，此时不下载FPGA。OpenCV缺失或8090占用就保留报错停止，不安装/改驱动。',
         "from system_bench.board import prepare, load, measure, summary, finish_export\nif 'w4_context' in globals():\n    raise RuntimeError('Already prepared; continue to next cell')\nw4_context = prepare(w4_root)\n"),
        ('3. 加载一次', '复用已核验C7 bit/HWH/官方驱动。只加载一次，尚未收发图像。不启动8090网页服务。',
         'await load(w4_context)\n'),
        ('4. 256正式对照', 'C7最终模式T112、固定im0001。3轮，每轮PS CPU和PL各3预热+100计时。ARM对照可能耗时较长；每帧有进度。每轮交替先测CPU/PL，全部保留。',
         'await measure(w4_context, 256)\n'),
        ('5. 512正式对照', '同样3轮×(3预热+100计时)，每种设备309次。不要同时在其他Notebook/8090提交任务。',
         'await measure(w4_context, 512)\n'),
        ('6. 汇总分组计时', '分别显示12组结果，预热不计入统计。PL核心包含流停顿，DMA事务与核心重叠；本轮没有纯DMA或浏览器FPS。',
         'w4_summary = summary(w4_context)\n'),
        ('7. 安全结束与导出', '正常完成才运行。看到W4_RESULTS_READY后Ctrl+S，File → Download as → Notebook下载本Notebook；回同级目录下载c7_w4_processing_results.zip。',
         'w4_bundle = finish_export(w4_context)\n')]
    cells = [dict(cell_type='markdown', metadata={}, source=[
        '# C7 W4.1：真实PL与同板PS CPU正式处理性能\n\n',
        'BOARD_NOT_RUN。算法和既有浏览器不改；亮区/细管质量尚未最终验收。\n\n',
        '红色报错或60秒无新进度：停止，保留输出和当前内核，不重跑、不重载、不释放失败缓冲。CPU结果仅为对照，不展示为FPGA结果。\n'])]
    for title, description, code in sections:
        ast.parse(code, feature_version=(3, 10))
        cells += [dict(cell_type='markdown', metadata={}, source=[f'## {title}\n\n{description}\n']),
                  dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=code.splitlines(True))]
    return dict(cells=cells, metadata=dict(kernelspec=dict(display_name='Python 3 (ipykernel)', language='python', name='python3'),
        language_info=dict(name='python', version='3.10.4')), nbformat=4, nbformat_minor=5)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    a = p.parse_args()
    require(not a.destination.exists(), 'Use a fresh release directory; never replace earlier package')
    require(info(a.baseline/'q4d_manifest.json')['sha256'] == BASELINE_MANIFEST_SHA, 'Not trusted C7 release')
    baseline_manifest = json.loads((a.baseline/'q4d_manifest.json').read_bytes())
    for name, expected in baseline_manifest['artifacts'].items():
        require(info(a.baseline/name) == expected, 'Baseline changed: '+name)
    release = a.destination/'package'; upload = a.destination/'upload'
    release.mkdir(parents=True); upload.mkdir()
    baseline_target = release/'c7_baseline'
    for name in sorted(set(baseline_manifest['artifacts']) | {'q4d_manifest.json'}):
        target = baseline_target/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.baseline/name, target)
    shutil.copytree(ROOT/'system_bench', release/'system_bench', ignore=shutil.ignore_patterns('__pycache__'))
    reference = release/'bench_reference'; reference.mkdir()
    (reference/'__init__.py').write_text('"""Frozen benchmark-only reference, never production inference."""\n')
    for name in ('q4d_features.py','q4d_forest.py','reference.py'):
        shutil.copy2(ROOT/'software'/name, reference/name)
    shutil.copy2(ROOT/'software/models/c7_d6_r1.json', reference/'c7_d6_r1.json')
    require(info(reference/'c7_d6_r1.json')['sha256'] == '6f3d83ac760c91988f5edd27f45b6f69cc7c610ff13500d77161cfcc525f44a6', 'Model changed')
    manifest = dict(revision=REVISION, board_status='BOARD_NOT_RUN',
        baseline_board_archive_sha256='bac5c69893f2e749cb4414b72551c948f0f2ea77efd4c1835e124abb93fe7bf0',
        protocol=dict(sizes=[256,512], repeats=3,warmup=3,samples=100,image_id='im0001',algorithm='C7',mode_code=3,threshold=112),
        artifacts={p.relative_to(release).as_posix():info(p) for p in sorted(release.rglob('*')) if p.is_file()})
    write_json(release/'w4_manifest.json', manifest)
    archive = upload/'c7_w4_processing_r1.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(release.rglob('*')):
            if path.is_file(): z.write(path,path.relative_to(release))
    write_json(upload/'c7_w4_processing.ipynb', notebook(info(archive)['sha256']))
    write_json(a.destination/'release.json', dict(status='HOST_PACKAGE_ONLY_BOARD_NOT_RUN',
        files={p.name:info(p) for p in upload.iterdir()}, embedded_files=len(manifest['artifacts'])+1))
    print(json.dumps(dict(upload=str(upload), files=2, embedded_files=len(manifest['artifacts'])+1)))


if __name__ == '__main__': main()
