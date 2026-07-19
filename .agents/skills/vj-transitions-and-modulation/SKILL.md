---
name: vj-transitions-and-modulation
description: >-
  基於 OpenCV/NumPy 的高效率 VJ 素材過渡效果（Displacement, Zoom Blur, Luma Matte, Glitch, Slide Push）、程序化 12 音 HSL 調色盤生成，以及自適應曲式導演系統映射。
---

# VJ Transitions and Modulation Skill

## 1. Overview
本 Skill 專門用於音訊驅動的 VJ 視覺過渡效果與情緒調變，包含了程序化配色系統、5 種基於 OpenCV/NumPy 的高效素材過渡演算法，以及一整套對應音樂結構與能量的「自適應導演調度規格」。

---

## 2. Dependencies
*   `vj-post-processing-effects`：協同處理影像後製特效鏈。
*   `audio-feature-extraction`：輸入音訊特徵（如低音能量、和弦等）以驅動調變。

---

## 3. 數學原理與 GLSL 規格（跨平台移植指引）

為了方便將這些效果移植到網頁端（WebGL/GLSL Shaders）或其他渲染引擎，以下提供核心演算法的數學公式與 Shader 實作指引：

### 3.1 Displacement (位移映射扭曲)
*   **數學原理**：使用 2D 弦波作為座標偏移量，調變 UV 座標。
    $$\text{disp\_strength} = \sin(\text{progress} \times \pi) \times \text{amplitude}$$
    $$\text{offset}_x(y) = \sin(y \times f) \times \text{disp\_strength}$$
    $$\text{offset}_y(x) = \cos(x \times f) \times \text{disp\_strength}$$
*   **GLSL Shader 核心邏輯**：
    ```glsl
    uniform float progress;
    uniform float intensity;
    uniform sampler2D from;
    uniform sampler2D to;
    varying vec2 uv;

    void main() {
        float wave_len = 0.15;
        float amp = intensity * 0.05;
        float disp = sin(progress * 3.14159) * amp;
        
        vec2 offset = vec2(
            sin(uv.y / wave_len * 6.28318) * disp,
            cos(uv.x / wave_len * 6.28318) * disp
        );
        
        vec4 colorA = texture2D(from, uv + offset * (1.0 - progress));
        vec4 colorB = texture2D(to, uv - offset * progress);
        gl_FragColor = mix(colorA, colorB, progress);
    }
    ```

### 3.2 Zoom Blur (縮放模糊過渡)
*   **數學原理**：對 UV 進行徑向發散偏移，以圖像中心 $(C_x, C_y)$ 為原點縮放並進行多重採樣。
    $$UV_{scaled} = (UV - C) \times \text{scale} + C$$
*   **GLSL Shader 核心邏輯**：
    ```glsl
    uniform float progress;
    uniform float intensity;
    uniform sampler2D from;
    uniform sampler2D to;
    varying vec2 uv;

    void main() {
        float amp = intensity * 0.3;
        float p_scale = sin(progress * 3.14159) * amp;
        vec2 center = vec2(0.5, 0.5);
        
        // 徑向多重採樣模擬模糊
        vec4 colorA = vec4(0.0);
        vec4 colorB = vec4(0.0);
        float steps[3];
        steps[0] = 0.98; steps[1] = 1.0; steps[2] = 1.02;
        
        for(int i = 0; i < 3; i++) {
            float s_a = 1.0 + p_scale * (1.0 - progress);
            float s_b = 1.0 + p_scale * progress;
            colorA += texture2D(from, (uv - center) * s_a * steps[i] + center);
            colorB += texture2D(to, (uv - center) * s_b * steps[i] + center);
        }
        gl_FragColor = mix(colorA / 3.0, colorB / 3.0, progress);
    }
    ```

### 3.3 Luma Wipe (亮度邊緣擦除)
*   **數學原理**：基於線性漸層值與進度閾值判斷像素歸屬，使用羽化區間進行平滑過度。
    $$\text{matte}(x, y) = \frac{x/w + y/h}{2}$$
    $$\text{mask} = \text{clamp}\left(\frac{\text{matte} - \text{progress}}{\text{feather}}, 0.0, 1.0\right)$$
*   **GLSL Shader 核心邏輯**：
    ```glsl
    uniform float progress;
    uniform sampler2D from;
    uniform sampler2D to;
    varying vec2 uv;

    void main() {
        float luma = (uv.x + uv.y) / 2.0;
        float feather = 0.1;
        float threshold = progress * (1.0 + feather) - feather / 2.0;
        float mask = clamp((luma - threshold) / feather + 0.5, 0.0, 1.0);
        
        gl_FragColor = mix(texture2D(from, uv), texture2D(to, uv), 1.0 - mask);
    }
    ```

