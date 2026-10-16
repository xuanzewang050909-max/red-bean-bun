"""Offline audit of partial failure collection; never upgrades interruption to pass."""
import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import numpy as np
from showcase_board import validate_showcase
from verify_showcase_run import check_run, expected_words, CANDIDATE
from pynq_showcase.protocol import Inputs


class SessionArchive:
    def __init__(self, archive, prefix):
        self.archive, self.prefix = archive, prefix

    def read(self, name):
        return self.archive.read(self.prefix+name)


def audit(archive, package):
    validate_showcase(package)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist(); index = json.loads(z.read('failure_collection_manifest.json'))
        assert len(names) == len(set(names)) and set(names) == set(index['files'])|{'failure_collection_manifest.json'}
        for name, meta in index['files'].items():
            data = z.read(name)
            assert len(data) == meta['bytes'] and hashlib.sha256(data).hexdigest() == meta['sha256']
            assert not meta.get('changed_during_collection')
        logs = json.loads(z.read('os_diagnostics.json'))
        notebook = json.loads(z.read('evidence/c7_showcase.ipynb'))
        texts = [''.join(''.join(o.get('text', [])) for o in c.get('outputs', [])) for c in notebook['cells'] if c['cell_type']=='code']
        boot = re.search(r"SHOWCASE_PRECHECK_PASS:.*?'boot_id': '([0-9a-f-]{36})'", '\n'.join(texts)).group(1)
        sessions = [n[:-len('events.jsonl')] for n in names if n.endswith('/events.jsonl')]
        assert len(sessions) == 1
        prefix = sessions[0]; adapter = SessionArchive(z, prefix)
        manifest = json.loads(z.read(prefix+'browser_manifest.json'))
        assert manifest == json.loads((package/'browser_manifest.json').read_bytes())
        events, malformed = [], []
        for i, raw in enumerate(z.read(prefix+'events.jsonl').splitlines(), 1):
            try: events.append(json.loads(raw))
            except (ValueError, UnicodeDecodeError): malformed.append(dict(line=i, bytes=len(raw), nul_bytes=raw.count(b'\0')))
        rows = []; words = pngs = 0
        for name in names:
            if not name.startswith(prefix) or not name.endswith('/record.json'): continue
            rid = name[len(prefix):].split('/')[0]
            row = dict(run_id=rid, record_bytes=z.getinfo(name).file_size)
            try:
                record = json.loads(z.read(name))
                row.update(image=record['request']['image_id'], sequence=record['evidence']['hardware_latched_parameter_readback']['sequence'])
                result = check_run(adapter, record, package, manifest)
                obs = json.loads(adapter.read(rid+'/browser_timing.json'))
                assert obs['run_id']==rid and obs['output_sha256']==record['output']['sha256'] and obs['input_sha256']==record['input']['sha256'] and obs['config_id']==record['config_id'] and obs['client_nonce']==record['request']['client_nonce'] and obs['visibility']=='visible'
                for kind in ('RUN_ACCEPTED','RUN_STARTED','RUN_COMPLETED','BROWSER_FIRST_RENDER'):
                    assert sum(e['event']==kind and e['detail'].get('run_id')==rid for e in events)==1
                row.update(status='COMPLETED_RECORD_VERIFIED_PARTIAL_ONLY', **result)
                words += result['matched_words']; pngs += result['matched_png_images']
            except Exception as exc:
                row.update(status='INCOMPLETE_OR_INVALID_NOT_COUNTED', error=type(exc).__name__+': '+str(exc))
                row['files'] = {n[len(prefix+rid+'/'):]: z.getinfo(n).file_size for n in names if n.startswith(prefix+rid+'/')}
            rows.append(row)
            print('PARTIAL_AUDIT', row.get('sequence'), row.get('image'), row['status'], flush=True)
        # Arrays from a recordless task are diagnostic comparisons only: they do
        # not establish its parameter readback, completion or browser evidence.
        orphans = []
        for row in rows:
            if row['status'] != 'INCOMPLETE_OR_INVALID_NOT_COUNTED': continue
            rid = row['run_id']; accepted = [e for e in events if e['event']=='RUN_ACCEPTED' and e['detail'].get('run_id')==rid]
            if not accepted: continue
            req = accepted[0]['detail']['request']; result = dict(run_id=rid, image=req['image_id'], status='NOT_A_COMPLETED_VERIFIED_FRAME')
            try:
                source = np.load(io.BytesIO(adapter.read(rid+'/input_packed.npy')), allow_pickle=False)
                output = np.load(io.BytesIO(adapter.read(rid+'/output_packed.npy')), allow_pickle=False)
                prepared, _ = Inputs(package, manifest['images']).load(req)
                result['input_matches'] = bool(np.array_equal(source, prepared))
                result['output_matches_reference'] = bool(np.array_equal(output, expected_words(prepared, req['mode_code'], req['algorithm'], req['threshold'], CANDIDATE)))
            except Exception as exc: result['error'] = type(exc).__name__+': '+str(exc)
            orphans.append(result)
        current_boot = logs['proc/sys/kernel/random/boot_id'].strip()
        return dict(status='INTERRUPTED_NOT_DEMO_PASS', archive=dict(bytes=Path(archive).stat().st_size,sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest()),
            collection_inventory_files=len(names), boot_at_demo=boot, boot_at_collection=current_boot, reboot_between_demo_and_collection=boot!=current_boot,
            user_reboot_recollection='UNCERTAIN', reboot_cause='UNDETERMINED; current-boot logs do not prove previous-boot failure cause',
            matched_words=words, matched_pngs=pngs, verified_complete_records=sum(r['status']=='COMPLETED_RECORD_VERIFIED_PARTIAL_ONLY' for r in rows),
            runs=rows, orphan_arrays_diagnostic_only=orphans, malformed_event_lines=malformed,
            events={kind:sum(e['event']==kind for e in events) for kind in ('SERVICE_READY','RUN_ACCEPTED','RUN_STARTED','RUN_COMPLETED','BROWSER_FIRST_RENDER','SERVICE_FAULT','SERVICE_FINISHED_IDLE')},
            screenshot_frame_17_missing_from_collected_records=not any(r['run_id']=='a5e500d4c02041ec8850d1975c9638ff' for r in rows),
            exclusions=['No safe-close/export completion','Malformed/empty metadata retained and excluded from verified totals','No automatic board retry or inferred power-supply/SD failure','Previous-boot journal not collected yet'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('package',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();args.destination.mkdir(parents=True,exist_ok=False)
    result=audit(args.archive,args.package)
    (args.destination/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
