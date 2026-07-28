import os
import sys
import re
import json
import shutil
import subprocess
import datetime

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
"""

def fix_assignments(code):
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    return code

def transpile_processing(code):
    if 'void setup' not in code and 'void draw' not in code and 'float ' not in code and 'int ' not in code:
        return code
    t = code
    t = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', t)
    t = re.sub(r'\bfinal\s+', '', t)
    t = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', t)
    t = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', t)
    t = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', t)
    t = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', t)
    t = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', t)
    t = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', t)
    t = re.sub(r'(\d+\.?\d*)f\b', r'\1', t)
    t = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', t)
    return t

def main():
    json_files = [f for f in os.listdir(ABNORMAL_BACKUP_DIR) if f.endswith('.json')]
    json_files.sort()
    total_files = len(json_files)
    
    print(f"🚀 Direct Repairing {total_files} abnormal modules...")
    
    repaired_count = 0
    failed_count = 0
    details = []

    # Process in chunk batches of 100
    chunk_size = 100
    for i in range(0, total_files, chunk_size):
        chunk = json_files[i:i+chunk_size]
        manifest = {}
        parsed_data = {}
        
        for fname in chunk:
            fpath = os.path.join(ABNORMAL_BACKUP_DIR, fname)
            raw = ""
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = json.loads(raw)
            except Exception:
                match = re.search(r'"code"\s*:\s*"(.*)"\s*,\s*"', raw, re.DOTALL)
                if not match: match = re.search(r'"code"\s*:\s*"(.*)"', raw, re.DOTALL)
                if match:
                    code_str = match.group(1).encode().decode('unicode_escape', errors='ignore')
                    data = {"id": fname[:-5], "name": fname[:-5], "code": code_str}
                else:
                    data = None
                    
            if not data or "code" not in data or not data["code"].strip():
                failed_count += 1
                details.append({"file": fname, "status": "failed", "reason": "Empty or broken JSON"})
                continue
                
            code = data["code"]
            code = fix_assignments(code)
            code = transpile_processing(code)
            if "setup" not in code and "createCanvas" not in code:
                code = "function setup() { createCanvas(windowWidth, windowHeight); }\n" + code
                
            data["code"] = code
            parsed_data[fname] = data
            manifest[fname] = IMMUNITY_STUBS_HEADER + "\n" + code

        # Batch validate using temporary node script
        manifest_path = os.path.join(WORKSPACE_DIR, f"_chunk_manifest_{i}.json")
        node_script_path = os.path.join(WORKSPACE_DIR, f"_chunk_node_{i}.js")
        results_path = os.path.join(WORKSPACE_DIR, f"_chunk_results_{i}.json")

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
            
        node_code = f"""
        const fs = require('fs');
        const vm = require('vm');
        const manifest = JSON.parse(fs.readFileSync({json.dumps(manifest_path)}, 'utf-8'));
        const results = {{}};
        for (const [fname, code] of Object.entries(manifest)) {{
            try {{
                new vm.Script(code);
                results[fname] = {{ ok: true }};
            }} catch(e) {{
                results[fname] = {{ ok: false, err: e.message }};
            }}
        }}
        fs.writeFileSync({json.dumps(results_path)}, JSON.stringify(results, null, 2));
        """
        with open(node_script_path, "w", encoding="utf-8") as f:
            f.write(node_code)
            
        subprocess.run(["node", node_script_path], capture_output=True, text=True)
        
        if os.path.exists(results_path):
            with open(results_path, "r", encoding="utf-8") as f:
                val_results = json.load(f)
                
            for fname, data in parsed_data.items():
                res_item = val_results.get(fname, {})
                if res_item.get("ok"):
                    dest_json = os.path.join(CUSTOM_VISUALS_DIR, fname)
                    with open(dest_json, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                        
                    fpath = os.path.join(ABNORMAL_BACKUP_DIR, fname)
                    try: os.remove(fpath)
                    except Exception: pass
                    
                    thumb_name = fname[:-5] + ".jpg"
                    src_thumb = os.path.join(ABNORMAL_BACKUP_DIR, "thumbnails", thumb_name)
                    dest_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", thumb_name)
                    if os.path.exists(src_thumb):
                        os.makedirs(os.path.dirname(dest_thumb), exist_ok=True)
                        shutil.move(src_thumb, dest_thumb)
                        
                    repaired_count += 1
                    details.append({"file": fname, "status": "repaired", "syntax": "vm.Script Validated"})
                else:
                    failed_count += 1
                    details.append({"file": fname, "status": "failed", "reason": res_item.get("err", "SyntaxError")})

            # Clean temporary chunk files
            for p in [manifest_path, node_script_path, results_path]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass

        print(f"  Processed batch {i+len(chunk)}/{total_files}... Repaired so far: {repaired_count}")

    report = {
        "total": total_files,
        "repaired": repaired_count,
        "failed": failed_count,
        "details": details,
        "completed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print(f"🎉 Direct Repair Complete! Repaired: {repaired_count}/{total_files}, Failed: {failed_count}")

if __name__ == "__main__":
    main()
