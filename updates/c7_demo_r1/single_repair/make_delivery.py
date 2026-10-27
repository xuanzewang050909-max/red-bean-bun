"""Package only finalized files. Console and archive receipts stay outside seals."""
from physical_gate import *
import shutil,subprocess,zipfile,ast,struct
PKG=Path('D:/PLD/review_packages/C7_SingleImage_Repair_Board_r1')
REVIEW=Path('D:/PLD/review_packages/C7_SingleImage_Repair_Review_r1')
COPIES=[]
def write(p,obj):
    with Path(p).open('x',encoding='utf8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)
def cp(src,dst):
    src=Path(src);dst=Path(dst);dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists();shutil.copy2(src,dst);assert ref(src)['sha256']==ref(dst)['sha256']
    COPIES.append(dict(source=ref(src),destination=str(dst)))
def entries(root):
    return {p.relative_to(root).as_posix():ref(p) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
def archive(root):
    path=root.with_suffix('.zip');assert not path.exists()
    expected=entries(root)
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in expected:z.write(root/name,name)
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist())==set(expected) and len(z.namelist())==len(expected)
        assert z.testzip() is None
        for name,r in expected.items():assert hashlib.sha256(z.read(name)).hexdigest()==r['sha256']
    r=ref(path);path.with_suffix('.zip.sha256').write_text(r['sha256']+'  '+path.name+'\n')
    write(path.with_suffix('.zip.receipt.json'),dict(status='ARCHIVE_BYTE_VERIFIED',zip=r,files=len(expected),self_hash_cycle=False))
    return r
def bit_payload(p):
    data=Path(p).read_bytes();n=int.from_bytes(data[:2],'big');pos=2+n;assert data[pos:pos+2]==b'\0\1';pos+=2;fields={}
    for key in b'abcd':
        assert data[pos]==key;size=int.from_bytes(data[pos+1:pos+3],'big');pos+=3
        fields[chr(key)]=data[pos:pos+size].rstrip(b'\0').decode();pos+=size
    assert data[pos:pos+1]==b'e';size=int.from_bytes(data[pos+1:pos+5],'big');pos+=5
    assert len(data)-pos==size;return fields,hashlib.sha256(data[pos:]).hexdigest()
def main():
    assert not PKG.exists() and not REVIEW.exists()
    gate=json.loads((OUT/'physical_gates.json').read_text());release=json.loads((OUT/'release_bit_r2.json').read_text())
    assert gate['status']=='OFFLINE_PHYSICAL_GATES_PASS' and release['status']=='SAME_BUILD_BIT_GENERATED'
    for k in ['bit','dcp','hwh']:assert ref(release[k]['path'])==release[k]
    newfields,payloadsha=bit_payload(release['bit']['path']);oldfields,oldsha=bit_payload(BUILD/'single_repair.bit')
    assert payloadsha==oldsha and newfields['b']=='7z020clg400'
    # Packaging fix changed board definition lookup, not routed configuration bits.
    write(OUT/'bit_configuration_comparison.json',dict(configuration_payload_equal=True,configuration_sha256=payloadsha,first_bit_fields=oldfields,release_fields=newfields,first_bit_retained=True))
    code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    PKG.mkdir();payload=PKG/'payload';payload.mkdir()
    for p in (ROOT/'single_repair/board').iterdir():
        if p.is_file():cp(p,payload/p.name)
    for src,name in [(release['bit']['path'],'single_repair.bit'),(release['hwh']['path'],'single_repair.hwh'),
        ('D:/PLD/tmp/single_repair_ip_r1/drivers/valley_repair_v1_0/src/xvalley_repair_hw.h','registers.h'),
        (OUT/'frozen_algorithm.json','frozen_algorithm.json'),(OUT/'input/source_manifest.json','input_source_manifest.json'),
        (OUT/'physical_gates.json','physical_gates.json')]:cp(src,payload/name)
    for name in ['Single_Image_Repair_Operator.ipynb','BOARD_STEPS.md','verify_download.py']:cp(ROOT/'single_repair'/name,PKG/name)
    # Validate board-file code syntactically; no import of PYNQ, no hardware.
    for p in payload.glob('*.py'):ast.parse(p.read_text(encoding='utf8'),filename=str(p))
    nb=json.loads((PKG/'Single_Image_Repair_Operator.ipynb').read_text(encoding='utf8'))
    for c in nb['cells']:
        if c['cell_type']=='code':ast.parse(''.join(c['source']))
    assert all(c.get('execution_count') is None for c in nb['cells'])
    with np.load(OUT/'selected/arrays.npz') as a:
        expected=np.load(payload/'native_expected.npy');n=512*512
        assert np.array_equal((expected[5*n:6*n].reshape(512,512)&1)!=0,a['final'])
        assert np.array_equal(((expected[5*n:6*n].reshape(512,512)>>1)&1)!=0,a['added'])
    manifest=dict(schema='single-image-board-package-v1',algorithm='single-image-vessel-valley-v1',clock_mhz=50,processing_shape=[512,512],
        hardware_release='OFFLINE_PHYSICAL_GATES_PASS',board_status='BOARD_NOT_RUN',implementation_commit=code_commit,
        default_hardware_access=False,expected_arrays='Host verification only; never written to PL',files=entries(payload))
    write(payload/'manifest.json',manifest)
    # Execute the delivered first Notebook cell in an isolated local interpreter.
    command=''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source'])+'\nassert "pynq" not in sys.modules\n'
    r=subprocess.run([sys.executable,'-X','utf8','-B','-c',command],cwd=PKG,text=True,capture_output=True)
    write(OUT/'delivered_interface_test.json',dict(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,hardware_operations=0,scope='Actual packaged first notebook cell only'))
    assert r.returncode==0 and 'OFFLINE_PACKAGE_VERIFIED' in r.stdout,r.stderr
    # No further mutations of payload after successful verification.
    boardzip=archive(PKG)
    write(OUT/'board_release_receipt.json',dict(status='READY_FOR_BOARD_AUTHORIZATION',zip=boardzip,payload_manifest=ref(payload/'manifest.json'),code_commit=code_commit,board_status='BOARD_NOT_RUN'))
    status=dict(status='READY_FOR_BOARD_AUTHORIZATION',VISUAL_REPAIR='SINGLE_IMAGE_REVIEW_COMPLETE_WITH_UNCERTAINTY',
        INTEGER_EQUIVALENCE='PASS',RTL_EQUIVALENCE='PASS',GENERATED_INTEGRATION='PASS',ROUTE='PASS',
        DRC='NO_ERRORS_OR_CRITICAL_WARNINGS;22_REVIEWED_WARNINGS',BOARD='BOARD_NOT_RUN',LATENCY_TARGET='UNSET',
        image='im0324',processing_shape=[512,512],old_pixels=6457,added_pixels=3083,final_pixels=9540,uncertain_pixels=2441,
        old_pixels_deleted=0,software_candidates=11,physical_builds=1,board_operations=0,model_training=0,manual_hints=False,
        implementation_commit=code_commit,previous_projects='READ_ONLY',limitation='No independent GT accuracy or complete topology guarantee; faint ends and intersections remain uncertain.')
    write(OUT/'status.json',status)
    # Compact review: selected images, actual source, receipts and final reports.
    REVIEW.mkdir()
    for p in (ROOT/'single_repair').rglob('*'):
        if p.is_file() and p.suffix in ['.py','.tcl','.hpp','.cpp','.md','.ipynb'] and '__pycache__' not in p.parts:
            cp(p,REVIEW/'source'/p.relative_to(ROOT/'single_repair'))
    for folder in ['selected','evidence','viewer','input']:
        for p in (OUT/folder).iterdir():
            if p.is_file():cp(p,REVIEW/'results'/folder/p.name)
    for p in OUT.glob('*'):
        if p.is_file() and p.suffix in ['.json','.md']:cp(p,REVIEW/'results'/p.name)
    for folder in ['integer','integration','board_unit','board_unit_r2']:
        for p in (OUT/folder).iterdir():
            if p.is_file() and p.suffix in ['.json','.log','.jsonl','.tcl','.sv','.py']:cp(p,REVIEW/'results'/folder/p.name)
    for p in (Path('D:/PLD/tmp/single_repair_ip_r1')/'hdl/verilog').iterdir():
        if p.is_file():cp(p,REVIEW/'generated_rtl'/p.name)
    for p in BUILD.iterdir():
        if p.is_file() and p.suffix in ['.rpt','.tsv','.txt','.xdc'] and p.name not in ['routed_constants_probe_r2.txt','routed_endpoints.txt','routed_boundary_audit.tsv']:
            cp(p,REVIEW/'physical_reports'/p.name)
    cp(release['dcp']['path'],REVIEW/'physical_reports/routed.dcp')
    for p in Path('D:/PLD').glob('single_repair*.log'):
        cp(p,REVIEW/'logs'/p.name) if p.name not in ['single_repair_delivery.log'] else None
    for p in [Path('D:/PLD/tmp/single_repair_rtl_r2/repair_tb.sv'),Path('D:/PLD/tmp/single_repair_rtl_r2/tb_axi_memory.sv'),BUILD/'sim_export/single_repair/xsim/integrated_tb.sv',BUILD/'sim_export/single_repair/xsim/tb_hp0_memory.sv']:
        cp(p,REVIEW/'testbenches'/p.name)
    cp(BD/'synth/single_repair.v',REVIEW/'generated_top/single_repair.v')
    cp(BD/'hdl/single_repair_wrapper.v',REVIEW/'generated_top/single_repair_wrapper.v')
    write(REVIEW/'source_copy_manifest.json',dict(copies=COPIES,implementation_commit=code_commit))
    origins=entries(REVIEW)
    write(REVIEW/'delivery_manifest.json',dict(schema='closed-file-review-v1',implementation_commit=code_commit,
        files=origins,board_package=boardzip,manifest_excludes_itself=True,archive_receipt_outside=True))
    reviewzip=archive(REVIEW)
    # Final receipt is outside both archives, no circular SHA.
    write(OUT/'delivery_receipt.json',dict(board_zip=boardzip,review_zip=reviewzip,status='DELIVERY_SEAL_VERIFIED',board_status='BOARD_NOT_RUN'))
    print(json.dumps(dict(board_zip=boardzip,review_zip=reviewzip,status=status['status']),indent=2))
if __name__=='__main__':main()
