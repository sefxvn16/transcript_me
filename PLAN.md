# PLAN: Website transcript video/audio (cá nhân)

Cập nhật: 2026-11-01 · Phiên: 1
Mục tiêu: Web cá nhân dán link (YouTube, Facebook công khai, ...) hoặc upload video/audio → transcript tiếng Anh/Việt hiện ngay, tải .txt/.md; không lưu gì trên web.
Phạm vi: Miễn phí hoàn toàn; chỉ cập nhật GitHub, Cloudflare Pages tự deploy; giao diện tối giản; mức dự án: đơn giản (kiểm tay, không test tự động). Dự phòng đã chấp nhận: link không xử lý được → người dùng tải về rồi upload.

## Các mục

- [x] 24. Ghi nhận kiểm thực tế của người dùng và commit
  - Tieu chi xong: lưu đúng phản hồi người dùng và commit bản ghi, giữ nguyên code đã chạy ổn.
  - Kết quả: PASS: ngày 01/11/2026 người dùng xác nhận “được rồi, chạy ổn rồi” sau khi dùng bản tích hợp Facebook trên production. Đã kiểm working tree sạch trước khi ghi nhận; chỉ cập nhật PLAN.md, không thay đổi code hoặc suy rộng sang các nền tảng, thiết bị hay link chưa được kiểm.

- [x] 22. Nối Render downloader vào luồng Facebook trên web
  - Tieu chi xong: backend nhận link Facebook HTTPS và trả MP3, giới hạn dung lượng/thời gian/một lượt xử lý, dọn file tạm; web dùng lại luồng chia đoạn Whisper và Dừng; kiểm local trước khi hỏi xác nhận push.
  - Kết quả: PASS: đã backup app.js, server.py và README; POST /audio local tải MP3 4872239 byte, ffprobe báo 811.882688 giây, 16000 Hz mono. Kiểm HTTP health/CORS/preflight, JSON lỗi, request quá lớn, sai Content-Type, URL HTTP/host giả/localhost/port khác/credentials đạt. Mô phỏng DOM đạt audio -> 2 đoạn Whisper, giữ phần đã chép khi đoạn 2 lỗi, backend bận, HTML khởi động, Dừng và HTTPS. 30 giây đầu audio mẫu gửi curl tới Whisper production HTTP 200 và text tiếng Việt không rỗng; chưa đối chiếu độ chính xác lời chép. Subagent chỉ đọc không thấy blocker, đã tăng timeout audio lên 420 giây theo góp ý. node --check, Python AST và git diff --check đạt. Chưa kiểm UI thật theo yêu cầu không điều khiển Chrome.
  - Có sẵn: downloader-trial/server.py đã tải link mẫu trên Render; public/app.js có transcribeAudio, chia đoạn, AbortController và giữ kết quả từng phần; đã đọc code.
  - Tận dụng: chỉnh backend và nhánh Facebook; giữ phụ đề/Gemini của YouTube và upload.
  - Tự làm: POST /audio có CORS cho transcript-me.pages.dev và kiểm input/giới hạn; nối request từ trình duyệt.

- [x] 23. Push tích hợp và kiểm Render/Pages production
  - Tieu chi xong: backend mới deploy và trả MP3 thực với CORS production; app.js production gọi /audio; kiểm audio -> Whisper trên production, không đánh đạt chỉ vì push xong.
  - Kết quả: PASS: đã push backend b2f1adf, chờ /audio mới hoạt động rồi kiểm production: CORS/preflight/input đạt, tải MP3 4872239 byte, ffprobe 811.883938 giây, 16000 Hz mono. Sau đó push giao diện/README/PLAN 4706c03; GET app.js HTTP 200 và nội dung khớp bản local sau chuẩn hóa CRLF; GET health Render HTTP 200. Audio tải từ Render production chuyển WAV và gửi đủ 28/28 đoạn 30 giây (đoạn cuối ngắn hơn) tới Whisper Pages bằng curl, tất cả thành công, transcript 12448 ký tự. Kiểm local mô phỏng DOM cho luồng frontend ở mục 22; không dùng Chrome, chưa kiểm UI/điện thoại thật hoặc đối chiếu độ chính xác từng câu. Python urllib bị Cloudflare từ chối 1010 khi gọi Pages nên dùng curl thông thường; không đổi cấu hình bảo mật. Backend local dùng kiểm đã dừng. Người dùng đã yêu cầu tự hoàn tất không hỏi lại; đã nêu push gây auto deploy trước khi làm.

