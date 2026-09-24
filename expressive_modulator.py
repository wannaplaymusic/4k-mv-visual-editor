# -*- coding: utf-8 -*-
"""
SENTINEL: Expressive Physiological Modulator
彈道生理阻尼濾波調變器 (Ballistic Asymmetric Attack/Release Dynamic Filter)
- 快充慢放 (Attack 25ms / Release 350ms)，將狂暴高頻音訊轉化為具備電影感心跳呼吸的動態
- 雙曲正切軟飽和 (Tanh Soft Saturation)，杜絕生硬突變與光敏性癲癇抽搐
- 計算標準心靈著色器參數: u_tension, u_chaos, u_sublime, u_dissolution
"""

import math
import time
from typing import Dict, Any, Optional

class ExpressiveModulator:
    def __init__(
        self,
        attack_time_sec: float = 0.025,   # 衝擊響應 25ms
        release_time_sec: float = 0.350,  # 有機釋放 350ms
        sample_rate: float = 60.0         # 預設 60 FPS
    ):
        self.attack_alpha = 1.0 - math.exp(-1.0 / (attack_time_sec * sample_rate))
        self.release_alpha = 1.0 - math.exp(-1.0 / (release_time_sec * sample_rate))
        
        # 濾波內部狀態暫存
        self._filtered_bass = 0.0
        self._filtered_energy = 0.0
        self._filtered_tension = 0.0
        self._last_update_time = time.time()

    def filter_signal(self, current_val: float, prev_filtered: float) -> float:
        """ 非對稱彈道濾波單步推進 """
        if current_val > prev_filtered:
            # 快充 (Attack)
            return prev_filtered + self.attack_alpha * (current_val - prev_filtered)
        else:
            # 慢放 (Release)
            return prev_filtered + self.release_alpha * (current_val - prev_filtered)

    def update_expressive_uniforms(
        self,
        raw_bass: float,
        raw_energy: float,
        section_tension_base: float = 0.5,
        section_progress: float = 0.0,
        is_climax_or_drop: bool = False
    ) -> Dict[str, float]:
        """
        計算單一時間步的電影級心靈參數
        回傳可在著色器/p5.js 中直接消費的 Uniforms 字典 (0.0 ~ 1.0)
        """
        # 1. 彈道非對稱平滑
        self._filtered_bass = self.filter_signal(max(0.0, min(1.0, raw_bass)), self._filtered_bass)
        self._filtered_energy = self.filter_signal(max(0.0, min(1.0, raw_energy)), self._filtered_energy)

        # 2. 複合張力指數 (結合樂段基礎張力與當前低音動態)
        raw_tension = section_tension_base * 0.6 + self._filtered_bass * 0.4
        self._filtered_tension = self.filter_signal(raw_tension, self._filtered_tension)

        # 3. 雙曲正切軟飽和 (Tanh Soft Saturation)
        u_tension = math.tanh(self._filtered_tension * 1.5)
        
        # 4. 混亂熵值 (u_chaos: 在高張力與衝擊下被激發，低能量時維持有機微噪)
        chaos_drive = abs(self._filtered_bass - self._filtered_energy) * 1.2
        if is_climax_or_drop:
            chaos_drive += 0.35
        u_chaos = max(0.02, min(1.0, math.tanh(chaos_drive * 1.4)))

        # 5. 崇高昇華感 (u_sublime: 在樂段後段高能量時達到頂峰，控制 Bloom 輝光與邊緣散射)
        sublime_curve = math.sin(section_progress * math.pi) * self._filtered_energy
        u_sublime = max(0.0, min(1.0, math.tanh(sublime_curve * 1.6)))

        # 6. 餘韻消解度 (u_dissolution: 分鏡結束前最後 15% 時間線性增長，用於模組褪色消融)
        if section_progress > 0.85:
            dissolution_t = (section_progress - 0.85) / 0.15
            u_dissolution = max(0.0, min(1.0, dissolution_t ** 1.5))
        else:
            u_dissolution = 0.0

        return {
            "u_tension": round(float(u_tension), 4),
            "u_chaos": round(float(u_chaos), 4),
            "u_sublime": round(float(u_sublime), 4),
            "u_dissolution": round(float(u_dissolution), 4)
        }
