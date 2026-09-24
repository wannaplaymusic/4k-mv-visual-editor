#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite for Studio Rack Engines (IVisualEngine & SRA)
驗證三大生成引擎 (MathSynth, PixelArt, SurrealCollage) 與動態發現、AST 參數解析、音訊生命週期勾子及 AI 總導演路由器
"""

import os
import unittest
from visual_studio_core import (
    get_engine_registry, EngineRegistry, BaseVisualEngine,
    ASTParamEngine, ScenarioMaestro
)
from visual_studio_core.engines import (
    MathSynthEngine, PixelArtEngine, SurrealCollageEngine
)


class TestStudioRackEngines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = get_engine_registry()
        cls.workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.maestro = ScenarioMaestro(cls.workspace_dir)

    def test_registry_discovery(self):
        """測試動態引擎發現與單例註冊表"""
        engines = self.registry.list_engines()
        engine_ids = [e.id for e in engines]
        self.assertIn("math_synth", engine_ids)
        self.assertIn("pixel_art", engine_ids)
        self.assertIn("surreal_collage", engine_ids)
        self.assertGreaterEqual(len(engines), 3)

        # 驗證元數據完整性
        for meta in engines:
            self.assertTrue(meta.name)
            self.assertTrue(meta.icon)
            self.assertTrue(meta.description)
            self.assertGreater(len(meta.tags), 0)
            self.assertGreater(len(meta.recommended_shaders), 0)

    def test_math_synth_engine(self):
        """測試神經數學幾何拓撲孵化引擎"""
        engine = self.registry.get_engine("math_synth")
        self.assertIsInstance(engine, MathSynthEngine)
        
        # 代碼生成測試
        code = engine.generate_code({"topology": "clifford", "speed": 1.5, "particleCount": 3000})
        self.assertTrue("Clifford" in code or "CLIFFORD" in code or "clifford" in code.lower())
        self.assertIn("window.onAudioFrame", code)
        self.assertIn("createCanvas", code)

        # AST 參數解析測試
        params = ASTParamEngine.parse_params(code)
        param_names = [p["name"] for p in params]
        self.assertIn("speed", param_names)
        self.assertIn("particleCount", param_names)
        self.assertIn("scaleFactor", param_names)

        # 遺傳變異測試
        init_params = {"speed": 1.0, "particleCount": 2000, "scaleFactor": 1.5}
        mutated = engine.mutate(init_params, strength=0.5)
        self.assertIsInstance(mutated, dict)
        self.assertIn("speed", mutated)

    def test_pixel_art_engine(self):
        """測試像素復古點陣工坊引擎"""
        engine = self.registry.get_engine("pixel_art")
        self.assertIsInstance(engine, PixelArtEngine)

        # 代碼生成測試
        code = engine.generate_code({"pixelSize": 16, "ditherStrength": 0.8, "styleMode": 1, "paletteMode": 0})
        self.assertIn("window.onAudioFrame", code)
        self.assertIn("BAYER_4x4", code)
        self.assertIn("PALETTES", code)

        # AST 參數解析測試
        params = ASTParamEngine.parse_params(code)
        param_names = [p["name"] for p in params]
        self.assertIn("pixelSize", param_names)
        self.assertIn("ditherStrength", param_names)
        self.assertIn("styleMode", param_names)
        self.assertIn("scanlineAlpha", param_names)

    def test_surreal_collage_engine(self):
        """測試超現實主義拼貼引擎"""
        engine = self.registry.get_engine("surreal_collage")
        self.assertIsInstance(engine, SurrealCollageEngine)

        # 代碼生成測試
        code = engine.generate_code({"scaleInversion": 3.0, "orbitRadius": 320, "duotoneStrength": 0.9})
        self.assertIn("window.onAudioFrame", code)
        self.assertIn("scaleInversion", code)
        self.assertIn("orbitRadius", code)

        # AST 參數解析測試
        params = ASTParamEngine.parse_params(code)
        param_names = [p["name"] for p in params]
        self.assertIn("scaleInversion", param_names)
        self.assertIn("orbitRadius", param_names)
        self.assertIn("orbitSpeed", param_names)
        self.assertIn("limbDecompose", param_names)

    def test_maestro_engine_director_routing(self):
        """測試 AI 總導演智能引擎路由器"""
        # 像素關鍵字路由
        r1 = self.maestro.route_engine("8bit 復古像素遊戲街機 Cyberpunk")
        self.assertEqual(r1, "pixel_art")

        # 超現實拼貼關鍵字路由
        r2 = self.maestro.route_engine("達利超現實融化鐘錶荒原夢境")
        self.assertEqual(r2, "surreal_collage")

        # 拓撲幾何路由
        r3 = self.maestro.route_engine("卡拉比-丘高維流形粒子引力透鏡")
        self.assertEqual(r3, "math_synth")

        # 全域調度規格書
        spec = self.maestro.recommend_engine_and_spec("Cyberpunk 16bit retro dither arcade")
        self.assertEqual(spec["engine_id"], "pixel_art")
        self.assertIn("pixelSize", spec["recommended_params"])
        self.assertGreater(len(spec["shaders"]), 0)


if __name__ == "__main__":
    unittest.main()
