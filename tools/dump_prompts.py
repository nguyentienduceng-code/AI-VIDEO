"""
Sinh docs/Prompt_Engineering_Templates.md TỪ CHÍNH CODE đang chạy.

Chạy:  python tools/dump_prompts.py

VÌ SAO CÓ FILE NÀY: tài liệu prompt trước đây được viết TAY từ mã nguồn ("được việt hoá từ
mã nguồn backend"), nên nó trôi khỏi thực tế mà không ai hay. Lúc rà lại, tài liệu vẫn mô
tả bốn cụm sáo rỗng bị cấm (code cấm 15), vẫn ghi các mục DYNAMIC PACING/TRANSITION/SFX như
thể Gemini điều khiển chúng (Python đã ghi đè từ lâu), khẳng định kịch bản dưới 60 điểm sẽ
"bị ép sinh lại" (không có vòng sinh lại nào tồn tại), và bỏ sót hoàn toàn ba prompt đang
chạy thật: BASE_STORYTELLING, split_script_to_scenes, generate_script_from_images.

Từ nay tài liệu là ARTIFACT: sửa prompt trong code rồi chạy lại file này. Đừng sửa tay file
.md — mọi thay đổi tay sẽ bị ghi đè ở lần chạy tiếp theo.
"""
from __future__ import annotations

import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from services import gemini_service as gs  # noqa: E402

OUT = os.path.join(ROOT, "docs", "Prompt_Engineering_Templates.md")


def fence(text: str) -> str:
    return "```text\n" + text.rstrip() + "\n```"


