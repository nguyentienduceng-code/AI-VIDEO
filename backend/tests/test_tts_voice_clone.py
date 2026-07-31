"""
Test cho phân hệ Giọng đọc: giọng clone (OmniVoice) và bản đọc liền mạch.

Chạy:  python tests/test_tts_voice_clone.py     (từ thư mục backend/)
       pytest tests/test_tts_voice_clone.py

KHÔNG test nào ở đây cần GPU, cần model OmniVoice, hay cần mạng: mọi thứ phụ thuộc
Edge-TTS/OmniVoice đều bị chặn bằng stub. Riêng bộ lọc FFmpeg của mẫu giọng thì chạy
FFMPEG THẬT trên file WAV tự dựng — kiểm chứng chuỗi filter "đúng cú pháp" mà không
render một lần là cách chắc chắn nhất để lọt một filtergraph hỏng vào nhánh chính.

Bốn lỗi thật mà bộ test này canh:
  1. `"male" in instruct` → "female, young adult, whisper" CHỨA "male", nên mọi giọng
     nữ đều rơi về giọng nam Nam Minh khi OmniVoice hỏng.
  2. Giọng clone bật "đọc liền mạch" bị ném NarrationSplitError → mất luôn chế độ
     hình-bám-theo-giọng, dù ghép từng cảnh hoàn toàn làm được.
  3. Sổ tra ngược cache nhận `**cache_params` — mà cache_params luôn có khoá "voice",
     trùng tham số đầu → TypeError bị nuốt trong try, sổ rỗng vĩnh viễn nên
     purge_voice_cache() không bao giờ xoá được gì.
  4. Mẫu giọng clone không gọt lặng/không chuẩn hoá độ to → OmniVoice sao chép cả tiếng
     ù và khoảng lặng thừa vào mọi cảnh của mọi video sau đó.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import imageio_ffmpeg

from services import tts_service as tts


# ──────────────────────────────────────────────────────────────────────
# 1. Giới tính & giọng đọc thay thế
# ──────────────────────────────────────────────────────────────────────

def test_gender_tu_instruct_khong_nham_female_thanh_male():
    """"female" chứa chuỗi con "male" — phải so khớp theo TOKEN, không phải substring."""
    assert tts._gender_from_instruct("female, young adult, whisper") == "Nữ"
    assert tts._gender_from_instruct("male, elderly, low pitch") == "Nam"
    # Tên preset dùng dấu gạch dưới cũng phải ra đúng
    assert tts._gender_from_instruct("omnivoice_female_child_vi") == "Nữ"
    assert tts._gender_from_instruct("omnivoice_male_podcast_vi") == "Nam"


def test_giong_thay_the_dung_gioi_tinh_cho_moi_preset():
    """Quét TOÀN BỘ bảng preset, không chỉ vài id chọn tay: thêm preset mới mà quên
    giới tính thì test này phải đỏ ngay."""
    for voice_id, instruct in tts.OMNIVOICE_MAPPING.items():
        mong_doi = "Nữ" if "female" in instruct else "Nam"
        edge_id, _, gender = tts.resolve_fallback_voice(voice_id)
        assert gender == mong_doi, f"{voice_id} ({instruct}) → {gender}, đáng lẽ {mong_doi}"
        assert edge_id == tts.FALLBACK_VOICE_BY_GENDER[mong_doi][0]


def test_giong_clone_tra_gioi_tinh_tu_registry():
    """
    Giọng clone không có token nào trong id (`omnivoice_custom_a1b2c3d4`) — thông tin
    giới tính DUY NHẤT nằm trong voices_custom.json.
    """
    with _tam_doi_registry():
        tts.register_custom_voice("omnivoice_custom_test1", "Anh Đức đọc truyện", "xin chào")
        assert tts.get_clone_gender("omnivoice_custom_test1") == "Nam"
        assert tts.resolve_fallback_voice("omnivoice_custom_test1")[0] == "vi-VN-NamMinhNeural"

        # gender truyền tường minh thắng phép suy từ tên
        tts.register_custom_voice("omnivoice_custom_test2", "Nam Phương", "xin chào", gender="female")
        assert tts.get_clone_gender("omnivoice_custom_test2") == "Nữ"
        assert tts.resolve_fallback_voice("omnivoice_custom_test2")[0] == "vi-VN-HoaiMyNeural"

        # Bản ghi CŨ chưa có trường gender (registry đã tồn tại trước bản vá này)
        voices = tts._load_custom_voices()
        for v in voices:
            v.pop("gender", None)
        tts._save_custom_voices(voices)
        assert tts.get_clone_gender("omnivoice_custom_test1") == "Nam"

        # Giọng không tồn tại → không được ném, chỉ trả mặc định
        assert tts.get_clone_gender("omnivoice_custom_khongcothat") == "Nữ"


def test_update_custom_voice_chi_ghi_de_truong_duoc_truyen():
    with _tam_doi_registry():
        tts.register_custom_voice("omnivoice_custom_upd", "Tên cũ", "lời mẫu cũ")

        entry = tts.update_custom_voice("omnivoice_custom_upd", name="Tên mới")
        assert entry["name"] == "Tên mới"
        assert entry["ref_text"] == "lời mẫu cũ", "không truyền transcript thì phải giữ nguyên"

        entry = tts.update_custom_voice("omnivoice_custom_upd", ref_text="lời mẫu mới")
        assert entry["name"] == "Tên mới"
        assert entry["ref_text"] == "lời mẫu mới"

        assert tts.update_custom_voice("omnivoice_custom_khongcothat", name="x") is None


# ──────────────────────────────────────────────────────────────────────
# 2. Sổ tra ngược cache của giọng clone
# ──────────────────────────────────────────────────────────────────────

def test_so_tra_cache_ghi_duoc_va_purge_xoa_dung_file():
    """
    Khoá cache là md5 của tham số → không suy ngược được từ voice_id ra tên file. Sổ tra
    ngược là thứ duy nhất cho phép xoá cache của một giọng. Test này khẳng định sổ THẬT
    SỰ có dữ liệu, chứ không chỉ "gọi hàm không nổ" — lỗi cũ nuốt TypeError trong khối
    try nên sổ luôn rỗng mà không ai biết.
    """
    with tempfile.TemporaryDirectory() as d:
        cache_dir = os.path.join(d, "cache")
        media_dir = os.path.join(cache_dir, "media")
        os.makedirs(media_dir)
        goc = (tts.CACHE_DIR, tts.MEDIA_CACHE_DIR, tts._VOICE_CACHE_INDEX_FILE)
        tts.CACHE_DIR, tts.MEDIA_CACHE_DIR = cache_dir, media_dir
        tts._VOICE_CACHE_INDEX_FILE = os.path.join(cache_dir, "tts_voice_cache_index.json")
        try:
            voice = "omnivoice_custom_abc123"
            params = dict(text="xin chào", voice=voice, rate="+0%", pitch="+0Hz",
                          emotion="", breathing=False)
            tts._index_voice_cache_entry(voice, "tts_meta", "tts", params)

            index = json.load(open(tts._VOICE_CACHE_INDEX_FILE, encoding="utf-8"))
            assert voice in index and index[voice], "sổ tra ngược rỗng — cache sẽ không bao giờ xoá được"
            meta_name, media_key = index[voice][0]

            # Dựng đúng 2 file mà cache_service sẽ tạo, rồi xem purge có tìm ra không
            open(os.path.join(cache_dir, meta_name), "w").write("{}")
            open(os.path.join(media_dir, media_key + ".mp3"), "wb").write(b"x")
            # File của giọng KHÁC phải còn nguyên
            open(os.path.join(media_dir, "tts_giongkhac.mp3"), "wb").write(b"x")

            assert tts.purge_voice_cache(voice) == 2
            assert not os.path.exists(os.path.join(cache_dir, meta_name))
            assert not os.path.exists(os.path.join(media_dir, media_key + ".mp3"))
            assert os.path.exists(os.path.join(media_dir, "tts_giongkhac.mp3"))
            assert json.load(open(tts._VOICE_CACHE_INDEX_FILE, encoding="utf-8")) == {}

            # Gọi lại trên giọng đã sạch: không nổ, không xoá nhầm gì
            assert tts.purge_voice_cache(voice) == 0
        finally:
            tts.CACHE_DIR, tts.MEDIA_CACHE_DIR, tts._VOICE_CACHE_INDEX_FILE = goc


def test_khong_ghi_so_tra_cho_giong_dung_san():
    """Giọng Edge-TTS không bao giờ đổi nội dung → không cần sổ, đừng làm nó phình."""
    with tempfile.TemporaryDirectory() as d:
        goc = tts._VOICE_CACHE_INDEX_FILE
        tts._VOICE_CACHE_INDEX_FILE = os.path.join(d, "index.json")
        try:
            tts._index_voice_cache_entry("vi-VN-HoaiMyNeural", "tts_meta", "tts", dict(voice="x"))
            assert not os.path.exists(tts._VOICE_CACHE_INDEX_FILE)
        finally:
            tts._VOICE_CACHE_INDEX_FILE = goc


# ──────────────────────────────────────────────────────────────────────
# 3. Đọc liền mạch cho giọng không hỗ trợ → ghép từng cảnh
# ──────────────────────────────────────────────────────────────────────

def test_giong_clone_khong_con_bi_chan_doc_lien_mach():
    """
    LỖI CŨ: `raise NarrationSplitError` ngay khi thấy giọng omnivoice_*. Giờ phải ra
    một dải audio thật + word boundaries MỐC TUYỆT ĐỐI tăng dần theo cảnh.
    """
    with tempfile.TemporaryDirectory() as d:
        canh = ["Cảnh một nói về tiền.", "Cảnh hai nói về thời gian.", "", "Cảnh bốn kết lại."]
        out = os.path.join(d, "narration_master.mp3")

        canh_da_sinh = []

        async def _stub_synthesize_speech(text, output_path, **kw):
            """Giả lập TTS: ghi ra file WAV thật 1.5s để FFmpeg còn có cái mà ghép."""
            canh_da_sinh.append(text)
            wav = os.path.splitext(output_path)[0] + ".wav"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-t", "1.5",
                 "-i", "sine=frequency=300:sample_rate=24000", "-ac", "1", wav],
                check=True, capture_output=True,
            )
            wbs = [{"offset": 0.5 * i, "duration": 0.4, "text": w}
                   for i, w in enumerate(text.split()[:3])]
            return 1.5, wbs

        # Gọi qua ĐÚNG cửa công khai mà main.py dùng — chính chỗ trước đây ném
        # NarrationSplitError. Test thẳng vào hàm ghép nối bên trong sẽ xanh cả khi cửa
        # ngoài vẫn chặn, tức không canh được gì.
        goc_tts = tts.synthesize_speech
        tts.synthesize_speech = _stub_synthesize_speech
        with _tam_doi_cache(d):
            try:
                dur, scene_wbs, dur2 = asyncio.run(tts.synthesize_script_single_pass(
                    canh, out, voice="omnivoice_custom_abc", rate="+0%", pitch="+0Hz"
                ))
            finally:
                tts.synthesize_speech = goc_tts
        assert dur2 == dur, "tham số thứ ba của hợp đồng trả về phải là tổng thời lượng"

        assert len(canh_da_sinh) == 3, "cảnh rỗng không được gọi TTS"
        assert os.path.isfile(out) and os.path.getsize(out) > 0, "phải ra một dải audio thật"
        assert len(scene_wbs) == len(canh), "phải trả đúng số bucket bằng số cảnh"
        assert scene_wbs[2] == [], "cảnh không lời → bucket rỗng, KHÔNG được lệch chỉ số"

        # Mốc phải TUYỆT ĐỐI (cộng dồn), không phải mốc tương đối của từng cảnh
        assert scene_wbs[0][0]["offset"] == 0.0
        assert scene_wbs[1][0]["offset"] > scene_wbs[0][-1]["offset"], "cảnh 2 phải nằm sau cảnh 1"
        assert scene_wbs[3][0]["offset"] > scene_wbs[1][-1]["offset"]

        cuoi = scene_wbs[3][-1]["offset"] + scene_wbs[3][-1]["duration"]
        assert cuoi <= dur + 0.5, f"mốc cuối {cuoi:.2f}s vượt quá thời lượng dải giọng {dur:.2f}s"

        # 3 đoạn 1.5s + 2 khoảng nghỉ, đo trên FILE THẬT chứ không cộng ước lượng
        du_kien = 3 * 1.5 + 2 * tts.NARRATION_SCENE_GAP
        assert abs(dur - du_kien) < 0.4, f"thời lượng {dur:.2f}s lệch quá xa {du_kien:.2f}s"


def test_giong_edge_van_di_duong_doc_lien_mach_mot_lan():
    """Bản vá không được kéo giọng Edge-TTS sang đường ghép nối (mất nhịp thở liên tục)."""
    goi = {"plain": 0, "per_scene": 0}

    async def _stub_plain(text, output_path, voice, rate, pitch):
        goi["plain"] += 1
        open(output_path, "wb").write(b"x")
        wbs, cursor = [], 0.0
        for w in text.split():
            wbs.append({"offset": cursor, "duration": 0.3, "text": w.strip(".,!?")})
            cursor += 0.3
        return cursor, wbs

    async def _stub_per_scene(*a, **kw):
        goi["per_scene"] += 1
        return 1.0, [[]]

    goc = (tts._synthesize_plain, tts._synthesize_script_per_scene_concat)
    tts._synthesize_plain = _stub_plain
    tts._synthesize_script_per_scene_concat = _stub_per_scene
    try:
        with tempfile.TemporaryDirectory() as d, _tam_doi_cache(d):
            asyncio.run(tts.synthesize_script_single_pass(
                ["Cảnh một nói về tiền bạc.", "Cảnh hai nói về thời gian."],
                os.path.join(d, "m.mp3"), voice="vi-VN-HoaiMyNeural",
            ))
    finally:
        tts._synthesize_plain, tts._synthesize_script_per_scene_concat = goc

    assert goi["plain"] == 1, "giọng Edge phải gọi ĐÚNG MỘT LẦN cho cả bài"
    assert goi["per_scene"] == 0, "giọng Edge không được rơi vào đường ghép từng cảnh"


# ──────────────────────────────────────────────────────────────────────
# 4. Bộ lọc mẫu giọng clone — CHẠY FFMPEG THẬT
# ──────────────────────────────────────────────────────────────────────

def test_bo_loc_mau_giong_got_lang_va_chuan_hoa_do_to():
    """
    Dựng một mẫu "bẩn" (lặng đầu + lặng đuôi + tiếng ù 50Hz), chạy đúng chuỗi filter mà
    /api/voice-clone dùng, rồi đo lại. Không có bước render này thì một filtergraph sai
    cú pháp chỉ lộ ra khi người dùng thật tải mẫu lên.
    """
    import main   # import muộn: main.py kéo theo cả FastAPI app

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as d:
        ban = os.path.join(d, "ban.wav")
        sach = os.path.join(d, "sach.wav")
        # 2s lặng + 5s "giọng" (sine 200Hz, to vừa) + 3s lặng, trộn thêm ù 50Hz
        subprocess.run(
            [ff, "-y",
             "-f", "lavfi", "-t", "2", "-i", "anullsrc=r=24000:cl=mono",
             "-f", "lavfi", "-t", "5", "-i", "sine=frequency=200:sample_rate=24000",
             "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=24000:cl=mono",
             "-f", "lavfi", "-t", "10", "-i", "sine=frequency=50:sample_rate=24000",
             "-filter_complex",
             "[0:a][1:a][2:a]concat=n=3:v=0:a=1[j];[3:a]volume=0.3[h];"
             "[j][h]amix=inputs=2:duration=first:normalize=0,volume=0.2[o]",
             "-map", "[o]", "-ac", "1", "-ar", "24000", ban],
            check=True, capture_output=True,
        )
        assert 9.5 < tts._probe_audio_duration(ban) < 10.5

        r = subprocess.run(
            [ff, "-y", "-i", ban, "-af", main.VOICE_SAMPLE_FILTERS,
             "-t", str(main.VOICE_SAMPLE_MAX_SECONDS), "-ar", "24000", "-ac", "1", sach],
            capture_output=True, text=True, errors="replace",
        )
        assert r.returncode == 0, f"filtergraph hỏng:\n{r.stderr[-800:]}"

        con_lai = tts._probe_audio_duration(sach)
        assert 4.0 < con_lai < 6.0, (
            f"còn {con_lai:.2f}s — 5 giây lặng hai đầu chưa bị gọt "
            "(kiểm tra cặp areverse quanh silenceremove)"
        )

        # loudnorm phải kéo về quanh -16 LUFS
        v = subprocess.run([ff, "-hide_banner", "-i", sach, "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True, errors="replace")
        dong_I = [l for l in v.stderr.splitlines() if "I:" in l and "LUFS" in l]
        assert dong_I, "không đọc được số đo ebur128"
        lufs = float(dong_I[-1].split("I:")[1].split("LUFS")[0].strip())
        assert -19 < lufs < -13, f"độ to sau chuẩn hoá là {lufs} LUFS, lệch xa mốc -16"


def test_do_giay_tieng_noi_tru_khoang_lang_ben_trong():
    """
    Mẫu 2 giây nói + 6 giây im + 2 giây nói dài 10 giây nhưng chỉ có 4 giây tiếng nói.
    Cửa chặn tối thiểu phải nhìn vào con số thứ hai, nếu không mẫu rác vẫn lọt.
    """
    import main

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "ho.wav")
        subprocess.run(
            [ff, "-y",
             "-f", "lavfi", "-t", "2", "-i", "sine=frequency=200:sample_rate=24000",
             "-f", "lavfi", "-t", "6", "-i", "anullsrc=r=24000:cl=mono",
             "-f", "lavfi", "-t", "2", "-i", "sine=frequency=200:sample_rate=24000",
             "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[o]",
             "-map", "[o]", "-ac", "1", "-ar", "24000", f],
            check=True, capture_output=True,
        )
        tong = tts._probe_audio_duration(f)
        noi = main._measure_speech_seconds(f)
        assert 9.5 < tong < 10.5, f"file mẫu dựng sai: {tong}s"
        assert 3.0 < noi < 5.0, f"đo được {noi:.2f}s tiếng nói, đáng lẽ ~4s (đang tính cả quãng im?)"


# ──────────────────────────────────────────────────────────────────────
# 5. Cặp (file mẫu, transcript) — nguyên nhân gốc của "đọc không hiểu tiếng Việt"
# ──────────────────────────────────────────────────────────────────────

def test_cat_mau_giong_uu_tien_cho_ket_thuc_TRON_MOT_CAU():
    """
    OmniVoice coi ref_text là phần mở đầu rồi đọc TIẾP sang văn bản đích. Mẫu dừng giữa
    câu = mời mô hình nói nốt câu dở đó.

    ĐÃ ĐO ĐƯỢC THẬT trên giọng nuxuxu: mẫu cắt cứng đúng 10.0s làm transcript kết thúc
    lửng ("...chuyển đến sống tại thành phố"), và bản đọc ra bắt đầu bằng rác lấy từ
    chính file mẫu — "giúp đỡ các phòng phố, 99% người tích góp tiền..." — trước khi vào
    nội dung cần đọc.

    Whisper cắt đoạn theo ~5 giây chứ KHÔNG theo ngữ pháp, nên đoạn cuối trong khoảng
    cho phép thường kết thúc lửng; phải ưu tiên đoạn thật sự có dấu kết câu.
    """
    cau = [
        {"start": 0.0, "end": 4.9, "text": "Sự trăn trở của tôi bắt đầu từ lúc tôi còn nhỏ."},
        {"start": 4.9, "end": 8.8, "text": "khoảng mùa hè năm ấy khi gia đình tô"},   # lửng
    ]
    cat, text = tts.chon_diem_cat_mau(cau, toi_da=10.0, toi_thieu=3.0)
    assert cat == 4.9, f"cắt tại {cat}s — đã lấy đoạn kết thúc lửng thay vì câu trọn vẹn"
    assert text.endswith("."), f"transcript kết thúc lửng: {text!r}"

    # Có hai câu trọn vẹn thì lấy câu SAU (mẫu dài hơn, vẫn trong trần)
    cau2 = cau + [{"start": 8.8, "end": 9.5, "text": "Và mọi thứ thay đổi từ đó."}]
    cat2, text2 = tts.chon_diem_cat_mau(cau2, toi_da=10.0, toi_thieu=3.0)
    assert cat2 == 9.5 and text2.endswith("thay đổi từ đó.")


def test_cat_mau_giong_khong_co_dau_ket_cau_thi_lay_ranh_gioi_doan():
    """Không đoạn nào có dấu kết câu thì vẫn phải cắt được, chỉ là kém lý tưởng hơn."""
    cau = [
        {"start": 0.0, "end": 4.0, "text": "một đoạn không có dấu chấm"},
        {"start": 4.0, "end": 7.0, "text": "đoạn thứ hai cũng vậy"},
    ]
    cat, text = tts.chon_diem_cat_mau(cau, toi_da=10.0, toi_thieu=3.0)
    assert cat == 7.0
    assert "đoạn thứ hai" in text


def test_cat_mau_giong_cac_truong_hop_bien():
    """Mẫu quá ngắn / câu đầu đã quá dài / không chép được lời — không cái nào được nổ."""
    # Không chép được lời → báo cho phía gọi tự cắt cứng
    assert tts.chon_diem_cat_mau([], 10.0, 3.0) == (None, "")

    # Ngay câu đầu đã vượt trần → không có mốc nào dùng được
    dai = [{"start": 0.0, "end": 14.0, "text": "một câu dài hơn cả trần cho phép."}]
    assert tts.chon_diem_cat_mau(dai, 10.0, 3.0) == (None, "")

    # Cả bài ngắn hơn sàn → vẫn lấy trọn câu đầu, còn hơn trả về rỗng
    ngan = [{"start": 0.0, "end": 2.0, "text": "Ngắn thôi."}]
    cat, text = tts.chon_diem_cat_mau(ngan, 10.0, 3.0)
    assert cat == 2.0 and text == "Ngắn thôi."


def test_do_khop_transcript_phan_biet_nghe_nham_voi_sai_han_noi_dung():
    """
    Ngưỡng phải tách được HAI trường hợp rất khác nhau:
      • whisper nghe nhầm vài chữ → CHO QUA (chỉ lệch phát âm chút ít);
      • transcript của một đoạn ghi âm KHÁC → CHẶN (giọng sẽ đọc ra vô nghĩa).

    Hai chuỗi dùng ở đây là dữ liệu THẬT lấy từ giọng clone bị hỏng trong dự án.
    """
    ghi_am_that = ("Hãy yêu thương bản thuân như cách đất tròi nâng nưu từng thiên nắng, "
                   "như cách cơn mơ nhẹ nhàng tưới mát những cánh đồng khô canh.")
    transcript_sai = ("Chào các bạn, tôi là Nam Tiến Đức. Đây là phần mềm AI Video Maker "
                      "do chính tôi phát triển, giúp tự động hóa hoàn toàn quy trình.")
    assert tts.transcript_similarity(transcript_sai, ghi_am_that) < tts.MIN_REF_TEXT_MATCH

    goc = "Sự trăn trở của tôi về hai câu hỏi này bắt đầu từ lúc tôi còn nhỏ."
    nghe_nham = "Sự tranh trở của tôi về hai câu hỏi này bắt đầu từ lúc tới còn nhỏ."
    assert tts.transcript_similarity(goc, nghe_nham) >= tts.MIN_REF_TEXT_MATCH

    assert tts.transcript_similarity("", "gì đó") == 0.0
    assert tts.transcript_similarity(goc, goc) == 1.0


def test_tu_chua_transcript_lech_va_khong_chep_loi_lai_lan_sau():
    """
    `ensure_clone_ref_text` phải: phát hiện lệch → THAY bằng lời chép từ file mẫu →
    ghi điểm để lần sau khỏi chạy whisper nữa (whisper mất vài giây mỗi lần gọi).
    """
    so_lan_chep = {"n": 0}

    def _stub_transcribe(path):
        so_lan_chep["n"] += 1
        return "Hãy yêu thương bản thân như cách đất trời nâng niu từng tia nắng."

    goc = tts.transcribe_vietnamese
    tts.transcribe_vietnamese = _stub_transcribe
    try:
        with _tam_doi_registry():
            tts.register_custom_voice("omnivoice_custom_lech", "Anh A",
                                      "Chào các bạn, tôi là Nam Tiến Đức, phần mềm này giúp tự động hóa.")
            ref_text, canh_bao = tts.ensure_clone_ref_text("omnivoice_custom_lech", "khong-quan-trong.wav")
            assert "yêu thương bản thân" in ref_text, "phải thay bằng lời THẬT của file mẫu"
            assert canh_bao and "KHÔNG khớp" in canh_bao, "phải báo cho user biết"
            assert tts.get_custom_voice("omnivoice_custom_lech")["ref_text"] == ref_text, "phải ghi vào registry"

            # Lần hai: đã có điểm đối chiếu → không được chạy whisper nữa
            ref_text2, canh_bao2 = tts.ensure_clone_ref_text("omnivoice_custom_lech", "khong-quan-trong.wav")
            assert ref_text2 == ref_text and canh_bao2 is None
            assert so_lan_chep["n"] == 1, f"chép lời {so_lan_chep['n']} lần, đáng lẽ đúng 1"
    finally:
        tts.transcribe_vietnamese = goc


def test_transcript_khop_thi_giu_nguyen_cua_user():
    """Whisper nghe nhầm vài chữ KHÔNG được phép ghi đè bản user gõ tay."""
    goc = tts.transcribe_vietnamese
    tts.transcribe_vietnamese = lambda p: "Sự tranh trở của tôi về hai câu hỏi này bắt đầu từ lúc tới còn nhỏ."
    try:
        with _tam_doi_registry():
            dung = "Sự trăn trở của tôi về hai câu hỏi này bắt đầu từ lúc tôi còn nhỏ."
            tts.register_custom_voice("omnivoice_custom_khop", "Chị B", dung)
            ref_text, canh_bao = tts.ensure_clone_ref_text("omnivoice_custom_khop", "x.wav")
            assert ref_text == dung, "bản user gõ tay phải được giữ"
            assert canh_bao is None
            assert tts.get_custom_voice("omnivoice_custom_khop")["ref_text_match"] >= tts.MIN_REF_TEXT_MATCH
    finally:
        tts.transcribe_vietnamese = goc


def test_doi_transcript_lam_mat_hieu_luc_diem_doi_chieu_cu():
    """Sửa transcript mà giữ lại điểm cũ = cửa đối chiếu bị vô hiệu vĩnh viễn."""
    with _tam_doi_registry():
        tts.register_custom_voice("omnivoice_custom_x", "Anh C", "lời ban đầu")
        tts.update_custom_voice("omnivoice_custom_x", ref_text_match=0.95)
        assert tts.get_custom_voice("omnivoice_custom_x")["ref_text_match"] == 0.95

        tts.update_custom_voice("omnivoice_custom_x", ref_text="lời hoàn toàn khác")
        assert "ref_text_match" not in tts.get_custom_voice("omnivoice_custom_x")

        # Trừ khi điểm mới được đo lại cùng lúc
        tts.update_custom_voice("omnivoice_custom_x", ref_text="lời mới nữa", ref_text_match=1.0)
        assert tts.get_custom_voice("omnivoice_custom_x")["ref_text_match"] == 1.0


# ──────────────────────────────────────────────────────────────────────
# 6. Đọc số bằng chữ cho OmniVoice
# ──────────────────────────────────────────────────────────────────────

def test_doc_so_tieng_viet_dung_luat_muoi_lam_hai_muoi_mot():
    """
    Ba cái bẫy của tiếng Việt mà bảng tra thẳng không xử lý được:
    "mười lăm" (không phải "mười năm" = 10 năm), "hai mươi mốt", và "lẻ".
    """
    v = tts.vi_number_to_words
    assert v(15) == "mười lăm"
    assert v(25) == "hai mươi lăm"
    assert v(21) == "hai mươi mốt"
    assert v(101) == "một trăm lẻ một"
    assert v(110) == "một trăm mười"
    assert v(1943) == "một nghìn chín trăm bốn mươi ba"
    assert v(1_500_000) == "một triệu năm trăm nghìn"
    assert v(0) == "không"


def test_chuan_hoa_so_va_ky_hieu_trong_kich_ban():
    """
    OmniVoice KHÔNG có bộ chuẩn hoá số cho tiếng Việt (README: chỉ zh/en, còn lại rơi
    về num2words — gói này không có trong dự án). Không tự làm thì "99%" đọc sai.
    """
    n = tts.normalize_vi_numbers
    assert n("99% người tích góp tiền.") == "chín mươi chín phần trăm người tích góp tiền."
    assert n("chứng kiến 40 năm.") == "chứng kiến bốn mươi năm."
    assert "một triệu năm trăm nghìn" in n("Giá 1.500.000 đồng.")      # dấu chấm = phân cách nghìn
    assert "ba phẩy năm" in n("Tăng 3,5 lần.")                          # dấu phẩy = thập phân
    assert n("Không có số nào cả.") == "Không có số nào cả."


def test_omnivoice_luon_gui_kem_ma_ngon_ngu_va_bo_cat_mau_thu_cong():
    """
    Canh bốn thay đổi cấu trúc, mỗi cái đều đã đo được tác dụng thật:
      • `language="vi"` — thiếu nó model chạy chế độ language-agnostic, đọc lệch âm;
      • KHÔNG tự tách câu / cắt mẩu — OmniVoice tự chia đoạn giữ được ngữ cảnh;
      • KHÔNG gọt lặng bằng librosa — model đã fade 0.1s hai đầu, gọt đè lên là cụt
        phụ âm đầu;
      • đọc số bằng chữ trước khi gửi.
    """
    import inspect
    src = inspect.getsource(tts._synthesize_omnivoice)
    assert "language=OMNIVOICE_LANG" in src, "quên gửi mã ngôn ngữ cho OmniVoice"
    assert "normalize_vi_numbers" in src, "quên đọc số bằng chữ"
    assert "ensure_clone_ref_text" in src, "quên đối chiếu cặp (file mẫu, transcript)"
    assert "_trim_tts_silence" not in src, "đang gọt lặng đè lên phần fade của model"
    assert "_split_sentence_for_tts" not in src, "đang tự cắt mẩu thay vì để model tự chia"
    assert tts.OMNIVOICE_LANG == "vi"


# ──────────────────────────────────────────────────────────────────────
# 7. Đệm prompt giọng (VoiceClonePrompt)
# ──────────────────────────────────────────────────────────────────────

class _PromptGia:
    """Bắt chước hợp đồng của VoiceClonePrompt: có `.save(path)` ghi ra file."""

    def __init__(self, ref_text, lan):
        self.tokens, self.lan = f"encoded::{ref_text}", lan

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.tokens)


class _ModelGia:
    """Giả lập OmniVoice: chỉ đếm số lần bị bắt mã hoá lại file mẫu."""

    def __init__(self):
        self.so_lan = 0

    def create_voice_clone_prompt(self, ref_audio, ref_text):
        self.so_lan += 1
        return _PromptGia(ref_text, self.so_lan)


def _dung_thu_muc_preview_tam(base):
    """Trỏ VOICES_PREVIEW_DIR sang thư mục tạm (prompt .pt được ghi vào đây)."""
    goc = tts.VOICES_PREVIEW_DIR
    tts.VOICES_PREVIEW_DIR = base
    tts._voice_prompt_cache.clear()
    return goc


def test_prompt_giong_chi_ma_hoa_mot_lan_cho_ca_video():
    """
    Mỗi cảnh gọi generate() một lần; nếu lần nào cũng mã hoá lại file mẫu thì video 20
    cảnh trả giá 20 lần cho một kết quả không đổi.
    """
    with tempfile.TemporaryDirectory() as d:
        goc = _dung_thu_muc_preview_tam(d)
        try:
            ref = os.path.join(d, "v_ref.wav")
            open(ref, "wb").write(b"\0" * 2048)
            m = _ModelGia()
            for _ in range(5):     # 5 cảnh
                p = tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu")
                assert p is not None
            assert m.so_lan == 1, f"mã hoá {m.so_lan} lần cho 5 cảnh, đáng lẽ đúng 1"
        finally:
            tts.VOICES_PREVIEW_DIR = goc
            tts._voice_prompt_cache.clear()


def test_prompt_giong_song_qua_lan_khoi_dong_lai():
    """Bản lưu .pt phải dùng lại được ở tiến trình sau (đệm RAM đã mất)."""
    with tempfile.TemporaryDirectory() as d:
        goc = _dung_thu_muc_preview_tam(d)
        try:
            ref = os.path.join(d, "v_ref.wav")
            open(ref, "wb").write(b"\0" * 2048)
            m = _ModelGia()
            tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu")
            assert os.path.isfile(tts._voice_prompt_path("omnivoice_custom_v")), "chưa lưu prompt xuống đĩa"
            # Bản .pt do torch ghi — ở đây model giả trả dict nên chỉ kiểm tra dấu vân tay
            assert os.path.isfile(tts._voice_prompt_path("omnivoice_custom_v") + ".fingerprint")
        finally:
            tts.VOICES_PREVIEW_DIR = goc
            tts._voice_prompt_cache.clear()


def test_doi_transcript_thi_prompt_cu_phai_bi_bo():
    """
    ref_text được NƯỚNG SẴN vào prompt (xem class VoiceClonePrompt). Dùng lại prompt cũ
    sau khi sửa transcript = quay lại đúng lỗi cặp lệch vừa sửa xong.
    """
    with tempfile.TemporaryDirectory() as d:
        goc = _dung_thu_muc_preview_tam(d)
        try:
            ref = os.path.join(d, "v_ref.wav")
            open(ref, "wb").write(b"\0" * 2048)
            m = _ModelGia()
            p1 = tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu cũ")
            p2 = tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu MỚI")
            assert m.so_lan == 2, "đổi ref_text mà vẫn xài prompt cũ"
            assert p1.tokens != p2.tokens
        finally:
            tts.VOICES_PREVIEW_DIR = goc
            tts._voice_prompt_cache.clear()


def test_thay_file_mau_thi_prompt_cu_phai_bi_bo():
    """Upload lại mẫu giọng khác mà vẫn dùng prompt cũ = clone ra giọng người khác."""
    with tempfile.TemporaryDirectory() as d:
        goc = _dung_thu_muc_preview_tam(d)
        try:
            ref = os.path.join(d, "v_ref.wav")
            open(ref, "wb").write(b"\0" * 2048)
            m = _ModelGia()
            tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu")
            open(ref, "wb").write(b"\1" * 4096)          # file mẫu mới, kích thước khác
            tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu")
            assert m.so_lan == 2, "thay file mẫu mà vẫn xài prompt cũ"
        finally:
            tts.VOICES_PREVIEW_DIR = goc
            tts._voice_prompt_cache.clear()


def test_bao_tien_do_truoc_moi_canh_va_bo_qua_canh_khong_loi():
    """
    Với giọng AI, mỗi cảnh mất hàng chục giây — không báo tiến độ thì user nhìn màn hình
    đứng im hơn mười phút và tưởng máy treo.

    Hai điều kiện: báo TRƯỚC khi sinh (báo sau thì suốt lúc chờ vẫn hiện cảnh cũ), và
    KHÔNG báo cho cảnh không có lời (chúng bị bỏ qua, báo vào là số đếm nhảy cóc).
    """
    moc = []

    async def _tien_do(i, n):
        moc.append((i, n))

    async def _stub(text, output_path, **kw):
        # Nếu tiến độ báo SAU khi sinh thì lúc này moc đã có phần tử của chính cảnh này
        assert moc, "chưa báo tiến độ trước khi sinh cảnh"
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-t", "0.4",
             "-i", "sine=frequency=300:sample_rate=24000", "-ac", "1",
             os.path.splitext(output_path)[0] + ".wav"],
            check=True, capture_output=True,
        )
        return 0.4, [{"offset": 0.0, "duration": 0.2, "text": "x"}]

    goc = tts.synthesize_speech
    tts.synthesize_speech = _stub
    try:
        with tempfile.TemporaryDirectory() as d:
            asyncio.run(tts._synthesize_script_per_scene_concat(
                ["Cảnh một.", "", "Cảnh ba.", "   "], os.path.join(d, "m.mp3"),
                "omnivoice_custom_x", "+0%", "+0Hz", progress_callback=_tien_do,
            ))
    finally:
        tts.synthesize_speech = goc

    assert [i for i, _ in moc] == [0, 2], f"báo tiến độ sai cảnh: {moc}"
    assert all(n == 4 for _, n in moc), "tổng số cảnh báo về phải là tổng THẬT"


def test_loi_trong_progress_callback_khong_giet_ca_ban_doc():
    """Giao diện ngắt kết nối giữa chừng không được phép làm mất cả bản đọc đã sinh."""
    async def _no(i, n):
        raise RuntimeError("WebSocket đã đóng")

    async def _stub(text, output_path, **kw):
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-t", "0.4",
             "-i", "sine=frequency=300:sample_rate=24000", "-ac", "1",
             os.path.splitext(output_path)[0] + ".wav"],
            check=True, capture_output=True,
        )
        return 0.4, [{"offset": 0.0, "duration": 0.2, "text": "x"}]

    goc = tts.synthesize_speech
    tts.synthesize_speech = _stub
    try:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.mp3")
            dur, wbs = asyncio.run(tts._synthesize_script_per_scene_concat(
                ["Cảnh một.", "Cảnh hai."], out, "omnivoice_custom_x", "+0%", "+0Hz",
                progress_callback=_no,
            ))
            assert dur > 0 and tts._resolve_written_path(out)
    finally:
        tts.synthesize_speech = goc


def test_pham_vi_cache_cua_ban_doc_ca_bai():
    """
    Nút "Nghe thử cả bài" hứa gì với user phụ thuộc hoàn toàn vào chỗ này.

    Giọng AI sinh TỪNG cảnh rồi ghép → mỗi cảnh một mục cache → render kiểu nào cũng
    tái dùng được. Giọng Edge gọi MỘT lần cho cả bài → chỉ một mục cache chung → chỉ
    dùng lại khi render bật "Đọc liền mạch". Nhầm chỗ này là giao diện tô xanh hết đèn
    rồi user ngồi chờ sinh lại từ đầu.
    """
    assert tts.narration_cache_scope("omnivoice_custom_abc") == "per_scene"
    assert tts.narration_cache_scope("omnivoice_male_podcast_vi") == "per_scene"
    assert tts.narration_cache_scope("minion") == "per_scene"
    assert tts.narration_cache_scope("vi-VN-HoaiMyNeural") == "full_narration"
    assert tts.narration_cache_scope("vi-VN-NamMinhNeural") == "full_narration"


def test_ghep_tung_canh_dung_text_THO_de_trung_khoa_cache_voi_luc_render():
    """
    Đường render từng cảnh truyền text THÔ vào synthesize_speech; khoá cache tính trên
    chuỗi nhận vào. Nếu nhánh ghép nối chuẩn hoá text trước khi truyền thì hai bên ra
    hai khoá khác nhau — nghe thử xong render vẫn sinh lại từ đầu, mất trắng công chờ
    (với giọng AI trên GPU là mất hàng chục phút).
    """
    nhan_duoc = []

    async def _stub(text, output_path, **kw):
        nhan_duoc.append(text)
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-t", "0.5",
             "-i", "sine=frequency=300:sample_rate=24000", "-ac", "1",
             os.path.splitext(output_path)[0] + ".wav"],
            check=True, capture_output=True,
        )
        return 0.5, [{"offset": 0.0, "duration": 0.3, "text": "x"}]

    tho = "Câu có   khoảng trắng thừa và dấu — gạch dài."
    goc = tts.synthesize_speech
    tts.synthesize_speech = _stub
    try:
        with tempfile.TemporaryDirectory() as d:
            asyncio.run(tts._synthesize_script_per_scene_concat(
                [tho], os.path.join(d, "m.mp3"), "omnivoice_custom_x", "+0%", "+0Hz"
            ))
    finally:
        tts.synthesize_speech = goc

    assert nhan_duoc == [tho], (
        f"đã chuẩn hoá text trước khi truyền ({nhan_duoc!r}) → khoá cache lệch với lúc render"
    )


def test_uoc_tinh_thoi_gian_chi_bao_khi_may_that_su_cham():
    """
    Chỉ nói khi có SỐ ĐO và số đó đáng lo. Máy nhanh mà vẫn dội cảnh báo "sẽ mất N phút"
    thì user học cách bỏ qua mọi thông báo.
    """
    goc = (tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc)
    try:
        tts._omnivoice_rtf_da_doc = True          # chặn việc nạp số đo thật của máy
        tts._omnivoice_rtf = None
        assert tts.uoc_tinh_thoi_gian_giong_ai(90) is None, "chưa đo được thì đừng đoán bừa"

        tts._omnivoice_rtf = 0.5                       # GPU mạnh, nhanh hơn thời gian thực
        assert tts.uoc_tinh_thoi_gian_giong_ai(90) is None

        tts._omnivoice_rtf = 8.3                       # số đo thật trên GTX 1660 SUPER
        msg = tts.uoc_tinh_thoi_gian_giong_ai(90)
        assert msg and "12 phút" in msg, f"ước tính sai: {msg}"
    finally:
        tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = goc


def test_rtf_nho_qua_lan_khoi_dong_lai():
    """
    Không lưu xuống đĩa thì sau mỗi lần khởi động lại backend, lần nghe thử ĐẦU TIÊN
    không có ước tính thời gian — đúng lúc user cần nhất, vì đó là lần chờ lâu nhất.
    """
    with tempfile.TemporaryDirectory() as d:
        goc_file, goc_rtf, goc_co = tts._RTF_FILE, tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc
        tts._RTF_FILE = os.path.join(d, "omnivoice_rtf.json")
        try:
            tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = None, True
            tts._ghi_nhan_rtf(93.0, 11.2)
            assert os.path.isfile(tts._RTF_FILE), "chưa ghi số đo xuống đĩa"

            # Mô phỏng tiến trình mới: quên sạch trong RAM, phải đọc lại được từ đĩa
            tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = None, False
            assert round(tts.get_omnivoice_rtf(), 1) == 8.3

            # File hỏng KHÔNG được làm chết đường sinh giọng, chỉ mất ước tính
            with open(tts._RTF_FILE, "w", encoding="utf-8") as f:
                f.write("{ rác rưởi")
            tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = None, False
            assert tts.get_omnivoice_rtf() is None
        finally:
            tts._RTF_FILE, tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = goc_file, goc_rtf, goc_co


def test_rtf_bo_qua_so_lieu_vo_nghia():
    """Cảnh dài 0 giây hoặc thời gian âm không được phép kéo lệch ước tính."""
    with tempfile.TemporaryDirectory() as d:
        # Phải cách ly cả FILE, không chỉ biến trong RAM: _ghi_nhan_rtf nạp số đo đã lưu
        # trước khi cộng dồn, nên test sẽ ăn phải RTF thật của máy đang chạy.
        goc = (tts._RTF_FILE, tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc)
        tts._RTF_FILE = os.path.join(d, "rtf.json")
        try:
            tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = None, True
            assert tts._ghi_nhan_rtf(10.0, 0.0) is None
            assert tts._ghi_nhan_rtf(0.0, 5.0) is None
            assert tts._omnivoice_rtf is None, "số liệu rác đã lọt vào trung bình trượt"
            assert round(tts._ghi_nhan_rtf(93.0, 11.2), 1) == 8.3
        finally:
            tts._RTF_FILE, tts._omnivoice_rtf, tts._omnivoice_rtf_da_doc = goc


def test_model_khong_ho_tro_prompt_thi_tra_None_chu_khong_no():
    """Bản OmniVoice cũ không có create_voice_clone_prompt → phía gọi quay về ref_audio."""
    class _ModelCu:
        pass
    assert tts.get_voice_clone_prompt(_ModelCu(), "omnivoice_custom_v", "x.wav", "y") is None


def test_xoa_giong_thi_don_luon_file_prompt():
    with tempfile.TemporaryDirectory() as d:
        goc = _dung_thu_muc_preview_tam(d)
        try:
            ref = os.path.join(d, "omnivoice_custom_v_ref.wav")
            open(ref, "wb").write(b"\0" * 2048)
            m = _ModelGia()
            tts.get_voice_clone_prompt(m, "omnivoice_custom_v", ref, "lời mẫu")
            pt = tts._voice_prompt_path("omnivoice_custom_v")
            assert os.path.isfile(pt)
            tts.invalidate_voice_prompt("omnivoice_custom_v")
            assert not os.path.isfile(pt), "file prompt nằm lại trong voices_preview mãi mãi"
            assert not os.path.isfile(pt + ".fingerprint")
        finally:
            tts.VOICES_PREVIEW_DIR = goc
            tts._voice_prompt_cache.clear()


# ──────────────────────────────────────────────────────────────────────

class _tam_doi_registry:
    """Trỏ registry giọng clone sang file tạm để test không đụng dữ liệu thật của user."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self._goc = tts.CUSTOM_VOICES_FILE
        tts.CUSTOM_VOICES_FILE = os.path.join(self._dir.name, "voices_custom.json")
        return self

    def __exit__(self, *exc):
        tts.CUSTOM_VOICES_FILE = self._goc
        self._dir.cleanup()
        return False


