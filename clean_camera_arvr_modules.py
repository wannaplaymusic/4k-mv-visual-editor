import os
import sys
import json
import re
import shutil
import datetime
from typing import List, Dict

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "camera_arvr_backup")
REPORT_TXT = os.path.join(WORKSPACE_DIR, "op_import_errors.txt")
REPORT_JSON = os.path.join(WORKSPACE_DIR, "camera_arvr_cleanup_report.json")

# 精準正則模式：過濾攝像頭與 WebXR / AR / VR 相關硬體呼叫
CAMERA_PATTERNS = [
    (r'\bcreateCapture\s*\(', '使用電腦視訊鏡頭 (createCapture)'),
    (r'\bgetUserMedia\s*\(', '存取攝像頭媒體裝置 (getUserMedia)'),
    (r'\b(ml5\s*\.\s*(?:poseNet|bodypix|handpose|faceapi)|clmtrackr|facemesh|faceapi)\b', '人臉/肢體視訊追蹤庫 (Camera ML Trackers)'),
    (r'\b(?:webcam|live_camera|videoCapture)\b', '包含 Webcam/視訊捕獲 關鍵字'),
]

AR_VR_PATTERNS = [
    (r'\b(WebXR|xrSession|VRButton|ARButton|WEBGL_VR|p5\.vr)\b', 'WebXR / VR 沉浸式裝置支援'),
    (r'\b(mindar|artoolkit|a-scene|a-entity)\b', 'AR / A-Frame 擴增實境框架'),
    (r'\brequestSession\s*\(\s*[\'\"](immersive-vr|immersive-ar)[\'\"]', 'VR/AR 沉浸式會話 (WebXR)'),
]

def strip_code_comments_and_stubs(code: str) -> str:
    """ 移除註解與注入的 Mock Stubs 以防防護代碼引發誤判 """
    if not code:
        return ""
    for marker in ["// 1. 免疫 DOM", "// 1. 免疫", "// === INJECTED_STUBS ==="]:
        if marker in code:
            code = code.split(marker)[0]
    return code

