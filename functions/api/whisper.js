// Body: base64 of a 16 kHz mono WAV chunk, sent as text so the Worker passes it through without re-encoding.
export async function onRequestPost({ request, env }) {
  const params = new URL(request.url).searchParams;
  const input = { audio: await request.text(), task: "transcribe", vad_filter: true };
  const lang = params.get("lang");
  if (lang) input.language = lang;
  const prompt = params.get("prompt");
  if (prompt) input.initial_prompt = prompt;
  try {
    const result = await env.AI.run("@cf/openai/whisper-large-v3-turbo", input);
    return Response.json({ text: (result.text || "").trim() });
  } catch (e) {
    return Response.json({ error: `Whisper lỗi: ${e.message}` }, { status: 502 });
  }
}
