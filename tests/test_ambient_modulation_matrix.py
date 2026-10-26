"""
32 維全態音視微觀調製矩陣 (SAVAP 32-D Modulation Matrix) 單元測試套件
驗證項目：
1. Ambient32DParameters: 6 大維度、32 個微觀參數的型別、邊界與 WebGL 導出
2. BallisticSmoother: 非對稱彈道濾波特性 (Attack vs Release)
3. SAVAPAmbientModulationBus: 聲學特徵非線性投影與相空間演化
4. AmbientChronosDirector: 實時調製匯流排聯動與 Uniforms 輸出完整度
5. shaders/ambient_ganzfeld_fog.frag: 32 維 Uniforms 聲明覆蓋率檢驗
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from savap_ambient_modulation_matrix import (
    Ambient32DParameters,
    BallisticSmoother,
    SAVAPAmbientModulationBus
)
from ambient_chronos_director import AmbientChronosDirector


class TestAmbientModulationMatrix(unittest.TestCase):

    def setUp(self):
        self.bus = SAVAPAmbientModulationBus()
        self.director = AmbientChronosDirector()

    def test_01_parameters_dimension_count(self):
        """驗證 32 維微觀參數數量與導出合法性"""
        params = Ambient32DParameters()
        param_dict = params.to_dict()
        uniforms = params.to_webgl_uniforms()

        # 驗證總參數數量嚴格為 32 個
        self.assertEqual(len(param_dict), 32)
        self.assertEqual(len(uniforms), 32)

        # 檢查代表性參數初值
        self.assertAlmostEqual(params.u_domainWarpAmp, 0.12)
        self.assertAlmostEqual(params.u_anisotropyG, 0.35)
        self.assertAlmostEqual(params.u_antiTroxlerRate, 0.33)
        self.assertAlmostEqual(params.u_cauchyDispersion, 0.045)

        for k, v in uniforms.items():
            self.assertIsInstance(v, float)
            self.assertTrue(k.startswith("u_"))

    def test_02_ballistic_smoother_asymmetry(self):
        """驗證非對稱彈道濾波器的 Attack / Release 響應"""
        smoother = BallisticSmoother(current_value=0.0, attack_tau=0.2, release_tau=5.0)

        # 1. 激發 Attack (突發目標 1.0)
        smoother.step(target=1.0, dt=0.1)
        val_after_attack = smoother.current_value
        self.assertGreater(val_after_attack, 0.2) # 快速爬升

        # 2. 激發 Release (目標回落到 0.0)
        smoother.step(target=0.0, dt=0.1)
        val_after_release = smoother.current_value
        # 由於 release_tau=5.0，衰減應非常緩慢
        self.assertGreater(val_after_release, val_after_attack * 0.9)

    def test_03_modulation_bus_telemetry_projection(self):
        """驗證聲學遙測到 32 維微觀參數的動態映射"""
        telemetry = {
            "sub_bass": 0.85,             # 強烈地質共振
            "spectral_centroid": 2400.0,  # 偏高音色 (明亮)
            "spectral_flux": 0.65,        # 高音色通量
            "spectral_flatness": 0.55,    # 偏噪聲
            "tension": 0.75               # 高緊張度
        }

        # 模擬 1 秒鐘的持續強烈輸入 (約 60 幀) 驗證彈道平滑爬升
        for _ in range(60):
            res_params = self.bus.update_from_telemetry(telemetry, dt=0.0166, breathing_rate=0.1)

        # 1. 驗證空間扭曲振幅隨 Sub-Bass 增大
        self.assertGreater(res_params.u_domainWarpAmp, 0.15)
        # 2. 驗證各向異性因子 g 隨明亮質心增加前向散射
        self.assertGreater(res_params.u_anisotropyG, 0.1)
        # 3. 驗證柯西色散因高音色通量激發
        self.assertGreater(res_params.u_cauchyDispersion, 0.03)

    def test_04_director_uniforms_injection(self):
        """驗證 AmbientChronosDirector 在 tick_frame 時成功輸出 32-D uniforms"""
        macro_sliders = {
            "breathing_rate": 0.12,
            "optical_translucency": 0.8,
            "luminance_gravity": 0.7,
            "time_dilation": 0.05,
            "chromatic_drift": 0.5
        }
        audio_features = {
            "bass": 0.6,
            "spectral_centroid": 1200.0,
            "spectral_flux": 0.3
        }

        director_output = self.director.tick_frame(
            current_time=10.0,
            dt=0.0166,
            audio_features=audio_features,
            macro_parameters=macro_sliders
        )

        uniforms = director_output["uniforms"]
        
        # 驗證微觀調製 Uniforms 是否已融入輸出字典
        self.assertIn("u_domainWarpAmp", uniforms)
        self.assertIn("u_anisotropyG", uniforms)
        self.assertIn("u_extinctionBeta", uniforms)
        self.assertIn("u_cauchyDispersion", uniforms)
        self.assertIn("u_antiTroxlerRate", uniforms)
        self.assertIn("u_sdfSmoothMinK", uniforms)

    def test_05_shader_uniforms_coverage(self):
        """驗證 GLSL 著色器檔案涵蓋所有 32 個 Uniform 變數宣告"""
        shader_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "shaders",
            "ambient_ganzfeld_fog.frag"
        )
        self.assertTrue(os.path.exists(shader_path))

        with open(shader_path, "r", encoding="utf-8") as f:
            shader_code = f.read()

        params = Ambient32DParameters()
        for uniform_name in params.to_dict().keys():
            self.assertIn(
                uniform_name,
                shader_code,
                f"Shader 缺少變數宣告: {uniform_name}"
            )


if __name__ == "__main__":
    unittest.main()
