import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --disable-gpu --disable-gpu-rasterization"

import sys
import re
import json
import time
import shutil
import gc
import datetime
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PyQt6.QtCore import QUrl, QTimer, QEventLoop

# Define paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
LIBS_DIR = os.path.join(CUSTOM_VISUALS_DIR, "libs")
LOG_FILE = os.path.join(WORKSPACE_DIR, "test_run_errors.log")

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

IMMUNITY_STUBS_JS = """
(function() {
  // 1. DOM Elements & Selectors Proxy
  const dummyHandler = {
    get: function(target, prop) {
      if (prop === 'style') {
        const styleFunc = function() { return styleProxy; };
        Object.setPrototypeOf(styleFunc, styleProxy);
        return styleProxy;
      }
      if (prop === 'option' || prop === 'parent' || prop === 'position' || prop === 'size') {
        return function() { return styleProxy; };
      }
      if (typeof target[prop] === 'function') {
        return target[prop].bind(target);
      }
      return styleProxy;
    }
  };
  const dummyObj = function() {};
  dummyObj.position = dummyObj.style = dummyObj.size = dummyObj.parent = dummyObj.option = function() { return dummyObj; };
  dummyObj.id = function() { return ""; };
  dummyObj.class = dummyObj.mousePressed = dummyObj.html = dummyObj.changed = dummyObj.input = function() { return dummyObj; };
  dummyObj.value = function() { return 0; };
  dummyObj.width = 1280;
  dummyObj.height = 720;
  dummyObj.texture = function() { return dummyObj; };
  dummyObj[Symbol.iterator] = function* () { yield dummyObj; };
  const styleProxy = new Proxy(dummyObj, dummyHandler);

  if (typeof createP === 'undefined') window.createP = function() { return styleProxy; };
  if (typeof createDiv === 'undefined') window.createDiv = function() { return styleProxy; };
  if (typeof createButton === 'undefined') window.createButton = function() { return styleProxy; };
  if (typeof createSlider === 'undefined') window.createSlider = function() { return styleProxy; };
  if (typeof createInput === 'undefined') window.createInput = function() { return styleProxy; };
  if (typeof createSelect === 'undefined') window.createSelect = function() { return styleProxy; };
  if (typeof select === 'undefined') window.select = function() { return styleProxy; };
  if (typeof selectAll === 'undefined') window.selectAll = function() { return []; };

  // 2. ML5, Tone, PVector stubs
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

  // 3. Audio & DSP Mock Stubs
  window.fft = window.fft || { getEnergy: () => 128, analyze: () => new Array(64).fill(100) };
  window.amplitude = window.amplitude || { getLevel: () => 0.5 };
  window.sound = window.sound || { isPlaying: () => true, duration: () => 180, stop: () => {}, play: () => {}, loop: () => {} };
  if (typeof window.isPlaying === 'undefined') window.isPlaying = () => true;

  // 4. Processing Math & Dimensions Globals
  if (typeof window.width === 'undefined') window.width = 1280;
  if (typeof window.height === 'undefined') window.height = 720;
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

  ['res','scr','gap','asd','nPoints','scaledT','_count','angleStepMax','objs','X0','pg','starColor','clr2','typ','largX','patternColors','palette'].forEach(k => {
    if (typeof window[k] === 'undefined') {
      if (['objs','patternColors','palette'].includes(k)) window[k] = [];
      else if (k === 'scr') window[k] = styleProxy;
      else if (k === 'pg') window[k] = { width: 100, height: 100, beginDraw: () => {}, endDraw: () => {}, background: () => {}, image: () => {}, get: function(){ return this; }, loadPixels: () => {}, updatePixels: () => {}, pixels: [] };
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
})();
"""

def fix_syntax_errors(code: str) -> str:
    """ 修復標準 JavaScript / p5.js 語法錯誤 """
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    code = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', code)
    return code

def transpile_processing_java_to_js(code: str) -> str:
    """ 將 Processing Java 語法轉譯為相容的 p5.js JavaScript """
    if "void setup" not in code and "void draw" not in code and "float " not in code and "int " not in code and "class " not in code:
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
    
    # 類別內部與函式參數中非法 let 的修剪
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
            if brace_depth == 1 and line.strip().startswith('let '):
                line = re.sub(r'^(\s*)let\s+', r'\1', line)
                
        if 'function' in line or '(' in line:
            line = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', lambda m: '(' + re.sub(r'\blet\s+', '', m.group(1)) + ')', line)
            
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def try_repair_code(code: str, errors_captured: list) -> str:
    repaired = code
    repaired = fix_syntax_errors(repaired)
    repaired = transpile_processing_java_to_js(repaired)
    
    if "await " in repaired and "async function" not in repaired:
        repaired = re.sub(r'\bfunction\s+setup\s*\(', 'async function setup(', repaired)
        repaired = re.sub(r'\bfunction\s+draw\s*\(', 'async function draw(', repaired)

    if "setup" not in repaired and "createCanvas" not in repaired:
        repaired = "function setup() { createCanvas(windowWidth, windowHeight); }\n" + repaired
        
    return repaired

def make_test_html(code: str, custom_css: str = "", custom_html: str = "") -> str:
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
    window.onerror = function(msg, url, line) {{
      console.error("WindowError Line " + line + ": " + msg);
      return true;
    }};
    window.addEventListener('unhandledrejection', function(event) {{
      const reason = event.reason ? (event.reason.message || String(event.reason)) : "";
      console.error("Promise Rejected: " + reason);
    }});
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

