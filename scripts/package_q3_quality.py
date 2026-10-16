"""Package the frozen 80-frame quality cohort using unchanged W4a runtime."""
import ast
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from pynq_w4a.protocol import file_info, sha, require, validate_package, write_json
from software.preprocessing import read_archive, prepare_sample, pack_input
from package_browser_w4a import startup_notebook as prior_notebook
from q3_board import validate_q3

BASE = ROOT / 'build/deploy/browser_w4a_png_r1'
OUT = ROOT / 'build/deploy/q3_full_quality_r1'
UPLOAD = ROOT / 'build/deploy/q3_quality_upload_r1'
PROTOCOL = ROOT / 'docs/q3_full_quality_protocol_r1.json'


def startup_notebook(digest):
    nb = prior_notebook(digest)
    cells = nb['cells']
    for c in cells:
        text = ''.join(c['source']).replace('browser_w4a_png_r1', 'q3_full_quality_r1')
        if c['cell_type'] == 'code' and 'bundle_path =' in text:
            text = text.replace("archive.read('browser_manifest.json')", "archive.read('q3_manifest.json')")
            text = text.replace("{'browser_manifest.json'}", "{'q3_manifest.json'}")
            text = text.replace("!= 'browser_manifest.json'", "!= 'q3_manifest.json'").replace('> 100', '> 200')
        if c['cell_type'] == 'code' and 'from pynq_w4a.launch' in text:
            text = text.replace('from pynq_w4a.launch import prepare, start, export_session, finish',
                'from q3_board import prepare_q3, start, collect_q3, export_q3, finish')
            text = text.replace('= prepare(', '= prepare_q3(')
        if c['cell_type'] == 'code' and 'browser_export_path =' in text:
            text = "q3_export_info = await export_q3(browser_context, Path.cwd() / 'q3_results_bundle.zip')\n"
        c['source'] = text.splitlines(True)
    cells[0]['source'] = ['# Q3 · 全20图真实FPGA质量验证\n',
        '复用已测W2固件与W4a服务，无HDMI。固定A/C2、阈值28；20图×256/512×A/C2共80帧。\n',
        '运行过程中不要在其他网页提交FPGA任务；每框结束且无报错后再继续，不要Run All。\n']
    for c in cells:
        if c['cell_type'] != 'markdown': continue
        t = ''.join(c['source'])
        if t.startswith('## 4.'):
            c['source'] = ['## 5. 浏览器查看两张图并核对状态\n',
                '第4框完成后，打开 http://192.168.2.99:8090/ 并Ctrl+F5，页眉应为Q3。\n',
                '固定512/C2/阈值28/最终掩膜/快速无损PNG：选im0002运行并截图，再选im0324运行并截图。\n',
                '两次都是新PL任务；不要运行20帧循环。两图完成后回来运行下面状态框，应completed=82、READY/IDLE、pending=0、无error/保留缓冲。\n',
                '这些预览不进入前80帧固定质量队列。单张图的Dice不等于完整留出集质量。\n']
        elif t.startswith('## 5.'):
            c['source'] = ['## 6. 导出完整记录\n',
                '应出现Q3_RESULTS_READY。下载本Notebook同目录的q3_results_bundle.zip。不要用网页导出的普通会话包替代，它不包含Q3固定队列记录。\n']
        elif t.startswith('## 6.'):
            c['source'] = ['## 7. 安全结束并下载\n',
                '应出现BROWSER_SERVICE_CLOSED_IDLE。Ctrl+S，然后File → Download as → Notebook下载q3_quality_start.ipynb。\n',
                '同时下载q3_results_bundle.zip。若FAULT/红色报错或一分钟无新进展，保留输出与内核，不重复运行/重新加载/释放缓冲。\n']
    index = next(i for i,c in enumerate(cells) if c['cell_type']=='markdown' and ''.join(c['source']).startswith('## 5.'))
    cells[index:index] = [
        {'cell_type':'markdown','metadata':{},'source':['## 4. 自动收集80帧\n','自动遍历全部20图/两尺寸/A和C2。每完成一帧打印Q3_FRAME_SAVED，最后Q3_COLLECTION_COMPLETE。\n','期间不要点击应用网页；不用守在这一框逐帧按键。完成表示记录齐全，医学质量和全字匹配须下载后独立复核。\n']},
        {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[], 'source':['q3_collection = await collect_q3(browser_context)\n','print(q3_collection)\n']}]
    for c in cells:
        if c['cell_type']=='code': ast.parse(''.join(c['source']),feature_version=(3,10))
    return nb


