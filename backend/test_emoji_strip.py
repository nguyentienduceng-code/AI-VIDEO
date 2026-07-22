import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.tts_service import _normalize_text, _strip_emoji
from services.video_service import _strip_emoji_for_subtitle

test_texts = [
    "Bạn có bao giờ tự hỏi, điều gì thực sự chi phối cuộc đời mình? 🤔",
    "Cuốn sách 'Luật Tâm Thức' của Ngô Sa Thạch hé lộ: vũ trụ vận hành theo những quy luật vô hình. 🌌",
    "Niềm tin sâu bên trong tâm thức — chứ không chỉ suy nghĩ bề mặt — mới là thứ tạo nên hiện thực. 🧘‍♂️",
    "Luật hấp dẫn, luật nhân quả, chu kỳ cuộc sống — tất cả đều phản chiếu chính nội tâm ta. 🌊",
    "Những khó khăn không phải nghịch cảnh, mà là bài học giúp ta tiến hóa tâm linh. 🌲",
    "Khi hiểu được tâm thức, bạn nắm giữ chìa khóa thay đổi chính cuộc đời mình. ✨",
]

print("=" * 70)
print("TEST 1: tts_service._normalize_text()")
print("=" * 70)
for i, t in enumerate(test_texts):
    cleaned = _normalize_text(t)
    has_emoji = bool(_strip_emoji(cleaned) != cleaned)
    print(f"  Scene {i+1}: emoji_left={has_emoji}  |  '{cleaned}'")

print()
print("=" * 70)
print("TEST 2: video_service._strip_emoji_for_subtitle()")
print("=" * 70)
for i, t in enumerate(test_texts):
    cleaned = _strip_emoji_for_subtitle(t)
    upper = cleaned.upper()
    has_emoji = bool(_strip_emoji(upper) != upper)
    print(f"  Scene {i+1}: emoji_in_subtitle={has_emoji}  |  '{upper}'")
