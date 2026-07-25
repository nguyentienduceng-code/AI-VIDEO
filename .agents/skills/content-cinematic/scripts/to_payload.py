#!/usr/bin/env python3
"""
to_payload.py — Convert kịch bản (Scene JSON của skill content-cinematic) thành payload
cho endpoint POST /api/render-video của AI-VIDEO-MAKER, có VALIDATE whitelist.

Dùng:
    python to_payload.py script.json                         # in payload ra stdout
    python to_payload.py script.json -o payload.json         # ghi ra file
    python to_payload.py script.json --preset book           # áp preset kể chuyện (16:9, stock video, cinematic_box)
    python to_payload.py script.json --send http://localhost:8000   # POST thẳng (cần `requests`)

Input JSON chấp nhận:
    - {"scenes":[...], "hook_text":"", "cta_text":"", "recommended_bgm":"", "sentiment":""}
    - hoặc chỉ mảng [ {scene...}, ... ]

Script CHỈ dùng thư viện chuẩn (json/argparse) để validate + build payload; --send mới cần `requests`.
"""
from __future__ import annotations

import argparse
import json
import sys

# ── Whitelist (đồng bộ references/app-schema.md) ──
EMOTIONS = {"hook", "calm", "dramatic", "excited", "suspense", "closing"}
SFX = {"", "whoosh", "swoosh_soft", "pop", "tick", "ding", "bell", "shimmer",
       "riser", "bass_drop", "impact", "suspense", "heartbeat", "laugh"}
TRANSITIONS = {"crossfade", "fade_black", "fade_white", "zoom_through", "zoom_punch",
               "slide_left", "slide_right", "slide_up", "slide_down",
               "wipe_right", "wipe_down", "whip_pan", "page_flip", "droplet"}
BGM = {"auto", "afro_pop", "black_light_all_good_folks_main", "comedy_cartoon",
       "deep_abstract_ambient", "fluffy_clouds_fugu_vibes_main_version", "hype_drill",
       "lofi_jazzy_love", "moment_of_peace", "music_promotion", "new_age_nature",
       "no_sleep_hiphop", "rap_beat", "running_night", "type_beat"}
VISUAL_EFFECTS = {"", "zoom_in", "zoom_out", "pan_left", "pan_right", "none"}
HOOK_EFFECTS = {"word_by_word", "full_shake", "carousel_quote"}

# ── Preset cấu hình render (khớp preset_service.py) ──
PRESETS = {
    "viral": dict(aspect_ratio="9:16", subtitle_style="karaoke_bold", color_grading="vivid_pop",
                  voice="vi-VN-NamMinhNeural", speech_rate="+0%", prefer_stock_video=False,
                  use_sfx=True, bgm_track="auto"),
    "book": dict(aspect_ratio="16:9", subtitle_style="cinematic_box", color_grading="warm_cinematic",
                 voice="omnivoice_male_podcast_vi", speech_rate="-5%", prefer_stock_video=True,
                 use_sfx=False, bgm_track="deep_abstract_ambient"),
}


def validate_scenes(scenes: list) -> list[str]:
    """Trả về danh sách cảnh báo (không chặn), giúp phát hiện giá trị sai whitelist."""
    warns: list[str] = []
    for i, s in enumerate(scenes, 1):
        if not s.get("text", "").strip():
            warns.append(f"Cảnh {i}: thiếu 'text' (lời thoại).")
        if not s.get("image_prompt", "").strip():
            warns.append(f"Cảnh {i}: thiếu 'image_prompt'.")
        if s.get("emotion") and s["emotion"] not in EMOTIONS:
            warns.append(f"Cảnh {i}: emotion '{s['emotion']}' KHÔNG hợp lệ → {sorted(EMOTIONS)}")
        if s.get("sfx", "") not in SFX:
            warns.append(f"Cảnh {i}: sfx '{s['sfx']}' KHÔNG hợp lệ → {sorted(SFX)}")
        if s.get("transition") and s["transition"] not in TRANSITIONS:
            warns.append(f"Cảnh {i}: transition '{s['transition']}' KHÔNG hợp lệ → {sorted(TRANSITIONS)}")
        if s.get("visual_effect", "") not in VISUAL_EFFECTS:
            warns.append(f"Cảnh {i}: visual_effect '{s['visual_effect']}' KHÔNG hợp lệ.")
        # Cảnh báo prompt kiểu AI-image lọt vào (hỏng tìm Pexels)
        p = s.get("image_prompt", "").lower()
        bad = [kw for kw in ("octane", "unreal engine", "midjourney", "8k", "hyper-realistic",
                             "extreme close-up shot of", "drone shot of", "establishing shot of") if kw in p]
        if bad:
            warns.append(f"Cảnh {i}: image_prompt chứa jargon AI/máy quay {bad} — có thể hỏng khi tìm video stock.")
    return warns


def build_payload(data, preset: str | None) -> dict:
    scenes = data if isinstance(data, list) else data.get("scenes", [])
    meta = {} if isinstance(data, list) else data

    hook_effect = meta.get("hook_effect", "word_by_word")
    if hook_effect not in HOOK_EFFECTS:
        print(f"⚠️  hook_effect '{hook_effect}' KHÔNG hợp lệ → {sorted(HOOK_EFFECTS)}. Dùng word_by_word.", file=sys.stderr)
        hook_effect = "word_by_word"
    if hook_effect == "carousel_quote" and not meta.get("hook_quote", "").strip():
        print("⚠️  hook_effect=carousel_quote nhưng thiếu 'hook_quote' (câu chốt). Hook sẽ trống.", file=sys.stderr)

    payload = dict(
        scenes=scenes,
        mode="storyteller",
        hook_effect=hook_effect,
        hook_text=meta.get("hook_text", ""),
        hook_quote=meta.get("hook_quote", ""),
        cta_text=meta.get("cta_text", ""),
        bgm_track=meta.get("recommended_bgm", "auto"),
        use_animated_captions=True,
        aspect_ratio="9:16",
    )
    if preset:
        if preset not in PRESETS:
            sys.exit(f"Preset '{preset}' không tồn tại. Chọn: {sorted(PRESETS)}")
        payload.update(PRESETS[preset])
        # BGM ưu tiên gợi ý từ kịch bản nếu có, nếu không dùng của preset
        if meta.get("recommended_bgm"):
            payload["bgm_track"] = meta["recommended_bgm"]

    if payload.get("bgm_track") not in BGM:
        payload["bgm_track"] = "auto"
    return payload


def main():
    ap = argparse.ArgumentParser(description="Convert Scene JSON → payload /api/render-video")
    ap.add_argument("input", help="File JSON kịch bản")
    ap.add_argument("-o", "--output", help="Ghi payload ra file (mặc định stdout)")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="Áp preset render (viral | book)")
    ap.add_argument("--send", metavar="BASE_URL", help="POST payload tới BASE_URL/api/render-video")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data if isinstance(data, list) else data.get("scenes", [])
    if not scenes:
        sys.exit("Không tìm thấy 'scenes' trong input.")

    for w in validate_scenes(scenes):
        print(f"⚠️  {w}", file=sys.stderr)

    payload = build_payload(data, args.preset)
    out = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"✅ Đã ghi payload ({len(scenes)} cảnh) → {args.output}", file=sys.stderr)
    else:
        print(out)

    if args.send:
        try:
            import requests
        except ImportError:
            sys.exit("Cần `pip install requests` để dùng --send.")
        r = requests.post(f"{args.send.rstrip('/')}/api/render-video", json=payload, timeout=30)
        print(f"[send] HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr)


if __name__ == "__main__":
    main()
