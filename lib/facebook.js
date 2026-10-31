// Facebook: pull a direct fbcdn video URL out of a public video page.

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36";

// Smaller renditions first: only the audio track is needed.
const PATTERNS = [
  /"browser_native_sd_url":"([^"]+)"/,
  /"playable_url":"([^"]+)"/,
  /"sd_src(?:_no_ratelimit)?":"([^"]+)"/,
  /"browser_native_hd_url":"([^"]+)"/,
  /"playable_url_quality_hd":"([^"]+)"/,
  /"hd_src(?:_no_ratelimit)?":"([^"]+)"/,
];

export function isFacebookUrl(url) {
  try {
    const host = new URL(url).hostname;
    return /(^|\.)facebook\.com$/.test(host) || host === "fb.watch";
  } catch {
    return false;
  }
}

export function isFbcdnUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && /(^|\.)fbcdn\.net$/.test(u.hostname);
  } catch {
    return false;
  }
}

export async function getFacebookVideoUrl(pageUrl) {
  const res = await fetch(pageUrl, {
    headers: { "user-agent": UA, "accept-language": "en-US,en;q=0.9", accept: "text/html" },
    redirect: "follow",
  });
  if (!res.ok) throw new Error(`Facebook HTTP ${res.status}`);
  const html = await res.text();
  for (const re of PATTERNS) {
    const m = html.match(re);
    if (m) {
      const url = JSON.parse(`"${m[1]}"`);
      if (isFbcdnUrl(url)) return url;
    }
  }
  const og = html.match(/<meta property="og:video(?::url)?" content="([^"]+)"/);
  if (og) {
    const url = og[1].replace(/&amp;/g, "&");
    if (isFbcdnUrl(url)) return url;
  }
  return null;
}
