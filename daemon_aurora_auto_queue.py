#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daemon Watcher & Auto-Chainer for Boreal Horizon -> Aurora Borealis Flash
=======================================================================
1. Monitors the ongoing 'Boreal Horizon' batch render task (10 tracks in total).
2. Continuously tracks active render logs, frame rates, and completion percentages.
3. Once all 10 tracks in 'Boreal Horizon' are fully rendered (valid 4K MP4 videos),
   automatically transitions and initiates the batch render task for:
   '/Users/unclerm/Desktop/音樂發行/AI音樂/Ambient-2026-2/Aurora Borealis Flash'
"""

import os
import sys
import time
import subprocess
import json
import glob
from datetime import datetime

workspace_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, workspace_dir)

BOREAL_DIR = "/Users/unclerm/Desktop/音樂發行/AI音樂/Ambient-2026-2/Boreal Horizon"
AURORA_DIR = "/Users/unclerm/Desktop/音樂發行/AI音樂/Ambient-2026-2/Aurora Borealis Flash"
LOG_FILE = os.path.join(workspace_dir, "logs", "daemon_aurora_queue.log")
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

def get_duration(file_path):
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json', file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return float(data.get('format', {}).get('duration', 0.0))
    except Exception:
        pass
    
    if file_path.lower().endswith(('.wav', '.mp3', '.flac')):
        try:
            import soundfile as sf
            info = sf.info(file_path)
            return float(info.duration)
        except Exception:
            pass
    return 0.0

def verify_single_video(mp4_path, wav_path):
    """驗證單支 MP4 是否完整有效"""
    if not os.path.exists(mp4_path) or os.path.getsize(mp4_path) < 10 * 1024 * 1024:
        return False, 0.0, 0.0
    
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height:format=duration',
            '-of', 'json', mp4_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        v_dur = float(data.get('format', {}).get('duration', 0.0))
    except Exception:
        return False, 0.0, 0.0
    
    a_dur = get_duration(wav_path)
    if v_dur <= 0 or a_dur <= 0:
        return False, v_dur, a_dur
    if abs(v_dur - a_dur) > 2.5:
        return False, v_dur, a_dur
    return True, v_dur, a_dur

def check_boreal_horizon_status():
    """檢查 Boreal Horizon 專輯的整體完成情況與當前活動狀態"""
    if not os.path.exists(BOREAL_DIR):
        return True, 0, 0, []

    wav_files = sorted([f for f in os.listdir(BOREAL_DIR) if f.lower().endswith(".wav")])
    if not wav_files:
        return True, 0, 0, []

    completed = []
    pending = []

    for wav_file in wav_files:
        base_name = os.path.splitext(wav_file)[0]
        wav_path = os.path.join(BOREAL_DIR, wav_file)
        mp4_path = os.path.join(BOREAL_DIR, f"{base_name}.mp4")

        is_valid, v_dur, a_dur = verify_single_video(mp4_path, wav_path)
        if is_valid:
            completed.append(wav_file)
        else:
            pending.append(wav_file)

    is_all_done = (len(completed) == len(wav_files))
    return is_all_done, len(completed), len(wav_files), pending

def get_active_rendering_info():
    """尋找當前正在渲染的所有曲目與最新幀數進度"""
    import re
    active_songs = []

    # 1. 檢查正在寫入的 mp4 (透過 ffmpeg 參數)
    try:
        cmd = ["pgrep", "-fl", "ffmpeg.*Boreal Horizon"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        for line in res.stdout.strip().split("\n"):
            if not line:
                continue
            matches = re.findall(r'/([^/\n]+?)\.mp4', line)
            for m in matches:
                if m not in active_songs:
                    active_songs.append(m)
    except Exception:
        pass

    # 2. 針對每首 active 曲目讀取其 _render.log
    active_details = []
    for s in active_songs:
        progress_info = None
        log_path = os.path.join(BOREAL_DIR, f"{s}_render.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", errors="ignore") as f:
                    lines = f.readlines()
                for line in reversed(lines[-100:]):
                    if "幀 " in line and "/4" in line:
                        progress_info = line.strip().split("[INFO] ")[-1]
                        break
            except Exception:
                pass
        if progress_info:
            active_details.append(f"{s} [{progress_info}]")
        else:
            active_details.append(f"{s} (編碼串流寫入中)")

    # 3. 檢查 Astral Causeway 單獨測試進程
    astral_active = False
    try:
        res = subprocess.run(["pgrep", "-f", "render_full_astral_causeway.py"], capture_output=True, text=True)
        astral_active = len(res.stdout.strip()) > 0
    except Exception:
        pass

    return active_details, astral_active

def is_any_ffmpeg_running_for_boreal():
    """檢查是否仍有 ffmpeg 在處理 Boreal Horizon"""
    try:
        res = subprocess.run(["pgrep", "-f", "ffmpeg.*Boreal Horizon"], capture_output=True, text=True)
        return len(res.stdout.strip()) > 0
    except Exception:
        return False

def main():
    log("=" * 70)
    log("🛸 [4K MV 守護排程器 (Boreal Horizon -> Aurora Borealis Flash) 啟動]")
    log(f"📁 監控中專輯: {BOREAL_DIR}")
    log(f"🎯 接續目標專輯: {AURORA_DIR}")
    log("=" * 70)

    # 階段一：輪詢監控 Boreal Horizon 直至完工
    iteration = 0
    while True:
        iteration += 1
        is_all_done, comp_cnt, total_cnt, pending_list = check_boreal_horizon_status()
        active_details, astral_active = get_active_rendering_info()
        ffmpeg_busy = is_any_ffmpeg_running_for_boreal()

        status_msg = f"📊 [Boreal Horizon 監控] 完成進度: {comp_cnt}/{total_cnt} 首 ({int(comp_cnt/total_cnt*100 if total_cnt else 0)}%)"
        if active_details:
            status_msg += f" | 正在渲染: {', '.join(active_details)}"
        elif ffmpeg_busy:
            status_msg += " | ffmpeg 編碼進行中"
        elif astral_active:
            status_msg += " | Astral Causeway 獨立渲染進程進行中"
        else:
            status_msg += " | 等待下首排程或即將結算"

        log(status_msg)

        # 完工判定：所有曲目驗證合格，且 ffmpeg 與 astral 腳本均已安全退出
        if is_all_done and not ffmpeg_busy and not astral_active:
            log("\n" + "🎉" * 25)
            log("🎉🎉 [重大通知] 'Boreal Horizon' 專輯全數 10 首 4K MV 批次渲染已全部完工！")
            log("🎉" * 25)
            break

        # 每 30 秒輪詢一次
        time.sleep(30)

    # 緩衝冷卻期 10 秒
    log("\n⏳ [冷卻階段] 等待 10 秒以確保檔案系統鎖完全釋放與 GPU 資源重設...")
    time.sleep(10)

    # 階段二：無縫啟動 Aurora Borealis Flash 專輯批次渲染任務
    log("=" * 70)
    log(f"🎬 [接續執行] 立即啟動 'Aurora Borealis Flash' 4K 批次渲染任務！")
    log("=" * 70)

    batch_script = os.path.join(workspace_dir, "batch_render_aurora.py")
    venv_py = os.path.join(workspace_dir, ".venv", "bin", "python")
    py_exec = venv_py if os.path.exists(venv_py) else sys.executable

    log(f"🐍 Python 直譯器: {py_exec}")
    log(f"📜 執行腳本: {batch_script}")

    process = subprocess.Popen(
        [py_exec, batch_script],
        cwd=workspace_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in iter(process.stdout.readline, ''):
        log(f"[Aurora-Engine] {line.rstrip()}")

    process.wait()
    log(f"🏁 'Aurora Borealis Flash' 批次渲染守護任務已全數完成！結束代碼: {process.returncode}")

if __name__ == "__main__":
    main()
