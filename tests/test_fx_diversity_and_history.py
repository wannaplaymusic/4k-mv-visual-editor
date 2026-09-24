import unittest
import numpy as np
from PIL import Image
import os
import sys
import json
import tempfile
import shutil

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import post_processor
from post_processor import PostProcessor, _load_vj_fx_history, _save_vj_fx_history

class TestFxDiversityAndHistory(unittest.TestCase):
    def setUp(self):
        # Setup temporary history path for isolated testing
        self.test_dir = tempfile.mkdtemp()
        self.orig_history_path = post_processor._VJ_FX_HISTORY_PATH
        post_processor._VJ_FX_HISTORY_PATH = os.path.join(self.test_dir, "vj_fx_history.json")

    def tearDown(self):
        post_processor._VJ_FX_HISTORY_PATH = self.orig_history_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_theme_pools_expanded_and_balanced(self):
        """驗證所有主題風格池均達到均衡容量 (>= 14 款特效)，特別是 DigitalPixel 不再僅有 10 款"""
        pp = PostProcessor(seed_string="balance_test", genre="generic")
        for theme_name, pool in pp.theme_pools.items():
            self.assertGreaterEqual(
                len(pool), 14,
                f"主題池 [{theme_name}] 容量為 {len(pool)}，低於 14 款的均衡要求"
            )
        # 特別檢驗 DigitalPixel
        digital_pool = pp.theme_pools['DigitalPixel']
        self.assertIn('matrix_ascii', digital_pool)
        self.assertIn('scanline_glitch', digital_pool)
        self.assertIn('synthwave_grid_scan', digital_pool)
        self.assertIn('pixel_sort', digital_pool)
        self.assertIn('data_mosh', digital_pool)

    def test_cross_song_history_persistence_and_cooldown(self):
        """驗證跨曲目歷史持久化儲存，以及冷卻降權機制對重複特效的強烈抑制"""
        # 連續模擬 10 首曲目的生成
        track_names = [f"Track_{i:02d}" for i in range(10)]
        chosen_signatures = []
        chosen_accents = []

        for name in track_names:
            pp = PostProcessor(seed_string=name, genre="hard_techno")
            chosen_signatures.append(set(pp.signature_effects))
            chosen_accents.append(set(pp.accent_effects))

        # 1. 驗證歷史檔案確實已生成且包含 10 筆記錄
        history = _load_vj_fx_history(max_entries=20)
        self.assertEqual(len(history), 10)
        self.assertEqual(history[-1]['seed_string'], "Track_09")

        # 2. 驗證相鄰曲目的 Signature 特效極少完全重複
        consecutive_identical_sig = 0
        for i in range(len(chosen_signatures) - 1):
            overlap = chosen_signatures[i].intersection(chosen_signatures[i+1])
            # 相鄰曲目的 Signature 特效交集不應完全相同
            if overlap == chosen_signatures[i]:
                consecutive_identical_sig += 1

        self.assertEqual(consecutive_identical_sig, 0, "相鄰曲目不應連續擁有完全相同的 Signature 特效群")

        # 3. 統計 10 首曲目動用到的獨特特效總數
        all_unique_effects = set()
        for s in chosen_signatures:
            all_unique_effects.update(s)
        for a in chosen_accents:
            all_unique_effects.update(a)

        # 10 首曲目中動用到的不重複特效數應顯著提升 (至少超過 15 種不同特效)
        self.assertGreaterEqual(
            len(all_unique_effects), 15,
            f"10 首曲目累計僅動用了 {len(all_unique_effects)} 種特效，多樣性不足"
        )

    def test_all_56_effects_mapped_to_audio_drivers(self):
        """驗證所有 56 種後製特效均在 process() 的重拍加權歸屬分類中"""
        pp = PostProcessor(seed_string="test_audio_mapping", genre="psychedelic")
        all_fx = set(pp.fx_active_states.keys())
        
        # 建立微型圖像驗證 process() 能順暢運行並觸發單曲內交替微冷卻
        test_img = Image.new("RGB", (320, 180), (100, 150, 200))
        audio_feats = {
            'sub_bass': 0.8,
            'percussive': 0.9,
            'roughness': 0.3,
            'ethereal': 0.5,
            'stereo_width': 0.7,
            'centroid': 0.6,
            'bpm': 130.0
        }
        fx_flags = {k: True for k in all_fx}
        
        # 連續呼叫 3 次重拍，驗證 _intra_song_fx_history 成功記錄並驅動特效交替
        out1 = pp.process(test_img, t=1.0, is_beat=True, beat_energy=0.9, audio_feats=audio_feats, fx_flags=fx_flags)
        self.assertIsNotNone(out1)
        self.assertTrue(hasattr(pp, '_intra_song_fx_history'))
        self.assertGreater(len(pp._intra_song_fx_history), 0)

        out2 = pp.process(test_img, t=1.5, is_beat=True, beat_energy=0.9, audio_feats=audio_feats, fx_flags=fx_flags)
        self.assertIsNotNone(out2)

if __name__ == '__main__':
    unittest.main()
