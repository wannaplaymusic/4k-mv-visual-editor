# -*- coding: utf-8 -*-
"""
Test p5_template_generator for CINEDANCE spatial anchors
"""
import unittest
from p5_template_generator import P5SurrealTemplateGenerator

class TestP5TemplateCinedance(unittest.TestCase):

    def test_cinedance_spatial_anchors_in_p5(self):
        theme_meta = {
            "title": "Quantum Odyssey",
            "concept_manifesto": "Test Manifesto"
        }
        orchestrated_scene = {
            "topology": "orbital",
            "elements": [
                {"role": "hero", "z_depth": 0.5},
                {"role": "satellite", "z_depth": 0.3}
            ]
        }
        js_code = P5SurrealTemplateGenerator.generate_multi_element_masterpiece_script(
            asset_id="test_asset",
            theme_meta=theme_meta,
            orchestrated_scene=orchestrated_scene,
            style_name="cyberpunk"
        )

        self.assertIn("cinedanceMeta", js_code)
        self.assertIn("elastic_spring_k", js_code)
        self.assertIn("horizon_ndc_y", js_code)
        self.assertIn("subject_anchor_ndc", js_code)

if __name__ == "__main__":
    unittest.main()
