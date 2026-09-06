import os
import sys
import logging
import datetime
from logging.handlers import RotatingFileHandler

def setup_surreal_logger(
    name: str = "SAVAP.SurrealEngine",
    log_dir: str = "logs",
    log_filename: str = "surreal_pipeline.log",
    level: int = logging.INFO
) -> logging.Logger:
    """
    建立 SAVAP 超現實音畫系統專用日誌記錄器：
    - 同時輸出至 Console 與 輪轉日誌檔案 (RotatingFileHandler, 最大 10MB, 保留 5 份備份)
    - 格式化時間、線程、日誌層級、模組與具體訊息
    - 支援偵錯與審美評估歷史追蹤
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_filename)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重複添加 handler
    if not logger.handlers:
        formatter = logging.Formatter(
            fmt='[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(threadName)s] [%(name)s.%(funcName)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. 檔案日誌 (支援自動輪轉)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024, # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)

        # 2. 控制台輸出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        logger.addHandler(console_handler)

    return logger

# 全域預設 Logger 實例
surreal_logger = setup_surreal_logger()
