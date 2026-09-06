#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Uploader Tab (PyQt6)
=============================
- Full Playlist Management (Select existing / Create new with privacy setting)
- Premiere & Scheduled Release (Unified datetime or staggered/serial intervals)
- Resumable 4K Chunked Upload Progress & Status Reporting
- Folder Scanning with Metadata Pairing (_social.txt)
- Duplicate Prevention via upload_history.json
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QTextEdit, QLineEdit, QComboBox, QProgressBar, QCheckBox,
    QGroupBox, QScrollArea, QFrame, QMessageBox, QSizePolicy, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton, QButtonGroup,
    QDateTimeEdit, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDateTime, QUrl
from PyQt6.QtGui import QFont, QColor, QDesktopServices

from youtube_uploader_engine import (
    YouTubeUploaderEngine,
    CredentialPoolManager,
    MetadataParser,
    GOOGLE_API_AVAILABLE
)
from youtube_logger import logger, quota_tracker


class VideoUploadWorker(QThread):
    """Background worker for batch uploading videos to YouTube."""

    file_progress = pyqtSignal(int, int, float, float)  # bytes_done, total_bytes, speed_mb, eta_s
    file_status = pyqtSignal(int, str)                  # row_idx, status_text
    file_finished = pyqtSignal(int, dict)               # row_idx, result_info
    log_message = pyqtSignal(str)                       # log text
    all_finished = pyqtSignal()
    fatal_error = pyqtSignal(str)

    def __init__(
        self,
        engine: YouTubeUploaderEngine,
        items_to_upload: List[Dict[str, Any]],
        playlist_id: Optional[str] = None,
        create_playlist_title: Optional[str] = None,
        create_playlist_privacy: str = "public",
        privacy_status: str = "unlisted",
        is_premiere: bool = False,
        start_premiere_time: Optional[datetime] = None,
        stagger_interval_seconds: int = 0,
        auto_thumbnail: bool = True,
        auto_comment: bool = True,
        enable_nav_chain: bool = True
    ):
        super().__init__()
        self.engine = engine
        self.items = items_to_upload
        self.playlist_id = playlist_id
        self.create_playlist_title = create_playlist_title
        self.create_playlist_privacy = create_playlist_privacy
        self.privacy_status = privacy_status
        self.is_premiere = is_premiere
        self.start_premiere_time = start_premiere_time
        self.stagger_interval_seconds = stagger_interval_seconds
        self.auto_thumbnail = auto_thumbnail
        self.auto_comment = auto_comment
        self.enable_nav_chain = enable_nav_chain
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.engine.request_cancel()

    def run(self):
        try:
            self.log_message.emit("🚀 Initializing YouTube API connection...")
            self.engine.connect()

            # 1. Handle Playlist Creation if requested
            target_playlist_id = self.playlist_id
            if self.create_playlist_title:
                self.log_message.emit(f"📋 Creating new playlist: '{self.create_playlist_title}' ({self.create_playlist_privacy})...")
                target_playlist_id = self.engine.create_playlist(
                    title=self.create_playlist_title,
                    description=f"Curated 4K Audio-Reactive MV Collection: {self.create_playlist_title}",
                    privacy=self.create_playlist_privacy
                )
                self.log_message.emit(f"✅ Playlist created successfully! ID: {target_playlist_id}")

            # 2. Iterate through items
            total_items = len(self.items)
            self.log_message.emit(f"🎬 Starting batch upload for {total_items} video(s)...")

            for idx, item in enumerate(self.items):
                if self._is_cancelled:
                    self.log_message.emit("🛑 Batch upload cancelled by user.")
                    break

                row_idx = item["row_idx"]
                video_path = item["path"]
                title = item["title"]
                description = item["description"]
                tags = item["tags"]
                filename = item["filename"]

                # Calculate scheduled premiere time for this item
                item_publish_at = None
                if self.is_premiere and self.start_premiere_time:
                    offset = timedelta(seconds=self.stagger_interval_seconds * idx)
                    item_publish_at = self.start_premiere_time + offset

                # Build Chained Navigation Links if enabled
                album_nav = None
                if self.enable_nav_chain:
                    album_nav = {}
                    if idx > 0:
                        album_nav["prev_title"] = self.items[idx - 1]["title"]
                        album_nav["prev_url"] = self.items[idx - 1].get("youtube_url", "")
                    if idx < total_items - 1:
                        album_nav["next_title"] = self.items[idx + 1]["title"]
                        album_nav["next_url"] = self.items[idx + 1].get("youtube_url", "")
                    if target_playlist_id:
                        album_nav["playlist_url"] = f"https://www.youtube.com/playlist?list={target_playlist_id}"

                self.file_status.emit(row_idx, "Uploading...")
                self.log_message.emit(f"\n[{idx+1}/{total_items}] Uploading: {filename} ({item['size_str']})")

                def on_progress(bytes_done, total_bytes, speed_mb, eta_s):
                    self.file_progress.emit(bytes_done, total_bytes, speed_mb, eta_s)

                def on_status(msg):
                    self.log_message.emit(f"  ℹ️ {msg}")

                try:
                    result = self.engine.upload_video(
                        video_path=video_path,
                        title=title,
                        description=description,
                        tags=tags,
                        privacy_status=self.privacy_status,
                        publish_at=item_publish_at,
                        playlist_id=target_playlist_id,
                        auto_thumbnail=self.auto_thumbnail,
                        auto_comment=self.auto_comment,
                        album_nav=album_nav,
                        progress_cb=on_progress,
                        status_cb=on_status
                    )
                    self.file_status.emit(row_idx, "Done")
                    self.file_finished.emit(row_idx, result)
                    self.log_message.emit(f"  ✅ Completed: {filename} -> {result['url']}")

                except Exception as e:
                    err_msg = str(e)
                    self.log_message.emit(f"  ❌ Error uploading {filename}: {err_msg}")
                    self.file_status.emit(row_idx, "Failed")
                    if "quota" in err_msg.lower():
                        self.fatal_error.emit(f"Daily quota reached: {err_msg}")
                        break

            self.log_message.emit("\n🏁 Batch processing finished.")
            self.all_finished.emit()

        except Exception as e:
            self.fatal_error.emit(str(e))
            self.log_message.emit(f"❌ Fatal error in upload worker: {e}")


