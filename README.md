# Transcript

Web cá nhân lấy transcript tiếng Việt/tiếng Anh từ link YouTube, Facebook công khai hoặc file video/audio. Media trên Render chỉ được giữ tạm trong lúc xử lý rồi xóa; transcript hiện trên trình duyệt và tải về `.txt` hoặc `.md`.

## Phạm vi hiện tại

- YouTube: ưu tiên phụ đề của ngôn ngữ đã chọn; nếu không có, dùng phụ đề có sẵn và báo ngôn ngữ thực tế. Chỉ gọi Gemini khi không lấy được phụ đề. Website không dịch transcript.
- Facebook: trình duyệt gọi Render để tải và chuyển audio bằng yt-dlp/FFmpeg, sau đó chia đoạn gửi Whisper. Chỉ nhận link HTTPS, video tối đa 1 giờ và file tải tối đa 32 MiB. Link `https://www.facebook.com/share/v/1cJ7U3xjpA/` đã tải/chuyển audio thành công trên Render ngày 01/11/2026; chưa xác nhận mọi link Reel hoặc video công khai đều tải được. Khi không lấy được, tải video hoặc audio về rồi chọn file.
- TikTok và X.com: hiện dùng file video/audio, chưa hỗ trợ tải trực tiếp từ link.
- File được chia thành đoạn 30 giây. Nội dung từng đoạn được giữ ngay khi nhận; nếu lỗi hoặc dừng, vẫn sao chép và tải được phần đã chép. File tải chưa đủ có `partial-` trong tên.
- Gemini trả nội dung bị cắt hoặc kết thúc bất thường sẽ được đánh dấu chưa hoàn tất. Không tự coi nội dung đó là transcript đầy đủ.

Giữ Cloudflare Pages cho giao diện và Whisper, thêm Render Free cho downloader theo lựa chọn ngày 01/11/2026.

`downloader-trial/` và `render.yaml` chứa backend Render. `POST /audio` nhận
JSON `{ "url": "https://www.facebook.com/..." }` và trả MP3 cho trang
`https://transcript-me.pages.dev`. Mỗi lúc chỉ chạy một lượt tải/chuyển audio.
Link chia sẻ được theo tối đa 5 chuyển hướng trong Facebook, timeout mỗi request
15 giây. Giới hạn tải 150 giây, kiểm nguồn 10 giây, chuyển audio 90 giây và kiểm
kết quả 10 giây; tổng file tạm tối đa 64 MiB. File tạm được xóa trước khi trả audio.
Nút Dừng hủy yêu cầu phía trình duyệt; một lượt đã chạy trên Render có thể tiếp tục
đến hết hoặc đến giới hạn thời gian rồi tự dọn file.

`POST /trial` vẫn kiểm riêng link mẫu, trả metadata audio và xóa file tạm;
gọi lại trả kết quả cũ trong cùng phiên server. `GET /health` kiểm dịch vụ sẵn sàng.
Không dùng cookie Facebook, database, thẻ thanh toán hoặc instance trả phí.
Máy chủ khởi động lại sẽ mất kết quả thử đã ghi trong RAM. CORS chỉ cho phép
website production đọc audio, không phải cơ chế đăng nhập; người dùng đã chọn
không khóa web, nên endpoint vẫn có thể bị dùng chung quota.

Để thử trên Render: tạo Blueprint từ repo này (đọc `render.yaml`), xác nhận
service `transcript-downloader-trial` có plan **Free**, rồi Deploy. Hoặc tạo
Web Service, chọn repo, Root directory `downloader-trial`, runtime Docker,
instance Free, health check `/health`. Deploy xong mới gọi `POST /trial`.
Render Free ngủ khi không dùng; cần chờ khởi động lại trước khi thử.
Người dùng đã thiết lập cron-job.org gọi `/health` mỗi 10 phút và báo HTTP 200.
Render Free vẫn giới hạn 750 giờ/tháng dùng chung workspace và có thể restart.

## Cách hoạt động

| Đầu vào | Xử lý |
|---|---|
| YouTube | Lấy phụ đề có sẵn (Innertube). Không có phụ đề → trình duyệt gọi thẳng Gemini API (key lưu trên thiết bị) |
| Facebook công khai | Trình duyệt gọi Render `/audio` → MP3 → chia đoạn 30 giây → Whisper (Workers AI) |
| File upload | Trình duyệt giải mã, chuyển 16 kHz mono, cắt đoạn 30 giây → Whisper (Workers AI) |

Cấu trúc:

```
public/          giao diện (index.html, app.js)
functions/api/   Pages Functions: youtube, facebook, media, whisper
lib/             logic YouTube và Facebook
wrangler.toml    cấu hình Pages + binding Workers AI
downloader-trial/ backend Python + yt-dlp/FFmpeg chạy trên Render Free
render.yaml      cấu hình deploy Render
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
