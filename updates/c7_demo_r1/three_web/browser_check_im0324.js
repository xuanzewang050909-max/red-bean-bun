async page => {
  if (new URL(page.url()).hostname !== '127.0.0.1') throw new Error('HOST_ONLY');
  await page.setViewportSize({width:1920,height:1080});
  const rows=[];
  const status=()=>page.evaluate(async()=>await(await fetch('/api/status',{cache:'no-store'})).json());
  const read=()=>page.evaluate(()=>({
    title:document.getElementById('selection-state').textContent,
    pixels:document.getElementById('area-detail').textContent,
    mask_pixels:[...document.getElementById('mask').getContext('2d').getImageData(0,0,512,512).data].filter((v,i)=>i%4===0 && v>0).length,
    badge:!document.getElementById('optimized-badge').hidden,
    pane_count:document.querySelectorAll('#panels article').length,
    message:document.getElementById('message').textContent,
    refine_enabled:!document.getElementById('refine').disabled
  }));
  const expect=(value,message)=>{if(!value)throw new Error(message);};
  for (const [id,oldCount,newCount] of [['im0324',6457,9540]]) {
    await page.locator('#image').selectOption(id);
    expect(await page.locator('#refine').isDisabled(),'Cannot refine another image before original');
    await page.locator('#run').click();
    await page.waitForFunction(()=>!document.getElementById('refine').disabled);
    const original=await read();const before=await status();
    expect(original.mask_pixels===oldCount && !original.badge && original.pane_count===4,'Original display mismatch '+id);
    await page.screenshot({path:'build/preview/im0324_staged_r4/'+id+'_original_desktop.png'});
    if(id==='im0324') {
      const originalDownload=page.waitForEvent('download');
      await page.locator('#export-run').click();
      await (await originalDownload).saveAs('build/preview/im0324_staged_r4/HOST_original_only.zip');
    }
    await page.locator('#refine').click();
    await page.waitForFunction(()=>document.getElementById('selection-state').textContent.includes('改进版 C7') && !document.getElementById('show-original').disabled);
    const improved=await read();const after=await status();
    expect(improved.mask_pixels===newCount && improved.badge && improved.pane_count===4,'Improved display mismatch '+id);
    expect(after.accepted===before.accepted+1,'Wrong refinement request count');
    await page.screenshot({path:'build/preview/im0324_staged_r4/'+id+'_improved_desktop.png'});
    const requests=[];const onRequest=req=>{if(req.method()!=='GET')requests.push({url:req.url(),method:req.method()});};
    page.on('request',onRequest);
    await page.locator('#show-original').click();
    await page.waitForFunction(()=>!document.getElementById('show-improved').disabled);
    const originalAgain=await read();
    await page.locator('#show-improved').click();
    await page.waitForFunction(()=>!document.getElementById('show-original').disabled);
    const improvedAgain=await read();const switched=await status();
    page.off('request',onRequest);
    expect(originalAgain.mask_pixels===oldCount && improvedAgain.mask_pixels===newCount,'Switch mismatch');
    expect(switched.accepted===after.accepted && requests.length===0,'Switch submitted work');
    rows.push({id,original,improved,accepted_after:after.accepted,switch_posts:requests.length,accepted_after_switch:switched.accepted});
  }
  const downloadPromise=page.waitForEvent('download');
  await page.locator('#export-session').click();
  const download=await downloadPromise;
  await download.saveAs('build/preview/im0324_staged_r4/HOST_browser_session.zip');
  expect(download.suggestedFilename().startsWith('HOST_TEST_'),'Host evidence marker absent');
  const lists=[];
  for(const view of ['all','examples','functions']) {
    await page.locator('#view').selectOption(view);
    const ids=await page.locator('#image option').evaluateAll(options=>options.map(o=>o.value));
    expect(ids.length===(view==='examples'?10:20),'Unexpected catalog count');
    expect(!ids.some(id=>id.includes('nogt')) && ids.filter(id=>id==='im0324').length===1,'Duplicate/test image visible');
    lists.push({view,ids});
  }
  await page.locator('#image').selectOption('im0324');
  expect(await page.locator('#comparison-controls').isVisible(),'im0324 controls missing');
  expect(await page.locator('#refine').isDisabled(),'Start with original after selection change');
  const errors=await page.evaluate(()=>document.getElementById('state').textContent);
  expect(errors==='READY / IDLE','Service failure');
  return {status:'BROWSER_STAGED_FLOW_PASS_NOT_BOARD',rows,lists,export:'build/preview/im0324_staged_r4/HOST_browser_session.zip',scope:'LOCALHOST_TEST_DOUBLE_NO_BOARD'};
}
