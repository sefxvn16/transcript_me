import { parseYouTubeId, getYouTubeCaptions } from "../../lib/youtube.js";

// Captions only. Without captions the browser calls Gemini itself: the Worker
// lands in Hong Kong (unsupported by Gemini) and long Gemini calls hit Cloudflare's 100 s timeout.
export async function onRequestPost({ request }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: "Nội dung gửi lên phải là JSON hợp lệ" }, { status: 400 });
  }
  const { url, lang } = body || {};
  if (![undefined, null, "", "vi", "en"].includes(lang)) {
    return Response.json({ error: "Ngôn ngữ không hợp lệ" }, { status: 400 });
  }
  const videoId = parseYouTubeId(url || "");
  if (!videoId) return Response.json({ error: "Link YouTube không hợp lệ" }, { status: 400 });

  const captions = await getYouTubeCaptions(videoId, lang || null);
  if (!captions) return Response.json({ text: null });
  return Response.json({ text: captions.text, method: `Phụ đề YouTube (${captions.language})`, language: captions.language });
}
