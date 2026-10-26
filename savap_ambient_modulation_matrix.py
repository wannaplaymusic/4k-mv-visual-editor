"""
SAVAP (Surreal-AudioVisual Asset Pipeline) 32-D Audiovisual Micro-Modulation Matrix
依據《Ambient & Drone 音視微觀參數調製矩陣：極致互動強化計劃書》實作：

包含 6 大物理與感知維度、共 32 個微觀著色器調製參數：
1. 空間幾何與高維流形 (Manifold & Warping, 6 維)
2. 體積光學與大氣光場 (Volumetric Optics, 6 維)
3. 反應擴散與非平衡自組織 (Reaction-Diffusion, 5 維)
4. 物質光學與光譜色散 (Material Dispersion, 5 維)
5. 時間非線性與彈道滯後 (Temporal Hysteresis, 5 維)
6. 神經感知與知覺微動 (Psychophysics, 5 維)
"""

import math
import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("SAVAP.ModulationMatrix")


@dataclass
class BallisticSmoother:
    """
    非對稱彈道濾波器 (Asymmetric Ballistic Envelope Follower)
    具有獨立的 Attack (上升) 與 Release (釋放) 時間常數，
    防止生硬的同頻抖動，營造大自然潮汐般的滯後呼吸感。
    """
    current_value: float = 0.0
    attack_tau: float = 0.8    # 秒 (上升阻尼常數)
    release_tau: float = 8.0   # 秒 (釋放長時衰減常數)

    def step(self, target: float, dt: float) -> float:
        dt = max(0.001, min(0.1, dt))
        if target > self.current_value:
            # 上升過程
            alpha = 1.0 - math.exp(-dt / max(0.01, self.attack_tau))
        else:
            # 釋放過程 (長時緩慢回落)
            alpha = 1.0 - math.exp(-dt / max(0.01, self.release_tau))

        self.current_value += alpha * (target - self.current_value)
        return self.current_value


@dataclass
class Ambient32DParameters:
    """32 維全態音視微觀參數數據封包"""

    # ── 1. 空間幾何與高維流形 (6 維) ──
    u_domainWarpAmp: float = 0.12        # 座標領域扭曲振幅 (0.0 ~ 0.5)
    u_domainWarpFreq: float = 1.5        # 座標空間擾動頻率 (0.5 ~ 6.0)
    u_sdfSmoothMinK: float = 0.35        # SDF 拓撲融解黏滯係數 (0.05 ~ 1.0)
    u_fbmOctaves: float = 4.0            # 分形噪聲迭代維度 (2.0 ~ 7.0)
    u_fractalFoldAngle: float = 0.785    # 空間多面體鏡面折疊角度 (弧度)
    u_manifoldCurvature: float = 0.08    # 仿射流形曲率 (-0.5 ~ 0.5)

    # ── 2. 體積光學與大氣光場 (6 維) ──
    u_anisotropyG: float = 0.35          # Henyey-Greenstein 各向異性因子 (-0.8 ~ 0.8)
    u_extinctionBeta: float = 1.85       # 大氣指數消光係數 (0.2 ~ 5.0)
    u_scatteringAlbedo: float = 0.82     # 單次散射反照率 (0.1 ~ 0.99)
    u_stepJitterStrength: float = 0.08   # 隨機光學步進抖動量 (0.0 ~ 0.25)
    u_opticalThickness: float = 1.2      # 介質光學厚度 (0.1 ~ 4.0)
    u_volumetricPhaseShift: float = 0.05 # 雙目立體光相延遲角 (0.0 ~ 0.3)

    # ── 3. 反應擴散與非平衡自組織 (5 維) ──
    u_rdFeedRate: float = 0.037          # Gray-Scott 進料率 F (0.01 ~ 0.08)
    u_rdKillRate: float = 0.060          # Gray-Scott 消亡率 k (0.04 ~ 0.07)
    u_rdDiffusionRatio: float = 0.5      # 介質擴散速率比 (0.1 ~ 0.9)
    u_vorticityConfinement: float = 0.25 # 渦流局域鎖定強度 (0.0 ~ 1.0)
    u_nonequilibriumTension: float = 0.45# 界面表面張力 (0.1 ~ 1.0)

    # ── 4. 物質光學與光譜色散 (5 維) ──
    u_cauchyDispersion: float = 0.045    # 柯西色散彩虹折射係數 (0.0 ~ 0.15)
    u_subsurfaceDepth: float = 0.32      # 次表面散射透光深度 (0.05 ~ 1.0)
    u_fresnelExponent: float = 3.2       # 菲涅爾掠射角輝光指數 (1.0 ~ 6.0)
    u_anisotropicRoughness: float = 0.4  # 各向異性金屬拉絲粗糙度 (0.1 ~ 0.9)
    u_retroReflectiveGain: float = 0.15  # 微觀逆反射銀鹽增益 (0.0 ~ 0.6)

    # ── 5. 時間非線性與彈道滯後 (5 維) ──
    u_ballisticAttack: float = 0.6       # 彈道上升時間常數 (秒)
    u_ballisticRelease: float = 12.0     # 彈道釋放時間常數 (秒)
    u_phaseHysteresis: float = 0.18      # 磁滯迴線相位延遲 (0.0 ~ 0.5)
    u_temporalDilationRate: float = 0.05 # 時間膨脹流動係數 (0.01 ~ 0.2)
    u_memoryFeedbackGain: float = 0.75   # 歷史幀幽靈拖尾反饋 (0.0 ~ 0.95)

    # ── 6. 神經感知與知覺微動 (5 維) ──
    u_antiTroxlerRate: float = 0.33      # 防視網膜疲勞微眼跳頻率 (Hz)
    u_oklchChromaClamp: float = 0.10     # 感知等距色度上限 (0.02 ~ 0.15)
    u_perceptualEntropy: float = 1.8     # 畫面香農資訊熵平衡因子 (1.2 ~ 2.5)
    u_subconsciousJitter: float = 0.015  # 次感知微觀浮動振幅 (0.005 ~ 0.05)
    u_dissolutionThreshold: float = 0.65 # 意識邊界消融臨界點 (0.1 ~ 1.0)

    def to_dict(self) -> Dict[str, float]:
        """轉為字典格式"""
        return asdict(self)

    def to_webgl_uniforms(self) -> Dict[str, float]:
        """封裝為純 WebGL Float Uniforms 映射字典"""
        return {k: float(v) for k, v in asdict(self).items()}


