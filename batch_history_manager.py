import os
import re
import json
import shutil
import datetime
import logging

logger = logging.getLogger("batch_history_manager")

class BatchHistoryManager:
    """
    4K MV 視覺整合編輯器 - 批次收編歷史與時光機回溯管理器
    核心原則：
    1. 歷史基準不可變（Legacy Baseline Protection）：現有 1400+ 個既有模組永久受只讀屏障保護，任何回溯操作絕不波及歷史基準。
    2. 原子交易快照（Atomic Snapshot Transactions）：每次收編任務記錄獨立 batch_id、日期時間、檔案清單與過濾設定。
    3. 非破壞性雙向回溯（Non-destructive Rollback & Restore）：回溯時將模組檔案、縮圖安全移入 rollback_backup，可隨時一鍵還原。
    """

    def __init__(self, workspace_dir=None):
        if workspace_dir is None:
            self.workspace_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.workspace_dir = os.path.abspath(workspace_dir)

        self.custom_visuals_dir = os.path.join(self.workspace_dir, "custom_visuals")
        self.manifest_dir = os.path.join(self.custom_visuals_dir, ".batch_manifest")
        self.backup_dir = os.path.join(self.manifest_dir, "rollback_backup")
        self.history_file = os.path.join(self.manifest_dir, "history.json")

        os.makedirs(self.manifest_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self.history_data = self._load_history()
        self.ensure_legacy_baseline()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"讀取批次歷史失敗: {e}")
        return {
            "version": "1.0",
            "legacy_baseline": {
                "initialized": False,
                "count": 0,
                "created_at": "",
                "files": []
            },
            "batches": []
        }

    def _save_history(self):
        temp_file = self.history_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, indent=4, ensure_ascii=False)
            os.replace(temp_file, self.history_file)
        except Exception as e:
            logger.error(f"儲存批次歷史失敗: {e}")

    def ensure_legacy_baseline(self):
        """
        將歷史已收錄模組（初次使用前的全部既有模組）永久鎖定為安全基準。
        歷史基準內的檔案被強制保護，任何最新批次的回溯都不會觸碰它們。
        """
        baseline = self.history_data.get("legacy_baseline", {})
        if baseline.get("initialized"):
            return

        legacy_files = []
        if os.path.exists(self.custom_visuals_dir):
            for fname in os.listdir(self.custom_visuals_dir):
                if fname.endswith(".json") and fname not in (
                    "modules_index.json", "module_usage_history.json", "batch_history.json"
                ):
                    legacy_files.append(fname)

        self.history_data["legacy_baseline"] = {
            "initialized": True,
            "count": len(legacy_files),
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": sorted(legacy_files)
        }
        self._save_history()

    def is_legacy_file(self, filename):
        """檢查某個檔案是否為神聖不可侵犯的歷史基準模組"""
        baseline_files = set(self.history_data.get("legacy_baseline", {}).get("files", []))
        return filename in baseline_files

    def start_new_batch(self, source_url="", filter_options=None):
        """
        發起一個新的收錄批次交易
        回傳 (batch_id, batch_date)
        """
        now = datetime.datetime.now()
        batch_date = now.strftime("%Y-%m-%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        batch_id = f"batch_{timestamp_str}"

        batch_record = {
            "batch_id": batch_id,
            "batch_date": batch_date,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "source_url": source_url,
            "filter_options": filter_options or {},
            "status": "active",  # active / rolled_back
            "items": [],        # list of dict {id, title, filename, thumb, asset_dir}
            "rolled_back_at": None
        }

        self.history_data["batches"].insert(0, batch_record)
        self._save_history()
        return batch_id, batch_date

    def record_imported_item(self, batch_id, sketch_id, title, filename, thumb_filename=None, asset_dir=None):
        """實時向批次登記成功收編的模組檔案資訊"""
        for batch in self.history_data["batches"]:
            if batch["batch_id"] == batch_id:
                item_entry = {
                    "sketch_id": str(sketch_id),
                    "title": title,
                    "filename": filename,
                    "thumbnail": thumb_filename,
                    "asset_dir": asset_dir
                }
                # 避免重複
                if not any(it["filename"] == filename for it in batch["items"]):
                    batch["items"].append(item_entry)
                self._save_history()
                return True
        return False

    def get_batch(self, batch_id):
        """獲取指定批次的詳細資訊"""
        for batch in self.history_data["batches"]:
            if batch["batch_id"] == batch_id:
                return batch
        return None

    def get_all_batches(self):
        """獲取所有歷史批次（依時間倒序）"""
        return self.history_data.get("batches", [])

    def rollback_batch(self, batch_id):
        """
        【時光機一鍵回溯 (Rollback)】
        將該批次的所有模組 JSON、縮圖與依賴資產非破壞性地安全移動至備份區，
        並更新狀態為 rolled_back。
        歷史基準模組受絕對保護，絕不被移動。
        回傳 (success, moved_count, message)
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return False, 0, f"找不到批次 {batch_id}"

        if batch.get("status") == "rolled_back":
            return False, 0, "該批次已處於回溯狀態，無法重複回溯"

        dest_batch_backup = os.path.join(self.backup_dir, batch_id)
        os.makedirs(dest_batch_backup, exist_ok=True)
        dest_thumb_backup = os.path.join(dest_batch_backup, "thumbnails")
        os.makedirs(dest_thumb_backup, exist_ok=True)
        dest_assets_backup = os.path.join(dest_batch_backup, "assets")
        os.makedirs(dest_assets_backup, exist_ok=True)

        moved_count = 0
        thumb_dir = os.path.join(self.custom_visuals_dir, "thumbnails")

        for item in batch.get("items", []):
            fname = item.get("filename")
            # 安全防線：絕對不可回溯歷史基準模組
            if self.is_legacy_file(fname):
                logger.warning(f"安全攔截：檔案 {fname} 屬於歷史基準，禁止回溯！")
                continue

            # 1. 移動模組 JSON
            src_json = os.path.join(self.custom_visuals_dir, fname)
            if os.path.exists(src_json):
                try:
                    shutil.move(src_json, os.path.join(dest_batch_backup, fname))
                    moved_count += 1
                except Exception as e:
                    logger.error(f"移動模組 JSON 失敗 ({fname}): {e}")

            # 2. 移動縮圖
            tname = item.get("thumbnail") or f"{fname[:-5]}.jpg"
            src_thumb = os.path.join(thumb_dir, tname)
            if os.path.exists(src_thumb):
                try:
                    shutil.move(src_thumb, os.path.join(dest_thumb_backup, tname))
                except Exception as e:
                    logger.error(f"移動縮圖失敗 ({tname}): {e}")

            # 3. 移動專屬 assets 目錄
            sid = item.get("sketch_id")
            if sid:
                src_asset_dir = os.path.join(self.custom_visuals_dir, "assets", str(sid))
                if os.path.exists(src_asset_dir):
                    try:
                        dest_single_asset = os.path.join(dest_assets_backup, str(sid))
                        if os.path.exists(dest_single_asset):
                            shutil.rmtree(dest_single_asset, ignore_errors=True)
                        shutil.move(src_asset_dir, dest_single_asset)
                    except Exception as e:
                        logger.error(f"移動素材資產失敗 (ID: {sid}): {e}")

        batch["status"] = "rolled_back"
        batch["rolled_back_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_history()

        return True, moved_count, f"已成功回溯批次 {batch_id}，安全移出 {moved_count} 個模組！"

    def restore_batch(self, batch_id):
        """
        【時光機一鍵還原/重做 (Restore)】
        若使用者後悔撤銷了某一天的批次，可將備份區的模組原封不動移回主庫存。
        回傳 (success, restored_count, message)
        """
        batch = self.get_batch(batch_id)
        if not batch:
            return False, 0, f"找不到批次 {batch_id}"

        if batch.get("status") != "rolled_back":
            return False, 0, "該批次目前為生效中，無需還原"

        src_batch_backup = os.path.join(self.backup_dir, batch_id)
        if not os.path.exists(src_batch_backup):
            return False, 0, "找不到該批次的備份封存資料夾"

        restored_count = 0
        thumb_dir = os.path.join(self.custom_visuals_dir, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        for item in batch.get("items", []):
            fname = item.get("filename")
            backup_json = os.path.join(src_batch_backup, fname)
            dest_json = os.path.join(self.custom_visuals_dir, fname)

            if os.path.exists(backup_json):
                try:
                    shutil.move(backup_json, dest_json)
                    restored_count += 1
                except Exception as e:
                    logger.error(f"還原模組 JSON 失敗 ({fname}): {e}")

            tname = item.get("thumbnail") or f"{fname[:-5]}.jpg"
            backup_thumb = os.path.join(src_batch_backup, "thumbnails", tname)
            dest_thumb = os.path.join(thumb_dir, tname)
            if os.path.exists(backup_thumb):
                try:
                    shutil.move(backup_thumb, dest_thumb)
                except Exception as e:
                    logger.error(f"還原縮圖失敗 ({tname}): {e}")

            sid = item.get("sketch_id")
            if sid:
                backup_asset_dir = os.path.join(src_batch_backup, "assets", str(sid))
                dest_asset_dir = os.path.join(self.custom_visuals_dir, "assets", str(sid))
                if os.path.exists(backup_asset_dir):
                    try:
                        os.makedirs(os.path.dirname(dest_asset_dir), exist_ok=True)
                        if os.path.exists(dest_asset_dir):
                            shutil.rmtree(dest_asset_dir, ignore_errors=True)
                        shutil.move(backup_asset_dir, dest_asset_dir)
                    except Exception as e:
                        logger.error(f"還原素材資產失敗 (ID: {sid}): {e}")

        batch["status"] = "active"
        batch["restored_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_history()

        return True, restored_count, f"已成功還原批次 {batch_id}，重新啟用 {restored_count} 個模組！"

    def get_date_filter_options(self):
        """
        為 UI 提供日期篩選選項清單：
        例如：[
          {"id": "all", "label": "🌐 全部視覺模組"},
          {"id": "latest_batch", "label": "✨ 最新收編批次"},
          {"id": "legacy_baseline", "label": "🏛️ 以往已完成收錄 (歷史基準)"},
          {"id": "date_2026-09-20", "label": "📅 2026-09-20 (今日收錄)"},
          ...
        ]
        """
        options = [
            {"id": "all", "label": "🌐 全部視覺模組"},
            {"id": "latest_batch", "label": "✨ 最新收編批次"},
            {"id": "legacy_baseline", "label": "🏛️ 以往已完成收錄 (歷史基準)"}
        ]

        # 收集生效中的批次日期
        seen_dates = set()
        active_batches = [b for b in self.history_data.get("batches", []) if b.get("status") == "active"]
        for b in active_batches:
            d = b.get("batch_date")
            if d and d not in seen_dates:
                seen_dates.add(d)
                count = sum(len(x.get("items", [])) for x in active_batches if x.get("batch_date") == d)
                options.append({
                    "id": f"date_{d}",
                    "label": f"📅 {d} 收錄批次 ({count} 個)"
                })

        return options

    def filter_modules_by_selection(self, all_presets_data, filter_id):
        """
        依據使用者選取的日期/批次篩選器，對全部模組資料進行高精準分流
        """
        if not filter_id or filter_id == "all":
            return all_presets_data

        baseline_files = set(self.history_data.get("legacy_baseline", {}).get("files", []))
        active_batches = [b for b in self.history_data.get("batches", []) if b.get("status") == "active"]

        if filter_id == "legacy_baseline":
            # 僅傳回歷史基準模組
            return [p for p in all_presets_data if f"{p['name']}.json" in baseline_files]

        if filter_id == "latest_batch":
            if not active_batches:
                return []
            latest = active_batches[0]
            latest_files = {item["filename"] for item in latest.get("items", [])}
            return [p for p in all_presets_data if f"{p['name']}.json" in latest_files]

        if filter_id.startswith("date_"):
            target_date = filter_id[5:]
            # 找到該日期的所有 active 批次所屬檔案
            target_files = set()
            for b in active_batches:
                if b.get("batch_date") == target_date:
                    for item in b.get("items", []):
                        target_files.add(item["filename"])
            return [p for p in all_presets_data if f"{p['name']}.json" in target_files or p.get("date_added", "").startswith(target_date)]

        return all_presets_data
