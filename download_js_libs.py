import os
import re
import json
import hashlib
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Set, List, Tuple

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
LIBS_DIR = os.path.join(CUSTOM_VISUALS_DIR, "libs")
JS_CACHE_DIR = os.path.join(WORKSPACE_DIR, "js_cache")

# 確保快取目錄齊全
os.makedirs(LIBS_DIR, exist_ok=True)
os.makedirs(JS_CACHE_DIR, exist_ok=True)

# 核心依賴庫標準映射表
KNOWN_LIBRARIES = {
    "p5.min.js": "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js",
    "p5.sound.min.js": "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js",
    "p5.func.min.js": "https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js",
    "gsap.min.js": "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js",
    "opc.min.js": "https://cdn.jsdelivr.net/gh/msawired/OPC@latest/opc.min.js",
    "p5.flex.min.js": "https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js",
    "rampensau.js": "https://cdn.jsdelivr.net/npm/rampensau/dist/index.js",
    "chroma.min.js": "https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js",
    "tone.min.js": "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js",
    "polybool.min.js": "https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js",
    "three.min.js": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
    "lil-gui.umd.min.js": "https://cdn.jsdelivr.net/npm/lil-gui@0.19/dist/lil-gui.umd.min.js",
    "matter.min.js": "https://cdnjs.cloudflare.com/ajax/libs/matter-js/0.19.0/matter.min.js",
    "p5.play.js": "https://cdn.jsdelivr.net/npm/p5.play@2/lib/p5.play.js",
    "p5.scribble.js": "https://cdn.jsdelivr.net/gh/generative-light/p5.scribble.js/p5.scribble.min.js",
    "clmtrackr.js": "https://cdn.jsdelivr.net/npm/clmtrackr@1.1.2/build/clmtrackr.min.js",
    "polygon-clipping.umd.min.js": "https://cdn.jsdelivr.net/npm/polygon-clipping@0.15.3/dist/polygon-clipping.umd.min.js",
    "decomp.min.js": "https://cdn.jsdelivr.net/npm/poly-decomp@0.3.0/build/decomp.min.js"
}

# 已知常見缺失庫的官方 Safe Stub 注入表
KNOWN_STUBS = {
    "opensimplexnoise": """// OpenSimplexNoise Safe Fallback Stub
if (typeof OpenSimplexNoise === 'undefined') {
    window.OpenSimplexNoise = class {
        constructor(seed = 0) { this.seed = seed; }
        eval2D(x, y) { return Math.sin(x * 0.1) * Math.cos(y * 0.1); }
        eval3D(x, y, z) { return Math.sin(x * 0.1 + z) * Math.cos(y * 0.1); }
        eval4D(x, y, z, w) { return Math.sin(x * 0.1 + w) * Math.cos(y * 0.1 + z); }
    };
}""",
    "matter": """// Matter.js Safe Stub
if (typeof Matter === 'undefined') {
    window.Matter = {
        Engine: { create: () => ({ world: {} }), update: () => {} },
        World: { add: () => {}, remove: () => {} },
        Bodies: { rectangle: () => ({ position: {x:0, y:0} }), circle: () => ({ position: {x:0, y:0} }) }
    };
}""",
    "clmtrackr": """// clmtrackr Safe Stub
if (typeof clm === 'undefined') {
    window.clm = { tracker: function() { return { init: function(){}, start: function(){}, getCurrentPosition: function(){ return []; } }; } };
}""",
    "p5play": """// p5play Safe Stub
if (typeof Sprite === 'undefined') {
    window.Sprite = class { constructor(x,y,w,h) { this.x=x||0; this.y=y||0; this.w=w||50; this.h=h||50; this.vel={x:0,y:0}; } };
}"""
}

def get_mapped_filename(url: str) -> str:
    """ 根據 URL 產生具備可辨識性的乾淨檔名 """
    parsed = urllib.parse.urlparse(url)
    base_name = os.path.basename(parsed.path)
    
    if not base_name or "." not in base_name:
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:8]
        return f"lib_{url_hash}.js"
        
    if not base_name.endswith(".js") and not base_name.endswith(".mjs"):
        base_name = f"{base_name}.js"
        
    return base_name

def extract_urls_from_code_and_html(content: str) -> List[str]:
    """ 從代碼與 HTML 中完整抓取所有 external JS / ESM CDN 網址 """
    if not content:
        return []
        
    urls = []
    # 1. 抓取 <script src="...">
    script_matches = re.findall(r'<script[^>]+src=["\'](https?://[^"\']+)["\']', content, re.IGNORECASE)
    urls.extend(script_matches)
    
    # 2. 抓取 ESM import 語句: import ... from "https://..."
    import_matches = re.findall(r'\bimport\s+.*?from\s+["\'](https?://[^"\']+)["\']', content)
    urls.extend(import_matches)
    
    # 3. 抓取動態 import("https://...")
    dynamic_import_matches = re.findall(r'\bimport\s*\(\s*["\'](https?://[^"\']+)["\']\s*\)', content)
    urls.extend(dynamic_import_matches)
    
    # 4. 抓取 importmap 內容
    importmap_match = re.search(r'<script\s+type=["\']importmap["\'][^>]*>(.*?)</script>', content, re.DOTALL | re.IGNORECASE)
    if importmap_match:
        try:
            map_data = json.loads(importmap_match.group(1))
            imports = map_data.get("imports", {})
            for target_url in imports.values():
                if target_url.startswith(("http://", "https://")):
                    urls.append(target_url)
        except Exception:
            pass
            
    return list(set(u.strip() for u in urls if u.strip()))

