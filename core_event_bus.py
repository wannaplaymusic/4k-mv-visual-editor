from PyQt6.QtCore import QObject, pyqtSignal

class GlobalEventBus(QObject):
    """
    4K MV Visual Integration Editor 全域無鎖事件總線 (Lock-Free EventBus)
    - 將 UI 層、音訊分析服務、渲染離屏管線與雲端排程進行解耦
    - 替換模組間的強耦合跨層直接引用
    """
    _instance = None

    # 音訊相關信號
    audio_loaded = pyqtSignal(str, float)       # file_path, duration
    audio_feature_updated = pyqtSignal(dict)    # stems & spectral features
    playback_position_changed = pyqtSignal(float) # current_time

    # 渲染與時間軸相關信號
    storyboard_updated = pyqtSignal(list)
    render_requested = pyqtSignal(dict)         # export configs
    render_progress = pyqtSignal(int, float)     # frame_idx, percentage
    render_finished = pyqtSignal(str)           # output_file

    # 系統健康度與安全指示
    pse_safety_alert = pyqtSignal(bool, str)     # is_safe, message
    system_status_message = pyqtSignal(str)     # status text

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
