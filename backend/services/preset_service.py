import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any

from config import BASE_DIR, PRESETS_FILE  # noqa: F401  (BASE_DIR giữ cho code cũ)

# ─────────────────────────────────────────────────────────────────────
# Preset MẪU CHUẨN — chỉnh theo 6 khung niche của skill content-cinematic
# (references/content-frameworks.md). Mỗi preset khớp palette riêng của niche:
# voice + nhịp + BGM + subtitle + color + hook_effect + prefer_stock_video.
# ─────────────────────────────────────────────────────────────────────
DEFAULT_PRESETS = [
    {
        "id": "preset_book_storytelling",
        "content_niche": "book",
        "name": "📚 Kể Chuyện Sách (Carousel + Video thật)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_male_podcast_vi",
        "art_style": "Cinematic realistic documentary footage, moody warm lighting",
        "bgm_track": "deep_abstract_ambient",
        "target_duration": "240s",
        "narration_tone": "storytelling",
        "speech_rate": "-5%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 18,
        "subtitle_style": "cinematic_box",
        "color_grading": "warm_cinematic",
        "prefer_stock_video": True,
        "hook_effect": "carousel_quote",
        "use_sfx": False,
        "sfx_volume": 9.6,
        "use_ken_burns": True,
        "hook_zoom_boost": False,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_finance",
        "content_niche": "finance",
        "name": "💰 Tài Chính/Làm Giàu (Số liệu, dồn dập)",
        "aspect_ratio": "9:16",
        "voice": "vi-VN-NamMinhNeural",
        "art_style": "Photorealistic, cinematic lighting, business documentary",
        "bgm_track": "type_beat",
        "target_duration": "60s",
        "narration_tone": "educational",
        "speech_rate": "+10%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 16,
        "subtitle_style": "karaoke_bold",
        "color_grading": "vivid_pop",
        "prefer_stock_video": True,
        "hook_effect": "word_by_word",
        "use_sfx": True,
        "sfx_volume": 14.4,
        "use_ken_burns": True,
        "hook_zoom_boost": True,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_history",
        "content_niche": "history",
        "name": "🏛️ Lịch Sử/Bí Ẩn (Trầm, hồi hộp)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_male_elderly_vi",
        "art_style": "Photorealistic documentary, ancient, cinematic moody lighting",
        "bgm_track": "deep_abstract_ambient",
        "target_duration": "180s",
        "narration_tone": "storytelling",
        "speech_rate": "-3%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 18,
        "subtitle_style": "cinematic_box",
        "color_grading": "cool_matrix",
        "prefer_stock_video": True,
        "hook_effect": "word_by_word",
        "use_sfx": True,
        "sfx_volume": 12,
        "use_ken_burns": True,
        "hook_zoom_boost": False,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_psychology",
        "content_niche": "psychology",
        "name": "🧠 Tâm Lý/Self-help (Sâu lắng)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_female_whisper_vi",
        "art_style": "Photorealistic, soft natural light, intimate lifestyle",
        "bgm_track": "moment_of_peace",
        "target_duration": "60s",
        "narration_tone": "emotional",
        "speech_rate": "-5%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 16,
        "subtitle_style": "cinematic_box",
        "color_grading": "warm_cinematic",
        "prefer_stock_video": True,
        "hook_effect": "word_by_word",
        "use_sfx": False,
        "sfx_volume": 8,
        "use_ken_burns": True,
        "hook_zoom_boost": False,
        "use_breathing": True,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_truecrime",
        "content_niche": "truecrime",
        "name": "🔪 True Crime/Vụ Án (Căng thẳng)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_male_podcast_vi",
        "art_style": "Photorealistic, dark cinematic, moody night, film noir",
        "bgm_track": "no_sleep_hiphop",
        "target_duration": "90s",
        "narration_tone": "storytelling",
        "speech_rate": "+5%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 17,
        "subtitle_style": "cinematic_box",
        "color_grading": "noir_dramatic",
        "prefer_stock_video": True,
        "hook_effect": "full_shake",
        "use_sfx": True,
        "sfx_volume": 14.4,
        "use_ken_burns": True,
        "hook_zoom_boost": False,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_art_masterpiece",
        "content_niche": "art_masterpiece",
        "name": "🎨 Phân Tích Tranh Kinh Điển (Sơn dầu, Uyn bác)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_male_podcast_vi",
        "art_style": "Oil painting, textured canvas brushstrokes, Renaissance style, chiaroscuro lighting",
        "bgm_track": "moment_of_peace",
        "target_duration": "90s",
        "narration_tone": "storytelling",
        "speech_rate": "0%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 16,
        "subtitle_style": "cinematic_box",
        "color_grading": "warm_cinematic",
        "prefer_stock_video": False,
        "visual_source": "ai_image",
        "hook_effect": "word_by_word",
        "use_sfx": True,
        "sfx_volume": 9.6,
        "use_ken_burns": True,
        "hook_zoom_boost": True,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-29T00:00:00"
    },
    {
        "id": "preset_poetry_literature",
        "content_niche": "poetry_literature",
        "name": "📜 Thơ Ca & Hồn Việt (Thủy mặc, Ngâm thơ)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_female_whisper_vi",
        "art_style": "Traditional Asian ink wash painting, Shan Shui watercolor, misty paper texture",
        "bgm_track": "moment_of_peace",
        "target_duration": "60s",
        "narration_tone": "emotional",
        "speech_rate": "-10%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 15,
        "subtitle_style": "cinematic_box",
        "color_grading": "warm_cinematic",
        "prefer_stock_video": False,
        "visual_source": "ai_image",
        "hook_effect": "typewriter_quote",
        "use_sfx": False,
        "sfx_volume": 8,
        "use_ken_burns": True,
        "hook_zoom_boost": False,
        "use_breathing": True,
        "is_default": True,
        "created_at": "2026-07-29T00:00:00"
    },
    {
        "id": "preset_architecture_wonders",
        "content_niche": "architecture_wonders",
        "name": "🏛️ Công Trình & Kỳ Quan (Kiến trúc, Hùng vĩ)",
        "aspect_ratio": "9:16",
        "voice": "omnivoice_male_middle_aged_low_vi",
        "art_style": "Architectural render, cinematic wide angle, dramatic twilight lighting, 8k detail",
        "bgm_track": "deep_abstract_ambient",
        "target_duration": "120s",
        "narration_tone": "educational",
        "speech_rate": "+0%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 18,
        "subtitle_style": "karaoke_bold",
        "color_grading": "vivid_pop",
        "prefer_stock_video": True,
        "hook_effect": "word_by_word",
        "use_sfx": True,
        "sfx_volume": 12.8,
        "use_ken_burns": True,
        "hook_zoom_boost": True,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-29T00:00:00"
    },
    {
        "id": "preset_travel",
        "content_niche": "travel",
        "name": "🌍 Du Lịch/Khám Phá (Rực rỡ)",
        "aspect_ratio": "9:16",
        "voice": "vi-VN-HoaiMyNeural",
        "art_style": "Photorealistic, vibrant travel cinematography, golden hour",
        "bgm_track": "new_age_nature",
        "target_duration": "30s",
        "narration_tone": "viral",
        "speech_rate": "+0%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 20,
        "subtitle_style": "minimal_white",
        "color_grading": "vivid_pop",
        "prefer_stock_video": True,
        "hook_effect": "word_by_word",
        "use_sfx": True,
        "sfx_volume": 12,
        "use_ken_burns": True,
        "hook_zoom_boost": False,
        "use_breathing": False,
        "use_beat_sync": True,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_viral_short",
        "content_niche": "",
        "name": "🔥 Short Viral Nhanh (Anime + Nam Minh)",
        "aspect_ratio": "9:16",
        "voice": "vi-VN-NamMinhNeural",
        "art_style": "Anime illustration, vibrant colors, Studio Ghibli inspired",
        "bgm_track": "auto",
        "target_duration": "30s",
        "narration_tone": "viral",
        "speech_rate": "+0%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 15,
        "subtitle_style": "karaoke_bold",
        "color_grading": "vivid_pop",
        "prefer_stock_video": False,
        "hook_effect": "word_by_word",
        "use_sfx": True,
        "sfx_volume": 12,
        "use_ken_burns": True,
        "hook_zoom_boost": True,
        "use_breathing": False,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    },
    {
        "id": "preset_import_json",
        "content_niche": "",
        "name": "🤖 Kịch Bản AI (Chuyên dụng Import JSON)",
        "aspect_ratio": "9:16",
        "voice": "vi-VN-NamMinhNeural",
        "art_style": "Anime illustration, vibrant colors, Studio Ghibli inspired",
        "bgm_track": "auto",
        "target_duration": "60s",
        "narration_tone": "storytelling",
        "speech_rate": "+0%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 15,
        "subtitle_style": "karaoke_bold",
        "color_grading": "none",
        "prefer_stock_video": False,
        "hook_effect": "word_by_word",
        "use_sfx": False,
        "sfx_volume": 12,
        "use_ken_burns": False,
        "hook_zoom_boost": False,
        "use_breathing": True,
        "use_frame_chaining": True,
        "use_beat_sync": True,
        "is_default": True,
        "created_at": "2026-07-25T00:00:00"
    }
]

