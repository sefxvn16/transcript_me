// Forwards generateContent calls to the Gemini API from a region Gemini supports.
// Holds no secrets: the caller sends its own x-goog-api-key.
const GEMINI = "https://generativelanguage.googleapis.com";

export default {
  async fetch(request) {
    const { pathname } = new URL(request.url);
    if (request.method !== "POST" || !/^\/v1beta\/models\/[\w.-]+:generateContent$/.test(pathname)) {
      return new Response("Not found", { status: 404 });
    }
    return fetch(GEMINI + pathname, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-goog-api-key": request.headers.get("x-goog-api-key") || "",
      },
      body: request.body,
    });
  },
};
