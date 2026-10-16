// HOST ONLY VM tests: no board or browser performance conclusions.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2]||'ui_w5a/app.js','utf8').replace(/initialize\(\);\s*$/,'');
async function scenario(failure) {
  let clock=0;
  const elements={};
  const document={visibilityState:'visible',addEventListener(){},getElementById(id){
    return elements[id]||(elements[id]={value:'',disabled:false,textContent:'',classList:{toggle(){},contains(){return false;}}});
  }};
  const context=vm.createContext({document,console,crypto:{randomUUID:()=> 'host-test-suite'},
    performance:{now:()=>clock},setTimeout:(f,ms)=>{clock+=ms;f();return 0;},clearTimeout(){},
    AbortController,setInterval(){},navigator:{userAgent:'HOST'},advance:()=>{clock+=20;},failure});
  vm.runInContext(source,context);
  vm.runInContext(`capabilities={w5a:{images:Array.from({length:20},(_,i)=>'im'+i)}};
    globalThis.calls=[];api=async()=>({completed:0,accepted:0});
    runOne=async()=>{
      if(failure==='error' && calls.length===7) throw new Error('HOST failure');
      calls.push({image:el('image').value,side:el('side').value,threshold:el('threshold').value,position:w5Position});
      if(failure==='hidden' && calls.length===7) document.visibilityState='hidden';
      advance();return true;
    };`,context);
  await vm.runInContext('run(true)',context);
  const count=context.calls.length;
  if(!failure){
    assert.equal(count,1000);assert(clock>=1800000);
    for(let i=0;i<1000;i++){
      const b=Math.floor(i/10),r=context.calls[i];
      assert.equal(r.position,i);assert.equal(r.image,'im'+(b%20));
      assert.equal(Number(r.side),Math.floor(b/20)%2?256:512);assert.equal(Number(r.threshold),[96,112,128][b%3]);
    }
    assert(elements.message.textContent.includes('W5A_BROWSER_COMPLETE'));
  }else{assert.equal(count,7);assert(elements.message.textContent.includes('停止'));}
  await vm.runInContext('run(true)',context);assert.equal(context.calls.length,count,'No automatic or manual restart of used suite');
}
(async()=>{for(const kind of [null,'error','hidden']){await scenario(kind);console.log('HOST_CONTROLLER_PASS',kind||'1000_schedule');}})().catch(e=>{console.error(e);process.exitCode=1;});