---

## 4. Python/OpenCV/NumPy 實作參考

### 4.1 五大素材過渡效果
```python
import cv2
import numpy as np
from PIL import Image

def apply_advanced_transition(pil_a, pil_b, progress, trans_type='displacement', intensity=0.5):
    progress = float(np.clip(progress, 0.0, 1.0))
    if progress <= 0.001: return pil_a
    if progress >= 0.999: return pil_b
        
    img_a = np.array(pil_a.convert("RGB"))
    img_b = np.array(pil_b.convert("RGB"))
    h, w = img_a.shape[:2]
    
    # 尺寸自動容錯適配
    if img_b.shape[:2] != (h, w):
        img_b = cv2.resize(img_b, (w, h), interpolation=cv2.INTER_LINEAR)
        
    try:
        if trans_type == 'displacement':
            y_grid, x_grid = np.mgrid[0:h, 0:w].astype(np.float32)
            wave_len = w * 0.15
            wave_amp = intensity * 40.0
            disp_strength = float(np.sin(progress * np.pi) * wave_amp)
            
            dx = np.sin(y_grid / wave_len * 2.0 * np.pi) * disp_strength
            dy = np.cos(x_grid / wave_len * 2.0 * np.pi) * disp_strength
            
            map_x_a = (x_grid + dx * (1.0 - progress)).astype(np.float32)
            map_y_a = (y_grid + dy * (1.0 - progress)).astype(np.float32)
            warped_a = cv2.remap(img_a, map_x_a, map_y_a, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            map_x_b = (x_grid - dx * progress).astype(np.float32)
            map_y_b = (y_grid - dy * progress).astype(np.float32)
            warped_b = cv2.remap(img_b, map_x_b, map_y_b, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            out_np = cv2.addWeighted(warped_a, 1.0 - progress, warped_b, progress, 0.0)
            
        elif trans_type == 'zoom_blur':
            scale_amp = intensity * 0.3
            p_scale = float(np.sin(progress * np.pi) * scale_amp)
            
            scale_a = 1.0 + p_scale * (1.0 - progress)
            M_a = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0, scale_a)
            zoomed_a = cv2.warpAffine(img_a, M_a, (w, h), borderMode=cv2.BORDER_REFLECT)
            
            scale_b = 1.0 + p_scale * progress
            M_b = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0, scale_b)
            zoomed_b = cv2.warpAffine(img_b, M_b, (w, h), borderMode=cv2.BORDER_REFLECT)
            
            steps = [0.98, 1.0, 1.02]
            blur_a = np.zeros_like(zoomed_a, dtype=np.float32)
            blur_b = np.zeros_like(zoomed_b, dtype=np.float32)
            
            for s in steps:
                M_sa = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0, s)
                M_sb = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0, s)
                blur_a += cv2.warpAffine(zoomed_a, M_sa, (w, h), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
                blur_b += cv2.warpAffine(zoomed_b, M_sb, (w, h), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
                
            zoomed_a = (blur_a / len(steps)).astype(np.uint8)
            zoomed_b = (blur_b / len(steps)).astype(np.uint8)
            
            out_np = cv2.addWeighted(zoomed_a, 1.0 - progress, zoomed_b, progress, 0.0)
            
        elif trans_type == 'luma_wipe':
            y_grid, x_grid = np.mgrid[0:h, 0:w]
            matte = ((x_grid / w + y_grid / h) / 2.0 * 255.0).astype(np.float32)
            feather = 30.0
            threshold = progress * (255.0 + feather) - feather / 2.0
            
            mask = np.clip((matte - threshold) / feather + 0.5, 0.0, 1.0)
            mask = np.expand_dims(mask, axis=2)
            out_np = (img_a * mask + img_b * (1.0 - mask)).astype(np.uint8)
            
        elif trans_type == 'glitch':
            # 光敏安全限制：水平偏移限制在 10 像素以內
            max_shift = min(10.0, 10.0 * intensity)
            shift_a = int(np.sin(progress * np.pi) * max_shift * 0.8)
            shift_b = int(np.sin(progress * np.pi) * max_shift * 0.8)
            
            out_a = img_a.copy()
            out_b = img_b.copy()
            
            if abs(shift_a) > 0:
                out_a[:, :, 0] = np.roll(img_a[:, :, 0], shift_a, axis=1)
                out_a[:, :, 2] = np.roll(img_a[:, :, 2], -shift_a, axis=1)
            if abs(shift_b) > 0:
                out_b[:, :, 0] = np.roll(img_b[:, :, 0], -shift_b, axis=1)
                out_b[:, :, 2] = np.roll(img_b[:, :, 2], shift_b, axis=1)
                
            rng_seed = int(progress * 100)
            import random
            local_rng = random.Random(rng_seed)
            
            num_slices = local_rng.randint(3, 8)
            for _ in range(num_slices):
                y_start = local_rng.randint(0, h - 20)
                slice_h = local_rng.randint(5, 20)
                h_offset = local_rng.randint(-int(max_shift), int(max_shift))
                
                out_a[y_start:y_start+slice_h, :] = np.roll(out_a[y_start:y_start+slice_h, :], h_offset, axis=1)
                out_b[y_start:y_start+slice_h, :] = np.roll(out_b[y_start:y_start+slice_h, :], -h_offset, axis=1)
                
            out_np = cv2.addWeighted(out_a, 1.0 - progress, out_b, progress, 0.0)
            
        elif trans_type == 'slide_push':
            dx = int(progress * w)
            out_np = np.zeros_like(img_a)
            out_np[:, :w - dx] = img_a[:, dx:]
            out_np[:, w - dx:] = img_b[:, :dx]
            
            blur_size = int(np.sin(progress * np.pi) * w * 0.04 * intensity)
            if blur_size > 1:
                if blur_size % 2 == 0: blur_size += 1
                blur_size = min(31, blur_size)
                out_np = cv2.blur(out_np, (blur_size, 1))
                
        else:
            out_np = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
            
    except Exception as e:
        # 異常降級機制
        out_np = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
        
    return Image.fromarray(out_np.astype(np.uint8), "RGB").convert("RGBA")
```

