# 🚀 SOP v3.2 — Quy Trình Turbo: Ebook → Video bằng NotebookLM + AI-VIDEO-MAKER

**Thời gian thực tế:** 15-20 phút cho sách 400-500 trang
**Phiên bản:** v3.2 — Đã đối chiếu từng thiết lập với code thật của app (26/07/2026)

> **Đổi gì so với v3.1** — xem [Phụ lục C](#phụ-lục-c--nhật-ký-thay-đổi) ở cuối.
> Bốn thay đổi quan trọng nhất: (1) bắt buộc bật `carousel_quote` nếu không toàn bộ
> phần Máy Xèng + Quote bìa **không chạy**; (2) hook dài **4.5s** chứ không phải 3.5s;
> (3) Cảnh 1 phải là cảnh ngắn nhất vì hình của nó bị ghim cứng là ảnh bìa;
> (4) thêm **Nhánh JSON** ở Bước 6 — bỏ hẳn khâu chia cảnh bằng AI.

---

## CHUẨN BỊ TRƯỚC KHI BẮT ĐẦU

### Nguyên liệu cần có:
1. **File ebook** (.PDF có text thật, .TXT, hoặc .MD) — KHÔNG phải PDF scan ảnh
2. **Ảnh bìa sách** (JPEG/PNG/WebP, tối thiểu 600×800px) — chụp bìa thật hoặc tải từ Fahasa/Tiki
3. Tài khoản Google để dùng NotebookLM

> ⚠️ Dùng bản sách có bản quyền hợp pháp nếu video sẽ bật kiếm tiền trên TikTok/YouTube.

---

## BƯỚC 1 — Nạp sách vào NotebookLM (2 phút)

1. Mở [notebooklm.google.com](https://notebooklm.google.com) → Tạo Notebook mới
2. Bấm **"+ Thêm nguồn"** → Upload nguyên file PDF (KHÔNG cần cắt chương)
3. Upload thêm 1-2 nguồn phụ nếu có (bài review sách, bài phỏng vấn tác giả)
4. Đợi thanh tiến trình biến mất

---

## BƯỚC 2 — Khai thác Studio tự động (10 phút)

Ở cột **Studio bên phải màn hình**, bấm lần lượt 4 nút. Sau mỗi nút đợi kết quả → bấm **"Lưu thành Ghi chú"**.

### Nút 1: Báo cáo → Tài liệu tóm tắt
- Bấm **"Báo cáo"** → Chọn định dạng **"Tài liệu tóm tắt"**
- Ngôn ngữ: **Tiếng Việt**
- Bấm **Tạo** → đợi xong → **"Lưu thành Ghi chú"**

### Nút 2: Bảng dữ liệu
- Bấm **"Bảng dữ liệu"**
- Vào ô **"Mô tả bảng dữ liệu bạn muốn tạo"**, dán đoạn sau:

```
Tạo bảng với 4 cột: Loại dữ liệu | Nội dung cụ thể | Ngữ cảnh/Ý nghĩa | Vị trí trong sách.
Liệt kê TẤT CẢ các mục sau:
- Mọi con số, tỉ lệ, phần trăm xuất hiện trong sách
- Mọi mốc thời gian, năm tháng, khoảng thời gian
- Mọi tên riêng (người, công ty, địa danh) kèm vai trò của họ
- Mọi kết quả thí nghiệm, khảo sát có số liệu cụ thể
- Mọi câu trích dẫn nguyên văn đáng nhớ (trong ngoặc kép)
```

- Bấm **Tạo** → đợi xong → **"Lưu thành Ghi chú"**

### Nút 3: Bản đồ tư duy
- Bấm **"Bản đồ tư duy"**
- Vào ô **"Chủ đề nên là gì?"**, dán đoạn sau:

```
Tạo bản đồ tư duy với chủ đề trung tâm là luận điểm cốt lõi của cuốn sách.
Từ đó phân nhánh ra:
- Nhánh 1: Các chương/phần chính và luận điểm của từng chương
- Nhánh 2: Các nguyên tắc/quy luật tác giả đặt tên riêng
- Nhánh 3: Các nhân vật/câu chuyện thực tế minh họa
- Nhánh 4: Những điều phản trực giác (người ta tưởng X → sách chỉ ra Y)
- Nhánh 5: Hành động/bài học áp dụng thực tế
```

- Bấm **Tạo** → đợi xong → **"Lưu thành Ghi chú"**

### Nút 4: Tổng quan bằng âm thanh
- Bấm nút **"Tổng quan bản..."** có biểu tượng **Sóng âm lấp lánh** (nút đầu tiên hàng trên)
- Bấm **"Tùy chỉnh"**
- Định dạng: chọn **"Tìm hiểu sâu"** ✅
- Độ dài: **Mặc định** ✅
- Vào ô **"Máy chủ AI nên tập trung vào điều gì?"**, dán đoạn sau:

```
Tập trung vào: các câu chuyện thật và thí nghiệm có tên nhân vật cụ thể,
các con số và số liệu thực tế trong sách, những điều phản trực giác mà
người đọc thường hiểu sai, các trích dẫn nguyên văn đắt giá nhất.
TUYỆT ĐỐI không nói chung chung hay đạo lý suông.
```

- Bấm thêm 3 tag: **+ Nội dung chính**, **+ Góc nhìn chuyên gia**, **+ Bài học thực tế**
- Bấm **Tạo** → đợi audio chạy xong → Bấm **"Xem bản chép"** → **"Lưu thành Ghi chú"**

---

## BƯỚC 3 — Prompt bổ sung trong Chat (3 phút)

Đảm bảo **tick chọn toàn bộ nguồn** (file PDF gốc). Dán đoạn sau vào khung chat:

```
Chỉ dùng nguồn đang được chọn. TUYỆT ĐỐI không suy diễn ngoài nguồn.
Nếu không có thông tin cho mục nào, ghi "KHÔNG CÓ TRONG NGUỒN".

Liệt kê cho tôi:
1. TRÍCH DẪN NGUYÊN VĂN — 10 câu đáng nhớ nhất, copy Y NGUYÊN trong ngoặc kép,
   ghi vị trí. Ưu tiên câu nghịch lý, thức tỉnh, câu tác giả tự đóng khung như nguyên tắc.
2. SỐ LIỆU & MỐC THỜI GIAN — TẤT CẢ con số, tỉ lệ, năm tháng.
   Mỗi dòng: con số + đơn vị + ngữ cảnh.
3. 5 CÂU CHUYỆN / THÍ NGHIỆM CỤ THỂ — Mỗi mục 60-100 từ, kể theo:
   ai → tình huống → điều bất ngờ → hệ quả. Giữ ĐÚNG tên riêng.
4. 5 NGHỊCH LÝ / ĐIỀU PHẢN TRỰC GIÁC — "Người ta tưởng X → sách chỉ ra Y".
5. 10 CHI TIẾT GIÁC QUAN — Hình ảnh, vật thể, ánh sáng, âm thanh cụ thể
   trong sách (VD: "lá thư viết dưới ánh nến"). Đây là nguyên liệu đặt hình ảnh video.
```

→ AI trả lời xong → Bấm **"Lưu vào ghi chú"**

**Tổng cộng sau Bước 2+3: 5 Ghi chú**

---

## BƯỚC 4 — Chưng cất thành Nguồn tinh chế (1 phút)

1. Nhìn vào danh sách Ghi chú bên phải
2. **Chọn tất cả 5 Ghi chú**
3. Bấm **"Thêm vào nguồn"** hoặc **"Chuyển thành nguồn"**
4. **Bỏ tick file PDF gốc** → CHỈ TICK Nguồn tinh chế mới

---

## BƯỚC 5 — Tạo Hook + Quote bìa (Prompt B) (2 phút)

Dán vào khung chat:

```
Chỉ dùng nguồn. Sinh cho tôi:

(A) 10 phương án câu HOOK mở màn video, mỗi câu dưới 14 từ, đánh số.
Mỗi câu ghi rõ dạng ở cuối: [NGHỊCH LÝ] / [CON SỐ SỐC] / [CÂU HỎI KHOÉT ĐAU]
/ [TUYÊN BỐ PHẢN TRỰC GIÁC].
CẤM: "Bạn có biết", "Hôm nay chúng ta", "Cùng tìm hiểu".

(B) 1 câu QUOTE BÌA: TỐI ĐA 10 TỪ (đếm kỹ — đây là giới hạn kỹ thuật của app,
vượt quá sẽ tràn 4-5 dòng và che mất ảnh bìa). Lấy nguyên văn từ sách
(được phép cắt ngắn nhưng không đổi từ), mang tính nghịch lý hoặc thức tỉnh.
Chỉ chữ và dấu câu — không emoji, không ngoặc kép.

(C) Nỗi đau cốt lõi mà cuốn sách giải quyết, 1 câu, bằng ngôn ngữ người đọc
tự nói với bản thân lúc 2 giờ sáng.
```

→ Đọc qua 10 Hook, **chọn 1 câu ưng nhất**. Ghi nhớ **câu (B) để dán vào ô Quote Bìa trong App**.

> ⚠️ **Vì sao tối đa 10 từ:** app render quote ở font 60px, khung rộng 88% màn hình,
> đặt tại 74% chiều cao và **không có cơ chế cắt bớt**. Quote dài sẽ xuống 4-5 dòng
> rồi trèo lên che chính tấm bìa vừa quay ra.

---

## BƯỚC 6 — Viết kịch bản (3 phút)

### 6.0 — Tra bảng quy đổi thời lượng (ĐÃ SỬA KHỚP APP)

| Thời lượng | Tổng từ | Số cảnh | Từ/cảnh | Độ dài video thật |
|---|---|---|---|---|
| 30s | 70-80 | **6** | 11-14 | ~32s |
| 60s | 140-160 | **12** | 11-14 | ~62s |
| 90s | 210-240 | **19** | 11-13 | ~92s |
| 120s | 280-320 | **25** | 11-13 | ~122s |
| 180s | 420-480 | **30** | 14-16 | ~182s |
| 240s | 560-640 | **30** | 19-21 | ~242s |
| 300s | 700-800 | **30** | 23-27 | ~302s |

> **Số cảnh phải khớp CHÍNH XÁC bảng này** — đây là con số app tự điền khi bạn bấm
> nút thời lượng. Lệch một cảnh là app sẽ ép gộp/tách lại kịch bản của bạn.
>
> **Vì sao video dài hơn ~2.4s:** khi bật Máy Xèng, app dời toàn bộ giọng đọc lùi
> 2.35 giây để tiếng trục quay không đè lên lời dẫn.
>
> **Sách 400-500 trang nên chọn 240s.** Trần cứng của app là 30 cảnh; ở mốc 300s
> mỗi cảnh phải gánh 23-27 từ (~10 giây/cảnh) nên video bắt đầu ì như slideshow.
> 240s là điểm ngọt: vẫn 30 cảnh nhưng nhịp đổi cảnh còn ~8 giây.

### 6.1 — Chọn VAI phù hợp ngách

| Ngách | VAI | Niche trong App |
|---|---|---|
| Review sách, kể chuyện | người kể chuyện sách bậc thầy, giọng trầm lắng, điện ảnh, không lên gân | `book` |
| Tâm lý, chữa lành | nhà tâm lý trị liệu nói chuyện riêng với một người đang tổn thương | `psychology` |
| Tài chính, kinh doanh | chuyên gia tài chính lão làng, nói thẳng vào cơ chế kiếm tiền và mất tiền | `finance` |
| Lịch sử, bí ẩn | nhà sử học kiêm thám tử, khách quan nhưng gây ám ảnh | `history` |

### 6.2 — Chọn 1 trong 2 nhánh

| | **Nhánh A — Văn bản** (cổ điển) | **Nhánh B — JSON** (khuyến nghị) |
|---|---|---|
| Cách làm | Dán kịch bản dạng chữ vào app, Gemini chia cảnh | Dán thẳng JSON qua nút **Nhập JSON** |
| Rủi ro AI sửa lời thoại | Còn (thấp) | **Không** |
| Tốn quota Gemini | 1 lượt | **0 lượt** |
| Điều khiển sfx/transition từng cảnh | Phải sửa tay trong Script Editor | **Có sẵn trong JSON** |
| Quote/BGM/CTA tự điền | Không | **Có** |
| Nhược điểm | — | NotebookLM đôi khi trả JSON lỗi cú pháp, phải bảo nó sửa lại |

---

### 6.A — NHÁNH A: Prompt C (văn bản)

Thay `{VAI}`, `{SỐ_CẢNH}`, `{TỔNG_TỪ}`, `{TỪ_MỖI_CẢNH}` rồi dán vào chat:

```
Bạn là {VAI}. Chỉ dùng thông tin trong nguồn đang được chọn.

Viết một kịch bản video dạng kể chuyện, chia thành ĐÚNG {SỐ_CẢNH} cảnh,
tổng lời thoại khoảng {TỔNG_TỪ} từ.

ĐỊNH DẠNG BẮT BUỘC — lặp ĐÚNG khối này cho từng cảnh, không thêm bớt nhãn:

CẢNH 1
Voice-over: <lời đọc tiếng Việt có dấu đầy đủ>
Hình ảnh: <mô tả bằng TIẾNG ANH>
Text on-screen: <1-3 từ khoá giật tít, hoặc để trống>

LUẬT LỜI THOẠI (Voice-over):
- Mỗi cảnh {TỪ_MỖI_CẢNH} từ, tuyệt đối không vượt quá.
- NGOẠI LỆ CẢNH 1: chỉ 8-10 từ, NGẮN NHẤT toàn bài (lý do ở luật hình ảnh bên dưới).
- Văn nói tự nhiên. TUYỆT ĐỐI không Markdown, không emoji, không ngoặc vuông.
- Mỗi cảnh kết bằng câu tạo tò mò nhẹ để người xem muốn nghe tiếp.
- BẮT BUỘC nhúng nguyên liệu thật: ≥2 trích dẫn nguyên văn, ≥2 con số/mốc
  thời gian, ≥1 câu chuyện có tên nhân vật.
- CẤM: "Xin chào các bạn", "Hôm nay mình sẽ chia sẻ", "Hôm nay chúng ta",
  "Cùng tìm hiểu nhé", "Bạn có biết", "chúng ta cần cố gắng", "hãy kiên trì".
  Cấm đạo lý suông.
- Cảnh 1 = hook sắc nhất (dùng câu Hook đã chọn ở Bước 5).
- Cảnh cuối = kết bài trọn vẹn + lời mời tự nhiên. Không được cụt.

LUẬT HÌNH ẢNH:
- Viết bằng TIẾNG ANH, bắt đầu bằng góc máy điện ảnh rồi " of " rồi chủ thể.
  VD: "Extreme close-up shot of a hand writing a letter by candlelight"
- Phải là cảnh QUAY THẬT, đời thường, tìm được trên kho video stock (Pexels).
  TUYỆT ĐỐI TRÁNH anime, CGI, phép thuật, nhân vật hoạt hình.
- Chọn hình theo CẢM XÚC, không minh hoạ từng chữ.
- CẢNH 1: cứ viết mô tả hình ảnh bình thường (KHÔNG mô tả bìa sách), nhưng biết
  trước rằng app sẽ ghim ảnh bìa lên Cảnh 1 và bỏ qua mô tả này. Đó chính là lý do
  lời thoại Cảnh 1 phải cực ngắn: người xem đã nhìn tấm bìa suốt 4.5 giây hook rồi.

Text on-screen: 1-3 từ HOA, đập vào mắt. Chỉ dùng ở 3-5 cảnh mạnh nhất,
các cảnh còn lại để trống.

Cuối kịch bản thêm 2 dòng riêng:
BGM: <chọn 1: moment_of_peace | deep_abstract_ambient | new_age_nature |
running_night | lofi_jazzy_love | type_beat | hype_drill>
CTA: <câu kêu gọi hành động dưới 12 từ>
```

---

### 6.B — NHÁNH B: Prompt C-JSON (khuyến nghị)

Thay `{VAI}`, `{SỐ_CẢNH}`, `{TỔNG_TỪ}`, `{TỪ_MỖI_CẢNH}`, `{QUOTE_BÌA}` rồi dán vào chat:

```
Bạn là {VAI}. Chỉ dùng thông tin trong nguồn đang được chọn.

Viết kịch bản video kể chuyện gồm ĐÚNG {SỐ_CẢNH} cảnh, tổng lời thoại
khoảng {TỔNG_TỪ} từ, rồi TRẢ VỀ DUY NHẤT MỘT KHỐI JSON hợp lệ.
Không viết bất kỳ chữ nào ngoài khối JSON. Không bọc trong dấu nháy ngược.

Cấu trúc chính xác:

{
  "hook_quote": "{QUOTE_BÌA}",
  "recommended_bgm": "<1 mã BGM>",
  "cta_text": "<câu CTA dưới 12 từ>",
  "scenes": [
    {
      "scene": 1,
      "text": "<lời đọc tiếng Việt có dấu>",
      "image_prompt": "<mô tả hình bằng tiếng Anh>",
      "sfx": "<1 mã sfx hoặc chuỗi rỗng>",
      "visual_effect": "<zoom_in|zoom_out|pan_left|pan_right|none>",
      "emotion": "<hook|calm|dramatic|excited|suspense|closing>",
      "speech_rate_modifier": "<vd: +10%, 0%, -5%>",
      "highlight_text": "<1-3 TỪ HOA hoặc chuỗi rỗng>",
      "transition": "<1 mã chuyển cảnh>"
    }
  ]
}

BẢNG GIÁ TRỊ HỢP LỆ — dùng SAI một mã là app bỏ qua hiệu ứng đó:
- recommended_bgm: moment_of_peace, deep_abstract_ambient, new_age_nature,
  running_night, lofi_jazzy_love, type_beat, hype_drill, afro_pop,
  comedy_cartoon, music_promotion, no_sleep_hiphop, rap_beat
- sfx: whoosh, swoosh_soft, pop, tick, ding, bell, shimmer, riser,
  bass_drop, impact, suspense, heartbeat, laugh
- transition: crossfade, fade_black, fade_white, zoom_through, zoom_punch,
  slide_left, slide_right, slide_up, slide_down, wipe_right, wipe_down,
  whip_pan, page_flip, droplet

LUẬT LỜI THOẠI (trường "text"):
- Mỗi cảnh {TỪ_MỖI_CẢNH} từ. NGOẠI LỆ Cảnh 1: chỉ 8-10 từ.
- Văn nói tự nhiên. KHÔNG emoji, KHÔNG Markdown, KHÔNG ngoặc vuông.
- Mỗi cảnh kết bằng câu tạo tò mò nhẹ.
- BẮT BUỘC: ≥2 trích dẫn nguyên văn, ≥2 con số/mốc thời gian,
  ≥1 câu chuyện có tên nhân vật.
- CẤM: "Xin chào các bạn", "Hôm nay chúng ta", "Cùng tìm hiểu nhé",
  "Bạn có biết", "hãy kiên trì". Cấm đạo lý suông.
- Cảnh 1 = hook sắc nhất (dùng câu Hook đã chọn ở Bước 5).
- Cảnh cuối = kết bài trọn vẹn, không cụt.

LUẬT "image_prompt":
- Tiếng Anh, mở đầu bằng góc máy điện ảnh rồi " of " rồi chủ thể.
- Cảnh QUAY THẬT, tìm được trên kho stock Pexels. Cấm anime/CGI/phép thuật.
- Chọn theo CẢM XÚC, không minh hoạ từng chữ.

LUẬT HIỆU ỨNG (bản vẽ kể chuyện sách — bám theo VỊ TRÍ TƯƠNG ĐỐI của cảnh):
- Cảnh 1: emotion "hook", sfx "riser", transition "crossfade", rate "+10%".
- ~15% đầu: emotion "calm", transition "crossfade", sfx rỗng.
- Giữa bài: transition "crossfade"; dùng "page_flip" khi sang chương/bước ngoặt mới.
- ~45%: MINI-TWIST giữ chân — emotion "suspense", sfx "suspense",
  transition "fade_black".
- ~80%: CAO TRÀO tiết lộ lớn nhất — emotion "dramatic", sfx "riser",
  transition "zoom_punch", rate "-3%".
- Sau cao trào: khoảnh khắc ngộ ra — sfx "shimmer" ĐÚNG 1 LẦN,
  transition "droplet".
- Cảnh cuối: emotion "closing", transition "fade_black", rate "-5%", sfx "ding".
- MỌI cảnh còn lại: sfx phải là chuỗi rỗng "". Lạm dụng sfx làm hỏng chất kể chuyện.
- highlight_text: chỉ điền ở 3-5 cảnh mạnh nhất, còn lại để rỗng "".
```

> **Nếu app báo lỗi parse JSON:** dán lại đúng thông báo lỗi vào chat và bảo
> *"Sửa lại JSON cho hợp lệ, chỉ trả về khối JSON, không thêm chữ nào."*

---

## BƯỚC 7 — Chống bịa (Prompt D) (1 phút)

Dán vào chat ngay sau khi nhận kịch bản:

```
Đây là kịch bản tôi vừa nhận. Đối chiếu từng câu với nguồn, lập bảng 3 cột:
Câu trong kịch bản | Có trong nguồn (Có/Không) | Số trích dẫn hoặc "KHÔNG CÓ TRONG NGUỒN".
Chỉ kiểm tra câu chứa con số, tên riêng, năm tháng, tuyên bố nhân quả.
Tuyệt đối không sửa kịch bản, chỉ báo cáo.
```

→ Xoá các câu bị đánh "KHÔNG CÓ TRONG NGUỒN" trước khi đưa vào App.

---

## BƯỚC 8 — Đưa vào App AI-VIDEO-MAKER

### 8.1 — Thiết lập BẮT BUỘC

| Ô cài đặt | Giá trị | Vì sao |
|---|---|---|
| Chế độ | **Script → Video** | |
| **Hiệu ứng Hook** | **Slot Machine & Bìa sách (Carousel Quote)** | 🔴 **Không bật thì Quote bìa và Máy Xèng đều không xuất hiện** — và app không báo lỗi gì cả |
| Ảnh bìa | Upload ảnh bìa sách | |
| Vị trí chèn ảnh bìa | **Chèn lên Cảnh Đầu (Start)** | 🔴 Bắt buộc — máy xèng lấy chính hình của Cảnh 1 làm bìa. Để `end` thì trục quay sẽ dừng ở một ảnh AI ngẫu nhiên |
| Quote Bìa | Câu (B) từ Bước 5, **tối đa 10 từ** | |
| Kịch Bản Của Bạn | Nhánh A: dán nguyên khối văn bản | |
| Thể loại (Niche) | `book` / `psychology` / `finance` / `history` | |
| Phong cách (Tone) | `storytelling` cho sách & tâm lý; `educational` cho tài chính | |
| Số cảnh + Thời lượng | Theo bảng 6.0 | |

### 8.2 — Thiết lập nên bật (nâng chất lượng rõ rệt)

| Ô cài đặt | Giá trị | Vì sao |
|---|---|---|
| **Nguồn hình ảnh** | **`stock_video`** | Prompt C đã ép viết mô tả kiểu cảnh quay thật — set thẳng stock_video để app lấy footage Pexels thay vì ảnh AI tĩnh. Để `auto` là app tự đoán bằng heuristic |
| Ken Burns | Bật | Ảnh tĩnh (kể cả bìa) vẫn có chuyển động nhẹ |
| Kiểu phụ đề | `karaoke_bold` | |

### 8.3 — Nếu đi Nhánh B (JSON)

1. Mở **Script Editor**
2. Bấm nút **Nhập JSON** (viền vàng)
3. Dán nguyên khối JSON từ Bước 6.B → OK
4. App tự điền: các cảnh, Quote bìa, BGM, CTA
5. Vẫn phải tự tay set ở phần cài đặt: **Hiệu ứng Hook = Carousel Quote**, ảnh bìa, vị trí `start`, niche, nguồn hình ảnh

### 8.4 — Spot-check rồi Render

Không cần rà cả 30 cảnh — bản vẽ niche đã tự gán hiệu ứng. Chỉ kiểm 3 cảnh:

- **Cảnh 1** — lời thoại có ngắn (8-10 từ) không?
- **Cảnh cao trào (~80%)** — có `zoom_punch` + `riser` không?
- **Cảnh cuối** — có `fade_black` và kết trọn vẹn không?

→ **Render!**

---

## CHECKLIST NHANH TRƯỚC KHI RENDER

**Nội dung**
- [ ] Đã có đủ 5 Ghi chú (4 Studio + 1 prompt chat)?
- [ ] Đã chuyển Ghi chú → Nguồn tinh chế, bỏ tick PDF gốc?
- [ ] Kịch bản có: ≥2 trích dẫn, ≥2 con số, ≥1 câu chuyện có tên nhân vật?
- [ ] Số cảnh khớp CHÍNH XÁC bảng 6.0?
- [ ] Lời thoại sạch: không emoji, không ký hiệu Markdown?
- [ ] **Cảnh 1 chỉ 8-10 từ?**
- [ ] Cảnh cuối kết trọn vẹn, không cụt?
- [ ] Hình ảnh toàn cảnh quay thật, có " of " sau góc máy?
- [ ] Đã chạy Prompt D và xoá câu bịa?

**Thiết lập App (dễ quên nhất)**
- [ ] 🔴 **Hiệu ứng Hook = Carousel Quote?**
- [ ] 🔴 **Ảnh bìa đã upload, vị trí = start?**
- [ ] Quote bìa **tối đa 10 từ**, không emoji?
- [ ] Nguồn hình ảnh = `stock_video`?
- [ ] Niche + Tone đã chọn?

---

## SƠ ĐỒ TỔNG THỂ

```
Ebook (.pdf)           Ảnh bìa sách
    │                       │
    └── Upload vào ──► NotebookLM
                            │
         ┌──────────────────┴───────────────────┐
         │           STUDIO (4 nút):            │
         │  1. Báo cáo → Tài liệu tóm tắt       │
         │  2. Bảng dữ liệu (dán prompt)        │
         │  3. Bản đồ tư duy (dán prompt)       │
         │  4. Âm thanh Tùy chỉnh (dán prompt)  │
         └──────────────┬───────────────────────┘
                        │
              + Prompt bổ sung (chat)
                        │
                   5 Ghi Chú
                        │
              Chuyển thành NGUỒN TINH CHẾ
              (bỏ tick PDF gốc)
                        │
           ┌────────────┼─────────────┐
       Prompt B     Prompt C      Prompt D
       Hook+Quote   Kịch bản      Chống bịa
           │             │
           │      ┌──────┴──────┐
           │   Nhánh A       Nhánh B
           │   (văn bản)     (JSON) ◄── khuyến nghị
           ▼      ▼              ▼
    AI-VIDEO-MAKER (Script → Video)
    ├─ Hiệu ứng Hook = CAROUSEL QUOTE  ◄── bắt buộc
    ├─ Ảnh Bìa (vị trí: start)         ◄── bắt buộc
    ├─ Quote Bìa (≤10 từ)
    ├─ Kịch Bản (dán) HOẶC Nhập JSON
    ├─ Niche & Tone
    └─ Nguồn hình = stock_video
    │
    └──► Spot-check 3 cảnh → RENDER
```

---

## PHỤ LỤC A — Timeline thật của video

```
0.00s ┬─ Máy Xèng: bìa sách cuộn như trục quay, tiếng reel_spin
      │  (8 bìa giả lướt qua, ease-out bậc 3)
2.00s ┼─ Bìa THẬT chốt giữa màn hình + tiếng "ding"
2.35s ┼─ GIỌNG ĐỌC Cảnh 1 bắt đầu (lời dẫn vào khi quote đang hiện)
      │  Quote bìa fade-in, giữ tới hết pha reveal
4.50s ┼─ Hết lớp phủ hook. Video chạy tiếp bằng hình của Cảnh 1
      │  ── mà hình đó CHÍNH LÀ ảnh bìa (do vị trí chèn = start)
      ▼
   → Vì vậy Cảnh 1 phải ngắn: qua Cảnh 2 càng sớm càng đỡ tĩnh.
```

**Tổng độ dài video = độ dài kịch bản + 2.35 giây.**

---

## PHỤ LỤC B — Bảng giá trị hợp lệ (tra nhanh)

| Trường | Giá trị hợp lệ |
|---|---|
| `sfx` | whoosh, swoosh_soft, pop, tick, ding, bell, shimmer, riser, bass_drop, impact, suspense, heartbeat, laugh |
| `transition` | crossfade, fade_black, fade_white, zoom_through, zoom_punch, slide_left, slide_right, slide_up, slide_down, wipe_right, wipe_down, whip_pan, page_flip, droplet |
| `emotion` | hook, calm, dramatic, excited, suspense, closing |
| `visual_effect` | zoom_in, zoom_out, pan_left, pan_right, none |
| `recommended_bgm` | afro_pop, black_light_all_good_folks_main, comedy_cartoon, deep_abstract_ambient, fluffy_clouds_fugu_vibes_main_version, hype_drill, lofi_jazzy_love, moment_of_peace, music_promotion, new_age_nature, no_sleep_hiphop, rap_beat, running_night, type_beat |
| `content_niche` | book, finance, history, psychology, truecrime, travel |
| `narration_tone` | viral, storytelling, educational, emotional, humorous |
| `visual_source` | auto, ai_image, stock_video, mixed |

---

## PHỤ LỤC C — Nhật ký thay đổi

**v3.2 — 26/07/2026** (đối chiếu trực tiếp với source code)

| # | Sửa gì | Vì sao |
|---|---|---|
| 1 | Thêm `Hiệu ứng Hook = Carousel Quote` vào thiết lập bắt buộc | App chỉ dựng máy xèng khi `hook_effect == "carousel_quote"`; mặc định là `word_by_word`, nên toàn bộ phần Quote bìa của v3.1 chạy trong vô hiệu mà không báo lỗi |
| 2 | "3.5s đầu" → **4.5s**, thêm ghi chú dời giọng đọc 2.35s | Hook = 2.0s pha quay + 2.5s pha reveal. Bảng thời lượng cũ không tính phần dôi ra |
| 3 | Cảnh 1 giảm còn 8-10 từ; nói rõ image_prompt Cảnh 1 bị bỏ qua | Vị trí bìa `start` thay thẳng ảnh Cảnh 1 bằng file bìa. Cộng với 4.5s hook là ~9 giây bìa tĩnh nếu Cảnh 1 dài |
| 4 | Sửa số cảnh: 90s 18→**19**, 120s 24→**25** | Khớp đúng con số app tự điền khi bấm nút thời lượng |
| 5 | Thêm mốc **240s / 300s** | Sách 400-500 trang nén vào 3 phút là phí nguyên liệu đã chưng cất; app hỗ trợ tới 800 từ |
| 6 | Quote bìa: 15 chữ → **tối đa 10 từ** | Render font 60px trong khung 88%, không có cơ chế cắt bớt |
| 7 | Thêm **Nhánh B — JSON** | App có nút Nhập JSON: bỏ hẳn khâu AI chia cảnh → không còn rủi ro sửa lời thoại, tiết kiệm 1 lượt quota, điều khiển hiệu ứng từng cảnh ngay từ NotebookLM |
| 8 | Thêm `Nguồn hình ảnh = stock_video` | Prompt C vốn đã ép viết mô tả cảnh quay thật; đây là đòn bẩy chất lượng lớn nhất mà v3.1 bỏ không |
| 9 | Bước 8: rà 30 cảnh → **spot-check 3 cảnh** | Bản vẽ niche đã tự gán sfx/transition theo vị trí cảnh |
| 10 | Bổ sung "Hôm nay chúng ta" vào danh sách CẤM của Prompt C | v3.1 chỉ cấm ở Prompt B, sót ở Prompt C |
| 11 | Thêm Phụ lục A (timeline) và B (bảng giá trị) | Tra nhanh khi viết JSON, khỏi đoán mò tên hiệu ứng |

**v3.1 — 26/07/2026** — Loại bỏ cắt chương thủ công. Thêm câu lệnh copy-paste sẵn cho từng bước.
