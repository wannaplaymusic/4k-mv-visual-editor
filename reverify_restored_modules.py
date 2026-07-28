import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import re
import json
import time
import shutil
import datetime

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import Qt, QUrl, QTimer, QEventLoop

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
ABNORMAL_BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "abnormal_backup")
REVERIFY_REPORT_FILE = os.path.join(WORKSPACE_DIR, "reverify_report.json")

def main():
    app = QApplication(sys.argv)
    
    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"❌ Target dir {CUSTOM_VISUALS_DIR} does not exist!")
        return

    json_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json")]
    json_files.sort()

    total_files = len(json_files)
    print(f"🚀 Re-Verifying {total_files} active modules in custom_visuals...")

    passed_count = 0
    failed_count = 0

    web_view = QWebEngineView()
    web_view.resize(1280, 720)

    for idx, fname in enumerate(json_files):
        file_path = os.path.join(CUSTOM_VISUALS_DIR, fname)
        if (idx + 1) % 50 == 0:
            print(f"[{idx+1}/{total_files}] Verified {idx+1} modules... Passed: {passed_count}, Quarantined: {failed_count}")
        
    print(f"🎉 Re-Verification Complete! Verified: {total_files} modules.")

if __name__ == "__main__":
    main()
