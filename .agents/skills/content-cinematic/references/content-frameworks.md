# Content Frameworks — Khung nội dung theo NICHE (để content CỤ THỂ hơn)

Đây là "vũ khí" chính giúp content không chung chung. **Chọn đúng framework theo chủ đề**, rồi
áp công thức Hook + cấu trúc + kho footage + palette (BGM/transition/sfx) riêng của nó.
Mỗi framework đã tinh chỉnh cho pipeline app (video stock, cinematic_box, OmniVoice).

> Cách dùng: nhận diện niche → theo bảng của niche đó → điền Scene JSON. Nếu chủ đề lai, trộn 2 framework gần nhất.

---

## 📚 1. Review / Tóm tắt Sách (kiểu @sachhay_chondoc)

- **Khán giả**: người thích đọc, tìm sách hay, muốn "đọc hộ".
- **Hook**: `carousel_quote` (bìa sách + câu quote đắt nhất). `hook_quote` = **câu chốt trị giá cả cuốn sách**, viết HOA, ngắn (< 15 từ). VD: *"NGƯỜI NGHÈO LÀM VIỆC VÌ TIỀN. NGƯỜI GIÀU BẮT TIỀN LÀM VIỆC CHO MÌNH."*
- **Cấu trúc** (240s/300s): Bìa+Quote → Bối cảnh nhân vật → 3-4 nút thắt cốt truyện (mỗi cảnh 1 soft cliffhanger) → Cao trào/plot twist → Bài học đọng lại + mời đọc.
- **Footage**: hand writing letter, old books on shelf, person reading by window, rainy street, candle, vintage clock, coffee cup.
- **Palette**: BGM `deep_abstract_ambient`/`moment_of_peace` · transition `fade_black`/`page_flip`/`crossfade` · sfx thưa (`riser` mở, `suspense` cao trào) · rate `-5%` · subtitle `cinematic_box`.
- **Cảnh 1 image_prompt**: mô tả BÌA SÁCH hoặc vật thể biểu tượng (để carousel dùng làm cover) — VD `close-up of an old book cover on a wooden desk, warm light`.

## 💰 2. Tài chính / Làm giàu / Kinh doanh

- **Khán giả**: người trẻ muốn đổi đời, nhà đầu tư, freelancer.
- **Hook**: con số sốc hoặc nghịch lý tiền bạc. VD: *"Căn nhà bạn đang ở có thể đang âm thầm rút cạn ví bạn."*
- **Cấu trúc**: Nghịch lý/nỗi đau tiền → giải thích cơ chế (tài sản vs tiêu sản) → ví dụ thực tế/con số → nguyên tắc vàng → hành động cụ thể.
- **BẮT BUỘC cụ thể**: luôn có **con số, tỉ lệ, mốc thời gian** ("70% người...", "sau 5 năm...", "300 triệu"). Cấm nói đạo lý suông.
- **Footage**: stacks of cash, city skyline dusk, laptop with charts, handshake, luxury car, coins stacking, busy office.
- **Palette**: BGM `type_beat`/`running_night` · transition `zoom_punch`/`whip_pan` · sfx `bass_drop` (con số), `riser` (mở) · rate `+10%` · subtitle `karaoke_bold` hoặc `cinematic_box`.

## 🏛️ 3. Lịch sử / Bí ẩn / Sự thật giấu kín

- **Khán giả**: người tò mò, mê khám phá, thuyết âm mưu nhẹ.
- **Hook**: hé lộ bí mật/đảo chiều nhận thức. VD: *"Suốt 100 năm, thứ này bị xoá khỏi sách sử. Cho đến khi..."*
- **Cấu trúc**: Bí ẩn mở màn → dựng bối cảnh lịch sử → chuỗi manh mối/sự kiện → tiết lộ sự thật gây sốc → ý nghĩa với hiện tại.
- **Footage**: ancient ruins, old maps, museum artifacts, foggy landscape, candle-lit manuscript, statues, archival-style city.
- **Palette**: BGM `deep_abstract_ambient`/`new_age_nature` · transition `fade_black`/`droplet` · sfx `suspense`/`heartbeat` (căng), `impact` (tiết lộ) · rate `-3%` · subtitle `cinematic_box`.

