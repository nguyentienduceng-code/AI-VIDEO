"""
Test cho tầng DỰNG PROMPT của gemini_service — build_script_system_prompt() và bạn bè.

Chạy:  python tests/test_prompt_assembly.py   (từ thư mục backend/, không cần pytest)
       pytest tests/test_prompt_assembly.py

VÌ SAO CÓ FILE NÀY: system_instruction trước đây được nối chuỗi NGAY TRONG THÂN
`generate_script`, phía trong closure `_call()` — không một test nào chạm nổi vào nó vì
muốn thấy chuỗi đó thì phải gọi Gemini thật. Hệ quả là ba lỗi CÂM đã sống rất lâu, cả ba
đều thuộc loại "video vẫn render xong, chỉ là nội dung nhạt hơn đáng lẽ phải có" nên không
ai phát hiện bằng cách dùng app:

  1. `NICHE_BLUEPRINTS` — toàn bộ bản vẽ nội dung theo niche — chưa từng được tiêm vào
     prompt. Chọn "Tài chính" hay "True Crime" trên UI chỉ đổi được sfx/transition.
  2. Kịch bản dài chia lô 12 cảnh, mỗi lô nhận nguyên dòng "CTA (Cảnh cuối)", nên video
     30 cảnh có BA cái kết — hai cái nằm giữa bài.
  3. `NARRATION_TONE_PROMPTS` đánh khoá lệch với UI: tone `viral` (mặc định) và `emotional`
     tra ra chuỗi rỗng, tức hai tone dùng nhiều nhất không có chỉ dẫn giọng nào.

Mọi test dưới đây là thuần chuỗi, không gọi mạng, không cần API key.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import (
    CLICHE_PHRASES,
    HOOK_FORMULAS,
    IMAGE_PROMPT_RULES_STOCK,
    NARRATION_TONE_PROMPTS,
    NICHE_BLUEPRINTS,
    NICHE_PERCENT_BLUEPRINTS,
    TONE_PERCENT_PALETTES,
    build_script_system_prompt,
    scene_word_rule_text,
)


# ---------------------------------------------------------------------------
# 1. Bản vẽ niche phải THỰC SỰ tới được Gemini
# ---------------------------------------------------------------------------
def test_ban_ve_niche_duoc_tiem_vao_prompt():
    """Lỗi #1: chọn niche mà lời thoại không đổi gì thì niche chỉ là trang trí."""
    for niche, blueprint in NICHE_BLUEPRINTS.items():
        prompt = build_script_system_prompt(num_scenes=8, content_niche=niche)
        # Lấy một câu đặc trưng của từng bản vẽ để chắc chắn đúng bản vẽ ĐÓ được dùng,
        # không phải một bản vẽ nào khác lọt vào.
        moc = blueprint.splitlines()[0]
        assert moc in prompt, f"Bản vẽ niche '{niche}' không có trong prompt"

    # Và không có niche thì không được rò bản vẽ của niche khác vào.
    trung_lap = build_script_system_prompt(num_scenes=8, content_niche=None)
    assert "NICHE:" not in trung_lap


def test_niche_nao_cung_co_ban_ve_phan_tram_di_kem():
    """Bản vẽ NỘI DUNG (Gemini) và bản vẽ CƠ HỌC (Python) phải phủ cùng bộ niche.

    Nếu lệch, user chọn niche sẽ được chỉ dẫn nội dung đúng chất nhưng nhận hiệu ứng của
    palette tone mặc định — hai nửa của cùng một lựa chọn nói hai chuyện khác nhau.
    """
    assert set(NICHE_BLUEPRINTS) == set(NICHE_PERCENT_BLUEPRINTS)


def test_ban_ve_noi_dung_khong_con_chi_dan_co_hoc():
    """Chỉ dẫn sfx/transition/rate trong bản vẽ nội dung là token vứt đi.

    LLMScene không có các trường đó và resolve_blueprint() ghi đè toàn bộ ngay sau khi
    parse, nên nói với Gemini "sfx 'riser'" vừa vô ích vừa làm loãng phần nó điều khiển thật.
    """
    for niche, blueprint in NICHE_BLUEPRINTS.items():
        low = blueprint.lower()
        for tu_co_hoc in ("sfx", "transition", "crossfade", "zoom_punch", "fade_black", "rate '"):
            assert tu_co_hoc not in low, (
                f"Bản vẽ nội dung của '{niche}' vẫn còn chỉ dẫn cơ học: {tu_co_hoc!r}"
            )


