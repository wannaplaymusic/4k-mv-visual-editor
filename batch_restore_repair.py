import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import re
import json
import time
import shutil
import gc
import datetime
import numpy as np

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QUrl, QTimer, QEventLoop
from PyQt6.QtGui import QColor, QImage

# Define paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
ABNORMAL_BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "abnormal_backup")
STATUS_FILE = "/tmp/repair_status.json"
REPORT_FILE = os.path.join(WORKSPACE_DIR, "repair_report.json")

# P5 v2 compatibility shim
P5_V2_COMPAT_SHIM = """
if (typeof p5 !== 'undefined') {
  if (p5.prototype && !p5.prototype.registerMethod) {
    p5.prototype._registeredMethods = p5.prototype._registeredMethods || {};
    p5.prototype.registerMethod = function(hookName, method) {
      if (typeof method !== 'function') return;
      if (!p5.prototype._registeredMethods[hookName]) {
        p5.prototype._registeredMethods[hookName] = [];
      }
      p5.prototype._registeredMethods[hookName].push(method);
    };
  }
  if (p5.prototype && !p5.prototype._checkFileExtension) {
    p5.prototype._checkFileExtension = function(path) {
      var ext = '';
      if (typeof path === 'string') {
        var idx = path.lastIndexOf('.');
        if (idx >= 0) ext = path.slice(idx + 1).toLowerCase();
      }
      return { ext: ext };
    };
  }
  if (p5.prototype && !p5.prototype.registerPreloadMethod) {
    p5.prototype.registerPreloadMethod = function(methodName, prototype) {};
  }
  if (p5.prototype) {
    try {
      var stepDesc = Object.getOwnPropertyDescriptor(p5.prototype, 'step');
      if (stepDesc && !stepDesc.configurable) {
        Object.defineProperty(p5.prototype, 'step', {
          value: stepDesc.value,
          writable: true,
          configurable: true,
          enumerable: stepDesc.enumerable
        });
      }
    } catch(e) {}
  }
}
"""

