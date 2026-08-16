# KIẾN TRÚC & CƠ CHẾ HOẠT ĐỘNG: AI VIDEO STUDIO (v2.3+)

> **Nguồn sự thật duy nhất** cho mọi lần nâng cấp, debug, và thay đổi luồng hoạt động.
> Cập nhật: **2026-08-13**

---

## 1. Tổng quan Hệ thống

**AI-VIDEO-MAKER** là hệ thống Client-Server tự động hoá sản xuất video ngắn (TikTok, YouTube Shorts, Reels) bằng AI.

| Thành phần | Công nghệ | Cổng |
|---|---|---|
| Frontend UI | React + Vite + TailwindCSS + Zustand | 3001 |
| Backend API | FastAPI + Python 3.11+ | 8000 |
| Render Engine | MoviePy v2 + FFmpeg (NVENC) | subprocess |

**5 chế độ tạo video:**

| Mode | Đầu vào | Đặc điểm |
|---|---|---|
| `storyteller` | Chủ đề (topic) | Gemini viết kịch bản → AI sinh ảnh → TTS → render |
| `script_video` | Script tự nhập | Gemini chia cảnh → AI sinh ảnh → TTS → render |
| `photo_narration` | Ảnh upload | Gemini multimodal phân tích ảnh → viết narration → render |
| `photo_slideshow` | Ảnh upload | Slideshow cinematic + BGM (không TTS) |
| `quiz_listicle` | Chủ đề | Gemini viết dạng Top N / Q&A → render |

---

## 2. Luồng xử lý cốt lõi (Pipeline)

```
User Input → Gemini (kịch bản) → TTS + AI Image/Video
                                              ↓
                                       FFmpeg Render
                                       (MoviePy + NVENC)
                                              ↓
                                          MP4 Final
```

### Bước 1: Sinh Kịch bản — `POST /api/generate-script`
- `gemini_service.generate_script()` gọi **Gemini 2.5 Flash/Pro** với **Structured Outputs** (Pydantic Schema)
- Trả về JSON chuẩn gồm: `scenes[]`, `sentiment`, `hook_text`, `review` (AI Script Reviewer)
- AI Script Reviewer tự chấm điểm kịch bản; nếu dưới 60/100 → tự viết lại 1 lượt

### Bước 2: Tạo TTS — `tts_service.synthesize_speech()`
- **OmniVoice V3.3** (GPU, zero-shot cloning) — engine chính
- **Edge-TTS** với `boundary="WordBoundary"` — fallback L1 (bắt buộc với edge-tts ≥7.x)
- **gTTS** — fallback L2
- **Offline TTS** — fallback L3
- **Forced Alignment**: stable-ts/whisper tìm word boundaries chính xác cho phụ đề karaoke
- **Voice Cloning**: upload mẫu 5–10s → whisper transcript → kiểm tra độ khớp → đăng ký giọng

### Bước 3: Sinh Hình ảnh — `image_router.generate_image_with_fallback()`
Router 4 tầng (ưu tiên → fallback):

1. **Veo 3.1** — nếu `use_veo=True` và API key có billing
2. **Pexels / Pixabay Stock Video** — nếu `prefer_stock_video=True`
3. **Google Imagen 3** — sinh ảnh AI chất lượng cao
4. **Pollinations AI** — fallback siêu tốc
5. **Gradient offline** — dự phòng cuối cùng

### Bước 4: Render Video — `video_service.render_final_video()`

| Thành phần | Công nghệ |
|---|---|
| Ghép clip | MoviePy v2.x (`CompositeVideoClip`, `concatenate_videoclips`) |
| Ken Burns | FFmpeg zoom từng ảnh thành clip `.mp4` |
| Chuyển cảnh | FFmpeg xfade (14 kiểu: crossfade, slide, whip_pan, page_flip...) |
| Beat Sync | librosa phát hiện onset → snap điểm cắt cảnh |
| Phụ đề | ASS file + FFmpeg burn-in (karaoke, cinematic_box, subtitle styles) |
| Audio Mix | FFmpeg: auto-ducking, EQ, loudnorm -14 LUFS, limiter |
| GPU Encode | FFmpeg NVENC (`h264_nvenc`) |

**Render Worker**: chạy trong `multiprocessing.Process` riêng, không block FastAPI event loop.

---

## 3. Cấu trúc thư mục

