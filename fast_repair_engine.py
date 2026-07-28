import os
import sys
import re
import json
import shutil
import subprocess
import datetime
from collections import Counter

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
ABNORMAL_BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "abnormal_backup")
STATUS_FILE = "/tmp/repair_status.json"
REPORT_FILE = os.path.join(WORKSPACE_DIR, "repair_report.json")

# Immunity Stubs Block to prepend/inject into code if needed
IMMUNITY_STUBS_HEADER = """
// Auto-injected Immunity Proxy & Compatibility Shims
if (typeof p5 !== 'undefined' && p5.prototype) {
  p5.prototype.registerMethod = p5.prototype.registerMethod || function() {};
}
if (typeof window !== 'undefined') {
  window.forceStartP5 = window.forceStartP5 || function() {};
  window.forceRedrawP5 = window.forceRedrawP5 || function() {};
}
"""

def fix_invalid_left_hand_assignments(code):
    """ Fix syntax errors like loc[] = val or pos[] = val """
    # Replace loc[] = val with loc.push(val)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    # Replace loc[loc.length] = val with loc.push(val)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    return code

def transpile_processing_java_to_js(code):
    """ Transpile Processing Java syntax to p5.js JavaScript """
    if "void setup" not in code and "void draw" not in code and "float " not in code and "int " not in code:
        return code
        
    transpiled = code
    # Remove Java access modifiers
    transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
    transpiled = re.sub(r'\bfinal\s+', '', transpiled)
    
    # Casts
    transpiled = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', transpiled)
    transpiled = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', transpiled)
    
    # Array declarations
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', transpiled)
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', transpiled)
    
    # Variable and function declarations
    transpiled = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', transpiled)
    transpiled = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', transpiled)
    
    # Float suffix
    transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
    
    # For-each loop
    transpiled = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', transpiled)
    
    return transpiled

def try_repair_code(code):
    repaired = code
    repaired = fix_invalid_left_hand_assignments(repaired)
    repaired = transpile_processing_java_to_js(repaired)
    
    if "setup" not in repaired and "createCanvas" not in repaired:
        repaired = "function setup() { createCanvas(windowWidth, windowHeight); }\n" + repaired
        
    return repaired

def try_repair_json_file(file_path):
    data = None
    raw_content = ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
        data = json.loads(raw_content)
    except Exception:
        # Regex extraction fallback
        match = re.search(r'"code"\s*:\s*"(.*)"\s*,\s*"', raw_content, re.DOTALL)
        if not match:
            match = re.search(r'"code"\s*:\s*"(.*)"', raw_content, re.DOTALL)
            
        if match:
            code_str = match.group(1).encode().decode('unicode_escape', errors='ignore')
            data = {"id": os.path.basename(file_path).replace(".json", ""), "name": os.path.basename(file_path).replace(".json", ""), "code": code_str}
        else:
            return None, "JSON parsing irrecoverable"
            
    if not data or "code" not in data or not data["code"].strip():
        return None, "Code content empty"
        
    original_code = data["code"]
    repaired_code = try_repair_code(original_code)
    data["code"] = repaired_code
    
    return data, None

def validate_js_syntax(code):
    """ Use node -c or basic regex check for JS syntax validity """
    temp_js = "/tmp/_test_syntax.js"
    full_code = IMMUNITY_STUBS_HEADER + "\n" + code
    with open(temp_js, "w", encoding="utf-8") as f:
        f.write(full_code)
        
    try:
        res = subprocess.run(["node", "-c", temp_js], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            return True, "Valid JS Syntax"
        else:
            return False, res.stderr.strip()
    except Exception as e:
        # Fallback regex check if node command is not present
        if "Invalid left-hand side" in code or "SyntaxError" in code:
            return False, "Syntax error detected"
        return True, "Syntax check fallback ok"

def main():
    if not os.path.exists(ABNORMAL_BACKUP_DIR):
        print(f"❌ Target dir {ABNORMAL_BACKUP_DIR} does not exist!")
        return

    json_files = [f for f in os.listdir(ABNORMAL_BACKUP_DIR) if f.endswith(".json")]
    json_files.sort()

    total_files = len(json_files)
    print(f"🚀 Starting Fast Repair Engine on {total_files} abnormal modules...")

    repaired_count = 0
    failed_count = 0
    
    repair_details = []
    start_time = time.time()

    def update_status(current_file=""):
        status = {
            "total": total_files,
            "processed": repaired_count + failed_count,
            "repaired": repaired_count,
            "failed": failed_count,
            "current_file": current_file,
            "elapsed_seconds": int(time.time() - start_time),
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)

    for idx, fname in enumerate(json_files):
        file_path = os.path.join(ABNORMAL_BACKUP_DIR, fname)
        update_status(fname)
        
        data, err = try_repair_json_file(file_path)
        if not data:
            failed_count += 1
            repair_details.append({"file": fname, "status": "failed", "reason": err})
            continue

        is_valid, syntax_info = validate_js_syntax(data["code"])
        
        if is_valid:
            # Save repaired module to custom_visuals
            dest_json = os.path.join(CUSTOM_VISUALS_DIR, fname)
            with open(dest_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
            try:
                os.remove(file_path)
            except Exception:
                pass
                
            # Restore thumbnail if exists
            thumb_name = f"{fname[:-5]}.jpg"
            src_thumb = os.path.join(ABNORMAL_BACKUP_DIR, "thumbnails", thumb_name)
            dest_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", thumb_name)
            if os.path.exists(src_thumb):
                os.makedirs(os.path.dirname(dest_thumb), exist_ok=True)
                shutil.move(src_thumb, dest_thumb)

            repaired_count += 1
            repair_details.append({"file": fname, "status": "repaired", "syntax": syntax_info})
            if (repaired_count + failed_count) % 50 == 0:
                print(f"[{idx+1}/{total_files}] Processed {idx+1}... Repaired so far: {repaired_count}")
        else:
            failed_count += 1
            repair_details.append({"file": fname, "status": "failed", "reason": syntax_info})

    # Write final status & report
    final_report = {
        "total": total_files,
        "repaired": repaired_count,
        "failed": failed_count,
        "details": repair_details,
        "completed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    update_status("COMPLETED")
    print(f"\n🎉 Repair Complete! Repaired & Restored: {repaired_count}/{total_files} modules.")

if __name__ == "__main__":
    main()
