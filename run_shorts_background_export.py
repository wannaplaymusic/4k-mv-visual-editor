import os
import sys
import json
import time
import logging
from datetime import datetime

# Setup workspace path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORKSPACE_DIR)

from PyQt6.QtCore import QCoreApplication
from shorts_exporter_tab import ShortsExportWorker, setup_exporter_logger, logger

STATUS_FILE = os.path.join(WORKSPACE_DIR, "logs", "shorts_exporter_status.json")
PID_FILE = os.path.join(WORKSPACE_DIR, "logs", "shorts_exporter.pid")

def is_already_running():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if process exists
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            pass
    return False, None

def write_status(data):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        temp_file = STATUS_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, STATUS_FILE)
    except Exception as e:
        logger.error(f"寫入狀態檔失敗: {e}")

def main():
    already_running, pid = is_already_running()
    if already_running:
        print(f"⚠️ 背景匯出程式已在執行中 (PID: {pid})，避免重複啟動。")
        return

    current_pid = os.getpid()
    with open(PID_FILE, "w") as f:
        f.write(str(current_pid))

    setup_exporter_logger()
    logger.info(f"🚀 [背景恢復] Shorts 匯出程式啟動 (PID: {current_pid})")

    app = QCoreApplication.instance()
    if not app:
        app = QCoreApplication(sys.argv)

    src_cache_file = "/Volumes/3TB-2/p5js MV/SRC2/.shorts_analysis_cache.json"
    out_dir = "/Volumes/3TB-2/p5js MV/SRC 2_Short/"

    if not os.path.exists(src_cache_file):
        logger.error(f"找不到分析快取檔案: {src_cache_file}")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return

    logger.info(f"載入分析快取: {src_cache_file}")
    with open(src_cache_file, "r", encoding="utf-8") as f:
        analysis_results = json.load(f)

    total_clips = sum(len(track_data.get("clips", [])) for track_data in analysis_results.values())
    logger.info(f"總曲目數: {len(analysis_results)}, 預計總片段數: {total_clips}")

    status_data = {
        "pid": current_pid,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_clips": total_clips,
        "completed_clips": 0,
        "current_clip": "正在初始化斷點掃描...",
        "percent": 0,
        "is_finished": False
    }
    write_status(status_data)

    worker = ShortsExportWorker(analysis_results, out_dir)

    def on_progress(msg, pct):
        status_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_data["current_clip"] = msg
        status_data["percent"] = pct
        write_status(status_data)

    def on_single_clip_done(clip_name):
        # Recount actual completed mp4s in out_dir
        try:
            mp4_count = len([f for f in os.listdir(out_dir) if f.endswith(".mp4") and "_short_" in f])
            status_data["completed_clips"] = mp4_count
            status_data["last_completed_clip"] = clip_name
            status_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            write_status(status_data)
        except Exception:
            pass

    def on_complete(success):
        status_data["is_finished"] = True
        status_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_data["current_clip"] = "全部匯出完成"
        write_status(status_data)
        logger.info("🎉 [背景恢復] 全部 Shorts 匯出完成！")

    worker.progress_update.connect(on_progress)
    worker.single_clip_done.connect(on_single_clip_done)
    worker.export_complete.connect(on_complete)

    try:
        worker.run()
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

if __name__ == "__main__":
    main()
