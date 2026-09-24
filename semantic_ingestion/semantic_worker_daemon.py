# -*- coding: utf-8 -*-
"""
SENTINEL: Standalone Semantic Ingestion Worker Daemon
獨立非同步子程序守護進程：無頭渲染抽樣、三道物理門禁、4-in-1拼貼、VLM心靈標註與自動入庫。
可由命令列單獨執行，或由 batch_importer / ai_incubator 啟動。
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --enable-webgl --ignore-gpu-blocklist"

import sys
import json
import time
import argparse
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import cv2

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PyQt6.QtCore import QUrl, QTimer, QEventLoop, QSize

from headless_qc_repair import IMMUNITY_STUBS_JS, P5_V2_COMPAT_SHIM
from .visual_gatekeeper import VisualGatekeeper
from .spatiotemporal_tiler import SpatiotemporalTiler
from .vlm_client import VLMInferenceClient
from .semantic_queue_manager import SemanticQueueManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [SENTINEL] %(message)s")
logger = logging.getLogger("StandaloneInjector.SentinelDaemon")

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")

def build_sentinel_html(code: str, custom_html: str = "") -> str:
    """ 建立免崩潰、乾淨的無頭採樣 HTML """
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body, html {{ width: 100vw; height: 100vh; overflow: hidden; background: #000; }}
    canvas {{ display: block !important; width: 100% !important; height: 100% !important; }}
  </style>
  <script>
    if (typeof window.innerWidth === 'undefined' || window.innerWidth === 0) window.innerWidth = 1280;
    if (typeof window.innerHeight === 'undefined' || window.innerHeight === 0) window.innerHeight = 720;
    window.windowWidth = 1280;
    window.windowHeight = 720;
  </script>
  <script src="custom_visuals/libs/p5.min.js"></script>
  <script>
    window.audio = {{ bass: 0.6, mid: 0.5, high: 0.7, level: 0.6, energy: 0.65 }};
    {P5_V2_COMPAT_SHIM}
    {IMMUNITY_STUBS_JS}
  </script>
  <script src="custom_visuals/libs/p5.sound.min.js"></script>
  {custom_html}
</head>
<body>
  <script>
    try {{
      {code}
    }} catch(e) {{
      console.warn("Sketch runtime caught:", e);
    }}
  </script>
</body>
</html>
"""

class HeadlessSampler:
    """ 無頭視訊抽樣器 """
    def __init__(self, app: QApplication):
        self.app = app
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.settings().setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        self.profile.settings().setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        
        self.view = QWebEngineView()
        self.view.resize(QSize(1280, 720))
        self.view.show() # 激活內部渲染管道

    def capture_timeline_frames(self, code: str, custom_html: str = "") -> List[np.ndarray]:
        """ 載入模組並在時序關鍵點截取影格 """
        full_html = build_sentinel_html(code, custom_html=custom_html)
        temp_html_path = os.path.join(WORKSPACE_DIR, "_temp_sentinel_sample.html")
        try:
            with open(temp_html_path, "w", encoding="utf-8") as f:
                f.write(full_html)
        except Exception:
            pass

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        load_loop = QEventLoop()
        self.view.loadFinished.connect(lambda ok: load_loop.quit())
        self.view.setUrl(QUrl.fromLocalFile(temp_html_path))
        
        # 設置 4 秒超時防止網路資源卡死
        QTimer.singleShot(4000, load_loop.quit)
        load_loop.exec()

        frames = []
        # 時序採樣點 (毫秒): 800ms(初態), 2200ms(鋪陳), 3500ms(重拍動態)
        sample_delays = [800, 1400, 1500]
        
        for delay in sample_delays:
            loop = QEventLoop()
            QTimer.singleShot(delay, loop.quit)
            loop.exec()

            # 優先從 canvas 獲取 base64 影像
            js_code = """
            (function() {
                try {
                    const c = document.querySelector('canvas');
                    if (c && c.width > 0 && c.height > 0) {
                        return c.toDataURL('image/jpeg', 0.85);
                    }
                } catch(e) {}
                return '';
            })();
            """
            data_url = [None]
            js_loop = QEventLoop()
            def on_js(res):
                data_url[0] = res
                if js_loop.isRunning():
                    js_loop.quit()

            self.view.page().runJavaScript(js_code, on_js)
            QTimer.singleShot(800, js_loop.quit)
            js_loop.exec()

            if data_url[0] and "data:image" in str(data_url[0]):
                import base64
                try:
                    _, encoded = str(data_url[0]).split(",", 1)
                    img_bytes = base64.b64decode(encoded)
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    arr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if arr is not None and arr.size > 0:
                        frames.append(arr)
                        continue
                except Exception:
                    pass

            # 回退使用 view.grab()
            pixmap = self.view.grab()
            qimg = pixmap.toImage().convertToFormat(pixmap.toImage().Format.Format_BGR888)
            width = qimg.width()
            height = qimg.height()
            
            ptr = qimg.bits()
            ptr.setsize(height * width * 3)
            arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 3)).copy()
            frames.append(arr)

        return frames

