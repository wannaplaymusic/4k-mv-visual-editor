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
from PyQt6.QtGui import QTextCursor, QFont

# Ensure main directory is in path
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

# Import constants from main app
try:
    from main import P5_V2_COMPAT_SHIM, OVERRIDE_16_9_JS, MOCK_NATIVE_AUDIO_JS, MOCK_P5_JS
except ImportError:
    # Fallback default constants in case of import issue
    P5_V2_COMPAT_SHIM = ""
    OVERRIDE_16_9_JS = ""
    MOCK_NATIVE_AUDIO_JS = ""
    MOCK_P5_JS = ""

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, log_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_callback = log_callback

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        self.log_callback(level, message, lineNumber)

def make_detector_html(code, custom_css="", custom_html=""):
    is_module = "import " in code or "export " in code
    script_tag = f'<script type="module">console.log("[DEBUG] SKETCH SCRIPT RUNS");\n{code}</script>' if is_module else f'<script>console.log("[DEBUG] SKETCH SCRIPT RUNS");\n{code}</script>'
    
    html_template = """<!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body { margin: 0; overflow: hidden; background: #000; display: flex; justify-content: center; align-items: center; }
        canvas { display: block !important; position: absolute !important; left: 50% !important; top: 50% !important; transform: translate(-50%, -50%) !important; width: 100vw !important; height: 100vh !important; max-width: 100vw !important; max-height: 100vh !important; object-fit: cover !important; }
        CUSTOM_CSS_PLACEHOLDER
        body canvas {
          position: absolute !important;
          left: 50% !important;
          top: 50% !important;
          transform: translate(-50%, -50%) !important;
          width: 100vw !important;
          height: 100vh !important;
          max-width: 100vw !important;
          max-height: 100vh !important;
          object-fit: cover !important;
        }
      </style>
      <script>
        window.__jsErrors = [];
        window.__drawCount = 0;
        window.__setupFinished = false;

        (function() {
          let wrappedSetup = null;
          Object.defineProperty(window, 'setup', {
            get: function() { return wrappedSetup; },
            set: function(val) {
              if (typeof val === 'function') {
                wrappedSetup = function(...args) {
                  window.__setupFinished = true;
                  console.log("[DEBUG] global setup() called");
                  return val.apply(this, args);
                };
              } else {
                wrappedSetup = val;
              }
            },
            configurable: true,
            enumerable: true
          });

          let wrappedDraw = null;
          Object.defineProperty(window, 'draw', {
            get: function() { return wrappedDraw; },
            set: function(val) {
              if (typeof val === 'function') {
                wrappedDraw = function(...args) {
                  window.__drawCount = (window.__drawCount || 0) + 1;
                  if (window.__drawCount % 30 === 1) {
                    console.log("[DEBUG] global draw() called, count=" + window.__drawCount);
                  }
                  return val.apply(this, args);
                };
              } else {
                wrappedDraw = val;
              }
            },
            configurable: true,
            enumerable: true
          });
        })();


        // Hook instance setup/draw via p5 constructor wrapper
        (function() {
          const checkP5 = setInterval(() => {
            if (typeof p5 !== 'undefined') {
              clearInterval(checkP5);
              const OriginalP5 = window.p5;
              window.p5 = function(sketchFunc, ...args) {
                if (typeof sketchFunc !== 'function') {
                  return new OriginalP5(sketchFunc, ...args);
                }
                const wrappedSketch = function(p) {
                  sketchFunc(p);
                  const origPSetup = p.setup;
                  p.setup = function() {
                    window.__setupFinished = true;
                    console.log("[DEBUG] instance p.setup() called");
                    if (origPSetup) origPSetup.call(p);
                  };
                  const origPDraw = p.draw;
                  p.draw = function() {
                    window.__drawCount = (window.__drawCount || 0) + 1;
                    if (window.__drawCount % 30 === 1) {
                      console.log("[DEBUG] instance p.draw() called, count=" + window.__drawCount);
                    }
                    if (origPDraw) origPDraw.call(p);
                  };
                };
                return new OriginalP5(wrappedSketch, ...args);
              };
              Object.assign(window.p5, OriginalP5);
              console.log("[DEBUG] p5 constructor hooked successfully");
            }
          }, 50);
        })();

        window.onerror = function(message, source, lineno, colno, error) {
          if (message && message.indexOf('vertices') !== -1) {
            return true; 
          }
          window.__jsErrors.push(message + " (Line " + lineno + ")");
          return false;
        };
        window.addEventListener('unhandledrejection', function(event) {
          const reason = event.reason ? (event.reason.message || String(event.reason)) : "";
          if (reason && reason.indexOf('vertices') !== -1) {
            return;
          }
          window.__jsErrors.push("Promise Rejected: " + (reason || "Unknown Error"));
        });
      </script>
      <script src="custom_visuals/libs/p5.min.js"></script>
      <script>
        if (typeof p5 !== 'undefined' && p5.prototype) {
          const origSetup = p5.prototype.setup;
          p5.prototype.setup = function() {
            window._p5Instance = this;
            if (origSetup) {
              return origSetup.apply(this, arguments);
            }
          };

          const origDraw = p5.prototype.draw;
          p5.prototype.draw = function() {
            window.__drawCount = (window.__drawCount || 0) + 1;
            window._p5Instance = this;
            if (origDraw) {
              return origDraw.apply(this, arguments);
            }
          };
        }
      </script>
      <script>{P5_V2_COMPAT_SHIM}</script>
      <script src="custom_visuals/libs/p5.sound.min.js"></script>
      <script src="custom_visuals/libs/p5.func.min.js"></script>
      <script src="custom_visuals/libs/gsap.min.js"></script>
      <script src="custom_visuals/libs/p5.flex.min.js"></script>
      <script src="custom_visuals/libs/rampensau.js"></script>
      <script src="custom_visuals/libs/chroma.min.js"></script>
      <script>
        AUDIO_MOCK_PLACEHOLDER
        if (typeof OPC === 'undefined') {
          window.OPC = {
            slider: function(name, value) { window[name] = value; return this; },
            button: function() { return this; },
            toggle: function(name, value) { window[name] = value; return this; },
            color: function(name, value) { window[name] = value; return this; },
            select: function(name, value) { window[name] = value; return this; },
            text: function(name, value) { window[name] = value; return this; },
            setGlobal: function(name, value) { window[name] = value; }
          };
        }
      </script>
      <script>
        // Force WebGL drawing buffer preservation
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

        // Mock audio parameters and interactions
        window.frequency = 50;
        window.storyboardWeight = 50;
        window.postFxIntensity = 50;
        window.isBeat = false;
        window.beatEnergy = 0;
        window.audioLow = 0.5;
        window.audioMid = 0.5;
        window.audioHigh = 0.5;
        
        window.simulatedMouseX = 640;
        window.simulatedMouseY = 360;
        window.simulatedPMouseX = 640;
        window.simulatedPMouseY = 360;

        let sandboxFrameCounter = 0;
        function tick() {
          sandboxFrameCounter++;
          
          // Oscillate audio parameters dynamically so visualizers move
          window.audioLow = 0.3 + 0.45 * Math.sin(sandboxFrameCounter * 0.08);
          window.audioMid = 0.4 + 0.35 * Math.sin(sandboxFrameCounter * 0.06);
          window.audioHigh = 0.2 + 0.55 * Math.sin(sandboxFrameCounter * 0.11);
          window.beatEnergy = 0.5 + 0.45 * Math.sin(sandboxFrameCounter * 0.15);
          window.isBeat = (sandboxFrameCounter % 35 === 0);
          
          // Simulate mouse interactions every 30 frames (0.5s)
          if (sandboxFrameCounter % 30 === 0) {
            let w = window.innerWidth || 1280;
            let h = window.innerHeight || 720;
            
            window.simulatedPMouseX = window.simulatedMouseX;
            window.simulatedPMouseY = window.simulatedMouseY;
            
            window.simulatedMouseX = w / 2 + Math.sin(sandboxFrameCounter * 0.035) * w * 0.38;
            window.simulatedMouseY = h / 2 + Math.cos(sandboxFrameCounter * 0.035) * h * 0.38;
            
            try {
              let moveEvt = new MouseEvent('mousemove', { clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, bubbles: true });
              let downEvt = new MouseEvent('mousedown', { clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, button: 0, buttons: 1, bubbles: true });
              let clickEvt = new MouseEvent('click', { clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, bubbles: true });
              let upEvt = new MouseEvent('mouseup', { clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, button: 0, bubbles: true });
              
              window.dispatchEvent(moveEvt);
              window.dispatchEvent(downEvt);
              window.dispatchEvent(clickEvt);
              window.dispatchEvent(upEvt);
              
              let canvas = document.querySelector('canvas');
              if (canvas) {
                canvas.dispatchEvent(moveEvt);
                canvas.dispatchEvent(downEvt);
                canvas.dispatchEvent(clickEvt);
                canvas.dispatchEvent(upEvt);
              }
            } catch(e) {}
            
            if (typeof mousePressed === 'function') { try { mousePressed(); } catch(e) {} }
            if (typeof mouseClicked === 'function') { try { mouseClicked(); } catch(e) {} }
            if (typeof mouseDragged === 'function') { try { mouseDragged(); } catch(e) {} }
          }
          requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);

        // Pixel check function (down-sampling average analyzer)
        window.checkCanvasPixels = function() {
          const canvases = document.getElementsByTagName("canvas");
          if (canvases.length === 0) {
            return { status: "no_canvas", detail: "No canvas element created" };
          }
          const canvas = canvases[0];
          if (canvas.width === 0 || canvas.height === 0) {
            return { status: "zero_size", detail: "Canvas size is 0x0" };
          }
          try {
            const tempCanvas = document.createElement("canvas");
            tempCanvas.width = 10;
            tempCanvas.height = 10;
            const tempCtx = tempCanvas.getContext("2d");
            tempCtx.drawImage(canvas, 0, 0, 10, 10);
            const imgData = tempCtx.getImageData(0, 0, 10, 10);
            const data = imgData.data;
            
            let r0 = data[0], g0 = data[1], b0 = data[2], a0 = data[3];
            let allSame = true;
            let allTransparent = true;
            let allBlack = true;
            
            for (let i = 0; i < data.length; i += 4) {
              let r = data[i];
              let g = data[i+1];
              let b = data[i+2];
              let a = data[i+3];
              
              if (a > 0) { allTransparent = false; }
              if (r !== 0 || g !== 0 || b !== 0) { allBlack = false; }
              if (r !== r0 || g !== g0 || b !== b0 || a !== a0) { allSame = false; }
            }
            
            if (allTransparent) return { status: "transparent", detail: "Canvas is completely transparent (alpha = 0)" };
            if (allBlack) return { status: "black", detail: "Canvas is completely black (RGB = 0, 0, 0)" };
            if (allSame) return { status: "solid_color", detail: `Canvas is solid color: rgba(${r0},${g0},${b0},${a0/255})` };
            
            return { status: "ok", detail: "Canvas rendering is active and varied" };
          } catch(e) {
            return { status: "error", detail: "Failed to read pixels: " + e.message };
          }
        };
      </script>
    </head>
    <body>
      CUSTOM_HTML_PLACEHOLDER
      SCRIPT_TAG_PLACEHOLDER
      <script>
        // Wrap setup and draw after they are defined by the sketch script
        (function() {
          console.log("[DEBUG] Wrapper script runs, typeof window.setup=" + typeof window.setup + ", typeof window.draw=" + typeof window.draw);
          if (typeof window.setup === 'function') {
            const origSetup = window.setup;
            window.setup = function(...args) {
              window.__setupFinished = true;
              console.log("[DEBUG] global setup() called");
              return origSetup.apply(this, args);
            };
          }
          if (typeof window.draw === 'function') {
            const origDraw = window.draw;
            window.draw = function(...args) {
              window.__drawCount = (window.__drawCount || 0) + 1;
              if (window.__drawCount % 30 === 1) {
                console.log("[DEBUG] global draw() called, count=" + window.__drawCount);
              }
              return origDraw.apply(this, args);
            };
          }
          
          // Watchdog and force methods to bypass Chromium background event loop throttling
          window.forceStartP5 = function() {
            if (window._p5Instance && !window.__setupFinished) {
              console.log("[DEBUG] p5 instance exists but setup not finished. Force calling _setup...");
              try {
                window._p5Instance._preloadCount = 0;
                if (typeof window._p5Instance._setup === 'function') {
                  window._p5Instance._setup();
                } else if (typeof window._p5Instance.setup === 'function') {
                  window._p5Instance.setup();
                } else if (typeof window.setup === 'function') {
                  window.setup();
                }
                window.__setupFinished = true;
                return { success: true, setupFinished: window.__setupFinished, forcedStartInstance: true };
              } catch(e) {
                console.error("[DEBUG] Force start instance failed: " + e.message);
                return { success: false, error: e.message };
              }
            }
            if (!window.__setupFinished && typeof p5 !== 'undefined') {
              console.log("[DEBUG] Force starting p5 via host command...");
              try {
                const inst = new p5();
                window._p5Instance = inst;
                inst._preloadCount = 0;
                if (inst && typeof inst._setup === 'function') {
                  inst._setup();
                } else if (inst && typeof inst._start === 'function') {
                  inst._start();
                }
                return { success: true, setupFinished: window.__setupFinished, forcedNewInstance: true };
              } catch(e) {
                console.error("[DEBUG] Force start failed: " + e.message);
                return { success: false, error: e.message };
              }
            }
            return { success: true, setupFinished: window.__setupFinished, alreadyStarted: true };
          };

          window.forceRedrawP5 = function() {
            if (window._p5Instance) {
              try {
                if (typeof window._p5Instance._draw === 'function') {
                  window._p5Instance._draw();
                } else {
                  window._p5Instance.redraw();
                }
                return true;
              } catch(e) {
                return false;
              }
            }
            return false;
          };
          
          setTimeout(() => {
            window.forceStartP5();
          }, 1000);
        })();
      </script>
    </body>
    </html>"""
    
    return html_template.replace("CUSTOM_CSS_PLACEHOLDER", custom_css)\
                        .replace("CUSTOM_HTML_PLACEHOLDER", custom_html)\
                        .replace("SCRIPT_TAG_PLACEHOLDER", f"<script>{OVERRIDE_16_9_JS}</script>\n" + script_tag)\
                        .replace("AUDIO_MOCK_PLACEHOLDER", MOCK_NATIVE_AUDIO_JS + "\n" + MOCK_P5_JS)\
                        .replace("{P5_V2_COMPAT_SHIM}", P5_V2_COMPAT_SHIM)

