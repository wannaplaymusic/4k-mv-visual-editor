import unittest
import numpy as np
from PIL import Image
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from post_processor import PostProcessor

class TestLensDefocusAndOcularTremor(unittest.TestCase):
    def setUp(self):
        self.processor = PostProcessor(seed_string="unit_test_seed", genre="psychedelic")
        # Create a sample synthetic test image (720p for fast test execution)
        self.w, self.h = 1280, 720
        y, x = np.mgrid[0:self.h, 0:self.w]
        grid = ((np.sin(x / 30.0) + np.cos(y / 30.0) + 2.0) * 60).astype(np.uint8)
        self.test_img = np.dstack([grid, np.roll(grid, 20, axis=1), np.roll(grid, 40, axis=0)])
        self.test_pil = Image.fromarray(self.test_img)

    def test_fx_registration(self):
        """驗證 lens_defocus 與 ocular_tremor 成功註冊於 fx_active_states"""
        self.assertIn('lens_defocus', self.processor.fx_active_states)
        self.assertIn('ocular_tremor', self.processor.fx_active_states)

    def test_lens_defocus_variants(self):
        """驗證鏡頭失焦 5 大變種 (0~4) 正確執行且形狀與數據類型保持一致"""
        for variant in range(5):
            out = self.processor.apply_lens_defocus_custom(
                self.test_img,
                intensity=0.8,
                lowpass_val=0.6,
                ethereal=0.5,
                is_beat=(variant % 2 == 1),
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray, f"Variant {variant} should return ndarray")
            self.assertEqual(out.shape, self.test_img.shape, f"Variant {variant} shape mismatch")
            self.assertEqual(out.dtype, np.uint8, f"Variant {variant} dtype should be uint8")

    def test_ocular_tremor_variants(self):
        """驗證生理眼球顫動 5 大變種 (0~4) 正確執行且形狀與數據類型保持一致"""
        for variant in range(5):
            out = self.processor.apply_ocular_tremor_custom(
                self.test_img,
                t=1.234 + variant * 0.5,
                intensity=0.75,
                beat_energy=0.8,
                sub_bass=0.7,
                roughness=0.6,
                is_beat=(variant == 1),
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray, f"Variant {variant} should return ndarray")
            self.assertEqual(out.shape, self.test_img.shape, f"Variant {variant} shape mismatch")
            self.assertEqual(out.dtype, np.uint8, f"Variant {variant} dtype should be uint8")

    def test_full_process_integration(self):
        """驗證 PostProcessor.process 能在開啟新特效的情況下順暢運行全域管線"""
        fx_flags = {
            'lens_defocus': True,
            'ocular_tremor': True,
            'color_boost': True,
            'sharpen': True
        }
        # 強制啟用對應的活躍狀態
        self.processor.fx_active_states['lens_defocus'] = 1.0
        self.processor.fx_active_states['ocular_tremor'] = 1.0

        audio_feats = {
            'sub_bass': 0.7,
            'percussive': 0.8,
            'spectral_roughness': 0.5,
            'lowpass': 0.65,
            'ethereal': 0.7,
            'arousal': 0.8,
            'valence': 0.6,
            'stereo_width': 0.65,
            'harmonic': 0.5,
            'spectral_centroid': 0.5,
            'chord_name': 'Am',
            'chord_brightness': 0.6
        }

        result = self.processor.process(
            self.test_pil,
            t=2.5,
            is_beat=True,
            beat_energy=0.85,
            audio_feats=audio_feats,
            fx_flags=fx_flags,
            fx_prob=1.0,
            fx_intensity=0.8,
            section_name='Drop'
        )
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (self.w, self.h))

if __name__ == '__main__':
    unittest.main()
