const SAMPLE_RATE = 16000;
const CHUNK_SECONDS = 30;
const GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash"];
const KEY_STORAGE = "gemini-api-key";
const DOWNLOADER_URL = "https://transcript-downloader-trial.onrender.com";

const $ = (id) => document.getElementById(id);
let last = null; // { text, source, method }
let activeJob = null;
let sourceMode = "link";

function selectSource(mode) {
  if (activeJob) return;
  sourceMode = mode;
  for (const source of ["link", "file"]) {
    $(`source-${source}`).setAttribute("aria-pressed", String(source === mode));
    $(`${source}-fields`).classList.toggle("hidden", source !== mode);
  }
}

function loadKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function setStatus(msg) {
  $("status").textContent = msg;
  $("status").dataset.state = msg.startsWith("Lỗi:") ? "error" : activeJob ? "busy" : "idle";
}

async function request(url, options = {}, timeout = 60000) {
  const signal = AbortSignal.any([activeJob.signal, AbortSignal.timeout(timeout)]);
  try {
    return await fetch(url, { ...options, signal });
  } catch (e) {
    if (signal.reason?.name === "TimeoutError") throw new Error("Chờ phản hồi quá lâu. Hãy thử lại hoặc tải file về để chép.");
    throw e;
  }
}

async function postJson(path, body) {
  const res = await request(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function isYouTube(url) {
  return /(^|\.)(youtube\.com|youtu\.be)$/.test(new URL(url).hostname);
}

function isFacebook(url) {
  const host = new URL(url).hostname;
  return /(^|\.)facebook\.com$/.test(host) || host === "fb.watch";
}

// Called from the browser: the user's own network is in a Gemini-supported region and has no 100 s proxy timeout.
async function transcribeWithGemini(url, lang) {
  const apiKey = loadKey();
  if (!apiKey) {
    throw new Error("Thiết bị này chưa được thiết lập để xử lý video không có phụ đề. Hãy chọn file để chép.");
  }
  const langHint = lang === "vi" ? " The speech is in Vietnamese." : lang === "en" ? " The speech is in English." : "";
  const prompt =
    "Transcribe the spoken audio of this video verbatim, in its original language." +
    langHint +
    " Output only the transcript text split into paragraphs. Do not summarize, translate, add timestamps or add comments.";
  let lastError;
  // Each model has its own free quota; move on when one is overloaded or out of quota.
  for (const model of GEMINI_MODELS) {
    setStatus(`Video không có phụ đề, đang nhờ Gemini (${model}) chép... có thể mất vài phút`);
    const res = await request(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }, { file_data: { file_uri: url } }] }] }),
    }, 300000);
    const data = await res.json().catch(() => ({}));
    if ([404, 429, 503].includes(res.status)) {
      lastError = new Error(`${model}: ${data?.error?.message || res.status}`);
      continue;
    }
    if (!res.ok) throw new Error(`Gemini: ${data?.error?.message || res.status}`);
    const candidate = data.candidates?.[0];
    const text = (candidate?.content?.parts || []).filter((p) => !p.thought).map((p) => p.text || "").join("").trim();
    if (!text) {
      const reason = data.candidates?.[0]?.finishReason || data.promptFeedback?.blockReason || "không rõ";
      const hint = reason === "RECITATION" ? " (nội dung có bản quyền, ví dụ lời bài hát)" : "";
      throw new Error(`Gemini không trả về nội dung, lý do: ${reason}${hint}`);
    }
    const reason = candidate?.finishReason;
    const warning = reason !== "STOP"
      ? `Gemini chưa hoàn tất (${reason || "không có lý do kết thúc"}). Nội dung bên dưới có thể bị thiếu.`
      : "";
    return { text, method: `Gemini (${model})`, warning };
  }
  throw lastError;
}

// Decode any audio/video the browser can play, then downmix and resample to 16 kHz mono.
async function decodeToMono16k(arrayBuffer) {
  const ctx = new AudioContext();
  let decoded;
  try {
    decoded = await ctx.decodeAudioData(arrayBuffer);
  } catch {
    throw new Error("Trình duyệt không giải mã được file này. Hãy thử file MP3, WAV hoặc video MP4 có audio được hỗ trợ.");
  } finally {
    await ctx.close();
  }
  activeJob.signal.throwIfAborted();
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * SAMPLE_RATE), SAMPLE_RATE);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  return (await offline.startRendering()).getChannelData(0);
}

