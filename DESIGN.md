# Transcript UI

## Phạm vi đã xác nhận
- Công cụ cá nhân bằng tiếng Việt, dùng trên điện thoại và máy tính.
- Nền sáng, teal; hình dựng bằng HTML/CSS/SVG, không ảnh hoặc dependency mới.
- Desktop: nguồn trái, kết quả phải. Mobile: nguồn trước, kết quả sau.
- Giữ API và định dạng xuất; sửa trực tiếp. Người dùng đã duyệt commit, push và deploy giao diện ngày 01/11/2026.

## Quy tắc triển khai
- Nút Tạo transcript là điểm nhấn chính; công cụ xuất thuộc vùng kết quả.
- Font hệ thống; input và transcript từ 16px, vùng chạm từ 44px.
- Căn mép nhất quán; khoảng cách trong nhóm nhỏ hơn giữa nhóm.
- Tiến độ từ luồng thật, không giả lập phần trăm hoặc kết quả.
- Màn hẹp một cột, công cụ xuống hàng, nguồn dài ngắt dòng.
- SVG trang trí ẩn khỏi accessibility; điều khiển có nhãn và focus rõ; hỗ trợ reduced motion.
