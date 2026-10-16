"""Package a new application around the exact, already verified A4 release."""
import ast
import json
import platform
import shutil
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
import PIL
import tornado

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pynq_app.protocol import MODES, REVISION, file_info, require, sha, write_json
from software.preprocessing import pack_input, prepare_sample, read_archive

BASE = ROOT / 'build/deploy/a4_segmentation_2017_4_r1'
OUT = ROOT / 'build/deploy/browser_a4_w1_r1'


def startup_notebook(bundle_sha):
    cells = []
    def markdown(text):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(True)})
    def code(text):
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': text.splitlines(True), 'execution_count': None, 'outputs': []})
    markdown('''# W1 浏览器真实 FPGA 闭环\n使用原 A4 的 bit/HWH；无 HDMI。上传本 Notebook 和 `browser_a4_w1_r1.zip` 到一个新建文件夹。\n每个代码框只执行一次，按顺序等待 In[数字] 且无红色报错。不要 Run All。\n本阶段阈值固定28，可切换两张图/256或512/四个真实PL模式。主机通过不是新板测通过。''')
    markdown('## 1. 验证下载包并展开\n应打印 PACKAGE_BYTES_PASS。只读验证通过后写入新的子文件夹；尚未访问 FPGA。')
    code('''from pathlib import Path
import hashlib, json, zipfile
if 'browser_package_root' in globals():
    raise RuntimeError('Already extracted; continue to the next cell')
bundle_path = Path('browser_a4_w1_r1.zip')
expected_bundle_sha256 = 'BUNDLE_SHA'
if hashlib.sha256(bundle_path.read_bytes()).hexdigest() != expected_bundle_sha256:
    raise ValueError('Wrong download bytes; stop before importing or loading FPGA')
with zipfile.ZipFile(bundle_path) as archive:
    members = archive.infolist()
    names = [member.filename for member in members]
    manifest = json.loads(archive.read('browser_manifest.json'))
    if len(names) != len(set(names)) or set(names) != set(manifest['artifacts']) | {'browser_manifest.json'}:
        raise ValueError('Unexpected archive inventory')
    if len(members) > 100 or sum(member.file_size for member in members) > 128 * 1024 * 1024:
        raise ValueError('Unexpected package size')
    for member in members:
        path = Path(member.filename)
        if path.is_absolute() or '..' in path.parts or '\\\\' in member.filename or ':' in member.filename or member.is_dir():
            raise ValueError('Unsafe package member')
        if member.filename != 'browser_manifest.json':
            data = archive.read(member)
            if {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} != manifest['artifacts'][member.filename]:
                raise ValueError('Package mismatch: ' + member.filename)
    browser_package_root = (Path.cwd() / 'browser_a4_w1_r1').resolve()
    browser_package_root.mkdir(exist_ok=False)
    for member in members:
        destination = browser_package_root / member.filename
        if browser_package_root not in destination.resolve().parents:
            raise ValueError('Package path escaped directory')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(member))
print('PACKAGE_BYTES_PASS: original A4 and browser application bytes checked; FPGA untouched')
'''.replace('BUNDLE_SHA', bundle_sha))
    markdown('## 2. 检查环境并保留端口\n应打印 BROWSER_PRECHECK_PASS 和实际版本。此步不加载FPGA。8090若被占用，保留报错，勿继续。')
    code('''import sys
if 'browser_context' in globals():
    raise RuntimeError('Already prepared; continue to the next cell')
sys.path.insert(0, str(browser_package_root))
from pynq_app.launch import prepare, start, export_session, finish
browser_context = prepare(browser_package_root, port=8090)
''')
    markdown('## 3. 加载一次并启动服务\n应打印 BROWSER_SERVICE_READY。尚未进行图像收发。出现红色报错则保留内核和上下文，不重复加载。')
    code('''browser_start_status = await start(browser_context)
print(browser_start_status)
''')
    markdown('''## 4. 在 Windows 浏览器操作\n打开上一框打印的 http://板卡IP:8090/。若IP仍为192.168.2.99，地址为 http://192.168.2.99:8090/ 。\n依次：im0001 /512/模式3运行；im0002 /512/模式3运行；im0002 /512/模式1运行；im0001 /256/模式3运行。\n每次等待同帧四图出现、任务ID更新及收发字节/帧计数增加。运行旁路时只有原图是正常的。\n然后选 im0001 /512/模式3，点击“连续运行20帧”，完成后截图界面。只在前台可见时取得连续展示FPS。\n阈值不能调是W1真实能力限制；透明度只改变叠加显示，不增加PL任务。\n此时可在网页“导出当前任务/本次会话”。不要关闭此Notebook、重启内核或运行其他Overlay。\n网页停止后续请求不会取消已经发送的DMA；等待板端IDLE后再执行下框。''')
    code('''print(browser_context['manager'].status())
''')
    markdown('## 5. 打包本次真实记录\n须无在途/待执行任务。应打印 BROWSER_RECORDS_READY。完整会话包含每任务原packed NPY、PNG、JSON、CSV及浏览器绘制观测；尚待项目独立复核，不自动宣称验收通过。')
    code('''import shutil
browser_export_path = await export_session(browser_context)
shutil.copyfile(browser_export_path, Path.cwd() / 'browser_session_bundle.zip')
print('DOWNLOAD: browser_session_bundle.zip in this notebook folder')
''')
    markdown('## 6. 安全结束并下载\n仅READY/IDLE且无在途或故障缓冲时关闭HTTP服务。FAULT时本框拒绝关闭，保留内核和原记录并反馈。\n完成后Ctrl+S；File → Download as → Notebook下载执行记录。回文件列表下载 `browser_session_bundle.zip`。反馈这两个文件和浏览器截图。')
    code('''await finish(browser_context)
''')
    for cell in cells:
        if cell['cell_type'] == 'code':
            ast.parse(''.join(cell['source']), feature_version=(3, 10))
    return {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3 (ipykernel)', 'language': 'python', 'name': 'python3'},
            'language_info': {'name': 'python', 'version': '3.10.4'}}, 'nbformat': 4, 'nbformat_minor': 4}


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    baseline_files = sorted(path for path in BASE.iterdir() if path.is_file())
    require(len(baseline_files) == 12, 'Expected the original 12-file A4 package')
    original = {path.name: file_info(path) for path in baseline_files}
    for path in baseline_files:
        shutil.copyfile(path, OUT / path.name)
    for folder, suffixes in (('pynq_app', {'.py'}), ('ui', {'.html', '.css', '.js'})):
        (OUT / folder).mkdir(exist_ok=True)
        for path in sorted((ROOT / folder).iterdir()):
            if path.is_file() and path.suffix in suffixes:
                shutil.copyfile(path, OUT / folder / path.name)
    raw = ROOT / 'data/raw/stare'
    images = read_archive(raw / 'stare-images.tar', '')
    ah, vk = read_archive(raw / 'labels-ah.tar', '.ah'), read_archive(raw / 'labels-vk.tar', '.vk')
    (OUT / 'inputs').mkdir(exist_ok=True)
    (OUT / 'evaluation_only').mkdir(exist_ok=True)
    catalog = {}
    for sample in ('im0001', 'im0002'):
        catalog[sample] = {}
        for side in (256, 512):
            labels = {}
            for name, source in (('AH', ah), ('VK', vk)):
                pixels = source[sample]['pixels']
                labels[name] = pixels > 0 if pixels.ndim == 2 else np.any(pixels > 0, axis=2)
            rgb, aligned, geometry = prepare_sample(images[sample]['pixels'], labels, side)
            words = pack_input(rgb, aligned['fov'])
            # Explicitly prove labels do not affect the RGB/FOV algorithm input.
            rgb_without_gt, fov_without_gt, _ = prepare_sample(images[sample]['pixels'], {}, side)
            require(np.array_equal(words, pack_input(rgb_without_gt, fov_without_gt['fov'])), 'GT entered input preparation')
            if sample == 'im0001':
                require(np.array_equal(words, np.load(BASE / ('stare_im0001_' + str(side) + '.npy'), allow_pickle=False)), 'Original tested STARE geometry changed')
            input_name = 'inputs/' + sample + '_' + str(side) + '.npy'
            np.save(OUT / input_name, words, allow_pickle=False)
            scores = {}
            for name in ('AH', 'VK'):
                label_name = 'evaluation_only/' + sample + '_' + str(side) + '_' + name + '.npy'
                np.save(OUT / label_name, aligned[name], allow_pickle=False)
                scores[name] = {'path': label_name, 'file': file_info(OUT / label_name), 'role': 'Evaluation after actual PL completion only',
                                'source_member': (ah if name == 'AH' else vk)[sample]['member_sha256']}
            catalog[sample][str(side)] = {'input': input_name, 'input_file': file_info(OUT / input_name),
                'input_word_sha256': sha(words.tobytes()), 'geometry': geometry, 'evaluation_only': scores,
                'rgb_source_member': images[sample]['member_sha256'], 'rgb_sha256': sha(rgb.tobytes())}
    names = set(original)
    for folder in ('pynq_app', 'ui'):
        names.update(folder + '/' + path.name for path in (ROOT / folder).iterdir()
                     if path.is_file() and path.suffix in ('.py', '.html', '.css', '.js'))
    for sides in catalog.values():
        for entry in sides.values():
            names.add(entry['input'])
            names.update(spec['path'] for spec in entry['evaluation_only'].values())
    artifacts = {name: file_info(OUT / name) for name in sorted(names)}
    manifest = {'revision': REVISION, 'board_status': 'NOT_RUN', 'phase': 'W1_FIXED28_PENDING_NEW_BOARD_TEST',
        'baseline_manifest': file_info(BASE / 'a4_manifest.json'), 'baseline_original_files': original,
        'artifacts': artifacts, 'images': catalog, 'modes': MODES, 'threshold': 28,
        'data_scope': 'Two STARE images for W1 bring-up. AH/VK are not PL inputs; not the formal 20-image train/heldout experiment.',
        'host_preparation_runtime': {'python': platform.python_version(), 'numpy': np.__version__, 'Pillow': PIL.__version__, 'OpenCV': cv2.__version__, 'tornado': tornado.version},
        'board_dependencies': 'Existing measured PYNQ3.0.1 Python3.10, NumPy, Pillow, Tornado>=6.1. Check installed runtime; no automatic pip installs.',
        'provenance': {str(path.relative_to(ROOT)).replace('\\', '/'): file_info(path) for path in
            (raw / 'stare-images.tar', raw / 'labels-ah.tar', raw / 'labels-vk.tar', raw / 'download_manifest.json',
             ROOT / 'software/preprocessing.py', ROOT / 'references/PYNQ/v3.0.1/pynq/lib/dma.py',
             ROOT / 'references/PYNQ/v3.0.1/pynq/lib/axigpio.py', ROOT / 'references/PYNQ/v3.0.1/pynq/buffer.py')}}
    write_json(OUT / 'browser_manifest.json', manifest)
    archive_path = OUT.parent / 'browser_a4_w1_r1.zip'
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(artifacts) | {'browser_manifest.json'}):
            archive.write(OUT / name, name)
    notebook = startup_notebook(file_info(archive_path)['sha256'])
    write_json(ROOT / 'notebooks/browser_start.ipynb', notebook)
    shutil.copyfile(ROOT / 'notebooks/browser_start.ipynb', OUT.parent / 'browser_start.ipynb')
    for name, info in original.items():
        require(file_info(BASE / name) == file_info(OUT / name) == info, 'Original A4 bytes changed')
    return {'application_directory': str(OUT), 'upload_bundle': str(archive_path), 'upload_notebook': str(OUT.parent / 'browser_start.ipynb'),
            'zip': file_info(archive_path), 'notebook': file_info(OUT.parent / 'browser_start.ipynb'),
            'original_12_files_byte_identical': True, 'board_status': 'NOT_RUN', 'artifact_count': len(artifacts)}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
