"""
Test cho scene_balancer — chia lại ranh giới cảnh cho đều nhịp.

Chạy:  python tests/test_scene_balancer.py    (từ thư mục backend/)
       pytest tests/test_scene_balancer.py

Điều kiện SỐNG CÒN của tính năng này: không được làm mất chữ. Chia lại ranh giới mà
nuốt mất một câu thì video ra thiếu nội dung, và người dùng gần như không thể phát hiện
cho tới lúc xem lại bản render — nên đó là test đầu tiên ở đây.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import duration_model, scene_balancer as sb

# Ước lượng phải tiền đoán được thì mới viết được kỳ vọng cho test.
#
# CÁCH LÀM: trỏ hồ sơ tự học sang thư mục tạm rỗng. Hồ sơ rỗng → words_per_second()
# trả đúng BASE_WPS = 3.0, tức con số các test dưới đây trông đợi, mà vẫn chạy qua
# hàm THẬT chứ không phải một bản giả.
#
# LỖI CŨ: dòng này từng là `duration_model.words_per_second = lambda ...: 3.0` — ghi đè
# vĩnh viễn một hàm của module DÙNG CHUNG, ngay lúc import, không bao giờ trả lại. Chạy
# tay từng file (mỗi file một tiến trình) thì không ai thấy gì; nhưng `pytest tests/`
# nạp mọi file vào CÙNG một tiến trình, nên bản giả này đè luôn sang
# test_duration_model.py và làm 4 test tự học ở đó đỏ — trong khi lỗi thật sự nằm ở đây.
_TIMING_TMP = tempfile.mkdtemp(prefix="avm_balancer_timing_")
duration_model._profile_path = lambda: os.path.join(_TIMING_TMP, "timing_profile.json")
duration_model.reset_cache()

WORD = "từ"


def _scene(n: int, words: int, **extra) -> dict:
    """Một cảnh gồm `words` từ, chia thành các câu 6 từ để có chỗ mà cắt."""
    sentences = []
    remaining = words
    while remaining > 0:
        take = min(6, remaining)
        sentences.append(" ".join([WORD] * take) + ".")
        remaining -= take
    scene = {
        "scene": n,
        "text": " ".join(sentences),
        "image_prompt": f"prompt cảnh {n}",
        "emotion": "calm",
        "pause_after_ms": 0,
    }
    scene.update(extra)
    return scene


def _all_words(scenes) -> list[str]:
    return " ".join(s["text"] for s in scenes).split()


# ── Bất biến quan trọng nhất: không mất chữ ─────────────────────────────────
def test_khong_lam_mat_hay_doi_thu_tu_mot_chu_nao():
    scenes = [_scene(1, 33), _scene(2, 4), _scene(3, 40), _scene(4, 7)]

    out = sb.rebalance_scenes(scenes)["scenes"]

    assert _all_words(out) == _all_words(scenes), "chữ bị mất hoặc đảo thứ tự"


def test_khong_sua_doi_du_lieu_dau_vao():
    """Hàm trả ĐỀ XUẤT — user có thể bấm Huỷ, nên bản gốc phải nguyên vẹn."""
    scenes = [_scene(1, 30), _scene(2, 5)]
    snapshot = [dict(s) for s in scenes]

    sb.rebalance_scenes(scenes)

    assert scenes == snapshot, "đầu vào bị sửa tại chỗ"


# ── Chất lượng chia ─────────────────────────────────────────────────────────
def test_chia_deu_canh_qua_dai_va_qua_ngan():
    """Kịch bản lệch nặng: một cảnh 13 giây, một cảnh 1.3 giây."""
    scenes = [_scene(1, 40), _scene(2, 4), _scene(3, 40), _scene(4, 4)]

    result = sb.rebalance_scenes(scenes)
    before, after = result["report"]["before"], result["report"]["after"]

    assert after["off_pace"] < before["off_pace"], (
        f"số cảnh lệch nhịp không giảm: {before['off_pace']} → {after['off_pace']}"
    )
    assert after["longest"] <= before["longest"], "cảnh dài nhất không được dài thêm"
    assert after["std"] < before["std"], "độ lệch giữa các cảnh không giảm"


def test_moi_canh_nam_trong_nhip_xem_khi_co_the():
    """Kịch bản dễ chia (toàn câu 2 giây) thì kết quả không được còn cảnh nào lệch nhịp."""
    scenes = [_scene(i, 36) for i in range(1, 4)]

    result = sb.rebalance_scenes(scenes)

    assert result["report"]["after"]["off_pace"] == 0, result["report"]["groups"]


def test_giu_nguyen_kich_ban_da_deu():
    """Đã đều sẵn thì đừng xáo trộn — báo changed=False để UI không mời gọi vô ích."""
    scenes = [_scene(i, 13) for i in range(1, 6)]  # ~4.3s mỗi cảnh

    result = sb.rebalance_scenes(scenes)

    assert result["report"]["after"]["off_pace"] == 0
    assert len(result["scenes"]) == len(scenes)


def test_cat_menh_de_khi_cau_dai_co_dau_phay():
    """Câu 30 từ (10 giây) nhưng có dấu phẩy: phải cắt tại đó để không cảnh nào vượt trần."""
    clause = " ".join([WORD] * 10)
    scenes = [{"scene": 1, "image_prompt": "p", "pause_after_ms": 0,
               "text": f"{clause}, {clause}, {clause}."}]

    result = sb.rebalance_scenes(scenes)

    assert len(result["scenes"]) > 1, "câu dài có mệnh đề mà không được cắt"
    assert all(not g["too_long"] for g in result["report"]["groups"]), result["report"]["groups"]
    assert _all_words(result["scenes"]) == _all_words(scenes)


def test_khong_cat_menh_de_khi_cau_du_ngan():
    """Câu 12 từ có dấu phẩy vẫn phải giữ nguyên — cắt giữa câu tạo nhịp ngắt trong
    giọng đọc, chỉ chấp nhận khi không còn lựa chọn nào khác."""
    scenes = [{"scene": 1, "image_prompt": "p", "pause_after_ms": 0,
               "text": " ".join([WORD] * 6) + ", " + " ".join([WORD] * 6) + "."},
              {"scene": 2, "image_prompt": "p2", "pause_after_ms": 0,
               "text": " ".join([WORD] * 12) + "."}]

    result = sb.rebalance_scenes(scenes)

    assert all("," not in s["text"] or s["text"].strip().endswith(".")
               for s in result["scenes"]), "câu ngắn bị cắt rời tại dấu phẩy"
    assert len(result["scenes"]) == 2


def test_cau_dai_bat_kha_phan_khong_lam_chet_ham():
    """Một câu duy nhất dài 15 giây: không ranh giới nào cứu được. Phải trả kết quả kèm
    cờ too_long chứ KHÔNG được ném lỗi giữa lúc user đang chờ."""
    scenes = [{"scene": 1, "text": " ".join([WORD] * 45), "image_prompt": "p", "pause_after_ms": 0}]

    result = sb.rebalance_scenes(scenes)

    assert len(result["scenes"]) == 1
    assert result["report"]["groups"][0]["too_long"] is True


# ── Tôn trọng chủ ý của người dùng ──────────────────────────────────────────
def test_khong_gop_canh_co_anh_tu_upload():
    """override_asset = user đã tự tay gắn ảnh cho ĐÚNG đoạn lời này."""
    scenes = [_scene(1, 6), _scene(2, 5, override_asset="/anh/cua_toi.png"), _scene(3, 6)]

    out = sb.rebalance_scenes(scenes)["scenes"]

    giu = [s for s in out if s.get("override_asset") == "/anh/cua_toi.png"]
    assert len(giu) == 1, "cảnh có ảnh riêng bị gộp/nhân bản"
    assert giu[0]["text"] == scenes[1]["text"], "lời thoại của cảnh có ảnh riêng bị trộn"


def test_khong_tron_quote_card_vao_canh_ke_chuyen():
    scenes = [_scene(1, 8), {"scene": 2, "text": "", "scene_type": "quote_card",
                             "subtitle_text": "Một câu trích dẫn", "image_prompt": "p2"},
              _scene(3, 8)]

    out = sb.rebalance_scenes(scenes)["scenes"]

    quotes = [s for s in out if s.get("scene_type") == "quote_card"]
    assert len(quotes) == 1
    assert quotes[0]["subtitle_text"] == "Một câu trích dẫn"


def test_thua_ke_thuoc_tinh_cua_canh_chi_phoi():
    """Cảnh mới lấy image_prompt của cảnh gốc đóng góp NHIỀU THỜI LƯỢNG nhất, không
    phải cảnh đầu tiên chạm vào."""
    scenes = [_scene(1, 3, image_prompt="prompt ngắn"), _scene(2, 24, image_prompt="prompt dài")]

    out = sb.rebalance_scenes(scenes)["scenes"]

    assert out[0]["image_prompt"] == "prompt dài", (
        f"lấy nhầm prompt của cảnh phụ: {out[0]['image_prompt']}"
    )


def test_canh_bi_tach_duoc_doi_goc_may():
    """Một cảnh tách làm nhiều phần thì mọi phần thừa kế cùng image_prompt — ba ảnh sinh
    từ cùng mô tả sẽ nhìn như nhau, người xem tưởng video đứng hình."""
    scenes = [_scene(1, 60, image_prompt="a fisherman at dawn, 8k")]

    out = sb.rebalance_scenes(scenes)["scenes"]

    assert len(out) > 1, "cảnh 60 từ lẽ ra phải bị tách"
    prompts = [s["image_prompt"] for s in out]
    assert prompts[0] == "a fisherman at dawn, 8k", "phần đầu phải giữ nguyên prompt gốc"
    assert len(set(prompts)) == len(prompts), f"prompt bị trùng lặp: {prompts}"
    assert all(p.startswith("a fisherman at dawn") for p in prompts), "nội dung mô tả bị đổi"


def test_canh_gop_khong_bi_them_goc_may():
    """Chỉ cảnh BỊ TÁCH mới cần đổi góc; cảnh gộp vẫn dùng đúng một prompt như cũ."""
    scenes = [_scene(1, 4, image_prompt="prompt A"), _scene(2, 4, image_prompt="prompt B")]

    out = sb.rebalance_scenes(scenes)["scenes"]

    assert all("," not in s["image_prompt"] for s in out), (
        f"prompt bị thêm góc máy không cần thiết: {[s['image_prompt'] for s in out]}"
    )


def test_bo_subtitle_rieng_khi_da_tron_loi_cua_nhieu_canh():
    """subtitle_text mô tả riêng đoạn chữ cũ; giữ lại sau khi trộn thì phụ đề hiện một
    đằng, giọng đọc một nẻo."""
    scenes = [_scene(1, 4, subtitle_text="phụ đề cũ", highlight_text="từ khoá"),
              _scene(2, 4, subtitle_text="phụ đề khác")]

    out = sb.rebalance_scenes(scenes)["scenes"]

    tron = [s for s in out if s["text"].count(".") > 1]
    for s in tron:
        assert "subtitle_text" not in s, "phụ đề của đoạn chữ cũ còn sót lại sau khi trộn"


def test_pause_lay_theo_canh_chua_cau_cuoi():
    """pause_after_ms là khoảng lặng CUỐI cảnh — phải theo câu cuối nhóm, không theo
    cảnh chi phối."""
    scenes = [_scene(1, 24, pause_after_ms=0), _scene(2, 3, pause_after_ms=800)]

    out = sb.rebalance_scenes(scenes)["scenes"]

    assert out[-1]["pause_after_ms"] == 800


# ── Biên ────────────────────────────────────────────────────────────────────
def test_danh_sach_rong():
    result = sb.rebalance_scenes([])
    assert result["scenes"] == []
    assert result["report"]["changed"] is False


def test_canh_khong_co_loi_thoai():
    scenes = [{"scene": 1, "text": "", "image_prompt": "p"}]
    out = sb.rebalance_scenes(scenes)["scenes"]
    assert len(out) == 1


def test_khong_vuot_tran_so_canh():
    scenes = [_scene(i, 60) for i in range(1, 12)]  # rất dài, dễ bị chia vụn
    out = sb.rebalance_scenes(scenes)["scenes"]
    assert len(out) <= sb.MAX_SCENES


if __name__ == "__main__":
    from services.log_setup import force_utf8_streams
    force_utf8_streams()

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} test đạt")
    sys.exit(1 if failed else 0)