def build():
    require(not OUT.exists() and not UPLOAD.exists(), 'Preserve earlier package; use a new revision')
    protocol = json.loads(PROTOCOL.read_bytes())
    # Protocol is committed before Q3 label preparation/scoring. Never select on heldout/VK.
    committed = subprocess.check_output(['git','show','69aaa7e:docs/q3_full_quality_protocol_r1.json'],cwd=ROOT)
    require(committed == PROTOCOL.read_bytes(), 'Prerecorded Q3 protocol changed')
    for name, info in protocol['frozen_files'].items(): require(file_info(ROOT/name)==info,'Frozen file changed: '+name)
    verification = json.loads((ROOT/'results/browser_w4a_2026-10-14/board_execution_2026-10-14/verification.json').read_bytes())
    require(verification['status']=='W4a_DOWNLOADED_ARRAYS_AND_OBSERVATIONS_VERIFIED_NOT_FINAL_ACCEPTANCE','Real W4a prerequisite missing')
    prior = validate_package(BASE)
    OUT.mkdir(parents=True)
    names = {n for n in prior['artifacts'] if not n.startswith(('inputs/','labels/'))}
    # Select fixed infrastructure explicitly, not old two-image arrays.
    names = {n for n in names if not n.endswith('.npy')}
    for name in names:
        dst=OUT/name; dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,dst)
    html=(OUT/'ui/index.html').read_text(encoding='utf-8').replace('W4a','Q3')
    html=html.replace('本轮比较两种 PS 无损图像传输设置，算法保持不变，提速待测。',
        'Q3 全20图质量验证：先在 Notebook 收集固定80帧，再在此查看。')
    html=html.replace('<option value="fast">','<option value="fast" selected>')
    (OUT/'ui/index.html').write_text(html,encoding='utf-8',newline='\n')
    raw=ROOT/'data/raw/stare'
    images=read_archive(raw/'stare-images.tar','')
    labels={key:read_archive(raw/('labels-'+key.lower()+'.tar'),'.'+key.lower()) for key in ('AH','VK')}
    ids=sorted(protocol['split']['train']+protocol['split']['heldout'])
    require(sorted(images)==ids and all(sorted(x)==ids for x in labels.values()),'Original 20 images/labels changed')
    catalog={}
    for image_id in ids:
        catalog[image_id]={}
        for side in (256,512):
            rgb, aligned, geometry=prepare_sample(images[image_id]['pixels'],{k:v[image_id]['pixels']!=0 for k,v in labels.items()},side)
            words=pack_input(rgb,aligned['fov']).astype('<u4')
            entry={'input':f'inputs/{image_id}_{side}.npy','geometry':geometry,'input_word_sha256':sha(words.tobytes()),'evaluation_only':{}}
            for name,array in [(entry['input'],words)]+[(f'labels/{image_id}_{side}_{key}.npy',aligned[key]) for key in ('AH','VK')]:
                dst=OUT/name;dst.parent.mkdir(exist_ok=True);np.save(dst,array,allow_pickle=False);names.add(name)
            entry['input_file']=file_info(OUT/entry['input'])
            for key in ('AH','VK'):
                name=f'labels/{image_id}_{side}_{key}.npy'
                entry['evaluation_only'][key]={'path':name,'file':file_info(OUT/name)}
            catalog[image_id][str(side)]=entry
    browser={**prior,'images':catalog,'phase':'Q3_20_IMAGE_COLLECTION_PENDING_REAL_BOARD',
             'scope':'W4a runtime reused; Q3 fixed 80 quality frames plus separate manual previews. No golden/CPU medical implementation shipped.',
             'artifacts':{n:file_info(OUT/n) for n in sorted(names)}}
    write_json(OUT/'browser_manifest.json',browser)
    shutil.copyfile(PROTOCOL,OUT/'q3_protocol.json')
    shutil.copyfile(ROOT/'scripts/q3_board.py',OUT/'q3_board.py')
    names.update({'browser_manifest.json','q3_protocol.json','q3_board.py'})
    write_json(OUT/'q3_manifest.json',{'revision':'q3_full_quality_r1','board_status':'NOT_RUN','protocol_commit':'69aaa7e',
        'artifacts':{n:file_info(OUT/n) for n in sorted(names)},'w4a_board_verification':file_info(ROOT/'results/browser_w4a_2026-10-14/board_execution_2026-10-14/verification.json')})
    validate_q3(OUT)
    UPLOAD.mkdir(parents=True)
    bundle=UPLOAD/'q3_full_quality_r1.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names|{'q3_manifest.json'}):z.write(OUT/name,name)
    nb=startup_notebook(file_info(bundle)['sha256'])
    write_json(UPLOAD/'q3_quality_start.ipynb',nb)
    write_json(ROOT/'notebooks/q3_quality_start.ipynb',nb)
    return {'board_status':'NOT_RUN','images':20,'fixed_quality_frames':80,'planned_words':13107200,'zip_members':len(names)+1,'files':{p.name:file_info(p) for p in sorted(UPLOAD.iterdir())}}


if __name__=='__main__': print(json.dumps(build(),ensure_ascii=False,indent=2))
