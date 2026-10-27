"""Seal an already built offline-verified release and a manual launch Notebook.

ZIP hash is embedded only in the external Notebook. Final receipt and SHA stay
outside the ZIP, so there is no self-hash cycle or active console in the seal.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def package(root,destination,revision='r1'):
    assert revision in ('r1','r2'), 'Unknown manual package revision'
    package_name='C7_Web_SingleImage_'+revision
    root=Path(root).resolve();dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=False)
    archive=dest/(package_name+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(root).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        m=json.loads(z.read('browser_manifest.json'))
        assert set(z.namelist())==set(m['artifacts'])|{'browser_manifest.json'}
        for name,ref in m['artifacts'].items():
            data=z.read(name);assert len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256']
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    cells=[]
    def md(s):cells.append(dict(cell_type='markdown',metadata={},source=s.splitlines(True)))
    def code(s):cells.append(dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=s.splitlines(True)))
    md('''# C7 测试网页 · 单图专项优化接入

方案名称仍为 C7。im0324 / 512 / 最终模式 / T112 由原C7 PL和50MHz补标PL顺序计算；其他选择沿用原流程。
已返回的单图板测数值通过，本网页组合流程等待本次实板核验。不得把主机测试截图当作网页板测。

不要 Run All。确保旧任务已正常完成、记录已保存，旧8090服务已正常关闭，才在独立的新Notebook内核运行本页；不强行终止故障任务。保留所有旧文件和内核现场。
''')
    md('''## 1．离线解包与校验（不操作FPGA）

本Notebook与 C7_Web_SingleImage_r1.zip 放在新的 `c7_web_single_image_r1` 文件夹。
每次在 `web_sessions/run_随机编号` 建立独立记录。首次校验通过后只继续下一格，不重复运行本格。
''')
    code('''from pathlib import Path
import hashlib,json,zipfile,sys,uuid,shutil
if 'web_root' in globals() or any(n=='pynq_showcase' or n.startswith('pynq_showcase.') for n in sys.modules):
    raise RuntimeError('本内核已经准备过；保留会话，不重复开始。请使用本次专用新Notebook内核。')
web_home=Path.cwd().resolve()
web_archive=web_home/'C7_Web_SingleImage_r1.zip'
assert hashlib.sha256(web_archive.read_bytes()).hexdigest() == '__ZIP_SHA__', 'ZIP_SHA_MISMATCH'
assert shutil.disk_usage(web_home).free >= 1024**3, 'SD空间不足1GiB；不删除旧记录'
web_root=web_home/'web_sessions'/('run_'+uuid.uuid4().hex)
web_root.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(web_archive) as bundle:
    names=bundle.namelist()
    manifest=json.loads(bundle.read('browser_manifest.json'))
    assert len(names)==len(set(names)) and set(names)==set(manifest['artifacts'])|{'browser_manifest.json'}
    for name in names:
        part=Path(name)
        assert not part.is_absolute() and '..' not in part.parts and ':' not in name and chr(92) not in name
        target=(web_root/name).resolve()
        assert web_root.resolve() in target.parents
        data=bundle.read(name)
        if name!='browser_manifest.json':
            ref=manifest['artifacts'][name]
            assert len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256'], name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(data)
sys.path.insert(0,str(web_root))
from pynq_showcase.protocol import validate_package
validate_package(web_root)
print('C7_WEB_OFFLINE_PACKAGE_VERIFIED',web_root)
'''.replace('__ZIP_SHA__',digest))
    md('''## 2．人工确认后启动网页服务（只执行一次）

确认旧工作已完成并封存、板卡空闲、8090旧服务已正常关闭后，将下面 `AUTHORIZED=False` 改为 `True`。
本格加载原C7并启动网页，不发送图像；专项overlay只在网页目标图请求时加载。若端口占用或任何错误，停止并保存提示，不重复执行、不强制关闭其他进程。
''')
    code('''AUTHORIZED=False
assert AUTHORIZED, '请先确认本次操作和旧会话安全状态'
assert 'web_context' not in globals(), '本次启动已经尝试过；保留现场，不重试'
from pynq_showcase import launch
web_context=launch.prepare(web_root,port=8090)
with (web_root/'WEB_START_ONCE.json').open('x',encoding='utf8') as f:
    json.dump({'authorization':'MANUAL_C7_WEB_SINGLE_IMAGE_START_ONCE','package_sha256':'__ZIP_SHA__'},f)
print(await launch.start(web_context))
'''.replace('__ZIP_SHA__',digest))
    md('''## 3．在浏览器运行和查看

打开上一格打印的 `http://板卡IP:8090/`。保持本Notebook内核运行。
选择 `im0324`、`512 × 512`、`C7`、最终掩膜、阈值112；点击一次 **运行 FPGA**。
完成后显示 **此图已专项优化**，最终绿色叠加是新结果。页面只展示原始眼底、FPGA增强、血管候选和血管叠加四张图。
已验证的单独补标实测约29.37秒；网页还包括原C7、overlay切换、记录和PNG传输，不能拿主机测试的毫秒数作板端时延。
不连续点击、不刷新重发。若断连、报错或长时间未完成，保留Notebook/缓冲/日志，不重启、不自动重跑。

完成后先点网页 **导出当前任务** 下载ZIP供独立核验。需要检验后续切回C7时，可在本次成功后再明确点击另一张图；切换只发生在新请求开始，失败时不会自动恢复或回放。
''')
    md('''## 4．导出会话（当前帧已完成或已明确失败后）

下格只打包现有记录，不运行图像。若硬件仍在运行则拒绝导出；不通过重启绕过。
''')
    code('''from IPython.display import FileLink,display
archive_path=Path(await launch.export_session(web_context))
display(FileLink(str(archive_path.relative_to(Path.cwd()))))
''')
    md('''## 5．正常结束服务（全部完成且无故障时）

只在无需继续展示时执行。故障状态不允许用此格清场，保留原内核和缓冲。
以后需要演示时，在旧服务正常结束、导出保存后，使用新Notebook内核从第1格开始；旧目录不删除。
''')
    code('''await launch.finish(web_context)
print('C7_WEB_CLOSED_IDLE_RECORDS_PRESERVED')
''')
    nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3 (ipykernel)',language='python',name='python3'),language_info=dict(name='python',version='3.10')),nbformat=4,nbformat_minor=5)
    for cell in cells:
        cell['source']=[line.replace('C7_Web_SingleImage_r1',package_name).replace('c7_web_single_image_r1','c7_web_single_image_'+revision) for line in cell['source']]
    notebook=dest/(package_name+'.ipynb');notebook.write_text(json.dumps(nb,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (dest/(package_name+'.zip.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    receipt=dict(status='OFFLINE_WEB_INTEGRATION_READY_FOR_MANUAL_DEPLOYMENT',WEB_BOARD_STATUS='NOT_RUN',zip=dict(path=str(archive),bytes=archive.stat().st_size,sha256=digest),notebook=dict(path=str(notebook),sha256=hashlib.sha256(notebook.read_bytes()).hexdigest()))
    (dest/'release_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--revision',default='r1',choices=['r1','r2'])
    a=p.parse_args();package(a.root,a.output,a.revision)
