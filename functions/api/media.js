import { isFbcdnUrl } from "../../lib/facebook.js";

// Streams an fbcdn video to the browser, which cannot fetch it directly because of CORS.
export async function onRequestGet({ request }) {
  const target = new URL(request.url).searchParams.get("url") || "";
  if (!isFbcdnUrl(target)) return new Response("URL không được phép", { status: 400 });
  const upstream = await fetch(target);
  if (!upstream.ok) return new Response(`Tải video lỗi: HTTP ${upstream.status}`, { status: 502 });
  return new Response(upstream.body, {
    headers: { "content-type": upstream.headers.get("content-type") || "video/mp4" },
  });
}
