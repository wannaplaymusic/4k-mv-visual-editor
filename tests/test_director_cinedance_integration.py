# -*- coding: utf-8 -*-
"""
Integration tests for director_choreographer and cinedance_compiler
"""
import unittest
from director_choreographer import DirectorChoreographer

class TestDirectorCinedanceIntegration(unittest.TestCase):

    def test_plan_cinematic_shots_with_cinedance(self):
        choreographer = DirectorChoreographer()

        storyboard_sections = [
            {"section": "Intro", "duration": 8.0},
            {"section": "Verse", "duration": 16.0},
            {"section": "Build", "duration": 8.0},
            {"section": "Drop", "duration": 16.0},
            {"section": "Outro", "duration": 8.0}
        ]

        audio_telemetry = {
            "bpm": 128.0,
            "duration": 56.0
        }

        assigned_modules = [
            {"module_name": "mod_intro", "target_energy": 0.2},
            {"module_name": "mod_verse", "target_energy": 0.45},
            {"module_name": "mod_build", "target_energy": 0.75},
            {"module_name": "mod_drop", "target_energy": 0.95},
            {"module_name": "mod_outro", "target_energy": 0.15}
        ]

        shots, intensity = choreographer.plan_cinematic_shots(
            storyboard_sections=storyboard_sections,
            audio_telemetry=audio_telemetry,
            assigned_modules=assigned_modules
        )

        self.assertEqual(len(shots), 5)
        self.assertEqual(len(intensity), 5)

        for shot in shots:
            self.assertIn("cinedance_optical_meta", shot)
            cm = shot["cinedance_optical_meta"]
            self.assertIn("target_fov_deg", cm)
            self.assertIn("light_triad", cm)
            self.assertIn("risk_audit", cm)
            self.assertIn("compiled_prompt_block", cm)

        # Drop shot should have wider FOV than Verse shot
        verse_fov = shots[1]["cinedance_optical_meta"]["target_fov_deg"]
        drop_fov = shots[3]["cinedance_optical_meta"]["target_fov_deg"]
        self.assertGreater(drop_fov, verse_fov)

        # Drop shot should have higher rim light intensity than Intro
        intro_rim = shots[0]["cinedance_optical_meta"]["light_triad"]["rim_light"]["intensity"]
        drop_rim = shots[3]["cinedance_optical_meta"]["light_triad"]["rim_light"]["intensity"]
        self.assertGreater(drop_rim, intro_rim)

if __name__ == "__main__":
    unittest.main()
