# -*- coding: utf-8 -*-
"""
啟動 Ambient / Drone 專屬沉浸式視覺工作台
使用方式:
    ./.venv/bin/python3 launch_ambient_studio.py
"""
import sys
import os

# 設置 Chromium 沙盒與 GPU 參數
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-web-security --enable-gpu --ignore-gpu-blocklist --enable-webgl --enable-accelerated-2d-canvas"

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt
from ambient_drone_studio_tab import AmbientDroneStudioTab

class AmbientStandaloneWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CHRONOS // Ambient & Drone 4K 沉浸式視覺整合工作室")
        self.resize(1440, 900)
        self.studio_tab = AmbientDroneStudioTab(self)
        self.setCentralWidget(self.studio_tab)

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = AmbientStandaloneWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
