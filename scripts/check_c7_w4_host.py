"""Actual host-only byte, CPU equivalence and Notebook extraction checks."""
import argparse
import ast
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('release', type=Path); parser.add_argument('board_archive', type=Path)
    parser.add_argument('output', type=Path)
    a = parser.parse_args()
    sys.path.insert(0,str(a.release.resolve()/'package'))
    from system_bench.common import validate, info, require, word_sha, write_json
    from system_bench.cpu import compute
    package = a.release/'package'
    manifest = validate(package)
    model = json.loads((package/'bench_reference/c7_d6_r1.json').read_bytes())
    protocol = json.loads((package/'c7_baseline/q4d_protocol.json').read_bytes())
    require(info(a.board_archive)['sha256'] == manifest['baseline_board_archive_sha256'], 'Wrong real-board evidence')
    matched=[]
    with zipfile.ZipFile(a.board_archive) as archive:
        seen=set()
        for name in archive.namelist():
            if not name.endswith('/record.json'): continue
            record=json.loads(archive.read(name)); q=record['request']
            key=(q['image_id'],q['side'])
            if q['algorithm']!='C7' or q['threshold']!=112 or q['mode_code']!=3 or key in seen: continue
            prefix=name.rsplit('/',1)[0]+'/'
            source=np.load(io.BytesIO(archive.read(prefix+'input_packed.npy')),allow_pickle=False)
            actual=np.load(io.BytesIO(archive.read(prefix+'output_packed.npy')),allow_pickle=False)
            before=word_sha(source); source.setflags(write=False)
            result=compute(source,model)
            require(np.array_equal(result,actual),'CPU differs from actual C7 DMA: '+str(key))
            expected=protocol['expected_output_sha256']['%s_%d_C7'%key]
            require(word_sha(result)==expected and word_sha(source)==before, 'SHA/input mutation')
            matched.append(dict(image_id=key[0],side=key[1],words=int(result.size),output_sha256=expected))
            seen.add(key)
            print('HOST_CPU_REAL_C7_MATCH',*key,flush=True)
    require(len(matched)==40,'Need all 20 images x two sizes')
    nb=json.loads((a.release/'upload/c7_w4_processing.ipynb').read_bytes())
    cells=[c for c in nb['cells'] if c['cell_type']=='code']; require(len(cells)==7,'Seven code cells required')
    for cell in cells:
        ast.parse(''.join(cell['source']), feature_version=(3,10))
        require(not cell['outputs'] and cell['execution_count'] is None,'Clean release Notebook required')
    # Exercise actual first-cell code and path safety on the exact delivered ZIP.
    old=Path.cwd()
    with tempfile.TemporaryDirectory() as td:
        import shutil
        shutil.copy2(a.release/'upload/c7_w4_processing_r1.zip',Path(td)/'c7_w4_processing_r1.zip')
        try:
            os.chdir(td); scope={}; exec(''.join(cells[0]['source']),scope)
            extracted=scope['w4_root']
            require(validate(extracted)==manifest,'Extraction changed release')
            try: exec(''.join(cells[0]['source']),scope)
            except RuntimeError: pass
            else: raise AssertionError('Repeated extraction permitted')
        finally: os.chdir(old)
    # Confirm unchanged production hardware/service/UI. Only bench code knows CPU.
    for path in (package/'c7_baseline/pynq_q4d').glob('*.py'):
        require('system_bench' not in path.read_text() and 'bench_reference' not in path.read_text(), 'CPU leaked into production')
    for path in package.rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'),feature_version=(3,10))
    report=dict(status='HOST_ONLY_PASS_BOARD_NOT_RUN',matched=matched,
        matched_words=sum(x['words'] for x in matched),compared_to='Real archived C7 DMA outputs, all 40 distinct image/size combinations',
        package=info(package/'w4_manifest.json'),release=json.loads((a.release/'release.json').read_bytes()),
        checks=['148-member package hashes', 'frozen baseline manifest pin', '40 actual C7 DMA whole-word comparisons',
                'immutable inputs', 'Python 3.10 syntax', 'seven clean code cells', 'actual ZIP Notebook extraction',
                'repeat extraction rejected', 'unchanged production CPU separation'],
        caveat='CPU comparator functionally equivalent; PS timing and 618 new real PL requests have NOT run.')
    a.output.parent.mkdir(parents=True,exist_ok=True);write_json(a.output,report)
    print('W4_HOST_AUDIT_PASS',report['matched_words'],'words; BOARD_NOT_RUN')


if __name__=='__main__': main()
