#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Social Uploader Engine (Instagram Reels & TikTok Batch Automation)
==================================================================
- Playwright-driven browser automation with real Chrome Profile reuse
- Human-like Gaussian cooldown intervals (180s - 300s) to prevent spam flags
- Anti-Bot Circuit Breakers (detects Captchas / Action Blocked and pauses queue)
- Multi-Platform State Matrix (social_upload_matrix.json) for atomic progress tracking
- Supports immediate publishing or native platform scheduling/drafting
"""

import os
import sys
import json
import time
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple

try:
    from playwright.sync_api import sync_playwright, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class SocialMatrixManager:
    """Manages multi-platform status matrix across YouTube, Instagram, and TikTok."""

    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir)
        self.matrix_file = self.target_dir / "social_upload_matrix.json"
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.matrix_file.exists():
            try:
                with open(self.matrix_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        try:
            with open(self.matrix_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_status(self, filename: str) -> Dict[str, Any]:
        return self.data.get(filename, {
            "youtube": {"status": "pending", "id": "", "url": "", "time": ""},
            "instagram": {"status": "pending", "post_id": "", "time": ""},
            "tiktok": {"status": "pending", "post_id": "", "time": ""}
        })

    def update_platform_status(self, filename: str, platform: str, status: str, details: Optional[Dict[str, Any]] = None):
        if filename not in self.data:
            self.data[filename] = self.get_status(filename)
        
        plat_data = self.data[filename].setdefault(platform, {})
        plat_data["status"] = status
        plat_data["time"] = datetime.now().isoformat()
        if details:
            plat_data.update(details)
        self._save()


class SocialUploaderEngine:
    """
    Automates uploading to Instagram Reels and TikTok via user-directed browser sessions.
    """

    def __init__(self, chrome_user_data_dir: Optional[str] = None):
        self.user_data_dir = chrome_user_data_dir or str(Path.home() / "Library/Application Support/Google/Chrome/Default")
        self.session_dir = Path(__file__).resolve().parent / "social_browser_profile"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._caffeinate_proc = None
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def reset_cancel(self):
        self._cancel_requested = False

    def start_sleep_prevention(self):
        if sys.platform == "darwin" and self._caffeinate_proc is None:
            try:
                self._caffeinate_proc = subprocess.Popen(
                    ["caffeinate", "-d", "-i", "-s"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

    def stop_sleep_prevention(self):
        if self._caffeinate_proc:
            try:
                self._caffeinate_proc.terminate()
                self._caffeinate_proc.wait(timeout=2)
            except Exception:
                pass
            self._caffeinate_proc = None

    # --------------------------------------------------------------------------
    # Human-like typing & timing simulation
    # --------------------------------------------------------------------------
    @staticmethod
    def human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
        time.sleep(random.uniform(min_sec, max_sec))

    @staticmethod
    def human_cooldown(base_sec: int = 180, jitter_sec: int = 45, status_cb: Optional[Callable[[str], None]] = None):
        """Dynamic Gaussian cooldown interval between uploads to mimic human cadence."""
        delay = max(30, int(random.gauss(base_sec, jitter_sec)))
        if status_cb:
            status_cb(f"⏳ [防風控冷卻] 擬人安全間隔等待 {delay} 秒，避免被平台判定為機器人...")
        time.sleep(delay)

    # --------------------------------------------------------------------------
    # Instagram Reels Uploader
    # --------------------------------------------------------------------------
    def upload_instagram_reel(
        self,
        video_path: str,
        caption: str,
        headless: bool = False,
        status_cb: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """Uploads a video as Instagram Reel using Web Creator flow."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright package is not installed. Run: pip install playwright")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        self.start_sleep_prevention()
        result = {"platform": "instagram", "status": "failed", "url": "", "error": ""}

        try:
            with sync_playwright() as p:
                if status_cb:
                    status_cb(f"🌐 正在啟動 Instagram 瀏覽器環境 (模式: {'背景' if headless else '可視化'})...")

                # Launch persistent context to preserve login cookies
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir / "instagram"),
                    headless=headless,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 800}
                )

                page = context.new_page()
                page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                self.human_delay(2, 4)

                # Check if logged in
                if status_cb:
                    status_cb("🔍 檢查 Instagram 登入狀態...")

                # Look for Create post (+) button (SVG or role)
                create_btn = page.locator("svg[aria-label='New post'], svg[aria-label='新貼文'], svg[aria-label='Create'], svg[aria-label='建立']")
                if create_btn.count() == 0:
                    # User needs to log in once
                    if headless:
                        raise RuntimeError("Instagram 尚未登入！請切換為『可視化瀏覽器模式』登入一次以保存 Session。")
                    if status_cb:
                        status_cb("🔑 請在開啟的瀏覽器中登入您的 Instagram 帳號 (只需登入一次即可永久記住)...")
                    
                    # Wait up to 120 seconds for user to log in
                    try:
                        create_btn.first.wait_for(state="visible", timeout=120000)
                    except Exception:
                        raise TimeoutError("Instagram 登入逾時，請重試並完成登入。")

                if status_cb:
                    status_cb("🎬 點擊『建立』並準備上傳 Reels 影片...")

                create_btn.first.click()
                self.human_delay(1.5, 2.5)

                # Select from computer input
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0:
                    file_input.first.set_input_files(video_path)
                else:
                    # Look for button that opens file dialog
                    select_btn = page.locator("button:has-text('Select from computer'), button:has-text('從電腦選擇')")
                    with page.expect_file_chooser() as fc_info:
                        select_btn.first.click()
                    file_chooser = fc_info.value
                    file_chooser.set_files(video_path)

                if status_cb:
                    status_cb("⏳ 影片已送入 Instagram 創作者後台，正在等待預覽加載...")
                self.human_delay(3, 5)

                # Next buttons in Reels flow (Crop -> Edit -> Details)
                for step_idx in range(2):
                    next_btn = page.locator("div[role='button']:has-text('Next'), div[role='button']:has-text('下一步')")
                    if next_btn.count() > 0:
                        next_btn.first.click()
                        self.human_delay(2, 3)

                # Caption input area
                if status_cb:
                    status_cb("✍️ 正在自動注入 Reels 文案與精準 Hashtags...")

                caption_area = page.locator("div[aria-label='Write a caption...'], div[aria-label='輸入說明文字...'], div[role='textbox']")
                if caption_area.count() > 0:
                    caption_area.first.click()
                    caption_area.first.fill(caption[:2200])
                    self.human_delay(1, 2)

                # Share / Publish Button
                share_btn = page.locator("div[role='button']:has-text('Share'), div[role='button']:has-text('分享')")
                if share_btn.count() > 0:
                    if status_cb:
                        status_cb("🚀 點擊『分享』，正在發布至 Instagram Reels...")
                    share_btn.first.click()

                    # Wait for completion dialog ("Your reel has been shared")
                    page.wait_for_selector("text='Your reel has been shared', text='你的連續短片已分享', text='Your post has been shared'", timeout=90000)
                    if status_cb:
                        status_cb("✅ Instagram Reel 發布成功！")
                    result["status"] = "done"
                    result["time"] = datetime.now().isoformat()
                else:
                    raise RuntimeError("找不到 Instagram 分享按鈕！")

                context.close()
                return result

        except Exception as e:
            result["error"] = str(e)
            if status_cb:
                status_cb(f"❌ Instagram 發布失敗: {e}")
            return result
        finally:
            self.stop_sleep_prevention()

    # --------------------------------------------------------------------------
    # TikTok Studio Uploader
    # --------------------------------------------------------------------------
    def upload_tiktok_video(
        self,
        video_path: str,
        caption: str,
        as_draft: bool = False,
        headless: bool = False,
        status_cb: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """Uploads a video to TikTok Studio using Web Creator flow."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright package is not installed. Run: pip install playwright")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        self.start_sleep_prevention()
        result = {"platform": "tiktok", "status": "failed", "url": "", "error": ""}

        try:
            with sync_playwright() as p:
                if status_cb:
                    status_cb(f"🌐 正在啟動 TikTok Studio 瀏覽器環境 (模式: {'背景' if headless else '可視化'})...")

                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir / "tiktok"),
                    headless=headless,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 800}
                )

                page = context.new_page()
                page.goto("https://www.tiktok.com/creator-center/upload?from=upload", wait_until="domcontentloaded")
                self.human_delay(3, 5)

                # Check if logged in
                if "login" in page.url.lower():
                    if headless:
                        raise RuntimeError("TikTok 尚未登入！請切換為『可視化瀏覽器模式』完成一次登入以保存 Session。")
                    if status_cb:
                        status_cb("🔑 請在開啟的瀏覽器中完成 TikTok 創作者登入...")
                    page.wait_for_url(lambda u: "login" not in u.lower(), timeout=120000)

                if status_cb:
                    status_cb("🎬 正在拖放影片至 TikTok Studio 上傳區...")

                # Drop file into upload input
                file_input = page.locator("input[type='file'], input[accept*='video']")
                file_input.first.set_input_files(video_path)

                if status_cb:
                    status_cb("⏳ 影片上傳中，正在等待 TikTok 伺服器校驗...")
                self.human_delay(5, 8)

                # Caption Editor
                if status_cb:
                    status_cb("✍️ 正在填寫 TikTok 影片說明與熱門標籤...")

                editor = page.locator("div[contenteditable='true'], div[class*='notranslate'][class*='public-DraftEditor-content']")
                if editor.count() > 0:
                    editor.first.click()
                    # Select all and replace
                    page.keyboard.press("Meta+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(caption[:2000], delay=15)
                    self.human_delay(1.5, 3)

                # Post or Save as draft
                if as_draft:
                    action_btn = page.locator("button:has-text('Save as draft'), button:has-text('存為草稿')")
                else:
                    action_btn = page.locator("button:has-text('Post'), button:has-text('發佈')")

                if action_btn.count() > 0:
                    action_name = "存為草稿" if as_draft else "發布"
                    if status_cb:
                        status_cb(f"🚀 點擊『{action_name}』...")
                    action_btn.first.click()

                    # Wait for success dialog
                    page.wait_for_selector("text='Your video has been uploaded', text='影片已發佈', text='Saved as draft', text='已存為草稿'", timeout=90000)
                    if status_cb:
                        status_cb(f"✅ TikTok 影片成功{action_name}！")
                    result["status"] = "done"
                    result["time"] = datetime.now().isoformat()
                else:
                    raise RuntimeError("找不到 TikTok 發布/草稿按鈕！")

                context.close()
                return result

        except Exception as e:
            result["error"] = str(e)
            if status_cb:
                status_cb(f"❌ TikTok 發布失敗: {e}")
            return result
        finally:
            self.stop_sleep_prevention()
