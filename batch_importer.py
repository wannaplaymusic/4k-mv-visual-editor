import os
import re
import json
import random
import datetime
import traceback
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QListWidget, QListWidgetItem, QProgressBar, QTextEdit,
    QSplitter, QMessageBox, QWidget, QApplication, QCheckBox, QComboBox,
    QScrollArea, QFrame, QGroupBox, QPlainTextEdit
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices

from batch_history_manager import BatchHistoryManager
from test_run_logger import TestRunLogger

# 取得 workspace 目錄路徑
workspace_dir = os.path.dirname(os.path.abspath(__file__))

DEFAULT_FILTER_OPTIONS = {
    "skip_games": True,
    "skip_camera_ar": True,
    "hide_controls": True,
    "skip_text_heavy": True,
    "skip_heavy_loading": True,
    "skip_static": True
}

def validate_visual_module_eligibility(title, code, custom_html="", tags=None, desc="", filter_options=None):
    """
    4K MV 視覺預設模組收錄過濾器（支援自訂勾選選項）：
    - skip_camera_ar: 攝影機與 AR/VR/XR
    - skip_games: 遊戲類別與計分勝負互動
    - skip_heavy_loading: 多遠端資源/大型 3D 模型/AI 權重
    - skip_text_heavy: 純文字/排版字型展示模組
    - skip_static: 純靜態無動態模組
    回傳 (is_eligible, reject_reason)
    """
    if filter_options is None:
        filter_options = DEFAULT_FILTER_OPTIONS

    tags = [t.lower().strip() for t in (tags or [])]
    text_check = f"{title.lower()} {' '.join(tags)} {desc.lower()} {code.lower()[:3000]} {custom_html.lower()}"
    full_content = code + "\n" + custom_html

    # 1. 攝影機與 AR / XR / VR (Camera / Webcam / AR / VR)
    if filter_options.get("skip_camera_ar", True):
        if re.search(r'\bcreateCapture\s*\(', full_content, re.IGNORECASE) and not ("p5capture" in full_content.lower() and not any(kw in full_content.lower() for kw in ["video", "camera", "webcam"])):
            return False, "含有攝影機輸入 (createCapture)"
        if re.search(r'\b(getUserMedia|clmtrackr|webcam|live_camera|videoCapture)\b', full_content, re.IGNORECASE):
            return False, "含有攝影機/Webcam 調用"
        if any(t in ['webcam', 'camera', 'camera capture', 'video capture'] for t in tags):
            return False, "標籤含有攝影機/Webcam"
        ar_xr_kws = ['webxr', 'webvr', 'xrsession', 'vrbutton', 'arbutton', 'webgl_vr', 'p5.vr', 'mindar', 'artoolkit', 'a-scene', 'a-entity', 'zappar', 'augmented reality', 'virtual reality']
        for kw in ar_xr_kws:
            if kw in text_check:
                return False, f"含有 AR/XR/VR 呼叫 ({kw})"
        if any(t in ['ar', 'xr', 'vr', 'webxr', 'webvr', 'augmented-reality', 'virtual-reality'] for t in tags):
            return False, "標籤含有 AR/XR/VR"

    # 2. 遊戲類型模組 (GAME)
    if filter_options.get("skip_games", True):
        game_types = ['tetris', 'flappy', 'pacman', 'pac-man', 'mario', 'breakout', 'asteroids', 'minesweeper', 'tictactoe', 'tic-tac-toe', 'sudoku', 'chess', 'shooter', 'invader', 'pinball', 'racing game', 'platformer', 'pong', 'samegame', 'gameport', 'hotorcoldgame', 'constraingame', '3dgame', 'duelashootergame']
        for kw in game_types:
            if kw in title.lower().replace(' ', '') or any(kw in t.replace(' ', '') for t in tags):
                if kw == 'asteroids' and 'planet' in title.lower():
                    continue
                return False, f"含有遊戲類型特徵 ({kw})"
        if any(t in ['game', 'games', 'gaming', 'arcade', 'minigame', 'gameplay'] for t in tags):
            return False, "標籤含有遊戲類別 (Game/Arcade)"
        clean_title = title.lower()
        if not clean_title.startswith('pixel_') and ('game' in clean_title or 'arcade' in clean_title):
            return False, f"標題含有遊戲關鍵字 ({title})"
        # 檢測遊戲機制 (Score + GameOver + Lives/Health)
        code_lower = code.lower()
        if re.search(r'\b(game_?over|you win|you lose)\b', code_lower) and re.search(r'\b(score\s*\+=|lives\s*-=|highscore|restartgame)\b', code_lower):
            return False, "代碼含有互動遊戲計分與勝負機制"

    # 3. 高耗時加載模組 (Heavy Loading)
    if filter_options.get("skip_heavy_loading", True):
        media_loads = re.findall(r'\b(loadImage|loadSound|loadModel|loadFont|loadJSON|loadBytes|loadStrings|createVideo)\s*\(\s*[\'\"`](https?://[^\'\"`]+)[\'\"`]', code)
        if len(media_loads) >= 2:
            return False, f"含有多重外部遠端媒體資源加載 ({len(media_loads)} 個)"
        all_urls = re.findall(r'https?://[^\s\'\"`)]+', full_content)
        non_cdn = [u for u in all_urls if not any(c in u for c in ['cdnjs', 'jsdelivr', 'unpkg', 'openprocessing.org', 'google', 'esm', 'github'])]
        if len(non_cdn) >= 5:
            return False, f"含有過多外部第三方遠端依賴 ({len(non_cdn)} 個)"
        if re.search(r'\b(loadModel|loadGLTF|GLTFLoader|OBJLoader)\s*\(', code):
            return False, "含有重型 3D 幾何模型載入 (GLTF/OBJ/FBX)"
        if re.search(r'\b(ml5\.(bodyPix|poseNet|imageClassifier|featureExtractor|yolo|unet|facemesh|handpose)|tf\.loadLayersModel|tf\.loadGraphModel)\b', full_content):
            return False, "含有大型 AI/ML 模型權重加載"
        if len(code) > 800 * 1024:
            return False, f"代碼或資料體積過大 ({len(code)//1024}KB > 800KB)"

    # 4. 純文字 / 排版展示模組 (Text-heavy / Typography)
    if filter_options.get("skip_text_heavy", True):
        # 標題或標籤含有排版字型特徵
        text_kws = ['typography', 'alphabet', 'pangram', 'word cloud', 'ascii art', 'type design', 'text particle']
        for tkw in text_kws:
            if tkw in text_check:
                return False, f"屬於純文字/排版字型展示模組 ({tkw})"
        # 檢測 text() 密集調用且缺乏其他幾何繪圖
        text_calls = len(re.findall(r'\btext\s*\(', code))
        font_calls = len(re.findall(r'\b(textFont|loadFont|textSize|textAlign)\s*\(', code))
        if font_calls >= 2 and text_calls >= 6:
            geom_calls = len(re.findall(r'\b(rect|circle|ellipse|vertex|triangle|sphere|box|point|curve|bezier)\s*\(', code))
            if geom_calls < 3:
                return False, f"文字輸出佔據主導且缺乏幾何動畫 (text調用: {text_calls}次)"

    # 5. 純靜態無動態模組 (Static / Non-animated)
    if filter_options.get("skip_static", True):
        # 呼叫了 noLoop() 且沒有事件監聽觸發重繪
        if re.search(r'\bnoLoop\s*\(\s*\)', code):
            has_redraw = re.search(r'\b(redraw|loop)\s*\(', code)
            has_interaction = any(ev in code for ev in ['mouseMoved', 'mouseDragged', 'mousePressed', 'keyPressed', 'touchStarted'])
            if not has_redraw and not has_interaction:
                return False, "模組調用 noLoop() 且無任何動態重繪或互動"
        # 只有 setup() 沒有 draw() 函數
        if "setup" in code and "draw" not in code:
            return False, "模組僅包含靜態 setup()，缺乏 draw() 連續幀動畫"

    return True, ""

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
    - 精準 Processing Java 語法轉譯
    - 自動對接音畫反應矩陣 (LiveAudioBeatDetector)
    - 注入崩潰防護 Stubs
    """
    if not code.strip():
        return ""

    adapted = code
    if sketch_id:
        adapted = rewrite_relative_assets(adapted, sketch_id)

    # 1. Processing (Java) 轉 JavaScript
    if any(kw in adapted for kw in ["void setup", "void draw"]):
        def transpile_processing_to_js(src):
            placeholders = {}
            def _mask_str(m):
                key = f"__STR_LITERAL_PLACEHOLDER_{len(placeholders)}__"
                placeholders[key] = m.group(0)
                return key
            transpiled = re.sub(r'(`[\s\S]*?`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', _mask_str, src)
            
            transpiled = re.sub(r'\b(private|public|protected|static|transient|volatile)\s+', '', transpiled)
            transpiled = re.sub(r'\bfinal\s+', '', transpiled)
            
            transpiled = re.sub(r'\((int|float|double)\)\s*([A-Za-z0-9_$\.]+)', r'\1(\2)', transpiled)
            transpiled = re.sub(r'\((int|float|double)\)\s*\(([^)]+)\)', r'\1(\2)', transpiled)
            transpiled = re.sub(r'\((double|char|long|boolean)\)\s*', '', transpiled)
            
            transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*\{([\s\S]*?)\}\s*;', r'let \1 = [\2];', transpiled)
            transpiled = re.sub(r'\b[A-Za-z0-9_$\.]+\[\]\s+([A-Za-z0-9_$\.]+)\s*=\s*new\s+[A-Za-z0-9_$\.]+\[([^\]]+)\]\s*;', r'let \1 = new Array(\2);', transpiled)
            
            transpiled = re.sub(r'(?<!\bclass\s)\b(?:int|float|double|boolean|color|char|[A-Z]\w*)(?:\[\])?\s+(?!(?:extends|implements|new|instanceof|return)\b)([A-Za-z0-9_$\.]+)\b(?!\s*\()', r'let \1', transpiled)
            transpiled = re.sub(r'\bfor\s*\(\s*(int|float|double)\s+', 'for (let ', transpiled)
            transpiled = re.sub(r'\bvoid\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \1(', transpiled)
            
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
                    brace_depth += line.count('{') - line.count('}')
                    new_lines.append(line)
                    continue
                
                if in_class:
                    is_class_body_field = (brace_depth == 1)
                    brace_depth += line.count('{') - line.count('}')
                    if brace_depth <= 0:
                        in_class = False
                    if class_name and re.search(r'\b' + class_name + r'\s*\(', line):
                        line = re.sub(r'\b' + class_name + r'\s*\(', 'constructor(', line)
                    elif re.search(r'\b(void|int|float|double|boolean|color|char|[A-Z]\w*)\s+([A-Za-z0-9_$\.]+)\s*\(', line):
                        line = re.sub(r'\b(void|int|float|double|boolean|color|char|[A-Z]\w*)\s+([A-Za-z0-9_$\.]+)\s*\(', r'\2(', line)
                    
                    if is_class_body_field:
                        stripped = line.strip()
                        if re.match(r'^(let|var|const)\s+', stripped) and '(' not in stripped:
                            line = re.sub(r'^(\s*)(let|var|const)\s+', r'\1', line)
                    
                    if '(' in line and ')' in line:
                        def clean_params(m):
                            params = m.group(1)
                            cleaned = re.sub(r'\blet\s+', '', params)
                            return '(' + cleaned + ')'
                        line = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', clean_params, line)
                else:
                    line = re.sub(r'\b(int|float|double|boolean|color|char|[A-Z]\w*)\s+([A-Za-z0-9_$\.]+)\s*\(', r'function \2(', line)
                
                new_lines.append(line)
            
            transpiled = "\n".join(new_lines)
            
            def clean_global_params(m):
                params = m.group(1)
                cleaned = re.sub(r'\blet\s+', '', params)
                return '(' + cleaned + ')'
            transpiled = re.sub(r'\(([^)]*\blet\s+[^)]*)\)', clean_global_params, transpiled)
            transpiled = re.sub(r'(\d+\.?\d*)f\b', r'\1', transpiled)
            transpiled = re.sub(r'\bfor\s*\(\s*(?:let\s+)?(?:[A-Z]\w*\s+)?(\w+)\s*:\s*(\w+)\s*\)', r'for (let \1 of \2)', transpiled)
            transpiled = re.sub(r'\bnew\s+\w+\[([^\]]+)\]', r'new Array(\1)', transpiled)
            
            if 'arraycopy' in transpiled and 'function arraycopy' not in transpiled:
                transpiled = "function arraycopy(s,sp,d,dp,l){for(var _i=0;_i<l;_i++)d[dp+_i]=s[sp+_i];}\n" + transpiled
            
            transpiled = re.sub(r'\bfullScreen\s*\(\s*(?:P3D|WEBGL|OPENGL)?\s*\)', 'createCanvas(windowWidth, windowHeight, WEBGL)', transpiled, flags=re.IGNORECASE)
            transpiled = re.sub(r'\bfullScreen\s*\(\s*\)', 'createCanvas(windowWidth, windowHeight)', transpiled)
            transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P3D|WEBGL|OPENGL)\s*\)', r'createCanvas(\1, \2, WEBGL)', transpiled, flags=re.IGNORECASE)
            transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*,\s*(?:P2D|JAVA2D)\s*\)', r'createCanvas(\1, \2)', transpiled, flags=re.IGNORECASE)
            transpiled = re.sub(r'\bsize\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'createCanvas(\1, \2)', transpiled)
            
            # Processing 色碼字面量 #000000 轉為 JS 字串字面量 "#000000"
            transpiled = re.sub(r'(?<![A-Za-z0-9_$])(#[0-9a-fA-F]{3,8})\b', r'"\1"', transpiled)
            
            for k, v in placeholders.items():
                transpiled = transpiled.replace(k, v)
                
            return transpiled

        adapted = transpile_processing_to_js(adapted)

    # 2. 16:9 畫布尺寸適配
    adapted = re.sub(r'\bmin\s*\(\s*windowWidth\s*,\s*windowHeight\s*\)', 'max(windowWidth, windowHeight)', adapted)
    adapted = re.sub(r'\bmin\s*\(\s*width\s*,\s*height\s*\)', 'max(width, height)', adapted)

    # 3. Shader 相容修復
    adapted = re.sub(
        r'new\s+p5\.Shader\s*\(\s*(this\.)?_?renderer\s*,\s*([^,)]+)\s*,\s*([^,)]+)\s*\)',
        r'createShader(\2, \3)',
        adapted
    )

    # 4. 音訊特徵原生對接
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

    adapted = adapted.replace(audio_reactive_mouseX, "___MOUSE_X_PLACEHOLDER___")
    adapted = adapted.replace(audio_reactive_mouseY, "___MOUSE_Y_PLACEHOLDER___")
    adapted = adapted.replace(audio_reactive_pressed, "___MOUSE_PRESSED_PLACEHOLDER___")

    adapted = re.sub(r'(?<!\.)\bmouseX\b', audio_reactive_mouseX, adapted)
    adapted = re.sub(r'(?<!\.)\bmouseY\b', audio_reactive_mouseY, adapted)
    adapted = re.sub(r'(?<!\.)\bpmouseX\b', audio_reactive_mouseX, adapted)
    adapted = re.sub(r'(?<!\.)\bpmouseY\b', audio_reactive_mouseY, adapted)
    adapted = re.sub(r'(?<!\.)\bmouseIsPressed\b', audio_reactive_pressed, adapted)

    adapted = adapted.replace("___MOUSE_X_PLACEHOLDER___", audio_reactive_mouseX)
    adapted = adapted.replace("___MOUSE_Y_PLACEHOLDER___", audio_reactive_mouseY)
    adapted = adapted.replace("___MOUSE_PRESSED_PLACEHOLDER___", audio_reactive_pressed)

    # 5. WebGL 判定
    has_3d_keywords = any(re.search(kw, adapted) for kw in [
        r'\bbox\s*\(', r'\bsphere\s*\(', r'\btorus\s*\(', r'\bcylinder\s*\(',
        r'\brotateX\s*\(', r'\brotateY\s*\(', r'\brotateZ\s*\(', r'\bcone\s*\('
    ])
    if has_3d_keywords and "WEBGL" not in adapted:
        adapted = re.sub(r'createCanvas\s*\(\s*([^,)]*)\s*,\s*([^,)]*)\s*\)', r'createCanvas(\1, \2, WEBGL)', adapted)

    # 6. 多分頁重複頂層 let/const 轉為 var 防止 Identifier already declared 語法錯誤
    lines = adapted.split("\n")
    declared_top_vars = set()
    new_lines = []
    for line in lines:
        m = re.match(r'^(\s*)(let|const)\s+([A-Za-z0-9_$]+)(.*)', line)
        if m:
            indent, kw, varname, rest = m.groups()
            if varname in declared_top_vars:
                new_lines.append(f"{indent}var {varname}{rest}")
            else:
                declared_top_vars.add(varname)
                new_lines.append(line)
        else:
            new_lines.append(line)
    adapted = "\n".join(new_lines)

    return adapted


class BatchImportWorker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, bool)
    item_finished = pyqtSignal(str, str, str)
    finished = pyqtSignal(list)

    def __init__(self, items_to_import, save_dir, batch_id=None, batch_date=None, filter_options=None, history_mgr=None):
        super().__init__()
        self.items = items_to_import
        self.save_dir = save_dir
        self.batch_id = batch_id or f"batch_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.batch_date = batch_date or datetime.datetime.now().strftime("%Y-%m-%d")
        self.filter_options = filter_options or DEFAULT_FILTER_OPTIONS
        self.history_mgr = history_mgr
        self.failed_list = []
        self.success_list = []

    def run(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
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
                retry_delay = 3
                
                for retry in range(max_retries + 1):
                    try:
                        resp = requests.get(embed_url, headers=headers, timeout=12)
                        if resp.status_code == 429:
                            if retry < max_retries:
                                wait_sec = retry_delay * (2 ** retry) + random.uniform(1.0, 2.5)
                                self.log.emit(f"⚠️ [HTTP 429] 限流防護：將於 {wait_sec:.1f} 秒後進行第 {retry+1} 次重試...", True)
                                self.msleep(int(wait_sec * 1000))
                                continue
                            else:
                                raise Exception("無法存取 OpenProcessing (HTTP 429 限流已達上限)")
                        elif resp.status_code != 200:
                            raise Exception(f"無法存取 OpenProcessing (HTTP {resp.status_code})")
                        break
                    except requests.exceptions.RequestException as req_err:
                        if retry < max_retries:
                            self.msleep(3000)
                        else:
                            raise req_err
                
                sketch_json = self.extract_js_object(resp.text, "sketch")
                if not sketch_json:
                    raise ValueError("無法在頁面中解析 sketch 核心資料。")
                
                sketch_data = json.loads(sketch_json)
                title_og = sketch_data.get("title", title)
                versions = sketch_data.get("versions", [])
                if not versions or not versions[0].get("codeObjects", []):
                    raise ValueError("作品代碼庫為空。")
                
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
                        custom_html += tab_code + "\n"
                    else:
                        code += f"// === Tab: {tab_title} ===\n" + tab_code + "\n\n"
                
                # 自動下載依賴資產
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
                        asset_url = file_base + clean_asset
                        local_file_path = os.path.join(assets_dir, clean_asset)
                        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                        try:
                            asset_resp = requests.get(asset_url, headers=headers, timeout=10)
                            if asset_resp.status_code == 200:
                                with open(local_file_path, "wb") as af:
                                    af.write(asset_resp.content)
                        except Exception:
                            pass
                
                meta_matches = re.findall(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', resp.text, re.IGNORECASE)
                author = "未知作者"
                if meta_matches:
                    content = meta_matches[0].replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
                    parts = content.split(" - ")
                    if len(parts) >= 2: author = parts[1].strip()
                if author == "未知作者" or not author:
                    author = sketch_data.get("username", "未知作者")
                
                # 依使用者選項執行視覺模組收錄資格檢測
                tags_list = sketch_data.get("tags", [])
                desc_text = sketch_data.get("description", "")
                is_eligible, reject_reason = validate_visual_module_eligibility(
                    title=title_og,
                    code=code,
                    custom_html=custom_html,
                    tags=tags_list,
                    desc=desc_text,
                    filter_options=self.filter_options
                )

                if not is_eligible:
                    self.log.emit(f"⚠️ 略過不符合規範模組: 「{title_og}」(ID: {sketch_id}) 原因: {reject_reason}", False)
                    try:
                        with open(os.path.join(workspace_dir, "op_import_errors.txt"), "a", encoding="utf-8") as ef:
                            ef.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - SKIPPED ({reject_reason}): {url} - {title_og}\n")
                    except Exception:
                        pass
                    continue

                # 🎛️ 控制項自動無痕隱藏樣式注入 (Pure Canvas)
                if self.filter_options.get("hide_controls", True):
                    pure_canvas_css = (
                        "\n/* === 4K MV Pure Canvas - 全域控制項與 UI 面板隱藏 === */\n"
                        ".dg, .lil-gui, .qs_main, .opc-control, #opc-control-panel, .control-panel, .gui-container,\n"
                        "[class*='gui'], [id*='gui'], [class*='control'], [id*='control'],\n"
                        "[class*='instruction'], [id*='instruction'], [class*='info'], [id*='info'],\n"
                        "[class*='fps'], [id*='fps'], [class*='overlay'], [id*='overlay'],\n"
                        "input, button, select, textarea, label, form {\n"
                        "  display: none !important;\n"
                        "  visibility: hidden !important;\n"
                        "  opacity: 0 !important;\n"
                        "  pointer-events: none !important;\n"
                        "}\n"
                    )
                    if "Pure Canvas" not in custom_css:
                        custom_css = pure_canvas_css + custom_css

                adapted_code = adapt_and_repair_code_text(code, sketch_id=sketch_id)
                
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
                    "tags": ["batch_import", "openprocessing", "audio_reactive", f"batch_{self.batch_date}"],
                    "url": url,
                    "batch_id": self.batch_id,
                    "batch_date": self.batch_date,
                    "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                # 縮圖下載
                thumb_dir = os.path.join(self.save_dir, "thumbnails")
                os.makedirs(thumb_dir, exist_ok=True)
                dest_thumb_path = os.path.join(thumb_dir, f"{unique_name}.jpg")
                thumb_downloaded = False
                for ext in [".jpg", ".png"]:
                    try:
                        thumb_url = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}{ext}"
                        img_resp = requests.get(thumb_url, headers=headers, timeout=5)
                        if img_resp.status_code == 200:
                            with open(dest_thumb_path, "wb") as img_f:
                                img_f.write(img_resp.content)
                            thumb_downloaded = True
                            break
                    except Exception:
                        continue
                
                # 向批次歷史管理器實時登記
                if self.history_mgr:
                    self.history_mgr.record_imported_item(
                        self.batch_id,
                        sketch_id,
                        title_og,
                        candidate,
                        f"{unique_name}.jpg" if thumb_downloaded else None,
                        os.path.join("custom_visuals", "assets", str(sketch_id)) if asset_names else None
                    )

                self.log.emit(f"  [+] 【成功收編】作品「{title_og}」(批次: {self.batch_date})", False)
                self.success_list.append({
                    "id": sketch_id, "title": title, "url": url, "filename": candidate,
                    "filepath": save_path, "code": adapted_code, "custom_html": custom_html,
                    "custom_css": custom_css, "save_dir": self.save_dir, "batch_id": self.batch_id
                })
                self.item_finished.emit(sketch_id, "SUCCESS", "")
                
            except Exception as e:
                err_detail = traceback.format_exc()
                self.log.emit(f"  [-] 【收編失敗】「{title}」: {e}", True)
                self.item_finished.emit(sketch_id, "ERROR", str(e))
                self.failed_list.append({
                    "id": sketch_id, "title": title, "url": url, "error": str(e),
                    "traceback": err_detail, "original_code": code if 'code' in locals() else "N/A"
                })
            
            self.msleep(int(random.uniform(1200, 2500)))
        
        # 觸發 SENTINEL 語義解析獨立子程序 (非同步處理)
        if self.success_list:
            imported_keys = [item.get("filename", "") for item in self.success_list if item.get("filename")]
            try:
                from semantic_ingestion.hooks import trigger_semantic_ingestion
                trigger_semantic_ingestion(imported_keys, background=True, priority="high")
                self.log.emit(f"🧠 【SENTINEL】已派遣獨立子程序為 {len(imported_keys)} 個新模組解析心靈語義與象徵意義...", False)
            except Exception as hook_err:
                self.log.emit(f"⚠️ SENTINEL 鉤子啟動異常: {hook_err}", True)

        self.finished.emit(self.failed_list)

    def extract_js_object(self, html, var_name):
        pattern = rf'var\s+{var_name}\s*=\s*'
        match = re.search(pattern, html)
        if not match:
            return None
        
        start_idx = match.end()
        first_brace_idx = html.find('{', start_idx)
        if first_brace_idx == -1:
            return None
            
        try:
            decoder = json.JSONDecoder()
            _, end_idx = decoder.raw_decode(html[first_brace_idx:])
            return html[first_brace_idx:first_brace_idx + end_idx]
        except Exception:
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
        layout.addWidget(QLabel('請選擇不收錄此模組的原因：', self))
        
        for name, text, obj_name in [
            ('預覽不正常', '❌ 預覽不正常', 'btn_abnormal'),
            ('一片黑/白/純色', '⚫ 一片黑/白/純色', 'btn_black_white'),
            ('含有控制項', '🎛️ 含有控制項', 'btn_controls'),
            ('遊戲類別', '🎮 遊戲類別', 'btn_game'),
            ('主視覺未居中/滿版', '📐 主視覺未居中/滿版', 'btn_alignment'),
            ('畫面不適用', '🎨 畫面不適用', 'btn_not_applicable')
        ]:
            btn = QPushButton(text, self)
            btn.setObjectName(obj_name)
            btn.clicked.connect(lambda checked, r=name: self.choose_reason(r))
            layout.addWidget(btn)
        
        btn_cancel = QPushButton('取消', self)
        btn_cancel.setObjectName('btn_cancel')
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)
        
    def choose_reason(self, reason_str):
        self.reason = reason_str
        self.accept()


class TestRunLogViewerDialog(QDialog):
    """
    📜 試運行審計日誌檢視器
    """
    def __init__(self, log_path, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle(f"📜 試運行審計日誌 - {os.path.basename(log_path)}")
        self.resize(880, 640)
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 7px 14px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QLineEdit {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 6px 12px; font-size: 12px;
            }
            QPlainTextEdit {
                background-color: #0d0e12; color: #e2e8f0; border: 1px solid #27272a;
                border-radius: 6px; font-family: 'SF Mono', 'Menlo', 'Monaco', 'Consolas', monospace;
                font-size: 12px; line-height: 1.5; padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 頂部控制列
        top_bar = QHBoxLayout()
        info_lbl = QLabel(f"📄 檔案: {os.path.basename(log_path)}", self)
        info_lbl.setStyleSheet("color: #38bdf8; font-weight: bold;")
        top_bar.addWidget(info_lbl)
        top_bar.addStretch()

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 搜尋日誌內容...")
        self.search_input.setFixedWidth(200)
        self.search_input.textChanged.connect(self.filter_content)
        top_bar.addWidget(self.search_input)

        btn_copy = QPushButton("📋 複製全文", self)
        btn_copy.clicked.connect(self.copy_all)
        top_bar.addWidget(btn_copy)

        btn_external = QPushButton("🖥️ 外部編輯器開啟", self)
        btn_external.clicked.connect(self.open_external)
        top_bar.addWidget(btn_external)

        btn_folder = QPushButton("📂 開啟資料夾", self)
        btn_folder.clicked.connect(self.open_folder)
        top_bar.addWidget(btn_folder)

        layout.addLayout(top_bar)

        # 日誌本文區域
        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        # 載入內容
        self.raw_content = ""
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    self.raw_content = f.read()
                self.text_edit.setPlainText(self.raw_content)
            except Exception as e:
                self.text_edit.setPlainText(f"無法讀取日誌內容: {e}")

        # 底部按鈕
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        btn_close = QPushButton("關閉", self)
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)
        layout.addLayout(bottom_bar)

    def filter_content(self, query):
        if not query.strip():
            self.text_edit.setPlainText(self.raw_content)
            return
        lines = self.raw_content.splitlines()
        filtered = [line for line in lines if query.lower() in line.lower()]
        self.text_edit.setPlainText("\n".join(filtered))

    def copy_all(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.raw_content)
        QMessageBox.information(self, "複製成功", "已將完整日誌複製至剪貼簿！")

    def open_external(self):
        if os.path.exists(self.log_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_path))

    def open_folder(self):
        folder = os.path.dirname(self.log_path)
        if os.path.exists(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


class TestRunSummaryDialog(QDialog):
    """
    📊 試運行與清理成果報告總結視窗
    """
    def __init__(self, summary_data, log_path, log_dir, parent=None):
        super().__init__(parent)
        self.summary_data = summary_data or {}
        self.log_path = log_path
        self.log_dir = log_dir
        self.setWindowTitle("📊 試運行與清理成果報告")
        self.resize(640, 520)
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px 16px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_view_log {
                background-color: #1e1b4b; color: #c7d2fe; border: 1px solid #4f46e5;
            }
            QPushButton#btn_view_log:hover { background-color: #312e81; }
            QPushButton#btn_folder {
                background-color: #064e3b; color: #a7f3d0; border: 1px solid #059669;
            }
            QPushButton#btn_folder:hover { background-color: #065f46; }
            QPushButton#btn_finish {
                background-color: #7c3aed; color: #ffffff; border: 1px solid #8b5cf6;
            }
            QPushButton#btn_finish:hover { background-color: #6d28d9; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 頂部橫幅
        header_box = QFrame(self)
        header_box.setStyleSheet("background: rgba(124, 58, 237, 0.1); border: 1px solid rgba(124, 58, 237, 0.3); border-radius: 8px; padding: 12px;")
        h_layout = QVBoxLayout(header_box)
        h_title = QLabel("🎉 試運行與模組庫存審核已完成！", header_box)
        h_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c084fc;")
        h_layout.addWidget(h_title)

        scope_txt = self.summary_data.get("scope", "全部模組")
        batch_txt = self.summary_data.get("batch_id", "N/A")
        duration_sec = self.summary_data.get("total_duration_sec", 0.0)
        mins = int(duration_sec // 60)
        secs = int(duration_sec % 60)
        time_txt = f"{mins}分{secs}秒" if mins > 0 else f"{secs}秒"

        h_sub = QLabel(f"審核範圍：{scope_txt}  |  批次：{batch_txt}  |  耗時：{time_txt}", header_box)
        h_sub.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        h_layout.addWidget(h_sub)
        layout.addWidget(header_box)

        # 核心數據卡片列
        stats = self.summary_data.get("stats", {})
        total_tested = self.summary_data.get("tested_items_count", 0)
        kept = stats.get("kept", 0)
        discarded = stats.get("discarded", 0)
        skipped = stats.get("skipped", 0)
        pass_rate = stats.get("pass_rate_percent", 0.0)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        def make_card(title, value, color_hex, subtext=""):
            card = QFrame(self)
            card.setStyleSheet(f"background-color: #18181b; border: 1px solid #27272a; border-top: 3px solid {color_hex}; border-radius: 6px; padding: 10px;")
            c_vbox = QVBoxLayout(card)
            c_vbox.setContentsMargins(4, 4, 4, 4)
            c_vbox.setSpacing(4)
            lbl_t = QLabel(title, card)
            lbl_t.setStyleSheet("color: #71717a; font-size: 11px; font-weight: bold;")
            c_vbox.addWidget(lbl_t)
            lbl_v = QLabel(str(value), card)
            lbl_v.setStyleSheet(f"color: {color_hex}; font-size: 20px; font-weight: bold;")
            c_vbox.addWidget(lbl_v)
            if subtext:
                lbl_s = QLabel(subtext, card)
                lbl_s.setStyleSheet("color: #a1a1aa; font-size: 10px;")
                c_vbox.addWidget(lbl_s)
            return card

        cards_layout.addWidget(make_card("總審核數", f"{total_tested} 個", "#38bdf8"))
        cards_layout.addWidget(make_card("🟢 保留模組", f"{kept} 個", "#10b981", f"合格率 {pass_rate}%"))
        cards_layout.addWidget(make_card("🔴 剔除模組", f"{discarded} 個", "#ef4444", f"淘汰率 {round(100.0 - pass_rate, 1) if total_tested else 0}%"))
        cards_layout.addWidget(make_card("⚡ 跳過暫緩", f"{skipped} 個", "#94a3b8"))
        layout.addLayout(cards_layout)

        # 剔除成因分析 (Defect Breakdown)
        defects = stats.get("defect_breakdown", {})
        defect_group = QGroupBox("🔍 剔除缺陷原因分析 (Defect Breakdown)", self)
        defect_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #27272a; border-radius: 8px; margin-top: 10px;
                font-weight: bold; font-size: 12px; color: #f43f5e; padding: 12px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)
        d_layout = QVBoxLayout(defect_group)
        if defects:
            for reason, count in sorted(defects.items(), key=lambda x: x[1], reverse=True):
                ratio = round(count / discarded * 100, 1) if discarded > 0 else 0
                row = QHBoxLayout()
                lbl_r = QLabel(f"• {reason}", defect_group)
                lbl_r.setStyleSheet("color: #e4e4e7; font-size: 12px;")
                lbl_c = QLabel(f"{count} 個 ({ratio}%)", defect_group)
                lbl_c.setStyleSheet("color: #f43f5e; font-weight: bold; font-size: 12px;")
                row.addWidget(lbl_r)
                row.addStretch()
                row.addWidget(lbl_c)
                d_layout.addLayout(row)
        else:
            lbl_empty = QLabel("🌟 完美合格！本次審核未剔除任何模組。", defect_group)
            lbl_empty.setStyleSheet("color: #34d399; font-size: 12px;")
            d_layout.addWidget(lbl_empty)
        layout.addWidget(defect_group)

        # 底部動作按鈕
        btn_box = QHBoxLayout()
        btn_view_log = QPushButton("📜 檢視本次日誌檔", self)
        btn_view_log.setObjectName("btn_view_log")
        btn_view_log.clicked.connect(self.view_log)
        btn_box.addWidget(btn_view_log)

        btn_folder = QPushButton("📂 開啟日誌資料夾", self)
        btn_folder.setObjectName("btn_folder")
        btn_folder.clicked.connect(self.open_folder)
        btn_box.addWidget(btn_folder)

        btn_box.addStretch()

        btn_finish = QPushButton("✨ 完成", self)
        btn_finish.setObjectName("btn_finish")
        btn_finish.clicked.connect(self.accept)
        btn_box.addWidget(btn_finish)

        layout.addLayout(btn_box)

    def view_log(self):
        if self.log_path and os.path.exists(self.log_path):
            viewer = TestRunLogViewerDialog(self.log_path, self)
            viewer.exec()
        else:
            QMessageBox.information(self, "查無日誌", "找不到對應的日誌檔案。")

    def open_folder(self):
        if self.log_dir and os.path.exists(self.log_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_dir))
        elif self.log_path and os.path.exists(os.path.dirname(self.log_path)):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.log_path)))


class TestRunDialog(QDialog):
    MAX_CODE_CHARS = 200000
    WATCHDOG_TIMEOUT_SEC = 8

    def __init__(self, items_to_test, parent=None, batch_id=None, history_mgr=None, scope_name="全部模組"):
        super().__init__(parent)
        self.setWindowTitle("音畫互動模組 - 批次收錄試運行工作區")
        self.resize(960, 720)
        self.items = items_to_test
        self.batch_id = batch_id
        self.history_mgr = history_mgr
        self.scope_name = scope_name or "全部模組"
        self.current_idx = 0
        self.errors = []
        self.countdown = 15
        self.parent_app = parent
        
        # 建立試運行審計與遙測日誌器
        self.logger = TestRunLogger(
            batch_id=self.batch_id,
            scope_name=self.scope_name,
            total_items=len(self.items)
        )
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { font-family: 'Inter', sans-serif; }
            QPushButton { border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px; }
        """)
        
        layout = QVBoxLayout(self)
        
        # 頂部資訊條
        top_info_layout = QHBoxLayout()
        self.title_label = QLabel(self)
        self.title_label.setStyleSheet("color: #e4e4e7; font-weight: bold; font-size: 14px;")
        top_info_layout.addWidget(self.title_label)
        top_info_layout.addStretch()

        if self.batch_id:
            batch_badge = QLabel(f"🛡️ 隔離批次: {self.batch_id}", self)
            batch_badge.setStyleSheet("color: #a855f7; font-size: 11px; background: rgba(168, 85, 247, 0.15); padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.3);")
            top_info_layout.addWidget(batch_badge)

        btn_view_current_log = QPushButton("📜 查看日誌", self)
        btn_view_current_log.setStyleSheet("""
            QPushButton { background-color: #1e1b4b; color: #c7d2fe; border: 1px solid #4f46e5; padding: 4px 10px; font-size: 11px; }
            QPushButton:hover { background-color: #312e81; }
        """)
        btn_view_current_log.clicked.connect(self.show_current_log)
        top_info_layout.addWidget(btn_view_current_log)

        layout.addLayout(top_info_layout)
        
        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.status_label)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setMinimumHeight(420)
        layout.addWidget(self.web_view)
        
        # 即時除錯控制台抽屜 (Live Console)
        self.console_container = QFrame(self)
        self.console_container.setStyleSheet("background-color: #0b0c10; border: 1px solid #27272a; border-radius: 6px;")
        console_layout = QVBoxLayout(self.console_container)
        console_layout.setContentsMargins(8, 6, 8, 6)
        console_layout.setSpacing(4)

        console_header = QHBoxLayout()
        self.btn_toggle_console = QPushButton("💻 即時除錯日誌 (0 個異常) ▾", self)
        self.btn_toggle_console.setStyleSheet("background-color: transparent; border: none; color: #a1a1aa; font-size: 11px; font-weight: bold; text-align: left;")
        self.btn_toggle_console.clicked.connect(self.toggle_live_console)
        console_header.addWidget(self.btn_toggle_console)
        console_header.addStretch()

        btn_clear_console = QPushButton("🧹 清除控制台", self)
        btn_clear_console.setStyleSheet("background-color: transparent; border: none; color: #71717a; font-size: 11px;")
        btn_clear_console.clicked.connect(lambda: self.live_console_edit.clear())
        console_header.addWidget(btn_clear_console)
        console_layout.addLayout(console_header)

        self.live_console_edit = QTextEdit(self.console_container)
        self.live_console_edit.setReadOnly(True)
        self.live_console_edit.setFixedHeight(90)
        self.live_console_edit.setStyleSheet("""
            QTextEdit {
                background-color: #09090b; color: #a1a1aa; border: 1px solid #18181b;
                border-radius: 4px; font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
                font-size: 11px;
            }
        """)
        console_layout.addWidget(self.live_console_edit)
        self.live_console_edit.setVisible(False)
        layout.addWidget(self.console_container)

        # 底部按鈕
        self.btn_layout = QHBoxLayout()
        self.btn_keep = QPushButton("🟢 保留此視覺模組", self)
        self.btn_keep.setStyleSheet("background-color: #10b981; color: white;")
        self.btn_keep.clicked.connect(self.keep_current)
        self.btn_layout.addWidget(self.btn_keep)
        
        self.btn_discard = QPushButton("🔴 不保留此模組", self)
        self.btn_discard.setStyleSheet("background-color: #ef4444; color: white;")
        self.btn_discard.clicked.connect(self.discard_current)
        self.btn_layout.addWidget(self.btn_discard)

        self.btn_skip = QPushButton("⚡ 跳過此模組", self)
        self.btn_skip.setStyleSheet("background-color: #64748b; color: white;")
        self.btn_skip.clicked.connect(self.skip_current)
        self.btn_layout.addWidget(self.btn_skip)

        self.cb_star = QCheckBox("⭐ 標記為我的最愛 (評星優先置頂)", self)
        self.cb_star.setStyleSheet("color: #eab308; font-weight: bold; font-size: 13px;")
        self.btn_layout.addWidget(self.cb_star)
        
        self.btn_layout.addStretch()

        # ⏳ 放棄並一鍵回溯本批次按鈕
        self.btn_rollback_batch = QPushButton("⏮️ 放棄並回溯本批次", self)
        self.btn_rollback_batch.setStyleSheet("""
            QPushButton { background-color: #4c0519; color: #f43f5e; border: 1px solid #e11d48; padding: 10px 14px; }
            QPushButton:hover { background-color: #e11d48; color: white; }
        """)
        self.btn_rollback_batch.clicked.connect(self.rollback_entire_batch)
        self.btn_layout.addWidget(self.btn_rollback_batch)

        layout.addLayout(self.btn_layout)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setSingleShot(True)
        self._watchdog_timer.timeout.connect(self._on_watchdog_timeout)
        self._watchdog_alive = False

        from code_injector import CustomWebEnginePage
        self.web_page = CustomWebEnginePage(self.handle_js_log, self.web_view)
        self.web_view.setPage(self.web_page)
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        QTimer.singleShot(0, self.start_next_item)

    def toggle_live_console(self):
        visible = not self.live_console_edit.isVisible()
        self.live_console_edit.setVisible(visible)
        arrow = "▴" if visible else "▾"
        self.btn_toggle_console.setText(f"💻 即時除錯日誌 ({len(self.errors)} 個異常) {arrow}")

    def append_live_console(self, tag, text, color):
        escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"<div style='margin-bottom: 2px;'><span style='color: {color}; font-weight: bold;'>[{tag}]</span> <span style='color: #e4e4e7;'>{escaped_text}</span></div>"
        self.live_console_edit.append(html)
        arrow = "▴" if self.live_console_edit.isVisible() else "▾"
        self.btn_toggle_console.setText(f"💻 即時除錯日誌 ({len(self.errors)} 個異常) {arrow}")

    def show_current_log(self):
        if self.logger and os.path.exists(self.logger.get_log_path()):
            viewer = TestRunLogViewerDialog(self.logger.get_log_path(), self)
            viewer.exec()
        else:
            QMessageBox.information(self, "查無日誌", "尚未生成日誌檔案。")

    def handle_js_log(self, level, message, lineNumber):
        msg_lower = message.lower()
        ignored = ["failed to fetch", "audiocontext", "cors", "[mock]", "[preloadguard]", "opentype", ".ttf", ".woff"]
        if any(p in msg_lower for p in ignored):
            return
            
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        is_warn = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel)
        
        if is_err or "uncaught" in msg_lower or "is not defined" in msg_lower:
            err_line = f"Line {lineNumber}: {message}"
            if err_line not in self.errors:
                self.errors.append(err_line)
            self.logger.log_js_message("ERROR", message, lineNumber)
            self.append_live_console("🔴 ERROR", f"Line {lineNumber}: {message}", "#ef4444")
        elif is_warn:
            self.logger.log_js_message("WARN", message, lineNumber)
            self.append_live_console("⚠️ WARN", f"Line {lineNumber}: {message}", "#f59e0b")
        else:
            self.append_live_console("ℹ️ INFO", message, "#71717a")

    def _on_watchdog_timeout(self):
        if not self._watchdog_alive:
            self.next_item()

    def start_next_item(self):
        if self.current_idx >= len(self.items):
            self.timer.stop()
            summary = self.logger.finish_session("COMPLETED")
            summary_dlg = TestRunSummaryDialog(
                summary,
                self.logger.get_log_path(),
                self.logger.get_log_dir(),
                self
            )
            summary_dlg.exec()
            self.accept()
            return
            
        self.current_item = self.items[self.current_idx]
        self.errors = []
        self.countdown = 15
        self.live_console_edit.clear()
        arrow = "▴" if self.live_console_edit.isVisible() else "▾"
        self.btn_toggle_console.setText(f"💻 即時除錯日誌 (0 個異常) {arrow}")
        
        title = self.current_item.get("title", "未命名模組")
        url = self.current_item.get("url", "")
        sketch_id = self.current_item.get("id") or self.current_item.get("sketch_id")
        filename = self.current_item.get("filename", "")
        
        # 記錄項目啟動至日誌
        self.logger.start_item(
            self.current_idx + 1,
            len(self.items),
            filename,
            title,
            sketch_id,
            url
        )
        
        self.title_label.setText(f"📋 模組：{title} ({url})   [{self.current_idx + 1} / {len(self.items)}]")
        self.status_label.setText(f"正在試運行中... 剩餘 {self.countdown} 秒")
        
        # 載入畫布 HTML
        if self.parent_app and hasattr(self.parent_app, 'get_html_content'):
            html = self.parent_app.get_html_content(self.current_item["code"])
        else:
            html = f"<html><body><script src='custom_visuals/libs/p5.min.js'></script><script>{self.current_item['code']}</script></body></html>"
            
        from main import get_local_base_url
        self.web_view.setHtml(html, get_local_base_url())
        self.timer.start(1000)
        self._watchdog_alive = True

    def next_item(self):
        self.current_idx += 1
        self.start_next_item()

    def tick(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.status_label.setText(f"正在試運行中... 剩餘 {self.countdown} 秒")
        else:
            self.timer.stop()
            self.status_label.setText("✨ 試運行完成，請選擇是否保留。")

    def keep_current(self):
        self.timer.stop()
        is_star = self.cb_star.isChecked()
        self.logger.record_action("KEEP", {"is_favorite": is_star})

        filepath = self.current_item.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if is_star:
                    data["is_starred"] = True
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
        self.cb_star.setChecked(False)
        self.next_item()

    def discard_current(self):
        self.timer.stop()
        reason_dlg = RejectReasonDialog(self)
        if reason_dlg.exec() != QDialog.DialogCode.Accepted or not reason_dlg.reason:
            self.timer.start(1000)
            return

        reason = reason_dlg.reason
        self.logger.record_action("DISCARD", {"reason": reason})

        filepath = self.current_item.get("filepath")
        if filepath and os.path.exists(filepath):
            try: os.remove(filepath)
            except Exception: pass
            
        save_dir = self.current_item.get("save_dir", os.path.join(workspace_dir, "custom_visuals"))
        filename = self.current_item.get("filename", "")
        if filename:
            thumb_name = filename[:-5] if filename.endswith(".json") else filename
            thumb_path = os.path.join(save_dir, "thumbnails", f"{thumb_name}.jpg")
            if os.path.exists(thumb_path):
                try: os.remove(thumb_path)
                except Exception: pass
            
        self.items.pop(self.current_idx)
        self.start_next_item()

    def skip_current(self):
        self.timer.stop()
        self.logger.record_action("SKIP")
        self.next_item()

    def rollback_entire_batch(self):
        self.timer.stop()
        reply = QMessageBox.question(
            self, "確認回溯撤銷",
            "確定要放棄本次收錄並【一鍵回溯撤銷本批次】嗎？\n\n"
            "本次新增的所有模組將安全移至回溯備份區，\n"
            "歷史確認的模組絕不受任何影響！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logger.record_action("ROLLBACK", {"batch_id": self.batch_id})
            self.logger.finish_session("ROLLED_BACK")
            if self.history_mgr and self.batch_id:
                ok, count, msg = self.history_mgr.rollback_batch(self.batch_id)
                if self.parent_app and hasattr(self.parent_app, 'refresh_callback') and self.parent_app.refresh_callback:
                    self.parent_app.refresh_callback()
                QMessageBox.information(self, "回溯完成", f"已成功放棄並撤銷本批次 ({count} 個模組)！")
            self.reject()

    def closeEvent(self, event):
        self.timer.stop()
        if hasattr(self, "logger") and self.logger:
            self.logger.finish_session("USER_CLOSED")
        super().closeEvent(event)


class BatchTimeMachineDialog(QDialog):
    """
    ⏳ 4K MV 視覺模組 - 收編時光機與歷史批次管理對話框
    提供：
    1. 歷史批次卡片清單（依日期時間倒序排列）
    2. 模組數量、名稱展開與縮圖預覽
    3. 一鍵回溯撤銷此批次 (Rollback)
    4. 一鍵還原重做此批次 (Restore)
    5. 重新啟動試運行審核此批次
    6. 歷史已收錄模組永久基準隔離保護
    """
    def __init__(self, parent=None, history_mgr=None, refresh_callback=None):
        super().__init__(parent)
        self.history_mgr = history_mgr or BatchHistoryManager(workspace_dir)
        self.refresh_callback = refresh_callback
        self.setWindowTitle("⏳ 4K MV 視覺模組 - 收編時光機 (批次歷史與回溯管理)")
        self.resize(960, 680)

        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 14px; font-weight: bold; font-size: 12px; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QScrollArea { border: 1px solid #27272a; border-radius: 8px; background-color: #09090b; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 頂部狀態橫條
        header_layout = QHBoxLayout()
        title_label = QLabel("⏳ 模組收編時光機", self)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #a855f7;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.lbl_stats = QLabel(self)
        self.lbl_stats.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.lbl_stats)
        layout.addLayout(header_layout)

        # 基準保護說明橫幅
        legacy_count = self.history_mgr.history_data.get("legacy_baseline", {}).get("count", 0)
        baseline_box = QFrame(self)
        baseline_box.setStyleSheet("background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 6px; padding: 8px;")
        b_layout = QHBoxLayout(baseline_box)
        b_layout.setContentsMargins(8, 4, 8, 4)
        b_lbl = QLabel(f"🛡️ 歷史基準庫存：共 {legacy_count} 個模組受只讀屏障永久保護，任何最新批次的回溯均不會波及歷史確認模組。", baseline_box)
        b_lbl.setStyleSheet("color: #34d399; font-size: 12px;")
        b_layout.addWidget(b_lbl)
        layout.addWidget(baseline_box)

        # 批次滾動列表
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.setSpacing(12)
        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)

        # 底部按鈕列
        bottom_layout = QHBoxLayout()
        btn_refresh = QPushButton("🔄 重新整理清單", self)
        btn_refresh.clicked.connect(self.populate_batches)
        bottom_layout.addWidget(btn_refresh)

        btn_open_logs = QPushButton("📜 開啟試運行日誌資料夾", self)
        btn_open_logs.setStyleSheet("""
            QPushButton { background-color: #1e1b4b; color: #c7d2fe; border: 1px solid #4f46e5; padding: 6px 14px; }
            QPushButton:hover { background-color: #312e81; }
        """)
        btn_open_logs.clicked.connect(self.open_logs_folder)
        bottom_layout.addWidget(btn_open_logs)

        bottom_layout.addStretch()

        btn_close = QPushButton("關閉", self)
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

        self.populate_batches()

    def open_logs_folder(self):
        log_dir = os.path.join(workspace_dir, "logs", "test_runs")
        os.makedirs(log_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    def populate_batches(self):
        # 清空舊卡片
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        batches = self.history_mgr.get_all_batches()
        active_count = sum(1 for b in batches if b.get("status") == "active")
        rolled_back_count = sum(1 for b in batches if b.get("status") == "rolled_back")

        self.lbl_stats.setText(f"📜 歷史批次總數: {len(batches)} | 🟢 生效中: {active_count} | ⏪ 已回溯: {rolled_back_count}")

        if not batches:
            empty_lbl = QLabel("目前尚無新批次收錄紀錄（全部模組均處於歷史基準安全保護中）", self.cards_container)
            empty_lbl.setStyleSheet("color: #71717a; font-size: 13px; padding: 20px; text-align: center;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_layout.addWidget(empty_lbl)
            self.cards_layout.addStretch()
            return

        for batch in batches:
            bid = batch["batch_id"]
            bdate = batch.get("batch_date", "")
            created_at = batch.get("created_at", "")
            status = batch.get("status", "active")
            items = batch.get("items", [])
            source_url = batch.get("source_url", "") or "自訂/外部載入"

            card = QFrame(self.cards_container)
            card.setStyleSheet("""
                QFrame {
                    background-color: #121215;
                    border: 1px solid #27272a;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(10, 8, 10, 8)
            c_layout.setSpacing(8)

            # 第一行：日期時間與狀態徽章
            r1 = QHBoxLayout()
            date_lbl = QLabel(f"📅 批次：{bdate}  <span style='color:#71717a;'>({created_at})</span>", card)
            date_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #f4f4f5;")
            r1.addWidget(date_lbl)

            r1.addStretch()

            if status == "active":
                status_badge = QLabel("🟢 生效中 (已收錄)", card)
                status_badge.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px; background: rgba(16, 185, 129, 0.15); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(16, 185, 129, 0.3);")
            else:
                status_badge = QLabel(f"⏪ 已回溯撤銷 ({batch.get('rolled_back_at', '')})", card)
                status_badge.setStyleSheet("color: #f43f5e; font-weight: bold; font-size: 11px; background: rgba(244, 63, 94, 0.15); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(244, 63, 94, 0.3);")
            r1.addWidget(status_badge)
            c_layout.addLayout(r1)

            # 第二行：來源網址與模組數量
            r2 = QHBoxLayout()
            url_display = (source_url[:65] + "...") if len(source_url) > 65 else source_url
            info_lbl = QLabel(f"🌐 來源: <span style='color:#94a3b8;'>{url_display}</span>   |   📦 收錄作品: <span style='color:#a855f7; font-weight:bold;'>{len(items)}</span> 個", card)
            info_lbl.setStyleSheet("font-size: 12px;")
            r2.addWidget(info_lbl)
            r2.addStretch()
            c_layout.addLayout(r2)

            # 第三行：操作按鈕
            r3 = QHBoxLayout()
            
            # 展開/收合作品清單按鈕與容器
            expand_btn = QPushButton(f"▼ 展開模組清單 ({len(items)})", card)
            expand_btn.setStyleSheet("font-size: 11px; padding: 4px 10px;")
            r3.addWidget(expand_btn)

            r3.addStretch()

            if status == "active":
                btn_rollback = QPushButton("⏮️ 一鍵回溯此批次 (Rollback)", card)
                btn_rollback.setStyleSheet("""
                    QPushButton { background-color: #4c0519; color: #f43f5e; border: 1px solid #e11d48; padding: 6px 14px; }
                    QPushButton:hover { background-color: #e11d48; color: white; }
                """)
                btn_rollback.clicked.connect(lambda ch, b=bid, d=bdate, n=len(items): self.do_rollback(b, d, n))
                r3.addWidget(btn_rollback)

                btn_test = QPushButton("🧪 試運行此批次", card)
                btn_test.setStyleSheet("background-color: #1e1b4b; color: #a5b4fc; border-color: #4338ca; padding: 6px 14px;")
                btn_test.clicked.connect(lambda ch, b=batch: self.do_retest(b))
                r3.addWidget(btn_test)

            else:
                btn_restore = QPushButton("🔁 一鍵還原重做此批次 (Restore)", card)
                btn_restore.setStyleSheet("""
                    QPushButton { background-color: #064e3b; color: #34d399; border: 1px solid #059669; padding: 6px 14px; }
                    QPushButton:hover { background-color: #059669; color: white; }
                """)
                btn_restore.clicked.connect(lambda ch, b=bid, d=bdate, n=len(items): self.do_restore(b, d, n))
                r3.addWidget(btn_restore)

            c_layout.addLayout(r3)

            # 可摺疊的模組清單
            items_container = QWidget(card)
            items_container.setVisible(False)
            items_layout = QVBoxLayout(items_container)
            items_layout.setContentsMargins(5, 5, 5, 5)
            names_text = ", ".join(it.get("title", it.get("filename", "")) for it in items)
            names_lbl = QLabel(names_text, items_container)
            names_lbl.setWordWrap(True)
            names_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px; background-color: #18181b; padding: 6px; border-radius: 4px;")
            items_layout.addWidget(names_lbl)
            c_layout.addWidget(items_container)

            expand_btn.clicked.connect(lambda ch, w=items_container, b=expand_btn, n=len(items): self.toggle_expand(w, b, n))

            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def toggle_expand(self, widget, btn, count):
        is_vis = widget.isVisible()
        widget.setVisible(not is_vis)
        btn.setText(f"▲ 收合模組清單 ({count})" if not is_vis else f"▼ 展開模組清單 ({count})")

    def do_rollback(self, batch_id, batch_date, count):
        reply = QMessageBox.question(
            self, "確認回溯撤銷",
            f"確定要回溯撤銷【{batch_date}】的批次收編嗎？\n\n"
            f"• 將安全移出此批次的 {count} 個模組\n"
            f"• 歷史基準模組完全不受任何影響\n"
            f"• 稍後若有需要，隨時可於此處一鍵【還原重做】",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, moved, msg = self.history_mgr.rollback_batch(batch_id)
            if ok:
                QMessageBox.information(self, "回溯成功", f"🎉 {msg}")
                if self.refresh_callback:
                    self.refresh_callback()
                self.populate_batches()
            else:
                QMessageBox.warning(self, "回溯失敗", msg)

    def do_restore(self, batch_id, batch_date, count):
        reply = QMessageBox.question(
            self, "確認還原重做",
            f"確定要還原重新啟用【{batch_date}】的批次模組嗎？\n\n"
            f"• 將還原重新啟用 {count} 個模組回主庫存\n",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, restored, msg = self.history_mgr.restore_batch(batch_id)
            if ok:
                QMessageBox.information(self, "還原成功", f"🎉 {msg}")
                if self.refresh_callback:
                    self.refresh_callback()
                self.populate_batches()
            else:
                QMessageBox.warning(self, "還原失敗", msg)

    def do_retest(self, batch):
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        items_to_test = []
        for it in batch.get("items", []):
            fname = it.get("filename")
            fpath = os.path.join(save_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items_to_test.append({
                        "id": it.get("sketch_id"),
                        "title": it.get("title"),
                        "url": data.get("url", ""),
                        "code": data.get("code", ""),
                        "filepath": fpath,
                        "filename": fname,
                        "save_dir": save_dir,
                        "batch_id": batch.get("batch_id")
                    })
                except Exception:
                    pass

        if not items_to_test:
            QMessageBox.warning(self, "無可用模組", "該批次模組檔案目前不存在或已被移出。")
            return

        scope_desc = f"時光機指定批次 ({batch.get('batch_date')}, {batch.get('batch_id')})"
        dlg = TestRunDialog(items_to_test, self, batch_id=batch.get("batch_id"), history_mgr=self.history_mgr, scope_name=scope_desc)
        dlg.exec()


class BatchScopeSelectionDialog(QDialog):
    """
    🎯 試運行與清理範圍選擇器
    支援：
    1. ✨ 本次/最新收錄批次 (只針對剛收編的模組進行試運行與清理，不影響歷史模組)
    2. 📅 選擇指定收錄批次 (下拉選單自由選擇任一歷史批次)
    3. 🏛️ 僅歷史基準模組 (1495 個基準庫存)
    4. 🌐 全部視覺模組 (全庫巡檢)
    """
    def __init__(self, parent=None, history_mgr=None, current_batch_items=None, current_batch_id=None):
        super().__init__(parent)
        self.history_mgr = history_mgr or BatchHistoryManager(workspace_dir)
        self.current_batch_items = current_batch_items or []
        self.current_batch_id = current_batch_id
        self.save_dir = os.path.join(workspace_dir, "custom_visuals")
        self.result_items = []
        self.result_batch_id = None
        self.result_scope_desc = "自訂範圍"

        self.setWindowTitle("🎯 選擇試運行與清理模組範圍")
        self.resize(540, 420)
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QPushButton {
                background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a;
                border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px;
                text-align: left;
            }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_current { border-left: 4px solid #a855f7; }
            QPushButton#btn_latest { border-left: 4px solid #38bdf8; }
            QPushButton#btn_specific { border-left: 4px solid #10b981; }
            QPushButton#btn_legacy { border-left: 4px solid #f59e0b; }
            QPushButton#btn_all { border-left: 4px solid #64748b; }
            QPushButton#btn_cancel { background-color: #09090b; text-align: center; font-weight: normal; }
            QComboBox { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 10px; font-size: 12px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title_lbl = QLabel("請選擇要進行試運行與清理的模組範圍：", self)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #f4f4f5; margin-bottom: 4px;")
        layout.addWidget(title_lbl)

        active_batches = [b for b in self.history_mgr.get_all_batches() if b.get("status") == "active"]

        # 1. 本次收錄批次按鈕（若剛完成批次收錄）
        if self.current_batch_items:
            count = len(self.current_batch_items)
            b_id_text = f" ({self.current_batch_id})" if self.current_batch_id else ""
            self.btn_current = QPushButton(f"✨ 僅試運行本次收錄批次{b_id_text}\n   (共 {count} 個新收編模組，精準審核剛抓取的作品，完全不影響以往模組)", self)
            self.btn_current.setObjectName("btn_current")
            self.btn_current.clicked.connect(self.select_current_batch)
            layout.addWidget(self.btn_current)
        elif active_batches:
            latest = active_batches[0]
            l_count = len(latest.get("items", []))
            l_date = latest.get("batch_date", "")
            l_id = latest.get("batch_id", "")
            self.btn_latest = QPushButton(f"✨ 最新收錄批次 ({l_date})\n   (共 {l_count} 個模組，批次 ID: {l_id})", self)
            self.btn_latest.setObjectName("btn_latest")
            self.btn_latest.clicked.connect(lambda ch, b=latest: self.select_batch(b))
            layout.addWidget(self.btn_latest)

        # 2. 指定歷史批次
        if active_batches:
            batch_box = QVBoxLayout()
            b_label = QLabel("📅 選擇指定收錄批次進行試運行與清理：", self)
            b_label.setStyleSheet("color: #a1a1aa; font-size: 12px; margin-top: 4px;")
            batch_box.addWidget(b_label)

            h_row = QHBoxLayout()
            self.combo_batches = QComboBox(self)
            for b in active_batches:
                b_date = b.get("batch_date", "")
                b_id = b.get("batch_id", "")
                b_count = len(b.get("items", []))
                self.combo_batches.addItem(f"批次 {b_date} ({b_count} 個模組) - {b_id}", b)
            h_row.addWidget(self.combo_batches, stretch=1)

            btn_go_batch = QPushButton("▶️ 執行此批次", self)
            btn_go_batch.setObjectName("btn_specific")
            btn_go_batch.clicked.connect(self.select_combo_batch)
            h_row.addWidget(btn_go_batch)
            batch_box.addLayout(h_row)
            layout.addLayout(batch_box)

        # 3. 僅歷史基準模組
        legacy_count = self.history_mgr.history_data.get("legacy_baseline", {}).get("count", 0)
        self.btn_legacy = QPushButton(f"🏛️ 僅歷史基準已確認模組\n   (共 {legacy_count} 個受保護之基底模組，執行歷史庫存覆查)", self)
        self.btn_legacy.setObjectName("btn_legacy")
        self.btn_legacy.clicked.connect(self.select_legacy)
        layout.addWidget(self.btn_legacy)

        # 4. 全部模組
        total_all = len([f for f in os.listdir(self.save_dir) if f.endswith(".json") and not f.startswith("module")]) if os.path.exists(self.save_dir) else 0
        self.btn_all = QPushButton(f"🌐 全部視覺模組全庫巡檢\n   (共 {total_all} 個模組，包含全部批次與歷史庫存)", self)
        self.btn_all.setObjectName("btn_all")
        self.btn_all.clicked.connect(self.select_all)
        layout.addWidget(self.btn_all)

        # 取消按鈕
        self.btn_cancel = QPushButton("取消", self)
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)

    def select_current_batch(self):
        self.result_items = self.current_batch_items
        self.result_batch_id = self.current_batch_id
        self.result_scope_desc = f"本次收錄批次 ({self.current_batch_id})" if self.current_batch_id else "本次收錄批次"
        self.accept()

    def select_combo_batch(self):
        b = self.combo_batches.currentData()
        if b:
            self.select_batch(b)

    def select_batch(self, batch):
        self.result_batch_id = batch.get("batch_id")
        self.result_scope_desc = f"指定收錄批次 ({batch.get('batch_date')}, {batch.get('batch_id')})"
        self.result_items = self._load_items_from_batch(batch)
        self.accept()

    def select_legacy(self):
        self.result_batch_id = "legacy_baseline"
        self.result_scope_desc = "歷史基準已確認模組 (Legacy Baseline)"
        baseline_files = self.history_mgr.history_data.get("legacy_baseline", {}).get("files", [])
        self.result_items = self._load_items_from_filenames(baseline_files)
        self.accept()

    def select_all(self):
        self.result_batch_id = "all"
        self.result_scope_desc = "全庫巡檢 (全部視覺模組)"
        if os.path.exists(self.save_dir):
            all_files = [f for f in os.listdir(self.save_dir) if f.endswith(".json") and not f.startswith("module")]
            all_files.sort()
            self.result_items = self._load_items_from_filenames(all_files)
        self.accept()

    def _load_items_from_batch(self, batch):
        items = []
        for it in batch.get("items", []):
            fname = it.get("filename")
            fpath = os.path.join(self.save_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items.append({
                        "id": it.get("sketch_id"),
                        "title": it.get("title") or data.get("name", fname[:-5]),
                        "url": data.get("url", ""),
                        "code": data.get("code", ""),
                        "filepath": fpath,
                        "filename": fname,
                        "save_dir": self.save_dir,
                        "batch_id": batch.get("batch_id")
                    })
                except Exception:
                    pass
        return items

    def _load_items_from_filenames(self, filenames):
        items = []
        for fname in filenames:
            fpath = os.path.join(self.save_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    url = data.get("url", "")
                    m = re.search(r'/sketch/(\d+)', url) or re.search(r'/@[\w\-]+/(\d+)', url)
                    sid = m.group(1) if m else fname[:-5]
                    items.append({
                        "id": sid,
                        "title": data.get("name", fname[:-5]),
                        "url": url,
                        "code": data.get("code", ""),
                        "filepath": fpath,
                        "filename": fname,
                        "save_dir": self.save_dir,
                        "batch_id": data.get("batch_id")
                    })
                except Exception:
                    pass
        return items


class FastSketchFetcherThread(QThread):
    finished = pyqtSignal(list)
    log = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        items = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest'
            }
            resp = requests.get(self.url, headers=headers, timeout=12)
            html = resp.text
            seen = set()

            # 1. 抓取作者頁面 (var user = {...})
            if 'var user' in html:
                idx = html.find('var user')
                first_brace = html.find('{', idx)
                if first_brace != -1:
                    try:
                        decoder = json.JSONDecoder()
                        user_obj, _ = decoder.raw_decode(html[first_brace:])
                        user_id = user_obj.get('userID')
                        sketches = user_obj.get('sketches', [])
                        total_expected = user_obj.get('numberOfSketches', len(sketches))
                        
                        for s in sketches:
                            sid = str(s.get('visualID', s.get('id', '')))
                            if sid and sid not in seen:
                                seen.add(sid)
                                items.append({
                                    'id': sid,
                                    'title': (s.get('title') or f'Sketch {sid}').strip(),
                                    'url': f'https://openprocessing.org/sketch/{sid}'
                                })
                                
                        # 若還有未載入作品且有 user_id，自動分頁請求
                        if user_id and total_expected > len(items):
                            offset = len(items)
                            limit = 60
                            while offset < total_expected and len(items) < 300:
                                page_url = f'https://openprocessing.org/user/{user_id}/getSketches_ajax/{limit}/{offset}'
                                try:
                                    r_page = requests.get(page_url, headers=headers, timeout=8)
                                    if r_page.status_code == 200:
                                        p_data = r_page.json()
                                        more_sketches = p_data.get('object', [])
                                        if not more_sketches: break
                                        for s in more_sketches:
                                            sid = str(s.get('visualID', s.get('id', '')))
                                            if sid and sid not in seen:
                                                seen.add(sid)
                                                items.append({
                                                    'id': sid,
                                                    'title': (s.get('title') or f'Sketch {sid}').strip(),
                                                    'url': f'https://openprocessing.org/sketch/{sid}'
                                                })
                                        offset += len(more_sketches)
                                    else:
                                        break
                                except Exception:
                                    break
                    except Exception:
                        pass

            # 2. 抓取單一作品 (var sketch = {...})
            if not items and 'var sketch' in html:
                idx = html.find('var sketch')
                first_brace = html.find('{', idx)
                if first_brace != -1:
                    try:
                        decoder = json.JSONDecoder()
                        sketch_obj, _ = decoder.raw_decode(html[first_brace:])
                        sid = str(sketch_obj.get('visualID', sketch_obj.get('id', '')))
                        if sid:
                            items.append({
                                'id': sid,
                                'title': (sketch_obj.get('title') or f'Sketch {sid}').strip(),
                                'url': f'https://openprocessing.org/sketch/{sid}'
                            })
                    except Exception:
                        pass

            # 3. DOM 正則 fallback
            if not items:
                matches = re.findall(r'href=[\'"]([^\'"]*?(?:sketch|@[\w\-]+)\/(\d+)[^\'"]*?)[\'"]', html)
                for full_h, sid in matches:
                    if sid not in seen:
                        seen.add(sid)
                        items.append({
                            'id': sid,
                            'title': f'Sketch {sid}',
                            'url': f'https://openprocessing.org/sketch/{sid}'
                        })

        except Exception as e:
            self.log.emit(f"⚠️ 後台網路解析異常: {e}")

        self.finished.emit(items)


class BatchImportDialog(QDialog):
    """OpenProcessing 藝術視覺模組 - 自動化批次收編工作區"""
    def __init__(self, parent=None, refresh_callback=None):
        super().__init__(parent)
        self.refresh_callback = refresh_callback
        self.history_mgr = BatchHistoryManager(workspace_dir)
        self.current_batch_date = datetime.date.today().strftime("%Y-%m-%d")
        self.detected_sketches_map = {}
        self.save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(self.save_dir, exist_ok=True)
        self.existing_urls = self.get_existing_urls()
        
        self.setWindowTitle("📥 OpenProcessing 藝術視覺模組 - 自動化批次收編工作區")
        self.resize(1340, 780)
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QLineEdit { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 12px; font-size: 13px; }
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_import { background-color: #7c3aed; border-color: #7c3aed; }
            QPushButton#btn_import:hover { background-color: #8b5cf6; }
            QPushButton#btn_time_machine { background-color: #312e81; border-color: #4f46e5; color: #c7d2fe; }
            QPushButton#btn_time_machine:hover { background-color: #4338ca; color: white; }
            QListWidget { background-color: #09090b; border: 1px solid #27272a; border-radius: 8px; color: #f4f4f5; }
            QTextEdit { background-color: #18181b; border: 1px solid #27272a; border-radius: 8px; color: #a1a1aa; font-family: 'Courier New', monospace; font-size: 11px; }
            QProgressBar { border: 1px solid #27272a; border-radius: 4px; background-color: #18181b; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #7c3aed; }
            QGroupBox { border: 1px solid #27272a; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #c084fc; padding: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QCheckBox { color: #d4d4d8; font-size: 12px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("作者首頁/分頁網址："))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("例如: https://openprocessing.org/@atzedent#sketches")
        self.url_input.returnPressed.connect(self.load_url)
        top_bar.addWidget(self.url_input)
        
        self.btn_load = QPushButton("⚡ 載入網頁")
        self.btn_load.clicked.connect(self.load_url)
        self.btn_expand = QPushButton("⬇️ 自動展開")
        self.btn_expand.clicked.connect(self.toggle_expand_sketches)
        self.btn_parse = QPushButton("🔍 解析作品")
        self.btn_parse.clicked.connect(self.parse_sketches)
        
        top_bar.addWidget(self.btn_load)
        top_bar.addWidget(self.btn_expand)
        top_bar.addWidget(self.btn_parse)

        # ⏳ 收編時光機按鈕與當前批次標籤
        self.btn_time_machine = QPushButton("⏳ 收編時光機 (批次回溯)")
        self.btn_time_machine.setObjectName("btn_time_machine")
        self.btn_time_machine.clicked.connect(self.open_time_machine_dialog)
        top_bar.addWidget(self.btn_time_machine)

        main_layout.addLayout(top_bar)
        
        # 批次狀態提示條
        sub_bar = QHBoxLayout()
        self.lbl_batch_tag = QLabel(f"📅 本次收錄隔離批次：{self.current_batch_date}  (歷史基準 1400+ 模組安全保護中)")
        self.lbl_batch_tag.setStyleSheet("color: #a855f7; font-weight: bold; font-size: 12px; background: rgba(168, 85, 247, 0.1); padding: 4px 10px; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.25);")
        sub_bar.addWidget(self.lbl_batch_tag)
        sub_bar.addStretch()
        main_layout.addLayout(sub_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左側瀏覽器
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        self.web_view.loadFinished.connect(self.on_page_load_finished)
        left_layout.addWidget(QLabel("🌐 OpenProcessing 瀏覽視窗"))
        left_layout.addWidget(self.web_view)
        splitter.addWidget(left_widget)
        
        # 右側控制台
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 🛡️ 智慧收錄過濾與預處理設定面板
        self.filter_group = QGroupBox("🛡️ 智慧收錄過濾與預處理設定 (使用者自訂勾選)")
        f_layout = QVBoxLayout(self.filter_group)
        f_layout.setContentsMargins(8, 8, 8, 8)
        f_layout.setSpacing(6)

        cb_row1 = QHBoxLayout()
        self.cb_skip_game = QCheckBox("🎮 排除遊戲模組")
        self.cb_skip_game.setChecked(True)
        self.cb_skip_camera_ar = QCheckBox("👓 排除 AR/VR/Webcam")
        self.cb_skip_camera_ar.setChecked(True)
        self.cb_hide_controls = QCheckBox("🎛️ 控制項自動隱藏")
        self.cb_hide_controls.setChecked(True)
        cb_row1.addWidget(self.cb_skip_game)
        cb_row1.addWidget(self.cb_skip_camera_ar)
        cb_row1.addWidget(self.cb_hide_controls)
        f_layout.addLayout(cb_row1)

        cb_row2 = QHBoxLayout()
        self.cb_skip_text_heavy = QCheckBox("🔤 排除文字/排版字型展示")
        self.cb_skip_text_heavy.setChecked(True)
        self.cb_skip_heavy = QCheckBox("📦 排除高耗時/重型3D模型")
        self.cb_skip_heavy.setChecked(True)
        self.cb_skip_static = QCheckBox("⏳ 排除純靜態無動態模組")
        self.cb_skip_static.setChecked(True)
        cb_row2.addWidget(self.cb_skip_text_heavy)
        cb_row2.addWidget(self.cb_skip_heavy)
        cb_row2.addWidget(self.cb_skip_static)
        f_layout.addLayout(cb_row2)

        cb_btn_row = QHBoxLayout()
        cb_btn_row.addStretch()
        btn_reset_defaults = QPushButton("💡 推薦最佳配置", self.filter_group)
        btn_reset_defaults.setStyleSheet("font-size: 11px; padding: 2px 8px; background-color: #27272a;")
        btn_reset_defaults.clicked.connect(self.reset_filter_defaults)
        cb_btn_row.addWidget(btn_reset_defaults)
        f_layout.addLayout(cb_btn_row)

        right_layout.addWidget(self.filter_group)
        
        right_layout.addWidget(QLabel("📋 待收編作品列表"))
        self.list_widget = QListWidget()
        right_layout.addWidget(self.list_widget)
        
        right_layout.addWidget(QLabel("💻 後台轉譯日誌"))
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        right_layout.addWidget(self.console)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        action_bar = QHBoxLayout()
        self.btn_import = QPushButton("🚀 開始批次轉譯收編")
        self.btn_import.setObjectName("btn_import")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self.start_batch_import)
        
        self.btn_close = QPushButton("關閉")
        self.btn_close.clicked.connect(self.close)
        
        action_bar.addWidget(self.btn_import)
        action_bar.addWidget(self.btn_close)
        right_layout.addLayout(action_bar)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([650, 650])
        main_layout.addWidget(splitter)
        
        self.is_expanding = False

    def reset_filter_defaults(self):
        self.cb_skip_game.setChecked(True)
        self.cb_skip_camera_ar.setChecked(True)
        self.cb_hide_controls.setChecked(True)
        self.cb_skip_text_heavy.setChecked(True)
        self.cb_skip_heavy.setChecked(True)
        self.cb_skip_static.setChecked(True)

    def get_filter_options(self):
        return {
            "skip_games": self.cb_skip_game.isChecked(),
            "skip_camera_ar": self.cb_skip_camera_ar.isChecked(),
            "hide_controls": self.cb_hide_controls.isChecked(),
            "skip_text_heavy": self.cb_skip_text_heavy.isChecked(),
            "skip_heavy_loading": self.cb_skip_heavy.isChecked(),
            "skip_static": self.cb_skip_static.isChecked()
        }

    def open_time_machine_dialog(self):
        dlg = BatchTimeMachineDialog(self, history_mgr=self.history_mgr, refresh_callback=self.on_time_machine_refresh)
        dlg.exec()

    def on_time_machine_refresh(self):
        self.existing_urls = self.get_existing_urls()
        if self.detected_sketches_map:
            self._populate_sketches(list(self.detected_sketches_map.values()))
        if self.refresh_callback:
            self.refresh_callback()

    def log_to_console(self, text, is_err=False):
        color = "#f43f5e" if is_err else "#38bdf8" if "[+]" in text or "✅" in text or "✨" in text else "#a1a1aa"
        self.console.append(f"<span style='color: {color};'>{text}</span>")

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
        if not url: return
        self.detected_sketches_map.clear()
        self.list_widget.clear()
        self.btn_import.setEnabled(False)
        self.log_to_console(f"正在載入: {url} ...")
        self.web_view.load(QUrl(url))

    def on_page_load_finished(self, ok):
        if not ok:
            self.log_to_console("⚠️ 瀏覽器頁面加載受阻，自動啟動後台高速解析引擎...", True)
            self.start_fallback_fetch(self.url_input.text().strip())
            return
        
        self.log_to_console("✅ 網頁加載成功，正在自動解析作品清單...")
        # 溫和對焦到作品區塊，避免網頁頂部空白造成視覺誤導
        js_focus = """
        let el = document.querySelector('#sketchesContainer') || document.querySelector('.mainSketches') || document.querySelector('#userTabs');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        """
        self.web_view.page().runJavaScript(js_focus)
        QTimer.singleShot(800, self.parse_sketches)

    def toggle_expand_sketches(self):
        if self.is_expanding:
            self.is_expanding = False
            if hasattr(self, 'expand_timer'):
                self.expand_timer.stop()
            self.btn_expand.setText("⬇️ 自動展開")
            self.log_to_console("已停止自動展開。")
        else:
            self.is_expanding = True
            self.btn_expand.setText("⏳ 停止展開")
            self.log_to_console("正在自動持續向下展開加載更多作品...")
            self.expand_timer = QTimer(self)
            self.expand_timer.timeout.connect(self.expand_step)
            self.expand_timer.start(2000)

    def expand_step(self):
        js = """
        (function() {
            let btn = document.querySelector('.seeMoreButton') || document.querySelector('.showMore');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                return { action: 'clicked_more' };
            }
            let el = document.querySelector('#sketchesContainer') || document.querySelector('.mainSketches');
            if (el) {
                window.scrollBy({ top: 600, behavior: 'smooth' });
                return { action: 'scrolled' };
            }
            return { action: 'none' };
        })()
        """
        self.web_view.page().runJavaScript(js, self._on_expand_step_done)

    def _on_expand_step_done(self, res):
        QTimer.singleShot(600, self.parse_sketches)

    def parse_sketches(self):
        js = """
        (function() {
            let items = [];
            let seen = new Set();
            
            // 1. 從 OpenProcessing 前端全域物件提取（不受 DOM 虛擬滾動裁切影響，完整精準）
            try {
                if (window.user && Array.isArray(window.user.sketches)) {
                    let u = window.user.username || '';
                    window.user.sketches.forEach(s => {
                        let id = String(s.visualID || s.id || '');
                        if (id && !seen.has(id)) {
                            seen.add(id);
                            items.push({
                                id: id,
                                title: (s.title || ('Sketch ' + id)).trim(),
                                url: 'https://openprocessing.org/sketch/' + id
                            });
                        }
                    });
                }
            } catch(e) {}

            try {
                if (window.curation && Array.isArray(window.curation.sketches)) {
                    window.curation.sketches.forEach(s => {
                        let id = String(s.visualID || s.id || '');
                        if (id && !seen.has(id)) {
                            seen.add(id);
                            items.push({
                                id: id,
                                title: (s.title || ('Sketch ' + id)).trim(),
                                url: 'https://openprocessing.org/sketch/' + id
                            });
                        }
                    });
                }
            } catch(e) {}

            // 2. 從 Vue 元件實例提取
            try {
                document.querySelectorAll('.sketchLi, sketch-li, [class*="sketch"]').forEach(el => {
                    let s = el.__vue__?.sketch;
                    if (s) {
                        let id = String(s.visualID || s.id || '');
                        if (id && !seen.has(id)) {
                            seen.add(id);
                            items.push({
                                id: id,
                                title: (s.title || ('Sketch ' + id)).trim(),
                                url: 'https://openprocessing.org/sketch/' + id
                            });
                        }
                    }
                });
            } catch(e) {}

            // 3. 從 DOM 超連結提取備援
            try {
                document.querySelectorAll('a, [data-href]').forEach(a => {
                    let href = a.href || a.getAttribute('data-href') || a.getAttribute('href') || '';
                    let m = href.match(/\\/(?:sketch|@[\\w\\-]+)\\/(\\d+)/);
                    if (m) {
                        let id = m[1];
                        if (!seen.has(id)) {
                            seen.add(id);
                            let titleEl = a.querySelector('.sketchTitle') || a.querySelector('[class*="title"]');
                            let title = titleEl ? titleEl.textContent : (a.innerText || ('Sketch ' + id));
                            items.push({
                                id: id,
                                title: title.trim(),
                                url: href.startsWith('http') ? href : ('https://openprocessing.org' + href)
                            });
                        }
                    }
                });
            } catch(e) {}

            return items;
        })()
        """
        self.web_view.page().runJavaScript(js, self.on_parse_finished)

    def on_parse_finished(self, items):
        if not items:
            self.log_to_console("⚠️ 瀏覽器頁面未擷取到作品（可能受虛擬滾動或腳本影響），立即啟用後端高速引擎備援...", True)
            self.start_fallback_fetch(self.url_input.text().strip())
            return
            
        self._populate_sketches(items)

    def start_fallback_fetch(self, url):
        if not url: return
        if hasattr(self, 'fetcher_thread') and self.fetcher_thread.isRunning():
            return
        self.log_to_console(f"🚀 啟動後台高速解析引擎: {url} ...")
        self.fetcher_thread = FastSketchFetcherThread(url, self)
        self.fetcher_thread.log.connect(lambda msg: self.log_to_console(msg, True))
        self.fetcher_thread.finished.connect(self._populate_sketches)
        self.fetcher_thread.start()

    def _populate_sketches(self, items):
        if not items:
            self.log_to_console("[-] 未能在該網址找到任何作品，請確認作者名稱或網址格式是否正確。", True)
            return

        old_count = len(self.detected_sketches_map)
        for it in items:
            sid = str(it["id"])
            if sid not in self.detected_sketches_map:
                self.detected_sketches_map[sid] = it
                
        if len(self.detected_sketches_map) == old_count and old_count > 0:
            return

        self.list_widget.clear()
        pending = 0
        for sid, it in self.detected_sketches_map.items():
            is_imported = it["url"].rstrip("/") in self.existing_urls or sid in self.existing_urls
            item_widget = QListWidgetItem()
            if is_imported:
                item_widget.setText(f"✓ [已收錄] {it['title']}")
                item_widget.setForeground(Qt.GlobalColor.darkGray)
            else:
                item_widget.setText(f"▢ [待收編: {self.current_batch_date}] {it['title']}")
                item_widget.setCheckState(Qt.CheckState.Checked)
                pending += 1
            item_widget.setData(Qt.ItemDataRole.UserRole, it)
            self.list_widget.addItem(item_widget)
            
        self.btn_import.setEnabled(pending > 0)
        self.log_to_console(f"✨ 成功解析出 {len(self.detected_sketches_map)} 個作品（待收編: {pending} 個，已收錄: {len(self.detected_sketches_map) - pending} 個）！")

    def start_batch_import(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
                
        if not selected: return
        self.btn_import.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(selected))
        
        # 發起獨立日期收編批次
        source_url = self.url_input.text().strip()
        filter_opts = self.get_filter_options()
        batch_id, batch_date = self.history_mgr.start_new_batch(source_url, filter_opts)
        self.log_to_console(f"🛡️ 【批次隔離已就緒】批次 ID: {batch_id} (日期: {batch_date})，歷史庫存受強制保護中！")

        self.worker = BatchImportWorker(
            selected,
            self.save_dir,
            batch_id=batch_id,
            batch_date=batch_date,
            filter_options=filter_opts,
            history_mgr=self.history_mgr
        )
        self.worker.progress.connect(lambda idx, txt: self.progress_bar.setValue(idx))
        self.worker.log.connect(self.log_to_console)
        self.worker.finished.connect(self.on_import_finished)
        self.worker.start()

    def on_import_finished(self, failed):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.btn_import.setEnabled(True)
        self.existing_urls = self.get_existing_urls()
        if self.refresh_callback:
            self.refresh_callback()
            
        success_items = getattr(self.worker, 'success_list', [])
        b_id = getattr(self.worker, 'batch_id', 'N/A')
        b_date = getattr(self.worker, 'batch_date', 'N/A')

        msg_box_text = (
            f"🎉 已成功收編 {len(success_items)} 個模組！\n\n"
            f"• 隔離批次：{b_id}\n"
            f"• 收錄日期：{b_date}\n"
            f"• 歷史基準 1400+ 模組安全保護無虞\n\n"
            f"💡 若發現此批次有任何瑕疵或不合心意，可隨時點擊【收編時光機】一鍵秒級回溯！\n\n"
            f"是否立即啟動試運行工作區審核本批次？"
        )
        reply = QMessageBox.question(
            self, "收編完成與時光快照建立", msg_box_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            scope_dlg = BatchScopeSelectionDialog(
                self,
                history_mgr=self.history_mgr,
                current_batch_items=success_items,
                current_batch_id=b_id
            )
            if scope_dlg.exec() == QDialog.DialogCode.Accepted and scope_dlg.result_items:
                dlg = TestRunDialog(
                    scope_dlg.result_items,
                    self,
                    batch_id=scope_dlg.result_batch_id,
                    history_mgr=self.history_mgr,
                    scope_name=scope_dlg.result_scope_desc
                )
                dlg.exec()
                if self.refresh_callback:
                    self.refresh_callback()