def test_niche_book_giu_anh_bia_o_canh_1_nhung_khong_ke_ve_bia():
    """Cảnh 1 vừa là ảnh bìa cho Máy Xèng, vừa KHÔNG được đọc lại tên sách.

    Hai vai trò này bị bản cũ nhập làm một rồi ra lệnh sai: nó cấm "mô tả bìa sách ở Cảnh
    1" nói chung. Nhưng video_service lấy CHÍNH `scene_assets[0]["image_path"]` làm bìa cho
    hiệu ứng carousel/Máy Xèng, nên cấm như vậy là để máy xèng quay ra ảnh bàn làm việc của
    tác giả. Thứ phải cấm là `text` nhắc lại tên sách (chữ đó đã in to trên bìa rồi).
    """
    bp = NICHE_BLUEPRINTS["book"]
    assert "image_prompt" in bp and "bìa sách" in bp
    assert "KHÔNG tả bìa" in bp or "KHÔNG tả bìa," in bp


# ---------------------------------------------------------------------------
# 2. Chia lô không được sinh ra nhiều cái kết
# ---------------------------------------------------------------------------
def test_lo_dau_va_lo_giua_bi_cam_viet_ket_va_cta():
    """Lỗi #2: video 30 cảnh từng có ba cái kết (cảnh 12, 24 và 30)."""
    lo_dau = build_script_system_prompt(num_scenes=30, batch_idx=0, batch_size=12)
    lo_giua = build_script_system_prompt(num_scenes=30, batch_idx=12, batch_size=12)
    lo_cuoi = build_script_system_prompt(num_scenes=30, batch_idx=24, batch_size=6)

    for prompt in (lo_dau, lo_giua):
        assert "KHÔNG viết cảnh kết" in prompt or "KHÔNG viết cảnh kết/đúc kết/CTA" in prompt
        assert "BỎ LỬNG" in prompt

    assert "CHỨA CẢNH CUỐI" in lo_cuoi
    assert "duy nhất được phép có lời kết" in lo_cuoi
    # Lô giữa còn phải bị cấm viết lại hook, nếu không video có hai lần mở màn.
    assert "KHÔNG viết lại hook" in lo_giua


def test_kich_ban_gon_trong_mot_lo_giu_nguyen_vong_cung_day_du():
    """Không được thêm luật phạm vi lô khi cả kịch bản nằm trong 1 lô — sẽ cấm oan cái kết."""
    prompt = build_script_system_prompt(num_scenes=6, batch_idx=0, batch_size=6)
    assert "PHẠM VI LÔ HIỆN TẠI" not in prompt
    assert "KHÔNG viết cảnh kết" not in prompt


def test_lo_biet_tong_so_canh_that_cua_video():
    """Ngân sách từ phải tính theo TỔNG số cảnh, không theo số cảnh của lô.

    Nếu tính theo lô, lô 12 cảnh của video 30 cảnh sẽ được cấp ngân sách của cả video chia
    12 — mỗi cảnh dài gấp 2.5 lần dự kiến.
    """
    prompt = build_script_system_prompt(
        num_scenes=30, target_duration="300s", batch_idx=0, batch_size=12
    )
    assert "tổng chữ của tất cả 30 cảnh" in prompt
    assert scene_word_rule_text("300s", 30) in prompt
    assert "CHÍNH XÁC 12 phân cảnh" in prompt  # nhưng lô này chỉ viết 12 cảnh


# ---------------------------------------------------------------------------
# 3. Tone: khoá phải khớp UI
# ---------------------------------------------------------------------------
# Đồng bộ frontend/src/constants.js › NARRATION_TONES.
TONE_UI = ["viral", "storytelling", "educational", "emotional", "humorous"]


