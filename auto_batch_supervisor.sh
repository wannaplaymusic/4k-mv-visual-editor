#!/bin/bash
# auto_batch_supervisor.sh
# 守護批次渲染隊列：當前進程結束後，自動掃描並補跑所有尚未完成的曲目

WORKSPACE="/Users/unclerm/Vibe Coding/4K MV Visual Integration Editor"
PYTHON_BIN="$WORKSPACE/.venv/bin/python"
LOG_FILE="$WORKSPACE/logs/supervisor.log"

mkdir -p "$WORKSPACE/logs"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 守護進程啟動，開始監視渲染任務..." >> "$LOG_FILE"

while true; do
    # 檢查是否有正在運行的 batch_render_queue.py
    PID=$(pgrep -f "batch_render_queue.py" | head -n 1)
    
    if [ -n "$PID" ]; then
        # 仍在運行中，稍候 30 秒再檢查
        sleep 30
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 檢測到 batch_render_queue.py 進程已結束，開始掃描是否有未完成曲目..." >> "$LOG_FILE"
        
        # 檢查是否有待補曲目
        SCAN_RESULT=$("$PYTHON_BIN" "$WORKSPACE/batch_render_queue.py" --scan-only 2>&1)
        echo "$SCAN_RESULT" >> "$LOG_FILE"
        
        # 判斷是否含有待補渲染或損毀
        if echo "$SCAN_RESULT" | grep -qE "(尚未渲染|渲染中斷/損毀)"; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 發現尚有未完成或新加入的曲目，立即啟動接力渲染！" >> "$LOG_FILE"
            nohup "$PYTHON_BIN" -u "$WORKSPACE/batch_render_queue.py" >> "$WORKSPACE/logs/batch_render_queue.log" 2>&1 &
            sleep 15
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🎉 所有目標目錄全部曲目已 100% 完工，守護進程圓滿退出！" >> "$LOG_FILE"
            break
        fi
    fi
done
