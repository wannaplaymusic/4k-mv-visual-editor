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
    QSplitter, QMessageBox, QWidget, QApplication, QCheckBox, QComboBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer

# 取得 workspace 目錄路徑
workspace_dir = os.path.dirname(os.path.abspath(__file__))

def validate_visual_module_eligibility(title, code, custom_html="", tags=None, desc=""):
    """
    4K MV 視覺預設模組收錄過濾器：
    嚴格排除：
    1. 攝影機 (Camera / Webcam / getUserMedia / createCapture)
    2. AR / XR / VR (WebXR, A-Frame, MindAR, Zappar, Tracking.js, PoseNet, FaceMesh)
    3. 遊戲 (Game / Arcade / Platformer / Shooter / Tetris / Pong / Chess / etc.)
    4. 高耗時加載 (Heavy Loading / Heavy 3D Models / Multi-remote media / ML Models / Large files)
    回傳 (is_eligible, reject_reason)
    """
    tags = [t.lower().strip() for t in (tags or [])]
    text_check = f"{title.lower()} {' '.join(tags)} {desc.lower()} {code.lower()[:3000]} {custom_html.lower()}"
    full_content = code + "\n" + custom_html

    # 1. 攝影機輸入 (Camera / Webcam)
    if re.search(r'\bcreateCapture\s*\(', full_content, re.IGNORECASE) and not ("p5capture" in full_content.lower() and not any(kw in full_content.lower() for kw in ["video", "camera", "webcam"])):
        return False, "含有攝影機輸入 (createCapture)"
    if re.search(r'\b(getUserMedia|clmtrackr|webcam|live_camera|videoCapture)\b', full_content, re.IGNORECASE):
        return False, "含有攝影機/Webcam 調用"
    if any(t in ['webcam', 'camera', 'camera capture', 'video capture'] for t in tags):
        return False, "標籤含有攝影機/Webcam"

    # 2. AR / XR / VR
    ar_xr_kws = ['webxr', 'webvr', 'xrsession', 'vrbutton', 'arbutton', 'webgl_vr', 'p5.vr', 'mindar', 'artoolkit', 'a-scene', 'a-entity', 'zappar', 'augmented reality', 'virtual reality']
    for kw in ar_xr_kws:
        if kw in text_check:
            return False, f"含有 AR/XR/VR 呼叫 ({kw})"
    if any(t in ['ar', 'xr', 'vr', 'webxr', 'webvr', 'augmented-reality', 'virtual-reality'] for t in tags):
        return False, "標籤含有 AR/XR/VR"

    # 3. 遊戲類型模組 (GAME)
    # 排除單純以 GameBoy 為調色盤名稱或非互動式數學模擬 (Game of Life)，但嚴格排除所有可互動遊戲
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

    # 4. 高耗時加載模組 (Heavy Loading)
    # 外部多重媒體檔案下載 (圖片/音效/字型)
    media_loads = re.findall(r'\b(loadImage|loadSound|loadModel|loadFont|loadJSON|loadBytes|loadStrings|createVideo)\s*\(\s*[\'\"`](https?://[^\'\"`]+)[\'\"`]', code)
    if len(media_loads) >= 2:
        return False, f"含有多重外部遠端媒體資源加載 ({len(media_loads)} 個)"
    # 大量外部非 CDN 資源引用
    all_urls = re.findall(r'https?://[^\s\'\"`)]+', full_content)
    non_cdn = [u for u in all_urls if not any(c in u for c in ['cdnjs', 'jsdelivr', 'unpkg', 'openprocessing.org', 'google', 'esm', 'github'])]
    if len(non_cdn) >= 5:
        return False, f"含有過多外部第三方遠端依賴 ({len(non_cdn)} 個)"
    # 重型 3D 模型載入 (GLTF / OBJ / FBX)
    if re.search(r'\b(loadModel|loadGLTF|GLTFLoader|OBJLoader)\s*\(', code):
        return False, "含有重型 3D 幾何模型載入 (GLTF/OBJ/FBX)"
    # 外部 AI / ML 權重下載 (ml5, posenet, facemesh)
    if re.search(r'\b(ml5\.(bodyPix|poseNet|imageClassifier|featureExtractor|yolo|unet|facemesh|handpose)|tf\.loadLayersModel|tf\.loadGraphModel)\b', full_content):
        return False, "含有大型 AI/ML 模型權重加載"
    # 代碼/資料體積過大 (> 800KB)
    if len(code) > 800 * 1024:
        return False, f"代碼或資料體積過大 ({len(code)//1024}KB > 800KB)"

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

    def __init__(self, items_to_import, save_dir):
        super().__init__()
        self.items = items_to_import
        self.save_dir = save_dir
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
                
                # 嚴格執行 4K MV 視覺預設模組收錄資格檢測 (排除 攝影機/AR/XR/GAME/高耗時加載)
                tags_list = sketch_data.get("tags", [])
                desc_text = sketch_data.get("description", "")
                is_eligible, reject_reason = validate_visual_module_eligibility(
                    title=title_og,
                    code=code,
                    custom_html=custom_html,
                    tags=tags_list,
                    desc=desc_text
                )

                if not is_eligible:
                    self.log_signal.emit(f"⚠️ 略過不符合規範模組: 「{title_og}」(ID: {sketch_id}) 原因: {reject_reason}", False)
                    try:
                        with open(os.path.join(workspace_dir, "op_import_errors.txt"), "a", encoding="utf-8") as ef:
                            ef.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - SKIPPED ({reject_reason}): {url} - {title_og}\n")
                    except Exception:
                        pass
                    continue

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
                    "tags": ["batch_import", "openprocessing", "audio_reactive"],
                    "url": url,
                    "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                # 縮圖下載
                thumb_dir = os.path.join(self.save_dir, "thumbnails")
                os.makedirs(thumb_dir, exist_ok=True)
                dest_thumb_path = os.path.join(thumb_dir, f"{unique_name}.jpg")
                for ext in [".jpg", ".png"]:
                    try:
                        thumb_url = f"https://openprocessing.org/usercontent/sketches/images/{sketch_id}{ext}"
                        img_resp = requests.get(thumb_url, headers=headers, timeout=5)
                        if img_resp.status_code == 200:
                            with open(dest_thumb_path, "wb") as img_f:
                                img_f.write(img_resp.content)
                            break
                    except Exception:
                        continue
                
                self.log.emit(f"  [+] 【成功收編】作品「{title_og}」", False)
                self.success_list.append({
                    "id": sketch_id, "title": title, "url": url, "filename": candidate,
                    "filepath": save_path, "code": adapted_code, "custom_html": custom_html,
                    "custom_css": custom_css, "save_dir": self.save_dir
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


class TestRunDialog(QDialog):
    MAX_CODE_CHARS = 200000
    WATCHDOG_TIMEOUT_SEC = 8

    def __init__(self, items_to_test, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音畫互動模組 - 批次收錄試運行工作區")
        self.resize(900, 650)
        self.items = items_to_test
        self.current_idx = 0
        self.errors = []
        self.countdown = 15
        self.parent_app = parent
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { font-family: 'Inter', sans-serif; }
            QPushButton { border-radius: 6px; padding: 10px; font-weight: bold; font-size: 13px; }
        """)
        
        layout = QVBoxLayout(self)
        
        self.title_label = QLabel(self)
        self.title_label.setStyleSheet("color: #e4e4e7; font-weight: bold; font-size: 14px; margin-bottom: 2px;")
        layout.addWidget(self.title_label)
        
        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.status_label)
        
        self.web_view = QWebEngineView(self)
        self.web_view.setMinimumHeight(450)
        layout.addWidget(self.web_view)
        
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

    def handle_js_log(self, level, message, lineNumber):
        msg_lower = message.lower()
        ignored = ["failed to fetch", "audiocontext", "cors", "[mock]", "[preloadguard]", "opentype", ".ttf", ".woff"]
        if any(p in msg_lower for p in ignored):
            return
            
        is_err = (level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel)
        if is_err or "uncaught" in msg_lower or "is not defined" in msg_lower:
            err_line = f"Line {lineNumber}: {message}"
            if err_line not in self.errors:
                self.errors.append(err_line)

    def _on_watchdog_timeout(self):
        if not self._watchdog_alive:
            self.next_item()

    def start_next_item(self):
        if self.current_idx >= len(self.items):
            QMessageBox.information(self, "試運行完成", "所有收編模組的試運行已全部完成！")
            self.accept()
            return
            
        self.current_item = self.items[self.current_idx]
        self.errors = []
        self.countdown = 15
        
        title = self.current_item["title"]
        url = self.current_item["url"]
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

    def tick(self):
        self.countdown -= 1
        if self.countdown > 0:
            self.status_label.setText(f"正在試運行中... 剩餘 {self.countdown} 秒")
        else:
            self.timer.stop()
            self.status_label.setText("✨ 試運行完成，請選擇是否保留。")

    def keep_current(self):
        self.timer.stop()
        filepath = self.current_item.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if self.cb_star.isChecked():
                    data["is_starred"] = True
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
        self.next_item()

    def discard_current(self):
        self.timer.stop()
        filepath = self.current_item.get("filepath")
        if filepath and os.path.exists(filepath):
            try: os.remove(filepath)
            except Exception: pass
            
        thumb_path = os.path.join(self.current_item["save_dir"], "thumbnails", f"{self.current_item['filename'][:-5]}.jpg")
        if os.path.exists(thumb_path):
            try: os.remove(thumb_path)
            except Exception: pass
            
        self.items.pop(self.current_idx)
        self.start_next_item()

    def skip_current(self):
        self.timer.stop()
        self.next_item()

    def next_item(self):
        self.current_idx += 1
        self.start_next_item()


class BatchImportDialog(QDialog):
    """OpenProcessing 藝術視覺模組 - 自動化批次收編工作區"""
    def __init__(self, parent=None, refresh_callback=None):
        super().__init__(parent)
        self.refresh_callback = refresh_callback
        self.detected_sketches_map = {}
        self.save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(self.save_dir, exist_ok=True)
        self.existing_urls = self.get_existing_urls()
        
        self.setWindowTitle("📥 OpenProcessing 藝術視覺模組 - 自動化批次收編工作區")
        self.resize(1300, 750)
        
        self.setStyleSheet("""
            QDialog { background-color: #09090b; color: #f4f4f5; }
            QLabel { color: #e4e4e7; font-family: 'Outfit', 'Inter', sans-serif; font-size: 13px; }
            QLineEdit { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 6px 12px; font-size: 13px; }
            QPushButton { background-color: #18181b; color: #f4f4f5; border: 1px solid #27272a; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
            QPushButton#btn_import { background-color: #7c3aed; border-color: #7c3aed; }
            QPushButton#btn_import:hover { background-color: #8b5cf6; }
            QListWidget { background-color: #09090b; border: 1px solid #27272a; border-radius: 8px; color: #f4f4f5; }
            QTextEdit { background-color: #18181b; border: 1px solid #27272a; border-radius: 8px; color: #a1a1aa; font-family: 'Courier New', monospace; font-size: 11px; }
            QProgressBar { border: 1px solid #27272a; border-radius: 4px; background-color: #18181b; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #7c3aed; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("作者首頁/分頁網址："))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("例如: https://openprocessing.org/@epi/#sketches")
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
        main_layout.addLayout(top_bar)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左側瀏覽器
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        left_layout.addWidget(QLabel("🌐 OpenProcessing 瀏覽視窗"))
        left_layout.addWidget(self.web_view)
        splitter.addWidget(left_widget)
        
        # 右側控制台
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
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

    def log_to_console(self, text, is_err=False):
        color = "#f43f5e" if is_err else "#38bdf8" if "[+]" in text else "#a1a1aa"
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
        self.log_to_console(f"正在載入: {url} ...")
        self.web_view.load(QUrl(url))

    def toggle_expand_sketches(self):
        if self.is_expanding:
            self.is_expanding = False
            self.expand_timer.stop()
            self.btn_expand.setText("⬇️ 自動展開")
        else:
            self.is_expanding = True
            self.btn_expand.setText("⏳ 停止展開")
            self.expand_timer = QTimer(self)
            self.expand_timer.timeout.connect(self.expand_step)
            self.expand_timer.start(2000)

    def expand_step(self):
        js = """
        window.scrollTo(0, document.body.scrollHeight);
        let btn = document.querySelector('.seeMoreButton') || document.querySelector('.showMore');
        if (btn) btn.click();
        """
        self.web_view.page().runJavaScript(js)

    def parse_sketches(self):
        js = """
        (function() {
            let items = [];
            document.querySelectorAll('a').forEach(a => {
                let m = a.href ? a.href.match(/\\/(?:sketch|@[\\w\\-]+)\\/(\\d+)/) : null;
                if (m) {
                    let titleEl = a.querySelector('.sketchTitle') || a.querySelector('[class*="title"]');
                    let title = titleEl ? titleEl.textContent : a.innerText;
                    items.push({ id: m[1], title: title.trim(), url: a.href });
                }
            });
            return items;
        })()
        """
        self.web_view.page().runJavaScript(js, self.on_parse_finished)

    def on_parse_finished(self, items):
        if not items: return
        for it in items:
            self.detected_sketches_map[it["id"]] = it
            
        self.list_widget.clear()
        pending = 0
        for sid, it in self.detected_sketches_map.items():
            is_imported = it["url"].rstrip("/") in self.existing_urls or sid in self.existing_urls
            item_widget = QListWidgetItem(f"[{sid}] {it['title']}")
            if is_imported:
                item_widget.setText(f"✓ [已收錄] {it['title']}")
                item_widget.setForeground(Qt.GlobalColor.darkGray)
            else:
                item_widget.setText(f"▢ [待收編] {it['title']}")
                item_widget.setCheckState(Qt.CheckState.Checked)
                pending += 1
            item_widget.setData(Qt.ItemDataRole.UserRole, it)
            self.list_widget.addItem(item_widget)
            
        self.btn_import.setEnabled(pending > 0)
        self.log_to_console(f"共解析出 {len(self.detected_sketches_map)} 個作品，待收編: {pending} 個。")

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
        
        self.worker = BatchImportWorker(selected, self.save_dir)
        self.worker.progress.connect(lambda idx, txt: self.progress_bar.setValue(idx))
        self.worker.log.connect(self.log_to_console)
        self.worker.finished.connect(self.on_import_finished)
        self.worker.start()

    def on_import_finished(self, failed):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.btn_import.setEnabled(True)
        if self.refresh_callback:
            self.refresh_callback()
            
        success_items = getattr(self.worker, 'success_list', [])
        reply = QMessageBox.question(self, "收編完成", f"已成功收編 {len(success_items)} 個模組！\n是否立即啟動試運行工作區？")
        if reply == QMessageBox.StandardButton.Yes and success_items:
            dlg = TestRunDialog(success_items, self)
            dlg.exec()
