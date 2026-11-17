// Text to Speech: chuyển tab và gọi backend tts-service (Azure Speech) trên Render.
// Luồng: chọn file/link -> Xem mục lục (chia theo chương) -> chọn phần -> Nghe ngay hoặc Tải MP3.
const TTS_API = ["localhost", "127.0.0.1"].includes(location.hostname)
  ? "http://127.0.0.1:8000"
  : "https://transcript-tts-6rig.onrender.com";
const MONTHLY_FREE_CHARS = 500000; // Azure Speech Free F0
const MONTHLY_FREE_OCR_PAGES = 500; // Azure Document Intelligence Free F0

const $ = (id) => document.getElementById(id);

// ---------- Chuyển giữa Transcript và Text to Speech (theo #hash để mở lại đúng tab) ----------
function showView() {
  const tts = location.hash === "#tts";
  $("view-transcript").hidden = tts;
  $("view-tts").hidden = !tts;
  for (const [id, active] of [["mode-transcript", !tts], ["mode-tts", tts]]) {
    if (active) $(id).setAttribute("aria-current", "page");
    else $(id).removeAttribute("aria-current");
  }
  document.title = tts ? "Text to Speech — Từ văn bản thành giọng nói" : "Transcript — Từ lời nói thành văn bản";
}
window.addEventListener("hashchange", showView);
showView();

// ---------- Trạng thái ----------
let sourceMode = "file";
let job = null; // AbortController của lần chạy hiện tại
let doc = null; // kết quả /api/document của nguồn đang chọn
const player = { sessionId: null, chunks: [], index: 0, token: 0, title: "" };
const audio = new Audio();
audio.preload = "auto";

function setStatus(msg, state = job ? "busy" : "idle") {
  $("tts-status").textContent = msg;
  $("tts-status").dataset.state = msg.startsWith("Lỗi:") ? "error" : state;
}

function setBadge(text, state = "") {
  $("tts-badge").textContent = text;
  $("tts-badge").dataset.state = state;
}

