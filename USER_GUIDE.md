# Sổ Tay Hướng Dẫn Kỹ Thuật: Skill "Content Cinematic" & Tính Năng Import JSON

Tài liệu này hướng dẫn cách kết hợp bộ AI Skill **Content Cinematic** với hệ thống **AI-VIDEO-MAKER** để tạo ra các kịch bản video chuyên sâu, kiểm soát hoàn toàn cảm xúc giọng đọc, hiệu ứng và tự động hoá dàn trang trên giao diện.

---

## 1. Giới thiệu Bộ Skill "Content Cinematic"
Skill này biến AI thành một Đạo diễn Hình ảnh kiêm Copywriter. Khi được gọi, AI không chỉ viết chữ, mà còn tính toán **Metadata** (hiệu ứng, tiếng động, tông giọng) để điều khiển trực tiếp hệ thống render.

**Cách gọi Skill ở khung Chat:**
Anh/chị chỉ cần ra lệnh rõ ràng về nguồn hình mong muốn:
- **Làm video đời thực (Stock):** *"Dùng skill Content cinematic, tạo kịch bản 5 cảnh về chủ đề Lối sống Minimalist. Nguồn hình: Stock Pexels."*
- **Làm video giả tưởng (AI Image/Veo):** *"Dùng skill Content cinematic, làm kịch bản Sci-fi về thành phố tương lai. Nguồn hình: Ảnh AI."*

**Điểm mạnh của Skill:**
- Sinh prompt tiếng Anh chuẩn điện ảnh. Tự động loại bỏ từ khóa ảo (8k, unreal engine...) nếu dùng chế độ Video Stock để tìm kiếm chính xác.
- Bắt buộc chèn SFX (tiếng động như `riser`, `whoosh`) ở các cảnh mở đầu và cao trào.

---

## 2. Giải mã các Thông số Điều khiển (Metadata)
Khi Skill sinh ra chuỗi mã JSON, hệ thống sẽ sử dụng các trường sau để thao túng video:
*   `emotion`: Chọn cảm xúc (`hook`, `calm`, `dramatic`...) để yêu cầu **OmniVoice** đổi giọng đọc tương ứng.
*   `speech_rate_modifier`: Chỉnh tốc độ (`+15%` đọc nhanh dồn dập, `-5%` đọc chậm sâu lắng).
*   `sfx`: Kích hoạt âm thanh hiệu ứng (VD: `impact`, `swoosh_soft`).
*   `transition`: Chọn loại chuyển cảnh (VD: `whip_pan`, `droplet`, `crossfade`).
*   `highlight_text`: Đánh dấu các từ khóa cần nổi bật to trên màn hình (B-Roll Text).

---

## 3. Quy trình Đưa Kịch bản vào Hệ thống (Workflow)

Sau khi AI trả về đoạn mã JSON của kịch bản, anh/chị có 2 cách để tiến hành Render video:

### CÁCH 1: Dùng nút "Import JSON" trên Giao diện (Khuyên dùng)
Tính năng mới nhất cho phép anh/chị kết nối kịch bản của AI trực tiếp lên giao diện Web để duyệt lại bằng mắt:
1. Copy toàn bộ đoạn mã JSON mà AI vừa sinh ra.
2. Mở trình duyệt, truy cập Web App, vào **Bước 2 (Tab Kịch bản - Script Editor)**.
3. Bấm vào nút **[< > Import JSON]** (Màu cam) trên thanh công cụ.
4. Dán đoạn JSON vào và nhấn OK. 
5. Lúc này, toàn bộ Lời thoại, Prompt ảnh, SFX, và Chuyển cảnh của 10-20 phân đoạn sẽ tự động lấp đầy vào các ô tương ứng.
6. Xem lại, tinh chỉnh theo ý thích và nhấn nút **Render Video (Bước 2)**.

### CÁCH 2: Kết xuất trực tiếp qua Server (Dành cho Automation)
Dành cho trường hợp muốn bỏ qua giao diện và chạy ẩn (Headless):
1. Lưu mã JSON của AI ra một file, ví dụ: `kichban.json`
2. Mở cửa sổ Terminal (CMD/PowerShell).
3. Chạy lệnh kích hoạt Tool chuyển đổi do hệ thống cung cấp sẵn:
```bash
python .agents\skills\content-cinematic\scripts\to_payload.py kichban.json --send http://localhost:8000
```
4. Lệnh này sẽ tự động đóng gói Metadata và bắn thẳng tới API Render, server sẽ tự động chạy ngầm và trả ra video thành phẩm.

---
*Lưu ý: Nếu dùng ảnh Sản phẩm (Cover Image) hình vuông/ngang cho video khổ dọc, hệ thống đã được nâng cấp cơ chế **FIT (Letterbox)** để lót viền đen, tuyệt đối không bị cắt xén hình ảnh.*
