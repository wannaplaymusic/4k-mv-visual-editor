# -*- coding: utf-8 -*-
"""
Test Suite: Ambient Color Remapping & Restraint System (AM-DCR System)
======================================================================
針對限定在 Ambient 曲風中導演系統/分鏡系統色彩重塑與模組動態覆寫的完整驗證：
1. 方案一：沙盒運行時色彩攔截器 (Runtime Color Proxy & Ambient Color Guard)
2. 方案二：AI 導演分鏡表模組調色盤動態覆蓋 (Per-Shot Module Palette Override)
3. 方案三：後處理 OKLab 感知色度限制器 (Perceptual Chroma Limiter & ShowLook)
4. 方案四：資產庫色彩風險審計與自適應調色盤開關 (Module Color Risk Audit)
"""

import os
import sys
import unittest
import numpy as np
from PIL import Image

workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, workspace_dir)

from post_processor import (
    PostProcessor,
    srgb_to_oklab,
    oklab_to_srgb,
    apply_ambient_perceptual_chroma_limiter
)
from ambient_chronos_director import AmbientChronosDirector
from ambient_ai_director_bridge import AmbientCognitiveDirectorBridge
from ambient_module_compatibility_gate import AmbientModuleCompatibilityGate
from visual_studio_core.scenario_maestro import ScenarioMaestro


