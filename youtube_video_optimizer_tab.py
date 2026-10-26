#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Video Optimizer & Batch Maintenance Tab (PyQt6)
======================================================
專用於 YouTube 頻道歷史影片維護、播放量分佈審計、批次隱私狀態切換與批次封面優化：
1. 頻道影片智能多維度篩選（時間、播放次數門檻、隱私狀態）
2. 全頻道觀看分佈即時審計（<10次、<50次等維度統計）
3. 批次隱私狀態變更（支援 Dry-Run 模擬安全模式、一鍵轉私人/不公開/公開）
4. 批次更換影片封面（4種模式：本地精彩黃金幀擷取、資料夾智慧匹配、統一主題封面、單部手動更換）
5. Google API 憑證池與 Quota 即時監控與自動輪換
"""

import os
import sys
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QTextEdit, QLineEdit, QComboBox, QProgressBar, QCheckBox,
    QGroupBox, QScrollArea, QFrame, QMessageBox, QSizePolicy, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton, QButtonGroup,
    QDateTimeEdit, QDateEdit, QAbstractItemView, QSpinBox, QSplitter, QTabWidget,
    QToolButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate, QUrl
from PyQt6.QtGui import QFont, QColor, QDesktopServices, QIcon, QPixmap

from youtube_uploader_engine import (
    YouTubeUploaderEngine,
    CredentialPoolManager,
    GOOGLE_API_AVAILABLE
)
from youtube_logger import logger, quota_tracker


# ---------------------------------------------------------------------------
# Background Workers
# ---------------------------------------------------------------------------

class ScanVideosWorker(QThread):
    """背景掃描頻道影片並進行條件篩選"""
    progress = pyqtSignal(int, int, str)       # current, total, status
    video_found = pyqtSignal(dict)             # single video item
    all_finished = pyqtSignal(list, dict)      # matched_list, audit_stats
    failed = pyqtSignal(str)

    def __init__(
        self,
        engine: YouTubeUploaderEngine,
        cutoff_date: Optional[datetime],
        max_views: int,
        privacy_filter: str = "all",           # all, public, unlisted, private
        max_scan: int = 1000
    ):
        super().__init__()
        self.engine = engine
        self.cutoff_date = cutoff_date
        self.max_views = max_views
        self.privacy_filter = privacy_filter
        self.max_scan = max_scan
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if not self.engine.service:
                self.engine.connect()
            svc = self.engine.service

            # 取得 uploads 播放清單
            self.progress.emit(0, 0, "正在連線 YouTube 取得頻道播放清單...")
            channel_res = svc.channels().list(mine=True, part="contentDetails,statistics,snippet").execute()
            if not channel_res.get("items"):
                self.failed.emit("找不到任何頻道資訊，請檢查 Google 帳號授權")
                return

            ch_item = channel_res["items"][0]
            uploads_id = ch_item["contentDetails"]["relatedPlaylists"]["uploads"]
            total_channel_videos = int(ch_item["statistics"].get("videoCount", 0))

            next_token = None
            seen_ids = set()
            matched_videos = []
            audit_stats = {
                "total_scanned": 0,
                "under_10": 0,
                "10_to_50": 0,
                "50_to_100": 0,
                "100_plus": 0,
                "public_count": 0,
                "unlisted_count": 0,
                "private_count": 0
            }

            self.progress.emit(0, total_channel_videos, f"開始掃描影片 (頻道總數: {total_channel_videos})...")

            while not self._is_cancelled:
                pl_req = svc.playlistItems().list(
                    playlistId=uploads_id,
                    part="contentDetails",
                    maxResults=50,
                    pageToken=next_token
                )
                pl_res = pl_req.execute()
                items = pl_res.get("items", [])
                if not items:
                    break

                batch_ids = []
                for item in items:
                    vid = item["contentDetails"]["videoId"]
                    if vid not in seen_ids:
                        seen_ids.add(vid)
                        batch_ids.append(vid)

                if batch_ids:
                    # 批次查詢詳細資料 (每批 50 支)
                    v_res = svc.videos().list(
                        id=",".join(batch_ids),
                        part="snippet,statistics,status"
                    ).execute()

                    for v in v_res.get("items", []):
                        if self._is_cancelled:
                            break
                        vid = v["id"]
                        title = v["snippet"]["title"]
                        pub_str = v["snippet"]["publishedAt"]
                        pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                        views = int(v["statistics"].get("viewCount", 0))
                        status = v["status"]["privacyStatus"]
                        thumb_url = (v["snippet"].get("thumbnails", {}).get("medium") or 
                                     v["snippet"].get("thumbnails", {}).get("default") or {}).get("url", "")

                        audit_stats["total_scanned"] += 1
                        if views < 10:
                            audit_stats["under_10"] += 1
                        elif views < 50:
                            audit_stats["10_to_50"] += 1
                        elif views < 100:
                            audit_stats["50_to_100"] += 1
                        else:
                            audit_stats["100_plus"] += 1

                        if status == "public":
                            audit_stats["public_count"] += 1
                        elif status == "unlisted":
                            audit_stats["unlisted_count"] += 1
                        elif status == "private":
                            audit_stats["private_count"] += 1

                        # 判斷是否符合使用者設定之篩選條件
                        date_match = True
                        if self.cutoff_date is not None:
                            date_match = (pub_dt < self.cutoff_date)

                        view_match = (views <= self.max_views)

                        status_match = True
                        if self.privacy_filter != "all":
                            status_match = (status == self.privacy_filter)

                        if date_match and view_match and status_match:
                            v_item = {
                                "id": vid,
                                "title": title,
                                "published_at": pub_dt,
                                "published_str": pub_dt.strftime("%Y-%m-%d"),
                                "views": views,
                                "status": status,
                                "thumb_url": thumb_url,
                                "new_thumb_path": None
                            }
                            matched_videos.append(v_item)
                            self.video_found.emit(v_item)

                scanned_count = len(seen_ids)
                self.progress.emit(
                    scanned_count,
                    total_channel_videos,
                    f"已掃描 {scanned_count} 部影片，找到 {len(matched_videos)} 部符合條件"
                )

                if self.max_scan > 0 and scanned_count >= self.max_scan:
                    break

                next_token = pl_res.get("nextPageToken")
                if not next_token:
                    break

            if self._is_cancelled:
                self.progress.emit(len(seen_ids), total_channel_videos, "掃描已由使用者中止。")
            else:
                self.progress.emit(len(seen_ids), total_channel_videos, f"掃描完成！符合條件: {len(matched_videos)} 部")

            self.all_finished.emit(matched_videos, audit_stats)

        except Exception as e:
            self.failed.emit(str(e))


class BatchPrivacyWorker(QThread):
    """背景批次修改影片隱私狀態"""
    progress = pyqtSignal(int, int, str)        # current, total, text
    item_done = pyqtSignal(str, str, bool, str) # video_id, new_status, success, error_msg
    log_msg = pyqtSignal(str)
    all_finished = pyqtSignal()
    fatal_error = pyqtSignal(str)

    def __init__(
        self,
        engine: YouTubeUploaderEngine,
        target_videos: List[Dict[str, Any]],
        new_privacy: str,                      # private, unlisted, public
        dry_run: bool = True
    ):
        super().__init__()
        self.engine = engine
        self.target_videos = target_videos
        self.new_privacy = new_privacy
        self.dry_run = dry_run
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            total = len(self.target_videos)
            self.log_msg.emit(f"🚀 開始批次修改隱私狀態 (共 {total} 部，目標: {self.new_privacy}，Dry-Run={self.dry_run})")

            for idx, item in enumerate(self.target_videos, 1):
                if self._is_cancelled:
                    self.log_msg.emit("⏹️ 使用者中止作業。")
                    break

                vid = item["id"]
                title = item["title"]

                self.progress.emit(idx, total, f"處理中 ({idx}/{total}): {title[:30]}...")

                if self.dry_run:
                    time.sleep(0.05)  # 模擬延遲
                    self.log_msg.emit(f"  [Dry-Run 模擬] 影片 {vid} ({title[:25]}...) -> 預計改為 {self.new_privacy}")
                    self.item_done.emit(vid, self.new_privacy, True, "Dry-Run 模擬成功")
                    continue

                try:
                    res = self.engine.update_video_schedule(
                        video_id=vid,
                        publish_at=None,
                        privacy_status=self.new_privacy
                    )
                    self.log_msg.emit(f"  ✅ 成功修改: {title[:25]}... (ID: {vid}) -> {self.new_privacy}")
                    self.item_done.emit(vid, self.new_privacy, True, "")
                except Exception as e:
                    err_msg = str(e)
                    self.log_msg.emit(f"  ❌ 修改失敗: {vid} - {err_msg}")
                    self.item_done.emit(vid, item["status"], False, err_msg)

                time.sleep(0.3)  # 避免觸發 API 頻率限制

            self.log_msg.emit("🏁 批次隱私修改處理完成！")
            self.all_finished.emit()

        except Exception as e:
            self.fatal_error.emit(str(e))


class BatchThumbnailWorker(QThread):
    """背景批次更換影片封面"""
    progress = pyqtSignal(int, int, str)        # current, total, text
    item_done = pyqtSignal(str, bool, str)      # video_id, success, error_msg
    log_msg = pyqtSignal(str)
    all_finished = pyqtSignal()
    fatal_error = pyqtSignal(str)

    def __init__(
        self,
        engine: YouTubeUploaderEngine,
        items_with_thumb: List[Tuple[Dict[str, Any], str]] # list of (item, thumb_image_path)
    ):
        super().__init__()
        self.engine = engine
        self.items_with_thumb = items_with_thumb
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            total = len(self.items_with_thumb)
            self.log_msg.emit(f"🖼️ 開始批次更換封面 (共 {total} 部，每部消耗 50 Quota)...")

            for idx, (item, thumb_path) in enumerate(self.items_with_thumb, 1):
                if self._is_cancelled:
                    self.log_msg.emit("⏹️ 使用者中止更換封面。")
                    break

                vid = item["id"]
                title = item["title"]

                self.progress.emit(idx, total, f"上傳封面 ({idx}/{total}): {title[:30]}...")

                if not os.path.exists(thumb_path):
                    self.log_msg.emit(f"  ⚠️ 找不到封面檔案: {thumb_path}")
                    self.item_done.emit(vid, False, "找不到封面檔案")
                    continue

                success = self.engine.set_thumbnail(vid, thumb_path)
                if success:
                    self.log_msg.emit(f"  ✅ 封面更新成功: {title[:25]}... (ID: {vid})")
                    self.item_done.emit(vid, True, "")
                else:
                    self.log_msg.emit(f"  ❌ 封面更新失敗: {vid}")
                    self.item_done.emit(vid, False, "API 傳回失敗")

                time.sleep(0.4)

            self.log_msg.emit("🏁 批次封面替換完成！")
            self.all_finished.emit()

        except Exception as e:
            self.fatal_error.emit(str(e))


# ---------------------------------------------------------------------------
# Main Tab Widget
# ---------------------------------------------------------------------------

class YouTubeVideoOptimizerTab(QWidget):
    """
    YouTube 影片優化與維護工作台 (Optimizer & Maintenance Tab)
    整合篩選、審計、批次轉私人、批次更換封面四大核心功能。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = YouTubeUploaderEngine()
        self.scan_worker: Optional[ScanVideosWorker] = None
        self.privacy_worker: Optional[BatchPrivacyWorker] = None
        self.thumb_worker: Optional[BatchThumbnailWorker] = None

        self.loaded_videos: List[Dict[str, Any]] = []
        self._init_ui()
        # Note: Do NOT call self._load_channel_stats() synchronously in __init__
        # to prevent blocking GUI startup when OAuth tokens need refreshing.

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # ----------------------------------------------------------------------
        # 1. 頂部儀表板：頻道資訊與 API Quota
        # ----------------------------------------------------------------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: #111827;
                border: 1px solid #1f2937;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 8, 12, 8)

        # 頻道基本資訊標籤
        self.lbl_channel_info = QLabel("📺 頻道: 尚未連線 (點擊右側按鈕連線) | 總影片數: -")
        self.lbl_channel_info.setStyleSheet("font-size: 14px; font-weight: bold; color: #f9fafb;")
        h_layout.addWidget(self.lbl_channel_info)

        h_layout.addStretch()

        # Quota 顯示標籤
        self.lbl_quota_info = QLabel("⚡ 今日配額: 待查詢")
        self.lbl_quota_info.setStyleSheet("font-size: 13px; color: #fbbf24; font-weight: bold;")
        h_layout.addWidget(self.lbl_quota_info)

        # 重新整理頻道按鈕
        self.btn_refresh_channel = QPushButton("🔄 重新載入頻道")
        self.btn_refresh_channel.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #334155; color: #ffffff; }
        """)
        self.btn_refresh_channel.clicked.connect(self._load_channel_stats)
        h_layout.addWidget(self.btn_refresh_channel)

        main_layout.addWidget(header_frame)

        # ----------------------------------------------------------------------
        # 2. 智能多維度篩選過濾器 (Smart Filter Bar)
        # ----------------------------------------------------------------------
        filter_group = QGroupBox("🔍 影片智能篩選與全頻道審計條件")
        filter_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #60a5fa;
                border: 1px solid #1e293b;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                background: #0b0f17;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """)
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setSpacing(10)

        # 第一行：條件控制
        row1 = QHBoxLayout()

        # 時間條件
        self.chk_cutoff_date = QCheckBox("僅限此日期前發布:")
        self.chk_cutoff_date.setChecked(True)
        self.chk_cutoff_date.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        row1.addWidget(self.chk_cutoff_date)

        self.date_cutoff = QDateEdit()
        self.date_cutoff.setDisplayFormat("yyyy-MM-dd")
        self.date_cutoff.setDate(QDate(2026, 9, 1))  # 預設九月以前
        self.date_cutoff.setStyleSheet("""
            QDateEdit {
                background: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
        """)
        row1.addWidget(self.date_cutoff)

        # 快捷時間按鈕
        btn_quick_sept = QPushButton("九月以前")
        btn_quick_sept.setStyleSheet("background: #374151; color: #d1d5db; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        btn_quick_sept.clicked.connect(lambda: (self.chk_cutoff_date.setChecked(True), self.date_cutoff.setDate(QDate(2026, 9, 1))))
        row1.addWidget(btn_quick_sept)

        btn_quick_30d = QPushButton("30天前")
        btn_quick_30d.setStyleSheet("background: #374151; color: #d1d5db; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        btn_quick_30d.clicked.connect(lambda: (self.chk_cutoff_date.setChecked(True), self.date_cutoff.setDate(QDate.currentDate().addDays(-30))))
        row1.addWidget(btn_quick_30d)

        btn_quick_all_time = QPushButton("不限時間")
        btn_quick_all_time.setStyleSheet("background: #374151; color: #d1d5db; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
        btn_quick_all_time.clicked.connect(lambda: self.chk_cutoff_date.setChecked(False))
        row1.addWidget(btn_quick_all_time)

        row1.addSpacing(16)

        # 播放次數條件
        lbl_views = QLabel("播放數上限 (<):")
        lbl_views.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        row1.addWidget(lbl_views)

        self.spin_max_views = QSpinBox()
        self.spin_max_views.setRange(1, 1000000)
        self.spin_max_views.setValue(50)  # 預設 50
        self.spin_max_views.setStyleSheet("""
            QSpinBox {
                background: #1f2937;
                color: #38bdf8;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        row1.addWidget(self.spin_max_views)

        # 播放數快捷按鈕
        btn_views_10 = QPushButton("< 10次")
        btn_views_10.setStyleSheet("background: #7f1d1d; color: #fecaca; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        btn_views_10.clicked.connect(lambda: self.spin_max_views.setValue(10))
        row1.addWidget(btn_views_10)

        btn_views_50 = QPushButton("< 50次")
        btn_views_50.setStyleSheet("background: #78350f; color: #fde68a; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        btn_views_50.clicked.connect(lambda: self.spin_max_views.setValue(50))
        row1.addWidget(btn_views_50)

        btn_views_100 = QPushButton("< 100次")
        btn_views_100.setStyleSheet("background: #1e3a8a; color: #bfdbfe; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        btn_views_100.clicked.connect(lambda: self.spin_max_views.setValue(100))
        row1.addWidget(btn_views_100)

        row1.addStretch()

        # 隱私狀態篩選
        lbl_status = QLabel("目前狀態:")
        lbl_status.setStyleSheet("color: #e5e7eb; font-weight: bold;")
        row1.addWidget(lbl_status)

        self.combo_status_filter = QComboBox()
        self.combo_status_filter.addItems(["全部狀態", "僅公開 (public)", "僅私人 (private)", "僅不公開 (unlisted)"])
        self.combo_status_filter.setStyleSheet("""
            QComboBox {
                background: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
        """)
        row1.addWidget(self.combo_status_filter)

        filter_layout.addLayout(row1)

        # 第二行：執行掃描按鈕與審計統計
        row2 = QHBoxLayout()

        self.btn_scan = QPushButton("🔍 掃描頻道符合條件影片")
        self.btn_scan.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 18px;
            }
            QPushButton:hover { background: #1d4ed8; }
        """)
        self.btn_scan.clicked.connect(self._start_scan)
        row2.addWidget(self.btn_scan)

        self.btn_cancel_scan = QPushButton("⏹️ 中止掃描")
        self.btn_cancel_scan.setEnabled(False)
        self.btn_cancel_scan.setStyleSheet("""
            QPushButton {
                background: #4b5563;
                color: #e5e7eb;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover { background: #6b7280; }
        """)
        self.btn_cancel_scan.clicked.connect(self._cancel_scan)
        row2.addWidget(self.btn_cancel_scan)

        row2.addSpacing(16)

        # 統計資訊摘要卡片
        self.lbl_audit_summary = QLabel("📊 尚未掃描：點擊按鈕即可依照設定條件過濾影片並進行分佈審計")
        self.lbl_audit_summary.setStyleSheet("color: #94a3b8; font-size: 12px;")
        row2.addWidget(self.lbl_audit_summary)

        row2.addStretch()

        filter_layout.addLayout(row2)
        main_layout.addWidget(filter_group)

        # ----------------------------------------------------------------------
        # 3. 影片清單表格 (Interactive Video Table)
        # ----------------------------------------------------------------------
        table_group = QGroupBox("📋 篩選結果與操作清單")
        table_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #10b981;
                border: 1px solid #1e293b;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                background: #0b0f17;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """)
        table_layout = QVBoxLayout(table_group)

        # 表格頂部選取快捷列
        tbl_ctrl = QHBoxLayout()
        btn_sel_all = QPushButton("全選")
        btn_sel_all.setStyleSheet("background: #1e293b; color: #93c5fd; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        btn_sel_all.clicked.connect(lambda: self._select_all_rows(True))
        tbl_ctrl.addWidget(btn_sel_all)

        btn_desel_all = QPushButton("取消全選")
        btn_desel_all.setStyleSheet("background: #1e293b; color: #93c5fd; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        btn_desel_all.clicked.connect(lambda: self._select_all_rows(False))
        tbl_ctrl.addWidget(btn_desel_all)

        btn_sel_under_10 = QPushButton("僅選取 <10 次")
        btn_sel_under_10.setStyleSheet("background: #7f1d1d; color: #fecaca; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: bold;")
        btn_sel_under_10.clicked.connect(self._select_under_10_only)
        tbl_ctrl.addWidget(btn_sel_under_10)

        tbl_ctrl.addStretch()

        self.lbl_selected_counter = QLabel("已勾選: 0 / 0 部 | 預計更換封面消耗 Quota: 0 單位")
        self.lbl_selected_counter.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        tbl_ctrl.addWidget(self.lbl_selected_counter)

        table_layout.addLayout(tbl_ctrl)

        # 表格本身
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "選取", "發布日期", "觀看次數", "目前狀態", "影片標題", "新封面路徑", "操作"
        ])
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0d1117;
                color: #e6edf3;
                gridline-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                selection-background-color: #1f6feb;
            }
            QHeaderView::section {
                background: #161b22;
                color: #8b949e;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #21262d;
            }
        """)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self.table)

        main_layout.addWidget(table_group)

        # ----------------------------------------------------------------------
        # 4. 批次操作雙引擎面板：隱私設定 & 封面更換
        # ----------------------------------------------------------------------
        action_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左引擎：批次修改隱私狀態
        p_box = QGroupBox("🔒 引擎一：批次修改隱私狀態")
        p_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #f59e0b;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding: 12px;
                background: #111827;
            }
        """)
        p_layout = QVBoxLayout(p_box)
        p_layout.setSpacing(10)

        p_row1 = QHBoxLayout()
        p_row1.addWidget(QLabel("目標狀態:"))
        self.combo_target_privacy = QComboBox()
        self.combo_target_privacy.addItems([
            "🔒 私人 (private)",
            "🔗 不公開 (unlisted)",
            "🌐 公開 (public)"
        ])
        self.combo_target_privacy.setStyleSheet("background: #1f2937; color: #f9fafb; padding: 4px; font-weight: bold;")
        p_row1.addWidget(self.combo_target_privacy)
        p_layout.addLayout(p_row1)

        self.chk_dry_run = QCheckBox("🛡️ 模擬執行模式 (Dry-Run: 僅測試預覽，不實際寫入)")
        self.chk_dry_run.setChecked(True)
        self.chk_dry_run.setStyleSheet("color: #a7f3d0; font-weight: bold;")
        p_layout.addWidget(self.chk_dry_run)

        self.btn_apply_privacy = QPushButton("🚀 執行批次隱私狀態變更")
        self.btn_apply_privacy.setStyleSheet("""
            QPushButton {
                background: #b45309;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton:hover { background: #d97706; }
        """)
        self.btn_apply_privacy.clicked.connect(self._apply_batch_privacy)
        p_layout.addWidget(self.btn_apply_privacy)

        action_splitter.addWidget(p_box)

        # 右引擎：批次更換影片封面
        t_box = QGroupBox("🖼️ 引擎二：批次更換影片封面")
        t_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #ec4899;
                border: 1px solid #374151;
                border-radius: 8px;
                margin-top: 10px;
                padding: 12px;
                background: #111827;
            }
        """)
        t_layout = QVBoxLayout(t_box)
        t_layout.setSpacing(8)

        # 封面來源模式 Tab
        self.thumb_mode_tabs = QTabWidget()
        self.thumb_mode_tabs.setStyleSheet("""
            QTabBar::tab {
                background: #1f2937;
                color: #9ca3af;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #374151;
                color: #f472b6;
            }
        """)

        # 模式 1: 本地精彩黃金幀擷取
        mode1_widget = QWidget()
        m1_layout = QVBoxLayout(mode1_widget)
        m1_layout.addWidget(QLabel("從本機渲染影片中自動使用 OpenCV 演算法抽取高對比黃金幀："))
        m1_h = QHBoxLayout()
        self.txt_video_folder = QLineEdit(os.path.join(os.getcwd(), "render_output"))
        self.txt_video_folder.setStyleSheet("background: #1f2937; color: white;")
        m1_h.addWidget(self.txt_video_folder)
        btn_browse_vid = QPushButton("瀏覽...")
        btn_browse_vid.clicked.connect(self._browse_video_folder)
        m1_h.addWidget(btn_browse_vid)
        m1_layout.addLayout(m1_h)
        btn_match_golden = QPushButton("📸 掃描並為選取影片抽取黃金幀")
        btn_match_golden.setStyleSheet("background: #0284c7; color: white; font-weight: bold; border-radius: 4px; padding: 6px;")
        btn_match_golden.clicked.connect(self._auto_extract_golden_thumbnails)
        m1_layout.addWidget(btn_match_golden)
        self.thumb_mode_tabs.addTab(mode1_widget, "📸 精彩黃金幀自動擷取")

        # 模式 2: 指定封面資料夾
        mode2_widget = QWidget()
        m2_layout = QVBoxLayout(mode2_widget)
        m2_layout.addWidget(QLabel("選擇本地封面圖片資料夾 (依檔名匹配 ID 或標題)："))
        m2_h = QHBoxLayout()
        self.txt_thumb_folder = QLineEdit()
        self.txt_thumb_folder.setStyleSheet("background: #1f2937; color: white;")
        m2_h.addWidget(self.txt_thumb_folder)
        btn_browse_thumb = QPushButton("瀏覽...")
        btn_browse_thumb.clicked.connect(self._browse_thumb_folder)
        m2_h.addWidget(btn_browse_thumb)
        m2_layout.addLayout(m2_h)
        btn_match_folder = QPushButton("📁 智慧比對資料夾中同名圖片")
        btn_match_folder.setStyleSheet("background: #0284c7; color: white; font-weight: bold; border-radius: 4px; padding: 6px;")
        btn_match_folder.clicked.connect(self._match_thumbnails_from_folder)
        m2_layout.addWidget(btn_match_folder)
        self.thumb_mode_tabs.addTab(mode2_widget, "📁 封面資料夾智慧匹配")

        # 模式 3: 統一單張底圖
        mode3_widget = QWidget()
        m3_layout = QVBoxLayout(mode3_widget)
        m3_layout.addWidget(QLabel("選擇單張圖片統一套用到所有選中的影片："))
        m3_h = QHBoxLayout()
        self.txt_single_cover = QLineEdit()
        self.txt_single_cover.setStyleSheet("background: #1f2937; color: white;")
        m3_h.addWidget(self.txt_single_cover)
        btn_browse_single = QPushButton("瀏覽...")
        btn_browse_single.clicked.connect(self._browse_single_image)
        m3_h.addWidget(btn_browse_single)
        m3_layout.addLayout(m3_h)
        btn_apply_single = QPushButton("🖼️ 設定此圖片至所有勾選項目")
        btn_apply_single.setStyleSheet("background: #0284c7; color: white; font-weight: bold; border-radius: 4px; padding: 6px;")
        btn_apply_single.clicked.connect(self._apply_single_image_to_selected)
        m3_layout.addWidget(btn_apply_single)
        self.thumb_mode_tabs.addTab(mode3_widget, "🖼️ 統一主題封面底圖")

        t_layout.addWidget(self.thumb_mode_tabs)

        self.btn_apply_thumbnails = QPushButton("🚀 批次上傳更換選取影片封面 (消耗 Quota)")
        self.btn_apply_thumbnails.setStyleSheet("""
            QPushButton {
                background: #be185d;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
            }
            QPushButton:hover { background: #db2777; }
        """)
        self.btn_apply_thumbnails.clicked.connect(self._apply_batch_thumbnails)
        t_layout.addWidget(self.btn_apply_thumbnails)

        action_splitter.addWidget(t_box)
        main_layout.addWidget(action_splitter)

        # ----------------------------------------------------------------------
        # 5. 進度條與即時日誌視窗
        # ----------------------------------------------------------------------
        prog_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                text-align: center;
                color: white;
                font-weight: bold;
                height: 18px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #3b82f6);
            }
        """)
        prog_layout.addWidget(self.progress_bar)

        self.btn_stop_all = QPushButton("⏹️ 中止作業")
        self.btn_stop_all.setEnabled(False)
        self.btn_stop_all.clicked.connect(self._stop_all_workers)
        prog_layout.addWidget(self.btn_stop_all)
        main_layout.addLayout(prog_layout)

        # 日誌終端
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(140)
        self.txt_log.setStyleSheet("""
            QTextEdit {
                background: #030712;
                color: #a7f3d0;
                font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
                font-size: 12px;
                border: 1px solid #1f2937;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        main_layout.addWidget(self.txt_log)

    # --------------------------------------------------------------------------
    # Helper & Logging
    # --------------------------------------------------------------------------
    def log(self, text: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{timestamp}] {text}")
        sb = self.txt_log.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _load_channel_stats(self):
        """讀取目前頻道資訊與 Quota 狀況"""
        try:
            if not self.engine.service:
                self.engine.connect()
            ch_req = self.engine.service.channels().list(part="snippet,statistics", mine=True)
            ch_resp = ch_req.execute()
            items = ch_resp.get("items", [])
            if items:
                title = items[0]["snippet"].get("title", "未命名頻道")
                ch_id = items[0].get("id", "-")
                v_count = items[0].get("statistics", {}).get("videoCount", "-")
                self.lbl_channel_info.setText(f"📺 頻道: {title} ({ch_id}) | 總影片數: {v_count} 部")
            else:
                self.lbl_channel_info.setText("📺 頻道: 已連線 (未能解析標題)")

            # Quota
            active_sec = self.engine.cred_manager.get_active_secret_file()
            proj = active_sec.stem if active_sec else "default"
            total_creds = len(self.engine.cred_manager.client_secrets_files)
            today_str = datetime.now().strftime("%Y-%m-%d")
            today_data = getattr(quota_tracker, "usage_data", {}).get(today_str, {})
            used_pts = today_data.get(proj, {}).get("total_points", 0)
            self.lbl_quota_info.setText(f"⚡ 今日 Quota: {used_pts}/10,000 [憑證池: {total_creds}組]")
            self.log(f"✅ 成功載入頻道資訊: {self.lbl_channel_info.text()}")
        except Exception as e:
            self.lbl_channel_info.setText(f"❌ 頻道連線失敗: {e}")
            self.log(f"❌ 頻道連線失敗: {e}")

    # --------------------------------------------------------------------------
    # 掃描與條件過濾
    # --------------------------------------------------------------------------
    def _start_scan(self):
        cutoff = None
        if self.chk_cutoff_date.isChecked():
            qd = self.date_cutoff.date()
            cutoff = datetime(qd.year(), qd.month(), qd.day(), 0, 0, 0, tzinfo=timezone.utc)

        max_views = self.spin_max_views.value()

        filter_idx = self.combo_status_filter.currentIndex()
        status_map = {0: "all", 1: "public", 2: "private", 3: "unlisted"}
        privacy_filter = status_map.get(filter_idx, "all")

        self.table.setRowCount(0)
        self.loaded_videos = []
        self.progress_bar.setValue(0)
        self.btn_scan.setEnabled(False)
        self.btn_cancel_scan.setEnabled(True)

        cutoff_str = cutoff.strftime('%Y-%m-%d') if cutoff else "不限時間"
        self.log(f"🔍 開始掃描頻道影片 (早於 {cutoff_str}，觀看數 <= {max_views}，狀態: {privacy_filter})...")

        self.scan_worker = ScanVideosWorker(
            engine=self.engine,
            cutoff_date=cutoff,
            max_views=max_views,
            privacy_filter=privacy_filter,
            max_scan=1500
        )
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.video_found.connect(self._on_video_found)
        self.scan_worker.all_finished.connect(self._on_scan_finished)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.start()

    def _cancel_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.log("正在請求停止掃描...")

    def _on_scan_progress(self, current: int, total: int, text: str):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.lbl_audit_summary.setText(f"📊 {text}")

    def _on_video_found(self, v_item: Dict[str, Any]):
        self.loaded_videos.append(v_item)
        row = self.table.rowCount()
        self.table.insertRow(row)

        # 0: 核取方塊
        chk = QCheckBox()
        chk.setChecked(True)
        chk.stateChanged.connect(self._update_selected_stats)
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.addWidget(chk)
        chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 0, chk_widget)

        # 1: 發布日期
        item_date = QTableWidgetItem(v_item["published_str"])
        item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 1, item_date)

        # 2: 觀看次數
        views = v_item["views"]
        item_views = QTableWidgetItem(f"{views:d} 次")
        item_views.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if views < 10:
            item_views.setForeground(QColor("#f87171")) # 紅色
        elif views < 50:
            item_views.setForeground(QColor("#fbbf24")) # 橘黃色
        self.table.setItem(row, 2, item_views)

        # 3: 目前狀態
        status = v_item["status"]
        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if status == "public":
            item_status.setForeground(QColor("#34d399")) # 綠色
        elif status == "private":
            item_status.setForeground(QColor("#f87171")) # 紅色
        else:
            item_status.setForeground(QColor("#fbbf24")) # 橘色
        self.table.setItem(row, 3, item_status)

        # 4: 標題
        item_title = QTableWidgetItem(v_item["title"])
        self.table.setItem(row, 4, item_title)

        # 5: 新封面路徑
        item_new_thumb = QTableWidgetItem("-")
        item_new_thumb.setForeground(QColor("#9ca3af"))
        self.table.setItem(row, 5, item_new_thumb)

        # 6: 操作按鈕
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)
        op_layout.setSpacing(4)

        btn_open = QPushButton("🔗 開啟")
        btn_open.setStyleSheet("background: #1f2937; color: #60a5fa; padding: 2px 6px; font-size: 11px;")
        vid = v_item["id"]
        btn_open.clicked.connect(lambda _, v=vid: QDesktopServices.openUrl(QUrl(f"https://youtu.be/{v}")))
        op_layout.addWidget(btn_open)

        btn_pick_one = QPushButton("🖼️ 換圖")
        btn_pick_one.setStyleSheet("background: #1f2937; color: #f472b6; padding: 2px 6px; font-size: 11px;")
        r_idx = row
        btn_pick_one.clicked.connect(lambda _, r=r_idx: self._pick_thumbnail_for_row(r))
        op_layout.addWidget(btn_pick_one)

        self.table.setCellWidget(row, 6, op_widget)

    def _on_scan_finished(self, matched: List[Dict[str, Any]], audit_stats: Dict[str, Any]):
        self.btn_scan.setEnabled(True)
        self.btn_cancel_scan.setEnabled(False)
        self.progress_bar.setValue(100)

        total_scanned = audit_stats.get("total_scanned", len(self.loaded_videos))
        u10 = audit_stats.get("under_10", 0)
        u50 = audit_stats.get("10_to_50", 0) + u10

        summary_msg = (
            f"📊 全頻道審計完成！共掃描 {total_scanned} 部 | "
            f"<10次: {u10} 部 | <50次: {u50} 部 | 本次篩選符合: {len(matched)} 部"
        )
        self.lbl_audit_summary.setText(summary_msg)
        self.log(summary_msg)
        self._update_selected_stats()

    def _on_scan_failed(self, err_msg: str):
        self.btn_scan.setEnabled(True)
        self.btn_cancel_scan.setEnabled(False)
        self.lbl_audit_summary.setText(f"❌ 掃描失敗: {err_msg}")
        self.log(f"❌ 掃描失敗: {err_msg}")
        QMessageBox.critical(self, "掃描失敗", f"無法查詢 YouTube 影片清單：\n{err_msg}")

    # --------------------------------------------------------------------------
    # 表格選取操作
    # --------------------------------------------------------------------------
    def _select_all_rows(self, select: bool):
        for row in range(self.table.rowCount()):
            chk_widget = self.table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    chk.setChecked(select)
        self._update_selected_stats()

    def _select_under_10_only(self):
        for row in range(self.table.rowCount()):
            chk_widget = self.table.cellWidget(row, 0)
            if chk_widget and row < len(self.loaded_videos):
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    chk.setChecked(self.loaded_videos[row]["views"] < 10)
        self._update_selected_stats()

    def _update_selected_stats(self):
        selected_count = 0
        total = self.table.rowCount()
        for row in range(total):
            chk_widget = self.table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk and chk.isChecked():
                    selected_count += 1

        quota_cost = selected_count * 50
        self.lbl_selected_counter.setText(
            f"已勾選: {selected_count} / {total} 部 | 預計更換封面消耗 Quota: {quota_cost:,} 單位"
        )

    def _get_selected_video_indices(self) -> List[int]:
        selected = []
        for row in range(self.table.rowCount()):
            chk_widget = self.table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk and chk.isChecked():
                    selected.append(row)
        return selected

    # --------------------------------------------------------------------------
    # 引擎一：批次修改隱私狀態 (Batch Privacy Changer)
    # --------------------------------------------------------------------------
    def _apply_batch_privacy(self):
        indices = self._get_selected_video_indices()
        if not indices:
            QMessageBox.warning(self, "提示", "請先至少勾選一部影片！")
            return

        target_text = self.combo_target_privacy.currentText()
        if "private" in target_text:
            new_privacy = "private"
        elif "unlisted" in target_text:
            new_privacy = "unlisted"
        else:
            new_privacy = "public"

        dry_run = self.chk_dry_run.isChecked()
        mode_str = "【模擬執行 (Dry-Run)】" if dry_run else "【正式修改】"

        if not dry_run:
            reply = QMessageBox.question(
                self,
                "確認修改隱私狀態",
                f"⚠️ 您即將把勾選的 {len(indices)} 部影片隱私狀態修改為「{new_privacy}」！\n\n確定要立即執行嗎？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        target_items = [self.loaded_videos[i] for i in indices]

        self.btn_apply_privacy.setEnabled(False)
        self.btn_stop_all.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log(f"🚀 開始執行批次隱私狀態變更：共 {len(target_items)} 部，目標: {new_privacy} {mode_str}")

        self.privacy_worker = BatchPrivacyWorker(
            engine=self.engine,
            target_videos=target_items,
            new_privacy=new_privacy,
            dry_run=dry_run
        )
        self.privacy_worker.progress.connect(self._on_worker_progress)
        self.privacy_worker.item_done.connect(self._on_privacy_item_done)
        self.privacy_worker.log_msg.connect(self.log)
        self.privacy_worker.all_finished.connect(self._on_privacy_finished)
        self.privacy_worker.fatal_error.connect(self._on_worker_error)
        self.privacy_worker.start()

    def _on_privacy_item_done(self, vid: str, new_status: str, success: bool, err_msg: str):
        if success:
            for row in range(self.table.rowCount()):
                if row < len(self.loaded_videos) and self.loaded_videos[row]["id"] == vid:
                    self.loaded_videos[row]["status"] = new_status
                    item_s = self.table.item(row, 3)
                    if item_s:
                        item_s.setText(new_status)
                        if new_status == "public":
                            item_s.setForeground(QColor("#34d399"))
                        elif new_status == "private":
                            item_s.setForeground(QColor("#f87171"))
                        else:
                            item_s.setForeground(QColor("#fbbf24"))
                    break

    def _on_privacy_finished(self):
        self.btn_apply_privacy.setEnabled(True)
        self.btn_stop_all.setEnabled(False)
        self.progress_bar.setValue(100)
        dry_str = " (模擬測試完畢)" if self.chk_dry_run.isChecked() else " (正式修改完成)"
        QMessageBox.information(self, "完成", f"批次隱私狀態變更已完成！{dry_str}")

    # --------------------------------------------------------------------------
    # 引擎二：批次更換封面功能 (Batch Thumbnail Replacer)
    # --------------------------------------------------------------------------
    def _browse_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇影片所在資料夾", self.txt_video_folder.text())
        if folder:
            self.txt_video_folder.setText(folder)

    def _browse_thumb_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "選擇封面圖片所在資料夾", self.txt_thumb_folder.text())
        if folder:
            self.txt_thumb_folder.setText(folder)

    def _browse_single_image(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "選擇封面圖片", "", "圖片檔案 (*.jpg *.jpeg *.png)")
        if fpath:
            self.txt_single_cover.setText(fpath)

    def _pick_thumbnail_for_row(self, row: int):
        fpath, _ = QFileDialog.getOpenFileName(self, "為此影片選擇封面", "", "圖片檔案 (*.jpg *.jpeg *.png)")
        if fpath and row < len(self.loaded_videos):
            self.loaded_videos[row]["new_thumb_path"] = fpath
            item = self.table.item(row, 5)
            if item:
                item.setText(Path(fpath).name)
                item.setForeground(QColor("#38bdf8"))
            self.log(f"已指定行 {row+1} ({self.loaded_videos[row]['title'][:20]}) 的封面: {fpath}")

    def _apply_single_image_to_selected(self):
        fpath = self.txt_single_cover.text().strip()
        if not fpath or not os.path.exists(fpath):
            QMessageBox.warning(self, "提示", "請先選擇有效的封面圖片檔案！")
            return

        indices = self._get_selected_video_indices()
        if not indices:
            QMessageBox.warning(self, "提示", "請先至少勾選一部影片！")
            return

        for row in indices:
            self.loaded_videos[row]["new_thumb_path"] = fpath
            item = self.table.item(row, 5)
            if item:
                item.setText(Path(fpath).name)
                item.setForeground(QColor("#38bdf8"))

        self.log(f"✅ 已將單張封面統一套用至 {len(indices)} 部選取影片！")
        QMessageBox.information(self, "完成", f"已為 {len(indices)} 部影片指定該封面！")

    def _match_thumbnails_from_folder(self):
        folder = self.txt_thumb_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "提示", "請選擇有效的圖片資料夾！")
            return

        valid_exts = {".jpg", ".jpeg", ".png"}
        img_files = [Path(folder) / f for f in os.listdir(folder) if Path(f).suffix.lower() in valid_exts]

        indices = self._get_selected_video_indices()
        matched_count = 0

        for row in indices:
            v_item = self.loaded_videos[row]
            vid = v_item["id"]
            title = v_item["title"].lower()

            # 1. 優先精確匹配影片 ID
            matched_file = None
            for f in img_files:
                if vid in f.stem:
                    matched_file = str(f)
                    break

            # 2. 次要模糊匹配標題關鍵字
            if not matched_file:
                for f in img_files:
                    clean_stem = re.sub(r"[^\w\s]", "", f.stem.lower())
                    clean_title = re.sub(r"[^\w\s]", "", title)
                    if clean_stem and clean_stem in clean_title:
                        matched_file = str(f)
                        break

            if matched_file:
                v_item["new_thumb_path"] = matched_file
                item = self.table.item(row, 5)
                if item:
                    item.setText(Path(matched_file).name)
                    item.setForeground(QColor("#38bdf8"))
                matched_count += 1

        self.log(f"📁 資料夾比對完成：共匹配到 {matched_count} / {len(indices)} 部影片封面！")
        QMessageBox.information(self, "匹配完成", f"共成功匹配到 {matched_count} 部影片的封面檔案！")

    def _auto_extract_golden_thumbnails(self):
        """從本地影片資料夾自動利用 OpenCV 演算法抽取高對比黃金幀"""
        folder = self.txt_video_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "提示", "請選擇有效的本機影片存放資料夾！")
            return

        indices = self._get_selected_video_indices()
        if not indices:
            QMessageBox.warning(self, "提示", "請先至少勾選一部影片！")
            return

        video_files = [Path(folder) / f for f in os.listdir(folder) if f.lower().endswith((".mp4", ".mov", ".mkv"))]
        if not video_files:
            QMessageBox.warning(self, "提示", f"在 {folder} 中未找到任何影片檔案 (.mp4)！")
            return

        self.log(f"📸 開始為 {len(indices)} 部影片尋找本地原檔並抽取 OpenCV 精彩黃金幀...")
        extracted_count = 0

        for row in indices:
            v_item = self.loaded_videos[row]
            vid = v_item["id"]
            title = v_item["title"].lower()

            # 尋找匹配的影片檔
            matched_v = None
            for vf in video_files:
                if vid in vf.stem:
                    matched_v = str(vf)
                    break
                # 比對標題主幹
                clean_vf = re.sub(r"[^\w\s]", "", vf.stem.lower())
                clean_title = re.sub(r"[^\w\s]", "", title)
                if len(clean_vf) > 4 and clean_vf in clean_title:
                    matched_v = str(vf)
                    break

            if matched_v:
                self.log(f"  🎬 找到影片檔案: {Path(matched_v).name}，正在擷取 4K 高對比黃金幀...")
                thumb_out = self.engine.extract_golden_thumbnail(matched_v)
                if thumb_out and os.path.exists(thumb_out):
                    v_item["new_thumb_path"] = thumb_out
                    item = self.table.item(row, 5)
                    if item:
                        item.setText(Path(thumb_out).name)
                        item.setForeground(QColor("#10b981"))
                    extracted_count += 1
                    self.log(f"    ✨ 成功擷取黃金封面: {Path(thumb_out).name}")

        self.log(f"📸 黃金幀擷取完成：共生成 {extracted_count} / {len(indices)} 張高品質封面！")
        QMessageBox.information(self, "擷取完成", f"已成功為 {extracted_count} 部影片生成精彩黃金幀封面！")

    def _apply_batch_thumbnails(self):
        """批次上傳更換影片封面"""
        indices = self._get_selected_video_indices()
        if not indices:
            QMessageBox.warning(self, "提示", "請先勾選欲更換封面的影片！")
            return

        items_to_upload = []
        for row in indices:
            v_item = self.loaded_videos[row]
            path = v_item.get("new_thumb_path")
            if path and os.path.exists(path):
                items_to_upload.append((v_item, path))

        if not items_to_upload:
            QMessageBox.warning(self, "提示", "勾選的項目尚未指定或找不到有效的新封面路徑！\n請先使用「黃金幀擷取」、「資料夾匹配」或「統一底圖」為影片指定圖片。")
            return

        quota_cost = len(items_to_upload) * 50
        reply = QMessageBox.question(
            self,
            "確認更換封面",
            f"🖼️ 即將為 {len(items_to_upload)} 部影片更換封面！\n"
            f"預計消耗 Google API 配額: {quota_cost:,} 單位。\n\n確定要立即開始上傳嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_apply_thumbnails.setEnabled(False)
        self.btn_stop_all.setEnabled(True)
        self.progress_bar.setValue(0)

        self.thumb_worker = BatchThumbnailWorker(
            engine=self.engine,
            items_with_thumb=items_to_upload
        )
        self.thumb_worker.progress.connect(self._on_worker_progress)
        self.thumb_worker.item_done.connect(self._on_thumb_item_done)
        self.thumb_worker.log_msg.connect(self.log)
        self.thumb_worker.all_finished.connect(self._on_thumb_finished)
        self.thumb_worker.fatal_error.connect(self._on_worker_error)
        self.thumb_worker.start()

    def _on_thumb_item_done(self, vid: str, success: bool, err_msg: str):
        for row in range(self.table.rowCount()):
            if row < len(self.loaded_videos) and self.loaded_videos[row]["id"] == vid:
                item = self.table.item(row, 5)
                if item:
                    if success:
                        item.setText(item.text() + " [✅已套用]")
                        item.setForeground(QColor("#10b981"))
                    else:
                        item.setText(item.text() + " [❌失敗]")
                        item.setForeground(QColor("#ef4444"))
                break

    def _on_thumb_finished(self):
        self.btn_apply_thumbnails.setEnabled(True)
        self.btn_stop_all.setEnabled(False)
        self.progress_bar.setValue(100)
        self._load_channel_stats()
        QMessageBox.information(self, "完成", "批次更換封面作業已全部完成！")

    # --------------------------------------------------------------------------
    # 通用 Worker 狀態回調
    # --------------------------------------------------------------------------
    def _on_worker_progress(self, current: int, total: int, text: str):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_worker_error(self, err_msg: str):
        self.btn_apply_privacy.setEnabled(True)
        self.btn_apply_thumbnails.setEnabled(True)
        self.btn_stop_all.setEnabled(False)
        self.log(f"❌ 作業發生錯誤: {err_msg}")
        QMessageBox.critical(self, "錯誤", f"背景作業中斷：\n{err_msg}")

    def _stop_all_workers(self):
        if self.privacy_worker and self.privacy_worker.isRunning():
            self.privacy_worker.cancel()
        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.cancel()
        self.btn_stop_all.setEnabled(False)
        self.log("⏹️ 已發送中止請求...")