# Bổ sung tường minh các toggle hiệu ứng còn thiếu cho MỌI preset default —
# tránh preset "kế thừa ngầm" trạng thái UI cũ khi user chuyển preset.
for _p in DEFAULT_PRESETS:
    _p.setdefault("use_veo", False)              # Veo cần billing — mặc định tắt
    _p.setdefault("use_frame_chaining", True)
    _p.setdefault("use_beat_sync", False)
    _p.setdefault("use_ken_burns", True)
    _p.setdefault("hook_zoom_boost", False)
    _p.setdefault("use_breathing", False)
    # "mixed" đề xuất xen kẽ thông minh video thật và ảnh AI theo cảm xúc/nhịp cảnh.
    _p.setdefault("visual_source", "mixed")
    _p.setdefault("use_single_pass_narration", False)
    _p.setdefault("hook_reel_sfx", "tick_wood")
    # Thang % (100 = 100%), khớp PresetRequest.hook_sfx_volume — đổi sang hệ số chỉ diễn
    # ra ở payload render. Đặt tường minh để chuyển sang preset dựng sẵn thì mức âm lượng
    # Hook SFX cũng trở về chuẩn, thay vì giữ lại con số user vừa kéo cho preset trước.
    _p.setdefault("hook_sfx_volume", 100)


