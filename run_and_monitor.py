import os
import sys
import time
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView

# 1. 動態環境與路徑配置
WORKSPACE_DIR = Path(__file__).resolve().parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

# 可透過環境變數覆寫路徑，預設相容本地開發環境
SCRATCH_DIR = WORKSPACE_DIR / "scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

MONITOR_LOG_PATH = SCRATCH_DIR / "monitor_log.txt"
MONITOR_FRAME_PATH = SCRATCH_DIR / "monitor_frame.png"

# 設定標準日誌系統（同時輸出控制台與檔案）
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(MONITOR_LOG_PATH, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logging.info("=== Monitor Log Session Started ===")

import main

# 2. 目錄自動注入
DEFAULT_BATCH_DIR = (
    "/Users/unclerm/Desktop/音樂發行/AI音樂/DUB-MV-3/Calm Twilight Chain/"
)
main.safe_get_existing_directory = (
    lambda parent, caption, directory="": DEFAULT_BATCH_DIR
)


# 3. 高效畫面檢測 (直接操作緩衝區)
def check_image_content(img):
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return "zero_size", (0, 0, 0)

    # 確保轉換為標準 32-bit RGB 格式以直接讀取記憶體
    formatted_img = img.convertToFormat(img.Format.Format_RGB32)
    ptr = formatted_img.bits()
    if not ptr:
        return "zero_size", (0, 0, 0)

    ptr.setsize(formatted_img.sizeInBytes())
    raw_bytes = bytes(ptr)
    bytes_per_line = formatted_img.bytesPerLine()

    samples = []
    step_x = max(1, w // 20)
    step_y = max(1, h // 20)
    is_black = True

    # 20x20 網格取樣 (RGB32 在小端序為 B, G, R, A)
    for y in range(0, h, step_y):
        row_offset = y * bytes_per_line
        for x in range(0, w, step_x):
            pixel_offset = row_offset + (x * 4)
            b = raw_bytes[pixel_offset]
            g = raw_bytes[pixel_offset + 1]
            r = raw_bytes[pixel_offset + 2]

            samples.append((r, g, b))
            if r > 8 or g > 8 or b > 8:
                is_black = False

    first_color = samples[0] if samples else (0, 0, 0)
    is_solid = all(c == first_color for c in samples)

    if is_black:
        return "black", first_color
    if is_solid:
        return "solid", first_color
    return "ok", first_color


# 4. 獨立監控管理器 (取代 Monkeypatch)
class RenderMonitor:
    def __init__(self, interval_sec=60):
        self.interval_ms = int(interval_sec * 1000)
        self.timer = QTimer()
        self.timer.timeout.connect(self.audit_render_frame)

    def start(self):
        self.timer.start(self.interval_ms)
        logging.info(
            f"[MONITOR] Audit monitor running every {self.interval_ms // 1000}s"
        )

    def audit_render_frame(self):
        # 尋找全螢幕/無邊框渲染 Clipper 實例
        clipper = None
        for widget in QApplication.topLevelWidgets():
            if (
                widget.windowFlags() & Qt.WindowType.FramelessWindowHint
                and widget.width() > 1000
            ):
                clipper = widget
                break

        if not clipper:
            logging.info(
                "[MONITOR] Standby: Clipper widget not found in active top-level widgets."
            )
            return

        views = clipper.findChildren(QWebEngineView)
        if not views:
            logging.warning(
                "[MONITOR] Warning: Clipper found, but no QWebEngineView children attached."
            )
            return

        view = views[0]
        pix = view.grab()
        img = pix.toImage()

        status, sample_color = check_image_content(img)
        log_msg = f"[AUDIT] Size={img.width()}x{img.height()}, Status={status}, SampleRGB={sample_color}"

        if status in ("black", "zero_size", "solid"):
            logging.warning(
                f"⚠️ [MONITOR WARNING] Potential rendering anomaly! {log_msg}"
            )
        else:
            logging.info(f"✅ {log_msg}")
            pix.save(str(MONITOR_FRAME_PATH), "PNG")


# 5. 主程式入口
def run_main():
    logging.info("[INFO] Starting QApplication...")
    app = QApplication(sys.argv)
    app.setOrganizationName("VibeCoding_Monitor")
    app.setOrganizationDomain("vibecoding_monitor.com")
    app.setApplicationName("4KMVVisualIntegrationEditor_Monitor")

    logging.info("[INFO] Instantiating StandaloneInjectorApp...")
    window = main.StandaloneInjectorApp()
    window.show()

    # 自動載入參數
    window.audio_dir_input.setText(DEFAULT_BATCH_DIR)
    window.res_select.setCurrentText("1080p (1920x1080)")
    window.fps_select.setCurrentText("30")

    # 啟動獨立定時監控器
    monitor = RenderMonitor(interval_sec=60)
    monitor.start()

    # 延遲 1.5 秒自動觸發渲染
    def auto_trigger():
        logging.info("[INFO] Auto-triggering batch rendering...")
        window.start_batch_smart_edit_rendering()

    QTimer.singleShot(1500, auto_trigger)
    sys.exit(app.exec())


if __name__ == "__main__":
    run_main()
