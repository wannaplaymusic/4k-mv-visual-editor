import sys
import os
import time
from PyQt6.QtWidgets import QApplication, QWidget, QProgressBar
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView

# Add workspace dir to system path
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

import main

# 1. Mock output directory selection to return the last batch folder automatically
main.safe_get_existing_directory = lambda parent, caption, directory="": "/Users/unclerm/Desktop/音樂發行/AI音樂/DUB-MV-3/Calm Twilight Chain/"

# Keep track of check times and frames
last_check_time = [0]
monitor_log_path = "/Users/unclerm/.gemini/antigravity/brain/09056949-c70c-41aa-8d63-30b863472947/scratch/monitor_log.txt"

with open(monitor_log_path, "w", encoding="utf-8") as f:
    f.write("=== Monitor Log Started ===\n")

def check_image_content(img, frame_idx):
    w = img.width()
    h = img.height()
    if w == 0 or h == 0:
        return "zero_size"
        
    is_black = True
    samples = []
    # Down-sample and check colors
    for x in range(0, w, int(max(1, w / 20))):
        for y in range(0, h, int(max(1, h / 20))):
            color = img.pixelColor(x, y)
            r, g, b = color.red(), color.green(), color.blue()
            samples.append((r, g, b))
            if r > 8 or g > 8 or b > 8:
                is_black = False
                
    # Check if solid color
    first_color = samples[0] if samples else (0,0,0)
    is_solid = all(c == first_color for c in samples)
    
    log_msg = f"[{time.strftime('%H:%M:%S')}] Frame {frame_idx}: size={w}x{h}, is_black={is_black}, is_solid={is_solid}, sample_color={first_color}\n"
    print(log_msg.strip())
    with open(monitor_log_path, "a", encoding="utf-8") as f:
        f.write(log_msg)
        
    if is_black:
        return "black"
    if is_solid:
        return "solid"
    return "ok"

# 2. Monkeypatch QProgressBar.setValue to perform visual check every 60 seconds
original_set_value = QProgressBar.setValue

def patched_set_value(self, val):
    original_set_value(self, val)
    
    curr_time = time.time()
    if curr_time - last_check_time[0] >= 60.0:  # Every 60 seconds
        last_check_time[0] = curr_time
        
        # Find the clipper widget
        clipper = None
        for widget in QApplication.topLevelWidgets():
            if widget.windowFlags() & Qt.WindowType.FramelessWindowHint:
                if widget.width() > 1000:  # Large render resolution (4K or 1080p)
                    clipper = widget
                    break
                    
        if clipper:
            views = clipper.findChildren(QWebEngineView)
            if views:
                # Capture frame from the active view
                view = views[0]
                pix = view.grab()
                img = pix.toImage()
                
                # Check pixel content
                status = check_image_content(img, val)
                if status in ["black", "zero_size"]:
                    warn_msg = f"⚠️ [MONITOR WARNING] Detect potential rendering anomaly! Status: {status} at Frame {val}\n"
                    print(warn_msg.strip())
                    with open(monitor_log_path, "a", encoding="utf-8") as f:
                        f.write(warn_msg)
                else:
                    # Save a sample check image to the scratch directory for audit
                    save_path = "/Users/unclerm/.gemini/antigravity/brain/09056949-c70c-41aa-8d63-30b863472947/scratch/monitor_frame.png"
                    pix.save(save_path, "PNG")
            else:
                print("[MONITOR] Clipper found, but no QWebEngineView children active.")
        else:
            print("[MONITOR] Clipper widget not found in top-level widgets.")

QProgressBar.setValue = patched_set_value

def run_main():
    print("[INFO] Starting QApplication...")
    app = QApplication(sys.argv)
    app.setOrganizationName("VibeCoding_Monitor")
    app.setOrganizationDomain("vibecoding_monitor.com")
    app.setApplicationName("4KMVVisualIntegrationEditor_Monitor")
    
    print("[INFO] Instantiating StandaloneInjectorApp...")
    window = main.StandaloneInjectorApp()
    window.show()
    
    # Configure input directories
    batch_dir = "/Users/unclerm/Desktop/音樂發行/AI音樂/DUB-MV-3/Calm Twilight Chain/"
    window.audio_dir_input.setText(batch_dir)
    
    # Force output resolution to 1080p or 4K
    window.res_select.setCurrentText("1080p (1920x1080)") # Use 1080p for faster self-test verification
    window.fps_select.setCurrentText("30")
    
    # We want to automatically trigger the batch rendering after UI is initialized
    def auto_trigger():
        print("[INFO] Auto-triggering batch rendering...")
        window.start_batch_smart_edit_rendering()
        
    window.auto_trigger_func = auto_trigger
    QTimer.singleShot(1500, window.auto_trigger_func)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run_main()
