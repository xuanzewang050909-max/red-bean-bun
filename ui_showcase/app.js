"use strict";
// getRandomValues also works on the board's plain HTTP origin.
const w5bPageId = Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, '0')).join('');
const el = id => document.getElementById(id);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const nonce = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
const panes = ["original", "enhanced", "mask", "overlay"];
let capabilities, selectionVersion = 0, currentVersion = -1, running = false, looping = false, fault = false, current = null, currentImages = null;
let hiddenDuringRequest = false;
document.addEventListener("visibilitychange", () => { if (running && document.visibilityState !== "visible") { hiddenDuringRequest = true; looping = false; } });

async function api(path, body) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 60000);
  try {
  const response = await fetch(path, {signal: controller.signal, cache: "no-store", ...(body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})});
  const result = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${result.message || result.error}`);
  return result;
  } finally {clearTimeout(timer);}
}
function message(text, error = false) {
  el("message").textContent = text;
  el("message").classList.toggle("fault-text", error);
}
const examples = ["im0077", "im0081", "im0162", "im0240", "im0001", "im0044", "im0004", "im0324"];
const notes = {
 im0077: "血管分支较清楚：观察主干和分叉；细小分支仍可能漏检。",
 im0081: "观察上下弧形血管走向与叠加对齐。",
 im0162: "观察长血管与多级分叉；对比增强和实际掩膜。",
 im0240: "较暗且亮度不均：观察主干保留及低对比细血管遗漏。",
 im0001: "局部高亮区域：观察已有抑制效果，也展示残余亮区误检。",
 im0044: "大范围明亮区域：观察穿越明亮区域的血管及背景干扰。",
 im0004: "模糊、低对比样例：血管遗漏明显，展示当前局限。",
 im0324: "较亮、细血管低对比：展示短断裂和漏检，不能称连续性已解决。"
};
let catalogIds = [], completedCount = 0;
function activeIds() { return el("view").value === "examples" ? examples : catalogIds; }
function buttons() {
  const locked = !capabilities || running || fault;
  for (const id of ["run", "previous", "next", "continuous"]) el(id).disabled = locked;
  el("list-run").disabled = locked || el("view").value === "functions";
  for (const id of ["view", "image", "side", "png-profile"]) el(id).disabled = locked;
  for (const id of ["algorithm", "mode", "threshold"]) el(id).disabled = locked || el("view").value !== "functions";
  el("previous").disabled = locked || activeIds().indexOf(el("image").value) <= 0;
  el("next").disabled = locked || activeIds().indexOf(el("image").value) < 0 || activeIds().indexOf(el("image").value) >= activeIds().length - 1;
  el("stop").disabled = !looping;
  el("export-run").disabled = !current || currentVersion !== selectionVersion || running || el("panels").classList.contains("stale");
  el("export-session").disabled = !capabilities || running;
}
function populateImages() {
  const previous = el("image").value;
  el("image").replaceChildren();
  const ids = [...activeIds(), ...(el("view").value === "functions" ? ["im0324_nogt"] : [])];
  for (const id of ids) {
    const option = document.createElement("option"); option.value = id;
    option.textContent = id + (id.endsWith("_nogt") ? " · 同图隐藏标注测试" : " · STARE"); el("image").append(option);
  }
  el("image").value = ids.includes(previous) ? previous : ids[0];
  if (el("view").value !== "functions") {
    el("algorithm").value = "C7"; el("mode").value = "final"; el("threshold").value = "112";
    el("threshold-help").textContent = "C7 分数：推荐112；运行写入 PL";
    for (const option of el("mode").options) option.disabled = !["final", "bypass"].includes(option.value);
  }
  changed();
}
function changed() {
  el("example-note").textContent = notes[el("image").value] || (el("image").value.endsWith("_nogt") ? "同一im0324输入隐藏标注，仅验证未评价显示，不是第21张独立图像。" : "自由选择真实图像；本页不预先计算或缓存分割结果。");
  selectionVersion++;
  looping = false;
  el("panels").classList.add("stale");
  el("selection-state").textContent = "选择已更改；下方为历史结果，点击运行更新";
  ["area", "quality", "core", "dma", "inference", "browser", "fps"].forEach(id => el(id).textContent = "—");
  el("area-detail").textContent = "等待当前选择的 PL 结果";
  el("quality-detail").textContent = "等待新帧评分；不沿用上一张图的指标";
  el("applied").textContent = "等待新帧硬件回读";
  el("observer").textContent = "—";
  el("ps-timing").textContent = "—";
  buttons();
}
function decode(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const timer = setTimeout(() => reject(new Error("图像下载超过60秒；保留任务记录")), 60000);
    image.onload = async () => { try { if (image.decode) await image.decode(); resolve(image); } catch (err) { reject(err); } finally {clearTimeout(timer);} };
    image.onerror = () => {clearTimeout(timer);reject(new Error("同帧图像下载失败；保留任务记录"));};
    image.src = url;
  });
}
function draw(canvas, image) {
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.getContext("2d").drawImage(image, 0, 0);
  canvas.parentElement.classList.add("has-image");
}
function drawOverlay() {
  el("alpha-value").textContent = el("alpha").value + "%";
  if (!currentImages || !currentImages.mask) return;
  const target = el("overlay"), context = target.getContext("2d");
  const rgb = el("original").getContext("2d").getImageData(0, 0, target.width, target.height);
  const mask = el("mask").getContext("2d").getImageData(0, 0, target.width, target.height).data;
  const amount = Number(el("alpha").value);
  for (let offset = 0; offset < rgb.data.length; offset += 4) {
    if (mask[offset]) {
      rgb.data[offset] = Math.floor(((100 - amount) * rgb.data[offset] + 50) / 100);
      rgb.data[offset + 1] = Math.floor(((100 - amount) * rgb.data[offset + 1] + amount * 255 + 50) / 100);
      rgb.data[offset + 2] = Math.floor(((100 - amount) * rgb.data[offset + 2] + 50) / 100);
    }
  }
  context.putImageData(rgb, 0, 0); // Display only, using this run's actual PL mask.
}
function showMetrics(job) {
  const quality = job.quality, timing = job.timing_ns;
  el("area").textContent = quality.vessel_area_fraction === null ? "不适用" : (quality.vessel_area_fraction * 100).toFixed(2) + "%";
  el("area-detail").textContent = quality.vessel_pixels === null ? "旁路没有分割掩膜" : `${quality.vessel_pixels.toLocaleString()} / ${quality.fov_pixels.toLocaleString()} 像素 · PS 计数`;
  const scores = Object.entries(quality.annotations).map(([name, values]) => `${name} ${values.dice.toFixed(3)} / ${values.iou.toFixed(3)}`);
  el("quality").textContent = scores.length ? scores.join(" · ") : "未评价";
  el("quality-detail").textContent = scores.length ? "当前帧 Dice / IoU；不是整体质量验收" : quality.quality_reason;
  el("core").textContent = (timing.pl_core_frame_ns / 1e6).toFixed(3) + " ms";
  el("ps-timing").textContent = `${job.png_profile} · 解包/叠加 ${(timing.array_decode_overlay_ns / 1e6).toFixed(1)} ms；PIL 转换 ${(timing.png_fromarray_ns / 1e6).toFixed(1)} ms；PNG 编码及写入 ${(timing.png_save_ns / 1e6).toFixed(1)} ms；PNG 哈希 ${(timing.png_file_hash_ns / 1e6).toFixed(1)} ms；文件清单哈希 ${(timing.file_inventory_hash_ns / 1e6).toFixed(1)} ms`;
  const applied = job.evidence.applied_parameters, observed = job.evidence.hardware_latched_parameter_readback;
  el("applied").textContent = `${applied.algorithm} / T=${applied.threshold} / ${applied.side} / 模式 ${applied.mode_code} / 帧标记 ${applied.task_tag} · 与本次请求一致`;
  el("observer").textContent = `${observed.pl_core_cycles.toLocaleString()} 周期 @ 100 MHz；流出完成 ${observed.pl_drain_cycles.toLocaleString()} 周期；纯 DMA 搬运未测`;
  el("dma").textContent = (timing.dma_transaction_ns / 1e6).toFixed(2) + " ms";
  el("inference").textContent = (timing.inference_ns / 1e6).toFixed(2) + " ms";
  el("browser").textContent = "测量中";
  el("fps").textContent = "—";
  el("identity").textContent = `${job.run_id} / ${job.config_id.slice(0, 16)} · ${job.request.image_id}, ${job.request.side}, ${job.request.algorithm}, mode ${job.request.mode_code}, T=${job.request.threshold}, ${job.request.png_profile}`;
  el("bytes").textContent = `发送 ${job.evidence.send_bytes.toLocaleString()} B / 接收 ${job.evidence.recv_bytes.toLocaleString()} B · PL 帧计数 ${job.evidence.frame_count} · 已核对实际锁存参数 / 标记 / 序号`;
  el("hashes").textContent = `${job.input.sha256} / ${job.output.sha256}`;
}
async function runOne(version, loop) {
  const request = {image_id: el("image").value, side: Number(el("side").value), threshold: Number(el("threshold").value), algorithm: el("algorithm").value,
                   mode: el("mode").value, client_nonce: nonce(), png_profile: el("png-profile").value};
  if (!Number.isInteger(request.threshold) || request.threshold < 1 || request.threshold > 255) throw new Error("阈值必须是 1–255 的整数");
  const start = performance.now();
  hiddenDuringRequest = document.visibilityState !== "visible";
  if (loop && loop.index === 1) loop.start = start;
  message(`提交 ${request.image_id} / ${request.side} / ${request.mode} 至真实 PL…`);
  el("panels").classList.add("stale");
  el("selection-state").textContent = "正在计算；下方保留上一次结果";
  let job = await api("/api/runs", request);
  while (job.status === "QUEUED" || job.status === "RUNNING") {
    if (performance.now() - start > 60000) throw new Error("任务超过60秒；停止请求，保留板端现场");
    await delay(100);
    job = await api("/api/runs/" + job.run_id);
  }
  const received = performance.now();
  if (job.status !== "COMPLETED") throw new Error(job.error ? job.error.message : job.status);
  if (version !== selectionVersion) {
    message(`任务 ${job.run_id.slice(0, 12)} 已完成并保存；选择已更改，未作为当前图显示。`);
    return false;
  }
  const entries = await Promise.all(panes.filter(kind => job.images[kind]).map(async kind => [kind, await decode(job.images[kind].url)]));
  const decoded = performance.now();
  if (version !== selectionVersion) return false;
  currentImages = Object.fromEntries(entries);
  for (const kind of panes) {
    const canvas = el(kind);
    canvas.parentElement.classList.remove("has-image");
    canvas.parentElement.querySelector(".placeholder").textContent = "旁路无此输出";
    if (currentImages[kind]) draw(canvas, currentImages[kind]);
  }
  current = job;
  currentVersion = version;
  drawOverlay();
  showMetrics(job);
  el("panels").classList.remove("stale");
  el("selection-state").textContent = `${request.image_id} · ${request.side} × ${request.side} · 同一任务 ${job.run_id.slice(0, 10)}`;
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const rendered = performance.now();
  if (version !== selectionVersion) return false;
  const observation = {client_nonce: request.client_nonce, config_id: job.config_id,
    input_sha256: job.input.sha256, output_sha256: job.output.sha256,
    request_start_ms: start, result_received_ms: received, images_decoded_ms: decoded, render_done_ms: rendered,
    visibility: hiddenDuringRequest ? "hidden" : document.visibilityState, user_agent: navigator.userAgent, page_id: w5bPageId,
    loop_id: loop ? loop.id : null, loop_index: loop ? loop.index : null, loop_start_ms: loop ? loop.start : null};
  const timing = await api(`/api/runs/${job.run_id}/browser-timing`, observation);
  if (version !== selectionVersion) return false;
  el("browser").textContent = timing.request_to_render_ms.toFixed(1) + " ms";
  el("fps").textContent = timing.browser_actual_fps === null ? "未形成连续样本" : timing.browser_actual_fps.toFixed(2) + " FPS";
  message(`任务完成，原始 DMA 数组和分段记录已保存。${loop ? `连续帧 ${loop.index} / 20。` : "可切换图像、尺寸或 PL 模式继续运行。"}`);
  return true;
}
async function runSequence(ids) {
  if (running || fault || !capabilities) return;
  if (document.visibilityState !== "visible") { message("请将此页保持前台后运行。", true); return; }
  if (completedCount + ids.length > capabilities.session_run_limit) {
    message("剩余次数不足以完成本列表；可单张运行，或回Notebook安全关闭并导出。", true); return;
  }
  running = true; looping = ids.length > 1; buttons();
  const isList = ids.length > 1;
  let displayedCount = 0;
  try {
    for (let i = 0; i < ids.length; i++) {
      if (fault || (isList && !looping)) break;
      if (document.visibilityState !== "visible") throw new Error("页面已隐藏，停止后续任务");
      el("image").value = ids[i]; changed(); looping = isList; buttons();
      el("playlist-status").textContent = `${isList ? "逐张展示" : "单张展示"} ${i+1} / ${ids.length} · ${ids[i]}`;
      if (!await runOne(selectionVersion, null)) break;
      displayedCount++;
      await refreshStatus();
      el("fps").textContent = "展示模式 · 非测速";
      if (isList && looping && i + 1 < ids.length) await delay(2000);
    }
  } catch (error) {
    fault = true;
    message(`运行停止：${error.message}\n保留记录；不要自动重载 FPGA 或关闭失败内核。`, true);
    el("panels").classList.add("stale");
    el("selection-state").textContent = "本次操作失败；下方为历史结果";
  } finally {
    el("playlist-status").textContent = `${fault ? "异常停止" : displayedCount === ids.length ? "已完成" : "已停止后续请求"} · 本轮 ${displayedCount} / ${ids.length} 张`;
    looping = false; running = false; await refreshStatus(); buttons();
  }
}
async function run() { return runSequence([el("image").value]); }
async function navigate(delta) {
  if (running || fault) return;
  const ids = activeIds(), i = ids.indexOf(el("image").value), next = i + delta;
  if (i >= 0 && next >= 0 && next < ids.length) return runSequence([ids[next]]);
}
async function refreshStatus() {
  try {
    const status = await api("/api/status");
    completedCount = status.accepted;
    fault = fault || status.service_state !== "READY" || status.hardware_state === "FAULT";
    el("state").textContent = `${status.service_state} / ${status.hardware_state}`;
    el("state-dot").className = fault ? "fault" : status.active_run_id ? "busy" : "ready";
    el("frame-count").textContent = `完成 ${status.completed} / ${status.run_limit} · 待执行 ${status.pending}`;
    if (status.error) message(status.error.message + "\n保留启动 Notebook 和在途缓冲，停止新的请求。", true);
    buttons();
  } catch (error) {
    fault = true; el("state").textContent = "连接中断"; el("state-dot").className = "fault"; buttons();
  }
}
async function download(path, filename) {
  try {
    const response = await fetch(path, {cache: "no-store"});
    if (!response.ok) { const value = await response.json(); throw new Error(value.message || value.error); }
    const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement("a");
    if (capabilities.evidence_kind !== "PYNQ_PL_DMA") filename = "HOST_TEST_" + filename;
    link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 3000);
    message(`已提交下载 ${filename}。包含原始 NPY、同帧 PNG、JSON、CSV 和客户端绘制观测。`);
  } catch (error) { message(`导出失败：${error.message}`, true); }
}
async function initialize() {
  try {
    capabilities = await api("/api/capabilities");
    el("host-warning").hidden = capabilities.evidence_kind === "PYNQ_PL_DMA";
    const catalog = await api("/api/images");
    catalogIds = catalog.images.map(x => x.image_id).filter(x => !x.endsWith("_nogt"));
    if (catalogIds.length !== 20 || examples.some(id => !catalogIds.includes(id))) throw new Error("图像清单不匹配");
    populateImages();
    el("view").addEventListener("change", populateImages);
    el("previous").addEventListener("click", () => navigate(-1));
    el("next").addEventListener("click", () => navigate(1));
    el("list-run").addEventListener("click", () => runSequence([...activeIds()]));
    ["image", "side", "mode", "algorithm", "threshold", "png-profile"].forEach(id => { el(id).disabled = false; el(id).addEventListener(id === "threshold" ? "input" : "change", changed); });
    function algorithmOptions(resetThreshold) {
      const c7 = el("algorithm").value === "C7";
      for (const option of el("mode").options) option.disabled = c7 && !["final", "bypass"].includes(option.value);
      if (c7 && !["final", "bypass"].includes(el("mode").value)) el("mode").value = "final";
      if (resetThreshold) el("threshold").value = c7 ? "112" : "28";
      el("threshold-help").textContent = c7 ? "C7 分数：推荐112；运行写入 PL" : "A/C2/C5 响应：推荐28；运行写入 PL";
      changed();
    }
    el("algorithm").addEventListener("change", () => algorithmOptions(true));
    algorithmOptions(false);
    el("run").addEventListener("click", () => run(false));
    el("continuous").hidden = true;
    el("stop").addEventListener("click", () => { looping = false; buttons(); message("停止后续请求；当前 DMA 继续正常完成并保存。"); });
    el("alpha").addEventListener("input", drawOverlay);
    el("export-run").addEventListener("click", () => download(`/api/runs/${current.run_id}/export`, "browser_run_" + current.run_id + ".zip"));
    el("export-session").addEventListener("click", () => download("/api/session/export", "browser_session_" + capabilities.session_id + ".zip"));
    message("服务就绪：20张自由展示／8张讲解样例／独立功能演示。每次运行均发送真实PL任务。");
    await refreshStatus(); setInterval(refreshStatus, 1500); buttons();
  } catch (error) { message("初始化失败：" + error.message, true); }
}
initialize();
