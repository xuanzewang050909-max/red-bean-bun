"""Check B imports against untouched pinned PYNQ 3.0.1 namespace sources.

No PYNQ hardware library is stubbed as a successful board import. This is a
source-level export check, separate from runtime driver/HDMI validation.
"""
import argparse
import ast
import json
from pathlib import Path

from check_b_hardware import info,require

ROOT=Path(__file__).resolve().parents[1]
VIDEO='pynq.lib.video'
SNAPSHOT=ROOT/'references/PYNQ/v3.0.1'


def module_file(module):
    path=SNAPSHOT.joinpath(*module.split('.'))
    return path/'__init__.py' if path.is_dir() else path.with_suffix('.py')


def exports(module,seen=None,sources=None):
    seen=set() if seen is None else seen
    sources={} if sources is None else sources
    require(module not in seen,'Cyclic star export: '+module)
    seen=seen|{module};path=module_file(module)
    require(path.is_file(),'Missing pinned module: '+module)
    sources[str(path.relative_to(ROOT)).replace('\\','/')]=info(path)
    tree=ast.parse(path.read_text(encoding='utf-8-sig'));names=set()
    package=module if path.name=='__init__.py' else module.rsplit('.',1)[0]
    pending=list(tree.body)
    while pending:
        node=pending.pop(0)
        if isinstance(node,(ast.If,ast.Try,ast.With)):
            pending.extend(node.body)
            pending.extend(getattr(node,'orelse',[]))
            pending.extend(getattr(node,'finalbody',[]))
            for handler in getattr(node,'handlers',[]):pending.extend(handler.body)
        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name):names.add(target.id)
        elif isinstance(node,ast.Import):
            names.update(a.asname or a.name.split('.')[0] for a in node.names)
        elif isinstance(node,ast.ImportFrom):
            if any(a.name=='*' for a in node.names):
                require(node.level and node.module,'Only pinned relative star imports are supported')
                parent=package.split('.')[:len(package.split('.'))-node.level+1]
                target='.'.join(parent+[node.module])
                names.update(exports(target,seen,sources))
            else:names.update(a.asname or a.name for a in node.names)
    return {n for n in names if not n.startswith('_')}


def check(runner):
    runner=Path(runner);tree=ast.parse(runner.read_text(encoding='utf-8-sig'))
    prepare=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prepare_b')
    imports=[n for n in ast.walk(prepare) if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith(VIDEO)]
    require(imports,'Missing official video imports')
    records=[];sources={};requested=set()
    for node in imports:
        available=exports(node.module,sources=sources)
        for symbol in node.names:
            require(symbol.name!='*' and symbol.name in available,'Missing official export: '+node.module+'.'+symbol.name)
            requested.add(symbol.name)
            records.append({'module':node.module,'symbol':symbol.name,'source':str(module_file(node.module).relative_to(ROOT)).replace('\\','/')})
    require(requested=={'AxiVDMA','VideoOut','HDMIWrapper','VideoMode','PIXEL_BGR'},'Unexpected video driver contract')
    manifest=json.loads((SNAPSHOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    originals={r['path']:{k:r[k] for k in ('bytes','sha256')} for r in manifest['files']}
    for path,recorded in sources.items():
        relative=str((ROOT/path).relative_to(SNAPSHOT)).replace('\\','/')
        require(recorded==originals[relative],'Fixed official import source changed: '+path)
    return {'status':'PASS_PINNED_PYNQ_3_0_1_VIDEO_IMPORT_NAMESPACES','board_status':'NOT_RUN','runner':info(runner),
        'resolved_imports':records,'official_sources':sources,'pynq_commit':manifest['commit'],
        'limit':'Source-level Python export validation; installed board driver binding and display still require board execution'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('runner',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=check(args.runner)
    require(not args.output.exists(),'Preserve earlier import check')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(report['status'],len(report['resolved_imports']),'resolved imports')


if __name__=='__main__':main()
