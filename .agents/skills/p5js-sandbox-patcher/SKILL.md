---
name: p5js-sandbox-patcher
description: 轉譯 Processing (Java) 代碼為 ES6 p5.js，並為 p5.js 運行沙盒環境注入防崩潰 Stubs (如免疫 Element.style、Element.position、ml5 等庫缺失錯誤)
---

# p5.js Sandbox Patcher & Transpiler Skill

本 Skill 專門用於創意代碼（Creative Coding）的語法自動轉譯、安全性沙盒建立與運行時錯誤免疫，整理自本專案的 `batch_importer.py`。

## 1. Processing (Java) 轉 ES6 p5.js 核心正則轉譯規則

當程式碼中包含 `void setup` 或 `void draw` 時，代表其為 Java-style Processing，需要進行轉譯：

```python
import re

def transpile_processing_to_js(src):
    # 0. 先行遮罩字串與 GLSL Shader 範本字面量，防止內部 void / float / int 等被誤轉譯
    placeholders = {}
    def _mask_str(m):
        key = f"__STR_LITERAL_PLACEHOLDER_{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key
    transpiled = re.sub(r'(`[\s\S]*?`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', _mask_str, src)
    
    # (a) 移除 Java 存取修飾詞與 final
    transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
    transpiled = re.sub(r'\bfinal\s+', '', transpiled)
    
    # (b) 修正 Java 浮點數/整數轉型：(int)x -> int(x)
    transpiled = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', transpiled)
    transpiled = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', transpiled)
    
    # (c) 修正 Java 複雜陣列宣告 (如: int[] x = {1, 2}; 或 Object[] o = new Object[5];)
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', transpiled)
    transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', transpiled)
    
    # (d) 修正變數與函式宣告 (類型替換為 let / function)
    transpiled = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', transpiled)
    transpiled = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', transpiled)
    
    # (e) 移除 float 字面量後綴 f (例如 0.85f -> 0.85)
    transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
    
    # (f) 轉換 for-each 迴圈 (例如 for (Particle p : list) -> for (let p of list))
    transpiled = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', transpiled)
    
    # 還原字串與 GLSL Shader
    for k, v in placeholders.items():
        transpiled = transpiled.replace(k, v)
        
    return transpiled
```

## 2. 運行時防崩潰防禦性注入 (JavaScript Immunity Proxies)

當任意第三方視覺代碼（如 OpenProcessing 抓取的 Canvas 腳本）在 Web 容器中執行時，為了防範其因為缺乏 DOM 元件、特定函式庫（如 `ml5.js`, `Tone.js`, `THREE.Group`）而拋錯中斷，應在運行前預先注入以下防護機制：

```javascript
// 1. 免疫 DOM 元素建立與樣式操作拋錯
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
  dummyObject.position = dummyObject.style = dummyObject.size = dummyObject.parent = function() { return dummyObject; };
  dummyObject.id = function() { return ""; };
  dummyObject.class = dummyObject.mousePressed = dummyObject.html = function() { return dummyObject; };
  dummyObject.value = function() { return 0; };
  
  const styleProxy = new Proxy(dummyObject, handler);
  
  if (typeof createP === 'undefined') window.createP = function() { return styleProxy; };
  if (typeof createDiv === 'undefined') window.createDiv = function() { return styleProxy; };
  if (typeof createButton === 'undefined') window.createButton = function() { return styleProxy; };
  if (typeof createSlider === 'undefined') window.createSlider = function() { return styleProxy; };
})();

// 2. 免疫 Element.prototype.size / style / checked 覆寫或崩潰
try {
  if (typeof Element !== 'undefined') {
    if (!Element.prototype.size) Element.prototype.size = function() { return this; };
    const dummyObj = function() { return dummyObj; };
    const p = new Proxy(dummyObj, { get: (t, prop) => p });
    Object.defineProperty(Element.prototype, 'style', {
      get: () => {
        const styleFunc = () => p;
        Object.setPrototypeOf(styleFunc, p);
        return styleFunc;
      },
      configurable: true
    });
  }
} catch(e) {}

// 3. 免疫機器學習、物理引擎與 p5.Image / p5.Graphics 缺失方法
if (typeof window.ml5 === 'undefined') {
    const mock = { on: () => {}, ready: Promise.resolve(), features: { get: () => [] } };
    window.ml5 = { poseNet: () => mock, bodypix: () => mock, handpose: () => mock };
}
if (typeof PVector === 'undefined') {
    window.PVector = class {
        constructor(x,y,z) { this.x=x||0; this.y=y||0; this.z=z||0; }
        static dist(v1,v2) { return Math.sqrt((v1.x-v2.x)**2+(v1.y-v2.y)**2); }
    };
}
if (typeof p5 !== 'undefined') {
  if (p5.Image && p5.Image.prototype) {
    if (!p5.Image.prototype.resize) p5.Image.prototype.resize = function(w, h) { if(w) this.width=w; if(h) this.height=h; return this; };
    if (!p5.Image.prototype.loadPixels) p5.Image.prototype.loadPixels = function() {};
    if (!p5.Image.prototype.updatePixels) p5.Image.prototype.updatePixels = function() {};
    if (!p5.Image.prototype.get) p5.Image.prototype.get = function() { return [0, 0, 0, 0]; };
  }
}

// 4. 免疫 Processing 渲染模式常量與未定義全域變數拋錯
if (typeof window.P3D === 'undefined') window.P3D = "webgl";
if (typeof window.OPENGL === 'undefined') window.OPENGL = "webgl";
if (typeof window.P2D === 'undefined') window.P2D = "p2d";
if (typeof window.JAVA2D === 'undefined') window.JAVA2D = "p2d";
['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'].forEach(k => {
    if (typeof window[k] === 'undefined') window[k] = k.toLowerCase();
});
['paper', 'col2', 'col1', 'S_actual', 'maxD', 'looping', 'sinput', 'SZ', 'medRadius', 'minRadius', 'maxRadius', 'locations', 'grid_size', 'circle_diams', 'dots', 'points', 'particles', 'img', 'imgs', 'moon', 'bg', 'palette'].forEach(k => {
    if (typeof window[k] === 'undefined') {
        if (['dots','points','particles','locations','palette','circle_diams','imgs'].includes(k)) window[k] = [];
        else if (['img','moon'].includes(k)) window[k] = { width: 100, height: 100, resize: function(w,h){ if(w) this.width=w; if(h) this.height=h; return this; }, loadPixels: function(){}, updatePixels: function(){}, get: function(){ return [0,0,0,0]; } };
        else if (['paper','pg'].includes(k)) window[k] = { width: 100, height: 100, beginDraw: function(){}, endDraw: function(){}, background: function(){}, image: function(){}, get: function(){ return this; }, resize: function(){ return this; } };
        else if (['col1','col2','bg'].includes(k)) window[k] = '#ffffff';
        else if (k === 'looping') window[k] = true;
        else window[k] = 0;
    }
});
```