class QWebEngineTester(QWebEnginePage):
    def __init__(self, err_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.err_callback = err_callback

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        msg_lower = message.lower()
        ignored_patterns = [
            "failed to fetch", "audiocontext", "cors", "[mock]", "[loadingwatchdog]",
            "opentype", ".ttf", ".otf", "width or height of 0", "[preloadguard]",
            "net::err", "mime type"
        ]
        if any(p in msg_lower for p in ignored_patterns):
            return
            
        if level.name in ['ErrorMessage', 'CriticalMessage'] or 'Uncaught' in message:
            self.err_callback(f"Console Line {lineNumber}: {message}")

def log_errors_to_file(title: str, url: str, errors: list):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n========================================\n")
        f.write(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Title: {title}\n")
        f.write(f"URL: {url}\n")
        f.write("Errors:\n")
        for err in errors:
            f.write(f"  - {err}\n")

def test_run_module(web_view: QWebEngineView, html_path: str) -> list:
    js_errors = []
    page = QWebEngineTester(lambda msg: js_errors.append(msg))
    web_view.setPage(page)
    
    loop = QEventLoop()
    
    # 專屬槽函數以供精確斷開信號，防止 Slot 洩漏
    def on_load(ok):
        if loop.isRunning():
            loop.quit()
            
    web_view.loadFinished.connect(on_load)
    web_view.setUrl(QUrl.fromLocalFile(html_path))
    
    QTimer.singleShot(700, loop.quit)
    loop.exec()
    
    try:
        web_view.loadFinished.disconnect(on_load)
    except Exception:
        pass
    
    # 等待繪圖幀執行
    loop_wait = QEventLoop()
    QTimer.singleShot(250, loop_wait.quit)
    loop_wait.exec()
    
    page.deleteLater()
    QApplication.processEvents()
    
    return list(set(js_errors))

def main():
    app = QApplication(sys.argv)
    
    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"❌ 找不到 custom_visuals 目錄: {CUSTOM_VISUALS_DIR}")
        return
        
    json_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
    json_files.sort()
    
    total = len(json_files)
    print(f"🔍 掃描到 {total} 個視覺模組，準備進行自動化無頭 QC 驗證與修復...")
    
    web_view = QWebEngineView()
    web_view.resize(1280, 720)
    
    # 配置 WebEngine 權限
    settings = web_view.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
    
    temp_html_path = os.path.join(WORKSPACE_DIR, "_temp_qc_test.html")
    
    broken_modules = []
    repaired_modules = []
    healthy_modules_count = 0
    
    for idx, fname in enumerate(json_files):
        if idx > 0 and idx % 100 == 0:
            gc.collect()
            web_view.setPage(None)
            
        fpath = os.path.join(CUSTOM_VISUALS_DIR, fname)
        
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[{idx+1}/{total}] ❌ 無法讀取 JSON {fname}: {e}")
            continue
            
        code = data.get("code", "")
        custom_css = data.get("custom_css", "")
        custom_html = data.get("custom_html", "")
        title = data.get("name") or data.get("title", fname)
        url = data.get("url", "N/A")
        
        html_content = make_test_html(code, custom_css, custom_html)
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        errors = test_run_module(web_view, temp_html_path)
        
        if len(errors) == 0:
            healthy_modules_count += 1
            if (idx + 1) % 25 == 0 or idx == total - 1:
                print(f"進度: [{idx+1}/{total}] 檢查完畢。健康: {healthy_modules_count}, 自動修復: {len(repaired_modules)}, 損毀: {len(broken_modules)}")
            continue
            
        log_errors_to_file(title, url, errors)
        print(f"[{idx+1}/{total}] ⚠️ 模組「{title}」發現錯誤: {errors[0]}。嘗試自動修補中...")
        repaired_code = try_repair_code(code, errors)
        
        repaired_html_content = make_test_html(repaired_code, custom_css, custom_html)
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(repaired_html_content)
            
        post_errors = test_run_module(web_view, temp_html_path)
        
        if len(post_errors) == 0:
            print(f"  ✨ 修復成功！模組「{title}」現已完全相容。")
            data["code"] = repaired_code
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            repaired_modules.append({
                "file": fname,
                "title": title,
                "original_errors": errors
            })
        else:
            print(f"  ❌ 修復失敗，仍有殘留錯誤: {post_errors[0]}")
            broken_modules.append({
                "file": fname,
                "title": title,
                "errors": post_errors
            })

    if os.path.exists(temp_html_path):
        try:
            os.remove(temp_html_path)
        except Exception:
            pass
        
    report = {
        "timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_scanned": total,
        "healthy": healthy_modules_count,
        "repaired_count": len(repaired_modules),
        "repaired_details": repaired_modules,
        "broken_count": len(broken_modules),
        "broken_details": broken_modules
    }
    with open(os.path.join(WORKSPACE_DIR, "repair_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print("\n" + "="*50)
    print("✅ 批量 QC 審查與自動修復程序完成！")
    print(f"總模組數: {total}")
    print(f"原生正常: {healthy_modules_count}")
    print(f"自動修補成功: {len(repaired_modules)}")
    print(f"待手動排查損毀: {len(broken_modules)}")
    print(f"日誌輸出至: {LOG_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
