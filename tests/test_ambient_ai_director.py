"""
SENTINEL-CHRONOS: Ambient AI Auteur Director & Visual Polyphony Unit Tests
驗證項目：
1. 聲學自相似矩陣 (SSM) 質地新穎度分析器功能
2. 三層視覺複調 (Visual Polyphony Trio) 自動策展與確定性種子分配
3. AI 導演長鏡頭生命週期與 6s~10s 同胚融鏡 (Cross-Dissolve) 狀態機
4. 32 維全態物理參數動態編舞介入機制
5. 4K NumPy/OpenCV 三層複調影像合成器 (AmbientPolyphonyCompositor)
6. AmbientDroneStudioTab UI 整合與 AI 導演全自動託管
"""

import os
import sys
import math
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 預先配置 Qt OpenGL 共享上下文屬性與 WebEngine
from PyQt6.QtCore import QCoreApplication, Qt
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication

from ambient_ai_director_bridge import (
    AmbientAcousticSSMAnalyzer,
    VisualPolyphonyTrio,
    AmbientCognitiveDirectorBridge
)
from ambient_polyphony_compositor import AmbientPolyphonyCompositor


class TestAmbientAIDirector(unittest.TestCase):

    def setUp(self):
        self.bridge = AmbientCognitiveDirectorBridge()
        self.compositor = AmbientPolyphonyCompositor()

    def test_01_ssm_novelty_analyzer(self):
        """驗證長時窗自相似矩陣質地新穎度計算"""
        analyzer = AmbientAcousticSSMAnalyzer(window_size_seconds=20.0)

        # 初始無足夠歷史時應回傳基準新穎度
        nov_init = analyzer.compute_novelty(0.0)
        self.assertAlmostEqual(nov_init, 0.1, places=2)

        # 模擬平穩的 Drone 音訊 (無質地轉變)
        for t in range(30):
            analyzer.record_feature(float(t), {
                "spectral_centroid": 600.0 + 5.0 * math.sin(t),
                "bass": 0.40 + 0.02 * math.cos(t)
            })

        nov_stable = analyzer.compute_novelty(30.0)
        self.assertTrue(nov_stable < 0.35, f"平穩訊號的新穎度應偏低: {nov_stable}")

        # 注入質地突變 (Centroid 躍遷與 Bass 驟降)
        for t in range(31, 45):
            analyzer.record_feature(float(t), {
                "spectral_centroid": 2200.0,
                "bass": 0.05
            })

        nov_shift = analyzer.compute_novelty(45.0)
        self.assertTrue(nov_shift > nov_stable, f"質地轉折後新穎度應上升: {nov_shift} vs {nov_stable}")

    def test_02_polyphony_trio_curation_and_determinism(self):
        """驗證三層視覺複調策展之多樣性與確定性"""
        seed1 = 12345678
        trio1 = self.bridge._curate_next_polyphony_trio(seed=seed1)

        self.assertEqual(trio1.layer1_atmospheric, "ambient_ganzfeld_fog")
        self.assertIsInstance(trio1.layer2_material_fluid, str)
        self.assertIsInstance(trio1.layer3_particulate, str)
        self.assertIsInstance(trio1.motif_id, str)
        self.assertEqual(len(trio1.blend_weights), 3)

        # 相同種子必須產生完全一致的策展結果
        trio1_repeat = self.bridge._curate_next_polyphony_trio(seed=seed1)
        self.assertEqual(trio1.layer2_material_fluid, trio1_repeat.layer2_material_fluid)
        self.assertEqual(trio1.layer3_particulate, trio1_repeat.layer3_particulate)
        self.assertEqual(trio1.motif_id, trio1_repeat.motif_id)

        # 不同種子能提供豐富分鏡變化
        seed2 = 87654321
        trio2 = self.bridge._curate_next_polyphony_trio(seed=seed2)
        self.assertNotEqual(trio1.motif_id, trio2.motif_id)

    def test_03_director_loop_and_choreography(self):
        """驗證 AI 導演循環：鏡頭生命週期、同胚融鏡與 32 維參數編舞"""
        # 模擬 1 秒幀循環
        state = self.bridge.tick_director_loop(
            current_time=1.0,
            dt=0.033,
            audio_features={"spectral_centroid": 650.0, "bass": 0.35, "mid": 0.25, "high": 0.15},
            audio_seed=9999
        )

        self.assertTrue(state["director_active"])
        self.assertIn("polyphony_trio", state)
        self.assertIn("shot_state", state)
        self.assertIn("intent_log", state)
        self.assertIn("uniforms_32d", state)

        uniforms = state["uniforms_32d"]
        self.assertIn("palette", uniforms)
        self.assertEqual(len(uniforms["palette"]), 12)  # 4 色 * 3 通道 (RGB)
        self.assertIn("u_domainWarpAmp", uniforms)
        self.assertIn("u_anisotropyG", uniforms)
        self.assertIn("u_extinctionBeta", uniforms)

        # 模擬時間推進至長鏡頭邊界消融階段 (> 25s)
        state_late = self.bridge.tick_director_loop(
            current_time=30.0,
            dt=0.033,
            audio_features={"spectral_centroid": 700.0, "bass": 0.40, "mid": 0.25, "high": 0.15},
            audio_seed=9999
        )
        # 各向異性散射 g 應被消融提升
        self.assertGreaterEqual(state_late["uniforms_32d"]["u_anisotropyG"], uniforms["u_anisotropyG"])

    def test_04_compositor_frame_blending(self):
        """驗證 4K NumPy/OpenCV 三層複調影像合成與色調映射"""
        h, w = 180, 320
        layer1 = np.full((h, w, 3), 40, dtype=np.uint8)   # 暗色大氣底層
        layer2 = np.full((h, w, 3), 100, dtype=np.uint8)  # 流體中層
        layer3 = np.full((h, w, 3), 180, dtype=np.uint8)  # 星塵頂層

        # 1. 軟濾色模式合成
        comp_soft = self.compositor.composite_frame(
            layer1_atmospheric=layer1,
            layer2_fluid=layer2,
            layer3_particulate=layer3,
            blend_mode="soft_screen"
        )
        self.assertEqual(comp_soft.shape, (h, w, 3))
        self.assertEqual(comp_soft.dtype, np.uint8)
        # 亮度應高於底層但被色調映射保護避免死白
        self.assertGreater(comp_soft[0, 0, 0], layer1[0, 0, 0])
        self.assertLess(comp_soft[0, 0, 0], 255)

        # 2. 測試加色輝光與亮度鍵控模式
        comp_glow = self.compositor.composite_frame(layer1, layer2, layer3, blend_mode="additive_glow")
        comp_luma = self.compositor.composite_frame(layer1, layer2, layer3, blend_mode="luma_key")
        self.assertEqual(comp_glow.shape, (h, w, 3))
        self.assertEqual(comp_luma.shape, (h, w, 3))

    def test_05_compositor_cross_dissolve(self):
        """驗證同胚慢速融鏡與中間光暈效果"""
        h, w = 180, 320
        frame_a = np.zeros((h, w, 3), dtype=np.uint8)
        frame_b = np.full((h, w, 3), 200, dtype=np.uint8)

        # 進度 0.0 應接近 A
        res_0 = self.compositor.cross_dissolve(frame_a, frame_b, progress=0.0)
        self.assertTrue(np.all(res_0 == 0))

        # 進度 1.0 應接近 B
        res_1 = self.compositor.cross_dissolve(frame_a, frame_b, progress=1.0)
        self.assertTrue(np.all(res_1 == 200))

        # 進度 0.5 應處於過渡中
        res_mid = self.compositor.cross_dissolve(frame_a, frame_b, progress=0.5, halation_boost=0.0)
        self.assertTrue(80 <= res_mid[0, 0, 0] <= 120)

    def test_06_compositor_webgl_canvas_html(self):
        """驗證 WebGL / Canvas 三層整合 HTML 模板輸出"""
        trio = VisualPolyphonyTrio()
        html = self.compositor.generate_polyphony_canvas_html(
            trio=trio,
            vertex_shader_code="void main() { gl_Position = vec4(0.0); }",
            fragment_shader_code="precision mediump float; out vec4 fragColor; void main() { fragColor = vec4(1.0); }",
            uniforms_32d_dict={"u_breathingRate": 0.12}
        )
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("layer1_webgl", html)
        self.assertIn("layer2_fluid", html)
        self.assertIn("layer3_particles", html)
        self.assertIn("u_breathingRate", html)

    def test_07_studio_tab_ui_integration(self):
        """驗證 AmbientDroneStudioTab UI 元件與 AI 導演全自動託管開關"""
        app = QApplication.instance()
        if app is None:
            app = QApplication(["test"])

        from ambient_drone_studio_tab import AmbientDroneStudioTab

        tab = AmbientDroneStudioTab()
        self.assertTrue(hasattr(tab, "ai_director_bridge"))
        self.assertTrue(hasattr(tab, "polyphony_compositor"))
        self.assertTrue(hasattr(tab, "btn_ai_autopilot"))
        self.assertTrue(hasattr(tab, "lbl_trio_status"))
        self.assertTrue(hasattr(tab, "lbl_director_intent"))
        self.assertTrue(tab.is_ai_auteur_active)

        # 模擬切換託管開關
        tab._toggle_ai_autopilot()
        self.assertFalse(tab.is_ai_auteur_active)
        self.assertIn("手動接管", tab.btn_ai_autopilot.text())

        tab._toggle_ai_autopilot()
        self.assertTrue(tab.is_ai_auteur_active)
        self.assertIn("運行中", tab.btn_ai_autopilot.text())

        # 模擬計時器循環呼叫
        tab._tick_ui_breathing()
        self.assertTrue(len(tab.lbl_director_intent.text()) > 0)
        self.assertTrue(len(tab.lbl_trio_status.text()) > 0)


if __name__ == "__main__":
    unittest.main()
