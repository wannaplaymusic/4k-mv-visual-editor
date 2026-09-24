import os
import logging
import math
from typing import Dict, Tuple, Optional, Union

import numpy as np
from scipy import signal
import librosa

logger = logging.getLogger(__name__)

class AudioStemSeparator:
    """
    現代 4-Stem (Drums, Bass, Vocals, Other) 音訊音軌分離器：
    - 支援 ONNXRuntime 加載輕量化神經源分離模型 (如 HTDemucs / MDX-Net ONNX)
    - 內建零依賴高保真物理聲學分軌回退 (Acoustic Decomposition Fallback Pipeline)
    - 輸出各音軌波形與動態包絡，直通 4K 幾何與 Shader 特效
    """
    def __init__(self, onnx_model_path: Optional[str] = None):
        self.onnx_model_path = onnx_model_path
        self.session = None
        self._init_engine()

    def _init_engine(self):
        if self.onnx_model_path and os.path.exists(self.onnx_model_path):
            try:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 4
                self.session = ort.InferenceSession(self.onnx_model_path, sess_options=opts)
                logger.info(f"✨ 成功載入神經音軌分離 ONNX 模型: {self.onnx_model_path}")
            except Exception as e:
                logger.warning(f"ONNX 模型載入失敗，將啟用高保真聲學物理回退分離: {e}")
                self.session = None
        else:
            logger.info("ℹ️ 未指定神經 ONNX 模型，使用內建高保真物理聲學分軌引擎 (HPSS + Filterbank)")

    def separate(
        self,
        audio_input: Union[str, np.ndarray],
        sr: int = 44100,
        hop_length: int = 1024
    ) -> Dict[str, dict]:
        """
        將音訊拆解為 Drums, Bass, Vocals, Other 四個獨立音軌。
        返回格式:
        {
            'drums': {'waveform': np.ndarray, 'envelope': np.ndarray},
            'bass':  {'waveform': np.ndarray, 'envelope': np.ndarray},
            'vocals':{'waveform': np.ndarray, 'envelope': np.ndarray},
            'other': {'waveform': np.ndarray, 'envelope': np.ndarray},
            'times': np.ndarray,
            'sr': int
        }
        """
        if isinstance(audio_input, str):
            y, sr = librosa.load(audio_input, sr=sr, mono=True)
        else:
            y = audio_input.astype(np.float32)

        # 優先嘗試神經網絡分離 (若 session 可用)
        if self.session is not None:
            try:
                return self._separate_onnx(y, sr, hop_length)
            except Exception as e:
                logger.warning(f"ONNX 神經分離推論異常，自動平滑回退: {e}")

        # 執行高品質物理聲學分軌 (Acoustic Filterbank + HPSS)
        return self._separate_acoustic_physics(y, sr, hop_length)

    def _separate_acoustic_physics(self, y: np.ndarray, sr: int, hop_length: int) -> Dict[str, dict]:
        """基於 HPSS 與精確 Hz 臨界頻帶的物理聲學四軌分離演算法"""
        # 1. HPSS 諧波與打擊樂分離
        y_harm, y_perc = librosa.effects.hpss(y, margin=(1.2, 2.0))

        # 2. Drums 軌道: HPSS 打擊分量 + 低頻衝擊
        drums_wave = y_perc

        # 3. Bass 軌道: 諧波分量之 20Hz ~ 250Hz 低通濾波
        nyquist = sr * 0.5
        b_low, a_low = signal.butter(4, min(250.0 / nyquist, 0.99), btype='low')
        bass_wave = signal.filtfilt(b_low, a_low, y_harm)

        # 4. Vocals 軌道: 諧波分量之人聲共振帶 (300Hz ~ 3400Hz 帶通濾波)
        low_cut = 300.0 / nyquist
        high_cut = min(3400.0 / nyquist, 0.99)
        b_voc, a_voc = signal.butter(4, [low_cut, high_cut], btype='band')
        vocals_wave = signal.filtfilt(b_voc, a_voc, y_harm)

        # 5. Other 軌道: 殘餘諧波與高頻氛圍 (Pad, Synth, Strings, FX)
        other_wave = y_harm - (bass_wave * 0.8 + vocals_wave * 0.8)

        # 6. 計算各軌動態能量包絡 (RMS + 對數壓縮 + 歸一化)
        def compute_envelope(w):
            rms = librosa.feature.rms(y=w, frame_length=2048, hop_length=hop_length)[0]
            log_rms = np.log1p(rms * 10.0)
            max_val = np.max(log_rms) + 1e-8
            return np.clip(log_rms / max_val, 0.0, 1.0)

        env_drums = compute_envelope(drums_wave)
        env_bass = compute_envelope(bass_wave)
        env_vocals = compute_envelope(vocals_wave)
        env_other = compute_envelope(other_wave)

        times = librosa.frames_to_time(np.arange(len(env_drums)), sr=sr, hop_length=hop_length)

        return {
            'drums': {
                'waveform': drums_wave,
                'envelope': env_drums,
                'description': '打擊樂與節奏點 (驅動攝影機震動、粒子爆炸)'
            },
            'bass': {
                'waveform': bass_wave,
                'envelope': env_bass,
                'description': '低音與次低音 (驅動空間流體、幾何縮放)'
            },
            'vocals': {
                'waveform': vocals_wave,
                'envelope': env_vocals,
                'description': '人聲主旋律 (驅動主光暈 Bloom、色彩冷暖呼吸)'
            },
            'other': {
                'waveform': other_wave,
                'envelope': env_other,
                'description': '和弦與背景氛圍 (驅動背景噪聲、微光斑)'
            },
            'times': times,
            'sr': sr
        }

    def _separate_onnx(self, y: np.ndarray, sr: int, hop_length: int) -> Dict[str, dict]:
        """ONNX 神經網絡推論實作 (針對通用 4-stem ONNX 輸出格式)"""
        # 輸入格式標準化為 (1, channels, samples)
        input_tensor = y[np.newaxis, np.newaxis, :].astype(np.float32)
        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: input_tensor})
        
        # 假設模型輸出 (1, 4, samples): 0: Drums, 1: Bass, 2: Other, 3: Vocals
        stems_data = outputs[0][0]
        drums_wave = stems_data[0]
        bass_wave = stems_data[1]
        other_wave = stems_data[2]
        vocals_wave = stems_data[3]

        def compute_envelope(w):
            rms = librosa.feature.rms(y=w, frame_length=2048, hop_length=hop_length)[0]
            log_rms = np.log1p(rms * 10.0)
            return np.clip(log_rms / (np.max(log_rms) + 1e-8), 0.0, 1.0)

        env_drums = compute_envelope(drums_wave)
        env_bass = compute_envelope(bass_wave)
        env_vocals = compute_envelope(vocals_wave)
        env_other = compute_envelope(other_wave)
        times = librosa.frames_to_time(np.arange(len(env_drums)), sr=sr, hop_length=hop_length)

        return {
            'drums': {'waveform': drums_wave, 'envelope': env_drums},
            'bass':  {'waveform': bass_wave, 'envelope': env_bass},
            'vocals':{'waveform': vocals_wave, 'envelope': env_vocals},
            'other': {'waveform': other_wave, 'envelope': env_other},
            'times': times,
            'sr': sr
        }
