# AI-VIDEO-MAKER Content Router Rule

Quy tắc điều phối nội dung bắt buộc dành cho AI Agent khi nhận được yêu cầu viết kịch bản video/tạo content:

## 1. BẮT BUỘC Phân tích trước khi Hành động (Analysis First)
Mỗi khi User gửi một đoạn tóm tắt sách, bài viết, hoặc ý tưởng thô và yêu cầu "tạo kịch bản", Agent **KHÔNG ĐƯỢC** viết kịch bản ngay lập tức.
Thay vào đó, Agent phải thực hiện bước phân tích (The Router Analysis) bằng cách in ra log chat:
- **Tone/Mood:** (Đánh giá sắc thái nội dung: Chữa lành, Kịch tính, hay Năng động?)
- **Audience:** (Đối tượng người xem là ai?)
- **Skill được chọn:** (Quyết định gọi 1 trong 3 Skill chuyên biệt).

## 2. Lựa chọn Skill Chuyên biệt
Dựa trên phân tích, Agent phải tự động kích hoạt ĐÚNG 1 trong 3 Skill (nằm trong thư mục `.agents/skills/`):
- Gọi **`content-cinematic`** NẾU: Nội dung thiên về chữa lành, triết lý, sách tâm linh, kể chuyện chậm rãi (VD: Không diệt không sinh, Nhà giả kim).
- Gọi **`content-viral-listicle`** NẾU: Nội dung thiên về thực chiến, bài học kinh doanh, top list, phát triển bản thân (VD: Cha giàu cha nghèo, Review sản phẩm).
- Gọi **`content-debunker`** NẾU: Nội dung có yếu tố bóc phốt, thuyết âm mưu, tranh luận, lịch sử bí ẩn, hoặc đi ngược số đông.

## 3. Thực thi
Sau khi tuyên bố Skill được chọn, Agent tiến hành áp dụng toàn bộ Rule của Skill đó để sinh ra File JSON hoàn chỉnh chuẩn định dạng của ứng dụng AI-VIDEO-MAKER.
Tuyệt đối tuân thủ chỉ thị âm thanh, hình ảnh và nhịp điệu của riêng Skill đó.
