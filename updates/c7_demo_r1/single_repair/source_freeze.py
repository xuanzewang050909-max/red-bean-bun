from identify import *
import cv2, shutil
def main():
    dst=ROOT/'results/single_repair_r1/input';dst.mkdir(exist_ok=False)
    pair=Path(json.loads((OUT/'references.json').read_text())[1]['source']['path'])
    refs=json.loads((OUT/'references.json').read_text())
    assert refs[1]['side']==512 and digest(pair)==refs[1]['source']['sha256']
    with np.load(pair,allow_pickle=False) as d:
        iw=d['input_words'];ow=d['output_words']
    rgb=np.stack([(iw>>s).astype('uint8') for s in (16,8,0)],-1)
    old=((ow>>16)&255)!=0;fov=(iw>>24)!=0
    assert np.array_equal(old,((ow>>24)>=112)&fov)
    np.savez_compressed(dst/'input.npz',rgb=rgb,old=old,fov=fov,input_words=iw,output_words=ow)
    for k,a in [('rgb',rgb),('old_mask',old.astype('uint8')*255),('fov',fov.astype('uint8')*255)]:Image.fromarray(a).save(dst/(k+'.png'))
    usernames=['48b3c53f-a426-4751-ac5c-b361d458b2ae','ae1a498c-023c-4da7-a87c-e51351bf7059','712661c4-72c5-425c-9cf0-19324bcc86d8']
    user=[]
    for i,n in enumerate(usernames):
        p=Path('C:/Users/Gabriel/AppData/Local/Temp')/('codex-clipboard-'+n+'.png')
        shutil.copy2(p,dst/f'user_{i}.png');user.append(dict(path=str(p),sha256=digest(p)))
    shot=np.asarray(Image.open(dst/'user_0.png').convert('RGB'))
    trials=[]
    for side in (256,512):
        base=np.asarray(Image.open(OUT/f'{side}_overlay.png'))
        for size in range(370,377):
            rendered=cv2.resize(base,(size,size),interpolation=cv2.INTER_LINEAR)
            for x in range(5,10):
                for y in range(0,3):
                    target=shot[y:350,x:x+size];r=rendered[:len(target)]
                    if r.shape!=target.shape:continue
                    # Only screenshot identity, not an algorithm or threshold experiment.
                    err=float(np.mean(np.abs(target.astype('float32')-r)))
                    trials.append((err,side,size,x,y))
    best=min(trials);err,side,size,x,y=best
    assert side==512 and err<5,best
    overlay=rgb.copy();overlay[old]=[0,255,0]
    Image.fromarray(overlay).save(dst/'old_overlay.png')
    idp=Path('D:/PLD/retina_c7_structured_refine/results/c7_structured_refine_r1/audit/native_pair_identity.json')
    ident=[a for a in json.loads(idp.read_text()) if a['image_id']=='im0324' and a['size']==512]
    assert len(ident)==1
    report=dict(status='INPUT_IDENTIFIED',image='im0324',processing_shape=[512,512],resampled_for_inference=False,
        old_mask='Real original C7 M7; preserved exactly',label_arrays_read=False,source_pair=refs[1]['source'],
        native_capture=ident[0],identity_record_sha256=digest(idp),user_sources=user,
        screenshot_registration=dict(mean_absolute_rgb_error=err,source_side=side,display_size=size,x_offset=x,y_offset=y,
            visible_area=[x,y,x+size,350],mapping='source_x=(screenshot_x-x_offset)*512/display_size; same for y; display/crop only'),
        budget=dict(software_max_candidates=20,physical_max_builds=3,board_operations=0),
        old_research='Paused by new scope; no active old research process at start',
        caveat='Screenshot is scaled/cropped display. Native inputs and M7 are authoritative; no manual ground-truth mask loaded.')
    (dst/'source_manifest.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(registration=best,geometry=ident[0]['geometry'],input_sha256=digest(dst/'input.npz'))))
if __name__=='__main__':main()
