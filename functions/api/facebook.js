import { isFacebookUrl, getFacebookVideoUrl } from "../../lib/facebook.js";

export async function onRequestPost({ request }) {
  let body;
  try { body = await request.json(); } catch {
    return Response.json({ error: "Nội dung gửi lên phải là JSON hợp lệ" }, { status: 400 });
  }
  const { url } = body || {};
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
