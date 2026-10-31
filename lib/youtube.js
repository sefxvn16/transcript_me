// YouTube: caption lookup via the Innertube player API, transcript fallback via Gemini.

const CLIENTS = [
  {
    ua: "com.google.ios.youtube/20.10.4 (iPhone16,2; U; CPU iOS 18_3 like Mac OS X)",
    ctx: { clientName: "IOS", clientVersion: "20.10.4", deviceModel: "iPhone16,2", hl: "en" },
  },
  {
    ua: "com.google.android.youtube/20.10.38 (Linux; U; Android 14) gzip",
    ctx: { clientName: "ANDROID", clientVersion: "20.10.38", androidSdkVersion: 34, hl: "en" },
  },
];

const GEMINI_MODEL = "gemini-3.8-flash";

export function parseYouTubeId(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^(www\.|m\.|music\.)/, "");
    if (host === "youtu.be") return u.pathname.slice(1).split("/")[0] || null;
    if (host !== "youtube.com") return null;
    if (u.searchParams.get("v")) return u.searchParams.get("v");
    const m = u.pathname.match(/^\/(shorts|embed|live|v)\/([\w-]{11})/);
    return m ? m[2] : null;
  } catch {
    return null;
  }
}

function pickTrack(tracks, lang) {
  const manual = tracks.filter((t) => t.kind !== "asr");
  const byLang = (list) => list.find((t) => t.languageCode.split("-")[0] === lang);
  if (lang) return byLang(manual) || byLang(tracks) || null;
  return manual[0] || tracks[0] || null;
}

function decodeEntities(s) {
  return s
    .replace(/<[^>]+>/g, "")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

// Caption bodies come back either as json3 or as timedtext XML depending on the client.
function captionLines(body) {
  const trimmed = body.trimStart();
  if (trimmed.startsWith("{")) {
    const data = JSON.parse(trimmed);
    return (data.events || [])
      .map((e) => (e.segs || []).map((s) => s.utf8).join(""))
      .map((l) => l.replace(/\s+/g, " ").trim());
  }
  return [...trimmed.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/g)].map((m) =>
    decodeEntities(m[1]).replace(/\s+/g, " ").trim()
  );
}

// Returns { text, language } or null when no usable caption track is reachable.
export async function getYouTubeCaptions(videoId, lang) {
  for (const client of CLIENTS) {
    try {
      const res = await fetch("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", {
        method: "POST",
        headers: { "content-type": "application/json", "user-agent": client.ua },
        body: JSON.stringify({ context: { client: client.ctx }, videoId }),
      });
      if (!res.ok) continue;
      const player = await res.json();
      const tracks = player?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
      const track = pickTrack(tracks, lang);
      if (!track) continue;
      const capRes = await fetch(track.baseUrl + "&fmt=json3", { headers: { "user-agent": client.ua } });
      if (!capRes.ok) continue;
      const lines = captionLines(await capRes.text()).filter((l) => l && !/^\[.*\]$/.test(l));
      if (lines.length) return { text: lines.join("\n"), language: track.languageCode };
    } catch {
      // try the next client
    }
  }
  return null;
}

export async function transcribeWithGemini(url, lang, apiKey) {
  const langHint = lang === "vi" ? " The speech is in Vietnamese." : lang === "en" ? " The speech is in English." : "";
  const prompt =
    "Transcribe the spoken audio of this video verbatim, in its original language." +
    langHint +
    " Output only the transcript text split into paragraphs. Do not summarize, translate, add timestamps or add comments.";
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`,
    {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }, { file_data: { file_uri: url } }] }],
      }),
    }
  );
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || `Gemini HTTP ${res.status}`);
  const text = (data.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("").trim();
  if (!text) throw new Error("Gemini không trả về nội dung");
  return text;
}
