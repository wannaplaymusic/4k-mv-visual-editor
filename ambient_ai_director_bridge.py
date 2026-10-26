"""
SENTINEL-CHRONOS: Ambient AI Auteur Director Bridge
依據《AI 導演系統介入 Ambient 視覺模組挑選與變化操控架構計劃書》實作：

三大核心機制：
1. 三層視覺複調策展器 (Tri-Layer Visual Polyphony Curation):
   - Layer 1: 大氣光場底層 (Turrell Ganzfeld 32-D Shader)
   - Layer 2: 空間物質流體中層 (Fluid / Topological Wave)
   - Layer 3: 懸浮星塵粒子頂層 (Ethereal Particulate / Stardust)
2. 長時窗自相似矩陣 (SSM Novelty Curve) 慢電影長鏡頭剪輯大腦 (20s~60s 鏡頭，6s~10s 同胚融鏡)
3. 32 維全態物理參數自適應動態編舞引擎 (Dynamic Choreography)
"""

import os
import math
import random
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from ambient_chronos_director import AmbientChronosDirector
from ambient_module_compatibility_gate import AmbientModuleCompatibilityGate
from savap_ambient_modulation_matrix import SAVAPAmbientModulationBus, Ambient32DParameters

logger = logging.getLogger("VisualStudio.AmbientAIDirector")


@dataclass
class VisualPolyphonyTrio:
    """三層視覺複調組合封包"""
    layer1_atmospheric: str = "ambient_ganzfeld_fog"  # 光場底層
    layer2_material_fluid: str = "HobbyCurve_1"       # 物質流體中層
    layer3_particulate: str = "Satellites"            # 懸浮粒子頂層
    motif_id: str = "turrell_mercury"                 # 144 組合母題
    blend_weights: Tuple[float, float, float] = (1.0, 0.65, 0.45) # 混合權重


class AmbientAcousticSSMAnalyzer:
    """
    長時窗聲學自相似矩陣 (SSM) 與質地新穎度分析器
    拒絕傳統瞬態敲擊卡點，以 16s~32s 滑動視窗識別質地演進奇異點
    """
    def __init__(self, window_size_seconds: float = 24.0):
        self.window_size = window_size_seconds
        self.feature_history: List[Tuple[float, Dict[str, float]]] = [] # (timestamp, features)

    def record_feature(self, timestamp: float, features: Dict[str, float]):
        self.feature_history.append((timestamp, features))
        # 裁剪歷史保持在當前時間前 60 秒以內
        cutoff = timestamp - 60.0
        while self.feature_history and self.feature_history[0][0] < cutoff:
            self.feature_history.pop(0)

    def compute_novelty(self, current_time: float) -> float:
        """
        計算長時窗質地演變新穎度 (Novelty Score: 0.0 ~ 1.0)
        """
        if len(self.feature_history) < 20:
            return 0.1

        # 提取前半窗與後半窗的頻譜特徵均值
        mid_time = current_time - (self.window_size * 0.5)
        early_window = [f for t, f in self.feature_history if t < mid_time]
        late_window = [f for t, f in self.feature_history if t >= mid_time]

        if not early_window or not late_window:
            return 0.1

        early_centroid = sum(f.get("spectral_centroid", 800.0) for f in early_window) / len(early_window)
        late_centroid = sum(f.get("spectral_centroid", 800.0) for f in late_window) / len(late_window)
        centroid_drift = abs(late_centroid - early_centroid) / 1500.0

        early_bass = sum(f.get("bass", 0.2) for f in early_window) / len(early_window)
        late_bass = sum(f.get("bass", 0.2) for f in late_window) / len(late_window)
        bass_shift = abs(late_bass - early_bass) * 1.5

        novelty = min(1.0, centroid_drift * 0.6 + bass_shift * 0.4)
        return round(novelty, 3)


