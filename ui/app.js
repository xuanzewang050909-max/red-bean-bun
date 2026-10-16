"use strict";
const el = id => document.getElementById(id);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const nonce = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
const panes = ["original", "enhanced", "mask", "overlay"];
let capabilities, selectionVersion = 0, currentVersion = -1, running = false, looping = false, fault = false, current = null, currentImages = null;
let hiddenDuringRequest = false;
document.addEventListener("visibilitychange", () => { if (running && document.visibilityState !== "visible") hiddenDuringRequest = true; });

async function api(path, body) {
  const response = await fetch(path, {cache: "no-store", ...(body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})});
  const result = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${result.message || result.error}`);
  return result;
}
function message(text, error = false) {
  el("message").textContent = text;
  el("message").classList.toggle("fault-text", error);
}
function buttons() {
  el("run").disabled = !capabilities || running || fault;
  el("continuous").disabled = !capabilities || running || fault;
  el("stop").disabled = !looping;
  el("export-run").disabled = !current || currentVersion !== selectionVersion || running || el("panels").classList.contains("stale");
  el("export-session").disabled = !capabilities || running;
}
function changed() {
  selectionVersion++;
  looping = false;
  el("panels").classList.add("stale");
  el("selection-state").textContent = "选择已更改；下方为历史结果，点击运行更新";
  ["area", "quality", "dma", "inference", "browser", "fps"].forEach(id => el(id).textContent = "—");
  el("area-detail").textContent = "等待当前选择的 PL 结果";
  el("quality-detail").textContent = "等待新帧评分；不沿用上一张图的指标";
  buttons();
}
function decode(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = async () => { try { if (image.decode) await image.decode(); resolve(image); } catch (err) { reject(err); } };
    image.onerror = () => reject(new Error("同帧图像下载失败；保留任务记录"));
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
  el("dma").textContent = (timing.dma_transaction_ns / 1e6).toFixed(2) + " ms";
  el("inference").textContent = (timing.inference_ns / 1e6).toFixed(2) + " ms";
  el("browser").textContent = "测量中";
  el("fps").textContent = "—";
  el("identity").textContent = `${job.run_id} / ${job.config_id.slice(0, 16)} · ${job.request.image_id}, ${job.request.side}, mode ${job.request.mode_code}, T=28`;
  el("bytes").textContent = `发送 ${job.evidence.send_bytes.toLocaleString()} B / 接收 ${job.evidence.recv_bytes.toLocaleString()} B · PL 帧计数 ${job.evidence.frame_count} · GPIO 配置为主机提交，无锁存回读`;
  el("hashes").textContent = `${job.input.sha256} / ${job.output.sha256}`;
}
async function runOne(version, loop) {
  const request = {image_id: el("image").value, side: Number(el("side").value), threshold: 28,
                   mode: el("mode").value, client_nonce: nonce()};
  const start = performance.now();
  hiddenDuringRequest = document.visibilityState !== "visible";
  if (loop && loop.index === 1) loop.start = start;
  message(`提交 ${request.image_id} / ${request.side} / ${request.mode} 至真实 PL…`);
  el("panels").classList.add("stale");
  el("selection-state").textContent = "正在计算；下方保留上一次结果";
  let job = await api("/api/runs", request);
  while (job.status === "QUEUED" || job.status === "RUNNING") {
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
    visibility: hiddenDuringRequest ? "hidden" : document.visibilityState, user_agent: navigator.userAgent,
    loop_id: loop ? loop.id : null, loop_index: loop ? loop.index : null, loop_start_ms: loop ? loop.start : null};
  const timing = await api(`/api/runs/${job.run_id}/browser-timing`, observation);
  el("browser").textContent = timing.request_to_render_ms.toFixed(1) + " ms";
  el("fps").textContent = timing.browser_actual_fps === null ? "未形成连续样本" : timing.browser_actual_fps.toFixed(2) + " FPS";
  message(`任务完成，原始 DMA 数组和分段记录已保存。${loop ? `连续帧 ${loop.index} / 20。` : "可切换图像、尺寸或 PL 模式继续运行。"}`);
  return true;
}
async function run(continuous) {
  if (running || fault) return;
  running = true; looping = continuous; buttons();
  const version = selectionVersion;
  const loop = continuous ? {id: nonce(), index: 1, start: null} : null;
  try {
    do {
      const displayed = await runOne(version, loop);
      if (!displayed || !loop || !looping || version !== selectionVersion) break;
      loop.index++;
    } while (loop.index <= 20);
  } catch (error) {
    message(`运行停止：${error.message}\n检查板端状态并保留记录；不要自动重载 FPGA 或关闭失败内核。`, true);
    el("panels").classList.add("stale");
    el("selection-state").textContent = "本次操作失败；下方为历史结果";
  } finally {
    looping = false; running = false; await refreshStatus(); buttons();
  }
}
async function refreshStatus() {
  try {
    const status = await api("/api/status");
    fault = status.service_state !== "READY" || status.hardware_state === "FAULT";
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
    for (const image of catalog.images) {
      const option = document.createElement("option"); option.value = image.image_id; option.textContent = image.image_id + " · STARE"; el("image").append(option);
    }
    ["image", "side", "mode"].forEach(id => { el(id).disabled = false; el(id).addEventListener("change", changed); });
    el("run").addEventListener("click", () => run(false));
    el("continuous").addEventListener("click", () => run(true));
    el("stop").addEventListener("click", () => { looping = false; buttons(); message("停止后续请求；当前 DMA 继续正常完成并保存。"); });
    el("alpha").addEventListener("input", drawOverlay);
    el("export-run").addEventListener("click", () => download(`/api/runs/${current.run_id}/export`, "browser_run_" + current.run_id + ".zip"));
    el("export-session").addEventListener("click", () => download("/api/session/export", "browser_session_" + capabilities.session_id + ".zip"));
    message("服务就绪。请选择图像和已有 PL 模式，点击运行 FPGA；新浏览器结果仍需独立板级复核。");
    await refreshStatus(); setInterval(refreshStatus, 1500); buttons();
  } catch (error) { message("初始化失败：" + error.message, true); }
}
initialize();