def test_moi_tone_cua_ui_deu_co_chi_dan_giong_va_cong_thuc_hook():
    """Lỗi #3: `viral` (mặc định) và `emotional` từng tra ra chuỗi rỗng ở cả hai bảng."""
    for tone in TONE_UI:
        assert NARRATION_TONE_PROMPTS.get(tone), f"Tone '{tone}' không có chỉ dẫn giọng"
        assert HOOK_FORMULAS.get(tone), f"Tone '{tone}' không có công thức hook"
        prompt = build_script_system_prompt(num_scenes=6, narration_tone=tone)
        assert NARRATION_TONE_PROMPTS[tone] in prompt


def test_tone_va_palette_hieu_ung_phu_cung_bo_khoa():
    """Tone có chỉ dẫn giọng nhưng thiếu palette % (hoặc ngược lại) là một nửa lựa chọn."""
    assert set(TONE_UI) <= set(TONE_PERCENT_PALETTES)
    assert set(TONE_UI) <= set(NARRATION_TONE_PROMPTS)


# ---------------------------------------------------------------------------
# 4. Danh sách cụm sáo rỗng: một nguồn chân lý
# ---------------------------------------------------------------------------
def test_moi_cum_sao_rong_bi_tru_diem_deu_duoc_noi_truoc_trong_prompt():
    """Model không được bị phạt vì luật chưa ai nói cho nó biết.

    LỖI CŨ: prompt liệt kê tay 4 cụm, `_local_review` trừ điểm theo 15 cụm.
    """
    prompt = build_script_system_prompt(num_scenes=6)
    for cum in CLICHE_PHRASES:
        assert cum in prompt, f"Cụm bị trừ điểm nhưng prompt không cấm: {cum!r}"


# ---------------------------------------------------------------------------
# 5. image_prompt phải rẽ theo nguồn hình
# ---------------------------------------------------------------------------
def test_che_do_stock_cam_thuat_ngu_may_quay_va_tu_khoa_render():
    """Với footage stock, image_prompt CHÍNH LÀ câu truy vấn tìm video.

    Prompt cũ ép "Extreme close-up shot of..., 8k, Unreal Engine 5" cho mọi chế độ, rồi
    extract_search_keyword() phải mang ~40 stopword đi gỡ lại đúng những chữ đó. Chữ nào
    lọt lưới thành từ khoá rác → kho stock trả video sai chủ đề.
    """
    stock = build_script_system_prompt(num_scenes=6, prefer_stock_video=True)
    ai = build_script_system_prompt(num_scenes=6, prefer_stock_video=False)

    assert "CẤM mở đầu bằng thuật ngữ máy quay" in stock
    assert "Unreal Engine" in ai and "Extreme close-up shot of" in ai
    # Chế độ stock KHÔNG được mang theo luật cinematic của chế độ ảnh AI.
    assert "Phẩm chất nghệ thuật (8k, photorealistic, Unreal Engine 5)" not in stock


def test_tone_ke_chuyen_luon_dung_luat_footage_that():
    """BASE_STORYTELLING sinh ra để dựng bằng footage thật (style @sachhay_chondoc).

    Nó tự có luật hình ảnh riêng nên không được nối thêm luật cinematic của chế độ ảnh AI
    vào — hai bộ luật sẽ ra lệnh trái nhau trong cùng một prompt.
    """
    prompt = build_script_system_prompt(num_scenes=8, narration_tone="storytelling")
    assert "DÙNG FOOTAGE THẬT" in prompt
    assert "Extreme close-up shot of" not in prompt
    assert IMAGE_PROMPT_RULES_STOCK not in prompt  # base đã tự lo, không nối trùng