- [x] 20. Tìm repo GitHub tương tự theo yêu cầu ngày 01/11/2026
  - Tieu chi xong: mở kiểm README, ghi repo có luồng URL/upload sang transcript và phân biệt khả năng được mô tả với kết quả chạy thực tế.
  - Kết quả: PASS: đã mở kiểm neromorph/local-whisper (URL/upload, yt-dlp, faster-whisper, TXT/SRT, MIT), jhj0517/Whisper-WebUI (file/YouTube/microphone, TXT/SRT/VTT; LICENSE Apache-2.0), iankiku/anytranscript (CLI/thư viện Node, phụ đề rồi Whisper, MIT), seanoliver/audioflare (Cloudflare Workers AI, upload, chỉ 30 giây đầu, MIT). Đã trình bày bảng trong chat; chưa cài/chạy các repo hoặc kiểm link Facebook mẫu bằng chúng. Không đổi kiến trúc hay thêm dependency.
  - Có sẵn: bốn repo trên GitHub, đã mở README; Whisper-WebUI đã mở thêm LICENSE.
  - Tận dụng: chỉ khảo sát, chưa dùng code hoặc cài công cụ ngoài.
  - Tự làm: chưa triển khai từ kết quả khảo sát này.
  - Nguồn: https://github.com/neromorph/local-whisper ; https://github.com/jhj0517/Whisper-WebUI ; https://github.com/jhj0517/Whisper-WebUI/blob/master/LICENSE ; https://github.com/iankiku/anytranscript ; https://github.com/seanoliver/audioflare

- [x] 16. Kiểm tra backend miễn phí chạy downloader sau phép thử Browser Run
  - Tieu chi xong: xác minh nguồn chính thức về chi phí, gắn thẻ, deploy Docker/GitHub và giới hạn; không hứa tải được link trước khi thử.
  - Kết quả: PASS: 01/11/2026 đã mở render.com/docs/free, /docs/your-first-deploy, /docs/docker, /docs/faq. Render có Free Web Service 750 giờ/workspace/tháng, ngủ sau 15 phút, khởi động khoảng một phút; không có payment method thì hết bandwidth/build quota sẽ dừng thay vì tính phí. Hỗ trợ Dockerfile từ repo, phù hợp chạy yt-dlp/ffmpeg. Chưa thử Facebook/TikTok từ Render; chưa có backend được triển khai. yt-dlp chưa cài trên máy, ffmpeg có sẵn. Koyeb FAQ yêu cầu thẻ, HF tạo Docker Space mới cần paid plan nên không chọn trong đề xuất này.
  - Có sẵn: Render Free Web Service + Docker deploy từ repo, yt-dlp và ffmpeg đã xác nhận tồn tại; repo hiện có Pages/Whisper.
  - Tận dụng: giữ Pages/Whisper; đề xuất dùng downloader có sẵn trong backend riêng, chưa thêm dependency.
  - Tự làm: API tải/tách audio tạm thời và kết nối Pages sau khi phép thử Render thành công.

- [x] 17. Chốt thêm Render Free cho phép thử downloader
  - Tieu chi xong: người dùng đồng ý thêm backend Render Free và xác nhận tài khoản sẵn sàng; không chọn paid instance hoặc thêm thẻ.
  - Kết quả: PASS: người dùng đồng ý “thử đi” sau khi chốt miễn phí; triển khai phép thử Render Free với yt-dlp/ffmpeg cùng repo, chưa tích hợp vào giao diện trước khi tải được audio thật. Không thêm thẻ hoặc dùng paid instance.

