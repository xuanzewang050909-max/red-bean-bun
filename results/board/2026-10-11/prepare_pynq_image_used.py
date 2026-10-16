from pathlib import Path
import hashlib
import json
import struct
import sys
import time
import zipfile
import zlib

sys.stdout.reconfigure(encoding='utf-8')
archive=Path('C:/Users/Gabriel/Downloads/pynq_z2_v3.0.1.zip')
out=Path('D:/PLD/retina_fpga/build/sd_images')
record=Path('D:/PLD/retina_fpga/results/board/2026-10-11/official_image_preparation.json')
out.mkdir(parents=True,exist_ok=True)
target=out/'pynq_z2_v3.0.1.img'
partial=out/'pynq_z2_v3.0.1.img.partial'
if partial.exists():
    raise RuntimeError('Existing partial image; inspect before retry')
archive_hash=hashlib.sha256()
with archive.open('rb') as f:
    for data in iter(lambda:f.read(8*1024*1024),b''):
        archive_hash.update(data)
with zipfile.ZipFile(archive) as z:
    info=z.getinfo('pynq_z2_v3.0.1.img')
    digest=hashlib.sha256()
    crc=0
    count=0
    last=time.monotonic()
    if target.exists():
        print('Existing image; verifying read-only',flush=True)
        with target.open('rb') as f:
            for data in iter(lambda:f.read(8*1024*1024),b''):
                digest.update(data)
                crc=zlib.crc32(data,crc)
                count+=len(data)
    else:
        print('Extracting official PYNQ-Z2 image to PC disk; SD card untouched',flush=True)
        with z.open(info) as f,partial.open('xb') as dst:
            for data in iter(lambda:f.read(8*1024*1024),b''):
                dst.write(data)
                digest.update(data)
                crc=zlib.crc32(data,crc)
                count+=len(data)
                if time.monotonic()-last>10:
                    print(f'{count*100/info.file_size:.1f}% extracted',flush=True)
                    last=time.monotonic()
        if count!=info.file_size or crc!=info.CRC:
            raise RuntimeError('Image length/CRC mismatch; partial file retained')
        partial.rename(target)
    if count!=info.file_size or crc!=info.CRC:
        raise RuntimeError('Existing image length/CRC mismatch')
with target.open('rb') as f:
    mbr=f.read(512)
partitions=[]
for i in range(4):
    entry=mbr[446+i*16:462+i*16]
    start,sectors=struct.unpack_from('<II',entry,8)
    if entry[4]:
        partitions.append({'index':i+1,'type':f'0x{entry[4]:02x}','start_sector':start,'sectors':sectors,'size_bytes':sectors*512})
report={'source_url':'https://download.amd.com/opendownload/xlnx/pynq_z2_v3.0.1.zip',
    'archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':archive_hash.hexdigest(),
    'image_path':str(target),'image_bytes':count,'image_sha256':digest.hexdigest(),'zip_crc32':f'{crc:08x}',
    'zip_crc_check':'PASS','mbr_signature':mbr[-2:].hex(),'partitions':partitions,
    'scope':'Extracted and verified on PC only; no SD card writes; no published vendor SHA256 used'}
record.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
