# HỆ THỐNG SOẠN CONTENT - AI VIDEO MAKER

Hệ thống soạn thảo kịch bản (Content Generation System) của dự án AI Video Maker được xây dựng trên một bộ lõi Prompt Engineering thiết kế cực kỳ tinh vi. Lõi hệ thống này không chỉ tạo ra kịch bản chữ mà còn tự động hoá toàn bộ vai trò của Đạo diễn Hình ảnh (Director of Photography), Đạo diễn Âm thanh (Audio Director) và Biên tập viên (Script Editor).

Dưới đây là tài liệu chi tiết về hệ thống soạn Content đang vận hành trong dự án:

## 1. Kiến trúc Cấu trúc Kể chuyện (Curiosity Gap & PAS)
Hệ thống ép buộc AI (Gemini) phải tuân thủ chuẩn cấu trúc nội dung Triệu View trên các nền tảng video ngắn (TikTok, Reels, Shorts):

*   **HOOK (Cảnh 1 - Móc câu sắc bén):** Bắt buộc tạo ra một "Curiosity Gap" (Lỗ hổng tò mò). Hệ thống có quy định rõ: *"Nếu xem xong cảnh 1 mà khán giả không bị sốc, bạn thất bại"*. Không được dùng các câu mở đầu sáo rỗng như *"Xin chào các bạn"*, *"Hôm nay mình sẽ chia sẻ"*.
*   **TENSION (Các cảnh giữa - Nút thắt):** Xoáy sâu vào vấn đề bằng các chi tiết gây sốc. Không kể lể dài dòng, nói đạo lý suông. Mọi luận điểm phải có con số hoặc hình ảnh so sánh thực tế.
*   **CLIMAX (Cảnh áp chót - Cao trào):** Đưa ra sự thật bất ngờ nhất (Plot twist) hoặc giải pháp tột đỉnh.
*   **CTA (Cảnh cuối - Kêu gọi hành động):** Lời kêu gọi hành động (Follow, Share, Like) được chèn tự nhiên vào kịch bản.

## 2. Hệ thống Quản trị Ngân sách Từ (Word Budgeting)
Thay vì sử dụng các luật cứng ngắc (ví dụ: mỗi cảnh 15-20 từ) khiến AI dễ bị "ảo giác", hệ thống tính toán ngân sách từ một cách linh hoạt bằng thuật toán:
*   Tổng số lượng từ được phân bổ dựa trên **Thời lượng mục tiêu** (Target Duration) và **Số lượng phân cảnh**.
*   Sử dụng tốc độ giọng đọc AI thực tế (`wps` - word per second) để đưa ra ràng buộc chặt chẽ vào Prompt: *"Mỗi phân cảnh tuyệt đối KHÔNG ĐƯỢC VƯỢT QUÁ [X] từ, tương đương [Y] giây đọc"*.
*   Nếu câu văn dài, hệ thống ép AI bắt buộc phải tách đôi thành 2-3 cảnh liên tiếp để giữ nhịp độ video dồn dập.

## 3. Hệ thống Đạo diễn Hình ảnh (Cinematic Camera System)
Kịch bản sinh ra không chỉ là chữ, mà bao gồm cả `image_prompt` chuyên sâu (bằng tiếng Anh) để chuyển thẳng tới hệ thống sinh ảnh (Veo/Midjourney/Stable Diffusion):

*   **Góc máy Điện ảnh:** Bắt buộc mở đầu mỗi `image_prompt` bằng các góc quay chuyên nghiệp như: `Extreme close-up shot`, `Low-angle drone shot`, `Over-the-shoulder shot`, `Wide establishing shot`.
*   **Đồng nhất Nhân vật (Character Consistency):** Hệ thống có cơ chế chèn tự động đoạn miêu tả ngoại hình (tuổi, giới tính, trang phục) vào tất cả các cảnh để AI vẽ ảnh không bị "đổi diễn viên" giữa chừng.
*   **Đồng bộ Tông màu:** Ép AI dùng chung 1 tông màu ánh sáng cho toàn video (VD: *cinematic teal and orange lighting, volumetric dust*).

## 4. Hệ thống Điều khiển Cảm xúc & Nhịp độ (Dynamic Pacing & Emotion)
Hệ thống không sinh ra một giọng đọc đều đều, phẳng lì, mà phân rã theo từng cảnh:
*   **Nhịp độ giọng đọc (`speech_rate_modifier`):** Dồn dập nhanh ở Hook (`+15%`), chậm rãi ở phần Giải thích (`-5%`), và bình thường ở Climax (`0%`).
*   **Đồng bộ Hiệu ứng âm thanh (SFX):** Cấm lạm dụng SFX liên tục. Chỉ dùng SFX ở Cảnh 1 (Hook) và 1-2 cảnh có Plot Twist.
*   **Hiệu ứng Chuyển cảnh (Transitions):** 
    *   Chuyển chủ đề / Bất ngờ → `fade_black`
    *   Kể liên tục / Tiếp nối → `crossfade`
    *   Cao trào / Phóng to chi tiết → `zoom_through`

## 5. Lớp Kiểm duyệt Chất lượng Đa tầng (AI Script Reviewer)
Sau khi sinh ra kịch bản, hệ thống sẽ KHÔNG tin tưởng AI 100% mà đưa qua hệ thống **2 tầng QC (Quality Control)**:

1.  **Tầng 1 (Heuristic Local Review):** Kiểm tra nội bộ siêu tốc để bắt lỗi:
    *   Chứa cụm từ sáo rỗng (*"Cùng tìm hiểu nhé"*, *"Các bạn ơi"*).
    *   Cảnh quá dài (vượt Word Budget).
    *   Thiếu câu CTA ở cảnh cuối.
    *   Hook mở đầu quá yếu.
    *   *(Nếu không đạt điểm tối thiểu 60/100, kịch bản sẽ bị trừ điểm hoặc ép sinh lại)*.
2.  **Tầng 2 (Gemini Narrative Review):** Gọi thêm 1 lần AI (temperature = 0.3) đóng vai Biên tập viên cấp cao để thẩm định:
    *   Sức hút của Hook trong 3 giây đầu.
    *   Cao trào (Climax) có đủ "đô" hay không.
    *   Mạch cảm xúc có bị đứt gãy không.

*(Tài liệu được trích xuất tự động từ hệ thống Backend Prompt của AI Video Maker)*