# ---------------------------------------------------------------------------
# 6. Các luật chất lượng nội dung phải có mặt ở mọi chế độ
# ---------------------------------------------------------------------------
def test_luat_cu_the_va_cta_that_co_o_moi_che_do():
    """Các luật này trước đây CHỈ nằm trong tài liệu skill (cho agent viết tay).

    Kịch bản do chính app sinh ra không hề được hưởng — đúng chỗ khiến content ra "chung
    chung" dù tài liệu dự án có đủ luật chống chung chung.
    """
    for kwargs in (
        {"mode": "storyteller"},
        {"mode": "quiz_listicle"},
        {"narration_tone": "storytelling"},
    ):
        prompt = build_script_system_prompt(num_scenes=8, **kwargs)
        assert "SHOW, DON'T TELL" in prompt
        assert "LÝ DO GIỮ CHÂN" in prompt
        assert "chi tiết " in prompt and "giác quan" in prompt


def test_cam_khan_hiem_gia_trong_cta():
    prompt = build_script_system_prompt(num_scenes=6)
    assert "CẤM khan hiếm giả" in prompt
    assert "trước khi video bị gỡ" in prompt  # nêu đúng ví dụ bị cấm


def test_khong_con_ra_lenh_ve_truong_gemini_khong_the_tra_ve():
    """LLMScene không có sfx/transition/speech_rate_modifier — resolve_blueprint gán ở Python.

    Ra lệnh về chúng chỉ tốn token và hút sự chú ý khỏi lời thoại + image_prompt.
    """
    prompt = build_script_system_prompt(num_scenes=6)
    assert "speech_rate_modifier" not in prompt
    assert "QUY TẮC TRANSITION" not in prompt
    assert "ĐỂ TRỐNG sfx" not in prompt


def test_co_yeu_cau_dien_source_quote():
    """source_coverage được tính và hiển thị như chỉ số chống bịa, nhưng không prompt nào
    từng yêu cầu điền `source_quote` — nên nó luôn bằng 0.0 với mọi video."""
    prompt = build_script_system_prompt(num_scenes=6)
    assert "source_quote" in prompt and "để RỖNG" in prompt


# ---------------------------------------------------------------------------
# 7. Lớp review không được báo động sai
# ---------------------------------------------------------------------------
def test_cau_hoi_mo_o_canh_cuoi_duoc_tinh_la_cta():
    """CTA dạng câu hỏi mở là kiểu được chính hook-library.md khuyến nghị.

    Đo trên kịch bản Gemini thật (chủ đề tài chính, 6 cảnh): cảnh cuối "Trích ngay 10% thu
    nhập tháng này để đầu tư. Bạn dám thử không?" bị báo THIẾU CTA và trừ 3 điểm, chỉ vì
    không chứa chữ 'like/share/follow'. Cảnh báo sai đẩy người dùng đi sửa một cảnh đã đúng.
    """
    from services.gemini_service import _local_review

    canh = [
        {"text": "Gửi 100 triệu vào ngân hàng, mỗi năm bạn cúng trắng 7 triệu."},
        {"text": "Trích ngay 10% thu nhập tháng này để đầu tư. Bạn dám thử không?"},
    ]
    kq = _local_review(canh, word_budget_hi=20)
    assert not [n for n in kq.review_notes if n.issue_type == "missing_cta"]

    # Nhưng cảnh cuối chỉ kể tiếp, không mời gọi gì, thì vẫn phải bị bắt.
    canh_cut = [canh[0], {"text": "Và lạm phát vẫn tiếp tục ăn dần số tiền đó."}]
    kq_cut = _local_review(canh_cut, word_budget_hi=20)
    assert [n for n in kq_cut.review_notes if n.issue_type == "missing_cta"]


# ---------------------------------------------------------------------------
# 8. Ngân sách từ: prompt tự đếm + review có biên dung sai
# ---------------------------------------------------------------------------
def test_prompt_co_buoc_tu_dem_lai_so_tu():
    """Đo trên kịch bản thật: 2/6 cảnh ra 15 từ trên trần 14 — lố đúng 1 từ.

    Model không "cảm" được số từ nếu không được yêu cầu đếm tường minh.
    """
    from services.gemini_service import WORD_COUNT_SELF_CHECK

    for kwargs in ({}, {"narration_tone": "storytelling"}, {"mode": "quiz_listicle"}):
        prompt = build_script_system_prompt(num_scenes=6, **kwargs)
        assert WORD_COUNT_SELF_CHECK in prompt, kwargs
    # Token không được sót lại chưa thay.
    assert "{WORD_COUNT_SELF_CHECK}" not in build_script_system_prompt(num_scenes=6)


