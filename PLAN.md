# PLAN: Website transcript video/audio (cá nhân)

Cập nhật: 2026-10-31 · Phiên: 1
Mục tiêu: Web cá nhân dán link (YouTube, Facebook công khai, ...) hoặc upload video/audio → transcript tiếng Anh/Việt hiện ngay, tải .txt/.md; không lưu gì trên web.
Phạm vi: Miễn phí hoàn toàn; chỉ cập nhật GitHub, Cloudflare Pages tự deploy; giao diện tối giản; mức dự án: đơn giản (kiểm tay, không test tự động). Dự phòng đã chấp nhận: link không xử lý được → người dùng tải về rồi upload.

## Các mục

- [ ] 12. Chuyển thiết lập key sang trang /key riêng theo yêu cầu người dùng
  - Tieu chi xong: trang chính không có ô hoặc nút đổi key và không liên kết trang riêng; /key lưu key cùng localStorage cũ; push và kiểm production.
  - Kết quả: đang triển khai; sửa trực tiếp đã được duyệt trong phiên; push hoàn thiện theo ủy quyền trước.
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
