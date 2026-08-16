# 🗺️ AI-VIDEO-MAKER — Lộ trình Nâng cấp & Bản đồ Kiến trúc

> **Mục đích file này:** Đây là tài liệu tham chiếu duy nhất cho mọi lần update sau. AI/Dev chỉ cần đọc file này để biết cần sửa file nào, ở đâu, làm gì — **không cần đọc lại toàn bộ codebase**.
>
> Cập nhật lần cuối: **2026-08-13**

---

## 1. BẢN ĐỒ KIẾN TRÚC (Architecture Map)

```
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND (Vite + React + TailwindCSS)                       │
│  frontend/src/                                               │
│  ├── App.jsx ─────── Router chính                            │
│  ├── AppContext.jsx ─ State management (job, scenes, config) │
│  ├── constants.js ── MODES, STYLES, VOICES, TONES, DURATIONS│
│  └── components/                                             │
│       ├── InputSection.jsx ── Nhập chủ đề / upload ảnh       │
│       ├── ConfigSection.jsx ─ Chọn style, voice, duration    │
│       ├── ScriptEditor.jsx ── Xem/sửa kịch bản AI sinh ra   │
│       ├── AdvancedSettings.jsx ── Veo, Ken Burns, Beat Sync  │
│       ├── SettingsPanel.jsx ── API key, watermark             │
│       ├── ModeSelector.jsx ── Chọn 5 mode                    │
│       └── RenderProgress.jsx ── WebSocket progress bar       │
└──────────────────────────────────────────────────────────────┘
          │ HTTP POST + WebSocket
          ▼
┌──────────────────────────────────────────────────────────────┐
│  BACKEND (FastAPI + Python)                                  │
│  backend/                                                    │
│  ├── main.py ─────────── API endpoints + Pipeline chạy nền   │
│  │   ├── GenerateScriptRequest  (POST /api/generate-script)  │
│  │   ├── RenderVideoRequest     (POST /api/render)           │
│  │   └── _run_render_pipeline() ← PIPELINE CHÍNH             │
│  └── services/                                               │
│       ├── gemini_service.py ── Gemini LLM: sinh kịch bản     │
│       ├── image_router.py ─── Router ảnh: Imagen → Pollinations│
│       ├── veo_service.py ──── Veo 3.1: sinh video AI         │
│       ├── tts_service.py ──── Edge TTS: giọng đọc tiếng Việt │
│       ├── video_service.py ── MoviePy: render + phụ đề .ass  │
│       ├── motion_effects.py ─ Ken Burns + Timeline sync      │
│       ├── audio_mix_service.py ─ FFmpeg: BGM + mastering     │
│       ├── beat_sync.py ────── Librosa: đồng bộ nhịp nhạc     │
│       ├── key_manager.py ──── Xoay vòng API key              │
│       ├── cache_service.py ── Cache JSON + Binary Media V2   │
│       ├── render_worker.py ── Offload render ra process con  │
│       ├── preset_service.py ─ Quản lý Preset/Template JSON   │
│       └── image_upload_service.py ── Xử lý ảnh upload        │
└──────────────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────┐
│  ASSETS (backend/assets/)                                    │
│  ├── sfx/     ── 22+ file: whoosh, pop, ding, riser, bell, bell_chime, shimmer, tick, suspense, heartbeat, heartbeat_dramatic, breath, bass_drop, impact, ambient_mystic, cinematic_swell, swoosh_soft… │
│  ├── bgm/     ── 14 file nhạc nền (.mp3)                    │
│  ├── presets.json ── File lưu các preset cấu hình tùy chỉnh  │
│  ├── output/  ── Video final (.mp4 + .ass)                   │
│  ├── veo_tmp/ ── Clip Veo tạm                                │
│  ├── cache/media/ ── Cache binary ảnh/video theo hash prompt │
│  └── render_status/ ── File JSON trạng thái render worker    │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. CHỈ MỤC FILE (Quick Reference)

> Mốc là **TÊN HÀM/HẰNG** (bền hơn số dòng — số dòng dễ lệch sau mỗi lần sửa). Dùng Grep tên hàm để nhảy tới.

| Khi cần sửa... | Mở file | Anchor (tên hàm/hằng) |
|---|---|---|
| Thêm mode mới | `main.py` | `VALID_MODES` |
| Sửa request schema render | `main.py` | `class RenderVideoRequest` |
| Sửa pipeline render (điều phối) | `main.py` | `_run_render_pipeline()` |
| Sửa chọn nguồn hình mỗi cảnh (Veo/Pexels video/ảnh AI) | `main.py` | `_do_visuals()` bên trong `_run_render_pipeline` |
| Sửa Hook Zoom Boost / auto riser | `main.py` | vòng lặp `apply_ken_burns` (biến `kb_zoom_end`, `scene_sfx`) |
| Voice cloning (upload mẫu giọng) | `main.py` | `create_voice_clone()`, `delete_voice_clone()` |
| Trạng thái/warmup TTS | `main.py` | `tts_health()`, `_startup_warmup()` |
| Sửa prompt AI / kịch bản | `gemini_service.py` | `base_storyteller` (viral), `BASE_STORYTELLING` (kể chuyện) |
| Thêm/sửa tone kể chuyện | `gemini_service.py` | `NARRATION_TONE_PROMPTS` |
| Thêm/sửa thời lượng ↔ số cảnh | `gemini_service.py` | `DURATION_CONFIG` |
| Sửa schema Scene (thêm field AI sinh) | `gemini_service.py` | `class Scene`, `class ScriptResponse` |
| Sửa keyword tìm footage Pexels | `gemini_service.py` | `extract_search_keyword()` |
| Sửa router sinh ảnh (4 tầng) | `image_router.py` | `generate_image_with_fallback()` |
| Sửa tải video stock Pexels | `image_router.py` | `fetch_pexels_video()` (⚠️ BẮT BUỘC User-Agent) |
| Thêm/sửa transition (slide/page_flip/droplet…) | `video_service.py` | `_apply_transition()`, `VALID_TRANSITIONS` |
| Sửa phụ đề / subtitle style | `video_service.py` | `generate_ass_file()` (dùng `start_time`, KHÔNG cộng dồn) |
| Sửa Ken Burns / timeline | `motion_effects.py` | `apply_ken_burns()`, `build_scene_timeline()` |
| Sửa BGM mixing / mastering / color grade | `audio_mix_service.py` | `master_audio_and_export()`, `COLOR_GRADING_FILTERS` |
| Sửa Prosody Engine / OmniVoice / emotion tempo | `tts_service.py` | `_synthesize_with_prosody()`, `_synthesize_omnivoice()`, `EMOTION_TEMPO_DELTA` |
| Sửa TTS cache | `tts_service.py` | `synthesize_speech()` (đầu hàm: check cache; cuối: `set_media`) |
| Registry giọng clone | `tts_service.py` | `register_custom_voice()`, `_load_custom_voices()` |
| Sửa preset mặc định | `preset_service.py` | `DEFAULT_PRESETS` (có migration merge theo `id`) |
| Sửa Veo video gen | `veo_service.py` | `generate_scene_video()` (⚠️ cần billing) |
| Thêm style/voice/tone/duration/transition/sfx FE | `constants.js` | `STYLES`, `VOICES`, `NARRATION_TONES`, `DURATION_OPTIONS`, `TRANSITIONS`, `SFX_OPTIONS` |
| Điều khiển per-scene (chuyển cảnh/SFX từng ảnh) | `ScriptEditor.jsx` | dropdown trong `.map(scene)` |
| Toggle nâng cao (Veo/Ken Burns/Hook/stock video…) | `AdvancedSettings.jsx` | `<ToggleRow>` |
| Auto-điền hook_text AI sinh | `SettingsPanel.jsx` | sau `setScenes(data.scenes)` |
| Áp preset ↔ state | `AppContext.jsx` | `applyPreset()` |

---

## 2.5. QUY ƯỚC & CẠM BẪY (đọc trước khi sửa — tránh vấp lại lỗi cũ)

**Biến môi trường (`backend/.env`):**
| Biến | Ý nghĩa |
|---|---|
| `GEMINI_API_KEY`, `GEMINI_API_KEY_1..N` | Key Gemini (xoay vòng tự động khi 429) |
| `PEXELS_API_KEY` | Bắt buộc để có ảnh/video stock thật |
| `PIXABAY_API_KEY` | Tuỳ chọn (key miễn phí ở pixabay.com/api/docs). Nhà cung cấp stock THỨ HAI: khi Pexels hụt clip cho một từ khoá, có key này thì vẫn giữ được footage thật thay vì âm thầm đổi cảnh đó sang ảnh AI tĩnh |
| `OMNIVOICE_PATH` | Thư mục cài OmniVoice (mặc định `C:\dev\OmniVoice`) |
| `OMNIVOICE_WARMUP` | `0` để tắt warmup model lúc khởi động |
| `ALLOWED_ORIGINS` | CORS. **Mặc định KHÔNG phải `*`** mà là danh sách trắng localhost:3001/5173 (xem `main.DEFAULT_LOCAL_ORIGINS`). Đặt `*` là bất kỳ trang web nào đang mở trong trình duyệt cũng đọc được `GET /api/api-keys-config` — tức lấy được toàn bộ API key. Chỉ mở thêm origin cụ thể khi cần vào từ máy khác trong LAN |

**API endpoints mới thêm gần đây:** `GET /api/tts-health`, `POST /api/voice-clone`, `DELETE /api/voice-clone/{id}`, `GET /api/quota`, `GET/POST/DELETE /api/presets`.

**Cạm bẫy đã từng dính (ĐỪNG lặp lại):**
- **Pexels API trả 403 nếu THIẾU `User-Agent`** → footage stock không bao giờ xuất hiện. Mọi request Pexels phải kèm User-Agent trình duyệt.
- **Từ khoá tìm footage phải lấy từ CUỐI cụm danh từ, không phải đầu.** Tiếng Anh đặt danh từ chính ở cuối, nên "lấy 3 từ đầu" làm mất chủ thể: `"a vintage closed leather book lying on a table"` → `"vintage closed leather"`, và Pexels trả về ảnh đồ da/thời trang thay vì sách. Xem `stock_query_from_prompt()` + `tests/test_stock_sourcing.py`.
- **ĐỪNG suy ra nguồn hình từ `art_style`.** Đã dính hai lần: (1) dò "photorealistic" trong `image_prompt` do Gemini sinh — mà base prompt bắt buộc chèn chuỗi đó nên điều kiện luôn đúng; (2) dò chính chuỗi đó trong `art_style` của user — mà `STYLES[1]` là "Realistic (Thực tế)" = `"Photorealistic, cinematic lighting, 8K UHD"`, nên chọn phong cách này là cả video âm thầm chuyển sang Pexels. `art_style` = "vẽ theo kiểu gì", `visual_source`/`prefer_stock_video` = "lấy hình từ đâu". Xem `main._pick_visual_source` + `tests/test_visual_source_routing.py`.
- **Dự phòng cho ẢNH AI phải là ảnh AI.** `generate_image_with_fallback` từng đặt Pexels photo trước Pollinations FLUX → hết quota Gemini là trả về ảnh stock tĩnh dù người dùng đang ở chế độ ảnh AI. Thứ tự đúng: Gemini → Pollinations FLUX → Pexels photo → gradient.
- **`config.write_env_value(key, "")` XOÁ dòng, không ghi `KEY=`.** Đừng đổi lại: giao diện Quản lý Key API dùng chính cơ chế đó để dọn slot key dự phòng cũ.
- **Mọi nhánh sinh hình phải ghi `source_meta["source"]`.** Không ghi thì hiện tượng "hết quota ảnh Gemini nên cả video âm thầm thành ảnh stock tĩnh" là hoàn toàn vô hình — video vẫn render xong. Xem `_summarize_visual_sources()`.
- **edge-tts ≥7.x mặc định `SentenceBoundary`** → mất word boundaries → phụ đề karaoke chết. Phải truyền `boundary="WordBoundary"`.
- **Phụ đề phải dùng `asset["start_time"]`** (đã tính overlap crossfade), KHÔNG cộng dồn `cursor += duration` (lệch tiếng dần).
- **KHÔNG trả script mock khi Gemini lỗi** — phải `raise` để UI báo lỗi thật.
- **Cache key phải dùng `hashlib.md5`**, KHÔNG dùng `hash()` builtin (đổi mỗi lần chạy).
- **Đường dẫn asset phải tuyệt đối** theo `__file__`, KHÔNG dùng path tương đối (phụ thuộc CWD/pm2).
- **`subprocess.run` FFmpeg phải có `timeout=`** (tránh treo vô hạn).
- **Transition "fancy" phải bọc `try/except` fallback crossfade** — không để hiệu ứng lạ làm hỏng render.
- **KHÔNG dùng `CompositeAudioClip` để trộn SFX ngắn** (MoviePy 2.1.2 bug: `frame_function` đọc clip vượt cửa sổ khi t là mảng → crash với file <1s như tick.wav). Trộn audio bằng numpy trong `_mix_audio_tracks` (đọc `soundfile`, resample `librosa`). `AudioFileClip.to_soundarray` cũng đọc buffer 50000 mẫu vượt file ngắn → tránh cho SFX ngắn.
- **SFX per-scene phải LUÔN phát** (không gate bởi `use_sfx` global). Transition per-scene: `scene[i].transition` = biên i→i+1 (dùng transition cảnh TRƯỚC cho lối vào cảnh sau).
- **Placement tuple Literary Mode 8-phần tử**: `_mix_audio_tracks` nhận tuple 8 giá trị `(path, start, volume, fadeout, max_dur, pitch_ratio, fade_in_ms, fade_out_ms)`. 4–6 phần tử vẫn backward-compatible. Fade envelope được áp bằng numpy trong `_mix_audio_tracks`, không phải FFmpeg.
- **Veo cần billing** — key free-tier trả 429 với mọi model Veo. `_do_visuals` tự tắt Veo + báo UI khi gặp 429/403.

**Backtest offline (không cần chạy server):**
```
cd backend
PYTHONPATH=<abs backend> PYTHONIOENCODING=utf-8 venv/Scripts/python.exe <script>.py
```
(`PYTHONIOENCODING=utf-8` bắt buộc — console cp1252 lỗi tiếng Việt). Syntax check: `python -m py_compile main.py services/*.py`.

---

## 3. TRẠNG THÁI CÁC HẠNG MỤC

### ✅ ĐÃ HOÀN THÀNH

| # | Hạng mục | File đã sửa | Ngày |
|---|----------|-------------|------|
| 1 | Fix Veo integration (use_veo bị bỏ qua) | `main.py` L252–265 | 2026-07-19 |
| 2 | Photorealistic Mode (auto-detect + art_style) | `image_router.py`, `main.py` | 2026-07-19 |
| 3 | Hormozi Subtitles (multi-color + Vietnamese stopwords) | `video_service.py` L389–430 | 2026-07-19 |
| 4 | Smart SFX (prompt + schema đồng bộ kho file) | `gemini_service.py` L87–90, L222–226 | 2026-07-19 |
| 5 | Upload ảnh bìa sản phẩm chèn cảnh đầu | `main.py`, `AppContext.jsx`, `InputSection.jsx`, `ScriptEditor.jsx` | 2026-07-19 |
| 6 | Stock footage API (Pexels - 4 Tầng Provider) | `image_router.py`, `main.py`, `gemini_service.py` | 2026-07-21 |
| 7 | Thêm file SFX còn thiếu | `assets/sfx/`, `gemini_service.py` | 2026-07-19 |
| 8 | Template system (save preset) | `main.py`, `services/preset_service.py`, `PresetManager.jsx` | 2026-07-21 |
| 10 | Advanced Beat Sync (HPSS transient detection) | `beat_sync.py` | 2026-07-19 |
| 11 | Subtitle style selector mở rộng | `video_service.py`, `constants.js`, `AdvancedSettings.jsx` | 2026-07-19 |
| 13 | OmniVoice GPU Sentence Chunking & Direct WAV | `tts_service.py`, `main.py` | 2026-07-21 |
| 14 | Sửa dứt điểm Lỗi Mất Giọng OmniVoice (Instruct Whitelist) | `tts_service.py` L423–440 | 2026-07-21 |
| 15 | Lọc 100% Emoji & Icons khỏi TTS (Không bị đọc "Mặt cười", "Lửa") | `tts_service.py` L93–105 | 2026-07-21 |
| 16 | Fast Fallback Pollinations (Thêm User-Agent Chrome 0.5s) | `image_router.py` L55–70 | 2026-07-21 |
| 17 | Tùy chọn Nam - Nam Minh (Giọng Nam Trầm -20Hz) | `constants.js`, `tts_service.py` | 2026-07-21 |
| 18 | Lưu Checkpoint Dự Án & Smart Resume (Không chạy lại khi lỗi) | `services/project_service.py`, `main.py` | 2026-07-21 |
| 19 | Chỉnh sửa & Thay ảnh lẻ riêng cho từng phân cảnh | `main.py`, `ScriptEditor.jsx` | 2026-07-21 |
| 21 | Offload Render Worker (multiprocessing.Process) | `services/render_worker.py`, `main.py` | 2026-07-23 |
| 22 | AI Media Cache V2 (Binary ảnh/video theo hash prompt) | `services/cache_service.py`, `image_router.py`, `veo_service.py` | 2026-07-23 |
| 23 | Emotion Profiles V2 (Kích hoạt pitch_delta ±3-5Hz) | `tts_service.py` L63–71 | 2026-07-23 |
| 24 | OmniVoice Prosody Engine V3.3 (micro-prosody per sentence) | `tts_service.py` L451–560 | 2026-07-23 |
| 25 | Forced Alignment Word Boundaries (stable-ts/whisper) — **đã cài stable-ts thật + singleton model** | `tts_service.py`, `requirements.txt` | 2026-07-24 |
| 26 | Fix Pexels sai chủ đề (keyword extractor lọc thuật ngữ góc máy, lấy chủ thể sau "of") | `gemini_service.py` `extract_search_keyword` | 2026-07-24 |
| 27 | Veo auto-disable + cảnh báo UI khi key chưa bật billing (hết fallback im lặng) | `main.py` `_run_render_pipeline` | 2026-07-24 |
| 28 | OmniVoice Warmup lúc khởi động + `GET /api/tts-health` | `tts_service.py`, `main.py` | 2026-07-24 |
| 29 | Emotion Tempo 6/6 (hook/excited/calm/dramatic/suspense/closing qua atempo, ref identity thuần) + chunk theo ranh giới từ | `tts_service.py` `_synthesize_omnivoice` | 2026-07-24 |
| 20 | Advanced Voice Cloning: `POST /api/voice-clone` (upload mẫu 5-10s, auto-transcribe whisper) + UI upload + registry `voices_custom.json` | `tts_service.py`, `main.py`, `ConfigSection.jsx` | 2026-07-24 |
| 30 | TTS Cache theo hash(text+voice+rate+pitch+emotion+breathing) — render lại không tốn thời gian sinh giọng | `tts_service.py` `synthesize_speech` | 2026-07-24 |
| 31 | Fix mất Word Boundaries với edge-tts ≥7.x (`boundary="WordBoundary"`) — khôi phục phụ đề karaoke nhảy chữ | `tts_service.py` | 2026-07-24 |
| 33 | Transition Engine đa dạng (10 kiểu: +fade_white, slide L/R/Up, whip_pan, page_flip ≈lật trang, droplet ≈giọt nước) — có fallback crossfade khi lỗi | `video_service.py` `_apply_transition` | 2026-07-24 |
| 34 | Điều khiển per-scene: dropdown Chuyển cảnh + Tiếng động (SFX, có "Không tiếng") cho TỪNG cảnh trong ScriptEditor | `ScriptEditor.jsx`, `constants.js` | 2026-07-24 |
| 35 | Wire `hook_zoom_boost` (trước là cờ chết): cảnh 0 zoom mạnh 1.0→1.35 + auto SFX riser mở màn — thành toggle thật | `main.py`, `AdvancedSettings.jsx` | 2026-07-24 |
| 36 | Auto-điền hook_text AI sinh vào ô Hook (trước bị frontend vứt bỏ) | `SettingsPanel.jsx` | 2026-07-24 |
| 37 | **FIX video ra toàn ảnh 100%**: Pexels VIDEO trả 403 do THIẾU User-Agent → luôn rơi về ảnh AI. Thêm User-Agent + chọn resolution hợp lý | `image_router.py` `fetch_pexels_video` | 2026-07-24 |
| 38 | Toggle "Dùng video nền thật (Pexels stock)" — ép video thật cho MỌI cảnh không cần Veo/billing, fallback ảnh AI nếu không có | `main.py`, `AdvancedSettings.jsx`, `AppContext.jsx` | 2026-07-24 |
| 39 | **Tầng A — Bắt kịp style viral kể chuyện sách/phim (@sachhay_chondoc)**: tone `storytelling` + base prompt long-form (cliffhanger, footage thật) + duration 240s/300s | `gemini_service.py`, `constants.js` | 2026-07-24 |
| 40 | Preset "📖 Kể Chuyện Sách/Phim" (16:9 + cinematic_box + warm + OmniVoice trầm + rate -5% + prefer_stock_video) + migration merge preset default mới | `preset_service.py`, `main.py`, `AppContext.jsx`, `PresetManager.jsx` | 2026-07-24 |
| 41 | **FIX transition per-scene off-by-one**: `scene[i].transition` giờ điều khiển đúng biên i→i+1 (trước đây transition cảnh 0 bị bỏ, mỗi lựa chọn lệch 1 cảnh) | `video_service.py` `render_final_video` | 2026-07-25 |
| 42 | **FIX SFX per-scene không phát khi tắt SFX global**: SFX chọn riêng từng cảnh LUÔN phát; toggle global chỉ còn điều khiển auto-riser mở màn | `video_service.py`, `AdvancedSettings.jsx` | 2026-07-25 |
| 43 | Bổ sung transition (14 kiểu): +zoom_punch, slide_down, wipe_right, wipe_down | `video_service.py`, `constants.js` | 2026-07-25 |
| 44 | Bổ sung 5 SFX tổng hợp: swoosh_soft, bass_drop, tick, shimmer, heartbeat (có envelope) | `assets/sfx/`, `constants.js`, `gemini_service.py` (whitelist) | 2026-07-25 |
| 45 | **FIX crash "Accessing time t=... tick.wav"**: MoviePy 2.1.2 CompositeAudioClip đọc SFX ngắn vượt cửa sổ + to_soundarray đọc buffer vượt file ngắn. Refactor sang TRỘN AUDIO BẰNG NUMPY (đọc bằng soundfile, đúng độ dài, resample librosa) | `video_service.py` `_mix_audio_tracks` | 2026-07-25 |
| 46 | **FIX hook carousel_quote không render**: `render_kwargs` thiếu `hook_effect`/`hook_quote` → hàm dựng carousel không nhận → feature chết âm thầm (bìa sách full-screen thay vì slot-machine+quote). Thêm vào cả worker path + inline path | `main.py` | 2026-07-25 |
| 47 | **FIX phụ đề lệch 3.5s khi carousel** + bỏ mutate `asset["start_time"]` (gây double-offset & cộng dồn khi render lại). Offset xác định qua `hook_effect` trong `generate_ass_file` (idempotent) | `video_service.py`, hằng `HOOK_CAROUSEL_DURATION` | 2026-07-25 |
| 48 | **Nâng slot-machine hook**: dùng BÌA THẬT cuộn dọc như trục quay (thay khối màu) + nền blurred-fill bỏ viền đen. Thêm audio hook: tiếng trục quay `reel_spin` + `ding` khi chốt | `hook_engine.py`, `video_service.py` | 2026-07-25 |
| 49 | **Làm dịu SFX** (thô/to): tạo `reel_spin.wav`, làm dịu bass_drop/tick/shimmer/impact (peak 0.9→0.31-0.45, lowpass) + `SFX_MIX_GAIN=0.6` giảm âm lượng SFX chung | `assets/sfx/`, `video_service.py` | 2026-07-25 |
| 50 | **Preset chuẩn theo 6 khung niche của skill** (Sách/Tài chính/Lịch sử/Tâm lý/True Crime/Du lịch) — mỗi preset khớp voice/nhịp/BGM/subtitle/color/hook_effect/stock. Migration ĐỒNG BỘ default từ code (add/update/remove), giữ preset user. applyPreset + PresetRequest nhận `hook_effect` | `preset_service.py`, `main.py`, `AppContext.jsx`, `PresetManager.jsx` | 2026-07-25 |
| 51 | **Hiệu ứng đi kèm theo niche — AI tự chọn**: Scene.transition mở rộng 3→14 kiểu trong schema Gemini + `TONE_EFFECT_PALETTES` (transition/sfx/nhịp theo tone) inject vào prompt. E2E: storytelling ra page_flip/droplet/fade_black + SFX thưa đúng chất | `gemini_service.py` | 2026-07-25 |
| 52 | Skill `scene-blueprints.md`: bản vẽ cảnh-theo-cảnh cho 6 niche (vai trò + emotion/sfx/transition/rate theo VỊ TRÍ) — cấu trúc content chuẩn khớp preset. Preset default bổ sung toggle tường minh (use_veo/frame_chaining/...) | `.agents/skills/content-cinematic/`, `preset_service.py` | 2026-07-25 |
| 53 | **`content_niche` end-to-end**: `NICHE_BLUEPRINTS` backend (6 niche, bản vẽ VỊ TRÍ mini-twist ~45%/cao trào ~80% inject vào prompt, ưu tiên hơn tone palette) + selector "THỂ LOẠI NỘI DUNG" trong ConfigSection + preset tự set niche (preset tiện ích reset về ""). E2E finance: 8/8 cảnh có số, tick/bass_drop/zoom_punch đúng blueprint | `gemini_service.py`, `main.py`, `constants.js`, `AppContext.jsx`, `ConfigSection.jsx`, `SettingsPanel.jsx`, `preset_service.py` | 2026-07-25 |
| 54 | **AI Script Reviewer (B2)**: Trả về đánh giá kịch bản tự động, UI review badge + check hook. | `gemini_service.py`, `main.py`, `ScriptEditor.jsx` | 2026-07-29 |
| 55 | **A/B Hook Selector (B3)**: Chọn hook variant thay thế trực tiếp trên UI. | `ScriptEditor.jsx`, `store.js` | 2026-07-29 |
| 56 | **Pattern Interrupt Engine (B4)**: Toggle vi-mô cắt nhịp (flash trắng ngắn) giữ chú ý. Tránh phá không khí ở tone Story/Emotional. | `audio_mix_service.py`, `video_service.py`, `AdvancedSettings.jsx`, `main.py` | 2026-07-29 |
| 57 | **Dynamic BGM Volume Envelope (B5)**: Parse bgm_volume từ LLM và áp dụng tự động cho từng scene thông qua Ffmpeg expression. | `audio_mix_service.py`, `gemini_service.py`, `main.py` | 2026-07-29 |
| 58 | **Literary Mode SFX — Phase 1 (Quick Fix)**: Tạo `bell_chime.wav`, `heartbeat_dramatic.wav` + sửa gain `heartbeat_dramatic` 1.20→0.95. | `assets/sfx/`, `video_service.py` | 2026-08-13 |
| 59 | **Literary Mode SFX — Phase 2 (Wire Pipeline)**: Wire `get_literary_sfx()`, `adjust_sfx_for_scene_duration()`, `apply_sfx_fade_filter()` vào render pipeline. Thêm `content_niche` vào passthrough fields. | `main.py`, `video_service.py` | 2026-08-13 |
| 60 | **Literary Mode SFX — Phase 3 (RMS Calibration)**: Đo RMS 14 file SFX, về SCENE_SFX_GAIN về RMS-calibrated (-22dB target), gain_boost=1.0 cho tất cả genre. Viết test `test_literary_sfx.py`. | `video_service.py`, `tools/measure_sfx_rms.py`, `tests/test_literary_sfx.py` | 2026-08-13 |

---

### 🟢 ƯU TIÊN 3 — Polish & Scale (Tương lai tiếp tục hoàn thiện)

| # | Hạng mục | File cần sửa | Mô tả ngắn | Trạng thái |
|---|----------|-------------|-------------|------------|
| 9 | Auto-publish TikTok/YouTube | `services/publish_service.py` (file mới) | Tích hợp API đăng video tự động lên kênh TikTok/YouTube Shorts | 🟢 Chờ làm |
| 12 | Batch render (hàng loạt video) | `main.py` (endpoint mới) | Nhập danh sách chủ đề CSV $\rightarrow$ render hàng loạt 50 video tự động | 🟢 Chờ làm |
| 32 | **Phase 2 Veo (TẠM HOÃN — cần bật billing Google)** | `main.py`, `veo_service.py` | Key free-tier KHÔNG có quota Veo (đã xác minh 429 cả 2 key, cả model lite). Khi bật billing: nối `generate_scene_chain` (frame chaining thật), cờ `use_veo_ambient_audio`, giới hạn Veo cho cảnh Hook+Climax để giảm ~60% chi phí | ⏸️ Hoãn |

---

## 4. QUY TẮC KHI UPDATE (Cho AI/Dev lần sau)

1. **Đọc file này TRƯỚC** khi bắt đầu bất kỳ task nào.
2. **Tra bảng Chỉ mục File** (mục 2) để biết cần mở file nào — KHÔNG đọc toàn bộ codebase.
3. **Sau khi hoàn thành**, cập nhật bảng "Trạng thái" (mục 3): chuyển hạng mục từ 🟡/🟢 sang ✅ và ghi ngày.
4. **Nếu phát hiện lỗ hổng mới**, thêm vào bảng tương ứng với mức ưu tiên phù hợp.
5. **Syntax check bắt buộc** sau mỗi lần sửa: `python -m py_compile backend/<file>.py`
6. **Kho SFX hiện có**: `whoosh.wav, pop.wav, ding.wav, riser.wav` — nếu thêm file mới, cập nhật cả prompt trong `gemini_service.py` L87–90 và L222–226.