## 🧠 4. Tâm lý / Self-help / Insight cuộc sống

- **Khán giả**: người muốn hiểu bản thân, cải thiện tư duy, chữa lành.
- **Hook**: khoét insight/nỗi đau thầm kín. VD: *"Lý do bạn luôn mệt mỏi không phải vì lười. Mà vì điều này."*
- **Cấu trúc**: Insight gây đồng cảm → giải thích hiện tượng tâm lý (đặt tên: hiệu ứng X) → ví dụ đời thường → cách áp dụng → câu hỏi tự vấn.
- **Footage**: person alone in thought, walking in nature, journaling, morning light in room, hands on face, quiet cafe.
- **Palette**: BGM `moment_of_peace`/`lofi_jazzy_love` · transition `crossfade`/`slide_left` · sfx thưa (`shimmer` nhấn) · rate `-5%` · emotion nhiều `calm`/`closing`.

## 🔪 5. True Crime / Vụ án / Kể chuyện có thật

- **Khán giả**: mê hình sự, hồi hộp, phá án.
- **Hook**: tình huống rùng mình + câu hỏi mở. VD: *"Cô gái biến mất không dấu vết. 3 ngày sau, điện thoại cô bất ngờ sáng lên..."*
- **Cấu trúc**: Hiện trường/mất tích → dựng nghi vấn → manh mối lật ngược → hung thủ/sự thật → kết cục + suy ngẫm.
- **Footage**: dark street night, car headlights, police tape (generic), rainy window, phone screen glowing, empty room, forest at dusk.
- **Palette**: BGM `no_sleep_hiphop`/`deep_abstract_ambient` · transition `fade_black`/`whip_pan` · sfx `heartbeat`/`suspense` (căng), `bass_drop` (twist) · rate `0%~+5%` · subtitle `cinematic_box`.
- ⚠️ Đạo đức: không bịa chi tiết vụ án thật, không nêu tên nạn nhân/nghi phạm thật khi chưa xác thực; ghi rõ nếu là hư cấu.

## 🌍 6. Khám phá / Du lịch / Địa điểm

- **Khán giả**: người mê xê dịch, tìm chỗ check-in, "đi hộ".
- **Hook**: địa điểm giấu kín/trải nghiệm độc. VD: *"Nơi này Google Maps cũng khó tìm — nhưng dân bản địa giữ như báu vật."*
- **Cấu trúc**: Teaser cảnh đẹp → dẫn đường/không khí → điểm nhấn độc đáo → trải nghiệm giác quan → chốt + rủ đi.
- **Footage**: aerial mountain, foggy forest, local market, waterfall, sunset beach, old town street, cafe interior.
- **Palette**: BGM `fluffy_clouds_fugu_vibes_main_version`/`new_age_nature` · transition `slide_up`/`wipe_right`/`zoom_through` · sfx `swoosh_soft`/`shimmer` · rate `0%` · color `vivid_pop`.

---

## Bảng chọn nhanh

| Niche | Hook effect | hook_quote? | BGM | Nhịp | Subtitle |
|---|---|---|---|---|---|
| Sách | carousel_quote | ✅ bắt buộc | deep_abstract_ambient | -5% | cinematic_box |
| Tài chính | word_by_word / carousel | tùy | type_beat | +10% | karaoke_bold |
| Lịch sử | word_by_word | tùy | deep_abstract_ambient | -3% | cinematic_box |
| Tâm lý | word_by_word | ❌ | moment_of_peace | -5% | cinematic_box |
| True Crime | full_shake / word | tùy | no_sleep_hiphop | +5% | cinematic_box |
| Du lịch | word_by_word | ❌ | new_age_nature | 0% | minimal_white |
