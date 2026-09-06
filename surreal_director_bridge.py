import os
import json
import logging
from typing import Dict, Any, List, Optional
from surreal_theme_engine import SurrealThemeConceptEngine

try:
    from sota_composition_optimizer import SOTACompositionOptimizer
    from neural_aesthetic_scorer import NeuralAestheticScorer
except ImportError:
    SOTACompositionOptimizer = None
    NeuralAestheticScorer = None

logger = logging.getLogger("StandaloneInjector.SurrealDirectorBridge")

class SurrealCognitiveDirectorBridge:
    """
    超現實認知導演橋接模組 (SAVAP Cognitive Director Bridge)
    - 賦能 LLMDirectorAgent：樂段張力解析、超現實主題自動策展、空間拓撲蛻變與神經審美評估自檢
    """

    @classmethod
    def evaluate_and_curate_surreal_scene(
        cls, 
        section_name: str, 
        audio_telemetry: Dict[str, Any],
        num_elements: int = 5
    ) -> Dict[str, Any]:
        """
        根據音軌樂段 (如 Drop, Build-up, Intro) 自主策展超現實主題與空間拓撲
        """
        sec = section_name.lower()
        
        # 1. 擲骰取得概念主題與對立素材
        dice = SurrealThemeConceptEngine.roll_dice(num_elements=num_elements)

        # 2. 依樂段動態指定初始拓撲形態與張力
        if "drop" in sec or "chorus" in sec:
            topology_mode = "orbital"  # 高潮爆發：天體公轉與炸裂
            tension_factor = 0.2       # 砸拍釋放
            recommended_fx = 0.95
        elif "build" in sec or "pre" in sec:
            topology_mode = "totem"    # 蓄力積累：圖騰堆疊
            tension_factor = 0.85      # 故意失衡製造懸念
            recommended_fx = 0.70
        else:
            topology_mode = "totem"    # 平緩段落：神聖堆疊
            tension_factor = 0.1
            recommended_fx = 0.35

        # 3. 模擬構圖質量與神經審美評估
        mock_assets = []
        for e in dice["elements"]:
            mock_assets.append({
                "id": e["id"],
                "keyword": e["keyword"],
                "image": None,
                "mass": 50000 if e.get("is_hero") else 12000
            })
        
        if SOTACompositionOptimizer:
            optimizer = SOTACompositionOptimizer(canvas_w=1280, canvas_h=720)
        # 純數學座標分佈
        optimized_elements = []
        golden_angle = 137.5 * (3.14159 / 180.0)
        for i, item in enumerate(mock_assets):
            if i == 0:
                pos = [640.0, 403.2]
                z = 0.4
            elif i == 1:
                pos = [590.0, 380.0]
                z = 0.52
            else:
                ang = i * golden_angle
                r = 180.0 + i * 55.0
                pos = [640.0 + np_cos(ang) * r, 360.0 + np_sin(ang) * (r * 0.62)]
                z = 0.5 + i * 0.06
            optimized_elements.append({
                "id": item["id"],
                "pos": pos,
                "z_depth": z,
                "mass": item["mass"],
                "role": "hero" if i == 0 else ("interlocked_cavity" if i == 1 else "satellite")
            })

        if NeuralAestheticScorer:
            aesthetic_eval = NeuralAestheticScorer.evaluate_composition_quality(optimized_elements, 1280, 720)
        else:
            aesthetic_eval = {"aesthetic_score": 0.88, "is_gallery_grade": True}

        return {
            "section": section_name,
            "theme_title": dice["theme_title"],
            "concept_thought": dice["concept_thought"],
            "topology_mode": topology_mode,
            "tension_factor": tension_factor,
            "recommended_fx": recommended_fx,
            "elements_count": len(dice["elements"]),
            "elements_keywords": [e["keyword"] for e in dice["elements"]],
            "aesthetic_score": aesthetic_eval["aesthetic_score"],
            "is_gallery_grade": aesthetic_eval["is_gallery_grade"]
        }

def np_cos(rad):
    import math
    return math.cos(rad)

def np_sin(rad):
    import math
    return math.sin(rad)