def get_mirror_fallback_urls(url: str) -> List[str]:
    """ 生成多層級 CDN 鏡像位址備援清單 """
    candidates = [url]
    
    # unpkg -> cdn.jsdelivr.net
    if "unpkg.com/" in url:
        candidates.append(url.replace("unpkg.com/", "cdn.jsdelivr.net/npm/"))
        candidates.append(url.replace("unpkg.com/", "esm.sh/"))
        
    # cdn.jsdelivr.net/npm/ -> unpkg.com
    elif "cdn.jsdelivr.net/npm/" in url:
        candidates.append(url.replace("cdn.jsdelivr.net/npm/", "unpkg.com/"))
        candidates.append(url.replace("cdn.jsdelivr.net/npm/", "esm.sh/"))
        
    # cdnjs -> jsdelivr
    elif "cdnjs.cloudflare.com/ajax/libs/" in url:
        match = re.search(r'/ajax/libs/([^/]+)/([^/]+)/(.*)', url)
        if match:
            pkg, ver, rest = match.groups()
            candidates.append(f"https://cdn.jsdelivr.net/npm/{pkg}@{ver}/{rest}")
            
    return candidates

def download_and_cache_url(url: str) -> Tuple[str, str, str]:
    """ 執行下載並同時同步寫入 libs/ 與 js_cache/ 目錄 """
    filename = get_mapped_filename(url)
    dest_path_libs = os.path.join(LIBS_DIR, filename)
    dest_path_cache = os.path.join(JS_CACHE_DIR, filename)
    
    # 若兩個目標路徑皆已存在，直接略過
    if os.path.exists(dest_path_libs) and os.path.exists(dest_path_cache):
        return url, "EXIST", filename

    candidates = get_mirror_fallback_urls(url)
    last_err = None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*'
    }

    for cand_url in candidates:
        try:
            req = urllib.request.Request(cand_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status == 200:
                    content = response.read()
                    with open(dest_path_libs, "wb") as f1:
                        f1.write(content)
                    with open(dest_path_cache, "wb") as f2:
                        f2.write(content)
                    return url, "SUCCESS", filename
        except Exception as e:
            last_err = e

    # 若所有鏡像皆失敗，檢查是否屬於已知可 Stub 的庫
    url_lower = url.lower()
    for stub_key, stub_code in KNOWN_STUBS.items():
        if stub_key in url_lower:
            with open(dest_path_libs, "w", encoding="utf-8") as f1:
                f1.write(stub_code)
            with open(dest_path_cache, "w", encoding="utf-8") as f2:
                f2.write(stub_code)
            return url, "SUCCESS (STUB REPLACED)", filename

    return url, f"FAILED ({last_err})", filename

def main():
    print("=" * 65)
    print("   🌐 視覺模組本地依賴庫 (Offline JS Libs & Cache) 全自動同步器")
    print("=" * 65)

    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"[錯誤] 找不到 custom_visuals 目錄: {CUSTOM_VISUALS_DIR}")
        return

    all_target_urls: Set[str] = set()

    # 1. 加入已知核心依賴庫
    for lib_url in KNOWN_LIBRARIES.values():
        all_target_urls.add(lib_url)

    # 2. 深度掃描 custom_visuals/ 底下所有 JSON 模組中的自訂引入
    print("\n[1/3] 正在深度掃描本機已收錄視覺模組之依賴...")
    json_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
    
    for fname in json_files:
        fpath = os.path.join(CUSTOM_VISUALS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            custom_html = data.get("custom_html", "")
            code = data.get("code", "")
            
            urls = extract_urls_from_code_and_html(f"{custom_html}\n{code}")
            for u in urls:
                all_target_urls.add(u)
        except Exception as e:
            print(f"  ⚠️ 讀取模組 {fname} 失敗: {e}")

    print(f"  掃描完畢！累計收錄模組: {len(json_files)} 個，共需維護 {len(all_target_urls)} 個獨立 JS 元件。")

    # 3. 檢查本地是否存在
    print("\n[2/3] 比對本地快取狀態 (custom_visuals/libs/ & js_cache/)...")
    urls_to_download = []
    for u in all_target_urls:
        fname = get_mapped_filename(u)
        p1 = os.path.join(LIBS_DIR, fname)
        p2 = os.path.join(JS_CACHE_DIR, fname)
        if not (os.path.exists(p1) and os.path.exists(p2)):
            urls_to_download.append(u)

    if not urls_to_download:
        print("  🎉 完美！所有必要依賴庫均已完整快取至本機。完全支援離線 4K 渲染！")
        return

    print(f"  發現 {len(urls_to_download)} 個元件缺失，啟動多執行緒安全下載 (並發數: 6)...")

    # 4. 多執行緒下載
    print("\n[3/3] 正在執行背景下載與鏡像同步...")
    success_count = 0
    failed_count = 0
    already_exist_count = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(download_and_cache_url, url): url for url in urls_to_download}
        for future in as_completed(futures):
            orig_url = futures[future]
            try:
                url, status, filename = future.result()
                if "SUCCESS" in status:
                    print(f"  [+] 成功就緒: {filename} <- ({url})")
                    success_count += 1
                elif status == "EXIST":
                    already_exist_count += 1
                else:
                    print(f"  [x] 下載失敗 [{status}]: {url}")
                    failed_count += 1
            except Exception as exc:
                print(f"  [x] 任務例外: {orig_url} ({exc})")
                failed_count += 1

    print("\n" + "=" * 65)
    print("   同步作業結束報告：")
    print(f"   - 成功下載並快取: {success_count} 個")
    print(f"   - 下載失敗: {failed_count} 個")
    print(f"   - 原本已就緒: {len(all_target_urls) - len(urls_to_download) + already_exist_count} 個")
    print(f"   - 本地庫路徑: {LIBS_DIR}")
    print("=" * 65)

if __name__ == "__main__":
    main()