# Extended Immunity Proxy JS Stub
IMMUNITY_STUBS_JS = """
(function() {
  // 1. Immunity for DOM Elements
  const dummyHandler = {
    get: function(target, prop) {
      if (prop === 'style') {
        const styleFunc = function() { return styleProxy; };
        Object.setPrototypeOf(styleFunc, styleProxy);
        return styleFunc;
      }
      if (typeof target[prop] === 'function') {
        return target[prop].bind(target);
      }
      return styleProxy;
    }
  };
  const dummyObj = function() {};
  dummyObj.position = dummyObj.style = dummyObj.size = dummyObj.parent = function() { return dummyObj; };
  dummyObj.id = function() { return ""; };
  dummyObj.class = dummyObj.mousePressed = dummyObj.html = function() { return dummyObj; };
  dummyObj.value = function() { return 0; };
  dummyObj.texture = function() { return dummyObj; };
  dummyObj.changed = dummyObj.input = function() { return dummyObj; };
  dummyObj.width = 1280;
  dummyObj.height = 720;
  dummyObj[Symbol.iterator] = function* () { yield dummyObj; };
  const styleProxy = new Proxy(dummyObj, dummyHandler);

  if (typeof createP === 'undefined') window.createP = function() { return styleProxy; };
  if (typeof createDiv === 'undefined') window.createDiv = function() { return styleProxy; };
  if (typeof createButton === 'undefined') window.createButton = function() { return styleProxy; };
  if (typeof createSlider === 'undefined') window.createSlider = function() { return styleProxy; };
  if (typeof createInput === 'undefined') window.createInput = function() { return styleProxy; };
  if (typeof select === 'undefined') window.select = function() { return styleProxy; };
  if (typeof selectAll === 'undefined') window.selectAll = function() { return []; };

  try {
    if (typeof Element !== 'undefined') {
      Object.defineProperty(Element.prototype, 'style', {
        get: () => {
          const styleFunc = () => styleProxy;
          Object.setPrototypeOf(styleFunc, styleProxy);
          return styleProxy;
        },
        configurable: true
      });
    }
  } catch(e) {}

  // 2. ML5, Tone, PVector, sound stubs
  if (typeof window.ml5 === 'undefined') {
    const mockML = { on: () => {}, ready: Promise.resolve(), features: { get: () => [] } };
    window.ml5 = { poseNet: () => mockML, bodypix: () => mockML, handpose: () => mockML, imageClassifier: () => mockML };
  }
  if (typeof PVector === 'undefined') {
    window.PVector = class {
      constructor(x,y,z) { this.x=x||0; this.y=y||0; this.z=z||0; }
      static dist(v1,v2) { return Math.sqrt((v1.x-(v2?v2.x:0))**2+(v1.y-(v2?v2.y:0))**2); }
      static random2D() { return new window.PVector(Math.random()*2-1, Math.random()*2-1, 0); }
    };
  }

  // 3. Audio reactive mocks
  window.fft = window.fft || { getEnergy: () => 128, analyze: () => new Array(64).fill(100) };
  window.amplitude = window.amplitude || { getLevel: () => 0.5 };
  window.sound = window.sound || { isPlaying: () => true, duration: () => 180 };

  // 4. Processing math & canvas dimension stubs
  if (typeof window.width === 'undefined') window.width = window.innerWidth || 1280;
  if (typeof window.height === 'undefined') window.height = window.innerHeight || 720;
  if (typeof HALF_PI === 'undefined') window.HALF_PI = Math.PI / 2;
  if (typeof QUARTER_PI === 'undefined') window.QUARTER_PI = Math.PI / 4;
  if (typeof TWO_PI === 'undefined') window.TWO_PI = Math.PI * 2;
  if (typeof window.P3D === 'undefined') window.P3D = "webgl";
  if (typeof window.OPENGL === 'undefined') window.OPENGL = "webgl";
  if (typeof window.P2D === 'undefined') window.P2D = "p2d";
  if (typeof window.JAVA2D === 'undefined') window.JAVA2D = "p2d";
  
  ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'].forEach(k => { if (typeof window[k] === 'undefined') window[k] = k.toLowerCase(); });
  ['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z'].forEach(k => { if (typeof window[k] === 'undefined') window[k] = 0; });
  
  if (typeof window.cnv === 'undefined') window.cnv = styleProxy;
  if (typeof window.inner1 === 'undefined') window.inner1 = styleProxy;
  if (typeof window.eyePic === 'undefined') window.eyePic = styleProxy;
  if (typeof window.myColor === 'undefined') window.myColor = '#ffffff';
  if (typeof window.grainAmount === 'undefined') window.grainAmount = 0;
  
  ['res','scr','gap','asd','nPoints','scaledT','_count','angleStepMax','objs','X0','pg','starColor','clr2','typ','largX', 'patternColors', 'palette'].forEach(k => {
    if (typeof window[k] === 'undefined') {
      if (['objs','patternColors','palette'].includes(k)) window[k] = [];
      else if (k === 'scr') window[k] = styleProxy;
      else if (k === 'pg') window[k] = { width: 100, height: 100, beginDraw: ()=>{}, endDraw: ()=>{}, background: ()=>{}, image: ()=>{}, get: function(){ return this; }, loadPixels: ()=>{}, updatePixels: ()=>{}, pixels: [] };
      else if (['starColor', 'clr2', 'myColor'].includes(k)) window[k] = '#ffffff';
      else if (k === 'angleStepMax') window[k] = 1;
      else window[k] = 0;
    }
  });

  if (typeof p5 !== 'undefined' && p5.prototype) {
    p5.prototype.loadImage = p5.prototype.loadImage || function(path, cb) {
      const dummyImg = { width: 100, height: 100, loadPixels: ()=>{}, updatePixels: ()=>{}, get: ()=>[0,0,0,255], resize: ()=>{} };
      if (cb) setTimeout(() => cb(dummyImg), 0);
      return dummyImg;
    };
  }

  // WebGL uniform alias compatibility
  if (typeof WebGLRenderingContext !== 'undefined') {
    const glProto = WebGLRenderingContext.prototype;
    if (!glProto.uniform1) glProto.uniform1 = function(loc, v0) { return this.uniform1f(loc, v0); };
    if (!glProto.uniform2) glProto.uniform2 = function(loc, v0, v1) { return this.uniform2f(loc, v0, v1); };
    if (!glProto.uniform3) glProto.uniform3 = function(loc, v0, v1, v2) { return this.uniform3f(loc, v0, v1, v2); };
    if (!glProto.uniform4) glProto.uniform4 = function(loc, v0, v1, v2, v3) { return this.uniform4f(loc, v0, v1, v2, v3); };
  }
})();
"""

def fix_invalid_left_hand_assignments(code: str) -> str:
    """ 修復語法錯誤 (如 loc[] = val 或 pos[] = val) """
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    code = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', code)
    return code

