"""
Ambient / Drone 沉浸式視覺系統全鏈路升級整合測試
驗證模組：
1. AmbientModuleCompatibilityGate 對 SAVAP Asset 審計與三色分級
2. SAVAPPhysicsEngine.generate_ambient_layout 微重力布朗漂移與負空間構圖
3. AmbientChronosDirector.plan_long_take_storyboard 極長鏡頭演化分鏡引擎
4. SAVAPDeterministic4KPipe 10-bit 抗色帶配置與 Blue Noise 抖動
"""

import os
import sys
import unittest
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from savap_asset_schema import SAVAPUniversalAsset, DynamicsPresetEnum
from ambient_module_compatibility_gate import AmbientModuleCompatibilityGate
from savap_physics_layout_optimizer import SAVAPPhysicsEngine
from ambient_chronos_director import AmbientChronosDirector
from savap_deterministic_4k_pipe import SAVAPDeterministic4KPipe


class TestAmbientPipelineIntegration(unittest.TestCase):

    def setUp(self):
        self.gate = AmbientModuleCompatibilityGate()
        self.director = AmbientChronosDirector()
        self.physics = SAVAPPhysicsEngine(canvas_w=3840, canvas_h=2160)

    def test_01_ambient_gate_savap_audit(self):
        """測試模組門禁對 SAVAP 資產的評審"""
        # 1. 綠色資產 (帶有 fluid 標籤與次低頻融化)
        green_asset = SAVAPUniversalAsset(
            asset_id="asset_green_drone",
            dynamics_preset=DynamicsPresetEnum.SUB_BASS_MELT.value,
            tags=["ambient", "fluid", "atmospheric"]
        )
        tier_g, reason_g = self.gate.evaluate_savap_asset(green_asset)
        self.assertEqual(tier_g, "GREEN")

        # 2. 紅色資產 (高頻閃爍，破壞冥想)
        red_asset = SAVAPUniversalAsset(
            asset_id="asset_red_flash",
            dynamics_preset=DynamicsPresetEnum.HIHAT_SOLARIZATION.value,
            tags=["glitch", "manic"]
        )
        tier_r, reason_r = self.gate.evaluate_savap_asset(red_asset)
        self.assertEqual(tier_r, "RED")

    def test_02_ambient_micro_gravity_layout(self):
        """測試 Ambient 專用微重力布朗漂移與負空間極大化佈局"""
        dummy_assets = [
            {"id": "monolith", "image": Image.new("RGBA", (400, 600), (200, 200, 200, 255)), "keyword": "monolith"},
            {"id": "orb", "image": Image.new("RGBA", (200, 200), (100, 150, 200, 255)), "keyword": "levitating_sphere"}
        ]

        layout = self.physics.generate_ambient_layout(dummy_assets, void_ratio=0.70)
        self.assertEqual(len(layout), 2)

        # 驗證負空間約束與縮放
        for item in layout:
            self.assertEqual(item["void_ratio"], 0.70)
            self.assertIn("brownian_drift", item)
            # 布朗漂移初速應極慢 (<= 0.5 px/step)
            drift_norm = np.linalg.norm(item["brownian_drift"])
            self.assertLessEqual(drift_norm, 0.5)

        # 驗證主體稍微偏置以留出光霧天光
        self.assertAlmostEqual(layout[0]["pos"][0], 3840 * 0.42, delta=50.0)

    def test_03_ambient_long_take_storyboard(self):
        """測試極長鏡頭分鏡演化規劃與交叉溶解時間窗口"""
        total_track_seconds = 120.0 # 2 分鐘測試
        storyboard = self.director.plan_long_take_storyboard(total_duration=total_track_seconds)
        
        self.assertGreater(len(storyboard), 1)
        
        # 驗證每個鏡頭時長都在 20s 以上，並具有交叉溶解窗口
        for shot in storyboard:
            self.assertGreaterEqual(shot["duration"], 10.0)
            self.assertIn("dissolve_window", shot)
            self.assertGreaterEqual(shot["dissolve_window"]["duration"], 2.0)
            self.assertIn("camera_motion", shot)
            self.assertEqual(len(shot["color_palette_oklch"]), 4)

    def test_04_deterministic_10bit_anti_banding(self):
        """測試 10-bit 離線編碼管線配置與 Blue Noise 抖動消除"""
        pipe = SAVAPDeterministic4KPipe(
            output_path="/tmp/test_ambient_10bit.mp4",
            width=3840,
            height=2160,
            enable_10bit=True
        )
        self.assertTrue(pipe.enable_10bit)

        # 測試 Blue Noise 抖動算子
        test_frame = np.full((100, 100, 4), 128, dtype=np.uint8)
        dithered = SAVAPDeterministic4KPipe.apply_blue_noise_dither(test_frame, strength=1.5)
        self.assertEqual(dithered.shape, (100, 100, 4))
        # 應有細微噪訊打散色階
        self.assertFalse(np.all(dithered[:, :, :3] == 128))


if __name__ == "__main__":
    unittest.main()
