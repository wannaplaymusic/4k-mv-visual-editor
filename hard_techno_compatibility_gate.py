# -*- coding: utf-8 -*-
"""
SENTINEL-HARDTECHNO: Hard Techno & Industrial Module Compatibility Gate
----------------------------------------------------------------------
庫存 4,500+ 模組對 Hard Techno / Industrial / Schranz 曲風的相容性審計與硬核美學門禁系統。

由 10 位跨領域專家會議決議落地：
1. 三色分級機制 (Tri-Tier Classification):
   - RED (Blacklist): 絕對封殺！花草、粉彩、融球、枕頭、泡泡、可愛卡通等有機軟性模組 100% 隔離。
   - YELLOW (Conditional Modulation): 具備抽象幾何或聲波特徵，但需增強對比與音訊瞬態響應。
   - GREEN (Native Hardcore): 原生極致硬核、高速穿梭隧道、結構光達、冷軋金屬、工業線框、高壓雷射。
2. 零延遲靜態過濾 (Zero-Latency In-Memory Filter):
   - 預加載與向量標籤位元過濾，耗時 < 1ms，杜絕主線程卡頓。
"""

import os
import json
import logging
import re
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger("VisualStudio.HardTechnoCompatibilityGate")

# ⚡ Hard Techno 專屬形態學白名單 (硬表面幾何、高速隧道、工業線框、高壓雷射、光達點雲)
HARD_TECHNO_MORPHOLOGY_KEYWORDS = {
    "tunnel", "tunnels", "spacetunnel", "wireframe", "grid", "mesh", "brutalist",
    "cyber", "matrix", "glitch", "industrial", "voxel", "voxels", "raymarch", "raymarching",
    "geometry", "geometric", "laser", "lasers", "strobe", "spectrum", "waveform",
    "monochrome", "cube", "cubes", "torus", "hypercube", "lidar", "pointcloud",
    "hexagon", "hexagons", "fractal", "fractals", "octahedron", "dodecahedron",
    "polyhedron", "architecture", "concrete", "metal", "metallic", "machine", "machinery",
    "scanline", "vector", "scope", "synthwave", "acid", "hardcore", "hyperspeed", "strobe",
    "reactor", "overdrive", "pulse", "shock", "kinetic", "audio_reactor", "blast", "surge"
}

# 🚫 軟性、慢速悠閒、有機生物、花草粉彩、融球、字符終端、玻璃靜物排除名單 (絕對禁止進入 Hard Techno 備選池)
HARD_TECHNO_TOXIC_BLACKLIST = {
    "flower", "flowers", "pillow", "pillowtalk", "cute", "soft", "pastel",
    "jelly", "jellyfish", "water", "droplet", "coral", "bubble", "bubbles",
    "rainbow", "rainbowmetaballs", "metaball", "metaballs", "fidget", "fidgetcubes",
    "cartoon", "nature", "leaf", "leaves", "petal", "petals", "sweet", "baby",
    "heart", "hearts", "romantic", "romance", "peaceful", "dreamy", "zen",
    "meditative", "auroralikepoints", "sedimentation", "bioluminescence",
    # ⚡ 徹底封殺假硬核、真冷靜模組 (Slow / Seaweed / Dragon / Ascii / Frosted Glass)
    "slow", "seaweed", "plant", "tree", "branch", "forest", "grass",
    "glass", "frosted", "translucent", "asciify", "ascii", "terminal", "console",
    "dragon", "animal", "creature", "statue", "figurine", "character", "face",
    "calm", "gentle", "chill", "ambient", "relax", "dream", "sleep"
}


# 🚫 測試/佔位/節慶/敏感題材模組 (完整名稱比對，不含子字串匹配)
HARD_TECHNO_JUNK_MODULES = {
    "errors", "testshader", "test3eurorack", "merrychristmas", "holalygia",
    "covidpledge", "alzheimers",
    # 渲染實測損壞：AutoDiff 未定義(JS 致命)、shader 'FAR' 編譯失敗、反覆被黑屏/死鎖守衛隔離 (45 支 Boom 批次渲染日誌實證)
    "genuarysquare", "global2dillumination", "absoluteinfinitemagicroom", "itcutsindeep",
    "thecomplexsociety", "planetwithasteroids", "websitedistortion", "fantasma",
    "reflactorunitalternativeactiontrippin", "obscure", "linesss", "emotionallines_newtest12",
    "koch3dsphericalfracal", "es6modulestest", "firesparklesshader", "beanofbestfit",
    "aurorashader4k", "futurewaveconcpet", "cloud", "cloudsmaker", "darkclouds",
}


