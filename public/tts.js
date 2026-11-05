// Text to Speech: chuyển tab và gọi backend tts-service (Azure Speech) trên Render.
const TTS_API = ["localhost", "127.0.0.1"].includes(location.hostname)
  ? "http://127.0.0.1:8000"
  : "https://transcript-tts.onrender.com";

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

function selectSource(mode) {
  if (job) return;
  sourceMode = mode;
  for (const s of ["file", "link"]) {
    $(`tts-source-${s}`).setAttribute("aria-pressed", String(s === mode));
    $(`tts-${s}-fields`).classList.toggle("hidden", s !== mode);
  }
}

function outputMode() {
  return document.querySelector('input[name="tts-mode"]:checked').value;
}

function syncModeFields() {
  const mp3 = outputMode() === "mp3";
  $("tts-merge-field").classList.toggle("hidden", !mp3);
  $("tts-run").firstChild.textContent = mp3 ? "Tạo file MP3" : "Bắt đầu đọc";
}

const formatTime = (s) => (!isFinite(s) || s < 0 ? "00:00"
  : `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`);

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
  form.append("voice", $("tts-voice").value);
  form.append("rate", $("tts-rate").value);
  return form;
}

function showPanel(which) {
  $("tts-empty").classList.toggle("hidden", which !== "empty");
  $("tts-player").classList.toggle("hidden", which !== "player");
  $("tts-files").classList.toggle("hidden", which !== "files");
}

// ---------- Nghe ngay ----------
function renderChunkList() {
  const list = $("tts-chunks");
  list.replaceChildren();
  player.chunks.forEach((c, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = c.preview; // văn bản từ tài liệu: textContent, không innerHTML
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

audio.addEventListener("play", () => $("tts-play-icon").setAttribute("href", "#i-pause"));
audio.addEventListener("pause", () => $("tts-play-icon").setAttribute("href", "#i-play"));
audio.addEventListener("play", () => $("tts-play").setAttribute("aria-label", "Tạm dừng"));
audio.addEventListener("pause", () => $("tts-play").setAttribute("aria-label", "Phát"));
audio.addEventListener("loadedmetadata", () => { $("tts-duration").textContent = formatTime(audio.duration); });
audio.addEventListener("timeupdate", () => {
  const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
  $("tts-progress-fill").style.width = `${pct}%`;
  $("tts-progress").setAttribute("aria-valuenow", String(Math.round(pct)));
  $("tts-time").textContent = formatTime(audio.currentTime);
});
audio.addEventListener("ended", () => {
  if (player.index + 1 < player.chunks.length) loadChunk(player.index + 1, true);
  else setStatus("Đã đọc hết tài liệu.", "idle");
});

$("tts-play").addEventListener("click", () => {
  if (!audio.src) return loadChunk(player.index, true);
  audio.paused ? audio.play() : audio.pause();
});
$("tts-prev").addEventListener("click", () => loadChunk(player.index - 1, true));
$("tts-next").addEventListener("click", () => loadChunk(player.index + 1, true));
$("tts-speed").addEventListener("change", () => { audio.playbackRate = Number($("tts-speed").value); });
function seekTo(fraction) {
  if (audio.duration) audio.currentTime = Math.min(Math.max(fraction, 0), 1) * audio.duration;
}
$("tts-progress").addEventListener("click", (e) => {
  const r = $("tts-progress").getBoundingClientRect();
  seekTo((e.clientX - r.left) / r.width);
});
$("tts-progress").addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") audio.currentTime += 10;
  if (e.key === "ArrowLeft") audio.currentTime -= 10;
});

async function startStream(form) {
  setStatus("Đang đọc tài liệu và chia đoạn...");
  const data = await api("/api/player/init", { method: "POST", body: form }, 300000);
  Object.assign(player, { sessionId: data.session_id, chunks: data.chunks, index: 0, title: data.title.replace(/^[0-9a-f]{8}_/, "") });
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
  setStatus("Đang gửi tài liệu...");
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
const controls = ["tts-run", "tts-file", "tts-url", "tts-voice", "tts-rate", "tts-merge", "tts-source-file", "tts-source-link"];

async function run() {
  if (job) return;
  let form;
  try {
    form = sourceForm();
  } catch (e) {
    return setStatus(`Lỗi: ${e.message}`);
  }
  job = new AbortController();
  const current = job;
  audio.pause();
  player.token++;
  controls.forEach((id) => { $(id).disabled = true; });
  document.querySelectorAll('input[name="tts-mode"]').forEach((r) => { r.disabled = true; });
  $("tts-cancel").classList.remove("hidden");
  try {
    await wakeServer();
    if (outputMode() === "mp3") await startMp3(form);
    else await startStream(form);
  } catch (e) {
    setStatus(current.signal.aborted ? "Đã dừng." : `Lỗi: ${e.message}`, "idle");
  } finally {
    job = null;
    controls.forEach((id) => { $(id).disabled = false; });
    document.querySelectorAll('input[name="tts-mode"]').forEach((r) => { r.disabled = false; });
    $("tts-cancel").classList.add("hidden");
  }
}

$("tts-run").addEventListener("click", run);
$("tts-cancel").addEventListener("click", () => job?.abort());
$("tts-source-file").addEventListener("click", () => selectSource("file"));
$("tts-source-link").addEventListener("click", () => selectSource("link"));
document.querySelectorAll('input[name="tts-mode"]').forEach((r) => r.addEventListener("change", syncModeFields));
$("tts-file").addEventListener("change", () => {
  $("tts-file-name").textContent = $("tts-file").files[0]?.name || "PDF hoặc .docx, tối đa 50 MB";
});
syncModeFields();
