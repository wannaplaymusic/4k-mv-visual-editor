---
name: pyside-web-bridge
description: 基於 PySide/PyQt 與 QWebEngineView 的混合軟體架構，實作高速雙向 Qt/JS WebBridge 通訊與高效多線程資源管理。
---

# PySide Web Bridge Skill

本 Skill 專門用於 PySide/PyQt 桌面視窗軟體與內嵌網頁畫布（WebGL / Canvas / p5.js）的混合架構開發，整理自本專案的 `main.py`。

## 1. QWebEngineView 與 JavaScript (QWebChannel) 雙向橋接

利用 QWebChannel 機制，可實作 Python 後端高頻發送音訊數據給前端 JS 渲染，以及前端 JS Console/Alert 自動對接至 Python Log 的邏輯：

### Python 端宣告 (Bridge & Page)

```python
from PySide6.QtCore import QObject, Slot, Signal
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

class WebBridge(QObject):
    """定義供前端 JavaScript 呼叫的 Slot，以及主動發送給前端的 Signal"""
    # 定義發送給 JS 的信號
    sig_beat_triggered = Signal()
    sig_audio_data = Signal(dict)

    @Slot(str)
    def log_from_js(self, message):
        print(f"[JS Console] {message}")

# 在視窗元件中綁定 Channel
class WebEngineContainer(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel = QWebChannel()
        self.bridge = WebBridge()
        
        # 註冊橋接對象名稱為 'pyBridge'
        self.channel.registerObject('pyBridge', self.bridge)
        self.page().setWebChannel(self.channel)
```

### HTML/JS 前端接收

在 HTML 模板中加載 `qwebchannel.js`，初始化後即可直接調用 `pyBridge` 或監聽信號：

```html
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
  new QWebChannel(qt.webChannelTransport, function (channel) {
    window.pyBridge = channel.objects.pyBridge;
    
    // 呼叫 Python 後端
    pyBridge.log_from_js("Web channel initialized successfully!");

    // 監聽 Python 信號
    pyBridge.sig_audio_data.connect(function(data) {
      // 接收 Python 發送過來的即時音訊特徵 (如 bass, centroid 等)
      window.live_centroid = data.centroid;
      window.sub_bass = data.sub_bass;
    });

    pyBridge.sig_beat_triggered.connect(function() {
      window.isBeat = true;
      setTimeout(() => { window.isBeat = false; }, 80);
    });
  });
</script>
```

## 2. 16:9 Canvas 適配封裝器 (AspectRatioWidget)

在桌面視窗佈局中，往往需要維持固定的渲染縱橫比（16:9），可以使用自訂 PyQt 元件來約束其寬高比例：

```python
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QSize

class AspectRatioWidget(QWidget):
    """保持 16:9 比例的 PyQt 容器元件"""
    def __init__(self, widget, ratio=16.0/9.0, parent=None):
        super().__init__(parent)
        self.ratio = ratio
        self.widget = widget
        widget.setParent(self)

    def resizeEvent(self, event):
        w = event.size().width()
        h = event.size().height()
        
        if w / h > self.ratio:
            # 視窗太寬，以高度為基準
            new_h = h
            new_w = int(h * self.ratio)
        else:
            # 視窗太高，以寬度為基準
            new_w = w
            new_h = int(w / self.ratio)
            
        x = (w - new_w) // 2
        y = (h - new_h) // 2
        self.widget.setGeometry(x, y, new_w, new_h)
```
