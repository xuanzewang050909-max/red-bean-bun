"""Audit actual generated RTL runs; incomplete shards can never release a board package."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RANGES = [(1, 3), (3, 5), (5, 7), (7, 9), (9, 11), (11, 13), (13, 15), (15, 18)]


def info(path):
    data = Path(path).read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def require(value, message):
    if not value:
        raise RuntimeError(message)


def check(directory):
    directory = Path(directory)
    compiled = ROOT / 'build/q4d_shard_compile_01'
    vectors = ROOT / 'build/q4d_detector_axis_sim_03'
    generated = ROOT / 'build/q4d_detector_hls_03/solution1/syn/verilog'
    identity = json.loads((compiled / 'source_identity.json').read_bytes())
    expected_sources = set(generated.glob('*.v')) | set(generated.glob('*.dat')) | {
        vectors / 'retina_detector_guard.v', ROOT / 'tests/retina_q4d_detector_shard_tb.sv'}
    require({Path(p) for p in identity} == expected_sources, 'Incomplete compiled source inventory')
    for path, expected in identity.items():
        require(info(path) == expected, 'Compiled source/ROM changed: ' + path)
    require(info(vectors / 'retina_detector_guard.v') == info(ROOT / 'rtl/core/retina_detector_guard.v'), 'Guard changed')
    require(info(compiled / 'retina_q4d_detector_shard_tb.sv') == info(ROOT / 'tests/retina_q4d_detector_shard_tb.sv'), 'Compiled testbench changed')
    original = (ROOT / 'tests/retina_q4d_detector_axis_tb.sv').read_text()
    sharded = (ROOT / 'tests/retina_q4d_detector_shard_tb.sv').read_text()
    # All scoreboarding, reset, framing, observer and stimulus tasks must be identical.
    prefix = original.split('    initial begin\n')[0]
    require(sharded.startswith(prefix.replace('retina_q4d_detector_axis_tb', 'retina_q4d_detector_shard_tb')), 'Shard changed scoreboard/stimulus tasks')
    elaborate = (compiled / 'elaborate.log').read_text(encoding='utf-8-sig')
    require('Built simulation snapshot q4d_detector_shard' in elaborate and 'ERROR:' not in elaborate, 'Elaboration failed')
    manifest = json.loads((vectors / 'vector_manifest.json').read_bytes())
    cases = {c['case']: c for c in manifest['cases']}
    require(set(cases) == set(range(1, 19)), 'Expected eighteen independent vectors')
    for index, case in cases.items():
        require(case['labels_used'] is False, 'Ground truth entered inference vector')
        for kind in ('input', 'expected'):
            path = vectors / f'case_{index:02d}_{kind}.hex'
            words = np.array([int(x, 16) for x in path.read_text().split()], dtype='<u4')
            require(len(words) == case['words'] and hashlib.sha256(words.tobytes()).hexdigest() == case[kind + '_sha256'], 'Independent vector bytes mismatch: ' + str(path))
    copied = list(vectors.glob('*.hex')) + list(generated.glob('*.dat')) + [vectors / 'vector_manifest.json']
    snapshot = compiled / 'xsim.dir/q4d_detector_shard'
    # Vivado rewrites webtalk usage statistics at simulator exit. Those are
    # run telemetry, not the executable/memory/relocation image. Audit every
    # actual snapshot component, explicitly; never mask an RTL/image change.
    snapshot_files = [p for p in snapshot.rglob('*') if p.is_file()
                      and 'webtalk' not in p.relative_to(snapshot).parts
                      and p.suffix not in {'.log', '.wdb'}]
    require({p.relative_to(snapshot).as_posix() for p in snapshot_files} == {
        'Compile_Options.txt', 'xsim.dbg', 'xsim.mem', 'xsim.reloc', 'xsim.rtti',
        'xsim.svtype', 'xsim.type', 'xsim.xdbg', 'xsimk.exe'}, 'Unexpected compiled snapshot inventory')
    launch = json.loads((directory / 'launch.json').read_text(encoding='utf-8-sig'))
    require([(r['first'], r['last']) for r in launch] == RANGES, 'Unexpected shard ranges')
    groups, covered, transitions = [], set(), set()
    for group, (first, last) in enumerate(RANGES, 1):
        folder = directory / f'group_{group:02d}'
        for path in copied:
            require(info(folder / path.name) == info(path), 'Shard vector/ROM mismatch: ' + str(path))
        require(info(folder / 'retina_q4d_detector_shard_tb.sv') == info(compiled / 'retina_q4d_detector_shard_tb.sv'), 'Shard testbench mismatch')
        for path in snapshot_files:
            require(info(folder / 'xsim.dir/q4d_detector_shard' / path.relative_to(snapshot)) == info(path), 'Shard executable image mismatch')
        log_path = folder / 'xsim.log'
        log = log_path.read_text(encoding='utf-8-sig')
        require(not re.search(r'(?im)^\s*(?:Fatal:|ERROR:|FATAL_ERROR|Error:)', log), 'RTL simulator failure: ' + str(folder))
        require(f'Q4D_SHARD_START: first={first} last={last}' in log, 'Wrong runtime range')
        completed = [(int(a), int(b)) for a, b in re.findall(r'Q4D_SHARD_VECTOR_PASS: vector=(\d+) words=(\d+)', log)]
        planned = [(n, cases[n]['words']) for n in range(first, last + 1) if n != 17]
        require(completed == planned, 'Full-word checks incomplete: ' + str(folder))
        observers = re.findall(r'Q4D_ACTUAL_HLS_OBSERVER_PASS: words=(\d+) cfg=([0-9a-f]+) core=(\d+) drain=(\d+) gaps=(\d+) stalls=(\d+)', log)
        require(len(observers) == len(planned), 'Observer coverage incomplete')
        for (n, words), observed in zip(planned, observers):
            count, cfg, core, drain, gaps, stalls = observed
            require(int(count) == words and int(cfg, 16) == (cases[n]['control_word'] | (n << 16)), 'Frame-latched configuration mismatch')
            require(int(drain) - int(core) >= 50 and int(gaps) > 0 and int(stalls) > 0, 'Missing backpressure/input gaps')
        finals = re.findall(r'Q4D_SHARD_PASS: first=(\d+) last=(\d+) frames=(\d+) checked=(\d+)', log)
        require(len(finals) == 1, 'No completed shard marker')
        a, b, frames, checked = map(int, finals[0])
        full_words = sum(w for _, w in planned)
        require((a, b, frames) == (first, last, len(planned)), 'Final shard counts mismatch')
        partial = checked - full_words
        if first <= 17 <= last:
            require('Q4D_SHARD_ABORT_RESET_PASS: vector=17' in log and 0 <= partial < cases[17]['words'], 'Missing interrupted/reset recovery')
        else:
            require(partial == 0, 'Unexplained extra checked words')
        covered.update(n for n, _ in planned)
        transitions.update((n, n + 1) for n in range(first, last))
        groups.append(dict(first=first, last=last, completed_frames=frames, full_words=full_words, aborted_partial_words=partial, log=info(log_path)))
    require(covered == set(range(1, 19)) - {17} and transitions == {(n, n + 1) for n in range(1, 18)}, 'Coverage gaps')
    return dict(status='PASS_ACTUAL_C7_RTL_SHARDED_NOT_BOARD', unique_complete_frames=len(covered),
                unique_complete_words=sum(cases[n]['words'] for n in covered),
                repeated_seed_frames=sum(g['completed_frames'] for g in groups) - len(covered),
                total_complete_frames=sum(g['completed_frames'] for g in groups),
                total_complete_words=sum(g['full_words'] for g in groups), groups=groups,
                compiled_sources=identity, compiled_snapshot={p.name:info(p) for p in snapshot_files},
                excluded_mutable_snapshot_data='Simulator logs/waveforms and webtalk usage statistics only; all nine executable/static data components checked.',
                vector_manifest=info(vectors / 'vector_manifest.json'),
                checker=info(__file__), scope='All original adjacent transitions retained; separate groups reset at start. Not one continuous eighteen-case simulator process. Board NOT_RUN.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=ROOT / 'build/q4d_sharded_rtl_02')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = check(args.directory)
    if args.output:
        require(not args.output.exists(), 'Preserve prior audit')
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'compiled_sources', 'groups'}}, indent=2))
