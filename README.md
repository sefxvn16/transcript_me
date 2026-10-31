# Transcript

Web cá nhân lấy transcript tiếng Việt/tiếng Anh từ link YouTube, Facebook công khai hoặc file video/audio. Không lưu gì trên server; kết quả hiện ngay, tải về `.txt` hoặc `.md`.

## Cách hoạt động

| Đầu vào | Xử lý |
|---|---|
| YouTube | Lấy phụ đề có sẵn (Innertube). Không có phụ đề → trình duyệt gọi thẳng Gemini API (key lưu trên thiết bị) |
| Facebook công khai | Function bóc link video fbcdn → trình duyệt tải về qua `/api/media` → Whisper |
| File upload | Trình duyệt giải mã, chuyển 16 kHz mono, cắt đoạn 30 giây → Whisper (Workers AI) |

Cấu trúc:

```
public/          giao diện (index.html, app.js)
functions/api/   Pages Functions: youtube, facebook, media, whisper
lib/             logic YouTube và Facebook
wrangler.toml    cấu hình Pages + binding Workers AI
```

Không có dependency npm, không có bước build.

## Deploy (làm một lần)

1. **GitHub:** tạo repo (nên để private) và push toàn bộ thư mục này.
2. **Cloudflare Pages:** Dashboard → Workers & Pages → Create → Pages → Connect to Git → chọn repo.
   - Framework preset: `None`
   - Build command: để trống
   - Build output directory: `public`
   - Binding Workers AI (`AI`) đã khai trong `wrangler.toml`, không cần thêm tay.
3. **Gemini API key** (cho YouTube không có phụ đề): lấy miễn phí ở https://aistudio.google.com → Get API key. Trên web, mở mục "Gemini API key" và dán key; nhập một lần trên mỗi thiết bị, key chỉ lưu trong trình duyệt đó. Gọi từ trình duyệt vì Function chạy ở Hồng Kông (Gemini không hỗ trợ) và Cloudflare cắt request chờ quá ~100 giây.
4. **Khóa web chỉ mình bạn dùng (tùy chọn, hiện không dùng):** Cloudflare Zero Trust → Access → Applications → Add application → Self-hosted → domain `<tên-project>.pages.dev` → policy Allow, Include: Emails = email của bạn. Giao diện Cloudflare có thể đã đổi tên mục.

Sau đó chỉ cần push lên GitHub, Cloudflare tự deploy.

## Giới hạn

- Workers AI miễn phí 10.000 neurons/ngày, khoảng 3,5 giờ audio Whisper (tự tính từ bảng giá 10/2026).
- Gemini free tier: khoảng 20 request/ngày cho mỗi model (thấy trong lỗi quota 10/2026), tối đa 8 giờ video YouTube/ngày, chỉ video công khai; tính năng đang preview. Gói miễn phí có thể dùng dữ liệu để cải thiện sản phẩm.
- Gemini có thể chép không đúng nguyên văn; phụ đề có sẵn được ưu tiên.
- File rất dài (trên khoảng 1 giờ) có thể làm trình duyệt điện thoại hết bộ nhớ khi giải mã.
- Lấy phụ đề YouTube và bóc link Facebook dùng API không chính thức, có thể hỏng khi nền tảng thay đổi. Khi hỏng: tải video về rồi upload.
