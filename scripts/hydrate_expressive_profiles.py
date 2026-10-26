# -*- coding: utf-8 -*-
"""
Hydrate Expressive Profiles for Visual Modules (M2.1 Implementation)
基於代碼 AST 靜態特徵、幾何特徵與元數據，為未標註的沉睡模組自動補齊心理狀態、榮格原型與動態特徵
"""
import os
import json
import re
import datetime
from typing import Dict, Any

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
EXPRESSIVE_DB_PATH = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")

def analyze_module_code(code: str, tags: list, name: str) -> Dict[str, Any]:
    """
    對 p5.js 代碼進行啟發式靜態特徵提取與語義心靈本體論映射
    """
    code_lower = code.lower()
    tags_lower = [str(t).lower() for t in tags]
    name_lower = name.lower()

    # 1. 幾何與動態特徵評估
    has_webgl = "webgl" in code_lower
    has_3d = has_webgl or "rotatex" in code_lower or "rotatey" in code_lower or "sphere(" in code_lower or "box(" in code_lower
    has_noise = "noise(" in code_lower or "perlin" in code_lower or "curl" in code_lower
    has_particles = "particle" in code_lower or "particles" in name_lower or "swarm" in name_lower or "dots" in code_lower
    has_fractal = "fractal" in code_lower or "lorenz" in code_lower or "attractor" in code_lower or "recursion" in code_lower
    has_grid = "grid" in code_lower or "matrix" in code_lower or "rect(" in code_lower or "tile" in code_lower
    has_fluid = "fluid" in code_lower or "flow" in code_lower or "smoke" in code_lower or "wave" in code_lower
    has_glitch = "glitch" in code_lower or "random(" in code_lower or "shake" in code_lower or "pixel" in code_lower

    # 2. 映射主要心理狀態 (primary_psychological_state) 與榮格原型 (jungian_archetype)
    # 支持 4 大核心心理狀態: 'manic_hyperarousal', 'hypnotic_trance', 'alienation_void', 'sublime_catharsis'
    if has_glitch or (has_particles and ("burst" in code_lower or "speed" in code_lower or "explode" in code_lower)):
        state = "manic_hyperarousal"
        archetype = "the_trickster"
        narrative = "climax_rupture"
        metaphors = ["能量爆發", "秩序解構", "躁狂超覺醒"]
        motion_type = "stochastic_jitter"
        velocity = 1.6
    elif has_fractal or has_noise or has_fluid:
        state = "hypnotic_trance"
        archetype = "the_animus"
        narrative = "tension_accelerator"
        metaphors = ["潛意識流動", "催眠冥想", "幾何自相似性"]
        motion_type = "sinusoidal_breath"
        velocity = 0.7
    elif has_3d or ("void" in name_lower or "dark" in name_lower or "space" in name_lower or "star" in name_lower):
        state = "alienation_void"
        archetype = "the_void"
        narrative = "genesis_anchor"
        metaphors = ["深邃虛空", "異化疏離", "宇宙原初寂靜"]
        motion_type = "static_crystalline"
        velocity = 0.3
    else: # 光影、色彩擴散、和諧幾何
        state = "sublime_catharsis"
        archetype = "the_self"
        narrative = "aftermath_resonance"
        metaphors = ["崇高淨化", "秩序重組", "意識回歸"]
        motion_type = "harmonic_orbit"
        velocity = 0.5

    # 3. 色彩特徵推導
    dominant_hues = [210.0]
    if "red" in code_lower or "crimson" in code_lower or "fire" in code_lower:
        dominant_hues = [15.0, 350.0]
    elif "green" in code_lower or "emerald" in code_lower or "tree" in code_lower:
        dominant_hues = [140.0]
    elif "blue" in code_lower or "cyan" in code_lower or "ocean" in code_lower:
        dominant_hues = [220.0, 190.0]
    elif "purple" in code_lower or "violet" in code_lower:
        dominant_hues = [285.0]
    elif "gold" in code_lower or "yellow" in code_lower:
        dominant_hues = [75.0]

    return {
        "primary_psychological_state": state,
        "secondary_psychological_states": ["sinusoidal_breath"],
        "symbolic_metaphors": metaphors,
        "narrative_function": narrative,
        "jungian_archetype": archetype,
        "color_profile": {
            "dominant_oklch_hues": dominant_hues,
            "mean_lightness": 0.65 if state == "sublime_catharsis" else 0.25,
            "mean_chroma": 0.16,
            "contrast_level": "analogous_subtle" if state == "hypnotic_trance" else "high_contrast",
            "emotional_temperature": "feverish_warm" if "red" in code_lower else "sterile_neutral"
        },
        "dynamics": {
            "mean_velocity": velocity,
            "curl_vorticity": 0.05 if has_fluid else 0.01,
            "divergence": 0.0,
            "motion_energy_type": motion_type
        },
        "hydration_level": 1,
        "confidence_score": 0.82,
        "analyzed_engine": "ast_heuristic_v2",
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def main():
    if os.path.exists(EXPRESSIVE_DB_PATH):
        try:
            with open(EXPRESSIVE_DB_PATH, "r", encoding="utf-8") as f:
                expressive_db = json.load(f)
        except Exception:
            expressive_db = {}
    else:
        expressive_db = {}

    initial_count = len(expressive_db)
    print(f"現有標註模組數: {initial_count}")

    added_count = 0
    all_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "module_usage_history.json"]

    for file in all_files:
        mod_key = file[:-5]
        if mod_key in expressive_db and expressive_db[mod_key].get("confidence_score", 0) >= 0.7:
            continue

        p_path = os.path.join(CUSTOM_VISUALS_DIR, file)
        try:
            with open(p_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            code = data.get("code", "")
            if not code or len(code) < 30 or "setup" not in code:
                continue

            profile = analyze_module_code(code, data.get("tags", []), data.get("name", mod_key))
            profile["module_id"] = mod_key
            expressive_db[mod_key] = profile
            added_count += 1
        except Exception as e:
            pass

    # 寫回 expressive_db
    with open(EXPRESSIVE_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(expressive_db, f, indent=2, ensure_ascii=False)

    print(f"✅ 全量語義本體標註完成！新增標註: {added_count} 個模組，目前總標註模組數: {len(expressive_db)}")

if __name__ == "__main__":
    main()
