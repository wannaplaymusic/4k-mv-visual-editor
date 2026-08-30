import os
import sys
import re
import json
import shutil
import subprocess
import datetime
from typing import Dict, Any, Tuple

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
ABNORMAL_BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "abnormal_backup")
REPORT_FILE = os.path.join(WORKSPACE_DIR, "repair_report.json")

IMMUNITY_STUBS_HEADER = """
if (typeof p5 !== 'undefined' && p5.prototype) {
  p5.prototype.registerMethod = p5.prototype.registerMethod || function() {};
}
if (typeof window !== 'undefined') {
  window.forceStartP5 = window.forceStartP5 || function() {};
  window.forceRedrawP5 = window.forceRedrawP5 || function() {};
}
// Processing 兼容墊片 (Polyfills)
const int = (v) => Math.floor(Number(v) || 0);
const float = (v) => Number(v) || 0.0;
const boolean = (v) => Boolean(v);
const byte = (v) => (Number(v) || 0) & 0xFF;
"""

def fix_assignments(code: str) -> str:
    """ 修復語法錯誤與陣列非法賦值 """
    # 修復 loc[] = val -> loc.push(val)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    
    # 轉換 size()
    code = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P3D|WEBGL|OPENGL)\s*\)', r'createCanvas(\1, \2, WEBGL)', code, flags=re.IGNORECASE)
    code = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*(?:,\s*(?:P2D|JAVA2D))?\s*\)', r'createCanvas(\1, \2)', code, flags=re.IGNORECASE)
    return code

def transpile_processing(code: str) -> str:
    """ 將 Processing Java 語法轉譯為標準 p5.js (JavaScript) """
    java_indicators = ["void ", "float ", "int ", "boolean ", "class ", "public ", "private ", "new ArrayList"]
    if not any(k in code for k in java_indicators):
        return code

    t = code

    # 1. 移除 Java 修飾符號
    t = re.sub(r'\b(private|public|protected|static|transient|volatile|final)\s+', '', t)

    # 2. 型別強制轉換: (int)x -> Math.floor(x) 或 int(x), (float)x -> Number(x)
    t = re.sub(r'\(int\)\s*([A-Za-z0-9_$\.]+)', r'Math.floor(\1)', t)
    t = re.sub(r'\(int\)\s*\(([^)]+)\)', r'Math.floor(\1)', t)
    t = re.sub(r'\((?:float|double)\)\s*([A-Za-z0-9_$\.]+)', r'Number(\1)', t)
    t = re.sub(r'\((?:float|double)\)\s*\(([^)]+)\)', r'Number(\1)', t)

    # 3. 陣列初始化語法轉換
    t = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', t)
    t = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', t)
    t = re.sub(
        r'\b[A-Za-z0-9_$\.]+\s*\[\s*\]\s*\[\s*\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*;',
        r'let \1 = Array.from({length: \2}, () => new Array(\3).fill(0));',
        t
    )

    # 4. 函式回傳值型別轉為 function (void, int, float, boolean, ArrayList 等)
    t = re.sub(r'\b(?:void|int|float|double|boolean|color|char|String|long)\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', t)

    # 5. 變數宣告型別清理 (例如: float x = 10; -> let x = 10;)
    primitive_types = r'\b(?:int|float|double|boolean|color|char|String|long|PVector|PImage|PGraphics|ArrayList)\b'
    t = re.sub(rf'{primitive_types}(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\s*([=;,\)])', r'let \1\2', t)

    # 6. 常見 Java 常數/符號處理
    t = re.sub(r'(\d+\.?\d*)f\b', r'\1', t) # 1.0f -> 1.0
    t = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Za-z0-9_$]+\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', t)

    # 7. 全螢幕轉換
    t = re.sub(r'\bfullScreen\s*\(\s*(?:P3D|WEBGL|OPENGL)?\s*\)', 'createCanvas(windowWidth, windowHeight, WEBGL)', t, flags=re.IGNORECASE)
    t = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', t)

    # 8. 清理 class 內部成員宣告與函式參數中殘留的 let
    lines = t.split('\n')
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
            # ES6 class 內部宣告不能使用 let
            if brace_depth == 1:
                line = re.sub(r'^\s*let\s+([A-Za-z0-9_$]+)\s*;', r'\1;', line)
                line = re.sub(r'^\s*let\s+([A-Za-z0-9_$]+)\s*=', r'\1 =', line)
                # 類別內部方法修復
                line = re.sub(r'^\s*function\s+([A-Za-z0-9_$]+)\s*\(', r'\1(', line)

        # 函式參數內不能有 let
        if 'function' in line or '(' in line:
            line = re.sub(r'\(([^)]*)\)', lambda m: '(' + re.sub(r'\blet\s+', '', m.group(1)) + ')', line)

        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)

def repair_single_code(code: str) -> str:
    repaired = fix_assignments(code)
    repaired = transpile_processing(repaired)

    # 補足 async / await 匹配
    if "await " in repaired and "async function" not in repaired:
        repaired = re.sub(r'\bfunction\s+setup\s*\(', 'async function setup(', repaired)
        repaired = re.sub(r'\bfunction\s+draw\s*\(', 'async function draw(', repaired)

    # 基本 p5.js 生命周期保障
    if "setup" not in repaired and "createCanvas" not in repaired:
        repaired = "function setup() { createCanvas(windowWidth, windowHeight); }\n" + repaired

    return repaired