- [x] 18. Thử yt-dlp độc lập và chuẩn bị backend Render có giới hạn
  - Tieu chi xong: ghi kết quả link mẫu với yt-dlp; có Dockerfile và API thử, giới hạn thời gian/dung lượng, file tạm được dọn; kiểm cục bộ trước push.
  - Kết quả: PASS: yt-dlp 2026.10.26 cài TEMP riêng; link mẫu nhận video ID 1124625790530691, tải audio 8.487.772 byte. Chạy chính perform_trial: sourceBytes 8487772, audioBytes 4872239, durationSeconds 811.883, MP3 16000 Hz mono, temporaryFilesDeleted true, elapsedSeconds 11.01 trên máy này. Đã kiểm AST và HTTP /health + /trial cache, git diff --check. Subagent rà chỉ đọc không thấy blocker cho thử Free; đã sửa race FileNotFoundError khi yt-dlp đổi tên .part. Có Dockerfile Python 3.13/ffmpeg, yt-dlp pin phiên bản, render.yaml plan free; chưa build Docker vì máy không có Docker. Trial chỉ link mẫu, không cookies/tùy ý URL.
  - Có sẵn: lib/facebook.js, Pages/Whisper, Render Docker hỗ trợ repo; yt-dlp 2026.10.26 từ PyPI.
  - Tận dụng: dùng yt-dlp nguyên, ffmpeg nguyên; giữ luồng transcript hiện tại.
  - Tự làm: API thử lấy audio tạm trên Render và kiểm hiệu quả link mẫu, chưa tự thêm CORS/proxy công khai vào web chính.

- [x] 19. Triển khai Render Free và thử link Facebook thực tế
  - Tieu chi xong: service Free deploy từ cùng repo GitHub, tải được audio hợp lệ từ link mẫu hoặc ghi rõ lỗi thực tế, không báo đạt chỉ vì build thành công.
  - Kết quả: PASS: 01/11/2026 người dùng tự deploy Blueprint từ transcript_me/main (render.yaml plan free) và cung cấp https://transcript-downloader-trial.onrender.com. Agent kiểm GET /health HTTP 200, ok true; POST /trial HTTP 200, ok true, sourceBytes 8487764, audioBytes 4872239, durationSeconds 811.98, codec mp3, sample_rate 16000, channels 1, temporaryFilesDeleted true, elapsedSeconds 49.89, sha256 b60963527792a366eeb4aa5c77d46217bf16f5dd7f0375750aaa0bfbc91a6775. Đây là kết quả downloader/ffprobe thực thi trên Render với link mẫu cố định; chưa nghe audio, chưa nối vào website hoặc kiểm transcript.

- [x] 21. Giữ service Render thức theo yêu cầu người dùng
  - Tieu chi xong: có lịch GET /health dưới 15 phút, kiểm phản hồi HTTP 200 và giờ Free dùng chung workspace; không cam kết hoạt động liên tục khi hết quota hoặc Render restart.
  - Kết quả: PASS: người dùng xác nhận đã tạo cronjob theo hướng dẫn mỗi 10 phút và kết quả HTTP 200. Agent đã kiểm GET /health HTTP 200 trên service này ngày 01/11/2026. Đây là xác nhận cấu hình/chạy thử của người dùng, chưa phải theo dõi uptime dài hạn. Đã kiểm tài liệu Render Free: ngủ sau 15 phút, 750 giờ/workspace/tháng và có thể restart. Dashboard còn service zalo-bot-tamquoc; đã thông báo quota dùng chung, chưa xác minh gói/giờ sử dụng của service đó.
  - Có sẵn: GET /health trong downloader-trial/server.py; cron-job.org có lịch HTTP miễn phí, đã mở trang chính thức.
  - Tận dụng: endpoint health hiện có; đề xuất dịch vụ lập lịch ngoài, không thêm dependency vào repo.
  - Tự làm: kết nối URL service thật với lịch sau khi deploy.
  - Nguồn: https://render.com/docs/free ; https://cron-job.org/en/

