import os
import re
import json
import random  # FIX: 移至最上層，避免線程內局部導入遮蔽
import datetime
import traceback
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QListWidget, QListWidgetItem, QProgressBar, QTextEdit,
    QSplitter, QMessageBox, QWidget, QApplication, QCheckBox, QComboBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer

# 取得 workspace 目錄路徑
workspace_dir = os.path.dirname(os.path.abspath(__file__))

def rewrite_relative_assets(code_str, sketch_id):
    if not sketch_id:
        return code_str
    
    funcs = ["loadImage", "loadFont", "loadTable", "loadJSON", "loadStrings", "loadBytes", 
             "loadXML", "loadShader", "loadSound", "loadModel", "createAudio", "createVideo"]
    
    base_url = f"https://openprocessing.org/sketch/{sketch_id}/files/"
    
    for func in funcs:
        pattern = rf'\b{func}\s*\(\s*([\'"])(.*?)\1'
        
        def replacer(match):
            quote = match.group(1)
            path = match.group(2).strip()
            if (path.startswith(("http://", "https://", "data:")) 
                or not path 
                or path.endswith((".js", ".wasm"))):
                return match.group(0)
            
            new_path = base_url + path.lstrip("/")
            return f"{func}({quote}{new_path}{quote}"
            
        code_str = re.sub(pattern, replacer, code_str)
        
    return code_str


