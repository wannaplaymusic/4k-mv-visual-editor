#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Batch Schedule Manager (PyQt6)
=====================================
- Separate management and scheduling for YouTube Shorts vs. Regular Long-form videos
- Read channel pending / scheduled / private videos
- Smart parse pasted Video URLs and Playlist IDs
- Staggered interval batch scheduling tailored for Long-form (24h/12h/48h) & Shorts (4h/6h/8h)
- Batch time shifting (+/- N days/hours)
- Individual inline schedule micro-adjustment via QDateTimeEdit
- Category tabs: [🎥 一般長影片] | [📱 Shorts 短影音] | [🎬 全部影片]
- Safe batch update execution with quota tracking and multi-credential rotation
"""

import os
import sys
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QTextEdit, QLineEdit, QComboBox, QProgressBar, QCheckBox,
    QGroupBox, QScrollArea, QFrame, QMessageBox, QSizePolicy, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton, QButtonGroup,
    QDateTimeEdit, QAbstractItemView, QSpinBox, QSplitter, QTabBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDateTime, QUrl
from PyQt6.QtGui import QFont, QColor, QDesktopServices

from youtube_uploader_engine import YouTubeUploaderEngine, GOOGLE_API_AVAILABLE
from youtube_logger import logger, quota_tracker


class FetchVideosWorker(QThread):
    """Background worker for querying channel videos, playlists, or custom IDs."""
    status_msg = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        engine: YouTubeUploaderEngine,
        mode: str = "channel", # "channel", "playlist", "ids"
        filter_mode: str = "scheduled_and_private",
        video_type: str = "all", # "all", "regular", "shorts"
        max_count: int = 50,
        playlist_id: Optional[str] = None,
        video_ids: Optional[List[str]] = None
    ):
        super().__init__()
        self.engine = engine
        self.mode = mode
        self.filter_mode = filter_mode
        self.video_type = video_type
        self.max_count = max_count
        self.playlist_id = playlist_id
        self.video_ids = video_ids or []
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.engine.request_cancel()

    def run(self):
        try:
            self.engine.reset_cancel()
            if self.mode == "channel":
                type_desc = "全部影片" if self.video_type == "all" else ("一般長影片" if self.video_type == "regular" else "Shorts 短影音")
                self.status_msg.emit(f"正在連線 YouTube API 並讀取頻道待發布影片 ({type_desc}，上限 {self.max_count} 部)...")
                def on_prog(cur, tot):
                    if not self._is_cancelled:
                        self.progress.emit(cur, tot)
                videos = self.engine.get_channel_videos(
                    filter_mode=self.filter_mode,
                    video_type=self.video_type,
                    max_count=self.max_count,
                    progress_cb=on_prog
                )
            elif self.mode == "playlist":
                self.status_msg.emit(f"正在讀取播放清單 (ID: {self.playlist_id})...")
                videos = self.engine.get_videos_from_playlist(self.playlist_id, max_count=self.max_count)
            elif self.mode == "ids":
                self.status_msg.emit(f"正在查詢 {len(self.video_ids)} 部指定影片詳細資訊...")
                videos = self.engine.get_videos_by_ids(self.video_ids)
            else:
                videos = []

            if self._is_cancelled:
                self.status_msg.emit("已取消讀取。")
                return

            self.finished.emit(videos)
        except Exception as e:
            logger.error(f"[FetchVideosWorker] Error: {e}", exc_info=True)
            self.failed.emit(str(e))


class BatchScheduleWorker(QThread):
    """Background worker for batch updating video publishAt / privacy status."""
    item_started = pyqtSignal(str, str) # video_id, title
    item_finished = pyqtSignal(str, bool, str, dict) # video_id, success, message, info
    progress = pyqtSignal(int, int)
    all_finished = pyqtSignal(int, int) # success_count, fail_count
    log_message = pyqtSignal(str)
    fatal_error = pyqtSignal(str)

    def __init__(self, engine: YouTubeUploaderEngine, tasks: List[Dict[str, Any]]):
        super().__init__()
        self.engine = engine
        self.tasks = tasks
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.engine.request_cancel()

    def run(self):
        total = len(self.tasks)
        success_count = 0
        fail_count = 0

        self.log_message.emit(f"\n🚀 === 開始執行批次排程修改 (共 {total} 部影片) ===")
        self.engine.reset_cancel()

        for idx, task in enumerate(self.tasks):
            if self._is_cancelled:
                self.log_message.emit("🛑 使用者已中止批次排程修改。")
                break

            video_id = task["video_id"]
            title = task.get("title", video_id)
            new_publish_at: Optional[datetime] = task.get("new_publish_at")
            new_privacy: str = task.get("new_privacy_status", "private")
            is_short = task.get("is_short", False)
            type_tag = "[Shorts]" if is_short else "[長片]"

            self.item_started.emit(video_id, title)
            sched_str = new_publish_at.strftime("%Y-%m-%d %H:%M") if new_publish_at else f"無 (設為 {new_privacy})"
            self.log_message.emit(f"[{idx+1}/{total}] {type_tag} 正在更新: {title} (ID: {video_id}) -> 排程: {sched_str} ...")

            max_retries = 2
            updated_info = {}
            is_success = False
            last_err = ""

            for attempt in range(max_retries):
                if self._is_cancelled:
                    break
                try:
                    res = self.engine.update_video_schedule(
                        video_id=video_id,
                        publish_at=new_publish_at,
                        privacy_status=new_privacy
                    )
                    updated_info = res
                    is_success = True
                    break
                except Exception as e:
                    last_err = str(e)
                    if "quota" in last_err.lower():
                        self.log_message.emit(f"  ⚠️ [Quota] 憑證配額耗盡，嘗試自動輪換金鑰池...")
                        if self.engine.cred_manager.rotate_to_next():
                            self.engine.service = None
                            continue
                        else:
                            self.fatal_error.emit(f"所有可用憑證專案配額皆已耗盡: {last_err}")
                            self._is_cancelled = True
                            break
                    if attempt < max_retries - 1 and not self._is_cancelled:
                        self.log_message.emit(f"  ⚠️ 更新失敗，3 秒後重試: {last_err}")
                        import time
                        time.sleep(3)
                    else:
                        break

            if is_success:
                success_count += 1
                self.log_message.emit(f"  ✅ [成功] 已成功排程為: {sched_str}")
                self.item_finished.emit(video_id, True, f"✅ 已排程: {sched_str}", updated_info)
            else:
                fail_count += 1
                self.log_message.emit(f"  ❌ [失敗] {last_err}")
                self.item_finished.emit(video_id, False, f"❌ 失敗: {last_err}", {})

            self.progress.emit(idx + 1, total)

        self.log_message.emit(f"\n🏁 批次修改完成！成功: {success_count} 部，失敗: {fail_count} 部。\n")
        self.all_finished.emit(success_count, fail_count)


class YouTubeBatchSchedulerWidget(QWidget):
    """
    Main Batch Scheduler Widget with first-class separation for Shorts & Regular videos.
    """

    def __init__(self, engine: Optional[YouTubeUploaderEngine] = None, parent=None):
        super().__init__(parent)
        self.engine = engine if engine is not None else YouTubeUploaderEngine()
        self.fetch_worker: Optional[FetchVideosWorker] = None
        self.update_worker: Optional[BatchScheduleWorker] = None

        # Data model: list of all loaded video dicts
        self.video_items: List[Dict[str, Any]] = []

        # Current category filter: "regular" (default), "shorts", "all"
        self.current_category: str = "regular"

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # Top Source Selection Panel
        # ----------------------------------------------------------------------
        source_group = QGroupBox("📥 1. 取得待修改影片清單 (Video Source & Query)")
        source_layout = QVBoxLayout(source_group)
        source_layout.setSpacing(8)

        # Row 1: Channel Query Controls
        row1 = QHBoxLayout()

        lbl_type = QLabel("影片類型:")
        lbl_type.setStyleSheet("font-weight: bold; color: #ffd369;")
        row1.addWidget(lbl_type)

        self.combo_query_type = QComboBox()
        self.combo_query_type.addItem("全部影片 (長片 + Shorts)", "all")
        self.combo_query_type.addItem("🎥 僅一般長影片 (Long-form)", "regular")
        self.combo_query_type.addItem("📱 僅 Shorts 短影音 (Shorts)", "shorts")
        self.combo_query_type.setStyleSheet("font-weight: bold; color: #00d2ff;")
        row1.addWidget(self.combo_query_type, 2)

        lbl_filter = QLabel("篩選條件:")
        lbl_filter.setStyleSheet("font-weight: bold; color: #a8b2d1;")
        row1.addWidget(lbl_filter)

        self.combo_filter_mode = QComboBox()
        self.combo_filter_mode.addItem("全部私人與已排程影片 (推薦)", "scheduled_and_private")
        self.combo_filter_mode.addItem("僅已排程影片 (已設定發布時間)", "only_scheduled")
        self.combo_filter_mode.addItem("僅私人影片 (尚未設定發布時間)", "only_private")
        self.combo_filter_mode.addItem("全部最近上傳 (含公開/不公開)", "all")
        row1.addWidget(self.combo_filter_mode, 2)

        lbl_count = QLabel("數量:")
        lbl_count.setStyleSheet("color: #a8b2d1;")
        row1.addWidget(lbl_count)

        self.combo_max_count = QComboBox()
        self.combo_max_count.addItems(["30 部", "50 部 (推薦)", "100 部", "200 部"])
        self.combo_max_count.setCurrentIndex(1)
        row1.addWidget(self.combo_max_count, 1)

        self.btn_fetch_channel = QPushButton("📥 讀取頻道待排程影片")
        self.btn_fetch_channel.setStyleSheet("""
            QPushButton {
                background: #0f3460;
                color: #00d2ff;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 5px;
                border: 1px solid #00d2ff;
            }
            QPushButton:hover { background: #164282; color: #ffffff; }
        """)
        self.btn_fetch_channel.clicked.connect(self._fetch_channel_videos)
        row1.addWidget(self.btn_fetch_channel, 2)

        self.btn_toggle_paste = QPushButton("📋 貼上網址 / 清單 ID...")
        self.btn_toggle_paste.setStyleSheet("""
            QPushButton {
                background: #1f4068;
                color: #ffd369;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 5px;
                border: 1px solid #ffd369;
            }
            QPushButton:hover { background: #2b588f; }
        """)
        self.btn_toggle_paste.clicked.connect(self._toggle_paste_panel)
        row1.addWidget(self.btn_toggle_paste, 1)

        source_layout.addLayout(row1)

        # Row 2: Collapsible Paste Text Area
        self.paste_panel = QFrame()
        self.paste_panel.setVisible(False)
        self.paste_panel.setStyleSheet("""
            QFrame {
                background: #0f141d;
                border-radius: 6px;
                border: 1px dashed #3a4750;
                padding: 8px;
            }
        """)
        paste_layout = QVBoxLayout(self.paste_panel)
        paste_layout.setContentsMargins(6, 6, 6, 6)

        lbl_paste_hint = QLabel("支援多行直接貼上 YouTube 影片網址、短網址 (youtu.be)、Shorts 網址或播放清單 (list=PL...)：")
        lbl_paste_hint.setStyleSheet("font-size: 11px; color: #8892b0;")
        paste_layout.addWidget(lbl_paste_hint)

        self.txt_paste_input = QTextEdit()
        self.txt_paste_input.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://youtu.be/...\nhttps://www.youtube.com/shorts/...\nhttps://www.youtube.com/playlist?list=PL...")
        self.txt_paste_input.setFixedHeight(70)
        self.txt_paste_input.setStyleSheet("background: #161b22; color: #e6edf3; font-family: monospace; font-size: 12px;")
        paste_layout.addWidget(self.txt_paste_input)

        paste_btn_row = QHBoxLayout()
        paste_btn_row.addStretch()
        self.btn_parse_paste = QPushButton("🔍 解析並載入影片")
        self.btn_parse_paste.setStyleSheet("background: #4ecca3; color: #121212; font-weight: bold; padding: 5px 15px; border-radius: 4px;")
        self.btn_parse_paste.clicked.connect(self._parse_pasted_urls)
        paste_btn_row.addWidget(self.btn_parse_paste)

        self.btn_close_paste = QPushButton("關閉")
        self.btn_close_paste.clicked.connect(lambda: self.paste_panel.setVisible(False))
        paste_btn_row.addWidget(self.btn_close_paste)

        paste_layout.addLayout(paste_btn_row)
        source_layout.addWidget(self.paste_panel)

        main_layout.addWidget(source_group)

        # ----------------------------------------------------------------------
        # Batch Scheduling Strategy Box
        # ----------------------------------------------------------------------
        strategy_group = QGroupBox("⏰ 2. 批次排程策略設定 (Scheduling Strategy)")
        strat_layout = QVBoxLayout(strategy_group)
        strat_layout.setSpacing(8)

        # Strategy Mode Radio Buttons
        strat_mode_row = QHBoxLayout()
        self.radio_stagger = QRadioButton("⚡ 等距階梯排程 (依序間隔連載)")
        self.radio_stagger.setChecked(True)
        self.radio_stagger.setStyleSheet("font-weight: bold; color: #00d2ff;")
        self.radio_stagger.toggled.connect(self._update_strategy_panel_state)
        strat_mode_row.addWidget(self.radio_stagger)

        self.radio_shift = QRadioButton("⏩ 批次平移時間 (延後/提前 N 小時或天數)")
        self.radio_shift.setStyleSheet("font-weight: bold; color: #ffd369;")
        self.radio_shift.toggled.connect(self._update_strategy_panel_state)
        strat_mode_row.addWidget(self.radio_shift)

        self.radio_unified = QRadioButton("📌 統一指定單一時間")
        self.radio_unified.setStyleSheet("font-weight: bold; color: #4ecca3;")
        self.radio_unified.toggled.connect(self._update_strategy_panel_state)
        strat_mode_row.addWidget(self.radio_unified)

        self.radio_clear = QRadioButton("🚫 清除排程 (設為純私人/不公開)")
        self.radio_clear.setStyleSheet("font-weight: bold; color: #e94560;")
        self.radio_clear.toggled.connect(self._update_strategy_panel_state)
        strat_mode_row.addWidget(self.radio_clear)

        strat_layout.addLayout(strat_mode_row)

        # Strategy Controls Frame
        self.strat_controls_frame = QFrame()
        self.strat_controls_frame.setStyleSheet("""
            QFrame {
                background: #161b22;
                border-radius: 6px;
                padding: 6px;
                border: 1px solid #30363d;
            }
        """)
        self.strat_controls_layout = QHBoxLayout(self.strat_controls_frame)
        self.strat_controls_layout.setContentsMargins(8, 4, 8, 4)

        # Sub-Layout 1: Staggered Controls
        self.widget_stagger = QWidget()
        w_stagger_layout = QHBoxLayout(self.widget_stagger)
        w_stagger_layout.setContentsMargins(0, 0, 0, 0)

        w_stagger_layout.addWidget(QLabel("起始時間:"))
        self.dt_start = QDateTimeEdit()
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        def_start = datetime.now() + timedelta(days=1)
        def_start = def_start.replace(hour=20, minute=0, second=0, microsecond=0)
        self.dt_start.setDateTime(QDateTime.fromString(def_start.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))
        w_stagger_layout.addWidget(self.dt_start)

        btn_tomorrow_20 = QPushButton("明日20:00")
        btn_tomorrow_20.setStyleSheet("padding: 2px 6px; font-size: 11px;")
        btn_tomorrow_20.clicked.connect(self._set_start_tomorrow_20)
        w_stagger_layout.addWidget(btn_tomorrow_20)

        btn_tomorrow_12 = QPushButton("明日12:00")
        btn_tomorrow_12.setStyleSheet("padding: 2px 6px; font-size: 11px;")
        btn_tomorrow_12.clicked.connect(self._set_start_tomorrow_12)
        w_stagger_layout.addWidget(btn_tomorrow_12)

        w_stagger_layout.addWidget(QLabel("發布間隔:"))
        self.combo_stagger_interval = QComboBox()
        self._populate_stagger_intervals_for_category("regular")
        self.combo_stagger_interval.currentIndexChanged.connect(self._on_stagger_interval_changed)
        w_stagger_layout.addWidget(self.combo_stagger_interval)

        # Custom interval widgets
        self.spin_custom_interval = QSpinBox()
        self.spin_custom_interval.setRange(1, 1000)
        self.spin_custom_interval.setValue(24)
        self.spin_custom_interval.setVisible(False)
        w_stagger_layout.addWidget(self.spin_custom_interval)

        self.combo_custom_unit = QComboBox()
        self.combo_custom_unit.addItems(["小時", "天", "分鐘"])
        self.combo_custom_unit.setVisible(False)
        w_stagger_layout.addWidget(self.combo_custom_unit)

        self.btn_apply_stagger = QPushButton("⚡ 套用等距排程到當前勾選項目")
        self.btn_apply_stagger.setStyleSheet("""
            QPushButton {
                background: #00d2ff;
                color: #0b132b;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background: #5ee2ff; }
        """)
        self.btn_apply_stagger.clicked.connect(self._apply_staggered_schedule)
        w_stagger_layout.addWidget(self.btn_apply_stagger)

        self.strat_controls_layout.addWidget(self.widget_stagger)

        # Sub-Layout 2: Shift Controls
        self.widget_shift = QWidget()
        self.widget_shift.setVisible(False)
        w_shift_layout = QHBoxLayout(self.widget_shift)
        w_shift_layout.setContentsMargins(0, 0, 0, 0)

        w_shift_layout.addWidget(QLabel("平移方向:"))
        self.combo_shift_dir = QComboBox()
        self.combo_shift_dir.addItem("延後 (+)", 1)
        self.combo_shift_dir.addItem("提前 (-)", -1)
        w_shift_layout.addWidget(self.combo_shift_dir)

        w_shift_layout.addWidget(QLabel("幅度:"))
        self.spin_shift_value = QSpinBox()
        self.spin_shift_value.setRange(1, 365)
        self.spin_shift_value.setValue(1)
        w_shift_layout.addWidget(self.spin_shift_value)

        self.combo_shift_unit = QComboBox()
        self.combo_shift_unit.addItem("天 (24 小時)", 86400)
        self.combo_shift_unit.addItem("小時", 3600)
        self.combo_shift_unit.addItem("分鐘", 60)
        w_shift_layout.addWidget(self.combo_shift_unit)

        self.btn_apply_shift = QPushButton("⏩ 批次平移當前勾選項目時間")
        self.btn_apply_shift.setStyleSheet("""
            QPushButton {
                background: #ffd369;
                color: #121212;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background: #ffe08a; }
        """)
        self.btn_apply_shift.clicked.connect(self._apply_time_shift)
        w_shift_layout.addWidget(self.btn_apply_shift)

        self.strat_controls_layout.addWidget(self.widget_shift)

        # Sub-Layout 3: Unified Controls
        self.widget_unified = QWidget()
        self.widget_unified.setVisible(False)
        w_uni_layout = QHBoxLayout(self.widget_unified)
        w_uni_layout.setContentsMargins(0, 0, 0, 0)

        w_uni_layout.addWidget(QLabel("統一發布時間:"))
        self.dt_unified = QDateTimeEdit()
        self.dt_unified.setCalendarPopup(True)
        self.dt_unified.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt_unified.setDateTime(self.dt_start.dateTime())
        w_uni_layout.addWidget(self.dt_unified)

        self.btn_apply_unified = QPushButton("📌 統一套用至當前勾選項目")
        self.btn_apply_unified.setStyleSheet("background: #4ecca3; color: #121212; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.btn_apply_unified.clicked.connect(self._apply_unified_time)
        w_uni_layout.addWidget(self.btn_apply_unified)

        self.strat_controls_layout.addWidget(self.widget_unified)

        # Sub-Layout 4: Clear Controls
        self.widget_clear = QWidget()
        self.widget_clear.setVisible(False)
        w_clr_layout = QHBoxLayout(self.widget_clear)
        w_clr_layout.setContentsMargins(0, 0, 0, 0)

        w_clr_layout.addWidget(QLabel("清除排程後設為:"))
        self.combo_clear_privacy = QComboBox()
        self.combo_clear_privacy.addItem("私人 (private)", "private")
        self.combo_clear_privacy.addItem("不公開 (unlisted)", "unlisted")
        w_clr_layout.addWidget(self.combo_clear_privacy)

        self.btn_apply_clear = QPushButton("🚫 取消當前勾選項目之排程")
        self.btn_apply_clear.setStyleSheet("background: #e94560; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.btn_apply_clear.clicked.connect(self._apply_clear_schedule)
        w_clr_layout.addWidget(self.btn_apply_clear)

        self.strat_controls_layout.addWidget(self.widget_clear)

        strat_layout.addWidget(self.strat_controls_frame)
        main_layout.addWidget(strategy_group)

        # ----------------------------------------------------------------------
        # Video List Table with Category Tabs (Shorts vs Long-form Separation)
        # ----------------------------------------------------------------------
        table_group = QGroupBox("📋 3. 影片佇列與分類排程 (Video Queue & Schedule Preview)")
        t_layout = QVBoxLayout(table_group)
        t_layout.setSpacing(6)

        # Prominent Category Tab Bar (Shorts vs Long-form Separation)
        cat_bar_layout = QHBoxLayout()
        self.category_tab_bar = QTabBar()
        self.category_tab_bar.addTab("🎥 一般長影片 (Long-form) (0)")
        self.category_tab_bar.addTab("📱 Shorts 短影音 (Shorts) (0)")
        self.category_tab_bar.addTab("🎬 全部影片 (All) (0)")
        self.category_tab_bar.setStyleSheet("""
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                font-weight: bold;
                font-size: 13px;
                padding: 7px 18px;
                border: 1px solid #30363d;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #1f4068;
                color: #00d2ff;
                border: 1px solid #00d2ff;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background: #21262d;
                color: #ffffff;
            }
        """)
        self.category_tab_bar.currentChanged.connect(self._on_category_tab_changed)
        cat_bar_layout.addWidget(self.category_tab_bar)

        cat_bar_layout.addStretch()

        self.lbl_category_hint = QLabel("💡 提示：長片與 Shorts 已獨立分開管理與套用排程間隔")
        self.lbl_category_hint.setStyleSheet("color: #718096; font-size: 11px; font-style: italic;")
        cat_bar_layout.addWidget(self.lbl_category_hint)

        t_layout.addLayout(cat_bar_layout)

        # Table Action Toolbar
        tb_bar = QHBoxLayout()
        self.btn_select_all = QPushButton("☑️ 全選目前分類")
        self.btn_select_all.clicked.connect(lambda: self._set_current_view_checkboxes(True))
        tb_bar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("◻️ 取消全選")
        self.btn_deselect_all.clicked.connect(lambda: self._set_current_view_checkboxes(False))
        tb_bar.addWidget(self.btn_deselect_all)

        self.btn_select_modified = QPushButton("⚡ 僅選有變更")
        self.btn_select_modified.setStyleSheet("color: #ffd369; font-weight: bold;")
        self.btn_select_modified.clicked.connect(self._select_only_modified_current_view)
        tb_bar.addWidget(self.btn_select_modified)

        tb_bar.addSpacing(10)

        self.btn_move_up = QPushButton("⬆️ 上移")
        self.btn_move_up.setToolTip("向上移動選定影片，調整目前分類之連載順序")
        self.btn_move_up.clicked.connect(lambda: self._move_row(-1))
        tb_bar.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("⬇️ 下移")
        self.btn_move_down.setToolTip("向下移動選定影片，調整目前分類之連載順序")
        self.btn_move_down.clicked.connect(lambda: self._move_row(1))
        tb_bar.addWidget(self.btn_move_down)

        self.btn_sort_time_asc = QPushButton("🕒 依原時間舊到新排序")
        self.btn_sort_time_asc.clicked.connect(lambda: self._sort_items(reverse=False))
        tb_bar.addWidget(self.btn_sort_time_asc)

        tb_bar.addStretch()

        self.btn_clear_table = QPushButton("🧹 清空清單")
        self.btn_clear_table.setStyleSheet("color: #ff5e78;")
        self.btn_clear_table.clicked.connect(self._clear_table)
        tb_bar.addWidget(self.btn_clear_table)

        t_layout.addLayout(tb_bar)

        # QTableWidget
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "選取", "類型", "影片 ID", "影片標題", "當前狀態", "原排程發布時間",
            "新排程發布時間 (可個別微調)", "變更預覽", "執行結果"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        t_layout.addWidget(self.table)

        # Status Summary Label
        self.lbl_table_summary = QLabel("目前無影片。請點擊「讀取頻道待排程影片」或「貼上網址/清單ID」。")
        self.lbl_table_summary.setStyleSheet("color: #8892b0; font-size: 12px; font-weight: bold;")
        t_layout.addWidget(self.lbl_table_summary)

        main_layout.addWidget(table_group, 3)

        # ----------------------------------------------------------------------
        # Progress Bar & Action Execution Bar
        # ----------------------------------------------------------------------
        exec_group = QFrame()
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 0, 0, 0)
        exec_layout.setSpacing(6)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #30363d;
                border-radius: 4px;
                text-align: center;
                height: 22px;
                background: #161b22;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4ecca3, stop:1 #00d2ff);
            }
        """)
        exec_layout.addWidget(self.progress_bar)

        btn_action_row = QHBoxLayout()
        self.lbl_action_status = QLabel("就緒。")
        self.lbl_action_status.setStyleSheet("color: #a8b2d1; font-weight: bold;")
        btn_action_row.addWidget(self.lbl_action_status)

        btn_action_row.addStretch()

        self.btn_execute = QPushButton("🚀 立即執行批次排程修改 (Update YouTube Schedule)")
        self.btn_execute.setStyleSheet("""
            QPushButton {
                background: #4ecca3;
                color: #0d1117;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #5df0c1; }
            QPushButton:disabled { background: #3a3f4b; color: #6e7681; }
        """)
        self.btn_execute.clicked.connect(self._execute_batch_update)
        btn_action_row.addWidget(self.btn_execute)

        self.btn_cancel = QPushButton("🛑 取消操作")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #e94560;
                color: white;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
            }
            QPushButton:disabled { background: #3a3f4b; color: #6e7681; }
        """)
        self.btn_cancel.clicked.connect(self._cancel_operation)
        btn_action_row.addWidget(self.btn_cancel)

        exec_layout.addLayout(btn_action_row)
        main_layout.addWidget(exec_group)

        # ----------------------------------------------------------------------
        # Log Output Area
        # ----------------------------------------------------------------------
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(110)
        self.txt_log.setStyleSheet("""
            QTextEdit {
                background: #0d1117;
                color: #38ef7d;
                font-family: Menlo, Monaco, Consolas, monospace;
                font-size: 11px;
                border: 1px solid #30363d;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.txt_log)

    # --------------------------------------------------------------------------
    # Helper & Event Handlers
    # --------------------------------------------------------------------------
    def _log(self, text: str):
        self.txt_log.append(text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _toggle_paste_panel(self):
        self.paste_panel.setVisible(not self.paste_panel.isVisible())

    def _set_start_tomorrow_20(self):
        dt = datetime.now() + timedelta(days=1)
        dt = dt.replace(hour=20, minute=0, second=0, microsecond=0)
        self.dt_start.setDateTime(QDateTime.fromString(dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))

    def _set_start_tomorrow_12(self):
        dt = datetime.now() + timedelta(days=1)
        dt = dt.replace(hour=12, minute=0, second=0, microsecond=0)
        self.dt_start.setDateTime(QDateTime.fromString(dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))

    def _populate_stagger_intervals_for_category(self, cat: str):
        self.combo_stagger_interval.blockSignals(True)
        self.combo_stagger_interval.clear()
        if cat == "shorts":
            self.combo_stagger_interval.addItem("每 4 小時 (Shorts 密集推薦: 1天4部)", 14400)
            self.combo_stagger_interval.addItem("每 6 小時 (1天3部)", 21600)
            self.combo_stagger_interval.addItem("每 8 小時 (1天2部)", 28800)
            self.combo_stagger_interval.addItem("每 12 小時 (1天2部)", 43200)
            self.combo_stagger_interval.addItem("每 24 小時 (1天1部)", 86400)
            self.combo_stagger_interval.addItem("每 2 小時 (極速排程)", 7200)
            self.combo_stagger_interval.addItem("自訂間隔...", -1)
        else:
            # regular long-form default
            self.combo_stagger_interval.addItem("每 24 小時 (長片推薦: 1天1部)", 86400)
            self.combo_stagger_interval.addItem("每 12 小時 (長片首播: 1天2部)", 43200)
            self.combo_stagger_interval.addItem("每 48 小時 (2天1部)", 172800)
            self.combo_stagger_interval.addItem("每 72 小時 (3天1部)", 259200)
            self.combo_stagger_interval.addItem("每 7 天 (每週一首)", 604800)
            self.combo_stagger_interval.addItem("每 8 小時", 28800)
            self.combo_stagger_interval.addItem("自訂間隔...", -1)
        self.combo_stagger_interval.blockSignals(False)

    def _on_stagger_interval_changed(self):
        val = self.combo_stagger_interval.currentData()
        is_custom = (val == -1)
        self.spin_custom_interval.setVisible(is_custom)
        self.combo_custom_unit.setVisible(is_custom)

    def _update_strategy_panel_state(self):
        self.widget_stagger.setVisible(self.radio_stagger.isChecked())
        self.widget_shift.setVisible(self.radio_shift.isChecked())
        self.widget_unified.setVisible(self.radio_unified.isChecked())
        self.widget_clear.setVisible(self.radio_clear.isChecked())

    def _on_category_tab_changed(self, idx: int):
        if idx == 0:
            self.current_category = "regular"
            self.btn_select_all.setText("☑️ 全選一般長片")
            self.lbl_category_hint.setText("💡 目前瀏覽：一般長片 (Long-form) 專用佇列與排程")
            self._populate_stagger_intervals_for_category("regular")
        elif idx == 1:
            self.current_category = "shorts"
            self.btn_select_all.setText("☑️ 全選 Shorts 短影音")
            self.lbl_category_hint.setText("💡 目前瀏覽：Shorts 短影音專用佇列與排程")
            self._populate_stagger_intervals_for_category("shorts")
        else:
            self.current_category = "all"
            self.btn_select_all.setText("☑️ 全選全部影片")
            self.lbl_category_hint.setText("💡 目前瀏覽：全部影片 (包含一般長片與 Shorts)")
            self._populate_stagger_intervals_for_category("regular")

        self._populate_table()

    # --------------------------------------------------------------------------
    # Fetching Operations
    # --------------------------------------------------------------------------
    def _fetch_channel_videos(self):
        if not GOOGLE_API_AVAILABLE:
            QMessageBox.critical(self, "缺少依賴套件", "未安裝 Google API 套件，請執行 pip install google-api-python-client google-auth-oauthlib")
            return

        query_type = self.combo_query_type.currentData()
        filter_mode = self.combo_filter_mode.currentData()
        max_cnt_str = self.combo_max_count.currentText()
        max_count = int(max_cnt_str.split()[0])

        self.btn_fetch_channel.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self.lbl_action_status.setText("正在讀取頻道影片...")
        self._log(f"🔍 開始讀取頻道影片 (類型: {query_type}, 篩選: {filter_mode}, 上限: {max_count})...")

        self.fetch_worker = FetchVideosWorker(
            engine=self.engine,
            mode="channel",
            filter_mode=filter_mode,
            video_type=query_type,
            max_count=max_count
        )
        self.fetch_worker.status_msg.connect(lambda msg: (self.lbl_action_status.setText(msg), self._log(f"ℹ️ {msg}")))
        self.fetch_worker.finished.connect(self._on_fetch_finished)
        self.fetch_worker.failed.connect(self._on_fetch_failed)
        self.fetch_worker.start()

    def _parse_pasted_urls(self):
        text = self.txt_paste_input.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "輸入為空", "請在文字框中貼上 YouTube 影片網址或播放清單 ID。")
            return

        video_ids, playlist_id = YouTubeUploaderEngine.extract_video_ids(text)

        if not video_ids and not playlist_id:
            QMessageBox.warning(self, "無效輸入", "未能從貼上的文字中辨識出有效的 YouTube 影片網址或播放清單 ID。")
            return

        self.btn_parse_paste.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setRange(0, 0)

        if playlist_id and not video_ids:
            self._log(f"🔍 正在解析播放清單 ID: {playlist_id} ...")
            self.fetch_worker = FetchVideosWorker(
                engine=self.engine,
                mode="playlist",
                playlist_id=playlist_id,
                max_count=50
            )
        else:
            self._log(f"🔍 正在解析 {len(video_ids)} 部指定影片 ID: {video_ids} ...")
            self.fetch_worker = FetchVideosWorker(
                engine=self.engine,
                mode="ids",
                video_ids=video_ids
            )

        self.fetch_worker.status_msg.connect(lambda msg: (self.lbl_action_status.setText(msg), self._log(f"ℹ️ {msg}")))
        self.fetch_worker.finished.connect(self._on_fetch_finished)
        self.fetch_worker.failed.connect(self._on_fetch_failed)
        self.fetch_worker.start()

    def _on_fetch_finished(self, videos: List[Dict[str, Any]]):
        self.btn_fetch_channel.setEnabled(True)
        self.btn_parse_paste.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.lbl_action_status.setText(f"成功取得 {len(videos)} 部影片！")
        self._log(f"✅ 成功載入 {len(videos)} 部影片。")

        if not videos:
            QMessageBox.information(self, "未找到符合影片", "未在頻道中找到符合篩選條件的影片。\n\n提示：您可以切換篩選條件為「全部最近上傳」，或手動貼上影片網址。")
            return

        # Initialize data model items
        for item in videos:
            orig_pub_str = item.get("publish_at")
            orig_dt: Optional[datetime] = None
            if orig_pub_str:
                try:
                    orig_dt = datetime.fromisoformat(orig_pub_str.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
                except Exception:
                    pass

            item["original_dt"] = orig_dt
            item["new_dt"] = orig_dt
            item["is_modified"] = False
            item["new_privacy"] = item.get("privacy_status", "private")
            item["checked"] = True
            item["result_text"] = "⏳ 待修改"

        self.video_items = videos
        self._update_category_tab_counts()
        self._populate_table()

    def _on_fetch_failed(self, err_msg: str):
        self.btn_fetch_channel.setEnabled(True)
        self.btn_parse_paste.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.lbl_action_status.setText("讀取失敗。")
        self._log(f"❌ 讀取失敗: {err_msg}")
        QMessageBox.critical(self, "讀取影片失敗", f"無法取得影片資訊：\n{err_msg}")

    # --------------------------------------------------------------------------
    # Category Filtering & Table Population
    # --------------------------------------------------------------------------
    def _get_visible_items(self) -> List[Dict[str, Any]]:
        """Returns the subset of video_items matching the current category filter."""
        if self.current_category == "regular":
            return [it for it in self.video_items if not it.get("is_short", False)]
        elif self.current_category == "shorts":
            return [it for it in self.video_items if it.get("is_short", False)]
        else:
            return self.video_items

    def _update_category_tab_counts(self):
        regular_count = sum(1 for it in self.video_items if not it.get("is_short", False))
        shorts_count = sum(1 for it in self.video_items if it.get("is_short", False))
        total_count = len(self.video_items)

        self.category_tab_bar.setTabText(0, f"🎥 一般長影片 (Long-form) ({regular_count})")
        self.category_tab_bar.setTabText(1, f"📱 Shorts 短影音 (Shorts) ({shorts_count})")
        self.category_tab_bar.setTabText(2, f"🎬 全部影片 (All) ({total_count})")

    def _populate_table(self):
        visible_items = self._get_visible_items()
        self.table.setRowCount(0)
        self.table.setRowCount(len(visible_items))

        for row, item in enumerate(visible_items):
            v_id = item.get("id", "")
            orig_dt: Optional[datetime] = item.get("original_dt")
            is_short = item.get("is_short", False)
            dur_str = item.get("duration_str", "")

            # Col 0: Checkbox
            chk = QCheckBox()
            chk.setChecked(item.get("checked", True))
            chk.setStyleSheet("margin-left: 8px;")
            # Store item reference in checkbox property
            chk.setProperty("video_id", v_id)
            chk.stateChanged.connect(lambda state, it=item: self._on_checkbox_state_changed(it, state))
            self.table.setCellWidget(row, 0, chk)

            # Col 1: Type Badge (Shorts vs Long-form)
            if is_short:
                badge_text = f"📱 Shorts ({dur_str})"
                badge_color = "#00d2ff"
                badge_bg = "#0f2b3c"
            else:
                badge_text = f"🎥 長片 ({dur_str})"
                badge_color = "#4ecca3"
                badge_bg = "#0d2b23"

            lbl_badge = QLabel(badge_text)
            lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_badge.setStyleSheet(f"""
                QLabel {{
                    color: {badge_color};
                    background: {badge_bg};
                    font-weight: bold;
                    font-size: 11px;
                    border-radius: 4px;
                    padding: 2px 8px;
                    border: 1px solid {badge_color};
                }}
            """)
            self.table.setCellWidget(row, 1, lbl_badge)

            # Col 2: Video ID
            item_id = QTableWidgetItem(v_id)
            item_id.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_id.setForeground(QColor("#718096"))
            self.table.setItem(row, 2, item_id)

            # Col 3: Title
            title = item.get("title", "")
            item_title = QTableWidgetItem(title)
            item_title.setToolTip(f"{title}\n\n長度: {dur_str} | 點擊可在瀏覽器開啟: https://youtu.be/{v_id}")
            self.table.setItem(row, 3, item_title)

            # Col 4: Current Privacy Status Badge
            priv = item.get("privacy_status", "")
            has_sched = bool(orig_dt)
            if has_sched:
                status_badge = "⏰ 已排程"
                stat_color = "#00d2ff"
            elif priv == "private":
                status_badge = "🔒 私人"
                stat_color = "#ffd369"
            elif priv == "unlisted":
                status_badge = "🔗 不公開"
                stat_color = "#a0aec0"
            elif priv == "public":
                status_badge = "🌐 公開"
                stat_color = "#4ecca3"
            else:
                status_badge = priv
                stat_color = "#ffffff"

            item_status = QTableWidgetItem(status_badge)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setForeground(QColor(stat_color))
            item_status.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 4, item_status)

            # Col 5: Original Schedule
            orig_text = orig_dt.strftime("%Y-%m-%d %H:%M") if orig_dt else "— (未排程)"
            item_orig = QTableWidgetItem(orig_text)
            item_orig.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_orig.setForeground(QColor("#cbd5e1" if orig_dt else "#64748b"))
            item_orig.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 5, item_orig)

            # Col 6: Embedded QDateTimeEdit for manual micro-adjustment
            dt_edit = QDateTimeEdit()
            dt_edit.setCalendarPopup(True)
            dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
            dt_edit.setStyleSheet("""
                QDateTimeEdit {
                    background: #1e293b;
                    color: #ffffff;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 12px;
                }
            """)
            display_dt = item["new_dt"] if item["new_dt"] else (orig_dt or (datetime.now() + timedelta(days=1)))
            dt_edit.setDateTime(QDateTime.fromString(display_dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))
            dt_edit.dateTimeChanged.connect(lambda qdt, it=item, r=row: self._on_cell_datetime_changed(it, r, qdt))
            self.table.setCellWidget(row, 6, dt_edit)

            # Col 7: Diff Preview
            item_diff = QTableWidgetItem("維持原樣")
            item_diff.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_diff.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 7, item_diff)

            # Col 8: Execution Result
            item_res = QTableWidgetItem(item.get("result_text", "⏳ 待修改"))
            item_res.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            res_txt = item.get("result_text", "")
            if "✅" in res_txt: item_res.setForeground(QColor("#4ecca3"))
            elif "❌" in res_txt: item_res.setForeground(QColor("#e94560"))
            else: item_res.setForeground(QColor("#94a3b8"))
            item_res.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 8, item_res)

            self._update_row_diff_preview(row, item)

        self._update_table_summary()

    def _on_checkbox_state_changed(self, item: dict, state: int):
        item["checked"] = (state == Qt.CheckState.Checked.value or state == 2)
        self._update_table_summary()

    def _on_cell_datetime_changed(self, item: dict, row: int, qdt: QDateTime):
        dt_str = qdt.toString("yyyy-MM-dd HH:mm")
        new_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        item["new_dt"] = new_dt
        item["is_modified"] = True
        self._update_row_diff_preview(row, item)
        self._update_table_summary()

    def _update_row_diff_preview(self, row: int, item: dict):
        orig_dt: Optional[datetime] = item.get("original_dt")
        new_dt: Optional[datetime] = item.get("new_dt")
        is_mod: bool = item.get("is_modified", False)
        new_privacy: str = item.get("new_privacy", "private")

        item_diff = self.table.item(row, 7)
        if not item_diff:
            return

        if not is_mod:
            item_diff.setText("維持原樣")
            item_diff.setForeground(QColor("#64748b"))
            return

        if new_dt is None:
            item_diff.setText(f"🚫 取消排程 ({new_privacy})")
            item_diff.setForeground(QColor("#f87171"))
        elif orig_dt is None:
            item_diff.setText(f"✨ 新設排程: {new_dt.strftime('%m-%d %H:%M')}")
            item_diff.setForeground(QColor("#4ade80"))
        else:
            diff_secs = (new_dt - orig_dt).total_seconds()
            if abs(diff_secs) < 60:
                item_diff.setText("時間相同")
                item_diff.setForeground(QColor("#64748b"))
            elif diff_secs > 0:
                hours = diff_secs / 3600.0
                if hours >= 24 and hours % 24 == 0:
                    item_diff.setText(f"⏩ 延後 {int(hours//24)} 天")
                else:
                    item_diff.setText(f"⏩ 延後 {hours:.1f} 小時")
                item_diff.setForeground(QColor("#facc15"))
            else:
                hours = abs(diff_secs) / 3600.0
                if hours >= 24 and hours % 24 == 0:
                    item_diff.setText(f"⏪ 提前 {int(hours//24)} 天")
                else:
                    item_diff.setText(f"⏪ 提前 {hours:.1f} 小時")
                item_diff.setForeground(QColor("#60a5fa"))

    def _update_table_summary(self):
        reg_total = sum(1 for it in self.video_items if not it.get("is_short", False))
        reg_sel = sum(1 for it in self.video_items if not it.get("is_short", False) and it.get("checked", True))
        shorts_total = sum(1 for it in self.video_items if it.get("is_short", False))
        shorts_sel = sum(1 for it in self.video_items if it.get("is_short", False) and it.get("checked", True))
        total_modified = sum(1 for it in self.video_items if it.get("is_modified", False) and it.get("checked", True))

        self.lbl_table_summary.setText(
            f"🎥 一般長片: {reg_total} 部 (已選: {reg_sel}) | "
            f"📱 Shorts: {shorts_total} 部 (已選: {shorts_sel}) | "
            f"⚡ 預計修改總數: {total_modified} 部"
        )
        self.btn_execute.setEnabled(total_modified > 0)

    # --------------------------------------------------------------------------
    # Scheduling Strategies Application (Category Scoped)
    # --------------------------------------------------------------------------
    def _apply_staggered_schedule(self):
        """Applies staggered interval scheduling starting from dt_start to checked items in current view."""
        start_qdt = self.dt_start.dateTime()
        start_str = start_qdt.toString("yyyy-MM-dd HH:mm")
        current_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M")

        val = self.combo_stagger_interval.currentData()
        if val == -1:
            num = self.spin_custom_interval.value()
            unit = self.combo_custom_unit.currentText()
            if unit == "天": interval_secs = num * 86400
            elif unit == "分鐘": interval_secs = num * 60
            else: interval_secs = num * 3600
        else:
            interval_secs = val

        visible_items = self._get_visible_items()
        applied_count = 0

        for row, item in enumerate(visible_items):
            if item.get("checked", True):
                new_dt = current_dt + timedelta(seconds=interval_secs * applied_count)
                item["new_dt"] = new_dt
                item["is_modified"] = True

                dt_edit = self.table.cellWidget(row, 6)
                if isinstance(dt_edit, QDateTimeEdit):
                    dt_edit.blockSignals(True)
                    dt_edit.setDateTime(QDateTime.fromString(new_dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))
                    dt_edit.blockSignals(False)

                self._update_row_diff_preview(row, item)
                applied_count += 1

        self._update_table_summary()
        cat_name = "一般長片" if self.current_category == "regular" else ("Shorts 短影音" if self.current_category == "shorts" else "影片")
        hours = interval_secs / 3600.0
        self._log(f"⚡ 已將等距排程 (間隔 {hours:.1f} 小時) 套用至 {applied_count} 部勾選之【{cat_name}】。")

    def _apply_time_shift(self):
        """Shifts existing scheduled time by +/- N days/hours for checked items in current view."""
        dir_mult = self.combo_shift_dir.currentData()
        shift_val = self.spin_shift_value.value()
        shift_unit_secs = self.combo_shift_unit.currentData()
        total_shift_secs = dir_mult * shift_val * shift_unit_secs

        visible_items = self._get_visible_items()
        applied_count = 0

        for row, item in enumerate(visible_items):
            if item.get("checked", True):
                base_dt = item.get("new_dt") or item.get("original_dt") or (datetime.now() + timedelta(days=1))
                new_dt = base_dt + timedelta(seconds=total_shift_secs)
                item["new_dt"] = new_dt
                item["is_modified"] = True

                dt_edit = self.table.cellWidget(row, 6)
                if isinstance(dt_edit, QDateTimeEdit):
                    dt_edit.blockSignals(True)
                    dt_edit.setDateTime(QDateTime.fromString(new_dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))
                    dt_edit.blockSignals(False)

                self._update_row_diff_preview(row, item)
                applied_count += 1

        self._update_table_summary()
        dir_label = "延後" if dir_mult > 0 else "提前"
        cat_name = "一般長片" if self.current_category == "regular" else ("Shorts 短影音" if self.current_category == "shorts" else "影片")
        self._log(f"⏩ 已將 {applied_count} 部【{cat_name}】排程時間統一 {dir_label} {shift_val} {self.combo_shift_unit.currentText()}。")

    def _apply_unified_time(self):
        """Sets a unified datetime to checked items in current view."""
        qdt = self.dt_unified.dateTime()
        uni_str = qdt.toString("yyyy-MM-dd HH:mm")
        target_dt = datetime.strptime(uni_str, "%Y-%m-%d %H:%M")

        visible_items = self._get_visible_items()
        applied_count = 0

        for row, item in enumerate(visible_items):
            if item.get("checked", True):
                item["new_dt"] = target_dt
                item["is_modified"] = True

                dt_edit = self.table.cellWidget(row, 6)
                if isinstance(dt_edit, QDateTimeEdit):
                    dt_edit.blockSignals(True)
                    dt_edit.setDateTime(qdt)
                    dt_edit.blockSignals(False)

                self._update_row_diff_preview(row, item)
                applied_count += 1

        self._update_table_summary()
        self._log(f"📌 已將 {applied_count} 部影片統一設定為發布時間: {uni_str}。")

    def _apply_clear_schedule(self):
        """Clears scheduled publishAt (reverts to private/unlisted) for checked items in current view."""
        target_priv = self.combo_clear_privacy.currentData()
        visible_items = self._get_visible_items()
        applied_count = 0

        for row, item in enumerate(visible_items):
            if item.get("checked", True):
                item["new_dt"] = None
                item["new_privacy"] = target_priv
                item["is_modified"] = True
                self._update_row_diff_preview(row, item)
                applied_count += 1

        self._update_table_summary()
        self._log(f"🚫 已清除 {applied_count} 部影片之排程時間 (改設為 {target_priv})。")

    # --------------------------------------------------------------------------
    # Table Toolbar Helpers (Current View Scoped)
    # --------------------------------------------------------------------------
    def _set_current_view_checkboxes(self, state: bool):
        visible_items = self._get_visible_items()
        for row, item in enumerate(visible_items):
            item["checked"] = state
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, QCheckBox):
                chk.blockSignals(True)
                chk.setChecked(state)
                chk.blockSignals(False)
        self._update_table_summary()

    def _select_only_modified_current_view(self):
        visible_items = self._get_visible_items()
        for row, item in enumerate(visible_items):
            state = bool(item.get("is_modified", False))
            item["checked"] = state
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, QCheckBox):
                chk.blockSignals(True)
                chk.setChecked(state)
                chk.blockSignals(False)
        self._update_table_summary()

    def _move_row(self, direction: int):
        """Moves selected row up (-1) or down (+1) within the current category."""
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        target_row = current_row + direction
        visible_items = self._get_visible_items()
        if target_row < 0 or target_row >= len(visible_items):
            return

        item_a = visible_items[current_row]
        item_b = visible_items[target_row]

        # Swap in the underlying self.video_items list
        idx_a = self.video_items.index(item_a)
        idx_b = self.video_items.index(item_b)
        self.video_items[idx_a], self.video_items[idx_b] = self.video_items[idx_b], self.video_items[idx_a]

        self._populate_table()
        self.table.selectRow(target_row)

    def _sort_items(self, reverse: bool = False):
        """Sorts videos by original schedule time."""
        if not self.video_items:
            return

        def sort_key(item):
            dt = item.get("original_dt")
            if dt is None:
                return datetime.max if not reverse else datetime.min
            return dt

        self.video_items.sort(key=sort_key, reverse=reverse)
        self._populate_table()
        self._log("🕒 已依原排程時間重新排序影片清單。")

    def _clear_table(self):
        self.video_items.clear()
        self.table.setRowCount(0)
        self._update_category_tab_counts()
        self._update_table_summary()
        self._log("🧹 已清空影片清單。")

    # --------------------------------------------------------------------------
    # Batch Update Execution
    # --------------------------------------------------------------------------
    def _execute_batch_update(self):
        """Gathers modified tasks across all loaded items, presents confirmation modal, then launches worker."""
        tasks = []
        reg_count = 0
        shorts_count = 0

        for item in self.video_items:
            if item.get("checked", True) and item.get("is_modified", False):
                is_short = item.get("is_short", False)
                if is_short: shorts_count += 1
                else: reg_count += 1

                tasks.append({
                    "video_id": item["id"],
                    "title": item.get("title", ""),
                    "new_publish_at": item.get("new_dt"),
                    "new_privacy_status": item.get("new_privacy", "private"),
                    "is_short": is_short
                })

        if not tasks:
            QMessageBox.information(self, "無排程變更", "目前勾選的影片皆無排程時間變更。請先套用等距排程或平移時間！")
            return

        # Confirmation Dialog Breakdown
        preview_lines = []
        for t in tasks[:8]:
            type_tag = "[Shorts]" if t["is_short"] else "[長片]"
            sched_txt = t["new_publish_at"].strftime("%Y-%m-%d %H:%M") if t["new_publish_at"] else "取消排程"
            preview_lines.append(f"• {type_tag} 《{t['title'][:22]}》 -> {sched_txt}")
        if len(tasks) > 8:
            preview_lines.append(f"... 等共 {len(tasks)} 部影片")

        confirm_msg = (
            f"即將透過 YouTube Data API v3 批次修改以下 {len(tasks)} 部影片的排程發布時間：\n"
            f"📊 統計明細：🎥 一般長片 {reg_count} 部 | 📱 Shorts 短影音 {shorts_count} 部\n\n"
            + "\n".join(preview_lines) +
            "\n\n確定要立即套用修改嗎？"
        )
        reply = QMessageBox.question(
            self,
            "確認批次修改排程",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_execute.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setRange(0, len(tasks))
        self.progress_bar.setValue(0)
        self.lbl_action_status.setText(f"正在更新排程中 (0/{len(tasks)})...")

        self.update_worker = BatchScheduleWorker(engine=self.engine, tasks=tasks)
        self.update_worker.item_started.connect(self._on_item_update_started)
        self.update_worker.item_finished.connect(self._on_item_update_finished)
        self.update_worker.progress.connect(self._on_update_progress)
        self.update_worker.all_finished.connect(self._on_all_updates_finished)
        self.update_worker.log_message.connect(self._log)
        self.update_worker.fatal_error.connect(lambda err: QMessageBox.critical(self, "批次修改中斷", err))
        self.update_worker.start()

    def _on_item_update_started(self, video_id: str, title: str):
        # Update result column for visible row if present
        visible_items = self._get_visible_items()
        for r, item in enumerate(visible_items):
            if item.get("id") == video_id:
                item_res = self.table.item(r, 8)
                if item_res:
                    item_res.setText("🔄 更新中...")
                    item_res.setForeground(QColor("#00d2ff"))
                break

    def _on_item_update_finished(self, video_id: str, success: bool, msg: str, info: dict):
        # Update underlying item
        for item in self.video_items:
            if item.get("id") == video_id:
                item["result_text"] = msg
                if success:
                    item["original_dt"] = item["new_dt"]
                    item["is_modified"] = False
                break

        # Update visible table row if present
        visible_items = self._get_visible_items()
        for r, item in enumerate(visible_items):
            if item.get("id") == video_id:
                item_res = self.table.item(r, 8)
                if item_res:
                    item_res.setText(msg)
                    item_res.setForeground(QColor("#4ecca3" if success else "#e94560"))

                if success:
                    item_orig = self.table.item(r, 5)
                    if item_orig:
                        ndt = item["new_dt"]
                        item_orig.setText(ndt.strftime("%Y-%m-%d %H:%M") if ndt else "— (未排程)")
                        item_orig.setForeground(QColor("#cbd5e1" if ndt else "#64748b"))

                    self._update_row_diff_preview(r, item)
                break

    def _on_update_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)
        self.lbl_action_status.setText(f"更新排程中 ({current}/{total})...")

    def _on_all_updates_finished(self, success_count: int, fail_count: int):
        self.btn_execute.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_action_status.setText(f"排程修改完畢！成功: {success_count}, 失敗: {fail_count}")
        self._update_table_summary()

        if fail_count == 0:
            QMessageBox.information(self, "排程修改成功", f"🎉 太棒了！所有 {success_count} 部影片排程時間皆已順利更新至 YouTube！")
        else:
            QMessageBox.warning(self, "排程修改部分失敗", f"完成批次修改，其中 {success_count} 部成功，{fail_count} 部遭遇錯誤，詳情請參閱下方日誌。")

    def _cancel_operation(self):
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.fetch_worker.cancel()
            self._log("🛑 正在取消讀取...")
        if self.update_worker and self.update_worker.isRunning():
            self.update_worker.cancel()
            self._log("🛑 正在取消批次更新...")
        self.btn_cancel.setEnabled(False)


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = YouTubeBatchSchedulerWidget()
    window.setWindowTitle("📅 YouTube 批次排程修改工具 (Shorts & 長片獨立管理)")
    window.resize(1220, 820)
    window.show()
    sys.exit(app.exec())