### 4.2 程序化配色調色盤生成器
```python
import hashlib
import random

class ProceduralPaletteGenerator:
    def __init__(self, seed_string):
        hash_val = int(hashlib.md5(seed_string.encode('utf-8')).hexdigest(), 16)
        self.rng = random.Random(hash_val)
        
        self.style = self.rng.choice([
            'Vaporwave', 'Cyberpunk', 'Morandi', 'DeepOcean', 'Forest',
            'Complementary', 'Triadic', 'Tetradic', 'Analogous', 'GoldenLava'
        ])
        
        self.base_hue = self.rng.uniform(0.0, 360.0)
        self.hue_step = self.rng.choice([15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 150.0])
        self.direction = self.rng.choice([1, -1])
        self.sat_base = self.rng.uniform(0.5, 0.9)
        
        self.chroma_colors = {}
        for root_idx in range(12):
            fifths_pos = (root_idx * 7) % 12
            # 依據 self.style 生成 12 音 HSL...
            # (具體實作請參考專案中的 audio_analyzer.py)
```

---

## 5. 自適應曲式導演系統映射規格 (Director System Specs)

情緒調變引擎應依據宏觀曲式段落，自動套用對應的過渡演算法與時間參數：

| 段落名稱 (Section) | 映射過渡演算法 | 推薦過渡時長 (秒) | 情緒氛圍描述 |
| :--- | :--- | :--- | :--- |
| **Intro / Outro** | `luma_wipe` | 2.5 - 3.0s | 慢速亮度漸層，水墨般柔和淡入/淡出 |
| **Verse** | `displacement` | 1.5 - 2.0s | 中速流體波紋位移，保持穩定敘事感 |
| **Chorus / Drop** | `zoom_blur` / `glitch` | 0.4 - 0.6s | 快速衝擊拉鏡或故障分色，配合重拍爆發 |
| **Build-up** | `glitch` | 0.8 - 1.2s | 水平故障切片與通道分裂，營造能量爬升緊張感 |
| **Bridge** | `slide_push` | 2.0 - 2.5s | 電影感推橫移加動態模糊，表現旋律與節奏轉折 |

---

## 6. Common Mistakes
1.  **過渡運算時的尺寸不匹配錯誤**：當 `pilA` 與 `pilB` 解析度尺寸不同時，若直接套用 NumPy 運算會引發 shape broadcast 崩潰。**必須**在進入過渡前呼叫自動尺寸適配 resize。
2.  **忽略光敏安全上限**：在移植到其他平台的 `glitch` 實作時，容易忽略水平偏移像素上限。在移植時，**必須**將分色抖動限制在 10px 以內，且禁止全螢幕連續黑白頻閃，以維護觀影安全。
