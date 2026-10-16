// HOST ONLY DOM/HTTP fixtures. No real browser rendering or board throughput claim.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2]||'ui_showcase/app.js','utf8').replace(/initialize\(\);\s*$/,'');
function setup(seed=1) {
  let clock=100;
  const nodes={},listeners={},drawn=[];
  function node(id){return nodes[id]||(nodes[id]={value:'',textContent:'',disabled:false,
    options:[], replaceChildren(){this.options=[];}, append(o){this.options.push(o);}, addEventListener(k,fn){(listeners[id] ||= {})[k]=fn;}, classList:{add(){},remove(){},toggle(){},contains(){return false;}},
    parentElement:{classList:{add(){},remove(){}},querySelector(){return {textContent:''};}}});}
  const document={createElement:()=>({}),visibilityState:'visible',getElementById:node,addEventListener:(kind,fn)=>{listeners[kind]=fn;}};
  const ctx=vm.createContext({document,console,Uint8Array,AbortController,navigator:{userAgent:'HOST_ONLY'},
    crypto:{getRandomValues:(a)=>{a.fill(seed);return a;}}, // deliberately no randomUUID on HTTP
    performance:{now:()=>++clock},Date,Math,setTimeout:()=>1,clearTimeout(){},setInterval(){},
    requestAnimationFrame:(fn)=>{clock+=5;fn();},drawn,selection:0});
  vm.runInContext(source,ctx);
  for(const [id,value] of Object.entries({view:'all',image:'im0001',side:'512',threshold:'112',algorithm:'C7',mode:'final','png-profile':'fast',alpha:'65'}))node(id).value=value;
  vm.runInContext(`catalogIds=['im0001','im0002','im0003']; capabilities={session_run_limit:100}; decode=async url=>({url});draw=(canvas,img)=>drawn.push(img.url);drawOverlay=()=>{};`,ctx);
  return {ctx,nodes,listeners,document};
}
function job(annotations={AH:{dice:.6,iou:.4}},bypass=false){
  return {status:'COMPLETED',run_id:'host_run',config_id:'host_config',
    request:{image_id:'im0001',side:512,algorithm:'C7',mode_code:bypass?0:3,threshold:112},
    input:{sha256:'in'},output:{sha256:'out'},png_profile:'fast',
    images:Object.fromEntries((bypass?['original']:['original','enhanced','mask','overlay']).map(k=>[k,{url:k}])),
    quality:{vessel_area_fraction:bypass?null:.05,vessel_pixels:bypass?null:100,fov_pixels:2000,annotations,
      quality_reason:bypass?'Bypass mode has no segmentation mask':'No matching annotation for this image; Dice/IoU are unavailable'},
    timing_ns:{pl_core_frame_ns:3000000,dma_transaction_ns:4000000,inference_ns:30000000},
    evidence:{applied_parameters:{algorithm:'C7',threshold:112,side:512,mode_code:bypass?0:3,task_tag:1},
      hardware_latched_parameter_readback:{pl_core_cycles:300000,pl_drain_cycles:300010},send_bytes:1048576,recv_bytes:1048576,frame_count:1}};
}
(async()=>{
  const a=setup(1),b=setup(2);
  assert.match(vm.runInContext('w5bPageId',a.ctx),/^[a-f0-9]{32}$/);
  assert.notEqual(vm.runInContext('w5bPageId',a.ctx),vm.runInContext('w5bPageId',b.ctx));
  console.log('HOST_CLIENT_PASS insecure_HTTP_page_identity');
  a.ctx.fixture=job();a.ctx.payloads=[];
  vm.runInContext(`api=async(path,body)=>{payloads.push({path,body});return path.endsWith('browser-timing')?{request_to_render_ms:20,browser_actual_fps:null}:fixture;}`,a.ctx);
  assert(await vm.runInContext('runOne(selectionVersion,null)',a.ctx));
  const payload=a.ctx.payloads.at(-1).body;
  assert.equal(payload.visibility,'visible');assert.equal(payload.loop_id,null);
  assert.equal(payload.page_id,vm.runInContext('w5bPageId',a.ctx));assert.equal(payload.output_sha256,'out');
  assert.equal(a.ctx.drawn.length,4);console.log('HOST_CLIENT_PASS same_task_observation_and_panels');
  a.ctx.fixture=job({});vm.runInContext('showMetrics(fixture)',a.ctx);
  assert.equal(a.nodes.quality.textContent,'未评价');assert(a.nodes['quality-detail'].textContent.includes('No matching'));
  a.ctx.fixture=job({},true);a.ctx.drawn.length=0;
  await vm.runInContext('runOne(selectionVersion,null)',a.ctx);
  assert.equal(a.ctx.drawn.length,1);assert.equal(a.nodes.area.textContent,'不适用');
  console.log('HOST_CLIENT_PASS no_GT_and_bypass_clear_metrics');
  const c=setup(3);c.ctx.fixture=job();c.ctx.calls=0;
  vm.runInContext(`api=async(path)=>{if(path==='/api/status')return {service_state:'READY',hardware_state:'IDLE',completed:1,accepted:1,pending:0,run_limit:100};calls++;throw new Error('HOST disconnected');};`,c.ctx);
  await vm.runInContext('run(false)',c.ctx);assert.equal(c.ctx.calls,1);
  await vm.runInContext('run(false)',c.ctx);assert.equal(c.ctx.calls,1);
  assert(vm.runInContext('fault',c.ctx));console.log('HOST_CLIENT_PASS unexpected_error_no_retry');
  vm.runInContext('running=true',b.ctx);b.document.visibilityState='hidden';b.listeners.visibilitychange();
  assert(vm.runInContext('hiddenDuringRequest',b.ctx));console.log('HOST_CLIENT_PASS hidden_frame_tracked');
  const d=setup(4);d.ctx.sent=[];d.ctx.seenNonces=[];
  vm.runInContext(`setTimeout=(fn)=>{fn();return 1;}; api=async(path,body)=> {
    if(path==='/api/status')return {service_state:'READY',hardware_state:'IDLE',completed:sent.length,accepted:sent.length,pending:0,run_limit:100};
    if(path==='/api/runs') {sent.push(body.image_id);seenNonces.push(body.client_nonce);return fixture;}
    return {request_to_render_ms:20,browser_actual_fps:null};
  };`,d.ctx);
  d.ctx.fixture=job();
  await vm.runInContext('runSequence([...catalogIds])',d.ctx);
  assert.deepEqual(Array.from(d.ctx.sent),['im0001','im0002','im0003']);
  assert.equal(new Set(d.ctx.seenNonces).size,3);assert.equal(d.nodes.image.value,'im0003');
  assert.equal(vm.runInContext('completedCount',d.ctx),3); assert(d.nodes['playlist-status'].textContent.includes('3 / 3'));
  await vm.runInContext('navigate(-1)',d.ctx);await vm.runInContext('navigate(1)',d.ctx);
  assert.deepEqual(Array.from(d.ctx.sent),['im0001','im0002','im0003','im0002','im0003']);
  await vm.runInContext('navigate(1)',d.ctx);assert.equal(d.ctx.sent.length,5);
  console.log('HOST_CLIENT_PASS playlist_new_POST_each_image_previous_next_bounds');
  vm.runInContext('completedCount=99',d.ctx);await vm.runInContext('runSequence([...catalogIds])',d.ctx);assert.equal(d.ctx.sent.length,5);
  console.log('HOST_CLIENT_PASS capacity_guard_before_list');
  vm.runInContext('completedCount=5; setTimeout=(fn)=>{looping=false;fn();return 1;};',d.ctx);
  await vm.runInContext('runSequence([...catalogIds])',d.ctx);assert.equal(d.ctx.sent.length,6);
  assert(d.nodes['playlist-status'].textContent.includes('1 / 3'));
  console.log('HOST_CLIENT_PASS stop_between_frames_no_extra_POST');
  d.document.visibilityState='hidden';await vm.runInContext('run()',d.ctx);assert.equal(d.ctx.sent.length,6);
  console.log('HOST_CLIENT_PASS hidden_before_start_no_POST');
  d.document.visibilityState='visible';vm.runInContext('running=true;buttons()',d.ctx);
  for(const id of ['view','image','side','run','previous','next','list-run'])assert(d.nodes[id].disabled);
  await vm.runInContext('navigate(-1)',d.ctx);assert.equal(d.ctx.sent.length,6);
  console.log('HOST_CLIENT_PASS busy_locks_navigation_and_selection');
  vm.runInContext('running=false;catalogIds=[...examples,...Array.from({length:12},(_,i)=>"extra"+i)];',d.ctx);
  d.nodes.view.value='all';vm.runInContext('populateImages()',d.ctx);assert.equal(d.nodes.image.options.length,20);
  d.nodes.view.value='examples';vm.runInContext('populateImages()',d.ctx);assert.equal(d.nodes.image.options.length,8);
  assert(d.nodes.algorithm.disabled);assert.equal(d.nodes.mode.value,'final');assert.equal(d.nodes.threshold.value,'112');
  d.nodes.view.value='functions';vm.runInContext('populateImages()',d.ctx);assert.equal(d.nodes.image.options.length,21);
  assert.equal(d.nodes.image.options.at(-1).value,'im0324_nogt');assert(d.nodes['list-run'].disabled);assert(!d.nodes.algorithm.disabled);
  console.log('HOST_CLIENT_PASS 20_images_8_examples_separate_function_alias');
})().catch(e=>{console.error(e);process.exitCode=1;});
