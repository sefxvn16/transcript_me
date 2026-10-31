# Transcript

Web cá nhân lấy transcript tiếng Việt/tiếng Anh từ link YouTube, Facebook công khai hoặc file video/audio. Không lưu gì trên server; kết quả hiện ngay, tải về `.txt` hoặc `.md`.

## Cách hoạt động

| Đầu vào | Xử lý |
|---|---|
| YouTube | Lấy phụ đề có sẵn (Innertube). Không có phụ đề → Gemini API nghe video và trả transcript |
| Facebook công khai | Function bóc link video fbcdn → trình duyệt tải về qua `/api/media` → Whisper |
| File upload | Trình duyệt giải mã, chuyển 16 kHz mono, cắt đoạn 30 giây → Whisper (Workers AI) |

Cấu trúc:

```
public/          giao diện (index.html, app.js)
functions/api/   Pages Functions: youtube, facebook, media, whisper
lib/             logic YouTube và Facebook
wrangler.toml    cấu hình Pages + binding Workers AI
gemini-worker/   Worker riêng chạy gần Singapore, chuyển tiếp request tới Gemini API
```

Không có dependency npm, không có bước build.

## Deploy (làm một lần)

1. **GitHub:** tạo repo (nên để private) và push toàn bộ thư mục này.
2. **Cloudflare Pages:** Dashboard → Workers & Pages → Create → Pages → Connect to Git → chọn repo.
   - Framework preset: `None`
   - Build command: để trống
   - Build output directory: `public`
   - Binding Workers AI (`AI`) đã khai trong `wrangler.toml`, không cần thêm tay.
3. **Gemini API key** (cho YouTube không có phụ đề): lấy miễn phí ở https://aistudio.google.com → Get API key. Trong project Pages: Settings → Variables and Secrets → thêm `GEMINI_API_KEY`, loại Secret, môi trường Production → deploy lại.
4. **Worker proxy cho Gemini** (Pages chạy ở Hồng Kông, Gemini không hỗ trợ Hồng Kông): Workers & Pages → Create → Continue with GitHub → repo này.
   - Project name: `transcript-gemini` (phải trùng `name` trong `gemini-worker/wrangler.toml`)
   - Advanced → Root directory: `gemini-worker`
   - Deploy xong, copy địa chỉ `https://transcript-gemini.<tài-khoản>.workers.dev`, điền vào `GEMINI_PROXY_URL` trong `wrangler.toml` gốc rồi push.
   - Worker không giữ secret nào; key Gemini vẫn chỉ nằm ở Pages.
5. **Khóa web chỉ mình bạn dùng (tùy chọn, hiện không dùng):** Cloudflare Zero Trust → Access → Applications → Add application → Self-hosted → domain `<tên-project>.pages.dev` → policy Allow, Include: Emails = email của bạn. Giao diện Cloudflare có thể đã đổi tên mục.

Sau đó chỉ cần push lên GitHub, Cloudflare tự deploy.

## Giới hạn

- Workers AI miễn phí 10.000 neurons/ngày, khoảng 3,5 giờ audio Whisper (tự tính từ bảng giá 10/2026).
- Gemini free tier: tối đa 8 giờ video YouTube/ngày, chỉ video công khai; tính năng đang preview. Gói miễn phí có thể dùng dữ liệu để cải thiện sản phẩm.
- Gemini có thể chép không đúng nguyên văn; phụ đề có sẵn được ưu tiên.
- File rất dài (trên khoảng 1 giờ) có thể làm trình duyệt điện thoại hết bộ nhớ khi giải mã.
- Lấy phụ đề YouTube và bóc link Facebook dùng API không chính thức, có thể hỏng khi nền tảng thay đổi. Khi hỏng: tải video về rồi upload.