class YouTubeUploaderTab(QWidget):
    """PyQt6 Tab Widget for YouTube Video Publishing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = YouTubeUploaderEngine()
        self.worker: Optional[VideoUploadWorker] = None
        self.scanned_items: List[Dict[str, Any]] = []

        self._init_ui()

        # Load default folder if exists
        default_dir = "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Delay Trail Hypnosis"
        if os.path.exists(default_dir):
            self.dir_input.setText(default_dir)
            self.scan_directory()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ----------------------------------------------------------------------
        # Top Header Banner
        # ----------------------------------------------------------------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1a2e, stop:1 #16213e);
                border-radius: 8px;
                padding: 10px;
                border: 1px solid #0f3460;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 5, 10, 5)

        title_lbl = QLabel("📤 YouTube 4K MV 自動發布中心 (4K Auto-Uploader)")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #00d2ff;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        self.lbl_channel = QLabel("📺 目前頻道: (點擊檢查)")
        self.lbl_channel.setStyleSheet("font-size: 13px; font-weight: bold; color: #4ecca3; background: #0f141d; padding: 4px 10px; border-radius: 4px; border: 1px solid #1a2634;")
        header_layout.addWidget(self.lbl_channel)

        self.btn_check_channel = QPushButton("🔍 檢查頻道")
        self.btn_check_channel.setStyleSheet("""
            QPushButton {
                background: #0f3460;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #164282; }
        """)
        self.btn_check_channel.clicked.connect(self._check_current_channel)
        header_layout.addWidget(self.btn_check_channel)

        self.btn_switch_channel = QPushButton("🔄 切換頻道")
        self.btn_switch_channel.setStyleSheet("""
            QPushButton {
                background: #533483;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #6c46a8; }
        """)
        self.btn_switch_channel.clicked.connect(self._switch_channel)
        header_layout.addWidget(self.btn_switch_channel)

        self.btn_guide = QPushButton("📖 憑證設定指南")
        self.btn_guide.setStyleSheet("""
            QPushButton {
                background: #e94560;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #ff5e78; }
        """)
        self.btn_guide.clicked.connect(self._open_setup_guide)
        header_layout.addWidget(self.btn_guide)

        main_layout.addWidget(header_frame)

        # ----------------------------------------------------------------------
        # 1. Directory Selection Group
        # ----------------------------------------------------------------------
        dir_group = QGroupBox("📁 1. 待發布影片目錄 (Video Source Directory)")
        dir_layout = QHBoxLayout(dir_group)

        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("請選擇存放 4K 影片與 _social.txt 的目錄...")
        self.dir_input.setStyleSheet("padding: 6px; font-size: 13px;")
        dir_layout.addWidget(self.dir_input, 4)

        btn_browse = QPushButton("瀏覽目錄...")
        btn_browse.setStyleSheet("padding: 6px 12px;")
        btn_browse.clicked.connect(self._browse_directory)
        dir_layout.addWidget(btn_browse, 1)

        self.btn_rescan = QPushButton("🔄 重新掃描")
        self.btn_rescan.setStyleSheet("padding: 6px 14px; font-weight: bold; background: #0f3460; color: white;")
        self.btn_rescan.clicked.connect(self.scan_directory)
        dir_layout.addWidget(self.btn_rescan, 1)

        main_layout.addWidget(dir_group)

        # ----------------------------------------------------------------------
        # Middle Control Grid (Playlists + Premiere & Privacy)
        # ----------------------------------------------------------------------
        grid_config = QHBoxLayout()

        # Group A: Playlist Settings
        playlist_group = QGroupBox("📋 2. 播放清單管理 (Playlist Settings)")
        pl_layout = QVBoxLayout(playlist_group)

        self.chk_playlist = QCheckBox("啟用加入播放清單功能")
        self.chk_playlist.setChecked(True)
        self.chk_playlist.setStyleSheet("font-weight: bold; color: #4ecca3;")
        self.chk_playlist.toggled.connect(self._toggle_playlist_ui)
        pl_layout.addWidget(self.chk_playlist)

        self.pl_mode_group = QButtonGroup(self)

        # Option A: Existing Playlist
        h_exist = QHBoxLayout()
        self.radio_pl_exist = QRadioButton("加入既有清單:")
        self.pl_mode_group.addButton(self.radio_pl_exist)
        h_exist.addWidget(self.radio_pl_exist)

        self.combo_playlists = QComboBox()
        self.combo_playlists.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h_exist.addWidget(self.combo_playlists, 1)

        self.btn_refresh_pl = QPushButton("🔄 載入清單")
        self.btn_refresh_pl.clicked.connect(self._fetch_user_playlists)
        h_exist.addWidget(self.btn_refresh_pl)
        pl_layout.addLayout(h_exist)

        # Option B: Create New Playlist
        h_new = QHBoxLayout()
        self.radio_pl_new = QRadioButton("建立全新清單:")
        self.radio_pl_new.setChecked(True)
        self.pl_mode_group.addButton(self.radio_pl_new)
        h_new.addWidget(self.radio_pl_new)

        self.input_new_pl_title = QLineEdit()
        self.input_new_pl_title.setPlaceholderText("例如: Techno 2026-2: Delay Trail Hypnosis")
        self.input_new_pl_title.setText("Techno 2026-2: Delay Trail Hypnosis")
        h_new.addWidget(self.input_new_pl_title, 2)

        self.combo_pl_privacy = QComboBox()
        self.combo_pl_privacy.addItems(["公開 (public)", "不公開 (unlisted)", "私人 (private)"])
        h_new.addWidget(self.combo_pl_privacy, 1)
        pl_layout.addLayout(h_new)

        grid_config.addWidget(playlist_group, 1)

        # Group B: Premiere & Privacy Schedule
        premiere_group = QGroupBox("⏰ 3. 發布與首播時間 (Premiere & Release Schedule)")
        pr_layout = QVBoxLayout(premiere_group)

        self.release_mode_group = QButtonGroup(self)

        # Mode 1: Immediate
        h_imm = QHBoxLayout()
        self.radio_imm = QRadioButton("立即發布 / 手動發布:")
        self.release_mode_group.addButton(self.radio_imm)
        h_imm.addWidget(self.radio_imm)

        self.combo_imm_privacy = QComboBox()
        self.combo_imm_privacy.addItems(["不公開 (unlisted) - 推薦先驗證4K畫質", "公開 (public)", "私人 (private)"])
        h_imm.addWidget(self.combo_imm_privacy, 1)
        pr_layout.addLayout(h_imm)

        # Mode 2: Premiere Scheduled
        h_prem = QHBoxLayout()
        self.radio_prem = QRadioButton("排程首播 (Premiere):")
        self.radio_prem.setChecked(True)
        self.release_mode_group.addButton(self.radio_prem)
        h_prem.addWidget(self.radio_prem)

        self.dt_premiere = QDateTimeEdit()
        self.dt_premiere.setCalendarPopup(True)
        self.dt_premiere.setDisplayFormat("yyyy-MM-dd HH:mm")
        # Default to tomorrow at 20:00 local time
        default_dt = datetime.now() + timedelta(days=1)
        default_dt = default_dt.replace(hour=20, minute=0, second=0, microsecond=0)
        self.dt_premiere.setDateTime(QDateTime.fromString(default_dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))
        self.dt_premiere.dateTimeChanged.connect(self._recalculate_schedule_table)
        h_prem.addWidget(self.dt_premiere, 1)
        pr_layout.addLayout(h_prem)

        # Staggered Interval
        h_stagger = QHBoxLayout()
        self.chk_stagger = QCheckBox("啟用階梯連載間隔 (每首依序首播)")
        self.chk_stagger.setChecked(True)
        self.chk_stagger.setStyleSheet("color: #00d2ff;")
        self.chk_stagger.toggled.connect(self._recalculate_schedule_table)
        h_stagger.addWidget(self.chk_stagger)

        self.combo_stagger = QComboBox()
        self.combo_stagger.addItem("每 12 小時 (長片首播: 一天兩片)", 43200)
        self.combo_stagger.addItem("每 4 小時 (Shorts首播: 一天四片)", 14400)
        self.combo_stagger.addItem("每 1 天 (24 小時)", 86400)
        self.combo_stagger.addItem("每 6 小時", 21600)
        self.combo_stagger.addItem("每 8 小時", 28800)
        self.combo_stagger.addItem("每 2 小時", 7200)
        self.combo_stagger.addItem("每 2 天", 172800)
        self.combo_stagger.addItem("每 3 天", 259200)
        self.combo_stagger.currentIndexChanged.connect(self._recalculate_schedule_table)
        h_stagger.addWidget(self.combo_stagger)
        pr_layout.addLayout(h_stagger)

        grid_config.addWidget(premiere_group, 1)
        main_layout.addLayout(grid_config)

        # ----------------------------------------------------------------------
        # Release Enhancements Pipeline Strip
        # ----------------------------------------------------------------------
        enhance_box = QHBoxLayout()
        self.chk_thumbnail = QCheckBox("🖼️ 4K 黃金影格自動封面 (Beat-Synced)")
        self.chk_thumbnail.setChecked(True)
        self.chk_thumbnail.setStyleSheet("color: #00d2ff; font-weight: bold;")
        enhance_box.addWidget(self.chk_thumbnail)

        self.chk_comment = QCheckBox("💬 自動發表置頂導流留言 (Pinned Comment)")
        self.chk_comment.setChecked(True)
        self.chk_comment.setStyleSheet("color: #4ecca3; font-weight: bold;")
        enhance_box.addWidget(self.chk_comment)

        self.chk_nav = QCheckBox("🔗 說明欄前後曲目連鎖導覽")
        self.chk_nav.setChecked(True)
        self.chk_nav.setStyleSheet("color: #ffd369; font-weight: bold;")
        enhance_box.addWidget(self.chk_nav)

        enhance_box.addStretch()

        self.btn_check_4k = QPushButton("🛡️ 檢查 4K 轉碼哨兵")
        self.btn_check_4k.setStyleSheet("""
            QPushButton {
                background: #1f4068;
                color: #e4e4e4;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: #162447; }
        """)
        self.btn_check_4k.clicked.connect(self._check_4k_transcode_status)
        enhance_box.addWidget(self.btn_check_4k)

        main_layout.addLayout(enhance_box)

        # ----------------------------------------------------------------------
        # 4. Video Queue Table
        # ----------------------------------------------------------------------
        table_group = QGroupBox("🎬 4. 發布佇列 (Video Queue)")
        table_layout = QVBoxLayout(table_group)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "選取", "檔名", "檔案大小", "YouTube 標題", "預計發布 / 首播時間", "狀態", "連結"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        table_layout.addWidget(self.table)

        main_layout.addWidget(table_group, 3)

        # ----------------------------------------------------------------------
        # 5. Progress Bar & Transfer Stats
        # ----------------------------------------------------------------------
        prog_layout = QVBoxLayout()
        self.lbl_stats = QLabel("準備就緒。共 0 部影片待發布。")
        self.lbl_stats.setStyleSheet("font-weight: bold; color: #a8b2d1;")
        prog_layout.addWidget(self.lbl_stats)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                height: 20px;
                background: #1e1e2f;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4ecca3, stop:1 #00d2ff);
            }
        """)
        prog_layout.addWidget(self.progress_bar)

        main_layout.addLayout(prog_layout)

        # ----------------------------------------------------------------------
        # 6. Action Control Buttons
        # ----------------------------------------------------------------------
        btn_box = QHBoxLayout()

        self.btn_select_all = QPushButton("☑️ 全選")
        self.btn_select_all.clicked.connect(self._select_all)
        btn_box.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("◻️ 取消全選")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        btn_box.addWidget(self.btn_deselect_all)

        btn_box.addStretch()

        self.btn_start = QPushButton("🚀 開始批次發布與加入清單")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: #4ecca3;
                color: #121212;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 6px;
            }
            QPushButton:hover { background: #5df0c1; }
            QPushButton:disabled { background: #555; color: #888; }
        """)
        self.btn_start.clicked.connect(self.start_batch_upload)
        btn_box.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("🛑 取消發布")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("background: #e94560; color: white; padding: 10px 18px; border-radius: 6px;")
        self.btn_cancel.clicked.connect(self.cancel_upload)
        btn_box.addWidget(self.btn_cancel)

        main_layout.addLayout(btn_box)

        # ----------------------------------------------------------------------
        # 7. Realtime Log Output & Telemetry Bar
        # ----------------------------------------------------------------------
        log_header = QHBoxLayout()
        lbl_log_title = QLabel("📋 即時執行與診斷日誌 (自動循環保存於 logs/youtube_uploader.log)")
        lbl_log_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #8892b0;")
        log_header.addWidget(lbl_log_title)
        log_header.addStretch()

        btn_quota = QPushButton("📊 今日配額統計")
        btn_quota.setToolTip("查看今日各憑證專案的 YouTube API 配額點數消耗與剩餘額度")
        btn_quota.setStyleSheet("background: #1f4068; color: #e0e6ed; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        btn_quota.clicked.connect(self._show_quota_analysis)
        log_header.addWidget(btn_quota)

        btn_open_log = QPushButton("📁 開啟完整日誌")
        btn_open_log.setToolTip("在外部編輯器中開啟 logs/youtube_uploader.log 查看詳細偵錯紀錄")
        btn_open_log.setStyleSheet("background: #162447; color: #e0e6ed; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        btn_open_log.clicked.connect(self._open_log_file)
        log_header.addWidget(btn_open_log)

        btn_clear = QPushButton("🧹 清除畫面")
        btn_clear.setToolTip("清除下方日誌顯示區域（不影響硬碟中的 log 檔案）")
        btn_clear.setStyleSheet("background: #1b1e2b; color: #a0a8b9; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        btn_clear.clicked.connect(self._clear_log_display)
        log_header.addWidget(btn_clear)

        main_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(140)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background: #0f141d;
                color: #5af78e;
                font-family: Menlo, Monaco, Consolas, monospace;
                font-size: 11px;
                border: 1px solid #1a2634;
            }
        """)
        main_layout.addWidget(self.log_text)

    # --------------------------------------------------------------------------
    # UI Event Handlers
    # --------------------------------------------------------------------------
    def _open_log_file(self):
        log_file = Path(__file__).resolve().parent / "logs" / "youtube_uploader.log"
        if log_file.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file)))
        else:
            QMessageBox.information(self, "日誌檔案", "目前尚未產生任何日誌紀錄 (logs/youtube_uploader.log)！")

    def _clear_log_display(self):
        self.log_text.clear()

    def _show_quota_analysis(self):
        today = datetime.now().strftime("%Y-%m-%d")
        data = quota_tracker.usage_data.get(today, {})
        lines = [f"📊 【YouTube API 今日配額統計】 (日期: {today})\n" + "=" * 50]
        if not data:
            lines.append("🎉 今日尚未進行任何會消耗配額的 API 操作。")
            lines.append("各憑證專案每日均擁有 10,000 點免費額度 (單一專案可發布約 6 部 4K 影片)。")
        else:
            total_consumed = 0
            for proj_name, info in data.items():
                pts = info.get("total_points", 0)
                total_consumed += pts
                rem = max(0, 10000 - pts)
                avail_uploads = rem // 1600
                lines.append(f"\n🔹 憑證專案: [{proj_name}]")
                lines.append(f"   已消耗: {pts:,} / 10,000 點")
                lines.append(f"   剩餘額度: {rem:,} 點 (預計還可上傳 {avail_uploads} 部影片)")
                lines.append(f"   最後更新: {info.get('last_updated', 'N/A')}")
                calls = info.get("calls", {})
                if calls:
                    call_summary = ", ".join([f"{k}: {v}次" for k, v in calls.items()])
                    lines.append(f"   API 呼叫明細: {call_summary}")

            lines.append("\n" + "=" * 50)
            lines.append(f"💡 總計今日已消耗點數: {total_consumed:,} 點")
            lines.append("💡 每日配額重置時間為太平洋時間午夜 (台灣時間約 15:00 / 16:00)。")

        msg_str = "\n".join(lines)
        self.log_text.append(msg_str)
        # Scroll to bottom
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        QMessageBox.information(self, "今日配額統計報告", msg_str)

    def _open_setup_guide(self):
        guide_path = Path(__file__).resolve().parent / "YOUTUBE_API_SETUP_GUIDE.md"
        if guide_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))
        else:
            QMessageBox.information(self, "說明指南", "請參閱專案目錄下的 YOUTUBE_API_SETUP_GUIDE.md 文件！")

    def _browse_directory(self):
        d = QFileDialog.getExistingDirectory(self, "選擇影片目錄", self.dir_input.text() or os.path.expanduser("~"))
        if d:
            self.dir_input.setText(d)
            self.scan_directory()

    def _toggle_playlist_ui(self, enabled: bool):
        self.radio_pl_exist.setEnabled(enabled)
        self.combo_playlists.setEnabled(enabled)
        self.btn_refresh_pl.setEnabled(enabled)
        self.radio_pl_new.setEnabled(enabled)
        self.input_new_pl_title.setEnabled(enabled)
        self.combo_pl_privacy.setEnabled(enabled)

    def _select_all(self):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def scan_directory(self):
        target_dir = self.dir_input.text().strip()
        if not target_dir or not os.path.isdir(target_dir):
            return

        self.log_text.append(f"🔍 掃描目錄: {target_dir}")
        self.scanned_items = YouTubeUploaderEngine.scan_directory(target_dir)

        # Update Default Playlist title to match directory name if empty
        folder_name = os.path.basename(target_dir)
        if not self.input_new_pl_title.text().strip():
            self.input_new_pl_title.setText(folder_name)

        self._populate_table()

    def _populate_table(self):
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.scanned_items))

        total_bytes = 0
        uploaded_count = 0

        for r, item in enumerate(self.scanned_items):
            total_bytes += item["size_bytes"]
            if item["uploaded"]:
                uploaded_count += 1

            # 0: Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked if item["uploaded"] else Qt.CheckState.Checked)
            self.table.setItem(r, 0, chk_item)

            # 1: Filename
            f_item = QTableWidgetItem(item["filename"])
            f_item.setToolTip(item["path"])
            self.table.setItem(r, 1, f_item)

            # 2: Size
            s_item = QTableWidgetItem(item["size_str"])
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 2, s_item)

            # 3: Title
            title_text = item["title"]
            title_len = len(title_text)
            t_item = QTableWidgetItem(title_text)
            if title_len > 100:
                t_item.setToolTip(f"⚠️ 標題字數 {title_len}/100 超出上限！上傳時將自動平滑截斷並收錄完整標題於說明欄。")
                t_item.setForeground(QColor("#ff5e78"))
            else:
                t_item.setToolTip(f"標題字數: {title_len}/100 (符合 YouTube 規定)")
            self.table.setItem(r, 3, t_item)

            # 4: Premiere / Release Time (will be computed)
            self.table.setItem(r, 4, QTableWidgetItem("-"))

            # 5: Status
            status_str = "✅ 已上傳" if item["uploaded"] else "⏳ 等待中"
            status_item = QTableWidgetItem(status_str)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if item["uploaded"]:
                status_item.setForeground(QColor("#4ecca3"))
            self.table.setItem(r, 5, status_item)

            # 6: Link
            link_item = QTableWidgetItem()
            if item.get("youtube_url"):
                link_item.setText("觀看 / ⚙️片尾")
                link_item.setForeground(QColor("#00d2ff"))
                link_item.setToolTip(f"雙擊開啟 YouTube Studio 片尾畫面設定頁\n{item.get('youtube_url')}")
            else:
                link_item.setText("-")
            link_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 6, link_item)

        self._recalculate_schedule_table()

        total_gb = total_bytes / (1024 ** 3)
        self.lbl_stats.setText(
            f"已載入 {len(self.scanned_items)} 部影片 (共 {total_gb:.2f} GB) | 已完成: {uploaded_count} 部 | 待上傳: {len(self.scanned_items) - uploaded_count} 部"
        )
        self.log_text.append(f"📋 載入完成！共 {len(self.scanned_items)} 部影片。")

    def _recalculate_schedule_table(self):
        """Updates the '預計發布 / 首播時間' column in the table."""
        is_premiere = self.radio_prem.isChecked()
        start_qdt = self.dt_premiere.dateTime()
        start_dt = start_qdt.toPyDateTime()

        stagger_enabled = self.chk_stagger.isChecked()
        interval_secs = self.combo_stagger.currentData() or 86400

        for r in range(self.table.rowCount()):
            time_item = self.table.item(r, 4)
            if not time_item:
                continue

            if not is_premiere:
                time_item.setText("立即發布")
                time_item.setForeground(QColor("#a8b2d1"))
            else:
                offset_secs = interval_secs * r if stagger_enabled else 0
                target_dt = start_dt + timedelta(seconds=offset_secs)
                time_str = target_dt.strftime("%Y-%m-%d %H:%M")
                time_item.setText(f"⏰ {time_str}")
                time_item.setForeground(QColor("#00d2ff"))

    def _on_table_double_clicked(self, row: int, col: int):
        if row < len(self.scanned_items):
            it = self.scanned_items[row]
            vid = it.get("video_id")
            if vid:
                # Open directly to Studio edit page for one-click End Screen import!
                studio_url = f"https://studio.youtube.com/video/{vid}/edit"
                QDesktopServices.openUrl(QUrl(studio_url))
            elif it.get("youtube_url"):
                QDesktopServices.openUrl(QUrl(it["youtube_url"]))

    def _check_current_channel(self):
        """Checks and displays currently authenticated YouTube channel."""
        self.btn_check_channel.setEnabled(False)
        self.btn_check_channel.setText("連線中...")
        self.log_text.append("🔍 正在查詢當前授權的 YouTube 頻道...")

        def _worker():
            try:
                info = self.engine.get_channel_info()
                return info, None
            except Exception as e:
                return {}, str(e)

        info, err = _worker()
        self.btn_check_channel.setEnabled(True)
        self.btn_check_channel.setText("🔍 檢查頻道")

        if err or not info.get("title") or info.get("title") == "未知頻道":
            self.lbl_channel.setText("📺 尚未授權或授權過期")
            self.lbl_channel.setStyleSheet("font-size: 13px; font-weight: bold; color: #ff5e78; background: #0f141d; padding: 4px 10px; border-radius: 4px; border: 1px solid #1a2634;")
            self.log_text.append(f"⚠️ 尚未連線或憑證需授權: {err or '請點擊發布進行登入'}")
            return

        display_name = info['title']
        if info.get('custom_url'):
            display_name += f" ({info['custom_url']})"

        self.lbl_channel.setText(f"📺 頻道: 【 {display_name} 】")
        self.lbl_channel.setStyleSheet("font-size: 13px; font-weight: bold; color: #4ecca3; background: #0f141d; padding: 4px 10px; border-radius: 4px; border: 1px solid #1a2634;")
        self.log_text.append(f"✅ 當前登入頻道: {info['title']} (ID: {info['id']})")

    def _switch_channel(self):
        """Clears local OAuth token and prompts user to re-select channel."""
        confirm = QMessageBox.question(
            self,
            "切換頻道",
            "是否清除當前的 YouTube 登入授權並重新選擇頻道？\n\n下次點擊發布或檢查時，瀏覽器將彈出登入視窗讓您選擇其他頻道。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.engine.logout()
            self.lbl_channel.setText("📺 尚未登入 / 請點擊發布登入")
            self.lbl_channel.setStyleSheet("font-size: 13px; font-weight: bold; color: #a8b2d1; background: #0f141d; padding: 4px 10px; border-radius: 4px; border: 1px solid #1a2634;")
            self.combo_playlists.clear()
            self.log_text.append("🔄 已清除舊授權憑證，下次操作時可在瀏覽器挑選想要登入的 YouTube 頻道！")
            QMessageBox.information(self, "切換頻道", "已成功登出！下次操作將開啟瀏覽器讓您挑選目標頻道。")

    def _check_4k_transcode_status(self):
        """Queries YouTube API to see if uploaded videos have completed 4K processing."""
        uploaded_rows = []
        for r in range(self.table.rowCount()):
            if r < len(self.scanned_items):
                it = self.scanned_items[r]
                vid = it.get("video_id")
                if vid:
                    uploaded_rows.append((r, vid, it["filename"]))

        if not uploaded_rows:
            QMessageBox.information(self, "4K 轉碼哨兵", "目前佇列中尚無已上傳的影片可供檢查轉碼狀態。")
            return

        self.btn_check_4k.setEnabled(False)
        self.btn_check_4k.setText("檢查中...")
        self.log_text.append(f"🛡️ 正在向 YouTube 伺服器檢查 {len(uploaded_rows)} 部影片的 4K 轉碼狀態 (每部僅消耗 1 點配額)...")

        for r, vid, fn in uploaded_rows:
            res = self.engine.check_transcode_status(vid)
            status_item = self.table.item(r, 5)
            if status_item:
                if res.get("ready") and res.get("is_hd_or_4k"):
                    status_item.setText("4K Ready ✅")
                    status_item.setForeground(QColor("#4ecca3"))
                    self.log_text.append(f"  🎬 [{fn}] 4K/HD 轉碼已完成！狀態: {res['status']} | 畫質: {res['definition']}")
                elif res.get("status") == "processing":
                    status_item.setText("4K 轉碼中 ⏳")
                    status_item.setForeground(QColor("#ffd369"))
                    self.log_text.append(f"  ⏳ [{fn}] YouTube 伺服器正在進行 4K 轉碼處理中...")
                else:
                    status_item.setText(f"已就緒 ({res.get('definition', 'sd')})")
                    self.log_text.append(f"  ℹ️ [{fn}] 狀態: {res.get('status')} | 畫質: {res.get('definition')}")

        self.btn_check_4k.setEnabled(True)
        self.btn_check_4k.setText("🛡️ 檢查 4K 轉碼哨兵")
        QMessageBox.information(self, "4K 轉碼哨兵", "4K 轉碼狀態檢查完成！詳情請參閱下方即時日誌。")

    def _fetch_user_playlists(self):
        """Loads user's YouTube playlists into the dropdown."""
        self.btn_refresh_pl.setEnabled(False)
        self.btn_refresh_pl.setText("連線中...")
        self.log_text.append("🔄 正在向 YouTube API 獲取頻道的播放清單...")

        def _worker():
            try:
                playlists = self.engine.list_playlists()
                return playlists, None
            except Exception as e:
                return [], str(e)

        # In a real app we can use a small QThread or direct call
        playlists, err = _worker()
        self.btn_refresh_pl.setEnabled(True)
        self.btn_refresh_pl.setText("🔄 載入清單")

        if err:
            self.log_text.append(f"❌ 取得播放清單失敗: {err}")
            QMessageBox.warning(self, "API 錯誤", f"無法讀取播放清單:\n{err}\n\n請確認 credentials 設定與登入權限。")
            return

        self.combo_playlists.clear()
        for pl in playlists:
            self.combo_playlists.addItem(f"{pl['title']} ({pl['item_count']} 部)", pl["id"])

        self.radio_pl_exist.setChecked(True)
        self.log_text.append(f"✅ 成功載入 {len(playlists)} 個播放清單！")

    # --------------------------------------------------------------------------
    # Upload Control
    # --------------------------------------------------------------------------
    def start_batch_upload(self):
        if not GOOGLE_API_AVAILABLE:
            QMessageBox.critical(
                self, "缺少依賴套件",
                "尚未安裝 Google API 庫！請在終端執行：\npip install google-api-python-client google-auth-oauthlib"
            )
            return

        if not self.engine.cred_manager.has_credentials():
            QMessageBox.warning(
                self, "缺少憑證檔案",
                "未在專案中找到 client_secrets.json 憑證檔案！\n\n"
                "請點擊右上角「3分鐘免費憑證設定指南」，\n"
                "下載後放入 youtube_credentials/ 資料夾。"
            )
            return

        # Collect checked items
        items_to_upload = []
        for r in range(self.table.rowCount()):
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                data = dict(self.scanned_items[r])
                data["row_idx"] = r
                items_to_upload.append(data)

        if not items_to_upload:
            QMessageBox.information(self, "提示", "請至少勾選一部待上傳的影片！")
            return

        # Prepare parameters
        playlist_id = None
        create_title = None
        create_privacy = "public"

        if self.chk_playlist.isChecked():
            if self.radio_pl_exist.isChecked():
                playlist_id = self.combo_playlists.currentData()
            else:
                create_title = self.input_new_pl_title.text().strip()
                if not create_title:
                    QMessageBox.warning(self, "播放清單名稱", "請輸入新播放清單名稱！")
                    return
                # Privacy mapping
                sel_priv = self.combo_pl_privacy.currentText()
                if "unlisted" in sel_priv: create_privacy = "unlisted"
                elif "private" in sel_priv: create_privacy = "private"
                else: create_privacy = "public"

        is_premiere = self.radio_prem.isChecked()
        start_premiere = self.dt_premiere.dateTime().toPyDateTime() if is_premiere else None
        stagger_secs = self.combo_stagger.currentData() if self.chk_stagger.isChecked() else 0

        # Immediate privacy
        imm_text = self.combo_imm_privacy.currentText()
        privacy_status = "unlisted"
        if "public" in imm_text: privacy_status = "public"
        elif "private" in imm_text: privacy_status = "private"

        # UI State
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)

        # Launch worker
        self.worker = VideoUploadWorker(
            engine=self.engine,
            items_to_upload=items_to_upload,
            playlist_id=playlist_id,
            create_playlist_title=create_title,
            create_playlist_privacy=create_privacy,
            privacy_status=privacy_status,
            is_premiere=is_premiere,
            start_premiere_time=start_premiere,
            stagger_interval_seconds=stagger_secs,
            auto_thumbnail=self.chk_thumbnail.isChecked(),
            auto_comment=self.chk_comment.isChecked(),
            enable_nav_chain=self.chk_nav.isChecked()
        )

        self.worker.file_progress.connect(self._on_file_progress)
        self.worker.file_status.connect(self._on_file_status)
        self.worker.file_finished.connect(self._on_file_finished)
        self.worker.log_message.connect(lambda msg: self.log_text.append(msg))
        self.worker.all_finished.connect(self._on_all_finished)
        self.worker.fatal_error.connect(self._on_fatal_error)

        self.worker.start()

    def cancel_upload(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.log_text.append("🛑 正在取消上傳...")

    def _on_file_progress(self, bytes_done: int, total_bytes: int, speed_mb: float, eta_s: float):
        percent = int((bytes_done / total_bytes) * 100) if total_bytes > 0 else 0
        self.progress_bar.setValue(percent)

        eta_min = int(eta_s // 60)
        eta_sec = int(eta_s % 60)
        done_mb = bytes_done / (1024 * 1024)
        total_mb = total_bytes / (1024 * 1024)

        self.lbl_stats.setText(
            f"上傳中: {done_mb:.1f} MB / {total_mb:.1f} MB ({percent}%) | 速度: {speed_mb:.2f} MB/s | 剩餘時間: {eta_min}分{eta_sec}秒"
        )

    def _on_file_status(self, row_idx: int, status: str):
        item = self.table.item(row_idx, 5)
        if item:
            item.setText(status)
            if status == "Uploading...":
                item.setForeground(QColor("#00d2ff"))
            elif status == "Done":
                item.setForeground(QColor("#4ecca3"))
            elif status == "Failed":
                item.setForeground(QColor("#e94560"))

    def _on_file_finished(self, row_idx: int, result: dict):
        chk = self.table.item(row_idx, 0)
        if chk:
            chk.setCheckState(Qt.CheckState.Unchecked)

        link_item = self.table.item(row_idx, 6)
        if link_item and result.get("url"):
            link_item.setText("點擊觀看")
            link_item.setForeground(QColor("#00d2ff"))

        # Update scanned item
        self.scanned_items[row_idx]["uploaded"] = True
        self.scanned_items[row_idx]["youtube_url"] = result.get("url", "")

    def _on_all_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100)
        self.lbl_stats.setText("🎉 批次上傳與播放清單歸入作業全部完成！")
        QMessageBox.information(self, "完成", "所有選取影片已成功上傳至 YouTube 並加入播放清單！")

    def _on_fatal_error(self, err: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        QMessageBox.critical(self, "上傳中斷", f"上傳發生嚴重錯誤：\n{err}")


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = YouTubeUploaderTab()
    window.resize(1100, 750)
    window.setWindowTitle("YouTube 4K Auto-Uploader")
    window.show()
    sys.exit(app.exec())
