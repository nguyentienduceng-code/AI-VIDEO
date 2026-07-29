# backend/services/audio_mix_service.py
import subprocess
import logging
import os
import sys
import imageio_ffmpeg

logger = logging.getLogger(__name__)

def _esc_path(p: str) -> str:
    """
    Đường dẫn Windows dùng trong filtergraph: đổi '\\' thành '/', escape dấu ':' của ổ đĩa.
    Không escape thì FFmpeg coi 'C:' là ranh giới tham số → 'Invalid argument'.
    (Cùng logic với ffmpeg_assembler._esc_path — giữ hai bản giống nhau có chủ ý.)
    """
    return os.path.abspath(p).replace('\\', '/').replace(':', r'\:')


def _ffmpeg_ass_path(ass_path: str) -> str:
    """
    Đường dẫn file .ass cho filter `ass=`. LUÔN dùng absolute + escape, KHÔNG dùng
    relative: render chạy trong process con (multiprocessing) nên CWD không chắc
    trùng với CWD lúc dựng lệnh — relative path sẽ trỏ sai chỗ.

    Kết quả phải được BỌC trong dấu nháy đơn ở nơi gọi. Đã đo trên FFmpeg 7.1 của dự
    án với tên file có dấu cách: chỉ dạng abs + escape ':' + bọc nháy đơn là chạy,
    ba biến thể còn lại (relative, hoặc không bọc nháy) đều 'Invalid argument'.
    """
    return _esc_path(ass_path)


# Dấu hiệu NVENC chết trong stderr. Trần phiên đồng thời của GeForce tiêu dùng là
# 3-5, vượt trần thì lỗi rơi vào OpenEncodeSessionEx.
_NVENC_FAILURE_MARKERS = (
    "too many nvenc sessions",
    "openencodesessionex failed",
    "no capable devices found",
    "cannot load nvcuda",
    "driver does not support",
    "incompatible client key",
    "out of memory",
)


def _is_nvenc_failure(stderr: str) -> bool:
    """
    Chỉ được gọi khi lệnh NVENC đã lỗi sẵn, nên bắt rộng là có lợi: đoán nhầm thì
    cùng lắm tốn một lần thử lại bằng CPU, còn bỏ sót thì hỏng nguyên job.
    """
    s = (stderr or "").lower()
    return "nvenc" in s or any(m in s for m in _NVENC_FAILURE_MARKERS)


def _has_nvenc() -> bool:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False

def _probe_width(video_path: str) -> int:
    """Bề ngang video, dùng để dựng dải thanh tiến trình đúng cỡ. 0 nếu không đọc được."""
    import re
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        res = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", video_path],
            capture_output=True, text=True, timeout=15, errors="replace",
        )
        m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", res.stderr)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _has_audio_stream(video_path: str) -> bool:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        res = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", video_path],
            capture_output=True, text=True, timeout=5
        )
        return "Audio:" in res.stderr
    except Exception:
        return False

# Segoe UI Bold. KHÔNG dùng Arial Black (ariblk.ttf) — thiếu glyph 'ư'/'ơ' tiếng Việt.
WATERMARK_FONT = (
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf")
    if sys.platform == "win32"
    else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)

# Tần số lấy mẫu của audio đầu ra. PHẢI ép lại sau `loudnorm`.
# LỖI CŨ: loudnorm ở chế độ động tự nâng nội bộ lên 192kHz và GIỮ NGUYÊN ở đầu ra.
# Encoder AAC không hỗ trợ 192k nên rơi xuống 96kHz — đã đo trên sản phẩm thật trong
# assets/output: mọi file đều là 96000 Hz. Nguồn chỉ 44.1kHz (MoviePy) và giọng đọc
# 24kHz, nên việc nâng tần số KHÔNG thêm một chút thông tin nào, chỉ phình luồng audio
# ~47% (đo được: 50031 -> 35490 byte trên cùng một đoạn) và tạo file 96kHz lệch chuẩn
# giao nộp cho các nền tảng. 48kHz là chuẩn của video.
OUTPUT_AUDIO_RATE = 48000