def test_review_co_bien_dung_sai_voi_ngan_sach_tu():
    """Lố 1 từ (≈0.35 giây) không phá nhịp, nhưng cảnh dài thật vẫn phải bị bắt.

    Bản cũ gắn severity 'error' + trừ 8 điểm cho cả trường hợp lố 1 từ — người dùng thấy lỗi
    ĐỎ trên kịch bản hoàn toàn dùng được rồi mất niềm tin vào cả lớp review.
    """
    from services.gemini_service import _local_review

    tran = 14
    lo_it = [{"text": " ".join(["từ"] * 15)}, {"text": "Bạn nghĩ sao?"}]
    lo_nhieu = [{"text": " ".join(["từ"] * 20)}, {"text": "Bạn nghĩ sao?"}]

    assert not [n for n in _local_review(lo_it, tran).review_notes if n.issue_type == "too_long"]
    assert [n for n in _local_review(lo_nhieu, tran).review_notes if n.issue_type == "too_long"]


# ---------------------------------------------------------------------------
# 9. hook_quote phải được sinh tự động
# ---------------------------------------------------------------------------
def test_hook_quote_co_trong_schema_va_duoc_giai_thich_trong_prompt():
    """`RenderVideoRequest.hook_quote` và `build_carousel_hook()` chờ trường này từ lâu,
    nhưng schema Gemini không có nó — nên hiệu ứng bìa-sách-kèm-quote luôn phải gõ tay."""
    from services.gemini_service import LLMScriptResponse, ScriptResponse

    assert "hook_quote" in LLMScriptResponse.model_fields
    assert "hook_quote" in ScriptResponse.model_fields

    prompt = build_script_system_prompt(num_scenes=8, content_niche="book")
    assert "hook_quote" in prompt
    # Phải phân biệt rõ với hook_text, nếu không model sẽ điền trùng nội dung vào cả hai.
    assert "hook_text" in prompt and "hook_variants" in prompt


# ---------------------------------------------------------------------------
# 10. Vòng viết lại
# ---------------------------------------------------------------------------
def test_gop_y_cua_review_duoc_noi_vao_prompt_luot_viet_lai():
    prompt = build_script_system_prompt(
        num_scenes=6, revision_notes=["Cảnh 1: Hook quá nhạt → thay bằng con số sốc"]
    )
    assert "LƯỢT VIẾT LẠI" in prompt
    assert "Hook quá nhạt" in prompt
    # Lượt đầu tuyệt đối không được mang câu này.
    assert "LƯỢT VIẾT LẠI" not in build_script_system_prompt(num_scenes=6)


def test_chi_loc_loi_ma_viet_lai_moi_sua_duoc():
    """`too_long` không đáng một lượt quota: scene_balancer + luật số từ đã lo."""
    from services.gemini_service import _revision_notes_from_review

    review = {
        "review_notes": [
            {"issue_type": "weak_hook", "scene_index": 1, "message": "Hook nhạt", "suggestion": "Dùng con số"},
            {"issue_type": "too_long", "scene_index": 3, "message": "Cảnh 20 từ", "suggestion": "Tách ra"},
            {"issue_type": "missing_cta", "scene_index": 6, "message": "Thiếu CTA", "suggestion": ""},
        ]
    }
    notes = _revision_notes_from_review(review)
    assert len(notes) == 1
    assert notes[0] == "Cảnh 1: Hook nhạt → Dùng con số"


def test_khong_viet_lai_khi_diem_da_dat():
    import asyncio

    from services.gemini_service import REGENERATE_SCORE_THRESHOLD, regenerate_if_low_quality

    ban_dau = {"scenes": [{"text": "x"}]}
    review = {"quality_score": REGENERATE_SCORE_THRESHOLD, "review_notes": []}
    kb, rv = asyncio.run(
        regenerate_if_low_quality(
            ban_dau, review, word_budget_hi=14, gen_kwargs={"topic": "x"},
        )
    )
    assert kb is ban_dau and rv is review  # không gọi API nào (gen_kwargs thiếu tham số)