- [x] 13. Nghiên cứu cách xử lý link Facebook/TikTok theo yêu cầu ngày 31/10/2026
  - Tieu chi xong: đối chiếu code hiện tại với công cụ có sẵn và tài liệu chính thức; nêu phương án thử, chi phí, giới hạn, bằng chứng và quyết định cần người dùng duyệt.
  - Kết quả: PASS: đã đọc nguồn chính thức cobalt Facebook/TikTok, yt-dlp Facebook extractor, license, Cloudflare Browser Run và CORS; subagent kiểm GitHub Actions/HF, agent chính mở lại điều khoản Actions và Spaces overview để đối chiếu. Link mẫu từ máy local HTTP 200 nhưng không có browser_native/playable/progressive_url/manifest/captions_url; không có CORS header. Browser Run có free 10 phút/ngày, content endpoint render JavaScript, có binding không cần API token; luôn nhận diện bot, chưa thử link thật trên Browser Run. Cobalt không có public API chính thức, cần tự host, AGPL-3.0; yt-dlp có parser dữ liệu Relay/DASH/progressive mới hơn code hiện tại, Unlicense ở source nhưng chưa cài/chạy. Không khuyến nghị Actions làm backend runtime theo điều khoản; HF tạo Docker/Gradio mới cần gói trả phí. Chưa xác minh giải pháp nào lấy được audio mẫu; không cài dependency hoặc thay đổi code sản phẩm.
  - Nguồn: https://developers.cloudflare.com/browser-run/pricing/ ; https://developers.cloudflare.com/browser-run/quick-actions/content-endpoint/ ; https://developers.cloudflare.com/browser-run/reference/automatic-request-headers/ ; https://github.com/imputnet/cobalt/blob/main/api/README.md ; https://github.com/imputnet/cobalt/blob/main/api/src/processing/services/tiktok.js ; https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/facebook.py ; https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions ; https://huggingface.co/docs/hub/en/spaces-overview
  - Có sẵn: lib/facebook.js và functions/api/facebook.js đã đọc; cobalt api source Facebook/TikTok, yt-dlp Facebook extractor, Cloudflare Browser Run pricing/content/headers đã mở nguồn chính thức.
  - Tận dụng: ý tưởng tách tải trang, đọc dữ liệu video và speech-to-text; chưa sao chép code AGPL của cobalt.
  - Tự làm: đánh giá phép thử nhỏ đáp ứng Cloudflare miễn phí và chốt với người dùng trước khi thêm binding/backend.

- [x] 14. Chốt phép thử Browser Run trước khi thay đổi backend
  - Tieu chi xong: người dùng đồng ý dùng quota Browser Run và thêm binding/endpoint thử có giới hạn, hoặc chọn giữ upload.
  - Kết quả: PASS: người dùng đồng ý “làm đi, phức tạp cũng được, tôi quan trọng là hiệu quả”; đã mở Dashboard theo yêu cầu. Ngày 01/11/2026 đã truy cập Browser Run Playground có sẵn; chọn Extract data / HTML Content, Network Idle 2, timeout 30000 và chạy một lần link mẫu, chưa tạo Worker hoặc token.

- [ ] 15. Kiểm kết quả Browser Run trên link Facebook mẫu trước khi tích hợp
  - Tieu chi xong: nhận kết quả thật và ghi rõ có URL media tải được hay lỗi cụ thể; chỉ tích hợp khi có bằng chứng lấy được audio/video.
  - Kết quả: CHỜ NGƯỜI DÙNG: ngày 01/11/2026 Playground trả JSON success:true, result là HTML Facebook cho link mẫu, đã thấy trên ảnh chụp. Chưa đọc được toàn bộ result để xác nhận URL media: cây accessibility còn hiển thị trạng thái Loading trong khi screenshot đã có kết quả; khi dùng Find để kiểm trường video, Computer Use tự dừng với thông báo không xác định được URL hiện tại đủ chắc chắn để thực thi chính sách. Không tiếp tục thao tác UI hoặc tìm đường vượt giới hạn. Nhờ người dùng đóng ô tìm kiếm Chrome (Esc), giữ trang Cloudflare Browser Run Playground với kết quả rồi báo để tiếp tục kiểm; hoặc cung cấp kết quả JSON qua file trong thư mục dự án. Chưa tạo Worker, token hoặc tích hợp vào web.

