import os
import json
import unittest
import tempfile
import shutil

from visual_studio_core import (
    ASTParamEngine,
    ScenarioMaestro,
    CreationWizard,
    VirtualAudioDeck,
    ShaderRackBridge,
    QCValidator
)

class TestVisualStudioPro(unittest.TestCase):
    def setUp(self):
        self.sample_code = """
let particleCount = 1200; // @wizard(min=100, max=5000, step=50, label="粒子密度")
let noiseScale = 0.005;   // @wizard(min=0.001, max=0.02, step=0.001, label="噪聲細緻度")
let speedMultiplier = 1.5;

function setup() {
  createCanvas(windowWidth, windowHeight, WEBGL);
}

function draw() {
  background(10);
  let pulse = 1.0 + (window.audioParams.bass || 0);
  scale(pulse);
  box(100);
}
"""

    def test_ast_param_engine_parsing_and_patching(self):
        params = ASTParamEngine.parse_params(self.sample_code)
        self.assertEqual(len(params), 3)

        # 檢測 @wizard 標籤解析
        p_count = next(p for p in params if p["name"] == "particleCount")
        self.assertEqual(p_count["label"], "粒子密度")
        self.assertEqual(p_count["min"], 100)
        self.assertEqual(p_count["max"], 5000)
        self.assertEqual(p_count["value"], 1200)
        self.assertTrue(p_count["has_wizard_tag"])

        # 檢測無標籤時的啟發式推算
        p_speed = next(p for p in params if p["name"] == "speedMultiplier")
        self.assertEqual(p_speed["label"], "Speed Multiplier")
        self.assertFalse(p_speed["has_wizard_tag"])

        # 測試熱修補 JS 生成
        hot_patch = ASTParamEngine.generate_hot_patch_js("particleCount", 2400)
        self.assertIn("particleCount = 2400", hot_patch)

        # 測試代碼文字精確回寫
        patched_code = ASTParamEngine.patch_code_text(self.sample_code, "particleCount", 3600)
        self.assertIn("let particleCount = 3600; // @wizard", patched_code)

    def test_scenario_maestro(self):
        maestro = ScenarioMaestro()
        slot = maestro.spin_inspiration_slot()
        self.assertIn("title", slot)
        self.assertIn("narrative", slot)
        self.assertTrue(len(slot["suggested_shaders"]) > 0)

        # 規格書生成
        spec = maestro.generate_rigid_spec("cyberpunk lorenz attractor", target_genre="synthwave")
        self.assertEqual(spec["topology_id"], "lorenz_attractor")
        self.assertIn("synthwave", spec["genre"].lower())

        # 代碼合成
        code = maestro.synthesize_p5_code(spec)
        self.assertIn("createCanvas", code)
        self.assertIn("windowResized", code)
        self.assertIn("@wizard", code)

    def test_creation_wizard_state_machine(self):
        wizard = CreationWizard()
        self.assertEqual(wizard.current_step, 1)

        step1 = wizard.get_step_options()
        self.assertIn("genres", step1)

        wizard.next_step()
        self.assertEqual(wizard.current_step, 2)
        step2 = wizard.get_step_options()
        self.assertIn("topologies", step2)

        # 時間旅行回退
        wizard.prev_step()
        self.assertEqual(wizard.current_step, 1)

    def test_virtual_audio_deck(self):
        deck = VirtualAudioDeck()
        frame = deck.get_manual_frame()
        self.assertIn("sub_bass", frame)
        self.assertIn("bass", frame)
        self.assertIn("damped_bass", frame)

        # 測試重拍點擊
        deck.trigger_tap_beat()
        hit_frame = deck.get_manual_frame()
        self.assertEqual(hit_frame["bass"], 1.0)
        self.assertTrue(hit_frame["is_beat"])

    def test_shader_rack_bridge(self):
        bridge = ShaderRackBridge()
        presets = bridge.get_rack_presets()
        self.assertTrue(len(presets) >= 4)
        active = [{"id": "volumetric_godrays", "intensity": 0.8}]
        js = bridge.generate_webgl_fx_script(active)
        self.assertIn("volumetric_godrays", js)

    def test_qc_validator_and_packaging(self):
        audit = QCValidator.audit_code_safety(self.sample_code)
        self.assertTrue(audit["is_valid"])

        # 封裝為 JSON
        pkg = QCValidator.package_module_json("TestModule_01", self.sample_code)
        self.assertEqual(pkg["name"], "TestModule_01")
        self.assertIn("fingerprint", pkg["visual_dna"])
        self.assertIn("section_fitness", pkg["visual_dna"])

if __name__ == "__main__":
    unittest.main()
