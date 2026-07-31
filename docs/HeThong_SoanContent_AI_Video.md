# HỆ THỐNG SOẠN CONTENT — AI VIDEO MAKER

Tài liệu tổng quan về hệ thống sinh kịch bản (Content Generation System). Đây là bản **mô
tả kiến trúc**; nội dung prompt nguyên văn nằm ở `Prompt_Engineering_Templates.md` — file đó
được **sinh tự động** từ code bằng `python tools/dump_prompts.py`, nên không bao giờ lệch
với thực tế.

Hệ thống chia làm hai nửa rạch ròi, và biết ranh giới này là điều quan trọng nhất khi sửa
bất cứ thứ gì ở đây:

| | Ai quyết định | Gồm những gì |
|---|---|---|
| **NỘI DUNG** | Gemini, qua system prompt | `text` (lời thoại), `image_prompt`, `highlight_text`, `hook_text`, `cta_text`, `source_quote`, `sentiment`, `recommended_bgm` |
| **CƠ HỌC** | Python, sau khi parse | `emotion`, `sfx`, `transition`, `speech_rate_modifier`, `visual_effect` |

Gemini **không** còn chọn sfx/transition/nhịp đọc: `resolve_blueprint()` gán chúng theo băng
vị trí trong `NICHE_PERCENT_BLUEPRINTS` / `TONE_PERCENT_PALETTES` và ghi đè toàn bộ. Vì vậy
mọi câu trong prompt ra lệnh về các trường đó đều là token vứt đi — chúng đã bị dọn khỏi
prompt trong lần chuẩn hoá ngày 2026-07-30.

---

## 1. Cấu trúc kể chuyện

Hai base prompt, chọn theo `narration_tone`:

**`BASE_VIRAL`** (mặc định, mọi tone trừ `storytelling`) — Curiosity Gap & PAS:

* **HOOK (Cảnh 1)** — móc câu tạo lỗ hổng tò mò. Prompt cung cấp sẵn **công thức hook theo
  từng tone** (`HOOK_FORMULAS`) để model có khuôn điền, thay vì chỉ được ra lệnh trừu tượng
  "hãy tạo Curiosity Gap" rồi tự bơi về mẫu an toàn nhất.
* **TENSION (các cảnh giữa)** — mỗi cảnh nâng mức căng thêm một bậc.
* **CLIMAX (~80% thời lượng)** — plot twist hoặc giải pháp tột đỉnh.
* **CTA (cảnh cuối)** — chốt lại rồi kêu gọi hành động.

**`BASE_STORYTELLING`** (tone `storytelling`) — kể lại cốt truyện sách/phim dạng dài, trầm
lắng, style @sachhay_chondoc: Mở → Diễn biến (mỗi cảnh một nút thắt, kết bằng soft
cliffhanger) → Cao trào → Kết & đúc kết. Base này yêu cầu `image_prompt` mô tả **cảnh quay
thật** tìm được trên kho stock, nên không nối thêm luật cinematic vào.

## 2. Luật chống "content chung chung" (`SPECIFICITY_RULES`)

Đây là phần tách content hay khỏi content nhạt, áp cho **mọi** chế độ:

* Mỗi cảnh phải có ít nhất một **con số / tên riêng / mốc thời gian / chi tiết giác quan**.
  "Rất giàu" → "kiếm 1 triệu đô năm 26 tuổi".
* **Show, don't tell**: "cô run rẩy mở lá thư", không phải "cô rất lo lắng".
* **Mỗi cảnh có đúng 1 lý do giữ chân**: tình tiết mới, câu hỏi bỏ lửng, hoặc một tiết lộ.
* **Cảnh sau nối ý cảnh trước**, không viết rời rạc như gạch đầu dòng.

Kèm theo là `CTA_RULES` (bắt dùng CTA thật, **cấm khan hiếm giả** kiểu "lưu ngay trước khi
video bị gỡ") và `TTS_WRITING_RULES` (câu ngắn, chèn `...` ở chỗ cần lặng, không
markdown/emoji).

> Các luật trên vốn chỉ tồn tại trong `.agents/skills/content-cinematic/` — tài liệu dành
> cho agent viết kịch bản **bằng tay**. Kịch bản do chính app sinh ra không hề được hưởng,
> đúng chỗ khiến content ra chung chung dù dự án đã có sẵn đủ luật chống chung chung.

## 3. Bản vẽ nội dung theo NICHE (`NICHE_BLUEPRINTS`)

Khi người dùng chọn niche trên UI, prompt được nối thêm bản vẽ vị trí riêng của niche đó:
cảnh 1 nói gì, ~45% có mini-twist gì, ~80% cao trào là gì, cảnh cuối chốt thế nào. Hiện có
9 niche: `book`, `finance`, `history`, `psychology`, `truecrime`, `travel`,
`art_masterpiece`, `poetry_literature`, `architecture_wonders`.

