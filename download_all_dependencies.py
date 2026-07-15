import os
import re
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

workspace_dir = os.path.dirname(os.path.abspath(__file__))
custom_visuals_dir = os.path.join(workspace_dir, "custom_visuals")
cache_dir = os.path.join(workspace_dir, "js_cache")
os.makedirs(cache_dir, exist_ok=True)

# 核心依賴庫對照表（與 main.py 同步）
KNOWN_LIBRARIES = {
    "p5.min.js": "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js",
    "p5.sound.min.js": "https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/addons/p5.sound.min.js",
    "p5.func.min.js": "https://cdn.jsdelivr.net/gh/IDMNYU/p5.js-func/lib/p5.func.min.js",
    "gsap.min.js": "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js",
    "opc.min.js": "https://cdn.jsdelivr.net/gh/msawired/OPC@latest/opc.min.js",
    "p5.flex.min.js": "https://cdn.jsdelivr.net/npm/p5.flex@0.2.0/src/p5.flex.min.js",
    "rampensau.min.js": "https://cdn.jsdelivr.net/npm/rampensau/dist/index.js",
    "chroma.min.js": "https://cdn.jsdelivr.net/npm/chroma-js/chroma.min.js",
    "Tone.min.js": "https://cdnjs.cloudflare.com/ajax/libs/tone/14.8.49/Tone.min.js",
    "polybool.min.js": "https://cdn.jsdelivr.net/npm/polybooljs@1.2.2/dist/polybool.min.js"
}

def get_mapped_filename(url):
    filename = url.split("/")[-1]
    if "?" in filename:
        filename = filename.split("?")[0]
    if not filename.endswith(".js"):
        filename = f"custom_lib_{abs(hash(url))}.js"
    return filename

def extract_urls_from_html(html_str):
    if not html_str:
        return []
    urls = []
    # 正則匹配 script src 中的線上 JS 網址
    matches = re.findall(r'src=["\'](https?://[^"\']+)["\']', html_str, re.IGNORECASE)
    for m in matches:
        urls.append(m.strip())
    return urls

def download_url(url):
    filename = get_mapped_filename(url)
    local_path = os.path.join(cache_dir, filename)
    
    if os.path.exists(local_path):
        return url, "EXIST", filename
        
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(local_path, "wb") as f:
                f.write(response.read())
        return url, "SUCCESS", filename
    except Exception as e:
        return url, f"FAILED ({e})", filename

def main():
    print("=========================================================")
    print("   視覺模組本地依賴庫（JS Cache）一鍵掃描與下載器")
    print("=========================================================")
    
    if not os.path.exists(custom_visuals_dir):
        print(f"[錯誤] 找不到 custom_visuals 目錄：{custom_visuals_dir}")
        return

    # 收集所有的 JS 庫 URL
    all_urls = set()
    
    # 預載預設的核心 JS 庫
    for lib_url in KNOWN_LIBRARIES.values():
        all_urls.add(lib_url)
        
    # 掃描所有的預設 JSON 檔
    print("[1/3] 正在掃描本機已收錄模組...")
    json_count = 0
    for file in os.listdir(custom_visuals_dir):
        if file.endswith(".json"):
            json_count += 1
            path = os.path.join(custom_visuals_dir, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                custom_html = data.get("custom_html", "")
                urls = extract_urls_from_html(custom_html)
                for u in urls:
                    all_urls.add(u)
            except Exception as e:
                print(f"  [!] 讀取檔案 {file} 出錯: {e}")
                
    print(f"  掃描完成！共尋找到 {json_count} 個模組，累計需要 {len(all_urls)} 個 JS 依賴元件。")
    
    # 篩選出需要下載的 URL
    urls_to_download = []
    print("\n[2/3] 正在檢查本機快取目錄...")
    for url in all_urls:
        filename = get_mapped_filename(url)
        local_path = os.path.join(cache_dir, filename)
        if not os.path.exists(local_path):
            urls_to_download.append(url)
            
    if not urls_to_download:
        print("  🎉 檢查完成！所有依賴庫均已下載至本地快取 (js_cache/)。不需要下載任何項目！")
        return
        
    print(f"  發現 {len(urls_to_download)} 個元件缺失，準備開始背景下載...")
    
    # 開始多執行緒安全下載
    print("\n[3/3] 正在進行多執行緒安全下載 (Thread Pool)...")
    success_count = 0
    failed_count = 0
    already_exists_count = 0
    
    # 限制最大並發數為 5，避免請求頻繁被 CDN 拒絕
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(download_url, url): url for url in urls_to_download}
        for future in as_completed(futures):
            url = futures[future]
            try:
                url, status, filename = future.result()
                if status == "SUCCESS":
                    print(f"  [+] 下載成功: {filename} ({url})")
                    success_count += 1
                elif status == "EXIST":
                    already_exists_count += 1
                else:
                    print(f"  [x] 下載失敗 ({status}): {url}")
                    failed_count += 1
            except Exception as exc:
                print(f"  [x] 下載任務異常: {url} ({exc})")
                failed_count += 1
                
    print("\n=========================================================")
    print("   下載任務執行完畢！")
    print(f"   - 成功下載: {success_count} 個")
    print(f"   - 下載失敗: {failed_count} 個")
    print(f"   - 本機已存在: {len(all_urls) - len(urls_to_download) + already_exists_count} 個")
    print("=========================================================")

if __name__ == "__main__":
    main()
