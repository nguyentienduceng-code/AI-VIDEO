# App Schema — Nguồn chân lý (AI-VIDEO-MAKER)

Đọc file này trước khi xuất JSON. Mọi giá trị `sfx`, `emotion`, `transition`, `recommended_bgm`
PHẢI nằm trong whitelist dưới đây, nếu không app sẽ bỏ qua hoặc lỗi.

> Đồng bộ với `backend/services/gemini_service.py` (class Scene, ScriptResponse) và
> `backend/services/video_service.py` (VALID_TRANSITIONS), `constants.js` (SFX_OPTIONS, TRANSITIONS).

## Scene (mỗi phân cảnh)

| Field | Kiểu | Bắt buộc | Ghi chú |
|---|---|---|---|
| `scene` | int | có | Số thứ tự từ 1 |
| `text` | string (VN) | có | Lời thoại TTS đọc. KHÔNG emoji/markdown/ký tự đặc biệt |
| `image_prompt` | string (EN) | có | Mô tả hình ảnh. Kiểu prompt phụ thuộc nguồn hình (stock vs AI) |
| `emotion` | enum | nên có | Điều khiển giọng OmniVoice/Edge |
| `sfx` | enum/"" | không | Để trống hầu hết cảnh |
| `transition` | enum | không | Chuyển SANG cảnh sau |
| `visual_effect` | enum | không | `zoom_in, zoom_out, pan_left, pan_right, none` (Ken Burns) |
| `speech_rate_modifier` | string | không | VD `"+15%"`, `"-5%"`, `"0%"` |
| `highlight_text` | string | không | 1-3 từ giật tít (chỉ viral; bỏ trống khi storytelling) |

## ScriptResponse (cấp video)

| Field | Kiểu | Ghi chú |
|---|---|---|
| `sentiment` | enum | `happy, sad, dramatic, suspense, chill, energetic` |
| `recommended_bgm` | enum | Mã BGM (xem whitelist BGM) |
| `hook_text` | string | Tiêu đề giật gân hiện 3s đầu (dùng với hook_effect word_by_word/full_shake) |
| `hook_quote` | string | Câu QUOTE đắt giá (dùng với hook_effect `carousel_quote`) — viết HOA, < 15 từ |
| `cta_text` | string | Kêu gọi hành động cuối |
| `scenes` | Scene[] | Mảng phân cảnh |

## Hook Effect (kiểu mở màn 3-3.5s đầu — cấp video, gửi trong payload render)

| `hook_effect` | Mô tả | Dùng field |
|---|---|---|
| `word_by_word` | Tiêu đề hiện từng chữ đập vào | `hook_text` |
| `full_shake` | Cả câu tiêu đề rung lắc, bung to | `hook_text` |
| `carousel_quote` | **Slot-machine 1s → bìa sách (ảnh cảnh 1) thu vào giữa + hiện Quote 2.5s**. Hợp review sách/quote | `hook_quote` (+ cảnh 1 nên là ảnh bìa/biểu tượng) |

> ⚠️ Khi dùng `carousel_quote`: `image_prompt` của **cảnh 1** được dùng làm ẢNH BÌA (cover) cho hiệu ứng.
> Hãy để cảnh 1 là bìa sách / vật thể biểu tượng rõ nét, và viết `hook_quote` là câu chốt trị giá cả nội dung.

## Whitelist `emotion` (6)

`hook` (mở màn hào hứng), `calm` (điềm tĩnh), `dramatic` (kịch tính, trầm),
`excited` (phấn khích, cao), `suspense` (hồi hộp, thì thầm), `closing` (kết, lắng lại).

## Whitelist `sfx` (14) — để trống nếu không cần

`whoosh`, `swoosh_soft` (vèo nhẹ), `pop`, `tick` (click), `ding`, `bell`, `shimmer` (lấp lánh),
`riser` (dâng trào — hợp mở màn/cao trào), `bass_drop` (trầm rơi), `impact` (va đập),
`suspense`, `heartbeat` (nhịp tim — hồi hộp), `laugh`.
Gợi ý: hook→`riser`; cao trào→`impact`/`bass_drop`; hồi hộp→`suspense`/`heartbeat`; nhấn nhẹ→`shimmer`/`ding`.

## Whitelist `transition` (14)

`crossfade` (mặc định, hoà tan), `fade_black`, `fade_white` (chớp trắng), `zoom_through`,
`zoom_punch` (giật zoom — hợp hook), `slide_left`, `slide_right`, `slide_up`, `slide_down`,
`wipe_right`, `wipe_down`, `whip_pan` (quét nhanh), `page_flip` (lật trang — hợp kể chuyện sách),
`droplet` (giọt nước lan). Gợi ý: chuyển chủ đề→`fade_black`; kể tiếp→`crossfade`; cao trào→`zoom_punch`/`whip_pan`.

## Whitelist `recommended_bgm` (14 mã)

`afro_pop`, `black_light_all_good_folks_main`, `comedy_cartoon`, `deep_abstract_ambient`,
`fluffy_clouds_fugu_vibes_main_version`, `hype_drill`, `lofi_jazzy_love`, `moment_of_peace`,
`music_promotion`, `new_age_nature`, `no_sleep_hiphop`, `rap_beat`, `running_night`, `type_beat`.
Gợi ý: kể chuyện sâu lắng→`deep_abstract_ambient`/`moment_of_peace`; drill/phonk viral→`hype_drill`/`no_sleep_hiphop`; chill→`lofi_jazzy_love`.

## Tone kịch bản (`narration_tone`)

`viral` (hook giật gân), `storytelling` (kể chuyện trầm, cliffhanger), `educational`,
`emotional`, `humorous`. Storytelling hợp review sách/phim + video stock + 240s/300s.

## Thời lượng (`target_duration` → số cảnh gợi ý)

`15s`→4, `30s`→5, `60s`→7, `90s`→9, `120s`→12, `180s`→16, `240s`→18, `300s`→20 (tối đa 20).

## Mode app

`storyteller` (chủ đề → kịch bản), `script_video` (paste script → chia cảnh),
`quiz_listicle` (Top N/Q&A), `photo_narration` / `photo_slideshow` (upload ảnh), `manual`.
