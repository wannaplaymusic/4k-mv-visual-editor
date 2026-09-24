import re
import logging

logger = logging.getLogger("VisualStudio.MaestroMetaphorAlchemist")

class MaestroMetaphorAlchemist:
    """
    概念隱喻解構與 4 大語意方向推子 (Metaphor Alchemist & Semantic Steer)
    - 基於 George Lakoff 概念隱喻理論 (CMT) 與意象圖式 (Image Schemas)
    - 將抽象詩意文學（如「荒涼廢土上的孤獨機械」）轉譯為具體的物理運動與幾何邊界
    - 提供 4 大高階語意方向推子 (Chaos, Organic, Aggression, Depth) 進行整體氣質動態調變
    """

    # 核心意象圖式庫 (Image Schemas)
    IMAGE_SCHEMAS = {
        "EXPANSION": {
            "keywords": ["爆裂", "膨脹", "擴散", "超新星", "繁衍", "綻放", "explode", "burst", "bloom"],
            "dynamics": "radial_velocity_positive",
            "bass_multiplier": 1.8,
            "damping_attack": 28.0
        },
        "CONTAINMENT": {
            "keywords": ["封閉", "囚禁", "深海", "牢籠", "虛空", "孤獨", "trap", "cage", "abyss", "solitude"],
            "dynamics": "boundary_reflection_damped",
            "bass_multiplier": 0.9,
            "stroke_contrast": 1.5
        },
        "VERTICALITY": {
            "keywords": ["上升", "沉淪", "墜落", "極光", "天梯", "雨滴", "ascend", "fall", "rain", "aurora"],
            "dynamics": "directional_gravity_flow",
            "y_axis_bias": 1.4
        },
        "FRACTURE": {
            "keywords": ["破碎", "撕裂", "晶體", "故障", "撕扯", "裂紋", "shatter", "crack", "fracture", "glitch"],
            "dynamics": "voronoi_voronoi_split",
            "jitter_factor": 2.2,
            "recommended_shader": "matrix_glitch_mosaic"
        }
    }

    @classmethod
    def deconstruct_metaphor(cls, text_prompt: str) -> dict:
        """
        剖析自然語言中的意象圖式並輸出物理空間指引
        """
        prompt_lower = text_prompt.lower()
        detected_schemas = []

        for schema_id, schema_meta in cls.IMAGE_SCHEMAS.items():
            for kw in schema_meta["keywords"]:
                if kw in prompt_lower:
                    detected_schemas.append((schema_id, schema_meta))
                    break

        if not detected_schemas:
            # 預設包含擴散與垂直圖式
            detected_schemas.append(("EXPANSION", cls.IMAGE_SCHEMAS["EXPANSION"]))

        primary_schema_id, primary_schema = detected_schemas[0]

        return {
            "primary_schema": primary_schema_id,
            "all_schemas": [s[0] for s in detected_schemas],
            "physics_hints": primary_schema,
            "narrative_insight": f"偵測到核心意象圖式【{primary_schema_id}】，將驅動相應的空間拓撲與阻尼曲線"
        }

    @classmethod
    def compute_semantic_modulation(cls, chaos: float, organic: float, aggression: float, depth: float) -> dict:
        """
        4 大語意方向推子映射矩陣 (0.0 ~ 1.0)
        - chaos (幾何混沌度): 影響噪聲尺度、旋轉不規則度、吸引子擾動
        - organic (有機呼吸度): 影響流體平滑度、彈簧阻尼衰減時間、邊緣柔和度
        - aggression (色彩侵略度): 影響重低音爆發倍率、線條對比度、OKLCH 色度飽和
        - depth (光影縱深): 影響 3D 空間焦距縮放、體積神光散射係數
        """
        chaos = max(0.0, min(1.0, chaos))
        organic = max(0.0, min(1.0, organic))
        aggression = max(0.0, min(1.0, aggression))
        depth = max(0.0, min(1.0, depth))

        return {
            # 物理運動映射
            "noise_frequency": float(f"{0.001 + chaos * 0.009:.4f}"),
            "particle_jitter": float(f"{chaos * 3.5:.2f}"),
            "fluid_viscosity": float(f"{0.1 + organic * 0.8:.2f}"),
            "spring_decay_time": float(f"{0.1 + organic * 0.4:.3f}"),
            
            # 音視頻譜衝擊映射
            "bass_power_multiplier": float(f"{0.8 + aggression * 2.2:.2f}"),
            "contrast_boost": float(f"{1.0 + aggression * 0.8:.2f}"),
            
            # 3D 鏡頭與光影映射
            "camera_zoom": float(f"{5.0 + depth * 12.0:.1f}"),
            "volumetric_glow_intensity": float(f"{0.2 + depth * 0.8:.2f}")
        }
