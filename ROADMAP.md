# 🗺️ AI-VIDEO-MAKER — Lộ trình Nâng cấp & Bản đồ Kiến trúc

> **Mục đích file này:** Đây là tài liệu tham chiếu duy nhất cho mọi lần update sau. AI/Dev chỉ cần đọc file này để biết cần sửa file nào, ở đâu, làm gì — **không cần đọc lại toàn bộ codebase**.
>
> Cập nhật lần cuối: **2026-07-19**

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
│  ├── sfx/     ── 4 file: whoosh.wav, pop.wav, ding.wav, riser.wav │
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

| Khi cần sửa... | Mở file | Dòng quan trọng |
|----------------|---------|-----------------|
| Thêm mode mới | `main.py` | L155 `VALID_MODES` |
| Sửa request schema | `main.py` | L115–155 |
| Sửa pipeline render | `main.py` | L175–378 `_run_render_pipeline()` |
| Sửa prompt AI / kịch bản | `gemini_service.py` | L81–114 (Schema), L188–226 (Prompt) |
| Sửa cách sinh ảnh | `image_router.py` | L58–102 `generate_image_with_fallback()` |
| Sửa phụ đề / subtitle style | `video_service.py` | L305–430 `generate_ass_file()` |
| Sửa Ken Burns / timeline | `motion_effects.py` | L26–79 (Ken Burns), L131–153 (Timeline) |
| Sửa BGM mixing / mastering | `audio_mix_service.py` | L20–90 |
| Sửa beat sync | `beat_sync.py` | L72–94 |
| Sửa Veo video gen | `veo_service.py` | L123–180 |
| Thêm style/voice/mode FE | `constants.js` | Toàn file (56 dòng) |

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
| 25 | Forced Alignment Word Boundaries (stable-ts/whisper) | `tts_service.py` L500–530 | 2026-07-23 |

---

### 🟢 ƯU TIÊN 3 — Polish & Scale (Tương lai tiếp tục hoàn thiện)

| # | Hạng mục | File cần sửa | Mô tả ngắn | Trạng thái |
|---|----------|-------------|-------------|------------|
| 9 | Auto-publish TikTok/YouTube | `services/publish_service.py` (file mới) | Tích hợp API đăng video tự động lên kênh TikTok/YouTube Shorts | 🟢 Chờ làm |
| 12 | Batch render (hàng loạt video) | `main.py` (endpoint mới) | Nhập danh sách chủ đề CSV $\rightarrow$ render hàng loạt 50 video tự động | 🟢 Chờ làm |
| 20 | Advanced Voice Cloning (Mẫu giọng OmniVoice tùy chỉnh) | `services/tts_service.py` | Upload file mẫu âm thanh 5s $\rightarrow$ clone giọng đọc cá nhân | 🟢 Chờ làm |

---

## 4. QUY TẮC KHI UPDATE (Cho AI/Dev lần sau)

1. **Đọc file này TRƯỚC** khi bắt đầu bất kỳ task nào.
2. **Tra bảng Chỉ mục File** (mục 2) để biết cần mở file nào — KHÔNG đọc toàn bộ codebase.
3. **Sau khi hoàn thành**, cập nhật bảng "Trạng thái" (mục 3): chuyển hạng mục từ 🟡/🟢 sang ✅ và ghi ngày.
4. **Nếu phát hiện lỗ hổng mới**, thêm vào bảng tương ứng với mức ưu tiên phù hợp.
5. **Syntax check bắt buộc** sau mỗi lần sửa: `python -m py_compile backend/<file>.py`
6. **Kho SFX hiện có**: `whoosh.wav, pop.wav, ding.wav, riser.wav` — nếu thêm file mới, cập nhật cả prompt trong `gemini_service.py` L87–90 và L222–226.

