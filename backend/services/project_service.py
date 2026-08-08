import os
import json
import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

from config import PROJECTS_DIR

# job_id đi thẳng từ URL (/api/projects/{job_id}) vào os.path.join. Không lọc thì
# "..%5C..%5C..%5Cevil" — Starlette giải mã %5C thành "\", dấu phân cách hợp lệ trên
# Windows — trỏ ra ngoài PROJECTS_DIR, và endpoint upload-image sẽ GHI file ra đó.
# Mọi job_id thật đều là uuid4, nên tập ký tự này rộng hơn nhu cầu thực tế rất nhiều.
_SAFE_JOB_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")


def safe_job_id(job_id: str) -> str:
    """Chuẩn hoá job_id trước khi ghép vào bất kỳ đường dẫn nào. Ném ValueError nếu bẩn.

    Dùng CẢ ở main.py cho os.path.join(IMAGES_DIR, job_id) — nơi cùng một giá trị
    được ghép vào một gốc thư mục khác.
    """
    candidate = os.path.basename(str(job_id or "").strip())
    if candidate in ("", ".", "..") or not _SAFE_JOB_ID.fullmatch(candidate):
        raise ValueError(f"job_id không hợp lệ: {job_id!r}")
    return candidate


def get_project_file_path(job_id: str) -> str:
    return os.path.join(PROJECTS_DIR, f"{safe_job_id(job_id)}.json")

def save_project_state(job_id: str, data: Dict[str, Any]) -> str:
    """Lưu toàn bộ trạng thái dự án vào tệp JSON checkpoint.

    Ghi qua file tạm rồi os.replace (cùng pattern config.write_env_value /
    cache_service.set_media): checkpoint này được ghi lại MỖI CẢNH trong lúc render
    (có thể chạy hàng chục phút). Ghi thẳng vào file_path mà process bị kill giữa
    chừng (crash, huỷ render, mất điện) để lại JSON cụt — lần load sau
    `json.load` ném exception, bị nuốt ở load_project_state và mất luôn tiến độ
    dự án. os.replace là atomic trên cả Windows/POSIX nên không có trạng thái dở.
    """
    file_path = get_project_file_path(job_id)
    tmp_path = file_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, file_path)
        logger.info(f"💾 Đã lưu project checkpoint: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Lỗi khi lưu project state: {e}")
        return ""

def load_project_state(job_id: str) -> Optional[Dict[str, Any]]:
    """Tải dữ liệu dự án từ tệp JSON checkpoint. Trả None nếu không có / job_id bẩn."""
    try:
        file_path = get_project_file_path(job_id)
    except ValueError as e:
        # "Không tìm thấy" là câu trả lời đúng cho một id không hợp lệ — mọi endpoint
        # gọi hàm này đều đã dịch None thành 404, không cần nhánh xử lý riêng.
        logger.warning("[Project] %s", e)
        return None
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Lỗi khi tải project state ({job_id}): {e}")
        return None

def update_scene_asset(job_id: str, scene_idx: int, **kwargs) -> Optional[Dict[str, Any]]:
    """Cập nhật riêng asset (ảnh/âm thanh/prompt) của 1 cảnh."""
    state = load_project_state(job_id)
    if not state:
        return None
    scenes = state.get("scenes", [])
    if scene_idx < 0 or scene_idx >= len(scenes):
        return None
    
    for k, v in kwargs.items():
        scenes[scene_idx][k] = v
        
    state["scenes"] = scenes
    save_project_state(job_id, state)
    return state

def list_projects() -> List[Dict[str, Any]]:
    """Liệt kê danh sách các dự án đã lưu."""
    result = []
    if not os.path.exists(PROJECTS_DIR):
        return result
    for filename in os.listdir(PROJECTS_DIR):
        if filename.endswith(".json"):
            fp = os.path.join(PROJECTS_DIR, filename)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    result.append({
                        "job_id": data.get("job_id", filename.replace(".json", "")),
                        "title": data.get("title", f"Dự án {filename[:8]}"),
                        "mode": data.get("mode", "storyteller"),
                        "scene_count": len(data.get("scenes", [])),
                        "created_at": data.get("created_at", ""),
                        "status": data.get("status", "completed"),
                        "final_video": data.get("final_video", "")
                    })
            except Exception:
                continue
    return sorted(result, key=lambda x: x.get("created_at", ""), reverse=True)