const formatTime = (s) => (!isFinite(s) || s < 0 ? "00:00"
  : `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
const formatMinutes = (sec) => (sec < 3600 ? `${Math.max(1, Math.round(sec / 60))} phút`
  : `${Math.floor(sec / 3600)} giờ ${Math.round((sec % 3600) / 60)} phút`);
const formatChars = (n) => n.toLocaleString("vi-VN");

function outputMode() {
  return document.querySelector('input[name="tts-mode"]:checked').value;
}

function selectedIds() {
  return [...document.querySelectorAll("#tts-section-list input:checked")].map((c) => Number(c.value));
}

function updateRunLabel() {
  const mp3 = outputMode() === "mp3";
  $("tts-merge-field").classList.toggle("hidden", !mp3);
  $("tts-run").firstChild.textContent = !doc ? "Xem mục lục" : mp3 ? "Tạo file MP3" : "Bắt đầu đọc";
  $("tts-run-selected").firstChild.textContent = mp3 ? "Tạo file MP3" : "Bắt đầu đọc";
}

function showPanel(which) {
  for (const [id, name] of [["tts-empty", "empty"], ["tts-sections", "sections"], ["tts-player", "player"], ["tts-files", "files"]]) {
    $(id).classList.toggle("hidden", which !== name);
  }
}

// Đổi file/link thì phải xem lại mục lục
function resetDocument() {
  doc = null;
  audio.pause();
  player.token++;
  showPanel("empty");
  setBadge("Chưa có tài liệu");
  updateRunLabel();
}

function selectSource(mode) {
  if (job) return;
  sourceMode = mode;
  for (const s of ["file", "link"]) {
    $(`tts-source-${s}`).setAttribute("aria-pressed", String(s === mode));
    $(`tts-${s}-fields`).classList.toggle("hidden", s !== mode);
  }
  resetDocument();
}

async function api(path, options = {}, timeout = 120000) {
  const signal = AbortSignal.any([job?.signal ?? new AbortController().signal, AbortSignal.timeout(timeout)]);
  let res;
  try {
    res = await fetch(`${TTS_API}${path}`, { ...options, signal });
  } catch (e) {
    if (signal.reason?.name === "TimeoutError") throw new Error("Máy chủ phản hồi quá lâu. Hãy thử lại.");
    if (e.name === "AbortError") throw e;
    throw new Error("Không kết nối được máy chủ đọc. Kiểm tra mạng rồi thử lại.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// Render gói free ngủ khi không dùng: đánh thức trước, báo cho người dùng chờ
async function wakeServer() {
  setStatus("Đang kết nối máy chủ đọc... Nếu máy chủ đang ngủ, bước này có thể mất khoảng một phút.");
  const health = await api("/health", {}, 150000);
  if (!health.tts_configured) throw new Error("Máy chủ chưa được cấu hình giọng đọc Azure.");
}

function sourceForm() {
  const form = new FormData();
  if (sourceMode === "file") {
    const file = $("tts-file").files[0];
    if (!file) throw new Error("Hãy chọn file PDF hoặc Word.");
    if (!file.size) throw new Error("File đang rỗng.");
    if (file.size > 50 * 1024 * 1024) throw new Error("File lớn hơn 50 MB.");
    form.append("file", file);
  } else {
    const url = $("tts-url").value.trim();
    try {
      if (!/^https?:$/.test(new URL(url).protocol)) throw new Error();
    } catch {
      throw new Error("Link không hợp lệ. Hãy dán địa chỉ bắt đầu bằng https://.");
    }
    form.append("url", url);
  }
  return form;
}

// ---------- Mục lục: chọn phần muốn nghe ----------
// Phần là ảnh scan chưa nhận dạng chữ (OCR)
const needsOcr = (s) => s.needs_ocr && s.char_count == null;
const pageCount = (s) => s.page_end - s.page_start;

function sectionMeta(s) {
  if (needsOcr(s)) return `Trang ${s.pages} · ảnh scan, cần nhận dạng chữ ${pageCount(s)} trang`;
  return `${s.pages ? `Trang ${s.pages} · ` : ""}~${formatMinutes(s.estimated_seconds)} · ${formatChars(s.char_count)} ký tự`;
}

function renderSections() {
  $("tts-doc-title").textContent = doc.title;
  const how = {
    bookmark: "theo mục lục của file", heading: "theo các tiêu đề trong file",
    size: "theo độ dài (file không có mục lục)", ocr: "theo trang",
  }[doc.structure];
  const pages = doc.total_pages ? `${doc.total_pages} trang · ` : "";
  let note = `${pages}${doc.sections.length} phần, chia ${how}. Chọn phần muốn nghe; chỉ phần được chọn mới tốn hạn mức đọc.`;
  if (doc.needs_ocr) {
    note = `${pages}${doc.sections.length} phần, chia ${how}. Đây là PDF dạng ảnh: phần bạn chọn sẽ được nhận dạng chữ (OCR) trước khi đọc, `
      + `khoảng 6–7 giây mỗi trang, tốn hạn mức ${MONTHLY_FREE_OCR_PAGES} trang OCR miễn phí mỗi tháng.`;
    if (!doc.ocr_available) note += " Máy chủ chưa bật nhận dạng chữ nên chưa đọc được file này.";
  }
  $("tts-doc-note").textContent = note;
  const checked = new Set(selectedIds());
  const list = $("tts-section-list");
  list.replaceChildren();
  doc.sections.forEach((s) => {
    const li = document.createElement("li");
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = String(s.id);
    box.checked = checked.has(s.id); // mặc định chưa chọn; giữ lựa chọn khi vẽ lại sau OCR
    box.addEventListener("change", updateSelection);
    const text = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = s.title; // văn bản từ tài liệu: textContent, không innerHTML
    const meta = document.createElement("span");
    meta.className = "hint";
    meta.textContent = sectionMeta(s);
    text.append(title, meta);
    label.append(box, text);
    li.append(label);
    list.append(li);
  });
  showPanel("sections");
  updateSelection();
}

function updateSelection() {
  const ids = new Set(selectedIds());
  const chosen = doc.sections.filter((s) => ids.has(s.id));
  const ready = chosen.filter((s) => !needsOcr(s));
  const ocrPages = chosen.filter(needsOcr).reduce((n, s) => n + pageCount(s), 0);
  const chars = ready.reduce((n, s) => n + s.char_count, 0);
  const secs = ready.reduce((n, s) => n + s.estimated_seconds, 0);
  const share = Math.round((chars / MONTHLY_FREE_CHARS) * 100);
  const parts = [];
  if (ready.length) parts.push(`~${formatMinutes(secs)} · ${formatChars(chars)} ký tự (khoảng ${share}% hạn mức đọc miễn phí mỗi tháng)`);
  if (ocrPages) parts.push(`cần nhận dạng chữ ${ocrPages} trang (${Math.round((ocrPages / MONTHLY_FREE_OCR_PAGES) * 100)}% hạn mức OCR tháng)`);
  $("tts-selection").textContent = chosen.length ? `Đã chọn ${chosen.length} phần · ${parts.join(" · ")}` : "Chưa chọn phần nào.";
  $("tts-selection").dataset.state = share > 100 || ocrPages > MONTHLY_FREE_OCR_PAGES ? "warn" : "";
  setBadge(`${chosen.length}/${doc.sections.length} phần`, chosen.length ? "complete" : "");
}

$("tts-select-all").addEventListener("click", () => {
  document.querySelectorAll("#tts-section-list input").forEach((c) => { c.checked = true; });
  updateSelection();
});
$("tts-select-none").addEventListener("click", () => {
  document.querySelectorAll("#tts-section-list input").forEach((c) => { c.checked = false; });
  updateSelection();
});
document.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => {
  if (!doc || job) return;
  audio.pause();
  player.token++;
  showPanel("sections"); // giữ nguyên các phần đã chọn
  updateSelection();
  setStatus("Chọn phần muốn nghe tiếp.", "idle");
}));

async function analyze() {
  setStatus("Đang đọc tài liệu và chia theo chương...");
  doc = await api("/api/document", { method: "POST", body: sourceForm() }, 300000);
  renderSections();
  updateRunLabel();
  setStatus(`Đã chia thành ${doc.sections.length} phần. Chọn phần muốn nghe rồi bấm ${outputMode() === "mp3" ? "Tạo file MP3" : "Bắt đầu đọc"}.`, "idle");
}

// Nhận dạng chữ cho các phần ảnh scan đã chọn, rồi cập nhật số ký tự/thời lượng của từng phần
async function runOcr(ids) {
  const form = new FormData();
  form.append("section_ids", ids.join(","));
  const { task_id, pages } = await api(`/api/document/${doc.doc_id}/ocr`, { method: "POST", body: form });
  setStatus(`Đang nhận dạng chữ ${pages} trang...`);
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    job.signal.throwIfAborted();
    const t = await api(`/api/process/offline/status/${task_id}`);
    if (t.status === "FAILED") throw new Error(t.error || "Nhận dạng chữ thất bại.");
    setStatus(`${t.current_step} (${t.progress}%)`);
    if (t.status === "COMPLETED") {
      for (const r of t.output_files) Object.assign(doc.sections.find((s) => s.id === r.id), r);
      renderSections();
      return;
    }
  }
}

function selectionForm() {
  const ids = selectedIds();
  if (!ids.length) throw new Error("Hãy chọn ít nhất một phần để nghe.");
  const form = new FormData();
  form.append("doc_id", doc.doc_id);
  form.append("section_ids", ids.join(","));
  form.append("voice", $("tts-voice").value);
  form.append("rate", $("tts-rate").value);
  return form;
}

// ---------- Nghe ngay ----------
function renderChunkList() {
  const list = $("tts-chunks");
  list.replaceChildren();
  player.chunks.forEach((c, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = c.preview;
    btn.addEventListener("click", () => loadChunk(i, true));
    li.append(btn);
    list.append(li);
  });
}

function markActiveChunk() {
  [...$("tts-chunks").children].forEach((li, i) => li.toggleAttribute("data-active", i === player.index));
  $("tts-now").textContent = `Đoạn ${player.index + 1} / ${player.chunks.length}`;
}

function prefetch(index) {
  const next = [index + 1, index + 2].filter((i) => i < player.chunks.length);
  if (!next.length) return;
  fetch(`${TTS_API}/api/player/prefetch/${player.sessionId}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chunk_indices: next }),
  }).catch(() => {});
}

