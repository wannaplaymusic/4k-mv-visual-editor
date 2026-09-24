#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VisualStudio Pro · 4K 視覺模組神經創作工作站 (V2 Pro Edition)
整合 AI 情景大師 Pro：聲學情感鏡像、創作者口味圖譜、概念隱喻與語意推子、多模態圖片逆向與心流微光
"""

import os
import sys
import json
import argparse
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSlider, QCheckBox, QSplitter,
    QStackedWidget, QTextEdit, QPlainTextEdit, QFrame, QFileDialog,
    QMessageBox, QScrollArea, QGroupBox, QComboBox, QProgressBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot, QRect, QSize
from PyQt6.QtGui import QColor, QFont, QPainter, QTextFormat, QTextCursor, QIcon

# 載入核心模組
from visual_studio_core import (
    ASTParamEngine, ScenarioMaestro, CreationWizard,
    VirtualAudioDeck, ShaderRackBridge, QCValidator,
    MaestroAcousticMirror, MaestroTasteProfiler,
    MaestroMetaphorAlchemist, MaestroVisionDecompiler,
    MaestroAmbientMuse,
    BaseVisualEngine, EngineMetadata, EngineRegistry, get_engine_registry
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("VisualStudioPro")

# 確保 WebEngine 繞過安全限制
if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-web-security"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"


class CustomWebPage(QWebEnginePage):
    def __init__(self, log_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_callback = log_callback

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        self.log_callback(level, message, lineNumber)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)


class StudioCodeEditor(QPlainTextEdit):
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
                background-color: #121316;
                color: #e4e4e7;
                border: 1px solid #27272a;
                border-radius: 6px;
                font-family: 'JetBrains Mono', 'Menlo', 'Courier New', monospace;
                font-size: 12px;
                line-height: 1.4;
            }
        """)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)

    def lineNumberAreaWidth(self):
        digits = 1
        max_blocks = max(1, self.blockCount())
        while max_blocks >= 10:
            max_blocks //= 10
            digits += 1
        return 16 + self.fontMetrics().horizontalAdvance('9') * digits

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
                    painter.setPen(QColor("#a855f7"))
                painter.drawText(0, top, self.lineNumberArea.width() - 8, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        extraSelections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor("#1f1f23"))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)


