# 📘 HƯỚNG DẪN TOÀN BỘ — NotebookLM → AI-VIDEO-MAKER
## Quy trình chuẩn khai thác sách thành nội dung video

**Phiên bản:** v4.0 — "Book Extract"
**Thay thế:** SOP v3.2 (8 bước NotebookLM/video)
**Nguyên tắc cốt lõi:** NotebookLM chỉ làm việc mà App không làm được — đọc sách và trả nguồn.
Mọi việc cơ học (chia cảnh, gán hiệu ứng, chống bịa) chuyển sang App xử lý tự động.

**Thời gian:** ~10-12 phút / sách (chạy 1 lần, dùng lại cho nhiều video)

---

## 0. TRIẾT LÝ THAY ĐỔI SO VỚI SOP CŨ

| | SOP v3.2 (cũ) | SOP v4.0 (mới) |
|---|---|---|
| Tần suất chạy NotebookLM | Mỗi video | **1 lần / sách** |
| Số lượt tương tác NotebookLM | 8 (4 Studio + 3 Prompt + Nhánh JSON) | **2 lượt** |
| Đầu ra NotebookLM | Kịch bản/JSON hoàn chỉnh | **File trích xuất có cấu trúc** (Book Extract) |
| Ai chia cảnh, gán sfx/transition | NotebookLM đoán mò | **App tự động** (Python, xem tài liệu kiến trúc) |
| Ai chống bịa | Prompt D thủ công | **App tự validate** bằng `quotes[]` |
| Làm video thứ 2 từ cùng sách | Chạy lại từ đầu (~40 phút) | **Chỉ chạy App** (~5 phút) |

**Vì sao đổi:** NotebookLM không có API công khai (kiểm tra lại tình trạng vì có thể đã đổi), nên nó mãi mãi là thao tác tay. Cách dùng hiệu quả nhất là **giảm số lần chạm vào nó xuống tối thiểu**, và bắt nó sinh ra một tài sản dùng lại được nhiều lần — không phải một kịch bản dùng một lần.

---

## PHẦN A — QUY TRÌNH TRONG NOTEBOOKLM

### A.0 — Chuẩn bị

| Nguyên liệu | Yêu cầu |
|---|---|
| File ebook | .PDF có text thật (không phải ảnh scan), .TXT, hoặc .MD |
| Ảnh bìa sách | JPEG/PNG/WebP, tối thiểu 600×800px |
| Nguồn phụ (khuyến khích) | Bài review, phỏng vấn tác giả, tranh cãi liên quan tới sách |

> ⚠️ Dùng bản sách có bản quyền hợp pháp nếu video sẽ bật kiếm tiền trên TikTok/YouTube.

### A.1 — Nạp nguồn (2 phút)