def main() -> None:
    parts: list[str] = []
    add = parts.append

    add("# TỔNG HỢP PROMPT ENGINEERING — AI VIDEO MAKER")
    add("")
    add(
        "> ⚠️ **FILE NÀY ĐƯỢC SINH TỰ ĐỘNG** bởi `tools/dump_prompts.py` từ chính "
        "`backend/services/gemini_service.py`. Đừng sửa tay — hãy sửa prompt trong code rồi "
        "chạy lại `python tools/dump_prompts.py`."
    )
    add("")
    add(f"- Sinh ngày: {date.today().isoformat()}")
    add(f"- `PROMPT_REVISION` (generate_script): `{gs.PROMPT_REVISION}`")
    add(f"- `SPLIT_PROMPT_REVISION` (split_script_to_scenes): `{gs.SPLIT_PROMPT_REVISION}`")
    add(f"- `IMAGE_PROMPT_REVISION` (generate_script_from_images): `{gs.IMAGE_PROMPT_REVISION}`")
    add("")
    add(
        "Đổi ba chuỗi revision trên mỗi khi sửa luật prompt — chúng nằm trong cache key, "
        "không đổi thì kịch bản cũ trong cache sẽ đè lên luật mới và trông như 'sửa không "
        "có tác dụng'."
    )
    add("")
    add("---")
    add("")

    # ── 1. Prompt hoàn chỉnh của từng chế độ, dựng đúng bằng hàm thật ──
    add("## 1. System prompt hoàn chỉnh theo chế độ (`build_script_system_prompt`)")
    add("")
    add(
        "Đây là chuỗi ĐÚNG NHƯ được gửi vào `system_instruction` của Gemini, dựng bằng chính "
        "hàm mà pipeline gọi. Các ví dụ dưới dùng 12 cảnh / 60s để số ngân sách từ hiện ra "
        "cụ thể."
    )
    add("")

    kich_ban = [
        (
            "1.1. Mặc định — `storyteller` + tone `viral` + ảnh AI",
            dict(num_scenes=12, target_duration="60s", narration_tone="viral"),
        ),
        (
            "1.2. Chế độ footage stock (`prefer_stock_video=True`)",
            dict(
                num_scenes=12,
                target_duration="60s",
                narration_tone="viral",
                prefer_stock_video=True,
            ),
        ),
        (
            "1.3. Kể chuyện long-form — tone `storytelling` (base prompt riêng)",
            dict(num_scenes=20, target_duration="240s", narration_tone="storytelling"),
        ),
        (
            "1.4. `quiz_listicle`",
            dict(num_scenes=8, target_duration="30s", mode="quiz_listicle"),
        ),
        (
            "1.5. Có bản vẽ niche + đồng nhất nhân vật",
            dict(
                num_scenes=12,
                target_duration="60s",
                narration_tone="educational",
                content_niche="finance",
                character_description="a 30-year-old Vietnamese man in a grey hoodie",
                sync_characters=True,
            ),
        ),
    ]
    for tieu_de, kwargs in kich_ban:
        add(f"### {tieu_de}")
        add("")
        add(f"Tham số: `{kwargs}`")
        add("")
        add(fence(gs.build_script_system_prompt(**kwargs)))
        add("")

    # ── 2. Luật phạm vi lô ──
    add("---")
    add("")
    add("## 2. Luật phạm vi LÔ (kịch bản dài > 12 cảnh)")
    add("")
    add(
        f"Gemini sinh tối đa {12} cảnh mỗi lần gọi. Mỗi lô nhận thêm đoạn dưới đây để chỉ "
        "MỘT lô duy nhất được viết cảnh kết — trước khi có luật này, video 30 cảnh có ba cái "
        "kết (cảnh 12, 24 và 30)."
    )
    add("")
    for nhan, (idx, size, tong) in {
        "Lô đầu (cảnh 1-12 / 30)": (0, 12, 30),
        "Lô giữa (cảnh 13-24 / 30)": (12, 12, 30),
        "Lô cuối (cảnh 25-30 / 30)": (24, 6, 30),
        "Kịch bản gọn trong 1 lô (6/6)": (0, 6, 6),
    }.items():
        rule = gs._batch_scope_rule(idx, size, tong)
        add(f"**{nhan}:**")
        add("")
        add(fence(rule or "(không thêm luật nào — giữ nguyên vòng cung đầy đủ)"))
        add("")

    # ── 3. Bảng cấu hình đang có hiệu lực ──
    add("---")
    add("")
    add("## 3. Bảng cấu hình đang có hiệu lực")
    add("")
    add("### 3.1. Bản vẽ NỘI DUNG theo niche (`NICHE_BLUEPRINTS`)")
    add("")
    add(
        "Được nối vào system prompt khi FE gửi `content_niche`. Chỉ chứa chỉ dẫn NỘI DUNG — "
        "phần cơ học (emotion/sfx/transition/nhịp đọc) do `NICHE_PERCENT_BLUEPRINTS` gán ở "
        "Python sau khi parse, Gemini không tham gia."
    )
    add("")
    for niche, bp in gs.NICHE_BLUEPRINTS.items():
        add(f"**`{niche}`**")
        add("")
        add(fence(bp))
        add("")

    add("### 3.2. Bản vẽ CƠ HỌC theo niche (`NICHE_PERCENT_BLUEPRINTS`)")
    add("")
    add("Cột: `vị trí bắt đầu → kết thúc | emotion | sfx | transition | nhịp đọc | hiệu ứng hình`")
    add("")
    for niche, bands in gs.NICHE_PERCENT_BLUEPRINTS.items():
        add(f"**`{niche}`**")
        add("")
        add("| Từ | Đến | emotion | sfx | transition | rate | visual_effect |")
        add("|---|---|---|---|---|---|---|")
        for lo, hi, emo, sfx, tran, rate, vfx in bands:
            add(f"| {lo:.0%} | {min(hi, 1.0):.0%} | {emo} | {sfx or '—'} | {tran} | {rate} | {vfx} |")
        add("")

    add("### 3.3. Tone kể chuyện (`NARRATION_TONE_PROMPTS`)")
    add("")
    add("Khoá PHẢI khớp `frontend/src/constants.js › NARRATION_TONES`.")
    add("")
    for tone, txt in gs.NARRATION_TONE_PROMPTS.items():
        add(f"- **`{tone}`** — {txt}")
    add("")

    add("### 3.4. Công thức Hook (`HOOK_FORMULAS`)")
    add("")
    for tone, txt in gs.HOOK_FORMULAS.items():
        add(f"**`{tone}`**")
        add("")
        add(fence(txt))
        add("")

    add("### 3.5. Ngân sách từ theo thời lượng (`DURATION_CONFIG`)")
    add("")
    add("| Thời lượng | Tổng số từ | Số cảnh gợi ý | Từ/cảnh (ở số cảnh gợi ý) |")
    add("|---|---|---|---|")
    for dur, cfg in gs.DURATION_CONFIG.items():
        n = cfg["suggested_scenes"]
        lo, hi = gs.scene_word_budget(dur, n)
        add(f"| {dur} | {cfg['words']} | {n} | {lo}-{hi} |")
    add("")
    add(
        f"Tốc độ đọc dùng để quy ra giây lấy từ `duration_model.words_per_second()` "
        f"(hiện tại: **{gs._default_wps():.2f} từ/giây**) — con số này tự hiệu chỉnh theo số "
        "đo thật của từng giọng, nên bảng trên đổi theo giọng đang dùng."
    )
    add("")

    add("### 3.6. Cụm từ sáo rỗng bị cấm (`CLICHE_PHRASES`)")
    add("")
    add(
        "MỘT nguồn chân lý duy nhất: danh sách này vừa được nối vào prompt (qua "
        "`_cliche_ban_rule()`) vừa là căn cứ trừ điểm của `_local_review()`. Trước đây prompt "
        "liệt kê tay 4 cụm còn lớp review phạt theo 15 cụm — model bị trừ điểm vì luật chưa "
        "ai nói cho nó biết."
    )
    add("")
    for p in gs.CLICHE_PHRASES:
        add(f"- `{p}`")
    add("")

    # ── 4. Các prompt còn lại ──
    add("---")
    add("")
    add("## 4. Các prompt khác trong hệ thống")
    add("")
    add("### 4.1. Base prompt kể chuyện long-form (`BASE_STORYTELLING`)")
    add("")
    add("Dùng khi tone = `storytelling`. Trước đây tài liệu bỏ sót hoàn toàn prompt này.")
    add("")
    add(fence(gs.BASE_STORYTELLING))
    add("")

    add("### 4.2. Luật viết `image_prompt` theo nguồn hình")
    add("")
    add("**Chế độ ảnh AI (`IMAGE_PROMPT_RULES_AI`)**")
    add("")
    add(fence(gs.IMAGE_PROMPT_RULES_AI))
    add("")
    add("**Chế độ footage stock (`IMAGE_PROMPT_RULES_STOCK`)**")
    add("")
    add(fence(gs.IMAGE_PROMPT_RULES_STOCK))
    add("")

    add("### 4.3. Luật nội dung dùng chung")
    add("")
    for ten, txt in [
        ("SPECIFICITY_RULES", gs.SPECIFICITY_RULES),
        ("TTS_WRITING_RULES", gs.TTS_WRITING_RULES),
        ("CTA_RULES", gs.CTA_RULES),
    ]:
        add(f"**`{ten}`**")
        add("")
        add(fence(txt))
        add("")

    add("### 4.4. Lớp thẩm định kịch bản (`_NARRATIVE_REVIEW_PROMPT`)")
    add("")
    add(
        "Tầng 2 của QC: một lần gọi `gemini-flash-latest` với `temperature=0.3`. Là lớp "
        "**best-effort** — lỗi quota/mạng bị bỏ qua êm, KHÔNG chặn luồng sinh kịch bản. "
        "Điểm cuối = trung bình cộng điểm heuristic (`_local_review`) và điểm này.\n\n"
        "⚠️ Kết quả review được TRẢ VỀ cho UI để người dùng tự quyết; hệ thống **không** tự "
        "sinh lại kịch bản khi điểm thấp (tài liệu cũ từng khẳng định có, nhưng không đúng)."
    )
    add("")
    add(fence(gs._NARRATIVE_REVIEW_PROMPT))
    add("")

    add("### 4.5. Chia cảnh từ kịch bản có sẵn (`build_split_system_prompt`)")
    add("")
    add(
        "Lời thoại được giữ NGUYÊN VĂN 100% (`temperature=0.1`); tone/niche chỉ quyết định "
        "hiệu ứng. Tài liệu cũ bỏ sót prompt này."
    )
    add("")
    add(fence(gs.build_split_system_prompt(num_scenes=8)))
    add("")

    add("### 4.6. Narration từ ảnh người dùng (`build_photo_system_prompt`)")
    add("")
    add("Gemini multimodal: xem ảnh rồi viết lời bình cho từng ảnh. Tài liệu cũ bỏ sót.")
    add("")
    add(fence(gs.build_photo_system_prompt(num_images=5, topic="Chuyến đi Đà Lạt")))
    add("")

    add("### 4.7. Lượt VIẾT LẠI khi điểm chất lượng thấp")
    add("")
    add(
        f"Nếu lớp review chấm dưới **{gs.REGENERATE_SCORE_THRESHOLD}/100**, hệ thống viết lại "
        "ĐÚNG MỘT lượt với đoạn dưới đây nối vào cuối prompt, và **chỉ nhận bản mới khi nó "
        "điểm cao hơn**. Chỉ các loại lỗi mà viết lại thật sự sửa được mới kích hoạt vòng này: "
        + ", ".join(f"`{i}`" for i in sorted(gs._REGENERATE_WORTHY_ISSUES))
        + "."
    )
    add("")
    mau = gs.build_script_system_prompt(
        num_scenes=6,
        revision_notes=[
            "Cảnh 1: Hook chưa đủ gây tò mò → mở bằng một con số bất ngờ",
            "Cảnh 4: Mạch cảm xúc phẳng, không có điểm nhấn nào",
        ],
    )
    add(fence(mau[mau.index("ĐÂY LÀ LƯỢT VIẾT LẠI"):]))
    add("")

    noi_dung = "\n".join(parts).rstrip() + "\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(noi_dung)
    print(f"Đã ghi {OUT} ({len(noi_dung):,} ký tự)")


if __name__ == "__main__":
    main()
