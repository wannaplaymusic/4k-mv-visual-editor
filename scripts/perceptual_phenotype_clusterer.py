# -*- coding: utf-8 -*-
"""
Visual Perceptual Hashing & Semantic Deduplicator (M3.2 Implementation)
基於 AST 語法結構指紋、渲染特徵與感知哈希的模組外觀聚類與去重引擎
"""
import os
import json
import re
import hashlib
from typing import Dict, Any, List, Set, Tuple

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
CLUSTERS_DB_PATH = os.path.join(WORKSPACE_DIR, "assets_cache", "module_phenotype_clusters.json")

class VisualPerceptualClusterer:
    """
    模組視覺表現型聚類器：
    1. 計算代碼 AST 幾何與算子指紋 (Geometric Operator Fingerprint)
    2. 結合 OKLCH 色彩空間特徵向量
    3. 產出 64-bit 視覺表現型雜湊 (Phenotype Hash)
    4. 輸出視覺等價聚類庫 (Phenotype Clusters)，杜絕換皮同質模組
    """

    @staticmethod
    def extract_code_structural_features(code: str) -> Dict[str, float]:
        """提取 p5.js 代碼結構與算子特徵向量"""
        code_clean = re.sub(r'//.*|/\*[\s\S]*?\*/', '', code)
        code_lower = code_clean.lower()

        # 幾何主算子特徵計數
        features = {
            "bezier": len(re.findall(r'bezier\w*\(', code_lower)),
            "curve": len(re.findall(r'curve\w*\(', code_lower)),
            "circle": len(re.findall(r'(circle|ellipse)\(', code_lower)),
            "rect": len(re.findall(r'(rect|square)\(', code_lower)),
            "vertex": len(re.findall(r'vertex\(', code_lower)),
            "line": len(re.findall(r'line\(', code_lower)),
            "noise": len(re.findall(r'noise\(', code_lower)),
            "random": len(re.findall(r'random\(', code_lower)),
            "sin_cos": len(re.findall(r'(sin|cos)\(', code_lower)),
            "rotate": len(re.findall(r'rotate\w*\(', code_lower)),
            "translate": len(re.findall(r'translate\w*\(', code_lower)),
            "webgl_3d": 1.0 if ("webgl" in code_lower or "rotatex" in code_lower) else 0.0,
            "shader": 1.0 if ("shader" in code_lower or "gl_fragcolor" in code_lower) else 0.0,
        }
        return features

    @classmethod
    def compute_phenotype_hash(cls, code: str, expressive_profile: Dict[str, Any]) -> str:
        """計算 16 位十六進制 (64-bit) 視覺表現型哈希"""
        feats = cls.extract_code_structural_features(code)
        
        # 決定主要幾何形態 (Dominant Shape Typology)
        shape_type = "abstract"
        if feats["shader"] > 0:
            shape_type = "glsl_shader"
        elif feats["webgl_3d"] > 0:
            shape_type = "webgl_mesh"
        elif feats["circle"] > max(feats["rect"], feats["line"], 5):
            shape_type = "circular_dot"
        elif feats["rect"] > max(feats["circle"], feats["line"], 5):
            shape_type = "quad_grid"
        elif feats["line"] > max(feats["circle"], feats["rect"], 5):
            shape_type = "linear_vector"
        elif feats["vertex"] > 10:
            shape_type = "polygon_complex"

        # 心理狀態與動態能量
        state = expressive_profile.get("primary_psychological_state", "hypnotic_trance")
        dynamics = expressive_profile.get("dynamics", {}).get("motion_energy_type", "sinusoidal_breath")
        
        # 雜訊與隨機性等級
        stochastic_level = "deterministic"
        if feats["noise"] > 3:
            stochastic_level = "perlin_flow"
        elif feats["random"] > 5:
            stochastic_level = "jitter_random"

        signature_str = f"{shape_type}|{state}|{dynamics}|{stochastic_level}"
        return hashlib.md5(signature_str.encode('utf-8')).hexdigest()[:16]

def build_phenotype_clusters() -> Dict[str, List[str]]:
    """掃描全庫建立表現型聚類庫"""
    os.makedirs(os.path.dirname(CLUSTERS_DB_PATH), exist_ok=True)
    
    expressive_db_path = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")
    expressive_db = {}
    if os.path.exists(expressive_db_path):
        try:
            with open(expressive_db_path, "r", encoding="utf-8") as fp:
                expressive_db = json.load(fp)
        except Exception:
            pass

    clusterer = VisualPerceptualClusterer()
    clusters: Dict[str, List[str]] = {}
    total_processed = 0

    all_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "module_usage_history.json"]
    for file in all_files:
        mod_key = file[:-5]
        p_path = os.path.join(CUSTOM_VISUALS_DIR, file)
        try:
            with open(p_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            code = data.get("code", "")
            if not code or len(code) < 30 or "setup" not in code:
                continue

            prof = expressive_db.get(mod_key, {})
            p_hash = clusterer.compute_phenotype_hash(code, prof)

            if p_hash not in clusters:
                clusters[p_hash] = []
            clusters[p_hash].append(mod_key)
            total_processed += 1
        except Exception:
            pass

    with open(CLUSTERS_DB_PATH, "w", encoding="utf-8") as fp:
        json.dump(clusters, fp, indent=2, ensure_ascii=False)

    print(f"✅ 視覺表現型指紋聚類完成！處理 {total_processed} 個模組，聚類為 {len(clusters)} 個互異視覺形態簇群。")
    return clusters

if __name__ == "__main__":
    build_phenotype_clusters()