def safe_load_json(raw_text: str, default_name: str) -> Dict[str, Any]:
    """ 容錯載入可能損壞的 JSON 檔 """
    try:
        return json.loads(raw_text)
    except Exception:
        # 正則提取 code 區塊
        match = re.search(r'"code"\s*:\s*("(?:[^"\\]|\\.)*")', raw_text, re.DOTALL)
        if match:
            try:
                code_str = json.loads(match.group(1))
                return {"id": default_name, "name": default_name, "code": code_str}
            except Exception:
                pass
    return None

def main():
    if not os.path.exists(ABNORMAL_BACKUP_DIR):
        print(f"❌ 找不到目錄: {ABNORMAL_BACKUP_DIR}", flush=True)
        return

    os.makedirs(CUSTOM_VISUALS_DIR, exist_ok=True)
    os.makedirs(os.path.join(CUSTOM_VISUALS_DIR, "thumbnails"), exist_ok=True)

    json_files = [f for f in os.listdir(ABNORMAL_BACKUP_DIR) if f.endswith('.json') and f != 'modules_index.json']
    json_files.sort()
    total_files = len(json_files)

    print(f"🚀 開始對 {total_files} 個異常模組進行分塊急速修復與 AST 驗證...", flush=True)

    repaired_count = 0
    failed_count = 0
    details = []

    chunk_size = 100
    for i in range(0, total_files, chunk_size):
        chunk = json_files[i:i+chunk_size]
        manifest: Dict[str, str] = {}
        parsed_data: Dict[str, Dict[str, Any]] = {}

        for fname in chunk:
            fpath = os.path.join(ABNORMAL_BACKUP_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception as e:
                failed_count += 1
                details.append({"file": fname, "status": "failed", "reason": f"Read error: {str(e)}"})
                continue

            data = safe_load_json(raw, fname[:-5])
            if not data or "code" not in data or not str(data["code"]).strip():
                failed_count += 1
                details.append({"file": fname, "status": "failed", "reason": "Empty or broken JSON/Code"})
                continue

            code = repair_single_code(str(data["code"]))
            data["code"] = code
            parsed_data[fname] = data
            manifest[fname] = IMMUNITY_STUBS_HEADER + "\n" + code

        # 生成 Node.js 批量驗證腳本
        chunk_id = f"{os.getpid()}_{i}"
        manifest_path = os.path.join(WORKSPACE_DIR, f"_chunk_manifest_{chunk_id}.json")
        node_script_path = os.path.join(WORKSPACE_DIR, f"_chunk_node_{chunk_id}.js")
        results_path = os.path.join(WORKSPACE_DIR, f"_chunk_results_{chunk_id}.json")

        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)

            node_code = f"""
            const fs = require('fs');
            const vm = require('vm');
            const manifest = JSON.parse(fs.readFileSync({json.dumps(manifest_path)}, 'utf-8'));
            const results = {{}};

            for (const [fname, code] of Object.entries(manifest)) {{
                try {{
                    if (code.includes('import ') || code.includes('export ')) {{
                        new vm.SourceTextModule(code, {{ initializeImportMeta() {{}} }});
                    }} else {{
                        new vm.Script(code);
                    }}
                    results[fname] = {{ ok: true }};
                }} catch(e) {{
                    try {{
                        const cleanedCode = code.replace(/\\b(import|export)\\b[^;\\n]+[;\\n]/g, '');
                        new vm.Script(cleanedCode);
                        results[fname] = {{ ok: true }};
                    }} catch(err2) {{
                        results[fname] = {{ ok: false, err: err2.message }};
                    }}
                }}
            }}
            fs.writeFileSync({json.dumps(results_path)}, JSON.stringify(results, null, 2));
            """
            with open(node_script_path, "w", encoding="utf-8") as f:
                f.write(node_code)

            proc = subprocess.run(
                ["node", "--experimental-vm-modules", node_script_path],
                capture_output=True,
                text=True
            )

            val_results = {}
            if os.path.exists(results_path):
                with open(results_path, "r", encoding="utf-8") as f:
                    val_results = json.load(f)

            for fname, data in parsed_data.items():
                res_item = val_results.get(fname, {})
                if res_item.get("ok"):
                    # 寫回修復後的 custom_visuals 目錄
                    dest_json = os.path.join(CUSTOM_VISUALS_DIR, fname)
                    with open(dest_json, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)

                    # 移除 abnormal 備份
                    fpath = os.path.join(ABNORMAL_BACKUP_DIR, fname)
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

                    # 同步搬移縮圖
                    thumb_name = fname[:-5] + ".jpg"
                    src_thumb = os.path.join(ABNORMAL_BACKUP_DIR, "thumbnails", thumb_name)
                    dest_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", thumb_name)
                    if os.path.exists(src_thumb):
                        try:
                            shutil.move(src_thumb, dest_thumb)
                        except Exception:
                            pass

                    repaired_count += 1
                    details.append({"file": fname, "status": "repaired", "syntax": "vm.Script Validated"})
                else:
                    failed_count += 1
                    err_msg = res_item.get("err", proc.stderr.strip() or "Syntax Validation Failed")
                    details.append({"file": fname, "status": "failed", "reason": err_msg})

        finally:
            for p in [manifest_path, node_script_path, results_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        print(f"   已處理: {min(i + chunk_size, total_files)}/{total_files} | 目前累計成功修復: {repaired_count}", flush=True)

    report = {
        "total": total_files,
        "repaired": repaired_count,
        "failed": failed_count,
        "details": details,
        "completed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 批量極速修復完成！成功修復: {repaired_count}/{total_files} 個模組，無法修復/損毀: {failed_count}", flush=True)

if __name__ == "__main__":
    main()
