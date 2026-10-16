"""Restore compact W5a records to conventional per-run NPY/PNG paths.

Integrity checking only, NOT a board/algorithm acceptance audit. Uses hardlinks
inside a newly created directory; never replaces existing user files.
"""
import argparse
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path


def restore(archive,destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('Use a new destination; preserve existing files')
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        if len(names)!=len(set(names)) or len(names)>10000 or sum(e.file_size for e in entries)>1536*1024**2:
            raise ValueError('Archive inventory/size invalid')
        for e in entries:
            if e.is_dir() or Path(e.filename).is_absolute() or '..' in Path(e.filename).parts or ':' in e.filename or '\\' in e.filename:
                raise ValueError('Unsafe archive path')
        manifest=json.loads(z.read('bundle_manifest.json'))
        if manifest['revision']!='c7_w5a_stability_r1' or set(names)!=set(manifest['files'])|{'bundle_manifest.json'}:
            raise ValueError('Manifest inventory mismatch')
        for name,meta in manifest['files'].items():
            data=z.read(name)
            if dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())!=meta:raise ValueError('Corrupted file: '+name)
        session=json.loads(z.read('session.json'));records=[]
        for rid in session['run_ids']:
            if re.fullmatch('[0-9a-f]{32}',rid) is None:raise ValueError('Invalid run id')
            r=json.loads(z.read(rid+'/record.json'))
            if set(r['storage_refs'])!=set(r['files']):raise ValueError('Missing file reference')
            for name,target in r['storage_refs'].items():
                if re.fullmatch('[A-Za-z0-9_]+\.(npy|png)',name) is None or target!='objects/'+r['files'][name]['sha256'] or manifest['files'][target]!=r['files'][name]:
                    raise ValueError('Unsafe or incorrect content reference')
            records.append(r)
        destination.mkdir(parents=True,exist_ok=False)
        for name in names:
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
        for r in records:
            for name,target in r['storage_refs'].items():
                os.link(destination/target,destination/r['run_id']/name)
    return len(records)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();print('RESTORED_INTEGRITY_ONLY',restore(a.archive,a.destination))