class TestAmbientColorRemappingSystem(unittest.TestCase):

    def setUp(self):
        self.chroma_ceiling = 0.070

    def test_post_processor_oklab_chroma_limiter(self):
        """[方案三] 驗證極端刺眼高飽和色在 OKLab 色度限制器下被溫和壓制"""
        # 構造一個包含純紅、純綠、純藍、純黃、純青的高彩度測試圖像 (100x100)
        h, w = 100, 100
        raw_vivid = np.zeros((h, w, 3), dtype=np.uint8)
        raw_vivid[0:20, :] = [255, 0, 0]      # 純紅 (Extreme Vivid Red)
        raw_vivid[20:40, :] = [0, 255, 0]     # 純綠 (Extreme Vivid Green)
        raw_vivid[40:60, :] = [0, 0, 255]     # 純藍 (Extreme Vivid Blue)
        raw_vivid[60:80, :] = [255, 255, 0]   # 純黃 (Extreme Vivid Yellow)
        raw_vivid[80:100, :] = [255, 0, 255]  # 純洋紅 (Extreme Vivid Magenta)

        # 檢驗未處理前 OKLab 色度
        ok_before = srgb_to_oklab(raw_vivid)
        chroma_before = np.sqrt(ok_before[:, :, 1]**2 + ok_before[:, :, 2]**2)
        max_c_before = np.max(chroma_before)
        mean_c_before = np.mean(chroma_before)
        self.assertGreater(max_c_before, 0.20, "未處理前高飽和色之 OKLab 色度應遠高於 0.20")

        # 套用 Ambient 感知色度抑制
        target_limit = 0.068
        tamed = apply_ambient_perceptual_chroma_limiter(
            raw_vivid,
            chroma_limit=target_limit,
            target_hue_deg=210.0,
            hue_blend=0.15,
            highlight_rolloff=0.88
        )

        ok_after = srgb_to_oklab(tamed)
        chroma_after = np.sqrt(ok_after[:, :, 1]**2 + ok_after[:, :, 2]**2)
        max_c_after = np.max(chroma_after)

        # 斷言：處理後的最大彩度必須小於等於目標限制門檻 (容許 0.005 數值公差)
        self.assertLessEqual(
            max_c_after, target_limit + 0.005,
            f"處理後最大色度 {max_c_after:.4f} 超出目標上限 {target_limit}"
        )
        self.assertLess(np.mean(chroma_after), mean_c_before * 0.5, "平均色彩刺激度應大幅下降超過 50%")

    def test_post_processor_ambient_process_pipeline(self):
        """[方案三] 驗證 PostProcessor.process 在 ambient 曲風下自動啟用防護"""
        pp = PostProcessor(genre='ambient')
        img_in = Image.new("RGB", (320, 240), color=(255, 10, 80)) # 刺眼桃紅
        audio_feats = {
            'bass': 0.3,
            'sub_bass': 0.3,
            'ethereal': 0.8,
            'percussive': 0.1,
            'roughness': 0.1,
            'silence_fade': 0.0
        }
        fx_flags = {'color_boost': True, 'photosensitive_safe': True}

        img_out = pp.process(
            img_in, t=1.0, is_beat=False, beat_energy=0.2,
            audio_feats=audio_feats, fx_flags=fx_flags,
            genre='ambient'
        )
        self.assertIsNotNone(img_out)
        out_np = np.array(img_out)
        ok_out = srgb_to_oklab(out_np)
        c_out = np.sqrt(ok_out[:, :, 1]**2 + ok_out[:, :, 2]**2)
        # 斷言：在 Ambient 曲風中，刺眼桃紅必須被壓低至 0.09 以下
        self.assertLessEqual(np.mean(c_out), 0.09)

    def test_ambient_director_storyboard_palette_policy(self):
        """[方案二] 驗證 AmbientChronosDirector 分鏡表自動注入色彩政策"""
        director = AmbientChronosDirector()
        storyboard = director.plan_long_take_storyboard(total_duration=120.0)

        self.assertGreater(len(storyboard), 0, "分鏡表不應為空")
        first_shot = storyboard[0]
        self.assertIn("palette_hex", first_shot, "分鏡必須包含 palette_hex 陣列")
        self.assertEqual(len(first_shot["palette_hex"]), 4, "調色盤應為 4 色")
        self.assertIn("ambient_color_policy", first_shot, "分鏡必須包含 ambient_color_policy")
        policy = first_shot["ambient_color_policy"]
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["mode"], "clamp_and_blend")
        self.assertLessEqual(policy["chroma_ceiling"], 0.08)

    def test_ambient_director_module_palette_override(self):
        """[方案二] 驗證可在 Ambient 曲風中臨時改動個別模組的配色"""
        director = AmbientChronosDirector()
        custom_palette = ["#1a202c", "#2d3748", "#4a5568", "#718096"]
        
        # 模擬臨時改動模組 "HobbyCurve_1" 的配色
        director.set_module_palette_override(
            module_name_or_id="HobbyCurve_1",
            palette_hex=custom_palette,
            chroma_limit=0.05,
            mode="snap_to_palette"
        )

        effective_policy = director.get_effective_color_policy("HobbyCurve_1")
        self.assertEqual(effective_policy["palette"], custom_palette)
        self.assertEqual(effective_policy["mode"], "snap_to_palette")
        self.assertEqual(effective_policy["chroma_ceiling"], 0.05)

        # 未被覆寫的模組應回退到預設
        default_policy = director.get_effective_color_policy("UnknownModule")
        self.assertNotEqual(default_policy["palette"], custom_palette)

    def test_ambient_ai_director_bridge_color_flow(self):
        """[方案二] 驗證 AmbientCognitiveDirectorBridge 在每幀調度中輸出色彩政策"""
        bridge = AmbientCognitiveDirectorBridge()
        audio_feats = {"sub_bass": 0.35, "spectral_centroid": 600.0, "tension": 0.2}

        # 模擬外部臨時改動中層模組配色
        custom_palette = ["#0f172a", "#1e293b", "#334155", "#475569"]
        bridge.set_module_palette_override("HobbyCurve_1", custom_palette)

        res = bridge.tick_director_loop(current_time=5.0, dt=0.033, audio_features=audio_feats)
        self.assertIn("ambient_color_policy", res)
        self.assertIn("palette_hex", res)
        self.assertIn("polyphony_trio", res)

    def test_module_compatibility_gate_color_risk_audit(self):
        """[方案四] 驗證資產庫能識別寫死鮮艷色彩風險並生成適配政策"""
        gate = AmbientModuleCompatibilityGate.get_instance()

        # 1. 測試高彩度關鍵詞模組
        vivid_audit = gate.audit_module_vivid_color_risk("CyberRainbowGlitch")
        self.assertEqual(vivid_audit["vivid_risk_level"], "HIGH")
        self.assertEqual(vivid_audit["recommended_action"], "FORCE_PALETTE_OVERRIDE")

        # 2. 測試純代碼中寫死原色的情況
        code_with_hardcoded_rgb = "function draw() { fill(255, 0, 0); stroke('#00ff00'); }"
        code_audit = gate.audit_module_vivid_color_risk("TestModule", code_with_hardcoded_rgb)
        self.assertEqual(code_audit["vivid_risk_level"], "HIGH")

        # 3. 測試獲取專屬 Ambient 色彩策略
        policy = gate.get_module_ambient_color_policy("CyberRainbowGlitch")
        self.assertEqual(policy["mode"], "snap_to_palette")
        self.assertLessEqual(policy["chroma_ceiling"], 0.06)

    def test_scenario_maestro_ambient_palette_refinement(self):
        """[方案二/四] 驗證 ScenarioMaestro 的 Ambient 曲風預設為莫蘭迪色系"""
        maestro = ScenarioMaestro()
        ambient_genre = next(g for g in maestro.GENRES if g["id"] == "ambient_drone")
        palette = ambient_genre["palette"]

        # 驗證調色盤不包含刺眼原色
        for hex_col in palette:
            self.assertNotIn(hex_col.lower(), ["#ff0000", "#00ff00", "#0000ff", "#ff007f", "#00f0ff"])

        # 測試動態覆寫
        maestro.override_genre_palette("ambient_drone", ["#111111", "#222222", "#333333", "#444444"])
        spec = maestro.generate_rigid_spec(user_prompt="ambient meditation")
        self.assertEqual(spec["palette"], ["#111111", "#222222", "#333333", "#444444"])

    def test_in_memory_module_hex_color_remapping(self):
        """[方案一] 驗證選擇 Ambient 曲風時，記憶體內臨時重映射個別模組寫死的鮮艷 Hex 色碼"""
        import colorsys
        import re
        from main import remap_module_colors_for_ambient_in_memory, AMBIENT_DIRECTOR_PALETTES

        raw_sketch = """
        let colors = ['#ff0055', '#00ffcc', '#f1d302', '#c1292e', '#101216'];
        function draw() {
            background('#05070a');
            fill("#ff007f");
        }
        """
        remapped = remap_module_colors_for_ambient_in_memory(
            raw_sketch,
            AMBIENT_DIRECTOR_PALETTES["nordic_glacier_mist"]
        )
        self.assertNotIn("#ff0055", remapped.lower())
        self.assertNotIn("#00ffcc", remapped.lower())
        self.assertNotIn("#ff007f", remapped.lower())

        # 檢查重映射後的所有 Hex 色碼飽和度皆 <= 0.26
        hex_matches = re.findall(r'#([0-9a-fA-F]{6})', remapped)
        self.assertGreaterEqual(len(hex_matches), 6)
        for h_code in hex_matches:
            r = int(h_code[0:2], 16) / 255.0
            g = int(h_code[2:4], 16) / 255.0
            b = int(h_code[4:6], 16) / 255.0
            _, _, sat = colorsys.rgb_to_hls(r, g, b)
            self.assertLessEqual(sat, 0.26, f"重映射色碼 #{h_code} 飽和度 {sat:.3f} 超出莫蘭迪安全上限")

    def test_step11_dark_exposure_boost_never_causes_neon_overflow(self):
        """[方案三] 驗證 Step 11 暗部自動曝光拉升後，依然通過 OKLab 終極色度夾持，絕不反彈為鮮艷色"""
        pp = PostProcessor(genre="Ambient / Drone (環境氛圍)")
        self.assertTrue(pp.is_ambient_genre)

        # 構造一個偏暗但具有強烈色彩傾向 (暗紫紅 RGB=45, 2, 35) 的畫面，觸發 Step 11 (cur_max < 95)
        dark_chromatic = Image.new("RGB", (240, 180), color=(45, 2, 35))
        img_out = pp.process(
            dark_chromatic,
            t=2.5,
            is_beat=False,
            beat_energy=0.15,
            audio_feats={"sub_bass": 0.3, "ethereal": 0.85, "force_ambient_color": True},
            fx_flags={"color_boost": True},
            genre="Ambient / Drone (環境氛圍)"
        )
        out_np = np.array(img_out)
        ok_out = srgb_to_oklab(out_np)
        c_out = np.sqrt(ok_out[:, :, 1]**2 + ok_out[:, :, 2]**2)
        self.assertLessEqual(float(np.max(c_out)), 0.080, "Step 11 曝光增益後最大 OKLab 色度不可溢出超過 0.080")

    def test_fx_polymorphic_mutation_engine_ambient_safety(self):
        """[方案四] 驗證 FXPolymorphicMutationEngine 在 Ambient 曲風下禁用霓虹反轉並採用莫蘭迪霧色"""
        from post_processor import FXPolymorphicMutationEngine
        for i in range(30):
            dna = FXPolymorphicMutationEngine.generate_invocation_dna(
                "reaction_diffusion_growth",
                t=float(i) * 0.5,
                beat_energy=0.2,
                audio_feats={"sub_bass": 0.3, "roughness": 0.1},
                song_seed=i,
                genre="Ambient / Drone"
            )
            self.assertNotIn(dna["color_polarity"], (1, 2), "Ambient 嚴禁觸發 pol=1 (霓虹反轉) 或 pol=2")
            np.testing.assert_array_equal(dna["palette"], FXPolymorphicMutationEngine.ACES_AMBIENT_MIST)

    def test_llm_director_ambient_worldview_and_per_shot_color_policy(self):
        """[方案五] 驗證 LLMDirectorAgent 在 Ambient 曲風下鎖定沉思世界觀並為每個分鏡注入莫蘭迪調色盤"""
        from llm_director import LLMDirectorAgent
        agent = LLMDirectorAgent()
        script = agent.generate_director_script(
            audio_telemetry={
                "genre": "ambient_drone",
                "bpm": 70.0,
                "valence": 0.1,
                "arousal": 0.2,
                "storyboard": [
                    {"section": "Intro", "start": 0.0, "end": 15.0, "duration": 15.0, "intensity": 0.2},
                    {"section": "Verse", "start": 15.0, "end": 45.0, "duration": 30.0, "intensity": 0.35},
                ],
            },
            available_modules=[
                {"_filename_key": "mod_a", "name": "AuroraMist", "tags": ["ambient", "fluid"]},
                {"_filename_key": "mod_b", "name": "SlowWaves", "tags": ["minimal", "nature"]},
            ],
        )
        self.assertNotIn(
            script.get("genre_cluster"),
            ("工業殘酷主義與重力塌陷", "賽博龐克、後人類與數位異化"),
            "Ambient 曲風絕不可被分配至工業殘酷主義或高飽和賽博龐克世界觀"
        )
        shots = script.get("shot_list", [])
        self.assertEqual(len(shots), 2)
        for shot in shots:
            self.assertIn("ambient_color_policy", shot)
            pol = shot["ambient_color_policy"]
            self.assertTrue(pol["enabled"])
            self.assertEqual(len(pol["palette"]), 5)
            self.assertLessEqual(pol["max_saturation"], 0.30)

    def test_v2_adaptive_breath_segment_coalescer(self):
        """[v2.0 支柱一] 驗證自適應呼吸長鏡頭熔接器將零碎 6~8s 分鏡合併為 16s~36s 冥想長鏡頭"""
        from llm_director import coalesce_ambient_storyboard_sections
        fragmented = [
            {"section": "Intro", "start": 0.0, "end": 7.0},
            {"section": "Verse", "start": 7.0, "end": 15.0},
            {"section": "Verse", "start": 15.0, "end": 23.0},
            {"section": "Build-up", "start": 23.0, "end": 30.0},
            {"section": "Drop", "start": 30.0, "end": 38.0},
            {"section": "Chorus", "start": 38.0, "end": 46.0},
            {"section": "Bridge", "start": 46.0, "end": 54.0},
            {"section": "Outro", "start": 54.0, "end": 64.0},
        ]
        coalesced = coalesce_ambient_storyboard_sections(fragmented, min_shot_dur=16.0, max_shot_dur=36.0)
        self.assertLess(len(coalesced), len(fragmented), "零碎分鏡應被熔接減少鏡頭數")
        for seg in coalesced[:-1]:
            self.assertGreaterEqual(seg["duration"], 16.0, "熔接後的長鏡頭章節應至少達 16 秒")
            self.assertLessEqual(seg["duration"], 36.0, "熔接後的長鏡頭章節不可超過 36 秒上限")

        # 短曲 (<= 3 段) 應保持原樣不誤殺
        short_story = [
            {"section": "Intro", "start": 0.0, "end": 10.0},
            {"section": "Verse", "start": 10.0, "end": 20.0},
        ]
        self.assertEqual(len(coalesce_ambient_storyboard_sections(short_story)), 2)

    def test_v2_gate_filter_modules_for_ambient_contract(self):
        """[v2.0 支柱二] 驗證 filter_modules_for_ambient 契約修復、GREEN/YELLOW 分級與速度阻尼標記"""
        gate = AmbientModuleCompatibilityGate.get_instance()
        raw_mods = [
            {"name": "StrobeGlitch3D", "tags": ["glitch", "strobe"], "storyboard_weight": 90},
            {"name": "FluidOrbit", "tags": ["fluid", "particle"], "storyboard_weight": 50},
            {"name": "SlowWaves", "tags": ["ambient", "nebula"], "storyboard_weight": 25},
        ]
        filtered = gate.filter_modules_for_ambient(raw_mods, allow_yellow=True)
        names = [m["name"] for m in filtered]
        self.assertNotIn("StrobeGlitch3D", names, "RED 禁制模組必須被剔除")
        self.assertIn("SlowWaves", names)
        self.assertIn("FluidOrbit", names)
        self.assertEqual(filtered[0]["name"], "SlowWaves", "GREEN 原生模組必須排在 YELLOW 模組之前")
        self.assertEqual(filtered[0]["ambient_tier"], "GREEN")
        self.assertAlmostEqual(filtered[0]["ambient_speed_multiplier"], 0.65)
        self.assertEqual(filtered[1]["ambient_tier"], "YELLOW")
        self.assertAlmostEqual(filtered[1]["ambient_speed_multiplier"], 0.22)

    def test_v2_realtime_qc_auditor_ambient_exemption(self):
        """[v2.0 支柱五] 驗證實時 QC 診斷器在 Ambient 模式下豁免 1.45x 對比暴衝與過早熱插拔"""
        from realtime_qc_auditor import RealtimeRenderQCAuditor
        auditor = RealtimeRenderQCAuditor()
        # 構造一張深海微光影格 (RGB = 14, 18, 22)，在舊版會因為 rgb_max < 22 被強制拉升 1.45x 對比度或觸發高潮補強
        dark_mist_frame = Image.new("RGB", (160, 120), color=(14, 18, 22))
        healed_frame, boost_fx = auditor.audit_frame(
            frame_i=30,
            pil_img=dark_mist_frame,
            t=2.5,
            is_beat=True,
            beat_energy=0.85,
            audio_feats={"force_ambient_color": True, "percussive": 0.75},
            sec_name="Drop",
            music_energy=0.85
        )
        self.assertFalse(boost_fx.get("trigger_hotswap_fallback", False), "Ambient 深海微光畫面絕不可觸發誤殺熱插拔")
        self.assertNotIn("contrast_boost", boost_fx, "Ambient 模式下 Drop 高能量或深色微光不得觸發 1.45x/1.25x 對比度暴衝")
        self.assertFalse(boost_fx.get("strobe_flash", False), "Ambient 模式下嚴禁觸發 strobe_flash")
        np.testing.assert_array_equal(np.array(healed_frame), np.array(dark_mist_frame))

    def test_v2_dual_pole_chromatic_depth_guard(self):
        """[v2.0 支柱四] 驗證 ambient_color_guard.js 與 main.py 內建明度分層雙色溫景深重映射"""
        guard_path = os.path.join(workspace_dir, "ambient_color_guard.js")
        with open(guard_path, "r", encoding="utf-8") as f:
            js_code = f.read()
        self.assertIn("isShadowLayer", js_code)
        self.assertIn("0.68", js_code)
        self.assertIn("0.48", js_code)


if __name__ == "__main__":
    unittest.main()

