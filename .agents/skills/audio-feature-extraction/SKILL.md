---
name: audio-feature-extraction
description: 提取多頻段音訊特徵（如 Bass、Mid、High 能量）、BPM、節奏點（Beats）以及使用 Chroma STFT 進行和弦辨識與 HSL 顏色映射
---

# Audio Feature Extraction Skill

本 Skill 專門用於音訊特徵分析與音視互動（Audio-Reactive Visuals）開發，整理自本專案的 `audio_analyzer.py`。

## 1. 核心頻段能量計算 (NumPy & Librosa)

分析音訊時，常需要將短時傅立葉變換（STFT）頻譜劃分為人耳敏感的子頻段（Sub-bass, Bass, Mid, High）：

```python
import librosa
import numpy as np

# 載入音訊
y, sr = librosa.load(audio_path, sr=22050)
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=1024))
total_energy = np.maximum(np.sum(S, axis=0), 1e-5)

# 頻段比率計算 (基於 STFT Bin 範圍)
sub_bass_ratio = np.sum(S[2:6, :], axis=0) / total_energy
bass_ratio = np.sum(S[6:23, :], axis=0) / total_energy
mid_ratio = np.sum(S[23:186, :], axis=0) / total_energy
high_ratio = np.sum(S[186:, :], axis=0) / total_energy

# 平滑處理 (Damping Filter / Moving Average)
box = np.ones(5) / 5.0
bass_ratio_smooth = np.convolve(bass_ratio, box, mode='same')
```

## 2. 和弦偵測與 HSL/Hex 色彩映射

利用 Chroma 特徵與內置的 pitch 大/小/增/減和弦模板比對，並以「五度圈（Circle of Fifths）」為基礎將根音映射至對應的 HSL 色彩相（Hue），實現音視色彩映射：

```python
import colorsys
import numpy as np

PITCH_CLASSES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def _get_chord_templates():
    templates = {}
    for i in range(12):
        # Major 三和弦 (0, 4, 7)
        template = np.zeros(12)
        template[i] = 1.0; template[(i + 4) % 12] = 1.0; template[(i + 7) % 12] = 1.0
        templates[PITCH_CLASSES[i]] = template / (np.linalg.norm(template) + 1e-8)
        
        # Minor 三和弦 (0, 3, 7)
        template = np.zeros(12)
        template[i] = 1.0; template[(i + 3) % 12] = 1.0; template[(i + 7) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}m"] = template / (np.linalg.norm(template) + 1e-8)
    return templates

CHORD_TEMPLATES = _get_chord_templates()

def parse_chord_name(chord_name):
    # 根據五度圈計算 Hue (五度圈相鄰音程在視覺上色彩相近)
    root = chord_name.replace('m', '').replace('aug', '').replace('dim', '')
    root_idx = PITCH_CLASSES.index(root)
    fifths_pos = (root_idx * 7) % 12
    hue = fifths_pos * 30 # 0 ~ 360 度
    
    # 根據和弦屬性（大/小/增/減）調整飽和度與亮度
    if 'm' in chord_name:
         return hue, 0.45, 0.5 # 憂鬱小調：低飽和度
    return hue, 0.95, 0.8     # 明亮大調：高飽和度
```

## 3. 音訊平滑與動態包絡處理

使用單向或雙向動態衰減器（Damping Filter），讓視覺信號「起音快、衰減慢」，模擬物理視覺慣性：

```python
class DampingFilter:
    def __init__(self, initial_value=0.0, lambda_attack=15.0, lambda_decay=2.5):
        self.val = initial_value
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, target, dt):
        # 若目標大於目前值，採用快速起音；若小於，則採用慢速衰減
        lambda_val = self.lambda_attack if target > self.val else self.lambda_decay
        self.val += (target - self.val) * (1.0 - np.exp(-lambda_val * dt))
        return self.val
```