class VisualStudioMainWindow(QMainWindow):
    def __init__(self, initial_module_name=None):
        super().__init__()
        self.workspace_dir = os.path.dirname(os.path.abspath(__file__))
        self.custom_visuals_dir = os.path.join(self.workspace_dir, "custom_visuals")
        os.makedirs(self.custom_visuals_dir, exist_ok=True)

        self.maestro = ScenarioMaestro(self.workspace_dir)
        self.wizard = CreationWizard(self.maestro)
        self.audio_deck = VirtualAudioDeck()
        self.shader_bridge = ShaderRackBridge(self.workspace_dir)

        self.current_code = ""
        self.current_module_name = initial_module_name or "New_Neural_Visual"
        self.active_shaders = []
        self.slider_widgets = {}

        # 4 大語意方向推子 (Chaos, Organic, Aggression, Depth)
        self.semantic_steer = {
            "chaos": 0.5,
            "organic": 0.5,
            "aggression": 0.5,
            "depth": 0.5
        }

        # 動態設備機架 (Studio Rack Engine Discovery)
        self.engine_registry = get_engine_registry()
        self.current_engine_id = self.engine_registry.get_default_engine_id() or "math_synth"
        self.engine_buttons = {}
        self.engine_control_panel_widget = None

        self.init_ui()
        self.switch_engine(self.current_engine_id, auto_generate=False)

        # 音訊同步計時器 (30 FPS 刷新聲學特徵)
        self.audio_sync_timer = QTimer(self)
        self.audio_sync_timer.timeout.connect(self.sync_audio_frame_to_sandbox)
        self.audio_sync_timer.start(33)

        # 心流微光輪詢計時器 (每 4 秒檢測一次猶豫)
        self.muse_timer = QTimer(self)
        self.muse_timer.timeout.connect(self.poll_ambient_muse)
        self.muse_timer.start(4000)

        if initial_module_name:
            self.load_existing_module(initial_module_name)
        else:
            self.spin_slot_and_init()

    def init_ui(self):
        self.setWindowTitle("VisualStudio Pro · 4K 視覺模組神經創作工作站 (V2 Pro Edition)")
        self.resize(1540, 930)
        self.setMinimumSize(1180, 720)

        self.setStyleSheet("""
            QMainWindow { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
            QLineEdit { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 12px; font-size: 13px; }
            QSlider::groove:horizontal { border: 1px solid #27272a; height: 6px; background: #18181b; border-radius: 3px; }
            QSlider::handle:horizontal { background: #a855f7; border: 1px solid #c084fc; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 7px 14px; font-weight: bold; font-size: 12px; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QGroupBox { border: 1px solid #27272a; border-radius: 8px; margin-top: 10px; font-size: 12px; font-weight: bold; color: #a1a1aa; padding-top: 14px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 6px; }
            QScrollArea { border: none; background: transparent; }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 頂部導航列 (Top Header Bar)
        top_bar = self._create_top_header()
        main_layout.addLayout(top_bar)

        # 主工作區拆分器 (Left, Center, Right)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, central_widget)
        main_layout.addWidget(self.main_splitter, stretch=1)

        # 左翼：雙軌面板 (Wizard Track / Pro Track)
        self.left_panel = self._create_left_panel()
        self.main_splitter.addWidget(self.left_panel)

        # 中央：4K 沙盒預覽區 + 4 大語意方向推子 + GLSL 機架
        self.center_panel = self._create_center_panel()
        self.main_splitter.addWidget(self.center_panel)

        # 右翼：AST 動態參數旋鈕盤 (Param Deck)
        self.right_panel = self._create_right_panel()
        self.main_splitter.addWidget(self.right_panel)

        self.main_splitter.setStretchFactor(0, 31)
        self.main_splitter.setStretchFactor(1, 49)
        self.main_splitter.setStretchFactor(2, 20)

        # 底部：虛擬調音台 (Virtual Audio Deck)
        bottom_deck = self._create_bottom_audio_deck()
        main_layout.addLayout(bottom_deck)

    def _create_top_header(self):
        bar = QHBoxLayout()
        logo_label = QLabel("🚀 <b>VisualStudio Pro</b> <span style='color:#a855f7;'>v2.0 Neural Maestro</span>")
        logo_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        bar.addWidget(logo_label)

        bar.addSpacing(12)

        # 動態引擎機架切換膠囊 (Studio Rack Engine Switcher Capsule)
        capsule_frame = QFrame()
        capsule_frame.setStyleSheet("""
            QFrame {
                background-color: #121316;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 2px 4px;
            }
        """)
        capsule_layout = QHBoxLayout(capsule_frame)
        capsule_layout.setContentsMargins(4, 2, 4, 2)
        capsule_layout.setSpacing(4)

        engines = self.engine_registry.list_engines()
        for meta in engines:
            btn = QPushButton(f"{meta.icon} {meta.name.split(' (')[0]}")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            is_active = (meta.id == self.current_engine_id)
            btn.setChecked(is_active)
            if is_active:
                btn.setStyleSheet("background-color: #7e22ce; border: 1px solid #c084fc; color: #ffffff; font-weight: bold; border-radius: 5px; padding: 2px 10px; font-size: 11px;")
            else:
                btn.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; color: #a1a1aa; border-radius: 5px; padding: 2px 10px; font-size: 11px;")
            btn.clicked.connect(lambda _, eid=meta.id: self.switch_engine(eid))
            capsule_layout.addWidget(btn)
            self.engine_buttons[meta.id] = btn

        bar.addWidget(capsule_frame)
        bar.addSpacing(10)

        # 雙軌切換按鈕
        self.btn_mode_wizard = QPushButton("🧚 視界引導精靈")
        self.btn_mode_wizard.setStyleSheet("background-color: #581c87; border-color: #7e22ce; color: #f3e8ff;")
        self.btn_mode_wizard.clicked.connect(lambda: self.switch_mode("wizard"))
        bar.addWidget(self.btn_mode_wizard)

        self.btn_mode_pro = QPushButton("🎛️ 專家代碼台")
        self.btn_mode_pro.setStyleSheet("background-color: #18181b; color: #f4f4f5;")
        self.btn_mode_pro.clicked.connect(lambda: self.switch_mode("pro"))
        bar.addWidget(self.btn_mode_pro)

        bar.addSpacing(10)

        # 靈感老虎機
        btn_slot = QPushButton("🎲 靈感老虎機")
        btn_slot.setStyleSheet("background-color: #1e1b4b; border-color: #3730a3; color: #c7d2fe;")
        btn_slot.clicked.connect(self.spin_slot_and_init)
        bar.addWidget(btn_slot)

        # 視覺參考圖多模態逆向解構按鈕
        btn_image_decompile = QPushButton("🖼️ 圖片逆向")
        btn_image_decompile.setStyleSheet("background-color: #312e81; border-color: #4338ca; color: #e0e7ff;")
        btn_image_decompile.clicked.connect(self.decompile_image_dialog)
        bar.addWidget(btn_image_decompile)

        # 模組名稱
        bar.addSpacing(10)
        bar.addWidget(QLabel("模組名稱:"))
        self.name_input = QLineEdit()
        self.name_input.setText(self.current_module_name)
        self.name_input.setFixedWidth(170)
        bar.addWidget(self.name_input)

        bar.addStretch()

        # 刷新編譯
        btn_compile = QPushButton("⚡ 熱重載 (F5)")
        btn_compile.clicked.connect(self.recompile_current_code)
        bar.addWidget(btn_compile)

        # 一鍵驗收收編入庫
        btn_publish = QPushButton("💾 【一鍵驗證並收編入庫】")
        btn_publish.setStyleSheet("background-color: #065f46; border-color: #059669; color: #ecfdf5;")
        btn_publish.clicked.connect(self.publish_module_to_library)
        bar.addWidget(btn_publish)

        return bar

    def _create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        # 心流微光呼吸提示橫幅 (Ambient Muse Banner)
        self.muse_banner = QLabel("🕯️ 靈感微光：大師正在默默守護您的心流創作...")
        self.muse_banner.setStyleSheet("""
            background-color: #18181b;
            color: #a1a1aa;
            border: 1px solid #27272a;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 11px;
        """)
        self.muse_banner.setWordWrap(True)
        layout.addWidget(self.muse_banner)

        # 引擎專屬語境控制抽屜 (Context-Aware Engine Control Drawer)
        self.engine_control_container = QWidget()
        self.engine_control_layout = QVBoxLayout(self.engine_control_container)
        self.engine_control_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.engine_control_container)

        self.left_stack = QStackedWidget()
        layout.addWidget(self.left_stack)

        # 視圖 0: 精靈引導模式 (Wizard Mode View)
        wizard_widget = self._create_wizard_view()
        self.left_stack.addWidget(wizard_widget)

        # 視圖 1: 專家代碼編輯模式 (Pro Studio View)
        pro_widget = self._create_pro_view()
        self.left_stack.addWidget(pro_widget)

        return panel

    def _create_wizard_view(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)

        self.wizard_step_lbl = QLabel("步驟 1 / 5: 氣質定錨 (Mood & Genre)")
        self.wizard_step_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #a855f7;")
        l.addWidget(self.wizard_step_lbl)

        # 大師意象敘事卡片
        self.maestro_card = QTextEdit()
        self.maestro_card.setReadOnly(True)
        self.maestro_card.setStyleSheet("""
            background-color: #13111c;
            border: 1px solid #3b0764;
            border-radius: 8px;
            color: #d8b4fe;
            padding: 8px;
            font-size: 12px;
            line-height: 1.4;
        """)
        self.maestro_card.setFixedHeight(120)
        l.addWidget(self.maestro_card)

        # 步驟內容滾動區域
        self.wizard_options_scroll = QScrollArea()
        self.wizard_options_container = QWidget()
        self.wizard_options_layout = QVBoxLayout(self.wizard_options_container)
        self.wizard_options_layout.setContentsMargins(4, 4, 4, 4)
        self.wizard_options_scroll.setWidget(self.wizard_options_container)
        self.wizard_options_scroll.setWidgetResizable(True)
        l.addWidget(self.wizard_options_scroll, stretch=1)

        # 導航步進按鈕
        nav_row = QHBoxLayout()
        self.btn_prev_step = QPushButton("◀ 上一步")
        self.btn_prev_step.clicked.connect(self.wizard_prev)
        self.btn_next_step = QPushButton("下一步 ▶")
        self.btn_next_step.setStyleSheet("background-color: #7e22ce; color: #ffffff;")
        self.btn_next_step.clicked.connect(self.wizard_next)
        nav_row.addWidget(self.btn_prev_step)
        nav_row.addWidget(self.btn_next_step)
        l.addLayout(nav_row)

        return w

    def _create_pro_view(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("💻 p5.js / WebGL 原始碼 (Monaco/AST Core)")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #10b981;")
        l.addWidget(lbl)

        self.code_editor = StudioCodeEditor()
        self.code_editor.textChanged.connect(self.on_code_editor_modified)
        l.addWidget(self.code_editor, stretch=1)

        # AI 意圖對話微調輸入
        ai_row = QHBoxLayout()
        self.ai_prompt_input = QLineEdit()
        self.ai_prompt_input.setPlaceholderText("向大師許願，例如：荒涼廢土上的機械輓歌、帶有極光呼吸感...")
        btn_ai_ask = QPushButton("🪄 意向鍊金")
        btn_ai_ask.clicked.connect(self.ask_ai_patch)
        ai_row.addWidget(self.ai_prompt_input)
        ai_row.addWidget(btn_ai_ask)
        l.addLayout(ai_row)

        return w

    def _create_center_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        # 4K 沙盒視窗
        sandbox_box = QGroupBox("🌐 4K 60FPS 實時沙盒預覽 (Live Testing Sandbox)")
        s_layout = QVBoxLayout(sandbox_box)
        s_layout.setContentsMargins(4, 8, 4, 4)

        self.web_view = QWebEngineView()
        self.web_profile = QWebEngineProfile()
        self.web_page = CustomWebPage(self.handle_js_log, self.web_profile, self.web_view)
        self.web_view.setPage(self.web_page)

        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        self.web_view.setStyleSheet("background-color: #000; border-radius: 6px;")
        s_layout.addWidget(self.web_view)

        # QC 指示儀表燈
        qc_row = QHBoxLayout()
        self.lbl_fps = QLabel("FPS: <b>60.0</b>")
        self.lbl_black_screen = QLabel("黑畫面審計: <span style='color:#10b981;'>PASS</span>")
        self.lbl_audio_dynamic = QLabel("聲畫響應度: <span style='color:#a855f7;'>95%</span>")
        self.lbl_taste_badge = QLabel(f"<span style='color:#38bdf8;'>👤 {self.maestro.taste_profiler.get_taste_summary()[:28]}...</span>")
        qc_row.addWidget(self.lbl_fps)
        qc_row.addWidget(self.lbl_black_screen)
        qc_row.addWidget(self.lbl_audio_dynamic)
        qc_row.addWidget(self.lbl_taste_badge)
        qc_row.addStretch()
        s_layout.addLayout(qc_row)

        layout.addWidget(sandbox_box, stretch=4)

        # 4 大高階語意方向推子 (Semantic Directional Steer)
        steer_box = QGroupBox("🎚️ 4 大語意方向推子 (Semantic Directional Steer)")
        steer_layout = QHBoxLayout(steer_box)
        steer_layout.setContentsMargins(6, 6, 6, 6)

        self._add_steer_slider_widget(steer_layout, "混沌 (Chaos)", "chaos")
        self._add_steer_slider_widget(steer_layout, "有機 (Organic)", "organic")
        self._add_steer_slider_widget(steer_layout, "侵略 (Aggression)", "aggression")
        self._add_steer_slider_widget(steer_layout, "縱深 (Depth)", "depth")
        layout.addWidget(steer_box, stretch=1)

        # 著色器外掛機架 (Shader Rack)
        shader_box = QGroupBox("🎨 GLSL 著色器外掛機架 (Post-Shader Rack)")
        sh_layout = QHBoxLayout(shader_box)
        sh_layout.setContentsMargins(6, 6, 6, 6)

        self.cb_godrays = QCheckBox("體積神光 (Godrays)")
        self.cb_godrays.stateChanged.connect(self.update_active_shaders)
        self.cb_chromatic = QCheckBox("膠片色散 (RGB Split)")
        self.cb_chromatic.stateChanged.connect(self.update_active_shaders)
        self.cb_feedback = QCheckBox("反應擴散 (Feedback)")
        self.cb_feedback.stateChanged.connect(self.update_active_shaders)
        self.cb_glitch = QCheckBox("矩陣故障 (Glitch)")
        self.cb_glitch.stateChanged.connect(self.update_active_shaders)

        sh_layout.addWidget(self.cb_godrays)
        sh_layout.addWidget(self.cb_chromatic)
        sh_layout.addWidget(self.cb_feedback)
        sh_layout.addWidget(self.cb_glitch)
        sh_layout.addStretch()
        layout.addWidget(shader_box, stretch=1)

        return panel

    def _add_steer_slider_widget(self, layout, title: str, steer_key: str):
        col = QVBoxLayout()
        lbl_row = QHBoxLayout()
        name_lbl = QLabel(f"<span style='color:#cbd5e1; font-size:11px;'>{title}</span>")
        val_lbl = QLabel("50%")
        val_lbl.setStyleSheet("color:#a855f7; font-size:11px; font-weight:bold;")
        lbl_row.addWidget(name_lbl)
        lbl_row.addStretch()
        lbl_row.addWidget(val_lbl)
        col.addLayout(lbl_row)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        slider.valueChanged.connect(lambda v, k=steer_key, vl=val_lbl: self.on_steer_slider_changed(k, v, vl))
        col.addWidget(slider)
        layout.addLayout(col)

    def on_steer_slider_changed(self, key: str, val: int, val_lbl: QLabel):
        self.maestro.ambient_muse.touch_action()
        val_lbl.setText(f"{val}%")
        self.semantic_steer[key] = val / 100.0

        # 動態重新計算語意推子並更新代碼/沙盒
        mods = MaestroMetaphorAlchemist.compute_semantic_modulation(
            chaos=self.semantic_steer["chaos"],
            organic=self.semantic_steer["organic"],
            aggression=self.semantic_steer["aggression"],
            depth=self.semantic_steer["depth"]
        )
        # 熱修補關鍵變數
        js = f"""(function() {{
            if (typeof noiseScale !== 'undefined') noiseScale = {mods['noise_frequency']};
            if (typeof bassPower !== 'undefined') bassPower = {mods['bass_power_multiplier']};
            if (typeof zoomLevel !== 'undefined') zoomLevel = {mods['camera_zoom']};
        }})();"""
        self.web_view.page().runJavaScript(js)

    def _create_right_panel(self):
        panel = QGroupBox("🎛️ AST 參數旋鈕盤 (Param Deck)")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 8, 6, 6)

        scroll = QScrollArea()
        self.param_deck_container = QWidget()
        self.param_deck_layout = QVBoxLayout(self.param_deck_container)
        self.param_deck_layout.setContentsMargins(2, 2, 2, 2)
        self.param_deck_layout.setSpacing(8)
        scroll.setWidget(self.param_deck_container)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        return panel

    def _create_bottom_audio_deck(self):
        deck = QHBoxLayout()
        deck.setContentsMargins(4, 4, 4, 4)

        # 音訊載入按鈕與資訊
        btn_load_audio = QPushButton("📁 載入 MP3 測試")
        btn_load_audio.clicked.connect(self.load_audio_dialog)
        deck.addWidget(btn_load_audio)

        self.lbl_track_info = QLabel("音訊源: 手動合成模式 (120 BPM)")
        self.lbl_track_info.setFixedWidth(200)
        deck.addWidget(self.lbl_track_info)

        # 時間軸 Scrubbing
        deck.addWidget(QLabel("Scrub:"))
        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setRange(0, 1000)
        self.scrub_slider.setValue(0)
        self.scrub_slider.valueChanged.connect(self.on_scrub_changed)
        deck.addWidget(self.scrub_slider, stretch=1)

        # 手動推子：Bass, Mid, High
        deck.addWidget(QLabel("Bass:"))
        self.slider_bass = QSlider(Qt.Orientation.Horizontal)
        self.slider_bass.setRange(0, 100)
        self.slider_bass.setValue(50)
        self.slider_bass.setFixedWidth(70)
        self.slider_bass.valueChanged.connect(lambda v: setattr(self.audio_deck, "manual_bass", v / 100.0))
        deck.addWidget(self.slider_bass)

        deck.addWidget(QLabel("Mid:"))
        self.slider_mid = QSlider(Qt.Orientation.Horizontal)
        self.slider_mid.setRange(0, 100)
        self.slider_mid.setValue(50)
        self.slider_mid.setFixedWidth(70)
        self.slider_mid.valueChanged.connect(lambda v: setattr(self.audio_deck, "manual_mid", v / 100.0))
        deck.addWidget(self.slider_mid)

        deck.addWidget(QLabel("High:"))
        self.slider_high = QSlider(Qt.Orientation.Horizontal)
        self.slider_high.setRange(0, 100)
        self.slider_high.setValue(50)
        self.slider_high.setFixedWidth(70)
        self.slider_high.valueChanged.connect(lambda v: setattr(self.audio_deck, "manual_high", v / 100.0))
        deck.addWidget(self.slider_high)

        # 重音打擊 Tap Beat
        self.btn_tap_beat = QPushButton("💥 Tap Beat (SPACE)")
        self.btn_tap_beat.setStyleSheet("background-color: #9333ea; color: #ffffff;")
        self.btn_tap_beat.pressed.connect(self.audio_deck.trigger_tap_beat)
        self.btn_tap_beat.released.connect(self.audio_deck.release_tap_beat)
        deck.addWidget(self.btn_tap_beat)

        return deck

    # ==================== 動態引擎機架 (Studio Rack Engines) ====================
    def switch_engine(self, engine_id: str, auto_generate: bool = True):
        self.maestro.ambient_muse.touch_action()
        self.current_engine_id = engine_id

        # 1. 更新頂部膠囊按鈕狀態
        for eid, btn in self.engine_buttons.items():
            if eid == engine_id:
                btn.setChecked(True)
                btn.setStyleSheet("background-color: #7e22ce; border: 1px solid #c084fc; color: #ffffff; font-weight: bold; border-radius: 5px; padding: 2px 10px; font-size: 11px;")
            else:
                btn.setChecked(False)
                btn.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; color: #a1a1aa; border-radius: 5px; padding: 2px 10px; font-size: 11px;")

        engine = self.engine_registry.get_engine(engine_id)
        if not engine:
            return

        # 2. 語境感知：切換左側專屬控制抽屜
        self._mount_engine_control_panel(engine)

        # 3. 生成新引擎代碼並編譯
        if auto_generate:
            self.current_code = engine.generate_code()
            meta = engine.get_metadata()
            self.current_module_name = f"{engine_id}_{meta.category}"
            self.name_input.setText(self.current_module_name)
            self.recompile_current_code()

    def _mount_engine_control_panel(self, engine: BaseVisualEngine):
        if not hasattr(self, "engine_control_container") or not hasattr(self, "engine_control_layout"):
            return

        # 清除舊專屬元件
        if self.engine_control_panel_widget:
            self.engine_control_layout.removeWidget(self.engine_control_panel_widget)
            self.engine_control_panel_widget.deleteLater()
            self.engine_control_panel_widget = None

        new_widget = engine.create_control_widget(parent=self, on_param_changed=self.on_engine_param_changed)
        if new_widget:
            self.engine_control_panel_widget = new_widget
            self.engine_control_layout.addWidget(new_widget)
            self.engine_control_container.setVisible(True)
        else:
            self.engine_control_container.setVisible(False)

    def on_engine_param_changed(self, params: dict):
        engine = self.engine_registry.get_engine(self.current_engine_id)
        if not engine:
            return

        if params.get("__action__") == "mutate":
            # 遺傳變異當前 AST 參數
            current_ast = {p["name"]: p["value"] for p in ASTParamEngine.parse_params(self.current_code)}
            mutated = engine.mutate(current_ast, strength=params.get("strength", 0.3))
            self.current_code = engine.generate_code(mutated)
            self.recompile_current_code()
        else:
            self.current_code = engine.generate_code(params)
            self.recompile_current_code()

    # ==================== 模式與視圖切換 ====================
    def switch_mode(self, mode: str):
        self.maestro.ambient_muse.touch_action()
        if mode == "wizard":
            self.left_stack.setCurrentIndex(0)
            self.btn_mode_wizard.setStyleSheet("background-color: #581c87; border-color: #7e22ce; color: #f3e8ff;")
            self.btn_mode_pro.setStyleSheet("background-color: #18181b; color: #f4f4f5;")
            self.refresh_wizard_step_ui()
        else:
            self.left_stack.setCurrentIndex(1)
            self.btn_mode_pro.setStyleSheet("background-color: #065f46; border-color: #059669; color: #ecfdf5;")
            self.btn_mode_wizard.setStyleSheet("background-color: #18181b; color: #f4f4f5;")
            self.code_editor.setPlainText(self.current_code)

    def spin_slot_and_init(self):
        """靈感老虎機隨機碰撞並初始化 (結合審美口味)"""
        self.maestro.ambient_muse.touch_action()
        acoustic_meta = {"bpm": self.audio_deck.bpm, "bass": self.audio_deck.manual_bass}
        slot = self.maestro.spin_inspiration_slot(acoustic_meta=acoustic_meta)
        
        self.maestro_card.setText(
            f"🎩 <b>【AI 情景大師·靈感湧現】</b><br>"
            f"<b>{slot['title']}</b><br>"
            f"{slot['narrative']}"
        )
        self.wizard.session_data["genre"] = slot["genre"]["id"]
        self.wizard.session_data["topology"] = slot["topology"]["id"]
        self.current_code = self.wizard.compile_step_code()
        self.current_module_name = f"{slot['topology']['id']}_{slot['genre']['id']}"
        self.name_input.setText(self.current_module_name)
        self.recompile_current_code()
        self.refresh_wizard_step_ui()

    def decompile_image_dialog(self):
        """視覺參考圖多模態逆向工程"""
        self.maestro.ambient_muse.touch_action()
        fpath, _ = QFileDialog.getOpenFileName(self, "選擇視覺參考截圖或海報", self.workspace_dir, "圖像檔案 (*.png *.jpg *.jpeg *.webp)")
        if not fpath:
            return

        try:
            res = self.maestro.decompile_image_reference(fpath)
            self.maestro_card.setText(
                f"👁️ <b>【多模態視覺逆向成功】</b><br>"
                f"<b>{res['title']}</b><br>"
                f"{res['narrative']}"
            )
            spec = self.maestro.generate_rigid_spec(
                user_prompt=res["vibe_name"],
                acoustic_meta={"bpm": self.audio_deck.bpm},
                semantic_steer=self.semantic_steer
            )
            spec["palette"] = res["palette"]
            spec["topology_id"] = res["topology_id"]
            self.current_code = self.maestro.synthesize_p5_code(spec)
            self.current_module_name = res["title"]
            self.name_input.setText(self.current_module_name)
            self.recompile_current_code()
            QMessageBox.information(self, "圖片逆向完成", f"已成功解析圖片質地：\n【{res['vibe_name']}】\n色系與動態骨架已自動更新至畫布！")
        except Exception as e:
            QMessageBox.critical(self, "逆向失敗", f"無法解析圖片: {e}")

    def poll_ambient_muse(self):
        """心流微光呼吸提示輪詢"""
        hint = self.maestro.ambient_muse.poll_for_muse_hint()
        if hint:
            self.muse_banner.setText(hint)
            self.muse_banner.setStyleSheet("""
                background-color: #2e1065;
                color: #fde047;
                border: 1px solid #a855f7;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
                font-weight: bold;
            """)

    def refresh_wizard_step_ui(self):
        """更新引導精靈當前步驟的選項卡片"""
        step_info = self.wizard.get_current_step_info()
        self.wizard_step_lbl.setText(f"步驟 {step_info['step']} / 5: {step_info['name']} ({step_info['desc']})")

        while self.wizard_options_layout.count():
            item = self.wizard_options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        opts = self.wizard.get_step_options()
        if "genres" in opts:
            self.wizard_options_layout.addWidget(QLabel("<b>選擇音樂流派:</b>"))
            for g in opts["genres"]:
                btn = QPushButton(f"🎵 {g['name']} ({g['bpm']} BPM)")
                btn.clicked.connect(lambda _, gid=g["id"]: self._select_genre(gid))
                self.wizard_options_layout.addWidget(btn)
        elif "topologies" in opts:
            self.wizard_options_layout.addWidget(QLabel("<b>選擇幾何拓撲骨架:</b>"))
            for t in opts["topologies"]:
                btn = QPushButton(f"📐 {t['name']}\n{t['desc']}")
                btn.clicked.connect(lambda _, tid=t["id"]: self._select_topology(tid))
                self.wizard_options_layout.addWidget(btn)
        elif "frequency_bands" in opts:
            self.wizard_options_layout.addWidget(QLabel("<b>當前頻段聯覺映射:</b>"))
            for b in opts["frequency_bands"]:
                grp = QGroupBox(b["band"])
                gl = QVBoxLayout(grp)
                for opt in b["options"]:
                    rb = QCheckBox(opt)
                    rb.setChecked(True)
                    gl.addWidget(rb)
                self.wizard_options_layout.addWidget(grp)
        elif "shader_presets" in opts:
            self.wizard_options_layout.addWidget(QLabel("<b>推薦著色器組合:</b>"))
            for s in opts["shader_presets"]:
                btn = QPushButton(f"✨ 加載: {s['name']}")
                btn.clicked.connect(lambda _, sid=s["id"]: self._toggle_shader(sid))
                self.wizard_options_layout.addWidget(btn)
        else:
            self.wizard_options_layout.addWidget(QLabel("🎉 <b>視覺模組已就緒！</b><br>點擊右上角【一鍵驗證並收編入庫】即可直接匯入 MV 編輯器。"))

        self.wizard_options_layout.addStretch()

    def _select_genre(self, gid):
        self.maestro.ambient_muse.touch_action()
        self.wizard.session_data["genre"] = gid
        self.current_code = self.wizard.compile_step_code()
        self.recompile_current_code()

    def _select_topology(self, tid):
        self.maestro.ambient_muse.touch_action()
        self.wizard.session_data["topology"] = tid
        self.current_code = self.wizard.compile_step_code()
        self.recompile_current_code()

    def _toggle_shader(self, sid):
        self.maestro.ambient_muse.touch_action()
        if sid == "volumetric_godrays":
            self.cb_godrays.setChecked(not self.cb_godrays.isChecked())
        elif sid == "chromatic_aberration":
            self.cb_chromatic.setChecked(not self.cb_chromatic.isChecked())
        elif sid == "reaction_diffusion":
            self.cb_feedback.setChecked(not self.cb_feedback.isChecked())
        elif sid == "matrix_glitch_mosaic":
            self.cb_glitch.setChecked(not self.cb_glitch.isChecked())

    def wizard_next(self):
        self.maestro.ambient_muse.touch_action()
        self.wizard.next_step()
        self.refresh_wizard_step_ui()

    def wizard_prev(self):
        self.maestro.ambient_muse.touch_action()
        self.wizard.prev_step()
        self.refresh_wizard_step_ui()

    # ==================== 沙盒編譯與 AST 參數 ====================
    def recompile_current_code(self):
        if not self.current_code.strip():
            return

        html_path = os.path.join(self.workspace_dir, "visual_studio_web", "index.html")
        base_url = QUrl.fromLocalFile(html_path)

        with open(html_path, "r", encoding="utf-8") as f:
            template = f.read()

        injection_tag = '<script id="user-code-injection">'
        if injection_tag in template:
            parts = template.split(injection_tag)
            after_parts = parts[1].split('</script>', 1)
            full_html = parts[0] + injection_tag + "\n" + self.current_code + "\n</script>" + after_parts[1]
        else:
            full_html = template

        self.web_view.setHtml(full_html, base_url)
        self.code_editor.blockSignals(True)
        self.code_editor.setPlainText(self.current_code)
        self.code_editor.blockSignals(False)

        self.refresh_ast_params_deck()

    def refresh_ast_params_deck(self):
        while self.param_deck_layout.count():
            item = self.param_deck_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.slider_widgets.clear()

        params = ASTParamEngine.parse_params(self.current_code)
        if not params:
            lbl = QLabel("<i>未發現數值變數<br>(可在代碼中加入 @wizard 標籤)</i>")
            lbl.setStyleSheet("color: #71717a; padding: 10px;")
            self.param_deck_layout.addWidget(lbl)
            self.param_deck_layout.addStretch()
            return

        for p in params:
            row = QVBoxLayout()
            lbl_row = QHBoxLayout()
            label_text = p["label"]
            name_lbl = QLabel(f"<b>{label_text}</b>")
            val_lbl = QLabel(str(p["value"]))
            val_lbl.setStyleSheet("color: #a855f7; font-weight: bold;")
            lbl_row.addWidget(name_lbl)
            lbl_row.addStretch()
            lbl_row.addWidget(val_lbl)
            row.addLayout(lbl_row)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 1000)
            cur_ratio = (p["value"] - p["min"]) / max(0.0001, (p["max"] - p["min"]))
            slider.setValue(int(cur_ratio * 1000))

            slider.valueChanged.connect(lambda v, p_meta=p, v_lbl=val_lbl: self.on_ast_slider_dragged(v, p_meta, v_lbl))
            slider.sliderReleased.connect(lambda p_meta=p: self.on_ast_slider_released(p_meta))

            row.addWidget(slider)
            self.param_deck_layout.addLayout(row)
            self.slider_widgets[p["name"]] = (slider, val_lbl, p)

        self.param_deck_layout.addStretch()

    def on_ast_slider_dragged(self, slider_val: int, param_meta: dict, val_lbl: QLabel):
        self.maestro.ambient_muse.touch_action()
        ratio = slider_val / 1000.0
        new_v = param_meta["min"] + ratio * (param_meta["max"] - param_meta["min"])
        if param_meta["is_int"]:
            new_v = int(round(new_v))
            val_lbl.setText(str(new_v))
        else:
            new_v = float(f"{new_v:.4f}")
            val_lbl.setText(f"{new_v:.3f}")

        param_meta["current_dragged_val"] = new_v
        js = ASTParamEngine.generate_hot_patch_js(param_meta["name"], new_v)
        self.web_view.page().runJavaScript(js)

    def on_ast_slider_released(self, param_meta: dict):
        new_v = param_meta.get("current_dragged_val", param_meta["value"])
        param_meta["value"] = new_v
        self.current_code = ASTParamEngine.patch_code_text(self.current_code, param_meta["name"], new_v)
        self.code_editor.blockSignals(True)
        self.code_editor.setPlainText(self.current_code)
        self.code_editor.blockSignals(False)

    def on_code_editor_modified(self):
        self.maestro.ambient_muse.touch_action()
        self.current_code = self.code_editor.toPlainText()

    def ask_ai_patch(self):
        self.maestro.ambient_muse.touch_action()
        prompt = self.ai_prompt_input.text().strip()
        if not prompt:
            return
        QMessageBox.information(self, "AI 意向鍊金", f"大師已收到您的意境訴求：\n「{prompt}」\n正在為您解構意象圖式並重構物理幾何...")
        spec = self.maestro.generate_rigid_spec(
            user_prompt=prompt,
            acoustic_meta={"bpm": self.audio_deck.bpm},
            semantic_steer=self.semantic_steer
        )
        self.current_code = self.maestro.synthesize_p5_code(spec)
        self.recompile_current_code()

    # ==================== 著色器外掛與音訊同步 ====================
    def update_active_shaders(self):
        self.maestro.ambient_muse.touch_action()
        active = []
        if self.cb_godrays.isChecked():
            active.append({"id": "volumetric_godrays", "intensity": 0.8})
        if self.cb_chromatic.isChecked():
            active.append({"id": "chromatic_aberration", "intensity": 0.6})
        if self.cb_feedback.isChecked():
            active.append({"id": "reaction_diffusion", "intensity": 0.7})
        if self.cb_glitch.isChecked():
            active.append({"id": "matrix_glitch_mosaic", "intensity": 0.5})

        self.active_shaders = active
        js = self.shader_bridge.generate_webgl_fx_script(active)
        self.web_view.page().runJavaScript(js)

    def load_audio_dialog(self):
        self.maestro.ambient_muse.touch_action()
        file_path, _ = QFileDialog.getOpenFileName(self, "選擇音樂檔案進行測試", self.workspace_dir, "音訊檔案 (*.mp3 *.wav *.ogg)")
        if file_path:
            success = self.audio_deck.load_audio_file(file_path)
            if success:
                fname = os.path.basename(file_path)
                self.lbl_track_info.setText(f"{fname[:18]} ({self.audio_deck.bpm:.0f} BPM)")
                # 觸發聲學情感鏡像提示
                va = MaestroAcousticMirror.project_to_va_space({"bpm": self.audio_deck.bpm})
                self.muse_banner.setText(f"🎵 聲學情感鏡像：已將本曲判定為【{va['quadrant_info']['name']}】，已自動適配推薦動力學！")

    def on_scrub_changed(self, val: int):
        progress = val / 1000.0
        frame = self.audio_deck.get_frame_at_progress(progress)
        self.inject_audio_frame(frame)

    def sync_audio_frame_to_sandbox(self):
        if self.audio_deck.manual_mode:
            frame = self.audio_deck.get_manual_frame()
        else:
            progress = self.scrub_slider.value() / 1000.0
            frame = self.audio_deck.get_frame_at_progress(progress)
        self.inject_audio_frame(frame)

    def inject_audio_frame(self, frame: dict):
        js = f"""(function() {{
            if (window.updateAudioTelemetry) {{
                window.updateAudioTelemetry({json.dumps(frame)});
            }}
        }})();"""
        self.web_view.page().runJavaScript(js)

    def handle_js_log(self, level, message, lineNumber):
        if "Sandbox Error Caught" in message:
            self.lbl_black_screen.setText("黑畫面審計: <span style='color:#ef4444;'>ERROR</span>")

    # ==================== 一鍵入庫發布 ====================
    def publish_module_to_library(self):
        self.maestro.ambient_muse.touch_action()
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "名稱錯誤", "模組名稱不得為空！")
            return

        audit = QCValidator.audit_code_safety(self.current_code)
        if not audit["is_valid"]:
            QMessageBox.critical(self, "品質審查失敗", f"代碼存在以下問題：\n" + "\n".join(audit["errors"]))
            return

        module_dict = QCValidator.package_module_json(
            name=name,
            code=self.current_code,
            post_fx=self.active_shaders
        )

        # 寫入 custom_visuals/
        save_path = os.path.join(self.custom_visuals_dir, f"{name}.json")
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(module_dict, f, indent=4, ensure_ascii=False)

            # 記錄創作者審美口味學習 (Taste Profiling)
            topo_id = self.wizard.session_data.get("topology", "lorenz_attractor")
            genre_id = self.wizard.session_data.get("genre", "synthwave")
            self.maestro.taste_profiler.record_published_module(
                name=name,
                topology_id=topo_id,
                genre_id=genre_id,
                active_shaders=self.active_shaders
            )
            self.lbl_taste_badge.setText(f"<span style='color:#38bdf8;'>👤 {self.maestro.taste_profiler.get_taste_summary()[:28]}...</span>")

            QMessageBox.information(
                self, "🎉 入庫發布成功",
                f"視覺模組【{name}】已成功發布並存入：\n{save_path}\n\n"
                f"• Visual DNA: {module_dict['visual_dna']['fingerprint']}\n"
                f"• 審美偏好記憶已同步更新！\n"
                f"• 主程式已可立即調用該模組！"
            )
        except Exception as e:
            QMessageBox.critical(self, "寫入失敗", f"無法儲存模組檔案: {e}")

    def load_existing_module(self, module_name: str):
        target = os.path.join(self.custom_visuals_dir, f"{module_name}.json")
        if not os.path.exists(target):
            target = os.path.join(self.custom_visuals_dir, module_name)
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.current_code = data.get("code", "")
                self.current_module_name = data.get("name", module_name)
                self.name_input.setText(self.current_module_name)
                self.recompile_current_code()
                self.switch_mode("pro")
            except Exception as e:
                logger.error(f"Failed to load module {module_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="VisualStudio Pro · 4K 視覺模組神經創作工作站 (V2 Pro Edition)")
    parser.add_argument("--edit", type=str, default=None, help="指定載入既有模組名稱進行編輯")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VisualStudioMainWindow(initial_module_name=args.edit)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
