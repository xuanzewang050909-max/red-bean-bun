"""Verify a manually downloaded C7 web run, without inference or board access."""
import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
import numpy as np


def verify(archive,package,host_test=False):
    root=Path(package).resolve()
    sys.path.insert(0,str(root))
    from pynq_showcase.protocol import validate_package
    from pynq_showcase.single_image import decode_workspace,pack_live_input,select_target
    validate_package(root)
    config=json.loads((root/'integration.json').read_bytes())
    digest=lambda b:hashlib.sha256(b).hexdigest()
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        assert len(names)==len(set(names)) and all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names)
        assert z.read('browser_manifest.json')==(root/'browser_manifest.json').read_bytes()
        capability=json.loads(z.read('capabilities.json'))
        required_source='HOST_TEST_DOUBLE_NOT_BOARD' if host_test else 'PYNQ_PL_DMA'
        assert capability['evidence_kind']==required_source
        completed=[];originals=[]
        for name in names:
            if not name.endswith('/record.json'):continue
            job=json.loads(z.read(name));prefix=name.rsplit('/',1)[0]+'/'
            assert job['status']=='COMPLETED',name
            is_original=job.get('presentation_stage')=='C7_ORIGINAL'
            if not is_original and not job.get('refinement',{}).get('applied'):continue
            assert job['evidence']['evidence_kind']==required_source
            assert job['request']['algorithm']=='C7' and job['request']['side']==512 and job['request']['threshold']==112 and job['request']['mode_code']==3
            for path,ref in job['files'].items():
                raw=z.read(prefix+path)
                assert len(raw)==ref['bytes'] and digest(raw)==ref['sha256'],path
            load=lambda filename:np.load(io.BytesIO(z.read(prefix+filename)),allow_pickle=False)
            words=load('input_packed.npy');c7=load('output_packed.npy')
            assert words.dtype==c7.dtype==np.uint32 and words.shape==c7.shape==(512,512)
            target=select_target(words,job['request'],config);assert target is not None
            assert digest(words.tobytes())==target['input_word_sha256']==job['input']['sha256']
            assert digest(c7.tobytes())==target['c7_output_word_sha256']==job.get('c7_output',job['output'])['sha256']
            from PIL import Image
            displayed=np.array(Image.open(io.BytesIO(z.read(prefix+'mask.png'))))
            browser=json.loads(z.read(prefix+'browser_timing.json'))
            assert browser['run_id']==job['run_id'] and browser['output_sha256']==job['output']['sha256']
            assert browser['visibility']=='visible' and browser['evidence_kind']==required_source
            if not host_test:
                assert job['evidence']['send_bytes']==job['evidence']['recv_bytes']==512*512*4
                obs=job['evidence']['hardware_latched_parameter_readback']
                assert obs['raw_pages']['9']==obs['raw_pages']['10']==512*512
                assert obs['raw_pages']['1']==2 and obs['raw_pages']['3']==obs['latched_control']
                assert obs['raw_pages']['4']==obs['raw_pages']['11']==obs['sequence']
                assert obs['clock_hz_from_paired_implementation']==100000000
                assert obs['latched_control']==job['evidence']['requested_control_word']
                assert all(v & 2 and not v & 0x771 for v in job['evidence']['dma_status'].values())
            if is_original:
                assert not job['refinement']['applied'] and job['refinement_available'] and not job.get('c7_parent')
                assert prefix+'refinement_actual.npy' not in names
                np.testing.assert_array_equal(displayed,((c7>>16)&255).astype(np.uint8))
                originals.append(dict(run_id=job['run_id'],image_id=target['image_id'],pixels=int((displayed!=0).sum()),output_sha256=digest(c7.tobytes())))
                continue
            if job.get('c7_parent'):
                binding=job['c7_parent'];parent_bytes=z.read(prefix+'c7_parent_record.json')
                assert binding['record_file']==dict(bytes=len(parent_bytes),sha256=digest(parent_bytes))
                parent=json.loads(parent_bytes)
                assert parent['status']=='COMPLETED' and parent['presentation_stage']=='C7_ORIGINAL'
                assert not parent['refinement']['applied'] and parent['refinement_available']
                assert parent['session_id']==job['session_id'] and parent['run_id']==binding['run_id']
                assert parent['input']['sha256']==binding['input_sha256']==job['input']['sha256']
                assert parent['output']['sha256']==binding['output_sha256']==job['c7_output']['sha256']
                assert parent['output']['file']==job['files']['output_packed.npy']
                for key in ('image_id','side','algorithm','mode','mode_code','threshold','png_profile'):
                    assert parent['request'][key]==job['request'][key],key
                assert parent['raw_timestamps_ns']['worker_result_ready_ns']<job['accepted_server_ns']
                assert all(job['timing_ns'][k]==0 for k in ('c7_inference_ns','pl_core_frame_ns','dma_transaction_ns','c7_overlay_restore_ns'))
                parent_name=binding['run_id']+'/record.json'
                if parent_name in names:assert z.read(parent_name)==parent_bytes
            actual=load('refinement_actual.npy')
            np.testing.assert_array_equal(pack_live_input(words,c7,target),load('refinement_input.npy'))
            final,added,uncertain=decode_workspace(actual,words,c7,target)
            for filename,expected in [('final_mask.npy',final),('added_mask.npy',added),('uncertain_mask.npy',uncertain)]:
                np.testing.assert_array_equal(load(filename),expected)
            assert job['output']['sha256']==digest(final.tobytes())
            rec=json.loads(z.read(prefix+'refinement_record.json'))
            assert rec==job['refinement'] and rec['source']=='REAL_PYNQ_PL' and rec['operation_count']==20 and rec['inference_on_PS'] is False
            assert rec['target_image']==target['image_id'] and rec['profile']==target['profile'] and rec['implementation']==target['implementation']
            for filename,identity in rec['refinement_artifacts'].items():
                data=(root/target['payload']/filename).read_bytes()
                assert identity==dict(bytes=len(data),sha256=digest(data))
            assert rec['added_pixels']==int(added.sum()) and rec['final_pixels']==int(final.sum())
            assert 49.9 <= rec['clock']['actual_register_derived_mhz'] <= 50.000001 and not rec['clock']['set_clock_performed']
            events=[json.loads(x) for x in z.read(prefix+'events.jsonl').decode().splitlines()]
            assert not any(e['event']=='ACCESS_FAILED' for e in events)
            assert [e['data']['op'] for e in events if e['event']=='OP_DONE']==[0,1,2]+[3]*16+[4]
            returned=[e['data']['label'] for e in events if e['event']=='ACCESS_RETURNED']
            assert returned.count('REFINEMENT_DOWNLOAD')==1 and returned.count('SYNC_FROM_DEVICE')==1
            assert returned.count('AP_START')==20 and returned.count('RELEASE_COMPLETED_BUFFER')==1
            runtime=json.loads(z.read(prefix+'refinement_runtime.json'))
            profile_writes=[e['data']['details']['value'] for e in events if e['event']=='ACCESS_RETURNED' and e['data']['label']=='CONTROL_WRITE' and e['data']['details']['offset']==0x40]
            assert profile_writes==([] if target['profile'] is None else [target['profile']])
            for key,ref in json.loads((root/target['payload']/'runtime_contract.json').read_bytes()).items():
                assert runtime[key]=={k:ref[k] for k in ('bytes','sha256')}
            np.testing.assert_array_equal(displayed,final.astype(np.uint8)*255)
            completed.append(dict(run_id=job['run_id'],image_id=target['image_id'],profile=target['profile'],added=int(added.sum()),final=int(final.sum()),mask_sha256=digest(final.tobytes())))
        assert completed or originals,'NO_COMPLETED_TARGETED_C7_RUN'
    return dict(status='HOST_TEST_VERIFIER_PASS_NOT_BOARD' if host_test else 'C7_WEB_TARGETED_IMAGES_NUMERIC_VERIFIED' if completed else 'C7_WEB_ORIGINAL_RESULT_VERIFIED',runs=completed,original_runs=originals,
                archive_sha256=digest(Path(archive).read_bytes()),quality='TARGETED_IMAGES_ONLY_NO_INDEPENDENT_GT_CLAIM')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--package',required=True,type=Path)
    p.add_argument('--host-test',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args();result=verify(a.archive,a.package,a.host_test)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:
        with a.output.open('x',encoding='utf8') as f:f.write(text+'\n')
    print(text)
