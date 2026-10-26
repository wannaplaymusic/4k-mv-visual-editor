# -*- coding: utf-8 -*-
import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts.audit_and_deduplicate_visual_modules import normalize_code, compute_code_hash, score_candidate

class TestVisualDeduplicationEngine(unittest.TestCase):
    def test_normalize_code_ignores_comments_and_whitespace(self):
        code1 = """
        // Author: Risou
        /* Global setup */
        let x = 10;
        function setup() {
            createCanvas(600, 600);
        }
        """
        code2 = """
        // Forked by Student
        let x = 10;
        function setup(){
            createCanvas(600, 600);
        }
        """
        self.assertEqual(compute_code_hash(code1), compute_code_hash(code2), "兩段實質相同但註解/排版不同的代碼應產生相同的指紋")

    def test_score_candidate_prefers_used_and_clean_name(self):
        info_used = {
            "used_count": 2,
            "is_starred": False,
            "needs_qc": False,
            "date_added": "2026-10-01 12:00:00"
        }
        info_dup = {
            "used_count": 0,
            "is_starred": False,
            "needs_qc": True,
            "date_added": "2026-10-05 14:00:00"
        }
        score1 = score_candidate("15Red.json", info_used, "/dummy/thumb.jpg")
        score2 = score_candidate("15Red_1.json", info_dup, "/dummy/thumb.jpg")
        self.assertGreater(score1, score2, "已被影片使用過且名稱規範之模組評分必須遠高於未使用的副本")

if __name__ == '__main__':
    unittest.main()
