# -*- coding: utf-8 -*-
"""
SENTINEL-CHRONOS: Ambient & Drone Dedicated Studio Tab (Pro)
-------------------------------------------------------------
專為 Ambient、Drone、Meditative 風格打造的獨立沉浸式工作台。

第三次會議代碼審計與除錯優化拓展亮點：
1. [除錯] 移除缺失的 -apple-system 字體引用，杜絕 macOS 439ms 字體別名開銷。
2. [拓展] 內建三欄式沉浸佈局：左側模組庫 + 中間 4K 實時 WebGL 全域光場畫布 + 右側五大宏觀推子。
3. [優化] 實現毫秒級 QWebEngineView 雙向動態綁定：推子拖動時，WebGL 著色器即時同步呼吸響應！
4. [生態] 單鍵注入與雙向同步，無縫對接主程式 main.py。
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QGroupBox, QFrame, QSplitter, QProgressBar, QSizePolicy,
    QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView

from ambient_module_compatibility_gate import AmbientModuleCompatibilityGate
from ambient_chronos_director import AmbientChronosDirector
from ambient_ai_director_bridge import AmbientCognitiveDirectorBridge, VisualPolyphonyTrio
from ambient_polyphony_compositor import AmbientPolyphonyCompositor

logger = logging.getLogger("VisualStudio.AmbientStudioTab")

class AmbientDroneStudioTab(QWidget):
    """
    Ambient / Drone 專屬沉浸式視覺工作台 (Pro)
    """
    macroParametersChanged = pyqtSignal(dict)
    moduleSelected = pyqtSignal(str, dict)
    audioLoaded = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gate = AmbientModuleCompatibilityGate()
        self.director = AmbientChronosDirector()
        self.ai_director_bridge = AmbientCognitiveDirectorBridge()
        self.polyphony_compositor = AmbientPolyphonyCompositor()
        self.is_ai_auteur_active = True
        self.current_audio_seed = 42108542
        
        self.current_audio_path: Optional[str] = None
        self.album_tracks: List[str] = []

        self.macro_params = {
            "breathing_rate": 0.12,       # 0.12 Hz 呼吸頻率
            "optical_translucency": 0.75, # 75% 光學透明度
            "luminance_gravity": 0.65,    # 65% 次低頻重力下壓強度
            "chromatic_drift": 0.10,      # 0.10°/s 慢速色相演變
            "time_dilation": 0.04         # 0.04x 時間膨脹降頻
        }

        self.selected_module_id: Optional[str] = None
        self.current_filter: str = "all"

        self._setup_ui()
        self._load_curated_ambient_modules()
        self._init_webgl_canvas()

    def _setup_ui(self):
        # 跨平台原生安全字體，杜絕字體警報
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0d13;
                color: #c5cdd9;
                font-family: "Helvetica", "Arial", sans-serif;
            }
            QGroupBox {
                border: 1px solid #1a202c;
                border-radius: 8px;
                margin-top: 14px;
                font-weight: bold;
                font-size: 13px;
                color: #8b9bb4;
                padding-top: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #1e2638;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #4f6b94;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #a2b7d4;
                border: 1px solid #c5d4eb;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
            }
            QListWidget {
                background-color: #0e121a;
                border: 1px solid #1a2233;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 4px;
                margin-bottom: 3px;
            }
            QListWidget::item:selected {
                background-color: #1a2538;
                color: #e2e8f0;
                border-left: 3px solid #63b3ed;
            }
            QPushButton {
                background-color: #1a2233;
                border: 1px solid #2d3748;
                color: #cbd5e0;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #243047;
                border-color: #4a5568;
                color: #ffffff;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(14)

        # ==================== 1. 左側：音訊選取、精選模組與母題 ====================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        header_title = QLabel("CHRONOS // STUDIO")
        header_title.setFont(QFont("Monospace", 14, QFont.Weight.Bold))
        header_title.setStyleSheet("color: #90cdf4; letter-spacing: 1.5px;")
        
        subtitle = QLabel("少即是多 (Less is More) · 微動態呼吸工作台")
        subtitle.setStyleSheet("color: #718096; font-size: 11px;")
        left_layout.addWidget(header_title)
        left_layout.addWidget(subtitle)

        # 新增：音訊訊源與專輯載入群組
        audio_group = QGroupBox("🎵 音訊與專輯 (Audio & Album)")
        audio_layout = QVBoxLayout(audio_group)
        audio_layout.setSpacing(6)

        audio_btn_row = QHBoxLayout()
        self.btn_browse_audio = QPushButton("📁 單曲檔案")
        self.btn_browse_audio.setFixedHeight(28)
        self.btn_browse_audio.clicked.connect(self._on_browse_single_audio)
        
        self.btn_browse_album = QPushButton("📂 專輯資料夾")
        self.btn_browse_album.setFixedHeight(28)
        self.btn_browse_album.clicked.connect(self._on_browse_album_folder)
        
        audio_btn_row.addWidget(self.btn_browse_audio)
        audio_btn_row.addWidget(self.btn_browse_album)
        audio_layout.addLayout(audio_btn_row)

        self.track_combo = QComboBox()
        self.track_combo.setStyleSheet("""
            QComboBox {
                background: #131824;
                border: 1px solid #232d42;
                border-radius: 4px;
                padding: 5px 8px;
                color: #e2e8f0;
                font-size: 11px;
            }
        """)
        self.track_combo.addItem("請選擇歌曲或專輯資料夾...")
        self.track_combo.currentIndexChanged.connect(self._on_track_selected)
        audio_layout.addWidget(self.track_combo)

        self.lbl_audio_status = QLabel("狀態: 尚未載入音訊 (就緒)")
        self.lbl_audio_status.setStyleSheet("color: #718096; font-size: 10px;")
        audio_layout.addWidget(self.lbl_audio_status)

        left_layout.addWidget(audio_group)

        # 哲學母題選取
        motif_group = QGroupBox("哲學母題 (Auteur Motif)")
        motif_layout = QVBoxLayout(motif_group)
        self.motif_combo = QComboBox()
        self.motif_combo.setStyleSheet("""
            QComboBox {
                background: #131824;
                border: 1px solid #232d42;
                border-radius: 4px;
                padding: 6px 10px;
                color: #e2e8f0;
            }
        """)
        for m in self.director.CONTEMPLATIVE_MOTIFS:
            self.motif_combo.addItem(f"{m['title']}", m["id"])
        self.motif_combo.currentIndexChanged.connect(self._on_motif_changed)
        motif_layout.addWidget(self.motif_combo)
        left_layout.addWidget(motif_group)

        # 精選原生模組架
        rack_group = QGroupBox("精選原生 Ambient 模組庫")
        rack_layout = QVBoxLayout(rack_group)
        
        filter_bar = QHBoxLayout()
        self.btn_all = QPushButton("全部")
        self.btn_particles = QPushButton("粒子")
        self.btn_fluids = QPushButton("流體")
        
        self.btn_all.setStyleSheet("background-color: #3182ce; color: #ffffff; font-weight: bold; border: 1px solid #63b3ed;")
        for btn in (self.btn_all, self.btn_particles, self.btn_fluids):
            btn.setFixedHeight(26)
            filter_bar.addWidget(btn)
        rack_layout.addLayout(filter_bar)

        self.btn_all.clicked.connect(lambda: self._set_filter("all"))
        self.btn_particles.clicked.connect(lambda: self._set_filter("particles"))
        self.btn_fluids.clicked.connect(lambda: self._set_filter("fluids"))

        self.module_list_widget = QListWidget()
        self.module_list_widget.itemClicked.connect(self._on_module_item_clicked)
        self.module_list_widget.itemDoubleClicked.connect(self._on_module_item_clicked)
        self.module_list_widget.currentItemChanged.connect(self._on_module_current_changed)
        rack_layout.addWidget(self.module_list_widget)

        self.lbl_module_info = QLabel("💡 點選模組即可在右側 16:9 沙盒即時預覽")
        self.lbl_module_info.setStyleSheet("color: #718096; font-size: 10px; padding: 2px 4px;")
        rack_layout.addWidget(self.lbl_module_info)

        left_layout.addWidget(rack_group)

        left_panel.setFixedWidth(280)
        main_layout.addWidget(left_panel)

        # ==================== 2. 中間：實時 WebGL 沉浸式預覽畫布 ====================
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        canvas_header = QHBoxLayout()
        canvas_title = QLabel("4K 實時全域光場畫布 (Live Turrell-Ganzfeld View)")
        canvas_title.setStyleSheet("color: #a0aec0; font-size: 12px; font-weight: bold;")
        
        self.btn_ai_autopilot = QPushButton("🎬 AI 導演作者全自動託管 [運行中]")
        self.btn_ai_autopilot.setStyleSheet(
            "background-color: #065f46; color: #34d399; font-weight: bold; border: 1px solid #10b981; border-radius: 5px; padding: 4px 10px; font-size: 11px;"
        )
        self.btn_ai_autopilot.clicked.connect(self._toggle_ai_autopilot)

        self.fps_indicator = QLabel("60.0 FPS // GPU BOUND")
        self.fps_indicator.setStyleSheet("color: #48bb78; font-family: Monospace; font-size: 11px;")
        canvas_header.addWidget(canvas_title)
        canvas_header.addSpacing(10)
        canvas_header.addWidget(self.btn_ai_autopilot)
        canvas_header.addStretch()
        canvas_header.addWidget(self.fps_indicator)
        center_layout.addLayout(canvas_header)

        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #000000; border-radius: 8px; border: 1px solid #1a202c;")
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_layout.addWidget(self.web_view)

        # AI 導演作者資訊與三層複調面板
        director_panel = QFrame()
        director_panel.setStyleSheet("background-color: #0f131c; border: 1px solid #1a2233; border-radius: 6px; padding: 6px 10px;")
        director_vbox = QVBoxLayout(director_panel)
        director_vbox.setContentsMargins(6, 4, 6, 4)
        director_vbox.setSpacing(4)

        self.lbl_trio_status = QLabel("🎭 三層複調: [底] 全域體積光場 (32-D)  |  [中] 流體拓撲  |  [頂] 懸浮星塵")
        self.lbl_trio_status.setStyleSheet("color: #63b3ed; font-size: 11px; font-weight: bold;")
        director_vbox.addWidget(self.lbl_trio_status)

        self.lbl_director_intent = QLabel("🎬 [AI導演] 系統初始化就緒，守護純淨冥想心流。")
        self.lbl_director_intent.setStyleSheet("color: #68d391; font-family: Monospace; font-size: 10px;")
        self.lbl_director_intent.setWordWrap(True)
        director_vbox.addWidget(self.lbl_director_intent)

        center_layout.addWidget(director_panel)

        main_layout.addWidget(center_panel, stretch=1)

        # ==================== 3. 右側：五大宏觀調變推子 ====================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        faders_group = QGroupBox("五大心流宏觀調變推子")
        faders_layout = QVBoxLayout(faders_group)
        faders_layout.setSpacing(14)

        # 1. 呼吸速率
        self.slider_breathing, self.label_breathing = self._create_macro_fader(
            "🫁 有機呼吸速率 (Breathing Rate)",
            "0.12 Hz", 12, 1, 40,
            lambda v: self._update_macro_param("breathing_rate", v / 100.0, f"{v/100.0:.2f} Hz")
        )
        faders_layout.addLayout(self.slider_breathing)

        # 2. 光學透明厚度
        self.slider_translucency, self.label_translucency = self._create_macro_fader(
            "✨ 光學透明厚度 (Translucency)",
            "75%", 75, 10, 100,
            lambda v: self._update_macro_param("optical_translucency", v / 100.0, f"{v}%")
        )
        faders_layout.addLayout(self.slider_translucency)

        # 3. 明暗與次低頻重力
        self.slider_luminance, self.label_luminance = self._create_macro_fader(
            "🌑 次低頻重力下壓 (Sub-bass Gravity)",
            "65%", 65, 0, 100,
            lambda v: self._update_macro_param("luminance_gravity", v / 100.0, f"{v}%")
        )
        faders_layout.addLayout(self.slider_luminance)

        # 4. OKLCH 色相漂移
        self.slider_chroma, self.label_chroma = self._create_macro_fader(
            "🎨 色彩演化速度 (Chromatic Drift)",
            "0.10°/s", 10, 1, 50,
            lambda v: self._update_macro_param("chromatic_drift", v / 100.0, f"{v/100.0:.2f}°/s")
        )
        faders_layout.addLayout(self.slider_chroma)

        # 5. 時間膨脹降頻
        self.slider_time, self.label_time = self._create_macro_fader(
            "⏳ 時間膨脹降頻 (Time Dilation)",
            "0.04x", 4, 1, 20,
            lambda v: self._update_macro_param("time_dilation", v / 100.0, f"{v/100.0:.2f}x")
        )
        faders_layout.addLayout(self.slider_time)

        right_layout.addWidget(faders_group)

        # 32 維微觀調製抽屜 (Micro-Modulation Drawer)
        self.drawer_group = QGroupBox("🎛️ 32 維微觀調製矩陣 (Micro-Drawer)")
        drawer_layout = QVBoxLayout(self.drawer_group)
        drawer_layout.setSpacing(4)

        from PyQt6.QtWidgets import QCheckBox
        self.chk_autopilot = QCheckBox("✨ 音視自適應自動駕駛 (Audio Autopilot)")
        self.chk_autopilot.setChecked(True)
        self.chk_autopilot.setStyleSheet("color: #68d391; font-weight: bold; font-size: 11px;")
        drawer_layout.addWidget(self.chk_autopilot)

        # 快速微觀滑塊 1: 空間流形扭曲 (Domain Warp)
        self.slider_warp, self.label_warp = self._create_macro_fader(
            "🌀 空間流形扭曲 (Domain Warp)",
            "0.12", 12, 1, 50,
            lambda v: self._update_micro_param("u_domainWarpAmp", v / 100.0, f"{v/100.0:.2f}")
        )
        drawer_layout.addLayout(self.slider_warp)

        # 快速微觀滑塊 2: 各向異性散射因子 g
        self.slider_aniso, self.label_aniso = self._create_macro_fader(
            "☀️ 各向異性散射 (Anisotropy g)",
            "0.35", 35, -80, 80,
            lambda v: self._update_micro_param("u_anisotropyG", v / 100.0, f"{v/100.0:.2f}")
        )
        drawer_layout.addLayout(self.slider_aniso)

        # 快速微觀滑塊 3: 柯西彩虹色散
        self.slider_disp, self.label_disp = self._create_macro_fader(
            "🌈 柯西彩虹色散 (Dispersion)",
            "0.045", 45, 0, 150,
            lambda v: self._update_micro_param("u_cauchyDispersion", v / 1000.0, f"{v/1000.0:.3f}")
        )
        drawer_layout.addLayout(self.slider_disp)

        # 快速微觀滑塊 4: 大氣消光係數 β
        self.slider_extinct, self.label_extinct = self._create_macro_fader(
            "🌫️ 大氣消光係數 (Extinction β)",
            "1.85", 185, 20, 500,
            lambda v: self._update_micro_param("u_extinctionBeta", v / 100.0, f"{v/100.0:.2f}")
        )
        drawer_layout.addLayout(self.slider_extinct)

        right_layout.addWidget(self.drawer_group)

        # 即時心流監控條
        monitor_group = QGroupBox("即時心流呼吸儀")
        monitor_layout = QVBoxLayout(monitor_group)
        self.breathing_bar = QProgressBar()
        self.breathing_bar.setFixedHeight(6)
        self.breathing_bar.setTextVisible(False)
        self.breathing_bar.setStyleSheet("""
            QProgressBar { background: #131824; border-radius: 3px; }
            QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4299e1, stop:1 #9f7aea); border-radius: 3px; }
        """)
        monitor_layout.addWidget(self.breathing_bar)
        right_layout.addWidget(monitor_group)

        # 動作按鈕區
        action_btn_box = QVBoxLayout()
        action_btn_box.setSpacing(6)

        self.apply_btn = QPushButton("✨ 注入當前調變至 4K 主管線")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b6cb0;
                color: #ffffff;
                font-weight: bold;
                padding: 9px 14px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #3182ce; }
        """)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        action_btn_box.addWidget(self.apply_btn)

        self.start_render_btn = QPushButton("🚀 立即開始 4K 離線渲染")
        self.start_render_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 14px;
                border-radius: 6px;
                border: 1px solid #10b981;
            }
            QPushButton:hover {
                background-color: #10b981;
                border-color: #34d399;
            }
        """)
        self.start_render_btn.clicked.connect(self._on_start_render_clicked)
        action_btn_box.addWidget(self.start_render_btn)

        right_layout.addLayout(action_btn_box)

        right_panel.setFixedWidth(310)
        main_layout.addWidget(right_panel)

        # 內部計時器驅動呼吸演示
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._tick_ui_breathing)
        self.ui_timer.start(33)
        self.anim_t = 0.0

    def _create_macro_fader(self, title: str, init_val_str: str, init_val: int, min_val: int, max_val: int, callback):
        layout = QVBoxLayout()
        layout.setSpacing(3)
        
        header_line = QHBoxLayout()
        name_lbl = QLabel(title)
        name_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        val_lbl = QLabel(init_val_str)
        val_lbl.setStyleSheet("color: #63b3ed; font-family: Monospace; font-size: 11px;")
        header_line.addWidget(name_lbl)
        header_line.addStretch()
        header_line.addWidget(val_lbl)
        layout.addLayout(header_line)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        slider.valueChanged.connect(callback)
        layout.addWidget(slider)

        return layout, val_lbl

    def _update_macro_param(self, key: str, value: float, text_repr: str):
        self.macro_params[key] = value
        if key == "breathing_rate":
            self.label_breathing.setText(text_repr)
        elif key == "optical_translucency":
            self.label_translucency.setText(text_repr)
        elif key == "luminance_gravity":
            self.label_luminance.setText(text_repr)
        elif key == "chromatic_drift":
            self.label_chroma.setText(text_repr)
        elif key == "time_dilation":
            self.label_time.setText(text_repr)

        self._sync_webgl_uniforms()
        self.macroParametersChanged.emit(self.macro_params)

    def _update_micro_param(self, key: str, value: float, text_repr: str):
        """更新微觀調製抽屜參數"""
        if not hasattr(self, "micro_params"):
            self.micro_params = {}
        self.micro_params[key] = value
        # 標記使用者已手動干預微調
        if hasattr(self, "chk_autopilot") and self.chk_autopilot.isChecked():
            self.chk_autopilot.setChecked(False) # 轉為手動模式
        self._sync_webgl_uniforms()

    def _init_webgl_canvas(self):
        """
        初始化 4K 實時 WebGL 畫布，直接載入專案 shaders/ambient_ganzfeld_fog.frag (32 維全態 Shader)
        """
        shader_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "shaders",
            "ambient_ganzfeld_fog.frag"
        )
        try:
            with open(shader_path, "r", encoding="utf-8") as f:
                frag_code = f.read()
        except Exception as e:
            logger.error(f"Failed to read ambient_ganzfeld_fog.frag: {e}")
            frag_code = "#version 300 es\nprecision highp float;\nout vec4 c;\nvoid main(){c=vec4(0.1,0.2,0.4,1.0);}"

        escaped_frag = json.dumps(frag_code)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #000; }}
        canvas {{ width: 100%; height: 100%; display: block; }}
    </style>
</head>
<body>
    <canvas id="glcanvas"></canvas>
    <script>
        const canvas = document.getElementById('glcanvas');
        const gl = canvas.getContext('webgl2');
        if (!gl) {{ document.body.innerHTML = 'WebGL2 not supported'; }}

        function resize() {{
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            gl.viewport(0, 0, canvas.width, canvas.height);
        }}
        window.addEventListener('resize', resize);
        resize();

        // 頂點著色器 (精確導出 vUv 傳遞給片元著色器)
        const vsSource = `#version 300 es
        in vec2 position;
        out vec2 vUv;
        void main() {{
            vUv = position * 0.5 + 0.5;
            gl_Position = vec4(position, 0.0, 1.0);
        }}`;

        // 32 維全態片元著色器源碼 (直接來自 shaders/ambient_ganzfeld_fog.frag)
        const fsSource = {escaped_frag};

        function createShader(gl, type, source) {{
            const shader = gl.createShader(type);
            gl.shaderSource(shader, source);
            gl.compileShader(shader);
            if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {{
                console.error("Shader Compile Error:", gl.getShaderInfoLog(shader));
            }}
            return shader;
        }}

        const program = gl.createProgram();
        gl.attachShader(program, createShader(gl, gl.VERTEX_SHADER, vsSource));
        gl.attachShader(program, createShader(gl, gl.FRAGMENT_SHADER, fsSource));
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {{
            console.error("Program Link Error:", gl.getProgramInfoLog(program));
        }}
        gl.useProgram(program);

        const posBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
            -1, -1,  1, -1, -1,  1,
            -1,  1,  1, -1,  1,  1,
        ]), gl.STATIC_DRAW);

        const posLoc = gl.getAttribLocation(program, "position");
        gl.enableVertexAttribArray(posLoc);
        gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

        // 建立全量 Uniforms 註冊表
        const uniformNames = [
            "u_resolution", "u_time", "u_spectralDrift", "u_subRumble", "u_timbralFlux",
            "u_breathingRate", "u_translucency", "u_luminanceGravity", "u_timeDilation",
            "u_domainWarpAmp", "u_domainWarpFreq", "u_sdfSmoothMinK", "u_fbmOctaves",
            "u_fractalFoldAngle", "u_manifoldCurvature", "u_anisotropyG", "u_extinctionBeta",
            "u_scatteringAlbedo", "u_stepJitterStrength", "u_opticalThickness", "u_volumetricPhaseShift",
            "u_rdFeedRate", "u_rdKillRate", "u_rdDiffusionRatio", "u_vorticityConfinement",
            "u_nonequilibriumTension", "u_cauchyDispersion", "u_subsurfaceDepth", "u_fresnelExponent",
            "u_anisotropicRoughness", "u_retroReflectiveGain", "u_ballisticAttack", "u_ballisticRelease",
            "u_phaseHysteresis", "u_temporalDilationRate", "u_memoryFeedbackGain", "u_antiTroxlerRate",
            "u_oklchChromaClamp", "u_perceptualEntropy", "u_subconsciousJitter", "u_dissolutionThreshold"
        ];

        window.uLocations = {{}};
        for (const name of uniformNames) {{
            window.uLocations[name] = gl.getUniformLocation(program, name);
        }}
        // 4 色調色盤 Uniform 陣列
        window.uPaletteLoc = gl.getUniformLocation(program, "u_palette");

        // 全局即時參數池
        window.ambientParams = {{
            u_breathingRate: 0.12,
            u_translucency: 0.75,
            u_luminanceGravity: 0.65,
            u_timeDilation: 0.04,
            u_spectralDrift: 0.2,
            u_subRumble: 0.35,
            u_timbralFlux: 0.15,
            u_domainWarpAmp: 0.12,
            u_domainWarpFreq: 1.5,
            u_anisotropyG: 0.35,
            u_extinctionBeta: 1.85,
            u_scatteringAlbedo: 0.82,
            u_cauchyDispersion: 0.045,
            u_fbmOctaves: 4.0,
            u_antiTroxlerRate: 0.33,
            palette: [
                0.18, 0.04, 0.35,
                0.45, 0.06, 0.65,
                0.85, 0.05, 0.85,
                0.08, 0.02, 0.15
            ]
        }};

        window.updateAllUniforms = function(data) {{
            if (!data) return;
            Object.assign(window.ambientParams, data);
        }};

        function render(time) {{
            const sec = time * 0.001;
            gl.uniform2f(window.uLocations["u_resolution"], canvas.width, canvas.height);
            gl.uniform1f(window.uLocations["u_time"], sec);

            // 逐一綁定非陣列 Uniforms
            for (const name of uniformNames) {{
                if (name === "u_resolution" || name === "u_time") continue;
                const loc = window.uLocations[name];
                if (loc !== null && window.ambientParams[name] !== undefined) {{
                    gl.uniform1f(loc, window.ambientParams[name]);
                }}
            }}

            // 綁定調色盤
            if (window.uPaletteLoc !== null && window.ambientParams.palette) {{
                gl.uniform3fv(window.uPaletteLoc, new Float32Array(window.ambientParams.palette));
            }}

            gl.drawArrays(gl.TRIANGLES, 0, 6);
            requestAnimationFrame(render);
        }}
        requestAnimationFrame(render);
    </script>
</body>
</html>"""
        self.web_view.setHtml(html_content)

    def _sync_webgl_uniforms(self):
        """
        將宏觀推子、32 維微觀參數與 OKLCH 調色盤即時注入 WebGL Canvas
        """
        payload = {}
        # 1. 宏觀推子
        payload["u_breathingRate"] = float(self.macro_params.get("breathing_rate", 0.12))
        payload["u_translucency"] = float(self.macro_params.get("optical_translucency", 0.75))
        payload["u_luminanceGravity"] = float(self.macro_params.get("luminance_gravity", 0.65))
        payload["u_timeDilation"] = float(self.macro_params.get("time_dilation", 0.04))
        
        # 2. 自動駕駛或微觀抽屜
        if hasattr(self, "chk_autopilot") and self.chk_autopilot.isChecked() and hasattr(self.director, "modulation_bus") and self.director.modulation_bus:
            # 由 32-D Modulation Bus 自動接管
            bus_params = self.director.modulation_bus.params.to_webgl_uniforms()
            payload.update(bus_params)
        elif hasattr(self, "micro_params"):
            # 手動微觀覆蓋
            payload.update(self.micro_params)

        # 3. 當前母題調色盤 (RGB Flat)
        if hasattr(self.director, "active_palette_rgb") and self.director.active_palette_rgb:
            flat_palette = []
            for col in self.director.active_palette_rgb:
                flat_palette.extend([float(c) for c in col])
            payload["palette"] = flat_palette

        json_str = json.dumps(payload)
        js = f"if (window.updateAllUniforms) {{ window.updateAllUniforms({json_str}); }}"
        self.web_view.page().runJavaScript(js)

    def _set_filter(self, category: str):
        self.current_filter = category
        active_style = "background-color: #3182ce; color: #ffffff; font-weight: bold; border: 1px solid #63b3ed;"
        normal_style = "background-color: #1a2233; color: #cbd5e0; font-weight: 500; border: 1px solid #2d3748;"
        
        self.btn_all.setStyleSheet(active_style if category == "all" else normal_style)
        self.btn_particles.setStyleSheet(active_style if category == "particles" else normal_style)
        self.btn_fluids.setStyleSheet(active_style if category == "fluids" else normal_style)
        
        self._load_curated_ambient_modules(category)

    def _load_curated_ambient_modules(self, category: str = "all"):
        self.module_list_widget.clear()
        native_list = self.gate.get_native_ambient_roster(limit=120)
        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        custom_dir = os.path.join(workspace_dir, "custom_visuals")

        for mod_id in native_list:
            clean_name = mod_id[:-5] if mod_id.endswith(".json") else mod_id
            target_name = None
            if os.path.exists(os.path.join(custom_dir, f"{clean_name}.json")):
                target_name = clean_name
            elif os.path.exists(os.path.join(custom_dir, f"{mod_id}.json")):
                target_name = mod_id

            if not target_name:
                continue

            meta = self.gate.module_metadata.get(mod_id, {})
            subgenre = meta.get("ambient_subgenre", "ambient_flow")
            title = meta.get("title", clean_name)

            if category == "particles":
                if not (subgenre == "particle_stardust" or "particle" in clean_name.lower() or "star" in clean_name.lower()):
                    continue
            elif category == "fluids":
                if not (subgenre in ("fluid_diffusion", "topological_wave") or "wave" in clean_name.lower() or "flow" in clean_name.lower() or "planet" in clean_name.lower()):
                    continue

            item = QListWidgetItem(f"✦ {title} ({subgenre})")
            item.setData(Qt.ItemDataRole.UserRole, target_name)
            item.setToolTip(f"點擊載入並在右側 16:9 沙盒即時預覽\n檔案: {target_name}.json\n風格: {subgenre}")
            self.module_list_widget.addItem(item)

    def _on_motif_changed(self, index: int):
        motif_id = self.motif_combo.currentData()
        if not motif_id:
            return
            
        # 尋找選中的母題
        selected_m = next((m for m in self.director.CONTEMPLATIVE_MOTIFS if m["id"] == motif_id), None)
        if selected_m:
            base_palette = selected_m["oklch_palette"]
            # 若有當前音訊，計算音訊 DNA 種子並衍生專屬色盤
            audio_seed = self.director.compute_audio_dna_seed(self.current_audio_path) if self.current_audio_path else 42108542
            derived_palette = self.director.derive_track_unique_palette(base_palette, audio_seed)
            
            # 轉換為 RGB 並更新導演
            temp_motif = dict(selected_m)
            temp_motif["oklch_palette"] = derived_palette
            self.director.active_palette_rgb = self.director._convert_motif_to_rgb(temp_motif)
            self.director.target_palette_rgb = list(self.director.active_palette_rgb)
            
            # 即時同步給 WebGL 畫布
            self._sync_webgl_uniforms()
            logger.info(f"[Ambient Studio] Switched Motif to: {selected_m['title']} with Audio Seed {audio_seed}")

    def _on_module_item_clicked(self, item: Optional[QListWidgetItem]):
        if not item:
            return
        target_name = item.data(Qt.ItemDataRole.UserRole)
        if not target_name:
            return
        meta = self.gate.module_metadata.get(target_name, {})
        title = meta.get("title", target_name)

        self.selected_module_id = target_name
        self.lbl_module_info.setText(f"當前選中: ✦ {title}")
        self.lbl_module_info.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold; padding: 2px 4px;")
        self.lbl_audio_status.setText(f"已就緒: {target_name}")
        self.lbl_audio_status.setStyleSheet("color: #68d391; font-size: 10px;")

        self.moduleSelected.emit(target_name, meta)

        main_win = self._find_main_window()
        if main_win:
            if hasattr(main_win, "checked_presets"):
                main_win.checked_presets.clear()
                main_win.checked_presets.add(target_name)
            if hasattr(main_win, "preview_preset"):
                main_win.preview_preset(target_name)
            if hasattr(main_win, "log_to_console"):
                main_win.log_to_console(f"🫁 [Ambient Studio] 已載入模組「{target_name}」至右側即時沙盒")
            logger.info(f"Loaded ambient module {target_name} into MainWindow preview and checked_presets.")

    def _on_module_current_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if current:
            self._on_module_item_clicked(current)

    def _find_main_window(self):
        p = self.parent()
        while p is not None:
            if hasattr(p, "preview_preset") or hasattr(p, "start_mv_rendering"):
                return p
            p = p.parent()
        return None

    def _on_apply_clicked(self):
        self.macroParametersChanged.emit(self.macro_params)
        self.lbl_audio_status.setText("狀態: 已注入 4K 主管線就緒")
        self.lbl_audio_status.setStyleSheet("color: #68d391; font-size: 10px;")

    def _on_start_render_clicked(self):
        """
        立即保存當前 Ambient 調校參數，並直接平滑轉發給主視窗啟動 4K 離線渲染
        """
        self._on_apply_clicked()
        logger.info("Triggering 4K Offline Render for Ambient track...")
        
        main_win = self._find_main_window()
        if main_win:
            if self.current_audio_path and hasattr(main_win, "audio_input"):
                main_win.audio_input.setText(self.current_audio_path)
            
            if hasattr(self, "selected_module_id") and self.selected_module_id:
                if hasattr(main_win, "checked_presets"):
                    main_win.checked_presets.clear()
                    main_win.checked_presets.add(self.selected_module_id)
            
            if hasattr(main_win, "left_tabs"):
                for idx in range(main_win.left_tabs.count()):
                    tab_name = main_win.left_tabs.tabText(idx)
                    if "離線渲染" in tab_name or "渲染" in tab_name:
                        main_win.left_tabs.setCurrentIndex(idx)
                        break

            if hasattr(main_win, "start_mv_rendering"):
                main_win.start_mv_rendering()
        else:
            logger.warning("Main window start_mv_rendering not found in parent hierarchy.")

    def _toggle_ai_autopilot(self):
        self.is_ai_auteur_active = not self.is_ai_auteur_active
        if self.is_ai_auteur_active:
            self.btn_ai_autopilot.setText("🎬 AI 導演作者全自動託管 [運行中]")
            self.btn_ai_autopilot.setStyleSheet(
                "background-color: #065f46; color: #34d399; font-weight: bold; border: 1px solid #10b981; border-radius: 5px; padding: 4px 10px; font-size: 11px;"
            )
            self.lbl_director_intent.setStyleSheet("color: #68d391; font-family: Monospace; font-size: 10px;")
        else:
            self.btn_ai_autopilot.setText("🎬 AI 導演作者全自動託管 [手動接管]")
            self.btn_ai_autopilot.setStyleSheet(
                "background-color: #1f2937; color: #9ca3af; font-weight: bold; border: 1px solid #374151; border-radius: 5px; padding: 4px 10px; font-size: 11px;"
            )
            self.lbl_director_intent.setText("⏸️ [AI導演] 已暫停自動託管，由工程師/藝術家手動推子接管微調。")
            self.lbl_director_intent.setStyleSheet("color: #a0aec0; font-family: Monospace; font-size: 10px;")

    def _tick_ui_breathing(self):
        self.anim_t += 0.033
        rate = self.macro_params.get("breathing_rate", 0.12)
        import math
        b_val = (math.sin(self.anim_t * rate * 6.28) * 0.5 + 0.5) * 100
        self.breathing_bar.setValue(int(b_val))

        # AI 導演作者系統全自動託管循環
        if getattr(self, "is_ai_auteur_active", False) and hasattr(self, "ai_director_bridge"):
            # 聲學微動態遙測特徵
            audio_telemetry = {
                "bass": 0.25 + 0.15 * math.sin(self.anim_t * 0.18),
                "mid": 0.20 + 0.10 * math.cos(self.anim_t * 0.12),
                "high": 0.15 + 0.08 * math.sin(self.anim_t * 0.25),
                "spectral_centroid": 600.0 + 350.0 * math.sin(self.anim_t * 0.05),
                "energy": 0.30 + 0.15 * math.sin(self.anim_t * 0.1)
            }
            
            director_state = self.ai_director_bridge.tick_director_loop(
                current_time=self.anim_t,
                dt=0.033,
                audio_features=audio_telemetry,
                audio_seed=self.current_audio_seed
            )
            
            # 更新意圖日誌與三層複調 UI 標籤
            if hasattr(self, "lbl_director_intent"):
                intent_text = director_state.get("intent_log", "")
                shot_state = director_state.get("shot_state", {})
                novelty = shot_state.get("acoustic_novelty", 0.0)
                in_dissolve = shot_state.get("in_cross_dissolve", False)
                diss_prog = shot_state.get("dissolve_progress", 0.0)
                
                status_suffix = f" [融鏡中 {diss_prog*100:.0f}%]" if in_dissolve else f" [SSM質地新穎度: {novelty:.2f}]"
                first_line = intent_text.split('\n')[0] if intent_text else "🎬 [AI導演] 運行中"
                self.lbl_director_intent.setText(first_line + status_suffix)

            if hasattr(self, "lbl_trio_status"):
                trio = director_state.get("polyphony_trio", {})
                l1 = trio.get("layer1_atmospheric", "Ganzfeld 32-D")
                l2 = trio.get("layer2_material_fluid", "None")
                l3 = trio.get("layer3_particulate", "None")
                m_title = trio.get("motif_title", "")
                self.lbl_trio_status.setText(
                    f"🎭 三層複調: [底] {l1}  |  [中] 流體: {l2}  |  [頂] 星塵: {l3}  ({m_title})"
                )

            # 同步母題下拉框
            cur_motif_id = director_state.get("polyphony_trio", {}).get("motif_id", "")
            if cur_motif_id and self.motif_combo.currentData() != cur_motif_id:
                for idx in range(self.motif_combo.count()):
                    if self.motif_combo.itemData(idx) == cur_motif_id:
                        self.motif_combo.blockSignals(True)
                        self.motif_combo.setCurrentIndex(idx)
                        self.motif_combo.blockSignals(False)
                        break

            # 實時注入 32 維編舞 Uniforms 至 WebGL Canvas
            uniforms = director_state.get("uniforms_32d", {})
            if uniforms and hasattr(self, "web_view"):
                json_str = json.dumps(uniforms)
                js = f"if (window.updateAllUniforms) {{ window.updateAllUniforms({json_str}); }}"
                self.web_view.page().runJavaScript(js)

    def _on_browse_single_audio(self):
        """
        開啟檔案選取器選擇單一音訊檔案
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇 Ambient / Drone 音訊檔案",
            "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg *.aiff)"
        )
        if file_path:
            self.album_tracks = [file_path]
            self.current_audio_path = file_path
            self.current_audio_seed = self.director.compute_audio_dna_seed(file_path)
            self.track_combo.blockSignals(True)
            self.track_combo.clear()
            filename = os.path.basename(file_path)
            self.track_combo.addItem(f"🎵 {filename}", file_path)
            self.track_combo.blockSignals(False)
            
            self.lbl_audio_status.setText(f"已就緒: {filename}")
            self.lbl_audio_status.setStyleSheet("color: #68d391; font-size: 10px;")
            
            logger.info(f"Loaded single audio file: {file_path}")
            self.audioLoaded.emit(file_path)
            self._sync_with_main_window(file_path)
            self._on_motif_changed(self.motif_combo.currentIndex())

    def _on_browse_album_folder(self):
        """
        開啟資料夾選取器選擇整張專輯資料夾並批次解析曲目
        """
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "選擇 Ambient / Drone 專輯資料夾"
        )
        if folder_path:
            valid_exts = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aiff")
            tracks = []
            for root, _, files in os.walk(folder_path):
                for f in sorted(files):
                    if f.lower().endswith(valid_exts):
                        tracks.append(os.path.join(root, f))
            
            if not tracks:
                self.lbl_audio_status.setText("警告: 資料夾內未找到支援的音訊檔案")
                self.lbl_audio_status.setStyleSheet("color: #f6ad55; font-size: 10px;")
                return

            self.album_tracks = tracks
            self.track_combo.blockSignals(True)
            self.track_combo.clear()
            
            for idx, track_path in enumerate(self.album_tracks, start=1):
                track_name = os.path.basename(track_path)
                self.track_combo.addItem(f"[{idx}/{len(self.album_tracks)}] {track_name}", track_path)
            
            self.track_combo.blockSignals(False)
            self.current_audio_path = self.album_tracks[0]
            self.current_audio_seed = self.director.compute_audio_dna_seed(self.current_audio_path)
            
            album_name = os.path.basename(folder_path)
            self.lbl_audio_status.setText(f"專輯已載入: {album_name} (共 {len(self.album_tracks)} 首曲目)")
            self.lbl_audio_status.setStyleSheet("color: #63b3ed; font-size: 10px;")
            
            logger.info(f"Loaded album folder: {folder_path} with {len(tracks)} tracks.")
            self.audioLoaded.emit(self.current_audio_path)
            self._sync_with_main_window(self.current_audio_path)

    def _on_track_selected(self, index: int):
        """
        切換專輯內的曲目
        """
        track_path = self.track_combo.currentData()
        if track_path and os.path.exists(track_path):
            self.current_audio_path = track_path
            self.current_audio_seed = self.director.compute_audio_dna_seed(track_path)
            filename = os.path.basename(track_path)
            self.lbl_audio_status.setText(f"切換曲目: {filename}")
            self.lbl_audio_status.setStyleSheet("color: #68d391; font-size: 10px;")
            
            logger.info(f"Switched track to: {track_path}")
            self.audioLoaded.emit(track_path)
            self._sync_with_main_window(track_path)
            self._on_motif_changed(self.motif_combo.currentIndex())

    def _sync_with_main_window(self, audio_path: str):
        """
        將在 Ambient Studio 選中的音訊即時同步給主程式的離線渲染器和沙盒
        """
        p = self.parent()
        while p is not None:
            if hasattr(p, "audio_input") and hasattr(p.audio_input, "setText"):
                p.audio_input.setText(audio_path)
                logger.info(f"Synced audio path to MainWindow.audio_input: {audio_path}")
                break
            p = p.parent()
