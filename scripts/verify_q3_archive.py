"""Offline Q3 audit of actual full-word/PNG/observer evidence and frozen quality.

The common per-run audit and lifecycle/CSV logic derive from W4a. There is no
requirement for 20-frame FPS loops in this quality experiment. Core/DMA/inference
samples are recorded but cannot replace the preregistered formal performance run.
"""
import argparse
import csv
import io
import json
import math
import sys
import zipfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from verify_browser_w4a_archive import check_run, notebook_outputs, notebook_code_hash, latency_statistics
from pynq_w4a.protocol import validate_package, require, file_info, write_json, REVISION, MODES, PNG_PROFILES, rgb_from_input
from software.reference import gaussian3
from verify_q1_training import independent_regions, independent_metrics
from evaluate_q1_bilateral import summarize, assess_candidate
from q3_board import validate_q3, planned_requests


def quality_report(archive, package, manifest, protocol, batch_records):
    scores={alg:{str(side):{observer:{} for observer in ('AH','VK')} for side in (256,512)} for alg in ('A','C2')}
    for record in batch_records:
        q=record['request']; run_id=record['run_id']; side=str(q['side']); image=q['image_id']; alg=q['algorithm']
        source=np.load(io.BytesIO(archive.read(run_id+'/input_packed.npy')),allow_pickle=False)
        output=np.load(io.BytesIO(archive.read(run_id+'/output_packed.npy')),allow_pickle=False)
        fov=(source>>24)!=0; mask=((output>>16)&255)!=0
        # Evaluation-only region definitions. This never creates/replaces a medical output.
        feat={'filtered':gaussian3(((source>>8)&255).astype(np.uint8))}
        entry=manifest['images'][image][side]
        for observer in ('AH','VK'):
            truth=np.load(package/entry['evaluation_only'][observer]['path'],allow_pickle=False)
            regions=independent_regions(feat,truth,fov)
            scores[alg][side][observer][image]={name:independent_metrics(mask,truth,region) for name,region in regions.items()}
    groups={}
    for split,ids in protocol['split'].items():
        for observer in ('AH','VK'):
            group={alg:{side:{'per_image':{i:scores[alg][side][observer][i] for i in ids}} for side in ('256','512')} for alg in ('A','C2')}
            for alg in group:
                for side in group[alg]:group[alg][side]['summary']=summarize(group[alg][side]['per_image'])
            assessment=assess_candidate(group['C2'],group['A'],protocol['comparison_gates'])
            groups[split+'_'+observer]={'scores':group,'meets_prespecified_protection_gates':assessment['eligible_for_Q2_feasibility'],
                'failed_gates':assessment['failed_gates'],'deltas':assessment['deltas']}
    return {'groups':groups,'scope':'80 actual PL masks, fixed A28/C2; original full FOV; train/heldout and AH/VK separate. Gate failures remain visible; no clinical conclusion.',
            'threshold':28,'candidate':protocol['candidate'],'retuned':False,'all_group_gates_met':all(g['meets_prespecified_protection_gates'] for g in groups.values())}


