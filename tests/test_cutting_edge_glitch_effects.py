import unittest
import numpy as np
from PIL import Image
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from post_processor import PostProcessor

class TestCuttingEdgeGlitchEffects(unittest.TestCase):
    def setUp(self):
        self.processor = PostProcessor(seed_string="glitch_matrix_seed", genre="hard_techno")
        # 建立測試影像 (720p 測試加速)
        self.w, self.h = 1280, 720
        y, x = np.mgrid[0:self.h, 0:self.w]
        grid = ((np.sin(x / 25.0) + np.cos(y / 25.0) + 2.0) * 60).astype(np.uint8)
        self.test_img = np.dstack([grid, np.roll(grid, 25, axis=1), np.roll(grid, 50, axis=0)])
        self.test_pil = Image.fromarray(self.test_img)

    def test_fx_registration(self):
        """驗證 5 大前沿故障特效均已在 fx_active_states 中註冊"""
        effects = [
            'quantum_decoherence',
            'latent_hallucination',
            'tape_head_drag',
            'huffman_entropy_collapse',
            'spectral_fractal_shear'
        ]
        for fx in effects:
            self.assertIn(fx, self.processor.fx_active_states, f"{fx} should be registered in fx_active_states")

    def test_quantum_decoherence_variants(self):
        """驗證量子退相干 5 大變種 (0~4) 正常運行"""
        for variant in range(5):
            out = self.processor.apply_quantum_decoherence_custom(
                self.test_img,
                t=2.5 + variant * 0.3,
                intensity=0.8,
                stereo_width=0.7,
                turbulence=0.6,
                is_beat=(variant == 4),
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray)
            self.assertEqual(out.shape, self.test_img.shape)
            self.assertEqual(out.dtype, np.uint8)

    def test_latent_hallucination_variants(self):
        """驗證潛空間幻覺 5 大變種 (0~4) 正常運行"""
        for variant in range(5):
            out = self.processor.apply_latent_hallucination_custom(
                self.test_img,
                t=1.8 + variant * 0.4,
                intensity=0.75,
                harmonic=0.7,
                chord_brightness=0.6,
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray)
            self.assertEqual(out.shape, self.test_img.shape)
            self.assertEqual(out.dtype, np.uint8)

    def test_tape_head_drag_variants(self):
        """驗證磁帶咬帶與刮痕 5 大變種 (0~4) 正常運行"""
        for variant in range(5):
            out = self.processor.apply_tape_head_drag_custom(
                self.test_img,
                t=3.1 + variant * 0.5,
                intensity=0.85,
                sub_bass=0.8,
                percussive=0.7,
                is_beat=(variant == 0),
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray)
            self.assertEqual(out.shape, self.test_img.shape)
            self.assertEqual(out.dtype, np.uint8)

    def test_huffman_entropy_collapse_variants(self):
        """驗證 JPEG 宏塊熵編碼崩毀 5 大變種 (0~4) 正常運行"""
        for variant in range(5):
            out = self.processor.apply_huffman_entropy_collapse_custom(
                self.test_img,
                t=0.9 + variant * 0.4,
                intensity=0.8,
                roughness=0.75,
                beat_energy=0.85,
                is_beat=(variant == 2),
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray)
            self.assertEqual(out.shape, self.test_img.shape)
            self.assertEqual(out.dtype, np.uint8)

    def test_spectral_fractal_shear_variants(self):
        """驗證時空頻譜碎形撕裂 5 大變種 (0~4) 正常運行"""
        synthetic_samples = np.sin(np.linspace(0, 32 * np.pi, 256)).astype(np.float32)
        for variant in range(5):
            out = self.processor.apply_spectral_fractal_shear_custom(
                self.test_img,
                t=4.2 + variant * 0.3,
                intensity=0.85,
                harmonic=0.8,
                percussive=0.75,
                audio_samples=synthetic_samples,
                is_beat=(variant == 2),
                variant=variant
            )
            self.assertIsInstance(out, np.ndarray)
            self.assertEqual(out.shape, self.test_img.shape)
            self.assertEqual(out.dtype, np.uint8)

    def test_full_pipeline_with_all_glitches(self):
        """驗證在啟用全部 5 大故障特效時，PostProcessor.process 全流程順暢執行"""
        fx_flags = {
            'quantum_decoherence': True,
            'latent_hallucination': True,
            'tape_head_drag': True,
            'huffman_entropy_collapse': True,
            'spectral_fractal_shear': True,
            'lens_defocus': True,
            'ocular_tremor': True
        }
        # 強制激活
        for k in fx_flags:
            self.processor.fx_active_states[k] = 1.0

        audio_feats = {
            'sub_bass': 0.8,
            'percussive': 0.85,
            'spectral_roughness': 0.7,
            'lowpass': 0.6,
            'ethereal': 0.5,
            'arousal': 0.9,
            'valence': 0.4,
            'stereo_width': 0.8,
            'harmonic': 0.7,
            'spectral_centroid': 0.65,
            'chord_name': 'F#m',
            'chord_brightness': 0.5,
            'audio_samples': np.sin(np.linspace(0, 16 * np.pi, 128)).astype(np.float32)
        }

        result = self.processor.process(
            self.test_pil,
            t=1.5,
            is_beat=True,
            beat_energy=0.9,
            audio_feats=audio_feats,
            fx_flags=fx_flags,
            fx_prob=1.0,
            fx_intensity=0.85,
            section_name='Drop'
        )
        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (self.w, self.h))

if __name__ == '__main__':
    unittest.main()
