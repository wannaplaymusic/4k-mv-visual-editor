import os
import math
import time
import logging
import numpy as np

logger = logging.getLogger("VisualStudio.VirtualAudioDeck")

class VirtualAudioDeck:
    """
    虛擬調音台與聲學動態注入器
    - 支援載入音訊檔並快取多頻段頻譜與和弦五度圈特徵
    - 時間軸毫秒級擦除 (Timeline Scrubbing)
    - 手動合成推子模式 (Manual Faders Mode)
    - 非對稱物理彈簧阻尼濾波器 (Attack 15ms / Decay 250ms)
    """

    def __init__(self):
        self.audio_file_path = None
        self.duration_seconds = 0.0
        self.is_loaded = False
        
        # 特徵序列緩衝區 (以 30 FPS 或 60 FPS 步長取樣)
        self.timeline_frames = []
        self.waveform_peaks = []
        self.bpm = 120.0

        # 手動合成推子狀態
        self.manual_mode = True
        self.manual_sub_bass = 0.5
        self.manual_bass = 0.5
        self.manual_mid = 0.5
        self.manual_high = 0.5
        self.manual_is_beat = False
        self.manual_chord_hue = 180
        
        # 阻尼器內部值
        self._damped_bass = 0.0
        self._last_update_time = time.time()

    def load_audio_file(self, file_path: str) -> bool:
        """載入音訊並進行分析"""
        if not os.path.exists(file_path):
            logger.error(f"Audio file not found: {file_path}")
            return False

        self.audio_file_path = file_path
        try:
            from audio_analyzer import AudioAnalyzer
            analyzer = AudioAnalyzer(file_path)
            analyzer.analyze_full()
            
            self.duration_seconds = analyzer.duration
            self.bpm = getattr(analyzer, "bpm", 120.0)
            
            # 生成波形峰值縮圖 (供前端繪製)
            raw_data = analyzer.y
            sr = analyzer.sr
            hop = max(1, len(raw_data) // 500)
            self.waveform_peaks = [float(np.max(np.abs(raw_data[i:i+hop]))) for i in range(0, len(raw_data), hop)]

            # 建立時間軸特徵序列
            self.timeline_frames = []
            fps = 30.0
            total_frames = int(self.duration_seconds * fps)
            for f in range(total_frames):
                t_sec = f / fps
                feat = analyzer.get_features_at_time(t_sec)
                self.timeline_frames.append(feat)

            self.is_loaded = True
            self.manual_mode = False
            logger.info(f"Successfully loaded audio: {file_path}, {self.duration_seconds:.1f}s, BPM: {self.bpm}")
            return True
        except Exception as e:
            logger.warning(f"Failed to use AudioAnalyzer, falling back to synthetic audio mock: {e}")
            self._create_mock_timeline(180.0, 128.0)
            self.is_loaded = True
            self.manual_mode = False
            return True

    def _create_mock_timeline(self, duration: float, bpm: float):
        """生成模擬的聲學時間軸"""
        self.duration_seconds = duration
        self.bpm = bpm
        fps = 30.0
        total_frames = int(duration * fps)
        self.timeline_frames = []
        self.waveform_peaks = [float(abs(math.sin(i * 0.05) * 0.8 + 0.1)) for i in range(500)]

        beat_interval = 60.0 / bpm
        for f in range(total_frames):
            t_sec = f / fps
            phase = (t_sec % beat_interval) / beat_interval
            is_beat = phase < 0.15
            bass_pulse = math.exp(-phase * 8.0) if is_beat else 0.15

            self.timeline_frames.append({
                "sub_bass": bass_pulse * 0.9,
                "bass": bass_pulse,
                "mid": 0.4 + math.sin(t_sec * 0.5) * 0.3,
                "high": 0.3 + (math.cos(t_sec * 2.0) * 0.2 if phase > 0.5 else 0.1),
                "is_beat": is_beat,
                "chord_hue": int((t_sec * 10) % 360),
                "chord_color": "#0ea5e9"
            })

    def get_frame_at_progress(self, progress: float) -> dict:
        """
        時間軸擦除 (Scrubbing)：傳入 0.0 ~ 1.0，回傳當前幀聲學特徵
        """
        progress = max(0.0, min(1.0, progress))
        if not self.timeline_frames:
            return self.get_manual_frame()

        idx = int(progress * (len(self.timeline_frames) - 1))
        frame = self.timeline_frames[idx]
        return self._apply_spring_damping(frame)

    def get_manual_frame(self) -> dict:
        """獲取手動推子模式下的特徵"""
        raw = {
            "sub_bass": self.manual_sub_bass,
            "bass": self.manual_bass,
            "mid": self.manual_mid,
            "high": self.manual_high,
            "is_beat": self.manual_is_beat,
            "chord_hue": self.manual_chord_hue,
            "chord_color": f"hsl({self.manual_chord_hue}, 80%, 55%)"
        }
        return self._apply_spring_damping(raw)

    def _apply_spring_damping(self, raw_frame: dict) -> dict:
        """非對稱物理彈簧阻尼器 (起得快、落得慢)"""
        now = time.time()
        dt = max(0.001, min(0.1, now - self._last_update_time))
        self._last_update_time = now

        target_bass = raw_frame.get("bass", 0.5)
        # 起得快 (Attack: lambda=25), 落得慢 (Decay: lambda=3.5)
        lambda_val = 25.0 if target_bass > self._damped_bass else 3.5
        self._damped_bass += (target_bass - self._damped_bass) * (1.0 - math.exp(-lambda_val * dt))

        out = dict(raw_frame)
        out["damped_bass"] = float(self._damped_bass)
        return out

    def trigger_tap_beat(self):
        """點擊重音打擊"""
        self.manual_is_beat = True
        self.manual_bass = 1.0
        self.manual_sub_bass = 1.0

    def release_tap_beat(self):
        self.manual_is_beat = False
        self.manual_bass = 0.3
        self.manual_sub_bass = 0.2