```
AI-VIDEO-MAKER/
├── ARCHITECTURE.md          ← Nguồn sự thật: kiến trúc + cơ chế
├── ROADMAP.md               ← Nguồn sự thật: trạng thái features + history
├── USER_GUIDE.md            ← Hướng dẫn sử dụng cho người dùng cuối
│
├── backend/
│   ├── main.py              ← Entry point, tất cả API endpoints
│   ├── config.py            ← Nguồn Sự Thật DUY NHẤT cho đường dẫn file
│   ├── requirements.txt
│   │
│   ├── services/
│   │   ├── gemini_service.py      ← Gemini LLM: sinh kịch bản + review
│   │   ├── tts_service.py        ← OmniVoice V3.3 + Edge-TTS + Voice Cloning
│   │   ├── image_router.py       ← Router 4 tầng: Veo → Stock → Imagen → Pollinations
│   │   ├── veo_service.py        ← Veo 3.1 video generation
│   │   ├── video_service.py       ← MoviePy render + ASS subtitles + Hook/Outro
│   │   ├── audio_mix_service.py  ← FFmpeg mastering: ducking, EQ, loudnorm, color grade
│   │   ├── beat_sync.py          ← Librosa onset detection → snap timeline
│   │   ├── motion_effects.py     ← Ken Burns, Timeline, Crossfade duration
│   │   ├── cache_service.py      ← Cache binary media theo hash prompt (V2)
│   │   ├── render_worker.py      ← multiprocessing.Process render
│   │   ├── preset_service.py     ← Quản lý preset JSON
│   │   ├── project_service.py     ← Checkpoint + Smart Resume
│   │   ├── key_manager.py         ← Xoay vòng API keys
│   │   ├── quota_service.py       ← Trạng thái quota API
│   │   ├── log_setup.py          ← UTF-8 log + [job_id] ContextVar
│   │   ├── hook_engine.py        ← Hiệu ứng mở màn: slot-machine, typewriter, blackout...
│   │   ├── ffmpeg_assembler.py   ← FastAssembly bằng FFmpeg (thay MoviePy)
│   │   ├── scene_balancer.py     ← Cân lại nhịp cảnh cho đều
│   │   ├── script_resplit.py     ← Chia lại cảnh từ script user
│   │   ├── duration_model.py     ← Ước lượng thời lượng theo tốc độ đọc thật
│   │   └── image_upload_service.py
│   │
│   ├── tests/                ← Pytest contract tests (21 file)
│   ├── logs/                 ← backend.log, render_worker.log (xoay vòng 10MB×5)
│   ├── scripts/
│   │   └── check_imports.py  ← Phát hiện UnboundLocalError do import cục bộ
│   └── assets/
│       ├── bgm/              ← 14 file nhạc nền (đi kèm mã nguồn)
│       ├── sfx/              ← Tiếng động: whoosh, pop, ding, riser, bass_drop...
│       ├── slot_covers/      ← Ảnh bìa cho hook Máy Xèng
│       ├── fonts/            ← Font phụ đề
│       ├── images/           ← Ảnh sinh ra (theo job_id)
│       ├── audio/            ← Giọng đọc sinh ra (theo job_id)
│       ├── output/          ← Video thành phẩm (.mp4 + .ass)
│       ├── cache/            ← Cache binary media (V2, 5GB max)
│       ├── projects/         ← State dự án để Smart Resume
│       ├── uploads/          ← Ảnh user upload
│       ├── overrides/         ← Hình/video user ghi đè per-scene
│       └── voices_preview/   ← File mẫu giọng clone
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx           ← Router chính (step: config→editor→rendering)
│   │   ├── store.js           ← Zustand store (job, scenes, config)
│   │   ├── constants.js       ← MODES, STYLES, VOICES, TONES, DURATIONS, TRANSITIONS, SFX
│   │   └── components/
│   │       ├── ModeSelector.jsx     ← Chọn 5 mode
│   │       ├── InputSection.jsx     ← Nhập topic / upload ảnh
│   │       ├── ConfigSection.jsx    ← Style, voice, duration, content niche
│   │       ├── SettingsPanel.jsx    ← API key, watermark, auto-fill hook
│   │       ├── AdvancedSettings.jsx ← Veo, Ken Burns, Beat Sync, stock video, hook/outro
│   │       ├── PresetManager.jsx    ← Save/load/delete preset
│   │       ├── QuotaBar.jsx         ← Thanh trạng thái quota API
│   │       ├── ScriptEditor.jsx    ← Xem/sửa kịch bản, per-scene controls, cache probe
│   │       └── RenderProgress.jsx   ← WebSocket progress + download
│   └── vite.config.js
│
├── start.bat              ← Khởi trực tiếp (uvicorn + npm)
├── start-pm2.bat        ← PM2 autorestart (khuyến nghị)
├── stop.bat              ← Tắt process
├── setup-pm2-autostart.bat ← Scheduled Task tự chạy khi boot
└── ecosystem.config.js   ← PM2 config (Backend + Frontend)
```

---

## 4. Kiến trúc đường dẫn (`config.py`)

Hai gốc thư mục, **KHÔNG phải một**:

| Biến | Nội dung | Di dời được? |
|---|---|---|
| `BUNDLED_ASSETS_DIR` (= `backend/assets`) | Nhạc nền, tiếng động, font — đi kèm mã nguồn | Không |
| `DATA_DIR` (= `backend/assets` mặc định) | Ảnh, video, cache, projects, uploads | Có — đặt `CUSTOM_ASSETS_DIR` trong `.env` |

Đổi `CUSTOM_ASSETS_DIR` → restart backend (biến môi trường chỉ đọc lúc startup).

---

## 5. Logging & Diagnostics