class _tam_doi_cache:
    """
    Trỏ cache TTS sang thư mục tạm.

    Không có nó, test chạy xong sẽ để lại rác trong cache thật của user VÀ — nguy hiểm
    hơn — lần chạy thứ hai ăn cache của lần thứ nhất, nên test xanh mà không hề gọi tới
    đoạn mã đang cần kiểm tra.
    """

    def __init__(self, base_dir):
        self._base = base_dir

    def __enter__(self):
        from services import cache_service as cs
        self._cs = cs
        cache_dir = os.path.join(self._base, "cache")
        media_dir = os.path.join(cache_dir, "media")
        os.makedirs(media_dir, exist_ok=True)
        self._goc = (cs.CACHE_DIR, cs.MEDIA_CACHE_DIR, tts.CACHE_DIR,
                     tts.MEDIA_CACHE_DIR, tts._VOICE_CACHE_INDEX_FILE)
        cs.CACHE_DIR, cs.MEDIA_CACHE_DIR = cache_dir, media_dir
        tts.CACHE_DIR, tts.MEDIA_CACHE_DIR = cache_dir, media_dir
        tts._VOICE_CACHE_INDEX_FILE = os.path.join(cache_dir, "tts_voice_cache_index.json")
        return self

    def __exit__(self, *exc):
        (self._cs.CACHE_DIR, self._cs.MEDIA_CACHE_DIR, tts.CACHE_DIR,
         tts.MEDIA_CACHE_DIR, tts._VOICE_CACHE_INDEX_FILE) = self._goc
        return False


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
