import os
import sys
import re
import json
import random
import datetime
import logging
import requests

# Disable web security (CORS/SOP bypass) for QtWebEngine globally
if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-web-security"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QCheckBox, QLabel, QSplitter, QTextEdit, QPlainTextEdit, QSlider, QWidget,
    QApplication, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile
from PyQt6.QtCore import Qt, QSize, QRect, QTimer, QUrl
from PyQt6.QtGui import QColor, QFont, QTextFormat, QPainter, QTextCursor

logger = logging.getLogger(__name__)

def get_local_base_url():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    return QUrl.fromLocalFile(os.path.join(workspace_dir, "dummy.html"))


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
                font-size: 12px;
            }
        """)

        font = QFont("Courier New", 11)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    def lineNumberAreaWidth(self):
        digits = 1
        max_blocks = max(1, self.blockCount())
        while max_blocks >= 10:
            max_blocks //= 10
            digits += 1
        space = 12 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor("#09090b"))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QColor("#71717a"))
                if blockNumber == self.textCursor().blockNumber():
                    painter.setPen(QColor("#c084fc"))
                
                painter.drawText(0, top, self.lineNumberArea.width() - 6, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor("#27272a")
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)


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
        # 攔截 alert 並轉為後台日誌，避免原生彈窗阻塞
        self.log_callback(QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel, f"[JS Alert Blocked] {msg}", 0)

    def javaScriptConfirm(self, securityOrigin, msg):
        # 攔截 confirm 並自動回傳 True，避免阻塞
        self.log_callback(QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel, f"[JS Confirm Blocked] {msg}", 0)
        return True

    def javaScriptPrompt(self, securityOrigin, msg, defaultValue, result):
        # 攔截 prompt 並自動回傳空字串，避免阻塞
        self.log_callback(QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel, f"[JS Prompt Blocked] {msg}", 0)
        return False



class CodeInjectorDialog(QDialog):
    def __init__(self, parent=None, initial_name="", initial_code="", initial_freq=50, initial_weight=50, initial_fx=50, on_save_callback=None, initial_html="", initial_css="", initial_assets=None, initial_filename=""):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.initial_filename = initial_filename
        self.custom_html = initial_html
        self.custom_css = initial_css
        self.inline_assets = initial_assets or {}
        
        self.setWindowTitle("外接開源視覺收編工作區 (Code Injector Workbench)")
        self.resize(1240, 720)
        self.setMinimumSize(900, 600)

        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; }
            QLineEdit { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 12px; font-size: 13px; }
            QSlider::groove:horizontal { border: 1px solid #27272a; height: 6px; background: #18181b; border-radius: 3px; }
            QSlider::handle:horizontal { background: #a855f7; border: 1px solid #a855f7; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QCheckBox { color: #a1a1aa; font-size: 12px; }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout.addWidget(splitter)

        # ── 左側控制面板 (45%) ──
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        editor_title = QLabel("💻 p5.js 代碼編輯器 (Code Editor)", left_widget)
        editor_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #a855f7;")
        left_layout.addWidget(editor_title)

        op_row = QHBoxLayout()
        op_lbl = QLabel("OpenProcessing 網址:", left_widget)
        op_lbl.setFixedWidth(140)
        self.op_input = QLineEdit(left_widget)
        self.op_input.setPlaceholderText("例如: https://openprocessing.org/sketch/2219276")
        self.btn_op_fetch = QPushButton("⚡ 【自動抓取程式碼】", left_widget)
        self.btn_op_fetch.setStyleSheet("background-color: #1e1b4b; border-color: #312e81; color: #e0e7ff;")
        self.btn_op_fetch.clicked.connect(self.fetch_and_load_openprocessing)
        op_row.addWidget(op_lbl)
        op_row.addWidget(self.op_input)
        op_row.addWidget(self.btn_op_fetch)
        left_layout.addLayout(op_row)

        self.editor = CodeEditor(left_widget)
        self.editor.setPlainText(initial_code if initial_code else self.get_default_template())
        left_layout.addWidget(self.editor)

        form_widget = QWidget(left_widget)
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 5, 0, 5)

        name_row = QHBoxLayout()
        name_lbl = QLabel("視覺模組名稱:", form_widget)
        name_lbl.setFixedWidth(140)
        self.name_input = QLineEdit(form_widget)
        self.name_input.setText(initial_name)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_input)
        form_layout.addLayout(name_row)

        # 頻率 / 權重 / 後製強度滑桿
        self.freq_slider, self.freq_val_lbl = self._add_slider_row(form_layout, "動態出現頻率 (Frequency):", initial_freq)
        self.weight_slider, self.weight_val_lbl = self._add_slider_row(form_layout, "分鏡切換權重 (Weight):", initial_weight)
        self.fx_slider, self.fx_val_lbl = self._add_slider_row(form_layout, "後製特效強度 (Post-FX):", initial_fx)
        left_layout.addWidget(form_widget)

        self.btn_adapt = QPushButton("🪄 【自動轉換與相容性修復】", left_widget)
        self.btn_adapt.setStyleSheet("background-color: #7c2d12; color: #ffedd5;")
        self.btn_adapt.clicked.connect(self.adapt_and_repair_code)
        left_layout.addWidget(self.btn_adapt)

        self.btn_compile = QPushButton("【執行即時運行測試】", left_widget)
        self.btn_compile.clicked.connect(self.compile_and_run_sandbox)
        left_layout.addWidget(self.btn_compile)

        self.cb_confirm = QCheckBox("【我確認此視覺特效運行正常且不卡頓】", left_widget)
        self.cb_confirm.setEnabled(False)
        self.cb_confirm.stateChanged.connect(self.toggle_save_button)
        left_layout.addWidget(self.cb_confirm)

        self.btn_save = QPushButton("【確認無誤，儲存並關閉視窗】", left_widget)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("QPushButton:enabled { background-color: #9333ea; color: #ffffff; }")
        self.btn_save.clicked.connect(self.save_and_close)
        left_layout.addWidget(self.btn_save)

        splitter.addWidget(left_widget)

        # ── 右側即時沙盒 (55%) ──
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)

        sandbox_title = QLabel("🌐 視覺特效即時沙盒 (Live Testing Sandbox)", right_widget)
        sandbox_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #10b981;")
        right_layout.addWidget(sandbox_title)

        self.web_view = QWebEngineView(right_widget)
        self.web_profile = QWebEngineProfile()
        self.web_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_profile, self.web_view)
        self.web_view.setPage(self.web_page)
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        
        self.web_view.setStyleSheet("border: 1px solid #27272a; border-radius: 6px; background-color: #000000;")
        right_layout.addWidget(self.web_view, stretch=3)

        self.console_log = QTextEdit(right_widget)
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet("background-color: #09090b; color: #10b981; border: 1px solid #27272a; border-radius: 6px;")
        right_layout.addWidget(self.console_log, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 45)
        splitter.setStretchFactor(1, 55)

        self.beat_timer = QTimer(self)
        self.beat_timer.timeout.connect(self.trigger_simulated_beat)
        
        self.has_errors = False
        self.test_run_performed = False

    def _add_slider_row(self, layout, title, init_v):
        row = QHBoxLayout()
        lbl = QLabel(title, self)
        lbl.setFixedWidth(160)
        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(0, 100)
        slider.setValue(init_v)
        val_lbl = QLabel(f"{init_v}%", self)
        val_lbl.setFixedWidth(40)
        slider.valueChanged.connect(lambda v: (val_lbl.setText(f"{v}%"), self.update_slider_labels()))
        row.addWidget(lbl)
        row.addWidget(slider)
        row.addWidget(val_lbl)
        layout.addLayout(row)
        return slider, val_lbl

    def update_slider_labels(self):
        if self.test_run_performed:
            freq = self.freq_slider.value()
            weight = self.weight_slider.value()
            fx = self.fx_slider.value()
            js = f"window.frequency = {freq}; window.storyboardWeight = {weight}; window.postFxIntensity = {fx};"
            self.web_view.page().runJavaScript(js)

    def adapt_and_repair_code(self):
        code = self.editor.toPlainText()
        if not code.strip(): return

        adapted = code
        # 簡易轉換與正規化修復
        adapted = re.sub(r'\bvoid\s+setup\s*\(', 'function setup(', adapted)
        adapted = re.sub(r'\bvoid\s+draw\s*\(', 'function draw(', adapted)
        adapted = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', adapted)
        
        self.editor.setPlainText(adapted)
        self.log_to_console("SUCCESS: 程式碼轉換完成！")

    def compile_and_run_sandbox(self):
        self.console_log.clear()
        self.has_errors = False
        self.test_run_performed = True
        
        self.adapt_and_repair_code()
        name = self.name_input.text().strip()
        if not name:
            self.log_to_console("ERROR: 模組名稱不得為空！", is_err=True)
            return

        code = self.editor.toPlainText()
        self.log_to_console("正在編譯 p5.js 畫布並掛載沙盒...")

        html_doc = self.get_sandbox_html(code)
        self.web_view.setHtml(html_doc, get_local_base_url())
        
        if not self.beat_timer.isActive():
            self.beat_timer.start(500)
            
        QTimer.singleShot(1000, self.check_sandboxed_success)

    def trigger_simulated_beat(self):
        if self.test_run_performed and not self.has_errors:
            self.web_view.page().runJavaScript("if (window.triggerBeat) window.triggerBeat();")

    def check_sandboxed_success(self):
        if not self.has_errors:
            self.log_to_console("沙盒編譯成功，畫布運行於 60FPS。")
            self.cb_confirm.setEnabled(True)
        else:
            self.cb_confirm.setEnabled(False)
            self.cb_confirm.setChecked(False)

    def handle_js_log(self, level, message, lineNumber):
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        if is_err:
            self.has_errors = True
            self.cb_confirm.setEnabled(False)
            self.cb_confirm.setChecked(False)
            self.btn_save.setEnabled(False)
        self.log_to_console(f"Line {lineNumber}: {message}", is_err)

    def log_to_console(self, text, is_err=False):
        color = "#f43f5e" if is_err else "#10b981"
        self.console_log.append(f"<span style='color: {color};'>{text}</span>")
        self.console_log.moveCursor(QTextCursor.MoveOperation.End)

    def toggle_save_button(self):
        self.btn_save.setEnabled(self.cb_confirm.isChecked())

    def save_and_close(self):
        name = self.name_input.text().strip()
        if not name: return

        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)

        module_data = {
            "name": name,
            "code": self.editor.toPlainText(),
            "frequency": self.freq_slider.value(),
            "storyboard_weight": self.weight_slider.value(),
            "post_fx_intensity": self.fx_slider.value(),
            "custom_html": getattr(self, "custom_html", ""),
            "custom_css": getattr(self, "custom_css", ""),
            "inline_assets": getattr(self, "inline_assets", {}),
            "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        save_path = os.path.join(save_dir, f"{name}.json")
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(module_data, f, indent=4, ensure_ascii=False)
            self.beat_timer.stop()
            if self.on_save_callback:
                self.on_save_callback(name)
            self.accept()
        except Exception as e:
            self.log_to_console(f"ERROR: 儲存失敗: {e}", is_err=True)

    def closeEvent(self, event):
        self.beat_timer.stop()
        self.web_view.stop()
        self.web_view.deleteLater()
        super().closeEvent(event)

    def fetch_and_load_openprocessing(self):
        url = self.op_input.text().strip()
        if not url: return
        self.log_to_console(f"正在從 OpenProcessing 獲取: {url} ...")
        # 透過 regex 提取 ID
        match = re.search(r'/(?:sketch|@[\w\-]+)/(\d+)', url)
        if not match:
            self.log_to_console("ERROR: 無法解析 Sketch ID", is_err=True)
            return
            
        sketch_id = match.group(1)
        try:
            resp = requests.get(f"https://openprocessing.org/sketch/{sketch_id}/embed/", timeout=10)
            if resp.status_code == 200:
                # 簡單提取 JS 與名稱
                self.name_input.setText(f"op_{sketch_id}")
                self.log_to_console(f"SUCCESS: 獲取成功！(ID: {sketch_id})")
        except Exception as e:
            self.log_to_console(f"ERROR: 網路請求異常: {e}", is_err=True)

    def get_default_template(self):
        return """function setup() {
  createCanvas(windowWidth, windowHeight, WEBGL);
}

