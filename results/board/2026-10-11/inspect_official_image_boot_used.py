from pathlib import Path
import struct,json,hashlib

root=Path('D:/PLD/retina_fpga')
image=root/'build/sd_images/pynq_z2_v3.0.1.img'
with image.open('rb') as f:
    f.seek(446+8)
    start=struct.unpack('<I',f.read(4))[0]*512
    f.seek(start)
    bpb=f.read(512)
    bps=struct.unpack_from('<H',bpb,11)[0]
    spc=bpb[13]
    reserved=struct.unpack_from('<H',bpb,14)[0]
    fats=bpb[16]
    fat16_sectors=struct.unpack_from('<H',bpb,22)[0]
    is_fat16=bool(fat16_sectors)
    sectors_per_fat=fat16_sectors or struct.unpack_from('<I',bpb,36)[0]
    root_cluster=0 if is_fat16 else struct.unpack_from('<I',bpb,44)[0]
    root_bytes=struct.unpack_from('<H',bpb,17)[0]*32
    root_sectors=(root_bytes+bps-1)//bps
    root_start=start+(reserved+fats*sectors_per_fat)*bps
    data_start=root_start+root_sectors*bps
    fat_start=start+reserved*bps
    def chain(cluster):
        visited=set()
        while 2<=cluster<(0xfff8 if is_fat16 else 0x0ffffff8):
            if cluster in visited:
                raise RuntimeError('FAT cycle')
            visited.add(cluster)
            f.seek(data_start+(cluster-2)*bps*spc)
            yield f.read(bps*spc)
            f.seek(fat_start+cluster*(2 if is_fat16 else 4))
            cluster=struct.unpack('<H' if is_fat16 else '<I',f.read(2 if is_fat16 else 4))[0]&(0xffff if is_fat16 else 0x0fffffff)
    if is_fat16:
        f.seek(root_start)
        directory=f.read(root_bytes)
    else:
        directory=b''.join(chain(root_cluster))
    entries=[]
    for offset in range(0,len(directory),32):
        entry=directory[offset:offset+32]
        if entry[0]==0:
            break
        if entry[0]==0xe5 or entry[11]==0x0f or entry[11]&0x18:
            continue
        stem=entry[:8].decode('ascii').rstrip()
        ext=entry[8:11].decode('ascii').rstrip()
        name=stem+('.'+ext if ext else '')
        cluster=(struct.unpack_from('<H',entry,20)[0]<<16)|struct.unpack_from('<H',entry,26)[0]
        size=struct.unpack_from('<I',entry,28)[0]
        data=b''.join(chain(cluster))[:size] if size else b''
        if len(data)!=size:
            raise RuntimeError('Truncated FAT file')
        row={'short_name':name,'size':size,'sha256':hashlib.sha256(data).hexdigest()}
        if name=='REVISION':
            row['content']=data.decode('utf-8',errors='replace')
        entries.append(row)
report={'scope':'Read-only PC IMG inspection, not SD write verification','fat_type':bpb[54:62].decode('ascii') if is_fat16 else bpb[82:90].decode('ascii'),
        'boot_partition_offset':start,'files':entries}
(root/'results/board/2026-10-11/official_image_boot_manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
