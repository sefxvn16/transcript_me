// YouTube: caption lookup via the Innertube player API.

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

export function parseYouTubeId(url) {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    const host = u.hostname.replace(/^(www\.|m\.|music\.)/, "");
    let id;
    if (host === "youtu.be") id = u.pathname.slice(1).split("/")[0];
    else if (host === "youtube.com") {
      id = u.pathname === "/watch" ? u.searchParams.get("v") : u.pathname.match(/^\/(?:shorts|embed|live|v)\/([\w-]+)\/?$/)?.[1];
    }
    return /^[\w-]{11}$/.test(id || "") ? id : null;
  } catch {
    return null;
  }
}

function pickTrack(tracks, lang) {
  const manual = tracks.filter((t) => t.kind !== "asr");
  const byLang = (list) => list.find((t) => t.languageCode.split("-")[0] === lang);
  if (lang) return byLang(manual) || byLang(tracks) || manual[0] || tracks[0] || null;
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
  return [...trimmed.matchAll(/<(p|text)\b[^>]*>([\s\S]*?)<\/\1>/g)].map((m) =>
    decodeEntities(m[2]).replace(/\s+/g, " ").trim()
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
        signal: AbortSignal.timeout(12000),
      });
      if (!res.ok) continue;
      const player = await res.json();
      const tracks = player?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
      const track = pickTrack(tracks, lang);
      if (!track) continue;
      const captionUrl = new URL(track.baseUrl);
      if (captionUrl.protocol !== "https:" || !/(^|\.)youtube\.com$/.test(captionUrl.hostname)) continue;
      captionUrl.searchParams.set("fmt", "json3");
      const capRes = await fetch(captionUrl, { headers: { "user-agent": client.ua }, signal: AbortSignal.timeout(12000) });
      if (!capRes.ok) continue;
      const lines = captionLines(await capRes.text()).filter((l) => l && !/^\[.*\]$/.test(l));
      if (lines.length) return { text: lines.join("\n"), language: track.languageCode };
    } catch {
      // try the next client
    }
  }
  return null;
}
