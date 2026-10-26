# -*- coding: utf-8 -*-
"""
SENTINEL-CHRONOS: Dedicated Visual Module Library Hub Tab (custom_visuals/ Hub)
-------------------------------------------------------------------------------
專屬 UI TAB：全庫 4,500+ 款視覺模組資產管理、分類檢索、即時沙盒預覽與時空隧道突變器。
"""

import os
import json
import logging
import subprocess
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QFrame, QSplitter, QProgressBar, QSizePolicy, QScrollArea,
    QTextEdit, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QPixmap, QIcon

logger = logging.getLogger("VisualStudio.CustomVisualsLibraryTab")


class ModuleCardWidget(QFrame):
    """
    視覺模組卡片元件 (支援網格與列表檢視)
    """
    previewClicked = pyqtSignal(str)
    starToggled = pyqtSignal(str, bool)
    editClicked = pyqtSignal(str)

    def __init__(self, data: Dict[str, Any], is_grid_mode: bool = True, parent=None):
        super().__init__(parent)
        self.data = data
        self.module_name = data.get("name", "")
        self.is_grid_mode = is_grid_mode
        self.is_starred = data.get("is_starred", False)
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("ModuleCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        star_border = "border: 1px solid rgba(245, 158, 11, 0.45);" if self.is_starred else "border: 1px solid #27272a;"
        self.setStyleSheet(f"""
            QFrame#ModuleCard {{
                background-color: #121217;
                border-radius: 8px;
                {star_border}
            }}
            QFrame#ModuleCard:hover {{
                background-color: #181820;
                border: 1px solid #38bdf8;
            }}
        """)

        layout = QVBoxLayout(self) if self.is_grid_mode else QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 縮圖 / 徽章
        self.thumb_label = QLabel(self)
        if self.is_grid_mode:
            self.thumb_label.setFixedSize(160, 90)
        else:
            self.thumb_label.setFixedSize(110, 62)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background-color: #09090c; border-radius: 6px; border: 1px solid #1f1f23;")

        thumb_path = self.data.get("thumbnail_path", "")
        if thumb_path and os.path.exists(thumb_path):
            pix = QPixmap(thumb_path)
            if not pix.isNull():
                self.thumb_label.setPixmap(pix.scaled(
                    self.thumb_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self._draw_fallback_thumb()
        else:
            self._draw_fallback_thumb()

        layout.addWidget(self.thumb_label)

        # 資訊區
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(3)

        # 標題與星標行
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        
        display_name = self.data.get("display_name") or self.module_name
        self.lbl_title = QLabel(display_name, self)
        self.lbl_title.setStyleSheet("color: #f4f4f5; font-weight: bold; font-size: 11px;")
        self.lbl_title.setToolTip(f"{display_name} ({self.module_name}.json)")
        title_row.addWidget(self.lbl_title, stretch=1)

        # Ambient 徽章
        amb_tier = self.data.get("ambient_tier", "RED")
        if amb_tier == "GREEN":
            amb_badge = QLabel("🌿", self)
            amb_badge.setToolTip("Ambient 原生相容模組 (Green Tier)")
            title_row.addWidget(amb_badge)
        elif amb_tier == "YELLOW":
            amb_badge = QLabel("⚡", self)
            amb_badge.setToolTip("Ambient 阻尼調製模組 (Yellow Tier)")
            title_row.addWidget(amb_badge)

        # 星標按鈕
        self.btn_star = QPushButton("★" if self.is_starred else "☆", self)
        self.btn_star.setFixedSize(22, 22)
        star_col = "#f59e0b" if self.is_starred else "#71717a"
        self.btn_star.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {star_col};
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: #fbbf24;
            }}
        """)
        self.btn_star.clicked.connect(self._toggle_star)
        title_row.addWidget(self.btn_star)
        info_layout.addLayout(title_row)

        # 標籤顯示 (最多前 3 個)
        tags = self.data.get("tags", [])
        if tags:
            tag_str = " · ".join([f"#{t}" for t in tags[:3]])
            lbl_tags = QLabel(tag_str, self)
            lbl_tags.setStyleSheet("color: #71717a; font-size: 10px;")
            info_layout.addWidget(lbl_tags)

        # 權重與使用次數
        weight = self.data.get("storyboard_weight", 50)
        used = self.data.get("used_count", 0)
        meta_lbl = QLabel(f"權重: {weight} | 使用: {used} 次", self)
        meta_lbl.setStyleSheet("color: #52525b; font-size: 10px;")
        info_layout.addWidget(meta_lbl)

        # 操作按鈕列
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        
        btn_preview = QPushButton("⚡ 預覽", self)
        btn_preview.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #38bdf8;
                color: #38bdf8;
                font-size: 10px;
                font-weight: bold;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        btn_preview.clicked.connect(lambda: self.previewClicked.emit(self.module_name))
        btn_row.addWidget(btn_preview, stretch=1)

        btn_edit = QPushButton("📝 編輯", self)
        btn_edit.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #d4d4d8;
                font-size: 10px;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #ffffff;
            }
        """)
        btn_edit.clicked.connect(lambda: self.editClicked.emit(self.module_name))
        btn_row.addWidget(btn_edit, stretch=1)

        info_layout.addLayout(btn_row)
        layout.addLayout(info_layout)

    def _draw_fallback_thumb(self):
        # 繪製代表性漸層圖示
        import hashlib
        h = int(hashlib.md5(self.module_name.encode('utf-8')).hexdigest(), 16)
        hue = h % 360
        self.thumb_label.setText(self.module_name[:2].upper())
        self.thumb_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 hsla({hue}, 60%, 20%, 1.0), stop:1 hsla({(hue+60)%360}, 50%, 10%, 1.0));
                color: hsla({hue}, 90%, 80%, 0.85);
                font-size: 20px;
                font-weight: bold;
                border-radius: 6px;
                border: 1px solid hsla({hue}, 50%, 30%, 0.5);
            }}
        """)

    def _toggle_star(self):
        self.is_starred = not self.is_starred
        star_col = "#f59e0b" if self.is_starred else "#71717a"
        self.btn_star.setText("★" if self.is_starred else "☆")
        self.btn_star.setStyleSheet(f"background: transparent; border: none; color: {star_col}; font-size: 14px; font-weight: bold;")
        self.starToggled.emit(self.module_name, self.is_starred)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.previewClicked.emit(self.module_name)
        super().mousePressEvent(event)


class CustomVisualsLibraryTab(QWidget):
    """
    專屬 UI TAB：4,500+ 款視覺模組資產庫管理與即時沙盒調度工作台
    """
    moduleSelected = pyqtSignal(str)
    editModuleRequested = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.workspace_dir = os.path.dirname(os.path.abspath(__file__))
        self.custom_visuals_dir = os.path.join(self.workspace_dir, "custom_visuals")
        os.makedirs(self.custom_visuals_dir, exist_ok=True)

        self.all_presets: List[Dict[str, Any]] = []
        self.filtered_presets: List[Dict[str, Any]] = []
        self.current_page = 1
        self.page_size = 48
        self.max_pages = 1
        self.selected_module_name: Optional[str] = None
        self.view_mode = 0  # 0: 網格卡片, 1: 詳細列表

        self._init_ui()
        self.reload_library()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ── 1. 頂部標題與快速操作列 ──
        header_bar = QHBoxLayout()
        header_bar.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("📦 視覺模組資產庫 (custom_visuals/ Hub)", self)
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        self.lbl_subtitle = QLabel("實時檢索、星標收藏、沙盒預覽與時空隧道突變器", self)
        self.lbl_subtitle.setStyleSheet("color: #71717a; font-size: 11px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        header_bar.addLayout(title_box, stretch=1)

        # 🌀 實例化新時空隧道突變按鈕
        self.btn_mutate_spacetime = QPushButton("🌀 突變新時空隧道", self)
        self.btn_mutate_spacetime.setToolTip("隨機突變並生成全新形態的 HyperSpacetimeConduit 時空隧道並在沙盒中啟動")
        self.btn_mutate_spacetime.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #ec4899);
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #c084fc;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a855f7, stop:1 #f43f5e);
            }
        """)
        self.btn_mutate_spacetime.clicked.connect(self._on_mutate_spacetime_clicked)
        header_bar.addWidget(self.btn_mutate_spacetime)

        # 🔄 重新整理按鈕
        btn_refresh = QPushButton("🔄 重新整理", self)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #e4e4e7;
                font-size: 11px;
                padding: 6px 10px;
                border-radius: 6px;
                border: 1px solid #3f3f46;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_refresh.clicked.connect(self.reload_library)
        header_bar.addWidget(btn_refresh)

        # 📂 開啟資料夾按鈕
        btn_open_folder = QPushButton("📁 開啟目錄", self)
        btn_open_folder.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #e4e4e7;
                font-size: 11px;
                padding: 6px 10px;
                border-radius: 6px;
                border: 1px solid #3f3f46;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_open_folder.clicked.connect(self._open_custom_visuals_folder)
        header_bar.addWidget(btn_open_folder)

        main_layout.addLayout(header_bar)

        # ── 2. 統計數據資訊條 ──
        stats_bar = QHBoxLayout()
        stats_bar.setSpacing(8)
        self.lbl_stat_total = QLabel("📊 總庫存: 0", self)
        self.lbl_stat_total.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold; background: rgba(56,189,248,0.1); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(56,189,248,0.25);")
        
        self.lbl_stat_starred = QLabel("⭐ 最愛: 0", self)
        self.lbl_stat_starred.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold; background: rgba(251,191,36,0.1); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(251,191,36,0.25);")

        self.lbl_stat_ambient = QLabel("🌿 Ambient: 0", self)
        self.lbl_stat_ambient.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold; background: rgba(52,211,153,0.1); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(52,211,153,0.25);")

        self.lbl_stat_conduit = QLabel("🌀 時空隧道: 1", self)
        self.lbl_stat_conduit.setStyleSheet("color: #c084fc; font-size: 11px; font-weight: bold; background: rgba(192,132,252,0.1); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(192,132,252,0.25);")

        stats_bar.addWidget(self.lbl_stat_total)
        stats_bar.addWidget(self.lbl_stat_starred)
        stats_bar.addWidget(self.lbl_stat_ambient)
        stats_bar.addWidget(self.lbl_stat_conduit)
        stats_bar.addStretch()
        main_layout.addLayout(stats_bar)

        # ── 3. 搜尋、分類與排序過濾列 ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        # 搜尋輸入框
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 搜尋名稱、#標籤、作者或檔案名稱...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
        """)
        self.search_input.textChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self.search_input, stretch=2)

        # 類別過濾下拉選單
        self.category_select = QComboBox(self)
        self.category_select.addItems([
            "🌟 全部品類 (All Categories)",
            "⭐ 我的最愛 (Favorites)",
            "🌀 時空隧道與蟲洞 (Spacetime & Wormhole)",
            "🌌 粒子系統 (Particles)",
            "🌊 流體與渦流 (Fluids)",
            "🫁 Ambient 靜謐心流 (Ambient Compatible)",
            "⚡ Hard Techno 工業硬核 (Hard Techno)",
            "📐 3D 與幾何網格 (3D & Geometry)",
            "🔮 著色器與碎形 (Shaders & Fractals)",
            "👾 像素與復古 (Pixel & Retro)"
        ])
        self.category_select.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)
        self.category_select.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self.category_select)

        # 排序方式下拉選單
        self.sort_select = QComboBox(self)
        self.sort_select.addItems([
            "⭐ 我的最愛優先",
            "🕒 最近新增/修改優先",
            "🔤 模組名稱 (A-Z)",
            "📈 歷史使用次數",
            "⚖️ 分鏡權重 (從大到小)"
        ])
        self.sort_select.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)
        self.sort_select.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self.sort_select)

        # 視圖模式
        self.view_mode_select = QComboBox(self)
        self.view_mode_select.addItems(["🎨 網格卡片", "📝 詳細列表"])
        self.view_mode_select.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)
        self.view_mode_select.currentIndexChanged.connect(self._on_view_mode_changed)
        filter_bar.addWidget(self.view_mode_select)

        main_layout.addLayout(filter_bar)

        # ── 4. 主內容工作區：Splitter (左側卡片網格 + 右側模組詳細檢查器) ──
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setHandleWidth(4)

        # 模組清單容器 (左側)
        list_container = QWidget(self)
        list_vbox = QVBoxLayout(list_container)
        list_vbox.setContentsMargins(0, 0, 0, 0)
        list_vbox.setSpacing(6)

        self.list_widget = QListWidget(list_container)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #09090b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item:selected {
                background: transparent;
                border: none;
            }
            QListWidget::item:hover {
                background: transparent;
                border: none;
            }
        """)
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        list_vbox.addWidget(self.list_widget, stretch=1)

        # 分頁導航列
        page_bar = QHBoxLayout()
        page_bar.setSpacing(8)
        self.btn_prev_page = QPushButton("◀ 上一頁", list_container)
        self.btn_prev_page.clicked.connect(self._prev_page)
        self.lbl_page_info = QLabel("第 1 頁 / 共 1 頁", list_container)
        self.lbl_page_info.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.btn_next_page = QPushButton("下一頁 ▶", list_container)
        self.btn_next_page.clicked.connect(self._next_page)

        page_btn_style = """
            QPushButton {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                color: #e4e4e7;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #27272a;
            }
            QPushButton:disabled {
                color: #52525b;
                border-color: #27272a;
            }
        """
        self.btn_prev_page.setStyleSheet(page_btn_style)
        self.btn_next_page.setStyleSheet(page_btn_style)

        page_bar.addWidget(self.btn_prev_page)
        page_bar.addWidget(self.lbl_page_info)
        page_bar.addWidget(self.btn_next_page)
        page_bar.addStretch()
        list_vbox.addLayout(page_bar)

        self.splitter.addWidget(list_container)

        # 右側模組檢查器 (Inspector Panel)
        self.inspector_panel = QFrame(self)
        self.inspector_panel.setObjectName("InspectorPanel")
        self.inspector_panel.setStyleSheet("""
            QFrame#InspectorPanel {
                background-color: #0d0e12;
                border: 1px solid #27272a;
                border-radius: 8px;
            }
        """)
        self._init_inspector_ui()
        self.splitter.addWidget(self.inspector_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        main_layout.addWidget(self.splitter, stretch=1)

    def _init_inspector_ui(self):
        insp_layout = QVBoxLayout(self.inspector_panel)
        insp_layout.setContentsMargins(12, 12, 12, 12)
        insp_layout.setSpacing(8)

        lbl_insp_title = QLabel("🔍 模組屬性檢查器 (Inspector)", self.inspector_panel)
        lbl_insp_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #a1a1aa;")
        insp_layout.addWidget(lbl_insp_title)

        # 大縮圖
        self.insp_thumb = QLabel(self.inspector_panel)
        self.insp_thumb.setFixedHeight(120)
        self.insp_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.insp_thumb.setStyleSheet("background-color: #09090b; border-radius: 6px; border: 1px solid #1f1f23;")
        insp_layout.addWidget(self.insp_thumb)

        # 模組名稱
        self.insp_name = QLabel("未選擇模組", self.inspector_panel)
        self.insp_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #f4f4f5;")
        self.insp_name.setWordWrap(True)
        insp_layout.addWidget(self.insp_name)

        # 元數據標籤
        self.insp_meta = QLabel("作者: - | 授權: - | 日期: -", self.inspector_panel)
        self.insp_meta.setStyleSheet("color: #71717a; font-size: 10px;")
        self.insp_meta.setWordWrap(True)
        insp_layout.addWidget(self.insp_meta)

        # 標籤列表
        self.insp_tags = QLabel("標籤: -", self.inspector_panel)
        self.insp_tags.setStyleSheet("color: #38bdf8; font-size: 10px;")
        self.insp_tags.setWordWrap(True)
        insp_layout.addWidget(self.insp_tags)

        # 參數數值
        self.insp_params = QLabel("分鏡權重: - | 頻率: - | 後製強度: -", self.inspector_panel)
        self.insp_params.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        insp_layout.addWidget(self.insp_params)

        # 程式碼摘要預覽
        lbl_code = QLabel("📄 程式碼速覽 (First 30 Lines):", self.inspector_panel)
        lbl_code.setStyleSheet("color: #71717a; font-size: 10px; font-weight: bold;")
        insp_layout.addWidget(lbl_code)

        self.insp_code_preview = QTextEdit(self.inspector_panel)
        self.insp_code_preview.setReadOnly(True)
        self.insp_code_preview.setStyleSheet("""
            QTextEdit {
                background-color: #070709;
                color: #a1a1aa;
                border: 1px solid #1f1f23;
                border-radius: 4px;
                font-family: 'Consolas', 'Menlo', 'Courier New', monospace;
                font-size: 10px;
            }
        """)
        insp_layout.addWidget(self.insp_code_preview, stretch=1)

        # 底部操作按鈕
        self.btn_insp_preview = QPushButton("🌐 啟動 16:9 沙盒即時預覽", self.inspector_panel)
        self.btn_insp_preview.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 7px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_insp_preview.clicked.connect(self._preview_current_inspector)
        insp_layout.addWidget(self.btn_insp_preview)

        self.btn_insp_edit = QPushButton("✏️ 載入至程式碼編輯器", self.inspector_panel)
        self.btn_insp_edit.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #e4e4e7;
                font-size: 11px;
                padding: 6px;
                border-radius: 6px;
                border: 1px solid #3f3f46;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        self.btn_insp_edit.clicked.connect(self._edit_current_inspector)
        insp_layout.addWidget(self.btn_insp_edit)

    # ── 資料載入與篩選 ──
    def reload_library(self):
        """重新載入 custom_visuals/ 模組庫"""
        logger.info("Reloading custom_visuals/ library...")
        presets_data = []

        if not os.path.exists(self.custom_visuals_dir):
            return

        starred_count = 0
        ambient_count = 0
        spacetime_count = 0

        from ambient_module_compatibility_gate import AmbientModuleCompatibilityGate
        gate = AmbientModuleCompatibilityGate.get_instance()

        for file in os.listdir(self.custom_visuals_dir):
            if file.endswith(".json") and file not in ("modules_index.json", "module_usage_history.json"):
                name = file[:-5]
                p_path = os.path.join(self.custom_visuals_dir, file)
                try:
                    with open(p_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict) or "code" not in data:
                        continue
                    
                    tags = data.get("tags", [])
                    is_starred = bool(data.get("is_starred", False))
                    storyboard_weight = data.get("storyboard_weight", 50)
                    used_count = data.get("used_count", 0)

                    if is_starred:
                        starred_count += 1
                    
                    # 統計分類
                    search_txt = f"{name} {' '.join(tags)}".lower()
                    if any(w in search_txt for w in ("spacetime", "tunnel", "wormhole", "hyperspace")):
                        spacetime_count += 1

                    amb_tier = gate.get_module_tier(name, {
                        "name": name, "tags": tags, "storyboard_weight": storyboard_weight
                    })
                    if amb_tier in ("GREEN", "YELLOW"):
                        ambient_count += 1

                    thumb_path = os.path.join(self.custom_visuals_dir, "thumbnails", f"{name}.jpg")
                    presets_data.append({
                        "name": name,
                        "display_name": data.get("display_name", name),
                        "tags": tags,
                        "author": data.get("author", "未知"),
                        "license_mode": data.get("license", "MIT"),
                        "date_added": data.get("date_added", ""),
                        "frequency": data.get("frequency", 50),
                        "storyboard_weight": storyboard_weight,
                        "post_fx_intensity": data.get("post_fx_intensity", 50),
                        "used_count": used_count,
                        "is_starred": is_starred,
                        "ambient_tier": amb_tier,
                        "thumbnail_path": thumb_path if os.path.exists(thumb_path) else "",
                        "file_path": p_path
                    })
                except Exception as e:
                    pass

        self.all_presets = presets_data
        self.lbl_stat_total.setText(f"📊 總庫存: {len(self.all_presets):,} 款")
        self.lbl_stat_starred.setText(f"⭐ 最愛: {starred_count} 款")
        self.lbl_stat_ambient.setText(f"🌿 Ambient: {ambient_count} 款")
        self.lbl_stat_conduit.setText(f"🌀 時空隧道: {spacetime_count} 款")

        self._on_filter_changed()

    def _on_filter_changed(self):
        query = self.search_input.text().strip().lower()
        cat_idx = self.category_select.currentIndex()
        sort_idx = self.sort_select.currentIndex()

        filtered = []
        for p in self.all_presets:
            p_name = p["name"].lower()
            p_disp = p["display_name"].lower()
            p_author = p["author"].lower()
            p_tags = [t.lower() for t in p["tags"]]
            combined = f"{p_name} {p_disp} {p_author} {' '.join(p_tags)}"

            # 關鍵字搜尋
            if query and query not in combined:
                continue

            # 類別過濾
            if cat_idx == 1 and not p["is_starred"]:  # 我的最愛
                continue
            elif cat_idx == 2:  # 時空隧道與蟲洞
                if not any(k in combined for k in ("spacetime", "tunnel", "wormhole", "hyperspace", "conduit")):
                    continue
            elif cat_idx == 3:  # 粒子系統
                if not any(k in combined for k in ("particle", "particles", "stardust", "spark")):
                    continue
            elif cat_idx == 4:  # 流體與渦流
                if not any(k in combined for k in ("fluid", "vortex", "smoke", "flow", "wave")):
                    continue
            elif cat_idx == 5:  # Ambient 靜謐
                if p["ambient_tier"] not in ("GREEN", "YELLOW"):
                    continue
            elif cat_idx == 6:  # Hard Techno
                if not any(k in combined for k in ("hard techno", "techno", "industrial", "strobe", "glitch")):
                    continue
            elif cat_idx == 7:  # 3D 與幾何網格
                if not any(k in combined for k in ("3d", "cube", "sphere", "geometry", "lattice", "grid")):
                    continue
            elif cat_idx == 8:  # 著色器與碎形
                if not any(k in combined for k in ("shader", "fractal", "mandelbrot", "glsl", "raymarch")):
                    continue
            elif cat_idx == 9:  # 像素與復古
                if not any(k in combined for k in ("pixel", "retro", "8bit", "arcade", "dither")):
                    continue

            filtered.append(p)

        # 排序
        if sort_idx == 0:  # ⭐ 我的最愛優先
            filtered.sort(key=lambda x: (not x["is_starred"], x["name"].lower()))
        elif sort_idx == 1:  # 🕒 最近新增/修改
            filtered.sort(key=lambda x: str(x.get("date_added", "")), reverse=True)
        elif sort_idx == 2:  # 🔤 名稱 A-Z
            filtered.sort(key=lambda x: x["name"].lower())
        elif sort_idx == 3:  # 📈 歷史使用次數
            filtered.sort(key=lambda x: int(x.get("used_count", 0)), reverse=True)
        elif sort_idx == 4:  # ⚖️ 分鏡權重
            filtered.sort(key=lambda x: int(x.get("storyboard_weight", 50)), reverse=True)

        self.filtered_presets = filtered
        self.current_page = 1
        self._render_current_page()

    def _on_view_mode_changed(self):
        self.view_mode = self.view_mode_select.currentIndex()
        if self.view_mode == 0:
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setMovement(QListWidget.Movement.Static)
            self.list_widget.setUniformItemSizes(True)
            self.list_widget.setSpacing(10)
        else:
            self.list_widget.setViewMode(QListWidget.ViewMode.ListMode)
            self.list_widget.setSpacing(4)
        self._render_current_page()

    def _render_current_page(self):
        self.list_widget.clear()
        total_items = len(self.filtered_presets)
        import math
        self.max_pages = max(1, math.ceil(total_items / self.page_size))
        self.current_page = max(1, min(self.current_page, self.max_pages))

        self.lbl_page_info.setText(f"第 {self.current_page} 頁 / 共 {self.max_pages} 頁 (每頁 {self.page_size} 款 / 篩選出 {total_items} 款)")
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < self.max_pages)

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_items = self.filtered_presets[start_idx:end_idx]

        for p_data in page_items:
            item = QListWidgetItem(self.list_widget)
            card = ModuleCardWidget(p_data, is_grid_mode=(self.view_mode == 0), parent=self.list_widget)
            card.previewClicked.connect(self._on_module_preview_clicked)
            card.editClicked.connect(self._on_module_edit_clicked)
            card.starToggled.connect(self._on_module_star_toggled)

            if self.view_mode == 0:
                item.setSizeHint(QSize(176, 215))
            else:
                item.setSizeHint(QSize(400, 78))

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)

        # 預設選擇第一項並更新 Inspector
        if page_items and not self.selected_module_name:
            self.update_inspector(page_items[0]["name"])

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_current_page()

    def _next_page(self):
        if self.current_page < self.max_pages:
            self.current_page += 1
            self._render_current_page()

    def _on_item_selected(self, current, previous):
        if not current:
            return
        widget = self.list_widget.itemWidget(current)
        if isinstance(widget, ModuleCardWidget):
            self.update_inspector(widget.module_name)

    def update_inspector(self, module_name: str):
        """更新右側模組檢查器"""
        self.selected_module_name = module_name
        p_path = os.path.join(self.custom_visuals_dir, f"{module_name}.json")
        if not os.path.exists(p_path):
            return

        try:
            with open(p_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            disp_name = data.get("display_name", module_name)
            self.insp_name.setText(disp_name)
            self.insp_meta.setText(f"作者: {data.get('author', '未知')} | 授權: {data.get('license', 'MIT')} | 檔案: {module_name}.json")
            tags_txt = ", ".join(data.get("tags", [])) or "無"
            self.insp_tags.setText(f"標籤: {tags_txt}")
            self.insp_params.setText(f"分鏡權重: {data.get('storyboard_weight', 50)} | 頻率: {data.get('frequency', 50)} | 後製強度: {data.get('post_fx_intensity', 50)}")

            # 縮圖更新
            thumb_path = os.path.join(self.custom_visuals_dir, "thumbnails", f"{module_name}.jpg")
            if os.path.exists(thumb_path):
                pix = QPixmap(thumb_path)
                if not pix.isNull():
                    self.insp_thumb.setPixmap(pix.scaled(
                        self.insp_thumb.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation
                    ))
                else:
                    self.insp_thumb.setText(module_name[:3].upper())
            else:
                self.insp_thumb.setText(module_name[:3].upper())

            # 程式碼摘要
            code = data.get("code", "")
            lines = code.split("\n")[:35]
            self.insp_code_preview.setPlainText("\n".join(lines))

        except Exception as e:
            logger.warning(f"Error updating inspector for {module_name}: {e}")

    def _on_module_preview_clicked(self, module_name: str):
        self.update_inspector(module_name)
        self.moduleSelected.emit(module_name)
        if self.main_window and hasattr(self.main_window, "preview_preset"):
            self.main_window.preview_preset(module_name)

    def _on_module_edit_clicked(self, module_name: str):
        self.update_inspector(module_name)
        self.editModuleRequested.emit(module_name)
        if self.main_window:
            if hasattr(self.main_window, "preview_preset"):
                self.main_window.preview_preset(module_name)
            if hasattr(self.main_window, "left_tabs"):
                self.main_window.left_tabs.setCurrentIndex(0)  # 切換至 Tab 0 程式碼編輯器

    def _on_module_star_toggled(self, module_name: str, is_starred: bool):
        p_path = os.path.join(self.custom_visuals_dir, f"{module_name}.json")
        if os.path.exists(p_path):
            try:
                with open(p_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["is_starred"] = is_starred
                with open(p_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                
                # 同步快取狀態
                for p in self.all_presets:
                    if p["name"] == module_name:
                        p["is_starred"] = is_starred
                        break
                logger.info(f"Updated star state for {module_name}: {is_starred}")
            except Exception as e:
                logger.warning(f"Failed to update star for {module_name}: {e}")

    def _preview_current_inspector(self):
        if self.selected_module_name:
            self._on_module_preview_clicked(self.selected_module_name)

    def _edit_current_inspector(self):
        if self.selected_module_name:
            self._on_module_edit_clicked(self.selected_module_name)

    def _on_mutate_spacetime_clicked(self):
        """點擊突變新時空隧道：在沙盒中加載 HyperSpacetimeConduit 並執行突變"""
        sp_name = "HyperSpacetimeConduit"
        self.update_inspector(sp_name)
        if self.main_window and hasattr(self.main_window, "preview_preset"):
            self.main_window.preview_preset(sp_name)
            # 若沙盒已運行，注入隨機突變指令
            if hasattr(self.main_window, "web_view"):
                QTimer.singleShot(500, lambda: self.main_window.web_view.page().runJavaScript(
                    "if (window.mutateSpacetimeConduit) { window.mutateSpacetimeConduit(); }"
                ))
            if hasattr(self.main_window, "log_to_console"):
                self.main_window.log_to_console("🌌 [時空隧道突變器] 已成功實例化並載入全新形態的時空蟲洞！")

    def _open_custom_visuals_folder(self):
        try:
            subprocess.Popen(["open", self.custom_visuals_dir])
        except Exception as e:
            logger.warning(f"Failed to open folder: {e}")