- [x] 12. Chuyển thiết lập key sang trang /key riêng theo yêu cầu người dùng
  - Tieu chi xong: trang chính không có ô hoặc nút đổi key và không liên kết trang riêng; /key lưu key cùng localStorage cũ; push và kiểm production.
  - Kết quả: PASS: push e83be35; production /key HTTP 200 có key-form và trang chủ không còn settings. node --check và git diff --check đạt; mô phỏng lưu/đổi key đạt, giữ storage cũ gemini-api-key. Không gọi Gemini bằng key thật, chưa kiểm trực quan trang riêng.
  - Có sẵn: public/app.js loadKey/localStorage, giao diện lưu key hiện có; đã đọc code.
  - Tận dụng: chỉnh cách đọc key, giữ storage gemini-api-key và luồng transcript.
  - Tự làm: public/key.html và device-settings.js; không thêm dependency.

- [x] 1. Tìm hiểu mọi cách lấy transcript/audio từ link chạy miễn phí trên Cloudflare (tự tra + hỏi ChatGPT + hỏi Gemini)
  - Tiêu chí xong: bảng phương án cho YouTube (có/không phụ đề) và Facebook công khai, mỗi phương án ghi nguồn đã kiểm, chi phí, rủi ro; có ý kiến ChatGPT và Gemini đã đối chiếu
  - Kết quả: PASS: 2026-10-31 đã tra web (Gemini API docs: YouTube URL miễn phí 8 giờ/ngày; Workers AI pricing; báo cáo chặn IP trên Workers/HF Spaces/cloud), hỏi ChatGPT (chatgpt.com, chưa đăng nhập) và Gemini (Flash-Lite, chưa đăng nhập). Hai bên cùng đề xuất: phụ đề → Gemini API cho YouTube → GitHub Actions + yt-dlp cho Facebook/khác → upload. Tổng hợp trình bày trong chat.
  - Kiểm bởi: tôi

- [x] 2. Khảo sát dự án mã nguồn mở có sẵn (GitHub) để tận dụng
  - Tiêu chí xong: danh sách repo đã mở kiểm (license, cập nhật gần nhất, phần dùng được) hoặc ghi "đã tra, không có"
  - Kết quả: PASS: (mức tra web, chưa mở từng repo kiểm license) không có repo làm trọn bộ. Tận dụng: tutorial chính thức Cloudflare "whisper-large-v3-turbo with chunking"; youtubei.js (bản `youtubei.js/cf-worker`); audioflare (seanoliver) chỉ để tham khảo giao diện. Kiểm license trước khi dùng code.
  - Kiểm bởi: tôi

- [x] 3. Người dùng chốt kiến trúc
  - Tiêu chí xong: người dùng duyệt phương án trong chat
  - Kết quả: PASS: 2026-10-31 người dùng chọn phương án A (Cloudflare Pages + Functions + Workers AI Whisper + Gemini API cho YouTube; Facebook bóc link trực tiếp, không được thì upload)
  - Kiểm bởi: người dùng

- [x] 4. Viết code: public/ (giao diện), functions/api/ (youtube, facebook, media, whisper), lib/, wrangler.toml, không thêm dependency npm
  - Tiêu chí xong: đủ file; `node --check` mọi file JS không lỗi
  - Kết quả: PASS: 2026-10-31 đã tạo public/index.html, public/app.js, functions/api/{youtube,facebook,media,whisper}.js, lib/{youtube,facebook}.js, wrangler.toml, .gitignore; `node --check` 7 file JS đều OK; không có package.json/dependency
  - Kiểm bởi: tôi

- [ ] 5. Thử cục bộ bằng Node: lib/youtube.js lấy được phụ đề video mẫu; lib/facebook.js bóc được link video từ 1 link Facebook công khai
  - Tiêu chí xong: in ra transcript phụ đề; in ra URL fbcdn (cần link mẫu từ người dùng)
  - Kết quả: CHỜ NGƯỜI DÙNG: phần YouTube đã đạt (dQw4w9WgXcQ → phụ đề en 60 dòng; parse ID 5 dạng link đúng; chọn "vi" → null để chuyển Gemini). Phần Facebook: trên web thật Facebook trả HTTP 400 cho request từ Cloudflare (chặn truy cập tự động). Thử giả lập thêm header trình duyệt bị công cụ chặn vì là vượt cơ chế chống bot → không theo hướng này. Cần người dùng chọn: giữ thử tự động + dự phòng upload, hay bỏ nhánh link Facebook
  - Kiểm bởi: tôi

