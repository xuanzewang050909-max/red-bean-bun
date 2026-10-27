"""Offline assembly only. Copies the sealed 181-member r4 release unchanged."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

BASE = Path('D:/PLD/review_packages/C7_Web_FourImage_r4_release/C7_Web_FourImage_r4.zip')
BASE_SHA = '9b6040142a0333792cf58f273a92629bd59c64aea83a6abe145d4bf8b33e03f7'
HERE = Path(__file__).resolve().parent


def identity(path):
    data = path.read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def package(output):
    assert identity(BASE)['sha256'] == BASE_SHA, 'SEALED_R4_CHANGED'
    output.mkdir(parents=True, exist_ok=False)
    payload = output/'payload'
    payload.mkdir()
    with zipfile.ZipFile(BASE) as archive:
        manifest = json.loads(archive.read('browser_manifest.json'))
        names = archive.namelist()
        assert len(names) == len(set(names)) == 181
        assert set(names) == set(manifest['artifacts']) | {'browser_manifest.json'}
        for name in names:
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            data = archive.read(name)
            if name != 'browser_manifest.json':
                assert dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) == manifest['artifacts'][name]
            target = payload/'app'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    for name in ('c7_demo.py', '展示操作.md'):
        shutil.copyfile(HERE/name, payload/name)
    files = {p.relative_to(payload).as_posix(): identity(p)
             for p in sorted(payload.rglob('*')) if p.is_file()}
    dm = dict(schema='c7-repeatable-demo-v1', original_release=dict(path=str(BASE), **identity(BASE)),
              scope='Lifecycle only; all 180 original artifacts and their manifest unchanged',
              hardware_access='Only explicit manual Notebook start and web FPGA requests',
              board_status='NOT_RUN_THIS_WRAPPER', files=files)
    dump(payload/'demo_manifest.json', dm)
    archive_path = output/'C7_Demo_r1.zip'
    with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(payload.rglob('*')):
            if p.is_file(): archive.write(p, p.relative_to(payload).as_posix())
    digest = identity(archive_path)['sha256']
    cells = []
    def md(text): cells.append(dict(cell_type='markdown', metadata={}, source=text.splitlines(True)))
    def code(text):
        compile(text, '<notebook>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        cells.append(dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=text.splitlines(True)))
    md('''# C7 可重复启动展示版

只上传本Notebook与同名ZIP一次。之后每次开机执行第1、2格；正常结束后，同一内核可再次执行第2格。**不要 Run All。**

名称仍为C7；四张专项图先原版后改进版，四个展示面板，没有nogt列表项。本版不改变算法，不加速原PL计算。首次启动前确认旧任务安全结束并保留记录；故障任务不能强行清场。
''')
    md('''## 1．离线安装/校验（每次开机执行，可重复）

不访问板卡。已安装则核对原文件，不覆盖，不删记录。
''')
    code('''from pathlib import Path
import hashlib,json,zipfile,sys,uuid,shutil
home=Path.cwd().resolve()
archive=home/'C7_Demo_r1.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='__SHA__', 'DEMO_ZIP_SHA_MISMATCH'
runtime=home/'demo_runtime'
with zipfile.ZipFile(archive) as bundle:
    names=bundle.namelist()
    manifest=json.loads(bundle.read('demo_manifest.json'))
    assert len(names)==len(set(names)) and set(names)==set(manifest['files'])|{'demo_manifest.json'}
    for name in names:
        p=Path(name)
        assert not p.is_absolute() and '..' not in p.parts and ':' not in name and chr(92) not in name
        data=bundle.read(name)
        if name!='demo_manifest.json':
            ref=manifest['files'][name]
            assert len(data)==ref['bytes'] and hashlib.sha256(data).hexdigest()==ref['sha256'], name
    if not runtime.exists():
        assert shutil.disk_usage(home).free>=1024**3, 'SD_FREE_SPACE_BELOW_1_GIB'
        stage=home/('demo_install_'+uuid.uuid4().hex)
        stage.mkdir()
        for name in names:
            target=stage/name
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(bundle.read(name))
        stage.rename(runtime)
    for name in names:
        assert (runtime/name).read_bytes()==bundle.read(name), 'EXISTING_INSTALL_CHANGED: '+name
loaded=sys.modules.get('c7_demo')
assert loaded is None or Path(loaded.__file__).resolve()==runtime/'c7_demo.py', 'DIFFERENT_DEMO_IN_KERNEL'
if str(runtime) not in sys.path:sys.path.insert(0,str(runtime))
import c7_demo
demo=c7_demo.open_demo(runtime)
print('C7_DEMO_OFFLINE_VERIFIED',runtime)
print('下一格经人工确认才启动板卡展示；未执行模型或FPGA操作。')
'''.replace('__SHA__',digest))
    md('''## 2．启动展示（人工确认板卡空闲）

把 AUTHORIZED 改为 True 后执行。正常运行时重复点这格只返回已有地址，不重复加载；正常结束后执行这格会新建会话。若发生异常，保留本内核与记录，不自动重试。端口占用时不强制结束其他程序。
''')
    code('''AUTHORIZED=False
assert AUTHORIZED, '请先确认旧任务正常结束、记录已保存、板卡空闲'
state=await demo.start(c7_demo.CONFIRMATION,port=8090)
print(state)
for url in state['urls']:print('打开展示网页：',url)
''')
    md('''## 网页操作

打开上格打印的8090网页。选择 **im0004 / im0291 / im0319 / im0324**，配置 **C7、512×512、最终掩膜、112**。

1. 点 **① 运行原版 C7**，等待四图显示原版。
2. 点 **② 运行改进版 FPGA**，等待专项补标完成。
3. 使用 **查看原版 / 查看改进版** 对比；切换已完成版本不触发计算。切换另一张图后重复1、2。

保持Notebook内核与网页开启；不要在运行中重启内核或断电。下面第3格是**展示结束才执行**，不要刚启动就执行。
''')
    md('''## 3．保存记录并正常结束（展示完才执行）

导出完成后正常关闭网页服务，保留所有记录。不复位板卡。忙碌或故障会拒绝关闭。正常结束后可再次执行第2格开始新一轮；下次开机只需执行第1、2格。
''')
    code('''from IPython.display import display,FileLink
saved=Path(await demo.finish())
print('C7_DEMO_CLOSED_IDLE；下次可再次启动。记录：',saved)
display(FileLink(str(saved.relative_to(Path.cwd()))))
''')
    md('''## 4．可选：只导出，不关闭服务

平时不用执行。只有当前调用已经结束/返回异常后才可导出；仍在运行则会拒绝。不重启内核，不重跑故障请求。
''')
    code('''from IPython.display import display,FileLink
saved=Path(await demo.export())
display(FileLink(str(saved.relative_to(Path.cwd()))))
''')
    nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3 (ipykernel)',language='python',name='python3'),
             language_info=dict(name='python',version='3.10')),nbformat=4,nbformat_minor=5)
    dump(output/'C7_Demo_r1.ipynb', nb)
    shutil.copyfile(HERE/'展示操作.md',output/'展示操作.md')
    (output/'C7_Demo_r1.zip.sha256').write_text(digest+'  C7_Demo_r1.zip\n',encoding='ascii')
    dump(output/'assembly_receipt.json', dict(status='PACKAGED_PENDING_HOST_TESTS',
        zip=identity(archive_path),notebook=identity(output/'C7_Demo_r1.ipynb'),
        immutable_original_files=181, original_release=dm['original_release']))
    print(json.dumps(dict(output=str(output),zip_sha256=digest,files=len(files)+1)))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    package(parser.parse_args().output)
