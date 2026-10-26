#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Direct Batch Rescheduler for Scheduled Long-form Videos
======================================================
- Target: 125 scheduled regular videos
- Start Date/Time: 2026-09-27 20:00 (Local time)
- Interval: Every 2 days (48 hours) at 20:00
- Engine: YouTubeUploaderEngine with multi-credential quota pool
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/Users/unclerm/Vibe Coding/4K MV Visual Integration Editor")
from youtube_uploader_engine import YouTubeUploaderEngine
from youtube_logger import logger, quota_tracker


def run():
    print("=" * 65)
    print("🚀 開始執行排程長影片批次調整")
    print("📌 起始時間: 2026-09-27 20:00 (晚間八點)")
    print("⏰ 發布間隔: 每 2 天 (48 小時) 一部")
    print("=" * 65)

    engine = YouTubeUploaderEngine()
    channel = engine.get_channel_info()
    print(f"📺 當前授權頻道: 【 {channel.get('title')} 】 (ID: {channel.get('id')})\n")

    # Step 1: Fetch all scheduled regular long-form videos
    print("📥 正在從 YouTube API 讀取所有已排程長影片清單...")
    videos = engine.get_channel_videos(filter_mode="only_scheduled", video_type="regular", max_count=200)

    if not videos:
        print("❌ 未在頻道中找到任何已排程長影片！")
        return

    # Sort chronologically by original publish_at so earlier scheduled videos come first
    def get_orig_time(v):
        p_str = v.get("publish_at")
        if p_str:
            try:
                return datetime.fromisoformat(p_str.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
            except Exception:
                pass
        return datetime.max

    videos.sort(key=get_orig_time)
    total_videos = len(videos)
    print(f"✅ 成功載入並按先後順序排列共 {total_videos} 部已排程長影片。\n")

    # Step 2: Calculate target dates
    start_dt = datetime(2026, 9, 27, 20, 0, 0)
    schedule_plan = []
    for idx, v in enumerate(videos):
        new_dt = start_dt + timedelta(days=idx * 2)
        orig_dt = get_orig_time(v)
        schedule_plan.append({
            "idx": idx + 1,
            "id": v["id"],
            "title": v.get("title", ""),
            "duration": v.get("duration_str", ""),
            "orig_dt": orig_dt,
            "new_dt": new_dt
        })

    # Preview first 3 and last 3
    print("📋 排程預覽 (部分展示):")
    for item in schedule_plan[:3]:
        orig_s = item["orig_dt"].strftime("%Y-%m-%d %H:%M") if item["orig_dt"] != datetime.max else "無"
        new_s = item["new_dt"].strftime("%Y-%m-%d %H:%M")
        print(f"  [{item['idx']:03d}/{total_videos}] 《{item['title'][:30]}》\n        原定: {orig_s} -> 新排程: {new_s}")
    print("  ...")
    for item in schedule_plan[-3:]:
        orig_s = item["orig_dt"].strftime("%Y-%m-%d %H:%M") if item["orig_dt"] != datetime.max else "無"
        new_s = item["new_dt"].strftime("%Y-%m-%d %H:%M")
        print(f"  [{item['idx']:03d}/{total_videos}] 《{item['title'][:30]}》\n        原定: {orig_s} -> 新排程: {new_s}")

    print("\n" + "=" * 65)
    print(f"⚡ 即將開始對 {total_videos} 部影片逐一更新 publishAt...")
    print("=" * 65 + "\n")

    success_count = 0
    fail_count = 0
    results = []

    for item in schedule_plan:
        v_id = item["id"]
        v_title = item["title"]
        new_dt = item["new_dt"]
        new_s = new_dt.strftime("%Y-%m-%d %H:%M")

        print(f"[{item['idx']:03d}/{total_videos}] 正在更新: 《{v_title[:28]}》 (ID: {v_id}) -> {new_s} ...", end=" ", flush=True)

        max_attempts = 2
        is_done = False
        err_msg = ""

        for attempt in range(max_attempts):
            try:
                res = engine.update_video_schedule(
                    video_id=v_id,
                    publish_at=new_dt,
                    privacy_status="private"
                )
                is_done = True
                break
            except Exception as e:
                err_msg = str(e)
                if "quota" in err_msg.lower():
                    print("⚠️ 配額達到上限，嘗試輪換金鑰池...", end=" ", flush=True)
                    if engine.cred_manager.rotate_to_next():
                        engine.service = None
                        continue
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue

        if is_done:
            success_count += 1
            print("✅ 成功！")
            results.append({"id": v_id, "title": v_title, "new_dt": new_s, "status": "SUCCESS"})
        else:
            fail_count += 1
            print(f"❌ 失敗: {err_msg}")
            results.append({"id": v_id, "title": v_title, "new_dt": new_s, "status": f"FAILED: {err_msg}"})

        # Polite brief delay to prevent burst rate limiting
        time.sleep(0.3)

    print("\n" + "=" * 65)
    print(f"🎉 批次排程更新完成！")
    print(f"   總數: {total_videos} 部 | ✅ 成功: {success_count} 部 | ❌ 失敗: {fail_count} 部")
    print(f"   排程時間範圍: {schedule_plan[0]['new_dt'].strftime('%Y-%m-%d %H:%M')} ~ {schedule_plan[-1]['new_dt'].strftime('%Y-%m-%d %H:%M')}")
    print("=" * 65)


if __name__ == "__main__":
    run()
