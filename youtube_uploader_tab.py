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
    QDateTimeEdit, QAbstractItemView, QTabWidget
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
from youtube_batch_scheduler import YouTubeBatchSchedulerWidget
from social_uploader_engine import (
    SocialUploaderEngine,
    SocialMatrixManager,
    PLAYWRIGHT_AVAILABLE
)


class VideoUploadWorker(QThread):
    """Background worker for batch uploading videos to YouTube, Instagram Reels, and TikTok."""

    file_progress = pyqtSignal(int, int, float, float)  # bytes_done, total_bytes, speed_mb, eta_s
    file_status = pyqtSignal(int, str)                  # row_idx, status_text
    file_finished = pyqtSignal(int, dict)               # row_idx, result_info
    log_message = pyqtSignal(str)                       # log text
    all_finished = pyqtSignal()
    fatal_error = pyqtSignal(str)

    def __init__(
        self,
        engine: YouTubeUploaderEngine,
        social_engine: SocialUploaderEngine,
        matrix_mgr: SocialMatrixManager,
        items_to_upload: List[Dict[str, Any]],
        upload_youtube: bool = True,
        upload_instagram: bool = False,
        upload_tiktok: bool = False,
        playlist_id: Optional[str] = None,
        create_playlist_title: Optional[str] = None,
        create_playlist_privacy: str = "public",
        privacy_status: str = "unlisted",
        is_premiere: bool = False,
        start_premiere_time: Optional[datetime] = None,
        stagger_interval_seconds: int = 0,
        auto_thumbnail: bool = True,
        auto_comment: bool = True,
        enable_nav_chain: bool = True,
        social_headless: bool = False,
        social_cooldown_seconds: int = 180
    ):
        super().__init__()
        self.engine = engine
        self.social_engine = social_engine
        self.matrix_mgr = matrix_mgr
        self.items = items_to_upload
        self.upload_youtube = upload_youtube
        self.upload_instagram = upload_instagram
        self.upload_tiktok = upload_tiktok
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
        self.social_headless = social_headless
        self.social_cooldown_seconds = social_cooldown_seconds
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.engine.request_cancel()
        self.social_engine.request_cancel()

    def run(self):
        try:
            target_playlist_id = self.playlist_id

            # 1. Handle YouTube connection & Playlist creation if YouTube is enabled
            if self.upload_youtube:
                self.log_message.emit("🚀 Initializing YouTube API connection...")
                self.engine.connect()

                if self.create_playlist_title:
                    self.log_message.emit(f"📋 Creating new playlist: '{self.create_playlist_title}' ({self.create_playlist_privacy})...")
                    target_playlist_id = self.engine.create_playlist(
                        title=self.create_playlist_title,
                        description=f"Curated 4K Audio-Reactive MV Collection: {self.create_playlist_title}",
                        privacy=self.create_playlist_privacy
                    )
                    self.log_message.emit(f"✅ Playlist created successfully! ID: {target_playlist_id}")

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

                current_matrix = self.matrix_mgr.get_status(filename)
                yt_done = current_matrix.get("youtube", {}).get("status") == "done"
                ig_done = current_matrix.get("instagram", {}).get("status") == "done"
                tt_done = current_matrix.get("tiktok", {}).get("status") == "done"
                yt_attempted = yt_done  # already done counts as attempted
                ig_attempted = ig_done
                tt_attempted = tt_done

                self.file_status.emit(row_idx, "Processing...")
                self.log_message.emit(f"\n[{idx+1}/{total_items}] === 處理影片: {filename} ({item['size_str']}) ===")

                # --- A. YouTube Upload ---
                if self.upload_youtube:
                    if yt_done:
                        yt_attempted = True
                        yt_url = current_matrix.get("youtube", {}).get("url") or item.get("youtube_url", "")
                        self.log_message.emit(f"  ⏩ [YouTube] 影片 '{filename}' 先前已發布完成 ({yt_url})，自動略過接續下一部。")
                        if yt_url:
                            self.file_finished.emit(row_idx, {"id": current_matrix.get("youtube", {}).get("id", ""), "url": yt_url})
                    else:
                        yt_attempted = True
                        if self._is_cancelled: break
                        self.file_status.emit(row_idx, "YT: 上傳中...")
                        self.log_message.emit(f"  ▶ [YouTube] 開始上傳 4K 影片: {filename}")

                        # Anchored premiere time calculation (immune to list slicing during resume)
                        item_publish_at = item.get("scheduled_publish_at")
                        if item_publish_at is None and self.is_premiere and self.start_premiere_time:
                            row_offset = item.get("row_idx", idx)
                            offset = timedelta(seconds=self.stagger_interval_seconds * row_offset)
                            item_publish_at = self.start_premiere_time + offset

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

                        def on_progress(bytes_done, total_bytes, speed_mb, eta_s):
                            self.file_progress.emit(bytes_done, total_bytes, speed_mb, eta_s)

                        def on_status(msg):
                            self.log_message.emit(f"    ℹ️ {msg}")

                        # Upload with item-level retry for transient unexpected failures
                        max_item_attempts = 2
                        for item_attempt in range(max_item_attempts):
                            if self._is_cancelled: break
                            try:
                                yt_res = self.engine.upload_video(
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
                                self.matrix_mgr.update_platform_status(
                                    filename, "youtube", "done",
                                    {"id": yt_res.get("id"), "url": yt_res.get("url")}
                                )
                                yt_done = True
                                self.file_finished.emit(row_idx, yt_res)
                                self.log_message.emit(f"    ✅ [YouTube] 發布成功: {yt_res.get('url')}")
                                break
                            except Exception as e:
                                err_msg = str(e)
                                if "quota" in err_msg.lower():
                                    self.log_message.emit(f"    ⚠️ [YouTube] 當前專案配額耗盡: {err_msg}")
                                    rotated = False
                                    if hasattr(self.engine, 'cred_manager') and self.engine.cred_manager:
                                        if self.engine.cred_manager.rotate_to_next():
                                            new_sec = self.engine.cred_manager.get_active_secret_file()
                                            sec_name = new_sec.name if new_sec else "未知憑證"
                                            self.log_message.emit(f"    🔄 [YouTube] 自動輪換至金鑰池憑證: {sec_name}，重新連接服務...")
                                            try:
                                                self.engine.connect()
                                                time.sleep(2)
                                                rotated = True
                                                continue  # 重試當前影片上傳
                                            except Exception as conn_err:
                                                self.log_message.emit(f"    ❌ [YouTube] 新憑證連接失敗: {conn_err}")
                                    if not rotated:
                                        self.log_message.emit(f"    ❌ [YouTube] 金鑰池所有可用憑證配額皆已耗盡: {err_msg}")
                                        self.matrix_mgr.update_platform_status(filename, "youtube", "failed", {"error": err_msg})
                                        self.fatal_error.emit(f"Daily YouTube quota reached on all available credentials: {err_msg}")
                                        break
                                
                                if item_attempt < max_item_attempts - 1 and not self._is_cancelled:
                                    self.log_message.emit(f"    ⚠️ [YouTube] 遭遇錯誤，5 秒後自動重試: {err_msg}")
                                    time.sleep(5)
                                    continue
                                else:
                                    self.log_message.emit(f"    ❌ [YouTube] 失敗: {err_msg}")
                                    self.matrix_mgr.update_platform_status(filename, "youtube", "failed", {"error": err_msg})

                # --- B. Instagram Reels Upload ---
                if self.upload_instagram:
                    if ig_done:
                        ig_attempted = True
                        self.log_message.emit(f"  ⏩ [Instagram Reels] 影片 '{filename}' 先前已發布完成，自動略過。")
                    else:
                        ig_attempted = True
                        if self._is_cancelled: break
                        self.file_status.emit(row_idx, "IG: 發布中...")
                        self.log_message.emit(f"  ▶ [Instagram Reels] 開始發布...")
                        ig_caption = item.get("instagram_caption") or f"{title}\n\n#ElectronicMusic #Visualizer #4KMV #Reels"

                        def on_ig_status(msg):
                            self.log_message.emit(f"    ℹ️ {msg}")

                        ig_res = self.social_engine.upload_instagram_reel(
                            video_path=video_path,
                            caption=ig_caption,
                            headless=self.social_headless,
                            status_cb=on_ig_status
                        )

                        if ig_res.get("status") == "done":
                            self.matrix_mgr.update_platform_status(filename, "instagram", "done")
                            ig_done = True
                            self.log_message.emit("    ✅ [Instagram Reels] 發布成功！")
                        else:
                            self.matrix_mgr.update_platform_status(filename, "instagram", "failed", {"error": ig_res.get("error")})
                            self.log_message.emit(f"    ❌ [Instagram Reels] 失敗: {ig_res.get('error')}")

                        # Anti-Bot Cooldown if another item or platform is queued
                        if not self._is_cancelled and (self.upload_tiktok or idx < total_items - 1):
                            self.social_engine.human_cooldown(
                                base_sec=self.social_cooldown_seconds,
                                status_cb=lambda m: self.log_message.emit(f"    {m}")
                            )

                # --- C. TikTok Upload ---
                if self.upload_tiktok:
                    if tt_done:
                        tt_attempted = True
                        self.log_message.emit(f"  ⏩ [TikTok] 影片 '{filename}' 先前已發布完成，自動略過。")
                    else:
                        tt_attempted = True
                        if self._is_cancelled: break
                        self.file_status.emit(row_idx, "TikTok: 發布中...")
                        self.log_message.emit(f"  ▶ [TikTok] 開始發布...")
                    tt_caption = item.get("tiktok_caption") or f"{title}\n\n#techno #music #visualizer #fyp"

                    def on_tt_status(msg):
                        self.log_message.emit(f"    ℹ️ {msg}")

                    tt_res = self.social_engine.upload_tiktok_video(
                        video_path=video_path,
                        caption=tt_caption,
                        as_draft=False,
                        headless=self.social_headless,
                        status_cb=on_tt_status
                    )

                    if tt_res.get("status") == "done":
                        self.matrix_mgr.update_platform_status(filename, "tiktok", "done")
                        tt_done = True
                        self.log_message.emit("    ✅ [TikTok] 發布成功！")
                    else:
                        self.matrix_mgr.update_platform_status(filename, "tiktok", "failed", {"error": tt_res.get("error")})
                        self.log_message.emit(f"    ❌ [TikTok] 失敗: {tt_res.get('error')}")

                    if not self._is_cancelled and idx < total_items - 1:
                        self.social_engine.human_cooldown(
                            base_sec=self.social_cooldown_seconds,
                            status_cb=lambda m: self.log_message.emit(f"    {m}")
                        )

                # Update composite status text (✅=done, ❌=failed, ⏳=skipped)
                status_parts = []
                if self.upload_youtube:
                    yt_icon = "✅" if yt_done else ("❌" if yt_attempted else "⏳")
                    status_parts.append(f"YT: {yt_icon}")
                if self.upload_instagram:
                    ig_icon = "✅" if ig_done else ("❌" if ig_attempted else "⏳")
                    status_parts.append(f"IG: {ig_icon}")
                if self.upload_tiktok:
                    tt_icon = "✅" if tt_done else ("❌" if tt_attempted else "⏳")
                    status_parts.append(f"TT: {tt_icon}")

                comp_status = " | ".join(status_parts) if status_parts else "Done"
                self.file_status.emit(row_idx, comp_status)

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
        self.social_engine = SocialUploaderEngine()
        self.matrix_mgr = SocialMatrixManager(os.getcwd())
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
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # Top Header Banner: 現代暗黑中樞控制列 (Command Hub Bar)
        # ----------------------------------------------------------------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #121624, stop:1 #171d30);
                border-radius: 8px;
                padding: 6px 12px;
                border: 1px solid #1f293d;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(10)

        title_lbl = QLabel("📤 全平台 4K 發布矩陣中心")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        header_layout.addWidget(title_lbl)

        pool_size = len(self.engine.cred_manager.client_secrets_files)
        cap_songs = pool_size * 6
        self.lbl_pool = QLabel(f"⚡ 憑證池: {pool_size} 專案 ({cap_songs} 首/天)")
        self.lbl_pool.setToolTip(f"已啟用 {pool_size} 個 Google Cloud 專案配額輪換，每日支援最多 {cap_songs} 首 MV 發布！")
        self.lbl_pool.setStyleSheet("""
            font-size: 12px; font-weight: 600; color: #fbbf24;
            background: rgba(251, 191, 36, 0.12);
            padding: 3px 10px; border-radius: 6px;
            border: 1px solid rgba(251, 191, 36, 0.3);
        """)
        header_layout.addWidget(self.lbl_pool)

        self.lbl_channel = QLabel("📺 頻道: (點擊檢查)")
        self.lbl_channel.setStyleSheet("""
            font-size: 12px; font-weight: 600; color: #34d399;
            background: rgba(52, 211, 153, 0.12);
            padding: 3px 10px; border-radius: 6px;
            border: 1px solid rgba(52, 211, 153, 0.3);
        """)
        header_layout.addWidget(self.lbl_channel)

        header_layout.addStretch()

        btn_style_subtle = """
            QPushButton {
                background: #1e2638;
                color: #e2e8f0;
                font-size: 12px;
                font-weight: 500;
                border-radius: 6px;
                padding: 5px 12px;
                border: 1px solid #2e3b55;
            }
            QPushButton:hover {
                background: #2b364f;
                color: #ffffff;
                border: 1px solid #3b82f6;
            }
        """

        self.btn_check_channel = QPushButton("🔍 檢查頻道")
        self.btn_check_channel.setStyleSheet(btn_style_subtle)
        self.btn_check_channel.clicked.connect(self._check_current_channel)
        header_layout.addWidget(self.btn_check_channel)

        self.btn_switch_channel = QPushButton("🔄 切換頻道")
        self.btn_switch_channel.setStyleSheet(btn_style_subtle)
        self.btn_switch_channel.clicked.connect(self._switch_channel)
        header_layout.addWidget(self.btn_switch_channel)

        self.btn_guide = QPushButton("📖 憑證指南")
        self.btn_guide.setStyleSheet(btn_style_subtle)
        self.btn_guide.clicked.connect(self._open_setup_guide)
        header_layout.addWidget(self.btn_guide)

        self.btn_goto_scheduler = QPushButton("📅 批次修改已上傳")
        self.btn_goto_scheduler.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                font-size: 12px;
                font-weight: 600;
                border-radius: 6px;
                padding: 5px 12px;
                border: 1px solid rgba(59, 130, 246, 0.4);
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.28);
                color: #ffffff;
            }
        """)
        self.btn_goto_scheduler.clicked.connect(lambda: self.inner_tabs.setCurrentIndex(1))
        header_layout.addWidget(self.btn_goto_scheduler)

        self.btn_goto_optimizer = QPushButton("🎯 影片審計與封面")
        self.btn_goto_optimizer.setStyleSheet("""
            QPushButton {
                background: rgba(236, 72, 153, 0.15);
                color: #f472b6;
                font-size: 12px;
                font-weight: 600;
                border-radius: 6px;
                padding: 5px 12px;
                border: 1px solid rgba(236, 72, 153, 0.4);
            }
            QPushButton:hover {
                background: rgba(236, 72, 153, 0.28);
                color: #ffffff;
            }
        """)
        self.btn_goto_optimizer.clicked.connect(self._goto_optimizer_tab)
        header_layout.addWidget(self.btn_goto_optimizer)

        main_layout.addWidget(header_frame)

        # ----------------------------------------------------------------------
        # Sub-Tabs: Upload vs Batch Schedule Manager
        # ----------------------------------------------------------------------
        self.inner_tabs = QTabWidget()
        self.inner_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #1e2638;
                border-radius: 8px;
                background: #0b0e14;
            }
            QTabBar::tab {
                background: #11151f;
                color: #94a3b8;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 18px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #1e2638;
                border-bottom: none;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0b0e14;
                color: #38bdf8;
                border: 1px solid #2e3b55;
                border-bottom: 2px solid #38bdf8;
            }
            QTabBar::tab:hover:!selected {
                background: #1a2030;
                color: #e2e8f0;
            }
        """)

        # Tab 1: Video Upload
        upload_tab = QWidget()
        upload_layout = QVBoxLayout(upload_tab)
        upload_layout.setContentsMargins(10, 10, 10, 10)
        upload_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # 1. 待發布影片目錄 (Directory Selection)
        # ----------------------------------------------------------------------
        dir_frame = QFrame()
        dir_frame.setStyleSheet("""
            QFrame {
                background: #111520;
                border: 1px solid #1e2538;
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        dir_layout = QHBoxLayout(dir_frame)
        dir_layout.setContentsMargins(6, 4, 6, 4)
        dir_layout.setSpacing(8)

        lbl_dir_icon = QLabel("📁 來源目錄:")
        lbl_dir_icon.setStyleSheet("font-weight: 600; color: #cbd5e1; font-size: 12px;")
        dir_layout.addWidget(lbl_dir_icon)

        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("請選擇存放 4K 影片與 _social.txt 的目錄...")
        self.dir_input.setStyleSheet("""
            QLineEdit {
                background: #0a0d13;
                border: 1px solid #242c3f;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 12px;
                padding: 5px 10px;
                min-height: 22px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        dir_layout.addWidget(self.dir_input, 1)

        btn_browse = QPushButton("📂 瀏覽目錄...")
        btn_browse.setStyleSheet("""
            QPushButton {
                background: #1e2638;
                color: #e2e8f0;
                font-size: 12px;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #2e3b55;
            }
            QPushButton:hover {
                background: #2b364f;
                color: #ffffff;
            }
        """)
        btn_browse.clicked.connect(self._browse_directory)
        dir_layout.addWidget(btn_browse)

        self.btn_rescan = QPushButton("🔄 重新掃描")
        self.btn_rescan.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 16px;
                border: 1px solid #0369a1;
            }
            QPushButton:hover {
                background: #0369a1;
            }
        """)
        self.btn_rescan.clicked.connect(self.scan_directory)
        dir_layout.addWidget(self.btn_rescan)

        upload_layout.addWidget(dir_frame)

        # ----------------------------------------------------------------------
        # 2. Bento-Grid 卡片網格：目標發布平台矩陣 (Target Distribution Matrix)
        # 4 欄獨立卡片設計，徹底根除文字截斷與排擠！
        # ----------------------------------------------------------------------
        plat_grid = QGridLayout()
        plat_grid.setSpacing(8)
        plat_grid.setContentsMargins(0, 0, 0, 0)

        tile_base_css = """
            QFrame {
                background: #111520;
                border: 1px solid #1e2638;
                border-radius: 8px;
                padding: 8px;
            }
        """

        # Tile 1: YouTube
        tile_yt = QFrame()
        tile_yt.setStyleSheet(tile_base_css + """
            QFrame:hover { border: 1px solid rgba(239, 68, 68, 0.4); }
        """)
        ly_yt = QVBoxLayout(tile_yt)
        ly_yt.setContentsMargins(6, 6, 6, 6)
        ly_yt.setSpacing(3)
        self.chk_plat_yt = QCheckBox("🔴 YouTube (4K MV)")
        self.chk_plat_yt.setChecked(True)
        self.chk_plat_yt.setStyleSheet("color: #f87171; font-weight: bold; font-size: 13px;")
        ly_yt.addWidget(self.chk_plat_yt)
        lbl_yt_sub = QLabel("4K 原畫無損 · 首播與播單管理")
        lbl_yt_sub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ly_yt.addWidget(lbl_yt_sub)
        plat_grid.addWidget(tile_yt, 0, 0)

        # Tile 2: Instagram Reels
        tile_ig = QFrame()
        tile_ig.setStyleSheet(tile_base_css + """
            QFrame:hover { border: 1px solid rgba(236, 72, 153, 0.4); }
        """)
        ly_ig = QVBoxLayout(tile_ig)
        ly_ig.setContentsMargins(6, 6, 6, 6)
        ly_ig.setSpacing(3)
        self.chk_plat_ig = QCheckBox("📸 Instagram Reels")
        self.chk_plat_ig.setChecked(False)
        self.chk_plat_ig.setStyleSheet("color: #f472b6; font-weight: bold; font-size: 13px;")
        ly_ig.addWidget(self.chk_plat_ig)
        lbl_ig_sub = QLabel("自動提取文案與標籤 (自動/手動)")
        lbl_ig_sub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ly_ig.addWidget(lbl_ig_sub)
        plat_grid.addWidget(tile_ig, 0, 1)

        # Tile 3: TikTok
        tile_tt = QFrame()
        tile_tt.setStyleSheet(tile_base_css + """
            QFrame:hover { border: 1px solid rgba(6, 182, 212, 0.4); }
        """)
        ly_tt = QVBoxLayout(tile_tt)
        ly_tt.setContentsMargins(6, 6, 6, 6)
        ly_tt.setSpacing(3)
        self.chk_plat_tt = QCheckBox("🎵 TikTok 創作者後台")
        self.chk_plat_tt.setChecked(False)
        self.chk_plat_tt.setStyleSheet("color: #22d3ee; font-weight: bold; font-size: 13px;")
        ly_tt.addWidget(self.chk_plat_tt)
        lbl_tt_sub = QLabel("瀏覽器無頭背景自動發布")
        lbl_tt_sub.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ly_tt.addWidget(lbl_tt_sub)
        plat_grid.addWidget(tile_tt, 0, 2)

        # Tile 4: Anti-Bot & Safety
        tile_safe = QFrame()
        tile_safe.setStyleSheet(tile_base_css + """
            QFrame:hover { border: 1px solid rgba(251, 191, 36, 0.4); }
        """)
        ly_safe = QVBoxLayout(tile_safe)
        ly_safe.setContentsMargins(6, 6, 6, 6)
        ly_safe.setSpacing(3)
        h_safe_row = QHBoxLayout()
        self.chk_social_visible = QCheckBox("🖥️ 可視化除錯登入")
        self.chk_social_visible.setChecked(False)
        self.chk_social_visible.setToolTip("勾選後將顯示 Chrome 瀏覽器視窗，便於首次手動登入 IG/TikTok 帳號。之後可取消勾選在背景靜默運行。")
        self.chk_social_visible.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 600;")
        h_safe_row.addWidget(self.chk_social_visible)

        lbl_cd = QLabel("⏳ 間隔:")
        lbl_cd.setStyleSheet("color: #94a3b8; font-size: 11px;")
        h_safe_row.addWidget(lbl_cd)

        self.combo_cooldown = QComboBox()
        self.combo_cooldown.addItem("180 秒 (標準安全)", 180)
        self.combo_cooldown.addItem("120 秒 (中速)", 120)
        self.combo_cooldown.addItem("300 秒 (5分鐘高防護)", 300)
        self.combo_cooldown.addItem("30 秒 (極速測試)", 30)
        self.combo_cooldown.setStyleSheet("""
            QComboBox {
                background: #0a0d13;
                border: 1px solid #242c3f;
                border-radius: 4px;
                color: #e2e8f0;
                font-size: 11px;
                padding: 2px 6px;
                min-height: 20px;
            }
        """)
        h_safe_row.addWidget(self.combo_cooldown)
        ly_safe.addLayout(h_safe_row)

        lbl_safe_sub = QLabel("智慧防風控 · 擬人隨機微延遲保護")
        lbl_safe_sub.setStyleSheet("color: #64748b; font-size: 10px;")
        ly_safe.addWidget(lbl_safe_sub)
        plat_grid.addWidget(tile_safe, 0, 3)

        upload_layout.addLayout(plat_grid)

        # ----------------------------------------------------------------------
        # 3. 雙欄 Bento 平衡卡片：播放清單管理 與 發布/首播時間
        # 徹底修復文字重疊、垂直疊字與底色遮蔽問題！
        # ----------------------------------------------------------------------
        grid_config = QHBoxLayout()
        grid_config.setSpacing(10)

        common_box_css = """
            QGroupBox {
                background: #111520;
                border: 1px solid #1e2538;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
                color: #cbd5e1;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #38bdf8;
            }
            QComboBox, QLineEdit, QDateTimeEdit {
                background: #0a0d13;
                border: 1px solid #242c3f;
                border-radius: 6px;
                color: #f8fafc;
                font-size: 12px;
                padding: 4px 8px;
                min-height: 26px;
            }
            QComboBox:focus, QLineEdit:focus, QDateTimeEdit:focus {
                border: 1px solid #38bdf8;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QRadioButton, QCheckBox {
                color: #e2e8f0;
                font-size: 12px;
                spacing: 6px;
            }
        """

        # Group A: Playlist Settings
        playlist_group = QGroupBox("📋 播放清單管理 (Playlist Settings)")
        playlist_group.setStyleSheet(common_box_css)
        pl_layout = QVBoxLayout(playlist_group)
        pl_layout.setContentsMargins(8, 12, 8, 8)
        pl_layout.setSpacing(8)

        self.chk_playlist = QCheckBox("啟用自動加入播放清單")
        self.chk_playlist.setChecked(True)
        self.chk_playlist.setStyleSheet("font-weight: 600; color: #34d399; font-size: 12px;")
        self.chk_playlist.toggled.connect(self._toggle_playlist_ui)
        pl_layout.addWidget(self.chk_playlist)

        self.pl_mode_group = QButtonGroup(self)

        # Option A: Existing Playlist
        h_exist = QHBoxLayout()
        h_exist.setSpacing(6)
        self.radio_pl_exist = QRadioButton("加入既有清單:")
        self.pl_mode_group.addButton(self.radio_pl_exist)
        h_exist.addWidget(self.radio_pl_exist)

        self.combo_playlists = QComboBox()
        self.combo_playlists.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h_exist.addWidget(self.combo_playlists, 1)

        self.btn_refresh_pl = QPushButton("🔄 載入")
        self.btn_refresh_pl.setStyleSheet("""
            QPushButton {
                background: #1e2638;
                color: #cbd5e1;
                font-size: 11px;
                border-radius: 4px;
                padding: 4px 10px;
                border: 1px solid #2e3b55;
            }
            QPushButton:hover { background: #2b364f; color: #ffffff; }
        """)
        self.btn_refresh_pl.clicked.connect(self._fetch_user_playlists)
        h_exist.addWidget(self.btn_refresh_pl)
        pl_layout.addLayout(h_exist)

        # Option B: Create New Playlist
        h_new = QHBoxLayout()
        h_new.setSpacing(6)
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
        premiere_group = QGroupBox("⏰ 發布與首播排程 (Premiere & Release Schedule)")
        premiere_group.setStyleSheet(common_box_css)
        pr_layout = QVBoxLayout(premiere_group)
        pr_layout.setContentsMargins(8, 12, 8, 8)
        pr_layout.setSpacing(8)

        self.release_mode_group = QButtonGroup(self)

        # Mode 1: Immediate
        h_imm = QHBoxLayout()
        h_imm.setSpacing(6)
        self.radio_imm = QRadioButton("立即發布 / 手動公開:")
        self.release_mode_group.addButton(self.radio_imm)
        h_imm.addWidget(self.radio_imm)

        self.combo_imm_privacy = QComboBox()
        self.combo_imm_privacy.addItems(["不公開 (unlisted) - 推薦先驗證4K畫質", "公開 (public)", "私人 (private)"])
        h_imm.addWidget(self.combo_imm_privacy, 1)
        pr_layout.addLayout(h_imm)

        # Mode 2: Premiere Scheduled
        h_prem = QHBoxLayout()
        h_prem.setSpacing(6)
        self.radio_prem = QRadioButton("排程首播 (Premiere):")
        self.radio_prem.setChecked(True)
        self.release_mode_group.addButton(self.radio_prem)
        h_prem.addWidget(self.radio_prem)

        self.dt_premiere = QDateTimeEdit()
        self.dt_premiere.setCalendarPopup(True)
        self.dt_premiere.setDisplayFormat("yyyy-MM-dd HH:mm")
        default_dt = datetime.now() + timedelta(days=1)
        default_dt = default_dt.replace(hour=20, minute=0, second=0, microsecond=0)
        self.dt_premiere.setDateTime(QDateTime.fromString(default_dt.strftime("%Y-%m-%d %H:%M"), "yyyy-MM-dd HH:mm"))
        self.dt_premiere.dateTimeChanged.connect(self._recalculate_schedule_table)
        h_prem.addWidget(self.dt_premiere, 1)
        pr_layout.addLayout(h_prem)

        # Staggered Interval
        h_stagger = QHBoxLayout()
        h_stagger.setSpacing(6)
        self.chk_stagger = QCheckBox("啟用階梯連載間隔 (每首依序首播)")
        self.chk_stagger.setChecked(True)
        self.chk_stagger.setStyleSheet("color: #38bdf8; font-weight: 500;")
        self.chk_stagger.toggled.connect(self._recalculate_schedule_table)
        h_stagger.addWidget(self.chk_stagger)

        self.combo_stagger = QComboBox()
        self.combo_stagger.addItem("每 12 小時 (長片推薦: 一天兩片)", 43200)
        self.combo_stagger.addItem("每 4 小時 (Shorts首播: 一天四片)", 14400)
        self.combo_stagger.addItem("每 1 天 (24 小時)", 86400)
        self.combo_stagger.addItem("每 6 小時", 21600)
        self.combo_stagger.addItem("每 8 小時", 28800)
        self.combo_stagger.addItem("每 2 小時", 7200)
        self.combo_stagger.addItem("每 2 天", 172800)
        self.combo_stagger.addItem("每 3 天", 259200)
        self.combo_stagger.currentIndexChanged.connect(self._recalculate_schedule_table)
        h_stagger.addWidget(self.combo_stagger, 1)
        pr_layout.addLayout(h_stagger)

        grid_config.addWidget(premiere_group, 1)
        upload_layout.addLayout(grid_config)

        # ----------------------------------------------------------------------
        # 4. 智能發布流水線卡片 (Automation Pipeline Strip)
        # ----------------------------------------------------------------------
        enhance_frame = QFrame()
        enhance_frame.setStyleSheet("""
            QFrame {
                background: #111520;
                border: 1px solid #1e2538;
                border-radius: 8px;
                padding: 4px 10px;
            }
        """)
        enhance_box = QHBoxLayout(enhance_frame)
        enhance_box.setContentsMargins(6, 4, 6, 4)
        enhance_box.setSpacing(16)

        lbl_pipe_tag = QLabel("🚀 智能流水線:")
        lbl_pipe_tag.setStyleSheet("color: #cbd5e1; font-weight: bold; font-size: 12px;")
        enhance_box.addWidget(lbl_pipe_tag)

        self.chk_thumbnail = QCheckBox("🖼️ 4K 黃金影格封面 (Beat-Synced)")
        self.chk_thumbnail.setChecked(True)
        self.chk_thumbnail.setStyleSheet("color: #38bdf8; font-weight: 500; font-size: 12px;")
        enhance_box.addWidget(self.chk_thumbnail)

        self.chk_comment = QCheckBox("💬 自動發表置頂導流留言 (Pinned)")
        self.chk_comment.setChecked(True)
        self.chk_comment.setStyleSheet("color: #34d399; font-weight: 500; font-size: 12px;")
        enhance_box.addWidget(self.chk_comment)

        self.chk_nav = QCheckBox("🔗 說明欄前後曲目連鎖導覽")
        self.chk_nav.setChecked(True)
        self.chk_nav.setStyleSheet("color: #fbbf24; font-weight: 500; font-size: 12px;")
        enhance_box.addWidget(self.chk_nav)

        enhance_box.addStretch()

        self.btn_check_4k = QPushButton("🛡️ 檢查 4K 轉碼哨兵")
        self.btn_check_4k.setStyleSheet("""
            QPushButton {
                background: #1e2638;
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 600;
                border-radius: 6px;
                padding: 5px 12px;
                border: 1px solid #2e3b55;
            }
            QPushButton:hover {
                background: #2b364f;
                color: #ffffff;
                border: 1px solid #38bdf8;
            }
        """)
        self.btn_check_4k.clicked.connect(self._check_4k_transcode_status)
        enhance_box.addWidget(self.btn_check_4k)

        upload_layout.addWidget(enhance_frame)

        # ----------------------------------------------------------------------
        # 5. 發布佇列表格 (Video Queue Table)
        # ----------------------------------------------------------------------
        table_frame = QFrame()
        table_frame.setStyleSheet("""
            QFrame {
                background: #111520;
                border: 1px solid #1e2538;
                border-radius: 8px;
            }
        """)
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(6, 6, 6, 6)
        table_layout.setSpacing(6)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "選取", "檔案名稱", "大小", "YouTube 標題", "預計發布 / 首播時間", "平台狀態矩陣", "連結"
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
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0a0d13;
                alternate-background-color: #10141f;
                gridline-color: #1a2233;
                color: #f1f5f9;
                font-size: 12px;
                border: none;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background: #151a27;
                color: #94a3b8;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #242c3f;
            }
        """)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)

        upload_layout.addWidget(table_frame, 3)

        # ----------------------------------------------------------------------
        # 6. 進度條與狀態統計
        # ----------------------------------------------------------------------
        prog_layout = QVBoxLayout()
        prog_layout.setSpacing(4)
        self.lbl_stats = QLabel("準備就緒。共 0 部影片待發布。")
        self.lbl_stats.setStyleSheet("font-weight: 600; color: #94a3b8; font-size: 12px;")
        prog_layout.addWidget(self.lbl_stats)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #242c3f;
                border-radius: 6px;
                text-align: center;
                height: 18px;
                background: #0a0d13;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 5px;
            }
        """)
        prog_layout.addWidget(self.progress_bar)
        upload_layout.addLayout(prog_layout)

        # ----------------------------------------------------------------------
        # 7. 控制按鈕與日誌抽屜列 (Action & Console Toolbar)
        # ----------------------------------------------------------------------
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        btn_action_css = """
            QPushButton {
                background: #1e2638;
                color: #cbd5e1;
                font-size: 12px;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #2e3b55;
            }
            QPushButton:hover {
                background: #2b364f;
                color: #ffffff;
            }
        """

        self.btn_select_all = QPushButton("☑️ 全選")
        self.btn_select_all.setStyleSheet(btn_action_css)
        self.btn_select_all.clicked.connect(self._select_all)
        btn_box.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("◻️ 取消全選")
        self.btn_deselect_all.setStyleSheet(btn_action_css)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        btn_box.addWidget(self.btn_deselect_all)

        self.btn_select_uncompleted = QPushButton("⚡ 僅選取未完成/失敗 (續傳)")
        self.btn_select_uncompleted.setToolTip("自動篩選：取消勾選已全數發布的影片，僅勾選上次失敗 (❌) 或待傳 (⏳) 的影片並定位")
        self.btn_select_uncompleted.setStyleSheet("""
            QPushButton {
                background: rgba(56, 189, 248, 0.12);
                color: #38bdf8;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 14px;
                border-radius: 6px;
                border: 1px solid rgba(56, 189, 248, 0.35);
            }
            QPushButton:hover {
                background: rgba(56, 189, 248, 0.22);
                color: #ffffff;
            }
        """)
        self.btn_select_uncompleted.clicked.connect(self._select_uncompleted)
        btn_box.addWidget(self.btn_select_uncompleted)

        btn_box.addStretch()

        # 折疊式日誌抽屜切換按鈕
        self.btn_toggle_log = QPushButton("📋 收起診斷日誌 ▴")
        self.btn_toggle_log.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                font-size: 12px;
                border: none;
                padding: 6px 10px;
            }
            QPushButton:hover {
                color: #38bdf8;
            }
        """)
        self.btn_toggle_log.clicked.connect(self._toggle_log_drawer)
        btn_box.addWidget(self.btn_toggle_log)

        self.btn_cancel = QPushButton("🛑 取消發布")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.15);
                color: #f87171;
                font-weight: 600;
                font-size: 12px;
                padding: 7px 16px;
                border-radius: 6px;
                border: 1px solid rgba(239, 68, 68, 0.35);
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.28);
                color: #ffffff;
            }
            QPushButton:disabled {
                background: #1a1e28;
                color: #475569;
                border: 1px solid #242c3f;
            }
        """)
        self.btn_cancel.clicked.connect(self.cancel_upload)
        btn_box.addWidget(self.btn_cancel)

        self.btn_start = QPushButton("🚀 開始批次發布與加入清單")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 24px;
                border-radius: 6px;
                border: 1px solid #047857;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #34d399);
            }
            QPushButton:disabled {
                background: #27272a;
                color: #71717a;
                border: 1px solid #3f3f46;
            }
        """)
        self.btn_start.clicked.connect(self.start_batch_upload)
        btn_box.addWidget(self.btn_start)

        upload_layout.addLayout(btn_box)

        # ----------------------------------------------------------------------
        # 8. 折疊式終端日誌抽屜 (Collapsible Log Drawer)
        # ----------------------------------------------------------------------
        self.log_container = QFrame()
        self.log_container.setStyleSheet("""
            QFrame {
                background: #080a0f;
                border: 1px solid #1e2538;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        log_inner_layout = QVBoxLayout(self.log_container)
        log_inner_layout.setContentsMargins(6, 4, 6, 4)
        log_inner_layout.setSpacing(4)

        log_header = QHBoxLayout()
        lbl_log_title = QLabel("📋 即時執行與診斷日誌 (自動循環保存於 logs/youtube_uploader.log)")
        lbl_log_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
        log_header.addWidget(lbl_log_title)
        log_header.addStretch()

        btn_quota = QPushButton("📊 今日配額統計")
        btn_quota.setToolTip("查看今日各憑證專案的 YouTube API 配額點數消耗與剩餘額度")
        btn_quota.setStyleSheet("""
            QPushButton {
                background: #151a26;
                color: #94a3b8;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                border: 1px solid #242c3f;
            }
            QPushButton:hover { color: #f8fafc; border: 1px solid #38bdf8; }
        """)
        btn_quota.clicked.connect(self._show_quota_analysis)
        log_header.addWidget(btn_quota)

        btn_open_log = QPushButton("📁 開啟完整日誌")
        btn_open_log.setToolTip("在外部編輯器中開啟 logs/youtube_uploader.log 查看詳細偵錯紀錄")
        btn_open_log.setStyleSheet("""
            QPushButton {
                background: #151a26;
                color: #94a3b8;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                border: 1px solid #242c3f;
            }
            QPushButton:hover { color: #f8fafc; border: 1px solid #38bdf8; }
        """)
        btn_open_log.clicked.connect(self._open_log_file)
        log_header.addWidget(btn_open_log)

        btn_clear = QPushButton("🧹 清除畫面")
        btn_clear.setToolTip("清除下方日誌顯示區域（不影響硬碟中的 log 檔案）")
        btn_clear.setStyleSheet("""
            QPushButton {
                background: #151a26;
                color: #94a3b8;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                border: 1px solid #242c3f;
            }
            QPushButton:hover { color: #f8fafc; border: 1px solid #38bdf8; }
        """)
        btn_clear.clicked.connect(self._clear_log_display)
        log_header.addWidget(btn_clear)

        log_inner_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(105)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background: #05070a;
                color: #34d399;
                font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
                font-size: 11px;
                border: 1px solid #1a2233;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        log_inner_layout.addWidget(self.log_text)

        upload_layout.addWidget(self.log_container)

        # Add tabs
        self.inner_tabs.addTab(upload_tab, "📤 4K 影片發布與多平台矩陣 (Upload)")

        self.scheduler_widget = YouTubeBatchSchedulerWidget(engine=self.engine, parent=self)
        self.inner_tabs.addTab(self.scheduler_widget, "📅 已上傳影片排程批次修改 (Batch Scheduler)")

        main_layout.addWidget(self.inner_tabs)

    def _toggle_log_drawer(self):
        """ 切換即時日誌抽屜的展開/收起狀態 """
        is_vis = not self.log_container.isVisible()
        self.log_container.setVisible(is_vis)
        self.btn_toggle_log.setText("📋 收起診斷日誌 ▴" if is_vis else "📋 展開診斷日誌 ▾")

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
        all_secrets = self.engine.cred_manager.client_secrets_files
        pool_count = len(all_secrets)
        total_pool_points = pool_count * 10000
        total_pool_capacity = pool_count * 6

        lines = [
            f"📊 【YouTube API 今日配額統計與輪換池總覽】",
            f"📅 統計日期: {today} | ⚡ 輪換池規模: {pool_count} 個專案",
            f"🚀 每日總額度: {total_pool_points:,} 點 | 總承載量: {total_pool_capacity} 首/天",
            "=" * 55
        ]

        total_avail_uploads = 0
        total_consumed = 0
        for idx, secret_path in enumerate(all_secrets, 1):
            proj_stem = secret_path.stem
            proj_data = data.get(proj_stem, {})
            pts = proj_data.get("total_points", 0)
            total_consumed += pts
            rem = max(0, 10000 - pts)
            avail_uploads = rem // 1600
            total_avail_uploads += avail_uploads

            status_icon = "🟢" if rem >= 1600 else ("🟡" if rem > 0 else "🔴")
            lines.append(f"\n{status_icon} 專案 {idx}: [{proj_stem}] ({secret_path.name})")
            lines.append(f"   已消耗: {pts:,} / 10,000 點 | 剩餘: {rem:,} 點 (可傳約 {avail_uploads} 首)")
            if proj_data.get("calls"):
                call_summary = ", ".join([f"{k}: {v}次" for k, v in proj_data["calls"].items()])
                lines.append(f"   API 呼叫: {call_summary}")

        remaining_total_points = sum(max(0, 10000 - data.get(sp.stem, {}).get("total_points", 0)) for sp in all_secrets)

        lines.append("\n" + "=" * 55)
        lines.append(f"📈 【全池總結】")
        lines.append(f"   今日已消耗點數: {total_consumed:,} / {total_pool_points:,} 點 (專案 1 過去歷史累計或已滿)")
        lines.append(f"   🔥 今日全池剩餘可用配額: {remaining_total_points:,} 點")
        lines.append(f"   🎬 今日還可再發布: 約 {total_avail_uploads} 首 (專案 2~7 額度充裕 100% 待命中！)")
        lines.append("💡 每日配額重置時間為太平洋時間午夜 (台灣時間約 15:00 / 16:00)。")

        msg_str = "\n".join(lines)
        self.log_text.append(msg_str)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        QMessageBox.information(self, "今日配額與輪換池總覽", msg_str)

    def _open_setup_guide(self):
        guide_path = Path(__file__).resolve().parent / "YOUTUBE_API_SETUP_GUIDE.md"
        if guide_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))
        else:
            QMessageBox.information(self, "說明指南", "請參閱專案目錄下的 YOUTUBE_API_SETUP_GUIDE.md 文件！")

    def _goto_optimizer_tab(self):
        parent_w = self.parent()
        while parent_w and not hasattr(parent_w, "youtube_optimizer"):
            parent_w = parent_w.parent()
        if parent_w and hasattr(parent_w, "left_tabs") and hasattr(parent_w, "youtube_optimizer"):
            parent_w.left_tabs.setCurrentWidget(parent_w.youtube_optimizer)

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

    def _select_uncompleted(self):
        """Selects only items that are failed or pending, unchecking fully completed ones."""
        first_target_item = None
        target_count = 0
        total_items = self.table.rowCount()

        upload_yt = self.chk_plat_yt.isChecked()
        upload_ig = self.chk_plat_ig.isChecked()
        upload_tt = self.chk_plat_tt.isChecked()

        for r in range(total_items):
            if r >= len(self.scanned_items):
                continue
            item = self.scanned_items[r]
            filename = item["filename"]
            mat_status = self.matrix_mgr.get_status(filename)

            yt_done = item.get("uploaded", False) or mat_status.get("youtube", {}).get("status") == "done"
            ig_done = mat_status.get("instagram", {}).get("status") == "done"
            tt_done = mat_status.get("tiktok", {}).get("status") == "done"

            all_target_done = True
            if upload_yt and not yt_done: all_target_done = False
            if upload_ig and not ig_done: all_target_done = False
            if upload_tt and not tt_done: all_target_done = False

            chk = self.table.item(r, 0)
            if chk:
                if all_target_done:
                    chk.setCheckState(Qt.CheckState.Unchecked)
                else:
                    chk.setCheckState(Qt.CheckState.Checked)
                    target_count += 1
                    if first_target_item is None:
                        first_target_item = chk

        if first_target_item:
            self.table.scrollToItem(first_target_item)
            self.lbl_stats.setText(f"🎯 已智慧選取 {target_count}/{total_items} 部待續傳影片（已略過完成項目）")
            self.log_text.append(f"🎯 [續傳模式] 已智慧選取 {target_count} 部未完成/失敗影片，可直接點擊『開始批次發布』接續上傳！")
        else:
            self.lbl_stats.setText("🎉 佇列中所有選定平台的影片皆已發布完成！")
            self.log_text.append("🎉 佇列中所有選定平台的影片皆已發布完成，無需續傳！")

    def scan_directory(self):
        target_dir = self.dir_input.text().strip()
        if not target_dir or not os.path.isdir(target_dir):
            return

        self.matrix_mgr = SocialMatrixManager(target_dir)
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
            filename = item["filename"]
            mat_status = self.matrix_mgr.get_status(filename)

            yt_info = mat_status.get("youtube", {})
            ig_info = mat_status.get("instagram", {})
            tt_info = mat_status.get("tiktok", {})

            yt_done = item["uploaded"] or yt_info.get("status") == "done"
            ig_done = ig_info.get("status") == "done"
            tt_done = tt_info.get("status") == "done"

            yt_failed = yt_info.get("status") == "failed"
            ig_failed = ig_info.get("status") == "failed"
            tt_failed = tt_info.get("status") == "failed"

            if yt_done:
                uploaded_count += 1

            # 0: Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked if (yt_done and ig_done and tt_done) else Qt.CheckState.Checked)
            self.table.setItem(r, 0, chk_item)

            # 1: Filename
            f_item = QTableWidgetItem(filename)
            f_item.setToolTip(item["path"])
            self.table.setItem(r, 1, f_item)

            # 2: Size
            s_item = QTableWidgetItem(item["size_str"])
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 2, s_item)

            # 3: Title
            title_text = item["title"]
            raw_title = item.get("raw_title", title_text)
            title_len = len(title_text)
            t_item = QTableWidgetItem(title_text)
            if raw_title != title_text:
                t_item.setToolTip(f"✂️ 標題已智慧精簡（優先移除末尾最不重要的 hashtag 標籤）：\n原標題 ({len(raw_title)}字): {raw_title}\n精簡後 ({title_len}/100字): {title_text}")
                t_item.setForeground(QColor("#5af78e"))
            elif title_len > 100:
                t_item.setToolTip(f"⚠️ 標題字數 {title_len}/100 超出上限！")
                t_item.setForeground(QColor("#ff5e78"))
            else:
                t_item.setToolTip(f"標題字數: {title_len}/100 (符合 YouTube 規定)")
            self.table.setItem(r, 3, t_item)

            # 4: Premiere / Release Time (will be computed)
            self.table.setItem(r, 4, QTableWidgetItem("-"))

            # 5: Multi-Platform Status Matrix Badge
            st_yt = "🔴✅" if yt_done else ("🔴❌" if yt_failed else "🔴⏳")
            st_ig = "📸✅" if ig_done else ("📸❌" if ig_failed else "📸⏳")
            st_tt = "🎵✅" if tt_done else ("🎵❌" if tt_failed else "🎵⏳")
            status_str = f"{st_yt}   {st_ig}   {st_tt}"
            status_item = QTableWidgetItem(status_str)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            tips = []
            if yt_failed and yt_info.get("error"):
                tips.append(f"YouTube 失敗原因: {yt_info.get('error')}")
            if ig_failed and ig_info.get("error"):
                tips.append(f"Instagram 失敗原因: {ig_info.get('error')}")
            if tt_failed and tt_info.get("error"):
                tips.append(f"TikTok 失敗原因: {tt_info.get('error')}")
            if tips:
                tips.append("💡 點擊下方『⚡ 僅選取未完成/失敗 (續傳)』可立即自動排程續傳！")
                status_item.setToolTip("\n\n".join(tips))

            if yt_done and ig_done and tt_done:
                status_item.setForeground(QColor("#34d399"))
            elif yt_failed or ig_failed or tt_failed:
                status_item.setForeground(QColor("#f87171"))
            elif yt_done:
                status_item.setForeground(QColor("#38bdf8"))
            else:
                status_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(r, 5, status_item)

            # 6: Link
            link_item = QTableWidgetItem()
            if item.get("youtube_url"):
                link_item.setText("觀看 / ⚙️片尾")
                link_item.setForeground(QColor("#38bdf8"))
                link_item.setToolTip(f"雙擊開啟 YouTube Studio 片尾畫面設定頁\n{item.get('youtube_url')}")
            else:
                link_item.setText("-")
                link_item.setForeground(QColor("#64748b"))
            link_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 6, link_item)

        self._recalculate_schedule_table()

        total_gb = total_bytes / (1024 ** 3)
        self.lbl_stats.setText(
            f"已載入 {len(self.scanned_items)} 部影片 (共 {total_gb:.2f} GB) | YouTube 已完成: {uploaded_count} 部 | 待處理: {len(self.scanned_items) - uploaded_count} 部"
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

        # Platform selection validation
        upload_yt = self.chk_plat_yt.isChecked()
        upload_ig = self.chk_plat_ig.isChecked()
        upload_tt = self.chk_plat_tt.isChecked()

        if not (upload_yt or upload_ig or upload_tt):
            QMessageBox.warning(self, "平台設定", "請至少勾選一個發布平台 (YouTube / Instagram / TikTok)！")
            return

        if (upload_ig or upload_tt) and not PLAYWRIGHT_AVAILABLE:
            QMessageBox.critical(
                self, "缺少依賴套件",
                "發布至 Instagram 或 TikTok 需要 Playwright 支援！\n請在終端機執行：pip install playwright"
            )
            return

        # Prepare parameters & schedule anchor
        playlist_id = None
        create_title = None
        create_privacy = "public"

        if self.chk_playlist.isChecked() and upload_yt:
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

        # Collect checked items with anchored premiere timestamps
        items_to_upload = []
        already_yt_done_count = 0
        for r in range(self.table.rowCount()):
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                data = dict(self.scanned_items[r])
                data["row_idx"] = r
                if is_premiere and start_premiere:
                    offset_secs = stagger_secs * r if self.chk_stagger.isChecked() else 0
                    data["scheduled_publish_at"] = start_premiere + timedelta(seconds=offset_secs)
                else:
                    data["scheduled_publish_at"] = None

                mat_status = self.matrix_mgr.get_status(data["filename"])
                if data.get("uploaded") or mat_status.get("youtube", {}).get("status") == "done":
                    already_yt_done_count += 1

                items_to_upload.append(data)

        if not items_to_upload:
            QMessageBox.information(self, "提示", "請至少勾選一部待上傳的影片！")
            return

        if upload_yt and already_yt_done_count > 0:
            self.log_text.append(
                f"🔄 [智慧續傳模式] 勾選了 {len(items_to_upload)} 部影片（其中 {already_yt_done_count} 部先前已完成發布，將自動略過並從未完成影片接續上傳）。"
            )

        # UI State
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)

        # Launch worker
        self.worker = VideoUploadWorker(
            engine=self.engine,
            social_engine=self.social_engine,
            matrix_mgr=self.matrix_mgr,
            items_to_upload=items_to_upload,
            upload_youtube=upload_yt,
            upload_instagram=upload_ig,
            upload_tiktok=upload_tt,
            playlist_id=playlist_id,
            create_playlist_title=create_title,
            create_playlist_privacy=create_privacy,
            privacy_status=privacy_status,
            is_premiere=is_premiere,
            start_premiere_time=start_premiere,
            stagger_interval_seconds=stagger_secs,
            auto_thumbnail=self.chk_thumbnail.isChecked(),
            auto_comment=self.chk_comment.isChecked(),
            enable_nav_chain=self.chk_nav.isChecked(),
            social_headless=not self.chk_social_visible.isChecked(),
            social_cooldown_seconds=self.combo_cooldown.currentData() or 180
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
