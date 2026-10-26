# -*- coding: utf-8 -*-
"""
單元測試：24 大前衛電影作者美學世界觀本體論矩陣 (24 Epic Auteur Worldview Ontology Matrix)
驗證項目：
1. 24 大世界觀資料完整度 (包含 6 大流派、24 種唯一世界觀、motifs、manifesto、progression、color_arc、數值區間等)
2. AuteurWorldviewOntologyEngine 多維度評分及歷史記憶滑動窗口降權
3. LLMDirectorAgent 腳本生成規格相容性
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_director import AUTEUR_THEMES, AuteurWorldviewOntologyEngine, LLMDirectorAgent

class TestAuteurWorldviewOntology(unittest.TestCase):

    def test_ontology_matrix_completeness(self):
        """ 測試 24 大世界觀規格完整性 """
        self.assertEqual(len(AUTEUR_THEMES), 27, "必須包含 27 種電影作者世界觀")
        
        clusters = set()
        ids = set()
        
        required_keys = [
            "id", "genre_cluster", "title", "motifs", "motif", "manifesto",
            "progression", "color_arc", "ideal_valence_range", "ideal_arousal_range",
            "target_tension_range", "target_roughness_range", "genre_keywords", "recommended_fx"
        ]
        
        for theme in AUTEUR_THEMES:
            # 唯一性檢驗
            self.assertNotIn(theme["id"], ids, f"重複的 ID: {theme['id']}")
            ids.add(theme["id"])
            clusters.add(theme["genre_cluster"])
            
            # 欄位完整性檢驗
            for k in required_keys:
                self.assertIn(k, theme, f"主題 {theme['id']} 缺少必填欄位 {k}")
                
            self.assertTrue(len(theme["motifs"]) >= 4, f"主題 {theme['id']} 母題數量過少")
            self.assertTrue(len(theme["manifesto"]) >= 15, f"主題 {theme['id']} 哲學宣言長度不足")
            self.assertTrue(len(theme["progression"]) >= 4, f"主題 {theme['id']} 劇作演進階段過少")
            self.assertTrue(len(theme["recommended_fx"]) >= 3, f"主題 {theme['id']} 推薦特效過少")
            
        self.assertEqual(len(clusters), 7, f"必須涵蓋 7 大美學流派，實際有: {clusters}")

    def test_ontology_engine_recency_penalty(self):
        """ 測試歷史記憶滑動窗口動態降權防撞車機制 """
        engine = AuteurWorldviewOntologyEngine(memory_window=6)
        engine.reset_history()
        
        telemetry = {
            "genre": "Industrial Techno",
            "bpm": 135.0,
            "valence": -0.7,
            "arousal": 0.85,
            "tension": 0.8,
            "roughness": 0.75
        }
        
        # 連續多次針對相同輸入求值，驗證防撞車機制會輪換不同作者論流派
        chosen_ids = []
        for _ in range(5):
            res = engine.resolve_theme(telemetry)
            chosen_ids.append(res["id"])
            
        # 連續 5 次在相同強曲風輸入下，不應全部鎖死在同一個世界觀
        unique_chosen = set(chosen_ids)
        self.assertTrue(len(unique_chosen) >= 3, f"防碰撞機制未有效分散世界觀: {chosen_ids}")

    def test_director_script_generation(self):
        """ 測試 LLMDirectorAgent 生成腳本完整性與向後相容性 """
        agent = LLMDirectorAgent()
        sample_audio = {
            "genre": "Ambient Cinematic",
            "bpm": 75.0,
            "valence": 0.2,
            "arousal": 0.25,
            "tension": 0.2,
            "roughness": 0.1,
            "storyboard": [
                {"section": "Intro", "duration": 15.0},
                {"section": "Theme", "duration": 30.0},
                {"section": "Climax", "duration": 25.0},
                {"section": "Outro", "duration": 15.0}
            ]
        }
        dummy_modules = [
            {"_filename_key": "mod_a", "name": "Module A", "used_count": 0},
            {"_filename_key": "mod_b", "name": "Module B", "used_count": 0},
            {"_filename_key": "mod_c", "name": "Module C", "used_count": 0},
            {"_filename_key": "mod_d", "name": "Module D", "used_count": 0}
        ]
        
        script = agent.generate_director_script(sample_audio, dummy_modules)
        
        # 驗證輸出欄位
        self.assertIn("genre_cluster", script)
        self.assertIn("manifesto", script)
        self.assertIn("motifs", script)
        self.assertIn("recommended_fx", script)
        self.assertIn("theme_title", script)
        self.assertIn("shot_list", script)
        self.assertIn("intensity_curve", script)
        self.assertEqual(len(script["shot_list"]), 4)
        
        # 驗證每個分鏡都已指派辯證演進與象徵母題
        for shot in script["shot_list"]:
            self.assertIn("dialectical_stage", shot)
            self.assertIn("symbolic_motif", shot)

if __name__ == "__main__":
    unittest.main()