async function loadChunk(index, autoplay) {
  if (index < 0 || index >= player.chunks.length) return;
  const token = ++player.token; // lần chuyển đoạn mới bỏ qua phản hồi cũ về muộn
  player.index = index;
  audio.pause();
  markActiveChunk();
  setStatus(`Đang chuẩn bị đoạn ${index + 1}...`, "busy");
  prefetch(index);
  try {
    const res = await fetch(`${TTS_API}/api/player/chunk/${player.sessionId}/${index}`);
    const data = await res.json().catch(() => ({}));
    if (token !== player.token) return;
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    $("tts-text").textContent = data.text;
    audio.src = `${TTS_API}${data.audio_url}`;
    audio.playbackRate = Number($("tts-speed").value);
    updateMediaSession();
    if (autoplay) await audio.play();
    setStatus(`Đang đọc đoạn ${index + 1} / ${player.chunks.length}`, "idle");
  } catch (e) {
    if (token !== player.token || e.name === "AbortError") return;
    if (e.name === "NotAllowedError") {
      setStatus(`Đoạn ${index + 1} đã sẵn sàng. Bấm nút phát để nghe.`, "idle");
      return;
    }
    setStatus(`Lỗi: không đọc được đoạn ${index + 1}: ${e.message}. Bấm đoạn trong danh sách để thử lại.`);
  }
}

