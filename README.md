# Transcript

Web cá nhân lấy transcript tiếng Việt/tiếng Anh từ link YouTube, Facebook công khai hoặc file video/audio. Không lưu gì trên server; kết quả hiện ngay, tải về `.txt` hoặc `.md`.

## Phạm vi hiện tại

- YouTube: ưu tiên phụ đề của ngôn ngữ đã chọn; nếu không có, dùng phụ đề có sẵn và báo ngôn ngữ thực tế. Chỉ gọi Gemini khi không lấy được phụ đề. Website không dịch transcript.
- Facebook: thử lấy video công khai. Link Reel mẫu `https://www.facebook.com/share/r/1E6dFuLXQ6/` đã trả HTTP 400 trên Cloudflare ngày 31/10/2026; chưa có cách tải tự động được kiểm chứng cho link này. Khi không lấy được, tải video hoặc audio về rồi chọn file.
- TikTok và X.com: hiện dùng file video/audio, chưa hỗ trợ tải trực tiếp từ link.
- File được chia thành đoạn 30 giây. Nội dung từng đoạn được giữ ngay khi nhận; nếu lỗi hoặc dừng, vẫn sao chép và tải được phần đã chép. File tải chưa đủ có `partial-` trong tên.
- Gemini trả nội dung bị cắt hoặc kết thúc bất thường sẽ được đánh dấu chưa hoàn tất. Không tự coi nội dung đó là transcript đầy đủ.

Giữ Cloudflare Pages, không cài thêm downloader hoặc backend riêng theo lựa chọn của người dùng ngày 31/10/2026.

Ngày 01/11/2026 người dùng duyệt thử backend Render Free. Thư mục
`downloader-trial/` và `render.yaml` chỉ phục vụ phép thử, chưa nối vào trang chính.
Backend dùng yt-dlp/ffmpeg, chỉ nhận đúng link Facebook mẫu đã duyệt:
`POST /trial` trả kết quả tải/chuyển MP3/kiểm audio và xóa file tạm; gọi lại trả
kết quả cũ trong cùng phiên server. `GET /health` kiểm dịch vụ sẵn sàng.
Không dùng cookie Facebook, database, thẻ thanh toán hoặc instance trả phí.
Máy chủ khởi động lại sẽ mất kết quả thử đã ghi trong RAM.

Để thử trên Render: tạo Blueprint từ repo này (đọc `render.yaml`), xác nhận
service `transcript-downloader-trial` có plan **Free**, rồi Deploy. Hoặc tạo
Web Service, chọn repo, Root directory `downloader-trial`, runtime Docker,
instance Free, health check `/health`. Deploy xong mới gọi `POST /trial`.
Render Free ngủ khi không dùng; cần chờ khởi động lại trước khi thử.

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
3. **Gemini API key** (cho YouTube không có phụ đề): lấy miễn phí ở https://aistudio.google.com → Get API key. Mở đường dẫn `/key` trên website, dán key và bấm Lưu key; nhập một lần trên mỗi thiết bị. Key cũ vẫn dùng được. Trang chính không có liên kết tới trang thiết lập. Trang riêng không yêu cầu đăng nhập; ai biết đường dẫn vẫn mở được. Key chỉ lưu trong trình duyệt đó.
4. **Khóa web chỉ mình bạn dùng (tùy chọn, hiện không dùng):** Cloudflare Zero Trust → Access → Applications → Add application → Self-hosted → domain `<tên-project>.pages.dev` → policy Allow, Include: Emails = email của bạn. Giao diện Cloudflare có thể đã đổi tên mục.

Sau đó chỉ cần push lên GitHub, Cloudflare tự deploy.

## Giới hạn

- Workers AI miễn phí 10.000 neurons/ngày, khoảng 3,5 giờ audio Whisper (tự tính từ bảng giá 10/2026).
- Gemini free tier: khoảng 20 request/ngày cho mỗi model (thấy trong lỗi quota 10/2026), tối đa 8 giờ video YouTube/ngày, chỉ video công khai; tính năng đang preview. Gói miễn phí có thể dùng dữ liệu để cải thiện sản phẩm.
- Gemini có thể chép không đúng nguyên văn; phụ đề có sẵn được ưu tiên.
- File rất dài (trên khoảng 1 giờ) có thể làm trình duyệt điện thoại hết bộ nhớ khi giải mã.
- Lấy phụ đề YouTube và bóc link Facebook dùng API không chính thức, có thể hỏng khi nền tảng thay đổi. Khi hỏng: tải video về rồi upload.
