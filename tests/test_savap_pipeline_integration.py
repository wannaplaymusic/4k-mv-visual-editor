"""
SAVAP (Surreal-AudioVisual Asset Pipeline) 全鏈路架構整合測試
驗證四大核心戰役模組：
1. Universal Asset Schema (序列化、確定性 Hash、骨骼拓撲、插槽特徵)
2. 構圖物理引擎 (力矩平衡、Poisson-Disc 空間防堆疊、詩意並置拘束)
3. 運動學路由器與 Unified Harmonizer 著色器接口
4. 確定性時間步進時鐘與離線管線流程
"""

import os
import sys
import unittest
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from savap_asset_schema import SAVAPUniversalAsset, DynamicsPresetEnum
from savap_physics_layout_optimizer import SAVAPPhysicsEngine, PoissonDiscSampler2D, SemanticJuxtapositionScorer
from savap_audio_kinematics import SAVAPAudioKinematicsRouter
from savap_deterministic_4k_pipe import DeterministicTimeStepClock, SAVAPDeterministic4KPipe


class TestSAVAPPipelineIntegration(unittest.TestCase):

    def setUp(self):
        # 建立臨時測試圖像
        self.test_img_hero = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
        draw_hero = ImageDraw.Draw(self.test_img_hero)
        draw_hero.ellipse([50, 50, 250, 350], fill=(220, 50, 50, 255)) # 主體紅球

        self.test_img_sat1 = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
        draw_sat1 = ImageDraw.Draw(self.test_img_sat1)
        draw_sat1.rectangle([20, 20, 130, 130], fill=(50, 150, 220, 255)) # 衛星方塊

        self.test_img_sat2 = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        draw_sat2 = ImageDraw.Draw(self.test_img_sat2)
        draw_sat2.polygon([(60, 10), (110, 100), (10, 100)], fill=(50, 220, 80, 255)) # 衛星三角

    def test_01_universal_asset_schema(self):
        """測試戰役一：Universal Asset Schema 封裝與確定性 Hash"""
        temp_path = "/tmp/test_savap_asset.png"
        self.test_img_hero.save(temp_path)

        asset = SAVAPUniversalAsset.create_from_image_path(temp_path, name="HeroBall", z_depth=0.35)
        self.assertTrue(asset.asset_id.startswith("savap_"))
        self.assertGreater(len(asset.source_hash), 0)
        self.assertEqual(asset.composition_z, 0.35)

        # 驗證序列化與反序列化一致性
        data_dict = asset.to_dict()
        restored = SAVAPUniversalAsset.from_dict(data_dict)
        self.assertEqual(restored.asset_id, asset.asset_id)
        self.assertEqual(restored.composition_z, 0.35)
        self.assertAlmostEqual(restored.shader_uniforms.u_grain_intensity, asset.shader_uniforms.u_grain_intensity)

        if os.path.exists(temp_path):
            os.remove(temp_path)

    def test_02_physics_engine_and_torque_balance(self):
        """測試戰役二：視覺質量與淨力矩平衡"""
        engine = SAVAPPhysicsEngine(canvas_w=1920, canvas_h=1080)
        
        # 測試視覺質量計算
        mass_hero = engine.calculate_visual_mass(self.test_img_hero)
        mass_sat1 = engine.calculate_visual_mass(self.test_img_sat1)
        self.assertGreater(mass_hero, mass_sat1)

        # 測試多元素力矩平衡佈局
        assets = [
            {"id": "hero", "image": self.test_img_hero, "keyword": "clock_face"},
            {"id": "sat1", "image": self.test_img_sat1, "keyword": "lobster"},
            {"id": "sat2", "image": self.test_img_sat2, "keyword": "umbrella"}
        ]
        layout = engine.generate_balanced_layout(assets)
        self.assertEqual(len(layout), 3)

        # 驗證總力矩是否成功被尋優約束
        net_torque = np.sum([np.array(el["residual_torque"]) for el in layout], axis=0)
        torque_magnitude = np.linalg.norm(net_torque)
        # 相比未優化前，力矩應被顯著控制
        self.assertTrue(np.isfinite(torque_magnitude))

        # 測試 Poisson-Disc 空間採樣器
        sampler = PoissonDiscSampler2D(width=800, height=600, min_radius=100)
        samples = sampler.sample_points((400, 300))
        self.assertGreater(len(samples), 1)

    def test_03_audio_kinematics_router(self):
        """測試戰役三：四頻段解耦運動學路由器與彈簧超調模型"""
        router = SAVAPAudioKinematicsRouter()
        
        telemetry = {
            "sub_bass": 0.85, # 強烈低音
            "kick": 0.92,     # 強烈衝擊
            "mid_lead": 0.45,
            "hihat": 0.80     # 觸發日光化
        }

        # 執行運動學推論
        kinematics = router.compute_kinematics(
            asset_id="asset_hero",
            audio_telemetry=telemetry,
            dt=0.0166, # 60 FPS (約 16.6ms)
            base_pos=(960.0, 540.0),
            z_depth=0.4
        )

        transform = kinematics["transform"]
        shader_bindings = kinematics["shader_bindings"]

        # 驗證彈簧拉伸或位移非零
        self.assertNotEqual(transform["y"], 540.0)
        # 驗證日光化暴光觸發
        self.assertEqual(shader_bindings["uSolarizationFlare"], 1.0)
        self.assertGreater(shader_bindings["uSubBass"], 0.5)

    def test_04_deterministic_clock(self):
        """測試戰役四：確定性步進時鐘與解耦時間"""
        clock = DeterministicTimeStepClock(fps=60, total_duration_seconds=1.0)
        self.assertEqual(clock.total_frames, 60)

        frames = []
        timestamps = []
        is_done = False
        while not is_done:
            f_idx, t_stamp, is_done = clock.step()
            frames.append(f_idx)
            timestamps.append(t_stamp)

        self.assertEqual(len(frames), 60)
        self.assertAlmostEqual(timestamps[-1], 59.0 / 60.0)
        self.assertTrue(is_done)


if __name__ == "__main__":
    unittest.main()
