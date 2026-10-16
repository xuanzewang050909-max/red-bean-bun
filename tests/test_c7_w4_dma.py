"""HOST only: real official channel methods, simulated MMIO/DDR, fault injection."""
import ast
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from dma_bench import board as b
from dma_bench.common import info, validate, write_json
from scripts.verify_c7_w4_dma import audit
RELEASE=Path(os.environ.get('W4C_TEST_RELEASE', str(ROOT/'build/deploy/c7_w4_dma_r1')))


def channel_class():
    p=ROOT/'references/PYNQ/v3.0.1/pynq/lib/dma.py'
    node=next(n for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.ClassDef) and n.name=='_SDMAChannel')
    scope={'DMA_TYPE_RX':0,'DMA_TYPE_TX':1}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),scope)
    return scope['_SDMAChannel']


class Buffer(np.ndarray):
    def __new__(cls, shape, dtype, address, owner, role):
        o=np.empty(shape,dtype).view(cls);o.physical_address=address;o.owner=owner;o.role=role;o.freed=False
        return o
    def flush(self):self.owner.calls.append(self.role+'.flush')
    def invalidate(self):
        self.owner.calls.append(self.role+'.invalidate')
        self[:]=self.owner.pending
    def freebuffer(self):
        self.owner.calls.append(self.role+'.free')
        if self.owner.fault=='free':raise RuntimeError('HOST free failure')
        self.freed=True


class MMIO:
    def __init__(self, owner):self.owner=owner;self.r={4:3,0x34:3}
    def read(self,offset):return self.r.get(offset,0)
    def write(self,offset,value):
        self.r[offset]=value
        if offset in (0,0x30):self.r[offset+4]=2 if value else 3
        if offset in (0x28,0x58):self.owner.calls.append('tx.transfer' if offset==0x28 else 'rx.transfer')
        if offset==0x28:
            self.owner.pending=np.asarray(self.owner.buffers[-2]).copy()
            if self.owner.fault=='corrupt':self.owner.pending[0]^=1
            if self.owner.fault=='bytes':self.r[0x58]-=4
            if self.owner.fault=='dma_error':self.r[0x34]=0x42


class DMA:
    __module__='pynq.lib.dma'
    def __init__(self,owner):
        self.mmio=MMIO(owner);cls=channel_class()
        self.sendchannel=cls(self.mmio,(1<<23)-1,8,1,False)
        self.recvchannel=cls(self.mmio,(1<<23)-1,4,0,False)