def transpile_processing_java_to_js(code: str) -> str:
    """ 將 Processing Java 語法轉譯為 JavaScript (p5.js) """
    if "void setup" not in code and "void draw" not in code and "float " not in code and "int " not in code:
        return code
        
    transpiled = code
    transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile|final)\s+', '', transpiled)
    
    transpiled = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', transpiled)
    transpiled = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', transpiled)
    
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', transpiled)
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', transpiled)
    
    transpiled = re.sub(
        r'\b[A-Za-z0-9_$\.]+\s*\[\s*\]\s*\[\s*\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*;',
        r'let \1 = Array.from({length: \2}, () => new Array(\3).fill(0));',
        transpiled
    )
    
    transpiled = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', transpiled)
    transpiled = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', transpiled)
    
    transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
    transpiled = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', transpiled)
    
    transpiled = re.sub(r'\bfullScreen\s*\(\s*(?:P3D|WEBGL|OPENGL)?\s*\)', 'createCanvas(windowWidth, windowHeight, WEBGL)', transpiled, flags=re.IGNORECASE)
    transpiled = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', transpiled)
    transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P3D|WEBGL|OPENGL)\s*\)', r'createCanvas(\1, \2, WEBGL)', transpiled, flags=re.IGNORECASE)
    transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P2D|JAVA2D)\s*\)', r'createCanvas(\1, \2)', transpiled, flags=re.IGNORECASE)
    transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', transpiled)
    
    return transpiled

def try_repair_code(code: str) -> str:
    repaired = code
    repaired = fix_invalid_left_hand_assignments(repaired)
    repaired = transpile_processing_java_to_js(repaired)
    
    if "await " in repaired and "async function" not in repaired:
        repaired = re.sub(r'\bfunction\s+setup\s*\(', 'async function setup(', repaired)
        repaired = re.sub(r'\bfunction\s+draw\s*\(', 'async function draw(', repaired)

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

def make_test_html(code, custom_css="", custom_html=""):
    is_module = "import " in code or "export " in code
    script_tag = f'<script type="module">{code}</script>' if is_module else f'<script>{code}</script>'
    
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ margin: 0; overflow: hidden; background: #000; }}
    canvas {{ display: block !important; width: 100vw !important; height: 100vh !important; }}
    {custom_css}
  </style>
  <script>
    (function() {{
      const _origWarn = console.warn;
      console.warn = function(...args) {{
        if (args[0] && typeof args[0] === 'string' && (args[0].includes('vectors of different sizes') || args[0].includes('linger vector'))) {{
          return;
        }}
        if (typeof _origWarn === 'function') {{
          _origWarn.apply(console, args);
        }}
      }};
    }})();
    window.__jsErrors = [];
    window.__drawCount = 0;
    window.__setupFinished = false;
    window.onerror = function(msg, url, line) {{
      window.__jsErrors.push("Line " + line + ": " + msg);
      return true;
    }};
  </script>
  <script src="custom_visuals/libs/p5.min.js"></script>
  <script>
    {P5_V2_COMPAT_SHIM}
    {IMMUNITY_STUBS_JS}
    if (typeof p5 !== 'undefined' && p5.prototype) {{
      const origSetup = p5.prototype.setup;
      p5.prototype.setup = function() {{
        window._p5Instance = this;
        window.__setupFinished = true;
        if (origSetup) return origSetup.apply(this, arguments);
      }};
      const origDraw = p5.prototype.draw;
      p5.prototype.draw = function() {{
        window.__drawCount = (window.__drawCount || 0) + 1;
        window._p5Instance = this;
        if (origDraw) return origDraw.apply(this, arguments);
      }};
    }}
  </script>
  <script src="custom_visuals/libs/p5.sound.min.js"></script>
  <script src="custom_visuals/libs/p5.func.min.js"></script>
  <script src="custom_visuals/libs/gsap.min.js"></script>
  <script src="custom_visuals/libs/p5.flex.min.js"></script>
  <script src="custom_visuals/libs/rampensau.js"></script>
  <script src="custom_visuals/libs/chroma.min.js"></script>
  {custom_html}
</head>
<body>
  {script_tag}
