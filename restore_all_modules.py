#!/usr/bin/env python3
"""
restore_all_modules.py
從 op_import_errors.txt 及歷史備份中完整還原所有視覺模組至 custom_visuals/
並自動關聯 scratch/ 中的縮圖資源。
"""

import os
import re
import json
import glob
from PIL import Image

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
THUMBNAILS_DIR = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails")
SCRATCH_DIR = os.path.join(WORKSPACE_DIR, "scratch")
ERRORS_FILE = os.path.join(WORKSPACE_DIR, "op_import_errors.txt")

os.makedirs(CUSTOM_VISUALS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

def parse_module_from_section(s):
    m_title = re.search(r"作品名稱 \(Title\):\s*(.+)", s)
    m_url = re.search(r"作品網址 \(URL\):\s*(.+)", s)
    m_time = re.search(r"產生時間:\s*(.+)", s)
    
    code_start = s.find("```javascript\n")
    code_end = s.find("\n```", code_start + 14) if code_start != -1 else -1
    code = s[code_start+14:code_end] if (code_start != -1 and code_end != -1) else ""
    
    html_start = s.find("```html\n")
    html_end = s.find("\n```", html_start + 8) if html_start != -1 else -1
    custom_html = s[html_start+8:html_end] if (html_start != -1 and html_end != -1) else ""
    
    if not m_title or not code or code.strip() in ("", "N/A"):
        return None
        
    title = m_title.group(1).strip()
    # Sanitize title for filename safety
    safe_title = "".join(c for c in title if c not in '<>:"/\\|?*').strip()
    if not safe_title:
        return None
        
    url = m_url.group(1).strip() if m_url else ""
    date_str = m_time.group(1).strip() if m_time else ""
    
    author = "未知"
    if "@" in url:
        try:
            author_part = url.split("@")[1].split("/")[0]
            if author_part:
                author = author_part
        except:
            pass
            
    module_data = {
        "name": safe_title,
        "display_name": title,
        "author": author,
        "license_mode": "CC BY-SA 3.0",
        "date_added": date_str if date_str else "2026-08-01 00:00:00",
        "url": url,
        "code": code,
        "custom_html": custom_html if custom_html != "N/A" else "",
        "tags": [],
        "frequency": 50,
        "storyboard_weight": 50,
        "post_fx_intensity": 50,
        "used_count": 0,
        "is_starred": False
    }
    return safe_title, module_data

def main():
    print(f"🚀 開始掃描並還原視覺模組庫...")
    
    existing_files = {f[:-5] for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"}
    print(f"📦 目前已存在模組數: {len(existing_files)}")
    
    if not os.path.exists(ERRORS_FILE):
        print(f"❌ 找不到錯誤日誌檔 {ERRORS_FILE}")
        return
        
    with open(ERRORS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
        
    sections = text.split("="*70)
    print(f"📑 讀取日誌區塊數: {len(sections)}")
    
    recovered_map = {}
    for s in sections:
        if "--- [縮圖渲染失敗項目] ---" in s or "--- [OP 模組導入失敗項目] ---" in s:
            res = parse_module_from_section(s)
            if res:
                title, mdata = res
                # Keep newest if duplicate
                recovered_map[title] = mdata
                
    print(f"🔍 解析出有效模組總數: {len(recovered_map)}")
    
    restored_count = 0
    for title, mdata in recovered_map.items():
        json_path = os.path.join(CUSTOM_VISUALS_DIR, f"{title}.json")
        if not os.path.exists(json_path):
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(mdata, f, indent=4, ensure_ascii=False)
                restored_count += 1
            except Exception as e:
                print(f"⚠️ 寫入模組 {title} 失敗: {e}")
                
    print(f"✅ 成功還原了 {restored_count} 個模組 JSON 檔案！")
    
    # 2. 自動關聯/轉換縮圖
    print(f"\n🖼️ 正在同步縮圖資料庫...")
    restored_thumbs = 0
    if os.path.exists(SCRATCH_DIR):
        for png_file in glob.glob(os.path.join(SCRATCH_DIR, "debug_grab_*.png")):
            base = os.path.basename(png_file)
            mod_name = base[len("debug_grab_"):-4]
            dest_jpg = os.path.join(THUMBNAILS_DIR, f"{mod_name}.jpg")
            
            # If module exists and thumbnail doesn't exist yet, convert and save
            mod_json = os.path.join(CUSTOM_VISUALS_DIR, f"{mod_name}.json")
            if os.path.exists(mod_json) and not os.path.exists(dest_jpg):
                try:
                    with Image.open(png_file) as img:
                        img_rgb = img.convert("RGB")
                        w, h = img_rgb.size
                        min_dim = min(w, h)
                        left = (w - min_dim) / 2
                        top = (h - min_dim) / 2
                        right = (w + min_dim) / 2
                        bottom = (h + min_dim) / 2
                        cropped = img_rgb.crop((left, top, right, bottom))
                        resized = cropped.resize((140, 140), Image.Resampling.LANCZOS)
                        resized.save(dest_jpg, "JPEG", quality=90)
                        restored_thumbs += 1
                except Exception as e:
                    pass
                    
    print(f"🎨 自動從暫存提取並修復了 {restored_thumbs} 個模組預覽縮圖！")
    
    final_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
    print(f"\n🎉 還原完成！目前「已收錄模組」總數為: {len(final_files)} 個 (含縮圖: {len(os.listdir(THUMBNAILS_DIR))} 個)")

if __name__ == "__main__":
    main()
