"""
render_worker.py
----------------
Module chạy tác vụ render video nặng (MoviePy + FFmpeg) trong process con
riêng biệt, giải phóng FastAPI event loop khỏi CPU-bound blocking.

Cơ chế hoạt động:
  1. FastAPI gọi spawn_render() → tạo multiprocessing.Process chạy _worker_main()
  2. Worker process thực hiện toàn bộ render (MoviePy ghép video + FFmpeg mastering)
  3. Trạng thái (progress %, message) được ghi vào file JSON (status_file)
  4. FastAPI poll file JSON này để broadcast qua WebSocket cho Frontend

Ưu điểm so với BackgroundTasks:
  - Process con có GIL riêng → MoviePy render không block FastAPI I/O
  - Nếu worker crash → FastAPI vẫn sống, chỉ job đó báo lỗi
  - Có thể giới hạn số worker đồng thời (MAX_CONCURRENT_RENDERS)
"""

from __future__ import annotations

import json
import multiprocessing
import logging
import os
import time
import traceback
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
MAX_CONCURRENT_RENDERS = 2  # Số lượng render đồng thời tối đa
_active_processes: Dict[str, multiprocessing.Process] = {}

from config import BASE_DIR, RENDER_STATUS_DIR as STATUS_DIR  # noqa: F401


def _status_path(job_id: str) -> str:
    return os.path.join(STATUS_DIR, f"{job_id}.json")


def write_status(job_id: str, **kwargs):
    """Ghi trạng thái render vào file JSON (gọi từ worker process)."""
    path = _status_path(job_id)
    data = {"job_id": job_id, "updated_at": time.time()}
    # Đọc data cũ nếu có
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data.update(kwargs)
    data["updated_at"] = time.time()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    # Atomic rename để tránh đọc file đang ghi dở
    os.replace(tmp_path, path)