class Host:
    def __init__(self,fault=None):self.fault=fault;self.buffers=[];self.calls=[];self.loads=0
    def allocate(self,shape,dtype):
        role='tx' if len(self.buffers)%2==0 else 'rx'
        if self.fault=='allocation' and role=='rx':raise MemoryError('HOST allocation failure')
        addr=0x10000000+(0x200000 if role=='rx' else 0)
        if self.fault=='alignment':addr+=4
        if self.fault=='overlap':addr=0x10000000
        v=Buffer(shape,dtype,addr,self,role);self.buffers.append(v);return v
    def modules(self):
        root=types.ModuleType('pynq');root.__version__='3.0.1';root.allocate=self.allocate
        lib=types.ModuleType('pynq.lib');dma=types.ModuleType('pynq.lib.dma');dma.DMA=DMA
        buf=types.ModuleType('pynq.buffer');ov=types.ModuleType('pynq.overlay')
        for m,rel in [(dma,'lib/dma.py'),(buf,'buffer.py'),(ov,'overlay.py')]:m.__file__=str(ROOT/'references/PYNQ/v3.0.1/pynq'/rel)
        host=self
        class Overlay:
            def __init__(self,path,download=False):
                assert not download
                expected={'c_include_sg':0,'c_micro_dma':0,'c_include_mm2s':1,'c_include_s2mm':1,'c_sg_length_width':23,
                    'c_m_axi_mm2s_data_width':64,'c_m_axi_s2mm_data_width':32,'c_m_axis_mm2s_tdata_width':32,'c_s_axis_s2mm_tdata_width':32}
                self.ip_dict={'axi_dma_0':dict(parameters=expected,phys_addr=0x40400000,type='xilinx.com:ip:axi_dma:7.1')}
            def download(self):host.loads+=1
            @property
            def axi_dma_0(self):return DMA(host)
            def is_loaded(self):return host.fault!='overlay'
        root.Overlay=Overlay;root.lib=lib;lib.dma=dma;root.buffer=buf;root.overlay=ov
        return {'pynq':root,'pynq.lib':lib,'pynq.lib.dma':dma,'pynq.buffer':buf,'pynq.overlay':ov}


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='w4c_HOST_');self.path=Path(self.temp.name)
        self.root=self.path/'package';shutil.copytree(RELEASE/'package',self.root)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close);self.addCleanup(self.temp.cleanup)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(b.original.platform,'system',return_value='Linux'))
        self.stack.enter_context(patch.object(b.original.platform,'machine',return_value='armv7l'))
        self.sock=self.stack.enter_context(patch.object(b.socket,'socket'))
        self.sock.return_value.__enter__.return_value.connect_ex.return_value=111
        self.stack.enter_context(patch.object(b.shutil,'disk_usage',return_value=types.SimpleNamespace(free=3*1024**3)))
    def prepared(self,fault=None):
        h=Host(fault);self.stack.enter_context(patch.dict(sys.modules,h.modules()))
        c=b.prepare(self.root);c['report']['evidence_kind']='HOST_TEST_DOUBLE_NOT_BOARD';b.save(c)
        return h,c
    def loaded(self,fault=None):
        h,c=self.prepared(fault);b.load(c);return h,c
    def test_release_pair_and_syntax(self):
        m=validate(self.root);self.assertEqual(len(m['artifacts']),7)
        import zipfile,hashlib
        z=RELEASE/'upload/c7_w4_dma_r1.zip'
        nb=json.loads((RELEASE/'upload/c7_w4_dma.ipynb').read_bytes())
        codes=[c for c in nb['cells'] if c['cell_type']=='code']
        self.assertEqual(len(codes),7);self.assertIn(hashlib.sha256(z.read_bytes()).hexdigest(),''.join(codes[0]['source']))
        for p in self.root.rglob('*.py'):ast.parse(p.read_bytes(),feature_version=(3,10))
        self.assertEqual(set(zipfile.ZipFile(z).namelist()),set(m['artifacts'])|{'w4c_manifest.json'})
    def test_precheck_no_download_and_single_load(self):
        h,c=self.prepared();self.assertEqual(h.loads,0);self.assertEqual(h.buffers,[])
        b.load(c);self.assertEqual(h.loads,1)
        with self.assertRaises(ValueError):b.load(c)
        self.assertEqual(h.loads,1)
    def test_active_service_rejected_before_hardware(self):
        self.sock.return_value.__enter__.return_value.connect_ex.return_value=0
        with self.assertRaisesRegex(ValueError,'8090'):b.prepare(self.root)
        self.assertFalse((self.root/'w4c_results').exists())
    def test_corrupt_package_rejected(self):
        (self.root/'a0_dma.hwh').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'mismatch'):b.prepare(self.root)
    def test_fresh_results_required(self):
        self.prepared()
        with self.assertRaises(FileExistsError):b.prepare(self.root)
    def test_cache_order_and_raw_smoke(self):
        h,c=self.loaded();b.smoke(c)
        self.assertEqual(h.calls,['rx.flush','rx.transfer','tx.flush','tx.transfer','rx.invalidate','rx.free','tx.free'])
        self.assertEqual(c['retained'],[]);self.assertEqual(len(c['report']['rows']),1)
        self.assertEqual(np.load(c['output']/'raw/0001.npy').size,17)
    def test_faults_retain_stop_no_retry(self):
        for fault in ('allocation','alignment','overlap','corrupt','bytes','dma_error','free','overlay'):
            with self.subTest(fault=fault):
                # Separate output directory for every failure, no reset of failed context.
                self.root=self.path/fault;shutil.copytree(RELEASE/'package',self.root)
                h,c=self.loaded(fault)
                with self.assertRaises((ValueError,RuntimeError,MemoryError)):b.smoke(c)
                self.assertEqual(c['report']['state'],'FAILED_OR_INTERRUPTED')
                before=len(h.calls)
                with self.assertRaises(ValueError):b.smoke(c)
                with self.assertRaises(ValueError):b.finish_export(c)
                self.assertEqual(len(h.calls),before);self.assertEqual(h.loads,1)
                if fault!='overlay':self.assertGreater(len(c['retained']),0)
    def test_timeout_retains_both_buffers(self):
        h,c=self.loaded()
        with patch.object(b.original,'wait_both_idle',side_effect=TimeoutError('HOST timeout')):
            with self.assertRaises(TimeoutError):b.smoke(c)
        self.assertEqual(len(c['retained']),2);self.assertFalse(any(x.freed for x in h.buffers))
    def test_order_gate(self):
        _,c=self.loaded()
        with self.assertRaises(ValueError):b.measure(c,512)
        self.assertEqual(c['report']['state'],'LOAD_PASS')
    def test_full_six_groups_and_independent_rejection(self):
        h,c=self.loaded();b.smoke(c);b.measure(c,256);b.measure(c,512)
        archive=Path(b.finish_export(c));self.assertEqual(h.loads,1)
        self.assertEqual(c['report']['state'],'CLOSED_IDLE');self.assertEqual(len(c['report']['rows']),619)
        self.assertEqual(len(c['report']['summary']['groups']),6)
        self.assertTrue(all(x.freed for x in h.buffers));self.assertEqual(c['retained'],[])
        nb=json.loads((RELEASE/'upload/c7_w4_dma.ipynb').read_bytes())
        codes=[x for x in nb['cells'] if x['cell_type']=='code']
        markers=['PACKAGE_PASS','PRECHECK_PASS','LOAD_PASS','SMOKE_PASS','256_COMPLETE','512_COMPLETE','CLOSED_IDLE\nW4C_RESULTS_READY']
        for i,(cell,marker) in enumerate(zip(codes,markers),1):
            cell['execution_count']=i;cell['outputs']=[dict(output_type='stream',name='stdout',text=['W4C_'+marker+'\n'])]
        executed=self.path/'executed.ipynb';write_json(executed,nb)
        with self.assertRaisesRegex(ValueError,'HOST'):
            audit(archive,executed,RELEASE,self.path/'host_rejected')
        # Synthetic parser fixture ONLY, not retained or reported as board proof.
        import zipfile,hashlib
        with zipfile.ZipFile(archive) as z:data={n:z.read(n) for n in z.namelist()}
        r=json.loads(data['report.json']);r['evidence_kind']='PYNQ_PL_DMA'
        data['report.json']=json.dumps(r).encode()
        m=json.loads(data['bundle_manifest.json']);m['files']['report.json']=dict(bytes=len(data['report.json']),sha256=hashlib.sha256(data['report.json']).hexdigest())
        data['bundle_manifest.json']=json.dumps(m).encode()
        fixture=self.path/'SYNTHETIC_PARSER_FIXTURE.zip'
        with zipfile.ZipFile(fixture,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            for n,v in data.items():z.writestr(n,v)
        result=audit(fixture,executed,RELEASE,self.path/'synthetic_parser_only')
        self.assertEqual(result['words'],101253137)
        r['rows'][1]['transaction_ns']+=1
        data['report.json']=json.dumps(r).encode();m['files']['report.json']=dict(bytes=len(data['report.json']),sha256=hashlib.sha256(data['report.json']).hexdigest());data['bundle_manifest.json']=json.dumps(m).encode()
        tampered=self.path/'SYNTHETIC_BAD_TIMING.zip'
        with zipfile.ZipFile(tampered,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            for n,v in data.items():z.writestr(n,v)
        with self.assertRaisesRegex(ValueError,'Timing formula'):
            audit(tampered,executed,RELEASE,self.path/'tamper_rejected')


if __name__=='__main__':unittest.main(verbosity=2)