def test_khong_viet_lai_khi_diem_thap_nhung_khong_co_loi_sua_duoc():
    """Điểm thấp vì cảnh dài thì viết lại cũng không giải quyết — đừng tốn quota."""
    import asyncio

    from services.gemini_service import regenerate_if_low_quality

    ban_dau = {"scenes": [{"text": "x"}]}
    review = {
        "quality_score": 40,
        "review_notes": [{"issue_type": "too_long", "scene_index": 2, "message": "dài"}],
    }
    kb, rv = asyncio.run(
        regenerate_if_low_quality(ban_dau, review, word_budget_hi=14, gen_kwargs={"topic": "x"})
    )
    assert kb is ban_dau and rv is review


def test_giu_ban_dau_khi_ban_viet_lai_khong_tot_hon():
    """Viết lại có thể ra bản TỆ HƠN. Im lặng thay bằng bản tệ hơn còn hại hơn không làm gì."""
    import asyncio

    from services import gemini_service as gs

    ban_dau = {"scenes": [{"text": "ban dau"}]}
    ban_moi = {"scenes": [{"text": "ban moi"}]}
    goc_gen, goc_review = gs.generate_script, gs.review_script

    async def gen_gia(**kwargs):
        assert kwargs.get("revision_notes"), "phải truyền góp ý xuống lượt viết lại"
        return ban_moi

    async def review_gia(script, **kwargs):
        return {"quality_score": 35, "review_notes": []}

    gs.generate_script, gs.review_script = gen_gia, review_gia
    try:
        kb, rv = asyncio.run(
            gs.regenerate_if_low_quality(
                ban_dau,
                {"quality_score": 50, "review_notes": [{"issue_type": "weak_hook", "scene_index": 1, "message": "nhạt"}]},
                word_budget_hi=14,
                gen_kwargs={"topic": "x"},
            )
        )
    finally:
        gs.generate_script, gs.review_script = goc_gen, goc_review

    assert kb is ban_dau, "bản viết lại điểm thấp hơn mà vẫn bị nhận"
    assert rv["regenerated"] is False
    assert rv["rejected_retry_score"] == 35


def test_nhan_ban_viet_lai_khi_tot_hon_va_bao_cho_ui_biet():
    import asyncio

    from services import gemini_service as gs

    ban_moi = {"scenes": [{"text": "ban moi"}]}
    goc_gen, goc_review = gs.generate_script, gs.review_script

    async def gen_gia(**kwargs):
        return ban_moi

    async def review_gia(script, **kwargs):
        return {"quality_score": 82, "review_notes": []}

    gs.generate_script, gs.review_script = gen_gia, review_gia
    try:
        kb, rv = asyncio.run(
            gs.regenerate_if_low_quality(
                {"scenes": [{"text": "ban dau"}]},
                {"quality_score": 48, "review_notes": [{"issue_type": "weak_climax", "scene_index": 4, "message": "phẳng"}]},
                word_budget_hi=14,
                gen_kwargs={"topic": "x"},
            )
        )
    finally:
        gs.generate_script, gs.review_script = goc_gen, goc_review

    assert kb is ban_moi
    assert rv["regenerated"] is True and rv["previous_score"] == 48


def test_loi_o_luot_viet_lai_khong_lam_chet_request():
    """Lớp này là bonus, không phải đường sống của request — quota cạn thì trả bản đầu."""
    import asyncio

    from services import gemini_service as gs

    ban_dau = {"scenes": [{"text": "ban dau"}]}
    goc_gen = gs.generate_script

    async def gen_no(**kwargs):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    gs.generate_script = gen_no
    try:
        kb, rv = asyncio.run(
            gs.regenerate_if_low_quality(
                ban_dau,
                {"quality_score": 30, "review_notes": [{"issue_type": "weak_hook", "scene_index": 1, "message": "nhạt"}]},
                word_budget_hi=14,
                gen_kwargs={"topic": "x"},
            )
        )
    finally:
        gs.generate_script = goc_gen
    assert kb is ban_dau and rv["quality_score"] == 30