function updateMediaSession() {
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: `${player.title} · Đoạn ${player.index + 1}/${player.chunks.length}`,
    artist: "Text to Speech",
  });
}

if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => audio.play());
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("previoustrack", () => loadChunk(player.index - 1, true));
  navigator.mediaSession.setActionHandler("nexttrack", () => loadChunk(player.index + 1, true));
}

audio.addEventListener("play", () => {
  $("tts-play-icon").setAttribute("href", "#i-pause");
  $("tts-play").setAttribute("aria-label", "Tạm dừng");
});
audio.addEventListener("pause", () => {
  $("tts-play-icon").setAttribute("href", "#i-play");
  $("tts-play").setAttribute("aria-label", "Phát");
});
audio.addEventListener("loadedmetadata", () => { $("tts-duration").textContent = formatTime(audio.duration); });
audio.addEventListener("timeupdate", () => {
  const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
  $("tts-progress-fill").style.width = `${pct}%`;
  $("tts-progress").setAttribute("aria-valuenow", String(Math.round(pct)));
  $("tts-time").textContent = formatTime(audio.currentTime);
});
audio.addEventListener("ended", () => {
  if (player.index + 1 < player.chunks.length) loadChunk(player.index + 1, true);
  else setStatus("Đã đọc hết phần đã chọn.", "idle");
});

$("tts-play").addEventListener("click", () => {
  if (!audio.src) return loadChunk(player.index, true);
  audio.paused ? audio.play() : audio.pause();
});
$("tts-prev").addEventListener("click", () => loadChunk(player.index - 1, true));
$("tts-next").addEventListener("click", () => loadChunk(player.index + 1, true));
$("tts-speed").addEventListener("change", () => { audio.playbackRate = Number($("tts-speed").value); });
$("tts-progress").addEventListener("click", (e) => {
  const r = $("tts-progress").getBoundingClientRect();
  if (audio.duration) audio.currentTime = Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1) * audio.duration;
});
$("tts-progress").addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") audio.currentTime += 10;
  if (e.key === "ArrowLeft") audio.currentTime -= 10;
});

async function startStream(form) {
  setStatus("Đang chuẩn bị phần đã chọn...");
  const data = await api("/api/player/init", { method: "POST", body: form }, 300000);
  Object.assign(player, { sessionId: data.session_id, chunks: data.chunks, index: 0, title: data.title });
  $("tts-book").textContent = player.title;
  renderChunkList();
  showPanel("player");
  setBadge(`${data.chunks.length} đoạn`, "complete");
  document.body.classList.add("has-result");
  job = null; // từ đây người dùng điều khiển trình phát
  await loadChunk(0, true);
}

