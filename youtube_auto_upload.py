#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube Auto-Upload CLI & Batch Processor
=========================================
Usage examples:
  python youtube_auto_upload.py
  python youtube_auto_upload.py "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Delay Trail Hypnosis"
  python youtube_auto_upload.py --playlist "Techno 2026-2: Delay Trail Hypnosis" --premiere "2026-09-08 20:00" --interval-days 1
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from youtube_uploader_engine import (
    YouTubeUploaderEngine,
    CredentialPoolManager,
    GOOGLE_API_AVAILABLE
)


def main():
    parser = argparse.ArgumentParser(description="YouTube 4K Auto-Uploader CLI")
    parser.add_argument(
        "directory",
        nargs="?",
        default="/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Delay Trail Hypnosis",
        help="Folder containing .mp4 and companion _social.txt files"
    )
    parser.add_argument("--playlist", default=None, help="Name of new or existing playlist to add videos to")
    parser.add_argument("--playlist-privacy", choices=["public", "unlisted", "private"], default="public", help="Playlist privacy")
    parser.add_argument("--premiere", default=None, help="Start Premiere datetime (YYYY-MM-DD HH:MM)")
    parser.add_argument("--interval-hours", type=float, default=None, help="Interval between premiere releases in hours (e.g. 12 for 2/day, 4 for 4/day)")
    parser.add_argument("--interval-days", type=float, default=None, help="Interval between premiere releases in days (legacy, e.g. 1.0)")
    parser.add_argument("--privacy", choices=["unlisted", "public", "private"], default="unlisted", help="Video privacy status (if not Premiere)")
    parser.add_argument("--dry-run", action="store_true", help="Scan and show queue without actually uploading")

    args = parser.parse_args()

    dir_path = os.path.abspath(args.directory)
    if not os.path.isdir(dir_path):
        print(f"❌ Error: Directory does not exist: {dir_path}")
        sys.exit(1)

    print("=" * 70)
    print("📤 YouTube 4K Auto-Uploader CLI")
    print(f"📁 Target Directory: {dir_path}")
    print("=" * 70)

    # 1. Scan directory
    items = YouTubeUploaderEngine.scan_directory(dir_path)
    if not items:
        print("⚠️ No .mp4 files found in the directory.")
        sys.exit(0)

    print(f"Found {len(items)} video file(s):")
    total_bytes = sum(it["size_bytes"] for it in items)
    print(f"Total size: {total_bytes / (1024**3):.2f} GB\n")

    # Premiere start time
    start_dt = None
    if args.premiere:
        try:
            start_dt = datetime.strptime(args.premiere, "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"❌ Error: Invalid datetime format '{args.premiere}', please use 'YYYY-MM-DD HH:MM'")
            sys.exit(1)

    # Print Table
    print(f"{'#':<3} | {'File Name':<30} | {'Size':<9} | {'Status':<10} | {'Premiere / Schedule'}")
    print("-" * 85)

    # Interval hours calculation (default to 12.0 hours if not specified)
    step_hours = 12.0
    if args.interval_hours is not None:
        step_hours = args.interval_hours
    elif args.interval_days is not None:
        step_hours = args.interval_days * 24.0

    pending_items = []
    for idx, it in enumerate(items):
        sched_str = "Immediate"
        if start_dt:
            item_dt = start_dt + timedelta(hours=step_hours * idx)
            sched_str = f"⏰ {item_dt.strftime('%Y-%m-%d %H:%M')}"

        status_str = "Uploaded" if it["uploaded"] else "Pending"
        print(f"{idx+1:<3} | {it['filename'][:29]:<30} | {it['size_str']:<9} | {status_str:<10} | {sched_str}")
        if not it["uploaded"]:
            pending_items.append((idx, it, item_dt if start_dt else None))

    print("-" * 85)
    print(f"Pending to upload: {len(pending_items)} / {len(items)}\n")

    if args.dry_run:
        print("ℹ️ Dry-run completed. No files were uploaded.")
        return

    if not pending_items:
        print("🎉 All videos in this folder have already been uploaded!")
        return

    if not GOOGLE_API_AVAILABLE:
        print("❌ Error: google-api-python-client is not installed in current environment.")
        print("Run: pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    engine = YouTubeUploaderEngine()
    if not engine.cred_manager.has_credentials():
        print("❌ Error: No client_secrets.json found!")
        print("Please follow instructions in YOUTUBE_API_SETUP_GUIDE.md and put client_secrets.json in youtube_credentials/.")
        sys.exit(1)

    # Prompt confirmation if interactive
    if sys.stdin.isatty():
        confirm = input(f"Ready to upload {len(pending_items)} video(s)? (y/N): ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    # Initialize YouTube connection
    print("\nConnecting to YouTube API...")
    engine.connect()
    ch_info = engine.get_channel_info()
    print(f"📺 Authenticated Channel: 【 {ch_info['title']} 】({ch_info.get('custom_url', 'No handle')}) [ID: {ch_info.get('id', '')}]")

    # Create playlist if requested
    playlist_id = None
    if args.playlist:
        print(f"Creating/getting playlist '{args.playlist}'...")
        # Check existing first
        existing_pls = engine.list_playlists()
        for pl in existing_pls:
            if pl["title"].strip().lower() == args.playlist.strip().lower():
                playlist_id = pl["id"]
                print(f"Found existing playlist: '{pl['title']}' (ID: {playlist_id})")
                break

        if not playlist_id:
            playlist_id = engine.create_playlist(
                title=args.playlist,
                description=f"Auto-generated playlist for {os.path.basename(dir_path)}",
                privacy=args.playlist_privacy
            )

    # Begin batch upload
    for num, (orig_idx, it, sched_time) in enumerate(pending_items, 1):
        print(f"\n=======================================================")
        print(f"[{num}/{len(pending_items)}] Uploading: {it['filename']} ({it['size_str']})")
        print(f"Title: {it['title']}")
        if sched_time:
            print(f"Scheduled Premiere: {sched_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"=======================================================")

        def on_prog(bytes_done, total_b, speed_mb, eta_s):
            pct = int((bytes_done / total_b) * 100) if total_b > 0 else 0
            eta_m = int(eta_s // 60)
            eta_sec = int(eta_s % 60)
            sys.stdout.write(
                f"\r  Progress: {pct}% ({bytes_done/(1024**2):.1f}/{total_b/(1024**2):.1f} MB) | "
                f"Speed: {speed_mb:.2f} MB/s | ETA: {eta_m}m{eta_sec}s   "
            )
            sys.stdout.flush()

        def on_stat(msg):
            print(f"\n  [Status] {msg}")

        try:
            res = engine.upload_video(
                video_path=it["path"],
                title=it["title"],
                description=it["description"],
                tags=it["tags"],
                privacy_status=args.privacy,
                publish_at=sched_time,
                playlist_id=playlist_id,
                progress_cb=on_prog,
                status_cb=on_stat
            )
            print(f"\n  ✅ Successfully uploaded: {it['filename']}")
            print(f"  🔗 Video URL: {res['url']}")

        except Exception as e:
            print(f"\n  ❌ Failed to upload {it['filename']}: {e}")
            if "quota" in str(e).lower():
                print("Daily quota reached! Progress has been recorded in upload_history.json. Rerun tomorrow to resume!")
                break

    print("\n🎉 Batch upload job finished.")


if __name__ == "__main__":
    main()
