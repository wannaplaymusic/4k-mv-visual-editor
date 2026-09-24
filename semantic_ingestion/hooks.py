# -*- coding: utf-8 -*-
"""
SENTINEL: Public Hooks & Integration Bridge
提供給 batch_importer、ai_incubator、auto_repair 的一鍵非同步掛載接口。
"""

import os
import sys
import subprocess
import logging
from typing import List, Optional

logger = logging.getLogger("StandaloneInjector.SentinelHooks")
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def trigger_semantic_ingestion(module_keys: List[str], background: bool = True, priority: str = "high"):
    """
    外部模組導入或修復完成時調用：
    1. 將模組鍵值加入持久化任務隊列
    2. 以獨立分離子進程 (Detached Subprocess) 啟動背景 Worker，完全不阻塞主程序
    """
    if not module_keys:
        return

    from .semantic_queue_manager import SemanticQueueManager
    
    # 1. 寫入隊列
    enqueued = SemanticQueueManager.enqueue_modules(module_keys, priority=priority)
    logger.info(f"📥 SENTINEL 鉤子已將 {enqueued}/{len(module_keys)} 個新模組登記入隊。")

    if not background:
        # 同步模式 (僅用於調試)
        from .semantic_worker_daemon import run_worker_loop
        run_worker_loop(max_tasks=enqueued)
        return

    # 2. 異步非阻塞分離子進程啟動
    python_bin = sys.executable
    daemon_script = os.path.join(WORKSPACE_DIR, "semantic_ingestion", "semantic_worker_daemon.py")

    cmd = [python_bin, "-m", "semantic_ingestion.semantic_worker_daemon", "--process-queue"]

    try:
        # 在 macOS / Linux 上以 start_new_session=True 完全分離進程
        proc = subprocess.Popen(
            cmd,
            cwd=WORKSPACE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        logger.info(f"🚀 SENTINEL 獨立語義解析子程序已在後台分離啟動 (PID: {proc.pid})。")
    except Exception as e:
        logger.error(f"❌ 啟動 SENTINEL 背景進程失敗: {str(e)}")
