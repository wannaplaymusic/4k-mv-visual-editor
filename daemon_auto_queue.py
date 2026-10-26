#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daemon Watcher & Auto-Chainer for MV Rendering Queue
===================================================
1. Monitors the ongoing 'Phantom Platform' batch render.
2. Once 'Phantom Platform' completes, automatically triggers 'batch_render_queue.py'
   to seamlessly render the remaining 11 tracks across 'Marina at Dusk' and 'Gradient of Silence'.
"""

import os
import sys
import time
import subprocess
import json
from datetime import datetime

workspace_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, workspace_dir)

PHANTOM_DIR = "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Phantom Platform"
LOG_FILE = os.path.join(workspace_dir, "logs", "daemon_queue.log")
os.makedirs(os.path.join(workspace_dir, "logs"), exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def check_phantom_platform_complete():
    """檢查 Phantom Platform 資料夾內所有 10 首 wav 是否都已渲染完成"""
    if not os.path.exists(PHANTOM_DIR):
        return True

    wavs = sorted([f for f in os.listdir(PHANTOM_DIR) if f.lower().endswith(".wav")])
    if not wavs:
        return True

    completed_count = 0
    for w in wavs:
        base = os.path.splitext(w)[0]
        mp4_path = os.path.join(PHANTOM_DIR, f"{base}.mp4")
        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 10 * 1024 * 1024:
            # 檢查是否有對應的 credits 或 duration
            credits_path = os.path.join(PHANTOM_DIR, f"{base}_credits.txt")
            if os.path.exists(credits_path):
                completed_count += 1

    return completed_count >= len(wavs), completed_count, len(wavs)

def is_gui_rendering():
    """檢查系統中是否有正在運行的 ffmpeg 渲染進程"""
    try:
        cmd = ["pgrep", "-f", "ffmpeg.*Phantom Platform"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return len(res.stdout.strip()) > 0
    except Exception:
        return False

def check_app_debug_batch_finished():
    """檢查 app_debug.log 是否包含批次完成紀錄"""
    log_path = os.path.join(workspace_dir, "app_debug.log")
    if not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "r", errors="ignore") as f:
            lines = f.readlines()
        for line in reversed(lines[-200:]):
            if "批次智能剪輯配對並渲染結束" in line or "批次渲染結束" in line:
                return True
    except Exception:
        pass
    return False

def main():
    log("=" * 60)
    log("🚀 [MV 守護排程器啟動] 正在監控目前前台的 Phantom Platform 批次任務...")
    log(f"📁 監控目錄: {PHANTOM_DIR}")
    log("=" * 60)

    # 階段一：等待 Phantom Platform 完成
    while True:
        is_done, comp, total = check_phantom_platform_complete()
        rendering = is_gui_rendering()
        batch_finished_log = check_app_debug_batch_finished()

        log(f"📊 [Phantom Platform 進度] 完成: {comp}/{total} 首 | 渲染器活動中: {rendering}")

        if (is_done or batch_finished_log) and not rendering:
            log("🎉 檢測到 Phantom Platform 批次渲染已全部完工！")
            break

        # 每 30 秒輪詢一次
        time.sleep(30)

    # 等待 5 秒讓系統緩衝並釋放文件鎖
    log("⏳ 緩衝 5 秒，準備啟動後續 11 首未完成曲目批次渲染...")
    time.sleep(5)

    # 階段二：調用 batch_render_queue.py 啟動補跑
    queue_script = os.path.join(workspace_dir, "batch_render_queue.py")
    log(f"🎬 正在啟動自動排程腳本: {queue_script}")

    venv_py = os.path.join(workspace_dir, ".venv", "bin", "python")
    py_exec = venv_py if os.path.exists(venv_py) else sys.executable
    log(f"🐍 使用 Python 解譯器: {py_exec}")

    process = subprocess.Popen(
        [py_exec, queue_script],
        cwd=workspace_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in iter(process.stdout.readline, ''):
        log(line.rstrip())

    process.wait()
    log(f"🏁 批次渲染守護進程執行結束，退出碼: {process.returncode}")

if __name__ == "__main__":
    main()
