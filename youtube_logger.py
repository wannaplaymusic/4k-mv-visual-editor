#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Uploader Logging & Telemetry Subsystem
=============================================
Provides production-grade logging, quota tracking, transfer performance metrics,
and error diagnostics for subsequent debugging and optimization.
"""

import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

LOGGER_NAME = "YouTubeUploader"

# API Quota Costs (Units)
QUOTA_COSTS = {
    "videos.insert": 1600,
    "playlists.insert": 50,
    "playlistItems.insert": 50,
    "thumbnails.set": 50,
    "commentThreads.insert": 50,
    "channels.list": 1,
    "videos.list": 1,
    "playlists.list": 1
}


class QuotaTracker:
    """Tracks Google API quota consumption per project to prevent unexpected exhaustion."""

    def __init__(self, log_dir: Path):
        self.tracker_file = log_dir / "quota_usage.json"
        self.usage_data = self._load_data()

    def _get_today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _load_data(self) -> Dict[str, Any]:
        if self.tracker_file.exists():
            try:
                with open(self.tracker_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_data(self):
        try:
            with open(self.tracker_file, "w", encoding="utf-8") as f:
                json.dump(self.usage_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def record_action(self, project_name: str, action: str) -> Dict[str, Any]:
        """Records an API call and returns updated quota usage."""
        cost = QUOTA_COSTS.get(action, 1)
        today = self._get_today_key()

        if today not in self.usage_data:
            self.usage_data[today] = {}

        proj_data = self.usage_data[today].setdefault(project_name, {
            "total_points": 0,
            "calls": {},
            "last_updated": ""
        })

        proj_data["total_points"] += cost
        proj_data["calls"][action] = proj_data["calls"].get(action, 0) + 1
        proj_data["last_updated"] = datetime.now().strftime("%H:%M:%S")

        self._save_data()
        remaining = max(0, 10000 - proj_data["total_points"])
        return {
            "cost": cost,
            "total": proj_data["total_points"],
            "remaining": remaining,
            "calls": proj_data["calls"]
        }


def setup_youtube_logger(log_level=logging.DEBUG) -> logging.Logger:
    """Configures rotating file logger and console output for YouTube Uploader."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(log_level)

    # Determine logs directory in workspace
    workspace_dir = Path(__file__).resolve().parent
    logs_dir = workspace_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / "youtube_uploader.log"

    # Rotating file handler: 10 MB per file, max 5 backup files (50 MB total history)
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "[%(asctime)s] [YT-%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logger.info("=================================================================")
    logger.info("📤 [YouTubeUploader] Logging Subsystem Initialized")
    logger.info(f"📁 Log File: {log_file}")
    logger.info("=================================================================")

    return logger


# Global singleton instance
logger = setup_youtube_logger()
quota_tracker = QuotaTracker(Path(__file__).resolve().parent / "logs")
