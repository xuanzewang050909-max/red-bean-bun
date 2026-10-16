"""Derive a software-only B r2; retain the r1 hardware and failure history."""
import argparse
import copy
import json
import re
import shutil
import tempfile
from pathlib import Path

from b_integration_board_test import REVISION,FIXED,NOTEBOOK,validate_b_package
from check_b_hardware import info,require
from check_b_driver_imports import check as check_imports

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    for name in ('baseline','destination','patch_destination','results'):parser.add_argument(name,type=Path)
    args=parser.parse_args()
    for path in (args.destination,args.patch_destination,args.results/'release_manifest.json'):
        require(not path.exists(),'Preserve earlier release: '+str(path))
    historical=ROOT/'results/b_integration_2017_4/release_manifest.json'
    baseline_manifest=args.baseline/'b_manifest.json'
    require(baseline_manifest.read_bytes()==historical.read_bytes(),'Original manifest changed')
    original=json.loads(baseline_manifest.read_text(encoding='utf-8'))
    require(original['revision']=='b_integration_r1_official_base_a4','Expected original r1')
    require(set(original['artifacts'])==FIXED|{NOTEBOOK},'Incomplete original release')
    for name,recorded in original['artifacts'].items():
        require(info(args.baseline/name)==recorded,'Original artifact changed: '+name)
    for path,recorded in original['source_files'].items():
        if path!='scripts/b_integration_board_test.py':require(info(ROOT/path)==recorded,'Other original source changed: '+path)
    old=(args.baseline/'b_integration_board_test.py').read_text(encoding='utf-8')
    expected=old.replace("REVISION='b_integration_r1_official_base_a4'","REVISION='b_integration_r2_explicit_video_imports'")
    expected=expected.replace('    from pynq.lib.video import AxiVDMA,VideoOut,HDMIWrapper,VideoMode,PIXEL_BGR\n',
        '    from pynq.lib.video.common import VideoMode,PIXEL_BGR\n    from pynq.lib.video.dma import AxiVDMA\n    from pynq.lib.video.hierarchies import VideoOut,HDMIWrapper\n')
    require(expected==(ROOT/'scripts/b_integration_board_test.py').read_text(encoding='utf-8'),'Fix changed more than explicit import paths and revision')
    tests=(args.results/'host_regression_tests.log').read_text(encoding='utf-8-sig')
    count=re.search(r'Ran (\d+) tests',tests)
    require(count and int(count.group(1))>=23 and '\nOK' in tests and 'FAILED' not in tests,'R2 regression incomplete')
    tested=json.loads((args.results/'host_test_sources.json').read_text(encoding='utf-8'))
    require(tested['log']==info(args.results/'host_regression_tests.log'),'Regression log changed')
    for path,recorded in tested['sources'].items():require(info(ROOT/path)==recorded,'Source changed after tests: '+path)
    imports=check_imports(ROOT/'scripts/b_integration_board_test.py')
    manifest=copy.deepcopy(original)
    manifest.update(revision=REVISION,board_status='NOT_RUN',host_status='PASS_REUSED_R1_HARDWARE_AND_R2_EXPLICIT_DRIVER_IMPORT_REGRESSION')
    manifest['hardware_provenance']={'baseline_manifest':str(historical.relative_to(ROOT)).replace('\\','/'),
        'baseline_manifest_sha256':info(baseline_manifest)['sha256'],'hardware_rebuilt':False,
        'policy':'Identical paired bit/HWH, inputs, unchanged A4 helpers, notebook and guide; original build/reset/timing evidence retained'}
    manifest['software_checks']={'host_test_count':int(count.group(1)),'log':info(args.results/'host_regression_tests.log'),
        'driver_import_check':imports,'original_failure_reproduced':True,
        'limit':'Official initializer export behavior and precheck tested on host; real installed video binding/display remains pending'}
    software_sources=('scripts/b_integration_board_test.py','scripts/package_b_import_fix.py','scripts/check_b_driver_imports.py',
        'tests/test_b_video_imports.py','docs/b_video_import_recovery_steps.md')
    for path in software_sources:manifest['source_files'][path]=info(ROOT/path)
    validation={}
    with tempfile.TemporaryDirectory() as tmp:
        staged=Path(tmp)
        for name in original['artifacts']:shutil.copyfile(args.baseline/name,staged/name)
        shutil.copyfile(ROOT/'scripts/b_integration_board_test.py',staged/'b_integration_board_test.py')
        manifest['artifacts']['b_integration_board_test.py']=info(staged/'b_integration_board_test.py')
        payload=json.dumps(manifest,indent=2,ensure_ascii=False)+'\n'
        (staged/'b_manifest.json').write_text(payload,encoding='utf-8',newline='\n')
        validation['original_package']=validate_b_package(staged,manifest)
        saved=json.loads((staged/NOTEBOOK).read_text(encoding='utf-8'))
        for cell in saved['cells']:
            if cell['cell_type']=='code':
                cell['execution_count']=5;cell['outputs']=[{'name':'stdout','output_type':'stream','text':'HOST SAVE PROBE ONLY - NOT BOARD EVIDENCE\n'}]
        (staged/NOTEBOOK).write_text(json.dumps(saved),encoding='utf-8')
        validation['saved_notebook']=validate_b_package(staged,manifest)
        shutil.copyfile(args.baseline/NOTEBOOK,staged/NOTEBOOK)
        validate_b_package(staged,manifest)
        args.destination.mkdir(parents=True)
        for path in staged.iterdir():shutil.copyfile(path,args.destination/path.name)
    unchanged=[name for name in original['artifacts'] if name!='b_integration_board_test.py']
    require(all(info(args.destination/name)==original['artifacts'][name] for name in unchanged),'Inherited artifact changed')
    args.patch_destination.mkdir(parents=True)
    for name in ('b_integration_board_test.py','b_manifest.json'):shutil.copyfile(args.destination/name,args.patch_destination/name)
    validation.update(status='PASS_SOFTWARE_ONLY_R2_PACKAGE_AND_SAVED_NOTEBOOK',board_status='NOT_RUN',
        full_package=str(args.destination.resolve()),patch_package=str(args.patch_destination.resolve()),
        unchanged_artifacts=unchanged,patch_files={p.name:info(p) for p in args.patch_destination.iterdir()},
        scope='Host package/import checks only; no new FPGA implementation or board display/FPS PASS')
    (args.results/'release_manifest.json').write_text(payload,encoding='utf-8',newline='\n')
    (args.results/'package_validation.json').write_text(json.dumps(validation,indent=2)+'\n',encoding='utf-8')
    (args.results/'driver_import_check_final.json').write_text(json.dumps(imports,indent=2)+'\n',encoding='utf-8')
    print('B_R2_VIDEO_IMPORT_FIX_READY_HOST_VERIFIED_BOARD_PENDING',args.patch_destination)


if __name__=='__main__':main()
