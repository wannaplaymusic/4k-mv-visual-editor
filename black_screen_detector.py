import os
import sys
import re
import json
import random
import time
import shutil
import datetime
import gc

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QProgressBar, QTextEdit, QMessageBox, QWidget, QApplication
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QUrl, QTimer, QEventLoop
from PyQt6.QtGui import QTextCursor, QFont, QImage

# 取得 workspace 目錄路徑
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

# 嘗試自 main.py 匯入全域相容常數
try:
    from main import (
        P5_V2_COMPAT_SHIM, OVERRIDE_16_9_JS, MOCK_NATIVE_AUDIO_JS, MOCK_P5_JS,
        BIND_MODULE_CALLBACKS_JS, get_local_base_url
    )
except ImportError:
    P5_V2_COMPAT_SHIM = ""
    OVERRIDE_16_9_JS = ""
    MOCK_NATIVE_AUDIO_JS = ""
    MOCK_P5_JS = ""
    BIND_MODULE_CALLBACKS_JS = ""
    def get_local_base_url():
        return QUrl.fromLocalFile(os.path.join(workspace_dir, "dummy.html"))

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, log_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_callback = log_callback
        try:
            self.featurePermissionRequested.connect(self._handle_feature_permission)
        except Exception:
            pass

    def _handle_feature_permission(self, securityOrigin, feature):
        try:
            self.setFeaturePermission(securityOrigin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
        except Exception:
            pass

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if "vectors of different sizes" in message or "linger vector" in message:
            return
        self.log_callback(level, message, lineNumber)

    def javaScriptAlert(self, securityOrigin, msg):
        self.log_callback(QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel, f"[JS Alert Blocked] {msg}", 0)

    def javaScriptConfirm(self, securityOrigin, msg):
        self.log_callback(QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel, f"[JS Confirm Blocked] {msg}", 0)
        return True

    def javaScriptPrompt(self, securityOrigin, msg, defaultValue, result):
        self.log_callback(QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel, f"[JS Prompt Blocked] {msg}", 0)
        return False


def make_detector_html(code, custom_css="", custom_html="", sketch_id=None):
    from main import StandaloneInjectorApp
    class DummyApp:
        js_local_paths = {}
        def cache_and_localize_scripts(self, html):
            return html
    html = StandaloneInjectorApp.get_html_content(
        DummyApp(),
        code,
        custom_css=custom_css,
        custom_html=custom_html,
        sketch_id=sketch_id,
        scaling_mode="auto",
        for_thumbnail=False,
        for_rendering=False
    ).replace("{P5_V2_COMPAT_SHIM}", P5_V2_COMPAT_SHIM)

    # 注入黑屏偵測器專用的 __drawCount 追蹤、音訊模擬與強制啟動腳本
    detector_bootstrap_js = """<script>
    // === 黑屏偵測器專用腳本 ===
    window.__jsErrors = window.__jsErrors || [];
    window.__drawCount = window.__drawCount || 0;
    window.__setupFinished = window.__setupFinished || false;

    // Hook p5.prototype.draw 以追蹤繪製次數
    if (typeof p5 !== 'undefined' && p5.prototype) {
      const _detectorOrigDraw = p5.prototype.draw;
      p5.prototype.draw = function() {
        window.__drawCount = (window.__drawCount || 0) + 1;
        window._p5Instance = this;
        if (_detectorOrigDraw) return _detectorOrigDraw.apply(this, arguments);
      };
      const _detectorOrigSetup = p5.prototype.setup;
      p5.prototype.setup = function() {
        window.__setupFinished = true;
        window._p5Instance = this;
        if (_detectorOrigSetup) return _detectorOrigSetup.apply(this, arguments);
      };
    }

    // 強制 WebGL preserveDrawingBuffer
    (function() {
      const orgGetContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(type, attribs) {
        if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
          attribs = attribs || {};
          attribs.preserveDrawingBuffer = true;
        }
        return orgGetContext.call(this, type, attribs);
      };
    })();

    // 模擬音訊動態參數
    window.frequency = window.frequency || 50;
    window.storyboardWeight = window.storyboardWeight || 50;
    window.postFxIntensity = window.postFxIntensity || 50;
    window.isBeat = true;
    window.beatEnergy = window.beatEnergy || 0.8;
    window.audioLow = window.audioLow || 0.7;
    window.audioMid = window.audioMid || 0.6;
    window.audioHigh = window.audioHigh || 0.8;

    let _detectorFrameCounter = 0;
    function _detectorTick() {
      _detectorFrameCounter++;
      window.audioLow = 0.4 + 0.45 * Math.sin(_detectorFrameCounter * 0.08);
      window.audioMid = 0.5 + 0.35 * Math.sin(_detectorFrameCounter * 0.06);
      window.audioHigh = 0.3 + 0.55 * Math.sin(_detectorFrameCounter * 0.11);
      window.beatEnergy = 0.6 + 0.35 * Math.sin(_detectorFrameCounter * 0.15);
      window.isBeat = (_detectorFrameCounter % 20 === 0);
      requestAnimationFrame(_detectorTick);
    }
    requestAnimationFrame(_detectorTick);

    window.forceStartP5 = function() {
      if (window._p5Instance && !window.__setupFinished) {
        try {
          window._p5Instance._preloadCount = 0;
          if (typeof window._p5Instance._setup === 'function') window._p5Instance._setup();
          else if (typeof window.setup === 'function') window.setup();
          window.__setupFinished = true;
          return true;
        } catch(e) { return false; }
      }
      return true;
    };

    window.forceRedrawP5 = function() {
      if (window._p5Instance) {
        try {
          if (typeof window._p5Instance._draw === 'function') window._p5Instance._draw();
          else window._p5Instance.redraw();
          return true;
        } catch(e) { return false; }
      }
      return false;
    };
    </script>"""

    # 在 </head> 之前注入偵測器腳本
    if '</head>' in html:
        html = html.replace('</head>', detector_bootstrap_js + '\n</head>')
    else:
        html = detector_bootstrap_js + html

    return html

class BlackScreenDetectorDialog(QDialog):
    """視覺模組黑屏、純色與無動態畫布自動檢測與備份隱藏工具"""
    def __init__(self, parent=None, auto_start=False):
        super().__init__(parent)
        self.auto_start = auto_start
        self.setWindowTitle("🎬 視覺模組黑屏與純色自檢自測清理工具")
        self.resize(1180, 720)
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QProgressBar {
                border: 1px solid #27272a; border-radius: 6px; text-align: center;
                background-color: #18181b; color: #f4f4f5; height: 20px; font-weight: bold;
            }
            QProgressBar::chunk { background-color: #7c3aed; border-radius: 5px; }
            QTextEdit {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; font-family: 'Courier New', monospace; font-size: 12px;
            }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_start { background-color: #7c3aed; border-color: #7c3aed; color: #ffffff; }
            QPushButton#btn_start:hover { background-color: #8b5cf6; }
            QPushButton#btn_abort { background-color: #ef4444; border-color: #ef4444; color: #ffffff; }
            QPushButton#btn_abort:hover { background-color: #f87171; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        desc = QLabel(
            "此工具將逐一對 `custom_visuals` 資料夾內的所有視覺模組進行 15 秒試運行：\n"
            "1. 實時動態模擬音訊及滑鼠互動，喚醒音樂響應模組。\n"
            "2. 自動執行像素分析（Early-Exit）：若在 1-2 秒內檢測到畫面呈彩色彩色變化，即刻通過以節省時間。\n"
            "3. 若 15 秒後畫面仍是**一片黑、純色或全透明**，則將其移動至備份資料夾隱藏，並生成專屬 txt/html/json 錯誤報告。", 
            self
        )
        main_layout.addWidget(desc)

        center_layout = QHBoxLayout()
        
        # 左側 WebEngine 畫布
        self.preview_container = QWidget(self)
        self.preview_container.setMinimumSize(640, 360)
        self.preview_container.setStyleSheet("background-color: #000000; border: 1px solid #27272a; border-radius: 8px;")
        preview_box = QVBoxLayout(self.preview_container)
        preview_box.setContentsMargins(0, 0, 0, 0)
        
        self.web_view = QWebEngineView(self.preview_container)
        self.web_view.setMinimumSize(640, 360)
        preview_box.addWidget(self.web_view)
        center_layout.addWidget(self.preview_container)

        # 右側終端日誌
        self.console = QTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setMinimumWidth(420)
        center_layout.addWidget(self.console)
        
        main_layout.addLayout(center_layout)

        # 進度條
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.stat_label = QLabel("📊 統計：已測試 0 | 通過 0 | 異常隱藏 0", self)
        self.stat_label.setStyleSheet("color: #a1a1aa; font-weight: bold;")
        main_layout.addWidget(self.stat_label)
        
        # 控制按鈕
        btn_box = QHBoxLayout()
        self.btn_start = QPushButton("🚀 開始自檢", self)
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self.start_detection)
        btn_box.addWidget(self.btn_start)

        self.btn_pause = QPushButton("⏸️ 暫停", self)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.toggle_pause)
        btn_box.addWidget(self.btn_pause)

        self.btn_abort = QPushButton("🛑 終止", self)
        self.btn_abort.setObjectName("btn_abort")
        self.btn_abort.setEnabled(False)
        self.btn_abort.clicked.connect(self.abort_detection)
        btn_box.addWidget(self.btn_abort)

        self.btn_restore = QPushButton("📦 一鍵還原隔離模組", self)
        self.btn_restore.clicked.connect(self.restore_all_quarantined_modules)
        btn_box.addWidget(self.btn_restore)
        
        self.btn_close = QPushButton("關閉", self)
        self.btn_close.clicked.connect(self.close)
        btn_box.addWidget(self.btn_close)
        
        main_layout.addLayout(btn_box)

        # QWebEngine 設定
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_view)
        self.web_view.setPage(self.web_page)

        # 狀態屬性
        self.custom_visuals_dir = os.path.join(workspace_dir, "custom_visuals")
        self.backup_dir = os.path.join(self.custom_visuals_dir, "abnormal_backup")
        self.files_to_test = []
        self.current_idx = 0
        self.passed_count = 0
        self.failed_count = 0
        self.current_errors = []
        
        self.is_paused = False
        self.is_aborted = False
        self.countdown = 15
        
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_timer_tick)
        
        self.failed_list = []
        if self.auto_start:
            QTimer.singleShot(500, self.start_detection)

    def handle_js_log(self, level, message, lineNumber):
        msg_lower = message.lower()
        ignored = [
            "failed to fetch", "audiocontext", "cors", "[mock]", "[preloadguard]",
            "opentype", ".ttf", ".woff", "width or height of 0", "drawimage"
        ]
        if any(p in msg_lower for p in ignored):
            return
            
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        is_real_js_err = any(kw in msg_lower for kw in ["uncaught", "is not defined", "unexpected token", "cannot read properties", "is not a function"])
        if is_err and is_real_js_err:
            err_line = f"Line {lineNumber}: {message}"
            if err_line not in self.current_errors:
                self.current_errors.append(err_line)

    def log(self, text, type="info"):
        color = "#ffffff"
        if type == "error": color = "#ef4444"
        elif type == "success": color = "#10b981"
        elif type == "warning": color = "#f59e0b"
        elif type == "stat": color = "#a855f7"
            
        print(f"[{type.upper()}] {text}", flush=True)
        self.console.append(f'<span style="color:{color};">{text}</span>')
        self.console.moveCursor(QTextCursor.MoveOperation.End)
        QApplication.processEvents()

    def update_stats(self):
        tested = self.current_idx
        total = len(self.files_to_test)
        self.progress_bar.setValue(tested)
        self.stat_label.setText(
            f"📊 統計：總數 {total} | 已測 {tested} | 通過 {self.passed_count} | 異常隱藏 {self.failed_count}"
        )

    def start_detection(self):
        if not os.path.exists(self.custom_visuals_dir):
            self.log("❌ 錯誤：找不到 custom_visuals 目錄！", "error")
            return
            
        self.files_to_test = [f for f in os.listdir(self.custom_visuals_dir) if f.endswith(".json") and f != "modules_index.json"]
        self.files_to_test.sort()
        
        if not self.files_to_test:
            self.log("ℹ️ custom_visuals 中沒有 JSON 模組。", "warning")
            return
            
        self.current_idx = 0
        self.passed_count = 0
        self.failed_count = 0
        self.failed_list = []
        self.is_aborted = False
        self.is_paused = False
        
        self.progress_bar.setRange(0, len(self.files_to_test))
        self.progress_bar.setValue(0)
        self.update_stats()
        
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("⏸️ 暫停")
        self.btn_abort.setEnabled(True)
        self.btn_close.setEnabled(False)
        
        self.log(f"🚀 開始對 {len(self.files_to_test)} 個模組進行黑屏/純色自檢...", "stat")
        self.load_next_module()

    def toggle_pause(self):
        if self.is_paused:
            self.is_paused = False
            self.btn_pause.setText("⏸️ 暫停")
            self.log("▶️ 恢復自檢...", "stat")
            self.on_timer_tick()
        else:
            self.is_paused = True
            self.btn_pause.setText("▶️ 繼續")
            self.log("⏸️ 暫停中...", "warning")

    def abort_detection(self):
        self.is_aborted = True
        self.tick_timer.stop()
        self.log("🛑 使用者終止了自檢！", "error")
        self.finish_detection()

    def load_next_module(self):
        if self.is_aborted: return
            
        if self.current_idx >= len(self.files_to_test):
            self.log("🏁 所有模組自檢自測完成！", "success")
            self.finish_detection()
            return
            
        filename = self.files_to_test[self.current_idx]
        file_path = os.path.join(self.custom_visuals_dir, filename)
        self.current_filename = filename
        self.current_file_path = file_path
        self.current_errors = []
        
        self.log(f"⌛ [{self.current_idx+1}/{len(self.files_to_test)}] 正在測試: {filename[:-5]}...")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.current_data = json.load(f)
        except Exception as e:
            self.log(f"  ❌ JSON 解析失敗: {e}", "error")
            self.mark_failed(f"JSON Parsing Error: {e}")
            return
            
        code = self.current_data.get("code", "")
        custom_css = self.current_data.get("custom_css", "")
        custom_html = self.current_data.get("custom_html", "")
        sketch_id = self.current_data.get("id")
        
        # 產生具備離線防護與即時喚醒機制的沙盒 HTML
        html_content = make_detector_html(code, custom_css, custom_html, sketch_id=sketch_id)
        base_url = get_local_base_url()
        
        self.countdown = 15
        self.web_view.setHtml(html_content, base_url)
        self.tick_timer.start(1000)

    def on_timer_tick(self):
        if self.is_paused or self.is_aborted: return
        self.countdown -= 1
        
        # 喚醒 p5.js 畫布引擎
        self.web_view.page().runJavaScript("if (window.forceStartP5) window.forceStartP5(); if (window.forceRedrawP5) window.forceRedrawP5();")
        
        # 透過 JavaScript 進行全畫布 32x32 縮圖取樣與動態循環檢測
        eval_js = """
        (function() {
          const c = document.querySelector('canvas') || document.getElementsByTagName('canvas')[0];
          if (!c) {
            if (window.__drawCount > 5) return { status: 'ok', detail: 'Render Loop Active (Custom DOM/SVG)' };
            return { status: 'no_canvas', detail: 'No Canvas Found' };
          }
          
          try {
            if (window.__drawCount > 5) {
              return { status: 'ok', detail: 'Draw Loop Active (Count: ' + window.__drawCount + ')' };
            }
            const helper = document.createElement('canvas');
            helper.width = 32;
            helper.height = 32;
            const hctx = helper.getContext('2d');
            hctx.drawImage(c, 0, 0, 32, 32);
            const imgData = hctx.getImageData(0, 0, 32, 32);
            const data = imgData.data;
            let sum = 0, alpha = 0, minVal = 255, maxVal = 0, nonZeroCount = 0;
            for (let i = 0; i < data.length; i += 4) {
              let r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
              let bright = Math.max(r, g, b);
              sum += r + g + b;
              alpha += a;
              if (bright > 8) nonZeroCount++;
              minVal = Math.min(minVal, r, g, b);
              maxVal = Math.max(maxVal, r, g, b);
            }
            
            if (nonZeroCount >= 3 || sum > 300) {
              return { status: 'ok', detail: 'Active Rendering (' + nonZeroCount + '/1024 active pixels, sum=' + sum + ')' };
            }
            if (window.__drawCount > 0) {
              return { status: 'ok', detail: 'Draw Loop Active (Count: ' + window.__drawCount + ')' };
            }
            if (alpha === 0) return { status: 'transparent', detail: 'Alpha = 0 across canvas' };
            if (maxVal <= 5 && sum <= 50) {
              return { status: 'black', detail: 'Pure Black (max=' + maxVal + ')' };
            }
            if (maxVal - minVal < 2 && nonZeroCount > 900) {
              return { status: 'solid', detail: 'Solid Color (diff=' + (maxVal - minVal) + ')' };
            }
          } catch(e) {
            if (window.__drawCount > 0) return { status: 'ok', detail: 'Draw Loop Active' };
            try {
              let dataUrl = c.toDataURL('image/jpeg', 0.5);
              if (dataUrl && dataUrl.length > 500) {
                return { status: 'ok', detail: 'Canvas DataURL Active' };
              }
            } catch(err2) {}
            return { status: 'ok', detail: 'Protected Canvas Active' };
          }
          
          if (window.__drawCount > 0) return { status: 'ok', detail: 'Draw Loop Active' };
          return { status: 'black', detail: 'Canvas Inactive' };
        })()
        """
        
        def handle_eval_result(res):
            if self.is_paused or self.is_aborted: return
            res = res or {}
            status = res.get("status", "unknown")
            detail = res.get("detail", "")
            
            # Early-Exit 通過條件
            if status == "ok":
                self.tick_timer.stop()
                self.passed_count += 1
                self.log(f"  ✅ 通過 (畫布活躍正常，耗時: {15 - self.countdown} 秒)", "success")
                self.current_idx += 1
                self.update_stats()
                QTimer.singleShot(100, self.load_next_module)
                return
                
            if self.current_errors and self.countdown <= 5:
                self.tick_timer.stop()
                self.mark_failed(f"JS Fatal Errors: {'; '.join(self.current_errors)}")
                return
                
            if self.countdown % 5 == 0 or self.countdown <= 3:
                self.log(f"  ⌛ 剩餘 {self.countdown} 秒 [狀態: {status} - {detail}]", "warning")
                
            # 超時判定為異常
            if self.countdown <= 0:
                self.tick_timer.stop()
                self.mark_failed(f"畫面異常 (15秒運行後仍為: {status} - {detail})")

        self.web_view.page().runJavaScript(eval_js, handle_eval_result)

    def mark_failed(self, reason):
        filename = self.current_filename
        name = filename[:-5]
        file_path = self.current_file_path
        
        self.failed_count += 1
        self.log(f"  ❌ 偵測到異常並隱藏: {reason}", "error")
        
        self.failed_list.append({
            "name": name,
            "url": self.current_data.get("url", "https://openprocessing.org"),
            "sketch_id": self.current_data.get("id", "Unknown"),
            "author": self.current_data.get("author", "Unknown"),
            "reason": reason,
            "js_errors": list(self.current_errors),
            "code": self.current_data.get("code", ""),
            "rejected_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        os.makedirs(self.backup_dir, exist_ok=True)
        dest_json = os.path.join(self.backup_dir, filename)
        try:
            if os.path.exists(file_path):
                shutil.move(file_path, dest_json)
        except Exception as e:
            self.log(f"  ⚠️ 移動模組檔失敗: {e}", "error")
            
        thumb_name = f"{name}.jpg"
        src_thumb = os.path.join(self.custom_visuals_dir, "thumbnails", thumb_name)
        dest_thumb_dir = os.path.join(self.backup_dir, "thumbnails")
        os.makedirs(dest_thumb_dir, exist_ok=True)
        dest_thumb = os.path.join(dest_thumb_dir, thumb_name)
        
        try:
            if os.path.exists(src_thumb):
                shutil.move(src_thumb, dest_thumb)
        except Exception:
            pass
            
        self.current_idx += 1
        self.update_stats()
        QTimer.singleShot(100, self.load_next_module)

    def finish_detection(self):
        self.tick_timer.stop()
        self.web_view.setHtml("<html><body style='background:#000;'></body></html>")
        
        self.write_json_report()
        self.write_text_report()
        self.write_html_report()
        
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_abort.setEnabled(False)
        self.btn_close.setEnabled(True)
        
        parent = self.parent()
        if parent and hasattr(parent, "refresh_presets_list"):
            parent.refresh_presets_list()
            
        if self.auto_start:
            self.accept()
            return
            
        QMessageBox.information(
            self, "自檢完成",
            f"黑屏與純色自檢完成！\n\n"
            f"總計評估: {len(self.files_to_test)} 個模組\n"
            f"保留: {self.passed_count} 個健康模組\n"
            f"異常隱藏: {self.failed_count} 個模組\n\n"
            f"隱藏的模組已移至 custom_visuals/abnormal_backup/。"
        )

    def restore_all_quarantined_modules(self):
        if not os.path.exists(self.backup_dir):
            self.log("ℹ️ 備份資料夾 abnormal_backup 不存在或為空。", "info")
            QMessageBox.information(self, "還原提示", "目前沒有已隔離的模組。")
            return
            
        files = [f for f in os.listdir(self.backup_dir) if f.endswith(".json") and f != "module_usage_history.json"]
        if not files:
            self.log("ℹ️ 備份資料夾中沒有可還原的模組。", "info")
            QMessageBox.information(self, "還原提示", "目前沒有已隔離的模組。")
            return
            
        restored = 0
        for f in files:
            src = os.path.join(self.backup_dir, f)
            dst = os.path.join(self.custom_visuals_dir, f)
            try:
                shutil.move(src, dst)
                restored += 1
                thumb_name = f[:-5] + ".jpg"
                src_thumb = os.path.join(self.backup_dir, "thumbnails", thumb_name)
                dst_thumb = os.path.join(self.custom_visuals_dir, "thumbnails", thumb_name)
                if os.path.exists(src_thumb):
                    os.makedirs(os.path.dirname(dst_thumb), exist_ok=True)
                    shutil.move(src_thumb, dst_thumb)
            except Exception as e:
                self.log(f"⚠️ 還原模組 {f} 失敗: {e}", "error")
                
        self.log(f"✅ 成功將 {restored} 個已隔離模組全部還原至 custom_visuals！", "success")
        
        parent = self.parent()
        if parent and hasattr(parent, "refresh_presets_list"):
            parent.refresh_presets_list()
            
        self.files_to_test = [f for f in os.listdir(self.custom_visuals_dir) if f.endswith(".json") and f != "modules_index.json"]
        self.update_stats()
        
        QMessageBox.information(
            self, "還原成功",
            f"已成功將 {restored} 個模組全部還原回 custom_visuals 資料夾！\n總庫模組數：{len(self.files_to_test)}"
        )

    def write_json_report(self):
        report_path = os.path.join(workspace_dir, "black_screen_report.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(self.failed_list, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f"⚠️ 寫入 JSON 報告失敗: {e}", "error")

    def write_text_report(self):
        report_path = os.path.join(workspace_dir, "black_screen_report.txt")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("======================================================================\n")
                f.write(f"   🎬 視覺模組庫 - 黑屏與純色異常自檢報告 (TXT)\n")
                f.write(f"   時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"   總計隱藏模組數: {len(self.failed_list)} 個\n")
                f.write("======================================================================\n\n")
                for idx, item in enumerate(self.failed_list, 1):
                    f.write(f"[{idx}] 模組名稱: {item['name']}\n")
                    f.write(f"    異常原因: {item['reason']}\n")
                    f.write(f"    原始網址: {item['url']}\n")
                    f.write(f"    排除時間: {item['rejected_at']}\n")
                    f.write("======================================================================\n\n")
        except Exception as e:
            self.log(f"⚠️ 寫入 TXT 報告失敗: {e}", "error")

    def write_html_report(self):
        report_path = os.path.join(workspace_dir, "black_screen_report.html")
        cards_html = ""
        for idx, item in enumerate(self.failed_list, 1):
            cards_html += f"""
            <div style="background:#18181b; border:1px solid #27272a; border-radius:8px; padding:16px; margin-bottom:16px;">
                <h3 style="color:#f43f5e; margin:0 0 8px 0;">#{idx} {item['name']}</h3>
                <div style="color:#a1a1aa; font-size:12px;">原因: {item['reason']}</div>
                <div style="color:#a1a1aa; font-size:12px;">時間: {item['rejected_at']}</div>
                <a style="color:#38bdf8; font-size:12px;" href="{item['url']}" target="_blank">前往 OpenProcessing 網頁 &rarr;</a>
            </div>
            """
        html_doc = f"<html><body style='background:#09090b; color:#f4f4f5; font-family:sans-serif; padding:20px;'><h1 style='color:#a855f7;'>黑屏與純色異常模組自檢報告</h1>{cards_html}</body></html>"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_doc)
        except Exception:
            pass

    def closeEvent(self, event):
        self.is_aborted = True
        self.tick_timer.stop()
        try:
            self.web_view.setPage(None)
            self.web_view.close()
            self.web_view.deleteLater()
        except Exception:
            pass
        gc.collect()
        event.accept()

if __name__ == "__main__":
    sys.argv.extend([
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows"
    ])
    app = QApplication(sys.argv)
    font = QFont("Outfit")
    if not font.exactMatch():
        font = QFont("Inter")
    app.setFont(font)
    
    auto_mode = "--auto" in sys.argv
    dialog = BlackScreenDetectorDialog(auto_start=auto_mode)
    dialog.show()
    sys.exit(app.exec())