function encodeWav(samples) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, SAMPLE_RATE, true);
  v.setUint32(28, SAMPLE_RATE * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result.slice(r.result.indexOf(",") + 1));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

async function transcribeAudio(arrayBuffer, lang, onProgress) {
  setStatus("Đang giải mã audio...");
  const samples = await decodeToMono16k(arrayBuffer);
  activeJob.signal.throwIfAborted();
  const size = CHUNK_SECONDS * SAMPLE_RATE;
  const total = Math.ceil(samples.length / size);
  const parts = [];
  for (let i = 0; i < total; i++) {
    activeJob.signal.throwIfAborted();
    setStatus(`Đang chuyển giọng nói thành chữ: đoạn ${i + 1}/${total}`);
    const b64 = await blobToBase64(encodeWav(samples.subarray(i * size, (i + 1) * size)));
    const params = new URLSearchParams();
    if (lang) params.set("lang", lang);
    const prev = parts.join(" ").slice(-200);
    if (prev) params.set("prompt", prev);
    const res = await request(`/api/whisper?${params}`, { method: "POST", body: b64 }, 180000);
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok || data.error) throw new Error(`Đoạn ${i + 1}: ${data.error || res.status}`);
    if (data.text?.trim()) parts.push(data.text.trim());
    if (parts.length) onProgress(parts.join("\n"), i + 1, total);
  }
  return parts.join("\n");
}

function showResult(text, method, source, complete, note = "") {
  last = { text, method, source, complete };
  $("output").value = text;
  $("result-note").textContent = `${complete ? "Hoàn tất" : "Chưa hoàn tất"} · ${method} · ${source}${note ? `\n${note}` : ""}`;
  $("result").classList.remove("hidden");
  $("empty-result").classList.add("hidden");
  document.body.classList.add("has-result");
  $("result-badge").textContent = complete ? "Hoàn tất" : "Chưa hoàn tất";
  $("result-badge").dataset.state = complete ? "complete" : "partial";
  $("copy-status").textContent = "";
}

