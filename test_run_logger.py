import os
import sys
import json
import time
from datetime import datetime

class TestRunLogger:
    """
    4K MV 視覺模組 - 試運行審計與遙測日誌核心 (TestRunLogger)
    
    具備特性：
    1. 雙軌持久化：同時輸出人類高可讀性 .log 與結構化 .json 遙測審計報告。
    2. 防崩潰即時持久化：每次事件均執行 flush() 與 os.fsync()，確保當機或強制退出時不遺漏日誌。
    3. 項目生命週期追蹤：精準記錄單一模組測試耗時、WebEngine JS/WebGL 錯誤與警報。
    4. 決策與成因分析：記錄 KEEP, DISCARD, SKIP, ROLLBACK 決策，並彙整 Defect Breakdown 缺陷佔比。
    5. 會話總結與合格率計算：自動統計 Pass Rate % 與會話總耗時。
    """
    def __init__(self, batch_id=None, scope_name="全部模組", total_items=0, log_dir=None):
        self.batch_id = batch_id or "general"
        self.scope_name = scope_name
        self.total_items = total_items
        
        # 決定日誌目錄
        if not log_dir:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            log_dir = os.path.join(base_dir, "logs", "test_runs")
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 生成時間戳記與檔名
        self.session_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_batch = str(self.batch_id).replace(":", "_").replace("/", "_").replace(" ", "_")
        
        self.log_filename = f"test_run_{self.session_time_str}_{clean_batch}.log"
        self.json_filename = f"test_run_{self.session_time_str}_{clean_batch}.json"
        
        self.log_path = os.path.join(self.log_dir, self.log_filename)
        self.json_path = os.path.join(self.log_dir, self.json_filename)
        
        self.start_timestamp = time.time()
        self.current_item_record = None
        
        # 遙測數據結構
        self.telemetry = {
            "session_id": f"{self.session_time_str}_{clean_batch}",
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "batch_id": self.batch_id,
            "scope": self.scope_name,
            "total_items_planned": self.total_items,
            "tested_items_count": 0,
            "stats": {
                "kept": 0,
                "discarded": 0,
                "skipped": 0,
                "rolled_back": 0,
                "pass_rate_percent": 0.0,
                "defect_breakdown": {}
            },
            "items": [],
            "status": "RUNNING",
            "end_time": None,
            "total_duration_sec": 0.0
        }
        
        # 初始化開啟 .log 檔案
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        self._write_header()

    def _format_now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _write_header(self):
        header = (
            "=" * 80 + "\n"
            f"🎬 4K MV 視覺整合編輯器 - 試運行審計日誌 (Test Run Audit Log)\n"
            f"會話 ID   : {self.telemetry['session_id']}\n"
            f"啟動時間 : {self.telemetry['start_time']}\n"
            f"目標批次 : {self.batch_id}\n"
            f"審核範圍 : {self.scope_name}\n"
            f"待測總數 : {self.total_items}\n"
            "=" * 80 + "\n\n"
        )
        self._write_log(header)

    def _write_log(self, text):
        if self.log_file and not self.log_file.closed:
            self.log_file.write(text)
            self.log_file.flush()
            try:
                os.fsync(self.log_file.fileno())
            except Exception:
                pass

    def start_item(self, index, total, filename, title, sketch_id=None, url=None):
        """當載入某個模組開始測試時調用"""
        # 如果前一個項目未正常結算（例如異常跳過），先進行隱式結算
        if self.current_item_record and self.current_item_record.get("action") is None:
            self.record_action("UNRESOLVED", {"note": "使用者未操作即切換"})

        now_str = self._format_now()
        item_id = str(sketch_id or "N/A")
        
        self.current_item_record = {
            "index": index,
            "total": total,
            "filename": filename,
            "title": title,
            "sketch_id": item_id,
            "url": url or "",
            "start_time": now_str,
            "start_epoch": time.time(),
            "duration_sec": 0.0,
            "js_errors": [],
            "js_warnings": [],
            "action": None,
            "action_details": {}
        }
        
        log_line = f"[{now_str}] [ITEM #{index}/{total}] 正在試運行「{title}」(ID: {item_id}, 檔案: {filename})\n"
        if url:
            log_line += f"  ↳ 來源連結: {url}\n"
        self._write_log(log_line)

    def log_js_message(self, level_name, message, line_number=0):
        """記錄 WebEngine 監聽到的 JS 異常或訊息"""
        if not self.current_item_record:
            return
            
        now_str = self._format_now()
        lvl = str(level_name).upper()
        line_info = f"Line {line_number}: " if line_number else ""
        formatted_msg = f"{line_info}{message}"
        
        if "ERR" in lvl:
            self.current_item_record["js_errors"].append(formatted_msg)
            self._write_log(f"[{now_str}]   [🔴 JS_ERROR] {formatted_msg}\n")
        elif "WARN" in lvl:
            self.current_item_record["js_warnings"].append(formatted_msg)
            self._write_log(f"[{now_str}]   [⚠️ JS_WARN]  {formatted_msg}\n")
        else:
            self._write_log(f"[{now_str}]   [ℹ️ JS_INFO]  {formatted_msg}\n")

    def record_action(self, action_type, details=None):
        """
        記錄審核決策動作：
        - KEEP: 保留模組 (可選 details: {'is_favorite': True})
        - DISCARD: 剔除模組 (可選 details: {'reason': '預覽不正常'})
        - SKIP: 跳過此模組
        - ROLLBACK: 撤銷整批
        """
        details = details or {}
        now_str = self._format_now()
        action_type = str(action_type).upper()
        
        if self.current_item_record:
            duration = round(time.time() - self.current_item_record["start_epoch"], 2)
            self.current_item_record["duration_sec"] = duration
            self.current_item_record["action"] = action_type
            self.current_item_record["action_details"] = details
            
            # 加入 telemetry 項目列表
            # 複製一份排除 start_epoch 的乾淨數據
            clean_rec = dict(self.current_item_record)
            clean_rec.pop("start_epoch", None)
            self.telemetry["items"].append(clean_rec)
            self.telemetry["tested_items_count"] += 1
            
            err_count = len(self.current_item_record["js_errors"])
            warn_count = len(self.current_item_record["js_warnings"])
        else:
            duration = 0.0
            err_count = 0
            warn_count = 0

        # 更新累計統計
        if action_type == "KEEP":
            self.telemetry["stats"]["kept"] += 1
            star_txt = " ⭐ (評星最愛)" if details.get("is_favorite") else ""
            self._write_log(
                f"[{now_str}]   [🟢 ACTION: KEEP] 保留此模組{star_txt} | 耗時: {duration}s | JS錯誤: {err_count}, 警告: {warn_count}\n\n"
            )
        elif action_type == "DISCARD":
            self.telemetry["stats"]["discarded"] += 1
            reason = details.get("reason", "未指定原因")
            defect_dict = self.telemetry["stats"]["defect_breakdown"]
            defect_dict[reason] = defect_dict.get(reason, 0) + 1
            self._write_log(
                f"[{now_str}]   [🔴 ACTION: DISCARD] 剔除模組 | 原因: 【{reason}】 | 耗時: {duration}s | 檔案已清理\n\n"
            )
        elif action_type == "SKIP":
            self.telemetry["stats"]["skipped"] += 1
            self._write_log(
                f"[{now_str}]   [⚡ ACTION: SKIP] 跳過此模組 (暫不做決定) | 耗時: {duration}s\n\n"
            )
        elif action_type == "ROLLBACK":
            self.telemetry["stats"]["rolled_back"] += 1
            self._write_log(
                f"[{now_str}]   [⏮️ ACTION: ROLLBACK] 放棄並撤銷整個批次 (Batch: {details.get('batch_id', self.batch_id)})\n\n"
            )
        else:
            self._write_log(
                f"[{now_str}]   [❓ ACTION: {action_type}] 詳情: {details}\n\n"
            )

        self.current_item_record = None

    def finish_session(self, status="COMPLETED"):
        """完成試運行會話，輸出結尾摘要並產生 JSON 結構化遙測檔案"""
        if self.telemetry.get("status") == "FINISHED":
            return self.telemetry["stats"]
            
        # 如果最後一個 item 仍在進行中，先記錄
        if self.current_item_record and self.current_item_record.get("action") is None:
            self.record_action("SESSION_TERMINATED", {"note": "會話結束時關閉"})

        now_str = self._format_now()
        total_duration = round(time.time() - self.start_timestamp, 2)
        self.telemetry["status"] = status
        self.telemetry["end_time"] = now_str
        self.telemetry["total_duration_sec"] = total_duration

        stats = self.telemetry["stats"]
        kept = stats["kept"]
        discarded = stats["discarded"]
        skipped = stats["skipped"]
        decided_total = kept + discarded
        
        pass_rate = round((kept / decided_total * 100), 1) if decided_total > 0 else 0.0
        stats["pass_rate_percent"] = pass_rate

        # 格式化總耗時
        mins = int(total_duration // 60)
        secs = int(total_duration % 60)
        duration_fmt = f"{mins} 分 {secs} 秒" if mins > 0 else f"{secs} 秒"

        # 寫入 .log 結尾摘要
        summary_text = (
            "=" * 80 + "\n"
            f"📊 試運行與清理任務總結報告 (Summary)\n"
            f"結束時間     : {now_str}\n"
            f"總測試耗時   : {duration_fmt} ({total_duration} 秒)\n"
            f"已審核模組數 : {self.telemetry['tested_items_count']} / {self.total_items}\n"
            f"  - 🟢 保留模組數 : {kept}\n"
            f"  - 🔴 剔除模組數 : {discarded}\n"
            f"  - ⚡ 跳過模組數 : {skipped}\n"
            f"🏆 合格保留率   : {pass_rate}%\n"
        )
        
        if stats["defect_breakdown"]:
            summary_text += "\n🔍 剔除缺陷原因分布分析 (Defect Breakdown):\n"
            for r_name, count in sorted(stats["defect_breakdown"].items(), key=lambda x: x[1], reverse=True):
                ratio = round(count / discarded * 100, 1) if discarded > 0 else 0.0
                summary_text += f"  • {r_name.ljust(18)}: {count} 個 ({ratio}%)\n"

        summary_text += "=" * 80 + "\n"
        self._write_log(summary_text)

        # 寫入 .json 報告
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.telemetry, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._write_log(f"[{now_str}] [ERROR] 寫入 JSON 遙測檔案失敗: {e}\n")

        if self.log_file and not self.log_file.closed:
            self.log_file.close()

        self.telemetry["status"] = "FINISHED"
        return self.telemetry

    def get_log_path(self):
        return self.log_path

    def get_json_path(self):
        return self.json_path

    def get_log_dir(self):
        return self.log_dir
