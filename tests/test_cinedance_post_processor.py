# -*- coding: utf-8 -*-
"""
Unit tests for ProceduralCameraRig 3D perspective and SpatialTriadRelighting in post_processor.py
"""
import unittest
import numpy as np
from post_processor import ProceduralCameraRig, SpatialTriadRelighting
from cinedance_compiler import CinedanceShotCompiler

class TestCinedancePostProcessor(unittest.TestCase):

    def test_procedural_camera_rig_3d(self):
        rig = ProceduralCameraRig()
        # Synthetic test image 1280x720 RGB
        dummy_img = np.zeros((720, 1280, 3), dtype=np.uint8)
        dummy_img[200:500, 400:800] = [200, 150, 100]

        shot_meta = CinedanceShotCompiler.compile_cinematic_shot(
            section_name="Drop",
            duration=4.0,
            composite_tension=0.92,
            framing_mode="fill"
        )

        # Apply with 3D perspective enabled and cinedance metadata
        out_img = rig.apply(
            dummy_img,
            t=1.5,
            beat_energy=0.8,
            section_name="Drop",
            cinedance_meta=shot_meta,
            enable_perspective_3d=True
        )

        self.assertEqual(out_img.shape, dummy_img.shape)
        self.assertEqual(out_img.dtype, np.uint8)
        # Should contain transformed pixels
        self.assertGreater(np.sum(out_img), 0)

    def test_spatial_triad_relighting(self):
        dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
        dummy_img[50:150, 50:150] = 120

        light_triad = {
            "key_light": {"intensity": 1.5, "direction_vector": [0.5, 0.5, 0.7]},
            "rim_light": {"intensity": 2.5, "direction_vector": [0.0, 0.0, -1.0]},
            "fill_light": {"intensity": 0.3, "direction_vector": [-0.5, 0.2, 0.8]}
        }

        lit_img = SpatialTriadRelighting.apply_relighting(dummy_img, light_triad, blend_weight=0.5)
        self.assertEqual(lit_img.shape, dummy_img.shape)
        # Edges should be brightened by rim light
        self.assertGreaterEqual(np.max(lit_img), np.max(dummy_img))

if __name__ == "__main__":
    unittest.main()
