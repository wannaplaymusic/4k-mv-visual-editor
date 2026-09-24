# -*- coding: utf-8 -*-
"""
CINEDANCE 鏡頭編譯系統 (Cinedance Shot Compilation Engine)
融合 Higgsfield CINEDANCE 核心理念之影視級幾何光學編譯器：
1. ShotRiskAuditor: 鏡頭風險審計與自動降級防翻車機制
2. DynamicFOVCompiler: 曲式與張力驅動的水平視場角 (H-FOV) 與 Dolly Zoom 參數求解
3. ElasticSpatialGrounder: NDC 歸一化空間三層景深槽位與彈性拉簧幾何錨定
4. LightTriadSolver: [光源] <--> [主體] <--> [相機] 三元幾何空間光學向量求解
5. CinedanceShotCompiler: 統一調度封裝與雙軌 (即時渲染 / AI 視頻提示詞) 輸出
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("StandaloneInjector.CinedanceCompiler")


class ShotRiskAuditor:
    """
    鏡頭風險審計器 (Shot Risk Auditor)
    靜態分析分鏡參數、運動幅度與光學設定，檢測潛在的模型崩壞或渲染溢出風險
    """
    RISK_THRESHOLD_HIGH = 0.75
    RISK_THRESHOLD_MEDIUM = 0.45

    @classmethod
    def audit_shot_risk(
        cls,
        section_name: str,
        duration: float,
        composite_tension: float,
        camera_motion_speed: float,
        angular_velocity_deg: float,
        fov_deg: float,
        num_subjects: int = 1
    ) -> Dict[str, Any]:
        """
        評估單一分鏡的生成/渲染風險分數 (0.0 ~ 1.0)
        """
        risk_score = 0.0
        risk_flags = []
        mitigation_actions = []

        # 1. 運動衝突審計 (Motion Conflict): 旋轉角速度過大 + 時間短
        if angular_velocity_deg > 60.0 and duration < 2.0:
            risk_score += 0.35
            risk_flags.append("HIGH_ANGULAR_VELOCITY_SHORT_CLIP")
            mitigation_actions.append("Clamp angular velocity to 30 deg/sec or extend shot duration")

        # 2. 劇烈推拉 + 旋轉複合運動
        if camera_motion_speed > 2.0 and angular_velocity_deg > 45.0:
            risk_score += 0.30
            risk_flags.append("COMPOUND_MOTION_OVERLOAD")
            mitigation_actions.append("Decouple compound motion into single-axis linear dolly or pan")

        # 3. 極限視場角畸變 (Extreme FOV Distortion)
        if fov_deg > 110.0:
            risk_score += 0.20
            risk_flags.append("EXTREME_WIDE_FISHEYE_WARP")
            mitigation_actions.append("Apply rectilinear constraint to avoid peripheral texture tearing")
        elif fov_deg < 20.0:
            risk_score += 0.15
            risk_flags.append("ULTRA_TELEPHOTO_DRIFT")
            mitigation_actions.append("Increase micro-stabilization dampening for ultra-narrow FOV")

        # 4. 多主體衝突 (Subject Topology Ambiguity)
        if num_subjects > 2:
            risk_score += 0.25
            risk_flags.append("MULTI_SUBJECT_SPATIAL_AMBIGUITY")
            mitigation_actions.append("Assign distinct NDC depth planes for each subject anchor")

        # 5. 高張力突變風險
        if composite_tension > 0.90 and duration < 1.0:
            risk_score += 0.20
            risk_flags.append("HYPER_TENSION_STROBE_RISK")
            mitigation_actions.append("Insert 1-beat J-Cut anticipation buffer")

        risk_score = min(1.0, risk_score)
        level = "LOW"
        if risk_score >= cls.RISK_THRESHOLD_HIGH:
            level = "HIGH"
        elif risk_score >= cls.RISK_THRESHOLD_MEDIUM:
            level = "MEDIUM"

        return {
            "risk_score": round(risk_score, 3),
            "risk_level": level,
            "risk_flags": risk_flags,
            "mitigation_actions": mitigation_actions,
            "safe_damping_factor": round(max(0.2, 1.0 - risk_score * 0.7), 3),
            "suggest_split_cut": risk_score >= cls.RISK_THRESHOLD_HIGH and duration >= 3.0
        }


class DynamicFOVCompiler:
    """
    動態視場角編譯器 (Dynamic FOV Compiler)
    以水平視場角 (Horizontal Field of View, H-FOV) 取代模糊的毫米焦段
    並提供透視壓縮指數 (Depth Compression) 與 Dolly Zoom 參數求解
    """

    # 曲式標準 FOV 階梯 (度數)
    FOV_LADDER = {
        "intro": (75.0, 95.0),       # 開闊宏大建立環境
        "verse": (38.0, 50.0),       # 自然人眼透視，穩定敘事
        "pre-chorus": (50.0, 70.0),  # 逐漸擴大張力
        "build": (70.0, 90.0),       # 空間拉伸蓄力
        "chorus": (85.0, 105.0),     # 廣角爆發衝擊
        "drop": (95.0, 115.0),       # 極限超廣角 / 魚眼衝擊
        "bridge": (30.0, 42.0),      # 空間收縮親密感
        "solo": (25.0, 35.0),        # 長焦強烈虛化色塊壓縮
        "outro": (70.0, 90.0)        # 緩解沉澱回退
    }

    @classmethod
    def compile_fov(
        cls,
        section_name: str,
        composite_tension: float,
        energy_hint: float = 0.5,
        is_shock_counterpoint: bool = False
    ) -> Dict[str, Any]:
        """
        編譯出精確的 FOV 參數、透視景深壓縮比與光學描述
        """
        sec = section_name.lower()
        matched_range = (45.0, 60.0)
        for key, r in cls.FOV_LADDER.items():
            if key in sec:
                matched_range = r
                break

        min_fov, max_fov = matched_range

        # 反對稱對位法 (Anti-Cinema Counterpoint)
        # 例如在高潮 Drop 時故意使用極端長焦特寫，引發強烈反差張力
        if is_shock_counterpoint and ("drop" in sec or "chorus" in sec):
            target_fov = 28.0 + (1.0 - energy_hint) * 8.0
        else:
            # 正常張力線性調製
            target_fov = min_fov + (max_fov - min_fov) * composite_tension

        target_fov = max(20.0, min(120.0, target_fov))

        # 透視壓縮指數: FOV 越小，背景被壓縮得越扁平 (0.0=無壓縮超廣角, 1.0=極致壓縮長焦)
        depth_compression = max(0.0, min(1.0, (120.0 - target_fov) / 100.0))

        # Dolly Zoom 參數求解:
        # 當張力極高 (Build-up) 且 FOV 劇烈變化時，計算虛擬相機 Z 軸位移以維持前景主體比例
        dolly_active = ("build" in sec or "drop" in sec) and composite_tension > 0.70
        dolly_speed = round(math.sin(composite_tension * math.pi * 0.5) * 1.5, 3) if dolly_active else 0.0

        # 生成 CINEDANCE 標準光學描述文字 (取代 85mm 等玄學詞彙)
        if target_fov >= 95.0:
            optic_desc = f"{round(target_fov)}° ultra-wide rectilinear FOV, deep vanishing perspective lines, edge dynamic stretch"
        elif target_fov >= 70.0:
            optic_desc = f"{round(target_fov)}° wide-angle cinematic perspective, enhanced spatial depth and expansive architecture"
        elif target_fov >= 42.0:
            optic_desc = f"{round(target_fov)}° natural human-eye FOV, balanced planar geometry, zero optical distortion"
        else:
            optic_desc = f"{round(target_fov)}° tight telephoto FOV, extreme optical background compression, flat graphical depth plane"

        return {
            "target_fov_deg": round(target_fov, 2),
            "depth_compression_index": round(depth_compression, 3),
            "dolly_zoom_active": dolly_active,
            "dolly_zoom_velocity": dolly_speed,
            "optical_descriptor": optic_desc
        }


class ElasticSpatialGrounder:
    """
    彈性幾何空間錨定器 (Elastic Spatial Grounder)
    以 NDC (Normalized Device Coordinates, 0.0 ~ 1.0) 坐標系錨定場景
    並以拉簧係數 (Spring-Damper) 隨音樂張力解鎖/收緊空間約束
    """

    @classmethod
    def compute_spatial_anchors(
        cls,
        framing_mode: str = "fill",
        composite_tension: float = 0.5,
        camera_lookat_offset: Tuple[float, float] = (0.0, 0.0)
    ) -> Dict[str, Any]:
        """
        計算場景三層景深槽位 (Foreground, Midground, Background) 的錨點坐標與約束張力
        """
        # 地平線基準線 (Horizon Line): 預設黃金分割 0.618 或中央 0.5
        horizon_y = 0.618 if framing_mode == "contain" else 0.500
        horizon_y += camera_lookat_offset[1] * 0.15
        horizon_y = max(0.2, min(0.8, horizon_y))

        # 主體中景錨點 (Midground Subject Anchor)
        subject_ndc = [
            round(0.50 + camera_lookat_offset[0] * 0.25, 3),
            round(horizon_y - 0.08, 3),
            0.50  # Z-depth (0.0=近裁剪面, 1.0=遠裁剪面)
        ]

        # 彈性拉簧常數 k (Spring Constant):
        # 張力低時 k=1.0 (嚴格空間鎖定); 張力極高 (Drop) 時 k=0.25 (允許粒子與幾何大幅形變散逸)
        spring_k = round(max(0.20, 1.0 - composite_tension * 0.75), 3)

        # 三層景深槽位規劃
        depth_layers = {
            "foreground": {
                "z_range": [0.05, 0.25],
                "content_type": "particles_and_bokeh",
                "motion_amplification": round(1.5 + composite_tension * 0.8, 2)
            },
            "midground": {
                "z_range": [0.35, 0.65],
                "content_type": "primary_subject",
                "anchor_ndc": subject_ndc,
                "spring_stiffness": spring_k
            },
            "background": {
                "z_range": [0.75, 0.98],
                "content_type": "environment_and_skybox",
                "parallax_factor": round(0.15 + (1.0 - spring_k) * 0.25, 2)
            }
        }

        # CINEDANCE 空間語言描述
        spatial_desc = (
            f"Horizon line anchored at Y={round(horizon_y, 2)}; "
            f"Primary subject pinned at NDC ({subject_ndc[0]}, {subject_ndc[1]}) with depth {subject_ndc[2]}; "
            f"Three distinct visual planes with parallax depth separation."
        )

        return {
            "horizon_ndc_y": round(horizon_y, 3),
            "subject_anchor_ndc": subject_ndc,
            "elastic_spring_k": spring_k,
            "depth_layers": depth_layers,
            "spatial_descriptor": spatial_desc
        }


class LightTriadSolver:
    """
    三元空間光影求解器 (Light Triad Solver)
    嚴格計算 [光源] <--> [主體] <--> [相機] 的三維空間向量關係
    可直接供 WebGL/GLSL 著色器消費，亦可編譯為好萊塢級光學提示詞
    """

    @classmethod
    def solve_light_triad(
        cls,
        section_name: str,
        composite_tension: float,
        energy_hint: float = 0.5,
        beat_pulse: float = 0.0
    ) -> Dict[str, Any]:
        """
        求解主光 (Key Light)、輪廓光 (Rim Light)、環境輔光 (Fill Light) 空間向量
        """
        sec = section_name.lower()
        is_climax = "drop" in sec or "chorus" in sec
        is_dark = "intro" in sec or "outro" in sec or "bridge" in sec

        # 1. 主光 (Key Light): 預設主體斜上方 45度
        key_azimuth = 45.0 + math.sin(composite_tension * math.pi) * 30.0
        key_elevation = 35.0 + energy_hint * 25.0
        key_intensity = round(0.8 + energy_hint * 0.8 + beat_pulse * 0.5, 3)

        # 2. 輪廓光 (Rim Light / Kicker): 主體背後 150°~180°，負責勾勒立體邊緣
        rim_azimuth = 175.0 - math.cos(composite_tension * math.pi * 0.5) * 20.0
        rim_elevation = 15.0 + energy_hint * 15.0
        # 高潮時輪廓光極強，製造強烈邊緣光芒 (Edge Silhouette Glow)
        rim_intensity = round(1.2 + (1.5 if is_climax else 0.4) * composite_tension, 3)

        # 3. 輔光 / 環境光 (Fill Light): 填補暗部，色調通常與主光形成冷暖對比
        fill_azimuth = key_azimuth - 120.0
        fill_elevation = 20.0
        fill_intensity = round(0.25 + (0.1 if is_dark else 0.35) * (1.0 - composite_tension * 0.5), 3)

        # 計算三維單位向量 (以主體為原點 [0,0,0], X=右, Y=上, Z=相機方向)
        def spherical_to_cartesian(azimuth_deg: float, elevation_deg: float) -> List[float]:
            az_rad = math.radians(azimuth_deg)
            el_rad = math.radians(elevation_deg)
            x = math.sin(az_rad) * math.cos(el_rad)
            y = math.sin(el_rad)
            z = math.cos(az_rad) * math.cos(el_rad)
            return [round(x, 4), round(y, 4), round(z, 4)]

        key_dir = spherical_to_cartesian(key_azimuth, key_elevation)
        rim_dir = spherical_to_cartesian(rim_azimuth, rim_elevation)
        fill_dir = spherical_to_cartesian(fill_azimuth, fill_elevation)

        # CINEDANCE 光影三元語意描述
        light_desc = (
            f"Key light from {round(key_azimuth)}° azimuth at {round(key_elevation)}° elevation (intensity {key_intensity}); "
            f"Harsh razor-sharp rim light from {round(rim_azimuth)}° behind subject creating crisp silhouette separation; "
            f"Soft diffused fill light (intensity {fill_intensity}) maintaining shadow contour detail."
        )

        return {
            "key_light": {
                "azimuth_deg": round(key_azimuth, 1),
                "elevation_deg": round(key_elevation, 1),
                "intensity": key_intensity,
                "direction_vector": key_dir
            },
            "rim_light": {
                "azimuth_deg": round(rim_azimuth, 1),
                "elevation_deg": round(rim_elevation, 1),
                "intensity": rim_intensity,
                "direction_vector": rim_dir
            },
            "fill_light": {
                "azimuth_deg": round(fill_azimuth, 1),
                "elevation_deg": round(fill_elevation, 1),
                "intensity": fill_intensity,
                "direction_vector": fill_dir
            },
            "lighting_descriptor": light_desc
        }


class CinedanceShotCompiler:
    """
    CINEDANCE 鏡頭編譯總成 (Shot Compilation Master Engine)
    統一調度四大模組，為每個分鏡生成影視級光學元數據與高確定性 AI 提示詞
    """

    @classmethod
    def compile_cinematic_shot(
        cls,
        section_name: str,
        duration: float,
        composite_tension: float,
        framing_mode: str = "fill",
        camera_lookat_offset: Tuple[float, float] = (0.0, 0.0),
        energy_hint: float = 0.5,
        is_shock_counterpoint: bool = False
    ) -> Dict[str, Any]:
        """
        編譯出完整的 CINEDANCE 分鏡光學元數據 (cinedance_optical_meta)
        """
        # 1. 編譯動態視場角與景深透視
        fov_meta = DynamicFOVCompiler.compile_fov(
            section_name=section_name,
            composite_tension=composite_tension,
            energy_hint=energy_hint,
            is_shock_counterpoint=is_shock_counterpoint
        )

        # 2. 空間幾何錨定
        spatial_meta = ElasticSpatialGrounder.compute_spatial_anchors(
            framing_mode=framing_mode,
            composite_tension=composite_tension,
            camera_lookat_offset=camera_lookat_offset
        )

        # 3. 三元空間光影求解
        lighting_meta = LightTriadSolver.solve_light_triad(
            section_name=section_name,
            composite_tension=composite_tension,
            energy_hint=energy_hint
        )

        # 4. 靜態鏡頭風險審計
        # 預設角速度隨張力提升，以檢測動態過載
        simulated_angular_spd = composite_tension * (70.0 if "drop" in section_name.lower() else 35.0)
        risk_meta = ShotRiskAuditor.audit_shot_risk(
            section_name=section_name,
            duration=duration,
            composite_tension=composite_tension,
            camera_motion_speed=1.0 + composite_tension * 1.2,
            angular_velocity_deg=simulated_angular_spd,
            fov_deg=fov_meta["target_fov_deg"],
            num_subjects=1
        )

        # 5. 編譯合成 CINEDANCE 15-Block 規範級 AI 提示詞 (用於對外導出)
        compiled_ai_prompt = (
            f"Cinematic shot, {section_name.upper()} sequence. "
            f"Optics: {fov_meta['optical_descriptor']}. "
            f"Geometry: {spatial_meta['spatial_descriptor']} "
            f"Lighting: {lighting_meta['lighting_descriptor']} "
            f"Motion: Smooth continuous motion, temporal stability factor {risk_meta['safe_damping_factor']}."
        )

        return {
            "target_fov_deg": fov_meta["target_fov_deg"],
            "depth_compression_index": fov_meta["depth_compression_index"],
            "dolly_zoom_active": fov_meta["dolly_zoom_active"],
            "dolly_zoom_velocity": fov_meta["dolly_zoom_velocity"],
            "horizon_ndc_y": spatial_meta["horizon_ndc_y"],
            "subject_anchor_ndc": spatial_meta["subject_anchor_ndc"],
            "elastic_spring_k": spatial_meta["elastic_spring_k"],
            "depth_layers": spatial_meta["depth_layers"],
            "light_triad": {
                "key_light": lighting_meta["key_light"],
                "rim_light": lighting_meta["rim_light"],
                "fill_light": lighting_meta["fill_light"]
            },
            "risk_audit": risk_meta,
            "compiled_prompt_block": compiled_ai_prompt
        }