def verify(archive_path, notebook_path, package, *, allow_incomplete_display=True):
    package = Path(package)
    manifest = validate_package(package)
    executed = json.loads(Path(notebook_path).read_bytes())
    release = json.loads((ROOT / 'notebooks/q3_quality_start.ipynb').read_bytes())
    # An empty, unexecuted tail is Jupyter UI data, not a changed executable step.
    original_count = sum(cell['cell_type'] == 'code' for cell in release['cells'])
    code = [cell for cell in executed['cells'] if cell['cell_type'] == 'code']
    if len(code) == original_count + 1 and not ''.join(code[-1]['source']).strip() and code[-1].get('execution_count') is None:
        executed = {**executed, 'cells': executed['cells'][:-1]}
        code = code[:-1]
    require(len(code) == original_count and notebook_code_hash(executed) == notebook_code_hash(release), 'Executed Notebook code differs')
    require(all(type(cell.get('execution_count')) is int and not any(output.get('output_type') == 'error' for output in cell.get('outputs', []))
                for cell in code), 'Startup/finish steps did not all complete cleanly')
    records = []
    observations = []
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and all(not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name and ':' not in name for name in names), 'Unsafe/duplicate evidence members')
        require(sum(item.file_size for item in archive.infolist()) <= 1024 ** 3, 'W4a evidence exceeds bounded session size')
        caps = json.loads(archive.read('capabilities.json'))
        require(caps['evidence_kind'] == 'PYNQ_PL_DMA', 'HOST TEST preview is not board evidence')
        require(caps['revision'] == REVISION and caps['threshold_range'] == [1, 255] and caps['algorithms'] == ['A', 'C2'] and caps['core_cycle_readback_supported'] and caps['latched_parameter_readback_supported'] and caps['modes'] == MODES, 'Wrong measured capabilities')
        require(caps['png_profiles'] == PNG_PROFILES, 'Wrong delivery options')
        require(archive.read('browser_manifest.json') == (package / 'browser_manifest.json').read_bytes(), 'Execution package differs')
        environment = json.loads(archive.read('environment.json'))
        require(environment['pynq'] == '3.0.1' and environment['machine'] in ('armv7l', 'armv7'), 'Wrong recorded real board runtime')
        require(environment['runtime_fclk0_mhz_register_readback'] == 100.0 and environment['drivers'] == {'dma': 'pynq.lib.dma.DMA', 'control': 'pynq.lib.axigpio.AxiGPIO', 'observer': 'pynq.lib.axigpio.AxiGPIO'}, 'Wrong clock/drivers')
        session = json.loads(archive.read('session.json'))
        require(session['status']['session_id'] == caps['session_id'] and session['status']['overlay_downloads'] == 1 and
                session['status']['service_state'] == 'READY' and session['status']['hardware_state'] == 'IDLE' and
                session['status']['active_run_id'] is None and session['status']['pending'] == 0 and not session['status']['error'], 'Export not from clean idle single-load session')
        require(session['status']['retained_buffer_count'] == 0, 'Idle session retains native buffers')
        lifecycle = notebook_outputs([code[i] for i in (0,1,2,4,5,6)], session, environment)
        require('Q3_COLLECTION_COMPLETE:' in ''.join(''.join(o.get('text', [])) for o in code[3]['outputs'] if o.get('output_type') == 'stream'), 'Missing completed quality collection')
        native_records = [json.loads(archive.read(run_id + '/record.json')) for run_id in session['run_ids']]
        native_records.sort(key=lambda record: record['accepted_server_ns'])
        previous_status, nonces = 0, set()
        loops = {}
        for record in native_records:
            require(record['session_id'] == caps['session_id'] and record['evidence_kind'] == record['evidence']['evidence_kind'] == 'PYNQ_PL_DMA', 'Mixed/unreal execution provenance')
            require(record['request']['client_nonce'] not in nonces, 'Duplicate request nonce counted twice')
            nonces.add(record['request']['client_nonce'])
            checked = check_run(archive, record, package, manifest)
            require(checked['frame_status_before'] == previous_status, 'Unexplained PL frames or reset between browser requests')
            previous_status = checked['frame_status_after']
            require(checked['hardware']['sequence'] == len(records) + 1, 'Observer sequence discontinuity')
            records.append(checked)
            timing_name = record['run_id'] + '/browser_timing.json'
            if timing_name not in names:
                continue  # Selection can change in flight; such a frame is not a displayed-FPS sample.
            observed = json.loads(archive.read(timing_name))
            require(observed['run_id'] == record['run_id'] and observed['session_id'] == caps['session_id'] and
                    observed['client_nonce'] == record['request']['client_nonce'] and observed['config_id'] == record['config_id'] and
                    observed['input_sha256'] == record['input']['sha256'] and observed['output_sha256'] == record['output']['sha256'], 'Stale browser frame observation')
            require(observed['visibility'] in ('visible', 'hidden') and observed['evidence_kind'] == 'PYNQ_PL_DMA',
                    'Invalid browser visibility/provenance')
            times = [observed[key] for key in ('request_start_ms', 'result_received_ms', 'images_decoded_ms', 'render_done_ms')]
            require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in times) and times == sorted(times), 'Invalid client times')
            require(observed['request_to_render_ms'] == times[-1] - times[0] and observed['result_received_to_render_ms'] == times[-1] - times[1], 'Browser interval arithmetic differs')
            if observed['loop_id'] is None:
                require(observed['browser_actual_fps'] is None, 'Manual click represented as FPS')
            else:
                loop_id, index, start = observed['loop_id'], observed['loop_index'], observed['loop_start_ms']
                previous = loops.get(loop_id, {'index': 0, 'start': times[0], 'render': times[0], 'visible': True, 'config_id': record['config_id']})
                require(index == previous['index'] + 1 and start == previous['start'] and times[0] >= previous['render'] and record['config_id'] == previous['config_id'], 'Nonconsecutive display loop')
                visible = previous['visible'] and observed['visibility'] == 'visible'
                fps = index * 1000 / (times[-1] - start) if index >= 2 and visible and times[-1] > start else None
                require(observed['browser_actual_fps'] == fps, 'Client FPS not unique completed frames per loop duration')
                hidden = previous.get('hidden_indices', []) + ([index] if observed['visibility'] == 'hidden' else [])
                loops[loop_id] = {'index': index, 'start': start, 'render': times[-1], 'visible': visible,
                                 'hidden_indices': hidden, 'verified_fps': fps, 'config_id': record['config_id']}
            observations.append(observed)
        require(session['status']['completed'] == session['status']['accepted'] == len(records) == len(session['run_ids']) and
                session['status']['last_completed_frame_status'] == previous_status, 'Completed/exported/native run count mismatch')
        coverage = {'image_ids': sorted({record['request']['image_id'] for record in records}),
                    'modes': sorted({record['request']['mode'] for record in records}),
                    'sides': sorted({record['request']['side'] for record in records})}
        rows = list(csv.DictReader(io.StringIO(archive.read('measurements.csv').decode('utf-8-sig'))))
        require(len(rows) == len(records), 'CSV count mismatch')
        by_id = {row['run_id']: row for row in rows}
        require(len(by_id) == len(records) and set(by_id) == {record['run_id'] for record in records}, 'Duplicate/missing CSV run IDs')
        observed_by_id = {observed['run_id']: observed for observed in observations}
        for record in records:
            row = by_id[record['run_id']]
            for name in ('dma_transaction_ns', 'inference_ns'):
                require(int(row[name]) == record['timing_ns'][name], 'CSV latency mismatch')
            require(int(row['pl_core_frame_ns']) == record['timing_ns']['pl_core_frame_ns'] and row['pure_dma_transport_ns'] == '', 'CSV invented core/pure transport time')
            require(all(row[key] == str(record['request'][key]) for key in ('image_id', 'side', 'mode', 'threshold', 'algorithm')),
                    'CSV request identity mismatch')
            require(row['png_profile'] == record['request']['png_profile'] and all(int(row[k]) == record['timing_ns'][k] for k in
                    ('array_decode_overlay_ns','png_fromarray_ns','png_save_ns','png_file_hash_ns','file_inventory_hash_ns')), 'CSV PNG profile/timing differs')
            expected_csv = {'vessel_area_fraction': record['quality']['vessel_area_fraction']}
            for label in ('AH', 'VK'):
                for metric in ('dice', 'iou'):
                    expected_csv[metric + '_' + label] = record['quality']['annotations'].get(label, {}).get(metric)
            observation = observed_by_id.get(record['run_id'], {})
            expected_csv.update(browser_request_to_render_ms=observation.get('request_to_render_ms'),
                                browser_actual_fps=observation.get('browser_actual_fps'))
            require(all(row[key] == '' if value is None else float(row[key]) == value for key, value in expected_csv.items()),
                    'CSV quality/browser observation mismatch')
        display_complete = any(loop['index'] >= 20 and loop['visible'] for loop in loops.values())
        if not allow_incomplete_display:
            require(display_complete, 'Visible 20-frame browser loop missing')
    release, protocol = validate_q3(package)
    plan = planned_requests(protocol)
    with zipfile.ZipFile(archive_path) as archive:
        require(archive.read('q3_manifest.json') == (package/'q3_manifest.json').read_bytes() and
                archive.read('q3_protocol.json') == (package/'q3_protocol.json').read_bytes(), 'Q3 package/protocol provenance differs')
        journal=json.loads(archive.read('q3_collection.json'))
        require(journal['status']=='COLLECTION_COMPLETE_PENDING_INDEPENDENT_VERIFICATION' and
                journal['completed']==len(journal['run_ids'])==80 and journal['session_id']==caps['session_id'] and
                journal['evidence_kind']=='PYNQ_PL_DMA' and journal['board_quality_pass'] is False and
                journal['protocol_file']==file_info(package/'q3_protocol.json'), 'Q3 journal incomplete/incorrect')
        require(journal['run_ids']==[r['run_id'] for r in records[:80]], 'Fixed cohort order/IDs changed')
        require(len(records)>=82, 'Missing two live browser previews after collection')
        for expected, actual in zip(plan,records[:80]):
            require(all(actual['request'][k]==v for k,v in expected.items()), 'Q3 frozen request differs')
        require(journal['started_ns'] <= native_records[0]['accepted_server_ns'] < native_records[79]['raw_timestamps_ns']['worker_result_ready_ns'] <= journal['finished_ns'], 'Q3 batch timing/identity differs')
        for image in ('im0002','im0324'):
            matches=[r['run_id'] for r in records[80:] if all(r['request'][k]==v for k,v in dict(image_id=image,side=512,algorithm='C2',threshold=28,mode='final',png_profile='fast').items())]
            require(any(o['run_id'] in matches and o['visibility']=='visible' for o in observations), 'Required visible preview missing: '+image)
        quality=quality_report(archive,package,manifest,protocol,records[:80])
    return {'status':'Q3_REAL_PL_DATA_VERIFIED_QUALITY_GATES_REPORTED_SEPARATELY','session_id':caps['session_id'],
        'archive':file_info(archive_path),'notebook':file_info(notebook_path),'fixed_quality_frames':80,
        'verified_runs':len(records),'matched_words':sum(r['matched_words'] for r in records),
        'matched_png_images':sum(r['matched_png_images'] for r in records),'quality':quality,
        'runs':records,'observations':observations,'lifecycle':lifecycle,
        'hardware_timing_by_side_algorithm':{str(side)+'_'+alg:{key.removesuffix('_ns')+'_ms':latency_statistics([r['timing_ns'][key]/1e6 for r in records[:80] if r['request']['side']==side and r['request']['algorithm']==alg]) for key in ('pl_core_frame_ns','dma_transaction_ns','inference_ns')} for side in (256,512) for alg in ('A','C2')},
        'browser_batch_fps':None,'formal_performance_pass':False,'pure_dma_transport_ns':None,'clinical_acceptance':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path);p.add_argument('notebook',type=Path);p.add_argument('destination',type=Path)
    p.add_argument('--package',type=Path,default=ROOT/'build/deploy/q3_full_quality_r1')
    args=p.parse_args();args.destination.mkdir(parents=True,exist_ok=False)
    try: result=verify(args.archive,args.notebook,args.package)
    except Exception as exc:
        write_json(args.destination/'failed_verification.json',{'status':'FAILED_VERIFICATION','error':type(exc).__name__+': '+str(exc)})
        raise
    write_json(args.destination/'verification.json',result)
    print(result['status'],result['verified_runs'],'runs',result['matched_words'],'words')
