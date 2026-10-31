import { parseYouTubeId, getYouTubeCaptions, transcribeWithGemini } from "../../lib/youtube.js";

export async function onRequestPost({ request, env }) {
  const { url, lang } = await request.json();
  const videoId = parseYouTubeId(url || "");
  if (!videoId) return Response.json({ error: "Link YouTube không hợp lệ" }, { status: 400 });

  const captions = await getYouTubeCaptions(videoId, lang || null);
  if (captions) return Response.json({ text: captions.text, method: `Phụ đề YouTube (${captions.language})` });

  if (!env.GEMINI_API_KEY) {
    return Response.json({ error: "Video không có phụ đề và chưa cấu hình GEMINI_API_KEY" }, { status: 500 });
  }
  try {
    const text = await transcribeWithGemini(
      `https://www.youtube.com/watch?v=${videoId}`,
      lang,
      env.GEMINI_API_KEY,
      env.GEMINI_PROXY_URL
    );
    return Response.json({ text, method: "Gemini API" });
  } catch (e) {
    return Response.json({ error: `Gemini lỗi: ${e.message}` }, { status: 502 });
  }
}