async function run() {
  if (activeJob) return;
  const url = sourceMode === "link" ? $("url").value.trim() : "";
  const file = sourceMode === "file" ? $("file").files[0] : null;
  const lang = $("lang").value;
  activeJob = new AbortController();
  for (const id of ["run", "url", "file", "lang", "source-link", "source-file"]) $(id).disabled = true;
  $("run").firstChild.textContent = "Đang xử lý…";
  $("cancel").classList.remove("hidden");
  const started = Date.now();
  let produced = false;
  try {
    let text, method, source, warning = "";
    if (url && !file) {
      try {
        if (!/^https?:$/.test(new URL(url).protocol)) throw new Error();
      } catch {
        throw new Error("Link không hợp lệ. Hãy dán địa chỉ bắt đầu bằng https://.");
      }
    }
    const progress = (partial, done, total) => {
      produced = true;
      showResult(partial, method, source, false, `Đã xử lý ${done}/${total} đoạn. Bạn có thể tải phần đã chép.`);
    };
    if (file) {
      if (!file.size) throw new Error("File đang rỗng. Hãy chọn file có audio.");
      source = file.name;
      method = "Whisper (Workers AI)";
      text = await transcribeAudio(await file.arrayBuffer(), lang, progress);
    } else if (url && isYouTube(url)) {
      const u = new URL(url);
      const id = u.hostname.endsWith("youtu.be") ? u.pathname.slice(1).split("/")[0]
        : u.pathname === "/watch" ? u.searchParams.get("v") : u.pathname.match(/^\/(?:shorts|embed|live|v)\/([\w-]+)\/?$/)?.[1];
      if (!/^https?:$/.test(u.protocol) || !/^[\w-]{11}$/.test(id || "")) throw new Error("Link YouTube không hợp lệ. Hãy sao chép lại link video.");
      source = `https://www.youtube.com/watch?v=${id}`;
      setStatus("Đang tìm phụ đề YouTube...");
      const captions = await postJson("/api/youtube", { url: source, lang });
      ({ text, method } = captions);
      if (!text) ({ text, method, warning } = await transcribeWithGemini(source, lang));
      else if (lang && captions.language?.split("-")[0] !== lang) {
        warning = `Không có phụ đề ${lang === "vi" ? "tiếng Việt" : "tiếng Anh"}; đã lấy phụ đề ${captions.language} có sẵn. Nội dung chưa được dịch.`;
      }
    } else if (url && isFacebook(url)) {
      source = url;
      if (new URL(url).protocol !== "https:") throw new Error("Hãy dùng link Facebook bắt đầu bằng https://.");
      setStatus("Đang tải audio từ Facebook... Nếu máy chủ đang ngủ, bước này có thể mất thêm khoảng một phút.");
      const res = await request(`${DOWNLOADER_URL}/audio`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url }),
      }, 420000);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(`Không tải được audio Facebook: ${data.error || `HTTP ${res.status}`}. Hãy thử lại hoặc tải file về rồi chọn file.`);
      }
      if (!res.headers.get("content-type")?.includes("audio/")) {
        throw new Error("Máy chủ tải audio chưa sẵn sàng. Hãy thử lại sau một phút.");
      }
      method = "Whisper (Workers AI)";
      text = await transcribeAudio(await res.arrayBuffer(), lang, progress);
    } else {
      throw new Error("Hãy dán link YouTube/Facebook hoặc chọn file. Với TikTok, X.com và link khác, hãy tải video hoặc audio về rồi chọn file.");
    }
    activeJob.signal.throwIfAborted();
    if (!text?.trim()) throw new Error("Không nhận được lời nói trong audio. Hãy kiểm tra file và ngôn ngữ đã chọn.");
    // A caption in another language is complete; a truncated model response is not.
    const complete = !warning || !method.startsWith("Gemini");
    showResult(text, method, source, complete, warning);
    produced = true;
    setStatus(`${complete ? "Xong" : "Chưa hoàn tất"} sau ${Math.round((Date.now() - started) / 1000)} giây · ${method}${warning ? `\n${warning}` : ""}`);
  } catch (e) {
    const message = activeJob.signal.aborted ? "Đã dừng." : `Lỗi: ${e.message}`;
    if (produced) $("result-note").textContent = `Chưa hoàn tất · ${last.method} · ${last.source}\n${message} Phần đã chép được giữ bên dưới.`;
    setStatus(`${message}${last ? produced ? " Phần đã chép vẫn có thể sao chép và tải về." : " Kết quả bên dưới vẫn thuộc lần trước." : ""}`);
  } finally {
    activeJob = null;
    for (const id of ["run", "url", "file", "lang", "source-link", "source-file"]) $(id).disabled = false;
    $("run").firstChild.textContent = "Tạo transcript";
    if ($("status").dataset.state === "busy") $("status").dataset.state = "idle";
    $("cancel").classList.add("hidden");
  }
}

function download(ext) {
  if (!last) return;
  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
  const body =
    ext === "md"
      ? `# Transcript\n\n- Nguồn: ${last.source}\n- Cách lấy: ${last.method}\n- Trạng thái: ${last.complete ? "Hoàn tất" : "Chưa hoàn tất"}\n- Ngày: ${new Date().toLocaleString("vi-VN")}\n\n${last.text}\n`
      : last.text;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
  a.download = `transcript-${last.complete ? "" : "partial-"}${stamp}.${ext}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

$("run").addEventListener("click", run);
$("cancel").addEventListener("click", () => activeJob?.abort());
$("source-link").addEventListener("click", () => selectSource("link"));
$("source-file").addEventListener("click", () => selectSource("file"));
$("file").addEventListener("change", () => {
  $("file-name").textContent = $("file").files[0]?.name || "Video hoặc audio của bạn";
});
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("output").value);
    $("copy-status").textContent = "Đã sao chép.";
  } catch {
    $("output").focus();
    $("output").select();
    $("copy-status").textContent = "Không truy cập được clipboard. Nội dung đã được chọn để bạn sao chép thủ công.";
  }
});
$("dl-txt").addEventListener("click", () => download("txt"));
$("dl-md").addEventListener("click", () => download("md"));
