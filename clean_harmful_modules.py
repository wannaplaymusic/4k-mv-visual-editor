import os
import sys
import json
import re
import shutil
import datetime
from typing import List, Dict, Tuple

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
QUARANTINE_DIR = os.path.join(CUSTOM_VISUALS_DIR, "harmful_quarantine")
REPORT_TXT = os.path.join(WORKSPACE_DIR, "op_import_errors.txt")
REPORT_JSON = os.path.join(WORKSPACE_DIR, "harmful_security_report.json")

# 精準惡意特徵正則規則庫 (Regular Expression Security Ruleset)
HARMFUL_PATTERNS: List[Tuple[str, str]] = [
    # 1. 頁面劫持與重定向 (Location Hijacking)
    (r'(?<![\w\.])(?:window|document|top|parent)\.location\s*(?:=|\.href|\.replace|\.assign)', '網頁主動重定向/頁面劫持 (location hijack)'),
    (r'(?<![\w\.])location\.(?:href|replace|assign)\s*=', '未限定全域之頁面重定向 (location.href redirect)'),
    
    # 2. 外部彈窗與廣告劫持 (Popup & Phishing)
    (r'(?<![\w\.])(?:window\.)?open\s*\(\s*[\'"`]https?://', '彈出新分頁/開啟外部廣告網頁 (window.open)'),
    
    # 3. 隱私與敏感資料竊取 (Credential & Storage Scraping)
    (r'(?<![\w\.])document\.cookie\b', '嘗試讀寫用戶 Cookie (document.cookie)'),
    (r'(?<![\w\.])(?:localStorage|sessionStorage)\.(?:getItem|setItem|removeItem|clear)\b', '存取本機儲存空間 (localStorage/sessionStorage)'),
    
    # 4. 加密貨幣挖礦特徵 (Cryptojacking)
    (r'\b(?:coinhive|cryptonight|coinminer|miner\.start|CoinHive|deepminer)\b', '加密貨幣挖礦程式碼 (Cryptominer)'),
    
    # 5. 可疑混淆與動態代碼執行 (Obfuscated Code Execution)
    (r'\beval\s*\(\s*(?:atob|unescape|decodeURIComponent)\s*\(', 'Base64 混淆動態代碼執行 (eval atob)'),
    (r'\bFunction\s*\(\s*(?:atob|unescape)\s*\(', '動態建構子混淆代碼 (Function atob)'),
    (r'\bdocument\.write\s*\(\s*unescape\s*\(', '未過濾動態寫入 (document.write unescape)'),
    
    # 6. 無窮死鎖 (Deadlock & Infinite Hang)
    (r'\bwhile\s*\(\s*(?:true|1|!0)\s*\)\s*\{(?![^}]*\bbreak\b)', '無跳出條件之無窮死循環 (while true deadlock)'),
    (r'\bfor\s*\(\s*;\s*;\s*\)\s*\{(?![^}]*\bbreak\b)', '無跳出條件之無窮 for 死循環 (for ;; deadlock)'),
    
    # 7. 隱蔽資料外傳與外連通道 (Exfiltration)
    (r'\bnew\s+WebSocket\s*\(\s*[\'"`]wss?://(?!(?:localhost|127\.0\.0\.1))', '外連 WebSocket 未授權通訊通道'),
    (r'\bnavigator\.sendBeacon\s*\(', '背景非同步敏感資料外傳 (navigator.sendBeacon)'),
]

def strip_code_comments(code: str) -> str:
    """ 移除註解文字以防止單純提及字串引發誤判 """
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    code = re.sub(r'//.*', '', code)
    return code