COLOR_GRADING_FILTERS = {
    "warm_cinematic": "eq=contrast=1.06:saturation=1.12,colorbalance=rs=0.06:gs=0.01:bs=-0.06:rh=0.04:gh=0.01:bh=-0.04",
    "cool_matrix": "eq=contrast=1.10:saturation=0.88,colorbalance=rs=-0.06:gs=0.04:bs=0.06:rh=-0.04:gh=0.02:bh=0.04",
    "vintage_film": "eq=contrast=1.04:saturation=0.90:brightness=0.02,colorbalance=rs=0.04:gs=0.02:bs=-0.04",
    "vivid_pop": "eq=contrast=1.12:saturation=1.25:brightness=0.01",
    "noir_dramatic": "hue=s=0,eq=contrast=1.25:brightness=-0.02",
    "none": "",
}

def _bgm_volume_expr(bgm_volume: float, segments: list | None) -> str:
    """
    Dựng bộ lọc `volume` cho nhạc nền — cố định, hoặc thay đổi theo từng cảnh.

    `segments` = [(start_giây, end_giây, mức_âm_lượng), ...] cho những cảnh user chỉnh
    riêng. Cảnh không chỉnh thì rơi về `bgm_volume` toàn cục.

    PHẢI có `eval=frame`: mặc định filter `volume` tính biểu thức ĐÚNG MỘT LẦN lúc khởi
    tạo (eval=once), nên `t` luôn bằng 0 và cả video sẽ dùng mức của cảnh đầu tiên —
    im lặng sai, không hề báo lỗi. Cùng loại bẫy với drawbox ở thanh tiến trình.

    Biểu thức được BỌC trong nháy đơn vì nó chứa dấu ',' — ký tự ngăn cách bộ lọc trong
    filtergraph; không bọc thì FFmpeg cắt nhầm ngay giữa hàm between().
    """
    if not segments:
        return f"volume={bgm_volume}"

    expr = f"{bgm_volume:.4f}"
    for start, end, vol in reversed(segments):
        expr = f"if(between(t,{float(start):.3f},{float(end):.3f}),{float(vol):.4f},{expr})"
    return f"volume=volume='{expr}':eval=frame"


