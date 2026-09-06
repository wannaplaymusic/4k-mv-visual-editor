#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Auto-Uploader Engine (4K Resumable Upload with Playlist & Premiere Support)
==================================================================================
- Google OAuth 2.0 Client Manager with Multi-Credential Pool (Quota rotation)
- Resumable Chunked Upload (10MB-20MB chunks) for large 4K files (1GB - 3GB+)
- Smart _social.txt Metadata Parsing (Title, Description, Hashtags, CC credits)
- Playlist Management (List existing playlists, create new playlist, add to playlist)
- Premiere & Scheduled Release (status.publishAt with UTC ISO 8601 conversion)
- macOS caffeinate integration to prevent sleep during 20GB transfers
- Persistent upload history (upload_history.json) to prevent duplicate uploads
"""

import os
import sys
import re
import json
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple

# Google API Client Libraries (imported lazily or guarded)
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtubepartner"
]

from youtube_logger import logger, quota_tracker

CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB per chunk for smooth progress reporting and memory efficiency


class MetadataParser:
    """Parses companion _social.txt and metadata files for videos."""

    @staticmethod
    def smart_truncate_title(title: str, max_len: int = 100) -> Tuple[str, Optional[str]]:
        """
        Safely truncates title to max_len (YouTube limit: 100 characters).
        Preserves complete words and delimiters without cutting mid-word.
        Returns: (safe_title, overflow_text_or_None)
        """
        clean_title = re.sub(r"\s+", " ", title).strip()
        if len(clean_title) <= max_len:
            return clean_title, None

        # Try splitting by ' | ' to drop secondary trailer if needed
        parts = clean_title.split(" | ")
        if len(parts) > 1:
            candidate = " | ".join(parts[:-1]).strip()
            if len(candidate) <= max_len:
                return candidate, parts[-1]

        # Break at last whitespace within max_len - 3
        truncated = clean_title[:max_len - 3]
        last_space = truncated.rfind(" ")
        if last_space > 30:
            truncated = truncated[:last_space]
        safe_title = truncated.strip() + "..."
        overflow = clean_title[len(safe_title.rstrip(".")):].strip()
        return safe_title, overflow

    @staticmethod
    def parse_social_file(social_path: str, clip_idx: Optional[int] = None) -> Dict[str, Any]:
        """
        Extracts YouTube Long-form or Shorts Video metadata from _social.txt or _shorts_social.txt
        """
        data = {
            "title": "",
            "description": "",
            "tags": [],
            "raw_hashtags": "",
            "track": "",
            "artist": "",
            "genre": "",
            "bpm": "",
            "duration": ""
        }

        if not os.path.exists(social_path):
            return data

        try:
            with open(social_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # 1. Basic Header Track Info
            m_track = re.search(r"^Track:\s*(.+)$", content, re.M)
            if m_track: data["track"] = m_track.group(1).strip()

            m_artist = re.search(r"^Artist:\s*(.+)$", content, re.M)
            if m_artist: data["artist"] = m_artist.group(1).strip()

            m_genre = re.search(r"^Genre:\s*(.+)$", content, re.M)
            if m_genre: data["genre"] = m_genre.group(1).strip()

            m_bpm = re.search(r"^BPM:\s*(\d+)", content, re.M)
            if m_bpm: data["bpm"] = m_bpm.group(1).strip()

            m_dur = re.search(r"^Duration:\s*(.+)$", content, re.M)
            if m_dur: data["duration"] = m_dur.group(1).strip()

            # 2. Check Shorts format (e.g. --- [Clip 1] --- and 【YouTube Shorts Title】)
            if clip_idx is not None or "【YouTube Shorts Title】" in content or "--- [Clip" in content:
                clip_num = clip_idx if clip_idx is not None else 1
                clip_pattern = rf"---\s*\[Clip\s*{clip_num}\](?:.*?)\s*---(.*?)(?:---\s*\[Clip|\Z)"
                clip_match = re.search(clip_pattern, content, re.DOTALL | re.IGNORECASE)
                section_text = clip_match.group(1) if clip_match else content

                # Shorts Title
                st_match = re.search(r"【YouTube Shorts Title】\s*\n+([^\n]+)", section_text)
                if st_match:
                    data["title"] = st_match.group(1).strip()

                # Shorts Description
                sd_match = re.search(r"【YouTube Shorts Description】\s*\n+(.*?)(?=【Instagram|【TikTok|【Hashtags|\Z)", section_text, re.DOTALL)
                if sd_match:
                    data["description"] = sd_match.group(1).strip()

                # Hashtags
                sh_match = re.search(r"【Hashtags】\s*\n*([^\n=]+)", section_text)
                if sh_match:
                    raw_tags = sh_match.group(1).strip()
                    data["raw_hashtags"] = raw_tags
                    tags_clean = [t.strip("#").strip() for t in re.split(r"[\s,]+", raw_tags) if t.strip("#").strip()]
                    data["tags"] = tags_clean[:30]

            # 3. Standard Long-form Video parsing (if not Shorts or if title empty)
            if not data["title"]:
                yt_section_match = re.search(
                    r"---\s*\[1\]\s*YOUTUBE LONG-FORM VIDEO\s*---(.*?)(?:---|===|$)",
                    content,
                    re.DOTALL | re.IGNORECASE
                )
                section_text = yt_section_match.group(1) if yt_section_match else content

                # Extract Title
                title_match = re.search(
                    r"Title:\s*\n+([^\n]+)",
                    section_text,
                    re.IGNORECASE
                )
                if title_match:
                    data["title"] = title_match.group(1).strip()

                # Extract Description
                desc_match = re.search(
                    r"Description:\s*\n(.*?)(?=\nHashtags:|\n===|\n---|$)",
                    section_text,
                    re.DOTALL | re.IGNORECASE
                )
                if desc_match:
                    data["description"] = desc_match.group(1).strip()

                # Extract Hashtags / Tags
                tags_match = re.search(
                    r"Hashtags:\s*\n*([^\n=]+)",
                    section_text,
                    re.IGNORECASE
                )
                if tags_match:
                    raw_tags = tags_match.group(1).strip()
                    data["raw_hashtags"] = raw_tags
                    tags_clean = [t.strip("#").strip() for t in re.split(r"[\s,]+", raw_tags) if t.strip("#").strip()]
                    data["tags"] = tags_clean[:30]

        except Exception as e:
            print(f"[MetadataParser] Error reading {social_path}: {e}", file=sys.stderr)

        return data


class CredentialPoolManager:
    """
    Manages multiple Google OAuth 2.0 client_secrets to bypass the 10,000 quota limit per project.
    Allows seamless rotation when one project's daily quota is exhausted.
    """

    def __init__(self, credentials_dir: Optional[str] = None):
        if credentials_dir is None:
            # Default to youtube_credentials/ or current workspace
            base_dir = Path(__file__).resolve().parent
            self.cred_dir = base_dir / "youtube_credentials"
        else:
            self.cred_dir = Path(credentials_dir)

        self.cred_dir.mkdir(parents=True, exist_ok=True)
        self.client_secrets_files: List[Path] = []
        self.current_index: int = 0
        self.reload_secrets()

    def reload_secrets(self):
        """Scans for client_secrets*.json in cred_dir and root workspace."""
        found: List[Path] = []
        # Check inside credentials_dir
        if self.cred_dir.exists():
            for p in sorted(self.cred_dir.glob("*.json")):
                if "client_secret" in p.name.lower() or "client_id" in p.name.lower():
                    found.append(p)

        # Also check root workspace
        root_dir = Path(__file__).resolve().parent
        for p in sorted(root_dir.glob("client_secrets*.json")):
            if p not in found:
                found.append(p)

        self.client_secrets_files = found
        print(f"[CredentialPool] Found {len(found)} client_secrets file(s): {[f.name for f in found]}")

    def has_credentials(self) -> bool:
        return len(self.client_secrets_files) > 0

    def get_active_secret_file(self) -> Optional[Path]:
        if not self.client_secrets_files:
            return None
        return self.client_secrets_files[self.current_index % len(self.client_secrets_files)]

    def rotate_to_next(self) -> bool:
        """Rotates to the next credential project in the pool. Returns True if a new project was chosen."""
        if len(self.client_secrets_files) <= 1:
            return False
        self.current_index = (self.current_index + 1) % len(self.client_secrets_files)
        print(f"[CredentialPool] 🔄 Rotated to credential project: {self.get_active_secret_file().name}")
        return True

    def get_authenticated_service(self, headless_port: int = 0):
        """
        Authenticates using the currently active client_secrets.
        Stores token_<index>.json in cred_dir.
        """
        if not GOOGLE_API_AVAILABLE:
            raise RuntimeError("Google API packages are not installed. Run: pip install google-api-python-client google-auth-oauthlib")

        secret_file = self.get_active_secret_file()
        if not secret_file:
            raise FileNotFoundError(f"No client_secrets.json found in {self.cred_dir}. Please refer to YOUTUBE_API_SETUP_GUIDE.md")

        token_file = self.cred_dir / f"token_{secret_file.stem}.json"
        creds = None

        if token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)
            except Exception as e:
                print(f"[CredentialPool] Existing token invalid: {e}")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"[CredentialPool] Failed to refresh token: {e}, re-authenticating...")
                    creds = None

            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), YOUTUBE_SCOPES)
                creds = flow.run_local_server(port=headless_port)

            with open(token_file, "w", encoding="utf-8") as token_out:
                token_out.write(creds.to_json())

        # Build YouTube v3 service
        service = build("youtube", "v3", credentials=creds)
        return service


class YouTubeUploaderEngine:
    """
    Main Upload Engine handling 4K Resumable Chunked Video Uploads,
    Playlists, and Scheduled Premiere Releases.
    """

    def __init__(self, credentials_dir: Optional[str] = None):
        self.cred_manager = CredentialPoolManager(credentials_dir)
        self.service = None
        self._caffeinate_proc = None
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def reset_cancel(self):
        self._cancel_requested = False

    def connect(self) -> Any:
        """Initializes YouTube API client."""
        self.service = self.cred_manager.get_authenticated_service()
        return self.service

    def get_channel_info(self) -> Dict[str, str]:
        """Fetches title, id, and customUrl of the currently authenticated channel."""
        if not self.service:
            self.connect()
        try:
            req = self.service.channels().list(part="snippet", mine=True)
            resp = req.execute()
            items = resp.get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                return {
                    "id": items[0].get("id", ""),
                    "title": snippet.get("title", "未命名頻道"),
                    "custom_url": snippet.get("customUrl", ""),
                    "description": snippet.get("description", "")
                }
        except Exception as e:
            print(f"[YouTubeUploaderEngine] Error getting channel info: {e}", file=sys.stderr)
        return {"id": "", "title": "未知頻道", "custom_url": "", "description": ""}

    def logout(self):
        """Removes saved token so user can switch channel/account on next login."""
        self.service = None
        secret_file = self.cred_manager.get_active_secret_file()
        if secret_file:
            token_file = self.cred_manager.cred_dir / f"token_{secret_file.stem}.json"
            if token_file.exists():
                try:
                    token_file.unlink()
                    print(f"[YouTubeUploaderEngine] Removed token {token_file.name}")
                except Exception as e:
                    print(f"[YouTubeUploaderEngine] Error removing token: {e}")

    # --------------------------------------------------------------------------
    # Sleep Prevention (macOS caffeinate)
    # --------------------------------------------------------------------------
    def start_sleep_prevention(self):
        """Prevents macOS from sleeping during large 4K uploads."""
        if sys.platform == "darwin" and self._caffeinate_proc is None:
            try:
                self._caffeinate_proc = subprocess.Popen(
                    ["caffeinate", "-d", "-i", "-s"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print("[SleepPrevention] ☕ Activated macOS caffeinate.")
            except Exception as e:
                print(f"[SleepPrevention] Note: Could not start caffeinate: {e}")

    def stop_sleep_prevention(self):
        if self._caffeinate_proc:
            try:
                self._caffeinate_proc.terminate()
                self._caffeinate_proc.wait(timeout=2)
            except Exception:
                pass
            self._caffeinate_proc = None
            print("[SleepPrevention] ☕ Deactivated macOS caffeinate.")

    # --------------------------------------------------------------------------
    # Playlist Management
    # --------------------------------------------------------------------------
    def list_playlists(self) -> List[Dict[str, str]]:
        """Fetches up to 50 playlists belonging to the authenticated channel."""
        if not self.service:
            self.connect()

        playlists = []
        try:
            req = self.service.playlists().list(
                part="snippet,contentDetails",
                mine=True,
                maxResults=50
            )
            resp = req.execute()
            for item in resp.get("items", []):
                playlists.append({
                    "id": item["id"],
                    "title": item["snippet"]["title"],
                    "item_count": str(item.get("contentDetails", {}).get("itemCount", 0)),
                    "privacy": item["snippet"].get("privacyStatus", "public")
                })
        except Exception as e:
            print(f"[YouTubeUploaderEngine] Error listing playlists: {e}", file=sys.stderr)
            raise e

        return playlists

    def create_playlist(self, title: str, description: str = "", privacy: str = "public") -> str:
        """Creates a new playlist and returns its playlistId."""
        if not self.service:
            self.connect()

        body = {
            "snippet": {
                "title": title,
                "description": description
            },
            "status": {
                "privacyStatus": privacy
            }
        }
        resp = self.service.playlists().insert(
            part="snippet,status",
            body=body
        ).execute()

        playlist_id = resp["id"]
        proj = self.cred_manager.get_active_secret_file().stem if self.cred_manager.get_active_secret_file() else "default"
        q = quota_tracker.record_action(proj, "playlists.insert")
        logger.info(f"✅ Created playlist '{title}' (ID: {playlist_id}) [Quota: -50, used {q['total']}/10000 on {proj}]")
        return playlist_id

    def add_video_to_playlist(self, video_id: str, playlist_id: str, position: Optional[int] = None) -> bool:
        """Adds a video to an existing playlist."""
        if not self.service:
            self.connect()

        snippet = {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id
            }
        }
        if position is not None:
            snippet["position"] = position

        try:
            self.service.playlistItems().insert(
                part="snippet",
                body={"snippet": snippet}
            ).execute()
            proj = self.cred_manager.get_active_secret_file().stem if self.cred_manager.get_active_secret_file() else "default"
            q = quota_tracker.record_action(proj, "playlistItems.insert")
            logger.info(f"➕ Video {video_id} added to playlist {playlist_id} [Quota: -50, used {q['total']}/10000 on {proj}]")
            return True
        except Exception as e:
            logger.error(f"Failed to add video {video_id} to playlist {playlist_id}: {e}", exc_info=True)
            return False

    # --------------------------------------------------------------------------
    # Thumbnail, Pinned Comment & Transcode Sentinel
    # --------------------------------------------------------------------------
    @staticmethod
    def extract_golden_thumbnail(video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Extracts a vibrant, non-black 4K golden frame at high visual energy point using OpenCV.
        Saves JPEG under 2MB (YouTube thumbnail requirement).
        """
        try:
            import cv2
            import numpy as np
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            if duration <= 1:
                cap.release()
                return None

            # Sample 8 candidates across the video (15% to 75%)
            candidates = np.linspace(duration * 0.15, duration * 0.75, 8)
            best_frame = None
            best_score = -1.0

            for sec in candidates:
                cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
                ret, frame = cap.read()
                if ret and frame is not None:
                    mean_b = float(np.mean(frame))
                    std_c = float(np.std(frame))
                    if 20 < mean_b < 235:
                        score = std_c * 1.5 + min(mean_b, 120.0)
                        if score > best_score:
                            best_score = score
                            best_frame = frame

            cap.release()

            if best_frame is None:
                return None

            if not output_path:
                stem = Path(video_path).stem
                output_path = str(Path(video_path).parent / f"{stem}_thumb.jpg")

            # Save JPEG with quality 90
            cv2.imwrite(output_path, best_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

            # Check file size < 2MB
            if os.path.exists(output_path) and os.path.getsize(output_path) > 2 * 1024 * 1024:
                resized = cv2.resize(best_frame, (1920, 1080), interpolation=cv2.INTER_AREA)
                cv2.imwrite(output_path, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 92])

            return output_path
        except Exception as e:
            print(f"[YouTubeUploaderEngine] Error extracting thumbnail: {e}", file=sys.stderr)
            return None

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """Sets a custom thumbnail for a video."""
        if not self.service:
            self.connect()
        try:
            req = self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            )
            req.execute()
            proj = self.cred_manager.get_active_secret_file().stem if self.cred_manager.get_active_secret_file() else "default"
            q = quota_tracker.record_action(proj, "thumbnails.set")
            logger.info(f"🖼️ Custom thumbnail set for video {video_id} [Quota: -50, used {q['total']}/10000 on {proj}]")
            return True
        except Exception as e:
            logger.error(f"Failed to set thumbnail for {video_id}: {e}", exc_info=True)
            return False

    def post_pinned_comment(self, video_id: str, comment_text: str) -> Optional[str]:
        """Posts an initial engagement comment on the video."""
        if not self.service:
            self.connect()
        try:
            body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
            resp = self.service.commentThreads().insert(
                part="snippet",
                body=body
            ).execute()
            comment_id = resp["id"]
            proj = self.cred_manager.get_active_secret_file().stem if self.cred_manager.get_active_secret_file() else "default"
            q = quota_tracker.record_action(proj, "commentThreads.insert")
            logger.info(f"💬 Posted engagement comment for video {video_id} (ID: {comment_id}) [Quota: -50, used {q['total']}/10000 on {proj}]")
            return comment_id
        except Exception as e:
            logger.error(f"Failed to post comment on {video_id}: {e}", exc_info=True)
            return None

    def check_transcode_status(self, video_id: str) -> Dict[str, Any]:
        """Checks if 4K/HD video processing is complete on YouTube servers."""
        if not self.service:
            self.connect()
        try:
            resp = self.service.videos().list(
                part="processingDetails,status,contentDetails",
                id=video_id
            ).execute()
            proj = self.cred_manager.get_active_secret_file().stem if self.cred_manager.get_active_secret_file() else "default"
            quota_tracker.record_action(proj, "videos.list")
            items = resp.get("items", [])
            if items:
                proc = items[0].get("processingDetails", {})
                content = items[0].get("contentDetails", {})
                status = items[0].get("status", {})
                is_ready = proc.get("processingStatus") == "succeeded"
                definition = content.get("definition", "sd")
                logger.info(f"🛡️ [Sentinel] Video {video_id} status: {proc.get('processingStatus')} | Definition: {definition} | Ready: {is_ready}")
                return {
                    "ready": is_ready,
                    "status": proc.get("processingStatus", "unknown"),
                    "definition": definition,
                    "is_hd_or_4k": definition == "hd",
                    "upload_status": status.get("uploadStatus", "")
                }
        except Exception as e:
            logger.error(f"Error checking transcode status for {video_id}: {e}", exc_info=True)
        return {"ready": False, "status": "error", "definition": "sd", "is_hd_or_4k": False}

    # --------------------------------------------------------------------------
    # Video Scanning & History
    # --------------------------------------------------------------------------
    @staticmethod
    def scan_directory(dir_path: str) -> List[Dict[str, Any]]:
        """
        Scans directory for .mp4 files and pairs them with companion _social.txt.
        Checks upload_history.json to indicate if already uploaded.
        """
        p = Path(dir_path)
        if not p.is_dir():
            return []

        history_file = p / "upload_history.json"
        history = {}
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = {}

        video_items = []
        mp4_files = sorted(p.glob("*.mp4"))
        if not mp4_files:
            mp4_files = sorted(p.rglob("*.mp4"))

        for file in mp4_files:
            file_name = file.name
            stem = file.stem
            parent_dir = file.parent
            size_bytes = file.stat().st_size
            size_gb = size_bytes / (1024 * 1024 * 1024)
            size_mb = size_bytes / (1024 * 1024)
            size_str = f"{size_gb:.2f} GB" if size_gb >= 1.0 else f"{size_mb:.1f} MB"

            # Check matching _social.txt or _shorts_social.txt
            social_file = parent_dir / f"{stem}_social.txt"
            clip_idx = None
            m_clip = re.search(r"_short_0*(\d+)", stem)
            if m_clip:
                clip_idx = int(m_clip.group(1))
                prefix = stem[:m_clip.start()]
                candidate_shorts_social = parent_dir / f"{prefix}_shorts_social.txt"
                if candidate_shorts_social.exists():
                    social_file = candidate_shorts_social

            metadata = MetadataParser.parse_social_file(str(social_file), clip_idx=clip_idx)

            # If title is empty in social, default to clean filename
            if not metadata["title"]:
                metadata["title"] = f"{stem} | 4K Audio-Reactive MV"

            is_uploaded = file_name in history
            hist_info = history.get(file_name, {})

            video_items.append({
                "filename": file_name,
                "path": str(file),
                "stem": stem,
                "size_bytes": size_bytes,
                "size_str": size_str,
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": metadata["tags"],
                "raw_hashtags": metadata["raw_hashtags"],
                "track": metadata["track"] or stem,
                "artist": metadata["artist"] or "POHAN",
                "genre": metadata["genre"],
                "bpm": metadata["bpm"],
                "uploaded": is_uploaded,
                "video_id": hist_info.get("video_id", ""),
                "youtube_url": hist_info.get("url", ""),
                "upload_time": hist_info.get("upload_time", "")
            })

        return video_items

    @staticmethod
    def record_upload_history(dir_path: str, filename: str, info: Dict[str, Any]):
        """Persists successful upload record in upload_history.json."""
        p = Path(dir_path)
        history_file = p / "upload_history.json"
        history = {}
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = {}

        history[filename] = info
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    # --------------------------------------------------------------------------
    # Resumable Chunked Video Upload (with Premiere & Quota handling)
    # --------------------------------------------------------------------------
    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        privacy_status: str = "unlisted",
        publish_at: Optional[datetime] = None,
        playlist_id: Optional[str] = None,
        category_id: str = "10",  # 10 = Music
        auto_thumbnail: bool = True,
        auto_comment: bool = True,
        album_nav: Optional[Dict[str, str]] = None,
        progress_cb: Optional[Callable[[int, int, float, float], None]] = None,
        status_cb: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Uploads a video to YouTube with resumable chunked upload.
        - publish_at: if set, privacy_status must be 'private', YouTube will schedule Premiere at that time.
        - auto_thumbnail: extracts 4K non-black high-contrast frame and sets as custom thumbnail.
        - auto_comment: posts initial engagement comment with playlist link.
        - album_nav: dict with prev_title, prev_url, next_title, next_url, playlist_url to chain in description.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = os.path.getsize(video_path)
        self.reset_cancel()
        self.start_sleep_prevention()

        if status_cb:
            status_cb(f"🚀 Preparing upload for '{os.path.basename(video_path)}' ({file_size / (1024**3):.2f} GB)...")

        # YouTube Scheduling Constraint:
        # If publishAt is specified, privacyStatus MUST be set to 'private'
        body_status: Dict[str, Any] = {}
        if publish_at:
            # Ensure UTC timezone
            if publish_at.tzinfo is None:
                # Assume local time, convert to UTC
                local_now = datetime.now()
                utc_now = datetime.now(timezone.utc)
                offset = local_now.astimezone().utcoffset()
                publish_at = publish_at.replace(tzinfo=timezone.utc) - offset

            # Format to ISO 8601: YYYY-MM-DDTHH:MM:SSZ
            iso_publish = publish_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            body_status["privacyStatus"] = "private"
            body_status["publishAt"] = iso_publish
            if status_cb:
                status_cb(f"⏰ Scheduled Premiere set for: {iso_publish} (UTC)")
        else:
            body_status["privacyStatus"] = privacy_status

        body_status["selfDeclaredMadeForKids"] = False
        body_status["embeddable"] = True

        safe_title, overflow = MetadataParser.smart_truncate_title(title, 100)
        final_desc = description
        if overflow:
            final_desc = f"📌 【完整曲目標題 / Full Title】: {title}\n\n" + description
            if status_cb:
                status_cb(f"⚠️ 標題超過 100 字元限制，已自動安全平滑縮短為: '{safe_title}' (完整標題已收錄於說明欄)")

        # Append Chained Navigation Links if provided
        if album_nav:
            nav_lines = ["\n\n======================================================================", "💿 【專輯曲目導覽 / Album Navigation】"]
            if album_nav.get("prev_title"):
                prev_text = f"⏮️ 上一首 (Previous): {album_nav['prev_title']}"
                if album_nav.get("prev_url"):
                    prev_text += f" -> {album_nav['prev_url']}"
                nav_lines.append(prev_text)
            if album_nav.get("next_title"):
                next_text = f"⏭️ 下一首 (Next): {album_nav['next_title']}"
                if album_nav.get("next_url"):
                    next_text += f" -> {album_nav['next_url']}"
                nav_lines.append(next_text)
            if album_nav.get("playlist_url"):
                nav_lines.append(f"📀 完整專輯 4K 清單 (Full Playlist): {album_nav['playlist_url']}")
            nav_lines.append("======================================================================")
            final_desc += "\n".join(nav_lines)

        body = {
            "snippet": {
                "title": safe_title,
                "description": final_desc[:5000],
                "tags": tags[:30],
                "categoryId": category_id
            },
            "status": body_status
        }

        # Attempt upload with quota auto-rotation
        max_retries = max(1, len(self.cred_manager.client_secrets_files))
        for attempt in range(max_retries):
            if self._cancel_requested:
                raise InterruptedError("Upload was cancelled by user.")

            try:
                if not self.service:
                    self.connect()

                media = MediaFileUpload(
                    video_path,
                    mimetype="video/mp4",
                    chunksize=CHUNK_SIZE,
                    resumable=True
                )

                request = self.service.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media
                )

                # Chunked upload loop
                response = None
                start_time = time.time()
                last_time = start_time
                last_bytes = 0

                while response is None:
                    if self._cancel_requested:
                        raise InterruptedError("Upload was cancelled by user.")

                    status, response = request.next_chunk()
                    if status:
                        bytes_uploaded = status.resumable_progress
                        now = time.time()
                        delta_t = now - last_time
                        if delta_t >= 0.5:
                            speed = (bytes_uploaded - last_bytes) / delta_t  # bytes/sec
                            speed_mb = speed / (1024 * 1024)
                            remaining_bytes = file_size - bytes_uploaded
                            eta = remaining_bytes / speed if speed > 0 else 0

                            if progress_cb:
                                progress_cb(bytes_uploaded, file_size, speed_mb, eta)

                            last_time = now
                            last_bytes = bytes_uploaded

                # Upload finished!
                video_id = response.get("id")
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                if status_cb:
                    status_cb(f"🎉 Upload Complete! Video ID: {video_id} -> {video_url}")

                # Optional: Add to Playlist
                if playlist_id and video_id:
                    if status_cb:
                        status_cb(f"📋 Adding video {video_id} to playlist {playlist_id}...")
                    self.add_video_to_playlist(video_id, playlist_id)

                # Optional: Auto-Thumbnail (Beat-Synced 4K Golden Frame)
                thumb_path = None
                if auto_thumbnail and video_id:
                    try:
                        if status_cb:
                            status_cb("🖼️ 正在由 4K 畫面自動抽取最佳視覺高潮影格作為自訂封面...")
                        thumb_path = self.extract_golden_thumbnail(video_path)
                        if thumb_path and os.path.exists(thumb_path):
                            self.set_thumbnail(video_id, thumb_path)
                            if status_cb:
                                status_cb(f"✅ 4K 高畫質黃金封面已成功設定！({os.path.basename(thumb_path)})")
                    except Exception as e:
                        if status_cb:
                            status_cb(f"⚠️ 設定封面時略過: {e}")

                # Optional: Auto-Comment (Engagement & Streaming Links)
                if auto_comment and video_id:
                    try:
                        comment_lines = [
                            f"🎧 感謝收聽《{title}》！",
                            "✨ 4K 音畫互動生成藝術 (Audio-Reactive Generative MV) ✨"
                        ]
                        if playlist_id:
                            comment_lines.append(f"👉 完整專輯 4K 播放清單：https://www.youtube.com/playlist?list={playlist_id}")
                        comment_lines.append("💬 你最喜歡本曲哪一段節拍視覺變化？歡迎在下方留言分享！")
                        self.post_pinned_comment(video_id, "\n\n".join(comment_lines))
                        if status_cb:
                            status_cb("💬 已自動發表官方置頂導流留言！")
                    except Exception as e:
                        if status_cb:
                            status_cb(f"⚠️ 發表留言時略過: {e}")

                result_info = {
                    "video_id": video_id,
                    "url": video_url,
                    "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
                    "title": safe_title,
                    "upload_time": datetime.now().isoformat(),
                    "privacy": body_status["privacyStatus"],
                    "publish_at": body_status.get("publishAt", ""),
                    "playlist_id": playlist_id or ""
                }

                upload_duration = max(0.1, time.time() - start_time)
                avg_speed_mb = (file_size / (1024 * 1024)) / upload_duration
                proj = self.cred_manager.get_active_secret_file().stem if self.cred_manager.get_active_secret_file() else "default"
                q = quota_tracker.record_action(proj, "videos.insert")
                logger.info(
                    f"📊 [Transfer Metrics] File: '{os.path.basename(video_path)}' | Size: {file_size/(1024**3):.2f} GB | "
                    f"Time: {upload_duration:.1f}s | Avg Speed: {avg_speed_mb:.2f} MB/s | "
                    f"Quota: {q['total']}/10000 used on '{proj}' (Remaining: {q['remaining']})"
                )

                # Record in history
                parent_dir = os.path.dirname(os.path.abspath(video_path))
                self.record_upload_history(parent_dir, os.path.basename(video_path), result_info)

                return result_info

            except HttpError as http_err:
                # Detect quotaExceeded
                error_content = str(http_err)
                if "quotaExceeded" in error_content or http_err.resp.status in (403, 429):
                    if status_cb:
                        status_cb(f"⚠️ Project quota exceeded ({http_err.resp.status}). Attempting credential rotation...")
                    rotated = self.cred_manager.rotate_to_next()
                    if rotated:
                        self.service = None  # Reconnect with next credentials
                        if status_cb:
                            status_cb("🔄 Switched to next credential project in pool! Retrying upload...")
                        continue
                    else:
                        raise RuntimeError(
                            "❌ YouTube API daily quota exceeded (10,000 units) and no alternative credentials available. "
                            "You can add client_secrets_2.json to the credentials folder or wait for tomorrow's quota reset."
                        ) from http_err
                else:
                    raise http_err

            finally:
                self.stop_sleep_prevention()

        raise RuntimeError("Failed to upload video after exhausting available credentials.")