def scan_and_clean_modules(dry_run: bool = False, permanent_delete: bool = False):
    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"❌ 找不到目錄: {CUSTOM_VISUALS_DIR}", flush=True)
        return

    all_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
    all_files.sort()

    flagged_modules: List[Dict] = []

    compiled_cam = [(re.compile(p, re.IGNORECASE), d, p) for p, d in CAMERA_PATTERNS]
    compiled_arvr = [(re.compile(p, re.IGNORECASE), d) for p, d in AR_VR_PATTERNS]

    for idx, filename in enumerate(all_files):
        if idx % 300 == 0:
            print(f"  進度: {idx}/{len(all_files)}...", flush=True)
        filepath = os.path.join(CUSTOM_VISUALS_DIR, filename)
        name = filename[:-5]

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        code = strip_code_comments_and_stubs(data.get("code", ""))
        custom_html = strip_code_comments_and_stubs(data.get("custom_html", ""))
        custom_css = data.get("custom_css", "")
        full_content = code + "\n" + custom_html + "\n" + custom_css

        cam_reasons = []
        for reg, desc, raw_pat in compiled_cam:
            if reg.search(full_content):
                # 排除純 P5Capture (螢幕錄影工具) 造成的誤殺
                if "createcapture" in raw_pat.lower() and "p5capture" in full_content.lower() and not ("video" in full_content.lower() or "camera" in full_content.lower() or "webcam" in full_content.lower()):
                    continue
                cam_reasons.append(desc)

        arvr_reasons = []
        for reg, desc in compiled_arvr:
            if reg.search(full_content):
                arvr_reasons.append(desc)

        all_reasons = list(set(cam_reasons + arvr_reasons))
        if all_reasons:
            flagged_modules.append({
                "name": name,
                "filename": filename,
                "file_path": filepath,
                "reasons": all_reasons,
                "url": data.get("url", "https://openprocessing.org"),
                "author": data.get("author", "未知作者")
            })

    print(f"\n📊 掃描結果：", flush=True)
    print(f"  總掃描模組數: {len(all_files)}", flush=True)
    print(f"  不相容鏡頭/AR/VR 模組數: {len(flagged_modules)}", flush=True)

    # 寫入專屬 JSON 診斷報告
    try:
        report_data = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_scanned": len(all_files),
            "flagged_count": len(flagged_modules),
            "action": "dry_run" if dry_run else ("permanent_delete" if permanent_delete else "backup_isolated"),
            "modules": flagged_modules
        }
        with open(REPORT_JSON, "w", encoding="utf-8") as jf:
            json.dump(report_data, jf, indent=2, ensure_ascii=False)
    except Exception as err:
        print(f"寫入 JSON 報告失敗: {err}", flush=True)

    if dry_run:
        print("\n🔎 [Dry-Run 預檢模式] 未執行任何檔案移動或刪除。", flush=True)
        for item in flagged_modules:
            print(f"  - [{item['name']}] -> {', '.join(item['reasons'])}", flush=True)
        return

    processed_count = 0
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(os.path.join(BACKUP_DIR, "thumbnails"), exist_ok=True)

    for item in flagged_modules:
        filepath = item["file_path"]
        name = item["name"]
        filename = item["filename"]
        reasons_str = ", ".join(item["reasons"])

        thumb_name = f"{name}.jpg"
        src_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", thumb_name)

        if permanent_delete:
            # 永久刪除
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass
            if os.path.exists(src_thumb):
                try: os.remove(src_thumb)
                except Exception: pass
            print(f"🗑️ [已永久刪除] [{name}]: {reasons_str}", flush=True)
        else:
            # 安全移動至備份區
            dest_json = os.path.join(BACKUP_DIR, filename)
            dest_thumb = os.path.join(BACKUP_DIR, "thumbnails", thumb_name)
            try:
                if os.path.exists(filepath):
                    shutil.move(filepath, dest_json)
                if os.path.exists(src_thumb):
                    shutil.move(src_thumb, dest_thumb)
                print(f"📦 [已安全隔離備份] [{name}]: {reasons_str}", flush=True)
            except Exception as e:
                print(f"⚠️ 移動 [{name}] 失敗: {e}", flush=True)

        processed_count += 1

    # 追加至全域日誌 op_import_errors.txt
    try:
        with open(REPORT_TXT, "a", encoding="utf-8") as f:
            f.write("\n" + "="*70 + "\n")
            f.write("Camera & AR/VR Modules Cleanup Report (電腦攝像頭與 AR/VR 模組清理報告)\n")
            f.write(f"Execution Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Evaluated: {len(all_files)}\n")
            f.write(f"Processed Modules Count: {processed_count}\n")
            f.write(f"Action: {'Permanent Delete' if permanent_delete else 'Moved to custom_visuals/camera_arvr_backup/'}\n")
            f.write("======================================================================\n\n")
            for idx, item in enumerate(flagged_modules, 1):
                f.write(f"[{idx}] Module: {item['name']} (Author: {item['author']})\n")
                f.write(f"    URL: {item['url']}\n")
                f.write(f"    Reason: {', '.join(item['reasons'])}\n\n")
            f.write("="*70 + "\n")
    except Exception as log_err:
        print(f"寫入日誌失敗: {log_err}")

    action_label = "永久刪除" if permanent_delete else "安全隔離至 camera_arvr_backup/"
    print(f"\n🎉 處理完成！共計 {processed_count} 個不相容模組已執行 [{action_label}]。")

if __name__ == "__main__":
    is_dry_run = "--dry-run" in sys.argv
    is_permanent = "--force-delete" in sys.argv
    scan_and_clean_modules(dry_run=is_dry_run, permanent_delete=is_permanent)