class SAVAPAmbientModulationBus:
    """
    32 維音視微觀調製匯流排 (Audiovisual Modulation Bus)
    負責接收聲學微特徵，透過非對稱彈道濾波與非線性曲線，
    實時驅動並輸出 32 維全態 Uniforms。
    """

    def __init__(self):
        # 為主要聲學通道配置獨立的彈道平滑器
        self.smooth_sub_rumble = BallisticSmoother(current_value=0.2, attack_tau=0.5, release_tau=10.0)
        self.smooth_spectral_centroid = BallisticSmoother(current_value=800.0, attack_tau=1.2, release_tau=14.0)
        self.smooth_timbral_flux = BallisticSmoother(current_value=0.1, attack_tau=0.4, release_tau=6.0)
        self.smooth_spectral_flatness = BallisticSmoother(current_value=0.2, attack_tau=1.5, release_tau=12.0)
        self.smooth_harmonic_tension = BallisticSmoother(current_value=0.3, attack_tau=0.8, release_tau=8.0)

        self.params = Ambient32DParameters()
        self.accumulated_phase = 0.0

    def update_from_telemetry(
        self,
        audio_telemetry: Dict[str, Any],
        dt: float = 0.0166,
        breathing_rate: float = 0.1
    ) -> Ambient32DParameters:
        """
        輸入原始聲學遙測數據與時間步長 dt，計算並更新 32 維參數
        """
        dt = max(0.001, min(0.1, dt))
        self.accumulated_phase += dt * (2.0 * math.pi * breathing_rate)

        # 1. 提取並平滑聲學特徵
        raw_sub = float(audio_telemetry.get("sub_bass", audio_telemetry.get("bass", 0.2)))
        raw_centroid = float(audio_telemetry.get("spectral_centroid", 800.0))
        raw_flux = float(audio_telemetry.get("spectral_flux", 0.1))
        raw_flatness = float(audio_telemetry.get("spectral_flatness", 0.2))
        raw_tension = float(audio_telemetry.get("tension", 0.3))

        sub = self.smooth_sub_rumble.step(raw_sub, dt)
        centroid = self.smooth_spectral_centroid.step(raw_centroid, dt)
        flux = self.smooth_timbral_flux.step(raw_flux, dt)
        flatness = self.smooth_spectral_flatness.step(raw_flatness, dt)
        tension = self.smooth_harmonic_tension.step(raw_tension, dt)

        # 慢速呼吸正弦波 (0.05 ~ 0.2 Hz)
        breath_wave = 0.5 + 0.5 * math.sin(self.accumulated_phase)

        # ── 2. 非線性映射：空間幾何與高維流形 (6 維) ──
        # Sub-bass 驅動空間領域扭曲振幅
        self.params.u_domainWarpAmp = round(0.05 + (sub * 0.28) + (breath_wave * 0.04), 4)
        # 音色通量驅動空間擾動頻率
        self.params.u_domainWarpFreq = round(1.0 + (flux * 3.5), 4)
        # 和弦緊張度反向控制流形融解黏滯度 (越放鬆越有機融解)
        self.params.u_sdfSmoothMinK = round(0.15 + (1.0 - tension) * 0.45, 4)
        # 頻譜平坦度控制分形維度
        self.params.u_fbmOctaves = round(3.0 + (flatness * 3.0), 2)
        # 空間折疊角隨呼吸與次低頻慢速漂移
        self.params.u_fractalFoldAngle = round(0.5 + (sub * 0.4) + (breath_wave * 0.2), 4)
        self.params.u_manifoldCurvature = round(-0.15 + (sub * 0.35), 4)

        # ── 3. 非線性映射：體積光學與大氣光場 (6 維) ──
        # 頻譜質心 (聲音明暗) 控制各向異性因子 g
        norm_centroid = max(0.0, min(1.0, (centroid - 200.0) / 3000.0))
        self.params.u_anisotropyG = round(-0.3 + (norm_centroid * 0.9), 4)
        # 次低頻能量增加大氣消光濃度
        self.params.u_extinctionBeta = round(1.2 + (sub * 2.5), 4)
        # 高頻空氣感提升反照率
        self.params.u_scatteringAlbedo = round(0.70 + (norm_centroid * 0.25), 4)
        # 隨機光學步進抖動量
        self.params.u_stepJitterStrength = round(0.05 + (flatness * 0.12), 4)
        # 光學厚度
        self.params.u_opticalThickness = round(0.8 + (tension * 2.0), 4)
        self.params.u_volumetricPhaseShift = round(0.02 + (flux * 0.15), 4)

        # ── 4. 非線性映射：反應擴散 (5 維) ──
        # 進料率 F 與消亡率 k (控制在 Gray-Scott 混沌相變邊緣)
        self.params.u_rdFeedRate = round(0.030 + (flux * 0.025), 5)
        self.params.u_rdKillRate = round(0.058 + (sub * 0.008), 5)
        self.params.u_rdDiffusionRatio = round(0.40 + (breath_wave * 0.25), 4)
        self.params.u_vorticityConfinement = round(0.1 + (sub * 0.5), 4)
        self.params.u_nonequilibriumTension = round(0.2 + (tension * 0.6), 4)

        # ── 5. 非線性映射：物質光學與光譜色散 (5 維) ──
        # 音色瞬態通量激發柯西色散彩虹分光
        self.params.u_cauchyDispersion = round(0.02 + (flux * 0.08), 4)
        # 中頻溫潤感控制次表面散射深度
        self.params.u_subsurfaceDepth = round(0.20 + (breath_wave * 0.40), 4)
        self.params.u_fresnelExponent = round(2.0 + (tension * 3.0), 2)
        self.params.u_anisotropicRoughness = round(0.25 + (flatness * 0.45), 4)
        self.params.u_retroReflectiveGain = round(0.08 + (sub * 0.25), 4)

        # ── 6. 非線性映射：時間與神經感知 (10 維) ──
        self.params.u_ballisticAttack = 0.5
        self.params.u_ballisticRelease = 10.0
        self.params.u_phaseHysteresis = round(0.10 + (sub * 0.20), 4)
        self.params.u_temporalDilationRate = round(0.03 + (breath_wave * 0.05), 4)
        self.params.u_memoryFeedbackGain = round(0.70 + (breath_wave * 0.18), 4)

        self.params.u_antiTroxlerRate = 0.33 # 0.33Hz 生理恆定震顫
        self.params.u_oklchChromaClamp = 0.10 # 恆定冥想色度鉗制
        self.params.u_perceptualEntropy = round(1.4 + (flatness * 0.8), 2)
        self.params.u_subconsciousJitter = round(0.008 + (flux * 0.02), 4)
        self.params.u_dissolutionThreshold = round(0.50 + (breath_wave * 0.35), 4)

        return self.params
