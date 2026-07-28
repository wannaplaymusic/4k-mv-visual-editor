import os
import json
import re
import datetime

workspace_dir = os.path.dirname(os.path.abspath(__file__))

HARMFUL_PATTERNS = [
    (r'\b(window|document|top|parent)\.location\b', '網頁重定向/頁面劫持 (location hijack)'),
    (r'\blocation\.(href|replace|assign|reload)\b', '頁面重定向 (location redirect)'),
    (r'\bwindow\.open\s*\(', '彈出視窗/開啟外部網頁 (window.open)'),
    (r'\bdocument\.cookie\b', '存取用戶 Cookie (document.cookie)'),
    (r'\b(coinhive|cryptonight|coinminer|miner\.start)\b', '加密貨幣挖礦程式碼 (Cryptominer)'),
    (r'\beval\s*\(\s*atob\s*\(', '混淆執行可疑代碼 (eval atob)'),
    (r'\bFunction\s*\(\s*atob\s*\(', '混淆執行可疑代碼 (Function atob)'),
    (r'\bwhile\s*\(\s*(true|1|!0)\s*\)', '無窮死循環 (while true deadlock)'),
    (r'\bfor\s*\(\s*;\s*;\s*\)', '無窮死循環 (for ;; deadlock)'),
]

def strip_comments(code):
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    code = re.sub(r'//.*', '', code)
    return code

save_dir = os.path.join(workspace_dir, "custom_visuals")
all_files = [f for f in os.listdir(save_dir) if f.endswith(".json")]

harmful_found = []
deleted_count = 0

for filename in sorted(all_files):
    filepath = os.path.join(save_dir, filename)
    name = filename[:-5]
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        code = strip_comments(data.get("code", ""))
        custom_html = strip_comments(data.get("custom_html", ""))
        custom_css = data.get("custom_css", "")
        full_content = code + "\n" + custom_html + "\n" + custom_css
        
        reasons = []
        for pattern, desc in HARMFUL_PATTERNS:
            if re.search(pattern, full_content, re.IGNORECASE):
                reasons.append(desc)
        
        if reasons:
            harmful_found.append({
                "name": name,
                "file_path": filepath,
                "reasons": reasons
            })
    except Exception as e:
        harmful_found.append({
            "name": name,
            "file_path": filepath,
            "reasons": [f"JSON 解析損毀: {e}"]
        })

print(f"Total scanned: {len(all_files)}")
print(f"Harmful modules detected: {len(harmful_found)}")

# Execute deletion
for item in harmful_found:
    filepath = item["file_path"]
    name = item["name"]
    reason_str = ", ".join(item["reasons"])
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            thumb_path = os.path.join(save_dir, "thumbnails", f"{name}.jpg")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            deleted_count += 1
            print(f"❌ Deleted harmful module [{name}]: {reason_str}")
        except Exception as del_err:
            print(f"Error deleting {name}: {del_err}")

# Append log to op_import_errors.txt
report_path = os.path.join(workspace_dir, "op_import_errors.txt")
try:
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n" + "="*70 + "\n")
        f.write("Harmful Code Security Scan & Deletion Report (有害程式碼安全掃描與刪除報告)\n")
        f.write(f"Execution Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Evaluated: {len(all_files)}\n")
        f.write(f"Deleted Harmful Count: {deleted_count}\n")
        f.write("======================================================================\n\n")
        for idx, item in enumerate(harmful_found, 1):
            f.write(f"[{idx}] Deleted Harmful Module: {item['name']}\n")
            f.write(f"    Reason: {', '.join(item['reasons'])}\n\n")
        f.write("="*70 + "\n")
except Exception as log_err:
    print(f"Error logging report: {log_err}")

print(f"\nDone! Cleaned {deleted_count} harmful modules.")
