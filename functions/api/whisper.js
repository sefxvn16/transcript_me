// Body: base64 of a 16 kHz mono WAV chunk, sent as text so the Worker passes it through without re-encoding.
export async function onRequestPost({ request, env }) {
  const params = new URL(request.url).searchParams;
  // A 30-second 16 kHz mono WAV is about 1.28 MB after base64 encoding.
  if (Number(request.headers.get("content-length")) > 1400000) {
    return Response.json({ error: "Đoạn audio quá lớn, tối đa 30 giây" }, { status: 413 });
  }
  const audio = await request.text();
  if (audio.length > 1400000) return Response.json({ error: "Đoạn audio quá lớn" }, { status: 413 });
  if (!audio || !/^[A-Za-z0-9+/]+={0,2}$/.test(audio) || audio.length % 4) {
    return Response.json({ error: "Audio base64 không hợp lệ" }, { status: 400 });
  }
  const input = { audio, task: "transcribe", vad_filter: true };
  const lang = params.get("lang");
  if (lang && !["vi", "en"].includes(lang)) return Response.json({ error: "Ngôn ngữ không hợp lệ" }, { status: 400 });
  if (lang) input.language = lang;
  const prompt = params.get("prompt");
  if (prompt) input.initial_prompt = prompt.slice(-200);
  try {
    if (!env.AI) return Response.json({ error: "Website chưa được cấu hình Workers AI (binding AI)" }, { status: 503 });
    const result = await env.AI.run("@cf/openai/whisper-large-v3-turbo", input);
    return Response.json({ text: (result.text || "").trim() });
  } catch (e) {
    return Response.json({ error: `Whisper lỗi: ${e.message}` }, { status: 502 });
  }
}