def run_security_scan(dry_run: bool = False, permanent_delete: bool = False):
    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"❌ 找不到目錄: {CUSTOM_VISUALS_DIR}", flush=True)
        return

    all_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
    all_files.sort()

    flagged_modules: List[Dict] = []
    print(f"🛡️ 開始對 {len(all_files)} 個視覺模組進行惡意代碼與安全沙盒掃描...", flush=True)

    for filename in all_files:
        filepath = os.path.join(CUSTOM_VISUALS_DIR, filename)
        name = filename[:-5]

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            flagged_modules.append({
                "name": name,
                "filename": filename,
                "file_path": filepath,
                "reasons": [f"JSON 檔案損毀無法解析: {e}"],
                "url": "N/A",
                "author": "N/A"
            })
            continue

        code = strip_code_comments(data.get("code", ""))
        custom_html = strip_code_comments(data.get("custom_html", ""))
        custom_css = data.get("custom_css", "")
        full_content = f"{code}\n{custom_html}\n{custom_css}"

        detected_reasons = []
        for pattern, desc in HARMFUL_PATTERNS:
            if re.search(pattern, full_content, re.IGNORECASE):
                detected_reasons.append(desc)

        if detected_reasons:
            flagged_modules.append({
                "name": name,
                "filename": filename,
                "file_path": filepath,
                "reasons": list(set(detected_reasons)),
                "url": data.get("url", "https://openprocessing.org"),
                "author": data.get("author", "未知作者")
            })

    total_flagged = len(flagged_modules)
    print(f"\n📊 安全掃描摘要：", flush=True)
    print(f"  總掃描模組數: {len(all_files)}", flush=True)
    print(f"  高風險/有害模組數: {total_flagged}", flush=True)

    if dry_run:
        print("\n🔎 [Dry-Run 預檢模式] 未執行任何檔案移動或刪除。", flush=True)
        for item in flagged_modules:
            print(f"  - ⚠️ [{item['name']}] -> {', '.join(item['reasons'])}", flush=True)
        return

    processed_count = 0
    if not permanent_delete:
        os.makedirs(QUARANTINE_DIR, exist_ok=True)
        os.makedirs(os.path.join(QUARANTINE_DIR, "thumbnails"), exist_ok=True)

    for item in flagged_modules:
        filepath = item["file_path"]
        name = item["name"]
        filename = item["filename"]
        reasons_str = ", ".join(item["reasons"])

        thumb_name = f"{name}.jpg"
        src_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", thumb_name)

        if permanent_delete:
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass
            if os.path.exists(src_thumb):
                try: os.remove(src_thumb)
                except Exception: pass
            print(f"🗑️ [永久物理刪除] [{name}]: {reasons_str}", flush=True)
        else:
            dest_json = os.path.join(QUARANTINE_DIR, filename)
            dest_thumb = os.path.join(QUARANTINE_DIR, "thumbnails", thumb_name)
            try:
                if os.path.exists(filepath):
                    shutil.move(filepath, dest_json)
                if os.path.exists(src_thumb):
                    shutil.move(src_thumb, dest_thumb)
                print(f"☣️ [已安全隔離至 quarantine] [{name}]: {reasons_str}", flush=True)
            except Exception as e:
                print(f"⚠️ 隔離模組 [{name}] 時失敗: {e}", flush=True)

        processed_count += 1

    # 寫入 JSON 安全掃描報告
    try:
        report_data = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_scanned": len(all_files),
            "harmful_count": total_flagged,
            "action": "permanent_delete" if permanent_delete else "quarantine_isolated",
            "modules": flagged_modules
        }
        with open(REPORT_JSON, "w", encoding="utf-8") as jf:
            json.dump(report_data, jf, indent=2, ensure_ascii=False)
    except Exception as err:
        print(f"寫入 JSON 報告失敗: {err}", flush=True)

    # 追加至全域診斷日誌 op_import_errors.txt
    try:
        with open(REPORT_TXT, "a", encoding="utf-8") as f:
            f.write("\n" + "="*70 + "\n")
            f.write("Harmful Code Security Scan & Isolation Report (有害程式碼安全掃描與隔離報告)\n")
            f.write(f"Execution Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Evaluated: {len(all_files)}\n")
            f.write(f"Harmful Modules Count: {processed_count}\n")
            f.write(f"Action Taken: {'Permanent Delete' if permanent_delete else 'Moved to custom_visuals/harmful_quarantine/'}\n")
            f.write("======================================================================\n\n")
            for idx, item in enumerate(flagged_modules, 1):
                f.write(f"[{idx}] Module: {item['name']} (Author: {item['author']})\n")
                f.write(f"    URL: {item['url']}\n")
                f.write(f"    Reason: {', '.join(item['reasons'])}\n\n")
            f.write("="*70 + "\n")
    except Exception as log_err:
        print(f"寫入日誌失敗: {log_err}", flush=True)

    action_label = "永久刪除" if permanent_delete else "安全隔離至 harmful_quarantine/"
    print(f"\n🎉 安全清理完成！共計 {processed_count} 個高風險模組已執行 [{action_label}]。", flush=True)

if __name__ == "__main__":
    is_dry_run = "--dry-run" in sys.argv
    is_permanent = "--force-delete" in sys.argv
    run_security_scan(dry_run=is_dry_run, permanent_delete=is_permanent)
