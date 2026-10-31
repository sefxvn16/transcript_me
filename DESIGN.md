# Giao diện Transcript

## Phạm vi đã xác nhận

Web cá nhân tiếng Việt, giao diện tối giản theo PLAN.md hiện có. Giữ một cột: nguồn đầu vào, ngôn ngữ lời nói, thiết lập Gemini, thao tác chạy và trạng thái, kết quả transcript và thao tác tải.

## Quy tắc từ hiện trạng

- Dùng phông hệ thống, nội dung rộng tối đa 760 px và lề 16 px.
- Trường link, ngôn ngữ và transcript dùng toàn chiều rộng vùng nội dung.
- Thiết lập API key nằm trên trang /key riêng; trang chính không hiển thị key hoặc liên kết tới trang thiết lập.
- Transcript là vùng chính sau xử lý; các nút sao chép và tải nằm cùng vùng kết quả.

## Trạng thái cần giữ rõ

- Khi đang chạy, khóa thay đổi nguồn và hiển thị nút dừng.
- Gắn nguồn và cách lấy vào kết quả; đánh dấu nội dung chưa hoàn tất.
- Khi lỗi, giữ phần đã chép; nếu chưa có kết quả mới thì ghi rõ kết quả bên dưới thuộc lần trước.
- Màn hẹp giữ bố cục một cột; tên file và URL dài được xuống dòng.