def read_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Đọc trạng thái render từ file JSON (gọi từ FastAPI process)."""
    path = _status_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def cleanup_status(job_id: str):
    """Xóa file status sau khi job hoàn tất."""
    path = _status_path(job_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Worker function — chạy trong process con
# ---------------------------------------------------------------------------
def _make_progress_logger(job_id: str, total_frames: int):
    """
    Logger tương thích proglog để MoviePy báo tiến độ thật ra file status.
    Ánh xạ số khung đã ghi vào dải 80-88% (phần còn lại dành cho phụ đề + master).
    Trả về "bar" nếu không có proglog (không làm chết render vì một cái thanh tiến độ).
    """
    try:
        from proglog import ProgressBarLogger
    except Exception:
        return "bar"

    class _StatusLogger(ProgressBarLogger):
        def __init__(self):
            super().__init__()
            self._last_pct = -1
            self._last_write = 0.0

        def bars_callback(self, bar, attr, value, old_value=None):
            if attr != "index" or not total_frames:
                return
            pct = 80 + int(min(value / total_frames, 1.0) * 8)
            now = time.time()
            # Ghi tối đa 1 lần/giây và chỉ khi % đổi — tránh spam I/O
            if pct != self._last_pct and now - self._last_write > 1.0:
                self._last_pct = pct
                self._last_write = now
                eta = ""
                write_status(
                    job_id, status="rendering", progress=pct,
                    message=f"[Worker] Đang dựng khung hình {value}/{total_frames}{eta}",
                )

    return _StatusLogger()


def _worker_main(
    job_id: str,
    scene_assets: list,
    raw_video_path: str,
    output_video_path: str,
    output_srt_path: str,
    render_kwargs: Dict[str, Any],
    master_kwargs: Dict[str, Any],
):
    """
    Hàm chạy trong process con, thực hiện:
      1. MoviePy render RAW video
      2. FFmpeg Audio Mastering & Subtitle Burn
      3. Dọn file thô
    """
    # Windows spawn process con MỚI TINH: stdout/stderr của nó không thừa hưởng cấu
    # hình UTF-8 của tiến trình cha. Không gọi lại ở đây thì mọi dòng log tiếng Việt
    # trong worker sẽ giết job khi output bị chuyển hướng. Xem services/log_setup.py.
    # log_name riêng: RotatingFileHandler không an toàn đa tiến trình trên Windows
    # (xoay vòng = đổi tên file, mà file đang bị tiến trình cha mở thì Windows cấm).
    from services.log_setup import set_job_id, setup_logging
    setup_logging(log_name="render_worker")

    # ContextVar KHÔNG vượt qua ranh giới tiến trình (spawn dựng interpreter mới),
    # nên phải gắn lại job_id ở đây — nếu không, toàn bộ log của khâu render/mastering
    # (khâu chạy lâu và hay chết nhất) sẽ nằm trơ không biết thuộc job nào.
    set_job_id(job_id)

    try:
        write_status(job_id, status="rendering", progress=80, message="[Worker] Đang render video...")

        # ── Phase 1: MoviePy render RAW ──
        # Tiến độ THẬT: trước đây progress bị đặt cứng 80 trước khi render và 85 sau khi
        # xong, nên với video dài người dùng nhìn "80%" đứng yên hàng chục phút mà không
        # biết máy còn sống hay đã treo. Giờ bám theo số khung hình MoviePy đã ghi.
        total_frames = 0
        for a in scene_assets:
            total_frames = max(total_frames, int((a.get("start_time", 0.0) + a.get("duration", 0.0)) * 30))

        from services.video_service import render_final_video
        render_kwargs = dict(render_kwargs)
        render_kwargs["progress_logger"] = _make_progress_logger(job_id, total_frames)
        # Đẩy cảnh báo "đang chạy đường chậm" lên tận giao diện. Tiêm ở đây chứ không
        # nhét vào render_kwargs từ main.py: closure không pickle được nên không qua nổi
        # ranh giới tiến trình — cùng lý do với progress_logger ngay trên.
        render_kwargs["on_fallback"] = lambda msg: write_status(
            job_id, status="rendering", message=msg
        )
        render_final_video(scene_assets, raw_video_path, **render_kwargs)

        write_status(job_id, progress=85, message="[Worker] Render RAW hoàn tất. Đang tạo phụ đề...")

        # ── Phase 1b: Tạo ASS subtitle ──
        mode = render_kwargs.get("mode", "storyteller")
        if mode != "photo_slideshow" and os.path.exists(raw_video_path):
            from services.video_service import generate_ass_file, ASPECT_RATIO_SIZES
            # Phụ đề phải được căn theo ĐÚNG khung hình sẽ burn lên, nếu không libass
            # co giãn lệch tỉ lệ và chữ méo (xem generate_ass_file).
            _vw, _vh = ASPECT_RATIO_SIZES.get(render_kwargs.get("aspect_ratio"), (1080, 1920))
            generate_ass_file(
                scene_assets, output_srt_path, mode,
                subtitle_style=master_kwargs.get("subtitle_style", "karaoke_bold"),
                hook_text=render_kwargs.get("hook_text"),
                hook_effect=master_kwargs.get("hook_effect", "word_by_word"),
                video_width=_vw, video_height=_vh,
            )

        # ── Phase 2: FFmpeg Audio Mastering & Burn Subtitle ──
        write_status(job_id, progress=90, message="[Worker] Đang Mastering Âm thanh & Tối ưu Video...")
        from services.audio_mix_service import master_audio_and_export
        
        ass_path = output_srt_path if os.path.isfile(output_srt_path) else None
        # Track chỉ-giọng cho ducking: render_final_video ghi nó cạnh video thô theo quy
        # ước hậu tố cố định, nên không cần thêm một kênh truyền tham số nữa.
        from services.video_service import VOICE_SIDECHAIN_SUFFIX
        sidechain = raw_video_path + VOICE_SIDECHAIN_SUFFIX
        if not os.path.isfile(sidechain):
            sidechain = None

        master_audio_and_export(
            sidechain_audio_path=sidechain,
            input_video_path=raw_video_path,
            output_path=output_video_path,
            bgm_path=master_kwargs.get("bgm_path"),
            ass_subtitle_path=ass_path,
            use_gpu=master_kwargs.get("use_gpu", True),
            bgm_volume=master_kwargs.get("bgm_volume", 0.15),
            watermark_text=master_kwargs.get("watermark_text"),
            color_grading=master_kwargs.get("color_grading", "warm_cinematic"),
            add_vignette=master_kwargs.get("add_vignette", True),
            progress_bar=master_kwargs.get("progress_bar", True),
            total_duration=master_kwargs.get("total_duration", 0.0),
            bgm_volume_segments=master_kwargs.get("bgm_volume_segments"),
            use_pattern_interrupt=master_kwargs.get("use_pattern_interrupt", True),
            narration_tone=master_kwargs.get("narration_tone", "viral"),
            # Để Pattern Interrupt không chớp đè lên hook — xem chú thích ở audio_mix_service.
            hook_duration=master_kwargs.get("hook_duration", 0.0),
        )

        # Dọn file thô
        if os.path.isfile(raw_video_path):
            os.remove(raw_video_path)
        if sidechain and os.path.isfile(sidechain):
            os.remove(sidechain)

        write_status(
            job_id, status="done", progress=100,
            message="Hoàn tất!",
            video_url=f"/api/download/{job_id}.mp4",
            srt_url=f"/api/download/{job_id}.ass" if mode != "photo_slideshow" else None,
        )

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[RenderWorker] Error for job {job_id}: {e}\n{tb}")
        
        # Fallback: nếu FFmpeg lỗi nhưng RAW video tồn tại → dùng RAW
        if os.path.isfile(raw_video_path):
            try:
                import time
                for _ in range(3):
                    try:
                        os.replace(raw_video_path, output_video_path)
                        break
                    except PermissionError:
                        time.sleep(1)
            except OSError:
                pass

        write_status(
            job_id, status="error",
            error=str(e), message=f"Lỗi render: {e}",
            # Vẫn cung cấp URL nếu fallback thành công
            video_url=f"/api/download/{job_id}.mp4" if os.path.isfile(output_video_path) else None,
        )


# ---------------------------------------------------------------------------
# Public API — gọi từ FastAPI
# ---------------------------------------------------------------------------
def spawn_render(
    job_id: str,
    scene_assets: list,
    raw_video_path: str,
    output_video_path: str,
    output_srt_path: str,
    render_kwargs: Dict[str, Any],
    master_kwargs: Dict[str, Any],
) -> bool:
    """
    Khởi chạy render trong process con. Trả về True nếu spawn thành công,
    False nếu đã đạt giới hạn MAX_CONCURRENT_RENDERS.
    """
    # Dọn các process đã kết thúc
    finished = [jid for jid, p in _active_processes.items() if not p.is_alive()]
    for jid in finished:
        _active_processes[jid].join(timeout=1)
        del _active_processes[jid]

    if len(_active_processes) >= MAX_CONCURRENT_RENDERS:
        return False

    write_status(job_id, status="rendering", progress=80, message="Đang khởi tạo Render Worker...")

    p = multiprocessing.Process(
        target=_worker_main,
        args=(job_id, scene_assets, raw_video_path, output_video_path,
              output_srt_path, render_kwargs, master_kwargs),
        daemon=True,
        name=f"RenderWorker-{job_id[:8]}",
    )
    p.start()
    _active_processes[job_id] = p
    return True


def is_render_active(job_id: str) -> bool:
    """Kiểm tra xem render worker của job_id có đang chạy không."""
    p = _active_processes.get(job_id)
    return p is not None and p.is_alive()


def get_active_render_count() -> int:
    """Số lượng render đang chạy."""
    # Dọn zombie
    finished = [jid for jid, p in _active_processes.items() if not p.is_alive()]
    for jid in finished:
        _active_processes[jid].join(timeout=1)
        del _active_processes[jid]
    return len(_active_processes)


def cancel_render(job_id: str) -> bool:
    """Hủy một render worker đang chạy."""
    p = _active_processes.get(job_id)
    if p is None or not p.is_alive():
        return False
        
    try:
        import psutil
        parent = psutil.Process(p.pid)
        children = parent.children(recursive=True)
        # Kill child processes (ffmpeg, moviepy, etc)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
                
        # Wait for children to terminate
        psutil.wait_procs(children, timeout=3)
        
        # Kill the main worker process
        parent.terminate()
        parent.wait(timeout=3)
    except ImportError:
        logger.warning("psutil not installed, falling back to process.terminate()")
        p.terminate()
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.error(f"[Cancel] Error killing process tree for job {job_id}: {e}")
        p.kill() # fallback
        
    p.join(timeout=2)
    if job_id in _active_processes:
        del _active_processes[job_id]
        
    write_status(job_id, status="error", progress=0, message="Đã huỷ theo yêu cầu của người dùng.", error="Cancelled by user")
    return True