// ---------- Tải MP3 ----------
async function startMp3(form) {
  form.append("merge_option", $("tts-merge").value);
  setStatus("Đang gửi yêu cầu tạo MP3...");
  const { task_id } = await api("/api/process/offline", { method: "POST", body: form }, 300000);
  setBadge("Đang tạo MP3");
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    job.signal.throwIfAborted();
    const t = await api(`/api/process/offline/status/${task_id}`);
    if (t.status === "FAILED") throw new Error(t.error || "Tạo MP3 thất bại.");
    const counts = t.total_chunks ? ` · ${t.processed_chunks}/${t.total_chunks} đoạn` : "";
    setStatus(`${t.current_step} (${t.progress}%${counts})`);
    if (t.status === "COMPLETED") return showFiles(t);
  }
}

function showFiles(task) {
  const list = $("tts-file-list");
  list.replaceChildren();
  const files = task.zip_file ? [task.zip_file, ...task.output_files] : task.output_files;
  for (const f of files) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `${TTS_API}${f.download_url}`;
    a.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-download"/></svg>';
    a.append(document.createTextNode(f.filename.replace(/^[0-9a-f]{8}_/, "")));
    const size = document.createElement("span");
    size.className = "hint";
    size.textContent = `${f.size_mb} MB${f === task.zip_file ? " · trọn bộ" : ""}`;
    li.append(a, size);
    list.append(li);
  }
  $("tts-files-note").textContent = "Bấm để tải về máy. File được giữ trên máy chủ khoảng 6 giờ.";
  showPanel("files");
  setBadge("Hoàn tất", "complete");
  document.body.classList.add("has-result");
  setStatus(`Xong: ${task.output_files.length} file MP3.`, "idle");
}

// ---------- Chạy ----------
const controls = ["tts-run", "tts-run-selected", "tts-file", "tts-url", "tts-voice", "tts-rate", "tts-merge", "tts-source-file", "tts-source-link", "tts-select-all", "tts-select-none"];

function setBusy(busy) {
  controls.forEach((id) => { $(id).disabled = busy; });
  document.querySelectorAll('input[name="tts-mode"], #tts-section-list input').forEach((r) => { r.disabled = busy; });
  $("tts-cancel").classList.toggle("hidden", !busy);
}

async function run() {
  if (job) return;
  let form = null;
  try {
    form = doc ? selectionForm() : sourceForm();
  } catch (e) {
    return setStatus(`Lỗi: ${e.message}`);
  }
  job = new AbortController();
  const current = job;
  audio.pause();
  player.token++;
  setBusy(true);
  try {
    await wakeServer();
    if (!doc) await analyze();
    else {
      const ids = selectedIds();
      const pending = doc.sections.filter((s) => ids.includes(s.id) && needsOcr(s)).map((s) => s.id);
      if (pending.length) await runOcr(pending);
      if (outputMode() === "mp3") await startMp3(form);
      else await startStream(form);
    }
  } catch (e) {
    setStatus(current.signal.aborted ? "Đã dừng." : `Lỗi: ${e.message}`, "idle");
  } finally {
    job = null;
    setBusy(false);
  }
}

$("tts-run").addEventListener("click", run);
$("tts-run-selected").addEventListener("click", run); // nút ngay dưới danh sách phần, đỡ phải cuộn lên trên điện thoại
$("tts-cancel").addEventListener("click", () => job?.abort());
$("tts-source-file").addEventListener("click", () => selectSource("file"));
$("tts-source-link").addEventListener("click", () => selectSource("link"));
document.querySelectorAll('input[name="tts-mode"]').forEach((r) => r.addEventListener("change", updateRunLabel));
$("tts-file").addEventListener("change", () => {
  $("tts-file-name").textContent = $("tts-file").files[0]?.name || "PDF hoặc .docx, tối đa 50 MB";
  resetDocument();
});
$("tts-url").addEventListener("input", () => { if (doc) resetDocument(); });
updateRunLabel();
