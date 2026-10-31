import { isFacebookUrl, getFacebookVideoUrl } from "../../lib/facebook.js";

export async function onRequestPost({ request }) {
  const { url } = await request.json();
  if (!isFacebookUrl(url || "")) return Response.json({ error: "Link Facebook không hợp lệ" }, { status: 400 });
  try {
    const mediaUrl = await getFacebookVideoUrl(url);
    if (!mediaUrl) {
      return Response.json(
        { error: "Không lấy được video từ link này. Hãy tải video về rồi upload." },
        { status: 422 }
      );
    }
    return Response.json({ mediaUrl });
  } catch (e) {
    return Response.json({ error: `${e.message}. Hãy tải video về rồi upload.` }, { status: 502 });
  }
}
