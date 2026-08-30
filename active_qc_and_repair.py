import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import re
import json
import time
import shutil
import datetime
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import QUrl, QTimer, QEventLoop

# Define paths
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
LIBS_DIR = os.path.join(CUSTOM_VISUALS_DIR, "libs")
LOG_FILE = os.path.join(WORKSPACE_DIR, "test_run_errors.log")

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
    p5.prototype.registerPreloadMethod = function(methodName, prototype) {
      // Stub
    };
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
  // 1. Immunity for DOM Elements & Selectors
  const dummyHandler = {
    get: function(target, prop) {
      if (prop === 'style') {
        const styleFunc = function() { return styleProxy; };
        Object.setPrototypeOf(styleFunc, styleProxy);
        return styleProxy;
      }
      if (prop === 'option') {
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
  dummyObj.width = 100;
  dummyObj.height = 100;
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

  // 3. Audio reactive & sound mocks
  window.fft = window.fft || { getEnergy: () => 128, analyze: () => new Array(64).fill(100) };
  window.amplitude = window.amplitude || { getLevel: () => 0.5 };
  window.sound = window.sound || { isPlaying: () => true, duration: () => 180, stop: () => {}, play: () => {}, loop: () => {} };
  
  if (typeof window.isPlaying === 'undefined') {
    window.isPlaying = () => true;
  }

  // 4. Processing dimension and math helpers
  if (typeof window.width === 'undefined') window.width = window.innerWidth || 1280;
  if (typeof window.height === 'undefined') window.height = window.innerHeight || 720;
  if (typeof HALF_PI === 'undefined') window.HALF_PI = Math.PI / 2;
  if (typeof QUARTER_PI === 'undefined') window.QUARTER_PI = Math.PI / 4;
  if (typeof TWO_PI === 'undefined') window.TWO_PI = Math.PI * 2;
  if (typeof window.P3D === 'undefined') window.P3D = "webgl";
  if (typeof window.OPENGL === 'undefined') window.OPENGL = "webgl";
  if (typeof window.P2D === 'undefined') window.P2D = "p2d";
  if (typeof window.JAVA2D === 'undefined') window.JAVA2D = "p2d";
  ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'].forEach(function(k) { if (typeof window[k] === 'undefined') window[k] = k.toLowerCase(); });
  ['a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z'].forEach(function(k) { if (typeof window[k] === 'undefined') window[k] = 0; });
  if (typeof window.cnv === 'undefined') window.cnv = typeof createDiv !== 'undefined' ? createDiv() : { width: 1422, height: 800, parent: function(){}, position: function(){}, style: function(){} };
  if (typeof window.inner1 === 'undefined') window.inner1 = window.cnv;
  if (typeof window.eyePic === 'undefined') window.eyePic = window.cnv;
  if (typeof window.myColor === 'undefined') window.myColor = '#ffffff';
  if (typeof window.grainAmount === 'undefined') window.grainAmount = 0;
  ['res','scr','gap','asd','nPoints','scaledT','_count','angleStepMax','objs','X0','pg','starColor','clr2','typ','largX'].forEach(function(k) {
    if (typeof window[k] === 'undefined') {
      if (k === 'objs') window[k] = [];
      else if (k === 'scr') window[k] = window.cnv;
      else if (k === 'pg') window[k] = { width: 100, height: 100, beginDraw: function(){}, endDraw: function(){}, background: function(){}, image: function(){}, get: function(){ return this; }, loadPixels: function(){}, updatePixels: function(){}, pixels: [] };
      else if (k === 'starColor') window[k] = '#ffffff';
      else if (k === 'clr2') window[k] = '#ffffff';
      else if (k === 'typ') window[k] = 0;
      else if (k === 'largX') window[k] = 0;
      else if (k === 'angleStepMax') window[k] = 1;
      else window[k] = 0;
    }
  });
  if (typeof Element !== 'undefined' && Element.prototype && !Element.prototype.size) {
    Element.prototype.size = function() { return this; };
  }
  if (typeof window._renderer !== 'undefined' && window._renderer && typeof window._renderer.getTexture !== 'function') {
    window._renderer.getTexture = function() { return { update: function(){}, bindTexture: function(){}, unbindTexture: function(){} }; };
  }
  if (typeof p5 !== 'undefined' && p5.Image && p5.Image.prototype) {
    if (!('gifProperties' in p5.Image.prototype)) {
      Object.defineProperty(p5.Image.prototype, 'gifProperties', {
        get: function() { return this._gifProps || { display: true, numFrames: 1, loopCount: 0, frameRate: 30, frames: [] }; },
        set: function(val) { this._gifProps = val; },
        configurable: true
      });
    }
  }
})();
"""

def fix_syntax_errors(code):
    """ Fix standard p5.js/JS issues """
    # 1. loc[] = val or pos[] = val -> push
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    # 2. loc[loc.length] = val -> push
    code = re.sub(r'([A-Za-z0-9_$\.]+)\s*\[\s*\1\.length\s*\]\s*=\s*([^;\n]+);', r'\1.push(\2);', code)
    # 3. size(x, y) call -> createCanvas(x, y)
    code = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', code)
    return code

def transpile_processing_java_to_js(code):
    """ Transpile Processing Java syntax to p5.js JavaScript """
    if "void setup" not in code and "void draw" not in code and "float " not in code and "int " not in code:
      return code
        
    transpiled = code
    transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
    transpiled = re.sub(r'\bfinal\s+', '', transpiled)
    
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

def try_repair_code(code, errors_captured):
    repaired = code
    repaired = fix_syntax_errors(repaired)
    repaired = transpile_processing_java_to_js(repaired)
    
    # Wrap with async if await is used outside functions
    if "await " in repaired and "async function" not in repaired:
        repaired = re.sub(r'\bfunction\s+setup\s*\(', 'async function setup(', repaired)
        repaired = re.sub(r'\bfunction\s+draw\s*\(', 'async function draw(', repaired)

    # Ensure setup and draw exist
    if "setup" not in repaired and "createCanvas" not in repaired:
        repaired = "function setup() { createCanvas(windowWidth, windowHeight); }\n" + repaired
        
    return repaired

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
    window.onerror = function(msg, url, line) {{
      console.error("WindowError Line " + line + ": " + msg);
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
        if level.name in ['ErrorMessage', 'CriticalMessage'] or 'Uncaught' in message:
            self.err_callback(f"Console Line {lineNumber}: {message}")

def log_errors_to_file(title, url, errors):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n========================================\n")
        f.write(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Title: {title}\n")
        f.write(f"URL: {url}\n")
        f.write(f"Errors:\n")
        for err in errors:
            f.write(f"  - {err}\n")

def test_run_module(web_view, html_path):
    js_errors = []
    page = QWebEngineTester(lambda msg: js_errors.append(msg))
    web_view.setPage(page)
    
    # Load and wait 800ms
    loop = QEventLoop()
    web_view.loadFinished.connect(lambda ok: loop.quit())
    web_view.setUrl(QUrl.fromLocalFile(html_path))
    
    QTimer.singleShot(800, loop.quit)
    loop.exec()
    
    # Give it another 300ms to execute draw() and catch errors
    loop_wait = QEventLoop()
    QTimer.singleShot(300, loop_wait.quit)
    loop_wait.exec()
    
    page.deleteLater()
    
    # Process events to allow QWebEngine view to finalize
    app = QApplication.instance()
    app.processEvents()
    
    return list(set(js_errors))

def main():
    app = QApplication(sys.argv)
    
    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"❌ Custom visuals directory not found: {CUSTOM_VISUALS_DIR}")
        return
        
    json_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json")]
    json_files.sort()
    
    total = len(json_files)
    print(f"🔍 Found {total} visual modules in custom_visuals/.")
    
    web_view = QWebEngineView()
    web_view.resize(1280, 720)
    
    temp_html_path = os.path.join(WORKSPACE_DIR, "_temp_qc_test.html")
    
    broken_modules = []
    repaired_modules = []
    healthy_modules_count = 0
    
    for idx, fname in enumerate(json_files):
        fpath = os.path.join(CUSTOM_VISUALS_DIR, fname)
        
        # Read JSON
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[{idx+1}/{total}] ❌ Failed to parse JSON {fname}: {e}")
            continue
            
        code = data.get("code", "")
        custom_css = data.get("custom_css", "")
        custom_html = data.get("custom_html", "")
        title = data.get("title", fname)
        url = data.get("url", "N/A")
        
        # Build temp HTML and test run
        html_content = make_test_html(code, custom_css, custom_html)
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        errors = test_run_module(web_view, temp_html_path)
        
        if len(errors) == 0:
            healthy_modules_count += 1
            # Print brief progress indicator
            if (idx + 1) % 50 == 0 or idx == total - 1:
                print(f"Progress: [{idx+1}/{total}] checked. Healthy: {healthy_modules_count}, Repaired: {len(repaired_modules)}, Broken: {len(broken_modules)}")
            continue
            
        # Log detected errors
        log_errors_to_file(title, url, errors)
        
        # Attempt repair
        print(f"[{idx+1}/{total}] ⚠️ Errors in '{title}' ({fname}): {errors}. Attempting auto-repair...")
        repaired_code = try_repair_code(code, errors)
        
        # Test run repaired code
        repaired_html_content = make_test_html(repaired_code, custom_css, custom_html)
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(repaired_html_content)
            
        post_errors = test_run_module(web_view, temp_html_path)
        
        if len(post_errors) == 0:
            print(f"  ✨ SUCCESS! Repaired module '{title}' is now running error-free.")
            # Save back
            data["code"] = repaired_code
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            repaired_modules.append({
                "file": fname,
                "title": title,
                "original_errors": errors
            })
        else:
            print(f"  ❌ Repair failed. Post-repair errors: {post_errors}")
            broken_modules.append({
                "file": fname,
                "title": title,
                "errors": post_errors
            })

    # Cleanup temp html
    if os.path.exists(temp_html_path):
        try: os.remove(temp_html_path)
        except Exception: pass
        
    # Write summary report JSON for reference
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
    print("✅ SCAN AND QC VERIFICATION COMPLETED!")
    print(f"Total Visual Modules Scanned: {total}")
    print(f"Initially Healthy: {healthy_modules_count}")
    print(f"Automatically Repaired: {len(repaired_modules)}")
    print(f"Still Broken (Manual Action Required): {len(broken_modules)}")
    print(f"Errors appended to: {LOG_FILE}")
    print("="*50)

if __name__ == "__main__":
    main()