Mỗi niche phải có **cả hai** nửa — bản vẽ nội dung (`NICHE_BLUEPRINTS`) và bản vẽ cơ học
(`NICHE_PERCENT_BLUEPRINTS`); `tests/test_prompt_assembly.py` chốt hai bộ khoá này bằng
nhau, vì thiếu một nửa thì lựa chọn của người dùng chỉ có tác dụng một nửa.

## 4. Ngân sách từ (Word Budgeting)

Chỉ có **một** nguồn chân lý: tổng số từ của thời lượng mục tiêu (`DURATION_CONFIG`) chia
cho số cảnh người dùng thực sự chọn (`scene_word_budget()`). Số giây đọc tương ứng quy ra
từ `duration_model.words_per_second()` — tốc độ **đo thật** của giọng đang dùng, không phải
hằng số.

Cách này thay cho luật cứng "15-20 từ/cảnh" của bản cũ: luật cứng đó đá nhau với luật tổng
số từ từ mốc 90s trở lên, và Gemini chọn phá luật số từ → cảnh dài 8+ giây, video ì.

## 5. Nguồn hình quyết định kiểu `image_prompt`

`image_prompt` có **hai kiểu viết khác hẳn nhau**, chọn theo nguồn hình sẽ dùng khi render
(`_wants_stock_footage()` ở `main.py` quyết định, gửi xuống qua `prefer_stock_video`):

* **Ảnh AI** (`IMAGE_PROMPT_RULES_AI`) — mở đầu bằng góc máy điện ảnh, kèm keyword chất
  lượng (`8k, photorealistic, Unreal Engine 5`), lặp lại ngoại hình nhân vật ở mọi cảnh,
  dùng chung một tông màu.
* **Footage stock** (`IMAGE_PROMPT_RULES_STOCK`) — tả cảnh quay thật, đời thường, 3-8 từ
  tiếng Anh, **cấm** thuật ngữ máy quay và keyword render.

Vì sao phải rẽ: ở chế độ stock, `image_prompt` chính là **câu truy vấn tìm video** trên
Pexels (`extract_search_keyword()`). Bản cũ ép jargon cinematic cho *mọi* chế độ, rồi
`extract_search_keyword()` phải mang một danh sách ~40 stopword đi gỡ lại đúng những chữ mà
prompt vừa ép model viết ra — hai tầng đánh nhau, và chữ nào lọt lưới thì thành từ khoá rác
→ Pexels trả về video sai chủ đề.

## 6. Kịch bản dài: chia lô và luật phạm vi lô

Gemini sinh tối đa 12 cảnh mỗi lần gọi, nên video dài được sinh theo nhiều lô, mỗi lô nhận
thêm ngữ cảnh 2 cảnh trước đó. Quan trọng: mỗi lô nhận **luật phạm vi riêng**
(`_batch_scope_rule()`) — lô đầu và lô giữa bị cấm viết cảnh kết/đúc kết/CTA và phải để cảnh
cuối lô bỏ lửng; chỉ lô cuối được phép có lời kết.

Trước khi có luật này, mọi lô đều nhận nguyên dòng "CTA (Cảnh cuối)" nên video 30 cảnh có
**ba cái kết** — hai cái nằm giữa bài (cảnh 12 và 24). `cta_text` cũng được lấy từ lô cuối,
vì chỉ nó biết video kết thúc ở đâu.

## 7. Kiểm duyệt chất lượng 2 tầng (`review_script`)

1. **Tầng 1 — `_local_review` (heuristic, miễn phí, luôn chạy):** bắt cụm từ sáo rỗng
   (`CLICHE_PHRASES`), cảnh vượt ngân sách từ, cảnh cuối thiếu CTA, hook mở đầu bằng câu
   chào. Danh sách cụm sáo rỗng dùng **chung một hằng số** với prompt, nên model không còn
   bị trừ điểm vì luật chưa ai nói cho nó biết (bản cũ: prompt cấm 4 cụm, review phạt 15).
2. **Tầng 2 — `_gemini_narrative_review`:** một lần gọi `gemini-flash-latest`
   (`temperature=0.3`) chấm 3 khía cạnh heuristic không "hiểu" được: sức hút của hook trong
   3 giây đầu, độ "đô" của cao trào, mạch cảm xúc có bị phẳng/đứt. Là lớp **best-effort** —
   lỗi quota/mạng bị bỏ qua êm, không chặn luồng sinh kịch bản.

Điểm cuối = trung bình cộng hai tầng; `passed` khi ≥ 60.