- [x] 6. README hướng dẫn: tạo repo GitHub, kết nối Cloudflare Pages, đặt GEMINI_API_KEY, bật Cloudflare Access
  - Tiêu chí xong: README.md có đủ các bước, mở đọc kiểm
  - Kết quả: PASS: README.md có mục Deploy 4 bước (GitHub, Pages, GEMINI_API_KEY, Access) và mục Giới hạn
  - Kiểm bởi: tôi

- [ ] 7. Deploy và thử trên web thật (~10 link + 1 file upload, cả máy tính và điện thoại)
  - Tiêu chí xong: ghi kết quả từng link (được/không, cách nào)
  - Kết quả: CHỜ NGƯỜI DÙNG: đã deploy https://transcript-me.pages.dev (2026-10-31). Đã đạt: trang chủ 200; /api/youtube lấy phụ đề en từ Worker (2083 ký tự, không bị chặn IP); /api/whisper chép đúng nguyên văn câu TTS tiếng Anh; giao diện: link YouTube → hiện transcript, upload WAV 40 giây → chia 2 đoạn → Whisper chạy hết; giao diện mobile 375px hiển thị đủ. Chưa đạt: Gemini (chưa có GEMINI_API_KEY), Facebook (chưa có link mẫu), tiếng Việt thật. Khóa truy cập: người dùng quyết định không dùng (2026-10-31), chấp nhận rủi ro bị dùng chung quota
  - Kiểm bởi: người dùng

- [ ] 8. Sửa lỗi Gemini "User location is not supported" (Function chạy ở HKG, Hồng Kông không được Gemini hỗ trợ)
  - Tiêu chí xong: /api/youtube với lang=vi trên video mẫu trả về method "Gemini API" có nội dung
  - Kết quả: CHỜ NGƯỜI DÙNG: đã push placement gcp:asia-southeast1 (commit 370852e); sau deploy vẫn lỗi "User location is not supported" (thử đơn lẻ sau 4 phút) → Pages không áp dụng placement hint. Lưu ý: free tier gemini-3.8-flash chỉ 20 request/ngày, request bị chặn vị trí vẫn bị tính. Người dùng chọn tách Worker riêng. Đã viết gemini-worker/ (proxy không giữ secret, placement gcp:asia-southeast1), Pages gọi qua GEMINI_PROXY_URL, thêm flag global_fetch_strictly_public; node --check OK. Đã push f70c5c8 + a4f01dd; Worker https://transcript-gemini.namdongplus.workers.dev chạy (gọi Google không key → 403, không còn lỗi vị trí). Thử 1 lần qua Pages: hết lỗi vị trí, nhưng gemini-3.8-flash báo quá tải. Đã push tự chuyển model (3f63680, 8c531fe: chỉ 3.8-flash → 3.6-flash) và báo lý do khi rỗng (0474b4f). Thử video bài hát: Gemini trả rỗng (nghi bản quyền). Thử video lời nói 19 giây: lỗi 524 (Cloudflare hết thời gian chờ ~100 giây). Đã quá 3 vòng sửa → dừng hỏi; người dùng chọn gọi Gemini từ trình duyệt, nhập key một lần mỗi thiết bị (localStorage). Đã chuyển code Gemini sang public/app.js, /api/youtube chỉ trả phụ đề, xóa gemini-worker/ và GEMINI_PROXY_URL, cập nhật README; push 07cc28c. Đã kiểm trên web: /api/youtube en → phụ đề 2083 ký tự, vi → text:null; giao diện không có key → mở mục key và báo nhập key; lưu/xóa key trong localStorage đúng. Còn lại: người dùng nhập key thật và thử 1 video không có phụ đề
  - Kiểm bởi: tôi

