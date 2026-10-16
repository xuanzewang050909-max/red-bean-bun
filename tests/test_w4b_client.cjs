// HOST ONLY browser-control simulation; never real browser or board timing.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(process.argv[2] || 'ui_w4b/app.js', 'utf8');

async function scenario(failure) {
  const elements = new Map(), events = {}, requests = [], observations = [];
  let clock = 0;
  const element = id => {
    if (elements.has(id)) return elements.get(id);
    const classes = new Set();
    const e = {value: id==='alpha' ? '65' : '', textContent:'', disabled:false, hidden:false, callbacks:{},
      options:[{value:'final'},{value:'bypass'},{value:'gaussian'}],
      classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle:(x,v)=>v?classes.add(x):classes.delete(x)},
      addEventListener:(k,f)=>{e.callbacks[k]=f},append:()=>{},click:()=>{},
      getContext:()=>({drawImage:()=>{},getImageData:()=>({data:new Uint8ClampedArray(16).fill(100)}),putImageData:()=>{}})};
    e.parentElement={classList:e.classList,querySelector:()=>({textContent:''})};elements.set(id,e);return e;
  };
  const document={visibilityState:'visible',getElementById:element,createElement:()=>({}),addEventListener:(k,f)=>{events[k]=f}};
  class Image {
    constructor(){this.naturalWidth=this.naturalHeight=2;}
    set src(value){queueMicrotask(()=> failure==='image' && requests.length===4 ? this.onerror() : this.onload());}
    async decode(){}
  }
  const response = (body,ok=true)=>({ok,status:ok?200:422,json:async()=>body});
  async function fetch(url,options){
    if(url==='/api/capabilities')return response({evidence_kind:'HOST_ONLY_CLIENT_TEST'});
    if(url==='/api/images')return response({images:[{image_id:'im0001'}]});
    if(url==='/api/status')return response({service_state:'READY',hardware_state:'IDLE',completed:requests.length,run_limit:309,pending:0});
    if(url==='/api/runs') {
      const request=JSON.parse(options.body);requests.push(request);
      if(failure==='network' && requests.length===7)throw Error('HOST injected network failure');
      if(failure==='hidden' && requests.length===5){document.visibilityState='hidden';events.visibilitychange();}
      if(failure==='stop' && requests.length===5)element('stop').callbacks.click();
      const job={request:{...request,mode_code:3},run_id:String(requests.length).padStart(32,'0'),config_id:'c'.repeat(64),
        status:'COMPLETED',png_profile:'fast',input:{sha256:'i'},output:{sha256:'o'},
        quality:{vessel_area_fraction:.1,vessel_pixels:1,fov_pixels:10,annotations:{AH:{dice:.5,iou:.3}}},
        timing_ns:{pl_core_frame_ns:3e6,dma_transaction_ns:5e6,inference_ns:34e6},
        evidence:{applied_parameters:{algorithm:'C7',threshold:112,side:512,mode_code:3,task_tag:requests.length},
          hardware_latched_parameter_readback:{pl_core_cycles:300000,pl_drain_cycles:300010},send_bytes:1048576,recv_bytes:1048576,frame_count:requests.length},
        images:Object.fromEntries(['original','enhanced','mask','overlay'].map(k=>[k,{url:'/test/'+k}]))};
      for(const key of ['array_decode_overlay_ns','png_fromarray_ns','png_save_ns','png_file_hash_ns','file_inventory_hash_ns'])job.timing_ns[key]=1e6;
      if(failure==='timeout' && requests.length===4){job.status='RUNNING';clock+=70000;}
      return response(job);
    }
    if(url.endsWith('/browser-timing')) {
      const o=JSON.parse(options.body);observations.push(o);
      if(o.visibility!=='visible')return response({error:'foreground required'},false);
      return response({request_to_render_ms:o.render_done_ms-o.request_start_ms,
        browser_actual_fps:o.loop_index>=2?o.loop_index*1000/(o.render_done_ms-o.loop_start_ms):null});
    }
    throw Error('Unexpected URL '+url);
  }
  const context=vm.createContext({document,Image,fetch,crypto:{getRandomValues:arr=>webcrypto.getRandomValues(arr)},
    performance:{now:()=>++clock},navigator:{userAgent:'HOST_ONLY'},Uint8Array,Uint8ClampedArray,
    requestAnimationFrame:fn=>queueMicrotask(fn),setTimeout,clearTimeout,setInterval:()=>{},queueMicrotask});
  vm.runInContext(source.replace(/initialize\(\);\s*$/, 'globalThis.ready = initialize();'),context);
  await context.ready;
  assert.equal(element('continuous').disabled,false);
  assert.equal(element('algorithm').value,'C7');assert.equal(element('threshold').value,'112');
  for(const id of ['image','side','mode','algorithm','threshold','png-profile'])assert.equal(element(id).disabled,true);
  await element('continuous').callbacks.click();
  const total=requests.length;
  await element('continuous').callbacks.click(); // Never restart on same page, even after an error.
  assert.equal(requests.length,total);
  if(!failure) {
    assert.equal(total,309);assert.equal(observations.length,309);
    assert.match(element('message').textContent,/W4B_BROWSER_COMPLETE/);
    const ids=new Set();let suite;
    requests.forEach((q,i)=>{
      const r=Math.floor(i/103)+1,w=i%103<3,n=w?i%103+1:i%103-2;
      const match=q.client_nonce.match(/^w4b_([a-f0-9]{32})_r([123])_([wm])(\d+)$/);assert.ok(match);
      suite ||= match[1];assert.equal(match[1],suite);assert.equal(match[2],String(r));assert.equal(match[3],w?'w':'m');assert.equal(match[4],String(n));
      assert.equal(q.image_id,'im0001');assert.equal(q.side,512);assert.equal(q.mode,'final');assert.equal(q.png_profile,'fast');
      ids.add(q.client_nonce);const o=observations[i];assert.equal(o.loop_id,w?null:suite+'_r'+r);assert.equal(o.loop_index,w?null:n);assert.equal(o.visibility,'visible');
      assert.ok(o.request_start_ms<=o.result_received_ms && o.result_received_ms<=o.images_decoded_ms && o.images_decoded_ms<=o.render_done_ms);
    });assert.equal(ids.size,309);
  } else {
    assert.equal(total,{hidden:5,stop:5,network:7,image:4,timeout:4}[failure]);
    assert.match(element('message').textContent,/运行停止/);assert.equal(element('continuous').disabled,true);
    assert.doesNotMatch(element('message').textContent,/W4B_BROWSER_COMPLETE/);
  }
  console.log('HOST_CLIENT_PASS',failure||'three_rounds_309_no_randomUUID',total);
}
(async()=>{for(const s of [null,'hidden','stop','network','image','timeout'])await scenario(s)})().catch(e=>{console.error(e);process.exitCode=1});