# ---------------------------------------------------------------------------
# 11. Hai prompt còn lại giờ cũng test được
# ---------------------------------------------------------------------------
def test_prompt_chia_canh_giu_hop_dong_nguyen_van():
    """Đây là đường có yêu cầu khắt khe nhất: lời của người dùng phải giữ 100%."""
    from services.gemini_service import build_split_system_prompt

    p = build_split_system_prompt(num_scenes=9)
    assert "CHÍNH XÁC 9 phân cảnh" in p
    assert "nguyên văn 100%" in p
    assert "KHÔNG tự bịa từ giật tít" in p
    # Cũng phải rẽ theo nguồn hình như generate_script.
    assert "CẤM mở đầu bằng thuật ngữ máy quay" in build_split_system_prompt(
        num_scenes=9, prefer_stock_video=True
    )


def test_prompt_narration_tu_anh_duoc_huong_luat_noi_dung_chung():
    """Đường photo_narration trước đây chỉ được dặn "văn nói, câu ngắn" nên lời bình ra
    kiểu chú thích album."""
    from services.gemini_service import build_photo_system_prompt

    p = build_photo_system_prompt(num_images=5, topic="Chuyến đi Đà Lạt")
    assert "CHÍNH XÁC 5 phân cảnh" in p
    assert "Đà Lạt" in p
    assert "SHOW, DON'T TELL" in p
    assert "CẤM khan hiếm giả" in p
    # Luật riêng của chế độ này: đừng tả lại thứ người xem đang nhìn thấy.
    assert "KHÔNG TỰ THẤY ĐƯỢC" in p
    for cum in CLICHE_PHRASES[:3]:
        assert cum in p


# ---------------------------------------------------------------------------
# 12. Hai báo động sai + rò keyword render, phát hiện từ kịch bản Gemini THẬT
# ---------------------------------------------------------------------------
def test_cta_cap_video_duoc_tinh_la_co_cta():
    """`resolve_outro_text()` đem `cta_text` ra làm chữ ở đuôi video.

    Kịch bản có cta_text thì video CÓ CTA, dù không cảnh nào chứa chữ 'like/share'. Đo trên
    kịch bản thật (Nhà Giả Kim, 90 điểm): note 'thiếu CTA' nổ trong khi
    cta_text='Hãy tìm đọc cuốn sách tuyệt vời này nhé!' đã sẵn sàng hiện ở outro.
    """
    from services.gemini_service import _local_review

    canh = [
        {"text": "Cậu bé chăn cừu từ bỏ sự bình yên."},
        {"text": "Hãy lắng nghe trái tim, vì kho báu lớn nhất nằm trong chính bạn."},
    ]
    co_cta = _local_review(canh, 20, cta_text="Hãy tìm đọc cuốn sách này nhé!")
    assert not [n for n in co_cta.review_notes if n.issue_type == "missing_cta"]

    # Không có cả hai thì vẫn phải bắt.
    khong_cta = _local_review(canh, 20, cta_text="")
    assert [n for n in khong_cta.review_notes if n.issue_type == "missing_cta"]


def test_base_ke_chuyen_cam_tuong_minh_keyword_render():
    """Đo trên kịch bản thật (tone storytelling + stock): 3/10 image_prompt vẫn kèm
    'photorealistic, 8k' / 'stock footage style'. Base chỉ dặn "tả cảnh quay thật" là chưa đủ.
    """
    prompt = build_script_system_prompt(num_scenes=10, narration_tone="storytelling")
    assert "CẤM các keyword render" in prompt
    for kw in ("8k", "photorealistic", "stock footage style", "Unreal Engine"):
        assert kw in prompt, kw


if __name__ == "__main__":
    ok = fail = 0
    for ten, fn in sorted(list(globals().items())):
        if ten.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
                print(f"  PASS  {ten}")
            except AssertionError as e:
                fail += 1
                print(f"  FAIL  {ten}: {e}")
    print(f"\n{ok} pass, {fail} fail")
    sys.exit(1 if fail else 0)