def load_presets() -> List[Dict[str, Any]]:
    """Đọc danh sách presets. Preset MẶC ĐỊNH luôn ĐỒNG BỘ từ code (add/update/remove theo
    DEFAULT_PRESETS), preset do USER tự lưu được giữ nguyên. Nhờ vậy mọi tinh chỉnh preset
    trong code tự động lan tới file đã seed từ trước."""
    if not os.path.exists(PRESETS_FILE):
        save_all_presets(DEFAULT_PRESETS)
        return list(DEFAULT_PRESETS)
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            presets = json.load(f)
        if not isinstance(presets, list):
            return list(DEFAULT_PRESETS)
        # Giữ preset user (không phải default); default lấy nguyên từ code (nguồn chân lý)
        user_presets = [p for p in presets if not p.get("is_default", False)]
        synced = list(DEFAULT_PRESETS) + user_presets
        if synced != presets:
            save_all_presets(synced)
        return synced
    except Exception:
        return list(DEFAULT_PRESETS)

def save_all_presets(presets: List[Dict[str, Any]]):
    """Ghi danh sách presets ra file JSON."""
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)

def add_preset(data: Dict[str, Any]) -> Dict[str, Any]:
    """Thêm 1 preset mới."""
    presets = load_presets()
    preset_id = f"preset_{uuid.uuid4().hex[:8]}"
    data["id"] = preset_id
    data["is_default"] = False
    data["created_at"] = datetime.now().isoformat()
    presets.append(data)
    save_all_presets(presets)
    return data

def delete_preset(preset_id: str) -> bool:
    """Xóa 1 preset theo ID (chỉ xóa preset do user tạo, không xóa preset mặc định)."""
    presets = load_presets()
    filtered = [p for p in presets if p.get("id") != preset_id or p.get("is_default", False)]
    if len(filtered) < len(presets):
        save_all_presets(filtered)
        return True
    return False
