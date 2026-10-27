"""Verify original archive mapping and offline production display path."""
from identify import *
import tarfile,gzip,io,cv2,importlib.util
def main():
    tar=Path('D:/PLD/retina_fpga/data/raw/stare/stare-images.tar')
    dm=json.loads(tar.with_name('download_manifest.json').read_text())
    expected=next(x for x in dm['files'] if x['name']==tar.name)
    assert tar.stat().st_size==expected['bytes'] and sha(tar)==expected['sha256']
    dst=OUT/'display_audit';dst.mkdir(exist_ok=False)
    rows=[]
    with tarfile.open(tar) as archive:
        for name in IDS:
            data=gzip.decompress(archive.extractfile(name+'.ppm.gz').read())
            native=np.array(Image.open(io.BytesIO(data)).convert('RGB'))
            assert native.shape==(605,700,3)
            with np.load(OUT/'input'/f'{name}.npz') as a:rgb=a['rgb'];old=a['old'];ow=a['output_words']
            mapped=np.zeros_like(rgb);mapped[34:477]=cv2.resize(native,(512,443),interpolation=cv2.INTER_LINEAR)
            assert np.array_equal(mapped,rgb),name
            # Exact current service.py presentation formula, verified against its source below.
            mask=((ow>>16)&255).astype('uint8');sel=mask!=0
            shown=rgb.copy();shown[sel]=((35*rgb[sel].astype('uint16')+np.array([0,16575,0],np.uint16)+50)//100).astype('uint8')
            assert np.array_equal(sel,old)
            assert np.all(np.any(shown[sel]!=rgb[sel],axis=1))
            assert np.array_equal(shown[~sel],rgb[~sel])
            Image.fromarray(native).save(dst/f'{name}_native.png');Image.fromarray(shown).save(dst/f'{name}_production_overlay.png')
            Image.fromarray(mask).save(dst/f'{name}_production_mask.png')
            rows.append(dict(id=name,native_ppm_sha256=hashlib.sha256(data).hexdigest(),mapping_differences=0,mask_differences=0,hidden_mask_pixels=0,old_pixels=int(old.sum())))
    service=ROOT/'single_repair/c7_web/pynq_showcase/service.py'
    source=service.read_text();assert 'mask = ((output >> 16) & 255).astype(np.uint8)' in source
    assert '((35 * rgb[selected].astype(np.uint16) + np.array([0, 16575, 0], np.uint16) + 50) // 100).astype(np.uint8)' in source
    (dst/'receipt.json').write_text(json.dumps(dict(status='ARCHIVE_MAPPING_AND_DISPLAY_FORMULA_EXACT',source_archive=ref(tar),service=ref(service),frames=rows,
      scope='Offline current renderer source and archived genuine PL words; no new browser capture or board execution. Missing vessels are also absent from the native old masks; no display correction counted as recognition improvement.'),indent=2))
    print(rows)
if __name__=='__main__':main()