class HardTechnoModuleCompatibilityGate:
    """
    專為 Hard Techno / Industrial / Schranz 曲風設計的資產庫存門禁守衛
    """
    _instance = None

    @classmethod
    def get_instance(cls, db_path: str = "module_expressive_db.json"):
        if cls._instance is None:
            cls._instance = cls(db_path=db_path)
        return cls._instance

    def __init__(self, db_path: str = "module_expressive_db.json"):
        self.db_path = db_path
        self.green_modules: Set[str] = set()
        self.yellow_modules: Set[str] = set()
        self.red_modules: Set[str] = set()
        self.module_metadata: Dict[str, Dict[str, Any]] = {}
        
        self.audit_and_classify_all()

    def audit_and_classify_all(self) -> Dict[str, int]:
        """
        全量加載並對資料庫內的所有模組執行三色分級審計
        """
        if not os.path.exists(self.db_path):
            return {"total": 0, "green": 0, "yellow": 0, "red": 0}

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "modules" in data and isinstance(data["modules"], dict):
                    modules = data["modules"]
                elif isinstance(data, dict):
                    modules = data
                else:
                    modules = {}
        except Exception as e:
            logger.error(f"讀取模組表現力資料庫失敗: {e}")
            return {"total": 0, "green": 0, "yellow": 0, "red": 0}

        self.green_modules.clear()
        self.yellow_modules.clear()
        self.red_modules.clear()
        self.module_metadata = modules

        for mod_key, meta in modules.items():
            if not isinstance(meta, dict):
                continue
            tier = self._classify_module_internal(mod_key, meta)
            clean_id = mod_key[:-5] if mod_key.endswith(".json") else mod_key
            if tier == "GREEN":
                self.green_modules.add(mod_key)
                self.green_modules.add(clean_id)
            elif tier == "YELLOW":
                self.yellow_modules.add(mod_key)
                self.yellow_modules.add(clean_id)
            else:
                self.red_modules.add(mod_key)
                self.red_modules.add(clean_id)

        logger.info(
            f"⚡ [Hard Techno 門禁審計完成] 總計: {len(modules)} | "
            f"🟢 GREEN(硬核認證): {len(self.green_modules)} | "
            f"🟡 YELLOW(中性調和): {len(self.yellow_modules)} | "
            f"🔴 RED(嚴格封殺): {len(self.red_modules)}"
        )
        return {
            "total": len(modules),
            "green": len(self.green_modules),
            "yellow": len(self.yellow_modules),
            "red": len(self.red_modules)
        }

    def _classify_module_internal(self, mod_key: str, meta: Dict[str, Any]) -> str:
        clean_key = (mod_key[:-5] if mod_key.endswith(".json") else mod_key).lower()
        name_lower = str(meta.get("name") or mod_key).lower()
        # 0. 測試/佔位/節慶/敏感題材模組 (以完整名稱比對) 一律不得進入正式發行 MV
        if clean_key in HARD_TECHNO_JUNK_MODULES or mod_key.lower() in HARD_TECHNO_JUNK_MODULES or name_lower in HARD_TECHNO_JUNK_MODULES:
            return "RED"
        tags = [str(t).lower() for t in meta.get("tags", [])]
        # 0.5 嚴格封殺帶有 unstable_blackscreen / quarantined 標籤或已隔離的故障模組
        if meta.get("quarantined") or any(t in ("unstable_blackscreen", "quarantined", "broken_shader") for t in tags):
            return "RED"
        desc = str(meta.get("description", "")).lower()
        search_blob = f"{mod_key.lower()} {name_lower} {' '.join(tags)} {desc}"

        # 1. 檢測絕對黑名單 (只要包含花朵、融球、枕頭、粉彩等直接標紅封殺)
        search_blob_l = search_blob.lower()
        for toxic in HARD_TECHNO_TOXIC_BLACKLIST:
            if toxic.lower() in search_blob_l:
                return "RED"

        # 2. 檢測硬核白名單 (包含隧道、線框、網格、雷射、光達、體素等直接標綠)
        for white in HARD_TECHNO_MORPHOLOGY_KEYWORDS:
            if white.lower() in search_blob_l:
                return "GREEN"

        # 3. 預設中性
        return "YELLOW"

    def get_module_tier(self, mod_key: str, meta: Optional[Dict[str, Any]] = None) -> str:
        """
        獲取單一模組的分級狀態 (GREEN / YELLOW / RED)
        """
        if mod_key in self.green_modules:
            return "GREEN"
        if mod_key in self.red_modules:
            return "RED"
        if mod_key in self.yellow_modules:
            return "YELLOW"

        meta_dict = meta or self.module_metadata.get(mod_key, {"name": mod_key})
        tier = self._classify_module_internal(mod_key, meta_dict)
        if tier == "GREEN":
            self.green_modules.add(mod_key)
        elif tier == "RED":
            self.red_modules.add(mod_key)
        else:
            self.yellow_modules.add(mod_key)
        return tier

    def filter_modules_for_hard_techno(self, available_modules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        為 Hard Techno 過濾模組清單：
        1. 徹底剔除 RED 模組。
        2. 優先保留 GREEN 模組（若不足則以 YELLOW 補充）。
        """
        approved = []
        yellows = []
        for m in available_modules:
            mod_k = m.get("_filename_key") or m.get("name") or ""
            tier = self.get_module_tier(mod_k, m)
            if tier == "GREEN":
                m_copy = dict(m)
                m_copy["hard_techno_tier"] = "GREEN"
                approved.append(m_copy)
            elif tier == "YELLOW":
                m_copy = dict(m)
                m_copy["hard_techno_tier"] = "YELLOW"
                yellows.append(m_copy)
            # RED 模組直接拋棄，不進入候選池

        if len(approved) >= 6:
            return approved
        # 若綠色模組偏少，補充黃色中性模組
        return approved + yellows
