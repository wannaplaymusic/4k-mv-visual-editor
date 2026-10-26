"""
SAVAP (Surreal-AudioVisual Asset Pipeline) Audio-Reactive Kinematics Engine
對齊 Google Antigravity SAVAP Technical Blueprint 第 8 頁規範：

頻段運動學解耦 (Frequency Decoupling):
1. Sub-Bass (20-60Hz)   -> 驅動 Simplex 液態融化 (Dali Liquid Melting)
2. Low-Mid / Kick       -> 觸發彈簧超調偶戲 (Spring Overshoot Puppetry)
3. Mid Lead (1-4kHz)    -> 驅動天體公轉與軌道角速度 (Orbital Rotation)
4. Hi-Hat (8kHz+)       -> 觸發日光化負片閃爍 (Solarization Flares) 與微粒子
"""

import math
from typing import Dict, Any, Tuple, List
from dataclasses import dataclass


@dataclass
class SpringOvershootState:
    """二階欠阻尼彈簧模型 (Second-Order Underdamped Spring System)"""
    position: float = 0.0
    velocity: float = 0.0
    target: float = 0.0
    stiffness: float = 240.0   # 彈性係數 k
    damping: float = 14.0      # 阻尼係數 c (低阻尼以產生過衝 overshoot)
    mass: float = 1.0          # 質量 m

    def update(self, dt: float) -> float:
        """歐拉/半隱式步進更新"""
        dt = min(0.05, max(0.001, dt))
        displacement = self.position - self.target
        spring_force = -self.stiffness * displacement
        damping_force = -self.damping * self.velocity
        total_force = spring_force + damping_force
        acceleration = total_force / max(0.1, self.mass)

        self.velocity += acceleration * dt
        self.position += self.velocity * dt
        return self.position

    def trigger_impulse(self, kick_energy: float):
        """Kick 突發衝量激勵"""
        self.velocity += kick_energy * 45.0


class SAVAPAudioKinematicsRouter:
    """
    音視頻運動學多頻段路由器
    """
    def __init__(self):
        # 為不同關節或物件維護彈簧實例
        self.spring_puppets: Dict[str, SpringOvershootState] = {}
        self.orbit_phases: Dict[str, float] = {}

    def get_or_create_spring(self, asset_id: str) -> SpringOvershootState:
        if asset_id not in self.spring_puppets:
            self.spring_puppets[asset_id] = SpringOvershootState()
        return self.spring_puppets[asset_id]

    def compute_kinematics(
        self,
        asset_id: str,
        audio_telemetry: Dict[str, float],
        dt: float,
        base_pos: Tuple[float, float] = (0.0, 0.0),
        z_depth: float = 0.4
    ) -> Dict[str, Any]:
        """
        輸入四頻段遙測訊號，計算該資產的即時運動學矩陣與 Shader Uniforms
        """
        sub_bass = float(audio_telemetry.get("sub_bass", 0.0))    # 20-60Hz
        kick = float(audio_telemetry.get("kick", 0.0))            # Low-Mid
        mid_lead = float(audio_telemetry.get("mid_lead", 0.0))    # 1-4kHz
        hihat = float(audio_telemetry.get("hihat", 0.0))          # 8kHz+

        # 1. Low-Mid / Kick 彈簧超調 (Puppetry Jump & Limb Snap)
        spring = self.get_or_create_spring(asset_id)
        if kick > 0.45:
            spring.trigger_impulse(kick)
        spring_offset_y = spring.update(dt)

        # 2. Mid Lead (1-4kHz) 軌道天體公轉角速度
        if asset_id not in self.orbit_phases:
            self.orbit_phases[asset_id] = 0.0
        orbit_speed = 0.4 + (mid_lead * 2.2)
        self.orbit_phases[asset_id] += orbit_speed * dt
        current_orbit_angle = self.orbit_phases[asset_id]

        # 3. Sub-Bass 液態融化強度
        melt_amplitude = math.pow(sub_bass, 1.4) * 1.2

        # 4. Hi-Hat 日光化閃光觸發
        solarization_flare = 1.0 if hihat > 0.75 else 0.0

        # 計算綜合空間偏移
        offset_x = math.cos(current_orbit_angle) * (15.0 * mid_lead)
        offset_y = -spring_offset_y + math.sin(current_orbit_angle) * (8.0 * mid_lead)

        return {
            "asset_id": asset_id,
            "transform": {
                "x": base_pos[0] + offset_x,
                "y": base_pos[1] + offset_y,
                "rotation": math.sin(current_orbit_angle * 0.5) * 8.0, # 度
                "scale_y_stretch": 1.0 + (spring.velocity * 0.005)     # 彈簧伸展變形
            },
            "shader_bindings": {
                "uSubBass": float(melt_amplitude),
                "uKick": float(kick),
                "uMidLead": float(mid_lead),
                "uHiHat": float(hihat),
                "uDepthZ": float(z_depth),
                "uSolarizationFlare": float(solarization_flare)
            }
        }