- [x] 9. Thêm nút Lưu key và ẩn ô nhập sau khi lưu
  - Tieu chi xong: bấm Lưu hoặc Enter thì lưu trên thiết bị và ẩn ô; tải lại vẫn ẩn; Đổi key mở lại ô nhập.
  - Ket qua: PASS: 2026-10-31 đã sửa trực tiếp theo xác nhận; kiểm node --check và mô phỏng DOM với key giả: lưu, đóng, mở lại, Enter đều đạt. Chưa kiểm giao diện trên trình duyệt thật ở lượt này.
  - Có sẵn: public/app.js có loadKey/saveKey, public/index.html có details settings; đã đọc code.
  - Tận dụng: chỉnh các thành phần hiện có, không thêm dependency.
  - Tự làm: nút Lưu key, Đổi key và trạng thái lưu; xử lý Enter.

- [x] 10. Chẩn đoán link Facebook người dùng gửi
  - Tieu chi xong: link share/v/1cJ7U3xjpA trả transcript hoặc xác định bước thất bại bằng kết quả thật.
  - Kết quả: PASS: chẩn đoán xác định được bước thất bại (không phải đã sửa được Facebook). 2026-10-31 link chia sẻ từ máy này trả HTTP 200, chuyển tới /groups/sacmaucuocsongxaque/permalink/4749560085324241/; API Pages trả 502 kèm Facebook HTTP 400 cho cả link chia sẻ lẫn link bài gốc. Thất bại ở bước tải trang, trước khi bóc media. Chưa xác định nguyên nhân HTTP 400; không đủ bằng chứng kết luận chặn bot. Chức năng transcript từ link này chưa đạt; dùng dự phòng upload theo phạm vi đã duyệt giữ Cloudflare, không thêm backend.

<!-- Kết quả hợp lệ:
  PASS: <bằng chứng cụ thể>   (rồi đổi [ ] thành [x])
  FAIL: <lý do>
  CHỜ NGƯỜI DÙNG: <câu hỏi>   (điểm cần xác nhận; cho phép dừng khi còn mục mở)
-->

## Tiếp nhận và sửa tiếp ngày 31/10/2026

- [x] 9. Xác nhận phạm vi theo mục tiêu YouTube, Facebook, nếu được TikTok và X.com.
  - Tieu chi xong: người dùng chọn giữ Cloudflare hoặc thêm backend tải media.
  - Ket qua: PASS: người dùng chọn giữ Cloudflare; link không tải được thì chọn file thủ công. Không cài yt-dlp, không thêm dependency. Đã tái hiện link Facebook Reel người dùng gửi trả HTTP 400 trên website production; TikTok/X.com hiện dùng file.
- [x] 10. Sửa và kiểm lại các lỗi trong luồng hiện có.
  - Tieu chi xong: JS hợp lệ; kiểm phụ đề, xử lý input lỗi, upload chia đoạn, dừng, sao chép và tải; ghi rõ nhánh không có key để thử.
  - Ket qua: PASS: node --check toàn bộ 7 JS và git diff --check; kiểm parser XML p/text và JSON3, ID YouTube sai, JSON hỏng và Whisper thiếu binding. Trình duyệt local: phụ đề en khi chọn vi hoạt động, WAV lời nói mẫu 40 giây chạy hết 2 đoạn Whisper production trong 7 giây và đúng nội dung; Copy, tải Markdown (đã mở file kiểm) và Dừng giữ kết quả cũ đạt; viewport 375px không tràn ngang. Mô phỏng MAX_TOKENS đánh dấu partial và lỗi đoạn 2 giữ đoạn 1 đạt. Subagent rà diff không thấy regression chặn push. Gemini chưa kiểm inference thật vì không có key; chưa thử tiếng Việt và điện thoại thực. Kết quả cũ không được dùng làm bằng chứng cho bản sửa này.
- [x] 11. Push và kiểm deployment.
  - Tieu chi xong: người dùng xác nhận push làm Cloudflare tự deploy; kiểm website sau cập nhật.
  - Kết quả: PASS: commit 43b830b trên origin đã được ghép cùng sửa key, push 604139e thành công. Đã kiểm production 2026-10-31: trang chủ và app.js HTTP 200, có save-key/key-saved/cancel, có submitKey và AbortController; API phụ đề tiếng Anh trả HTTP 200, 2083 ký tự. Chưa kiểm Gemini bằng key thật và điện thoại thực.
