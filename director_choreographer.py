import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from saliency_eyetrace_bridge import SaliencyEyeTraceBridge

logger = logging.getLogger("StandaloneInjector.DirectorChoreographer")

class DirectorChoreographer:
    """
    L2 微觀動態編舞器 (Micro Dynamic Choreographer)
    - 落地好萊塢大師 Walter Murch「Rule of Six」剪輯六法則評估模型
    - 複合張力指數 (Composite Tension Index) 即時計算
    - J-Cut / L-Cut 視聽錯位非對稱剪輯與弱拍切分音 (Syncopated Editing) 調度
    - 生理感知時長約束與動態相機構圖模式 (Framing & Intensity) 智慧指派
    """

    # Walter Murch 剪輯權重矩陣
    W_EMOTION = 0.51
    W_STORY = 0.23
    W_RHYTHM = 0.10
    W_EYE_TRACE = 0.07
    W_PLANAR_2D = 0.05
    W_SPATIAL_3D = 0.04

    def __init__(self, min_shot_sec: float = 1.25, max_shot_sec: float = 18.0):
        self.min_shot_sec = min_shot_sec
        self.max_shot_sec = max_shot_sec

    def evaluate_murch_cut_score(
        self,
        emotion_score: float,
        story_score: float,
        rhythm_score: float,
        eye_trace_score: float,
        planar_score: float = 0.9,
        spatial_score: float = 0.85
    ) -> float:
        """
        計算單一切點的 Walter Murch 加權綜合得分
        """
        return (
            self.W_EMOTION * emotion_score +
            self.W_STORY * story_score +
            self.W_RHYTHM * rhythm_score +
            self.W_EYE_TRACE * eye_trace_score +
            self.W_PLANAR_2D * planar_score +
            self.W_SPATIAL_3D * spatial_score
        )

    def calculate_composite_tension(
        self, 
        section_name: str, 
        bpm: float = 120.0,
        energy_hint: float = 0.5,
        time_pos: float = 0.0,
        duration: float = 180.0
    ) -> float:
        """
        合成音軌複合張力指數 (0.0 ~ 1.0)
        結合曲式結構、BPM 速度因數、時間推進動能與能量提示
        """
        sec = section_name.lower()
        base_tension = 0.35
        if "drop" in sec or "climax" in sec:
            base_tension = 0.95
        elif "build" in sec or "pre" in sec:
            base_tension = 0.75
        elif "chorus" in sec:
            base_tension = 0.82
        elif "verse" in sec:
            base_tension = 0.45
        elif "bridge" in sec:
            base_tension = 0.60
        elif "intro" in sec:
            base_tension = 0.20
        elif "outro" in sec:
            base_tension = 0.15

        # 融入 BPM 影響 (速度越快基礎張力微幅提升)
        bpm_factor = min(0.15, max(-0.1, (bpm - 120.0) / 400.0))
        # 融入全曲進程累積
        progress_factor = math.sin((time_pos / max(1.0, duration)) * math.pi) * 0.08

        tension = base_tension * 0.7 + energy_hint * 0.2 + bpm_factor + progress_factor
        return max(0.05, min(1.0, tension))

    def plan_cinematic_shots(
        self,
        storyboard_sections: List[Dict[str, Any]],
        audio_telemetry: Dict[str, Any],
        assigned_modules: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[float]]:
        """
        依據 L1 概念與音訊特徵，微觀規劃全曲分鏡、轉場、構圖與張力曲線
        """
        bpm = float(audio_telemetry.get("bpm", 120.0))
        total_duration = float(audio_telemetry.get("duration", 180.0))
        beat_duration = 60.0 / max(40.0, bpm)
        bar_duration = beat_duration * 4.0

        shot_list = []
        intensity_curve = []
        prev_centroid = {"cx": 0.5, "cy": 0.45}
        accumulated_time = 0.0

        for idx, sec in enumerate(storyboard_sections):
            sec_name = sec.get("section", "Verse")
            sec_duration = float(sec.get("duration", bar_duration * 4))
            
            assigned = assigned_modules[idx] if idx < len(assigned_modules) else {}
            mod_id = assigned.get("assigned_module_id") or assigned.get("module_name") or "default_module"

            tension = self.calculate_composite_tension(
                section_name=sec_name,
                bpm=bpm,
                energy_hint=assigned.get("target_energy", 0.5),
                time_pos=accumulated_time,
                duration=total_duration
            )

            # J-Cut / L-Cut 錯位剪輯判定
            # 當即將進入 Drop/Chorus 高潮時，啟用 J-Cut 提前 1 拍進入新視覺或預收縮
            is_climax = "drop" in sec_name.lower() or "chorus" in sec_name.lower()
            is_build = "build" in sec_name.lower() or "pre" in sec_name.lower()
            
            cut_offset_sec = 0.0
            cut_style = "standard_cut"
            if is_climax:
                cut_offset_sec = -round(beat_duration, 3)  # 提前 1 拍切入 (J-Cut)
                cut_style = "j_cut_anticipation"
            elif is_build:
                cut_offset_sec = round(beat_duration * 0.5, 3)  # 延遲半拍滲入 (L-Cut)
                cut_style = "l_cut_suspense"

            # 構圖模式動態選擇 (避免高潮單純 fill，引入對位法 Counterpoint)
            # 默認: Drop/Build -> fill, Intro/Outro -> contain
            if "intro" in sec_name.lower() or "outro" in sec_name.lower():
                framing_mode = "contain"
            elif is_climax:
                # 85% 機率填滿衝擊，15% 機率故意使用極簡超寬景 (Extreme Wide Negative Space Counterpoint)
                framing_mode = "fill" if idx % 4 != 0 else "contain"
            else:
                framing_mode = "fill"

            # 視線引導連續性評估
            # 若為 Climax Drop 則啟動反對稱震撼切 (Shock Cut)
            continuity_info = SaliencyEyeTraceBridge.compute_cut_transition_continuity(
                prev_centroid=prev_centroid,
                is_high_tension_drop=is_climax and tension > 0.88
            )

            # 計算 Walter Murch 得分
            murch_score = self.evaluate_murch_cut_score(
                emotion_score=tension,
                story_score=0.88 if is_climax else 0.75,
                rhythm_score=0.92,
                eye_trace_score=continuity_info["continuity_score"]
            )

            # 後製特效強度曲線
            target_fx = round(tension * 0.95, 3)
            intensity_curve.append(target_fx)

            shot_list.append({
                "section_index": idx,
                "section_name": sec_name,
                "start_time": round(accumulated_time, 2),
                "duration": round(sec_duration, 2),
                "assigned_module_id": mod_id,
                "framing_mode": framing_mode,
                "target_fx_intensity": target_fx,
                "transition_style": continuity_info["recommended_transition"],
                "cinematic_meta": {
                    "cut_style": cut_style,
                    "cut_offset_sec": cut_offset_sec,
                    "murch_score": round(murch_score, 3),
                    "composite_tension": round(tension, 3),
                    "camera_lookat_offset": continuity_info["camera_lookat_offset"],
                    "is_shock_cut": continuity_info["is_shock_cut"]
                }
            })

            # 更新質心
            target_c = continuity_info.get("target_centroid", [0.5, 0.5])
            prev_centroid = {"cx": target_c[0], "cy": target_c[1]}
            accumulated_time += sec_duration

        return shot_list, intensity_curve
