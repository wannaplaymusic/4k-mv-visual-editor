# -*- coding: utf-8 -*-
"""
SENTINEL-CHRONOS: Ambient Particle & Fluid Auto-Tagger
------------------------------------------------------
批次掃描 module_expressive_db.json 中的 3,329 個模組，
精準識別粒子 (Particle)、流體 (Fluid)、噪聲波浪 (Perlin/Wave)、星塵 (Stardust) 模組，
自動注入專屬 Ambient/Drone 標籤與自適應調諧參數，供導演系統毫秒級取用。
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("VisualStudio.AmbientTagger")

KEYWORDS = {
    "particle_stardust": ["particle", "stardust", "galaxy", "dust", "star", "cosmic"],
    "fluid_diffusion": ["fluid", "smoke", "cloud", "water", "mist", "flow", "viscous"],
    "topological_wave": ["wave", "ripple", "perlin", "curl", "noise", "mesh", "harmonic"]
}

def tag_existing_modules(db_path: str = "module_expressive_db.json") -> Dict[str, Any]:
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tagged_count = 0
    subgenre_counts = {"particle_stardust": 0, "fluid_diffusion": 0, "topological_wave": 0}

    for mod_id, meta in data.items():
        id_lower = mod_id.lower()
        metaphors = [m.lower() for m in meta.get("symbolic_metaphors", [])]
        combined_text = id_lower + " " + " ".join(metaphors)

        matched_subgenre = None
        for subgenre, kws in KEYWORDS.items():
            if any(k in combined_text for k in kws):
                matched_subgenre = subgenre
                break

        if matched_subgenre:
            dyn = meta.get("dynamics", {})
            v_mean = dyn.get("mean_velocity", 0.5)

            # 速度與阻尼適配計算
            if v_mean < 0.25:
                tier = "GREEN"
                speed_scale = 1.0
            elif v_mean < 0.65:
                tier = "YELLOW"
                speed_scale = 0.05  # 強制 20 倍時間膨脹減速
            else:
                tier = "RED_EXCLUDED"
                speed_scale = 0.02

            # 注入 Ambient 專屬字段
            meta["ambient_drone_compatible"] = (tier in ("GREEN", "YELLOW"))
            meta["ambient_subgenre"] = matched_subgenre
            meta["ambient_tier"] = tier
            meta["ambient_recommended_speed_scale"] = speed_scale
            meta["ambient_desaturation_factor"] = 0.35 if tier == "YELLOW" else 0.0

            if meta["ambient_drone_compatible"]:
                tagged_count += 1
                subgenre_counts[matched_subgenre] += 1

    # 寫回資料庫
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "total_analyzed": len(data),
        "total_ambient_tagged": tagged_count,
        "subgenre_breakdown": subgenre_counts
    }

if __name__ == "__main__":
    result = tag_existing_modules()
    print("Tagging Finished:", json.dumps(result, ensure_ascii=False, indent=2))
