"""One-time full backup of the identified original card. Never opens the card for writing."""
from pathlib import Path
import ctypes
import hashlib
import json
import shutil
import subprocess
import time
import traceback

ROOT = Path('D:/PLD/retina_fpga')
OUTPUT = ROOT / 'build/sd_backups'
RECORD = ROOT / 'results/board/2026-10-11'
STATUS = RECORD / 'sd_backup_status.json'
EXPECTED_SIZE = 15931539456
EXPECTED_BOOT_SHA256 = 'ccc272148b46c85bd7db0cc38d81981a59a48b80777fcab7b06782da9d267027'
CHUNK = 8 * 1024 * 1024

def status(state, **fields):
    obj = {'state': state, 'source': r'\\.\PhysicalDrive1',
           'source_access': 'rb (read only)', 'card_expected_bytes': EXPECTED_SIZE,
           'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'), **fields}
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(STATUS)

def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('Full-card read requires Windows administrator permission')
    query = "$p = Get-Partition -DriveLetter F -ErrorAction Stop; $d = $p | Get-Disk; [pscustomobject]@{DiskNumber=$d.Number;BusType=[string]$d.BusType;Size=$d.Size;IsBoot=$d.IsBoot;IsSystem=$d.IsSystem;PartitionSize=$p.Size;PartitionOffset=$p.Offset} | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', query],
                            capture_output=True, text=True, check=True, creationflags=0x08000000)
    disk = json.loads(result.stdout)
    if (disk['DiskNumber'] != 1 or disk['BusType'] != 'USB' or disk['Size'] != EXPECTED_SIZE
            or disk['IsBoot'] or disk['IsSystem'] or disk['PartitionSize'] != 104857600
            or disk['PartitionOffset'] != 1048576):
        raise RuntimeError('Card identity changed; refusing to read a different device')
    if hashlib.sha256(Path('F:/BOOT.BIN').read_bytes()).hexdigest() != EXPECTED_BOOT_SHA256:
        raise RuntimeError('Original card boot-file fingerprint changed')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / 'original_card_20261011.img'
    partial = OUTPUT / 'original_card_20261011.img.partial'
    if target.exists() or partial.exists():
        raise FileExistsError('Existing backup/partial backup retained; inspect before retry')
    if shutil.disk_usage(OUTPUT).free < EXPECTED_SIZE + 1024**3:
        raise RuntimeError('Insufficient free space for full card backup')
    digest = hashlib.sha256()
    copied = 0
    last = time.monotonic()
    status('COPYING', image_path=str(target), bytes_copied=0, disk_identity=disk)
    # rb is deliberate: no SD writes, partition changes, lock/discard, or repair commands.
    with open(r'\\.\PhysicalDrive1', 'rb', buffering=0) as source, partial.open('xb') as destination:
        while copied < EXPECTED_SIZE:
            data = source.read(min(CHUNK, EXPECTED_SIZE - copied))
            if not data or len(data) % 512:
                raise IOError('Unexpected EOF or unaligned raw card read')
            destination.write(data)
            digest.update(data)
            copied += len(data)
            if time.monotonic() - last > 5:
                status('COPYING', image_path=str(target), bytes_copied=copied,
                       percent=round(copied * 100 / EXPECTED_SIZE, 1))
                last = time.monotonic()
        destination.flush()
    source_sha = digest.hexdigest()
    status('VERIFYING_PC_BACKUP', image_path=str(target), bytes_copied=copied, percent=100)
    check = hashlib.sha256()
    with partial.open('rb') as f:
        for data in iter(lambda: f.read(CHUNK), b''):
            check.update(data)
    if partial.stat().st_size != EXPECTED_SIZE or check.hexdigest() != source_sha:
        raise IOError('Backup verification failed; partial image preserved')
    partial.rename(target)
    status('COMPLETE', image_path=str(target), bytes_copied=copied, percent=100,
           sha256=source_sha, verification='Full destination reread matches source-stream SHA256',
           scope='Full physical card including MBR, both partitions and unallocated bytes; SD untouched')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        status('FAILED', error=traceback.format_exc(), scope='No SD writes were attempted')
        raise
