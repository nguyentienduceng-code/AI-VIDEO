# Hook Library — Công thức Hook, Tone & CTA

## Công thức Hook (3 giây đầu) — chọn theo tone

**Viral / Short (giật gân, FOMO):**
- Phủ định gây sốc: "Đừng [làm X]... nếu bạn chưa biết điều này."
- Sự thật ẩn giấu: "Sự thật rùng mình về [chủ đề] mà không ai nói cho bạn."
- Con số sốc: "99% người [làm X] đều sai ở bước này."
- Câu hỏi khoét insight: "Bạn có bao giờ tự hỏi vì sao [nghịch lý]?"

**Storytelling (kể chuyện sách/phim — trầm, tò mò):**
- Giới thiệu bí ẩn: "Câu chuyện bắt đầu với [tình huống lạ], nhưng không ai ngờ..."
- Nghịch lý nhân vật: "Cùng một [người/vật], nhưng lại có hai [số phận] trái ngược."
- Lời hứa hé lộ: "Cuốn sách này giấu một bí mật về [chủ đề] — và nó sẽ thay đổi cách bạn nghĩ."

**Educational (khai mở):**
- "Hoá ra [điều tưởng đúng] lại hoàn toàn sai. Đây là lý do."

## Hook Quote (cho hiệu ứng `carousel_quote` — bìa sách + câu chốt)

App có hook `carousel_quote`: 1s slot-machine → bìa sách (ảnh cảnh 1) thu vào giữa + hiện `hook_quote` 2.5s.
Đây là **câu trị giá cả cuốn sách/nội dung** — phải "đắt" đến mức người xem muốn nghe hết.

**Quy tắc viết `hook_quote`:**
- Viết HOA, cực ngắn (< 15 từ), 1-2 vế đối lập → dễ nhớ, dễ trích.
- Chứa một **nghịch lý / sự thật lật ngược** hoặc **công thức sống**.
- KHÔNG chung chung ("sách rất hay", "bài học sâu sắc"). Phải là mệnh đề cụ thể.

**Ví dụ đạt:**
- 💰 *"NGƯỜI NGHÈO LÀM VIỆC VÌ TIỀN. NGƯỜI GIÀU BẮT TIỀN LÀM VIỆC CHO MÌNH."*
- 📖 *"ĐÁM MÂY KHÔNG BAO GIỜ CHẾT. NÓ CHỈ BIẾN THÀNH CƠN MƯA."*
- 🧠 *"BẠN KHÔNG SỢ THẤT BẠI. BẠN SỢ NGƯỜI KHÁC THẤY BẠN THẤT BẠI."*
- ⏳ *"THỜI GIAN KHÔNG CHỮA LÀNH. NÓ CHỈ DẠY TA QUEN VỚI VẾT THƯƠNG."*

**Đi kèm:** `image_prompt` cảnh 1 phải là ẢNH BÌA/biểu tượng rõ nét (VD `close-up of a book cover on wooden desk, warm light`) vì carousel dùng nó làm cover.

## Soft Cliffhanger (kết mỗi cảnh storytelling — GIỮ CHÂN)

Mỗi cảnh giữa kết bằng câu bỏ lửng tạo tò mò:
- "Nhưng điều [nhân vật] không ngờ tới là..."
- "Câu trả lời anh nhận được nghe thật vô lý..."
- "Và đó mới chỉ là khởi đầu..."
- "Nhưng sự thật còn đáng sợ hơn thế..."

## Tone Library (giọng văn)

| Tone | Đặc điểm | Nhịp (speech_rate) | BGM gợi ý |
|---|---|---|---|
| viral | Đanh thép, dồn dập, giật gân | +10% ~ +15% | hype_drill, no_sleep_hiphop |
| storytelling | Trầm lắng, chiêm nghiệm, cliffhanger | -5% ~ 0% | deep_abstract_ambient, moment_of_peace |
| educational | Rõ ràng, logic, số liệu | 0% | lofi_jazzy_love, type_beat |
| emotional | Sâu sắc, chạm tim | -5% | moment_of_peace, new_age_nature |
| humorous | Cà khịa, Gen Z, bất ngờ | +5% | comedy_cartoon, afro_pop |

## CTA — dùng CTA THẬT (cấm fake scarcity)

**✅ Nên dùng:**
- "Lưu lại để không quên nhé."
- "Bạn nghĩ sao về điều này? Comment cho mình biết."
- "Theo dõi để xem phần 2 — còn bất ngờ hơn."
- "Tag người bạn muốn cùng xem."
- "Đọc cuốn này nếu bạn đang tìm câu trả lời cho [vấn đề]."

**❌ TRÁNH (giả tạo, dễ vi phạm policy, mất uy tín):**
- "Lưu ngay trước khi video bị gỡ!"
- "Xem nhanh kẻo mất!"
- "99% sẽ bỏ lỡ điều này" (nếu không có cơ sở).

## Quy tắc văn nói cho TTS

- Câu ngắn, mỗi câu 1 ý. Ngắt bằng dấu phẩy/chấm rõ ràng.
- Chèn `...` ở chỗ cần lặng/nhấn cảm xúc (app hiểu và ngắt nghỉ).
- Không markdown (`*`, `#`), không emoji trong `text` (TTS sẽ đọc sai/ký tự lạ).
- Xưng "bạn" trực tiếp để tăng kết nối.
