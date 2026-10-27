"""Read-only public snapshot byte/optional syntax audit. No imports of project code."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--syntax',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    update=json.loads((root/'PUBLICATION_UPDATE_2026-10-28.json').read_bytes())
    count=0
    for name,expected in update['files'].items():
        path=(root/name).resolve()
        assert root in path.parents,name
        data=path.read_bytes()
        assert dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())==expected,name
        if args.syntax and path.suffix=='.py':
            ast.parse(data,filename=name,feature_version=(3,10));count+=1
        if args.syntax and path.suffix=='.ipynb':
            for cell in json.loads(data)['cells']:
                assert not cell.get('outputs'),name
                if cell['cell_type']=='code':
                    compile(''.join(cell['source']),name,'exec',flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    forbidden={'.npy','.npz','.png','.jpg','.jpeg','.ppm','.tif','.tiff','.zip'}
    for path in (root/'updates/c7_demo_r1').rglob('*'):
        assert not path.is_file() or path.suffix.lower() not in forbidden,path
    print(json.dumps(dict(status='PUBLICATION_BYTES_VERIFIED',files=len(update['files']),
                          python_syntax_files=count,hardware_operations=0,inference=0)))


if __name__=='__main__':main()