- **File log**: `backend/logs/backend.log` (FastAPI) + `backend/logs/render_worker.log` (render)
- **Xoay vòng**: 10MB × 5 file — tránh đầy ổ đĩa
- **Encoding**: UTF-8 ( không phải cp1252 — cp1252 làm vỡ mọi dòng log tiếng Việt)
- **Nhãn `[job_id]`**: gắn vào mọi dòng log qua `ContextVar` + `logging.Filter`, kể cả log từ thư viện bên thứ ba (`httpx`, `google_genai`)

---

## 6. Cổng chất lượng (4 lớp)

| Lớp | Bắt được | Chạy khi |
|---|---|---|
| `compileall` | Lỗi cú pháp | `start.bat`, `start-pm2.bat` |
| `ruff --select F821,F811,E9` | Tên chưa import, định nghĩa trùng | commit hook |
| `scripts/check_imports.py` | `UnboundLocalError` do import cục bộ | `start.bat` |
| `pytest tests/` | Sai hành vi (hợp đồng model ↔ kwargs) | commit hook |

Loại test quan trọng nhất: **test hợp đồng** — đối chiếu tập field giữa model và kwargs thật, phát hiện field bị quên thêm vào `render_kwargs` (triệu chứng: kéo thanh trượt mà không thấy gì thay đổi).

---

## 7. Các tính năng nâng cao

### 7.1. OmniVoice V3.3 & Prosody Engine
- Zero-shot voice cloning từ mẫu 5–10s
- Prosody Engine điều chỉnh micro-prosody theo emotion mỗi cảnh
- Forced Alignment (stable-ts/whisper) cho karaoke word-level chính xác
- Kho giọng custom (`omnivoice_custom_*`)

### 7.2. AI Script Reviewer (B2)
- Gemini chấm kịch bản tự động sau khi sinh
- Điểm < 60/100 → tự viết lại 1 lượt, chỉ nhận nếu điểm cao hơn
- UI hiển thị badge review + hook check

### 7.3. A/B Hook Selector (B3)
- Chọn variant hook thay thế trực tiếp trên UI

### 7.4. Pattern Interrupt Engine (B4)
- Flash trắng ngắn chèn giữa cảnh để giữ chú ý người xem

### 7.5. Dynamic BGM Volume Envelope (B5)
- Gemini parse `bgm_volume` cho từng cảnh
- FFmpeg áp `volume='if(lte(t,N1),v1,if(lte(t,N2),v2,...))'` expression

### 7.6. Hiệu ứng Hook & Outro
- **Hook**: Máy Xèng (slot-machine), Đánh máy, Màn đen, Vignette thở, Chụp ảnh, Nhiễu số, Cháy phim
- **Outro**: CTA card, fade, swipe

### 7.7. Beat Sync
- `librosa.onset.onset_strength()` phát hiện nhịp
- `snap_cut_points_to_beats()` snap điểm cắt cảnh về beat gần nhất (max shift 0.35s)

### 7.8. Smart Resume Checkpoints
- Lưu project state sau mỗi cảnh → render lỗi không mất quota API

---

## 8. Bảo mật & CORS

- **CORS mặc định**: whitelist `localhost:3001` + `localhost:5173` — không còn `*`
- Thêm origin khác qua `ALLOWED_ORIGINS` trong `.env`
- **API Keys**: che 4 ký tự đầu + 4 cuối khi hiển thị mặc định; reveal nguyên văn chỉ khi user chủ động bấm "Hiện Key"

---

## 9. Environment Variables

| Biến | Ý nghĩa |
|---|---|
| `GEMINI_API_KEY` | Key Gemini chính |
| `GEMINI_API_KEY_1..N` | Key dự phòng (xoay vòng khi 429) |
| `PEXELS_API_KEY` | Stock video (bắt buộc để dùng footage thật) |
| `PIXABAY_API_KEY` | Stock video thứ hai (tuỳ chọn) |
| `OMNIVOICE_PATH` | Thư mục cài OmniVoice (mặc định `C:\dev\OmniVoice`) |
| `OMNIVOICE_WARMUP` | `0` để tắt warmup lúc startup |
| `ALLOWED_ORIGINS` | Danh sách CORS origin (phân cách bằng dấu phẩy) |
| `CUSTOM_ASSETS_DIR` | Di dời DATA_DIR sang ổ khác |

---

## 10. Debugging & Khắc phục sự cố

### Backend không khởi động
```bash
cd backend
venv\Scripts\activate
python -c "import main; print('OK')"
```

### Render treo / job đứng ở "pending"
```bash
pm2 logs AI-Backend --lines 50
# Xem backend/logs/render_worker.log
```

### Ảnh AI toàn stock / không sinh ảnh
- Kiểm tra `GEMINI_API_KEY` có quota còn không
- Veo 3.1 cần billing bật → luôn fallback; không phải lỗi

### Phụ đề lệch
- Đảm bảo dùng `boundary="WordBoundary"` với edge-tts ≥7.x
- Dùng `asset["start_time"]` (đã trừ crossfade), không cộng dồn cursor

### Tiếng riser/SFX không phát
- Toggle `use_sfx` global chỉ ảnh hưởng auto-riser cảnh 1; SFX per-scene luôn phát

---

*File này cập nhật tự động khi code thay đổi. ROADMAP.md ghi lịch sử thay đổi theo ngày.*
