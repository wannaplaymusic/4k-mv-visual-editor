import math
import logging

logger = logging.getLogger("VisualStudio.MaestroAcousticMirror")

class MaestroAcousticMirror:
    """
    聲學情感鏡像神經引擎 (Acoustic-to-VA Neural Mirror)
    - 基於 Russell 情感環狀模型 (Valence-Arousal Circumplex Model)
    - 將客觀物理聲學特徵 (BPM, RMS, 頻譜形心, 和弦調性) 投影至情感座標
    - 自動推算視覺運動速度、色彩對比度、粒子密度與著色器推薦
    """

    QUADRANTS = {
        "Q1_Euphoric": {
            "name": "狂喜振奮 (Euphoric & Exuberant)",
            "desc": "高能量、正向歡愉，適合重拍爆發、節日電音、極限躍動",
            "preferred_topologies": ["curl_noise_fluid", "voronoi_crystalline"],
            "recommended_shaders": ["volumetric_godrays", "chromatic_aberration"],
            "palette_bias": "bright_warm_neon"
        },
        "Q2_Aggressive": {
            "name": "狂暴焦慮 (Aggressive & Frantic)",
            "desc": "高能量、負向壓抑，適合工業重金屬、暗黑故障、緊張撕裂",
            "preferred_topologies": ["lorenz_attractor", "chladni_plate"],
            "recommended_shaders": ["matrix_glitch_mosaic", "chromatic_aberration"],
            "palette_bias": "high_contrast_dark_red"
        },
        "Q3_Melancholic": {
            "name": "憂鬱深邃 (Melancholic & Gloomy)",
            "desc": "低能量、負向低落，適合深海沉潛、荒涼廢土、沉思輓歌",
            "preferred_topologies": ["gyroid_surface", "physarum_slime"],
            "recommended_shaders": ["drone_spectral_fog", "analog_saturation_grain"],
            "palette_bias": "desaturated_cold_blue"
        },
        "Q4_Ethereal": {
            "name": "空靈恬靜 (Ethereal & Serene)",
            "desc": "低能量、正向溫潤，適合宇宙星塵、禪意極簡、冥想氛圍",
            "preferred_topologies": ["curl_noise_fluid", "gyroid_surface"],
            "recommended_shaders": ["aurora_borealis_curtain", "caustic_refraction_flow"],
            "palette_bias": "pastel_luminescent"
        }
    }

    @classmethod
    def project_to_va_space(cls, acoustic_meta: dict) -> dict:
        """
        將聲學特徵投影至 Valence (-1.0 ~ 1.0) 與 Arousal (0.0 ~ 1.0) 空間
        """
        bpm = float(acoustic_meta.get("bpm", 120.0))
        rms = float(acoustic_meta.get("rms_energy", acoustic_meta.get("bass", 0.5)))
        centroid = float(acoustic_meta.get("spectral_centroid", 1500.0))
        is_minor = bool(acoustic_meta.get("is_minor", False))

        # 1. 喚醒度 (Arousal 0.0 ~ 1.0: 平緩 -> 激昂)
        norm_bpm = max(0.0, min(1.0, (bpm - 60.0) / 120.0))  # 60~180 BPM 映射為 0~1
        norm_rms = max(0.0, min(1.0, rms * 1.2))
        norm_centroid = max(0.0, min(1.0, (centroid - 500.0) / 3500.0))
        arousal = float(f"{0.45 * norm_bpm + 0.35 * norm_rms + 0.20 * norm_centroid:.3f}")
        arousal = max(0.05, min(1.0, arousal))

        # 2. 價度 (Valence -1.0 ~ 1.0: 悲傷/沉重 -> 歡快/明朗)
        # 小調和弦與低頻沉重壓向負向，大調與高明亮頻譜偏向正向
        base_valence = -0.35 if is_minor else 0.45
        valence_shift = (norm_centroid - 0.5) * 0.7 + (norm_rms - 0.5) * 0.3
        valence = float(f"{base_valence + valence_shift:.3f}")
        valence = max(-1.0, min(1.0, valence))

        # 3. 判定象限
        if arousal >= 0.5 and valence >= 0.0:
            quadrant_id = "Q1_Euphoric"
        elif arousal >= 0.5 and valence < 0.0:
            quadrant_id = "Q2_Aggressive"
        elif arousal < 0.5 and valence < 0.0:
            quadrant_id = "Q3_Melancholic"
        else:
            quadrant_id = "Q4_Ethereal"

        quadrant_info = cls.QUADRANTS[quadrant_id]

        # 4. 生成具體物理視覺建議
        recommended_physics = {
            "speed_multiplier": float(f"{0.5 + arousal * 1.5:.2f}"),
            "particle_density": int(500 + arousal * 2500),
            "stroke_contrast": float(f"{1.0 + abs(valence) * 1.2:.2f}"),
            "damping_decay": float(f"{0.05 + (1.0 - arousal) * 0.3:.3f}")
        }

        return {
            "arousal": arousal,
            "valence": valence,
            "quadrant": quadrant_id,
            "quadrant_info": quadrant_info,
            "recommended_physics": recommended_physics
        }