1. Mở [notebooklm.google.com](https://notebooklm.google.com) → Tạo Notebook mới
2. Đặt tên Notebook = tên sách (để dễ tìm lại khi cần làm video thứ 2, thứ 3)
3. **"+ Thêm nguồn"** → Upload file PDF chính
4. Upload thêm 1-2 nguồn phụ nếu có — **đây là bước hay bị bỏ quên nhưng quan trọng**: nguồn phụ là nơi duy nhất chứa thông tin sách không tự kể về mình (tranh cãi, số liệu bán chạy, tác giả nói gì sau này)
5. Đợi thanh tiến trình xử lý biến mất ở tất cả nguồn

### A.2 — Prompt 1: Sinh Book Extract (5-6 phút)

Tick chọn **toàn bộ nguồn** đã upload. Dán nguyên văn prompt sau vào khung chat:

````
Bạn là một biên tập viên nội dung, nhiệm vụ là khai thác cuốn sách này để làm
nguyên liệu cho video ngắn. CHỈ dùng thông tin có trong nguồn đang được chọn.
TUYỆT ĐỐI không suy diễn hay bịa thêm. Nếu một mục không đủ thông tin trong
nguồn, bỏ qua mục đó thay vì đoán.

Trả lời DUY NHẤT bằng một khối JSON hợp lệ theo đúng cấu trúc dưới đây,
không thêm chữ nào trước hoặc sau khối JSON, không dùng markdown code fence.

{
  "book": {
    "title": "tên sách",
    "author": "tên tác giả",
    "core_pain": "1 câu mô tả nỗi đau người đọc đang gặp, viết như thể người đọc tự nói với bản thân lúc 2 giờ sáng",
    "counter_thesis": "1 câu: điều sách chỉ ra ngược với điều đa số người tưởng"
  },

  "moments": [
    // Tìm đúng 6-8 khoảnh khắc/câu chuyện/thí nghiệm HAY NHẤT trong sách,
    // xếp theo độ cuốn hút giảm dần. Với mỗi moment:
    {
      "id": "m1",
      "title": "tên ngắn gọn cho khoảnh khắc này",
      "hook_score": 0,        // 1-10, mức độ gây shock/tò mò/đồng cảm
      "type": "story",        // "story" (có nhân vật+diễn biến) hoặc "insight" (một ý tưởng phản trực giác không cần nhân vật)
      "summary": "80-120 từ, kể theo: ai/bối cảnh -> điều xảy ra -> điều bất ngờ -> hệ quả. Giữ đúng tên riêng và số liệu.",
      "characters": ["tên nhân vật xuất hiện, để rỗng nếu type=insight"],
      "numbers": ["mọi con số/tỉ lệ/năm tháng xuất hiện trong đoạn này"],
      "source_ref": "chương/trang cụ thể",
      "why_viral": "1 cụm ngắn: relatable / counter-intuitive / shocking / dark-twist"
    }
  ],

  "quotes": [
    // 12-15 câu trích dẫn NGUYÊN VĂN, ưu tiên câu nghịch lý, thức tỉnh,
    // hoặc câu tác giả tự đóng khung như một nguyên tắc.
    {
      "id": "q1",
      "text": "nguyên văn chính xác từ sách, được phép cắt ngắn nhưng KHÔNG đổi từ",
      "source_ref": "chương/trang",
      "word_count": 0,          // tự đếm số từ
      "cover_eligible": false   // true nếu <= 10 từ VÀ mang tính nghịch lý/thức tỉnh cao -> ứng viên cho Quote Bìa
    }
  ],

  "stats": [
    // TẤT CẢ con số, tỉ lệ, mốc thời gian có ý nghĩa trong sách
    { "value": "con số kèm đơn vị", "context": "con số này nói về điều gì", "source_ref": "chương/trang" }
  ],

  "sensory_details": [
    // 10 chi tiết giác quan cụ thể trong sách: hình ảnh, vật thể, ánh sáng, âm thanh
    // (VD: "lá thư viết dưới ánh nến"). Đây là nguyên liệu để đặt hình ảnh video.
  ],

  "context": {
    "reception": "sách được đón nhận thế nào (nếu có nguồn phụ đề cập), để rỗng nếu không có",
    "controversy": "tranh cãi/phản bác nếu có, để rỗng nếu không có",
    "author_note": "phát ngôn đáng chú ý của tác giả ngoài sách nếu có nguồn phụ đề cập, để rỗng nếu không có"
  }
}
````

→ Đợi AI trả lời xong → Bấm **"Lưu vào Ghi chú"**

> **Vì sao 1 prompt duy nhất thay cho 3 nút Studio + prompt cũ:** Báo cáo/Bảng dữ liệu/Bản đồ tư duy của SOP cũ là 3 định dạng khác nhau của cùng một việc — đọc hiểu sách. Gộp lại thành 1 yêu cầu JSON có cấu trúc giúp NotebookLM tập trung nội dung, đồng thời output đã sẵn sàng để copy thẳng vào App mà không cần diễn giải lại.

### A.3 — Prompt 2: Hook + Quote bìa (2-3 phút)

Dán tiếp vào cùng khung chat (vẫn giữ nguyên tick chọn nguồn):

````
Dựa trên các "moments" và "quotes" đã liệt kê ở trên, sinh thêm:

Trả lời DUY NHẤT bằng JSON, nối thêm 2 trường sau vào cấu trúc trước đó
(chỉ cần trả 2 trường này, không cần lặp lại toàn bộ JSON cũ):

{
  "hook_candidates": [
    // 10 phương án câu HOOK mở màn video, mỗi câu dưới 14 từ.
    // CẤM: "Bạn có biết", "Hôm nay chúng ta", "Cùng tìm hiểu".
    // Mỗi hook phải bám vào ĐÚNG MỘT trong các "moments" ở trên (ghi rõ from_moment).
    {
      "text": "câu hook",
      "type": "NGHICH_LY",   // hoặc: CON_SO_SOC / CAU_HOI_KHOET_DAU / TUYEN_BO_PHAN_TRUC_GIAC
      "from_moment": "m1",   // id của moment tương ứng
      "word_count": 0
    }
  ],
  "cover_quote_recommendation": "id của quote trong danh sách quotes có cover_eligible=true, phù hợp nhất làm Quote Bìa. Nếu không có quote nào <=10 từ đủ mạnh, viết 1 câu MỚI tối đa 10 từ, lấy nguyên văn cắt ngắn từ 1 quote gần nhất, không đổi từ."
}
````

→ Đợi AI trả lời → Bấm **"Lưu vào Ghi chú"**

**Tổng cộng sau A.2 + A.3: 2 Ghi chú.**

### A.4 — Gộp thành 1 file Book Extract hoàn chỉnh (1-2 phút)

1. Copy nội dung JSON từ 2 Ghi chú
2. Gộp thủ công (hoặc dán cả 2 vào một trình soạn thảo, hợp nhất 2 khối JSON làm một — `hook_candidates` và `cover_quote_recommendation` nối vào object chính)
3. Kiểm tra nhanh bằng mắt:
   - [ ] JSON không báo lỗi cú pháp (dán thử vào [jsonlint.com](https://jsonlint.com) nếu không chắc)
   - [ ] `moments` có ít nhất 6 mục, mỗi mục có `source_ref`
   - [ ] `quotes` có ít nhất 10 mục
   - [ ] Có ít nhất 1 quote với `cover_eligible: true` hoặc có `cover_quote_recommendation`
4. Lưu file: `extracts/[ten-sach].json`

> 💡 **Đây là tài sản, không phải rác tạm thời.** Lưu lại trong một thư mục cố định. Lần sau muốn làm video 60s cho TikTok từ cùng cuốn sách này, bạn mở lại file này — **không cần mở NotebookLM nữa**.

---

## PHẦN B — TỪ BOOK EXTRACT VÀO APP

Đây là phần thay thế Bước 5-7 của SOP v3.2 (Hook, Kịch bản, Chống bịa). Thay vì dán prompt vào NotebookLM để nó tự viết kịch bản, bạn **chọn nguyên liệu** rồi để App xử lý.

### B.1 — Chọn moments cho video này (thao tác tay, ~1 phút)

Mở file Book Extract, nhìn vào mảng `moments[]` đã được xếp theo `hook_score` giảm dần.

**Quy tắc chọn theo thời lượng video:**

| Thời lượng video | Số moment nên dùng | Ghi chú |
|---|---|---|
| 60s (TikTok) | 1 moment | Chọn `hook_score` cao nhất |
| 90-120s | 2 moment | 1 story + 1 insight, hoặc 2 story |
| 180-240s | 2-3 moment | Sách 400-500 trang nên ở mốc này |
| 300s | 3-4 moment | Trần cứng app là 30 cảnh — đừng nhồi quá 4 moment |

→ Ghi lại `id` của các moment đã chọn, ví dụ: `["m1", "m3", "m5"]`

### B.2 — Trường nào copy vào ô nào của App

Đây là bảng tra cứu chính — dùng mỗi lần dựng video.

| Trường trong App | Lấy từ Book Extract | Cách xử lý |
|---|---|---|
| **Topic / Chủ đề** (nếu mode `storyteller`) | `book.title` + `book.core_pain` | Ghép thành 1 câu ngắn |
| **Kịch Bản Của Bạn** (nếu mode `script_video`) | Nội dung tự viết dựa trên `moments` đã chọn (xem B.3) | Viết narrative, KHÔNG dán thẳng JSON |
| **Quote Bìa** | `cover_quote_recommendation` hoặc quote có `cover_eligible: true` | Đếm lại đúng ≤10 từ trước khi dán |
| **Ảnh bìa** | File ảnh bìa đã chuẩn bị ở A.0 | Upload trực tiếp, vị trí = `start` |
| **Hook** (nếu app có ô hook riêng) | 1 câu chọn từ `hook_candidates`, ưu tiên `from_moment` trùng với moment đã chọn ở B.1 | — |
| **Character Description** (nếu bật) | `moments[].characters` của moment chính | Chỉ điền nếu muốn AI giữ nhất quán 1 nhân vật xuyên video |
| **Niche** | Suy từ nội dung sách | `book` mặc định cho SOP này |
| **Tone** | `storytelling` cho sách kể chuyện; `educational` nếu sách thiên kỹ năng/số liệu | — |
| **Nguồn hình ảnh** | — | Luôn set `stock_video` (không để `auto`) |
| **Số cảnh + Thời lượng** | — | Theo bảng ngân sách từ của App (không tự tính tay nữa nếu Sprint 4 đã làm — xem Phần D) |

### B.3 — Viết "Kịch Bản Của Bạn" (nếu dùng mode `script_video`)

**Nguyên tắc:** đây KHÔNG phải chỗ dán JSON. App không hiểu `moments[]`. Bạn viết một đoạn văn narrative bằng lời của mình (hoặc nhờ Claude/ChatGPT viết hộ), dựa trên các moment đã chọn.

**Khung viết nhanh (điền vào rồi ghép lại thành 1 khối văn bản liên tục):**

```
[HOOK — lấy từ hook_candidates đã chọn]

[Kể moment 1: dùng summary trong Book Extract làm sườn, viết lại tự nhiên hơn,
 chèn 1-2 quote nguyên văn từ quotes[] nếu hợp]

[Câu chuyển ý — "Điều hay ở đây là..."]

[Kể moment 2, tương tự]

[Nếu có moment 3: lặp lại]

[Kết: 1 câu insight tổng kết + CTA "Muốn biết thêm? Đọc {book.title}"]
```

**Lưu ý khi viết:**
- Giữ nguyên tên riêng, số liệu đúng như trong `moments[].characters` và `.numbers`
- Nếu trích quote, copy CHÍNH XÁC từ `quotes[].text` — đừng diễn giải lại rồi để trong ngoặc kép (đó là bịa trá hình)
- Không cần lo chia cảnh hay đếm từ/cảnh — App tự làm ở bước Script → Video

### B.4 — Nếu dùng Nhánh JSON (mode `manual`, import JSON)

> ⚠️ **Khuyến nghị đọc lại tài liệu kiến trúc trước khi dùng nhánh này.** Sau khi App đã tách hiệu ứng (sfx/transition/emotion) ra khỏi phần LLM phải sinh, Nhánh JSON không còn cần bạn tự gán `zoom_punch`, `riser`... nữa — App tự gán theo blueprint. Nếu App **chưa** nâng cấp phần đó, nhánh JSON vẫn dùng được nhưng bạn phải tự tra Phụ lục giá trị hợp lệ như SOP cũ.

Nếu vẫn cần tự soạn JSON cảnh, chỉ điền 2 trường bắt buộc mỗi cảnh, để App tự vá phần còn lại (nếu App đã có auto-repair) hoặc tự điền dựa trên bảng blueprint đã tra:

```json
{
  "scene": 1,
  "text": "lời thoại — viết từ moment đã chọn",
  "image_prompt": "mô tả cảnh quay tiếng Anh, kiểu \"cinematic shot of ... \"",
  "source_quote": "nếu cảnh này trích quote, copy đúng nguyên văn từ quotes[]",
  "source_ref": "copy từ source_ref tương ứng"
}
```

Hai trường `source_quote` / `source_ref` chỉ cần điền nếu App đã hỗ trợ validator chống bịa tự động (xem Phần C). Nếu App chưa có, bỏ qua 2 trường này và tự đối chiếu bằng mắt trước khi render.

### B.5 — Thiết lập bắt buộc trong App (không đổi so với SOP cũ)

| Ô cài đặt | Giá trị | Vì sao |
|---|---|---|
| Chế độ | `Script → Video` (nếu viết tay ở B.3) hoặc `manual` (nếu JSON ở B.4) | |
| Hiệu ứng Hook | **Carousel Quote** | 🔴 Không bật thì Quote bìa & Máy Xèng không xuất hiện, không báo lỗi |
| Ảnh bìa | Upload, vị trí = **start** | 🔴 Máy xèng lấy ảnh Cảnh 1 làm bìa |
| Quote Bìa | Từ B.2, tối đa 10 từ | |
| Niche | `book` | |
| Tone | `storytelling` / `educational` | |
| Nguồn hình ảnh | `stock_video` | |

---

## PHẦN C — CHỐNG BỊA: LÀM Ở ĐÂU BÂY GIỜ

SOP cũ có "Bước 7 — Chống bịa (Prompt D)" chạy trong NotebookLM. Với quy trình mới, việc này chuyển thành 2 lớp:

### Lớp 1 — Tự động (nếu App có validator, xem tài liệu kiến trúc §7.4)

Nếu bạn đã thêm `source_quote`/`source_ref` vào schema cảnh và validator ở backend, App tự so khớp và gắn cờ vàng vào cảnh có vấn đề. **Không cần làm gì thêm.**

### Lớp 2 — Thủ công (nếu App chưa có validator)

Trước khi Render, tự kiểm bằng mắt theo checklist:

- [ ] Mọi câu có số liệu trong kịch bản → có xuất hiện trong `stats[]` hoặc `moments[].numbers` không?
- [ ] Mọi tên riêng → có trong `moments[].characters` không?
- [ ] Mọi câu trong ngoặc kép (nếu có) → copy Y NGUYÊN từ `quotes[].text`, không phải diễn giải?
- [ ] Câu nào không đối chiếu được → xoá hoặc sửa lại cho khớp nguồn

**Không cần chạy lại NotebookLM để làm việc này** — Book Extract đã có sẵn đủ dữ liệu để đối chiếu tay.

---

## PHẦN D — LÀM VIDEO THỨ 2, THỨ 3 TỪ CÙNG SÁCH

Đây là điểm khác biệt lớn nhất so với SOP cũ.

```
Video 1 (YouTube, 240s)     Video 2 (TikTok, 60s)      Video 3 (so sánh 3 sách)
        │                            │                            │
        └────────────┬───────────────┴────────────────────────────┘
                      ▼
          extracts/atomic-habits.json     (đã có sẵn, không đổi)
```

Quy trình:
1. Mở lại file Book Extract đã lưu — **không mở NotebookLM**
2. Chọn moment khác (hoặc cùng moment, viết lại kịch bản theo hook khác) — quay lại B.1
3. Có thể dùng `hook_candidates` khác trong cùng file để A/B test
4. Dựng lại App — quay lại B.2 → B.5

**Thời gian video thứ 2 trở đi: ~5-8 phút** (so với ~40-50 phút nếu chạy lại toàn bộ SOP cũ).

---

## PHẦN E — SƠ ĐỒ TỔNG THỂ QUY TRÌNH MỚI

```
Ebook (.pdf) + Ảnh bìa + Nguồn phụ
            │
            ▼
     NotebookLM (10-12 phút, 1 LẦN / 1 SÁCH)
            │
    ┌───────┴────────┐
    │  Prompt A.2     │  → Book Extract cơ bản
    │  (moments,      │    (moments, quotes, stats,
    │   quotes,       │     sensory_details, context)
    │   stats...)     │
    ├─────────────────┤
    │  Prompt A.3     │  → Hook + Quote bìa
    │  (hooks,        │
    │   cover quote)  │
    └───────┬─────────┘
            ▼
   extracts/[ten-sach].json   ◄── TÀI SẢN LƯU LẠI, DÙNG NHIỀU LẦN
            │
            │  (mỗi lần muốn ra 1 video mới, bắt đầu lại từ đây)
            ▼
┌───────────────────────────────────────────┐
│  B.1  Chọn 1-4 moment theo hook_score      │
│  B.2  Copy đúng ô: Quote bìa, Hook,        │
│       Character desc, Niche, Tone          │
│  B.3  Viết kịch bản narrative (script_video)│
│       HOẶC B.4 soạn JSON tối giản (manual) │
│  B.5  Set: Carousel Quote, ảnh bìa=start,  │
│       stock_video                          │
└───────────────────┬───────────────────────┘
                     ▼
         App tự động: chia cảnh, gán sfx/
         transition/emotion theo blueprint,
         (tuỳ chọn) validate chống bịa
                     ▼
              Spot-check 3 cảnh → RENDER
```

---

## CHECKLIST NHANH TRƯỚC KHI RENDER (v4.0)

**Book Extract (chỉ kiểm khi tạo mới)**
- [ ] `moments` ≥ 6 mục, mỗi mục có `source_ref`
- [ ] `quotes` ≥ 10 mục, đúng nguyên văn
- [ ] Có ít nhất 1 quote/hook đủ điều kiện làm Quote Bìa (≤10 từ)
- [ ] Đã lưu file vào thư mục `extracts/` để dùng lại

**Mỗi lần dựng video (bắt đầu từ B.1)**
- [ ] Đã chọn đúng số moment theo thời lượng (bảng ở B.1)
- [ ] Kịch bản viết narrative, không dán thẳng JSON
- [ ] Mọi số liệu/tên riêng trong kịch bản đối chiếu được với Book Extract
- [ ] Quote bìa ≤10 từ, không emoji
- [ ] Hiệu ứng Hook = Carousel Quote
- [ ] Ảnh bìa đã upload, vị trí = start
- [ ] Nguồn hình ảnh = stock_video
- [ ] Niche + Tone đã chọn đúng loại sách

---

## PHỤ LỤC — MẪU PROMPT RÚT GỌN (copy nhanh)

### Prompt A.2 (dán vào NotebookLM, đã tick toàn bộ nguồn)
→ Xem khối JSON đầy đủ ở mục A.2 phía trên.

### Prompt A.3 (dán ngay sau, cùng khung chat)
→ Xem khối JSON đầy đủ ở mục A.3 phía trên.

### Prompt sửa lỗi (nếu NotebookLM trả JSON không hợp lệ)
```
JSON bạn vừa trả bị lỗi cú pháp. Sửa lại cho hợp lệ, chỉ trả về khối JSON,
không thêm chữ nào trước hoặc sau, không dùng markdown code fence.
```

---

## PHỤ LỤC — SO SÁNH THỜI GIAN

| | SOP v3.2 (cũ) | SOP v4.0 (mới) |
|---|---|---|
| Sách mới, video đầu tiên | ~40-50 phút | ~15-18 phút |
| Video thứ 2 từ cùng sách | ~40-50 phút (chạy lại từ đầu) | **~5-8 phút** |
| Video thứ 3, 4, 5... | ~40-50 phút / video | **~5-8 phút / video** |
| Số lượt gọi NotebookLM / sách | 8 lượt × N video | **2 lượt, 1 lần duy nhất** |
