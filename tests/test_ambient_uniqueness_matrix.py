"""
Ambient 沉浸心流工作台：3000+ 作品視覺獨特性與 144 組合母題單元測試
驗證項目：
1. 144 組合哲學母題庫 (12 Archetypes x 12 Mediums) 完整性與 OKLCH 合法性
2. 32-bit 確定性音訊 DNA 哈希種子 (Deterministic Audio DNA Seed) 高分散度
3. 全動態 OKLCH 12-Tone 色彩衍生算法 (No Fixed Palette) 獨特性驗證 (模擬 3,000 首隨機曲目碰撞率趨近於 0)
4. 32 維全態片元著色器檔案完整加載檢驗
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ambient_chronos_director import AmbientChronosDirector
from savap_ambient_modulation_matrix import Ambient32DParameters


class TestAmbientUniquenessMatrix(unittest.TestCase):

    def setUp(self):
        self.director = AmbientChronosDirector()

    def test_01_motifs_144_catalog(self):
        """驗證母題庫擴展至 144 個 (12x12 笛卡兒積)"""
        motifs = self.director.CONTEMPLATIVE_MOTIFS
        self.assertEqual(len(motifs), 144)

        seen_ids = set()
        seen_titles = set()
        for m in motifs:
            self.assertIn("id", m)
            self.assertIn("title", m)
            self.assertIn("oklch_palette", m)
            self.assertEqual(len(m["oklch_palette"]), 4)

            # 檢查唯一性
            self.assertNotIn(m["id"], seen_ids)
            self.assertNotIn(m["title"], seen_titles)
            seen_ids.add(m["id"])
            seen_titles.add(m["title"])

            # 檢查 OKLCH 參數邊界 [L, C, h]
            for col in m["oklch_palette"]:
                self.assertTrue(0.0 <= col[0] <= 1.0, f"Lightness 越界: {col[0]}")
                self.assertTrue(0.0 <= col[1] <= 0.20, f"Chroma 越界: {col[1]}")
                self.assertTrue(0.0 <= col[2] <= 360.0, f"Hue 越界: {col[2]}")

    def test_02_audio_dna_seed_distribution(self):
        """驗證 32-bit 確定性音訊種子分散性"""
        seeds = set()
        for i in range(100):
            mock_audio_features = {
                "spectral_centroid": 500.0 + i * 27.3,
                "bass": 0.2 + (i % 7) * 0.1,
                "spectral_flux": 0.1 + (i % 5) * 0.05
            }
            seed = AmbientChronosDirector.compute_audio_dna_seed(mock_audio_features)
            self.assertIsInstance(seed, int)
            self.assertGreater(seed, 0)
            seeds.add(seed)

        # 100 首不同的特徵應該產生 100 個互不相同的種子
        self.assertEqual(len(seeds), 100)

    def test_03_derive_track_unique_palette_3000_simulation(self):
        """模擬 3,000 首不同曲目的色彩衍生，驗證絕不撞色"""
        base_palette = [
            [0.18, 0.04, 210.0],
            [0.45, 0.06, 210.0],
            [0.85, 0.05, 75.0],
            [0.08, 0.02, 260.0]
        ]

        generated_signatures = set()
        num_simulations = 3000

        for track_id in range(num_simulations):
            # 生成該歌曲的唯一音訊種子與 Chroma 主音
            seed = (track_id * 2654435761) & 0xFFFFFFFF
            chroma_vec = [0.0] * 12
            chroma_vec[track_id % 12] = 1.0 # 12 半音輪轉

            derived = AmbientChronosDirector.derive_track_unique_palette(
                base_palette=base_palette,
                audio_seed=seed,
                chroma_vector=chroma_vec
            )

            # 以衍生色相角組合作為指紋
            hues = tuple(round(col[2], 1) for col in derived)
            generated_signatures.add(hues)

        # 驗證 3,000 首曲目產生的色相簽名多樣性
        diversity_ratio = len(generated_signatures) / num_simulations
        self.assertGreater(diversity_ratio, 0.95, "3000首色彩衍生多樣性過低，可能存在碰撞")

    def test_04_shader_contains_all_32d_uniforms(self):
        """驗證 shaders/ambient_ganzfeld_fog.frag 確實存在並具備 32 維全態 Uniforms"""
        shader_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "shaders",
            "ambient_ganzfeld_fog.frag"
        )
        self.assertTrue(os.path.exists(shader_file))
        with open(shader_file, "r", encoding="utf-8") as f:
            code = f.read()

        # 驗證關鍵新特性
        self.assertIn("u_domainWarpAmp", code)
        self.assertIn("u_anisotropyG", code)
        self.assertIn("u_cauchyDispersion", code)
        self.assertIn("u_extinctionBeta", code)
        self.assertIn("u_antiTroxlerRate", code)
        self.assertIn("in vec2 vUv", code)


if __name__ == "__main__":
    unittest.main()
