import os
import unittest
import tempfile
from PIL import Image
import numpy as np

from visual_studio_core import (
    ScenarioMaestro,
    MaestroAcousticMirror,
    MaestroTasteProfiler,
    MaestroMetaphorAlchemist,
    MaestroVisionDecompiler,
    MaestroAmbientMuse
)

class TestMaestroV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.maestro = ScenarioMaestro(workspace_dir=self.temp_dir)

    def test_acoustic_mirror(self):
        # 1. 激昂音樂 (140 BPM, high RMS, high centroid)
        track_fast = {"bpm": 140.0, "rms_energy": 0.8, "spectral_centroid": 3200.0, "is_minor": False}
        res_fast = MaestroAcousticMirror.project_to_va_space(track_fast)
        self.assertGreater(res_fast["arousal"], 0.5)
        self.assertIn("Q1_Euphoric", res_fast["quadrant"])
        self.assertGreater(res_fast["recommended_physics"]["particle_density"], 1500)

        # 2. 憂鬱慢板 (65 BPM, low RMS, minor key)
        track_slow = {"bpm": 65.0, "rms_energy": 0.2, "spectral_centroid": 800.0, "is_minor": True}
        res_slow = MaestroAcousticMirror.project_to_va_space(track_slow)
        self.assertLess(res_slow["arousal"], 0.5)
        self.assertLess(res_slow["valence"], 0.0)
        self.assertIn("Q3_Melancholic", res_slow["quadrant"])

    def test_taste_profiler(self):
        profiler = MaestroTasteProfiler(workspace_dir=self.temp_dir)
        initial_summary = profiler.get_taste_summary()
        self.assertIn("探索階段", initial_summary)

        # 記錄發布模組
        profiler.record_published_module("Test_Cyber", "curl_noise_fluid", "synthwave", [{"id": "volumetric_godrays"}])
        self.assertEqual(profiler.profile_data["total_creations"], 1)
        self.assertGreater(profiler.profile_data["topology_weights"].get("curl_noise_fluid", 0), 0)

        # 測試加權抽樣
        candidates = [{"id": "curl_noise_fluid"}, {"id": "lorenz_attractor"}]
        choice = profiler.get_weighted_choice(candidates, "topology", serendipity=0.0)
        self.assertIsNotNone(choice)

    def test_metaphor_alchemist(self):
        # 隱喻剖析
        res = MaestroMetaphorAlchemist.deconstruct_metaphor("荒涼深海沉潛孤獨牢籠")
        self.assertEqual(res["primary_schema"], "CONTAINMENT")

        # 4 大語意方向推子映射
        steer_mods = MaestroMetaphorAlchemist.compute_semantic_modulation(
            chaos=0.9, organic=0.8, aggression=0.9, depth=0.7
        )
        self.assertGreater(steer_mods["bass_power_multiplier"], 2.0)
        self.assertGreater(steer_mods["camera_zoom"], 10.0)

    def test_vision_decompiler(self):
        # 建立測試影像
        test_img_path = os.path.join(self.temp_dir, "test_ref.png")
        img = Image.new("RGB", (80, 80), color=(10, 15, 25))
        for x in range(20, 60):
            for y in range(20, 60):
                img.putpixel((x, y), (255, 0, 128))
        img.save(test_img_path)

        res = MaestroVisionDecompiler.decompile_reference_image(test_img_path)
        self.assertIn("palette", res)
        self.assertTrue(len(res["palette"]) >= 4)
        self.assertIn("topology_id", res)

    def test_ambient_muse(self):
        muse = MaestroAmbientMuse(idle_threshold_seconds=0.01)
        import time
        time.sleep(0.02)
        hint = muse.poll_for_muse_hint()
        self.assertIsNotNone(hint)
        self.assertIn("💡", hint)

        # 測試操作重置
        muse.touch_action()
        self.assertFalse(muse.is_hint_active)

    def test_scenario_maestro_v2_e2e(self):
        # 測試結合聲學與審美記憶的老虎機
        slot = self.maestro.spin_inspiration_slot(acoustic_meta={"bpm": 135.0, "bass": 0.8})
        self.assertIn("title", slot)
        self.assertIn("va_result", slot)

        # 測試規格書生成與代碼合成
        spec = self.maestro.generate_rigid_spec(
            user_prompt="賽博廢土的機械爆裂",
            semantic_steer={"chaos": 0.8, "organic": 0.3, "aggression": 0.9, "depth": 0.6}
        )
        code = self.maestro.synthesize_p5_code(spec)
        self.assertIn("createCanvas", code)
        self.assertIn("Maestro V2 Enhanced", code)

if __name__ == "__main__":
    unittest.main()
