import os
import json
import re
import datetime

workspace_dir = os.path.dirname(os.path.abspath(__file__))

CAMERA_PATTERNS = [
    (r'\bcreateCapture\s*\(', '使用電腦攝像頭 (createCapture)'),
    (r'\bnavigator\.(mediaDevices\.getUserMedia|getUserMedia)\b', '存取攝像頭媒體裝置 (getUserMedia)'),
    (r'\b(clmtrackr|facemesh|handpose|poseNet|bodypix|faceapi)\b', '人臉/肢體視訊追蹤 (Camera ML Trackers)'),
    (r'\bwebcam\b', '包含 Webcam 關鍵字'),
]

AR_VR_PATTERNS = [
    (r'\b(WebXR|xrSession|VRButton|ARButton|WEBGL_VR|p5\.vr)\b', 'WebXR / VR 裝置支援'),
    (r'\b(mindar|artoolkit|a-scene|a-entity)\b', 'AR / A-Frame 擴增實境套件'),
    (r'\brequestSession\s*\(\s*[\'\"](immersive-vr|immersive-ar)[\'\"]', 'VR/AR 沉浸式會話 (WebXR)'),
]

def strip_comments(code):
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    code = re.sub(r'//.*', '', code)
    return code

save_dir = os.path.join(workspace_dir, "custom_visuals")
all_files = [f for f in os.listdir(save_dir) if f.endswith(".json")]

camera_modules = []
arvr_modules = []
deleted_list = []

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
        
        cam_reasons = []
        for pattern, desc in CAMERA_PATTERNS:
            if re.search(pattern, full_content, re.IGNORECASE):
                cam_reasons.append(desc)
        
        arvr_reasons = []
        for pattern, desc in AR_VR_PATTERNS:
            if re.search(pattern, full_content, re.IGNORECASE):
                arvr_reasons.append(desc)
                
        all_reasons = cam_reasons + arvr_reasons
        if all_reasons:
            deleted_list.append({
                "name": name,
                "filename": filename,
                "file_path": filepath,
                "reasons": all_reasons,
                "is_cam": bool(cam_reasons),
                "is_arvr": bool(arvr_reasons)
            })
    except Exception as e:
        pass

print(f"Total scanned: {len(all_files)}")
print(f"Target modules to delete (Camera / AR / VR): {len(deleted_list)}")

deleted_count = 0
for item in deleted_list:
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
            print(f"❌ Deleted [{name}]: {reason_str}")
        except Exception as del_err:
            print(f"Error deleting {name}: {del_err}")

# Append log to op_import_errors.txt
report_path = os.path.join(workspace_dir, "op_import_errors.txt")
try:
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n" + "="*70 + "\n")
        f.write("Camera & AR/VR Modules Cleanup Report (電腦攝像頭與 AR/VR 模組清理報告)\n")
        f.write(f"Execution Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Evaluated: {len(all_files)}\n")
        f.write(f"Deleted Modules Count: {deleted_count}\n")
        f.write("======================================================================\n\n")
        for idx, item in enumerate(deleted_list, 1):
            f.write(f"[{idx}] Deleted Module: {item['name']}\n")
            f.write(f"    Reason: {', '.join(item['reasons'])}\n\n")
        f.write("="*70 + "\n")
except Exception as log_err:
    print(f"Error logging report: {log_err}")

print(f"\nDone! Cleaned {deleted_count} Camera / AR / VR modules.")