def process_single_module(module_key: str, sampler: HeadlessSampler, vlm_client: VLMInferenceClient) -> bool:
    """ 處理單一模組的完整流水線 """
    # 查找模組檔案路徑
    filename = module_key if module_key.endswith(".json") else f"{module_key}.json"
    file_path = os.path.join(CUSTOM_VISUALS_DIR, filename)
    
    if not os.path.exists(file_path):
        logger.error(f"❌ 模組檔案不存在: {file_path}")
        SemanticQueueManager.mark_failed(module_key, "FILE_NOT_FOUND")
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        SemanticQueueManager.mark_failed(module_key, f"JSON_DECODE_ERROR: {str(e)}")
        return False

    code = data.get("code", "")
    custom_html = data.get("custom_html", "")

    # 1. 無頭渲染抽樣
    logger.info(f"⏳ 正在採樣模組畫面: {module_key}...")
    try:
        frames = sampler.capture_timeline_frames(code, custom_html)
    except Exception as e:
        logger.error(f"❌ 渲染採樣異常: {str(e)}")
        SemanticQueueManager.mark_failed(module_key, f"RENDER_EXCEPTION: {str(e)}")
        return False

    # 2. 物理門禁校驗
    passed, reason, metrics = VisualGatekeeper.audit_frames(frames)
    if not passed:
        logger.warning(f"⚠️ 模組未通過物理門禁: {module_key} 原因: {reason}")
        SemanticQueueManager.mark_failed(module_key, reason)
        # 標記模組需修復
        data["needs_qc_repair"] = True
        data["qc_reject_reason"] = reason
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return False

    # 3. 4-in-1 拼貼與特徵提取
    collage_img = SpatiotemporalTiler.create_4in1_collage(frames)
    color_feats = SpatiotemporalTiler.extract_color_features(frames)
    motion_feats = SpatiotemporalTiler.extract_motion_features(frames)

    # 4. 多模態 VLM 心理學標註
    logger.info(f"🧠 調用多模態 VLM 分析心理狀態: {module_key}...")
    profile = vlm_client.analyze_module(
        module_id=module_key,
        collage_img=collage_img,
        color_feats=color_feats,
        motion_feats=motion_feats,
        code_snippet=code[:1000]
    )

    # 5. 更新寫入資料庫與回寫模組 JSON
    profile_dict = profile.model_dump()
    SemanticQueueManager.mark_completed(module_key, profile_dict)

    # 回寫模組檔案自身，將其持久化在模組中
    data["expressive_profile"] = profile_dict
    data.pop("needs_qc_repair", None)
    data.pop("qc_reject_reason", None)
    # 若有新收錄標記，給予 Bandit 優先探索加權
    data["is_new_semantic_ingested"] = True
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    logger.info(f"✨ 成功完成心靈標註: [{module_key}] -> {profile.primary_psychological_state} ({profile.jungian_archetype})")
    return True

def run_worker_loop(max_tasks: int = 0):
    """ 運行守護任務工作迴圈 """
    app = QApplication.instance() or QApplication(sys.argv)
    sampler = HeadlessSampler(app)
    vlm_client = VLMInferenceClient()

    logger.info("🚀 SENTINEL 語義解析守護進程啟動，監聽任務隊列中...")
    processed_count = 0

    while True:
        task = SemanticQueueManager.pop_next_task()
        if not task:
            logger.info("💤 隊列當前已清空，工作進程正常休眠結束。")
            break

        process_single_module(task, sampler, vlm_client)
        processed_count += 1
        
        if max_tasks > 0 and processed_count >= max_tasks:
            logger.info(f"達到單批次上限 {max_tasks}，結束工作進程。")
            break
        
        # 輕微釋放事件循環
        app.processEvents()

def scan_and_enqueue_missing():
    """ 掃描 custom_visuals 中所有缺少 expressive_profile 的模組入隊 """
    all_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json")]
    db = SemanticQueueManager.load_expressive_db()
    missing_keys = []

    for fname in all_files:
        key = fname[:-5]
        if key not in db:
            missing_keys.append(key)

    logger.info(f"🔍 全庫掃描完成：共 {len(all_files)} 個模組，其中 {len(missing_keys)} 個缺少心靈語義標籤。")
    added = SemanticQueueManager.enqueue_modules(missing_keys, priority="normal")
    logger.info(f"📥 成功加入待處理佇列: {added} 個模組。")
    return added

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SENTINEL Semantic Ingestion Daemon")
    parser.add_argument("--process-queue", action="store_true", help="處理目前隊列中的模組")
    parser.add_argument("--scan-missing", action="store_true", help="掃描全庫缺失語義標籤的模組並入隊")
    parser.add_argument("--batch-keys", type=str, default="", help="指定批次模組名稱逗號分隔")
    parser.add_argument("--max-tasks", type=int, default=0, help="最多處理的任務數 (0為無限制)")

    args = parser.parse_args()

    if args.scan_missing:
        scan_and_enqueue_missing()

    if args.batch_keys:
        keys = [k.strip() for k in args.batch_keys.split(",") if k.strip()]
        SemanticQueueManager.enqueue_modules(keys, priority="high")

    if args.process_queue or args.batch_keys or args.scan_missing:
        run_worker_loop(max_tasks=args.max_tasks)
    else:
        status = SemanticQueueManager.get_queue_status()
        print(json.dumps(status, indent=2))
