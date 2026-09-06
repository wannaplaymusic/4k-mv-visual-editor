import math
import random
from PIL import Image

class MultiElementSceneOrchestrator:
    """
    超過 3~10 個超現實元素的空間拓撲與動態分流調度器
    支援：垂直圖騰堆疊 (Totem)、天體引力軌道群 (Orbital)、深度星系矩陣 (Constellation)
    """
    def __init__(self, canvas_w=1280, canvas_h=720):
        self.cw = canvas_w
        self.ch = canvas_h

    def orchestrate(self, asset_list: list, topology_mode="auto") -> dict:
        n = len(asset_list)
        if n == 0:
            return {}

        # 1. 自動依數量決定拓撲模式
        if topology_mode == "auto":
            if n <= 4:
                topology_mode = "totem"      # 垂直圖騰堆疊
            elif n <= 7:
                topology_mode = "orbital"    # 天體衛星軌道
            else:
                topology_mode = "constellation" # 矩陣散布

        # 2. 指定第 1 個（佔比最大者）為核心主體 (Hero Anchor)
        hero = asset_list[0]
        orchestrated_scene = {
            "topology": topology_mode,
            "elements": []
        }

        # 核心主體固定綁定 Kick 與低頻
        orchestrated_scene["elements"].append({
            "id": hero["id"],
            "role": "hero",
            "pos": [self.cw * 0.5, self.ch * 0.6],
            "scale": 1.0,
            "z_depth": 0.4,
            "audio_channel": "kick_and_bass",
            "motion_type": "squash_and_bounce"
        })

        remaining_assets = asset_list[1:]

        # 3. 根據拓撲模式排布其餘次要物件
        if topology_mode == "totem":
            # 垂直圖騰堆疊：Y 軸依序向上延伸
            current_y = self.ch * 0.45
            for idx, item in enumerate(remaining_assets):
                y_offset = current_y - (idx * 110)
                orchestrated_scene["elements"].append({
                    "id": item["id"],
                    "role": "stacked_part",
                    "pos": [self.cw * 0.5 + math.sin(idx) * 20, y_offset],
                    "scale": max(0.4, 0.9 - idx * 0.15),
                    "z_depth": 0.45 + idx * 0.05,
                    "audio_channel": "mid_freq" if idx % 2 == 0 else "high_freq",
                    "motion_type": "pendulum_swing"
                })

        elif topology_mode == "orbital":
            # 天體軌道：環繞主體公轉
            audio_bands = ["low_mid", "mid_freq", "high_mid", "hihat_treble"]
            for idx, item in enumerate(remaining_assets):
                orbit_r = 160 + (idx * 55) # 遞增軌道半徑
                initial_angle = (2 * math.pi / max(1, len(remaining_assets))) * idx
                orchestrated_scene["elements"].append({
                    "id": item["id"],
                    "role": "satellite",
                    "center": [self.cw * 0.5, self.ch * 0.55],
                    "orbit_radius": orbit_r,
                    "angle_offset": initial_angle,
                    "orbit_speed": 0.01 + (0.005 * (idx + 1)),
                    "scale": random.uniform(0.45, 0.8),
                    "z_depth": 0.6 + (idx * 0.05),
                    "audio_channel": audio_bands[idx % len(audio_bands)],
                    "motion_type": "elliptical_orbit"
                })

        elif topology_mode == "constellation":
            # 深度星系矩陣：泊松分佈散布於不同景深
            for idx, item in enumerate(remaining_assets):
                z = random.uniform(0.2, 0.9)
                scale_inv = (1.0 - z) * 1.5 # 越近越大，越遠越小
                orchestrated_scene["elements"].append({
                    "id": item["id"],
                    "role": "floating_debris",
                    "pos": [random.uniform(100, self.cw - 100), random.uniform(80, self.ch - 80)],
                    "scale": scale_inv,
                    "z_depth": z,
                    "audio_channel": "percussive_burst",
                    "motion_type": "levitation_drift"
                })

        return orchestrated_scene
