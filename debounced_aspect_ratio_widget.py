from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer

class DebouncedAspectRatioWidget(QWidget):
    """
    防抖動 4K 預覽畫布容器 (Debounced Aspect Ratio Viewport)
    - 徹底消除拖拉窗口時高頻觸發 Chromium WebEngine 重新排版而引起的畫面黑屏與閃爍
    - 拖拉窗口時僅以 CSS 或視口 Margin 等比置中排版
    - 釋放滑鼠或拖拉停止 100ms 之後才觸發單次內部重繪通知
    """
    def __init__(self, inner_widget, ratio=16/9, parent=None):
        super().__init__(parent)
        self.inner_widget = inner_widget
        self.ratio = ratio

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(100) # 100ms 防抖
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(inner_widget)

    def resizeEvent(self, event):
        w = event.size().width()
        h = event.size().height()
        
        target_h = int(w / self.ratio)
        if target_h <= h:
            margin = (h - target_h) // 2
            self.layout().setContentsMargins(0, margin, 0, margin)
        else:
            target_w = int(h * self.ratio)
            margin = (w - target_w) // 2
            self.layout().setContentsMargins(margin, 0, margin, 0)

        # 啟動防抖計時器
        self._debounce_timer.start()
        super().resizeEvent(event)

    def _on_debounce_timeout(self):
        """尺寸調整穩定後調用更新"""
        if hasattr(self.inner_widget, 'update'):
            self.inner_widget.update()