class AmbientCognitiveDirectorBridge:
    """
    AI 導演作者系統橋接器 (Auteur Ambient Director)
    全面接管視覺模組的挑選與 32 維參數的動態編舞演化
    """

    def __init__(self):
        self.chronos_director = AmbientChronosDirector()
        self.compatibility_gate = AmbientModuleCompatibilityGate()
        self.modulation_bus = SAVAPAmbientModulationBus()
        self.ssm_analyzer = AmbientAcousticSSMAnalyzer()

        self.current_trio = VisualPolyphonyTrio()
        self.shot_start_time = 0.0
        self.current_shot_duration = 35.0
        self.in_cross_dissolve = False
        self.dissolve_start_time = 0.0
        self.dissolve_duration = 8.0

        # 心流編舞狀態變數
        self.curation_history: List[str] = []
        self.director_intent_log: str = "🎬 [AI導演] 系統初始化就緒，守護純淨冥想心流。"

        # 初次自適應策展
        self._curate_next_polyphony_trio(seed=42108542)

    def _curate_next_polyphony_trio(self, seed: int = 0) -> VisualPolyphonyTrio:
        """
        基於上下文多臂賭博機 (Contextual Bandit) 自動策展三層複調模組組合
        """
        green_modules = self.compatibility_gate.get_native_ambient_roster(limit=100)

        # 依子類型分類
        fluids = []
        particulates = []
        for mod_id in green_modules:
            meta = self.compatibility_gate.module_metadata.get(mod_id, {})
            subg = meta.get("ambient_subgenre", "")
            name = mod_id.lower()
            if "fluid" in subg or "wave" in name or "flow" in name or "curve" in name:
                fluids.append(mod_id)
            elif "particle" in subg or "satellite" in name or "star" in name or "dust" in name:
                particulates.append(mod_id)

        # 隨機種子確定性選取
        fluids = fluids or ["HobbyCurve_1", "thecurvesofyou"]
        particulates = particulates or ["Satellites", "PencilTrace3B"]

        selected_fluid = fluids[seed % len(fluids)]
        selected_particulate = particulates[(seed >> 4) % len(particulates)]

        # 從 144 母題中篩選
        num_motifs = len(self.chronos_director.CONTEMPLATIVE_MOTIFS)
        selected_motif = self.chronos_director.CONTEMPLATIVE_MOTIFS[(seed >> 8) % num_motifs]

        self.current_trio = VisualPolyphonyTrio(
            layer1_atmospheric="ambient_ganzfeld_fog",
            layer2_material_fluid=selected_fluid,
            layer3_particulate=selected_particulate,
            motif_id=selected_motif["id"],
            blend_weights=(1.0, 0.65, 0.45)
        )

        self.curation_history.append(self.current_trio.motif_id)
        self.director_intent_log = (
            f"🎬 [AI導演策展] 新分鏡確立：【{selected_motif['title']}】\n"
            f"  └─ 底層: 全域體積光場 (Ganzfeld 32-D)\n"
            f"  └─ 中層: 空間流形 [{selected_fluid}]\n"
            f"  └─ 頂層: 懸浮星塵 [{selected_particulate}]"
        )
        logger.info(self.director_intent_log)
        return self.current_trio

    def tick_director_loop(
        self,
        current_time: float,
        dt: float,
        audio_features: Dict[str, Any],
        audio_seed: int = 42108542
    ) -> Dict[str, Any]:
        """
        AI 導演主循環每幀調度計算：
        1. 聲學自相似矩陣紀錄與新穎度計算
        2. 宏觀長鏡頭生命週期與自動策展
        3. 32 維物理參數微動態編舞 (Choreography)
        """
        # 1. 記錄特徵
        self.ssm_analyzer.record_feature(current_time, audio_features)
        novelty = self.ssm_analyzer.compute_novelty(current_time)

        # 2. 宏觀長鏡頭生命週期管理
        elapsed_in_shot = current_time - self.shot_start_time

        if not self.in_cross_dissolve:
            # 當鏡頭已持續 25 秒以上，且出現質地演進奇異點 (novelty > 0.40) 或超時強制輪轉
            if (elapsed_in_shot >= self.current_shot_duration and novelty > 0.35) or (elapsed_in_shot >= self.current_shot_duration * 1.5):
                self.in_cross_dissolve = True
                self.dissolve_start_time = current_time
                self.dissolve_duration = 8.0 # 8 秒深度同胚融鏡
                
                # 計算新種子並策展下一個三層複調
                new_seed = (audio_seed ^ int(current_time * 100)) & 0xFFFFFFFF
                self._curate_next_polyphony_trio(seed=new_seed)

        # 同胚交叉溶解進度計算
        dissolve_progress = 0.0
        if self.in_cross_dissolve:
            d_elapsed = current_time - self.dissolve_start_time
            if d_elapsed >= self.dissolve_duration:
                self.in_cross_dissolve = False
                self.shot_start_time = current_time
                dissolve_progress = 1.0
            else:
                d_norm = d_elapsed / self.dissolve_duration
                # Smoothstep 慢速過渡
                dissolve_progress = d_norm * d_norm * (3.0 - 2.0 * d_norm)

        # 3. 32 維微觀物理參數動態編舞 (Choreography)
        mod_params = self.modulation_bus.update_from_telemetry(
            audio_telemetry=audio_features,
            dt=dt,
            breathing_rate=0.10
        )

        # 導演微觀戲劇介入：
        # A. 光學邊界消融臨界點 (長鏡頭進入第 30~45 秒時，邊界逐漸融化)
        if elapsed_in_shot > 25.0:
            dissolution_boost = min(0.35, (elapsed_in_shot - 25.0) * 0.02)
            mod_params.u_anisotropyG = min(0.85, mod_params.u_anisotropyG + dissolution_boost)
            mod_params.u_scatteringAlbedo = min(0.98, mod_params.u_scatteringAlbedo + dissolution_boost * 0.5)

        # B. 空間流形非平衡演化 (依長鏡頭時間演進平滑調製空間扭曲)
        warp_orbit = math.sin(current_time * 0.05) * 0.05
        mod_params.u_domainWarpAmp = max(0.04, min(0.40, mod_params.u_domainWarpAmp + warp_orbit))

        # C. 當正在融鏡時，提高柯西色散與大氣消光，製造夢境光暈
        if self.in_cross_dissolve:
            mod_params.u_cauchyDispersion = max(0.06, mod_params.u_cauchyDispersion * 1.5)
            mod_params.u_extinctionBeta = max(2.5, mod_params.u_extinctionBeta * 1.3)

        uniforms = mod_params.to_webgl_uniforms()

        # 當前母題調色盤
        active_motif = next(
            (m for m in self.chronos_director.CONTEMPLATIVE_MOTIFS if m["id"] == self.current_trio.motif_id),
            self.chronos_director.CONTEMPLATIVE_MOTIFS[0]
        )
        unique_palette_oklch = self.chronos_director.derive_track_unique_palette(
            base_palette=active_motif["oklch_palette"],
            audio_seed=audio_seed
        )
        temp_m = dict(active_motif)
        temp_m["oklch_palette"] = unique_palette_oklch
        rgb_palette = self.chronos_director._convert_motif_to_rgb(temp_m)
        flat_palette = []
        for c in rgb_palette:
            flat_palette.extend([float(x) for x in c])
        uniforms["palette"] = flat_palette

        hex_palette = [
            self.chronos_director._oklch_to_hex(c[0], c[1], c[2])
            for c in unique_palette_oklch
        ]
        color_policy = self.chronos_director.get_effective_color_policy(
            module_name_or_id=self.current_trio.layer2_material_fluid,
            shot_palette_hex=hex_palette
        )

        return {
            "director_active": True,
            "polyphony_trio": {
                "layer1_atmospheric": self.current_trio.layer1_atmospheric,
                "layer2_material_fluid": self.current_trio.layer2_material_fluid,
                "layer3_particulate": self.current_trio.layer3_particulate,
                "motif_id": self.current_trio.motif_id,
                "motif_title": active_motif["title"],
                "blend_weights": self.current_trio.blend_weights
            },
            "shot_state": {
                "elapsed_in_shot": round(elapsed_in_shot, 2),
                "current_shot_duration": self.current_shot_duration,
                "in_cross_dissolve": self.in_cross_dissolve,
                "dissolve_progress": round(dissolve_progress, 4),
                "acoustic_novelty": round(novelty, 3)
            },
            "intent_log": self.director_intent_log,
            "uniforms_32d": uniforms,
            "ambient_color_policy": color_policy,
            "palette_hex": hex_palette
        }

    def set_module_palette_override(
        self,
        module_name_or_id: str,
        palette_hex: List[str],
        chroma_limit: float = 0.065,
        mode: str = "clamp_and_blend"
    ):
        """支援外部臨時改動個別模組配色"""
        self.chronos_director.set_module_palette_override(
            module_name_or_id=module_name_or_id,
            palette_hex=palette_hex,
            chroma_limit=chroma_limit,
            mode=mode
        )
        self.director_intent_log = f"🎨 [AI導演] 已臨時覆寫模組 [{module_name_or_id}] 配色為 Ambient 專屬調色盤。"
