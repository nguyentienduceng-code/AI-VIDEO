import os
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

def get_project_file_path(job_id: str) -> str:
    return os.path.join(PROJECTS_DIR, f"{job_id}.json")

def save_project_state(job_id: str, data: Dict[str, Any]) -> str:
    """Lưu toàn bộ trạng thái dự án vào tệp JSON checkpoint."""
    file_path = get_project_file_path(job_id)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Đã lưu project checkpoint: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Lỗi khi lưu project state: {e}")
        return ""

def load_project_state(job_id: str) -> Optional[Dict[str, Any]]:
    """Tải dữ liệu dự án từ tệp JSON checkpoint."""
    file_path = get_project_file_path(job_id)
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
