"""W4a derives the board-tested W3 service and compares lossless PNG delivery.

No medical reference or golden result is shipped to the runtime application.
"""
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pynq_w4a.protocol import REVISION, MODES, file_info, require, validate_package, write_json
from package_browser_w1 import startup_notebook as original_startup

BASE = ROOT / 'build/deploy/w2_quality_2017_4_r1'
W1 = ROOT / 'build/deploy/browser_a4_w1_r1'
OUT = ROOT / 'build/deploy/browser_w4a_png_r1'
UPLOAD = ROOT / 'build/deploy/browser_w4a_upload_r1'


def startup_notebook(digest):
    nb = original_startup(digest)
    for cell in nb['cells']:
        text = ''.join(cell['source']).replace('browser_a4_w1_r1', 'browser_w4a_png_r1').replace('pynq_app', 'pynq_w4a')
        text = text.replace('original A4', 'paired W2').replace('browser_session_bundle.zip', 'browser_w4a_session_bundle.zip')
        cell['source'] = text.splitlines(True)
    nb['cells'][0]['source'] = ['# W4a · 无损 PNG 对照与 PS 分段计时\n',
        '复用已板测 W3 服务及 W2 bit/HWH；只改 PS 编码设置并补分段计时。无 HDMI。\n',
        '上传本 Notebook 和 browser_w4a_png_r1.zip 到新 retina_browser_w4a_r1 文件夹。\n',
        '只在上一步结束且无报错后运行下一框；不要 Run All。FAULT 时保留内核和缓冲，不重复加载。\n']
    for cell in nb['cells']:
        if cell['cell_type'] == 'markdown' and ''.join(cell['source']).startswith('## 4.'):
            cell['source'] = ['''## 4. 浏览器对照实验
打开 http://192.168.2.99:8090/，确认页眉W4a。每次完成再继续，实际算法/阈值回读应一致。
固定 im0001 /512/阈值28/最终掩膜，依次手动运行：
1. A + 原方案；2. A + 快速候选；3. C2 + 原方案；4. C2 + 快速候选。
同算法两种传输设置的图像和Dice应一致。PNG文件字节/大小可不同，解码像素须一致。
然后固定 im0001 /512/C2/28/最终掩膜：
先选“原方案 · 默认 PNG”，点击“预热3帧+测量20帧”；完成并截图后，
再选“快速候选 · 无损 PNG”，点击同一按钮；完成并截图。
两组保持网页前台，每组3个新PL预热帧+20个计时帧，全部保存，FPS只计后20帧。
本轮共50个新PL任务，一次加载；不是正式3预热+100帧×三配置×三复测，也不是Q3全数据集实验。
比较PS解包、PIL转换、PNG编码/写入、哈希、文件大小和浏览器端到端耗时。没有预定提速结论。
返回Notebook运行状态框，应IDLE、completed至少50、pending0、无错误和保留缓冲。
''']
    return nb


def build():
    verified = json.loads((ROOT / 'results/browser_w3_2026-10-14/board_execution_2026-10-14/verification.json').read_bytes())
    require(verified['status'] == 'W3_DOWNLOADED_ARRAYS_AND_OBSERVATIONS_VERIFIED_NOT_FINAL_ACCEPTANCE' and verified['visible_20_frame_loop_verified'], 'W3 real-board gate missing')
    OUT.mkdir(parents=True, exist_ok=True)
    original = json.loads((W1 / 'browser_manifest.json').read_bytes())
    baseline = json.loads((BASE / 'w2_manifest.json').read_bytes())
    names = {'w2_quality.bit', 'w2_quality.hwh', 'w2_manifest.json', 'a0_dma_board_test.py'}
    for name in names:
        shutil.copyfile(BASE / name, OUT / name)
    for source, dest in (('pynq_w4a', 'pynq_w4a'), ('ui_w4a', 'ui')):
        (OUT / dest).mkdir(exist_ok=True)
        for path in (ROOT / source).iterdir():
            if path.is_file() and path.suffix in ('.py', '.html', '.css', '.js'):
                name = dest + '/' + path.name
                names.add(name)
                shutil.copyfile(path, OUT / name)
    for sides in original['images'].values():
        for entry in sides.values():
            for name in [entry['input']] + [s['path'] for s in entry['evaluation_only'].values()]:
                require(file_info(W1 / name) == original['artifacts'][name], 'W1 input/label changed')
                names.add(name)
                (OUT / name).parent.mkdir(exist_ok=True)
                shutil.copyfile(W1 / name, OUT / name)
    manifest = dict(revision=REVISION, board_status='NOT_RUN', phase='W4A_LOSSLESS_PNG_COMPARISON_PENDING_REAL_BOARD',
        baseline_manifest=file_info(BASE / 'w2_manifest.json'), images=original['images'], modes=MODES,
        algorithms=['A', 'C2'], threshold_range=[1, 255], png_profiles={'baseline': {}, 'fast': {'compress_level': 1}}, candidate=baseline['candidate'],
        artifacts={name: file_info(OUT / name) for name in sorted(names)},
        provenance={'W3_board_verification': file_info(ROOT / 'results/browser_w3_2026-10-14/board_execution_2026-10-14/verification.json'),
                    'W1_manifest': file_info(W1 / 'browser_manifest.json')},
        scope='50 requested real tasks, 4 gates and two (3 warmup + 20 measured) profile groups; formal Q3 quality/W4 performance/W5 stability pending. No golden/reference arrays shipped.',
        ps_role='Read input/DDR/DMA/control; snapshot actual PL; unpack/score/display/export. No PS vessel computation.',
        hardware=baseline['hardware'])
    write_json(OUT / 'browser_manifest.json', manifest)
    validate_package(OUT)
    require(len(names) == 26, 'Unexpected W4a inventory')
    UPLOAD.mkdir(parents=True, exist_ok=True)
    archive = UPLOAD / 'browser_w4a_png_r1.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names | {'browser_manifest.json'}):
            z.write(OUT / name, name)
    nb = startup_notebook(file_info(archive)['sha256'])
    write_json(UPLOAD / 'browser_w4a_start.ipynb', nb)
    write_json(ROOT / 'notebooks/browser_w4a_start.ipynb', nb)
    return {'artifacts': len(names), 'zip_members': len(names) + 1, 'board_status': 'NOT_RUN',
            'upload': {p.name: file_info(p) for p in sorted(UPLOAD.iterdir()) if p.is_file()}}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