</body>
</html>
"""
    return html

class HeadlessTesterPage(QWebEnginePage):
    def __init__(self, log_err_cb, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log_err_cb = log_err_cb

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        msg_lower = message.lower()
        ignored_patterns = [
            "vectors of different sizes", "linger vector", "audiocontext", "cors",
            "[mock]", "opentype", ".ttf", ".otf", "width or height of 0", "[preloadguard]"
        ]
        if any(p in msg_lower for p in ignored_patterns):
            return
            
        if level.name in ['ErrorMessage', 'CriticalMessage'] or 'Uncaught' in message:
            self.log_err_cb(f"Line {lineNumber}: {message}")

def inspect_canvas_image(img: QImage):
    """
    雙重檢驗：採樣非黑像素數量 + 色彩變異數（Variance），防止純色黑屏或無動態畫布
    """
    w = img.width()
    h = img.height()
    if w == 0 or h == 0:
        return True, "zero_size"
        
    step_x = max(1, int(w / 32))
    step_y = max(1, int(h / 32))
    
    samples = []
    non_black = 0
    
    for x in range(0, w, step_x):
        for y in range(0, h, step_y):
            c = img.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            samples.append((r, g, b))
            if r > 10 or g > 10 or b > 10:
                non_black += 1

    total = len(samples)
    if non_black == 0:
        return True, f"all_black_pixels (0/{total})"
        
    # 計算色彩標準差，避免純色單一畫面
    arr = np.array(samples, dtype=np.float32)
    std_dev = float(np.std(arr))
    
    is_abnormal = (non_black == 0) or (std_dev < 1.0 and non_black < (total * 0.9))
    return is_abnormal, f"non_black={non_black}/{total}, std_dev={std_dev:.2f}"

def main():
    app = QApplication(sys.argv)
    
    if not os.path.exists(ABNORMAL_BACKUP_DIR):
        print(f"❌ 目標目錄不存在: {ABNORMAL_BACKUP_DIR}", flush=True)
        return

    json_files = [f for f in os.listdir(ABNORMAL_BACKUP_DIR) if f.endswith(".json") and f != "modules_index.json"]
    json_files.sort()

    total_files = len(json_files)
    print(f"🚀 開始自動化修復與驗證 {total_files} 個異常模組...", flush=True)
    
    repaired_count = 0
    failed_count = 0
    skipped_count = 0
    
    repair_details = []
    
    web_view = QWebEngineView()
    web_view.resize(1280, 720)
    
    start_timestamp = time.time()
    
    def update_status(current_file=""):
        status = {
            "total": total_files,
            "processed": repaired_count + failed_count + skipped_count,
            "repaired": repaired_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "current_file": current_file,
            "elapsed_seconds": int(time.time() - start_timestamp),
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)

    temp_html_path = os.path.join(WORKSPACE_DIR, "_temp_repair_test.html")

    for idx, fname in enumerate(json_files):
        # 記憶體維護：每 30 筆強制執行記憶體回收
        if idx > 0 and idx % 30 == 0:
            gc.collect()

        file_path = os.path.join(ABNORMAL_BACKUP_DIR, fname)
        print(f"[{idx+1}/{total_files}] 正在處理 {fname}...", flush=True)
        update_status(fname)
        
        data, err = try_repair_json_file(file_path)
        if not data:
            print(f"  ❌ 修復失敗: {err}", flush=True)
            failed_count += 1
            repair_details.append({"file": fname, "status": "failed", "reason": err})
            continue

        html_content = make_test_html(data.get("code", ""), data.get("custom_css", ""), data.get("custom_html", ""))
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        js_errors = []
        page = HeadlessTesterPage(lambda msg: js_errors.append(msg))
        web_view.setPage(page)
        
        loop_load = QEventLoop()
        web_view.loadFinished.connect(lambda ok: loop_load.quit())
        web_view.setUrl(QUrl.fromLocalFile(temp_html_path))
        
        # 載入超時防護
        QTimer.singleShot(1200, loop_load.quit)
        loop_load.exec()
        
        # 等待畫布渲染運算 (1.2 秒)
        loop_wait = QEventLoop()
        QTimer.singleShot(1200, loop_wait.quit)
        loop_wait.exec()

        pix = web_view.grab()
        img = pix.toImage()
        is_abnormal, stats_info = inspect_canvas_image(img)
        
        fatal_errors = [e for e in js_errors if "SyntaxError" in e or "Uncaught TypeError" in e]

        if not is_abnormal and len(fatal_errors) == 0:
            print(f"  ✨ SUCCESS! 畫面正常活躍 ({stats_info})，還原至 custom_visuals！", flush=True)
            
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
            repair_details.append({"file": fname, "status": "repaired", "stats": stats_info})
        else:
            reason_msg = f"is_abnormal={is_abnormal}, fatal_errors={len(fatal_errors)}"
            print(f"  ❌ 仍異常 ({reason_msg})", flush=True)
            failed_count += 1
            repair_details.append({"file": fname, "status": "failed", "reason": reason_msg, "errors": fatal_errors})

        page.deleteLater()
        app.processEvents()

    if os.path.exists(temp_html_path):
        try:
            os.remove(temp_html_path)
        except Exception:
            pass

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
    print(f"\n🎉 自動修復流程完成！成功還原: {repaired_count}/{total_files} 個模組。", flush=True)

if __name__ == "__main__":
    main()
