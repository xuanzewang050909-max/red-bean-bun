// HOST ONLY DOM/HTTP fixtures. No real browser rendering or board throughput claim.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2]||'ui_w5b/app.js','utf8').replace(/initialize\(\);\s*$/,'');
function setup(seed=1) {
  let clock=100;
  const nodes={},listeners={},drawn=[];
  function node(id){return nodes[id]||(nodes[id]={value:'',textContent:'',disabled:false,
    classList:{add(){},remove(){},toggle(){},contains(){return false;}},
    parentElement:{classList:{add(){},remove(){}},querySelector(){return {textContent:''};}}});}
  const document={visibilityState:'visible',getElementById:node,addEventListener:(kind,fn)=>{listeners[kind]=fn;}};
  const ctx=vm.createContext({document,console,Uint8Array,AbortController,navigator:{userAgent:'HOST_ONLY'},
    crypto:{getRandomValues:(a)=>{a.fill(seed);return a;}}, // deliberately no randomUUID on HTTP
    performance:{now:()=>++clock},Date,Math,setTimeout:()=>1,clearTimeout(){},setInterval(){},
    requestAnimationFrame:(fn)=>{clock+=5;fn();},drawn,selection:0});
  vm.runInContext(source,ctx);
  for(const [id,value] of Object.entries({image:'im0001',side:'512',threshold:'112',algorithm:'C7',mode:'final','png-profile':'fast',alpha:'65'}))node(id).value=value;
  vm.runInContext(`decode=async url=>({url});draw=(canvas,img)=>drawn.push(img.url);drawOverlay=()=>{};`,ctx);
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
  vm.runInContext(`api=async(path)=>{if(path==='/api/status')return {service_state:'READY',hardware_state:'IDLE',completed:1,pending:0,run_limit:42};calls++;throw new Error('HOST disconnected');};`,c.ctx);
  await vm.runInContext('run(false)',c.ctx);assert.equal(c.ctx.calls,1);
  await vm.runInContext('run(false)',c.ctx);assert.equal(c.ctx.calls,1);
  assert(vm.runInContext('fault',c.ctx));console.log('HOST_CLIENT_PASS unexpected_error_no_retry');
  vm.runInContext('running=true',b.ctx);b.document.visibilityState='hidden';b.listeners.visibilitychange();
  assert(vm.runInContext('hiddenDuringRequest',b.ctx));console.log('HOST_CLIENT_PASS hidden_frame_tracked');
})().catch(e=>{console.error(e);process.exitCode=1;});
