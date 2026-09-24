# -*- coding: utf-8 -*-
"""
SENTINEL: Semantic Queue & Database Manager
負責持久化隊列、狀態追蹤 (pending/running/completed/failed) 與代碼 SHA256 去重。
"""

import os
import json
import hashlib
import time
from typing import List, Dict, Any, Optional

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_FILE = os.path.join(WORKSPACE_DIR, "semantic_ingestion", "semantic_queue.json")
EXPRESSIVE_DB_FILE = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")

class SemanticQueueManager:
    @staticmethod
    def _load_json(file_path: str, default: Any) -> Any:
        if not os.path.exists(file_path):
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def _save_json(file_path: str, data: Any):
        temp_path = file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, file_path)

    @classmethod
    def compute_code_hash(cls, code: str, custom_html: str = "") -> str:
        content = (code + "\n" + custom_html).strip().encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    @classmethod
    def enqueue_modules(cls, module_keys: List[str], priority: str = "normal") -> int:
        """
        將模組名稱/鍵值加入待處理佇列
        回傳成功入隊數量
        """
        queue_data = cls._load_json(QUEUE_FILE, {"pending": [], "running": [], "failed": []})
        pending_set = set(queue_data.get("pending", []))
        running_set = set(queue_data.get("running", []))
        
        # 讀取 DB，若已經完整水合 (Level 2)，則不需要再入隊
        db = cls.load_expressive_db()

        added = 0
        for k in module_keys:
            if not k:
                continue
            if k in db and db[k].get("hydration_level", 0) >= 2:
                continue
            if k not in pending_set and k not in running_set:
                if priority == "high":
                    queue_data["pending"].insert(0, k)
                else:
                    queue_data["pending"].append(k)
                pending_set.add(k)
                added += 1

        if added > 0:
            cls._save_json(QUEUE_FILE, queue_data)
        return added

    @classmethod
    def pop_next_task(cls) -> Optional[str]:
        """ 取出下一個待處理任務並標記為 running """
        queue_data = cls._load_json(QUEUE_FILE, {"pending": [], "running": [], "failed": []})
        pending = queue_data.get("pending", [])
        if not pending:
            return None
        task = pending.pop(0)
        queue_data["pending"] = pending
        if task not in queue_data["running"]:
            queue_data["running"].append(task)
        cls._save_json(QUEUE_FILE, queue_data)
        return task

    @classmethod
    def mark_completed(cls, module_key: str, profile_dict: Dict[str, Any]):
        """ 標記任務完成，並寫入全局 Expressive DB """
        # 1. 更新隊列
        queue_data = cls._load_json(QUEUE_FILE, {"pending": [], "running": [], "failed": []})
        if module_key in queue_data.get("running", []):
            queue_data["running"].remove(module_key)
        cls._save_json(QUEUE_FILE, queue_data)

        # 2. 寫入 DB
        db = cls.load_expressive_db()
        profile_dict["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        db[module_key] = profile_dict
        cls._save_json(EXPRESSIVE_DB_FILE, db)

    @classmethod
    def mark_failed(cls, module_key: str, reason: str):
        """ 標記任務失敗 """
        queue_data = cls._load_json(QUEUE_FILE, {"pending": [], "running": [], "failed": []})
        if module_key in queue_data.get("running", []):
            queue_data["running"].remove(module_key)
        failed_list = queue_data.get("failed", [])
        failed_list.append({"module_key": module_key, "reason": reason, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        queue_data["failed"] = failed_list[-500:] # 保留最新 500 個失敗日誌
        cls._save_json(QUEUE_FILE, queue_data)

    @classmethod
    def load_expressive_db(cls) -> Dict[str, Any]:
        return cls._load_json(EXPRESSIVE_DB_FILE, {})

    @classmethod
    def get_queue_status(cls) -> Dict[str, int]:
        queue_data = cls._load_json(QUEUE_FILE, {"pending": [], "running": [], "failed": []})
        db = cls.load_expressive_db()
        return {
            "pending_count": len(queue_data.get("pending", [])),
            "running_count": len(queue_data.get("running", [])),
            "failed_count": len(queue_data.get("failed", [])),
            "total_indexed_in_db": len(db)
        }