Lớp này cố ý **không báo động sai**, vì một cảnh báo sai làm người dùng đi sửa thứ vốn đã
đúng rồi mất niềm tin vào cả lớp review. Ba chỗ đã tinh chỉnh theo số đo trên kịch bản thật:

* **Ngân sách từ có biên dung sai ±10%** — lố 1 từ trên trần 14 (≈0.35 giây) không phá nhịp,
  nhưng bản cũ vẫn gắn `error` và trừ 8 điểm. Cảnh dài thật (20/14) vẫn bị bắt.
* **CTA dạng câu hỏi mở** được tính là CTA (đây còn là kiểu CTA hook-library.md khuyến nghị).
* **`cta_text` cấp video** được tính là CTA, vì `resolve_outro_text()` đem đúng chuỗi đó ra
  làm chữ ở đuôi video.

## 7.5. Vòng VIẾT LẠI khi điểm thấp (`regenerate_if_low_quality`)

Nếu điểm dưới **60/100**, hệ thống viết lại **đúng một lượt**, nối các nhận xét của lớp
review vào prompt để bản mới sửa đúng chỗ. Ba chốt an toàn:

1. **Đúng một lượt** — mỗi lượt tốn thêm quota.
2. **Bản mới phải điểm cao hơn mới được nhận.** Viết lại có thể ra bản tệ hơn; im lặng thay
   bằng bản tệ hơn còn hại hơn không làm gì. UI nhận `regenerated` + `previous_score` để nói
   rõ cho người dùng, hoặc `rejected_retry_score` khi bản viết lại bị loại.
3. **Chỉ kích hoạt với loại lỗi mà viết lại thật sự sửa được** (`weak_hook`, `weak_climax`,
   `flat_emotion`, `flat_pacing`, `narrative_gap`, `cliche`). `too_long` bị loại cố ý —
   scene_balancer và luật số từ đã lo, một cảnh lố 2 từ không xứng một lượt quota.
4. Lỗi ở lượt viết lại (quota/mạng) bị bỏ qua êm, trả về bản đầu.

Tắt được bằng `auto_retry_low_quality` (công tắc ở Cài đặt nâng cao). **Không áp cho mode
`script_video`**: lời thoại ở đó là của người dùng, giữ nguyên văn 100% là hợp đồng — "viết
lại" nghĩa là sửa lời người ta.

## 7.6. Ba trường hook cấp video

Rất dễ nhầm lẫn với nhau, nên prompt giải thích tường minh cả ba:

| Trường | Dùng cho | Ràng buộc |
|---|---|---|
| `hook_text` | Tiêu đề vẽ ĐÈ lên ảnh bìa (`word_by_word`, `full_shake`) | < 10 chữ, **không** lặp tên sách/chủ đề (bìa đã in sẵn) |
| `hook_variants` | A/B test hook | 3 biến thể khác nhau cả góc tiếp cận |
| `hook_quote` | Hiệu ứng dạng quote (`carousel_quote`, `typewriter_quote`, `blackout_question`) | Viết HOA, < 15 từ, 2 vế đối lập, đứng một mình vẫn đáng trích |

`hook_quote` trước đây **không có trong schema Gemini** dù `RenderVideoRequest` và
`video_service.build_carousel_hook()` đều chờ nó — ai muốn dùng hiệu ứng bìa-sách-kèm-quote
đều phải tự gõ câu quote.

## 8. Chống bịa (`source_coverage`)

Prompt yêu cầu điền `source_quote` + `source_ref` khi chủ đề gắn với tác phẩm/tài liệu/sự
kiện thật, và nói rõ **thà để trống còn hơn bịa** một câu trích không tồn tại.
`source_coverage` = tỉ lệ cảnh có `source_quote`. Chỉ số này trước đây luôn bằng 0.0 vì
không prompt nào từng yêu cầu điền trường đó.

---

## Sửa prompt ở đâu, cần làm gì

1. Sửa trong `backend/services/gemini_service.py`. Cả ba prompt giờ đều là **hàm thuần** —
   test được, không cần gọi mạng:
   * `build_script_system_prompt()` — `generate_script` (storyteller/quiz/storytelling)
   * `build_split_system_prompt()` — `split_script_to_scenes`
   * `build_photo_system_prompt()` — `generate_script_from_images`
2. **Đổi chuỗi revision** tương ứng (`PROMPT_REVISION` / `SPLIT_PROMPT_REVISION` /
   `IMAGE_PROMPT_REVISION`). Chúng nằm trong cache key; không đổi thì kịch bản cũ trong
   cache sẽ đè lên luật mới và trông như "sửa không có tác dụng".
3. Chạy `python tests/test_prompt_assembly.py` (từ `backend/`).
4. Chạy `python tools/dump_prompts.py` để cập nhật `Prompt_Engineering_Templates.md`.