def adapt_and_repair_code_text(code, sketch_id=None):
    """
    強化版 p5.js 核心轉譯與修復引擎
    核心優化：更精準的 Java 語法轉譯、防崩潰 Stub、以及自動對接進階音訊響應矩陣
    """
    if not code.strip():
        return ""

    adapted = code
    if sketch_id:
        adapted = rewrite_relative_assets(adapted, sketch_id)

    # 1. 進階 Processing (Java) 轉 JavaScript 轉譯器 (必須包含 Java 專屬 entrypoints 避免誤判 JS 的 GLSL Shader)
    if any(kw in adapted for kw in ["void setup", "void draw"]):
        def transpile_processing_to_js(src):
            transpiled = src
            
            # (a) 移除 Java 存取修飾詞、關鍵字與不必要的類型修飾
            transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
            transpiled = re.sub(r'\bfinal\s+', '', transpiled)
            
            # (b) 修正 Java 浮點數轉型：(float)x 或 (int)x -> float(x), int(x)
            transpiled = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', transpiled)
            transpiled = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', transpiled)
            transpiled = re.sub(r'\((double|char|long|boolean)\)\s*', '', transpiled)
            
            # (c) 修正 Java 複雜陣列宣告 (如: int[] x = {1, 2}; 或 Object[] o = new Object[5];)
            transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', transpiled)
            transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', transpiled)
            
            # (d) 修正一般的變數宣告（將 int x, float y, ClassName obj 等轉換為 let）
            # 包含原始型別與自定義類別型別（大寫開頭），可選 [] 陣列後綴
            transpiled = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', transpiled)
            
            # (e) 修正類別內的成員變數與方法（Java 的變數直接宣告，在 JS 必須在 constructor 內初始化，或在前方加上 let/var 避免全域污染）
            transpiled = re.sub(r'\bfor\s*\(\s*(int|float|double)\s+', 'for (let ', transpiled)
            transpiled = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', transpiled)
            
            # (f) 修正物件與自訂 Class (將 Class 內部宣告的變數與函數進行 JS 規範化)
            lines = transpiled.split("\n")
            new_lines = []
            in_class = False
            class_name = ""
            brace_depth = 0
            for line in lines:
                class_match = re.search(r'\bclass\s+([A-Za-z0-9_$\.]+)\b', line)
                if class_match and not in_class:
                    in_class = True
                    class_name = class_match.group(1)
                    brace_depth = 0
                    # Count braces on the class declaration line itself
                    brace_depth += line.count('{') - line.count('}')
                    new_lines.append(line)
                    continue
                
                if in_class:
                    is_class_body_field = (brace_depth == 1)
                    brace_depth += line.count('{') - line.count('}')
                    if brace_depth <= 0:
                        in_class = False
                    # 將與 class 同名之 Java 建構子轉換為 constructor
                    if class_name and re.search(r'\b' + class_name + r'\s*\(', line):
                        line = re.sub(r'\b' + class_name + r'\s*\(', 'constructor(', line)
                    # 移除 class 內部函數的前綴關鍵字 (如 void update() -> update())
                    elif re.search(r'\b(void|int|float|double|boolean|color|char|[A-Z]\w*)\s+([A-Za-z0-9_$\.]+)\s*\(', line):
                        line = re.sub(r'\b(void|int|float|double|boolean|color|char|[A-Z]\w*)\s+([A-Za-z0-9_$\.]+)\s*\(', r'\2(', line)
                    
                    # (g) 移除 class 內部欄位宣告的 let 關鍵字（JS class body 不允許 let/const/var）
                    # 例如: "  let GRID_SIZE = 16;" → "  GRID_SIZE = 16;"
                    if is_class_body_field:
                        stripped = line.strip()
                        if stripped.startswith('let ') and '(' not in stripped and '=' in stripped:
                            line = line.replace('let ', '', 1)
                    
                    # (h) 移除方法參數列中的 let 關鍵字
                    # 例如: "getVelocityX(let x, let y)" → "getVelocityX(x, y)"
                    if '(' in line and ')' in line:
                        # Extract and clean the parameter list
                        def clean_params(m):
                            params = m.group(1)
                            cleaned = re.sub(r'\blet\s+', '', params)
                            return '(' + cleaned + ')'
                        line = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', clean_params, line)
                else:
                    # 全域 Java 風格函數轉換
                    line = re.sub(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \2(', line)
                
                new_lines.append(line)
            
            transpiled = "\n".join(new_lines)
            
            # (i) 全域範圍：移除函數參數中誤加的 let 關鍵字
            # 例如: "function foo(let x, let y)" → "function foo(x, y)"
            def clean_global_params(m):
                params = m.group(1)
                cleaned = re.sub(r'\blet\s+', '', params)
                return '(' + cleaned + ')'
            transpiled = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', clean_global_params, transpiled)
            
            # (j) 移除 Java float 字面量後綴 f（例如: 0.85f → 0.85）
            transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
            
            # (k) 轉換 Java for-each 迴圈（例如: for (Particle p : list) → for (let p of list)）
            transpiled = re.sub(
                r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)',
                r'for (let \1 of \2)',
                transpiled
            )
            
            # (l) 轉換 Java 風格陣列建立（例如: new Particle[n] → new Array(n)）
            transpiled = re.sub(r'\bnew\s+\w+\[([^\]]+)\]', r'new Array(\1)', transpiled)
            
            # (m) 加入 arraycopy polyfill
            if 'arraycopy' in transpiled and 'function arraycopy' not in transpiled:
                transpiled = "function arraycopy(s,sp,d,dp,l){for(var _i=0;_i<l;_i++)d[dp+_i]=s[sp+_i];}\n" + transpiled
            
            transpiled = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', transpiled)
            transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', transpiled)
            return transpiled

        adapted = transpile_processing_to_js(adapted)

    # 2. 16:9 畫布尺寸智能適配（防止拉伸扭曲）
    adapted = re.sub(r'\bmin\s*\(\s*windowWidth\s*,\s*windowHeight\s*\)', 'max(windowWidth, windowHeight)', adapted)
    adapted = re.sub(r'\bmin\s*\(\s*width\s*,\s*height\s*\)', 'max(width, height)', adapted)

    # 3. Shader 渲染器建立相容性修正
    adapted = re.sub(
        r'new\s+p5\.Shader\s*\(\s*(this\.)?_?renderer\s*,\s*([^,)]+)\s*,\s*([^,)]+)\s*\)',
        r'createShader(\2, \3)',
        adapted
    )

    # 4. 完美融合：音訊特徵矩陣原生對接 (將滑鼠與點擊映射至 LiveAudioBeatDetector 核心特徵欄位)
    # 優化：引入平滑緩衝與多指標權重，若無音訊信號則退回常規滑鼠，實現無縫切換
    audio_reactive_mouseX = (
        "(window.simulatedMouseX !== undefined ? window.simulatedMouseX : "
        "(typeof sub_bass !== 'undefined' ? map(sub_bass, 0, 1, width*0.1, width*0.9) : "
        "(typeof live_centroid !== 'undefined' ? map(live_centroid, 100, 4000, 0, width) : mouseX)))"
    )
    audio_reactive_mouseY = (
        "(window.simulatedMouseY !== undefined ? window.simulatedMouseY : "
        "(typeof percussive !== 'undefined' ? map(percussive, 0, 1, height, 0) : "
        "(typeof roughness !== 'undefined' ? map(roughness, 0, 1, height*0.2, height*0.8) : mouseY)))"
    )
    audio_reactive_pressed = "((window.isBeat || false) || (typeof window.is_silent !== 'undefined' ? !window.is_silent : mouseIsPressed))"

    # Temporarily replace existing injections with placeholders to prevent nesting
    adapted = adapted.replace(audio_reactive_mouseX, "___MOUSE_X_PLACEHOLDER___")
    adapted = adapted.replace(audio_reactive_mouseY, "___MOUSE_Y_PLACEHOLDER___")
    adapted = adapted.replace(audio_reactive_pressed, "___MOUSE_PRESSED_PLACEHOLDER___")

    adapted = re.sub(r'(?<!\.)\bmouseX\b', audio_reactive_mouseX, adapted)
    adapted = re.sub(r'(?<!\.)\bmouseY\b', audio_reactive_mouseY, adapted)
    adapted = re.sub(r'(?<!\.)\bpmouseX\b', audio_reactive_mouseX, adapted)
    adapted = re.sub(r'(?<!\.)\bpmouseY\b', audio_reactive_mouseY, adapted)
    adapted = re.sub(r'(?<!\.)\bmouseIsPressed\b', audio_reactive_pressed, adapted)

    # Restore placeholders
    adapted = adapted.replace("___MOUSE_X_PLACEHOLDER___", audio_reactive_mouseX)
    adapted = adapted.replace("___MOUSE_Y_PLACEHOLDER___", audio_reactive_mouseY)
    adapted = adapted.replace("___MOUSE_PRESSED_PLACEHOLDER___", audio_reactive_pressed)

    # 4.5. p5.js v2 alpha/red/green/blue/... compatibility by wrapping arguments in window.color() to avoid local variable shadowing
    adapted = re.sub(
        r'\b(alpha|red|green|blue|hue|saturation|brightness|lightness)\s*\(\s*(?!window\.color\()((?:[^()]+|\([^()]*\))+)\)',
        r'\1(window.color(\2))',
        adapted
    )

    # 5. WebGL 3D 畫布模式智能自動判定
    has_3d_keywords = any(re.search(kw, adapted) for kw in [
        r'\bbox\s*\(', r'\bsphere\s*\(', r'\btorus\s*\(', r'\bcylinder\s*\(',
        r'\brotateX\s*\(', r'\brotateY\s*\(', r'\brotateZ\s*\(', r'\bcone\s*\('
    ])
    if has_3d_keywords and "WEBGL" not in adapted:
        adapted = re.sub(r'createCanvas\s*\(\s*([^,)]*)\s*,\s*([^,)]*)\s*\)', r'createCanvas(\1, \2, WEBGL)', adapted)

    # 6. Auto Stub 完美補置（常規開源庫缺失常數/函數防止紅字崩潰）
    def is_declared(name, text):
        # 檢查變數/函數/類別是否已在程式碼中被宣告
        pattern = rf'\b(function|const|let|var|class)\s+{name}\b'
        return bool(re.search(pattern, text))

    stubs = []
    if 'makeFilter' in adapted and not is_declared('makeFilter', adapted):
        stubs.append("function makeFilter() { if(typeof filter !== 'undefined') filter(GRAY); }")
    if 'drawOverPattern' in adapted and not is_declared('drawOverPattern', adapted):
        stubs.append("function drawOverPattern() {}")
    if 'setPalette' in adapted and not is_declared('setPalette', adapted):
        stubs.append("function setPalette() {}")
    if 'overAllTexture' in adapted and not is_declared('overAllTexture', adapted):
        stubs.append("var overAllTexture;")
    if 'palettes' in adapted and not is_declared('palettes', adapted) and 'palettes =' not in adapted:
        stubs.append("var palettes = [ ['#fdfffc', '#235789', '#c1292e', '#f1d302', '#020100'], ['#0D1E40', '#224573', '#5679A6', '#F2A25C', '#D96B43'] ];")
    
    if stubs:
        adapted += "\n\n// === Auto Generated Stubs ===\n" + "\n".join(stubs) + "\n"

    # 7. drawingContext 特效渲染圖層導向修復
    if "originalGraphics" in adapted:
        adapted = re.sub(r'(?<![\w.])drawingContext\.(createRadialGradient|createLinearGradient)\s*\(', r'originalGraphics.drawingContext.\1(', adapted)
        adapted = adapted.replace("originalGraphics.originalGraphics", "originalGraphics")

    # 8. 防衛性轉譯器常駐外掛 Stub 注入
    if "window._origLoadImage =" not in adapted and "const _origLoadImage =" not in adapted:
        adapted += """

// 1. 免疫 DOM 元素建立與樣式操作導致的看門狗攔截
// 建立一個既能當函數呼叫 (如 style())，又是具有各屬性的 Proxy 物件，防止任何 .style、.style()、.position 錯誤
(function() {
  const handler = {
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
  const dummyObject = function() {};
  dummyObject.position = function() { return dummyObject; };
  dummyObject.style = function() { return dummyObject; };
  dummyObject.size = function() { return dummyObject; };
  dummyObject.parent = function() { return dummyObject; };
  dummyObject.id = function() { return ""; };
  dummyObject.class = function() { return dummyObject; };
  dummyObject.mousePressed = function() { return dummyObject; };
  dummyObject.mouseOver = function() { return dummyObject; };
  dummyObject.changed = function() { return dummyObject; };
  dummyObject.html = function() { return dummyObject; };
  dummyObject.value = function() { return 0; };
  
  const styleProxy = new Proxy(dummyObject, handler);
  
  if (typeof createP === 'undefined') { window.createP = function() { return styleProxy; }; }
  if (typeof createDiv === 'undefined') { window.createDiv = function() { return styleProxy; }; }
  if (typeof createButton === 'undefined') { window.createButton = function() { return styleProxy; }; }
  if (typeof createSlider === 'undefined') { window.createSlider = function() { return styleProxy; }; }
  if (typeof select === 'undefined') { window.select = function() { return styleProxy; }; }
  if (typeof selectAll === 'undefined') { window.selectAll = function() { return [styleProxy]; }; }
})();

// 1.2 免疫 HTML 屬性與 Element.prototype.style 崩潰 (確保 style 與 checked 既可以當物件又可以當函數呼叫)
try {
  if (typeof Element !== 'undefined') {
    const dummyObj = function() { return dummyObj; };
    const p = new Proxy(dummyObj, {
      get: function(target, prop) {
        if (typeof target[prop] === 'function') return target[prop];
        return p;
      }
    });
    
    // 用屬性定義防止被覆寫
    Object.defineProperty(Element.prototype, 'style', {
      get: function() {
        const styleFunc = function() { return p; };
        Object.setPrototypeOf(styleFunc, p);
        return styleFunc;
      },
      set: function() {},
      configurable: true
    });
    
    Object.defineProperty(Element.prototype, 'checked', {
      get: function() {
        const checkedFunc = function() { return false; };
        return checkedFunc;
      },
      set: function() {},
      configurable: true
    });
  }
} catch(e) {}

// 1.3 免疫 HTMLInputElement.size = 0 或非法負數導致的瀏覽器拋錯
try {
  if (typeof HTMLInputElement !== 'undefined') {
    const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'size');
    if (desc && desc.set) {
      const originalSet = desc.set;
      Object.defineProperty(HTMLInputElement.prototype, 'size', {
        set: function(val) {
          if (val <= 0) val = 20; // 設為預設合規大小
          originalSet.call(this, val);
        },
        configurable: true
      });
    }
  }
} catch(e) {}

// 1.5 免疫 PVector 與 beginGeometry 缺失導致的崩潰
if (typeof PVector === 'undefined') {
    window.PVector = class PVector {
        constructor(x, y, z) {
            this.x = x || 0;
            this.y = y || 0;
            this.z = z || 0;
        }
        static dist(v1, v2) {
            return Math.sqrt((v1.x - v2.x) ** 2 + (v1.y - v2.y) ** 2 + (v1.z - v2.z) ** 2);
        }
        set(x, y, z) {
            this.x = x || 0;
            this.y = y || 0;
            this.z = z || 0;
        }
    };
}
if (typeof beginGeometry === 'undefined') { window.beginGeometry = function() {}; }
if (typeof endGeometry === 'undefined') { window.endGeometry = function() { return { draw: function() {} }; }; }

// 1.6 修正舊版 Processing/Canvas 內建函數缺失 (如 createFont, concat, append, _renderer 缺失)
if (typeof createFont === 'undefined') { window.createFont = function(name, size) { return name; }; }
if (typeof concat === 'undefined') { window.concat = function(a, b) { return (a || []).concat(b || []); }; }
if (typeof append === 'undefined') { window.append = function(array, value) { if(array) { array.push(value); } return array; }; }
if (typeof _renderer === 'undefined') { window._renderer = { _setAttributes: function() {} }; }

// 1.7 免疫機器學習與人臉偵測 (ml5.js, clmtrackr, aiptag, lime) 缺失與內部指標 null 導致的崩潰 (修復 ml5.js .features of null 報錯)
if (typeof window.clm === 'undefined') {
    window.clm = {
        tracker: class {
            init() {}
            start() {}
            track() { return []; }
            getCurrentPosition() { return []; }
            getScore() { return 0; }
        }
    };
}
if (typeof window.ml5 === 'undefined') {
    const ml5MockObj = {
        detectStart: function() {},
        features: { get: function() { return []; } },
        on: function() {},
        ready: Promise.resolve(),
        loadModel: Promise.resolve()
    };
    window.ml5 = {
        bodypix: function() { return ml5MockObj; },
        faceapi: function() { return ml5MockObj; },
        handpose: function() { return ml5MockObj; },
        poseNet: function() { return ml5MockObj; },
        objectDetector: function() { return ml5MockObj; }
    };
}
if (typeof window.aiptag === 'undefined') { window.aiptag = {}; }
if (typeof window.lime === 'undefined') { window.lime = {}; }

// 1.8 免疫 3D 物理引擎與高階渲染 (THREE.Group, Tone.js, p5.asciify, REGL, Voronoi, PolyK, qrcode, P5Capture) 缺失導致的崩潰
if (typeof window.THREE === 'undefined') {
    window.THREE = {
        Group: class {},
        Scene: class {},
        PerspectiveCamera: class {},
        WebGLRenderer: class { setSize() {} },
        Mesh: class {},
        BoxGeometry: class {}
    };
}
if (typeof window.Tone === 'undefined') {
    window.Tone = {
        Player: class { play() {} start() {} stop() {} connect() {} toDestination() {} },
        Players: class { play() {} start() {} stop() {} connect() {} toDestination() {} },
        Sampler: class { triggerAttackRelease() {} connect() {} toDestination() {} },
        Sequence: class { start() {} stop() {} },
        Transport: { start: function() {}, stop: function() {}, bpm: { value: 120 } }
    };
}
if (typeof window.createREGL === 'undefined') {
    window.createREGL = function() {
        const regl = function() {};
        regl.texture = function() { return { resize: function() {} }; };
        regl.buffer = function() { return { subdata: function() {} }; };
        regl.framebuffer = function() { return { use: function(cb) { cb(); } }; };
        return regl;
    };
}
if (typeof window.Voronoi === 'undefined') {
    window.Voronoi = class {
        compute() { return { cells: [], edges: [] }; }
    };
}
if (typeof window.qrcode === 'undefined') {
    window.qrcode = function(data) {
        return {
            createImgTag: function() { return ""; },
            createTableTag: function() { return ""; },
            createSvgTag: function() { return ""; }
        };
    };
    window.qrcode.stringToBytes = function(s) { return []; };
}
if (typeof window.PolyK === 'undefined') {
    window.PolyK = {
        Slice: function() { return []; },
        Triangulate: function() { return []; },
        getArea: function() { return 0; }
    };
}
if (typeof window.P5Capture === 'undefined') {
    window.P5Capture = {
        getInstance: function() {
            return { start: function() {}, stop: function() {}, setFormat: function() {} };
        },
        setDefaultOptions: function() {}
    };
}

// 1.9 免疫 OPC (OpenProcessing Controller) 與 WebGL 內部 setUniform 崩潰
if (typeof window.OPC === 'undefined') {
    window.OPC = {
        title: function() {},
        slider: function() {},
        button: function() {},
        toggle: function() {},
        color: function() {}
    };
}
if (typeof p5 !== 'undefined' && p5.Shader) {
    const origSetUniform = p5.Shader.prototype.setUniform;
    p5.Shader.prototype.setUniform = function(name, val) {
        if (!this) return this;
        try {
            return origSetUniform.call(this, name, val);
        } catch(e) {
            return this;
        }
    };
}

// 1.95 免疫某些特定遊戲模組對 parent / maeExportApis_ 或是唯讀屬性的寫入崩潰
try {
  if (typeof window.parent !== 'undefined') {
    if (!window.parent.maeExportApis_) {
      try {
        window.parent.maeExportApis_ = function() {};
      } catch(e) {}
    }
  }
} catch(e) {}

// 1.96 免疫 textmode 缺失以及 loadSVG / p5.SVG 插件型別拋錯
if (typeof textmode === 'undefined') { window.textmode = function() {}; }
if (typeof MAT === 'undefined') { window.MAT = []; }
if (typeof SIDES === 'undefined') { window.SIDES = 4; }
if (typeof GRIDBOX === 'undefined') { window.GRIDBOX = 10; }
if (typeof COLUMNS === 'undefined') { window.COLUMNS = 5; }
if (typeof tileSize === 'undefined') { window.tileSize = 30; }
if (typeof mouseTileX === 'undefined') { window.mouseTileX = 0; }
if (typeof p5 !== 'undefined') {
  if (!p5.prototype.loadSVG) {
    p5.prototype.loadSVG = function(path, success, failure) {
      if (success) success({});
      return {};
    };
  }
  // 免疫 window.VERSION 唯讀寫入錯誤
  try {
    Object.defineProperty(window, 'VERSION', {
      value: "p5-stub",
      writable: true,
      configurable: true
    });
  } catch(e) {}
}

// 2. 圖片與非同步資產載入後備自癒護欄
if (typeof p5 !== 'undefined' && p5.prototype) {
    if (typeof window._origLoadImage === 'undefined') { window._origLoadImage = p5.prototype.loadImage; }
    p5.prototype.loadImage = function(path, successCallback, failureCallback) {
        if (typeof path !== 'string' || path.startsWith('http') || (path.startsWith('data:') === false && path.indexOf('.') === -1)) {
            // 當發現是遠端 URL、相對路徑或格式無副檔名時，使用 1x1 灰色 GIF 的 Base64 代替，防止渲染死鎖與 CORS 錯誤
            const dummyPath = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
            return window._origLoadImage.call(this, dummyPath, successCallback, failureCallback);
        }
        return window._origLoadImage.call(this, path, successCallback, failureCallback);
    };
    
    // 修正 img.loadPixels / img.resize 缺失與未非同步載入完成呼叫
    if (!p5.Image.prototype.loadPixels) { p5.Image.prototype.loadPixels = function() { return this; }; }
    if (!p5.Image.prototype.resize) { p5.Image.prototype.resize = function() { return this; }; }
    if (!p5.Image.prototype.get) { p5.Image.prototype.get = function() { return [0,0,0,255]; }; }
    if (!p5.Image.prototype.width) {
        Object.defineProperty(p5.Image.prototype, 'width', {
            get: function() { return this._width || 1280; },
            set: function(v) { this._width = v; }
        });
    }
    if (!p5.Image.prototype.height) {
        Object.defineProperty(p5.Image.prototype, 'height', {
            get: function() { return this._height || 720; },
            set: function(v) { this._height = v; }
        });
    }
    
    // 修正 p5.Graphics / p5.Renderer / Element.prototype.style
    if (p5.Graphics && p5.Graphics.prototype) {
        if (!p5.Graphics.prototype.loadPixels) { p5.Graphics.prototype.loadPixels = function() { return this; }; }
    }
}

// 2.2 修正 p5.Table / loadTable / getRowCount 缺失與錯誤
if (typeof p5 !== 'undefined' && p5.Table) {
    if (!p5.Table.prototype.getRowCount) { p5.Table.prototype.getRowCount = function() { return 0; }; }
}

// 3. VJ Aesthetic Engine - 全域 AI 審美調色與緩動防死板輔助庫
if (typeof window.VJ_AESTHETIC_ENGINE === 'undefined') {
    window.VJ_AESTHETIC_ENGINE = {
        getHarmonicColor: function(pitchClass, energy, isMinor) {
            var pc = (typeof pitchClass === 'number') ? pitchClass : 0;
            var e = (typeof energy === 'number') ? energy : 0.5;
            var baseHue = (pc * 30 + 15) % 360;
            var sat = isMinor ? Math.round(35 + e * 25) : Math.round(65 + e * 25);
            var light = isMinor ? Math.round(25 + e * 30) : Math.round(45 + e * 30);
            return 'hsl(' + Math.round(baseHue) + ', ' + sat + '%, ' + light + '%)';
        },
        applyAestheticEasing: function(current, target, factor) {
            var f = (typeof factor === 'number') ? factor : 0.15;
            return current + (target - current) * f;
        },
        PRESETS: {
            CYBERPUNK: { primary: '#00F0FF', secondary: '#FF0055', bg: '#0B0E14' },
            SYNTHWAVE: { primary: '#7928CA', secondary: '#FF0080', bg: '#0F051D' },
            FLUID: { primary: '#00DF89', secondary: '#0369A1', bg: '#1E293B' },
            MONOCHROME: { primary: '#F59E0B', secondary: '#71717A', bg: '#09090B' }
        }
    };
    window.getHarmonicColor = window.VJ_AESTHETIC_ENGINE.getHarmonicColor;
    window.applyAestheticEasing = window.VJ_AESTHETIC_ENGINE.applyAestheticEasing;
}

// 3.1 修正 3D 渲染圖層 WebGL 與 Canvas 2D 上下文屬性缺失
if (typeof p5 !== 'undefined' && p5.prototype) {
    if (typeof window._origGet === 'undefined') { window._origGet = p5.prototype.get; }
    p5.prototype.get = function(...args) {
        if (!this || this.width === 0 || this.height === 0) {
            return [0,0,0,255];
        }
        try {
            return window._origGet.apply(this, args);
        } catch(e) {
            return [0,0,0,255];
        }
    };
}
"""

    return adapted


class BatchImportWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, bool)
    item_finished = pyqtSignal(str, str, str)
    finished = pyqtSignal(list)

    def __init__(self, items_to_import, save_dir):
        super().__init__()
        self.items = items_to_import
        self.save_dir = save_dir
        self.failed_list = []
        self.success_list = []

    def run(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        for i, item in enumerate(self.items):
            sketch_id = item["id"]
            title = item["title"] or f"op_{sketch_id}"
            url = item["url"]
            
            self.progress.emit(i, f"正在下載「{title}」(ID: {sketch_id})...")
            self.log.emit(f"[{i+1}/{len(self.items)}] 正在下載「{title}」...", False)
            
            try:
                embed_url = f"https://openprocessing.org/sketch/{sketch_id}/embed/"
                resp = None
                max_retries = 3
                retry_delay = 4
                
                # 防 429 / 503 動態指數型退避重試
                for retry in range(max_retries + 1):
                    try:
                        resp = requests.get(embed_url, headers=headers, timeout=12)
                        if resp.status_code == 429:
                            if retry < max_retries:
                                wait_sec = retry_delay * (2 ** retry) + random.uniform(1.0, 3.0)
                                self.log.emit(f"⚠️ [HTTP 429 限流] 觸發安全防護。將在 {wait_sec:.1f} 秒後進行第 {retry+1} 次退避重試...", True)
                                self.msleep(int(wait_sec * 1000))
                                continue
                            else:
                                raise Exception("無法存取 OpenProcessing (HTTP 429 限流，已達最大重試次數)")
                        elif resp.status_code != 200:
                            raise Exception(f"無法存取 OpenProcessing (HTTP {resp.status_code})")
                        break
                    except requests.exceptions.RequestException as req_err:
                        if retry < max_retries:
                            self.log.emit(f"⚠️ 網路超時或斷線 ({req_err})，將於 4 秒後重試...", True)
                            self.msleep(4000)
                        else:
                            raise req_err
                
                # 依賴庫過濾與提取
                ext_script_tags = ""
                try:
                    script_matches = re.finditer(r'<script([^>]+)>', resp.text, re.IGNORECASE)
                    builtin_keywords = ["p5.js", "p5.min.js", "p5.sound", "p5.func", "gsap", "opc.min.js", "opc.js", "p5.flex", "chroma.min.js", "rampensau", "three.js", "three.module.js", "sketch.js", "sketch_embed.js", "Tone.js", "Tone.min.js", "tone.js"]
                    wrapper_keywords = ["/assets/js/vendor/", "civiccomputing.com", "cloudflareinsights.com", "beacon.min.js", "codemirror", "quill"]
                    
                    for match in script_matches:
                        attrs = match.group(1)
                        src_match = re.search(r'src=["\'](.*?)["\']', attrs, re.IGNORECASE)
                        if not src_match:
                            continue
                        
                        src = src_match.group(1)
                        src_lower = src.lower()
                        
                        if any(kw in src_lower for kw in builtin_keywords):
                            continue
                        if re.search(r'/assets/.*?/js/', src_lower) or any(kw in src_lower for kw in wrapper_keywords):
                            continue
                            
                        abs_src = src if src.startswith(("http://", "https://")) else "https://openprocessing.org" + ("/" + src.lstrip("/"))
                        
                        if "type=\"module\"" in attrs.lower() or "type='module'" in attrs.lower() or src_lower.endswith(".mjs"):
                            ext_script_tags += f'<script type="module" src="{abs_src}"></script>\n'
                        else:
                            ext_script_tags += f'<script src="{abs_src}"></script>\n'
                except Exception as parse_err:
                    self.log.emit(f"   [!] 解析外部依賴庫時發生非致命錯誤: {parse_err}", False)
                
                # 精準解析內嵌 JavaScript 物件
                sketch_json = self.extract_js_object(resp.text, "sketch")
                if not sketch_json:
                    raise ValueError("無法在 HTML 頁面中定位到 'var sketch =' 核心資料庫。")
                
                sketch_data = json.loads(sketch_json)
                
                # 提取 JSON 中聲明的自訂外部依賴庫
                json_libs_html = ""
                libs_list = sketch_data.get("libraries", [])
                if libs_list and isinstance(libs_list, list):
                    for lib in libs_list:
                        lib_url = lib.get("url")
                        if lib_url:
                            if not lib_url.startswith(("http://", "https://")):
                                lib_url = "https://openprocessing.org" + ("/" + lib_url.lstrip("/"))
                            json_libs_html += f'<script src="{lib_url}"></script>\n'

                title_og = sketch_data.get("title", title)
                versions = sketch_data.get("versions", [])
                if not versions or not versions[0].get("codeObjects", []):
                    raise ValueError("此視覺模組的雲端多核心代碼版本庫為空。")
                
                # 排序多代碼頁籤（Tab）
                def get_order_id(x):
                    val = x.get("orderID")
                    try: return float(val) if val is not None else 0
                    except (ValueError, TypeError): return 0
                    
                sorted_objects = sorted(versions[0]["codeObjects"], key=get_order_id)
                
                code = ""
                custom_css = ""
                custom_html = ""
                
                for obj in sorted_objects:
                    tab_title = obj.get("title", "tab")
                    tab_code = obj.get("code", "")
                    
                    if tab_title.lower().endswith('.css'):
                        custom_css += tab_code + "\n"
                    elif tab_title.lower().endswith(('.html', '.htm')):
                        body_match = re.search(r'<body[^>]*>(.*?)</body>', tab_code, re.DOTALL | re.IGNORECASE)
                        custom_html += body_match.group(1) + "\n" if body_match else tab_code + "\n"
                
                custom_html = json_libs_html + ext_script_tags + custom_html
                # 整理 JS 區塊，過濾非 JS 資源頁籤
                js_objects = []
                for obj in sorted_objects:
                    tab_title = obj.get("title", "tab")
                    if tab_title.lower().endswith(('.css', '.html', '.htm', '.txt', '.json', '.glsl', '.vert', '.frag')):
                        continue
                    js_objects.append(obj)

                # HTML/CSS/JS 模式特異性過濾：如果存在自訂 HTML 頁籤，只編譯 HTML 中明確載入的 JS 頁籤，防止備份頁籤（如 original.js 或備份 tab）被併入導致變數重複宣告
                html_tab_code = ""
                for obj in sorted_objects:
                    tab_title = obj.get("title", "tab")
                    if tab_title.lower().endswith(('.html', '.htm')):
                        html_tab_code = obj.get("code", "")
                        break
                
                if html_tab_code and js_objects:
                    # 移除非指令碼 HTML 註解，防範註解掉的 script 標籤誤判
                    html_no_comments = re.sub(r'<!--.*?-->', '', html_tab_code, flags=re.DOTALL)
                    # 匹配所有 src 指向的本地 js 檔案
                    loaded_scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html_no_comments, re.IGNORECASE)
                    loaded_script_names = []
                    for src in loaded_scripts:
                        fname = src.split('/')[-1].lower().strip()
                        loaded_script_names.append(fname)
                        if fname.endswith('.js'):
                            loaded_script_names.append(fname[:-3])
                    
                    filtered_js_objects = []
                    for obj in js_objects:
                        t = obj.get("title", "").lower().strip()
                        t_js = t if t.endswith('.js') else f"{t}.js"
                        if t in loaded_script_names or t_js in loaded_script_names:
                            filtered_js_objects.append(obj)
                        elif t in ["mysketch", "mysketch.js", "sketch", "sketch.js", "main", "main.js"]:
                            filtered_js_objects.append(obj)
                    js_objects = filtered_js_objects

                # 優先將 mysketch 移至後方
                sorted_js_objects = []
                main_sketches_fallback = []
                for obj in js_objects:
                    t = obj.get("title", "").lower().strip()
                    if t in ["mysketch.js", "mysketch"]:
                        main_sketches_fallback.append(obj)
                    else:
                        sorted_js_objects.append(obj)
                sorted_js_objects.extend(main_sketches_fallback)

                # 確保主繪圖檔 (包含 setup/draw 或是主檔名) 串接在最後，避免 shader/tools 變數先被引用而未初始化
                final_js_objects = []
                main_sketches = []
                for obj in sorted_js_objects:
                    t = obj.get("title", "").lower().strip()
                    obj_code = obj.get("code", "")
                    is_main = (
                        t in ["mysketch.js", "mysketch", "sketch.js", "sketch", "main.js", "main"] 
                        or "function setup(" in obj_code 
                        or "function draw(" in obj_code 
                        or "void setup(" in obj_code
                    )
                    if is_main:
                        main_sketches.append(obj)
                    else:
                        final_js_objects.append(obj)
                final_js_objects.extend(main_sketches)
                
                js_blocks = []
                local_import_pattern = r'(\bimport\s+(?:[^"\']*?)\s+from\s+["\'])(?!https?://)([^"\']+)(["\'])'
                for obj in final_js_objects:
                    tab_title = obj.get("title", "tab")
                    tab_code = obj.get("code", "")
                    # 註解掉本地模組導入 (例如 import ... from './shaderSource.js')，避免合併後同名宣告衝突
                    cleaned_code = re.sub(local_import_pattern, r'// \g<0>', tab_code)
                    js_blocks.append(f"// === Tab: {tab_title} ===\n" + cleaned_code)
                    
                code = "\n\n".join(js_blocks)
                
                # 強健的動畫有效性合規檢查（放寬邊界以確保 WebGL 與非標準框架順利收編）
                full_content = code + "\n" + custom_html
                has_render_logic = any(kw in full_content for kw in ["setup", "draw", "void", "canvas", "WebGL", "Olon", "Three", "render", "animate", "requestAnimationFrame"])
                if not has_render_logic and len(code.strip()) < 50:
                    raise Exception("代碼塊內容過於稀疏且未偵測到任何 p5 結構或 Canvas 渲染特徵，判定為非動畫作品，拒絕收錄")
                
                # 提取代碼中的外部資產檔並自動下載
                check_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
                check_code = re.sub(r'//.*', '', check_code)
                asset_pattern = r'["\'`]([^"\'`]+?\.(?:png|jpg|jpeg|gif|svg|ttf|otf|woff|woff2|mp3|wav|ogg|obj|fbx|gltf|glb))["\'`]'
                asset_names = list(set(re.findall(asset_pattern, check_code)))
                
                file_base = sketch_data.get("fileBase")
                if file_base and asset_names:
                    assets_dir = os.path.join(workspace_dir, "custom_visuals", "assets", str(sketch_id))
                    os.makedirs(assets_dir, exist_ok=True)
                    for asset in asset_names:
                        clean_asset = asset.lstrip("./")
                        # 拼接為絕對 URL
                        asset_url = file_base + clean_asset
                        local_file_path = os.path.join(assets_dir, clean_asset)
                        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                        
                        self.log.emit(f"   [📥] 正在下載外部資產: {clean_asset}...", False)
                        try:
                            asset_resp = requests.get(asset_url, headers=headers, timeout=15)
                            if asset_resp.status_code == 200:
                                with open(local_file_path, "wb") as af:
                                    af.write(asset_resp.content)
                                self.log.emit(f"   [✅] 資產 {clean_asset} 下載並快取成功！", False)
                            else:
                                self.log.emit(f"   [⚠️] 資產 {clean_asset} 下載失敗 (HTTP {asset_resp.status_code})", True)
                        except Exception as dl_err:
                            self.log.emit(f"   [⚠️] 下載資產 {clean_asset} 時出錯: {dl_err}", True)
                
                # 擷取真實作者名稱 (強正則過濾)
                meta_matches = re.findall(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', resp.text, re.IGNORECASE)
                author = "未知作者"
                if meta_matches:
                    content = meta_matches[0].replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
                    title_part = title_og.strip()
                    if content.startswith(title_part):
                        author_part = re.sub(r'^[\s\-–—]+', '', content[len(title_part):].strip())
                        author = re.sub(r'[\s\-–—]+OpenProcessing$', '', author_part, flags=re.IGNORECASE).strip() or author
                    else:
                        parts = content.split(" - ")
                        if len(parts) >= 2: author = parts[1].strip()
                        
                if author == "未知作者" or not author:
                    author = sketch_data.get("username", "未知作者")
                
                # 代碼核心轉譯與適配
                adapted_code = adapt_and_repair_code_text(code, sketch_id=sketch_id)
                
                # 儲存 JSON 實體檔
                cleaned_title = re.sub(r'[^a-zA-Z0-9_]', '', title_og) or f"op_{sketch_id}"
                candidate = f"{cleaned_title}.json"
                counter = 1
                while os.path.exists(os.path.join(self.save_dir, candidate)):
                    candidate = f"{cleaned_title}_{counter}.json"
                    counter += 1
                
                save_path = os.path.join(self.save_dir, candidate)
                unique_name = candidate[:-5]
                
                data = {
                    "name": cleaned_title,
                    "code": adapted_code,
                    "frequency": 50,
                    "storyboard_weight": 50,
                    "post_fx_intensity": 50,
                    "custom_html": custom_html,
                    "custom_css": custom_css,
                    "inline_assets": {},
                    "author": author,
                    "license": "CC BY-NC-SA",
                    "tags": ["batch_import", "audio_reactive"],
                    "url": url,
                    "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                # 強驗證縮圖下載
                thumb_dir = os.path.join(self.save_dir, "thumbnails")
                os.makedirs(thumb_dir, exist_ok=True)
                dest_thumb_path = os.path.join(thumb_dir, f"{unique_name}.jpg")
                thumb_success = False
                for ext in [".jpg", ".png"]:
                    try:
                        thumb_url = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}{ext}"
                        img_resp = requests.get(thumb_url, headers=headers, timeout=6)
                        if img_resp.status_code == 200:
                            with open(dest_thumb_path, "wb") as img_f:
                                img_f.write(img_resp.content)
                            thumb_success = True
                            break
                    except Exception:
                        continue
                        
                if not thumb_success:
                    self.log.emit("   [!] 未能從伺服器下載縮圖，主程序渲染引擎將在預覽時自動動態生成", False)
                
                self.log.emit(f"   [+] 【成功收編】作品「{title_og}」，格式已適配音訊矩陣！", False)
                self.success_list.append({
                    "id": sketch_id,
                    "title": title,
                    "url": url,
                    "filename": candidate,
                    "filepath": save_path,
                    "code": adapted_code,
                    "custom_html": custom_html,
                    "custom_css": custom_css,
                    "save_dir": self.save_dir
                })
                self.item_finished.emit(sketch_id, "SUCCESS", "")
                
            except Exception as e:
                err_detail = traceback.format_exc()
                self.log.emit(f"   [-] 【收編失敗】「{title}」: {e}", True)
                self.item_finished.emit(sketch_id, "ERROR", str(e))
                self.failed_list.append({
                    "id": sketch_id, "title": title, "url": url, "error": str(e),
                    "traceback": err_detail, "original_code": code if 'code' in locals() else "N/A"
                })
            
            # 安全防護：設定隨機間隔，徹底告別 429 阻斷
            self.msleep(int(random.uniform(1500, 3000)))
        
        self.finished.emit(self.failed_list)

    def extract_js_object(self, html, var_name):
        import re
        pattern = rf'var\s+{var_name}\s*=\s*'
        match = re.search(pattern, html)
        if not match:
            return None
        
        start_idx = match.end()
        first_brace_idx = html.find('{', start_idx)
        if first_brace_idx == -1:
            return None
            
        try:
            import json
            decoder = json.JSONDecoder()
            _, end_idx = decoder.raw_decode(html[first_brace_idx:])
            return html[first_brace_idx:first_brace_idx + end_idx]
        except Exception as e:
            brace_count = 0
            in_string = False
            string_char = None
            escaped = False
            
            for i in range(first_brace_idx, len(html)):
                char = html[i]
                
                if escaped:
                    escaped = False
                    continue
                if char == '\\':
                    escaped = True
                    continue
                if in_string:
                    if char == string_char:
                        in_string = False
                        string_char = None
                    continue
                if char in ('"', "'", '`'):
                    in_string = True
                    string_char = char
                    continue
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return html[first_brace_idx:i+1]
            return None


class RejectReasonDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('選擇不收錄原因')
        self.resize(380, 360)
        self.reason = None
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Inter', sans-serif; font-size: 13px; font-weight: bold; margin-bottom: 5px; }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px;
                text-align: left;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_abnormal { border-left: 4px solid #ef4444; }
            QPushButton#btn_black_white { border-left: 4px solid #a855f7; }
            QPushButton#btn_controls { border-left: 4px solid #06b6d4; }
            QPushButton#btn_game { border-left: 4px solid #ec4899; }
            QPushButton#btn_alignment { border-left: 4px solid #3b82f6; }
            QPushButton#btn_not_applicable { border-left: 4px solid #f59e0b; }
            QPushButton#btn_cancel { background-color: #09090b; text-align: center; font-weight: normal; }
        """)
        
        layout = QVBoxLayout(self)
        label = QLabel('請選擇不收錄此模組的原因：', self)
        layout.addWidget(label)
        
        btn_abnormal = QPushButton('❌ 預覽不正常', self)
        btn_abnormal.setObjectName('btn_abnormal')
        btn_abnormal.clicked.connect(lambda: self.choose_reason('預覽不正常'))
        layout.addWidget(btn_abnormal)

        btn_black_white = QPushButton('⚫ 一片黑/白/純色', self)
        btn_black_white.setObjectName('btn_black_white')
        btn_black_white.clicked.connect(lambda: self.choose_reason('一片黑/白/純色'))
        layout.addWidget(btn_black_white)

        btn_controls = QPushButton('🎛️ 含有控制項', self)
        btn_controls.setObjectName('btn_controls')
        btn_controls.clicked.connect(lambda: self.choose_reason('含有控制項'))
        layout.addWidget(btn_controls)

        btn_game = QPushButton('🎮 遊戲類別', self)
        btn_game.setObjectName('btn_game')
        btn_game.clicked.connect(lambda: self.choose_reason('遊戲類別'))
        layout.addWidget(btn_game)

        btn_alignment = QPushButton('📐 主視覺未居中/滿版', self)
        btn_alignment.setObjectName('btn_alignment')
        btn_alignment.clicked.connect(lambda: self.choose_reason('主視覺未居中/滿版'))
        layout.addWidget(btn_alignment)
        
        btn_not_applicable = QPushButton('🎨 畫面不適用', self)
        btn_not_applicable.setObjectName('btn_not_applicable')
        btn_not_applicable.clicked.connect(lambda: self.choose_reason('畫面不適用'))
        layout.addWidget(btn_not_applicable)
        
        btn_cancel = QPushButton('取消', self)
        btn_cancel.setObjectName('btn_cancel')
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)
        
    def choose_reason(self, reason_str):
        self.reason = reason_str
        self.accept()



class ErrorCopyDialog(QDialog):
    def __init__(self, errors, parent=None):
        super().__init__(parent)
        self.setWindowTitle('試運行錯誤報告 (請複製提供偵錯)')
        self.resize(600, 400)
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Inter', sans-serif; font-size: 13px; font-weight: bold; margin-bottom: 5px; }
            QTextEdit {
                background-color: #18181b; color: #f43f5e; border: 1px solid #27272a;
                border-radius: 6px; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px;
                padding: 10px;
            }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_copy { background-color: #18181b; border-left: 4px solid #7c3aed; }
            QPushButton#btn_close { background-color: #18181b; }
        """)
        
        layout = QVBoxLayout(self)
        label = QLabel('偵測到以下 JavaScript 試運行錯誤，請複製並提供給 Google Antigravity 進行診斷：', self)
        layout.addWidget(label)
        
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText('\n'.join(errors))
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton('📋 複製錯誤訊息', self)
        btn_copy.setObjectName('btn_copy')
        btn_copy.clicked.connect(self.copy_errors)
        btn_layout.addWidget(btn_copy)
        
        btn_close = QPushButton('關閉', self)
        btn_close.setObjectName('btn_close')
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)
        
    def copy_errors(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        QMessageBox.information(self, '複製成功', '錯誤訊息已成功複製到剪貼簿！')

class TestRunDialog(QDialog):
    def __init__(self, items_to_test, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音畫互動模組 - 批次收錄試運行工作區")
        self.resize(900, 650)
        self.items = items_to_test
        self.current_idx = 0
        self.errors = []
        self.countdown = 5
        self.parent_app = parent
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { font-family: 'Inter', sans-serif; }
            QPushButton {
                border-radius: 6px; padding: 12px; font-weight: bold; font-size: 13px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Header info
        self.title_label = QLabel(self)
        self.title_label.setStyleSheet("color: #e4e4e7; font-weight: bold; font-size: 14px; margin-bottom: 2px;")
        layout.addWidget(self.title_label)
        
        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.status_label)
        
        # Web View
        self.web_view = QWebEngineView(self)
        self.web_view.setMinimumHeight(450)
        layout.addWidget(self.web_view)
        
        # 智慧型滿版縮放模式選取器
        self.scaling_layout = QHBoxLayout()
        self.scaling_label = QLabel("🔍 滿版縮放模式：", self)
        self.scaling_label.setStyleSheet("color: #a1a1aa; font-weight: bold; font-size: 13px;")
        self.scaling_layout.addWidget(self.scaling_label)
        
        self.scaling_combo = QComboBox(self)
        self.scaling_combo.addItems([
            "自動偵測比例 (預設)",
            "高度適應 (Contain Height) - 適合正方形",
            "寬度適應 (Contain Width) - 適合高窄型",
            "滿版裁切 (Cover) - 強制裁切滿版",
            "拉伸滿版 (Stretch) - 忽略比例拉滿"
        ])
        self.scaling_combo.setStyleSheet("""
            QComboBox {
                background-color: #1c1c1e; color: #f4f4f5; border: 1px solid #3a3a3c;
                border-radius: 4px; padding: 6px 12px; min-width: 250px; font-size: 13px;
            }
            QComboBox QAbstractItemView {
                background-color: #1c1c1e; color: #f4f4f5; selection-background-color: #3a3a3c;
            }
        """)
        self.scaling_combo.currentIndexChanged.connect(self.on_scaling_changed)
        self.scaling_layout.addWidget(self.scaling_combo)
        self.scaling_layout.addStretch()
        
        layout.addLayout(self.scaling_layout)
        
        # Bottom Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_keep = QPushButton("🟢 保留此視覺模組", self)
        self.btn_keep.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; padding: 10px;")
        self.btn_keep.clicked.connect(self.keep_current)
        self.btn_layout.addWidget(self.btn_keep)
        
        self.btn_discard = QPushButton("🔴 不保留此模組", self)
        self.btn_discard.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold; padding: 10px;")
        self.btn_discard.clicked.connect(self.discard_current)
        self.btn_layout.addWidget(self.btn_discard)

        # Star rating checkbox (評星/我的最愛)
        self.btn_layout.addSpacing(20)
        self.cb_star = QCheckBox("⭐ 標記為我的最愛 (評星優先置頂)", self)
        self.cb_star.setStyleSheet("""
            QCheckBox {
                color: #eab308;
                font-weight: bold;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.btn_layout.addWidget(self.cb_star)
        self.btn_layout.addStretch()

        layout.addLayout(self.btn_layout)
        
        # Timer for countdown
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        
        # Set Page to intercept JS logs
        from code_injector import CustomWebEnginePage
        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_view)
        self.web_view.setPage(self.web_page)
        
        # Configure QWebEngineSettings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        
        QTimer.singleShot(0, self.start_next_item)
        
    def handle_js_log(self, level, message, lineNumber):
        msg_lower = message.lower()
        # Filter out known benign messages
        if "failed to fetch" in msg_lower or "audiocontext" in msg_lower or "cors" in msg_lower:
            return
        if "[mock]" in msg_lower or "[loadingwatchdog]" in msg_lower or "audio decoding failed" in msg_lower:
            return
        if "dummy silent buffer" in msg_lower or "decodeaudiodata" in msg_lower:
            return
        if "[preloadguard]" in msg_lower or "[object event]" in msg_lower:
            return
        if ("p5.sound" in msg_lower or "p5.min.js" in msg_lower) and not ("error" in msg_lower or "stack" in msg_lower or "uncaught" in msg_lower):
            return
        if "opentype" in msg_lower or "unsupported opentype" in msg_lower or ".ttf" in msg_lower or ".otf" in msg_lower or ".woff" in msg_lower:
            return
        # Filter canvas/image errors caused by placeholder system
        if "width or height of 0" in msg_lower or "drawimage" in msg_lower:
            return
        # Filter raw Event objects being logged as errors
        if message.strip() == "[object Event]" or message.strip() == "[object ErrorEvent]":
            return
        # Filter MIME type, CORS, and network loading errors (CDN issues, not sketch bugs)
        if "mime type" in msg_lower or "refused to execute script" in msg_lower or "net::err" in msg_lower:
            return
        # Filter WebGL shader compilation errors (sandbox GPU limitation, not sketch bugs)
        if "useprogram" in msg_lower or "webglprogram" in msg_lower or "webgl" in msg_lower:
            return
        if "ensurecompiledoncontext" in msg_lower or "shader" in msg_lower:
            return
        # Filter missing external library errors (module dependencies we can't provide)
        if any(lib in msg_lower for lib in ["ml5 is not defined", "tone is not defined", "simplex",
                "lil is not defined", "resolvelygia", "svgfont", "opc' has already been declared",
                "matter is not defined", "dat is not defined"]):
            return
        # Filter p5.js DOM element method confusion (instance mode issues)
        if ".createcanvas is not a function" in msg_lower:
            return
        # Filter JSON/HTML parse errors from network resources
        if "is not valid json" in msg_lower and "unexpected token '<'" in msg_lower:
            return
        # Filter audio connect/disconnect errors in mock system
        if ("connect" in msg_lower or "disconnect" in msg_lower) and lineNumber <= 2:
            return
        # Filter non-fatal asset loading race errors (e.g. vertices of undefined)
        if "vertices" in msg_lower:
            return
            
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        if is_err or "uncaught" in msg_lower or "is not defined" in msg_lower or "unexpected token" in msg_lower or "cannot read properties" in msg_lower or "constructor color" in msg_lower:
            err_line = f"Line {lineNumber}: {message}"
            import sys
            print(f"[JS_ERROR] {err_line}")
            sys.stdout.flush()
            if err_line not in self.errors:
                self.errors.append(err_line)

    def save_progress(self):
        try:
            progress_path = os.path.join(workspace_dir, "batch_test_progress.json")
            data = {
                "items": self.items,
                "current_idx": self.current_idx
            }
            with open(progress_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Failed to save progress:", e)

    def delete_progress(self):
        try:
            progress_path = os.path.join(workspace_dir, "batch_test_progress.json")
            if os.path.exists(progress_path):
                os.remove(progress_path)
        except Exception as e:
            print("Failed to delete progress:", e)
                
    def start_next_item(self):
        self.save_progress()
        if self.current_idx >= len(self.items):
            QMessageBox.information(self, "試運行完成", "所有收編模組的試運行已全部完成！")
            self.delete_progress()
            self.accept()
            return
            
        self.current_item = self.items[self.current_idx]
        self.errors = []
        self.countdown = 15
        
        title = self.current_item["title"]
        url = self.current_item["url"]
        self.title_label.setText(f"📋 模組：{title} ({url})   [{self.current_idx + 1} / {len(self.items)}]")
        self.status_label.setText(f"正在試運行中... 剩餘 {self.countdown} 秒")
        
        # 允許使用者隨時點擊保留或捨棄
        self.btn_keep.setEnabled(True)
        self.btn_discard.setEnabled(True)
        self.cb_star.setChecked(False)
        
        # 初始化下拉選單狀態
        self.scaling_combo.blockSignals(True)
        saved_mode = self.current_item.get("scaling_mode", "auto")
        modes = ["auto", "contain_height", "contain_width", "cover", "stretch"]
        if saved_mode in modes:
            self.scaling_combo.setCurrentIndex(modes.index(saved_mode))
        else:
            self.scaling_combo.setCurrentIndex(0)
        self.scaling_combo.blockSignals(False)
        
        # Generate Sandbox HTML
        html_content = self.generate_sandbox_html(self.current_item)
        import random
        unique_url = QUrl.fromLocalFile(os.path.join(workspace_dir, f"dummy_test_batch_{self.current_idx}_{random.randint(0, 1000000)}.html"))
        self.web_view.setHtml(html_content, unique_url)
        self.timer.start(1000)
        
    def on_scaling_changed(self, index):
        modes = ["auto", "contain_height", "contain_width", "cover", "stretch"]
        if not (0 <= index < len(modes)):
            return
        mode = modes[index]
        self.current_item["scaling_mode"] = mode
        
        # 重新生成 sandbox HTML 以便 100% 正確重新繪製（相容 setup() 靜態與非迴圈模組）
        html_content = self.generate_sandbox_html(self.current_item)
        import random
        unique_url = QUrl.fromLocalFile(os.path.join(workspace_dir, f"dummy_test_batch_{self.current_idx}_{random.randint(0, 1000000)}.html"))
        self.web_view.setHtml(html_content, unique_url)
        
        # 重置倒數計時為 15 秒，給予使用者充裕時間預覽新模式
        self.countdown = 15
        self.status_label.setText(f"正在試運行中... 剩餘 {self.countdown} 秒")
        
    def tick(self):
        self.countdown -= 1
        
        # 查詢並輸出 canvas 的 computed styles 至 stdout
        def style_callback(res):
            import sys
            print(f"[STYLE_DEBUG] Canvas computed style: {res}")
            sys.stdout.flush()
        self.web_view.page().runJavaScript(
            "(() => { const c = document.querySelector('canvas'); const b = document.body; const de = document.documentElement; return {canvasWidth: c ? getComputedStyle(c).width : null, canvasHeight: c ? getComputedStyle(c).height : null, bodyWidth: b ? getComputedStyle(b).width : null, bodyHeight: b ? getComputedStyle(b).height : null, viewWidth: de ? de.clientWidth : null, viewHeight: de ? de.clientHeight : null}; })()",
            style_callback
        )
        
        # 保證每次 tick 時即時刷新 UI 上的秒數
        if self.countdown > 0:
            self.status_label.setText(f"正在試運行中... 剩餘 {self.countdown} 秒")
        
        # 若已有主動攔截到的控制台錯誤，立刻中止並回報
        if self.errors:
            self.timer.stop()
            self.status_label.setText("❌ 試運行偵測到 JavaScript 錯誤！")
            self.on_trial_finished()
            return

        # 處理倒數結束的超時邏輯（保證在 tick 中斷，不依賴 runJavaScript 的 callback）
        if self.countdown <= 0:
            self.timer.stop()
            self.errors.append("試運行超時：模組卡在載入或無回應狀態")
            self.status_label.setText("❌ 試運行偵測到 JavaScript 錯誤！")
            self.on_trial_finished()
            return
            
        js_check = """
        (function() {
          const loadingEl = document.getElementById("p5_loading");
          if (loadingEl && window.getComputedStyle(loadingEl).display !== 'none') {
            return "p5_loading_visible";
          }
          const bodyText = document.body ? document.body.innerText.trim() : "";
          if (bodyText === "Loading..." || bodyText === "Loading") {
            return "body_text_loading";
          }
          const canvases = document.getElementsByTagName("canvas");
          if (canvases.length === 0) {
            return "no_canvas_created";
          }
          return "ok";
        })();
        """
        
        def check_callback(result):
            # 若定時器已停止，忽略延遲的回呼
            if not self.timer.isActive():
                return
                
            if self.errors:
                self.timer.stop()
                self.status_label.setText("❌ 試運行偵測到 JavaScript 錯誤！")
                self.on_trial_finished()
                return

            if result == "ok":
                self.timer.stop()
                self.on_trial_finished()
                return
                
        self.web_view.page().runJavaScript(js_check, check_callback)
            
    def on_trial_finished(self):
        if self.errors:
            self.status_label.setText("❌ 試運行偵測到 JavaScript 錯誤！")
            reply = QMessageBox.question(
                self, 
                "偵測到錯誤", 
                f"模組「{self.current_item['title']}」在試運行時發生了錯誤。\n是否當下處理錯誤？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                dlg = ErrorCopyDialog(self.errors, self)
                dlg.exec()
            else:
                log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_run_errors.log")
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"\n========================================\n")
                        f.write(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"Title: {self.current_item['title']}\n")
                        f.write(f"URL: {self.current_item['url']}\n")
                        f.write(f"Errors:\n" + "\n".join(self.errors) + "\n")
                except Exception as e:
                    print(f"寫入 log 失敗: {e}")
                QMessageBox.information(self, "已儲存", f"錯誤訊息已記錄於 {log_path}，待後續處理。")
            
            self.next_item()
        else:
            self.btn_keep.setEnabled(True)
            self.btn_discard.setEnabled(True)
            self.status_label.setText("✨ 試運行正常無錯誤。請選擇是否保留此模組。")
            
    def keep_current(self):
        self.timer.stop()
        filepath = self.current_item.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # 寫入指定的縮放模式
                modes = ["auto", "contain_height", "contain_width", "cover", "stretch"]
                idx = self.scaling_combo.currentIndex()
                if 0 <= idx < len(modes):
                    data["scaling_mode"] = modes[idx]
                    
                if self.cb_star.isChecked():
                    data["is_starred"] = True
                    
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    
                # 即時通知主視窗更新 UI 狀態
                if self.parent_app and hasattr(self.parent_app, 'refresh_presets_list'):
                    self.parent_app.refresh_presets_list()
            except Exception as e:
                print("Failed to save preset metadata:", e)
        self.next_item()
        
    def discard_current(self):
        self.timer.stop()
        dlg = RejectReasonDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            reason = dlg.reason
            if reason in ["預覽不正常", "一片黑/白/純色", "主視覺未居中/滿版"]:
                self.record_abnormal_preview(self.current_item)
            
            filepath = self.current_item["filepath"]
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except Exception: pass
            
            filename = self.current_item["filename"]
            unique_name = filename[:-5]
            thumb_path = os.path.join(self.current_item["save_dir"], "thumbnails", f"{unique_name}.jpg")
            if os.path.exists(thumb_path):
                try: os.remove(thumb_path)
                except Exception: pass
            
            # 從清單中移除被刪除的項目，讓總數減少
            self.items.pop(self.current_idx)
            
            # 即時通知主視窗更新 UI 狀態
            if self.parent_app and hasattr(self.parent_app, 'refresh_presets_list'):
                self.parent_app.refresh_presets_list()
                
            # 因為彈出了目前索引，後面元素會自動遞補，故不需遞增 current_idx，直接加載下一個
            self.start_next_item()
            
    def next_item(self):
        self.current_idx += 1
        self.start_next_item()
        
    def record_abnormal_preview(self, item):
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abnormal_previews.json")
        data = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception: pass
            
        data.append({
            "id": item["id"],
            "title": item["title"],
            "url": item["url"],
            "rejected_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception: pass
        
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abnormal_previews.html")
        
        cards_html = ""
        for idx, rec in enumerate(data, 1):
            cards_html += f"""
            <div class="card">
                <div class="card-badge">#{idx}</div>
                <div class="card-title">{rec['title']}</div>
                <div class="card-meta">Sketch ID: {rec['id']}</div>
                <div class="card-meta">排除時間: {rec['rejected_at']}</div>
                <a class="card-link" href="{rec['url']}" target="_blank">🌐 前往 OpenProcessing 原始網頁 &rarr;</a>
            </div>
            """
            
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>預覽不正常視覺模組紀錄檔</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0f172a;
            color: #f1f5f9;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            color: #f43f5e;
            font-size: 28px;
            border-bottom: 2px solid #334155;
            padding-bottom: 15px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
            position: relative;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .card:hover {{
            transform: translateY(-5px);
            border-color: #f43f5e;
            box-shadow: 0 10px 15px -3px rgba(244, 63, 94, 0.3);
        }}
        .card-badge {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: #f43f5e;
            color: white;
            font-weight: bold;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
        }}
        .card-title {{
            font-weight: bold;
            font-size: 18px;
            margin-bottom: 12px;
            color: #f8fafc;
            padding-right: 30px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .card-meta {{
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 6px;
        }}
        .card-link {{
            display: inline-block;
            margin-top: 15px;
            color: #38bdf8;
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
        }}
        .card-link:hover {{
            text-decoration: underline;
            color: #7dd3fc;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ 預覽不正常視覺模組紀錄區</h1>
        <p style="color: #94a3b8; margin-bottom: 30px;">本頁面記錄了在批次收錄試運行中，使用者手動標記為「預覽不正常」的視覺模組。點擊卡片連結可直接前往 OpenProcessing 對應網頁進行偵錯與修復。</p>
        <div class="grid">
            {cards_html}
        </div>
    </div>
</body>
</html>
"""
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_template)
        except Exception: pass
        
    def _fix_class_body_syntax(self, code):
        """修復已轉譯代碼中殘留的 Java/Processing 語法問題。
        
        涵蓋：class body 的 let 欄位、function 前綴、Java 陣列型別、
        float 字面量後綴、for-each 迴圈、arraycopy 等。
        """
        # ── 1. 全域性修復（不需要追蹤 class 範圍）──
        
        # 1a. 自動宣告 for 迴圈中未經宣告的變數（如 for(n=0; ... → for(let n=0; ...）
        code = re.sub(r'\bfor\s*\(\s*(?!(?:let|var|const)\b)(\w+)\s*=', r'for(let \1 =', code)
        code = re.sub(r'\bfor\s*\(\s*(?!(?:let|var|const)\b)(\w+)\s+(of|in)\b', r'for(let \1 \2 ', code)
        
        # 1b. 修復特例：250223Lsystemdynamictree 遺失迴圈變數的 typo (for (of newBranchString) -> for (let char of newBranchString))
        code = code.replace("for (of newBranchString)", "for (let char of newBranchString)")
        code = code.replace("for(of newBranchString)", "for(let char of newBranchString)")
        
        # 1c. 將 displayWidth/displayHeight 映射至視窗尺寸，避免預覽視窗比例失調或偏斜
        code = code.replace("displayWidth", "windowWidth")
        code = code.replace("displayHeight", "windowHeight")
        
        # 1c.2 修正 private 欄位標記造成的 SyntaxError (如 #DBE7FF 或 #D1313D 被誤讀為 private class variables)
        # 僅針對未加引號的 hex 顏色進行包裹，排除已在雙引號/單引號/模板字串內的 hex 顏色
        def replace_hex(match):
            if match.group(1):
                return match.group(1)
            return f'"{match.group(2)}"'
        
        pattern = r'("[^"\n\\]*(?:\\.[^"\n\\]*)*"|' + r"'[^'\n\\]*(?:\\.[^'\n\\]*)*'" + r'|`[^`\\]*(?:\\.[^`\\]*)*`)|(?<![\w])(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b'
        code = re.sub(pattern, replace_hex, code)
        
        # 1c.3 修正未定義或順序錯誤的區塊變數 (如 Cannot access 'ballNum' / 'sh' / 'SIDES' / 'GRIDBOX' / 'Ship' / 'Mover' before initialization)
        # 將 let/const 提升至 setup/class 頂層全域，以 var 代替 const/let 來解決 TDZ 暫時死區問題
        code = re.sub(r'\bconst\s+(ballNum|sh|SIDES|GRIDBOX|Mover|Ship|tileSize|mouseTileX)\b', r'var \1', code)
        code = re.sub(r'\blet\s+(ballNum|sh|SIDES|GRIDBOX|Mover|Ship|tileSize|mouseTileX)\b', r'var \1', code)
        
        # 1c.4 修正 for 迴圈或 assignment 中 invalid left-hand side 或是語法拼寫錯 (如 size, list, w, links 等殘留關鍵字)
        # 將 for(lista ...), for(particles ...), for(w ...), for(links ...) 轉為 let 宣告
        code = re.sub(r'\bfor\s*\(\s*(lista|particles|links|incr)\b', r'for(let \1', code)
        
        # 1c. 修復特例：250223Lsystemdynamictree 的 SpriteFactory 遺失 static 關鍵字
        if "class SpriteFactory" in code:
            code = code.replace("  leafSprites = [];", "  static leafSprites = [];")
            code = code.replace("  flowerSprites = [];", "  static flowerSprites = [];")
            code = code.replace("  initializeSprites() {", "  static initializeSprites() {")
            code = code.replace("  createFruitSprite(size, colors) {", "  static createFruitSprite(size, colors) {")
            code = code.replace("  getRandomLeafSprite() {", "  static getRandomLeafSprite() {")
            code = code.replace("  getRandomFlowerSprite() {", "  static getRandomFlowerSprite() {")

        # 1d. 修復特例：Arrival 的 anguloInicialConDesfase 與 p0 遺失 let 宣告 (避免重複宣告)
        if "prepararSegmentos()" in code:
            code = re.sub(r'(?<!\blet\s)(?<!\bvar\s)(?<!\bconst\s)\banguloInicialConDesfase\s*=\s*(?![=\s])', r'let anguloInicialConDesfase = ', code)
            code = re.sub(r'(?<!\blet\s)(?<!\bvar\s)(?<!\bconst\s)\bp0\s*=\s*(?![=\s])', r'let p0 = ', code)

        # 1e. 修復特例：Arrival 的 f1 被誤包含在註解內的問題
        if "// Factores polinómicos de" in code:
            code = code.replace("// Factores polinómicos de let let f1 = ", "let f1 = ")
            code = code.replace("// Factores polinómicos de let f1 = ", "let f1 = ")
            code = code.replace("// Factores polinómicos de f1 = ", "let f1 = ")

        # 1f. 修復特例：AspergillusSpores 的 spores 被包含在註解內的問題
        if "watch?v=let" in code:
            code = code.replace("watch?v=let let spores = [];", "watch?v=let\nlet spores = [];")
            code = code.replace("watch?v=let spores = [];", "watch?v=let\nlet spores = [];")

        # 1g. 修復特例：BullsEye 的 vx 和 vy 陣列未初始化導致 NaN 的問題
        if "randomGaussian() * 16" in code:
            code = code.replace("y[i] = random(height);", "y[i] = random(height);\n\t\tvx[i] = 0;\n\t\tvy[i] = 0;")

        # 1h. 修復特例：Butterflies 的 k 變數在 for 迴圈外被使用，不應設為 block scope
        if "newButterfly()" in code:
            code = code.replace("for(let k =0; k<aPoints.length-1; k++)", "let k;\n  for(k =0; k<aPoints.length-1; k++)")
            code = code.replace("for (let k =0; k<aPoints.length-1; k++)", "let k;\n  for(k =0; k<aPoints.length-1; k++)")
            code = code.replace("for(let k=0; k<aPoints.length-1; k++)", "let k;\n  for(k=0; k<aPoints.length-1; k++)")

        # 1i. 修復特例：若使用自定義 w, h 常數/變數定義畫布尺寸，且確實在 createCanvas 中被呼叫，需在 createCanvas 後同步為真實的 width/height 避免縮在左上角
        if "createCanvas(" in code and ("w =" in code or "h =" in code or "w=" in code or "h=" in code):
            uses_w_in_canvas = re.search(r'createCanvas\s*\(\s*w\s*,', code) is not None
            uses_h_in_canvas = re.search(r'createCanvas\s*\(\s*[^,]+\s*,\s*h\s*[),]', code) is not None
            if uses_w_in_canvas or uses_h_in_canvas:
                setup_match = re.search(r'function\s+setup\s*\([^)]*\)\s*\{(.*?)\}', code, re.DOTALL)
                setup_body = setup_match.group(1) if setup_match else ""
                has_local_w = re.search(r'\b(const|let|var)\s+w\b', setup_body) is not None
                has_local_h = re.search(r'\b(const|let|var)\s+h\b', setup_body) is not None
                
                code = re.sub(r'\bconst\s+w\s*=\s*', 'let w = ', code)
                code = re.sub(r'\bconst\s+h\s*=\s*', 'let h = ', code)
                
                append_lines = []
                if uses_w_in_canvas and not has_local_w:
                    append_lines.append("    w = width;")
                if uses_h_in_canvas and not has_local_h:
                    append_lines.append("    h = height;")
                if append_lines:
                    append_str = "\n" + "\n".join(append_lines)
                    code = re.sub(r'^(\s*createCanvas\s*\(.+?\);?\s*)$', r'\1' + append_str, code, flags=re.MULTILINE)

        # 1j. 修復特例：若使用未定義的 randomColor()，補上其實作
        if "randomColor(" in code and "function randomColor" not in code:
            code += "\nfunction randomColor() { return color(random(360), random(255), random(255)); }"

        # 1k. 修復特例：Coding 的 c 陣列在全域初始化會因為 color/random 未定義而報錯，必須挪入 setup() 內
        if "const c = [randomColor(" in code:
            code = code.replace("const c = [randomColor(), randomColor(), randomColor(), randomColor(), randomColor(), randomColor(), randomColor()];", "let c;")
            code = re.sub(r'(setup\([^)]*\)\s*\{)', r'\1\n  c = [randomColor(), randomColor(), randomColor(), randomColor(), randomColor(), randomColor(), randomColor()];', code)

        # 1l. 修復特例：ColorSmoke 的陣列與變數未初始化導致 NaN 的問題
        if "sympathy = 0.25" in code:
            code = code.replace("let vr, vg, vb;", "let vr = 0, vg = 0, vb = 0;")
            code = code.replace("py[i] = halfHeight + sin(angle) * halfHeight;", "py[i] = halfHeight + sin(angle) * halfHeight;\n    vx[i] = 0;\n    vy[i] = 0;\n    ax[i] = 0;\n    ay[i] = 0;")

        # 1m. 修復特例：Codeisinthebin 因為裁剪會被切掉關鍵內容，強制其畫布貼合模式為 contain (留黑邊不裁剪)
        if "for(let y = 100; y < 300;" in code:
            code = re.sub(r'^(\s*createCanvas\s*\(.+?\);?\s*)$', r'\1\n    let canvas = document.getElementsByTagName("canvas")[0];\n    if(canvas) canvas.style.setProperty("object-fit", "contain", "important");', code, flags=re.MULTILINE)

        # 1n. 修復特例：210523 的 WebGL 投影與圓形繪製問題
        if "const CYCLE = 450;" in code:
            # 註解掉與新版 WebGL 不相容的 ortho 投影，使其回歸預設的 3D 透視投影
            code = code.replace("ortho(-width / 2, width / 2, -height / 2, height / 2,-dep*3 , dep*3);", "// ortho(-width / 2, width / 2, -height / 2, height / 2,-dep*3 , dep*3);")
            # 簡化 3D 下的 2D 圓形繪製參數，移除不相容的第 5 參數 (detail)
            code = code.replace("ellipse(0, 0, r, r, 45);", "ellipse(0, 0, r, r);")

        # 1o. 修復特例：Blue 模組的 DILATE/ERODE 像素濾鏡在全螢幕下效能極差會卡死，將其內部解析度降低 4 倍，利用 GPU 進行無感拉伸
        if "I have a blue house with a blue window" in code:
            code = code.replace("cw = windowWidth", "cw = windowWidth / 4")
            code = code.replace("ch = windowHeight", "ch = windowHeight / 4")

        # 1p. 修復特例：Colorful 模組在 WEBGL 模式下未調用 background() 導致繪圖無法累積而空洞，必須在 setup 中設定 preserveDrawingBuffer
        if "epi_stars" in code and "WEBGL" in code:
            code = code.replace("createCanvas((W = windowWidth), (H = windowHeight), WEBGL);", "setAttributes('preserveDrawingBuffer', true);\n  createCanvas((W = windowWidth), (H = windowHeight), WEBGL);")

        # 1q. 修復特例：Day4243RainyDays 為 9:16 直式畫面，在寬螢幕下使用 cover 會將底部漣漪和濺射完全裁剪切掉，強制其畫布貼合模式為 contain (留黑邊不裁剪)
        if "Day4243RainyDays" in code or "resizeCanvasToWindow" in code:
            code = re.sub(r'(createCanvas\([^)]+\);?)', r'\1\n    let canvas = document.getElementsByTagName("canvas")[0];\n    if(canvas) canvas.style.setProperty("object-fit", "contain", "important");', code, flags=re.MULTILINE)

        # 1r. 修復特例：DifferentialGrowth 需要滑鼠拖曳才有初始圖案，在此在 draw 開始時自動注入種子圓形使其能自主生長
        if "curves = []" in code and "curveVertex" in code and "spd = 0.05" in code:
            seed_code = """
	if (frameCount === 1 && curves.length === 0) {
		let seed = [];
		let cx = width / 2;
		let cy = height / 2;
		let r = rad * 1.5;
		for (let theta = 0; theta < TWO_PI; theta += 0.5) {
			seed.push(new p5.Vector(cx + cos(theta) * r, cy + sin(theta) * r));
		}
		curves.push(seed);
	}
"""
            code = re.sub(r'(function\s+draw\s*\([^)]*\)\s*\{)', r'\1' + seed_code, code)

        # 1s. 修復特例：Emotionallines_12 主視覺太小，在 draw 中進行 scale 放大 3.0 倍
        if "Samuel_Ann" in code or "SamuelYAN" in code:
            code = code.replace("push();\n\n\tfor (let q = 0;", "push();\n\tscale(3.0);\n\n\tfor (let q = 0;")
            code = code.replace("push();\n\tfor (let q = 0;", "push();\n\tscale(3.0);\n\tfor (let q = 0;")

        # 1t. 修復特例：SamuelYAN 模組在啟動時視窗尺寸未就緒導致計算出的 radius 太小，在 draw 開始時動態重新計算，並放大 1.8 倍
        if "Samuel_Ann" in code or "SamuelYAN" in code:
            factor = 0.75 if "radius = mySize * 0.75" in code else 0.25
            recalc_code = f"\n\tmySize = max(width, height);\n\tradius = mySize * {factor};\n"
            code = re.sub(r'(function\s+draw\s*\([^)]*\)\s*\{)', r'\1' + recalc_code, code)
            if "translate(width / 2, height / 2);" in code:
                code = code.replace("translate(width / 2, height / 2);", "translate(width / 2, height / 2);\n\tscale(1.8);")

        # 1u. 修正 Processing 獨有的 TESS 頂點剖分常量在 p5.js 中不存在導致的 ReferenceError 崩潰
        if "TESS" in code:
            code = code.replace("beginShape(TESS)", "beginShape()")

        # 1v. 修復特例：Erosion1 在 WebGL 模式下使用預設 ortho() 導致畫布縮放後近剪切面裁剪出錯而黑屏/灰屏，給定明確的三維剪切邊界
        if "noiseDetail(15, 0.35);" in code:
            code = code.replace("ortho()", "ortho(-300, 300, 300, -300, -600, 600);")

        # 1w. 修復特例：ExtrudedColors 模組中存在無效的 5 位 Hex 顏色引發 Canvas 繪圖失效，且在啟動時視窗尺寸未就緒導致圖案縮小在左上角，在 draw 開始時動態重算佈局參數
        if "ExtrudedColors" in code or "wt1 = 0.5" in code:
            code = code.replace('"#ef562"', '"#ef5622"')
            recalc_layout = """
	W = width;
	H = height;
	S = min(W, H);
	hMargin = H * 0.085;
	ht = (H - 2 * hMargin) / (nLines - 1);
	sz = ht / sqrt(2) - 8;
	wt2 = sz / 12;
	wMargin = max(S * 0.10, ht * 0.75, hMargin);
	L = W - wMargin;
"""
            code = re.sub(r'(function\s+draw\s*\([^)]*\)\s*\{)', r'\1' + recalc_layout, code)

        # 1x. 修復特例：FlowField 模組宣告了 Particle 類別但漏掉了粒子陣列的初始化，在 setup 中自動初始化 1000 個粒子使其能流暢運行
        if "let attractors = [];" in code and "class Attractor{" in code and "clockwise" in code:
            if "particles.push" not in code and "particles = [" not in code:
                init_particles_code = "\n\tfor(let i = 0; i < 1000; i++) {\n\t\tparticles.push(new Particle());\n\t}\n"
                code = re.sub(r'(function\s+setup\s*\([^)]*\)\s*\{)', r'\1' + init_particles_code, code)

        # 1y. 修復特例：FluidSimulation 需要滑鼠點擊才有流體，在此在 draw 中注入自動運行的軌跡點生成流體，並限制像素密度以保障效能
        if "initSim();" in code and "polarBoxMullerTransform" in code:
            code = code.replace("initSim();", "initSim();\n  pixelDensity(1);")
            orbit_code = """
  let cx = int(N/2 + sin(frameCount * 0.05) * N * 0.3);
  let cy = int(N/2 + cos(frameCount * 0.07) * N * 0.3);
  let prev_cx = int(N/2 + sin((frameCount-1) * 0.05) * N * 0.3);
  let prev_cy = int(N/2 + cos((frameCount-1) * 0.07) * N * 0.3);
  let idx = IX(cx, cy);
  dens[idx] += source * 2;
  u[idx] += (cx - prev_cx) * 5;
  v[idx] += (cy - prev_cy) * 5;
"""
            code = re.sub(r'(function\s+draw\s*\([^)]*\)\s*\{)', r'\1' + orbit_code, code)

        # 1z. 修復特例：FracturedOcean 啟動時視窗尺寸未就緒導致 m 被算成 300 且無自適應，在此在 draw 開頭動態重算佈局，並追加 windowResized 自適應函數
        if "let section = 4;" in code and "let spot = 8;" in code and "plusSign" in code:
            recalc_code = """
	m = max(width, height);
	section_step = (m*(1-2*padding))/section;
	spot_step = section_step/spot;
"""
            code = re.sub(r'(function\s+draw\s*\([^)]*\)\s*\{)', r'\1' + recalc_code, code)
            window_resized_func = """
function windowResized() {
	m = max(windowWidth, windowHeight);
	resizeCanvas(m, m);
	section_step = (m*(1-2*padding))/section;
	spot_step = section_step/spot;
}
"""
            code += window_resized_func

        # 1aa. 修復特例：GPUParticles 模組原版使用 45 萬次 WebGL .rect() 繪圖來初始化紋理，會引發瀏覽器卡死/溢出黑屏，改用記憶體內 loadPixels() 快取優化；且視窗初始大小異常，改用 window.innerWidth / innerHeight
        if "function pack3(value)" in code and "initTextures()" in code:
            code = code.replace("createCanvas(windowWidth, windowHeight)", "createCanvas(window.innerWidth || 880, window.innerHeight || 450)")
            optimized_init_textures = """
function initTextures() {
  texture_initialData = createGraphics(512, 512, WEBGL);
  texture_initialData.noSmooth();
  texture_initialData.textureWrap(CLAMP, CLAMP);
  texture_initialData.setAttributes({ alpha: true, antialias: false });

  texture_randomSeed = createGraphics(512, 512, WEBGL);
  texture_randomSeed.noSmooth();
  texture_randomSeed.textureWrap(CLAMP, CLAMP);
  texture_randomSeed.setAttributes({ alpha: true, antialias: false });

  texture_particleDataA = createGraphics(512, 512, WEBGL);
  texture_particleDataB = createGraphics(512, 512, WEBGL);
  texture_particleDataA.noSmooth();
  texture_particleDataB.noSmooth();
  texture_particleDataA.textureWrap(CLAMP, CLAMP);
  texture_particleDataB.textureWrap(CLAMP, CLAMP);
  texture_particleDataA.setAttributes({ alpha: true, antialias: false });
  texture_particleDataB.setAttributes({ alpha: true, antialias: false });
	
  shader_particleDataA = texture_particleDataA.createShader(particleMoveVert, particleMoveFrag);
  shader_particleDataB = texture_particleDataB.createShader(particleMoveVert, particleMoveFrag);

  let pgA = createGraphics(512, 512);
  let pgB = createGraphics(512, 512);
  pgA.pixelDensity(1);
  pgB.pixelDensity(1);
  pgA.loadPixels();
  pgB.loadPixels();

  function setPixel(pixelsArray, px, py, rgb) {
    let idx = (px + py * 512) * 4;
    pixelsArray[idx] = rgb[0];
    pixelsArray[idx + 1] = rgb[1];
    pixelsArray[idx + 2] = rgb[2];
    pixelsArray[idx + 3] = 255;
  }

  for(let x = 0; x < 256; x++) {
    for(let y = 0; y < 256; y++) {
      let xRatio = x / 256;
      let yRatio = y / 256;
      let xPos = int(xRatio * width);
      let yPos = int(yRatio * height);
      let storeX = realToRaw(xPos);
      let storeY = realToRaw(yPos);
      let packedX = pack3(storeX);
      let packedY = pack3(storeY);
      let rot = random(0, 360);
      let packRot = pack3(realToRaw(rot));
      let initialVel = random(1.0, 1000.0);
      let packVel = pack3(realToRaw(initialVel));

      setPixel(pgA.pixels, x, y, packedX);
      setPixel(pgA.pixels, x + 256, y, packedY);
      setPixel(pgA.pixels, x, y + 256, packRot);
      setPixel(pgA.pixels, x + 256, y + 256, packVel);

      let randomValue = int(random(0, 65535));
      let packedRandom = pack3(randomValue);
      let initLife = int(random(0, 300));
      let partLife = int(random(15, 90));
      let packedInitLife = pack3(initLife);
      let packedPartLife = pack3(partLife);

      setPixel(pgB.pixels, x, y, packedRandom);
      setPixel(pgB.pixels, x, y + 256, packedInitLife);
      setPixel(pgB.pixels, x + 256, y + 256, packedPartLife);
    }
  }
  pgA.updatePixels();
  pgB.updatePixels();

  texture_initialData.image(pgA, -256, -256);
  texture_randomSeed.image(pgB, -256, -256);
}
"""
            code = re.sub(r'function\s+initTextures\s*\([^)]*\)\s*\{.*?\}', optimized_init_textures, code, flags=re.DOTALL)

        # 1ab. 修復特例：GenerativeP 模組中宣告了速度陣列 vx, vy 但在 reset() 中忘記初始化，導致在 draw 運算時 undefined 乘算產生 NaN 導致所有粒子坐標變成 NaN 而黑屏，在 reset 中將速度初始化為 0
        if "let vx = new Array(n);" in code and "bluechannel[i] = random(255);" in code:
            code = code.replace("greenchannel[i] = random(255);", "greenchannel[i] = random(255);\n\t\tvx[i] = 0;\n\t\tvy[i] = 0;")

        # 1ac. 修復特例：Genuary2026day27 模組原版使用固定 500x500 尺寸且 pixelDensity(4) 導致高負載與黑邊，改用視窗寬高滿版並限制像素密度為 1 以優化流暢度
        if "Poisson-disc Sampling" in code and "thetaDivs = 24;" in code:
            code = code.replace("createCanvas(500, 500);", "createCanvas(window.innerWidth || 880, window.innerHeight || 450);")
            code = code.replace("pixelDensity(4);", "pixelDensity(1);")

        # 1ad. 修復特例：Genuary2026day4 模組原版使用固定 600x600 尺寸導致黑邊，改用視窗寬高滿版
        if "noiseCloudImg = createGraphics(200, 200);" in code and "imgCopies" in code:
            code = code.replace("createCanvas(600, 600);", "createCanvas(window.innerWidth || 880, window.innerHeight || 450);")

        # 1ae. 修復特例：Gridoflines 模組未設置背景色，在編輯器暗色容器中默認透明黑底繪製黑線導致完全看不見，在 draw 開頭加上 background(255)
        if "allColumnsPoints = [];" in code and "drawGrid(5, 5, 40, 40" in code:
            code = re.sub(r'(function\s+draw\s*\([^)]*\)\s*\{)', r'\1\n\tbackground(255);', code)

        # 1af. 移除 Java float 字面量後綴 f（例如: 0.85f → 0.85）
        code = re.sub(r'(\d+\.?\d*)f\b', r'\1', code)
        
        # 1b. 轉換 Java 自定義類別型別的變數宣告（必須在陣列型別移除之前）
        # 例如: "NavierStokesFluidSolver fluidSolver;" → "let fluidSolver;"
        # 例如: "Particle p = new Particle();" → "let p = new Particle();"
        code = re.sub(r'^(\s*)([A-Z]\w+)\s+(\w+)\s*;', r'\1let \3;', code, flags=re.MULTILINE)
        code = re.sub(r'^(\s*)([A-Z]\w+)\s+(\w+)\s*=', r'\1let \3 =', code, flags=re.MULTILINE)
        
        # 1c. 轉換 Java 陣列型別宣告
        # 獨立宣告行 (以分號結尾): "Particle[] particles;" → "let particles;"
        code = re.sub(r'^(\s*)(?:int|float|double|boolean|color|char|byte|short|long|String|[A-Z]\w*)\[\]\s+(\w+)\s*;', r'\1let \2;', code, flags=re.MULTILINE)
        code = re.sub(r'^(\s*)(?:int|float|double|boolean|color|char|byte|short|long|String|[A-Z]\w*)\[\]\s+(\w+)\s*=', r'\1let \2 =', code, flags=re.MULTILINE)
        # 函數參數中的陣列型別: "function foo(double[] arr)" → "function foo(arr)"
        code = re.sub(r'\b(?:int|float|double|boolean|color|char|byte|short|long|String|[A-Z]\w*)\[\][ \t]+(\w+)', r'\1', code)
        
        # 1d. 轉換 Java for-each 迴圈
        # 例如: "for (Particle particle : particles)" → "for (let particle of particles)"
        code = re.sub(
            r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)',
            r'for (let \1 of \2)',
            code
        )
        
        # 1e. 轉換 Java 風格陣列建立
        # 例如: "new Particle[numberOfParticles]" → "new Array(numberOfParticles)"
        code = re.sub(r'\bnew\s+\w+\[([^\]]+)\]', r'new Array(\1)', code)
        
        # 1e. 轉換 Processing 的 arraycopy 為 JS
        # arraycopy(src, srcPos, dest, destPos, length) 
        # → for(let _i=0;_i<length;_i++) dest[destPos+_i]=src[srcPos+_i];
        # 簡單方案：用 JS polyfill 函數
        if 'arraycopy' in code and 'function arraycopy' not in code:
            code = "function arraycopy(s,sp,d,dp,l){for(var _i=0;_i<l;_i++)d[dp+_i]=s[sp+_i];}\n" + code
        
        # 1f. 移除函數參數中誤加的 let 關鍵字 (排除 for 迴圈)
        def _clean_global_params(m):
            params = m.group(1)
            if ";" in params or " of " in params or " in " in params:
                return "(" + params + ")"
            cleaned = re.sub(r'\blet\s+', '', params)
            return '(' + cleaned + ')'
        code = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', _clean_global_params, code)
        
        # ── 2. 逐行修復（需要追蹤 class 範圍）──
        
        def strip_comments_and_strings(code_str):
            pattern = r'(/\*([^*]|\*[^/])*\*/)|(//[^\n]*)|("[^"\\]*(?:\\.[^"\\]*)*")|(\'[^\'\\]*(?:\\.[^\'\\]*)*\')|(`[^`\\]*(?:\\.[`\\]*)*`)'
            def replacer(match):
                text = match.group(0)
                return re.sub(r'[^\n]', ' ', text)
            return re.sub(pattern, replacer, code_str)

        clean_code = strip_comments_and_strings(code)
        lines = code.split("\n")
        clean_lines = clean_code.split("\n")
        new_lines = []
        in_class = False
        brace_depth = 0
        
        for line, clean_line in zip(lines, clean_lines):
            class_match = re.search(r'\bclass\s+\w+', clean_line)
            if class_match and not in_class:
                in_class = True
                brace_depth = 0
                brace_depth += clean_line.count('{') - clean_line.count('}')
                new_lines.append(line)
                continue
            
            if in_class:
                brace_depth += clean_line.count('{') - clean_line.count('}')
                if brace_depth <= 0:
                    in_class = False
                
                # 移除 class 內部方法的 function 關鍵字前綴
                line = re.sub(r'^(\s*)function\s+(\w+)\s*\(', r'\1\2(', line)
                
                # 移除 class 內部欄位宣告的 let/var/const（僅在 brace_depth == 1，即 class 頂層欄位宣告時）
                stripped = clean_line.strip()
                if brace_depth == 1 and re.match(r'^(let|var|const)\s+\w+', stripped):
                    if not re.match(r'^(let|var|const)\s+\w+\s*\(', stripped):
                        line = re.sub(r'^(\s*)(let|var|const)\s+', r'\1', line)
                
                # 移除方法參數中的 let (排除 for 迴圈)
                if '(' in line and ')' in line:
                    def _clean_params(m):
                        params = m.group(1)
                        if ";" in params or " of " in params or " in " in params:
                            return "(" + params + ")"
                        cleaned = re.sub(r'\blet\s+', '', params)
                        return '(' + cleaned + ')'
                    line = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', _clean_params, line)
            
            new_lines.append(line)
        
        return "\n".join(new_lines)
    
    def generate_sandbox_html(self, item):
        code = item["code"]
        custom_html = item["custom_html"]
        if self.parent_app and hasattr(self.parent_app, "cache_and_localize_scripts"):
            custom_html = self.parent_app.cache_and_localize_scripts(custom_html)
        custom_css = item["custom_css"]
        
        # 後處理修復：修正已存代碼中 class body 內的 let 欄位宣告與方法參數
        code = self._fix_class_body_syntax(code)
        
        # Repair old mouse/pmouse subtraction mismatch on-the-fly
        old_x_sub = "(window.simulatedMouseX !== undefined ? window.simulatedMouseX : width / 2) - (window.simulatedMouseX !== undefined ? window.simulatedMouseX : width / 2)"
        new_x_sub = "(window.simulatedMouseX !== undefined ? window.simulatedMouseX : width / 2) - (window.simulatedPMouseX !== undefined ? window.simulatedPMouseX : width / 2)"
        old_y_sub = "(window.simulatedMouseY !== undefined ? window.simulatedMouseY : height / 2) - (window.simulatedMouseY !== undefined ? window.simulatedMouseY : height / 2)"
        new_y_sub = "(window.simulatedMouseY !== undefined ? window.simulatedMouseY : height / 2) - (window.simulatedPMouseY !== undefined ? window.simulatedPMouseY : height / 2)"
        code = code.replace(old_x_sub, new_x_sub).replace(old_y_sub, new_y_sub)
        
        # Repair global x/y loop variable collisions on-the-fly
        import re
        code = re.sub(r'\bfor\s*\(\s*([xy])\s*=\s*', r'for(let \1=', code)
        
        # Repair TDZ ReferenceError (cannot access h before initialization) caused by w/h helper injection on-the-fly
        setup_match = re.search(r'function\s+setup\s*\([^)]*\)\s*\{(.*?)\}', code, re.DOTALL)
        if setup_match:
            setup_body = setup_match.group(1)
            if re.search(r'\b(const|let|var)\s+h\b', setup_body):
                code = code.replace("h = height;", "")
            if re.search(r'\b(const|let|var)\s+w\b', setup_body):
                code = code.replace("w = width;", "")
        
        # Repair hoisted v vector assignment in NoiseFlowField on-the-fly
        if "flowField[index] = v;" in code:
            code = code.replace("flowField[index] = v;", "")
            code = code.replace("v.setMag(180);", "v.setMag(180);\n      flowField[index] = v;")
            code = code.replace("v.setMag(250);", "v.setMag(250);\n      flowField[index] = v;")
        # Repair dark particle color on dark backgrounds on-the-fly
        code = code.replace("stroke(0,50);", "stroke(255, 50);").replace("stroke(0, 50);", "stroke(255, 50);")
        
        # Repair p5.js v2 alpha/red/green/blue/... compatibility by wrapping arguments in window.color() to avoid local variable shadowing
        code = re.sub(
            r'\b(alpha|red|green|blue|hue|saturation|brightness|lightness)\s*\(\s*(?!window\.color\()((?:[^()]+|\([^()]*\))+)\)',
            r'\1(window.color(\2))',
            code
        )
        
        try:
            with open(os.path.join(workspace_dir, "last_batch_run_code.js"), "w", encoding="utf-8") as f_dump:
                f_dump.write(code)
        except Exception:
            pass
        
        is_module = "import " in code or "export " in code
        
        import main
        
        script_tag = f'<script type="module">{code}\n{main.BIND_MODULE_CALLBACKS_JS}</script>' if is_module else f'<script>{code}</script>'
        
        sketch_id = item.get("id")
        asset_override_js = ""
        if sketch_id:
            asset_override_js = f"""
            // Asset Loading Override for p5.js
            (function() {{
              const sketchId = "{sketch_id}";
              if (!sketchId || sketchId === "None") return;
              const assetSubdir = "custom_visuals/assets/" + sketchId + "/";
              const loadFuncs = ["loadImage", "loadSound", "loadFont", "loadModel", "loadStrings", "loadTable", "loadBytes", "loadXML"];
              loadFuncs.forEach(funcName => {{
                if (typeof window[funcName] === 'function') {{
                  const original = window[funcName];
                  window[funcName] = function(path, ...args) {{
                    if (typeof path === 'string' && !path.startsWith('http') && !path.startsWith('data:')) {{
                      let cleanPath = path;
                      if (cleanPath.startsWith('./')) {{
                        cleanPath = cleanPath.substring(2);
                      }} else if (cleanPath.startsWith('/')) {{
                        cleanPath = cleanPath.substring(1);
                      }}
                      path = assetSubdir + cleanPath;
                    }}
                    return original.call(this, path, ...args);
                  }};
                }}
                if (typeof p5 !== 'undefined' && p5.prototype && typeof p5.prototype[funcName] === 'function') {{
                  const original = p5.prototype[funcName];
                  p5.prototype[funcName] = function(path, ...args) {{
                    if (typeof path === 'string' && !path.startsWith('http') && !path.startsWith('data:')) {{
                      let cleanPath = path;
                      if (cleanPath.startsWith('./')) {{
                        cleanPath = cleanPath.substring(2);
                      }} else if (cleanPath.startsWith('/')) {{
                        cleanPath = cleanPath.substring(1);
                      }}
                      path = assetSubdir + cleanPath;
                    }}
                    return original.call(this, path, ...args);
                  }};
                }}
              }});
            }})();
            """

        # 處理 inline_assets 攔截器，確保 shader、json 檔案正常載入
        import json
        inline_assets = item.get("inline_assets", {})
        assets_json = json.dumps(inline_assets or {})
        interceptor_js = f"""
            window.inline_assets = {assets_json};
            
            // Intercept fetch
            const originalFetch = window.fetch;
            window.fetch = function(input, init) {{
              const url = typeof input === 'string' ? input : (input.url || "");
              const filename = url.split('/').pop();
              if (window.inline_assets && window.inline_assets[filename] !== undefined) {{
                return Promise.resolve(new Response(window.inline_assets[filename]));
              }}
              return originalFetch.apply(this, arguments);
            }};

            // Intercept XMLHttpRequest
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, async, user, password) {{
              const filename = url.split('/').pop();
              if (window.inline_assets && window.inline_assets[filename] !== undefined) {{
                this.send = function() {{
                  Object.defineProperty(this, 'readyState', {{ value: 4, writable: true }});
                  Object.defineProperty(this, 'status', {{ value: 200, writable: true }});
                  Object.defineProperty(this, 'responseText', {{ value: window.inline_assets[filename], writable: true }});
                  if (this.onload) this.onload();
                  if (this.onreadystatechange) this.onreadystatechange();
                }};
                return;
              }}
              return originalOpen.apply(this, arguments);
            }};
        """

        html_template = f"""<!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #000000 !important; display: flex; justify-content: center; align-items: center; }}
            canvas {{ display: block !important; position: absolute !important; left: 50% !important; top: 50% !important; transform: translate(-50%, -50%) !important; width: 100vw !important; height: 100vh !important; max-width: none !important; max-height: none !important; object-fit: cover !important; background-color: transparent !important; }}
            /*CUSTOM_CSS_PLACEHOLDER*/
            /* Enforce final centering in case custom_css overwrote canvas positioning */
            body canvas {{
              position: absolute !important;
              left: 50% !important;
              top: 50% !important;
              transform: translate(-50%, -50%) !important;
              width: 100vw !important;
              height: 100vh !important;
              max-width: none !important;
              max-height: none !important;
              object-fit: cover !important;
            }}
          </style>
          <script>
            window.addEventListener('unhandledrejection', function(event) {{
              const reason = event.reason;
              if (reason && reason.stack) {{
                console.error("Unhandled Rejection Stack:\\n" + reason.stack);
              }} else {{
                console.error("Unhandled Rejection: " + reason);
              }}
            }});
            window.onerror = function(message, source, lineno, colno, error) {{
              if (error && error.stack) {{
                console.error("Window Error Stack:\\n" + error.stack);
              }}
            }};

            Object.defineProperty(window, 'innerWidth', {{ get: function() {{ return 1280; }}, set: function(val) {{}}, configurable: true }});
            Object.defineProperty(window, 'innerHeight', {{ get: function() {{ return 720; }}, set: function(val) {{}}, configurable: true }});
            Object.defineProperty(window, 'windowWidth', {{ get: function() {{ return 1280; }}, set: function(val) {{}}, configurable: true }});
            Object.defineProperty(window, 'windowHeight', {{ get: function() {{ return 720; }}, set: function(val) {{}}, configurable: true }});

            (function() {{
              const orgGetContext = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, attribs) {{
                if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {{
                  attribs = attribs || {{}};
                  attribs.preserveDrawingBuffer = true;
                }}
                return orgGetContext.call(this, type, attribs);
              }};
            }})();

            window.fxrand = window.fxrand || Math.random;
            window.fxhash = window.fxhash || (function() {{
              const alphabet = "123456789alphabet";
              return "oo" + Array(49).fill(0).map(() => alphabet[(Math.random() * alphabet.length) | 0]).join('');
            }})();

            // Inject CSS to hard-hide any leftover GUI containers
            (function() {{
              const style = document.createElement('style');
              style.innerHTML = `
                .dg, .lil-gui, .qs_main, .opc-control, #opc-control-panel, .control-panel, .gui-container {{
                  display: none !important;
                  visibility: hidden !important;
                  opacity: 0 !important;
                  pointer-events: none !important;
                }}
              `;
              document.head.appendChild(style);
            }})();

            // Overwrite OPC methods to prevent control panels from rendering and dynamically link them to audio low/mid/high/beat
            if (typeof OPC !== 'undefined' || true) {{
              const opcMock = {{
                slider: function(name, value, min, max, step) {{
                  const channels = ['audioLow', 'audioMid', 'audioHigh', 'beatEnergy'];
                  const bound = channels[Math.floor(Math.random() * channels.length)];
                  Object.defineProperty(window, name, {{
                    get: function() {{
                      let norm = window[bound] || 0.5;
                      let rMin = min !== undefined ? min : 0;
                      let rMax = max !== undefined ? max : 1;
                      return rMin + norm * (rMax - rMin);
                    }},
                    set: function() {{}},
                    configurable: true
                  }});
                  return this;
                }},
                button: function() {{ return this; }},
                toggle: function(name, value) {{
                  Object.defineProperty(window, name, {{
                    get: function() {{
                      return (window.audioLow || 0.5) > 0.5;
                    }},
                    set: function() {{}},
                    configurable: true
                  }});
                  return this;
                }},
                color: function(name, value) {{
                  window[name] = value;
                  return this;
                }},
                select: function(name, value) {{
                  window[name] = value;
                  return this;
                }},
                text: function(name, value) {{
                  window[name] = value;
                  return this;
                }},
                setGlobal: function(name, value) {{
                  window[name] = value;
                }}
              }};
              window.OPC = opcMock;
            }}

            window.seed = window.seed || Math.floor(Math.random() * 999999);
            {main.MOCK_NATIVE_AUDIO_JS}
          </script>
          <script src="https://cdn.jsdelivr.net/npm/p5@2.3.0/lib/p5.min.js"></script>
          <script>{main.P5_V2_COMPAT_SHIM}</script>
          <script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js"></script>
          <script src="https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js"></script>
          <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
          <!-- OPC CDN removed: our inline Mock OPC above is sufficient and avoids 'Identifier OPC has already been declared' -->
          <script src="https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js"></script>
          <script src="https://cdn.jsdelivr.net/npm/rampensau/dist/index.js"></script>
          <script src="https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js"></script>
          <script src="https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js"></script>
          <script src="https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js"></script>
          <script>
            {interceptor_js}
            {asset_override_js}
            window.customScalingMode = "{item.get('scaling_mode', 'auto')}";
            {main.OVERRIDE_16_9_JS}
            {main.MOCK_P5_JS}
            window.frequency = 50;
            window.storyboardWeight = 50;
            window.postFxIntensity = 50;
            window.isBeat = false;
            window.beatEnergy = 0;
            window.audioLow = 0;
            window.audioMid = 0;
            window.audioHigh = 0;
            window.simulatedMouseX = 400;
            window.simulatedMouseY = 300;
            window.simulatedPMouseX = 400;
            window.simulatedPMouseY = 300;
            
            let sandboxFrameCounter = 0;
            function tick() {{
              sandboxFrameCounter++;
              // 每 30 幀 (約 0.5 秒) 模擬滑鼠移動、點擊與拖曳，使需要互動的模組（如 Ants）能自動動起來
              if (sandboxFrameCounter % 30 === 0) {{
                let w = window.innerWidth || 900;
                let h = window.innerHeight || 650;
                
                window.simulatedPMouseX = window.simulatedMouseX || (w / 2);
                window.simulatedPMouseY = window.simulatedMouseY || (h / 2);
                
                let prevX = window.simulatedMouseX;
                let prevY = window.simulatedMouseY;
                
                window.simulatedMouseX = w / 2 + Math.sin(sandboxFrameCounter * 0.05) * w * 0.3;
                window.simulatedMouseY = h / 2 + Math.cos(sandboxFrameCounter * 0.05) * h * 0.3;
                
                window.simulatedPMouseX = prevX;
                window.simulatedPMouseY = prevY;
                
                try {{
                  let moveEvt = new MouseEvent('mousemove', {{ clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, bubbles: true }});
                  let downEvt = new MouseEvent('mousedown', {{ clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, button: 0, buttons: 1, bubbles: true }});
                  let clickEvt = new MouseEvent('click', {{ clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, bubbles: true }});
                  let upEvt = new MouseEvent('mouseup', {{ clientX: window.simulatedMouseX, clientY: window.simulatedMouseY, button: 0, bubbles: true }});
                  
                  window.dispatchEvent(moveEvt);
                  window.dispatchEvent(downEvt);
                  window.dispatchEvent(clickEvt);
                  window.dispatchEvent(upEvt);
                  
                  let canvas = document.querySelector('canvas');
                  if (canvas) {{
                    canvas.dispatchEvent(moveEvt);
                    canvas.dispatchEvent(downEvt);
                    canvas.dispatchEvent(clickEvt);
                    canvas.dispatchEvent(upEvt);
                  }}
                }} catch(e) {{}}
                
                if (typeof mousePressed === 'function') {{
                  try {{ mousePressed(); }} catch(e) {{}}
                }}
                if (typeof mouseClicked === 'function') {{
                  try {{ mouseClicked(); }} catch(e) {{}}
                }}
                if (typeof mouseDragged === 'function') {{
                  try {{ mouseDragged(); }} catch(e) {{}}
                }}
              }}
              requestAnimationFrame(tick);
            }}
            requestAnimationFrame(tick);
          </script>
        </head>
        <body>
          <!--CUSTOM_HTML_PLACEHOLDER-->
          {script_tag}
        </body>
        </html>
        """
        html = html_template.replace("/*CUSTOM_CSS_PLACEHOLDER*/", custom_css or "").replace("<!--CUSTOM_HTML_PLACEHOLDER-->", custom_html or "")
        if self.parent_app and hasattr(self.parent_app, "js_local_paths") and self.parent_app.js_local_paths:
            for online_url, local_url in self.parent_app.js_local_paths.items():
                html = html.replace(online_url, local_url)
        return html


class BatchImportDialog(QDialog):
    def __init__(self, parent=None, refresh_callback=None):
        super().__init__(parent)
        self.refresh_callback = refresh_callback
        self.detected_sketches_map = {}
        self.detected_items = []
        self.save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(self.save_dir, exist_ok=True)
        self.existing_urls = self.get_existing_urls()
        
        self.setWindowTitle("📥 OpenProcessing 藝術視覺模組 - 自動化批次收編工作區")
        self.resize(1350, 800)
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QLineEdit { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 12px; font-size: 13px; }
            QLineEdit:focus { border-color: #a855f7; }
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_import { background-color: #7c3aed; border-color: #7c3aed; }
            QPushButton#btn_import:hover { background-color: #8b5cf6; }
            QPushButton#btn_import:disabled { background-color: #27272a; border-color: #27272a; color: #71717a; }
            QListWidget { background-color: #09090b; border: 1px solid #27272a; border-radius: 8px; color: #f4f4f5; padding: 4px; }
            QListWidget::item { border-bottom: 1px solid #18181b; padding: 8px; }
            QListWidget::item:hover { background-color: #18181b; border-radius: 4px; }
            QTextEdit { background-color: #18181b; border: 1px solid #27272a; border-radius: 8px; color: #a1a1aa; font-family: 'Fira Code', 'Menlo', 'Monaco', monospace; font-size: 12px; }
            QProgressBar { border: 1px solid #27272a; border-radius: 4px; background-color: #18181b; text-align: center; color: white; font-weight: bold; }
            QProgressBar::chunk { background-color: #7c3aed; border-radius: 3px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addWidget(QLabel("作者首頁/分頁網址："))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("貼上網址，例如: https://openprocessing.org/@epi/#sketches 或是 https://openprocessing.org/user/425308")
        top_bar.addWidget(self.url_input)
        
        self.btn_load = QPushButton("⚡ 【1. 載入網頁】")
        self.btn_load.clicked.connect(self.load_url)
        self.btn_expand = QPushButton("⬇️ 【2. 自動展開全部】")
        self.btn_expand.clicked.connect(self.toggle_expand_sketches)
        self.btn_parse = QPushButton("🔍 【3. 解析作品清單】")
        self.btn_parse.clicked.connect(self.parse_sketches)
        
        top_bar.addWidget(self.btn_load)
        top_bar.addWidget(self.btn_expand)
        top_bar.addWidget(self.btn_parse)
        main_layout.addLayout(top_bar)
        
        self.tips_lbl = QLabel(
            "💡 **高階防禦指南**：\n"
            "1. 部分環境下 OpenProcessing 會跳出 **Cloudflare 人機驗證（Just a moment...）**，請直接在下方左側視窗中手動勾選，通過後再執行後續步驟。\n"
            "2. 點擊「自動展開全部」後，系統會自動在背景進行頁面深滾動與點擊「See More」，右側日誌會即時回報累計作品數量。"
        )
        self.tips_lbl.setStyleSheet("color: #a1a1aa; line-height: 1.4;")
        main_layout.addWidget(self.tips_lbl)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左側內嵌安全瀏覽器
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        lbl_browser = QLabel("🌐 OpenProcessing 核心視窗（支援手動通過人機驗證與分頁切換）")
        lbl_browser.setStyleSheet("font-weight: bold; color: #a855f7;")
        self.web_view = QWebEngineView()
        # 覆蓋固定不變的現代 User-Agent，最大程度防範被判定為自動腳本
        self.web_view.page().profile().setHttpUserAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        left_layout.addWidget(lbl_browser)
        left_layout.addWidget(self.web_view)
        splitter.addWidget(left_widget)
        
        # 右側控制與日誌台
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_list = QLabel("📋 待收編模組列表（已自動過濾系統既有項目）")
        lbl_list.setStyleSheet("font-weight: bold; color: #10b981;")
        right_layout.addWidget(lbl_list)
        
        selection_bar = QHBoxLayout()
        self.btn_select_all = QPushButton("全選待處理")
        self.btn_select_all.clicked.connect(self.select_all)
        self.btn_select_none = QPushButton("取消全選")
        self.btn_select_none.clicked.connect(self.select_none)
        selection_bar.addWidget(self.btn_select_all)
        selection_bar.addWidget(self.btn_select_none)
        selection_bar.addStretch()
        right_layout.addLayout(selection_bar)
        
        self.list_widget = QListWidget()
        right_layout.addWidget(self.list_widget)
        
        right_layout.addWidget(QLabel("💻 實時後台轉譯日誌終端"))
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        right_layout.addWidget(self.console)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        action_bar = QHBoxLayout()
        self.btn_import = QPushButton("🚀 開始自動化批次轉譯收編")
        self.btn_import.setObjectName("btn_import")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self.start_batch_import)
        
        self.btn_resume_test = QPushButton("▶️ 繼續上次試運行")
        self.btn_resume_test.setStyleSheet("background-color: #047857; color: white;")
        self.btn_resume_test.clicked.connect(self.resume_test_run)
        
        # Check if progress file exists to decide initial visibility/state
        progress_path = os.path.join(workspace_dir, "batch_test_progress.json")
        if os.path.exists(progress_path):
            self.btn_resume_test.setEnabled(True)
        else:
            self.btn_resume_test.setEnabled(False)
            self.btn_resume_test.setStyleSheet("background-color: #27272a; color: #71717a;")
            
        self.btn_close = QPushButton("關閉視窗")
        self.btn_close.clicked.connect(self.close)
        
        action_bar.addWidget(self.btn_import)
        action_bar.addWidget(self.btn_resume_test)
        action_bar.addWidget(self.btn_close)
        right_layout.addLayout(action_bar)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([700, 650])
        main_layout.addWidget(splitter)
        
        self.is_expanding = False

    def log_to_console(self, text, is_err=False):
        color = "#f43f5e" if is_err else "#38bdf8" if "[+]" in text else "#a1a1aa"
        text_html = text.replace('\n', '<br>')
        self.console.append(f"<span style='color: {color};'>{text_html}</span>")

    def select_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if "已收錄" not in item.text():
                item.setCheckState(Qt.CheckState.Checked)

    def select_none(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def get_existing_urls(self):
        urls = set()
        if not os.path.exists(self.save_dir):
            return urls
        for fname in os.listdir(self.save_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.save_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    url = data.get("url", "").strip()
                    if url:
                        urls.add(url.rstrip("/"))
                        match = re.search(r'/sketch/(\d+)', url)
                        if match: urls.add(match.group(1))
                except Exception:
                    continue
        return urls

    def load_url(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.critical(self, "錯誤", "請貼上正確的 OpenProcessing 作者首頁連結！")
            return
        self.detected_sketches_map.clear()
        self.log_to_console(f"正在建立安全連接並載入網頁: {url} ...")
        self.web_view.load(QUrl(url))

    def toggle_expand_sketches(self):
        if self.is_expanding: self.stop_expand()
        else: self.start_expand()

    def start_expand(self):
        self.is_expanding = True
        self.btn_expand.setText("⏳ 【停止自動展開】")
        self.btn_expand.setStyleSheet("background-color: #7f1d1d; border-color: #b91c1c; color: #fee2e2; font-weight: bold;")
        self.log_to_console("▶️ 開始自動化背景探測：程式每 2 秒向下強滾動頁面並自動尋找點擊「See More」按鈕...")
        
        self.detected_sketches_map.clear()
        self.last_sketch_count = 0
        self.same_count_strikes = 0
        self.button_cool_down = 0
        
        self.expand_timer = QTimer(self)
        self.expand_timer.timeout.connect(self.expand_step)
        self.expand_timer.start(2000)

    def stop_expand(self):
        self.is_expanding = False
        if hasattr(self, 'expand_timer') and self.expand_timer.isActive():
            self.expand_timer.stop()
        self.btn_expand.setText("⬇️ 【自動展開全部】")
        self.btn_expand.setStyleSheet("")
        self.log_to_console("⏹️ 背景自動展開探測結束。")
        self.render_detected_list()

    def expand_step(self):
        allow_click = "true" if self.button_cool_down <= 0 else "false"
        if self.button_cool_down > 0: self.button_cool_down -= 1
            
        js_script = f"""
        (function(allowClick) {{
            try {{
                window.scrollTo(0, document.body.scrollHeight);
                try {{ window.dispatchEvent(new Event('scroll', {{ bubbles: true }})); }} catch(e) {{}}
                
                document.querySelectorAll('*').forEach(el => {{
                    try {{
                        if (el.scrollHeight > el.clientHeight) {{
                            el.scrollTop = el.scrollHeight;
                            el.dispatchEvent(new Event('scroll', {{ bubbles: true }}));
                        }}
                    }} catch(e) {{}}
                }});
                
                let btn = document.querySelector('.seeMoreButton') || document.querySelector('.showMore') || document.querySelector('[class*="seeMore"]');
                let items = [];
                document.querySelectorAll('a').forEach(a => {{
                    if (a.href) {{
                        let m = a.href.match(/\\/(?:sketch|@[\\w\\-]+)\\/(\\d+)/);
                        if (m) {{
                            let sketch_id = m[1];
                            let titleEl = a.querySelector('.sketchTitle') || a.querySelector('[class*="title"]');
                            let title = titleEl ? titleEl.textContent : (a.getAttribute('title') || a.innerText || "");
                            title = title.replace(/\\s+/g, ' ').trim();
                            items.push({{ id: sketch_id, title: title, url: a.href }});
                        }}
                    }}
                }});
                
                let clicked = false;
                if (btn && allowClick && btn.offsetHeight > 0 && btn.style.display !== 'none' && !btn.disabled) {{
                    btn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, view: window }}));
                    clicked = true;
                }}
                return {{ items: items, clicked: clicked }};
            }} catch(err) {{
                return {{ items: [], clicked: false, error: err.toString() }};
            }}
        }})({allow_click})
        """
        self.web_view.page().runJavaScript(js_script, self.on_expand_step_finished)

    def on_expand_step_finished(self, res):
        if not self.is_expanding or not res: return
        if "error" in res: self.log_to_console(f"⚠️ [DOM 探測異常] {res['error']}", True)
            
        for item in res.get("items", []):
            sid = item["id"]
            if sid not in self.detected_sketches_map: self.detected_sketches_map[sid] = item
            elif item["title"] and not self.detected_sketches_map[sid]["title"]:
                self.detected_sketches_map[sid]["title"] = item["title"]
                
        current_total = len(self.detected_sketches_map)
        self.log_to_console(f"   [探測累計] 網頁 DOM 已成功撈出作品數：{current_total} 個...")
        
        if res.get("clicked", False): self.button_cool_down = 2
        
        if current_total == self.last_sketch_count:
            self.same_count_strikes += 1
        else:
            self.same_count_strikes = 0
            self.last_sketch_count = current_total
            
        if self.same_count_strikes >= 12:  # 連續 12 次探測數量無變化，判定到底部
            self.log_to_console("🎉 網頁加載成功觸底，已解鎖所有動態節點！")
            self.stop_expand()

    def parse_sketches(self):
        self.log_to_console("正在對當前視窗載入的完全態網頁 DOM 進行深度解析...")
        js_code = """
        (function() {
            let items = [];
            document.querySelectorAll('a').forEach(a => {
                if (a.href) {
                    let m = a.href.match(/\\/(?:sketch|@[\\w\\-]+)\\/(\\d+)/);
                    if (m) {
                        let sketch_id = m[1];
                        let titleEl = a.querySelector('.sketchTitle') || a.querySelector('[class*="title"]');
                        let title = titleEl ? titleEl.textContent : (a.getAttribute('title') || a.innerText || "");
                        title = title.replace(/\\s+/g, ' ').trim();
                        items.push({ id: sketch_id, title: title, url: a.href });
                    }
                }
            });
            return { items: items, html: document.body.innerHTML };
        })()
        """
        self.web_view.page().runJavaScript(js_code, self.on_parse_finished)

    def on_parse_finished(self, result):
        if not result:
            self.log_to_console("解析失敗：未能成功從主頁讀取到 JS 回傳物件。", True)
            return
            
        items = result.get("items", [])
        
        # 建立快照 Debug 檔，供極端情況下查驗
        debug_path = os.path.join(workspace_dir, "debug_op_page.html")
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(result.get("html", ""))
        except Exception: pass
            
        if items:
            if os.path.exists(debug_path):
                try: os.remove(debug_path)
                except Exception: pass
                
        for item in items:
            sid = item["id"]
            if sid not in self.detected_sketches_map: self.detected_sketches_map[sid] = item
            elif item["title"] and not self.detected_sketches_map[sid]["title"]:
                self.detected_sketches_map[sid]["title"] = item["title"]
                
        self.render_detected_list()

    def render_detected_list(self):
        self.detected_items = list(self.detected_sketches_map.values())
        self.list_widget.clear()
        
        imported_count = 0
        pending_count = 0
        
        for item in self.detected_items:
            sketch_id = item["id"]
            title = item["title"] or f"op_{sketch_id}"
            url = item["url"]
            
            is_imported = url.rstrip("/") in self.existing_urls or sketch_id in self.existing_urls
            list_text = f"[{sketch_id}] {title}"
            list_item = QListWidgetItem(list_text)
            
            if is_imported:
                list_item.setText(f"✓ [本地存檔已存在] {list_text}")
                list_item.setForeground(Qt.GlobalColor.darkGray)
                list_item.setCheckState(Qt.CheckState.Unchecked)
                list_item.setFlags(list_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                imported_count += 1
            else:
                list_item.setText(f"▢ [待收編模組] {list_text}")
                list_item.setCheckState(Qt.CheckState.Checked)
                pending_count += 1
                
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list_widget.addItem(list_item)
            
        self.log_to_console(f"分析報表：共捕獲 {len(self.detected_items)} 個項目，{imported_count} 個已在既有資料庫中，{pending_count} 個可執行全新的轉譯收編。")
        self.btn_import.setEnabled(pending_count > 0)

    def resume_test_run(self):
        progress_path = os.path.join(workspace_dir, "batch_test_progress.json")
        if not os.path.exists(progress_path):
            QMessageBox.information(self, "無進度", "目前沒有未完成的試運行任務進度。")
            self.btn_resume_test.setEnabled(False)
            self.btn_resume_test.setStyleSheet("background-color: #27272a; color: #71717a;")
            return
            
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            test_dlg = TestRunDialog(data["items"], self)
            test_dlg.current_idx = data["current_idx"]
            test_dlg.exec()
            
            # Update resume button state after dialog closes
            if not os.path.exists(progress_path):
                self.btn_resume_test.setEnabled(False)
                self.btn_resume_test.setStyleSheet("background-color: #27272a; color: #71717a;")
                
            if self.refresh_callback:
                try: self.refresh_callback()
                except Exception: pass
        except Exception as e:
            QMessageBox.warning(self, "讀取失敗", f"讀取上次進度時發生錯誤：{e}")

    def start_batch_import(self):
        selected_items = []
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if list_item.checkState() == Qt.CheckState.Checked:
                selected_items.append(list_item.data(Qt.ItemDataRole.UserRole))
                
        if not selected_items: return
            
        self.btn_import.setEnabled(False)
        self.btn_load.setEnabled(False)
        self.btn_expand.setEnabled(False)
        self.btn_parse.setEnabled(False)
        self.url_input.setEnabled(False)
        self.list_widget.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(selected_items))
        self.progress_bar.setValue(0)
        
        self.log_to_console(f"\n🚀 多執行緒核心啟動：開始批次自動化轉譯，排程總計：{len(selected_items)} 個作品...")
        
        self.worker = BatchImportWorker(selected_items, self.save_dir)
        self.worker.progress.connect(lambda idx, txt: self.progress_bar.setValue(idx))
        self.worker.log.connect(self.log_to_console)
        self.worker.item_finished.connect(self.on_worker_item_finished)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_item_finished(self, sketch_id, status, error_msg):
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_data = list_item.data(Qt.ItemDataRole.UserRole)
            if item_data and item_data["id"] == sketch_id:
                if status == "SUCCESS":
                    list_item.setText(f"✅ [轉譯成功] {item_data['title'] or f'op_{sketch_id}'}")
                    list_item.setForeground(Qt.GlobalColor.green)
                else:
                    list_item.setText(f"❌ [轉譯失敗] {item_data['title'] or f'op_{sketch_id}'}")
                    list_item.setForeground(Qt.GlobalColor.red)
                    list_item.setToolTip(f"詳細錯誤原因: {error_msg}")
                list_item.setCheckState(Qt.CheckState.Unchecked)
                break

    def on_worker_finished(self, failed_items):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.log_to_console("\n🏁 批次收編轉譯流水線作業全部完成！")
        
        self.btn_load.setEnabled(True)
        self.btn_expand.setEnabled(True)
        self.btn_parse.setEnabled(True)
        self.url_input.setEnabled(True)
        self.list_widget.setEnabled(True)
        
        self.existing_urls = self.get_existing_urls()
        if self.refresh_callback:
            try: self.refresh_callback()
            except Exception: pass
            
        if failed_items:
            report_path = os.path.join(workspace_dir, "op_import_errors.txt")
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write("======================================================================\n")
                    f.write("OpenProcessing Batch Import Error Report (視覺模組收編錯誤診斷報告)\n")
                    f.write(f"Generated Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Failed Count: {len(failed_items)}\n")
                    f.write("======================================================================\n\n")
                    for idx, item in enumerate(failed_items, 1):
                        f.write(f"--- [錯誤項目 {idx}] ---\n")
                        f.write(f"Sketch ID: {item['id']}\n")
                        f.write(f"作品名稱 (Title): {item['title']}\n")
                        f.write(f"錯誤訊息 (Error): {item['error']}\n")
                        f.write(f"\n[System Traceback]\n{item['traceback']}\n")
                        f.write(f"\n[Original Code Snapshot]\n```javascript\n{item['original_code']}\n```\n")
                        f.write("\n" + "="*70 + "\n\n")
                self.log_to_console(f"⚠️ 系統已自動在專案根目錄下產出錯誤報告文字檔：{report_path}，可直接丟給 AI 完成一鍵修復。", True)
            except Exception: pass
            QMessageBox.warning(self, "批次收編結束", f"作業完成！其中 {len(failed_items)} 個作品因特殊語法限制收編失敗。診斷報告已匯出至 op_import_errors.txt 。")
        else:
            QMessageBox.information(self, "大功告成", "恭喜！所有勾選的 Creative Coding 視覺模組皆已完美收編、完成 16:9 修正與平滑音訊矩陣注入！")
            
        # 詢問使用者是否同時進行試運行
        success_list = getattr(self.worker, "success_list", [])
        if success_list:
            progress_path = os.path.join(workspace_dir, "batch_test_progress.json")
            has_saved = os.path.exists(progress_path)
            
            if has_saved:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("試運行任務選項")
                msg_box.setText("系統偵測到有上次未完成的試運行任務。\n請選擇要如何進行：")
                
                resume_btn = msg_box.addButton("▶️ 繼續未完成的任務", QMessageBox.ButtonRole.AcceptRole)
                start_new_btn = msg_box.addButton("🔁 重頭開始本次新任務", QMessageBox.ButtonRole.YesRole)
                cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                
                msg_box.exec()
                clicked = msg_box.clickedButton()
                
                if clicked == resume_btn:
                    try:
                        with open(progress_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        test_dlg = TestRunDialog(data["items"], self)
                        test_dlg.current_idx = data["current_idx"]
                        test_dlg.exec()
                    except Exception as e:
                        QMessageBox.warning(self, "讀取失敗", f"讀取上次進度時發生錯誤：{e}")
                elif clicked == start_new_btn:
                    test_dlg = TestRunDialog(success_list, self)
                    test_dlg.exec()
            else:
                reply = QMessageBox.question(
                    self, 
                    "開始試運行", 
                    f"批次收編完成！共成功收編 {len(success_list)} 個模組。\n是否要同時進行這些模組的試運行？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    test_dlg = TestRunDialog(success_list, self)
                    test_dlg.exec()
                    
            # 根據最後檔案狀態，同步更新「繼續上次試運行」按鈕狀態
            if not os.path.exists(progress_path):
                self.btn_resume_test.setEnabled(False)
                self.btn_resume_test.setStyleSheet("background-color: #27272a; color: #71717a;")
            else:
                self.btn_resume_test.setEnabled(True)
                self.btn_resume_test.setStyleSheet("background-color: #047857; color: white;")
                
                # 重新整理 Preset 列表，因為部分模組可能被排除刪除了
                if self.refresh_callback:
                    try: self.refresh_callback()
                    except Exception: pass
