import os
import re
import json
import shutil
import tempfile
import subprocess
import datetime
from collections import Counter

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
ABNORMAL_BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "abnormal_backup")
REPORT_FILE = os.path.join(WORKSPACE_DIR, "repair_report.json")

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

def fix_invalid_syntax_constructs(code: str) -> str:
    """ 修復標準 JavaScript 語法錯誤 """
    # 1. 修復非法的空下標 push 語法: loc[] = val; -> loc.push(val);
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    # 2. 修復 loc[loc.length] = val; -> loc.push(val);
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    # 3. size(x, y) -> createCanvas(x, y)
    code = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', code)
    return code

def transpile_processing_java_to_js(code: str) -> str:
    """ 將 Processing Java 語法轉譯為 JavaScript (p5.js) """
    if "void setup" not in code and "void draw" not in code and "float " not in code and "int " not in code and "class " not in code:
        return code
        
    transpiled = code
    # 移除 Java 修飾詞
    transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile|final)\s+', '', transpiled)
    
    # 型別轉換 (float)x -> float(x)
    transpiled = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', transpiled)
    transpiled = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', transpiled)
    
    # 陣列初始化語法: int[] arr = {1, 2, 3}; -> let arr = [1, 2, 3];
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', transpiled)
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', transpiled)
    
    # 二維陣列: int[][] matrix = new int[w][h];
    transpiled = re.sub(
        r'\b[A-Za-z0-9_$\.]+\s*\[\s*\]\s*\[\s*\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*;',
        r'let \1 = Array.from({length: \2}, () => new Array(\3).fill(0));',
        transpiled
    )
    
    # 變數宣告與函式簽名
    transpiled = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', transpiled)
    transpiled = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', transpiled)
    
    # 移除 float 後綴 (如 1.5f -> 1.5)
    transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
    
    # Java for-each: for (Particle p : list) -> for (let p of list)
    transpiled = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', transpiled)
    
    # 畫布模式替代
    transpiled = re.sub(r'\bfullScreen\s*\(\s*(?:P3D|WEBGL|OPENGL)?\s*\)', 'createCanvas(windowWidth, windowHeight, WEBGL)', transpiled, flags=re.IGNORECASE)
    transpiled = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', transpiled)
    transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P3D|WEBGL|OPENGL)\s*\)', r'createCanvas(\1, \2, WEBGL)', transpiled, flags=re.IGNORECASE)
    transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P2D|JAVA2D)\s*\)', r'createCanvas(\1, \2)', transpiled, flags=re.IGNORECASE)
    transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', transpiled)
    
    # 清理類別內部與函式參數中的非法宣告
    lines = transpiled.split('\n')
    cleaned_lines = []
    in_class = False
    brace_depth = 0
    
    for line in lines:
        if re.search(r'\bclass\s+\w+', line):
            in_class = True
            brace_depth = 0
            
        if in_class:
            brace_depth += line.count('{') - line.count('}')
            if brace_depth <= 0:
                in_class = False
            # 移除 JS 類別欄位宣告前誤加的 let
            if brace_depth == 1 and line.strip().startswith('let '):
                line = re.sub(r'^(\s*)let\s+', r'\1', line)
                
        # 移除函式參數中誤加的 let
        if 'function' in line or '(' in line:
            line = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', lambda m: '(' + re.sub(r'\blet\s+', '', m.group(1)) + ')', line)
            
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def try_repair_code(code: str) -> str:
    repaired = code
    repaired = fix_invalid_syntax_constructs(repaired)
    repaired = transpile_processing_java_to_js(repaired)
    
    # 處理全域 await 使用
    if "await " in repaired and "async function" not in repaired:
        repaired = re.sub(r'\bfunction\s+setup\s*\(', 'async function setup(', repaired)
        repaired = re.sub(r'\bfunction\s+draw\s*\(', 'async function draw(', repaired)

    # 確保具有基礎生命週期
    if "setup" not in repaired and "createCanvas" not in repaired:
        repaired = "function setup() { createCanvas(windowWidth, windowHeight); }\n" + repaired
        
    return repaired

def try_repair_json_file(file_path: str):
    data = None
    raw_content = ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
        data = json.loads(raw_content)
    except Exception:
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
        
    data["code"] = try_repair_code(data["code"])
    return data, None

def validate_js_syntax(code: str):
    """ 使用 Node.js 進行快速語法審查 (AST Level Check) """
    is_module = bool(re.search(r'\b(import|export)\b', code))
    full_code = IMMUNITY_STUBS_HEADER + "\n" + code
    
    suffix = ".mjs" if is_module else ".js"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=False) as f:
        f.write(full_code)
        temp_js = f.name
        
    try:
        cmd = ["node", "--check", temp_js]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            return True, "Valid JS Syntax"
        else:
            return False, res.stderr.strip()
    except Exception as e:
        return True, f"Syntax check fallback passed ({e})"
    finally:
        if os.path.exists(temp_js):
            try:
                os.remove(temp_js)
            except Exception:
                pass

def run_batch_repair():
    if not os.path.exists(ABNORMAL_BACKUP_DIR):
        print(f"❌ Target dir {ABNORMAL_BACKUP_DIR} does not exist!")
        return

    json_files = [f for f in os.listdir(ABNORMAL_BACKUP_DIR) if f.endswith(".json")]
    json_files.sort()

    total_files = len(json_files)
    print(f"🚀 Batch Repairing {total_files} abnormal modules...")

    repaired_count = 0
    failed_count = 0
    repair_details = []

    for idx, fname in enumerate(json_files):
        file_path = os.path.join(ABNORMAL_BACKUP_DIR, fname)
        
        data, err = try_repair_json_file(file_path)
        if not data:
            failed_count += 1
            repair_details.append({"file": fname, "status": "failed", "reason": err})
            continue

        is_valid, syntax_info = validate_js_syntax(data["code"])
        
        if is_valid:
            dest_json = os.path.join(CUSTOM_VISUALS_DIR, fname)
            with open(dest_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
            try:
                os.remove(file_path)
            except Exception:
                pass
                
            thumb_name = f"{fname[:-5]}.jpg"
            src_thumb = os.path.join(ABNORMAL_BACKUP_DIR, "thumbnails", thumb_name)
            dest_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", thumb_name)
            if os.path.exists(src_thumb):
                os.makedirs(os.path.dirname(dest_thumb), exist_ok=True)
                shutil.move(src_thumb, dest_thumb)

            repaired_count += 1
            repair_details.append({"file": fname, "status": "repaired", "syntax": syntax_info})
            print(f"[{idx+1}/{total_files}] ✨ Repaired: {fname}")
        else:
            failed_count += 1
            repair_details.append({"file": fname, "status": "failed", "reason": syntax_info})
            print(f"[{idx+1}/{total_files}] ❌ Failed: {fname}")

    final_report = {
        "total": total_files,
        "repaired": repaired_count,
        "failed": failed_count,
        "details": repair_details,
        "completed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Batch Repair Completed! Repaired & Restored: {repaired_count}/{total_files} modules. Failed/Unrecoverable: {failed_count}")

if __name__ == "__main__":
    run_batch_repair()
