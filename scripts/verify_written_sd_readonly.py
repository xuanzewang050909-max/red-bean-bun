"""Read-only comparison after the user's imaging-tool verification failure."""
from pathlib import Path
import ctypes
import hashlib
import json
import struct
import subprocess
import time
import traceback

ROOT=Path('D:/PLD/retina_fpga')
IMAGE=ROOT/'build/sd_images/pynq_z2_v3.0.1.img'
RECORD=ROOT/'results/board/2026-10-11'
STATUS=RECORD/'sd_compare_status.json'
RESULT=RECORD/'sd_compare_result.json'
SIZE=7858807808
CHUNK=8*1024*1024
EXPECTED_SHA='f17405d25298a2c5ea23ccf95f868b42b18f819ff9d7fe5d079ac9ef53415861'

def save(path,obj):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)

def status(state,**kw):
    save(STATUS,{'state':state,'timestamp':time.strftime('%Y-%m-%d %H:%M:%S'),
         'scope':'Source SD read-only; no card writes or repairs',**kw})

def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('Administrator access required for raw device read')
    query="$p=Get-Partition -DriveLetter F -ErrorAction Stop; $d=$p|Get-Disk; [pscustomobject]@{DiskNumber=$d.Number;BusType=[string]$d.BusType;Size=$d.Size;IsBoot=$d.IsBoot;IsSystem=$d.IsSystem;PartitionSize=$p.Size;PartitionOffset=$p.Offset}|ConvertTo-Json -Compress"
    disk=json.loads(subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',query],
         capture_output=True,text=True,check=True,creationflags=0x08000000).stdout)
    if (disk['DiskNumber']!=1 or disk['BusType']!='USB' or disk['Size']!=15931539456
        or disk['IsBoot'] or disk['IsSystem'] or disk['PartitionOffset']!=4096
        or disk['PartitionSize']!=136314880):
        raise RuntimeError('Card identity/layout differs from confirmed newly written SD')
    if IMAGE.stat().st_size!=SIZE:
        raise RuntimeError('PC image size changed')
    if hashlib.sha256(Path('F:/BOOT.BIN').read_bytes()).hexdigest()!='3fcdd4303567d75ac1e7be96c4a93816acb6c150f6facbf1f123d729a5bd5def':
        raise RuntimeError('Written card boot-file fingerprint changed')
    image_hash,card_hash=hashlib.sha256(),hashlib.sha256()
    offset=0
    last=time.monotonic()
    differences=[]
    count=0
    region_counts={'mbr':0,'pre_boot_partition_gap':0,'boot_partition':0,'partition_gap':0,'linux_partition':0}
    root_image,root_card=hashlib.sha256(),hashlib.sha256()
    root_start=137363456
    status('READING',percent=0,bytes_compared=0)
    with open(r'\\.\PhysicalDrive1','rb',buffering=0) as sd,IMAGE.open('rb') as img:
        while offset<SIZE:
            length=min(CHUNK,SIZE-offset)
            expected=img.read(length)
            actual=sd.read(length)
            if len(expected)!=length or len(actual)!=length:
                raise IOError('Short raw read; comparison incomplete')
            image_hash.update(expected)
            card_hash.update(actual)
            if offset+length>root_start:
                begin=max(0,root_start-offset)
                root_image.update(expected[begin:])
                root_card.update(actual[begin:])
            if actual!=expected:
                for i in range(0,length,512):
                    a,b=actual[i:i+512],expected[i:i+512]
                    if a==b:
                        continue
                    byte_offset=offset+i
                    region=('mbr' if byte_offset<512 else 'pre_boot_partition_gap' if byte_offset<4096
                            else 'boot_partition' if byte_offset<136318976
                            else 'partition_gap' if byte_offset<root_start else 'linux_partition')
                    region_counts[region]+=1
                    count+=1
                    if len(differences)<512:
                        byte_diffs=[{'byte_in_sector':j,'expected':b[j],'actual':a[j]} for j in range(512) if a[j]!=b[j]]
                        differences.append({'sector':byte_offset//512,'byte_offset':byte_offset,'region':region,
                            'different_bytes':len(byte_diffs),'first_byte_differences':byte_diffs[:32]})
            offset+=length
            if time.monotonic()-last>5:
                status('READING',bytes_compared=offset,percent=round(100*offset/SIZE,1),
                       differing_sectors_so_far=count,first_different_sector=differences[0]['sector'] if differences else None)
                last=time.monotonic()
    result={'state':'COMPLETE','disk_identity':disk,'image_path':str(IMAGE),'bytes_compared':offset,
         'pc_image_sha256':image_hash.hexdigest(),'pc_image_matches_preparation_hash':image_hash.hexdigest()==EXPECTED_SHA,
         'sd_image_range_sha256':card_hash.hexdigest(),'exact_image_match':count==0,
         'linux_partition_exact_match':root_image.hexdigest()==root_card.hexdigest(),
         'linux_partition_image_sha256':root_image.hexdigest(),'linux_partition_sd_sha256':root_card.hexdigest(),
         'differing_sectors_total':count,'region_counts':region_counts,'first_differing_sectors':differences,
         'scope':'Read-only comparison of the full official image byte range; extra card capacity excluded; no board boot proof'}
    save(RESULT,result)
    status('COMPLETE',percent=100,result_file=str(RESULT),exact_image_match=count==0,
           differing_sectors=count,linux_partition_exact_match=result['linux_partition_exact_match'])

if __name__=='__main__':
    try:
        main()
    except Exception:
        status('FAILED',error=traceback.format_exc())
        raise
