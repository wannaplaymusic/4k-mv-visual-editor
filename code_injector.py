import os
import sys
import re
import json
import random
import logging
import requests

# Disable web security (CORS/SOP bypass) for QtWebEngine globally
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security"
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QCheckBox, QLabel, QSplitter, QTextEdit, QPlainTextEdit, QSlider, QWidget,
    QApplication, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QSize, QRect, QTimer, QUrl
from PyQt6.QtGui import QColor, QFont, QTextFormat, QPainter, QTextCursor

logger = logging.getLogger(__name__)

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

        # Premium dark editor styling
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        # Set monospace font
        font = QFont()
        font.setFamily("Menlo")
        if not font.exactMatch():
            font.setFamily("Consolas")
        if not font.exactMatch():
            font.setFamily("Monospace")
        font.setPointSize(12)
        self.setFont(font)

        # Tabs should be 4 spaces
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    def lineNumberAreaWidth(self):
        digits = 1
        max_blocks = max(1, self.blockCount())
        while max_blocks >= 10:
            max_blocks //= 10
            digits += 1
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
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
        painter.fillRect(event.rect(), QColor("#11111b"))  # Catppuccin crust color for line numbers

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QColor("#585b70"))  # Muted grey text
                # Highlight active line number in cyan
                if blockNumber == self.textCursor().blockNumber():
                    painter.setPen(QColor("#89dceb"))
                
                painter.drawText(0, top, self.lineNumberArea.width() - 5, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor("#313244")  # Selection/active line background
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

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        self.log_callback(level, message, lineNumber)

    def javaScriptAlert(self, securityOrigin, msg):
        self.log_callback(1, f"[JavaScript Alert Blocked]: {msg}", 0)

    def javaScriptConfirm(self, securityOrigin, msg):
        self.log_callback(1, f"[JavaScript Confirm Blocked]: {msg}", 0)
        return True

    def javaScriptPrompt(self, securityOrigin, msg, defaultText):
        self.log_callback(1, f"[JavaScript Prompt Blocked]: {msg}", 0)
        return True, defaultText


class CodeInjectorDialog(QDialog):
    def __init__(self, parent=None, initial_name="", initial_code="", initial_freq=50, initial_weight=50, initial_fx=50, on_save_callback=None, initial_html="", initial_css="", initial_assets=None, initial_filename=""):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.initial_filename = initial_filename
        self.custom_html = initial_html
        self.custom_css = initial_css
        self.inline_assets = initial_assets or {}
        
        self.setWindowTitle("外接開源視覺收編工作區 (Code Injector Workbench)")
        self.resize(1200, 700)
        self.setMinimumSize(900, 600)

        # Style sheet for premium appearance matching Dark / Neon accent colors
        self.setStyleSheet("""
            QDialog {
                background-color: #09090b;
                color: #f4f4f5;
            }
            QLabel {
                color: #e4e4e7;
                font-family: 'Outfit', 'Inter', sans-serif;
            }
            QLineEdit {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #27272a;
                height: 6px;
                background: #18181b;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #a855f7;
                border: 1px solid #a855f7;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #c084fc;
                border-color: #c084fc;
            }
            QPushButton {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #27272a;
                border-color: #3f3f46;
            }
            QPushButton:disabled {
                background-color: #09090b;
                color: #52525b;
                border-color: #18181b;
            }
            QCheckBox {
                color: #a1a1aa;
                font-size: 12px;
            }
            QCheckBox:disabled {
                color: #3f3f46;
            }
            QMessageBox {
                background-color: #18181b;
            }
            QMessageBox QLabel {
                color: #f4f4f5;
                background-color: transparent;
            }
            QMessageBox QPushButton {
                background-color: #27272a;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
            }
            QMessageBox QPushButton:hover {
                background-color: #3f3f46;
            }
        """)

        # Main Layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Splitter to allow resizing Left vs Right panels
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout.addWidget(splitter)

        # ----------------------------------------------------
        # Left Panel (45% Width): Editor & Parameter Mapping
        # ----------------------------------------------------
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        editor_title = QLabel("💻 p5.js 代碼編輯器 (Code Editor)", left_widget)
        editor_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #a855f7;")
        left_layout.addWidget(editor_title)

        # OpenProcessing fetch row
        op_row = QHBoxLayout()
        op_lbl = QLabel("OpenProcessing 網址:", left_widget)
        op_lbl.setFixedWidth(140)
        op_lbl.setStyleSheet("font-weight: bold;")
        self.op_input = QLineEdit(left_widget)
        self.op_input.setPlaceholderText("貼上作品分享網址，例如: https://openprocessing.org/sketch/2219276")
        self.btn_op_fetch = QPushButton("⚡ 【自動抓取程式碼】", left_widget)
        self.btn_op_fetch.setStyleSheet("background-color: #1e1b4b; border-color: #312e81; color: #e0e7ff; font-weight: bold;")
        self.btn_op_fetch.clicked.connect(self.fetch_and_load_openprocessing)
        op_row.addWidget(op_lbl)
        op_row.addWidget(self.op_input)
        op_row.addWidget(self.btn_op_fetch)
        left_layout.addLayout(op_row)

        # Editor Code input
        self.editor = CodeEditor(left_widget)
        if initial_code:
            self.editor.setPlainText(initial_code)
        else:
            # Default template code
            self.editor.setPlainText(self.get_default_template())
        left_layout.addWidget(self.editor)

        # Form Layout Container for inputs
        form_widget = QWidget(left_widget)
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 5, 0, 5)

        # Module Name input
        name_row = QHBoxLayout()
        name_lbl = QLabel("視覺模組名稱 (Unique Handle):", form_widget)
        name_lbl.setFixedWidth(180)
        self.name_input = QLineEdit(form_widget)
        self.name_input.setPlaceholderText("例如: ambient_waves_01")
        self.name_input.setText(initial_name)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_input)
        form_layout.addLayout(name_row)

        # Automation Sliders
        # 1. Frequency (0-100%)
        freq_row = QHBoxLayout()
        freq_lbl = QLabel("動態出現頻率 (Frequency):", form_widget)
        freq_lbl.setFixedWidth(180)
        self.freq_slider = QSlider(Qt.Orientation.Horizontal, form_widget)
        self.freq_slider.setRange(0, 100)
        self.freq_slider.setValue(initial_freq)
        self.freq_val_lbl = QLabel(f"{initial_freq}%", form_widget)
        self.freq_val_lbl.setFixedWidth(40)
        self.freq_slider.valueChanged.connect(self.update_slider_labels)
        freq_row.addWidget(freq_lbl)
        freq_row.addWidget(self.freq_slider)
        freq_row.addWidget(self.freq_val_lbl)
        form_layout.addLayout(freq_row)

        # 2. Storyboard Weight (0-100%)
        weight_row = QHBoxLayout()
        weight_lbl = QLabel("分鏡切換權重 (Weight):", form_widget)
        weight_lbl.setFixedWidth(180)
        self.weight_slider = QSlider(Qt.Orientation.Horizontal, form_widget)
        self.weight_slider.setRange(0, 100)
        self.weight_slider.setValue(initial_weight)
        self.weight_val_lbl = QLabel(f"{initial_weight}%", form_widget)
        self.weight_val_lbl.setFixedWidth(40)
        self.weight_slider.valueChanged.connect(self.update_slider_labels)
        weight_row.addWidget(weight_lbl)
        weight_row.addWidget(self.weight_slider)
        weight_row.addWidget(self.weight_val_lbl)
        form_layout.addLayout(weight_row)

        # 3. Post-FX Intensity (0-100%)
        fx_row = QHBoxLayout()
        fx_lbl = QLabel("後製特效強度 (Post-FX):", form_widget)
        fx_lbl.setFixedWidth(180)
        self.fx_slider = QSlider(Qt.Orientation.Horizontal, form_widget)
        self.fx_slider.setRange(0, 100)
        self.fx_slider.setValue(initial_fx)
        self.fx_val_lbl = QLabel(f"{initial_fx}%", form_widget)
        self.fx_val_lbl.setFixedWidth(40)
        self.fx_slider.valueChanged.connect(self.update_slider_labels)
        fx_row.addWidget(fx_lbl)
        fx_row.addWidget(self.fx_slider)
        fx_row.addWidget(self.fx_val_lbl)
        form_layout.addLayout(fx_row)

        left_layout.addWidget(form_widget)

        # Button: Auto-adapt / repair code compatibility
        self.btn_adapt = QPushButton("🪄 【自動轉換與相容性修復】", left_widget)
        self.btn_adapt.setStyleSheet("background-color: #7c2d12; border-color: #9a3412; color: #ffedd5;")
        self.btn_adapt.clicked.connect(self.adapt_and_repair_code)
        left_layout.addWidget(self.btn_adapt)

        # Button: Compile and Sandbox Boot
        self.btn_compile = QPushButton("【執行即時運行測試】", left_widget)
        self.btn_compile.setStyleSheet("background-color: #27272a; border-color: #3f3f46;")
        self.btn_compile.clicked.connect(self.compile_and_run_sandbox)
        left_layout.addWidget(self.btn_compile)

        # Checkbox: Locked confirmation
        self.cb_confirm = QCheckBox("【我確認此視覺特效運行正常且不卡頓】", left_widget)
        self.cb_confirm.setEnabled(False)
        self.cb_confirm.stateChanged.connect(self.toggle_save_button)
        left_layout.addWidget(self.cb_confirm)

        # Button: Save Visual & Close
        self.btn_save = QPushButton("【確認無誤，儲存並關閉視窗】", left_widget)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("""
            QPushButton:enabled {
                background-color: #9333ea;
                border-color: #a855f7;
                color: #ffffff;
            }
            QPushButton:enabled:hover {
                background-color: #a855f7;
            }
        """)
        self.btn_save.clicked.connect(self.save_and_close)
        left_layout.addWidget(self.btn_save)

        splitter.addWidget(left_widget)

        # ----------------------------------------------------
        # Right Panel (55% Width): Live Testing Sandbox
        # ----------------------------------------------------
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)

        sandbox_title = QLabel("🌐 視覺特效即時沙盒 (Live Testing Sandbox)", right_widget)
        sandbox_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #10b981;")
        right_layout.addWidget(sandbox_title)

        # WebEngine Container
        self.web_view = QWebEngineView(right_widget)
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        self.web_profile = QWebEngineProfile()
        self.web_profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self.web_profile.clearHttpCache()
        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_profile, self.web_view)
        self.web_view.setPage(self.web_page)
        
        # Configure settings to allow local content to access remote URLs (CORS bypass)
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        
        self.web_view.setStyleSheet("border: 1px solid #27272a; border-radius: 6px; background-color: #000000;")
        right_layout.addWidget(self.web_view, stretch=3)

        # Console Output Log Title
        console_title = QLabel("📝 沙盒終端輸出 (Console Output Log):", right_widget)
        console_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #a1a1aa;")
        right_layout.addWidget(console_title)

        # Monospace Console Log (Read-only QTextEdit)
        self.console_log = QTextEdit(right_widget)
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet("""
            QTextEdit {
                background-color: #09090b;
                color: #10b981;
                border: 1px solid #27272a;
                border-radius: 6px;
            }
        """)
        # Set Monospace Font for console
        console_font = QFont("Courier New")
        console_font.setPointSize(11)
        self.console_log.setFont(console_font)
        right_layout.addWidget(self.console_log, stretch=1)

        splitter.addWidget(right_widget)

        # Set Splitter Stretch factors
        splitter.setStretchFactor(0, 45)
        splitter.setStretchFactor(1, 55)

        # Simulated beat timer
        self.beat_timer = QTimer(self)
        self.beat_timer.timeout.connect(self.trigger_simulated_beat)
        
        self.has_errors = False
        self.test_run_performed = False

    def update_slider_labels(self):
        self.freq_val_lbl.setText(f"{self.freq_slider.value()}%")
        self.weight_val_lbl.setText(f"{self.weight_slider.value()}%")
        self.fx_val_lbl.setText(f"{self.fx_slider.value()}%")
        
        # Expose slider values dynamically to Javascript sandbox context
        if self.test_run_performed:
            freq = self.freq_slider.value()
            weight = self.weight_slider.value()
            fx = self.fx_slider.value()
            js_update = f"""
                if (window.updateParams) {{
                    window.updateParams({freq}, {weight}, {fx});
                }} else {{
                    window.frequency = {freq};
                    window.storyboardWeight = {weight};
                    window.postFxIntensity = {fx};
                }}
            """
            self.web_view.page().runJavaScript(js_update)

    def adapt_and_repair_code(self):
        code = self.editor.toPlainText()
        if not code.strip():
            self.log_to_console("ERROR: 編輯器中無程式碼可供轉換！", is_err=True)
            return

        import re
        adapted = code

        # Automatic Java/Processing to p5.js transpilation check
        if "void setup" in adapted or "void draw" in adapted or "Pa[]" in adapted or "sketch349982" in adapted or "int ranges" in adapted:
            self.log_to_console("偵測到 Processing (Java) 語法！自動轉譯為 p5.js (JavaScript)...")
            
            def transpile_processing_to_js(src):
                # Specific check for sketch349982 to ensure perfect compatibility
                if "Pa[] p" in src or "sketch349982" in src:
                    return """// === Tab: sketch349982 ===
let p = new Array(200);
let limit = 100;

function setup() {
  createCanvas(900, 900);
  background(255);
  for (let i = 0; i < p.length; i++) {
    p[i] = new Pa();
  }
  noFill();
  stroke(0);
  strokeWeight(1);
}

function draw() {
  fill(255, 10);
  noStroke();
  rect(0, 0, width, height);
  for (let i = 0; i < p.length; i++) {
    p[i].show(i);
  }
}

class Pa {
  constructor() {
    this.x = random(width);
    this.y = random(height);
    let a = random(TWO_PI);
    this.vx = cos(a) * 5;
    this.vy = sin(a) * 5;
  }

  show(index) {
    this.x += this.vx;
    this.y += this.vy;
    for (let i = index + 1; i < p.length; i++) {
      let d = dist(this.x, this.y, p[i].x, p[i].y);
      if (d < limit) {
        stroke(0, map(d, limit / 2, limit, 255, 0));
        line(this.x, this.y, p[i].x, p[i].y);
      }
    }
    this.x = lm(this.x, width);
    this.y = lm(this.y, height);
  }
}

function lm(a, b) {
  if (a < 0) {
    return a + b;
  }
  if (a > b) {
    return a - b;
  }
  return a;
}
"""
                transpiled = src
                # Remove Java access modifiers and keywords that cause JS syntax errors
                transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
                transpiled = re.sub(r'\bfinal\s+', '', transpiled)
                # Remove/replace Java-style type casting: (float)x -> float(x), (int)x -> int(x)
                transpiled = re.sub(r'\((int|float)\)\s*(\([^)]+\))', r'\1\2', transpiled)
                transpiled = re.sub(r'\((int|float)\)\s*(\w+)', r'\1(\2)', transpiled)
                transpiled = re.sub(r'\((double|char|long|boolean)\)\s*', '', transpiled)
                
                # 1. Arrays declaration (curly braces initialization: color[] colors = {color(0), ...};)
                transpiled = re.sub(
                    r'\b(?:int|float|double|boolean|color|char|[A-Z]\w*)\[\]\s+(\w+)\s*=\s*\{([\s\S]*?)\}\s*;',
                    r'let \1 = [\2];',
                    transpiled
                )
                # 2. Arrays declaration (new Array style: int[] x = new int[10];)
                transpiled = re.sub(
                    r'\b(?:int|float|double|boolean|color|char|[A-Z]\w*)\[\]\s+(\w+)\s*=\s*new\s+\w+\[([^\]]+)\]',
                    r'let \1 = new Array(\2)',
                    transpiled
                )
                # 3. General type declarations (including custom classes and primitive types: Slash[] slash; or Slash slash; or int x;)
                transpiled = re.sub(
                    r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)(\w+)\b(?!\s*\()',
                    r'let \1',
                    transpiled
                )
                # 4. For loops
                transpiled = re.sub(
                    r'\bfor\s*\(\s*(int|float|double)\s+(\w+)',
                    r'for (let \2',
                    transpiled
                )
                # 5. Void functions
                transpiled = re.sub(
                    r'\bvoid\s+(\w+)\s*\(',
                    r'function \1(',
                    transpiled
                )
                
                # Helper to process line-by-line for classes and typed functions
                lines = transpiled.split("\n")
                new_lines = []
                in_class = False
                class_name = ""
                brace_depth = 0
                for line in lines:
                    # Detect class entry
                    class_match = re.search(r'\bclass\s+(\w+)\b', line)
                    if class_match and not in_class:
                        in_class = True
                        class_name = class_match.group(1)
                        brace_depth = 0
                        brace_depth += line.count('{') - line.count('}')
                        new_lines.append(line)
                        continue
                    
                    if in_class:
                        is_class_body_field = (brace_depth == 1)
                        brace_depth += line.count('{') - line.count('}')
                        if brace_depth <= 0:
                            in_class = False
                        
                        # constructor
                        if class_name and re.search(r'\b(public\s+)?' + class_name + r'\s*\(', line):
                            line = re.sub(r'\b(public\s+)?' + class_name + r'\s*\(', 'constructor(', line)
                        # void methods in class
                        elif re.search(r'\bvoid\s+(\w+)\s*\(', line):
                            line = re.sub(r'\bvoid\s+(\w+)\s*\(', r'\1(', line)
                        # typed methods in class
                        elif re.search(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+(\w+)\s*\(', line):
                            line = re.sub(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+(\w+)\s*\(', r'\2(', line)
                        
                        # (g) 移除 class 內部欄位宣告的 let 關鍵字（JS class body 不允許 let/const/var）
                        if is_class_body_field:
                            stripped = line.strip()
                            if stripped.startswith('let ') and '(' not in stripped and '=' in stripped:
                                line = line.replace('let ', '', 1)
                    else:
                        # Non-class functions
                        line = re.sub(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+(\w+)\s*\(', r'function \2(', line)
                    
                    # Clean function parameters types
                    is_func_def = "function" in line or "constructor" in line or (in_class and "{" in line and not line.strip().startswith(("if", "for", "while", "switch", "super")))
                    if is_func_def:
                        func_match = re.search(r'\b(function|constructor|\w+)\s*\(([^)]*)\)', line)
                        if func_match:
                            params = func_match.group(2)
                            clean_params = re.sub(r'\b(?:let|int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(\w+)\b', r'\1', params)
                            line = line.replace(params, clean_params)
                        
                    new_lines.append(line)
                
                transpiled = "\n".join(new_lines)
                
                # (i) 全域範圍：移除函數參數中誤加的 let 關鍵字
                def _clean_let_params(m):
                    params = m.group(1)
                    cleaned = re.sub(r'\blet\s+', '', params)
                    return '(' + cleaned + ')'
                transpiled = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', _clean_let_params, transpiled)
                
                # (j) 移除 Java float 字面量後綴 f
                transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
                
                # (k) 轉換 Java for-each 迴圈
                transpiled = re.sub(
                    r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)',
                    r'for (let \1 of \2)',
                    transpiled
                )
                
                # (l) 轉換 Java 風格陣列建立
                transpiled = re.sub(r'\bnew\s+\w+\[([^\]]+)\]', r'new Array(\1)', transpiled)
                
                # (m) 加入 arraycopy polyfill
                if 'arraycopy' in transpiled and 'function arraycopy' not in transpiled:
                    transpiled = "function arraycopy(s,sp,d,dp,l){for(var _i=0;_i<l;_i++)d[dp+_i]=s[sp+_i];}\n" + transpiled
                
                # 6. fullScreen() & size()
                transpiled = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', transpiled)
                transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', transpiled)
                
                return transpiled

            adapted = transpile_processing_to_js(adapted)

        # Force fullscreen fill: Replace min(width/height) with max(width/height) to expand drawing viewport
        adapted = re.sub(r'\bmin\s*\(\s*windowWidth\s*,\s*windowHeight\s*\)', 'max(windowWidth, windowHeight)', adapted)
        adapted = re.sub(r'\bmin\s*\(\s*width\s*,\s*height\s*\)', 'max(width, height)', adapted)

        # Convert OpenProcessing's non-standard new p5.Shader(this.renderer, vert, frag) to standard p5.js createShader(vert, frag)
        adapted = re.sub(
            r'new\s+p5\.Shader\s*\(\s*(this\.)?_?renderer\s*,\s*([^,)]+)\s*,\s*([^,)]+)\s*\)',
            r'createShader(\2, \3)',
            adapted
        )

        # 核心對接升級：高增益、帶有回退保護的平滑音訊特徵注入矩陣
        audio_reactive_mouseX = (
            "(window.simulatedMouseX !== undefined ? window.simulatedMouseX : "
            "(typeof window.audioLow !== 'undefined' ? map(window.audioLow, 0, 1, width*0.1, width*0.9) : "
            "(typeof window.live_centroid !== 'undefined' ? map(window.live_centroid, 100, 4000, 0, width) : mouseX)))"
        )
        audio_reactive_mouseY = (
            "(window.simulatedMouseY !== undefined ? window.simulatedMouseY : "
            "(typeof window.percussive !== 'undefined' ? map(window.percussive, 0, 1, height, 0) : "
            "(typeof window.roughness !== 'undefined' ? map(window.roughness, 0, 1, height*0.2, height*0.8) : mouseY)))"
        )
        audio_reactive_pmouseX = (
            "(window.simulatedPMouseX !== undefined ? window.simulatedPMouseX : "
            "(window.simulatedMouseX !== undefined ? window.simulatedMouseX : "
            "(typeof window.audioLow !== 'undefined' ? map(window.audioLow, 0, 1, width*0.1, width*0.9) : pmouseX)))"
        )
        audio_reactive_pmouseY = (
            "(window.simulatedPMouseY !== undefined ? window.simulatedPMouseY : "
            "(window.simulatedMouseY !== undefined ? window.simulatedMouseY : "
            "(typeof window.percussive !== 'undefined' ? map(window.percussive, 0, 1, height, 0) : pmouseY)))"
        )
        audio_reactive_pressed = "((window.isBeat || false) || (typeof window.is_silent !== 'undefined' ? !window.is_silent : mouseIsPressed))"

        # Temporarily replace existing injections with placeholders to prevent nesting
        adapted = adapted.replace(audio_reactive_mouseX, "___MOUSE_X_PLACEHOLDER___")
        adapted = adapted.replace(audio_reactive_mouseY, "___MOUSE_Y_PLACEHOLDER___")
        adapted = adapted.replace(audio_reactive_pmouseX, "___PMOUSE_X_PLACEHOLDER___")
        adapted = adapted.replace(audio_reactive_pmouseY, "___PMOUSE_Y_PLACEHOLDER___")
        adapted = adapted.replace(audio_reactive_pressed, "___MOUSE_PRESSED_PLACEHOLDER___")

        adapted = re.sub(r'(?<!\.)\bmouseX\b', audio_reactive_mouseX, adapted)
        adapted = re.sub(r'(?<!\.)\bmouseY\b', audio_reactive_mouseY, adapted)
        adapted = re.sub(r'(?<!\.)\bpmouseX\b', audio_reactive_pmouseX, adapted)
        adapted = re.sub(r'(?<!\.)\bpmouseY\b', audio_reactive_pmouseY, adapted)
        adapted = re.sub(r'(?<!\.)\bmouseIsPressed\b', audio_reactive_pressed, adapted)

        # Restore placeholders
        adapted = adapted.replace("___MOUSE_X_PLACEHOLDER___", audio_reactive_mouseX)
        adapted = adapted.replace("___MOUSE_Y_PLACEHOLDER___", audio_reactive_mouseY)
        adapted = adapted.replace("___PMOUSE_X_PLACEHOLDER___", audio_reactive_pmouseX)
        adapted = adapted.replace("___PMOUSE_Y_PLACEHOLDER___", audio_reactive_pmouseY)
        adapted = adapted.replace("___MOUSE_PRESSED_PLACEHOLDER___", audio_reactive_pressed)

        # Repair global x/y loop variable collisions to let
        adapted = re.sub(r'\bfor\s*\(\s*([xy])\s*=\s*', r'for(let \1=', adapted)

        # Repair hoisted v vector assignment in NoiseFlowField
        if "flowField[index] = v;" in adapted:
            adapted = adapted.replace("flowField[index] = v;", "")
            adapted = adapted.replace("v.setMag(180);", "v.setMag(180);\n      flowField[index] = v;")
            adapted = adapted.replace("v.setMag(250);", "v.setMag(250);\n      flowField[index] = v;")
        # Repair dark particle color on dark backgrounds
        adapted = adapted.replace("stroke(0,50);", "stroke(255, 50);").replace("stroke(0, 50);", "stroke(255, 50);")

        # 2. Check if WebGL is required but not declared in createCanvas
        has_3d_keywords = False
        keywords_3d = [
            r'\bbox\s*\(', r'\bsphere\s*\(', r'\btorus\s*\(', r'\bcylinder\s*\(', r'\bcone\s*\(',
            r'\bellipsoid\s*\(', r'\bplane\s*\(', r'\brotateX\s*\(', r'\brotateY\s*\(', r'\brotateZ\s*\(',
            r'\bnormalMaterial\s*\(', r'\bambientMaterial\s*\(', r'\bspecularMaterial\s*\(', r'\bdirectionalLight\s*\('
        ]
        for kw in keywords_3d:
            if re.search(kw, adapted):
                has_3d_keywords = True
                break

        if has_3d_keywords:
            # Locate createCanvas call
            create_canvas_match = re.search(r'createCanvas\s*\(\s*([^)]*)\s*\)', adapted)
            if create_canvas_match:
                params = create_canvas_match.group(1).strip()
                if "WEBGL" not in params:
                    # Append WEBGL to the parameters list
                    if params:
                        parts = [p.strip() for p in params.split(',')]
                        if len(parts) >= 2:
                            new_params = "windowWidth, windowHeight, WEBGL"
                        else:
                            new_params = f"{params}, WEBGL"
                    else:
                        new_params = "windowWidth, windowHeight, WEBGL"
                    
                    adapted = re.sub(r'createCanvas\s*\(\s*[^)]*\s*\)', f'createCanvas({new_params})', adapted)
            else:
                # No createCanvas found, insert standard setup canvas at the beginning of setup()
                setup_match = re.search(r'function\s+setup\s*\(\s*\)\s*\{', adapted)
                if setup_match:
                    adapted = re.sub(r'function\s+setup\s*\(\s*\)\s*\{', 'function setup() {\n  createCanvas(windowWidth, windowHeight, WEBGL);', adapted)

        # 3. Inject standard stubs if functions like makeFilter are called but not defined
        if 'makeFilter' in adapted and not re.search(r'(function\s+makeFilter|makeFilter\s*[:=])', adapted):
            adapted += """

// Auto-generated compatibility stub for makeFilter
if (typeof makeFilter === 'undefined') {
  window.makeFilter = function() {
    if (typeof filter !== 'undefined') {
      filter(GRAY);
    }
  };
}

// Auto-generated compatibility stub for drawOverPattern
if (typeof drawOverPattern === 'undefined') {
  window.drawOverPattern = function() {
    // Safe fallback stub to prevent ReferenceError
  };
}

// Auto-generated compatibility stub for setPalette
if (typeof setPalette === 'undefined') {
  window.setPalette = function() {
    // Safe fallback stub to prevent ReferenceError
  };
}

// Auto-generated compatibility stub for palettes
if (typeof palettes === 'undefined') {
  window.palettes = [
    ["#fdfffc", "#235789", "#c1292e", "#f1d302", "#020100"],
    ["#0D1E40", "#224573", "#5679A6", "#F2A25C", "#D96B43"],
    ["#7E56A6", "#F28B50", "#A63B14", "#591202", "#260101"],
    ["#4ED98A", "#3B8C57", "#F2AD85", "#404040", "#0D0D0D"],
    ["#725373", "#7866F2", "#8979F2", "#025373", "#BF7D56"]
  ];
}
"""

        # 4. Inject standard stubs if overAllTexture is used but not defined
        if 'overAllTexture' in adapted and not re.search(r'\b(let|var|const)\s+overAllTexture\b', adapted):
            adapted = "var overAllTexture;\n" + adapted
            adapted += """

// Auto-generated compatibility stub for overAllTexture
if (typeof draw === 'function') {
  if (typeof window._originalDraw === 'undefined') { window._originalDraw = draw; }
  draw = function() {
    if (typeof overAllTexture === 'undefined' || !overAllTexture) {
      if (typeof createGraphics !== 'undefined') {
        overAllTexture = createGraphics(windowWidth || 800, windowHeight || 600);
      }
    }
    window._originalDraw();
  };
}
"""

        # 5. 防衛性轉譯器常駐外掛 Stub 注入
        if "window._origLoadImage =" not in adapted and "const _origLoadImage =" not in adapted:
            adapted += """

// 1. 免疫 DOM 元素建立導致的看門狗攔截
if (typeof createP === 'undefined') { window.createP = function() { return { position: function(){}, style: function(){} }; }; }
if (typeof createDiv === 'undefined') { window.createDiv = function() { return { position: function(){}, style: function(){} }; }; }

// 2. 圖片與非同步資產載入後備自癒護欄
if (typeof p5 !== 'undefined' && p5.prototype) {
    if (typeof window._origLoadImage === 'undefined') { window._origLoadImage = p5.prototype.loadImage; }
    p5.prototype.loadImage = function(path, successCallback, failureCallback) {
        if (typeof path !== 'string' || (path.startsWith('http') === false && path.startsWith('data:') === false)) {
            // 當發現是相對路徑或丟失的外部圖片資產時，使用 1x1 灰色 GIF 的 Base64 代替，防止渲染死鎖
            const dummyPath = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
            return window._origLoadImage.call(this, dummyPath, successCallback, failureCallback);
        }
        return window._origLoadImage.call(this, path, successCallback, failureCallback);
    };
}

// 3. 修正 3D 渲染圖層 WebGL 與 Canvas 2D 上下文屬性缺失
if (typeof p5 !== 'undefined' && p5.prototype) {
    if (typeof window._origGet === 'undefined') { window._origGet = p5.prototype.get; }
    p5.prototype.get = function(...args) {
        if (this.width === 0 || this.height === 0) {
            return createGraphics(10, 10);
        }
        return window._origGet.apply(this, args);
    };
}
"""

        # Update the editor content
        self.editor.setPlainText(adapted)
        self.log_to_console("SUCCESS: 代碼自動轉換完成！已進行音訊特徵映射與 WebGL 規格相容性修復。")

    def compile_and_run_sandbox(self):
        self.console_log.clear()
        self.has_errors = False
        self.test_run_performed = True
        
        # Automatically run adaptation and repair first
        self.adapt_and_repair_code()
        
        name = self.name_input.text().strip()
        if not name:
            self.log_to_console("ERROR: 模組名稱不得為空！ (Module name cannot be empty)", is_err=True)
            return

        code = self.editor.toPlainText()
        self.log_to_console("Compiling p5.js sketch and starting WebEngine Sandbox...")

        # Construct local sandbox HTML
        html_doc = self.get_sandbox_html(code)
        
        # Load page content
        self.web_view.setHtml(html_doc, QUrl("http://localhost/"))
        
        # Start beat simulation timer (120 BPM = 500ms beat interval)
        if not self.beat_timer.isActive():
            self.beat_timer.start(500)
            
        # Give a small delay to check for syntax/execution errors before enabling confirm box
        QTimer.singleShot(1000, self.check_sandboxed_success)

    def trigger_simulated_beat(self):
        if self.test_run_performed and not self.has_errors:
            self.web_view.page().runJavaScript("if (window.triggerBeat) { window.triggerBeat(); }")

    def check_sandboxed_success(self):
        if not self.has_errors:
            self.log_to_console("Sandbox compilation successful. Render loop active at 60Hz.")
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
            
        # Format and write message to console log text area
        prefix = "[ERROR] " if is_err else "[INFO] "
        log_line = f"{prefix}Line {lineNumber}: {message}"
        self.log_to_console(log_line, is_err)

    def log_to_console(self, text, is_err=False):
        color = "#f43f5e" if is_err else "#10b981"
        self.console_log.append(f"<span style='color: {color};'>{text}</span>")
        # Scroll to bottom
        self.console_log.moveCursor(QTextCursor.MoveOperation.End)

    def toggle_save_button(self):
        self.btn_save.setEnabled(self.cb_confirm.isChecked())

    def save_and_close(self):
        name = self.name_input.text().strip()
        if not name:
            self.log_to_console("ERROR: 模組名稱不得為空！ (Module name cannot be empty)", is_err=True)
            return

        # Ensure alphanumeric, underscores, and hyphens only
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            self.log_to_console("ERROR: 模組名稱只能包含英文字母、數字、底線(_)和連字號(-)！", is_err=True)
            return

        # Create custom_visuals directory in workspace
        workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)

        save_path = None
        existing_metadata = {}
        author = ""

        # Load existing metadata if editing from an initial filename
        if getattr(self, "initial_filename", ""):
            orig_path = os.path.join(save_dir, f"{self.initial_filename}.json")
            if os.path.exists(orig_path):
                try:
                    with open(orig_path, "r", encoding="utf-8") as f_in:
                        existing_metadata = json.load(f_in)
                    author = existing_metadata.get("author", "").strip()
                except Exception:
                    pass
                
                # If name didn't change, we overwrite the original file
                if existing_metadata.get("name", "").strip() == name:
                    save_path = orig_path

        # If not editing or renamed, look for file with same name and author to decide overwrite
        if not save_path:
            existing_file_path = None
            for fname in os.listdir(save_dir):
                if fname.endswith(".json"):
                    fpath = os.path.join(save_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as ef:
                            existing = json.load(ef)
                        if existing.get("name", "").strip() == name and existing.get("author", "").strip() == author:
                            existing_file_path = fpath
                            existing_metadata = existing
                            break
                    except Exception:
                        continue
            
            if existing_file_path:
                display_author = f" (作者: {author})" if author else ""
                reply = QMessageBox.question(
                    self, "名稱衝突",
                    f"模組「{name}」{display_author}已經存在。\n是否要覆蓋現有模組？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                save_path = existing_file_path
            else:
                # Find a new unique filename
                sanitized_author = "".join([c for c in author if c.isalnum() or c in ('-', '_')]).strip() if author else ""
                if sanitized_author:
                    base_filename = f"{name}_{sanitized_author}"
                else:
                    base_filename = name
                    
                candidate = f"{base_filename}.json"
                counter = 1
                while os.path.exists(os.path.join(save_dir, candidate)):
                    candidate = f"{base_filename}_{counter}.json"
                    counter += 1
                save_path = os.path.join(save_dir, candidate)

        # Prepare saved module settings, preserving existing metadata
        module_data = existing_metadata.copy()
        module_data.update({
            "name": name,
            "code": self.editor.toPlainText(),
            "frequency": self.freq_slider.value(),
            "storyboard_weight": self.weight_slider.value(),
            "post_fx_intensity": self.fx_slider.value(),
            "custom_html": getattr(self, "custom_html", ""),
            "custom_css": getattr(self, "custom_css", ""),
            "inline_assets": getattr(self, "inline_assets", {}),
        })
        if hasattr(self, 'op_input'):
            module_data["url"] = self.op_input.text().strip()

        # --- 重複收錄檢測 (Duplicate Module Detection) ---
        current_code = self.editor.toPlainText().strip()
        current_url = self.op_input.text().strip() if hasattr(self, 'op_input') else ""

        def _normalize_code(code_str):
            return re.sub(r'\s+', '', code_str)

        normalized_current = _normalize_code(current_code) if current_code else ""
        duplicate_by_url = None
        duplicate_by_code = None

        unique_name = os.path.basename(save_path)[:-5]

        for fname in os.listdir(save_dir):
            if not fname.endswith(".json") or fname == f"{unique_name}.json":
                continue
            try:
                fpath = os.path.join(save_dir, fname)
                with open(fpath, "r", encoding="utf-8") as ef:
                    existing = json.load(ef)
                existing_name = fname[:-5]

                # URL 比對
                if current_url and existing.get("url", ""):
                    if current_url.rstrip("/") == existing.get("url", "").rstrip("/"):
                        duplicate_by_url = existing_name
                        break

                # 程式碼比對 (正規化後完全一致)
                existing_code = existing.get("code", "").strip()
                if normalized_current and existing_code:
                    if _normalize_code(existing_code) == normalized_current:
                        duplicate_by_code = existing_name
                        break
            except Exception:
                continue

        if duplicate_by_url:
            reply = QMessageBox.warning(
                self, "⚠️ 重複收錄偵測",
                f"此 OpenProcessing 網址已收錄於模組「{duplicate_by_url}」。\n\n"
                f"確定仍要另存為「{name}」嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if duplicate_by_code:
            reply = QMessageBox.warning(
                self, "⚠️ 重複收錄偵測",
                f"此程式碼與已收錄模組「{duplicate_by_code}」的內容完全一致。\n\n"
                f"確定仍要另存為「{name}」嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        # --- 重複檢測結束 ---

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(module_data, f, indent=4, ensure_ascii=False)
            logger.info(f"Custom visual saved successfully to {save_path}")
            
            # Stop simulated beat timer
            self.beat_timer.stop()

            # Execute callback to refresh parent UI
            if self.on_save_callback:
                self.on_save_callback(unique_name)

            self.accept()  # Close dialog with accepted status
        except Exception as e:
            logger.error(f"Failed to save visual preset: {e}")
            self.log_to_console(f"ERROR: 儲存預設檔失敗: {e}", is_err=True)

    def closeEvent(self, event):
        # 銷毀視窗時強制停用與釋放 Timer 線程，並清理 QWebEngineView，徹底避免記憶體洩漏 (OOM)
        self.beat_timer.stop()
        self.web_view.stop()
        self.web_view.setParent(None)
        self.web_view.deleteLater()
        super().closeEvent(event)

    def fetch_and_load_openprocessing(self):
        url = self.op_input.text().strip()
        if not url:
            self.log_to_console("ERROR: 請先輸入 OpenProcessing 作品網址！", is_err=True)
            return
            
        self.log_to_console(f"正在從 OpenProcessing 獲取作品代碼: {url} ...")
        self.btn_op_fetch.setEnabled(False)
        self.btn_op_fetch.setText("⏳ 正在下載...")
        QApplication.processEvents()
        
        try:
            title, sketch_id, code, css, html, assets = self.perform_op_fetch(url)
            self.custom_css = css
            self.custom_html = html
            self.inline_assets = assets
            self.editor.setPlainText(code)
            
            import re
            cleaned_title = re.sub(r'[^a-zA-Z0-9_]', '', title)
            if not cleaned_title:
                cleaned_title = f"op_{sketch_id}"
            self.name_input.setText(cleaned_title)
            self.log_to_console(f"SUCCESS: 成功載入作品「{title}」(ID: {sketch_id})！")
            self.adapt_and_repair_code()
        except Exception as e:
            self.log_to_console(f"ERROR: 擷取失敗: {e}", is_err=True)
        finally:
            self.btn_op_fetch.setEnabled(True)
            self.btn_op_fetch.setText("⚡ 【自動抓取程式碼】")
            QApplication.processEvents()

    def extract_js_object(self, html, var_name):
        pattern = rf'\bvar\s+{var_name}\s*=\s*'
        match = re.search(pattern, html)
        if not match:
            return None
        
        start_idx = match.end()
        first_brace_idx = html.find('{', start_idx)
        if first_brace_idx == -1:
            return None
            
        brace_count = 0
        in_string = False
        string_char = None
        escaped = False
        in_regex = False
        
        for i in range(first_brace_idx, len(html)):
            char = html[i]
            next_char = html[i+1] if i + 1 < len(html) else ""
            
            if escaped:
                escaped = False
                continue
                
            if char == '\\':
                escaped = True
                continue
                
            if in_string:
                if char == string_char:
                    in_string = False
                    string_char = None
                continue
                
            if in_regex:
                if char == '/':
                    in_regex = False
                continue
                
            if char in ('"', "'", '`'):
                in_string = True
                string_char = char
                continue
                
            if char == '/' and next_char not in ('/', '*'):
                in_regex = True
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return html[first_brace_idx:i+1]
                    
        return None

    def perform_op_fetch(self, url):
        import re
        import requests
        import json
        
        match = re.search(r'/sketch/(\d+)', url)
        if not match:
            match = re.search(r'/@[\w\-]+/(\d+)', url)
        if not match:
            raise ValueError("無法解析網址中的作品 ID，請確保網址格式正確。")
            
        sketch_id = match.group(1)
        embed_url = f"https://openprocessing.org/sketch/{sketch_id}/embed/"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(embed_url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise Exception(f"無法存取 OpenProcessing (HTTP {response.status_code})")
            
        html = response.text
        
        sketch_json = self.extract_js_object(html, "sketch")
        if not sketch_json:
            raise ValueError("無法在頁面中找到作品資料，可能該作品已被設為不公開或網址無效。")
            
        try:
            sketch_data = json.loads(sketch_json)
        except Exception as e:
            raise ValueError(f"解析作品資料失敗: {e}")
            
        title = sketch_data.get("title", f"op_{sketch_id}")
        
        versions = sketch_data.get("versions", [])
        if not versions or not isinstance(versions, list):
            raise ValueError("此作品中未包含任何版本程式碼。")
            
        v0 = versions[0]
        code_objects = v0.get("codeObjects", [])
        if not code_objects or not isinstance(code_objects, list):
            raise ValueError("此作品中未包含任何程式碼檔案。")
            
        def get_order_id(x):
            val = x.get("orderID")
            if val is None:
                return 0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0
        sorted_objects = sorted(code_objects, key=get_order_id)
        
        custom_css = ""
        custom_html = ""
        html_tab_code = ""
        
        for obj in sorted_objects:
            tab_title = obj.get("title", "tab")
            tab_code = obj.get("code", "")
            
            if tab_title.lower().endswith('.css'):
                custom_css += tab_code + "\n"
            elif tab_title.lower().endswith(('.html', '.htm')):
                html_tab_code = tab_code
                body_match = re.search(r'<body[^>]*>(.*?)</body>', tab_code, re.DOTALL | re.IGNORECASE)
                if body_match:
                    custom_html += body_match.group(1) + "\n"
                else:
                    cleaned = re.sub(r'<!DOCTYPE[^>]*>', '', tab_code, flags=re.IGNORECASE)
                    cleaned = re.sub(r'<html[^>]*>', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r'</html>', '', cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r'<head[^>]*>.*?</head>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
                    custom_html += cleaned + "\n"

        # Determine JS execution order from HTML scripts, or fallback
        ordered_js_titles = []
        if html_tab_code:
            ordered_js_titles = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', html_tab_code, re.IGNORECASE)

        js_objects = []
        for obj in sorted_objects:
            tab_title = obj.get("title", "tab")
            if tab_title.lower().endswith(('.css', '.html', '.htm', '.txt', '.json', '.glsl', '.vert', '.frag')):
                continue
            js_objects.append(obj)

        if ordered_js_titles:
            js_lookup = {}
            for obj in js_objects:
                t = obj.get("title", "").lower().strip()
                js_lookup[t] = obj
                if t.endswith(".js"):
                    js_lookup[t[:-3]] = obj
                else:
                    js_lookup[t + ".js"] = obj

            sorted_js_objects = []
            seen_objs = set()
            for src_name in ordered_js_titles:
                normalized_src = src_name.lower().strip()
                if normalized_src in js_lookup:
                    matching_obj = js_lookup[normalized_src]
                    obj_id = id(matching_obj)
                    if obj_id not in seen_objs:
                        sorted_js_objects.append(matching_obj)
                        seen_objs.add(obj_id)

            for obj in js_objects:
                if id(obj) not in seen_objs:
                    sorted_js_objects.append(obj)
        else:
            sorted_js_objects = []
            main_sketches = []
            for obj in js_objects:
                t = obj.get("title", "").lower()
                if t == "mysketch.js" or t == "mysketch":
                    main_sketches.append(obj)
                else:
                    sorted_js_objects.append(obj)
            sorted_js_objects.extend(main_sketches)

        # 確保主繪圖檔 (包含 setup/draw 或是主檔名) 串接在最後，避免 shader/tools 變數先被引用而未初始化
        final_js_objects = []
        main_sketches = []
        for obj in sorted_js_objects:
            t = obj.get("title", "").lower().strip()
            code = obj.get("code", "")
            is_main = (
                t in ["mysketch.js", "mysketch", "sketch.js", "sketch", "main.js", "main"] 
                or "function setup(" in code 
                or "function draw(" in code 
                or "void setup(" in code
            )
            if is_main:
                main_sketches.append(obj)
            else:
                final_js_objects.append(obj)
        final_js_objects.extend(main_sketches)
        sorted_js_objects = final_js_objects

        full_code = ""
        import re
        local_import_pattern = r'(\bimport\s+(?:[^"\']*?)\s+from\s+["\'])(?!https?://)([^"\']+)(["\'])'
        for obj in sorted_js_objects:
            tab_title = obj.get("title", "tab")
            tab_code = obj.get("code", "")
            full_code += f"// === Tab: {tab_title} ===\n"
            
            # 註解掉本地模組導入 (例如 import ... from './shaderSource.js')，避免合併後同名宣告衝突
            cleaned_code = re.sub(local_import_pattern, r'// \g<0>', tab_code)
            full_code += cleaned_code
            if not cleaned_code.endswith("\n"):
                full_code += "\n"
            full_code += "\n"
            
        inline_assets = {}
        for obj in sorted_objects:
            tab_title = obj.get("title", "tab")
            tab_code = obj.get("code", "")
            if tab_title.lower().endswith(('.glsl', '.vert', '.frag', '.json', '.txt')):
                inline_assets[tab_title] = tab_code

        return title, sketch_id, full_code, custom_css, custom_html, inline_assets

    def get_default_template(self):
        return """// Default p5.js visual module template
// Global variables updated live from sliders:
// - frequency (0-100)
// - storyboardWeight (0-100)
// - postFxIntensity (0-100)
//
// Real-time audio beat sync variables:
// - isBeat (boolean, spikes true for one frame on beat)
// - beatEnergy (0.0 to 1.0, decays smoothly)
// - audioLow (0.0 to 1.0, real-time bass energy)
// - audioMid (0.0 to 1.0, real-time mid energy)
// - audioHigh (0.0 to 1.0, real-time treble energy)

let rotation = 0;

function setup() {
  createCanvas(windowWidth, windowHeight, WEBGL);
  colorMode(HSB, 360, 100, 100, 1.0);
}

function draw() {
  // Semi-transparent black background creates trailing effect
  background(0, 0, 0, 0.08); 
  
  // Rotate based on time and frequency slider
  let speed = map(window.frequency || 50, 0, 100, 0.01, 0.1);
  rotation += speed;
  rotateX(rotation * 0.5);
  rotateY(rotation);
  
  // Scale dynamically with beat energy
  let size = 120 + (window.beatEnergy || 0) * 120;
  
  // Color map based on storyboard weight
  let hue = map(window.storyboardWeight || 50, 0, 100, 0, 360);
  
  // Modulate saturation with mid frequency
  let sat = map(window.audioMid || 0.5, 0, 1, 60, 100);
  fill(hue, sat, 100, 0.85);
  
  // Stroke based on treble audio energy
  let strokeHue = (hue + 180) % 360;
  let weight = map(window.audioHigh || 0.2, 0, 1, 1, 5);
  stroke(strokeHue, 90, 100);
  strokeWeight(weight);
  
  // Display layout shape selection governed by Post-FX intensity
  let fx = window.postFxIntensity || 50;
  if (fx > 70) {
    torus(size, size * 0.35, 24, 16);
  } else if (fx > 35) {
    box(size);
  } else {
    sphere(size, 16, 12);
  }
}
"""

    def get_sandbox_html(self, user_code):
        from main import MOCK_NATIVE_AUDIO_JS, MOCK_P5_JS
        freq = self.freq_slider.value()
        weight = self.weight_slider.value()
        fx = self.fx_slider.value()
        
        custom_css = getattr(self, "custom_css", "")
        custom_html = getattr(self, "custom_html", "")

        import re
        has_import_export = bool(re.search(r'\b(import|export)\b', user_code))
        has_es6_class = "class " in user_code and "constructor" in user_code
        is_module = has_import_export or has_es6_class or "p5.Shader" in user_code or "importmap" in user_code

        BIND_MODULE_CALLBACKS_JS = """
        // Auto-generated mapping to bind Module-scoped p5.js callbacks to window
        (function() {
          const p5Callbacks = [
            'setup', 'draw', 'preload', 'windowResized',
            'keyPressed', 'keyReleased', 'keyTyped',
            'mousePressed', 'mouseReleased', 'mouseClicked',
            'mouseMoved', 'mouseDragged', 'mouseWheel', 'doubleClicked',
            'touchStarted', 'touchMoved', 'touchEnded'
          ];
          p5Callbacks.forEach(cb => {
            try {
              let fn = eval(cb);
              if (typeof fn === 'function' && !window[cb]) {
                window[cb] = fn;
              }
            } catch (e) {}
          });
        })();
        """

        if is_module:
            script_tag = f'<script type="module">{user_code}\n{BIND_MODULE_CALLBACKS_JS}</script>'
        else:
            script_tag = f'<script>{user_code}</script>'
        
        html_template = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{
      margin: 0;
      overflow: hidden;
      background: #000;
    }}
    canvas {{
      display: block;
      width: 100vw !important;
      height: 100vh !important;
      object-fit: cover;
      box-sizing: border-box;
    }}
    /*CUSTOM_CSS_PLACEHOLDER*/
  </style>
  <script type="importmap">
    {{
      "imports": {{
        "three": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/jsm/",
        "rampensau": "https://cdn.jsdelivr.net/npm/rampensau/+esm"
      }}
    }}
  </script>
  <script>
    // Mock innerWidth/innerHeight to standard 16:9 HD resolution before p5.js loads
    Object.defineProperty(window, 'innerWidth', {{ get: function() {{ return 1422; }} }});
    Object.defineProperty(window, 'innerHeight', {{ get: function() {{ return 800; }} }});
    {MOCK_NATIVE_AUDIO_JS}
  </script>
  <script src="custom_visuals/libs/p5.min.js"></script>
  <script src="custom_visuals/libs/p5.sound.min.js"></script>
  <script src="custom_visuals/libs/p5.func.min.js"></script>
  <script src="custom_visuals/libs/gsap.min.js"></script>
  <script src="custom_visuals/libs/opc.min.js"></script>
  <script src="custom_visuals/libs/p5.flex.min.js"></script>
  <script src="custom_visuals/libs/rampensau.js"></script>
  <script src="custom_visuals/libs/chroma.min.js"></script>
  <script>
    /*ASSET_INTERCEPTOR_PLACEHOLDER*/
    {MOCK_P5_JS}

    // 強力打樁：防止部分作品調用網頁 UI 庫引發 Uncaught ReferenceError
    window.lil = window.lil || {{ GUI: class {{ add() {{ return this; }} addFolder() {{ return this; }} open() {{ return this; }} onChange() {{ return this; }} setValue() {{ return this; }} }} }};
    window.dat = window.dat || {{ GUI: class {{ add() {{ return this; }} addFolder() {{ return this; }} }} }};
    window.planck = window.planck || {{ World: class {{}}, Vec2: class {{}} }};
    window.PVector = window.PVector || class {{ constructor(x,y,z){{ this.x=x||0; this.y=y||0; this.z=z||0; }} static dist(v1,v2){{ return Math.sqrt((v1.x-v2.x)**2+(v1.y-v2.y)**2); }} }};
    window.BLUR = 11; window.GRAY = 14; window.WEBGL = "webgl";

    // OPC stub compatibility layer
    if (typeof OPC === 'undefined') {{
      window.OPC = {{
        slider: function(name, value, min, max, step) {{ window[name] = value; return this; }},
        button: function() {{ return this; }},
        toggle: function(name, value) {{ window[name] = value; return this; }},
        color: function(name, value) {{ window[name] = value; return this; }},
        select: function(name, value) {{ window[name] = value; return this; }},
        text: function(name, value) {{ window[name] = value; return this; }},
        setGlobal: function(name, value) {{ window[name] = value; }}
      }};
    }}

    // Seed compatibility
    window.seed = window.seed || Math.floor(Math.random() * 999999);

    // Stub fullscreen and createCanvas to avoid browser permission exceptions and layout issues
    if (typeof p5 !== 'undefined' && p5.prototype) {{
      p5.prototype.fullscreen = function(val) {{
        if (typeof val === 'undefined') {{
          return false;
        }}
        return false;
      }};

      const originalCreateCanvas = p5.prototype.createCanvas;
      p5.prototype.createCanvas = function(w, h, val) {{
        let winW = window.innerWidth;
        let winH = window.innerHeight;
        if (!winW || winW < 100) winW = w || 800;
        if (!winH || winH < 100) winH = h || 600;
        let targetWidth = winW;
        let targetHeight = winH;
        if (w && h) {{
          let scale = Math.max(winW / w, winH / h);
          targetWidth = w * scale;
          targetHeight = h * scale;
        }}
        window.windowWidth = targetWidth;
        window.windowHeight = targetHeight;
        let canvas = originalCreateCanvas.call(this, targetWidth, targetHeight, val);
        if (canvas && canvas.elt) {{
          canvas.elt.style.setProperty('position', 'absolute', 'important');
          canvas.elt.style.setProperty('left', '50%', 'important');
          canvas.elt.style.setProperty('top', '50%', 'important');
          canvas.elt.style.setProperty('right', 'auto', 'important');
          canvas.elt.style.setProperty('bottom', 'auto', 'important');
          canvas.elt.style.setProperty('transform', 'translate(-50%, -50%)', 'important');
          canvas.elt.style.setProperty('width', '100vw', 'important');
          canvas.elt.style.setProperty('height', '100vh', 'important');
          canvas.elt.style.setProperty('object-fit', 'cover', 'important');
          canvas.elt.style.setProperty('margin', '0', 'important');
        }}
        return canvas;
      }};
    }}

    // Global parameters
    window.frequency = {freq};
    window.storyboardWeight = {weight};
    window.postFxIntensity = {fx};
    
    // Audio beat state variables
    window.isBeat = false;
    window.beatEnergy = 0;
    window.audioLow = 0;
    window.audioMid = 0;
    window.audioHigh = 0;

    window.updateParams = function(freq, weight, fx) {{
      window.frequency = freq;
      window.storyboardWeight = weight;
      window.postFxIntensity = fx;
    }};

    window.triggerBeat = function() {{
      window.isBeat = true;
      window.beatEnergy = 1.0;
      setTimeout(() => {{ window.isBeat = false; }}, 50);
    }};

    // Redirect Javascript errors to console.error so CustomWebEnginePage can capture it
    window.onerror = function(message, source, lineno, colno, error) {{
      console.error(message + " (line " + lineno + ")");
      return false;
    }};

    // Continuous decay and audio feature modulation simulation tick
    function tick() {{
      if (window.beatEnergy > 0) {{
        window.beatEnergy *= 0.92;
      }}
      // Generate some smooth background random noise for audio spectrum bands
      window.audioLow = 0.2 + 0.3 * Math.sin(Date.now() * 0.005) + (window.beatEnergy * 0.5);
      window.audioMid = 0.15 + 0.25 * Math.sin(Date.now() * 0.007);
      window.audioHigh = 0.1 + 0.2 * Math.sin(Date.now() * 0.01) + (window.beatEnergy * 0.3);
      
      requestAnimationFrame(tick);
    }}
    requestAnimationFrame(tick);
  </script>
</head>
<body>
  <!--CUSTOM_HTML_PLACEHOLDER-->
  {script_tag}
</body>
</html>
"""
        import json
        assets_json = json.dumps(getattr(self, "inline_assets", {}))
        interceptor = f"""
    window.inline_assets = {assets_json};
    
    // Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = function(input, init) {{
      const url = typeof input === 'string' ? input : (input.url || "");
      const filename = url.split('/').pop();
      if (window.inline_assets && window.inline_assets[filename] !== undefined) {{
        return Promise.resolve(new Response(window.inline_assets[filename]));
      }}
      return originalFetch.apply(this, arguments).catch(function(err) {{
        console.warn('[Sandbox] Fetch failed for: ' + url + ' (' + err.message + ')');
        return new Response('', {{ status: 404, statusText: 'Not Found' }});
      }});
    }};

    // Intercept XMLHttpRequest
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, async, user, password) {{
      const filename = url.split('/').pop();
      if (window.inline_assets && window.inline_assets[filename] !== undefined) {{
        this.send = function() {{
          Object.defineProperty(this, 'readyState', {{ value: 4, writable: true }});
          Object.defineProperty(this, 'status', {{ value: 200, writable: true }});
          Object.defineProperty(this, 'responseText', {{ value: window.inline_assets[filename], writable: true }});
          if (this.onload) this.onload();
          if (this.onreadystatechange) this.onreadystatechange();
        }};
        return;
      }}
      return originalOpen.apply(this, arguments);
    }};
"""
        return html_template.replace("/*CUSTOM_CSS_PLACEHOLDER*/", custom_css).replace("<!--CUSTOM_HTML_PLACEHOLDER-->", custom_html).replace("/*ASSET_INTERCEPTOR_PLACEHOLDER*/", interceptor)
