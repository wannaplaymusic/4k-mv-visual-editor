# -*- coding: utf-8 -*-
"""
SENTINEL: Ambient Particle Curation & Real-Time Auto-Tagging Assistant
---------------------------------------------------------------------
在幕後即時協助收錄作業：
1. 即時監聽與掃描 custom_visuals/，自動辨識粒子類型模組 (Particle / Attractor / Flow Field / Stardust)
2. 自動打上標準標籤: ['particle', 'particles', 'ambient_particle', 'ambient', 'ambient_compatible']
3. 同步註冊至 module_expressive_db.json 與 AmbientModuleCompatibilityGate (GREEN 原生神級名單)
4. 供日後導演系統、Bandit 演算法與 UI 分類秒級精準調用。
"""

import os
import re
import json
import time
import glob
import logging
from typing import Dict, List, Any, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AmbientParticleAssistant")

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
EXPRESSIVE_DB_PATH = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")

PARTICLE_KEYWORDS = [
    "particle", "particles", "attractor", "flowfield", "flow field", 
    "stardust", "cosmic", "galaxy", "swarm", "flock", "flocking", 
    "boid", "physics", "dots", "nebula", "spore", "emitter", "curl noise"
]

CODE_PARTICLE_SIGNATURES = [
    r"\bclass\s+Particle\b",
    r"\bfunction\s+Particle\b",
    r"\bparticles\s*=\s*\[\]",
    r"\bparticles\.push\b",
    r"\bparticles\.length\b",
    r"\bnew\s+Particle\b",
    r"\bupdateParticles\b",
    r"\bdrawParticles\b",
    r"\bflowfield\b",
    r"\bParticleSystem\b"
]

REQUIRED_TAGS = ["particle", "particles", "ambient_particle", "ambient", "ambient_compatible"]


def is_particle_module(data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    精確檢測模組是否屬於粒子類別
    """
    name = str(data.get("name", "")).lower()
    title = str(data.get("title", "")).lower()
    url = str(data.get("url", "")).lower()
    tags = [str(t).lower() for t in data.get("tags", [])]
    desc = str(data.get("description", "")).lower()
    code = str(data.get("code", ""))

    combined_meta = f"{name} {title} {url} {' '.join(tags)} {desc}"

    # 1. 來源與元數據匹配
    for kw in PARTICLE_KEYWORDS:
        if kw in combined_meta:
            return True, f"元數據匹配關鍵詞 [{kw}]"

    # 2. 程式碼特徵簽名匹配
    for sig in CODE_PARTICLE_SIGNATURES:
        if re.search(sig, code, flags=re.IGNORECASE):
            return True, f"代碼匹配粒子特徵語法 [{sig}]"

    return False, ""


def tag_single_module(file_path: str, expressive_db: Dict[str, Any] = None) -> bool:
    """
    為單個模組實施粒子與 Ambient 智能標記，並註冊至表達力資料庫
    """
    if not os.path.exists(file_path) or not file_path.endswith(".json"):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"讀取模組失敗 ({file_path}): {e}")
        return False

    is_particle, reason = is_particle_module(data)
    if not is_particle:
        return False

    # 注入標籤
    current_tags = data.get("tags", [])
    if not isinstance(current_tags, list):
        current_tags = []

    tags_changed = False
    for req_tag in REQUIRED_TAGS:
        if req_tag not in current_tags:
            current_tags.append(req_tag)
            tags_changed = True

    mod_name = data.get("name", os.path.basename(file_path)[:-5])
    unique_key = os.path.basename(file_path)[:-5]

    # 如果有變更，寫回 custom_visuals
    if tags_changed:
        data["tags"] = current_tags
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"✨ [粒子標記] 已為模組「{mod_name}」成功注入 Ambient 粒子標籤 (原因: {reason})")
        except Exception as e:
            logger.error(f"寫入模組失敗 ({file_path}): {e}")
            return False

    # 同步更新 module_expressive_db.json
    if expressive_db is not None:
        if unique_key not in expressive_db or not expressive_db[unique_key].get("ambient_drone_compatible"):
            expressive_db[unique_key] = {
                "module_id": unique_key,
                "name": mod_name,
                "primary_psychological_state": "hypnotic_trance",
                "symbolic_metaphors": ["微觀粒子", "量子流動", "深空星塵", "意識漣漪"],
                "narrative_function": "ambient_soundscape",
                "dynamics": {
                    "mean_velocity": 0.15,
                    "motion_energy_type": "sinusoidal_breath"
                },
                "ambient_drone_compatible": True,
                "ambient_subgenre": "particle_stardust",
                "ambient_tier": "GREEN",
                "ambient_recommended_speed_scale": 1.0,
                "ambient_desaturation_factor": 0.0
            }

    return True


def scan_and_tag_all_existing() -> Dict[str, int]:
    """
    全量掃描並標註目前已收錄的所有粒子模組
    """
    logger.info("🔍 開始掃描現有庫存以標記所有粒子類別模組...")
    db = {}
    if os.path.exists(EXPRESSIVE_DB_PATH):
        try:
            with open(EXPRESSIVE_DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = {}

    files = glob.glob(os.path.join(CUSTOM_VISUALS_DIR, "*.json"))
    tagged_count = 0

    for p in files:
        if tag_single_module(p, expressive_db=db):
            tagged_count += 1

    try:
        with open(EXPRESSIVE_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"更新表達力資料庫失敗: {e}")

    logger.info(f"✅ 全量掃描完成！總計掃描 {len(files)} 個模組，成功標註/確認 {tagged_count} 個 Ambient 粒子模組。")
    return {"total_files": len(files), "tagged_particle_modules": tagged_count}


def run_realtime_curation_watcher(poll_interval: float = 2.0, max_duration: float = 3600.0):
    """
    幕後即時監聽守護行程：在使用者進行批次收錄時，自動對新入庫模組打標
    """
    logger.info("🛰️ 啟動幕後收錄作業守護引擎 (即時監聽新收錄作品)...")
    seen_mtimes = {}
    for p in glob.glob(os.path.join(CUSTOM_VISUALS_DIR, "*.json")):
        seen_mtimes[p] = os.path.getmtime(p)

    start_t = time.time()
    while time.time() - start_t < max_duration:
        time.sleep(poll_interval)
        current_files = glob.glob(os.path.join(CUSTOM_VISUALS_DIR, "*.json"))
        db_needs_save = False

        db = {}
        if os.path.exists(EXPRESSIVE_DB_PATH):
            try:
                with open(EXPRESSIVE_DB_PATH, "r", encoding="utf-8") as f:
                    db = json.load(f)
            except Exception:
                db = {}

        for p in current_files:
            mtime = os.path.getmtime(p)
            if p not in seen_mtimes or mtime > seen_mtimes[p]:
                seen_mtimes[p] = mtime
                if tag_single_module(p, expressive_db=db):
                    db_needs_save = True

        if db_needs_save:
            try:
                with open(EXPRESSIVE_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(db, f, ensure_ascii=False, indent=2)
            except Exception:
                pass


if __name__ == "__main__":
    scan_and_tag_all_existing()
