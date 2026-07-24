import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS_FILE = os.path.join(BASE_DIR, "assets", "presets.json")

DEFAULT_PRESETS = [
    {
        "id": "preset_viral_short",
        "name": "🔥 Short TikTok Viral (Nam Minh + Anime)",
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
        "use_sfx": True,
        "sfx_volume": 50,
        "is_default": True,
        "created_at": "2026-07-21T00:00:00"
    },
    {
        "id": "preset_cinematic_story",
        "name": "🎬 Kể Chuyện Cinematic (Hoài My + Realistic)",
        "aspect_ratio": "16:9",
        "voice": "vi-VN-HoaiMyNeural",
        "art_style": "Photorealistic, cinematic lighting, 8K UHD",
        "bgm_track": "auto",
        "target_duration": "60s",
        "narration_tone": "emotional",
        "speech_rate": "+0%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 20,
        "subtitle_style": "cinematic_box",
        "use_sfx": True,
        "sfx_volume": 40,
        "is_default": True,
        "created_at": "2026-07-21T00:00:00"
    },
    {
        # Preset tái tạo style viral @sachhay_chondoc: kể chuyện sách/phim long-form,
        # footage thật (Pexels), phụ đề hộp mờ, giọng nam trầm ấm, nhịp chậm.
        "id": "preset_book_storytelling",
        "name": "📖 Kể Chuyện Sách/Phim (Long-form + Video thật)",
        "aspect_ratio": "16:9",
        "voice": "omnivoice_male_podcast_vi",
        "art_style": "Cinematic, realistic documentary footage, moody warm lighting",
        "bgm_track": "deep_abstract_ambient",
        "target_duration": "240s",
        "narration_tone": "storytelling",
        "speech_rate": "-5%",
        "speech_pitch": "+0Hz",
        "bgm_volume": 18,
        "subtitle_style": "cinematic_box",
        "color_grading": "warm_cinematic",
        "prefer_stock_video": True,
        "use_sfx": False,
        "sfx_volume": 30,
        "is_default": True,
        "created_at": "2026-07-24T00:00:00"
    }
]

def load_presets() -> List[Dict[str, Any]]:
    """Đọc danh sách presets từ file JSON. Nếu chưa có thì tạo các mẫu mặc định.
    Tự động merge các preset MẶC ĐỊNH mới (theo id) vào file đã seed từ trước."""
    if not os.path.exists(PRESETS_FILE):
        save_all_presets(DEFAULT_PRESETS)
        return DEFAULT_PRESETS
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            presets = json.load(f)
            if not isinstance(presets, list):
                return DEFAULT_PRESETS
        # Migration: bổ sung preset mặc định mới chưa có trong file (giữ nguyên preset user)
        existing_ids = {p.get("id") for p in presets}
        missing = [dp for dp in DEFAULT_PRESETS if dp["id"] not in existing_ids]
        if missing:
            # Chèn preset mặc định mới lên đầu để dễ thấy
            presets = missing + presets
            save_all_presets(presets)
        return presets
    except Exception:
        return DEFAULT_PRESETS

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
