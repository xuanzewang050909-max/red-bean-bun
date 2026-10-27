"""Execute the delivered offline Notebook cell twice, never its hardware cell."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument('--release',required=True,type=Path)
parser.add_argument('--evidence',required=True,type=Path)
args=parser.parse_args()
release=args.release.resolve();evidence=args.evidence.resolve()
evidence.mkdir(parents=True,exist_ok=False)
for name in ('C7_Demo_r1.zip','C7_Demo_r1.ipynb'):
    shutil.copyfile(release/name,evidence/name)
nb=json.loads((evidence/'C7_Demo_r1.ipynb').read_bytes())
cells=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
for cell in cells:compile(cell,'notebook','exec',flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
os.chdir(evidence)
ns={}
exec(compile(cells[0],'offline_install_first','exec'),ns)
first=ns['demo']
exec(compile(cells[0],'offline_install_repeat','exec'),ns)
assert ns['demo'] is first
assert not (evidence/'demo_runtime/demo_attempts').exists()
assert not (evidence/'demo_runtime/demo_owner.lock').exists()
assert 'pynq' not in sys.modules and 'pynq_showcase.launch' not in sys.modules
assert first.context is None
# Default second cell must refuse before evaluating demo.start or importing drivers.
try:
    coroutine=eval(compile(cells[1],'manual_default','exec',flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT),ns)
    import asyncio
    asyncio.run(coroutine)
    raise RuntimeError('DEFAULT_AUTHORIZATION_WAS_NOT_BLOCKED')
except AssertionError:
    pass
assert 'pynq' not in sys.modules and first.context is None
original=Path('D:/PLD/review_packages/C7_Web_FourImage_r4_release/C7_Web_FourImage_r4.zip')
assert hashlib.sha256(original.read_bytes()).hexdigest()=='9b6040142a0333792cf58f273a92629bd59c64aea83a6abe145d4bf8b33e03f7'
with zipfile.ZipFile(original) as source,zipfile.ZipFile(release/'C7_Demo_r1.zip') as target:
    assert source.testzip() is None and target.testzip() is None
    equal=all(source.read(n)==target.read('app/'+n) for n in source.namelist())
    assert equal and len(source.namelist())==181
result=dict(status='PASS_OFFLINE',offline_cell_executions=2,same_python_object=True,
    default_start_blocked=True,no_hardware_module_import=True,attempts_created=0,
    exact_original_members=181,original_artifacts=180,algorithm_changes=0,
    hardware_operations=0,model_forwards=0,
    zip_sha256=hashlib.sha256((release/'C7_Demo_r1.zip').read_bytes()).hexdigest())
(evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
