"""W3 derives the tested W1 transport/UI and reuses the verified W2 hardware.

No medical reference or golden result is shipped to the runtime application.
"""
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pynq_w3.protocol import REVISION, MODES, file_info, require, validate_package, write_json
from package_browser_w1 import startup_notebook as original_startup

BASE = ROOT / 'build/deploy/w2_quality_2017_4_r1'
W1 = ROOT / 'build/deploy/browser_a4_w1_r1'
OUT = ROOT / 'build/deploy/browser_w3_c2_r1'
UPLOAD = ROOT / 'build/deploy/browser_w3_upload_r1'


def startup_notebook(digest):
    nb = original_startup(digest)
    for cell in nb['cells']:
        text = ''.join(cell['source']).replace('browser_a4_w1_r1', 'browser_w3_c2_r1').replace('pynq_app', 'pynq_w3')
        text = text.replace('original A4', 'paired W2').replace('browser_session_bundle.zip', 'browser_w3_session_bundle.zip')
        cell['source'] = text.splitlines(True)
    nb['cells'][0]['source'] = ['# W3 · C2 与真实参数浏览器验证\n',
        '复用已板测 W2 bit/HWH、原 DMA/DDR 和 W1 网络服务。无 HDMI。\n',
        '上传本 Notebook 和 browser_w3_c2_r1.zip 到新 retina_browser_w3_r1 文件夹。\n',
        '只在上一步结束且无报错后运行下一框；不要 Run All。FAULT 时保留内核和缓冲，不重复加载。\n']
    for cell in nb['cells']:
        if cell['cell_type'] == 'markdown' and ''.join(cell['source']).startswith('## 4.'):
            cell['source'] = ['''## 4. 在 Windows 浏览器运行新任务
打开 http://192.168.2.99:8090/ ，若板卡 IP 变化使用第3框地址。每次等待任务完成且硬件实际参数与选择一致，再执行下一行。

|次序|图像|尺寸|算法|阈值|PL处理模式|
|---|---|---|---|---|---|
|1|im0001|512|A|28|最终掩膜 3|
|2|im0001|512|C2|28|最终掩膜 3|
|3|im0001|512|C2|40|最终掩膜 3|
|4|im0001|512|A|28|最终掩膜 3|
|5|im0002|512|C2|28|最终掩膜 3|
|6|im0001|256|C2|28|最终掩膜 3|
|7|im0001|256|C2|28|初始阈值候选 1|
|8|im0001|256|C2|28|输入旁路 0|

旁路只有原图，没有分割分数。选择改变后旧图变暗，点击“运行 FPGA”才发送真实新任务。
再选 im0001 /512/C2/28/最终掩膜，点击“连续运行20帧”，保持网页在前台，完成后截图。
PL核心窗口来自硬件周期且含流式等待；DMA事务含PL重叠；完整推理含配置、分配、DMA和CPU快照；浏览器延迟来自客户端单调时钟。纯搬运仍待独立实验。
本次28帧是交互集成验证，不是正式性能/完整数据集质量或稳定性验收。完成后返回Notebook运行下面状态框，应为IDLE、完成至少28帧，无故障/保留缓冲。
''']
    return nb


def build():
    verified = json.loads((ROOT / 'results/w2_quality_2017_4/board_execution_2026-10-14/verification.json').read_bytes())
    require(verified['status'] == 'PASS_DOWNLOADED_W2_EXACT_WORDS_AND_OBSERVERS' and verified['frames'] == 80, 'W2 real-board gate missing')
    OUT.mkdir(parents=True, exist_ok=True)
    original = json.loads((W1 / 'browser_manifest.json').read_bytes())
    baseline = json.loads((BASE / 'w2_manifest.json').read_bytes())
    names = {'w2_quality.bit', 'w2_quality.hwh', 'w2_manifest.json', 'a0_dma_board_test.py'}
    for name in names:
        shutil.copyfile(BASE / name, OUT / name)
    for source, dest in (('pynq_w3', 'pynq_w3'), ('ui_w3', 'ui')):
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
    manifest = dict(revision=REVISION, board_status='NOT_RUN', phase='W3_BROWSER_INTEGRATION_PENDING_REAL_BOARD',
        baseline_manifest=file_info(BASE / 'w2_manifest.json'), images=original['images'], modes=MODES,
        algorithms=['A', 'C2'], threshold_range=[1, 255], candidate=baseline['candidate'],
        artifacts={name: file_info(OUT / name) for name in sorted(names)},
        provenance={'W2_board_verification': file_info(ROOT / 'results/w2_quality_2017_4/board_execution_2026-10-14/verification.json'),
                    'W1_manifest': file_info(W1 / 'browser_manifest.json')},
        scope='28 requested real tasks, two existing images; formal Q3 quality/W4 performance/W5 stability pending. No golden/reference arrays shipped.',
        ps_role='Read input/DDR/DMA/control; snapshot actual PL; unpack/score/display/export. No PS vessel computation.',
        hardware=baseline['hardware'])
    write_json(OUT / 'browser_manifest.json', manifest)
    validate_package(OUT)
    require(len(names) == 26, 'Unexpected W3 inventory')
    UPLOAD.mkdir(parents=True, exist_ok=True)
    archive = UPLOAD / 'browser_w3_c2_r1.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names | {'browser_manifest.json'}):
            z.write(OUT / name, name)
    nb = startup_notebook(file_info(archive)['sha256'])
    write_json(UPLOAD / 'browser_w3_start.ipynb', nb)
    write_json(ROOT / 'notebooks/browser_w3_start.ipynb', nb)
    return {'artifacts': len(names), 'zip_members': len(names) + 1, 'board_status': 'NOT_RUN',
            'upload': {p.name: file_info(p) for p in sorted(UPLOAD.iterdir()) if p.is_file()}}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
