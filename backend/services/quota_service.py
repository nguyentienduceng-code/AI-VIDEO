import os
import json
from datetime import datetime

# Đường dẫn tuyệt đối theo vị trí file, không phụ thuộc thư mục làm việc (CWD) khi khởi động server.
from config import QUOTA_FILE
DAILY_LIMIT = 1500

def _get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _load_quota() -> dict:
    if not os.path.exists(QUOTA_FILE):
        return {"date": _get_today_str(), "used": 0}
    
    try:
        with open(QUOTA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Reset if it's a new day
            if data.get("date") != _get_today_str():
                return {"date": _get_today_str(), "used": 0}
            return data
    except Exception:
        return {"date": _get_today_str(), "used": 0}

def _save_quota(data: dict):
    os.makedirs(os.path.dirname(QUOTA_FILE), exist_ok=True)
    with open(QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def get_quota() -> dict:
    data = _load_quota()
    used = data.get("used", 0)
    percent = (used / DAILY_LIMIT) * 100
    return {
        "used": used,
        "limit": DAILY_LIMIT,
        "percent": round(percent, 2)
    }

def increment_quota(amount: int = 1):
    data = _load_quota()
    data["used"] = data.get("used", 0) + amount
    _save_quota(data)