class BlackScreenDetectorDialog(QDialog):
    def __init__(self, parent=None, auto_start=False):
        super().__init__(parent)
        self.auto_start = auto_start
        self.setWindowTitle("🎬 視覺模組黑屏與純色自檢自測清理工具")
        self.resize(1150, 700)
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
                border-radius: 6px; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px;
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

        # Main Layout split into preview and logs
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        desc = QLabel(
            "此工具將逐一對 `custom_visuals` 資料夾內的所有視覺模組進行 15 秒試運行：\n"
            "1. 實時動態模擬音訊及滑鼠互動，喚醒音樂響應模組。\n"
            "2. 自動執行像素 analysis（Early-Exit）：若在 1-2 秒內檢測到畫面呈彩色彩色變化，即刻通過以節省時間。\n"
            "3. 若 15 秒後畫面仍是**一片黑、純色或全透明**，則將其移動至備份文件夾隱藏，並生成專屬 txt/html/json 錯誤報告。", 
            self
        )
        main_layout.addWidget(desc)

        # Center area layout: horizontal splitter
        center_layout = QHBoxLayout()
        
        # Left side: Web Engine View for live preview
        self.preview_container = QWidget(self)
        self.preview_container.setMinimumSize(640, 360)
        self.preview_container.setStyleSheet("background-color: #000000; border: 1px solid #27272a; border-radius: 8px;")
        preview_box = QVBoxLayout(self.preview_container)
        preview_box.setContentsMargins(0, 0, 0, 0)
        
        self.web_view = QWebEngineView(self.preview_container)
        self.web_view.setMinimumSize(640, 360)
        preview_box.addWidget(self.web_view)
        center_layout.addWidget(self.preview_container)

        # Right side: console logs
        self.console = QTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setMinimumWidth(400)
        center_layout.addWidget(self.console)
        
        main_layout.addLayout(center_layout)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Statistics / Current Info label
        self.stat_label = QLabel("📊 統計：已測試 0 | 通過 0 | 異常隱藏 0", self)
        self.stat_label.setStyleSheet("color: #a1a1aa; font-weight: bold;")
        main_layout.addWidget(self.stat_label)
        
        # Buttons layout
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
        
        self.btn_close = QPushButton("關閉", self)
        self.btn_close.clicked.connect(self.close)
        btn_box.addWidget(self.btn_close)
        
        main_layout.addLayout(btn_box)

        # QWebEngine config
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_view)
        self.web_view.setPage(self.web_page)

        # State vars
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
        
        # Timer for test loop
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.on_timer_tick)
        
        self.failed_list = []
        if self.auto_start:
            QTimer.singleShot(500, self.start_detection)

    def handle_js_log(self, level, message, lineNumber):
        print(f"[BROWSER_LOG] Line {lineNumber}: {message}")
        sys.stdout.flush()
        msg_lower = message.lower()
        if "failed to fetch" in msg_lower or "audiocontext" in msg_lower or "cors" in msg_lower:
            return
        if "[mock]" in msg_lower or "[loadingwatchdog]" in msg_lower or "audio decoding failed" in msg_lower:
            return
        if "dummy silent buffer" in msg_lower or "decodeaudiodata" in msg_lower:
            return
        if "[preloadguard]" in msg_lower or "[object event]" in msg_lower:
            return
        if "p5.sound" in msg_lower or "p5.min.js" in msg_lower:
            return
        if "opentype" in msg_lower or ".ttf" in msg_lower or ".otf" in msg_lower or ".woff" in msg_lower:
            return
        if "width or height of 0" in msg_lower or "drawimage" in msg_lower:
            return
        if message.strip() in ("[object Event]", "[object ErrorEvent]"):
            return
        if "mime type" in msg_lower or "refused to execute script" in msg_lower or "net::err" in msg_lower:
            return
        if "useprogram" in msg_lower or "webglprogram" in msg_lower or "webgl" in msg_lower:
            return
        if "ensurecompiledoncontext" in msg_lower or "shader" in msg_lower:
            return
        if any(lib in msg_lower for lib in ["ml5 is not defined", "tone is not defined", "simplex",
                "lil is not defined", "resolvelygia", "svgfont", "opc' has already been declared",
                "matter is not defined", "dat is not defined", "csslint", "plotsvg", "chromotome", "failed to load resource"]):
            return
        if ".createcanvas is not a function" in msg_lower:
            return
        if "is not valid json" in msg_lower and "unexpected token '<'" in msg_lower:
            return
        if ("connect" in msg_lower or "disconnect" in msg_lower) and lineNumber <= 2:
            return
            
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        # Check if it is a real JavaScript execution error (has uncaught, syntax error, or is a common JS error type)
        is_real_js_err = "uncaught" in msg_lower or "is not defined" in msg_lower or "unexpected token" in msg_lower or "cannot read properties" in msg_lower or "is not a function" in msg_lower or "is not a constructor" in msg_lower
        if is_err and is_real_js_err:
            err_line = f"Line {lineNumber}: {message}"
            if err_line not in self.current_errors:
                self.current_errors.append(err_line)

    def log(self, text, type="info"):
        color = "#ffffff"
        if type == "error":
            color = "#ef4444"
        elif type == "success":
            color = "#10b981"
        elif type == "warning":
            color = "#f59e0b"
        elif type == "stat":
            color = "#a855f7"
            
        self.console.append(f'<span style="color:{color};">{text}</span>')
        self.console.moveCursor(QTextCursor.MoveOperation.End)
        print(f"[{type.upper()}] {text}")
        sys.stdout.flush()
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
            
        self.files_to_test = [f for f in os.listdir(self.custom_visuals_dir) if f.endswith(".json")]
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
            self.on_timer_tick() # trigger immediately
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
        if self.is_aborted:
            return
            
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
        
        # Load JSON file
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
        
        html_content = make_detector_html(code, custom_css, custom_html)
        
        # Save temp HTML to workspace to resolve relative script tags
        import random
        self.temp_html_name = f"dummy_detect_{filename[:-5]}_{random.randint(0, 1000000)}.html"
        self.temp_html_path = os.path.join(workspace_dir, self.temp_html_name)
        
        try:
            with open(self.temp_html_path, "w", encoding="utf-8") as hf:
                hf.write(html_content)
        except Exception as e:
            self.log(f"  ❌ 無法建立臨時 HTML: {e}", "error")
            self.mark_failed(f"Temp HTML Creation Error: {e}")
            return
            
        self.web_view.setUrl(QUrl.fromLocalFile(self.temp_html_path))
        self.countdown = 15
        
        # Wait for page to finish loading completely
        loop = QEventLoop()
        def on_load_finished(ok):
            if loop.isRunning():
                loop.quit()
        self.web_view.loadFinished.connect(on_load_finished)
        QTimer.singleShot(4000, loop.quit) # 4s safety timeout
        loop.exec()
        try:
            self.web_view.loadFinished.disconnect(on_load_finished)
        except Exception:
            pass
            
        # Clean up temp HTML file immediately
        try:
            if os.path.exists(self.temp_html_path):
                os.remove(self.temp_html_path)
        except Exception:
            pass
            
        self.tick_timer.start(1000)

    def on_timer_tick(self):
        if self.is_paused or self.is_aborted:
            return
            
        self.countdown -= 1
        
        # 1. Force start p5.js in case Chromium backgrounded tab suspended it
        loop_start = QEventLoop()
        def on_start_done(res):
            print(f"[DEBUG_PYTHON] forceStartP5 result: {res}")
            sys.stdout.flush()
            if loop_start.isRunning():
                loop_start.quit()
        self.web_view.page().runJavaScript("window.forceStartP5()", on_start_done)
        QTimer.singleShot(150, loop_start.quit)
        loop_start.exec()
        
        # 2. Force redraw a frame in case Chromium suspended requestAnimationFrame
        loop_draw = QEventLoop()
        def on_draw_done(res):
            print(f"[DEBUG_PYTHON] forceRedrawP5 result: {res}")
            sys.stdout.flush()
            if loop_draw.isRunning():
                loop_draw.quit()
        self.web_view.page().runJavaScript("window.forceRedrawP5()", on_draw_done)
        QTimer.singleShot(150, loop_draw.quit)
        loop_draw.exec()
        
        # Detailed state query on every tick
        debug_state = {}
        loop_debug = QEventLoop()
        def on_debug_done(debug_val):
            nonlocal debug_state
            debug_state = debug_val if isinstance(debug_val, dict) else {}
            print(f"[DEBUG_STATE] countdown={self.countdown}, state={debug_val}")
            sys.stdout.flush()
            if loop_debug.isRunning():
                loop_debug.quit()
        self.web_view.page().runJavaScript(
            "({ setupFinished: window.__setupFinished, drawCount: window.__drawCount, hasP5Instance: !!window._p5Instance, preloadCount: window._p5Instance ? window._p5Instance._preloadCount : null, errors: window.__jsErrors, testDraw: (()=>{let c=document.getElementsByTagName('canvas')[0]; if(!c)return 'no_canvas'; let ctx=c.getContext('2d'); if(!ctx)return 'no_ctx'; ctx.fillStyle='red'; ctx.fillRect(0,0,1,1); return Array.from(ctx.getImageData(0,0,1,1).data);})() })",
            on_debug_done
        )
        QTimer.singleShot(150, loop_debug.quit)
        loop_debug.exec()
        
        draw_count = debug_state.get("drawCount", 0) or 0
        
        # Grab web view's visible pixels directly using Qt's paint engine.
        # This triggers a synchronous render/composition cycle of the web page.
        status = "no_canvas"
        detail = "Pending check"
        try:
            pixmap = self.web_view.grab()
            image = pixmap.toImage()
            w = image.width()
            h = image.height()
            if w > 0 and h > 0:
                # Sample 100 pixels in a 10x10 grid
                rgba_list = []
                for grid_x in range(10):
                    for grid_y in range(10):
                        px = int(grid_x * (w - 1) / 9)
                        py = int(grid_y * (h - 1) / 9)
                        c = image.pixelColor(px, py)
                        rgba_list.append((c.red(), c.green(), c.blue(), c.alpha()))
                
                # Check if all pixels are transparent
                if all(rgba[3] == 0 for rgba in rgba_list):
                    if draw_count > 30:
                        status = "ok"
                        detail = f"Canvas is active (drawCount={draw_count})"
                    else:
                        status = "transparent"
                        detail = "Canvas is completely transparent (alpha = 0)"
                else:
                    first_color = rgba_list[0]
                    # Check if all pixels are of the same color
                    if all(rgba == first_color for rgba in rgba_list):
                        if draw_count > 30:
                            status = "ok"
                            detail = f"Canvas is active (drawCount={draw_count})"
                        else:
                            if first_color[0] == 0 and first_color[1] == 0 and first_color[2] == 0:
                                status = "black"
                                detail = "Canvas is completely black"
                            else:
                                status = "solid"
                                detail = f"Canvas is a solid color: rgba{first_color}"
                    else:
                        status = "ok"
                        detail = "Canvas rendered active content"
                        
            # Save a debug image to scratch directory if it fails at countdown 0
            if self.countdown == 0 and status != "ok":
                debug_img_path = os.path.join(workspace_dir, "scratch", f"debug_grab_{self.current_filename[:-5]}.png")
                os.makedirs(os.path.dirname(debug_img_path), exist_ok=True)
                pixmap.save(debug_img_path, "PNG")
        except Exception as e:
            status = "grab_error"
            detail = f"Grab failed: {e}"
        
        # Early exit if healthy rendering is detected
        if status == "ok":
            self.tick_timer.stop()
            self.passed_count += 1
            self.log(f"  ✅ 通過 (畫布運行正常，耗時: {15 - self.countdown} 秒)", "success")
            self.current_idx += 1
            self.update_stats()
            self.load_next_module()
            return
            
        # If JS console has fatal errors, exit early as failure
        if self.current_errors:
            self.tick_timer.stop()
            self.mark_failed(f"JS Console Errors: {'; '.join(self.current_errors)}")
            return
            
        # Show status warnings
        if self.countdown % 5 == 0 or self.countdown <= 3:
            self.log(f"  ⌛ 剩餘 {self.countdown} 秒 [狀態: {status} - {detail}]", "warning")
            
        # Out of time: Mark as failed and hide
        if self.countdown <= 0:
            self.tick_timer.stop()
            reason = f"畫面異常 (15秒運行後仍為: {status} - {detail})"
            self.mark_failed(reason)

    def mark_failed(self, reason):
        filename = self.current_filename
        name = filename[:-5]
        file_path = self.current_file_path
        
        self.failed_count += 1
        self.log(f"  ❌ 偵測到異常並隱藏: {reason}", "error")
        
        # Record details
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
        
        # Backup and Hide JSON file
        os.makedirs(self.backup_dir, exist_ok=True)
        dest_json = os.path.join(self.backup_dir, filename)
        try:
            if os.path.exists(file_path):
                shutil.move(file_path, dest_json)
        except Exception as e:
            self.log(f"  ⚠️ 移動模組檔失敗: {e}", "error")
            
        # Backup and Hide thumbnail if exists
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
            
        # Add to abnormal_previews.json for compatibility
        self.append_to_abnormal_previews(name, self.current_data.get("url", "https://openprocessing.org"), self.current_data.get("id", "Unknown"))
        
        self.current_idx += 1
        self.update_stats()
        self.load_next_module()

    def append_to_abnormal_previews(self, name, url, sketch_id):
        ab_path = os.path.join(workspace_dir, "abnormal_previews.json")
        data = []
        if os.path.exists(ab_path):
            try:
                with open(ab_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
                
        # Avoid duplicate entries
        if not any(item.get("id") == sketch_id for item in data):
            data.append({
                "id": sketch_id,
                "title": name,
                "url": url,
                "rejected_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            try:
                with open(ab_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

    def finish_detection(self):
        self.tick_timer.stop()
        self.web_view.setHtml("<html><body style='background:#000;'></body></html>")
        
        # Save Reports
        self.write_json_report()
        self.write_text_report()
        self.write_html_report()
        
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_abort.setEnabled(False)
        self.btn_close.setEnabled(True)
        
        # Refresh main app presets if running within main app
        parent = self.parent()
        if parent and hasattr(parent, "refresh_presets_list"):
            parent.refresh_presets_list()
            
        if self.auto_start:
            self.accept()
            return
            
        QMessageBox.information(
            self, "自檢自測完成",
            f"黑屏與純色自檢完成！\n\n"
            f"總計評估: {len(self.files_to_test)} 個模組\n"
            f"保留: {self.passed_count} 個健康模組\n"
            f"異常隱藏: {self.failed_count} 個模組\n\n"
            f"隱藏的模組已移至 custom_visuals/abnormal_backup/。\n"
            f"詳細分析報告已輸出至黑屏專屬錯誤報告檔案中。"
        )

    def write_json_report(self):
        report_path = os.path.join(workspace_dir, "black_screen_report.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(self.failed_list, f, indent=4, ensure_ascii=False)
            self.log("💾 成功寫入黑屏專屬錯誤報告 (JSON): black_screen_report.json", "success")
        except Exception as e:
            self.log(f"⚠️ 寫入 JSON 報告失敗: {e}", "error")

    def write_text_report(self):
        report_path = os.path.join(workspace_dir, "black_screen_report.txt")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("======================================================================\n")
                f.write("   🎬 音畫互動模組庫 - 黑屏與純色異常模組專屬自檢報告 (TXT 版本)   \n")
                f.write(f"   時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"   總計隱藏模組數: {len(self.failed_list)} 個\n")
                f.write("======================================================================\n\n")
                
                for idx, item in enumerate(self.failed_list, 1):
                    f.write(f"[{idx}] 模組名稱: {item['name']}\n")
                    f.write(f"    Sketch ID: {item['sketch_id']}\n")
                    f.write(f"    原始網址: {item['url']}\n")
                    f.write(f"    排除時間: {item['rejected_at']}\n")
                    f.write(f"    異常原因: {item['reason']}\n")
                    if item['js_errors']:
                        f.write(f"    主控台錯誤: {'; '.join(item['js_errors'])}\n")
                    f.write("    --- 原始程式碼 ---\n")
                    f.write(item['code'] + "\n")
                    f.write("======================================================================\n\n")
            self.log("💾 成功寫入黑屏專屬複製版報告 (TXT): black_screen_report.txt", "success")
        except Exception as e:
            self.log(f"⚠️ 寫入 TXT 報告失敗: {e}", "error")

    def write_html_report(self):
        report_path = os.path.join(workspace_dir, "black_screen_report.html")
        
        cards_html = ""
        for idx, item in enumerate(self.failed_list, 1):
            js_err_section = ""
            if item["js_errors"]:
                js_err_section = f"""
                <div class="card-meta" style="color: #f87171; font-weight: bold;">
                    ❌ 主控台錯誤: {'; '.join(item['js_errors'])}
                </div>
                """
                
            code_escaped = item['code'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            cards_html += f"""
            <div class="card">
                <div class="card-badge">#{idx}</div>
                <div class="card-title">{item['name']}</div>
                <div class="card-meta">Sketch ID: {item['sketch_id']}</div>
                <div class="card-meta">排除原因: <span style="color: #ef4444; font-weight: bold;">{item['reason']}</span></div>
                <div class="card-meta">排除時間: {item['rejected_at']}</div>
                {js_err_section}
                <a class="card-link" href="{item['url']}" target="_blank">🌐 前往 OpenProcessing 原始網頁 &rarr;</a>
                <button class="copy-btn" onclick="copyCode('code-{idx}')">📋 複製模組程式碼</button>
                <div class="code-container">
                    <pre><code id="code-{idx}">{code_escaped}</code></pre>
                </div>
            </div>
            """
            
        html_template = f"""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>黑屏/純色視覺模組自檢排除紀錄報告</title>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    background-color: #09090b;
                    color: #f4f4f5;
                    margin: 0;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 1000px;
                    margin: 0 auto;
                }}
                h1 {{
                    font-family: 'Outfit', sans-serif;
                    font-size: 2.5rem;
                    color: #a855f7;
                    margin-bottom: 8px;
                    background: linear-gradient(135deg, #a855f7, #d946ef);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                .subtitle {{
                    color: #71717a;
                    font-size: 1.1rem;
                    margin-bottom: 40px;
                }}
                .stats-bar {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 16px;
                    margin-bottom: 40px;
                }}
                .stat-card {{
                    background-color: #18181b;
                    border: 1px solid #27272a;
                    border-radius: 12px;
                    padding: 20px;
                    text-align: center;
                }}
                .stat-value {{
                    font-size: 2.2rem;
                    font-weight: bold;
                    color: #a855f7;
                }}
                .stat-label {{
                    color: #71717a;
                    font-size: 0.9rem;
                    margin-top: 4px;
                }}
                .card {{
                    background-color: #18181b;
                    border: 1px solid #27272a;
                    border-radius: 12px;
                    padding: 24px;
                    margin-bottom: 24px;
                    position: relative;
                    overflow: hidden;
                }}
                .card-badge {{
                    position: absolute;
                    top: 20px;
                    right: 20px;
                    background-color: #7c3aed;
                    color: #ffffff;
                    padding: 4px 12px;
                    border-radius: 9999px;
                    font-size: 0.85rem;
                    font-weight: bold;
                }}
                .card-title {{
                    font-size: 1.4rem;
                    font-weight: bold;
                    margin-bottom: 12px;
                    color: #ffffff;
                }}
                .card-meta {{
                    font-size: 0.9rem;
                    color: #a1a1aa;
                    margin-bottom: 6px;
                }}
                .card-link {{
                    display: inline-block;
                    margin-top: 16px;
                    color: #3b82f6;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .card-link:hover {{
                    text-decoration: underline;
                }}
                .copy-btn {{
                    background-color: #27272a;
                    color: #f4f4f5;
                    border: 1px solid #3f3f46;
                    padding: 6px 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 0.85rem;
                    cursor: pointer;
                    margin-left: 16px;
                }}
                .copy-btn:hover {{
                    background-color: #3f3f46;
                }}
                .code-container {{
                    margin-top: 16px;
                    background-color: #09090b;
                    border: 1px solid #27272a;
                    border-radius: 8px;
                    padding: 16px;
                    max-height: 250px;
                    overflow-y: auto;
                }}
                pre {{
                    margin: 0;
                }}
                code {{
                    font-family: 'JetBrains Mono', 'Fira Code', monospace;
                    font-size: 0.85rem;
                    color: #c084fc;
                }}
            </style>
            <script>
                function copyCode(id) {{
                    const code = document.getElementById(id).innerText;
                    navigator.clipboard.writeText(code).then(() => {{
                        alert("模組原始碼已成功複製到剪貼簿！");
                    }}).catch(err => {{
                        alert("複製失敗: " + err);
                    }});
                }}
            </script>
        </head>
        <body>
            <div class="container">
                <h1>🎬 黑屏/純色視覺模組自檢排除報告</h1>
                <div class="subtitle">此報告記錄了經由像素檢測判定為一片黑、純色或全透明的音畫互動模組，並已自動將其移至備份資料夾隱藏。</div>
                
                <div class="stats-bar">
                    <div class="stat-card">
                        <div class="stat-value">{len(self.files_to_test)}</div>
                        <div class="stat-label">評估模組總數</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: #10b981;">{self.passed_count}</div>
                        <div class="stat-label">保留合規數</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: #ef4444;">{self.failed_count}</div>
                        <div class="stat-label">異常隱藏數</div>
                    </div>
                </div>

                <div class="list">
                    {cards_html or '<div class="card" style="text-align:center; color:#71717a;">🎉 太棒了！本次自檢未發現任何黑屏或純色異常模組！</div>'}
                </div>
            </div>
        </body>
        </html>
        """
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_template)
            self.log("💾 成功寫入黑屏專屬視覺化報告 (HTML): black_screen_report.html", "success")
        except Exception as e:
            self.log(f"⚠️ 寫入 HTML 報告失敗: {e}", "error")

    def closeEvent(self, event):
        self.is_aborted = True
        self.tick_timer.stop()
        
        # Clean up temp HTML if exists
        try:
            if hasattr(self, "temp_html_path") and os.path.exists(self.temp_html_path):
                os.remove(self.temp_html_path)
        except Exception:
            pass
            
        # Clean up web view memory explicitly
        try:
            self.web_view.setPage(None)
            self.web_view.setParent(None)
            self.web_view.close()
            self.web_view.deleteLater()
        except Exception:
            pass
        gc.collect()
        event.accept()

if __name__ == "__main__":
    # Append Chromium command line arguments to prevent background throttling
    sys.argv.extend([
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-gpu",
        "--disable-gpu-rasterization",
        "--disable-gpu-compositing"
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
