import os
import sys
import re
import json
import base64
import random
import logging
import datetime
import subprocess
from io import BytesIO
import numpy as np
from PIL import Image, ImageDraw

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSlider, QCheckBox, QFileDialog, QMessageBox, QDialog,
    QScrollArea, QFrame, QListView, QSizePolicy, QTextEdit, QSplitter,
    QGroupBox, QProgressDialog
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot, QThread
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap, QTextCursor

from pixel_ai_engine import PixelAIEngine

class PixelAIParamWorker(QThread):
    params_ready = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, prompt: str, engine: PixelAIEngine, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.engine = engine

    def run(self):
        try:
            params = self.engine.decode_prompt_to_params(self.prompt)
            self.params_ready.emit(params)
        except Exception as e:
            self.failed.emit(str(e))

class PixelAIPaletteWorker(QThread):
    palette_ready = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, genre: str, mood: str, engine: PixelAIEngine, parent=None):
        super().__init__(parent)
        self.genre = genre
        self.mood = mood
        self.engine = engine

    def run(self):
        try:
            pal = self.engine.generate_harmonic_palette(self.genre, self.mood)
            self.palette_ready.emit(pal)
        except Exception as e:
            self.failed.emit(str(e))

# ─────────────────────────────────────────────────────────────────────────────
# 1. 專屬詳細日誌系統配置 (Dedicated Pixel Generator Logger)
# ─────────────────────────────────────────────────────────────────────────────
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(WORKSPACE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
PIXEL_LOG_FILE = os.path.join(LOG_DIR, "pixel_generator.log")

def setup_pixel_logger():
    logger = logging.getLogger("PixelGenerator")
    logger.setLevel(logging.DEBUG)
    
    # 避免重複添加 Handler
    if not logger.handlers:
        file_handler = logging.FileHandler(PIXEL_LOG_FILE, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "[%(asctime)s] [PixelGen-%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger

pixel_logger = setup_pixel_logger()
pixel_logger.info("=======================================================")
pixel_logger.info("👾 [PixelModuleGenerator] Session Started")
pixel_logger.info(f"📁 Workspace: {WORKSPACE_DIR}")
pixel_logger.info(f"📄 Log File: {PIXEL_LOG_FILE}")
pixel_logger.info(f"🖥️ Python: {sys.version.split()[0]} | Platform: {sys.platform}")
pixel_logger.info("=======================================================")


# ─────────────────────────────────────────────────────────────────────────────
# 2. QWebEngine 診斷頁面 (攔截所有 JS Console / Error / WebGL 遙測)
# ─────────────────────────────────────────────────────────────────────────────
class PixelDiagnosticPage(QWebEnginePage):
    """自訂 WebEngine 頁面，即時捕獲瀏覽器內部的所有 console 訊息、例外與 WebGL 資訊"""
    log_received = pyqtSignal(str, str, int, str)  # level, msg, line, source

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        lvl_name = "INFO"
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            lvl_name = "WARN"
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            lvl_name = "ERROR"

        # 輸出至日誌檔案
        log_entry = f"[JS-{lvl_name}] (Line {line_number} in {os.path.basename(source_id or 'inline')}): {message}"
        if lvl_name == "ERROR":
            pixel_logger.error(log_entry)
        elif lvl_name == "WARN":
            pixel_logger.warning(log_entry)
        else:
            pixel_logger.debug(log_entry)

        # 發送 Signal 供 UI 日誌視窗即時顯示
        self.log_received.emit(lvl_name, message, line_number, str(source_id or "inline"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. 像素模組即時互動測試視窗 (Live Inspector Modal)
# ─────────────────────────────────────────────────────────────────────────────
class PixelModuleTestDialog(QDialog):
    """像素模組即時互動測試視窗 (Live Inspector Modal) 具備詳細遙測與即時日誌控制台"""
    def __init__(self, config_data, image_paths, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.config_data = config_data
        self.image_paths = image_paths
        self.current_img_idx = 0
        self.log_entries_count = 0

        pixel_logger.info(f"[PixelInspector] Initializing Inspector Dialog with {len(image_paths)} images")
        pixel_logger.debug(f"[PixelInspector] Initial Config: {json.dumps(config_data, ensure_ascii=False)}")

        self.setWindowTitle("👾 像素視覺模組即時測試與調校 (Live Inspector with Diagnostics)")
        self.resize(1320, 840)
        self.setStyleSheet("""
            QDialog {
                background-color: #09090b;
                border: 1px solid #27272a;
                border-radius: 10px;
            }
            QLabel {
                color: #e4e4e7;
                font-family: 'Outfit', 'Inter', -apple-system, sans-serif;
            }
            QLineEdit, QComboBox {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #18181b;
                color: #f4f4f5;
                selection-background-color: #a855f7;
                selection-color: #ffffff;
                border: 1px solid #27272a;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #27272a;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #a855f7;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #f4f4f5;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #27272a;
                border-color: #3f3f46;
            }
            QTextEdit {
                background-color: #0d0d11;
                color: #a1a1aa;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 11px;
                border: 1px solid #27272a;
                border-radius: 6px;
            }
        """)

        # 主垂直佈局
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # 頂部核心工作區 Splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_splitter.setHandleWidth(4)

        # ── 左側：16:9 WebGL 測試畫布 ──
        left_widget = QWidget(self)
        left_box = QVBoxLayout(left_widget)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(8)

        sandbox_title_row = QHBoxLayout()
        sandbox_title = QLabel("🌐 60FPS 即時音畫像素著色畫布 (16:9 WebGL)", left_widget)
        sandbox_title.setStyleSheet("font-weight: bold; color: #10b981; font-size: 13px;")
        sandbox_title_row.addWidget(sandbox_title)
        
        self.lbl_fps_telemetry = QLabel("⚡ 遙測狀態: 啟動中...", left_widget)
        self.lbl_fps_telemetry.setStyleSheet("color: #38bdf8; font-size: 11px;")
        sandbox_title_row.addStretch()
        sandbox_title_row.addWidget(self.lbl_fps_telemetry)
        left_box.addLayout(sandbox_title_row)

        self.web_view = QWebEngineView(left_widget)
        self.diagnostic_page = PixelDiagnosticPage(self.web_view)
        self.diagnostic_page.log_received.connect(self.append_live_log)
        self.web_view.setPage(self.diagnostic_page)

        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        
        self.web_view.setStyleSheet("border: 1px solid #27272a; border-radius: 8px; background: #000;")
        left_box.addWidget(self.web_view, stretch=1)

        # 畫布下方控制列
        img_switch_box = QHBoxLayout()
        self.btn_prev_img = QPushButton("◀ 上一張照片", left_widget)
        self.btn_prev_img.clicked.connect(self.prev_image)
        self.lbl_img_info = QLabel(f"影像: {1 if self.image_paths else 0} / {len(self.image_paths)}", left_widget)
        self.lbl_img_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_next_img = QPushButton("下一張照片 ▶", left_widget)
        self.btn_next_img.clicked.connect(self.next_image)
        
        img_switch_box.addWidget(self.btn_prev_img)
        img_switch_box.addWidget(self.lbl_img_info, stretch=1)
        img_switch_box.addWidget(self.btn_next_img)
        left_box.addLayout(img_switch_box)

        main_splitter.addWidget(left_widget)

        # ── 右側：即時參數 HUD 與 Metadata ──
        right_scroll = QScrollArea(self)
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(5, 0, 5, 0)
        # ── 一鍵風格預設按鈕列 (Quick Style Presets) 與突變骰子 ──
        preset_header = QHBoxLayout()
        preset_title = QLabel("⚡ 一鍵風格預設 (Quick Style Presets)", right_content)
        preset_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        preset_header.addWidget(preset_title)
        preset_header.addStretch()

        self.btn_mutate = QPushButton("🎲 隨機突變 (Mutate)", right_content)
        self.btn_mutate.setStyleSheet("""
            QPushButton {
                background-color: #ec4899;
                color: white;
                font-size: 11px;
                padding: 4px 8px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f43f5e;
            }
        """)
        self.btn_mutate.clicked.connect(self.mutate_randomly)
        preset_header.addWidget(self.btn_mutate)
        right_layout.addLayout(preset_header)

        preset_grid_1 = QHBoxLayout()
        preset_grid_1.setSpacing(6)
        preset_grid_2 = QHBoxLayout()
        preset_grid_2.setSpacing(6)

        presets = [
            ("🕹️ GameBoy", 12, 1, 1, True, 10, 100),
            ("💜 Cyberpunk", 10, 2, 0, True, 60, 150),
            ("🌊 Vaporwave", 14, 3, 5, True, 40, 100),
            ("📟 Matrix", 10, 8, 7, True, 20, 120),
            ("🏎️ Outrun", 12, 7, 8, True, 50, 140),
            ("👾 Arcade", 8, 6, 4, True, 30, 110),
            ("📰 Halftone", 12, 4, 15, False, 0, 100),
            ("💎 Voronoi", 16, 10, 0, True, 40, 140),
            ("🧊 3D Voxel", 14, 11, 8, True, 30, 130),
            ("🦠 Life Game", 12, 13, 12, True, 70, 160)
        ]

        for i, (p_name, g_val, m_val, pal_val, crt_val, chr_val, gain_val) in enumerate(presets):
            btn = QPushButton(p_name, right_content)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e1e24;
                    color: #e4e4e7;
                    font-size: 11px;
                    padding: 6px 4px;
                    border: 1px solid #3f3f46;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #7c3aed;
                    color: #fff;
                    border-color: #a855f7;
                }
            """)
            btn.clicked.connect(lambda checked, g=g_val, m=m_val, p=pal_val, c=crt_val, ch=chr_val, gn=gain_val: self.apply_preset(g, m, p, c, ch, gn))
            if i < 5:
                preset_grid_1.addWidget(btn)
            else:
                preset_grid_2.addWidget(btn)

        right_layout.addLayout(preset_grid_1)
        right_layout.addLayout(preset_grid_2)

        # ── AI 自然語言即時調參 ──
        ai_modal_box = QHBoxLayout()
        self.modal_prompt_input = QLineEdit(right_content)
        self.modal_prompt_input.setPlaceholderText("💬 AI 風格指令 (例: 90s GameBoy、賽博故障、極致黑白)...")
        self.modal_prompt_input.setStyleSheet("QLineEdit { background-color: #18181b; border: 1px solid #3f3f46; color: #f4f4f5; padding: 4px 8px; border-radius: 4px; font-size: 11px; }")
        self.modal_prompt_input.returnPressed.connect(self.run_ai_tuning)

        self.btn_modal_ai = QPushButton("🪄 AI調參", right_content)
        self.btn_modal_ai.setStyleSheet("QPushButton { background-color: #7c3aed; color: white; font-weight: bold; border-radius: 4px; padding: 4px 8px; font-size: 11px; } QPushButton:hover { background-color: #6d28d9; }")
        self.btn_modal_ai.clicked.connect(self.run_ai_tuning)

        self.btn_modal_palette = QPushButton("🎨 AI調色盤", right_content)
        self.btn_modal_palette.setStyleSheet("QPushButton { background-color: #065f46; color: #a7f3d0; font-weight: bold; border-radius: 4px; padding: 4px 8px; font-size: 11px; } QPushButton:hover { background-color: #047857; }")
        self.btn_modal_palette.clicked.connect(self.run_ai_palette)

        ai_modal_box.addWidget(self.modal_prompt_input, stretch=1)
        ai_modal_box.addWidget(self.btn_modal_ai)
        ai_modal_box.addWidget(self.btn_modal_palette)
        right_layout.addLayout(ai_modal_box)

        # 分隔線
        sep0 = QFrame(right_content)
        sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setStyleSheet("color: #27272a; margin-top: 6px;")
        right_layout.addWidget(sep0)

        # HUD 標題
        hud_title = QLabel("🎛️ 即時參數調校 (Live HUD)", right_content)
        hud_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #c084fc;")
        right_layout.addWidget(hud_title)

        # 顆粒大小
        self.grid_slider, self.lbl_grid = self._add_slider(right_layout, "像素網格 (Grid Size)", 2, 64, config_data.get("grid_size", 12), "px")
        self.grid_slider.valueChanged.connect(self.update_shader_params)

        # 抖色與樣式模式 (擴充至 15 種風格模式)
        right_layout.addWidget(QLabel("著色與抖色模式 (15 種前衛風格):", right_content))
        self.mode_select = QComboBox(right_content)
        self.mode_select.setView(QListView())
        self.mode_select.addItems([
            "0: 區塊方塊像素 (Block Pixel)",
            "1: Bayer 4×4 網點抖色 (Bayer 4x4)",
            "2: Bayer 8×8 矩陣平滑抖色 (Bayer 8x8)",
            "3: Blue Noise 藍噪聲隨機顆粒 (Blue Noise)",
            "4: Halftone 印刷半色調波點 (Halftone Dot)",
            "5: Crosshatch 漫畫交叉素描排線 (Crosshatch)",
            "6: CRT Phosphor Subpixel (RGB 垂直子像素)",
            "7: Diamond 45° 菱形斜交抖色 (Diamond Dither)",
            "8: ASCII 字符密度矩陣 (ASCII / Matrix Glyph)",
            "9: Glitch Slicing 故障切片撕裂 (Glitch Tear)",
            "10: 💎 Voronoi 水晶多邊形碎裂 (Voronoi Crystal)",
            "11: 🧊 3D 體積浮雕像素 (3D Voxel Prism)",
            "12: 🎨 Amiga 500 HAM6 流體油畫 (HAM6 Fluid)",
            "13: 🦠 Cellular Life 生命遊戲繁衍 (Cellular Life)",
            "14: 🔥 Thermal FLIR 熱成像紅外線 (Thermal FLIR)"
        ])
        self.mode_select.setCurrentIndex(config_data.get("style_mode_idx", 2))
        self.mode_select.currentIndexChanged.connect(self.update_shader_params)
        right_layout.addWidget(self.mode_select)

        # 色彩調色盤 (擴充至 21 種配色 + K-Means 萃取按鈕)
        pal_header = QHBoxLayout()
        pal_header.addWidget(QLabel("色彩調色盤 (21 款主題色盤):", right_content))
        pal_header.addStretch()
        self.btn_extract_pal = QPushButton("🎨 萃取照片主色", right_content)
        self.btn_extract_pal.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-size: 10px;
                padding: 3px 6px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #38bdf8;
            }
        """)
        self.btn_extract_pal.clicked.connect(self.extract_palette_from_current_image)
        pal_header.addWidget(self.btn_extract_pal)
        right_layout.addLayout(pal_header)

        self.palette_select = QComboBox(right_content)
        self.palette_select.setView(QListView())
        self.palette_select.addItems([
            "0: 💜 Cyberpunk Neon (賽博霓虹)",
            "1: 🕹️ Game Boy Classic 1989 (初版綠灰四階)",
            "2: 🎮 Game Boy Pocket (黑白灰階四階)",
            "3: 📺 Commodore 64 (C64 復古色系)",
            "4: 👾 PICO-8 幻想主機 (16-bit 經典調)",
            "5: 🌊 Vaporwave Pastel (蒸汽波粉彩)",
            "6: 🌃 Tokyo Night Neo-Tokyo (東京暗夜藍紫金)",
            "7: 📟 Matrix Digital Rain (駭客任務數位綠)",
            "8: 🏎️ Synthwave Outrun 1984 (落日公路紫橙)",
            "9: 🖥️ Apple II Amber Terminal (琥珀金終端)",
            "10: 🧊 Nord Arctic Frost (北歐極地冰原)",
            "11: 🩸 Dracula Gothic (德古拉歌德黑紅紫)",
            "12: ☣️ Acid Techno Neon (迷幻酸性高飽和)",
            "13: 📜 Sepia Vintage Film (老照片復古褐斑)",
            "14: 🔥 Thermal Heatmap (熱成像紅外線)",
            "15: ⬛ Monochrome 1-bit Manga (黑白漫畫純二值)",
            "16: 🌈 Original Quantized (原圖自適應階調量化)",
            "17: 🎨 K-Means 當前照片專屬萃取色 (Photo K-Means)",
            "18: 🌅 Sunset Outrun Gold (落日金橙)",
            "19: 🌌 Solarized Deep Space (深空藍紫)",
            "20: 📼 Amiga Copper Rainbow (阿米加彩虹條帶)"
        ])
        self.palette_select.setCurrentIndex(config_data.get("palette_idx", 0))
        self.palette_select.currentIndexChanged.connect(self.update_shader_params)
        right_layout.addWidget(self.palette_select)

        # 後製效果
        self.crt_cb = QCheckBox("CRT 掃描線與暗角 (Scanlines & Vignette)", right_content)
        self.crt_cb.setChecked(config_data.get("crt", True))
        self.crt_cb.toggled.connect(self.update_shader_params)
        right_layout.addWidget(self.crt_cb)

        self.chromatic_slider, self.lbl_chromatic = self._add_slider(right_layout, "RGB 色差位移 (Chromatic)", 0, 100, int(config_data.get("chromatic", 0.4) * 100), "%")
        self.chromatic_slider.valueChanged.connect(self.update_shader_params)

        # 音畫反應敏感度
        self.audio_gain_slider, self.lbl_gain = self._add_slider(right_layout, "音畫響應增益 (Audio Gain)", 10, 300, 100, "%")
        self.audio_gain_slider.valueChanged.connect(self.update_shader_params)

        # 分隔線
        sep = QFrame(right_content)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #27272a;")
        right_layout.addWidget(sep)

        # 模組 Metadata 登記
        meta_title = QLabel("📝 模組元數據 (Metadata)", right_content)
        meta_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        right_layout.addWidget(meta_title)

        right_layout.addWidget(QLabel("模組名稱 (英數底線):", right_content))
        self.name_input = QLineEdit(right_content)
        self.name_input.setText(config_data.get("default_name", f"pixel_synth_{int(datetime.datetime.now().timestamp())}"))
        right_layout.addWidget(self.name_input)

        right_layout.addWidget(QLabel("作者署名:", right_content))
        self.author_input = QLineEdit(right_content)
        self.author_input.setText(config_data.get("author", "unclerm"))
        right_layout.addWidget(self.author_input)

        right_layout.addWidget(QLabel("分類標籤 (逗號分隔):", right_content))
        self.tags_input = QLineEdit(right_content)
        self.tags_input.setText("pixel, shader, audio-reactive, cyberpunk, bayer-dither")
        right_layout.addWidget(self.tags_input)

        right_layout.addStretch()

        # 儲存按鈕
        self.btn_save_module = QPushButton("💾 確認儲存並收編至模組庫", right_content)
        self.btn_save_module.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                font-size: 13px;
                padding: 12px;
                border: none;
            }
            QPushButton:hover {
                background-color: #10b981;
            }
        """)
        self.btn_save_module.clicked.connect(self.save_and_integrate_module)
        right_layout.addWidget(self.btn_save_module)

        right_scroll.setWidget(right_content)
        main_splitter.addWidget(right_scroll)
        main_splitter.setStretchFactor(0, 6)
        main_splitter.setStretchFactor(1, 4)
        root_layout.addWidget(main_splitter, stretch=1)

        # ── 底部：實時診斷日誌控制台 (Live Diagnostic Console) ──
        log_box = QVBoxLayout()
        log_header = QHBoxLayout()
        self.lbl_log_title = QLabel("📋 實時運行與 WebGL 診斷日誌 (Live Diagnostic Console)", self)
        self.lbl_log_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #a1a1aa;")
        log_header.addWidget(self.lbl_log_title)
        log_header.addStretch()

        self.btn_copy_log = QPushButton("📋 複製日誌", self)
        self.btn_copy_log.clicked.connect(self.copy_log_to_clipboard)
        self.btn_clear_log = QPushButton("🧹 清空視窗", self)
        self.btn_clear_log.clicked.connect(self.clear_log_window)
        self.btn_open_file = QPushButton("📂 開啟完整日誌檔", self)
        self.btn_open_file.clicked.connect(self.open_log_file_externally)

        log_header.addWidget(self.btn_copy_log)
        log_header.addWidget(self.btn_clear_log)
        log_header.addWidget(self.btn_open_file)
        log_box.addLayout(log_header)

        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(120)
        log_box.addWidget(self.log_view)
        root_layout.addLayout(log_box)

        # 節奏模擬器
        self.beat_timer = QTimer(self)
        self.beat_timer.timeout.connect(self.simulate_audio_beat)
        self.beat_timer.start(450)

        # 萃取的當前色調
        self.current_extracted_colors = [
            [0.05, 0.05, 0.15],
            [0.92, 0.05, 0.55],
            [0.05, 0.92, 0.85],
            [0.98, 0.95, 0.98]
        ]

        # 初次載入 WebGL
        pixel_logger.info("[PixelInspector] Triggering initial reload_canvas()")
        self.reload_canvas()

    def mutate_randomly(self):
        """🎲 智慧隨機突變一組高美感參數組合"""
        grids = [6, 8, 10, 12, 14, 16, 20, 24]
        g = random.choice(grids)
        m = random.randint(0, 14)
        p = random.randint(0, 20)
        c = random.choice([True, True, False])
        ch = random.randint(15, 80)
        gn = random.randint(80, 200)
        self.apply_preset(g, m, p, c, ch, gn)
        pixel_logger.info(f"[PixelInspector] Mutated: Grid={g}, Mode={m}, Pal={p}, CRT={c}")

    def extract_palette_from_current_image(self):
        """從目前照片自動萃取 4 色代表色"""
        if not self.image_paths or not (0 <= self.current_img_idx < len(self.image_paths)):
            return
        fpath = self.image_paths[self.current_img_idx]
        try:
            with Image.open(fpath) as im:
                im = im.convert("RGB")
                im_small = im.resize((64, 64))
                extracted = [[0.1, 0.1, 0.2], [0.8, 0.2, 0.5], [0.2, 0.8, 0.9], [0.95, 0.95, 0.98]]
                try:
                    q = im_small.quantize(colors=4, method=Image.Quantize.MEDIANCUT)
                    pal = q.getpalette() if q else None
                    if pal and len(pal) >= 12:
                        extracted = []
                        for i in range(4):
                            r = pal[i*3] / 255.0
                            g = pal[i*3+1] / 255.0
                            b = pal[i*3+2] / 255.0
                            extracted.append([round(r, 3), round(g, 3), round(b, 3)])
                except Exception:
                    pass
                self.current_extracted_colors = extracted
                self.palette_select.setCurrentIndex(17) # Switch to Photo K-Means
                self.update_shader_params()
                pixel_logger.info(f"[PixelInspector] Extracted 4 Colors from Photo: {extracted}")
                QMessageBox.information(self, "色調萃取成功", f"已成功從當前照片萃取 4 色調色盤！\nColors: {extracted}")
        except Exception as e:
            pixel_logger.error(f"[PixelInspector] Failed to extract palette: {e}")

    def run_ai_tuning(self):
        prompt = self.modal_prompt_input.text().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "請輸入風格描述指令！")
            return
        
        self.btn_modal_ai.setEnabled(False)
        self.btn_modal_ai.setText("⏳ AI解析中...")
        
        engine = PixelAIEngine()
        self.ai_worker = PixelAIParamWorker(prompt, engine, self)
        self.ai_worker.params_ready.connect(self._on_ai_params_ready)
        self.ai_worker.failed.connect(self._on_ai_failed)
        self.ai_worker.finished.connect(lambda: (self.btn_modal_ai.setEnabled(True), self.btn_modal_ai.setText("🪄 AI調參")))
        self.ai_worker.start()

    def _on_ai_params_ready(self, params: dict):
        self.grid_slider.setValue(params.get("grid_size", 12))
        self.mode_select.setCurrentIndex(params.get("style_mode", 2))
        self.palette_select.setCurrentIndex(params.get("palette_id", 0))
        self.crt_cb.setChecked(params.get("crt", True))
        self.chromatic_slider.setValue(int(params.get("chromatic", 0.4) * 100))
        self.audio_gain_slider.setValue(int(params.get("audio_gain", 1.0) * 100))
        if "suggested_name" in params:
            self.name_input.setText(params["suggested_name"])
        self.update_shader_params()
        self.append_live_log("INFO", f"✨ AI 智慧調參成功: Grid={params.get('grid_size')}, Mode={params.get('style_mode')}, Pal={params.get('palette_id')}", 0, "AI")

    def run_ai_palette(self):
        prompt = self.modal_prompt_input.text().strip() or "Cyberpunk Neon"
        self.btn_modal_palette.setEnabled(False)
        self.btn_modal_palette.setText("⏳ 色彩演算...")
        
        engine = PixelAIEngine()
        self.palette_worker = PixelAIPaletteWorker(prompt, "Dynamic Harmonics", engine, self)
        self.palette_worker.palette_ready.connect(self._on_ai_palette_ready)
        self.palette_worker.failed.connect(self._on_ai_failed)
        self.palette_worker.finished.connect(lambda: (self.btn_modal_palette.setEnabled(True), self.btn_modal_palette.setText("🎨 AI調色盤")))
        self.palette_worker.start()

    def _on_ai_palette_ready(self, pal_data: dict):
        col1 = pal_data.get("color1", [0.05, 0.02, 0.12])
        col2 = pal_data.get("color2", [0.92, 0.05, 0.55])
        col3 = pal_data.get("color3", [0.05, 0.92, 0.85])
        col4 = pal_data.get("color4", [0.98, 0.95, 0.98])
        self.current_extracted_colors = [col1, col2, col3, col4]
        self.palette_select.setCurrentIndex(17) # Custom Slot
        self.update_shader_params()
        self.append_live_log("INFO", f"🎨 AI 生成 4 色原創調色盤: {pal_data.get('name')}", 0, "AI")

    def _on_ai_failed(self, err_msg: str):
        self.append_live_log("ERROR", f"AI 解析失敗: {err_msg}", 0, "AI")

    def apply_preset(self, grid_val, mode_idx, pal_idx, crt_on, chr_val, gain_val):
        """一鍵套用風格預設"""
        self.grid_slider.setValue(grid_val)
        self.mode_select.setCurrentIndex(mode_idx)
        self.palette_select.setCurrentIndex(pal_idx)
        self.crt_cb.setChecked(crt_on)
        self.chromatic_slider.setValue(chr_val)
        self.audio_gain_slider.setValue(gain_val)
        self.update_shader_params()
        pixel_logger.info(f"[PixelInspector] Applied Preset: Grid={grid_val}, Mode={mode_idx}, Pal={pal_idx}, CRT={crt_on}")

    def _add_slider(self, layout, title, min_v, max_v, init_v, unit=""):
        row = QHBoxLayout()
        lbl_title = QLabel(title, self)
        lbl_val = QLabel(f"{init_v}{unit}", self)
        lbl_val.setStyleSheet("color: #c084fc; font-weight: bold;")
        row.addWidget(lbl_title)
        row.addStretch()
        row.addWidget(lbl_val)
        layout.addLayout(row)

        slider = QSlider(Qt.Orientation.Horizontal, self)
        slider.setRange(min_v, max_v)
        slider.setValue(init_v)
        slider.valueChanged.connect(lambda v: lbl_val.setText(f"{v}{unit}"))
        layout.addWidget(slider)
        return slider, lbl_val

    def append_live_log(self, level: str, message: str, line: int, source: str):
        color_map = {
            "INFO": "#38bdf8",
            "WARN": "#fbbf24",
            "ERROR": "#f87171"
        }
        c = color_map.get(level, "#e4e4e7")
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"<span style='color: #71717a;'>[{timestamp}]</span> <span style='color: {c}; font-weight: bold;'>[{level}]</span> {message}"
        self.log_view.append(formatted)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_entries_count += 1

        if "[FPS_TELEMETRY]" in message:
            self.lbl_fps_telemetry.setText(f"⚡ {message.replace('[FPS_TELEMETRY]', '').strip()}")

    def copy_log_to_clipboard(self):
        text = self.log_view.toPlainText()
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        pixel_logger.info(f"[PixelInspector] Copied {len(text)} chars of live log to clipboard")
        QMessageBox.information(self, "成功", "即時日誌已複製到剪貼簿！")

    def clear_log_window(self):
        self.log_view.clear()
        pixel_logger.info("[PixelInspector] Live log window cleared")

    def open_log_file_externally(self):
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", PIXEL_LOG_FILE])
            elif sys.platform == "win32":
                os.startfile(PIXEL_LOG_FILE)
            else:
                subprocess.run(["xdg-open", PIXEL_LOG_FILE])
            pixel_logger.info(f"[PixelInspector] Opened log file: {PIXEL_LOG_FILE}")
        except Exception as e:
            pixel_logger.error(f"[PixelInspector] Failed to open log file: {e}")
            QMessageBox.warning(self, "警告", f"無法開啟日誌檔案: {e}")

    def prev_image(self):
        if not self.image_paths: return
        self.current_img_idx = (self.current_img_idx - 1) % len(self.image_paths)
        self.lbl_img_info.setText(f"影像: {self.current_img_idx + 1} / {len(self.image_paths)}")
        pixel_logger.info(f"[PixelInspector] Navigated to Prev Image #{self.current_img_idx + 1}: {self.image_paths[self.current_img_idx]}")
        self.reload_canvas()

    def next_image(self):
        if not self.image_paths: return
        self.current_img_idx = (self.current_img_idx + 1) % len(self.image_paths)
        self.lbl_img_info.setText(f"影像: {self.current_img_idx + 1} / {len(self.image_paths)}")
        pixel_logger.info(f"[PixelInspector] Navigated to Next Image #{self.current_img_idx + 1}: {self.image_paths[self.current_img_idx]}")
        self.reload_canvas()

    def get_current_image_base64(self) -> str:
        """安全載入當前照片並轉為 Base64 Data URI，避免 file:// 權限或路徑特殊符號問題"""
        if self.image_paths and 0 <= self.current_img_idx < len(self.image_paths):
            fpath = self.image_paths[self.current_img_idx]
            try:
                if os.path.exists(fpath):
                    with Image.open(fpath) as pil_img:
                        pil_img = pil_img.convert("RGB")
                        # 限制預覽縮放至最大 1920x1080 提升 WebGL 上傳速度
                        pil_img.thumbnail((1920, 1080), Image.Resampling.BICUBIC)
                        buffered = BytesIO()
                        pil_img.save(buffered, format="JPEG", quality=90)
                        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                        pixel_logger.debug(f"[PixelInspector] Image loaded & converted to Base64 (Size: {pil_img.size}) from {fpath}")
                        return f"data:image/jpeg;base64,{img_b64}"
            except Exception as e:
                pixel_logger.error(f"[PixelInspector] Failed to load image {fpath}: {e}")

        # 若無照片或載入失敗，產生程序化高對比 Cyber 漸層測試圖
        pixel_logger.warning("[PixelInspector] Using procedural fallback test pattern")
        test_img = Image.new("RGB", (640, 360), (20, 20, 35))
        draw = ImageDraw.Draw(test_img)
        for x in range(0, 640, 40):
            for y in range(0, 360, 40):
                if (x // 40 + y // 40) % 2 == 0:
                    draw.rectangle([x, y, x + 39, y + 39], fill=(255, 0, 128))
                else:
                    draw.rectangle([x, y, x + 39, y + 39], fill=(0, 240, 255))
        draw.text((220, 170), "PIXEL SYNTH TEST PATTERN", fill=(255, 255, 255))
        
        buffered = BytesIO()
        test_img.save(buffered, format="PNG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_b64}"

    def generate_shader_code(self):
        img_data_uri = self.get_current_image_base64()
        grid_size = self.grid_slider.value()
        mode_idx = self.mode_select.currentIndex()
        palette_idx = self.palette_select.currentIndex()
        crt_enabled = "true" if self.crt_cb.isChecked() else "false"
        chromatic_val = self.chromatic_slider.value() / 100.0
        audio_gain = self.audio_gain_slider.value() / 100.0

        kc = self.current_extracted_colors

        pixel_logger.info(f"[PixelInspector] Generating Shader Code (Grid={grid_size}, Mode={mode_idx}, Palette={palette_idx}, CRT={crt_enabled}, Chromatic={chromatic_val})")

        js_code = f"""
        let img;
        let shaderProgram;
        let gridVal = {grid_size};
        let ditherMode = {mode_idx};
        let paletteMode = {palette_idx};
        let crtOn = {crt_enabled};
        let chromaticAmt = {chromatic_val};
        let audioGain = {audio_gain};
        let lastFpsLog = 0;
        let kcolor1 = [{kc[0][0]}, {kc[0][1]}, {kc[0][2]}];
        let kcolor2 = [{kc[1][0]}, {kc[1][1]}, {kc[1][2]}];
        let kcolor3 = [{kc[2][0]}, {kc[2][1]}, {kc[2][2]}];
        let kcolor4 = [{kc[3][0]}, {kc[3][1]}, {kc[3][2]}];

        // 全螢幕安全頂點著色器
        const vertSrc = `
          precision highp float;
          attribute vec3 aPosition;
          attribute vec2 aTexCoord;
          uniform mat4 uModelViewMatrix;
          uniform mat4 uProjectionMatrix;
          varying vec2 vTexCoord;
          void main(void) {{
            vec4 positionVec4 = vec4(aPosition, 1.0);
            gl_Position = uProjectionMatrix * uModelViewMatrix * positionVec4;
            vTexCoord = aTexCoord;
          }}
        `;

        const fragSrc = `
          precision mediump float;
          varying vec2 vTexCoord;
          uniform sampler2D u_tex;
          uniform vec2 u_resolution;
          uniform float u_grid;
          uniform int u_dither_mode;
          uniform int u_palette;
          uniform bool u_crt;
          uniform float u_chromatic;
          uniform float u_time;
          uniform float u_bass;
          uniform float u_mid;
          uniform float u_high;
          uniform float u_gain;
          uniform vec3 u_kcol1;
          uniform vec3 u_kcol2;
          uniform vec3 u_kcol3;
          uniform vec3 u_kcol4;

          float bayer4(vec2 p) {{
            vec2 p4 = floor(mod(p, 4.0));
            mat4 b = mat4(
                 0.0,  8.0,  2.0, 10.0,
                12.0,  4.0, 14.0,  6.0,
                 3.0, 11.0,  1.0,  9.0,
                15.0,  7.0, 13.0,  5.0
            );
            int x = int(p4.x);
            int y = int(p4.y);
            float v = 0.0;
            if (x == 0) {{ if (y == 0) v = b[0][0]; else if (y == 1) v = b[0][1]; else if (y == 2) v = b[0][2]; else v = b[0][3]; }}
            else if (x == 1) {{ if (y == 0) v = b[1][0]; else if (y == 1) v = b[1][1]; else if (y == 2) v = b[1][2]; else v = b[1][3]; }}
            else if (x == 2) {{ if (y == 0) v = b[2][0]; else if (y == 1) v = b[2][1]; else if (y == 2) v = b[2][2]; else v = b[2][3]; }}
            else {{ if (y == 0) v = b[3][0]; else if (y == 1) v = b[3][1]; else if (y == 2) v = b[3][2]; else v = b[3][3]; }}
            return v / 16.0;
          }}

          float bayer8(vec2 p) {{
            vec2 p2 = floor(mod(p, 2.0));
            float b4 = bayer4(floor(p / 2.0));
            float offset = (p2.x < 1.0 && p2.y < 1.0) ? 0.0 : ((p2.x >= 1.0 && p2.y < 1.0) ? 2.0 : ((p2.x < 1.0 && p2.y >= 1.0) ? 3.0 : 1.0));
            return (b4 * 4.0 + offset / 4.0) / 4.0;
          }}

          float blueNoise(vec2 uv) {{
            return fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
          }}

          vec2 voronoiHash(vec2 p) {{
            p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
            return fract(sin(p) * 43758.5453);
          }}

          float voronoiDist(vec2 x) {{
            vec2 n = floor(x);
            vec2 f = fract(x);
            float md = 8.0;
            for (int j = -1; j <= 1; j++) {{
              for (int i = -1; i <= 1; i++) {{
                vec2 g = vec2(float(i), float(j));
                vec2 o = voronoiHash(n + g);
                vec2 r = g + o - f;
                float d = dot(r, r);
                if (d < md) md = d;
              }}
            }}
            return sqrt(md);
          }}

          vec3 applyPalette(vec3 color, float lum) {{
            // 0: Cyberpunk Neon
            if (u_palette == 0) {{
              if (lum < 0.22) return vec3(0.04, 0.02, 0.12);
              else if (lum < 0.48) return vec3(0.92, 0.05, 0.55);
              else if (lum < 0.78) return vec3(0.05, 0.92, 0.85);
              return vec3(0.98, 0.95, 0.98);
            }}
            // 1: Game Boy Classic 1989
            else if (u_palette == 1) {{
              if (lum < 0.25) return vec3(0.06, 0.22, 0.06);
              else if (lum < 0.50) return vec3(0.19, 0.38, 0.19);
              else if (lum < 0.75) return vec3(0.55, 0.67, 0.06);
              return vec3(0.61, 0.73, 0.06);
            }}
            // 2: Game Boy Pocket
            else if (u_palette == 2) {{
              if (lum < 0.25) return vec3(0.09, 0.09, 0.09);
              else if (lum < 0.50) return vec3(0.35, 0.35, 0.35);
              else if (lum < 0.75) return vec3(0.63, 0.63, 0.63);
              return vec3(0.97, 0.97, 0.97);
            }}
            // 3: Commodore 64 Retro
            else if (u_palette == 3) {{
              if (lum < 0.20) return vec3(0.0, 0.0, 0.0);
              else if (lum < 0.40) return vec3(0.42, 0.24, 0.58);
              else if (lum < 0.65) return vec3(0.44, 0.71, 0.28);
              else if (lum < 0.85) return vec3(0.44, 0.64, 0.70);
              return vec3(0.92, 0.93, 0.95);
            }}
            // 4: PICO-8 16-color
            else if (u_palette == 4) {{
              if (lum < 0.15) return vec3(0.10, 0.09, 0.15);
              else if (lum < 0.30) return vec3(0.48, 0.15, 0.21);
              else if (lum < 0.45) return vec3(0.0, 0.53, 0.32);
              else if (lum < 0.60) return vec3(1.0, 0.64, 0.0);
              else if (lum < 0.75) return vec3(0.18, 0.67, 0.95);
              else if (lum < 0.90) return vec3(1.0, 0.47, 0.66);
              return vec3(1.0, 0.95, 0.91);
            }}
            // 5: Vaporwave Pastel
            else if (u_palette == 5) {{
              if (lum < 0.25) return vec3(0.18, 0.05, 0.28);
              else if (lum < 0.50) return vec3(0.44, 0.16, 0.52);
              else if (lum < 0.75) return vec3(0.96, 0.45, 0.68);
              return vec3(0.98, 0.88, 0.71);
            }}
            // 6: Tokyo Night Neo-Tokyo
            else if (u_palette == 6) {{
              if (lum < 0.20) return vec3(0.08, 0.09, 0.17);
              else if (lum < 0.45) return vec3(0.96, 0.26, 0.45);
              else if (lum < 0.70) return vec3(0.48, 0.38, 0.98);
              else if (lum < 0.88) return vec3(0.24, 0.82, 0.76);
              return vec3(0.98, 0.84, 0.46);
            }}
            // 7: Matrix Digital Rain
            else if (u_palette == 7) {{
              if (lum < 0.25) return vec3(0.0, 0.04, 0.0);
              else if (lum < 0.55) return vec3(0.0, 0.45, 0.12);
              else if (lum < 0.85) return vec3(0.15, 0.95, 0.35);
              return vec3(0.85, 1.0, 0.88);
            }}
            // 8: Synthwave Outrun 1984
            else if (u_palette == 8) {{
              if (lum < 0.22) return vec3(0.14, 0.02, 0.22);
              else if (lum < 0.50) return vec3(0.72, 0.08, 0.48);
              else if (lum < 0.75) return vec3(0.98, 0.42, 0.18);
              return vec3(1.0, 0.88, 0.25);
            }}
            // 9: Apple II Amber Terminal
            else if (u_palette == 9) {{
              if (lum < 0.25) return vec3(0.05, 0.02, 0.0);
              else if (lum < 0.55) return vec3(0.60, 0.25, 0.0);
              else if (lum < 0.85) return vec3(0.95, 0.55, 0.05);
              return vec3(1.0, 0.85, 0.45);
            }}
            // 10: Nord Arctic Frost
            else if (u_palette == 10) {{
              if (lum < 0.22) return vec3(0.18, 0.20, 0.25);
              else if (lum < 0.50) return vec3(0.37, 0.51, 0.67);
              else if (lum < 0.75) return vec3(0.53, 0.75, 0.82);
              return vec3(0.93, 0.95, 0.96);
            }}
            // 11: Dracula Gothic
            else if (u_palette == 11) {{
              if (lum < 0.20) return vec3(0.16, 0.16, 0.21);
              else if (lum < 0.45) return vec3(0.74, 0.46, 0.98);
              else if (lum < 0.70) return vec3(1.0, 0.48, 0.64);
              else if (lum < 0.88) return vec3(0.31, 0.98, 0.48);
              return vec3(0.97, 0.97, 0.95);
            }}
            // 12: Acid Techno Neon
            else if (u_palette == 12) {{
              if (lum < 0.22) return vec3(0.05, 0.0, 0.10);
              else if (lum < 0.48) return vec3(0.85, 0.0, 0.95);
              else if (lum < 0.75) return vec3(0.0, 0.98, 0.45);
              return vec3(0.98, 0.98, 0.05);
            }}
            // 13: Sepia Vintage Film
            else if (u_palette == 13) {{
              if (lum < 0.22) return vec3(0.14, 0.09, 0.06);
              else if (lum < 0.50) return vec3(0.44, 0.30, 0.21);
              else if (lum < 0.75) return vec3(0.76, 0.60, 0.45);
              return vec3(0.95, 0.89, 0.79);
            }}
            // 14: Thermal Heatmap
            else if (u_palette == 14) {{
              if (lum < 0.18) return vec3(0.05, 0.05, 0.45);
              else if (lum < 0.42) return vec3(0.55, 0.05, 0.55);
              else if (lum < 0.68) return vec3(0.95, 0.25, 0.05);
              else if (lum < 0.88) return vec3(0.98, 0.88, 0.05);
              return vec3(0.98, 0.98, 0.98);
            }}
            // 15: Monochrome 1-bit Manga
            else if (u_palette == 15) {{
              return vec3(step(0.5, lum));
            }}
            // 16: Original Quantized
            else if (u_palette == 16) {{
              return floor(color * 4.0) / 4.0;
            }}
            // 17: K-Means Photo Extracted
            else if (u_palette == 17) {{
              if (lum < 0.25) return u_kcol1;
              else if (lum < 0.50) return u_kcol2;
              else if (lum < 0.75) return u_kcol3;
              return u_kcol4;
            }}
            // 18: Sunset Outrun Gold
            else if (u_palette == 18) {{
              if (lum < 0.25) return vec3(0.15, 0.02, 0.10);
              else if (lum < 0.50) return vec3(0.85, 0.20, 0.15);
              else if (lum < 0.75) return vec3(0.98, 0.70, 0.10);
              return vec3(1.0, 0.95, 0.60);
            }}
            // 19: Solarized Deep Space
            else if (u_palette == 19) {{
              if (lum < 0.25) return vec3(0.01, 0.12, 0.15);
              else if (lum < 0.50) return vec3(0.15, 0.55, 0.82);
              else if (lum < 0.75) return vec3(0.51, 0.58, 0.59);
              return vec3(0.99, 0.96, 0.89);
            }}
            // 20: Amiga Copper Rainbow
            else if (u_palette == 20) {{
              float h = fract(lum + u_time * 0.1);
              return vec3(sin(h * 6.28) * 0.5 + 0.5, sin((h + 0.33) * 6.28) * 0.5 + 0.5, sin((h + 0.66) * 6.28) * 0.5 + 0.5);
            }}
            return floor(color * 4.0) / 4.0;
          }}

          void main() {{
            vec2 uv = vTexCoord;
            uv.y = 1.0 - uv.y;

            // 低頻 (Bass) 調變網格尺寸與脈衝
            float activeGrid = max(2.0, u_grid + (u_bass * u_gain) * 16.0);
            vec2 gridCount = u_resolution / activeGrid;
            vec2 cellIndex = floor(uv * gridCount);
            vec2 gridUV = cellIndex / gridCount;
            vec2 localCoord = fract(uv * gridCount);

            // 10: 💎 Voronoi 水晶多邊形碎裂
            if (u_dither_mode == 10) {{
              float vD = voronoiDist(uv * (gridCount * 0.5) + u_time * 0.2);
              gridUV = floor(uv * gridCount + (vD - 0.5) * 0.1 * (u_bass * u_gain + 0.2)) / gridCount;
            }}

            // 9: 故障切片撕裂 (Glitch Mode 9)
            if (u_dither_mode == 9) {{
              float glitchLine = step(0.91, fract(sin(floor(uv.y * 35.0) + u_time * 4.0) * 43758.5453));
              gridUV.x += glitchLine * ((u_high * u_gain) * 0.05 + 0.02) * sin(u_time * 15.0);
            }}

            // 高頻與瞬態觸發 RGB 色差位移 (Chromatic Aberration)
            float shift = (u_chromatic * 0.02) + ((u_high * u_gain) * 0.035);
            vec3 col;
            col.r = texture2D(u_tex, gridUV + vec2(shift, 0.0)).r;
            col.g = texture2D(u_tex, gridUV).g;
            col.b = texture2D(u_tex, gridUV - vec2(shift, 0.0)).b;

            float lum = dot(col, vec3(0.299, 0.587, 0.114));

            // 著色抖色模式評估 (15 種風格模式)
            // 1: Bayer 4x4
            if (u_dither_mode == 1) {{
              float ditherThreshold = bayer4(gl_FragCoord.xy);
              lum = lum + (ditherThreshold - 0.5) * (0.35 + (u_mid * u_gain) * 0.45);
            }}
            // 2: Bayer 8x8
            else if (u_dither_mode == 2) {{
              float ditherThreshold = bayer8(gl_FragCoord.xy);
              lum = lum + (ditherThreshold - 0.5) * (0.32 + (u_mid * u_gain) * 0.45);
            }}
            // 3: Blue Noise 隨機顆粒
            else if (u_dither_mode == 3) {{
              float noise = blueNoise(cellIndex + fract(u_time * 0.05));
              lum = lum + (noise - 0.5) * (0.38 + (u_mid * u_gain) * 0.5);
            }}
            // 4: Halftone 印刷半色調波點
            else if (u_dither_mode == 4) {{
              float dist = length(localCoord - 0.5);
              float dotRadius = (1.0 - lum) * 0.65;
              lum = step(dotRadius, dist);
            }}
            // 5: Crosshatch 漫畫素描排線
            else if (u_dither_mode == 5) {{
              float line1 = step(0.5, mod(gl_FragCoord.x + gl_FragCoord.y, 6.0) / 6.0);
              float line2 = step(0.5, mod(gl_FragCoord.x - gl_FragCoord.y, 6.0) / 6.0);
              if (lum < 0.25) lum = (line1 * line2);
              else if (lum < 0.50) lum = line1;
              else if (lum < 0.75) lum = 0.5 + 0.5 * line2;
              else lum = 1.0;
            }}
            // 6: CRT Phosphor Subpixel (垂直 RGB 子像素)
            else if (u_dither_mode == 6) {{
              float subpixel = mod(gl_FragCoord.x, 3.0);
              if (subpixel < 1.0) col.gb *= 0.25;
              else if (subpixel < 2.0) col.rb *= 0.25;
              else col.rg *= 0.25;
            }}
            // 7: Diamond 45° 菱形抖色
            else if (u_dither_mode == 7) {{
              vec2 dp = mod(gl_FragCoord.xy, 4.0);
              float diamond = (abs(dp.x - 2.0) + abs(dp.y - 2.0)) / 4.0;
              lum = lum + (diamond - 0.5) * 0.45;
            }}
            // 8: ASCII 字符密度矩陣
            else if (u_dither_mode == 8) {{
              float pattern = mod(floor(localCoord.x * 3.0) + floor(localCoord.y * 3.0) * 3.0, 9.0) / 9.0;
              lum = step(pattern, lum);
            }}
            // 11: 🧊 3D 體積浮雕像素 (3D Voxel Prism)
            else if (u_dither_mode == 11) {{
              float edgeDist = min(min(localCoord.x, 1.0 - localCoord.x), min(localCoord.y, 1.0 - localCoord.y));
              float shade = smoothstep(0.0, 0.12, edgeDist) * 0.6 + 0.4;
              if (localCoord.x + localCoord.y < 0.35) shade *= 1.35;
              if (localCoord.x + localCoord.y > 1.65) shade *= 0.65;
              col *= shade;
            }}
            // 12: 🎨 Amiga 500 HAM6 流體油畫
            else if (u_dither_mode == 12) {{
              float hamQuant = floor(lum * 12.0) / 12.0;
              lum = mix(lum, hamQuant, 0.7);
            }}
            // 13: 🦠 Cellular Life 生命遊戲繁衍
            else if (u_dither_mode == 13) {{
              float life = fract(sin(dot(cellIndex, vec2(12.9898, 78.233)) + floor(u_time * 4.0)) * 43758.5453);
              if (life > 0.7) lum = min(1.0, lum + (u_bass * u_gain) * 0.35);
              else if (life < 0.25) lum = max(0.0, lum - 0.25);
            }}
            // 14: 🔥 Thermal FLIR
            else if (u_dither_mode == 14) {{
              lum = pow(lum, 1.3);
            }}

            vec3 finalColor = applyPalette(col, lum);

            // CRT 掃描線與暗角 (Vignette)
            if (u_crt) {{
              float scanline = sin(uv.y * u_resolution.y * 1.6) * 0.12;
              finalColor -= scanline;

              float vig = uv.x * uv.y * (1.0 - uv.x) * (1.0 - uv.y);
              vig = clamp(pow(16.0 * vig, 0.22), 0.0, 1.0);
              finalColor *= vig;
            }}

            gl_FragColor = vec4(finalColor, 1.0);
          }}
        `;

        function preload() {{
          console.log("[PRELOAD] Loading Base64 Image Texture...");
          img = loadImage('{img_data_uri}', 
            () => console.log("[PRELOAD_OK] Image loaded successfully (Width=" + img.width + ", Height=" + img.height + ")"),
            (err) => console.error("[PRELOAD_ERR] Failed to load image texture: " + err)
          );
        }}

        function setup() {{
          console.log("[SETUP] Initializing WebGL Canvas: " + windowWidth + "x" + windowHeight);
          createCanvas(windowWidth, windowHeight, WEBGL);
          noStroke();
          
          try {{
            shaderProgram = createShader(vertSrc, fragSrc);
            console.log("[SHADER_OK] WebGL Shader Program Compiled and Linked Successfully");
          }} catch(e) {{
            console.error("[SHADER_ERR] Shader compilation exception: " + e.message);
          }}
        }}

        function draw() {{
          if (!shaderProgram || !img) return;

          shader(shaderProgram);
          shaderProgram.setUniform('u_tex', img);
          shaderProgram.setUniform('u_resolution', [width, height]);
          shaderProgram.setUniform('u_grid', gridVal);
          shaderProgram.setUniform('u_dither_mode', ditherMode);
          shaderProgram.setUniform('u_palette', paletteMode);
          shaderProgram.setUniform('u_crt', crtOn);
          shaderProgram.setUniform('u_chromatic', chromaticAmt);
          shaderProgram.setUniform('u_gain', audioGain);
          shaderProgram.setUniform('u_time', millis() / 1000.0);
          shaderProgram.setUniform('u_bass', window.audioLow || 0.0);
          shaderProgram.setUniform('u_mid', window.audioMid || 0.0);
          shaderProgram.setUniform('u_high', window.audioHigh || 0.0);
          shaderProgram.setUniform('u_kcol1', kcolor1);
          shaderProgram.setUniform('u_kcol2', kcolor2);
          shaderProgram.setUniform('u_kcol3', kcolor3);
          shaderProgram.setUniform('u_kcol4', kcolor4);

          // 覆蓋全螢幕 16:9 WebGL 視口
          rect(-width / 2, -height / 2, width, height);

          // 每 2 秒輸出一次 FPS 遙測
          if (millis() - lastFpsLog > 2000) {{
            lastFpsLog = millis();
            console.log("[FPS_TELEMETRY] FPS: " + Math.round(frameRate()) + " | Grid: " + gridVal + "px | Res: " + width + "x" + height);
          }}
        }}

        function windowResized() {{
          resizeCanvas(windowWidth, windowHeight);
          console.log("[RESIZE] WebGL Canvas Resized: " + windowWidth + "x" + windowHeight);
        }}
        """
        return js_code

    def reload_canvas(self):
        js_code = self.generate_shader_code()
        
        # 建立具備完整錯誤攔截的專用沙盒 HTML
        html = f"""<!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #000; }}
            canvas {{ display: block !important; width: 100% !important; height: 100% !important; }}
          </style>
          <script>
            window.onerror = function(msg, url, line, col, error) {{
              console.error("[UNCAUGHT_ERR] " + msg + " at " + (url || "inline") + ":" + line);
              return false;
            }};
            window.addEventListener("unhandledrejection", function(event) {{
              console.error("[PROMISE_REJECT] " + (event.reason ? (event.reason.message || event.reason) : "unknown"));
            }});
          </script>
          <script src="https://cdn.jsdelivr.net/npm/p5@1.9.0/lib/p5.min.js"></script>
        </head>
        <body>
          <script>
            {js_code}
          </script>
        </body>
        </html>"""

        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        base_url = QUrl.fromLocalFile(os.path.join(workspace_dir, "dummy_pixel_preview.html"))
        pixel_logger.debug(f"[PixelInspector] Setting HTML to WebEngineView with Base URL: {base_url.toString()}")
        self.web_view.setHtml(html, base_url)

    def update_shader_params(self):
        grid_val = self.grid_slider.value()
        mode_idx = self.mode_select.currentIndex()
        palette_idx = self.palette_select.currentIndex()
        crt_on = "true" if self.crt_cb.isChecked() else "false"
        chromatic_val = self.chromatic_slider.value() / 100.0
        audio_gain = self.audio_gain_slider.value() / 100.0

        kc = self.current_extracted_colors
        update_js = f"""
        gridVal = {grid_val};
        ditherMode = {mode_idx};
        paletteMode = {palette_idx};
        crtOn = {crt_on};
        chromaticAmt = {chromatic_val};
        audioGain = {audio_gain};
        kcolor1 = [{kc[0][0]}, {kc[0][1]}, {kc[0][2]}];
        kcolor2 = [{kc[1][0]}, {kc[1][1]}, {kc[1][2]}];
        kcolor3 = [{kc[2][0]}, {kc[2][1]}, {kc[2][2]}];
        kcolor4 = [{kc[3][0]}, {kc[3][1]}, {kc[3][2]}];
        console.log("[PARAMS_SYNC] Grid=" + gridVal + ", Mode=" + ditherMode + ", Palette=" + paletteMode + ", CRT=" + crtOn + ", Chromatic=" + chromaticAmt);
        """
        self.web_view.page().runJavaScript(update_js)

    def simulate_audio_beat(self):
        js = """
        window.audioLow = Math.random() > 0.6 ? 0.85 : 0.15;
        window.audioMid = Math.random() * 0.65;
        window.audioHigh = Math.random() > 0.7 ? 0.9 : 0.1;
        """
        self.web_view.page().runJavaScript(js)

    def save_and_integrate_module(self):
        name = self.name_input.text().strip()
        author = self.author_input.text().strip() or "unclerm"
        tags_str = self.tags_input.text().strip()

        if not name:
            pixel_logger.warning("[PixelInspector] Attempted to save module with empty name")
            QMessageBox.critical(self, "錯誤", "模組名稱不得為空！")
            return

        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)

        full_code = self.generate_shader_code()

        module_payload = {
            "name": name,
            "author": author,
            "license": "CC BY-SA",
            "tags": tags,
            "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "frequency": 65,
            "storyboard_weight": 70,
            "post_fx_intensity": 60,
            "code": full_code,
            "custom_html": "",
            "custom_css": "",
            "inline_assets": {},
            "scaling_mode": "cover"
        }

        save_path = os.path.join(save_dir, f"{name}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(module_payload, f, indent=4, ensure_ascii=False)

        pixel_logger.info(f"[PixelInspector] Module JSON successfully written to: {save_path}")

        # 儲存縮圖供模組庫與離線渲染器網格列表使用
        thumb_dir = os.path.join(save_dir, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = os.path.join(thumb_dir, f"{name}.jpg")
        try:
            pixmap = self.web_view.grab()
            scaled = pixmap.scaled(800, 450, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            scaled.save(thumb_path, "JPEG", 85)
            pixel_logger.info(f"[PixelInspector] Thumbnail captured and saved to: {thumb_path}")
        except Exception as e:
            pixel_logger.error(f"[PixelInspector] Error saving thumbnail: {e}")

        # 刷新主視窗模組庫清單
        if self.parent_tab and self.parent_tab.parent_app:
            self.parent_tab.parent_app.cached_presets = None
            self.parent_tab.parent_app.refresh_presets_list()
            self.parent_tab.parent_app.log_to_console(f"🎉 像素視覺模組「{name}」已成功收編入庫！")

        QMessageBox.information(self, "收編成功", f"模組 {name} 已成功寫入視覺庫，可在 4K 離線渲染器中直接調用！")
        self.accept()

    def closeEvent(self, event):
        pixel_logger.info("[PixelInspector] Closing Inspector Dialog and stopping beat timer")
        self.beat_timer.stop()
        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# 4. 第 4 個獨立頁籤：👾 像素視覺模組生成器 主控制面板
# ─────────────────────────────────────────────────────────────────────────────
class PixelModuleGeneratorTab(QWidget):
    """第 4 個獨立頁籤：👾 像素視覺模組生成器"""
    def __init__(self, parent_app=None):
        super().__init__(parent_app)
        self.parent_app = parent_app

        pixel_logger.info("[PixelGeneratorTab] Initializing PixelModuleGeneratorTab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("👾 像素音畫視覺模組生成器 (Pixel Visual Synth Generator)", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        layout.addWidget(title)

        # ── 1. 來源照片資料夾選擇 ──
        folder_box = QHBoxLayout()
        self.folder_input = QLineEdit(self)
        self.folder_input.setPlaceholderText("請選擇或貼入照片來源資料夾路徑...")
        self.lbl_detected_count = QLabel("📷 已偵測: 0 張照片", self)
        self.lbl_detected_count.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: bold;")
        
        btn_browse_folder = QPushButton("選擇資料夾...", self)
        btn_browse_folder.clicked.connect(self.browse_image_folder)
        
        folder_box.addWidget(self.folder_input, stretch=3)
        folder_box.addWidget(self.lbl_detected_count, stretch=1)
        folder_box.addWidget(btn_browse_folder)
        layout.addLayout(folder_box)

        # ── 2. 測試音訊來源 ──
        audio_box = QHBoxLayout()
        self.audio_input = QLineEdit(self)
        self.audio_input.setPlaceholderText("選擇測試音訊檔案 (.mp3, .wav，選填)...")
        btn_browse_audio = QPushButton("瀏覽...", self)
        btn_browse_audio.clicked.connect(self.browse_audio_file)
        audio_box.addWidget(self.audio_input)
        audio_box.addWidget(btn_browse_audio)
        layout.addLayout(audio_box)

        # ── 3. 像素風格化初始設定 ──
        style_title = QLabel("🎨 像素風格與音畫機制預設", self)
        style_title.setStyleSheet("font-weight: bold; color: #a1a1aa; margin-top: 5px;")
        layout.addWidget(style_title)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("初始網格尺寸:", self))
        self.grid_combo = QComboBox(self)
        self.grid_combo.setView(QListView())
        self.grid_combo.addItems(["8px (細膩)", "12px (標準)", "16px (復古)", "24px (粗糙)", "32px (極限像素)"])
        self.grid_combo.setCurrentIndex(1)
        grid_row.addWidget(self.grid_combo)

        grid_row.addWidget(QLabel("著色抖色模式:", self))
        self.style_mode_combo = QComboBox(self)
        self.style_mode_combo.setView(QListView())
        self.style_mode_combo.addItems(["區塊降採樣", "Bayer 4x4 網點抖色", "Bayer 8x8 矩陣抖色", "Blue Noise 藍噪聲", "ASCII 字符矩陣", "幾何點陣"])
        self.style_mode_combo.setCurrentIndex(2)
        grid_row.addWidget(self.style_mode_combo)

        grid_row.addWidget(QLabel("預設調色盤:", self))
        self.palette_combo = QComboBox(self)
        self.palette_combo.setView(QListView())
        self.palette_combo.addItems(["Cyberpunk Neon", "Game Boy (4 Colors)", "C64 Retro", "Vaporwave Pastel", "Monochrome", "Original Quantized"])
        grid_row.addWidget(self.palette_combo)
        layout.addLayout(grid_row)

        # ── 4. 音畫調變機制勾選 ──
        mod_box = QHBoxLayout()
        self.cb_bass = QCheckBox("低頻 (Bass) 調變網格尺寸與震動", self)
        self.cb_bass.setChecked(True)
        self.cb_mid = QCheckBox("中頻 (Mid) 調變抖色臨界值與色相", self)
        self.cb_mid.setChecked(True)
        self.cb_high = QCheckBox("高頻/瞬態 (High) 觸發 RGB 色差 Glitch", self)
        self.cb_high.setChecked(True)
        mod_box.addWidget(self.cb_bass)
        mod_box.addWidget(self.cb_mid)
        mod_box.addWidget(self.cb_high)
        layout.addLayout(mod_box)

# ─────────────────────────────────────────────────────────────────────────────
# 3.5 向量化像素 Shader 縮圖渲染核心 (Pixel Shader Thumbnail Renderer)
# ─────────────────────────────────────────────────────────────────────────────
_PALETTES_THUMB = [
    [(0.04, 0.02, 0.12), (0.92, 0.05, 0.55), (0.05, 0.92, 0.85), (0.98, 0.95, 0.98)], # 0: Cyberpunk
    [(0.06, 0.22, 0.06), (0.19, 0.38, 0.19), (0.55, 0.67, 0.06), (0.61, 0.73, 0.06)], # 1: GameBoy
    [(0.09, 0.09, 0.09), (0.35, 0.35, 0.35), (0.63, 0.63, 0.63), (0.97, 0.97, 0.97)], # 2: GBPocket
    [(0.0, 0.0, 0.0), (0.42, 0.24, 0.58), (0.44, 0.71, 0.28), (0.44, 0.64, 0.70), (0.92, 0.93, 0.95)], # 3: C64
    [(0.10, 0.09, 0.15), (0.48, 0.15, 0.21), (0.0, 0.53, 0.32), (1.0, 0.64, 0.0), (0.18, 0.67, 0.95), (1.0, 0.47, 0.66), (1.0, 0.95, 0.91)], # 4: PICO-8
    [(0.18, 0.05, 0.28), (0.44, 0.16, 0.52), (0.96, 0.45, 0.68), (0.98, 0.88, 0.71)], # 5: Vaporwave
    [(0.08, 0.09, 0.17), (0.96, 0.26, 0.45), (0.48, 0.38, 0.98), (0.24, 0.82, 0.76), (0.98, 0.84, 0.46)], # 6: TokyoNight
    [(0.0, 0.04, 0.0), (0.0, 0.45, 0.12), (0.15, 0.95, 0.35), (0.85, 1.0, 0.88)], # 7: Matrix
    [(0.14, 0.02, 0.22), (0.72, 0.08, 0.48), (0.98, 0.42, 0.18), (1.0, 0.88, 0.25)], # 8: Outrun
    [(0.05, 0.02, 0.0), (0.60, 0.25, 0.0), (0.95, 0.55, 0.05), (1.0, 0.85, 0.45)], # 9: Apple II
    [(0.18, 0.20, 0.25), (0.37, 0.51, 0.67), (0.53, 0.75, 0.82), (0.93, 0.95, 0.96)], # 10: Nord
    [(0.16, 0.16, 0.21), (0.74, 0.46, 0.98), (1.0, 0.48, 0.64), (0.31, 0.98, 0.48), (0.97, 0.97, 0.95)], # 11: Dracula
    [(0.05, 0.0, 0.10), (0.85, 0.0, 0.95), (0.0, 0.98, 0.45), (0.98, 0.98, 0.05)], # 12: Acid
    [(0.14, 0.09, 0.06), (0.44, 0.30, 0.21), (0.76, 0.60, 0.45), (0.95, 0.89, 0.79)], # 13: Sepia
    [(0.05, 0.05, 0.45), (0.55, 0.05, 0.55), (0.95, 0.25, 0.05), (0.98, 0.88, 0.05), (0.98, 0.98, 0.98)], # 14: Thermal
    [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)], # 15: Manga
    None, # 16: Quantized
    None, # 17: K-Means
    [(0.15, 0.02, 0.10), (0.85, 0.20, 0.15), (0.98, 0.70, 0.10), (1.0, 0.95, 0.60)], # 18: Sunset
    [(0.01, 0.12, 0.15), (0.15, 0.55, 0.82), (0.51, 0.58, 0.59), (0.99, 0.96, 0.89)], # 19: Solarized
    None # 20: Copper
]

_BAYER_4_THUMB = np.array([
    [ 0.0,  8.0,  2.0, 10.0],
    [12.0,  4.0, 14.0,  6.0],
    [ 3.0, 11.0,  1.0,  9.0],
    [15.0,  7.0, 13.0,  5.0]
], dtype=np.float32) / 16.0

def _get_bayer8_thumb():
    b8 = np.zeros((8, 8), dtype=np.float32)
    for y in range(8):
        for x in range(8):
            b4 = _BAYER_4_THUMB[(y // 2) % 4, (x // 2) % 4]
            p2x, p2y = x % 2, y % 2
            offset = 0.0 if (p2x < 1 and p2y < 1) else (2.0 if (p2x >= 1 and p2y < 1) else (3.0 if (p2x < 1 and p2y >= 1) else 1.0))
            b8[y, x] = (b4 * 4.0 + offset / 4.0) / 4.0
    return b8

_BAYER_8_THUMB = _get_bayer8_thumb()

def render_pixel_shader_thumbnail(pil_img: Image.Image, grid_val=12, dither_mode=2, palette_mode=0, crt_on=True, chromatic_amt=0.4, kcolors=None, width=800, height=450):
    img_resized = pil_img.resize((width, height), Image.Resampling.BICUBIC)
    active_grid = max(2, int(grid_val))
    gx = max(1, width // active_grid)
    gy = max(1, height // active_grid)
    
    im_small = img_resized.resize((gx, gy), Image.Resampling.BOX)
    im_pixelated = im_small.resize((width, height), Image.Resampling.NEAREST)
    arr_pix = np.array(im_pixelated, dtype=np.float32) / 255.0

    if chromatic_amt > 0:
        shift = int(chromatic_amt * 4.0) + 1
        arr_shifted = np.copy(arr_pix)
        if 0 < shift < width:
            arr_shifted[:, shift:, 0] = arr_pix[:, :-shift, 0]
            arr_shifted[:, :-shift, 2] = arr_pix[:, shift:, 2]
        arr_pix = arr_shifted

    lum = arr_pix[:, :, 0] * 0.299 + arr_pix[:, :, 1] * 0.587 + arr_pix[:, :, 2] * 0.114
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    
    if dither_mode == 1:
        b4_tiled = np.tile(_BAYER_4_THUMB, (height // 4 + 1, width // 4 + 1))[:height, :width]
        lum = np.clip(lum + (b4_tiled - 0.5) * 0.4, 0.0, 1.0)
    elif dither_mode == 2:
        b8_tiled = np.tile(_BAYER_8_THUMB, (height // 8 + 1, width // 8 + 1))[:height, :width]
        lum = np.clip(lum + (b8_tiled - 0.5) * 0.38, 0.0, 1.0)
    elif dither_mode == 3:
        np.random.seed(42)
        noise = np.random.rand(height, width).astype(np.float32)
        lum = np.clip(lum + (noise - 0.5) * 0.45, 0.0, 1.0)
    elif dither_mode == 4:
        lx = (x_coords % active_grid) / float(active_grid) - 0.5
        ly = (y_coords % active_grid) / float(active_grid) - 0.5
        dist = np.sqrt(lx**2 + ly**2)
        dot_radius = (1.0 - lum) * 0.65
        lum = (dist > dot_radius).astype(np.float32)
    elif dither_mode == 5:
        line1 = ((x_coords + y_coords) % 6 < 3).astype(np.float32)
        line2 = ((x_coords - y_coords) % 6 < 3).astype(np.float32)
        lum = np.where(lum < 0.25, line1 * line2, np.where(lum < 0.5, line1, np.where(lum < 0.75, 0.5 + 0.5 * line2, 1.0)))
    elif dither_mode == 6:
        sub = x_coords % 3
        arr_pix[:, :, 1] = np.where(sub == 0, arr_pix[:, :, 1] * 0.25, arr_pix[:, :, 1])
        arr_pix[:, :, 2] = np.where(sub == 0, arr_pix[:, :, 2] * 0.25, arr_pix[:, :, 2])
        arr_pix[:, :, 0] = np.where(sub == 1, arr_pix[:, :, 0] * 0.25, arr_pix[:, :, 0])
        arr_pix[:, :, 2] = np.where(sub == 1, arr_pix[:, :, 2] * 0.25, arr_pix[:, :, 2])
        arr_pix[:, :, 0] = np.where(sub == 2, arr_pix[:, :, 0] * 0.25, arr_pix[:, :, 0])
        arr_pix[:, :, 1] = np.where(sub == 2, arr_pix[:, :, 1] * 0.25, arr_pix[:, :, 1])
    elif dither_mode == 7:
        dp = np.abs((x_coords % 4) - 2.0) + np.abs((y_coords % 4) - 2.0)
        diamond = dp / 4.0
        lum = np.clip(lum + (diamond - 0.5) * 0.45, 0.0, 1.0)
    elif dither_mode == 12:
        lum = np.floor(lum * 12.0) / 12.0
    elif dither_mode == 14:
        lum = np.power(lum, 1.3)

    out = np.zeros((height, width, 3), dtype=np.float32)
    pal = _PALETTES_THUMB[palette_mode] if palette_mode < len(_PALETTES_THUMB) else None
    
    if palette_mode == 16:
        out = np.floor(arr_pix * 4.0) / 4.0
    elif palette_mode == 17 and kcolors and len(kcolors) >= 4:
        kc = np.array(kcolors, dtype=np.float32)
        out = np.where(lum[:, :, None] < 0.25, kc[0],
              np.where(lum[:, :, None] < 0.50, kc[1],
              np.where(lum[:, :, None] < 0.75, kc[2], kc[3])))
    elif pal is not None:
        num_colors = len(pal)
        steps = np.linspace(0.0, 1.0, num_colors + 1)
        for i in range(num_colors):
            mask = (lum >= steps[i]) if i == num_colors - 1 else ((lum >= steps[i]) & (lum < steps[i+1]))
            col = np.array(pal[i], dtype=np.float32)
            out[mask] = col
    else:
        out = arr_pix

    if crt_on:
        uv_y = y_coords.astype(np.float32) / float(height)
        uv_x = x_coords.astype(np.float32) / float(width)
        scanline = np.sin(uv_y * height * 1.6) * 0.10
        out -= scanline[:, :, None]
        
        vig = uv_x * uv_y * (1.0 - uv_x) * (1.0 - uv_y)
        vig = np.clip(np.power(np.maximum(16.0 * vig, 0.0), 0.22), 0.0, 1.0)
        out *= vig[:, :, None]

    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out)

# ─────────────────────────────────────────────────────────────────────────────
# 4. 批次自動命名與生成工作執行緒 (Batch Auto-Naming & Export Worker)
# ─────────────────────────────────────────────────────────────────────────────
class BatchPixelExportWorker(QThread):
    progress_updated = pyqtSignal(int, int, str)  # current, total, name
    batch_finished = pyqtSignal(int, int, list)   # success_count, fail_count, created_names

    def __init__(self, image_paths, config_data, parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.config_data = config_data
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def _sanitize_name(self, name_str: str) -> str:
        clean = re.sub(r'[^a-zA-Z0-9_-]', '_', name_str)
        return clean.strip('_')[:40] or "pixel_module"

    def run(self):
        total = len(self.image_paths)
        success_count = 0
        fail_count = 0
        created_names = []

        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        thumb_dir = os.path.join(save_dir, "thumbnails")
        os.makedirs(save_dir, exist_ok=True)
        os.makedirs(thumb_dir, exist_ok=True)

        palette_tags = [
            "cyberpunk", "gameboy", "gbpocket", "c64", "pico8", "vaporwave",
            "tokyonight", "matrix", "outrun", "apple2", "nord", "dracula",
            "acid", "sepia", "thermal", "manga", "quantized", "kmeans",
            "sunset", "solarized", "copper"
        ]
        mode_tags = [
            "block", "bayer4", "bayer8", "bluenoise", "halftone", "crosshatch",
            "crt_subpixel", "diamond", "ascii", "glitch", "voronoi", "voxel3d",
            "ham6", "life_game", "thermal_flir"
        ]

        for idx, img_path in enumerate(self.image_paths):
            if self.is_cancelled:
                pixel_logger.warning("[BatchWorker] Batch export cancelled by user")
                break

            # 智慧風格打散模式：每張照片自動輪轉不同風格與調色盤
            if self.config_data.get("smart_diversity", True):
                mode_idx = idx % 15
                palette_idx = idx % 21
            else:
                mode_idx = self.config_data.get("style_mode_idx", 2)
                palette_idx = self.config_data.get("palette_idx", 0)

            pal_tag = palette_tags[min(palette_idx, len(palette_tags) - 1)]
            mod_tag = mode_tags[min(mode_idx, len(mode_tags) - 1)]

            base_stem = os.path.splitext(os.path.basename(img_path))[0]
            clean_stem = self._sanitize_name(base_stem)
            module_name = f"pixel_{clean_stem}_{mod_tag}_{pal_tag}"

            # 避免重複檔名
            counter = 1
            final_name = module_name
            while os.path.exists(os.path.join(save_dir, f"{final_name}.json")):
                final_name = f"{module_name}_{counter:02d}"
                counter += 1

            self.progress_updated.emit(idx + 1, total, final_name)

            try:
                # 1. 讀取並轉換 Base64 & 萃取色彩
                with Image.open(img_path) as pil_img:
                    pil_img = pil_img.convert("RGB")
                    
                    # 萃取 4 色代表色
                    kc = [[0.1, 0.1, 0.2], [0.8, 0.2, 0.5], [0.2, 0.8, 0.9], [0.95, 0.95, 0.98]]
                    try:
                        im_small = pil_img.resize((64, 64))
                        q = im_small.quantize(colors=4, method=Image.Quantize.MEDIANCUT)
                        pal = q.getpalette() if q else None
                        if pal and len(pal) >= 12:
                            kc = []
                            for k_i in range(4):
                                r = pal[k_i*3] / 255.0
                                g = pal[k_i*3+1] / 255.0
                                b = pal[k_i*3+2] / 255.0
                                kc.append([round(r, 3), round(g, 3), round(b, 3)])
                    except Exception:
                        pass

                    # 產生 800x450 像素 Shader 視覺效果縮圖 (非原始照片)
                    thumb_save_path = os.path.join(thumb_dir, f"{final_name}.jpg")
                    try:
                        thumb_img = render_pixel_shader_thumbnail(
                            pil_img,
                            grid_val=self.config_data.get("grid_size", 12),
                            dither_mode=mode_idx,
                            palette_mode=palette_idx,
                            crt_on=self.config_data.get("crt", True),
                            chromatic_amt=self.config_data.get("chromatic", 0.4),
                            kcolors=kc,
                            width=800,
                            height=450
                        )
                        thumb_img.save(thumb_save_path, "JPEG", quality=88)
                    except Exception as th_err:
                        pixel_logger.warning(f"[BatchWorker] Shader thumbnail fallback: {th_err}")
                        thumb_img = pil_img.copy()
                        thumb_img.thumbnail((800, 450), Image.Resampling.BICUBIC)
                        thumb_img.save(thumb_save_path, "JPEG", quality=85)

                    # 縮放主圖轉 Base64
                    pil_img.thumbnail((1920, 1080), Image.Resampling.BICUBIC)
                    buffered = BytesIO()
                    pil_img.save(buffered, format="JPEG", quality=90)
                    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    img_data_uri = f"data:image/jpeg;base64,{img_b64}"

                # 2. 建立專屬 Shader Code
                grid_size = self.config_data.get("grid_size", 12)
                crt_enabled = "true" if self.config_data.get("crt", True) else "false"
                chromatic_val = self.config_data.get("chromatic", 0.4)
                audio_gain = 1.0

                code = f"""
let img;
let shaderProgram;
let gridVal = {grid_size};
let ditherMode = {mode_idx};
let paletteMode = {palette_idx};
let crtOn = {crt_enabled};
let chromaticAmt = {chromatic_val};
let audioGain = {audio_gain};
let kcolor1 = [{kc[0][0]}, {kc[0][1]}, {kc[0][2]}];
let kcolor2 = [{kc[1][0]}, {kc[1][1]}, {kc[1][2]}];
let kcolor3 = [{kc[2][0]}, {kc[2][1]}, {kc[2][2]}];
let kcolor4 = [{kc[3][0]}, {kc[3][1]}, {kc[3][2]}];

const vertSrc = `
  precision highp float;
  attribute vec3 aPosition;
  attribute vec2 aTexCoord;
  uniform mat4 uModelViewMatrix;
  uniform mat4 uProjectionMatrix;
  varying vec2 vTexCoord;
  void main(void) {{
    vec4 positionVec4 = vec4(aPosition, 1.0);
    gl_Position = uProjectionMatrix * uModelViewMatrix * positionVec4;
    vTexCoord = aTexCoord;
  }}
`;

const fragSrc = `
  precision mediump float;
  varying vec2 vTexCoord;
  uniform sampler2D u_tex;
  uniform vec2 u_resolution;
  uniform float u_grid;
  uniform int u_dither_mode;
  uniform int u_palette;
  uniform bool u_crt;
  uniform float u_chromatic;
  uniform float u_time;
  uniform float u_bass;
  uniform float u_mid;
  uniform float u_high;
  uniform float u_gain;
  uniform vec3 u_kcol1;
  uniform vec3 u_kcol2;
  uniform vec3 u_kcol3;
  uniform vec3 u_kcol4;

  float bayer4(vec2 p) {{
    vec2 p4 = floor(mod(p, 4.0));
    mat4 b = mat4(
         0.0,  8.0,  2.0, 10.0,
        12.0,  4.0, 14.0,  6.0,
         3.0, 11.0,  1.0,  9.0,
        15.0,  7.0, 13.0,  5.0
    );
    int x = int(p4.x);
    int y = int(p4.y);
    float v = 0.0;
    if (x == 0) {{ if (y == 0) v = b[0][0]; else if (y == 1) v = b[0][1]; else if (y == 2) v = b[0][2]; else v = b[0][3]; }}
    else if (x == 1) {{ if (y == 0) v = b[1][0]; else if (y == 1) v = b[1][1]; else if (y == 2) v = b[1][2]; else v = b[1][3]; }}
    else if (x == 2) {{ if (y == 0) v = b[2][0]; else if (y == 1) v = b[2][1]; else if (y == 2) v = b[2][2]; else v = b[2][3]; }}
    else {{ if (y == 0) v = b[3][0]; else if (y == 1) v = b[3][1]; else if (y == 2) v = b[3][2]; else v = b[3][3]; }}
    return v / 16.0;
  }}

  float bayer8(vec2 p) {{
    vec2 p2 = floor(mod(p, 2.0));
    float b4 = bayer4(floor(p / 2.0));
    float offset = (p2.x < 1.0 && p2.y < 1.0) ? 0.0 : ((p2.x >= 1.0 && p2.y < 1.0) ? 2.0 : ((p2.x < 1.0 && p2.y >= 1.0) ? 3.0 : 1.0));
    return (b4 * 4.0 + offset / 4.0) / 4.0;
  }}

  float blueNoise(vec2 uv) {{
    return fract(sin(dot(uv, vec2(12.9898, 78.233))) * 43758.5453);
  }}

  vec2 voronoiHash(vec2 p) {{
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453);
  }}

  float voronoiDist(vec2 x) {{
    vec2 n = floor(x);
    vec2 f = fract(x);
    float md = 8.0;
    for (int j = -1; j <= 1; j++) {{
      for (int i = -1; i <= 1; i++) {{
        vec2 g = vec2(float(i), float(j));
        vec2 o = voronoiHash(n + g);
        vec2 r = g + o - f;
        float d = dot(r, r);
        if (d < md) md = d;
      }}
    }}
    return sqrt(md);
  }}

  vec3 applyPalette(vec3 color, float lum) {{
    if (u_palette == 0) {{
      if (lum < 0.22) return vec3(0.04, 0.02, 0.12);
      else if (lum < 0.48) return vec3(0.92, 0.05, 0.55);
      else if (lum < 0.78) return vec3(0.05, 0.92, 0.85);
      return vec3(0.98, 0.95, 0.98);
    }} else if (u_palette == 1) {{
      if (lum < 0.25) return vec3(0.06, 0.22, 0.06);
      else if (lum < 0.50) return vec3(0.19, 0.38, 0.19);
      else if (lum < 0.75) return vec3(0.55, 0.67, 0.06);
      return vec3(0.61, 0.73, 0.06);
    }} else if (u_palette == 2) {{
      if (lum < 0.25) return vec3(0.09, 0.09, 0.09);
      else if (lum < 0.50) return vec3(0.35, 0.35, 0.35);
      else if (lum < 0.75) return vec3(0.63, 0.63, 0.63);
      return vec3(0.97, 0.97, 0.97);
    }} else if (u_palette == 3) {{
      if (lum < 0.20) return vec3(0.0, 0.0, 0.0);
      else if (lum < 0.40) return vec3(0.42, 0.24, 0.58);
      else if (lum < 0.65) return vec3(0.44, 0.71, 0.28);
      else if (lum < 0.85) return vec3(0.44, 0.64, 0.70);
      return vec3(0.92, 0.93, 0.95);
    }} else if (u_palette == 4) {{
      if (lum < 0.15) return vec3(0.10, 0.09, 0.15);
      else if (lum < 0.30) return vec3(0.48, 0.15, 0.21);
      else if (lum < 0.45) return vec3(0.0, 0.53, 0.32);
      else if (lum < 0.60) return vec3(1.0, 0.64, 0.0);
      else if (lum < 0.75) return vec3(0.18, 0.67, 0.95);
      else if (lum < 0.90) return vec3(1.0, 0.47, 0.66);
      return vec3(1.0, 0.95, 0.91);
    }} else if (u_palette == 5) {{
      if (lum < 0.25) return vec3(0.18, 0.05, 0.28);
      else if (lum < 0.50) return vec3(0.44, 0.16, 0.52);
      else if (lum < 0.75) return vec3(0.96, 0.45, 0.68);
      return vec3(0.98, 0.88, 0.71);
    }} else if (u_palette == 6) {{
      if (lum < 0.20) return vec3(0.08, 0.09, 0.17);
      else if (lum < 0.45) return vec3(0.96, 0.26, 0.45);
      else if (lum < 0.70) return vec3(0.48, 0.38, 0.98);
      else if (lum < 0.88) return vec3(0.24, 0.82, 0.76);
      return vec3(0.98, 0.84, 0.46);
    }} else if (u_palette == 7) {{
      if (lum < 0.25) return vec3(0.0, 0.04, 0.0);
      else if (lum < 0.55) return vec3(0.0, 0.45, 0.12);
      else if (lum < 0.85) return vec3(0.15, 0.95, 0.35);
      return vec3(0.85, 1.0, 0.88);
    }} else if (u_palette == 8) {{
      if (lum < 0.22) return vec3(0.14, 0.02, 0.22);
      else if (lum < 0.50) return vec3(0.72, 0.08, 0.48);
      else if (lum < 0.75) return vec3(0.98, 0.42, 0.18);
      return vec3(1.0, 0.88, 0.25);
    }} else if (u_palette == 9) {{
      if (lum < 0.25) return vec3(0.05, 0.02, 0.0);
      else if (lum < 0.55) return vec3(0.60, 0.25, 0.0);
      else if (lum < 0.85) return vec3(0.95, 0.55, 0.05);
      return vec3(1.0, 0.85, 0.45);
    }} else if (u_palette == 10) {{
      if (lum < 0.22) return vec3(0.18, 0.20, 0.25);
      else if (lum < 0.50) return vec3(0.37, 0.51, 0.67);
      else if (lum < 0.75) return vec3(0.53, 0.75, 0.82);
      return vec3(0.93, 0.95, 0.96);
    }} else if (u_palette == 11) {{
      if (lum < 0.20) return vec3(0.16, 0.16, 0.21);
      else if (lum < 0.45) return vec3(0.74, 0.46, 0.98);
      else if (lum < 0.70) return vec3(1.0, 0.48, 0.64);
      else if (lum < 0.88) return vec3(0.31, 0.98, 0.48);
      return vec3(0.97, 0.97, 0.95);
    }} else if (u_palette == 12) {{
      if (lum < 0.22) return vec3(0.05, 0.0, 0.10);
      else if (lum < 0.48) return vec3(0.85, 0.0, 0.95);
      else if (lum < 0.75) return vec3(0.0, 0.98, 0.45);
      return vec3(0.98, 0.98, 0.05);
    }} else if (u_palette == 13) {{
      if (lum < 0.22) return vec3(0.14, 0.09, 0.06);
      else if (lum < 0.50) return vec3(0.44, 0.30, 0.21);
      else if (lum < 0.75) return vec3(0.76, 0.60, 0.45);
      return vec3(0.95, 0.89, 0.79);
    }} else if (u_palette == 14) {{
      if (lum < 0.18) return vec3(0.05, 0.05, 0.45);
      else if (lum < 0.42) return vec3(0.55, 0.05, 0.55);
      else if (lum < 0.68) return vec3(0.95, 0.25, 0.05);
      else if (lum < 0.88) return vec3(0.98, 0.88, 0.05);
      return vec3(0.98, 0.98, 0.98);
    }} else if (u_palette == 15) {{
      return vec3(step(0.5, lum));
    }} else if (u_palette == 16) {{
      return floor(color * 4.0) / 4.0;
    }} else if (u_palette == 17) {{
      if (lum < 0.25) return u_kcol1;
      else if (lum < 0.50) return u_kcol2;
      else if (lum < 0.75) return u_kcol3;
      return u_kcol4;
    }} else if (u_palette == 18) {{
      if (lum < 0.25) return vec3(0.15, 0.02, 0.10);
      else if (lum < 0.50) return vec3(0.85, 0.20, 0.15);
      else if (lum < 0.75) return vec3(0.98, 0.70, 0.10);
      return vec3(1.0, 0.95, 0.60);
    }} else if (u_palette == 19) {{
      if (lum < 0.25) return vec3(0.01, 0.12, 0.15);
      else if (lum < 0.50) return vec3(0.15, 0.55, 0.82);
      else if (lum < 0.75) return vec3(0.51, 0.58, 0.59);
      return vec3(0.99, 0.96, 0.89);
    }} else if (u_palette == 20) {{
      float h = fract(lum + u_time * 0.1);
      return vec3(sin(h * 6.28) * 0.5 + 0.5, sin((h + 0.33) * 6.28) * 0.5 + 0.5, sin((h + 0.66) * 6.28) * 0.5 + 0.5);
    }}
    return floor(color * 4.0) / 4.0;
  }}

  void main() {{
    vec2 uv = vTexCoord;
    uv.y = 1.0 - uv.y;

    float activeGrid = max(2.0, u_grid + (u_bass * u_gain) * 16.0);
    vec2 gridCount = u_resolution / activeGrid;
    vec2 cellIndex = floor(uv * gridCount);
    vec2 gridUV = cellIndex / gridCount;
    vec2 localCoord = fract(uv * gridCount);

    if (u_dither_mode == 10) {{
      float vD = voronoiDist(uv * (gridCount * 0.5) + u_time * 0.2);
      gridUV = floor(uv * gridCount + (vD - 0.5) * 0.1 * (u_bass * u_gain + 0.2)) / gridCount;
    }}

    if (u_dither_mode == 9) {{
      float glitchLine = step(0.91, fract(sin(floor(uv.y * 35.0) + u_time * 4.0) * 43758.5453));
      gridUV.x += glitchLine * ((u_high * u_gain) * 0.05 + 0.02) * sin(u_time * 15.0);
    }}

    float shift = (u_chromatic * 0.02) + ((u_high * u_gain) * 0.035);
    vec3 col;
    col.r = texture2D(u_tex, gridUV + vec2(shift, 0.0)).r;
    col.g = texture2D(u_tex, gridUV).g;
    col.b = texture2D(u_tex, gridUV - vec2(shift, 0.0)).b;

    float lum = dot(col, vec3(0.299, 0.587, 0.114));

    if (u_dither_mode == 1) {{
      float ditherThreshold = bayer4(gl_FragCoord.xy);
      lum = lum + (ditherThreshold - 0.5) * (0.35 + (u_mid * u_gain) * 0.45);
    }} else if (u_dither_mode == 2) {{
      float ditherThreshold = bayer8(gl_FragCoord.xy);
      lum = lum + (ditherThreshold - 0.5) * (0.32 + (u_mid * u_gain) * 0.45);
    }} else if (u_dither_mode == 3) {{
      float noise = blueNoise(cellIndex + fract(u_time * 0.05));
      lum = lum + (noise - 0.5) * (0.38 + (u_mid * u_gain) * 0.5);
    }} else if (u_dither_mode == 4) {{
      float dist = length(localCoord - 0.5);
      float dotRadius = (1.0 - lum) * 0.65;
      lum = step(dotRadius, dist);
    }} else if (u_dither_mode == 5) {{
      float line1 = step(0.5, mod(gl_FragCoord.x + gl_FragCoord.y, 6.0) / 6.0);
      float line2 = step(0.5, mod(gl_FragCoord.x - gl_FragCoord.y, 6.0) / 6.0);
      if (lum < 0.25) lum = (line1 * line2);
      else if (lum < 0.50) lum = line1;
      else if (lum < 0.75) lum = 0.5 + 0.5 * line2;
      else lum = 1.0;
    }} else if (u_dither_mode == 6) {{
      float subpixel = mod(gl_FragCoord.x, 3.0);
      if (subpixel < 1.0) col.gb *= 0.25;
      else if (subpixel < 2.0) col.rb *= 0.25;
      else col.rg *= 0.25;
    }} else if (u_dither_mode == 7) {{
      vec2 dp = mod(gl_FragCoord.xy, 4.0);
      float diamond = (abs(dp.x - 2.0) + abs(dp.y - 2.0)) / 4.0;
      lum = lum + (diamond - 0.5) * 0.45;
    }} else if (u_dither_mode == 8) {{
      float pattern = mod(floor(localCoord.x * 3.0) + floor(localCoord.y * 3.0) * 3.0, 9.0) / 9.0;
      lum = step(pattern, lum);
    }} else if (u_dither_mode == 11) {{
      float edgeDist = min(min(localCoord.x, 1.0 - localCoord.x), min(localCoord.y, 1.0 - localCoord.y));
      float shade = smoothstep(0.0, 0.12, edgeDist) * 0.6 + 0.4;
      if (localCoord.x + localCoord.y < 0.35) shade *= 1.35;
      if (localCoord.x + localCoord.y > 1.65) shade *= 0.65;
      col *= shade;
    }} else if (u_dither_mode == 12) {{
      float hamQuant = floor(lum * 12.0) / 12.0;
      lum = mix(lum, hamQuant, 0.7);
    }} else if (u_dither_mode == 13) {{
      float life = fract(sin(dot(cellIndex, vec2(12.9898, 78.233)) + floor(u_time * 4.0)) * 43758.5453);
      if (life > 0.7) lum = min(1.0, lum + (u_bass * u_gain) * 0.35);
      else if (life < 0.25) lum = max(0.0, lum - 0.25);
    }} else if (u_dither_mode == 14) {{
      lum = pow(lum, 1.3);
    }}

    vec3 finalColor = applyPalette(col, lum);

    if (u_crt) {{
      float scanline = sin(uv.y * u_resolution.y * 1.6) * 0.12;
      finalColor -= scanline;

      float vig = uv.x * uv.y * (1.0 - uv.x) * (1.0 - uv.y);
      vig = clamp(pow(16.0 * vig, 0.22), 0.0, 1.0);
      finalColor *= vig;
    }}

    gl_FragColor = vec4(finalColor, 1.0);
  }}
`;

function preload() {{
  img = loadImage('{img_data_uri}');
}}

function setup() {{
  createCanvas(windowWidth, windowHeight, WEBGL);
  noStroke();
  shaderProgram = createShader(vertSrc, fragSrc);
}}

function draw() {{
  if (!shaderProgram || !img) return;
  shader(shaderProgram);
  shaderProgram.setUniform('u_tex', img);
  shaderProgram.setUniform('u_resolution', [width, height]);
  shaderProgram.setUniform('u_grid', gridVal);
  shaderProgram.setUniform('u_dither_mode', ditherMode);
  shaderProgram.setUniform('u_palette', paletteMode);
  shaderProgram.setUniform('u_crt', crtOn);
  shaderProgram.setUniform('u_chromatic', chromaticAmt);
  shaderProgram.setUniform('u_gain', audioGain);
  shaderProgram.setUniform('u_time', millis() / 1000.0);
  shaderProgram.setUniform('u_bass', window.audioLow || 0.0);
  shaderProgram.setUniform('u_mid', window.audioMid || 0.0);
  shaderProgram.setUniform('u_high', window.audioHigh || 0.0);
  shaderProgram.setUniform('u_kcol1', kcolor1);
  shaderProgram.setUniform('u_kcol2', kcolor2);
  shaderProgram.setUniform('u_kcol3', kcolor3);
  shaderProgram.setUniform('u_kcol4', kcolor4);
  rect(-width / 2, -height / 2, width, height);
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}
"""

                # Phase 3: AI Visual DNA & Director Tagging
                dither_mode = mode_idx
                ai_dna = {
                    "geometry": {"type": "pixel_shader", "topology": f"StyleMode_{dither_mode}"},
                    "audio_binding": {
                        "bass": {"target": "grid_distortion", "multiplier": audio_gain},
                        "mid": {"target": "dither_threshold", "multiplier": audio_gain},
                        "high": {"target": "chromatic_glitch", "multiplier": audio_gain}
                    },
                    "section_fitness": {
                        "intro": 0.85 if dither_mode in [6, 14, 3] else (0.7 if dither_mode in [1, 2] else 0.4),
                        "verse": 0.9 if dither_mode in [1, 2, 4, 5] else 0.6,
                        "buildup": 0.85 if dither_mode in [8, 9, 10, 12] else 0.6,
                        "drop": 0.95 if dither_mode in [8, 9, 10, 12] else 0.5,
                        "outro": 0.8 if dither_mode in [1, 2, 6, 14] else 0.5
                    }
                }

                payload = {
                    "name": final_name,
                    "author": self.config_data.get("author", "unclerm"),
                    "license": "CC BY-SA",
                    "tags": ["pixel", "shader", "audio-reactive", pal_tag, "batch_generated"],
                    "visual_dna": ai_dna,
                    "suggested_tags": {
                        "section_fitness": ai_dna["section_fitness"],
                        "energy_level": 0.8 if dither_mode in [8, 9, 10, 12] else 0.6,
                        "style_tags": ["pixel", "shader", pal_tag, f"mode_{dither_mode}"]
                    },
                    "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "frequency": 65,
                    "storyboard_weight": 70,
                    "post_fx_intensity": 60,
                    "code": code,
                    "custom_html": "",
                    "custom_css": "",
                    "inline_assets": {},
                    "scaling_mode": "cover"
                }

                json_path = os.path.join(save_dir, f"{final_name}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4, ensure_ascii=False)

                success_count += 1
                created_names.append(final_name)
                pixel_logger.debug(f"[BatchWorker] [{idx+1}/{total}] Generated module: {final_name}")

            except Exception as e:
                fail_count += 1
                pixel_logger.error(f"[BatchWorker] Failed to process {img_path}: {e}")

        self.batch_finished.emit(success_count, fail_count, created_names)


# ─────────────────────────────────────────────────────────────────────────────
# 5. 第 4 個獨立頁籤：👾 像素視覺模組生成器 主控制面板
# ─────────────────────────────────────────────────────────────────────────────
class PixelModuleGeneratorTab(QWidget):
    """第 4 個獨立頁籤：👾 像素視覺模組生成器"""
    def __init__(self, parent_app=None):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.batch_worker = None

        pixel_logger.info("[PixelGeneratorTab] Initializing PixelModuleGeneratorTab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("👾 像素音畫視覺模組生成器 (Pixel Visual Synth Generator)", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        layout.addWidget(title)

        # ── 1. 來源照片資料夾選擇 ──
        folder_box = QHBoxLayout()
        self.folder_input = QLineEdit(self)
        self.folder_input.setPlaceholderText("請選擇或貼入照片來源資料夾路徑...")
        self.lbl_detected_count = QLabel("📷 已偵測: 0 張照片", self)
        self.lbl_detected_count.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: bold;")
        
        btn_browse_folder = QPushButton("選擇資料夾...", self)
        btn_browse_folder.clicked.connect(self.browse_image_folder)
        
        folder_box.addWidget(self.folder_input, stretch=3)
        folder_box.addWidget(self.lbl_detected_count, stretch=1)
        folder_box.addWidget(btn_browse_folder)
        layout.addLayout(folder_box)

        # ── 2. 測試音訊來源 ──
        audio_box = QHBoxLayout()
        self.audio_input = QLineEdit(self)
        self.audio_input.setPlaceholderText("選擇測試音訊檔案 (.mp3, .wav，選填)...")
        btn_browse_audio = QPushButton("瀏覽...", self)
        btn_browse_audio.clicked.connect(self.browse_audio_file)
        audio_box.addWidget(self.audio_input)
        audio_box.addWidget(btn_browse_audio)
        layout.addLayout(audio_box)

        # ── 2.5. 🧠 本地 AI 自然語言像素調參 ──
        ai_box = QGroupBox("💬 AI 自然語言智能調參 (Local LLM Prompt-to-Pixel)", self)
        ai_box.setStyleSheet("""
            QGroupBox {
                background-color: #121215;
                border: 1px solid #27272a;
                border-radius: 8px;
                margin-top: 4px;
                font-size: 11px;
                font-weight: bold;
                color: #c084fc;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
                background-color: #121215;
            }
        """)
        ai_layout = QVBoxLayout(ai_box)
        ai_layout.setContentsMargins(8, 8, 8, 8)
        ai_layout.setSpacing(6)

        ai_input_row = QHBoxLayout()
        self.ai_prompt_input = QLineEdit(self)
        self.ai_prompt_input.setPlaceholderText("輸入像素風格描述（例：『90年代街機故障賽博龐克，高對比色散，重低音強烈抖動』）...")
        self.ai_prompt_input.setStyleSheet("QLineEdit { background-color: #18181b; border: 1px solid #3f3f46; color: #f4f4f5; padding: 6px 10px; border-radius: 4px; font-size: 11px; } QLineEdit:focus { border-color: #a855f7; }")
        self.ai_prompt_input.returnPressed.connect(self.run_ai_prompt_tuning)

        self.btn_ai_tune = QPushButton("🪄 【AI 智能調參】", self)
        self.btn_ai_tune.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 4px;
                border: 1px solid #8b5cf6;
            }
            QPushButton:hover { background-color: #6d28d9; border-color: #c084fc; }
        """)
        self.btn_ai_tune.clicked.connect(self.run_ai_prompt_tuning)

        self.btn_ai_palette = QPushButton("🎨 【AI 原創調色盤】", self)
        self.btn_ai_palette.setStyleSheet("""
            QPushButton {
                background-color: #065f46;
                color: #a7f3d0;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #059669;
            }
            QPushButton:hover { background-color: #047857; border-color: #34d399; }
        """)
        self.btn_ai_palette.clicked.connect(self.run_ai_palette_generation)

        ai_input_row.addWidget(self.ai_prompt_input, stretch=1)
        ai_input_row.addWidget(self.btn_ai_tune)
        ai_input_row.addWidget(self.btn_ai_palette)
        ai_layout.addLayout(ai_input_row)

        self.lbl_ai_status = QLabel("💡 支援 DeepSeek-R1 / Llama3 本地模型自然語言調參，自動解析網格、著色模式與音視綁定", self)
        self.lbl_ai_status.setStyleSheet("color: #71717a; font-size: 10px; padding-left: 2px;")
        ai_layout.addWidget(self.lbl_ai_status)

        layout.addWidget(ai_box)

        # ── 3. 一鍵風格預設 ──
        preset_title = QLabel("⚡ 一鍵風格預設 (Quick Style Presets)", self)
        preset_title.setStyleSheet("font-weight: bold; color: #38bdf8; margin-top: 4px;")
        layout.addWidget(preset_title)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        presets_main = [
            ("🕹️ 1989 GameBoy", 12, 1, 1),
            ("💜 賽博龐克 Cyberpunk", 10, 2, 0),
            ("🌊 蒸汽波 Vaporwave", 14, 3, 5),
            ("📟 駭客任務 Matrix", 10, 8, 7),
            ("🏎️ 落日 Outrun", 12, 7, 8),
            ("👾 街機 Arcade", 8, 6, 4),
            ("📰 報紙 Halftone", 12, 4, 15),
            ("☣️ 酸性 Acid", 16, 9, 12)
        ]
        for p_name, g_val, m_val, pal_val in presets_main:
            btn = QPushButton(p_name, self)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e1e24;
                    color: #e4e4e7;
                    font-size: 11px;
                    padding: 6px 4px;
                    border: 1px solid #3f3f46;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #7c3aed;
                    color: #fff;
                    border-color: #a855f7;
                }
            """)
            btn.clicked.connect(lambda checked, g=g_val, m=m_val, p=pal_val: self.apply_main_preset(g, m, p))
            preset_row.addWidget(btn)
        layout.addLayout(preset_row)

        # ── 4. 像素風格化初始設定 ──
        style_title = QLabel("🎨 像素風格與音畫機制細節調校", self)
        style_title.setStyleSheet("font-weight: bold; color: #a1a1aa; margin-top: 5px;")
        layout.addWidget(style_title)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("初始網格尺寸:", self))
        self.grid_combo = QComboBox(self)
        self.grid_combo.setView(QListView())
        self.grid_combo.addItems(["8px (細膩)", "10px (推薦)", "12px (標準)", "16px (復古)", "24px (粗糙)", "32px (極限像素)"])
        self.grid_combo.setCurrentIndex(2)
        grid_row.addWidget(self.grid_combo)

        grid_row.addWidget(QLabel("著色抖色模式:", self))
        self.style_mode_combo = QComboBox(self)
        self.style_mode_combo.setView(QListView())
        self.style_mode_combo.addItems([
            "0: 區塊方塊像素 (Block Pixel)",
            "1: Bayer 4×4 網點抖色 (Bayer 4x4)",
            "2: Bayer 8×8 矩陣平滑抖色 (Bayer 8x8)",
            "3: Blue Noise 藍噪聲隨機顆粒 (Blue Noise)",
            "4: Halftone 印刷半色調波點 (Halftone Dot)",
            "5: Crosshatch 漫畫交叉素描排線 (Crosshatch)",
            "6: CRT Phosphor Subpixel (RGB 垂直子像素)",
            "7: Diamond 45° 菱形斜交抖色 (Diamond Dither)",
            "8: ASCII 字符密度矩陣 (ASCII / Matrix Glyph)",
            "9: Glitch Slicing 故障切片撕裂 (Glitch Tear)",
            "10: 💎 Voronoi 水晶多邊形碎裂 (Voronoi Crystal)",
            "11: 🧊 3D 體積浮雕像素 (3D Voxel Prism)",
            "12: 🎨 Amiga 500 HAM6 流體油畫 (HAM6 Fluid)",
            "13: 🦠 Cellular Life 生命遊戲繁衍 (Cellular Life)",
            "14: 🔥 Thermal FLIR 熱成像紅外線 (Thermal FLIR)"
        ])
        self.style_mode_combo.setCurrentIndex(2)
        grid_row.addWidget(self.style_mode_combo)

        grid_row.addWidget(QLabel("色彩調色盤:", self))
        self.palette_combo = QComboBox(self)
        self.palette_combo.setView(QListView())
        self.palette_combo.addItems([
            "0: 💜 Cyberpunk Neon (賽博霓虹)",
            "1: 🕹️ Game Boy Classic 1989 (初版綠灰四階)",
            "2: 🎮 Game Boy Pocket (黑白灰階四階)",
            "3: 📺 Commodore 64 (C64 復古色系)",
            "4: 👾 PICO-8 幻想主機 (16-bit 經典調)",
            "5: 🌊 Vaporwave Pastel (蒸汽波粉彩)",
            "6: 🌃 Tokyo Night Neo-Tokyo (東京暗夜藍紫金)",
            "7: 📟 Matrix Digital Rain (駭客任務數位綠)",
            "8: 🏎️ Synthwave Outrun 1984 (落日公路紫橙)",
            "9: 🖥️ Apple II Amber Terminal (琥珀金終端)",
            "10: 🧊 Nord Arctic Frost (北歐極地冰原)",
            "11: 🩸 Dracula Gothic (德古拉歌德黑紅紫)",
            "12: ☣️ Acid Techno Neon (迷幻酸性高飽和)",
            "13: 📜 Sepia Vintage Film (老照片復古褐斑)",
            "14: 🔥 Thermal Heatmap (熱成像紅外線)",
            "15: ⬛ Monochrome 1-bit Manga (黑白漫畫純二值)",
            "16: 🌈 Original Quantized (原圖自適應階調量化)",
            "17: 🎨 K-Means 當前照片專屬萃取色 (Photo K-Means)",
            "18: 🌅 Sunset Outrun Gold (落日金橙)",
            "19: 🌌 Solarized Deep Space (深空藍紫)",
            "20: 📼 Amiga Copper Rainbow (阿米加彩虹條帶)"
        ])
        grid_row.addWidget(self.palette_combo)
        layout.addLayout(grid_row)

        # ── 5. 音畫調變機制與智慧打散勾選 ──
        mod_box = QHBoxLayout()
        self.cb_bass = QCheckBox("低頻 (Bass) 調變網格尺寸與震動", self)
        self.cb_bass.setChecked(True)
        self.cb_mid = QCheckBox("中頻 (Mid) 調變抖色臨界值與色相", self)
        self.cb_mid.setChecked(True)
        self.cb_high = QCheckBox("高頻/瞬態 (High) 觸發 RGB 色差 Glitch", self)
        self.cb_high.setChecked(True)
        mod_box.addWidget(self.cb_bass)
        mod_box.addWidget(self.cb_mid)
        mod_box.addWidget(self.cb_high)
        layout.addLayout(mod_box)

        # 智慧多樣性打散
        self.cb_smart_diversity = QCheckBox("🎲 批次輸出時啟用智慧風格多樣性打散 (自動分配 15 種風格與 21 款調色盤)", self)
        self.cb_smart_diversity.setStyleSheet("color: #ec4899; font-weight: bold; font-size: 12px; margin-top: 4px;")
        self.cb_smart_diversity.setChecked(True)
        layout.addWidget(self.cb_smart_diversity)

        layout.addStretch()

        # ── 5. 雙操作生成按鈕列 ──
        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)

        self.btn_generate = QPushButton("⚡ 生成並啟動單模組測試視窗 (Live Inspector)", self)
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                font-size: 13px;
                padding: 14px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #8b5cf6;
            }
        """)
        self.btn_generate.clicked.connect(self.launch_inspector)
        actions_row.addWidget(self.btn_generate, stretch=1)

        self.btn_batch_export = QPushButton("📦 一鍵全自動批次生成全目錄模組 (Auto-Name & Batch Export)", self)
        self.btn_batch_export.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                font-size: 13px;
                padding: 14px;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #10b981;
            }
        """)
        self.btn_batch_export.clicked.connect(self.start_batch_export)
        actions_row.addWidget(self.btn_batch_export, stretch=1)

        layout.addLayout(actions_row)

    def browse_image_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "選擇照片來源資料夾")
        if dir_path:
            self.folder_input.setText(dir_path)
            # 掃描並更新計數
            imgs = self._scan_images(dir_path)
            self.lbl_detected_count.setText(f"📷 已偵測: {len(imgs)} 張照片")
            pixel_logger.info(f"[PixelGeneratorTab] Selected Image Folder: {dir_path} ({len(imgs)} photos detected)")

    def _scan_images(self, folder_path: str):
        image_paths = []
        if folder_path and os.path.isdir(folder_path):
            for f in os.listdir(folder_path):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
                    image_paths.append(os.path.join(folder_path, f))
            image_paths.sort()
        return image_paths

    def browse_audio_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "選擇測試音訊檔案", "", "Audio Files (*.mp3 *.wav)")
        if file_path:
            self.audio_input.setText(file_path)
            pixel_logger.info(f"[PixelGeneratorTab] Selected Audio File: {file_path}")

    def apply_main_preset(self, grid_val, mode_idx, pal_idx):
        grid_map_rev = {8: 0, 10: 1, 12: 2, 16: 3, 24: 4, 32: 5}
        self.grid_combo.setCurrentIndex(grid_map_rev.get(grid_val, 2))
        self.style_mode_combo.setCurrentIndex(mode_idx)
        self.palette_combo.setCurrentIndex(pal_idx)
        pixel_logger.info(f"[PixelGeneratorTab] Applied Main Preset: Grid={grid_val}, Mode={mode_idx}, Pal={pal_idx}")

    def _get_current_config(self):
        grid_map = {0: 8, 1: 10, 2: 12, 3: 16, 4: 24, 5: 32}
        return {
            "grid_size": grid_map.get(self.grid_combo.currentIndex(), 12),
            "style_mode_idx": self.style_mode_combo.currentIndex(),
            "palette_idx": self.palette_combo.currentIndex(),
            "smart_diversity": self.cb_smart_diversity.isChecked(),
            "crt": True,
            "chromatic": 0.4,
            "author": "unclerm",
            "default_name": f"pixel_synth_{int(datetime.datetime.now().timestamp())}"
        }

    def launch_inspector(self):
        folder_path = self.folder_input.text().strip()
        image_paths = self._scan_images(folder_path)
        pixel_logger.info(f"[PixelGeneratorTab] Launching Inspector with {len(image_paths)} images from '{folder_path}'")

        config_data = self._get_current_config()
        dlg = PixelModuleTestDialog(config_data, image_paths, self)
        dlg.exec()

    def start_batch_export(self):
        folder_path = self.folder_input.text().strip()
        image_paths = self._scan_images(folder_path)

        if not image_paths:
            QMessageBox.warning(self, "警告", "選定的資料夾中沒有任何支援的圖片檔案！\n請先選擇包含照片的資料夾。")
            return

        reply = QMessageBox.question(
            self,
            "確認全自動批次生成",
            f"即將為資料夾中的 {len(image_paths)} 張照片自動命名、建立像素 Shader 視覺模組與高畫質縮圖並收編入庫。\n\n是否立即開始？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from PyQt6.QtWidgets import QProgressDialog
        self.progress_dlg = QProgressDialog(f"正在批次生成像素模組 (共 {len(image_paths)} 個)...", "取消", 0, len(image_paths), self)
        self.progress_dlg.setWindowTitle("👾 像素模組極速批次收編中")
        self.progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dlg.setMinimumDuration(0)
        self.progress_dlg.setValue(0)

        config_data = self._get_current_config()
        self.batch_worker = BatchPixelExportWorker(image_paths, config_data, self)
        self.batch_worker.progress_updated.connect(self._on_batch_progress)
        self.batch_worker.batch_finished.connect(self._on_batch_finished)
        self.progress_dlg.canceled.connect(self.batch_worker.cancel)

        pixel_logger.info(f"[PixelGeneratorTab] Starting Batch Worker for {len(image_paths)} images")
        self.batch_worker.start()

    def _on_batch_progress(self, current: int, total: int, name: str):
        if hasattr(self, 'progress_dlg') and self.progress_dlg:
            self.progress_dlg.setValue(current)
            self.progress_dlg.setLabelText(f"[{current}/{total}] 正在處理並收編: {name}...")

    def _on_batch_finished(self, success_count: int, fail_count: int, created_names: list):
        if hasattr(self, 'progress_dlg') and self.progress_dlg:
            self.progress_dlg.close()

        pixel_logger.info(f"[PixelGeneratorTab] Batch Finished: {success_count} success, {fail_count} failed")

        # 刷新主視窗模組庫清單
        if self.parent_app:
            self.parent_app.cached_presets = None
            self.parent_app.refresh_presets_list()
            self.parent_app.log_to_console(f"🎉 成功批次生成並收編 {success_count} 個像素視覺模組入庫！")

        QMessageBox.information(
            self,
            "批次收編完成",
            f"🎉 批次生成作業已完成！\n\n✅ 成功收編: {success_count} 個模組\n❌ 失敗: {fail_count} 個\n\n所有模組已自動命名並建立對應縮圖，可直接在「視覺模組編輯」與「4K 離線渲染器」中調用！"
        )

    def run_ai_prompt_tuning(self):
        prompt = self.ai_prompt_input.text().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "請輸入風格描述指令！")
            return
        
        self.btn_ai_tune.setEnabled(False)
        self.btn_ai_tune.setText("⏳ AI 解析中...")
        self.lbl_ai_status.setText(f"🧠 本地 AI 模型正在解碼像素風格: 『{prompt}』...")
        
        engine = PixelAIEngine()
        self.main_ai_worker = PixelAIParamWorker(prompt, engine, self)
        self.main_ai_worker.params_ready.connect(self._on_main_ai_params_ready)
        self.main_ai_worker.failed.connect(self._on_main_ai_failed)
        self.main_ai_worker.finished.connect(lambda: (self.btn_ai_tune.setEnabled(True), self.btn_ai_tune.setText("🪄 【AI 智能調參】")))
        self.main_ai_worker.start()

    def _on_main_ai_params_ready(self, params: dict):
        grid_map_rev = {8: 0, 10: 1, 12: 2, 16: 3, 24: 4, 32: 5}
        grid_val = params.get("grid_size", 12)
        self.grid_combo.setCurrentIndex(grid_map_rev.get(grid_val, 2))
        self.style_mode_combo.setCurrentIndex(params.get("style_mode", 2))
        self.palette_combo.setCurrentIndex(params.get("palette_id", 0))
        
        # Audio checkboxes
        gain = params.get("audio_gain", 1.0)
        self.cb_bass.setChecked(True)
        self.cb_mid.setChecked(True)
        self.cb_high.setChecked(params.get("chromatic", 0.4) > 0.3)
        
        mode_name = self.style_mode_combo.currentText().split(':')[1].strip() if ':' in self.style_mode_combo.currentText() else ""
        pal_name = self.palette_combo.currentText().split(':')[1].strip() if ':' in self.palette_combo.currentText() else ""
        self.lbl_ai_status.setText(f"✅ AI 調參完成！網格: {grid_val}px | 模式: {mode_name} | 色盤: {pal_name}")
        pixel_logger.info(f"[PixelGeneratorTab] AI Auto-tuned params: {params}")

    def run_ai_palette_generation(self):
        prompt = self.ai_prompt_input.text().strip() or "Cyberpunk Outrun"
        self.btn_ai_palette.setEnabled(False)
        self.btn_ai_palette.setText("⏳ 色彩演算...")
        self.lbl_ai_status.setText(f"🎨 本地 AI 正在計算專屬 4 色 OKLCH/RGB 像素調色盤...")
        
        engine = PixelAIEngine()
        self.main_pal_worker = PixelAIPaletteWorker(prompt, "Audio-Reactive Dynamic", engine, self)
        self.main_pal_worker.palette_ready.connect(self._on_main_palette_ready)
        self.main_pal_worker.failed.connect(self._on_main_ai_failed)
        self.main_pal_worker.finished.connect(lambda: (self.btn_ai_palette.setEnabled(True), self.btn_ai_palette.setText("🎨 【AI 原創調色盤】")))
        self.main_pal_worker.start()

    def _on_main_palette_ready(self, pal_data: dict):
        self.palette_combo.setCurrentIndex(17) # Custom K-Means/AI slot
        name = pal_data.get("name", "AI Custom Palette")
        self.lbl_ai_status.setText(f"✅ AI 已生成原創調色盤: 『{name}』")
        QMessageBox.information(self, "AI 調色盤生成成功", f"已成功為您生成 4 色原創像素調色盤：\n『{name}』\n已自動套用至當前著色器槽位！")

    def _on_main_ai_failed(self, err: str):
        self.lbl_ai_status.setText(f"❌ AI 解析失敗: {err}")

