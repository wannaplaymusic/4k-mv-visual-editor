#!/usr/bin/env python3
"""
fetch_missing_thumbnails.py
高效非同步批次補齊 OpenProcessing 視覺模組預覽縮圖工具

特性：
1. 自動掃描 custom_visuals/ 下所有 .json 預設模組
2. 比對 custom_visuals/thumbnails/{name}.jpg 是否存在
3. 支援多執行緒並發 (ThreadPoolExecutor) 從 OpenProcessing 官方端點拉取官方 400x400 高清縮圖
4. 自動以 PIL 轉碼儲存為標準 JPEG 90% 畫質，解決格式相容問題
5. 對於無網址或失效的作品，自動生成暗色系霓虹質感占位卡片，徹底消除綠色預設卡片
"""

import os
import sys
import glob
import json
import re
import io
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
THUMB_DIR = os.path.join(CUSTOM_DIR, "thumbnails")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def generate_fallback_image(dest_path, name):
    """生成暗色微光霓虹占位縮圖，美觀且保證不會出現純黑或綠色突兀占位"""
    try:
        w, h = 300, 300
        img = Image.new("RGB", (w, h), color=(18, 20, 28))
        draw = ImageDraw.Draw(img)
        
        # 繪製外框與內框層次
        draw.rectangle([10, 10, w - 10, h - 10], outline=(45, 55, 75), width=2)
        draw.rectangle([20, 20, w - 20, h - 20], outline=(80, 50, 120), width=1)
        
        # 中心幾何微光
        cx, cy = w // 2, h // 2
        r = 60
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 25, 45), outline=(147, 51, 234), width=3)
        
        inner_r = 30
        draw.polygon([
            (cx, cy - inner_r),
            (cx + inner_r, cy + inner_r),
            (cx - inner_r, cy + inner_r)
        ], fill=(79, 70, 229), outline=(192, 132, 252))
        
        img.save(dest_path, "JPEG", quality=85)
        return True
    except Exception as e:
        return False

def process_single_preset(session, name, json_path, dest_thumb_path):
    """處理單個作品的縮圖下載或生成"""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        generate_fallback_image(dest_thumb_path, name)
        return name, "FALLBACK", "無法讀取 JSON"

    url = data.get("url", "").strip()
    match = re.search(r'/(?:sketch/|@[\w\-]+/)?(\d+)', url)
    if not match:
        generate_fallback_image(dest_thumb_path, name)
        return name, "FALLBACK", "無 OpenProcessing ID"

    sketch_id = match.group(1)
    thumb_url = f"https://openprocessing.org/sketch/{sketch_id}/thumbnail"

    # 最多重試 2 次
    for attempt in range(2):
        try:
            resp = session.get(thumb_url, headers=HEADERS, timeout=7)
            if resp.status_code == 200 and len(resp.content) > 500:
                # 驗證為有效圖檔並轉換為乾淨的 JPEG
                with Image.open(io.BytesIO(resp.content)) as im:
                    im.convert("RGB").save(dest_thumb_path, "JPEG", quality=90)
                return name, "SUCCESS", f"{len(resp.content)} bytes"
            elif resp.status_code == 429:
                time.sleep(1.5)
            elif resp.status_code == 404:
                break
        except requests.exceptions.RequestException:
            time.sleep(0.5)

    # 若下載失敗則生成優質占位圖
    generate_fallback_image(dest_thumb_path, name)
    return name, "FALLBACK", "官方無縮圖或請求超時"

def main():
    os.makedirs(THUMB_DIR, exist_ok=True)
    all_json = glob.glob(os.path.join(CUSTOM_DIR, "*.json"))
    
    tasks = []
    for jpath in all_json:
        name = os.path.splitext(os.path.basename(jpath))[0]
        thumb_path = os.path.join(THUMB_DIR, f"{name}.jpg")
        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) < 500:
            tasks.append((name, jpath, thumb_path))

    total = len(tasks)
    print(f"==================================================")
    print(f"🎨 4K MV 視覺整合編輯器 - 預覽縮圖補齊引擎")
    print(f"==================================================")
    print(f"📦 全庫預設總數: {len(all_json)}")
    print(f"🔍 缺失縮圖待補齊項目: {total}")
    print(f"⚡ 啟動並發下載執行緒池 (Workers: 12)...")
    print(f"--------------------------------------------------")

    if total == 0:
        print("🎉 所有視覺模組均已有專屬預覽縮圖，無需補齊！")
        return

    success_cnt = 0
    fallback_cnt = 0
    start_time = time.time()

    # 每個執行緒獨立 session 提高連線複用效能
    import threading
    thread_local = threading.local()
    def get_session():
        if not hasattr(thread_local, "session"):
            thread_local.session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
            thread_local.session.mount("https://", adapter)
            thread_local.session.mount("http://", adapter)
        return thread_local.session

    def worker(item):
        name, jpath, tpath = item
        sess = get_session()
        return process_single_preset(sess, name, jpath, tpath)

    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(worker, t): t for t in tasks}
        
        processed = 0
        for future in as_completed(futures):
            processed += 1
            name, status, detail = future.result()
            if status == "SUCCESS":
                success_cnt += 1
            else:
                fallback_cnt += 1

            if processed % 20 == 0 or processed == total:
                elapsed = max(0.1, time.time() - start_time)
                speed = processed / elapsed
                percent = (processed / total) * 100
                sys.stdout.write(f"\r🚀 進度: [{processed}/{total}] {percent:.1f}% | 官方縮圖: {success_cnt} | 質感備援: {fallback_cnt} | 速度: {speed:.1f} 張/秒")
                sys.stdout.flush()

    print("\n--------------------------------------------------")
    print(f"✅ 全部縮圖補齊完畢！")
    print(f"  - 官方高解析縮圖成功下載: {success_cnt} 張")
    print(f"  - 生成專屬質感占位縮圖: {fallback_cnt} 張")
    print(f"  - 總耗時: {time.time() - start_time:.2f} 秒")
    print(f"==================================================")

if __name__ == "__main__":
    main()
