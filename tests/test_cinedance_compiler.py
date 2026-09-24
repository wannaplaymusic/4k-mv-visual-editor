# -*- coding: utf-8 -*-
"""
Unit tests for cinedance_compiler.py
"""
import unittest
from cinedance_compiler import (
    ShotRiskAuditor,
    DynamicFOVCompiler,
    ElasticSpatialGrounder,
    LightTriadSolver,
    CinedanceShotCompiler
)

class TestCinedanceCompiler(unittest.TestCase):

    def test_dynamic_fov_compiler(self):
        # Test Verse FOV range
        verse_res = DynamicFOVCompiler.compile_fov("Verse", 0.5)
        self.assertGreaterEqual(verse_res["target_fov_deg"], 35.0)
        self.assertLessEqual(verse_res["target_fov_deg"], 55.0)
        self.assertIn("FOV", verse_res["optical_descriptor"])

        # Test Drop FOV range (should be wide)
        drop_res = DynamicFOVCompiler.compile_fov("Drop", 0.95)
        self.assertGreaterEqual(drop_res["target_fov_deg"], 90.0)
        self.assertLessEqual(drop_res["target_fov_deg"], 120.0)

        # Test Counterpoint solo (should be tight)
        counter_res = DynamicFOVCompiler.compile_fov("Drop", 0.95, is_shock_counterpoint=True)
        self.assertLessEqual(counter_res["target_fov_deg"], 36.0)

    def test_elastic_spatial_grounder(self):
        ground_low = ElasticSpatialGrounder.compute_spatial_anchors("fill", 0.2)
        ground_high = ElasticSpatialGrounder.compute_spatial_anchors("fill", 0.9)

        # Spring k should be stiffer when tension is low, looser when tension is high
        self.assertGreater(ground_low["elastic_spring_k"], ground_high["elastic_spring_k"])
        self.assertEqual(len(ground_low["subject_anchor_ndc"]), 3)
        self.assertIn("midground", ground_low["depth_layers"])

    def test_light_triad_solver(self):
        triad = LightTriadSolver.solve_light_triad("Chorus", 0.85, energy_hint=0.8)
        self.assertIn("key_light", triad)
        self.assertIn("rim_light", triad)
        self.assertIn("fill_light", triad)

        # Direction vector should be 3D unit vector
        key_vec = triad["key_light"]["direction_vector"]
        self.assertEqual(len(key_vec), 3)
        mag = (key_vec[0]**2 + key_vec[1]**2 + key_vec[2]**2)**0.5
        self.assertAlmostEqual(mag, 1.0, places=2)

        # Rim light intensity in chorus should be high
        self.assertGreaterEqual(triad["rim_light"]["intensity"], 1.5)

    def test_shot_risk_auditor(self):
        # Low risk shot
        low_risk = ShotRiskAuditor.audit_shot_risk(
            section_name="Verse",
            duration=4.0,
            composite_tension=0.3,
            camera_motion_speed=1.0,
            angular_velocity_deg=10.0,
            fov_deg=45.0
        )
        self.assertEqual(low_risk["risk_level"], "LOW")
        self.assertFalse(low_risk["suggest_split_cut"])

        # High risk shot (extreme angular velocity in short duration)
        high_risk = ShotRiskAuditor.audit_shot_risk(
            section_name="Drop",
            duration=1.2,
            composite_tension=0.95,
            camera_motion_speed=3.0,
            angular_velocity_deg=90.0,
            fov_deg=115.0,
            num_subjects=3
        )
        self.assertIn(high_risk["risk_level"], ["MEDIUM", "HIGH"])
        self.assertTrue(len(high_risk["risk_flags"]) >= 2)

    def test_cinedance_master_compiler(self):
        shot_meta = CinedanceShotCompiler.compile_cinematic_shot(
            section_name="Drop",
            duration=4.0,
            composite_tension=0.9,
            framing_mode="fill",
            camera_lookat_offset=(0.1, -0.05),
            energy_hint=0.85
        )
        self.assertIn("target_fov_deg", shot_meta)
        self.assertIn("light_triad", shot_meta)
        self.assertIn("risk_audit", shot_meta)
        self.assertIn("compiled_prompt_block", shot_meta)
        self.assertIn("Optics:", shot_meta["compiled_prompt_block"])
        self.assertIn("Geometry:", shot_meta["compiled_prompt_block"])
        self.assertIn("Lighting:", shot_meta["compiled_prompt_block"])

if __name__ == "__main__":
    unittest.main()
