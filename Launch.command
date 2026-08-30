#!/bin/bash
# 取得此腳本所在的目錄
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "========================================================="
echo "   音畫互動 4K MV 視覺整合編輯器 - 啟動腳本"
echo "========================================================="

# 檢查虛擬環境是否存在，若不存在則建立
if [ ! -d ".venv" ]; then
    echo "[INFO] 未偵測到虛擬環境 (.venv)，正在自動建立..."
    
    # 尋找最適合的 Python 版本 (優先使用與原專案相同的 3.10)
    PYTHON_CMD=""
    if command -v python3.10 &>/dev/null; then
        PYTHON_CMD="python3.10"
        echo "[INFO] 偵測到 python3.10，將使用其建立虛擬環境..."
    elif command -v python3.11 &>/dev/null; then
        PYTHON_CMD="python3.11"
        echo "[INFO] 偵測到 python3.11，將使用其建立虛擬環境..."
    elif command -v python3.9 &>/dev/null; then
        PYTHON_CMD="python3.9"
        echo "[INFO] 偵測到 python3.9，將使用其建立虛擬環境..."
    else
        PYTHON_CMD="python3"
        echo "[WARNING] 未偵測到 python3.9~3.11，將使用預設的 python3 建立虛擬環境..."
    fi
    
    $PYTHON_CMD -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] 建立虛擬環境失敗！請確認已安裝 $PYTHON_CMD 且具備 venv 模組。"
        read -p "按任意鍵結束..." -n1 -s
        exit 1
    fi
    echo "[INFO] 虛擬環境建立成功。"
    
    echo "[INFO] 正在安裝依賴套件 (requirements.txt)..."
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[ERROR] 安裝套件失敗！請確認網路連線正常且 requirements.txt 無誤。"
        read -p "按任意鍵結束..." -n1 -s
        exit 1
    fi
    echo "[INFO] 所有依賴套件安裝完成。"
fi

# 檢查並自動啟動本地 LLM 服務 (Ollama)
echo "[INFO] 正在檢查本地 LLM 服務 (Ollama)..."
if curl -s --max-time 1.5 http://localhost:11434/api/version &>/dev/null; then
    echo "[INFO] 偵測到 Ollama 服務已在背景運行。"
else
    OLLAMA_BIN=""
    if command -v ollama &>/dev/null; then
        OLLAMA_BIN="ollama"
    elif [ -f "/usr/local/bin/ollama" ]; then
        OLLAMA_BIN="/usr/local/bin/ollama"
    fi

    if [ -n "$OLLAMA_BIN" ]; then
        echo "[INFO] 正在自動啟動背景 Ollama LLM 服務..."
        $OLLAMA_BIN serve > /dev/null 2>&1 &
        sleep 1.5
        if curl -s --max-time 2 http://localhost:11434/api/version &>/dev/null; then
            echo "[INFO] 本地 LLM 服務 (Ollama) 背景啟動成功。"
        else
            echo "[WARNING] LLM 服務啟動中，系統將於非同步背景繼續嘗試連線。"
        fi
    else
        echo "[INFO] 未偵測到本地 Ollama 命令，系統將自動採用 Rule-Based 預設導播模式。"
    fi
fi

# 檢查 AI 核心模型檔案
if [ -f "models/yamnet.onnx" ]; then
    echo "[INFO] YAMNet 音頻神經網路模型 (models/yamnet.onnx) 已就緒。"
else
    echo "[WARNING] 未找到 models/yamnet.onnx，將使用備用 STFT 音訊特徵分析器。"
fi

# 執行主程式
echo "[INFO] 正在啟動編輯器 GUI..."
.venv/bin/python main.py

# 捕捉結束狀態
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "[ERROR] 程式異常結束 (Exit Code: $EXIT_CODE)。"
    read -p "按任意鍵結束..." -n1 -s
    exit $EXIT_CODE
else
    echo "[SUCCESS] 編輯器已安全關閉。"
    sleep 1.5
fi
