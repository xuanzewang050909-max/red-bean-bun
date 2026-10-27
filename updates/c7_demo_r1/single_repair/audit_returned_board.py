"""Read-only host review of a returned partial capture. No board or model calls."""
from pathlib import Path
import json, hashlib, zipfile, re

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/Gabriel/Downloads/single_image_existing_a980b3cb.zip')
PAYLOAD=Path('D:/PLD/review_packages/C7_SingleImage_Repair_Board_r1/payload')
OUT=ROOT/'results/single_repair_board_audit_r1'
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p):p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=sha(b))
def write(p,o):
    with Path(p).open('x',encoding='utf8') as f:json.dump(o,f,indent=2,ensure_ascii=False,allow_nan=False)
def main():
    OUT.mkdir(exist_ok=False);extract=OUT/'original';extract.mkdir()
    original=SOURCE.read_bytes();(OUT/SOURCE.name).write_bytes(original)
    extracted={}
    with zipfile.ZipFile(SOURCE) as z:
        assert len(z.namelist())==len(set(z.namelist())) and z.testzip() is None
        for info in z.infolist():
            p=Path(info.filename);assert not p.is_absolute() and '..' not in p.parts and ':' not in str(p)
            data=z.read(info);target=extract/p;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(data)
            extracted[info.filename]=dict(bytes=len(data),sha256=sha(data))
    files=lambda n:(extract/n).read_bytes()
    load=lambda n:json.loads(files(n))
    session=load('board_results_r1/session.json');marker=load('payload/ATTEMPT_STARTED.json')
    assert session==marker and session['manifest_sha256']==sha(files('payload/manifest.json'))
    manifest=load('payload/manifest.json')
    for name in ['manifest.json','board_run.py']:
        assert files('payload/'+name)==(PAYLOAD/name).read_bytes(),name
    assert sha(files('payload/board_run.py'))==manifest['files']['board_run.py']['sha256']
    # Recheck local released bytes against the original frozen manifest, not new expectations.
    for name,r in manifest['files'].items():
        p=(PAYLOAD/name).resolve();assert PAYLOAD in p.parents
        assert p.stat().st_size==r['bytes'] and sha(p.read_bytes())==r['sha256'],name
    runtime=load('board_results_r1/runtime_identity.json');contract=json.loads((PAYLOAD/'runtime_contract.json').read_bytes())
    assert runtime['pynq']=='3.0.1' and runtime['machine']=='armv7l'
    for name in ['Overlay','allocate']:
        for key in ['bytes','sha256']:assert runtime['sources'][name][key]==contract[name][key]
    events=[json.loads(x) for x in files('board_results_r1/events.jsonl').decode().splitlines()]
    expected=['LOAD_METADATA','DOWNLOAD_NEW_OVERLAY','CLOCK_READBACK','ALLOCATE','SYNC_TO_DEVICE']
    for i,label in enumerate(expected):
        assert events[2*i]['event']=='ACCESS_INTENT' and events[2*i+1]['event']=='ACCESS_RETURNED'
        assert events[2*i]['data']['label']==events[2*i+1]['data']['label']==label
    assert len(events)==11 and events[-1]['event']=='ACCESS_INTENT' and events[-1]['data']['label']=='CONTROL_WRITE'
    assert events[-1]['data']['details']==dict(offset=24,value=377815040)
    assert not any(e['data']['label']=='AP_START' for e in events)
    clock=load('board_results_r1/clock.json');assert clock['actual_register_derived_mhz']==50 and clock['metadata_divisor0']*clock['metadata_divisor1']==20
    absent=['FAULT.json','summary.json','smoke_record.json','native_record.json','smoke_actual.npy','native_actual.npy']
    assert all(not (extract/'board_results_r1'/n).exists() for n in absent)
    build=Path('D:/PLD/tmp/single_repair_design_r1')
    topfile=build/'single_repair.srcs/sources_1/bd/single_repair/synth/single_repair.v'
    top=re.search(r'\bmodule single_repair\s*\([\s\S]*?endmodule',topfile.read_text())[0]
    def ports(n):
        m=re.search(r'\b\w+\s+'+n+r'\s*\(([\s\S]*?)\);',top)
        return dict(re.findall(r'\.(\w+)\(([^()]*)\)',m[1]))
    ps=ports('ps7_0');ctl=ports('control_axi');checks=[]
    for name,wire in ctl.items():
        if name.startswith('S00_AXI_'):
            key='M_AXI_GP0_'+name[8:].upper();assert wire==ps[key]
            checks.append(dict(ps_port=key,control_port=name,net=wire,match=True))
    write(OUT/'control_connection_check.json',dict(scope='Existing generated production top only; no new simulation, no live state',top=ref(topfile),connections=checks))
    rec=dict(status='BOARD_ATTEMPT_INCOMPLETE_CONTROL_ACCESS_UNRESOLVED',session=session['session'],source=ref(SOURCE),
        source_identity='MATCHES_RELEASED_MANIFEST_AND_DRIVER',runtime_identity='MATCHES_FROZEN_CONTRACT',
        last_event=events[-1],returned_operations=expected,smoke_allocated_words=6176,smoke_allocation_bytes=24704,
        pointer_value_hex='0x16850000',control_register_offset_hex='0x18',effective_control_address_expected='0x43C00018',
        recorded_ap_start_count=0,completed_smoke_frames=0,completed_native_frames=0,clock=clock,
        absent_files=absent,root_cause='UNDETERMINED',
        uncertainty='Snapshot does not establish writer quiescence. Missing ACCESS_RETURNED does not alone prove the exact bus phase or exclude logging/process interruption.',
        generated_ps_control_connections_checked=len(checks),generated_ps_control_mismatches=0,
        live_board_state='NOT_READ',host_board_commands=0,new_model_forwards=0,new_physical_builds=0,retries=0,
        historical_release_and_failures='UNCHANGED',next_action='Preserve board/kernel; clarify intervening restart/reconnect history before any proposed hardware action')
    write(OUT/'status.json',rec)
    report='''# 单图板测已有记录核验

本包与已发布manifest、board_run.py完全一致；PYNQ 3.0.1 ARM运行库身份一致，会话54a5300886c64d79ae27cd8acf7434af。原ZIP和全部字节已旁路保留。

日志显示新overlay加载已返回，时钟寄存器推导值50MHz，小工作区6176字（24704字节）分配及flush均返回。最后记录为5.41209673秒处写控制偏移0x18，值0x16850000；后续ACCESS_RETURNED缺失。

没有AP_START记录、smoke/native数值输出、完成记录、summary或FAULT。已验证完成帧：小图0、原生图0。不能把缺少FAULT解释为成功，也不能把重复保护本身解释为最初故障。

这次截图中的ALREADY_ATTEMPTED属于后续调用，在加载前被拒绝；更早那次调用已经访问硬件。当前包未证明写入者全部退出，因此不能单凭最后日志断言AXI某个握手信号就是根因；控制调用未返回、日志落盘中断、进程异常等尚不能完全区分。

本机复查同次构建生成顶层：PS GP0到控制互连38个字段连接一致，没有发现新断线。已有软件、RTL、布线结果保留，但不能替代运行中的地址映射、时钟/复位状态证据。未重跑算法、仿真、物理构建或板测。

当前状态：BOARD_ATTEMPT_INCOMPLETE_CONTROL_ACCESS_UNRESOLVED，根因UNDETERMINED。保留ATTEMPT_STARTED.json和board_results_r1，不绕过保护重试，不复位或重载。是否还保有原执行上下文，需要用户说明这次单图尝试之间的板卡/内核重启情况；本轮未读取现场。
'''
    with (OUT/'report.md').open('x',encoding='utf8') as f:f.write(report)
    write(OUT/'delivery_manifest.json',dict(source=ref(SOURCE),extracted=extracted,
        files={p.relative_to(OUT).as_posix():ref(p) for p in sorted(OUT.rglob('*')) if p.is_file()},script=ref(__file__),manifest_excludes_itself=True))
    print(json.dumps({k:rec[k] for k in ['status','session','recorded_ap_start_count','completed_native_frames','root_cause']},ensure_ascii=False))
if __name__=='__main__':main()
