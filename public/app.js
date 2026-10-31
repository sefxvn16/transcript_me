const SAMPLE_RATE = 16000;
const CHUNK_SECONDS = 30;
const GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash"];
const KEY_STORAGE = "gemini-api-key";

const $ = (id) => document.getElementById(id);
let last = null; // { text, source, method }

function loadKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function saveKey(key) {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    // storage blocked (private mode): the key still works for this page load
  }
}

function setStatus(msg) {
  $("status").textContent = msg;
}

async function postJson(path, body) {
  const res = await fetch(path, {
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
  const apiKey = $("gemini-key").value.trim();
  if (!apiKey) {
    $("settings").open = true;
    throw new Error("Video không có phụ đề. Nhập Gemini API key ở mục bên trên rồi bấm lại.");
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
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }, { file_data: { file_uri: url } }] }] }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 429 || res.status === 503) {
      lastError = new Error(`${model}: ${data?.error?.message || res.status}`);
      continue;
    }
    if (!res.ok) throw new Error(`Gemini: ${data?.error?.message || res.status}`);
    const text = (data.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("").trim();
    if (!text) {
      const reason = data.candidates?.[0]?.finishReason || data.promptFeedback?.blockReason || "không rõ";
      const hint = reason === "RECITATION" ? " (nội dung có bản quyền, ví dụ lời bài hát)" : "";
      throw new Error(`Gemini không trả về nội dung, lý do: ${reason}${hint}`);
    }
    return { text, method: `Gemini (${model})` };
  }
  throw lastError;
}

// Decode any audio/video the browser can play, then downmix and resample to 16 kHz mono.
async function decodeToMono16k(arrayBuffer) {
  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(arrayBuffer);
  ctx.close();
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

async function transcribeAudio(arrayBuffer, lang) {
  setStatus("Đang giải mã audio...");
  const samples = await decodeToMono16k(arrayBuffer);
  const size = CHUNK_SECONDS * SAMPLE_RATE;
  const total = Math.ceil(samples.length / size);
  const parts = [];
  for (let i = 0; i < total; i++) {
    setStatus(`Đang chuyển giọng nói thành chữ: đoạn ${i + 1}/${total}`);
    const b64 = await blobToBase64(encodeWav(samples.subarray(i * size, (i + 1) * size)));
    const params = new URLSearchParams();
    if (lang) params.set("lang", lang);
    const prev = parts.join(" ").slice(-200);
    if (prev) params.set("prompt", prev);
    const res = await fetch(`/api/whisper?${params}`, { method: "POST", body: b64 });
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
    if (!res.ok || data.error) throw new Error(`Đoạn ${i + 1}: ${data.error || res.status}`);
    if (data.text) parts.push(data.text);
  }
  return parts.join("\n");
}

async function run() {
  const url = $("url").value.trim();
  const file = $("file").files[0];
  const lang = $("lang").value;
  $("run").disabled = true;
  $("result").classList.add("hidden");
  const started = Date.now();
  try {
    let text, method, source;
    if (file) {
      source = file.name;
      text = await transcribeAudio(await file.arrayBuffer(), lang);
      method = "Whisper (Workers AI)";
    } else if (url && isYouTube(url)) {
      source = url;
      setStatus("Đang tìm phụ đề YouTube...");
      ({ text, method } = await postJson("/api/youtube", { url, lang }));
      if (!text) ({ text, method } = await transcribeWithGemini(url, lang));
    } else if (url && isFacebook(url)) {
      source = url;
      setStatus("Đang tìm video trong link Facebook...");
      const { mediaUrl } = await postJson("/api/facebook", { url });
      setStatus("Đang tải video...");
      const res = await fetch(`/api/media?url=${encodeURIComponent(mediaUrl)}`);
      if (!res.ok) throw new Error(await res.text());
      text = await transcribeAudio(await res.arrayBuffer(), lang);
      method = "Whisper (Workers AI)";
    } else {
      throw new Error("Hãy dán link YouTube/Facebook hoặc chọn file. Link khác: tải về rồi upload.");
    }
    last = { text, method, source };
    $("output").value = text;
    $("result").classList.remove("hidden");
    setStatus(`Xong sau ${Math.round((Date.now() - started) / 1000)} giây · ${method}`);
  } catch (e) {
    setStatus(`Lỗi: ${e.message}`);
  } finally {
    $("run").disabled = false;
  }
}

function download(ext) {
  if (!last) return;
  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
  const body =
    ext === "md"
      ? `# Transcript\n\n- Nguồn: ${last.source}\n- Cách lấy: ${last.method}\n- Ngày: ${new Date().toLocaleString("vi-VN")}\n\n${last.text}\n`
      : last.text;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
  a.download = `transcript-${stamp}.${ext}`;
  a.click();
  URL.revokeObjectURL(a.href);
}

$("gemini-key").value = loadKey();
$("gemini-key").addEventListener("change", (e) => saveKey(e.target.value.trim()));
$("run").addEventListener("click", run);
$("copy").addEventListener("click", () => navigator.clipboard.writeText($("output").value));
$("dl-txt").addEventListener("click", () => download("txt"));
$("dl-md").addEventListener("click", () => download("md"));