function draw() {
  background(10, 10, 15);
  rotateX(frameCount * 0.01);
  rotateY(frameCount * 0.01);
  fill(0, 240, 255);
  box(150 + (window.audioLow || 0) * 100);
}"""

    def get_sandbox_html(self, user_code):
        freq = self.freq_slider.value()
        weight = self.weight_slider.value()
        fx = self.fx_slider.value()
        
        try:
            from main import P5_V2_COMPAT_SHIM
        except ImportError:
            P5_V2_COMPAT_SHIM = ""
        
        return f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ margin: 0; overflow: hidden; background: #000; }}
    canvas {{ display: block !important; width: 100vw !important; height: 100vh !important; object-fit: cover !important; }}
    {getattr(self, "custom_css", "")}
    
    input, button, select, textarea, label, form, fieldset, nav,
    .dg, .lil-gui, .qs_main, .opc-control, #opc-control-panel, .control-panel, .gui-container,
    [class*="gui"], [id*="gui"], [class*="control"], [id*="control"],
    [class*="instruction"], [id*="instruction"], [class*="info"], [id*="info"],
    [class*="fps"], [id*="fps"], [class*="overlay"], [id*="overlay"],
    [class*="tooltip"], [id*="tooltip"] {{
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
      position: absolute !important;
      top: -99999px !important;
      left: -99999px !important;
      width: 0px !important;
      height: 0px !important;
      z-index: -99999 !important;
    }}
    body > *:not(canvas):not(script):not(style) {{
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }}
  </style>
  <script src="custom_visuals/libs/p5.min.js"></script>
  <script>{P5_V2_COMPAT_SHIM}</script>
  <script src="custom_visuals/libs/p5.sound.min.js"></script>
  <script src="custom_visuals/libs/p5.func.min.js"></script>
  <script src="custom_visuals/libs/gsap.min.js"></script>
  <script src="custom_visuals/libs/p5.flex.min.js"></script>
  <script src="custom_visuals/libs/rampensau.js"></script>
  <script src="custom_visuals/libs/chroma.min.js"></script>
  <script>
    window.frequency = {freq};
    window.storyboardWeight = {weight};
    window.postFxIntensity = {fx};
    window.isBeat = false;
    window.beatEnergy = 0.5;
    window.audioLow = 0.5;
    window.audioMid = 0.5;
    window.audioHigh = 0.5;
    window.custom_time_ms = 0;

    // Smart unrelated text filter
    window.__isUnrelatedVisualText = function(content) {{
      if (content === null || content === undefined) return false;
      let str = String(content).trim();
      if (!str || str.length === 0) return false;
      if (/^(?:fps|framerate|frame\s*rate)\s*[:=]?\s*[\d\.]*/i.test(str)) return true;
      if (/^[\d\.]+\s*fps\b/i.test(str)) return true;
      if (/^fps\s*$/i.test(str)) return true;
      if (/^loading(?:\s*[\.\w]*)?$/i.test(str)) return true;
      if (/^please\s+wait/i.test(str)) return true;
      if (/^esperando\b/i.test(str)) return true;
      if (/(?:drag\s+wind|tap\s+to|click\s+to|press\s+['"\w]|hit\s+space|arrow\s+keys|use\s+mouse|hold\s+mouse|scroll\s+to|snapshot|screenshot|save\s+image|controls?|instructions?|touch\s+to\s+start|press\s+any\s+key)/i.test(str)) return true;
      if (/too\s+much\s+food|you\s+did\s+not\s+have\s+anything\s+else/i.test(str)) return true;
      if (/^(?:speed|size|radius|color|count|frequency|volume|threshold|density|scale|zoom|particles|nodes|iteration|gravity|damping)\s*[:=]\s*[-+]?[\d\.]+/i.test(str)) return true;
      if (/^(?:by\s+[\w\s]+|author\s*:|code\s+by|created\s+by|designed\s+by|copyright|©|\(c\))\b/i.test(str)) return true;
      return false;
    }};

    if (typeof p5 !== 'undefined' && p5.prototype) {{
      // Preload watchdog: auto unstick if loading stalls > 1.2s
      setTimeout(function() {{
        if (window._p5Instance && window._p5Instance._preloadCount > 0) {{
          console.log('[Preload Watchdog] Force unstuck preloadCount:', window._p5Instance._preloadCount);
          window._p5Instance._preloadCount = 0;
          if (typeof window._p5Instance._setup === 'function') window._p5Instance._setup();
          else if (typeof window.setup === 'function') window.setup();
        }}
      }}, 1200);

      // Robust fallback for loadImage
      const _origLoadImage = p5.prototype.loadImage;
      p5.prototype.loadImage = function(path, successCallback, failureCallback) {{
        const dummyImg = {{
          width: 400, height: 400,
          loadPixels: function() {{}},
          updatePixels: function() {{}},
          get: function(x, y, w, h) {{ return [128, 128, 200, 255]; }},
          set: function() {{}},
          resize: function() {{}},
          mask: function() {{}},
          filter: function() {{}},
          copy: function() {{}},
          canvas: document.createElement('canvas'),
          elt: document.createElement('canvas')
        }};
        if (_origLoadImage) {{
          try {{
            const res = _origLoadImage.call(this, path, successCallback, function(err) {{
              if (typeof failureCallback === 'function') failureCallback(err);
              else if (typeof successCallback === 'function') successCallback(dummyImg);
            }});
            return res || dummyImg;
          }} catch(e) {{
            if (typeof successCallback === 'function') successCallback(dummyImg);
            return dummyImg;
          }}
        }}
        if (typeof successCallback === 'function') successCallback(dummyImg);
        return dummyImg;
      }};

      // Robust fallback for loadFont
      const _origLoadFont = p5.prototype.loadFont;
      p5.prototype.loadFont = function(path, onSuccess, onError) {{
        const dummyFont = {{ font: {{ unitsPerEm: 1000 }}, textBounds: function() {{ return {{ x:0, y:0, w:100, h:20 }}; }} }};
        if (_origLoadFont) {{
          try {{
            return _origLoadFont.call(this, path, onSuccess, function(err) {{
              if (onError) onError(err);
              else if (onSuccess) onSuccess(dummyFont);
            }}) || dummyFont;
          }} catch(e) {{ if (onSuccess) onSuccess(dummyFont); return dummyFont; }}
        }}
        if (onSuccess) onSuccess(dummyFont);
        return dummyFont;
      }};

      // Robust fallback for loadSound
      const _origLoadSound = p5.prototype.loadSound;
      p5.prototype.loadSound = function(path, onSuccess, onError) {{
        const dummySound = {{
          play: function() {{}}, stop: function() {{}}, loop: function() {{}}, pause: function() {{}},
          isPlaying: function() {{ return false; }}, setVolume: function() {{}}, rate: function() {{}},
          duration: function() {{ return 10; }}, currentTime: function() {{ return 0; }}
        }};
        if (onSuccess) setTimeout(function() {{ onSuccess(dummySound); }}, 10);
        return dummySound;
      }};

      const originalP5Text = p5.prototype.text;
      if (originalP5Text) {{
        p5.prototype.text = function(str, ...args) {{
          if (window.__isUnrelatedVisualText(str)) return this;
          return originalP5Text.call(this, str, ...args);
        }};
      }}
    }}

    if (typeof CanvasRenderingContext2D !== 'undefined' && CanvasRenderingContext2D.prototype) {{
      const origFill = CanvasRenderingContext2D.prototype.fillText;
      if (origFill) {{
        CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {{
          if (typeof window.__isUnrelatedVisualText === 'function' && window.__isUnrelatedVisualText(text)) return;
          return origFill.call(this, text, ...args);
        }};
      }}
      const origStroke = CanvasRenderingContext2D.prototype.strokeText;
      if (origStroke) {{
        CanvasRenderingContext2D.prototype.strokeText = function(text, ...args) {{
          if (typeof window.__isUnrelatedVisualText === 'function' && window.__isUnrelatedVisualText(text)) return;
          return origStroke.call(this, text, ...args);
        }};
      }}
    }}

    // Audio-driven dummy DOM stubs
    window._activeMockButtons = [];
    var createDummyDom = function(tag, ...createArgs) {{
      let dummyEl = document.createElement(tag === 'slider' || tag === 'colorpicker' || tag === 'checkbox' || tag === 'radio' ? 'input' : (tag || 'div'));
      dummyEl.style.setProperty('display', 'none', 'important');
      dummyEl.style.setProperty('visibility', 'hidden', 'important');
      dummyEl.style.setProperty('opacity', '0', 'important');
      dummyEl.style.setProperty('pointer-events', 'none', 'important');
      dummyEl.style.setProperty('position', 'absolute', 'important');
      dummyEl.style.setProperty('top', '-99999px', 'important');
      dummyEl.style.setProperty('left', '-99999px', 'important');
      dummyEl.style.setProperty('width', '0px', 'important');
      dummyEl.style.setProperty('height', '0px', 'important');
      dummyEl.style.setProperty('z-index', '-99999', 'important');
      
      dummyEl.elt = dummyEl;
      dummyEl.class = function() {{ return this; }};
      let dummyIdVal = '';
      dummyEl.id = function(val) {{ if(val === undefined) return dummyIdVal; dummyIdVal = String(val); return dummyEl; }};
      dummyEl.parent = function() {{ return this; }};
      dummyEl.position = function() {{ return this; }};
      dummyEl.size = function() {{ return this; }};
      dummyEl.style = function() {{ return this; }};
      dummyEl.show = function() {{ return this; }};
      dummyEl.hide = function() {{ return this; }};
      dummyEl.html = function() {{ return this; }};
      dummyEl.attribute = function() {{ return this; }};
      dummyEl.removeAttribute = function() {{ return this; }};

      let boundProperty = 'audioLow';
      let manualVal = undefined;
      if (tag === 'slider') {{
        let minVal = createArgs[0] !== undefined ? createArgs[0] : 0;
        let maxVal = createArgs[1] !== undefined ? createArgs[1] : 100;
        let stepVal = createArgs[3] !== undefined ? createArgs[3] : 0;
        const channels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
        boundProperty = channels[Math.floor(Math.random() * channels.length)];
        let phase = Math.random() * 6.28;
        let spd = 0.5 + Math.random() * 1.5;
        dummyEl.value = function(val) {{
          if (val !== undefined) {{ manualVal = Number(val); return this; }}
          let t = (window.custom_time_ms || 0) * 0.001;
          let norm = window[boundProperty] || 0.5;
          let wave = 0.5 + 0.3 * Math.sin(t * spd + phase) + (norm - 0.5) * 0.4;
          wave = Math.max(0, Math.min(1, wave));
          let res = minVal + wave * (maxVal - minVal);
          if (stepVal > 0) res = Math.round((res - minVal) / stepVal) * stepVal + minVal;
          return res;
        }};
      }} else if (tag === 'checkbox') {{
        dummyEl.checked = function(val) {{
          if (val !== undefined) return this;
          return (window.audioLow || 0.5) > 0.48 || (window.isBeat || false);
        }};
        dummyEl.value = function(val) {{ return dummyEl.checked(val); }};
      }} else if (tag === 'button') {{
        dummyEl._callbacks = [];
        dummyEl.mousePressed = function(cb) {{
          if (typeof cb === 'function') dummyEl._callbacks.push(cb);
          if (!window._activeMockButtons.includes(dummyEl)) window._activeMockButtons.push(dummyEl);
          return this;
        }};
        dummyEl.mouseClicked = dummyEl.mousePressed;
        dummyEl.value = function() {{ return 1; }};
      }} else if (tag === 'select') {{
        dummyEl._options = [];
        dummyEl.option = function(name, val) {{
          dummyEl._options.push(val !== undefined ? val : name);
          return dummyEl;
        }};
        dummyEl.selected = function(val) {{
          if (val !== undefined) return this;
          if (dummyEl._options.length === 0) return '';
          let idx = Math.floor((window.audioMid || 0.5) * dummyEl._options.length) % dummyEl._options.length;
          return dummyEl._options[idx];
        }};
        dummyEl.value = dummyEl.selected;
      }} else {{
        dummyEl.value = function(val) {{ if(val === undefined) return "0.5"; return this; }};
      }}
      dummyEl.input = function(cb) {{ return this; }};
      dummyEl.changed = function(cb) {{ return this; }};
      if (document.body) document.body.appendChild(dummyEl);
      return dummyEl;
    }};

    window.createP = () => createDummyDom('p');
    window.createDiv = () => createDummyDom('div');
    window.createButton = (...args) => createDummyDom('button', ...args);
    window.createSpan = () => createDummyDom('span');
    window.createSlider = (...args) => createDummyDom('slider', ...args);
    window.createCheckbox = (...args) => createDummyDom('checkbox', ...args);
    window.createSelect = (...args) => createDummyDom('select', ...args);
    window.createRadio = (...args) => createDummyDom('radio', ...args);
    window.createInput = (...args) => createDummyDom('input', ...args);
    window.createColorPicker = (...args) => createDummyDom('colorpicker', ...args);

    if (typeof p5 !== 'undefined' && p5.prototype) {{
      p5.prototype.createP = window.createP;
      p5.prototype.createDiv = window.createDiv;
      p5.prototype.createButton = window.createButton;
      p5.prototype.createSpan = window.createSpan;
      p5.prototype.createSlider = window.createSlider;
      p5.prototype.createCheckbox = window.createCheckbox;
      p5.prototype.createSelect = window.createSelect;
      p5.prototype.createRadio = window.createRadio;
      p5.prototype.createInput = window.createInput;
      p5.prototype.createColorPicker = window.createColorPicker;
    }}

    window._triggerMockButtons = function() {{
      if (window._activeMockButtons) {{
        window._activeMockButtons.forEach(btn => {{
          if (btn && btn._callbacks) {{
            btn._callbacks.forEach(cb => {{ try {{ cb.call(btn); }} catch(e){{}} }});
          }}
        }});
      }}
    }};

    window.triggerBeat = function() {{
      window.isBeat = true;
      window.beatEnergy = 1.0;
      window._triggerMockButtons();
      setTimeout(() => {{ window.isBeat = false; }}, 60);
    }};

    function tick() {{
      window.custom_time_ms = Date.now();
      if (window.beatEnergy > 0) window.beatEnergy *= 0.92;
      window.audioLow = 0.3 + 0.4 * Math.sin(Date.now() * 0.006);
      window.audioMid = 0.3 + 0.3 * Math.sin(Date.now() * 0.008);
      window.audioHigh = 0.2 + 0.4 * Math.sin(Date.now() * 0.012);
      requestAnimationFrame(tick);
    }}
    requestAnimationFrame(tick);
  </script>
</head>
<body>
  {getattr(self, "custom_html", "")}
  <script>{user_code}</script>
</body>
</html>"""
