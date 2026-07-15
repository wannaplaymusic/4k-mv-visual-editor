---
name: vj-post-processing-effects
description: 基於 OpenCV/NumPy 的高效率實時 VJ 特效模組，包括 Reaction-Diffusion 反應擴散迭代系統與 Vortex Field 渦流流體模擬，並與音訊動態耦合。
---

# VJ Post Processing Effects Skill

本 Skill 專門用於高性能影像後製特效與音視動態耦合，整理自本專案的 `post_processor.py`。

## 1. 反應擴散（Reaction-Diffusion）迭代動力學反饋系統

透過累積前一格畫面（Feedback Frame），進行無感微幅放大（擴散）、對比度調整（反應），並結合大/小調音樂情緒色調混合，實現具有回音感、夢幻感且高性能的擴散特效：

```python
import cv2
import numpy as np

class FeedbackSystem:
    def __init__(self):
        self.feedback_img = None

    def apply(self, img_np, intensity, chord_name='N.C.', reverb_decay=0.15):
        """
        img_np: 輸入的 RGB 影像 (ndarray)
        intensity: 音訊特徵強度 (0.0 ~ 1.0)
        chord_name: 當前偵測到的和弦名稱
        reverb_decay: 衰減率
        """
        if intensity < 0.05:
            return img_np

        h, w = img_np.shape[:2]
        # 初始化 Feedback 畫布 (單通道 Gray 以提升效率)
        if self.feedback_img is None or self.feedback_img.shape != (h, w):
            self.feedback_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            return img_np

        curr_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        blended = cv2.addWeighted(self.feedback_img, 1.0 - reverb_decay, curr_gray, reverb_decay, 0)
        
        # 1. 擴散：微幅外擴放大
        scale = 1.01 + 0.005 * intensity
        rw, rh = int(w * scale), int(h * scale)
        diffused = cv2.resize(blended, (rw, rh), interpolation=cv2.INTER_LINEAR)
        
        # 居中裁切回原尺寸
        left = (rw - w) // 2
        top = (rh - h) // 2
        diffused = diffused[top:top+h, left:left+w]
        
        # 2. 反應：對比度激化
        mean_val = np.mean(diffused)
        diffused_float = diffused.astype(np.float32)
        contrast_factor = 1.3 + 0.3 * intensity
        diffused_enhanced = diffused_float * contrast_factor + mean_val * (1.0 - contrast_factor)
        diffused = np.clip(diffused_enhanced, 0, 255).astype(np.uint8)
        
        self.feedback_img = diffused

        # 3. 色調映射：根據大/小調給予情緒色塊 (小調給冷色，大調給暖色)
        chord_lower = chord_name.lower()
        is_minor = any(m in chord_lower for m in ('min', 'dim', 'aug')) or ('m' in chord_lower and 'maj' not in chord_lower)
        morandi_rgb = np.array([110, 180, 200] if is_minor else [230, 170, 190], dtype=np.float32) / 255.0
        
        colored_feedback = (diffused[:, :, np.newaxis].astype(np.float32) * morandi_rgb).astype(np.uint8)
        
        # 混合輸出
        return cv2.addWeighted(img_np, 1.0 - 0.25 * intensity, colored_feedback, 0.25 * intensity, 0)
```

## 2. 渦流場（Vortex Field）即時流體平流模擬器

當重拍（Beat）觸發時，產生多個旋轉渦流點。透過對每個像素點套用基於高斯能量衰減的旋轉向量偏移量，再藉由 `cv2.remap` 在 GPU 或 CPU 上完成超快速的流體平滑扭曲：

```python
import cv2
import numpy as np
import random

class FluidSimulator:
    def __init__(self):
        self.vortices = [] # 格式: [cx, cy, radius, strength, life]

    def update_and_apply(self, img_np, is_beat, beat_energy, fluid_scale=1.0, spectral_centroid=0.2):
        # 1. 更新現有渦流壽命
        self.vortices = [[cx, cy, rad, strg, life - 0.03] for cx, cy, rad, strg, life in self.vortices if life - 0.03 > 0]

        # 2. 重拍觸發新渦流
        if is_beat and len(self.vortices) < 4:
            cx, cy = random.uniform(0.2, 0.8), random.uniform(0.2, 0.8)
            rad = random.uniform(0.15, 0.3)
            strength = random.choice([-60.0, 60.0]) * (0.4 + 0.6 * beat_energy)
            self.vortices.append([cx, cy, rad, strength, 1.0])

        if not self.vortices:
            return img_np

        h, w = img_np.shape[:2]
        
        # 建立像素映射網格 (使用快取避免重疊配置記憶體)
        y_grid, x_grid = np.mgrid[0:h, 0:w].astype(np.float32)
        dx = np.zeros_like(x_grid)
        dy = np.zeros_like(y_grid)

        # 3. 計算累加的渦流旋轉力場
        for cx_r, cy_r, rad_r, strength, life in self.vortices:
            cx, cy = cx_r * w, cy_r * h
            rad = (rad_r * fluid_scale) * min(w, h)
            v_strength = strength * (1.0 + spectral_centroid * 0.5)
            
            rx, ry = x_grid - cx, y_grid - cy
            r2 = rx*rx + ry*ry
            dist = np.sqrt(r2)
            
            # 高斯能量衰減
            factor = np.exp(-r2 / (2.0 * rad * rad)) * v_strength * life
            dx += (-ry / (dist + 1.0)) * factor
            dy += (rx / (dist + 1.0)) * factor

        # 4. Remap 仿射變換與映射
        map_x = (x_grid + dx).astype(np.float32)
        map_y = (y_grid + dy).astype(np.float32)
        return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
```
