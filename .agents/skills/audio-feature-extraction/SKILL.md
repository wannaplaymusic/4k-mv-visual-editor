---
name: audio-feature-extraction
description: 提取多頻段音訊特徵（如 Bass、Mid、High 能量）、BPM、節奏點（Beats）以及使用 CQT/Chroma 與 Oklab 進行和弦辨識與色彩映射、Ballistic 非對稱動態濾波與 SSM 結構分鏡切分
---

# Audio Feature Extraction Skill (Modern Audio-Visual Pipeline)

本 Skill 專門用於音訊特徵分析與前沿音畫互動（Audio-Reactive Visuals）開發，整理自本專案的 `audio_analyzer.py` 與 `audio_stem_separator.py`。

## 1. 物理聲學精確頻帶分割 (Decoupled Dynamic Hz Masking)

徹底解耦取樣率 `sr` 與 FFT 尺寸 `n_fft`，根據精確赫茲（Hz）計算頻率遮罩，劃分人耳敏感的臨界頻帶：

```python
import librosa
import numpy as np

def get_freq_mask(n_fft: int, sr: int, low_hz: float, high_hz: float) -> np.ndarray:
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    return (freqs >= low_hz) & (freqs < high_hz)

# 精確 Hz 物理頻帶劃分
sub_mask = get_freq_mask(n_fft=2048, sr=44100, low_hz=20.0, high_hz=60.0)
bass_mask = get_freq_mask(n_fft=2048, sr=44100, low_hz=60.0, high_hz=250.0)
mid_mask = get_freq_mask(n_fft=2048, sr=44100, low_hz=250.0, high_hz=3000.0)
high_mask = get_freq_mask(n_fft=2048, sr=44100, low_hz=3000.0, high_hz=16000.0)
```

## 2. 知覺均勻色彩引擎 (Oklab Color Space)

為了解決傳統 HSL 空間在色相切換時造成人眼感知亮度劇烈跳動（Luminance Strobing），音畫生成管線推薦使用 **Oklab** 感知均勻色彩空間：

```python
def oklab_to_srgb(L: float, a: float, b: float) -> tuple[int, int, int]:
    """將感知均勻的 Oklab 空間轉換至標準 sRGB (防止視覺閃爍與感知亮度跳躍)"""
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3; m = m_ ** 3; s = s_ ** 3
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_out = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def gamma_correct(c: float) -> int:
        c = max(0.0, min(1.0, c))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
        return int(round(c * 255.0))

    return gamma_correct(r), gamma_correct(g), gamma_correct(b_out)
```

## 3. 常數 Q 變換 (CQT) 諧波和弦識別與時序平滑

使用 HPSS 諧波分量結合常數 Q 變換（Logarithmic Pitch Resolution）以及滑動中值平滑（Median Filter），徹底消除和弦微跳動與打擊樂噪聲污染：

```python
import librosa
from scipy.ndimage import median_filter

# 1. 諧波分離
y_harm, y_perc = librosa.effects.hpss(y, margin=(1.2, 2.0))

# 2. CQT Chroma 提取
chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop_length, n_chroma=12)

# 3. 時間軸滑動中值濾波
chroma_smooth = median_filter(chroma, size=(1, 5))
```

## 4. 彈簧式非對稱動態濾波器 (BallisticFilter)

視覺互動需要「起音極速（Attack）、釋音平滑（Release）」，模擬真實物理世界的彈簧阻尼慣性：

```python
import math

class BallisticFilter:
    """音畫互動非對稱動態濾波器 (瞬態疾速爆發，平滑釋放)"""
    def __init__(self, attack_ms: float = 10.0, release_ms: float = 180.0, fps: float = 60.0):
        dt = 1.0 / max(fps, 1.0)
        self.alpha_attack = math.exp(-dt / (attack_ms * 1e-3))
        self.alpha_release = math.exp(-dt / (release_ms * 1e-3))
        self.state = 0.0

    def process(self, target: float) -> float:
        if target > self.state:
            self.state = target + self.alpha_attack * (self.state - target)
        else:
            self.state = target + self.alpha_release * (self.state - target)
        return self.state
```

## 5. 自我相似矩陣 (SSM) 結構分鏡分割

取代傳統寫死能量閥值（$t_e > 0.58$），透過 MFCC 降採樣計算 Cosine 距離 SSM，並以 Foote 棋盤核捲積計算 Novelty 曲線尋找段落轉折點（Intro, Drop, Breakdown, Outro）：

```python
# 下採樣 MFCC 特徵計算 SSM
hop = max(1, S_mag.shape[1] // 200)
mfcc = librosa.feature.mfcc(S=librosa.power_to_db(S_mag[:, ::hop]), n_mfcc=13)
mfcc_norm = librosa.util.normalize(mfcc, axis=1)
ssm = np.dot(mfcc_norm.T, mfcc_norm)

# Foote Novelty Curve 峰值提取
kernel_size = 10
novelty = np.zeros(ssm.shape[0])
for i in range(kernel_size, ssm.shape[0] - kernel_size):
    novelty[i] = np.sum(ssm[i-kernel_size:i, i:i+kernel_size]) - np.sum(ssm[i-kernel_size:i, i-kernel_size:i])
```
