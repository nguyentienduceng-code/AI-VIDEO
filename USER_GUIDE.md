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

## 4. Chuyển Kho Lưu Trữ Sang Ổ Đĩa Khác

Mặc định mọi ảnh, video và bộ nhớ đệm đổ vào `backend/assets` trên ổ C — riêng phần này đã chiếm hơn 1GB và tăng liên tục.

**Cách chuyển sang ổ D:**
1. Vào **Bước 1 (Cấu hình)**, kéo xuống khối **🖴 Thư mục lưu trữ** ở cột trái.
2. Nhập đường dẫn tuyệt đối, ví dụ `D:\AIVideoAssets`, rồi bấm **Lưu**.
3. **TẮT và BẬT LẠI cửa sổ CMD Backend** — biến môi trường chỉ đọc lúc khởi động, không tắt đi bật lại thì mọi thứ vẫn đổ về ổ C.

**Những điều cần biết:**
- Nhạc nền và tiếng động **ở lại cùng mã nguồn**, không cần chép đi đâu. Preset và danh sách dự án tự chuyển sang trong lần khởi động kế tiếp.
- Ảnh/video/cache **cũ không được chép sang** (hơn 1GB, và đều tự sinh lại được). Vài video đầu tiên sau khi chuyển sẽ render chậm hơn vì cache bắt đầu lại từ đầu. Muốn giữ, tự chép tay `backend/assets/cache` sang thư mục mới trước khi khởi động lại.
- Tránh đường dẫn có dấu nháy đơn, dấu phẩy hoặc dấu chấm phẩy — chúng phá vỡ lệnh FFmpeg. Hệ thống sẽ chặn và báo lỗi ngay.
- Nếu ổ D là ổ rời chưa cắm lúc khởi động, backend tự quay về thư mục mặc định và ghi rõ lý do trên giao diện.

---

## 5. Công Cụ Chỉnh Sửa Hậu Kỳ (Sửa Từng Cảnh)

Sau khi render xong, bấm **[Chỉnh sửa & Render lại]** để quay về trình sửa kịch bản. Ở đó mỗi cảnh có:

- **Đèn báo 🟢 / 🔴** cạnh số cảnh: 🟢 *Giọng*/*Hình* nghĩa là đã có sẵn trong bộ nhớ đệm, render lại dùng ngay không tốn giây nào. Vừa sửa lời thoại là đèn chuyển 🔴 — cảnh đó sẽ phải gọi AI tạo lại. Thanh công cụ trên cùng tổng kết *bao nhiêu cảnh tái dùng / bao nhiêu cảnh tạo mới* trước khi bấm Render.
- **[⏸ Chèn nhịp nghỉ]**: chèn thẻ `<break time="1s"/>` tại vị trí con trỏ, ép giọng đọc dừng hẳn 1 giây để ngưng đọng cảm xúc. Sửa số giây trực tiếp trong thẻ (`time="2.5s"`), tối đa 5 giây. *Không dùng được khi bật "Đọc liền mạch cả bài"* — chế độ đó gọi TTS một lần cho toàn bài nên không có chỗ chèn khoảng lặng riêng.
- **[⬆ Tải ảnh/video của tôi]**: khi AI vẽ hỏng ngón tay/khuôn mặt, tự tải ảnh chụp hoặc clip quay sẵn lên thay riêng cho cảnh đó. Chấp nhận PNG/JPG/WEBP/MP4/MOV, tối đa 200MB. Cảnh đã ghi đè sẽ bỏ qua hoàn toàn phần mô tả hình ảnh.
- **[🎧 Nghe thử]**: đọc thử riêng cảnh đó, nghe được cả nhịp nghỉ vừa chèn, không phải render cả video 20 phút mới biết. **Mẹo quan trọng:** bản nghe thử được lưu lại luôn — nghe thử xong đèn chuyển 🟢 và lúc render cảnh đó không phải sinh lại. Nghe thử càng nhiều, render càng nhanh.
- **Nhạc nền cảnh này**: tick vào để chỉnh riêng âm lượng nhạc nền cho một cảnh — ví dụ cảnh nói thầm hạ xuống 5%, cảnh kết đẩy lên 50%. Không tick thì theo mức chung của cả video.

### Dọn bộ nhớ đệm

Trong khối **🖴 Thư mục lưu trữ** có dòng *"Bộ nhớ đệm: X MB"* kèm nút **[Dọn]**. Chỉ bấm khi thật sự cần chỗ trống — đây chính là thứ khiến render lại gần như tức thì. Xoá xong không mất dữ liệu nào, chỉ là mọi cảnh chuyển 🔴 và phải gọi AI tạo lại (chậm hơn, tốn quota API). Kịch bản Gemini đã sinh được **giữ lại** vì sinh lại tốn quota mà chỉ chiếm vài trăm KB.

---
*Lưu ý: Nếu dùng ảnh Sản phẩm (Cover Image) hình vuông/ngang cho video khổ dọc, hệ thống đã được nâng cấp cơ chế **FIT (Letterbox)** để lót viền đen, tuyệt đối không bị cắt xén hình ảnh.*