def master_audio_and_export(
    input_video_path: str,
    output_path: str,
    bgm_path: str | None = None,
    intro_bgm_path: str | None = None,
    intro_bgm_duration: float = 0.0,
    ass_subtitle_path: str | None = None,
    use_gpu: bool = False,
    bgm_volume: float = 0.15,
    watermark_text: str = None,
    color_grading: str = "warm_cinematic",
    add_vignette: bool = True,
    progress_bar: bool = True,
    total_duration: float = 0.0,
    bgm_volume_segments: list | None = None,
    use_audio_ducking: bool = True,
    # Track CHỈ-GIỌNG do video_service.write_voice_sidechain() ghi ra, dùng làm tín hiệu
    # điều khiển ducking. None → rơi về tách đôi track đã trộn (kém hơn, xem chỗ dùng).
    sidechain_audio_path: str | None = None,
    use_pattern_interrupt: bool = True,
    narration_tone: str = "viral",
) -> str:
    """
    Bước cuối: trộn BGM, master âm thanh, lọc màu, vignette, thanh tiến trình, phụ đề, encode.

    `add_vignette` và `progress_bar` TRƯỚC ĐÂY được MoviePy vẽ ở từng khung hình bằng
    Python — hai lớp phủ toàn màn hình đó một mình đã ngốn 1.93 lần tốc độ render
    (6.83 → 3.54 fps, đo trên máy này). Chuyển xuống đây thì chúng chỉ là 2 filter trong
    lượt encode vốn đã bắt buộc phải chạy, và được NVENC tăng tốc luôn.
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    gpu_available = use_gpu and _has_nvenc()

    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_video_path
    ]

    has_bgm = bgm_path and os.path.isfile(bgm_path)
    has_intro_bgm = intro_bgm_path and os.path.isfile(intro_bgm_path) and intro_bgm_duration > 0
    
    # 1: Main BGM (if present)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_path])
    
    # 2: Intro BGM (if present)
    intro_idx = 2 if has_bgm else 1
    if has_intro_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", intro_bgm_path])

    # 3: track CHỈ-GIỌNG, chỉ dùng làm tín hiệu điều khiển ducking (không phát ra loa).
    # KHÔNG -stream_loop: nó dài đúng bằng video, lặp lại là vô nghĩa.
    sc_idx = None
    if use_audio_ducking and sidechain_audio_path and os.path.isfile(sidechain_audio_path):
        sc_idx = 1 + int(bool(has_bgm)) + int(bool(has_intro_bgm))
        cmd.extend(["-i", sidechain_audio_path])

    input_has_audio = _has_audio_stream(input_video_path)
    filter_complex = []
    bgm_vol_filter = _bgm_volume_expr(bgm_volume, bgm_volume_segments)

    # ── Chuyển tông Intro BGM → Main BGM ────────────────────────────────────────
    # DÙNG acrossfade, KHÔNG dùng afade+amix. Ba lý do, đều đã cắn trong bản trước:
    #
    #  1. amix mặc định `normalize=1` → CHIA biên độ cho số input. Intro và Main đều chỉ
    #     còn 0.5 (−6dB), trong khi nhánh không có intro (`[1:a]` trần) là nguyên 100%.
    #     Kết quả: BẬT nhạc mở màn làm nhạc nền cả video nhỏ hẳn đi so với khi tắt —
    #     loudnorm phía sau chuẩn hoá tổng nên không lộ ở âm lượng chung, nhưng TỈ LỆ
    #     nhạc/giọng thì đổi thật và nghe ra ngay.
    #  2. Hai afade độc lập không bù nhau ở điểm giao: cả hai cùng ~0.5 biên độ tạo một
    #     chỗ TRŨNG âm lượng giữa crossfade. acrossfade với c1/c2=tri giữ năng lượng phẳng.
    #  3. afade=t=in chỉ BỊT TIẾNG nhạc chính chứ không giữ nó lại — bài hát vẫn chạy từ
    #     t=0, nên lúc hiện ra thì đã trôi mất T giây đầu, đúng đoạn intro hay nhất.
    #     atrim + acrossfade cho nhạc chính vào từ giây 0 của chính nó.
    #
    # atrim biến luồng `-stream_loop -1` vô hạn thành hữu hạn đúng T giây (và tự lặp nếu
    # bản nhạc intro ngắn hơn T) — acrossfade bắt buộc input đầu phải hữu hạn.
    bgm_stream = None
    if has_intro_bgm:
        t = intro_bgm_duration
        fade_d = min(2.0, t / 2.0)
        filter_complex.append(f"[{intro_idx}:a]atrim=0:{t:.3f},asetpts=N/SR/TB[intro_t]")
        if has_bgm:
            filter_complex.append(
                f"[intro_t][1:a]acrossfade=d={fade_d:.3f}:c1=tri:c2=tri[bgm_mix]"
            )
        else:
            # Chỉ có nhạc mở màn: tự tắt dần rồi im, không có gì nối tiếp.
            filter_complex.append(
                f"[intro_t]afade=t=out:st={max(0.0, t - fade_d):.3f}:d={fade_d:.3f}[bgm_mix]"
            )
        bgm_stream = "[bgm_mix]"
    elif has_bgm:
        bgm_stream = "[1:a]"


    if input_has_audio:
        if bgm_stream:
            filter_complex.append(f"{bgm_stream}equalizer=f=2000:t=q:w=2:g=-6,{bgm_vol_filter}[bgm_eq]")
            filter_complex.append("[0:a]bass=g=5:f=110,acompressor=threshold=-15dB:ratio=3:attack=5:release=50[voice_eq_raw]")

            if use_audio_ducking:
                if sc_idx is not None:
                    # Tín hiệu điều khiển là track CHỈ-GIỌNG do video_service ghi riêng.
                    filter_complex.append(f"[{sc_idx}:a]highpass=f=120,acompressor=threshold=-20dB:ratio=4[sc_key]")
                    ducking_key = "[sc_key]"
                    voice_out = "[voice_eq_raw]"
                else:
                    # Không có track riêng → đành tách đôi chính track đã trộn. Kém hơn
                    # (SFX cũng dìm nhạc) nhưng vẫn tốt hơn là không ducking gì.
                    filter_complex.append("[voice_eq_raw]asplit=2[voice_eq1][voice_eq2]")
                    ducking_key = "[voice_eq1]"
                    voice_out = "[voice_eq2]"

                # threshold 0.03 (~-30dBFS) thay cho 0.05: giọng đã qua bass boost +
                # acompressor nên rất "nóng", ngưỡng cũ gần như luôn bị vượt → ducking
                # thành thường trực chứ không theo nhịp nói.
                # attack 20ms thay cho 5ms: 5ms bập vào quá nhanh, nghe rõ tiếng "chụp"
                # ở đầu mỗi câu.
                # release: 1000ms quá chậm (nhạc không kịp nổi lên trong khoảng nghỉ giữa
                # câu, nghe như tắt hẳn suốt đoạn thoại) nhưng 350ms lại gần đúng bằng
                # khoảng lặng 0.45s cố định giữa MỌI cặp cảnh (TTS tự chèn) — nhạc nền kịp
                # "phồng" gần hết biên độ trong đúng khoảng lặng đó rồi bị đè xuống ngay khi
                # câu sau bắt đầu, lặp lại y hệt ở TẤT CẢ điểm chuyển cảnh trong cả video,
                # nghe như một tiếng "phập phồng" phát đều đặn. Đo trên video thật (12 cảnh,
                # cả 11 điểm nối đều lặng đúng 0.45s): 650ms vẫn đủ nhanh để nhạc nổi lên
                # trong khoảng nghỉ DÀI thật sự (giữa đoạn/paragraph), nhưng không kịp hồi
                # hết trong 0.45s ngắn nên độ "phồng" ở mỗi điểm nối giảm hẳn.
                filter_complex.append(
                    f"[bgm_eq]{ducking_key}sidechaincompress="
                    "threshold=0.03:ratio=6:attack=20:release=650[bgm_ducked]"
                )
                # normalize=0: xem lý do ở khối crossfade phía trên. Ở đây nó giữ đúng
                # TỈ LỆ giọng/nhạc mà người dùng đã chỉnh, thay vì bóp cả hai còn một nửa.
                filter_complex.append(f"{voice_out}[bgm_ducked]amix=inputs=2:duration=first:normalize=0[mixed]")
            else:
                filter_complex.append("[voice_eq_raw][bgm_eq]amix=inputs=2:duration=first:normalize=0[mixed]")

            audio_out = "[mixed]"
        else:
            filter_complex.append("[0:a]bass=g=5:f=110,acompressor=threshold=-15dB:ratio=3:attack=5:release=50[voice_eq]")
            audio_out = "[voice_eq]"
        filter_complex.append(f"{audio_out}loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.95:attack=5:release=50,aresample={OUTPUT_AUDIO_RATE}[audio_master]")
    else:
        if bgm_stream:
            filter_complex.append(f"{bgm_stream}equalizer=f=2000:t=q:w=2:g=-6,{bgm_vol_filter}[bgm_eq]")
            filter_complex.append(f"[bgm_eq]loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.95:attack=5:release=50,aresample={OUTPUT_AUDIO_RATE}[audio_master]")

    video_chain = "[0:v]"

    # ── Cinematic Color Grading Filter ──
    cg_filter = COLOR_GRADING_FILTERS.get(color_grading, "")
    if cg_filter:
        filter_complex.append(f"{video_chain}{cg_filter}[v_cg]")
        video_chain = "[v_cg]"

    # ── Pattern Interrupt (B4) ──
    # Cú giật sáng nhanh (flash) mỗi ~3s để thu hút sự chú ý.
    #
    # LỖI NGHIÊM TRỌNG ĐÃ VÁ: bộ lọc `eq` mặc định `eval=init` — biểu thức tham số
    # (brightness ở đây) chỉ được TÍNH MỘT LẦN lúc khởi tạo filter, không tính lại mỗi
    # khung hình, HỆT lỗi `drawbox` từng gặp ở thanh tiến trình (xem chú thích chỗ dùng
    # `overlay` bên dưới). Thiếu `eval=frame`, `t` bị khoá ở giá trị lúc khởi tạo và
    # điều kiện `lt(mod(t,3.2),0.1)` luôn đúng — ĐO THẬT bằng `signalstats`: TOÀN BỘ
    # video cháy sáng trắng xoá (YAVG=255) từ khung đầu tới khung cuối, không có "khung
    # ngoài cửa sổ flash" nào cả. Đây là loại lỗi cú pháp hợp lệ 100%, FFmpeg không báo
    # lỗi gì — "đã kiểm tra cú pháp" không bắt được, phải render thật + đo pixel mới lộ.
    #
    # Cũng hạ độ mạnh 0.6 → 0.2: đo bằng `eq=brightness=0.6` cố định thấy TỰ NÓ đã đẩy
    # nền xám 128 lên 255 (bão hoà trắng hoàn toàn) — một "cú giật NHẸ" theo đúng mô tả
    # tính năng không thể là một khung hình trắng xoá; 0.2 cho độ sáng nhô lên rõ nhưng
    # không cháy sáng, cũng đỡ rủi ro với người nhạy ánh sáng nhấp nháy hơn một cú full-white.
    if use_pattern_interrupt and narration_tone not in ("storytelling", "emotional"):
        filter_complex.append(
            f"{video_chain}eq=eval=frame:brightness='if(lt(mod(t,3.2),0.1), 0.2, 0)'[v_pi]"
        )
        video_chain = "[v_pi]"

    # ── Vignette: làm tối 4 góc (thay lớp ImageClip RGBA của MoviePy) ──
    if add_vignette:
        filter_complex.append(f"{video_chain}vignette=angle=PI/5:mode=forward[v_vig]")
        video_chain = "[v_vig]"

    # ── Thanh tiến trình vàng dưới đáy ──
    # Kỹ thuật: một dải vàng đúng bề ngang khung hình, TRƯỢT vào từ bên trái.
    # Phần lộ ra = W*t/tổng_thời_lượng, tức đúng một thanh tiến trình chạy dần.
    # KHÔNG dùng drawbox: đã đo trên chính FFmpeg 7.1 của dự án — drawbox chỉ tính biểu
    # thức `w` MỘT LẦN lúc khởi tạo nên thanh luôn full width ở mọi khung. Riêng overlay
    # thì đánh giá x/y theo từng khung (đo được 80/270/458 px đúng mốc 15/50/85%).
    bar_w = _probe_width(input_video_path) if (progress_bar and total_duration > 0) else 0
    if bar_w:
        filter_complex.append(f"color=c=0xFFD700:s={bar_w}x12:d={total_duration:.3f}[pbar]")
        filter_complex.append(
            f"{video_chain}[pbar]overlay=x='-{bar_w}+{bar_w}*t/{total_duration:.3f}':y=H-12[v_pb]"
        )
        video_chain = "[v_pb]"

    if watermark_text:
        # Dấu nháy đơn và dấu ':' đều là ký tự cấu trúc của filtergraph. Bỏ hẳn chúng
        # (thay vì escape) vì watermark là chuỗi trang trí ngắn — an toàn hơn là
        # rủi ro vỡ cả lệnh vì một dấu nháy lạc. Dấu ',' thì escape được, xem _esc_expr
        # bên ffmpeg_assembler.
        wm_text = watermark_text.replace("'", "").replace(":", "")
        filter_complex.append(
            f"{video_chain}drawtext=fontfile='{_esc_path(WATERMARK_FONT)}':text='{wm_text}':"
            f"fontcolor=white@0.45:fontsize=56:x=w-text_w-60:y=100:borderw=2:bordercolor=black@0.3[v_wm]"
        )
        video_chain = "[v_wm]"

    if ass_subtitle_path and os.path.isfile(ass_subtitle_path):
        ass_safe = _ffmpeg_ass_path(ass_subtitle_path)
        filter_complex.append(f"{video_chain}ass='{ass_safe}'[video_out]")
        video_chain = "[video_out]"

    if filter_complex:
        # ';' ngăn cách các FILTERCHAIN, ',' ngăn cách các bộ lọc TRONG một chain.
        # Ở đây mọi chain đều có label vào/ra tường minh nên FFmpeg 7.1 chấp nhận cả
        # hai (đã đo: output MD5 giống hệt nhau). Vẫn dùng ';' vì đó mới là dạng đúng
        # ngữ nghĩa — nếu sau này thêm một chain KHÔNG label thì ',' sẽ nối sai âm thầm.
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
    
    if video_chain != "[0:v]":
        cmd.extend(["-map", video_chain])
    else:
        cmd.extend(["-map", "0:v"])
        
    # `bgm_stream`, KHÔNG phải `has_bgm`: bgm_stream bật cả khi CHỈ có nhạc mở màn.
    # LỖI CŨ: điều kiện `has_bgm` bỏ sót đúng trường hợp đó — filtergraph vẫn dựng
    # [audio_master] đầy đủ nhưng không map, nên video (vd photo_slideshow chỉ chọn
    # Intro BGM) ra CÂM HOÀN TOÀN mà không một dòng lỗi nào.
    if input_has_audio or bgm_stream:
        cmd.extend(["-map", "[audio_master]"])

    # Phần đuôi không phụ thuộc encoder. Tách ra để khi fallback thì DỰNG LẠI lệnh
    # từ đầu, thay vì gỡ các tham số NVENC ra khỏi một list đã trộn lẫn: lọc theo
    # giá trị ("p4", "8M", "vbr"...) sẽ để lại cờ mồ côi như '-b:v' hay '-preset'
    # không còn giá trị, và FFmpeg sẽ nuốt nhầm token kế tiếp làm giá trị của nó.
    tail = [
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-max_muxing_queue_size", "2048",
        "-shortest", output_path,
    ]

    def _build(use_nvenc: bool) -> list:
        if use_nvenc:
            # CQ (chất lượng cố định) thay cho `-b:v 8M` cố định.
            # LÝ DO: bitrate cố định trả cùng một lượng bit cho cảnh tĩnh lẫn cảnh động,
            # nên video 3:42 phình lên 215MB dù phần lớn nội dung là ảnh gần như đứng yên.
            # Đo trên chính video của dự án (10s, 1080x1920, SSIM so với bản CRF14):
            #     p4 -b:v 8M (cũ) : 7.94 MB  SSIM 0.99765
            #     p4 -cq 23 (mới) : 4.74 MB  SSIM 0.99660   → nhỏ hơn 40%
            #     p6 -cq 23       : 4.14 MB  SSIM 0.99659   → nhỏ hơn 48%, encode chậm ~45%
            # SSIM lệch 0.001, mắt không phân biệt được. Muốn ép thêm dung lượng thì
            # đổi p4 → p6; muốn nét hơn nữa thì hạ cq xuống 21 (đo được 6.06 MB).
            # `-b:v 0` BẮT BUỘC: để số khác thì NVENC vẫn ghì theo bitrate mục tiêu và
            # CQ mất tác dụng. maxrate/bufsize chặn đỉnh ở cảnh chuyển động mạnh.
            enc = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-maxrate", "12M", "-bufsize", "24M"]
        else:
            enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        return cmd + enc + tail

    def _run(command: list):
        # -nostats: không có nó, 30 phút encode sẽ nhồi hàng megabyte dòng "frame=..."
        # vào bộ nhớ vì đang capture stderr. Cảnh báo/lỗi vẫn giữ nguyên.
        return subprocess.run(
            command[:1] + ["-nostats"] + command[1:],
            check=True, capture_output=True, text=True, errors="replace", timeout=1800,
        )

    logger.info(
        "[AudioMaster] Processing: %s. BGM: %s%s",
        "NVENC" if gpu_available else "CPU", has_bgm,
        f" (âm lượng riêng cho {len(bgm_volume_segments)} cảnh)" if bgm_volume_segments else "",
    )
    try:
        _run(_build(gpu_available))
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        if gpu_available and _is_nvenc_failure(stderr):
            # GeForce tiêu dùng chỉ cho 3-5 phiên NVENC đồng thời. Render song song
            # vượt trần → phiên thứ 6 chết ngay lúc khởi tạo. CPU chậm hơn nhưng
            # không có trần, nên thà chậm còn hơn hỏng job.
            logger.warning(
                "[AudioMaster] NVENC không dùng được (hết session hoặc lỗi khởi tạo) "
                "→ fallback libx264. Nguyên văn: %s", stderr.strip().splitlines()[-1] if stderr.strip() else "?"
            )
            try:
                _run(_build(False))
            except subprocess.CalledProcessError as e2:
                logger.error("[AudioMaster] Fallback CPU cũng thất bại: %s", (e2.stderr or "")[-1500:])
                raise
        else:
            logger.error("[AudioMaster] FFmpeg thất bại: %s", stderr[-1500:])
            raise

    return output_path
