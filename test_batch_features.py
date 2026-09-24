import os
import sys
import json
import shutil
import unittest

from batch_history_manager import BatchHistoryManager
from batch_importer import validate_visual_module_eligibility, DEFAULT_FILTER_OPTIONS

class TestBatchFeatures(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.dirname(os.path.abspath(__file__))
        self.mgr = BatchHistoryManager(self.test_dir)

    def test_legacy_baseline_protection(self):
        """驗證歷史基準模組受永久保護"""
        baseline = self.mgr.history_data.get("legacy_baseline", {})
        self.assertTrue(baseline.get("initialized"))
        self.assertGreater(baseline.get("count", 0), 1000)
        
        # 測試隨機抽取基準檔案，確認 is_legacy_file 判定為 True
        first_file = baseline["files"][0]
        self.assertTrue(self.mgr.is_legacy_file(first_file))

    def test_filter_options_games(self):
        """測試遊戲類別過濾選項"""
        game_code = "let score = 0; function draw() { if(lives <= 0) { gameOver(); } score += 10; }"
        # 勾選 skip_games: 應被排除
        ok, reason = validate_visual_module_eligibility("Flappy Bird Game", game_code, filter_options={"skip_games": True})
        self.assertFalse(ok)
        self.assertIn("遊戲", reason)

        # 取消勾選 skip_games: 應通過（假設其他項未開啟）
        ok2, _ = validate_visual_module_eligibility("Flappy Bird Game", game_code, filter_options={"skip_games": False})
        self.assertTrue(ok2)

    def test_filter_options_text_heavy(self):
        """測試純文字/排版字型展示模組過濾"""
        text_code = """
        function setup() { textFont('Arial'); textSize(32); }
        function draw() {
            text("Hello", 10, 10);
            text("World", 10, 20);
            text("Typography", 10, 30);
            text("Test", 10, 40);
            text("Pangram", 10, 50);
            text("ASCII", 10, 60);
        }
        """
        ok, reason = validate_visual_module_eligibility("Typography Art", text_code, filter_options={"skip_text_heavy": True})
        self.assertFalse(ok)
        self.assertTrue("文字" in reason or "Typography" in reason)

        ok2, _ = validate_visual_module_eligibility("Typography Art", text_code, filter_options={"skip_text_heavy": False})
        self.assertTrue(ok2)

    def test_filter_options_static(self):
        """測試純靜態模組過濾"""
        static_code = "function setup() { createCanvas(800, 800); background(0); rect(10, 10, 50, 50); noLoop(); }"
        ok, reason = validate_visual_module_eligibility("Static Shape", static_code, filter_options={"skip_static": True})
        self.assertFalse(ok)
        self.assertIn("noLoop", reason)

        ok2, _ = validate_visual_module_eligibility("Static Shape", static_code, filter_options={"skip_static": False})
        self.assertTrue(ok2)

    def test_batch_lifecycle_and_rollback_restore(self):
        """測試獨立批次建立、登記、一鍵回溯 (Rollback) 與還原 (Restore)"""
        custom_visuals = os.path.join(self.test_dir, "custom_visuals")
        test_filename = "__test_mock_module_batch.json"
        test_filepath = os.path.join(custom_visuals, test_filename)
        
        # 1. 建立假批次
        batch_id, batch_date = self.mgr.start_new_batch("https://openprocessing.org/test", {"skip_games": True})
        
        # 2. 寫入模擬模組
        with open(test_filepath, "w", encoding="utf-8") as f:
            json.dump({"name": "__test_mock", "code": "// mock", "batch_id": batch_id, "batch_date": batch_date}, f)
            
        self.mgr.record_imported_item(batch_id, "999999", "Mock Module", test_filename)
        self.assertTrue(os.path.exists(test_filepath))

        # 3. 測試一鍵回溯 (Rollback)
        ok, count, msg = self.mgr.rollback_batch(batch_id)
        self.assertTrue(ok)
        self.assertEqual(count, 1)
        # 模組應已從主目錄移走
        self.assertFalse(os.path.exists(test_filepath))
        # 應位於備份目錄中
        backup_path = os.path.join(self.mgr.backup_dir, batch_id, test_filename)
        self.assertTrue(os.path.exists(backup_path))

        # 4. 測試一鍵還原 (Restore)
        ok_res, res_count, res_msg = self.mgr.restore_batch(batch_id)
        self.assertTrue(ok_res)
        self.assertEqual(res_count, 1)
        # 模組應重新回到主目錄
        self.assertTrue(os.path.exists(test_filepath))

        # 清理測試模組
        if os.path.exists(test_filepath):
            os.remove(test_filepath)
        # 清理測試批次記錄
        self.mgr.history_data["batches"] = [b for b in self.mgr.history_data["batches"] if b["batch_id"] != batch_id]
        self.mgr._save_history()

if __name__ == "__main__":
    unittest.main()
