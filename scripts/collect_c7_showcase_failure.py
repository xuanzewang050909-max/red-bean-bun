"""Collect interrupted demo files and OS logs without importing PYNQ or hardware.

Run from an independent Jupyter terminal. Never reset/restart/kill/probe PL.
Source files are read only; one uniquely named diagnostic ZIP is written.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path


def os_snapshot():
    result = {'scope': 'OS/process evidence only; no PL access or recovery'}
    for name in ('sys/kernel/random/boot_id', 'uptime', 'meminfo'):
        try:
            result['proc/'+name] = (Path('/proc')/name).read_text()
        except OSError as exc:
            result['proc/'+name] = {'error': str(exc)}
    commands = [
        ['uname', '-a'], ['uptime'], ['free', '-m'], ['df', '-h', '/'],
        ['ps', '-ww', '-eo', 'pid,ppid,stat,pcpu,pmem,wchan:24,args'],
        ['ss', '-ltnp'], ['dmesg'],
        ['journalctl', '-b', '-n', '300', '--no-pager', '-o', 'short-monotonic'],
    ]
    for args in commands:
        key = ' '.join(args)
        print('READ_ONLY:', key, flush=True)
        try:
            p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=5, text=True, errors='replace', check=False)
            text = re.sub(r'(?i)((?:token|password|secret|api_key)\s*[=:]\s*)[^\s&]+', r'\1[REDACTED]', p.stdout)
            result[key] = dict(returncode=p.returncode, output=text[-2*1024*1024:])
        except (OSError, subprocess.TimeoutExpired) as exc:
            result[key] = {'error': type(exc).__name__+': '+str(exc)}
    return result


def collect(root, snapshot=os_snapshot):
    root = Path(root).resolve()
    package = root/'c7_showcase_r1'
    if not (root/'c7_showcase.ipynb').is_file() or not (package/'showcase_manifest.json').is_file():
        raise ValueError('Expected original uploaded folder containing c7_showcase.ipynb and c7_showcase_r1/showcase_manifest.json; preserve old files')
    files = [root/'c7_showcase.ipynb']
    for name in ('showcase_manifest.json', 'browser_manifest.json', 'q4d_hardware_manifest.json', 'browser_startup_failure.json'):
        if (package/name).exists():
            files.append(package/name)
    results = package/'browser_results'
    if results.exists():
        files.extend(p for p in sorted(results.rglob('*')) if p.is_file() or p.is_symlink())
    for p in files:
        if p.is_symlink() or not p.is_file() or root not in p.resolve().parents:
            raise ValueError('Unsafe evidence path; no collection: '+str(p))
    total = sum(p.stat().st_size for p in files)
    if len(files) > 4096 or total > 1024**3:
        raise ValueError('Evidence size exceeds collection bound; preserve files')
    if shutil.disk_usage(root).free < total + 64*1024**2:
        raise ValueError('Insufficient space for diagnostic ZIP; do not delete original evidence')
    logs = snapshot()
    target = root/('c7_showcase_failure_'+time.strftime('%Y%m%d_%H%M%S', time.gmtime())+'_'+uuid.uuid4().hex[:8]+'.zip')
    inventory = {}
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for p in files:
            name = 'evidence/'+p.relative_to(root).as_posix()
            before = p.stat(); digest = hashlib.sha256(); count = 0
            with p.open('rb') as source, z.open(name, 'w') as dest:
                for chunk in iter(lambda: source.read(1024*1024), b''):
                    digest.update(chunk); count += len(chunk); dest.write(chunk)
            after = p.stat()
            inventory[name] = dict(bytes=count, sha256=digest.hexdigest(),
                changed_during_collection=(before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns))
        raw = (json.dumps(logs, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
        z.writestr('os_diagnostics.json', raw)
        inventory['os_diagnostics.json'] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        z.writestr('failure_collection_manifest.json', json.dumps(dict(
            status='INTERRUPTED_DIAGNOSTICS_ONLY_NOT_PASS', files=inventory,
            scope='No PYNQ import, PL/DMA/register access, requests, retries, process signals or reset; originals retained',
            video='DEFERRED_BY_USER'), ensure_ascii=False, indent=2))
    print('FAILURE_RECORDS_READY:', target, flush=True)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    collect(parser.parse_args().root)
