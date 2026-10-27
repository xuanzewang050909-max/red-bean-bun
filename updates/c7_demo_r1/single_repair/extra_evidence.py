from software import *
import hashlib
dst=OUT/'evidence';dst.mkdir(exist_ok=True)
rgb=np.asarray(Image.open(OUT/'input/rgb.png'));old=np.asarray(Image.open(OUT/'input/old_mask.png'))>0
source=np.asarray(Image.open(OUT/'input/user_0.png').convert('RGB'))
rows=[]
for i in (1,2):
    crop=np.asarray(Image.open(OUT/'input'/f'user_{i}.png').convert('RGB'))
    score=cv2.matchTemplate(source,crop,cv2.TM_SQDIFF_NORMED)
    minimum,_,xy,_=cv2.minMaxLoc(score);x,y=xy;h,w=crop.shape[:2]
    # These windows are for display registration only, never algorithm coordinates.
    rows.append(dict(example=i,screenshot_rectangle=[x,y,x+w,y+h],normalized_squared_error=minimum,
        native_rectangle=[(x-7)*512/373,(y-1)*512/373,(x+w-7)*512/373,(y+h-1)*512/373],purpose='display only'))
(dst/'example_registration.json').write_text(json.dumps(rows,indent=2))
with np.load(OUT/'selected/arrays.npz') as a:
    final=a['final'];add=a['added'];unc=a['uncertain']
for row in rows:
    box=tuple(int(round(x)) for x in row['native_rectangle'])
    panel([Image.fromarray(a).crop(box).resize(((box[2]-box[0])*2,(box[3]-box[1])*2),Image.Resampling.NEAREST) for a in [rgb,overlay(rgb,old,np.zeros_like(old)),overlay(rgb,old,add,True)]],['Native RGB','Original C7','Green=old Cyan=added'],dst/('user_example_'+str(row['example'])+'.png'))
assert np.array_equal(final,old|add) and not np.any(old&~final) and not np.any(old&add)
u=rgb.copy();u[unc]=[255,60,210];Image.fromarray(u).save(dst/'uncertainty_overlay.png')
stats=dict(old_preserved=int(old.sum()),old_removed=0,added=int(add.sum()),final=int(final.sum()),uncertain=int(unc.sum()),
           no_GT_arrays_loaded=True,no_quality_accuracy_claim=True,manual_points=False,regional_parameters=False,
           software_candidate_count=11,software_routes=1,refinement_rounds=2,software_budget_closed=True,
           complete_model_forwards=0,training_updates=0,board_accesses=0)
(dst/'add_only_check.json').write_text(json.dumps(stats,indent=2))
print(rows,stats)
