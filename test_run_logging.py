import os
import sys
import shutil
import tempfile
import json

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_run_logger import TestRunLogger

def test_logger_full_lifecycle():
    temp_dir = tempfile.mkdtemp()
    try:
        logger = TestRunLogger(
            batch_id="batch_20260920_230000",
            scope_name="測試範圍",
            total_items=3,
            log_dir=temp_dir
        )
        
        # 1. 測試第一個模組 - KEEP
        logger.start_item(1, 3, "particle_flow.json", "Particle Flow", 10001, "https://openprocessing.org/sketch/10001")
        logger.log_js_message("INFO", "Canvas initialized 1920x1080")
        logger.record_action("KEEP", {"is_favorite": True})
        
        # 2. 測試第二個模組 - DISCARD with reason & JS errors
        logger.start_item(2, 3, "glitch_cube.json", "Glitch Cube", 10002, "https://openprocessing.org/sketch/10002")
        logger.log_js_message("WARN", "High GPU memory usage", 120)
        logger.log_js_message("ERROR", "Uncaught TypeError: cannot read property 'bind' of undefined", 88)
        logger.record_action("DISCARD", {"reason": "預覽不正常"})
        
        # 3. 測試第三個模組 - DISCARD with another reason
        logger.start_item(3, 3, "game_controller.json", "Game Controller", 10003, "https://openprocessing.org/sketch/10003")
        logger.record_action("DISCARD", {"reason": "遊戲類別"})
        
        # 4. 結束會話
        summary = logger.finish_session()
        
        # 驗證統計
        assert summary["stats"]["kept"] == 1, f"Expected kept=1, got {summary['stats']['kept']}"
        assert summary["stats"]["discarded"] == 2, f"Expected discarded=2, got {summary['stats']['discarded']}"
        assert summary["stats"]["pass_rate_percent"] == 33.3, f"Expected pass_rate=33.3%, got {summary['stats']['pass_rate_percent']}"
        assert summary["stats"]["defect_breakdown"]["預覽不正常"] == 1
        assert summary["stats"]["defect_breakdown"]["遊戲類別"] == 1
        
        # 驗證檔案是否存在
        assert os.path.exists(logger.get_log_path()), "Log file does not exist!"
        assert os.path.exists(logger.get_json_path()), "JSON file does not exist!"
        
        # 驗證 .log 內容
        with open(logger.get_log_path(), "r", encoding="utf-8") as f:
            log_content = f.read()
            assert "🎬 4K MV 視覺整合編輯器 - 試運行審計日誌" in log_content
            assert "Particle Flow" in log_content
            assert "Uncaught TypeError" in log_content
            assert "ACTION: KEEP" in log_content
            assert "⭐ (評星最愛)" in log_content
            assert "ACTION: DISCARD" in log_content
            assert "預覽不正常" in log_content
            assert "遊戲類別" in log_content
            assert "33.3%" in log_content
            
        # 驗證 .json 內容
        with open(logger.get_json_path(), "r", encoding="utf-8") as f:
            json_data = json.load(f)
            assert json_data["batch_id"] == "batch_20260920_230000"
            assert len(json_data["items"]) == 3
            assert json_data["items"][1]["js_errors"][0] == "Line 88: Uncaught TypeError: cannot read property 'bind' of undefined"
            
        print("✅ [TestRunLogger] Core lifecycle tests passed successfully!")
        return logger.get_log_path(), temp_dir, summary
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

def test_ui_components(log_path, temp_dir, summary):
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    
    from batch_importer import TestRunLogViewerDialog, TestRunSummaryDialog, RejectReasonDialog, TestRunDialog
    
    # 1. 測試 TestRunLogViewerDialog
    viewer = TestRunLogViewerDialog(log_path)
    assert "試運行審計日誌" in viewer.windowTitle()
    assert len(viewer.raw_content) > 0
    viewer.filter_content("Particle Flow")
    assert "Particle Flow" in viewer.text_edit.toPlainText()
    viewer.filter_content("")
    assert len(viewer.text_edit.toPlainText()) == len(viewer.raw_content)
    print("✅ [TestRunLogViewerDialog] Initialized and content filtered successfully!")

    # 2. 測試 TestRunSummaryDialog
    summary_dlg = TestRunSummaryDialog(summary, log_path, temp_dir)
    assert "試運行與清理成果報告" in summary_dlg.windowTitle()
    assert summary_dlg.summary_data["stats"]["kept"] == 1
    assert summary_dlg.summary_data["stats"]["discarded"] == 2
    print("✅ [TestRunSummaryDialog] Metrics cards and defect breakdown rendered successfully!")

    # 3. 測試 RejectReasonDialog
    reject_dlg = RejectReasonDialog()
    assert reject_dlg.reason is None
    reject_dlg.choose_reason("預覽不正常")
    assert reject_dlg.reason == "預覽不正常"
    print("✅ [RejectReasonDialog] Reason selection tested successfully!")

    # 4. 測試 TestRunDialog 實例化與 Console Drawer
    sample_items = [{
        "id": 9999,
        "title": "Neon Wave",
        "url": "https://openprocessing.org/sketch/9999",
        "code": "function setup(){ createCanvas(400, 400); }",
        "filepath": os.path.join(temp_dir, "neon_wave.json"),
        "filename": "neon_wave.json",
        "save_dir": temp_dir
    }]
    test_run_dlg = TestRunDialog(sample_items, batch_id="batch_test", scope_name="測試範圍")
    assert test_run_dlg.logger is not None
    assert test_run_dlg.console_container is not None
    assert test_run_dlg.live_console_edit is not None
    test_run_dlg.append_live_console("🔴 ERROR", "Line 10: SyntaxError", "#ef4444")
    assert "SyntaxError" in test_run_dlg.live_console_edit.toHtml()
    test_run_dlg.close()
    print("✅ [TestRunDialog] Instantiation, live console, and logger integration verified!")

if __name__ == "__main__":
    log_path, temp_dir, summary = test_logger_full_lifecycle()
    try:
        test_ui_components(log_path, temp_dir, summary)
        print("🎉 [ALL TESTS PASSED] Test Run Audit Logging System verified completely!")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
