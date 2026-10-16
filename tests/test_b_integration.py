"""Host contract/fault tests only. Fake DMA/video is never board evidence."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import b_integration_board_test as runner
import check_b_hardware as hardware
import package_b as package
from a1_point_board_test import notebook_code_hash
import test_a4_board_runner as a4_fixtures
from test_a0_board_runner import Buffer


class FakeOverlay:
    loaded=True
    def is_loaded(self):return self.loaded


class FakeHDMI:
    def __init__(self):self.count=0;self.closed=False;self.fail=False;self.last=None;self.last_buffer=None
    def configure(self,mode,pixel):self.mode=mode
    def start(self):pass
    def newframe(self):
        frame=Buffer((720,1280,3),np.uint8);frame.physical_address=0x14000000
        return frame
    def writeframe(self,frame):
        if self.fail:raise TimeoutError('Synthetic video failure')
        self.count+=1;self.last=np.asarray(frame).copy();self.last_buffer=frame
    def close(self):self.closed=True


class FakeVDMA:
    running=True
    def __init__(self):self.mmio=self;self.writechannel=self;self.error=False
    def read(self,offset):return 0x20 if self.error else 0x1000


class BRunnerTests(unittest.TestCase):
    def context(self,**faults):
        # Existing A4 fixtures and independent golden; never mutate their code.
        fixture=a4_fixtures.SegmentationRunnerTests();self.addCleanup(fixture.doCleanups)
        context,buffers=fixture.context(**faults)
        context['report'].update(status='B_LOADED_NO_TRANSFER',overlay_downloads=1,display={'visual_status':'PENDING_USER_OBSERVATION','submissions':[]})
        context.update(overlay=FakeOverlay(),hdmi_out=FakeHDMI(),display_retained=[],video=type('Video',(),{'axi_vdma':FakeVDMA()})(),
            video_mode_class=lambda *args:args,pixel_bgr='BGR')
        def save():
            (context['directory']/'b_integration_result.json').write_text(json.dumps(context['report']),encoding='utf-8')
        context['save']=save
        return context,buffers

    def test_staged_digital_flow_and_video_ownership(self):
        context,buffers=self.context()
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_b(context);runner.start_hdmi_b(context);runner.full_b(context)
        self.assertEqual(len(context['report']['transfers']),61)
        self.assertEqual(context['report']['status'],'B_61_SEGMENTATION_FRAMES_WITH_HDMI_RUNNING')
        self.assertEqual(context['display_retained'],[])
        self.assertFalse(context['hdmi_out'].last_buffer.freed,'Project must not free submitted VDMA frames')
        self.assertTrue(all(b.freed for b in buffers))
        self.assertEqual(context['report']['display']['visual_status'],'PENDING_USER_OBSERVATION')
        with self.assertRaises(RuntimeError):runner.full_b(context)

    def test_algorithm_faults_retain_buffers_and_block_next_phase(self):
        for fault in ('corrupt','bad_length','counter_error'):
            with self.subTest(fault=fault):
                context,buffers=self.context(**{fault:True})
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(Exception):runner.smoke_b(context)
                self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')
                self.assertEqual(len(context['retained']),2)
                self.assertFalse(any(b.freed for b in buffers))
                with self.assertRaises(RuntimeError):runner.start_hdmi_b(context)

    def test_video_fault_retains_display_frame(self):
        context,_=self.context();context['report']['status']='B_DMA_SMOKE_PASS';context['hdmi_out'].fail=True
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(TimeoutError):runner.start_hdmi_b(context)
        self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')
        self.assertEqual(context['report']['retained_display_frames'],1)
        self.assertFalse(context['display_retained'][0].freed)
        with self.assertRaises(RuntimeError):runner.finish_b(context)

    def test_changed_overlay_blocks_hardware_actions(self):
        context,buffers=self.context();context['overlay'].loaded=False
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):runner.smoke_b(context)
        self.assertEqual(buffers,[])
        self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')

    def test_video_status_detects_error_and_stopped_channel(self):
        context,_=self.context();context['video'].axi_vdma.error=True
        with self.assertRaises(RuntimeError):runner.video_status(context)
        context['video'].axi_vdma.error=False;context['video'].axi_vdma.running=False
        with self.assertRaises(RuntimeError):runner.video_status(context)

    def test_color_order_position_and_real_mask_layout(self):
        pattern=runner.color_pattern()
        np.testing.assert_array_equal(pattern[100,100],[255,0,0])
        np.testing.assert_array_equal(pattern[100,700],[0,255,0])
        np.testing.assert_array_equal(pattern[100,1100],[0,0,255])
        self.assertTrue(np.all(pattern[0]==255) and np.all(pattern[:,640]==255))
        output=np.full((512,512),np.uint32(73),dtype=np.uint32);output[10,15]|=np.uint32(255<<16)
        image=runner.medical_canvas(output)
        np.testing.assert_array_equal(image[138,79],[73,73,73])
        np.testing.assert_array_equal(image[138,719],[0,255,0])
        np.testing.assert_array_equal(image[140,720],[73,73,73])
        output[0,0]|=np.uint32(1<<16)
        with self.assertRaises(RuntimeError):runner.medical_canvas(output)

    def test_reused_bench_buffers_100_timed_plus_3_warmup(self):
        context,buffers=self.context()
        with contextlib.redirect_stdout(io.StringIO()):summary=runner.measure_group(context,256,False)
        self.assertEqual(summary['count'],100)
        self.assertEqual(len(context['report']['transfers']),103)
        self.assertEqual(sum(r['benchmark']['warmup'] for r in context['report']['transfers']),3)
        self.assertEqual(len(buffers),2);self.assertTrue(all(b.freed for b in buffers))
        self.assertGreater(summary['loop_seconds'],0)
        self.assertAlmostEqual(summary['frames_per_sum_transaction_seconds'],100/(sum(summary['samples_ns'])/1e9))
        self.assertEqual(summary['display_refresh_measurement'].split(';')[0],'NOT_MEASURED')

    def test_display_benchmark_counts_official_submissions(self):
        context,_=self.context()
        with contextlib.redirect_stdout(io.StringIO()):summary=runner.measure_group(context,512,True)
        self.assertEqual(context['hdmi_out'].count,103)
        self.assertEqual(context['display_retained'],[])
        self.assertTrue(summary['with_display']);self.assertEqual(summary['count'],100)
        self.assertEqual(context['report']['display']['visual_status'],'PENDING_USER_OBSERVATION')

    def test_bench_failure_keeps_buffers_and_stops_measurements(self):
        context,buffers=self.context(corrupt=True);context['report']['status']='B_MEDICAL_DISPLAY_SUBMITTED'
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(Exception):runner.performance_b(context)
        self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')
        self.assertEqual(len(context['retained']),2);self.assertFalse(any(b.freed for b in buffers))
        self.assertNotIn('performance',context['report'])

    def test_invalid_timing_samples_and_contract(self):
        for data in ([],[0],[-1],[float('nan')],[float('inf')]):
            with self.subTest(data=data),self.assertRaises(RuntimeError):runner.timing_summary(data)
        context,_=self.context()
        with self.assertRaises(RuntimeError):runner.measure_group(context,256,True)
        with self.assertRaises(RuntimeError):runner.measure_group(context,512,False,count=1)

    def test_partial_ledger_cannot_claim_timing_complete(self):
        context,_=self.context();context['report']['status']='B_MEDICAL_DISPLAY_SUBMITTED'
        with patch.object(runner,'measure_group',return_value={'frames_per_sum_transaction_seconds':1,'loop_fps':1}),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):
            runner.performance_b(context)
        self.assertEqual(context['report']['status'],'FAILED_OR_INTERRUPTED')

    def test_complete_measurements_bundle_stays_visual_pending(self):
        context,buffers=self.context()
        display_stub=types.ModuleType('IPython.display');display_stub.display=lambda image:None
        with patch.dict(sys.modules,{'IPython.display':display_stub}),contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_b(context);runner.start_hdmi_b(context);runner.full_b(context)
            runner.display_medical_b(context);runner.performance_b(context);runner.finish_b(context)
        self.assertEqual(len(context['report']['transfers']),370)
        self.assertEqual(sum(r['words'] for r in context['report']['transfers']),70647808)
        self.assertEqual(context['report']['overlay_downloads'],1)
        self.assertEqual(context['report']['status'],'B_RECORDS_READY_VISUAL_REVIEW_PENDING')
        self.assertEqual(context['report']['display']['visual_status'],'PENDING_USER_OBSERVATION')
        self.assertEqual(len(context['report']['performance']),3)
        self.assertTrue(all(x['clock']['monotonic'] for x in context['report']['performance']))
        self.assertTrue(context['hdmi_out'].closed)
        self.assertEqual(context['hdmi_out'].count,105)
        self.assertTrue(all(b.freed for b in buffers))
        from zipfile import ZipFile
        with ZipFile(context['directory']/'b_results_bundle.zip') as archive:
            self.assertEqual(len(archive.namelist()),9)
            report=json.loads(archive.read('b_integration_result.json'))
            self.assertEqual(report['display']['visual_status'],'PENDING_USER_OBSERVATION')

    def test_package_immutable_artifacts_and_mutable_notebook_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);nb=json.loads((ROOT/'notebooks'/runner.NOTEBOOK).read_text(encoding='utf-8'))
            for name in runner.FIXED:(p/name).write_bytes(name.encode())
            (p/runner.NOTEBOOK).write_text(json.dumps(nb),encoding='utf-8')
            manifest={'revision':runner.REVISION,'artifacts':{name:{'sha256':runner.sha256_file(p/name)} for name in runner.FIXED|{runner.NOTEBOOK}},
                'notebook_validation':{'algorithm':'sha256-code-cells-v1','sha256':notebook_code_hash(nb)}}
            runner.validate_b_package(p,manifest)
            for cell in nb['cells']:
                if cell['cell_type']=='code':cell['execution_count']=4;cell['outputs']=[{'name':'stdout','output_type':'stream','text':'HOST SAVE PROBE ONLY\n'}]
            (p/runner.NOTEBOOK).write_text(json.dumps(nb),encoding='utf-8');runner.validate_b_package(p,manifest)
            code=next(c for c in nb['cells'] if c['cell_type']=='code');code['source']=['raise RuntimeError("changed")\n']
            (p/runner.NOTEBOOK).write_text(json.dumps(nb),encoding='utf-8')
            with self.assertRaises(RuntimeError):runner.validate_b_package(p,manifest)
            (p/runner.NOTEBOOK).write_text((ROOT/'notebooks'/runner.NOTEBOOK).read_text(encoding='utf-8'),encoding='utf-8')
            (p/'b_integration.bit').write_bytes(b'wrong')
            with self.assertRaises(RuntimeError):runner.validate_b_package(p,manifest)


class BMetadataTests(unittest.TestCase):
    def candidate(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);p=Path(temp.name);src=ROOT/'build/b_integration_05'
        names=('original_official_system.bd','gaussian_guard_used.v','build_script_used.tcl',
            'b_integration.srcs/sources_1/bd/system/system.bd','b_integration.srcs/sources_1/bd/system/hw_handoff/system.hwh')
        for name in names:
            target=p/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((src/name).read_bytes())
        return p

    def test_actual_generated_metadata_and_official_video_derivation(self):
        result=hardware.check(self.candidate());self.assertEqual(result['video_objects_unchanged'],41)
        self.assertEqual(result['board_status'],'NOT_RUN')

    def test_hwh_dma_address_clock_reset_and_video_irq_tampering_rejected(self):
        for mutation in ('dma','clock','reset','irq'):
            with self.subTest(mutation=mutation):
                p=self.candidate();path=p/'b_integration.srcs/sources_1/bd/system/hw_handoff/system.hwh';t=ET.parse(path)
                modules={m.get('FULLNAME').lstrip('/'):m for m in t.findall('.//MODULE')}
                if mutation=='dma':modules['axi_dma_0'].find("./PARAMETERS/PARAMETER[@NAME='c_include_sg']").set('VALUE','1')
                if mutation=='clock':modules['ps7_0'].find("./PARAMETERS/PARAMETER[@NAME='PCW_S_AXI_HP2_FREQMHZ']").set('VALUE','142')
                if mutation=='reset':modules['reset_100m'].find("./PARAMETERS/PARAMETER[@NAME='C_AUX_RESET_HIGH']").set('VALUE','1')
                if mutation=='irq':
                    port=modules['video/axi_vdma'].find("./PORTS/PORT[@NAME='mm2s_introut']");port.set('SIGNAME','unconnected');port.find('CONNECTIONS').clear()
                t.write(path,encoding='utf-8')
                with self.assertRaises((ValueError,KeyError)):hardware.check(p)

    def test_official_video_config_and_board_ddr_tampering_rejected(self):
        for mutation in ('video','ddr'):
            with self.subTest(mutation=mutation):
                p=self.candidate();path=p/'b_integration.srcs/sources_1/bd/system/system.bd';t=ET.parse(path)
                name='axi_vdma' if mutation=='video' else 'ps7_0'
                node=next(c for c in t.findall('.//s:componentInstance',hardware.NS) if c.findtext('s:instanceName','',hardware.NS)==name)
                key='c_num_fstores' if mutation=='video' else 'PCW_DDR_RAM_HIGHADDR'
                value=next(c for c in node.findall('./s:configurableElementValues/s:configurableElementValue',hardware.NS) if c.get(hardware.SPIRIT+'referenceId')==key)
                value.text='1' if mutation=='video' else '0x0FFFFFFF';t.write(path,encoding='utf-8')
                with self.assertRaises(ValueError):hardware.check(p)


class BReleaseGateTests(unittest.TestCase):
    def inputs(self):
        p=ROOT/'build/b_integration_04'
        return [package.read(p/name) for name in ('timing_summary.rpt','drc.rpt','utilization.rpt')]

    def test_rejected_actual_first_clock_drc_is_not_released(self):
        with self.assertRaisesRegex(ValueError,'DRC error/critical warning'):package.timing_gate(*self.inputs())

    def test_negative_setup_or_hold_rejected_even_with_pass_banner(self):
        for old,new in (('0.407','-0.407'),('0.008','-0.008')):
            with self.subTest(slack=old):
                timing,drc,util=self.inputs();timing=timing.replace(old,new)
                with self.assertRaisesRegex(ValueError,'Timing violation'):package.timing_gate(timing,drc,util)

    def test_missing_internal_constraints_rejected(self):
        timing,drc,util=self.inputs();timing=timing.replace('There are 0 pins that are not constrained for maximum delay.','There are 1 pins that are not constrained for maximum delay.')
        with self.assertRaisesRegex(ValueError,'Missing timing check'):package.timing_gate(timing,drc,util)

    def test_exact_pin_constraint_derivation_and_precise_clock(self):
        source=package.read(ROOT/'references/PYNQ/v2.2.1/boards/Pynq-Z2/base/vivado/constraints/top.xdc')
        target=package.read(ROOT/'build/b_integration_05/constraints_used.xdc')
        self.assertEqual(package.constraints_gate(source,target)['original_gpio_hdmi_pin_assignments_unchanged'],36)
        for changed in (target.replace('PACKAGE_PIN M20','PACKAGE_PIN M18'),target.replace('8.333333','8.334'),
            target+'\nset_false_path -from [get_clocks clk_fpga_0]\n'):
            with self.assertRaisesRegex(ValueError,'Changed retained board pin'):package.constraints_gate(source,changed)


if __name__=='__main__':unittest.main()
