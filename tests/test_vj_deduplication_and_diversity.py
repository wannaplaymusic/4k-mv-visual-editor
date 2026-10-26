# -*- coding: utf-8 -*-
import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bandit_inventory_selector import BanditInventorySelector, extract_base_family
from post_processor import PostProcessor

class TestVjDeduplicationAndDiversity(unittest.TestCase):
    def test_theme_pool_count_and_ocular_isolation(self):
        pp = PostProcessor(seed_string='test_iso', genre='techno')
        self.assertEqual(len(pp.theme_pools), 13, '應該具備 13 大美學風格池')
        for t, pool in pp.theme_pools.items():
            self.assertGreaterEqual(len(pool), 14, f'風格池 {t} 數量不足 14 款')
        
        # 驗證 ocular_tremor 僅存在於 CyberGlitch 與 HardcoreThermal，不再泛濫於 4 個池
        ocular_pools = [t for t, p in pp.theme_pools.items() if 'ocular_tremor' in p]
        self.assertEqual(sorted(ocular_pools), ['CyberGlitch', 'HardcoreThermal'], 'ocular_tremor 應僅限於 2 個專屬風格池')

    def test_bandit_family_and_name_deduplication(self):
        bandit = BanditInventorySelector()
        
        # 模擬具有多個副本的模組清單 (例如 3 個 Frozenbrush 變體，同 name 或同 family)
        mock_modules = [
            {'_filename_key': 'Frozenbrush_1', 'name': 'Frozenbrush', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'Frozenbrush_2', 'name': 'Frozenbrush', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'Frozenbrush_3', 'name': 'Frozenbrush', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'WobblySwarm_1', 'name': 'WobblySwarm', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'WobblySwarm_2', 'name': 'WobblySwarm', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'CosmicNebula', 'name': 'CosmicNebula', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'AcidGrid', 'name': 'AcidGrid', 'storyboard_weight': 50, 'used_count': 0},
            {'_filename_key': 'LaserArray', 'name': 'LaserArray', 'storyboard_weight': 50, 'used_count': 0},
        ]
        
        sections = [{'section': 'Intro', 'duration': 15.0}, {'section': 'Verse', 'duration': 30.0}, {'section': 'Drop', 'duration': 30.0}]
        telemetry = {'genre': 'Techno', 'bpm': 130.0}
        
        results = bandit.select_modules_for_storyboard(sections, mock_modules, telemetry, historical_used_counts={})
        assigned_names = [r['module_name'] for r in results]
        assigned_ids = [r['assigned_module_id'] for r in results]
        assigned_fams = [extract_base_family(i) for i in assigned_ids]
        
        # 驗證單曲內絕對無相同名稱、無相同家族
        self.assertEqual(len(assigned_names), len(set(assigned_names)), '單曲內不可有重複模組名稱！')
        self.assertEqual(len(assigned_fams), len(set(assigned_fams)), '單曲內不可有重複模組家族！')

    def test_used_count_zero_bonus_gating_for_families(self):
        bandit = BanditInventorySelector()
        # 測試變體模組：雖本身 used_count=0，但 _family_used_count > 0 時，嚴禁發放 2.2 首秀紅利
        mod_with_used_family = {
            '_filename_key': 'Frozenbrush_99',
            'name': 'Frozenbrush',
            'storyboard_weight': 50,
            'used_count': 0,
            '_family_used_count': 5,
            '_name_used_count': 5
        }
        mod_truly_fresh = {
            '_filename_key': 'BrandNewSketch_01',
            'name': 'BrandNewSketch',
            'storyboard_weight': 50,
            'used_count': 0,
            '_family_used_count': 0,
            '_name_used_count': 0
        }
        sec_ctx = {'section': 'Verse', 'genre': 'Techno', 'target_energy': 0.5}
        
        score_variant = bandit.calculate_module_score(mod_with_used_family, sec_ctx, 100, 10.0, {})
        score_fresh = bandit.calculate_module_score(mod_truly_fresh, sec_ctx, 100, 10.0, {})
        
        self.assertGreater(score_fresh, score_variant * 3.0, '真正全新的模組得分應遠高於同家族換皮副本')

if __name__ == '__main__':
    unittest.main()
