import os
import sys
import math
import random
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageChops, ImageFilter

logger = logging.getLogger("StandaloneInjector.PostProcessor")

# 全域 cv2 導入：統一入口，避免各方法分散 import 的 overhead
try:
    import cv2
except ImportError:
    cv2 = None


class DampingFilter:
    """單階非對稱阻尼插值濾波器，實作「起得快、落得慢」的極佳 VJ 視覺節奏"""
    def __init__(self, initial_value=0.0, lambda_attack=15.0, lambda_decay=2.5):
        self.value = initial_value
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, target, dt):
        if dt <= 0:
            return self.value
        # 非對稱上升/下降邏輯
        lambda_val = self.lambda_attack if target > self.value else self.lambda_decay
        self.value += (target - self.value) * (1.0 - math.exp(-lambda_val * dt))
        return self.value


class DynamicBaselineAdapter:
    """滾動歷史緩衝區，利用 Z-Score 演算法將實時聲學特徵自適應歸一化"""
    def __init__(self, window_size=150):
        self.window_size = window_size
        self.history = []

    def update_and_normalize(self, val):
        self.history.append(val)
        if len(self.history) > self.window_size:
            self.history.pop(0)
        
        arr = np.array(self.history)
        mean = np.mean(arr)
        std = np.std(arr)
        
        if std < 1e-4:
            return val
            
        norm = (val - mean) / (std + 1e-4)
        # 將 -1.5 到 +1.5 標準差精準映射至 0.0 到 1.0 區間
        mapped = (norm + 1.5) / 3.0
        return max(0.0, min(1.0, float(mapped)))


class TimeDisplacementBuffer:
    """時空反饋狹縫掃描（Slit-Scan）影格環形緩衝區 (優化：直存 NumPy ndarray 防止重覆轉型)"""
    def __init__(self, max_size=30):
        self.max_size = max_size
        self.buffer = []
        self._grid_cache = None

    def push(self, img_np):
        """直存 ndarray 提升性能，省去 PIL Image 的解包開銷"""
        self.buffer.append(img_np.copy())
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)

    def apply(self, img_np, intensity):
        """接收並返回 ndarray，迴圈內直接索引 ndarray buffer"""
        if len(self.buffer) < 5 or intensity < 0.05:
            return img_np

        try:
            h, w = img_np.shape[:2]
            # 建立並快取中心徑向距離矩陣
            if self._grid_cache is None or self._grid_cache[0] != (w, h):
                y, x = np.mgrid[0:h, 0:w]
                dist = np.sqrt((x - w/2)**2 + (y - h/2)**2)
                max_dist = np.sqrt((w/2)**2 + (h/2)**2)
                self._grid_cache = ((w, h), dist, max_dist)
            _, dist, max_dist = self._grid_cache
            
            # 將徑向距離映射為歷史影格索引延遲
            delay_map = (dist / max_dist) * (self.max_size - 1) * intensity
            delay_map = np.clip(delay_map, 0, len(self.buffer) - 1).astype(np.int32)

            out_np = np.zeros_like(img_np)

            # 依據延遲地圖原位重構全景影格 — 直接索引 ndarray，零轉型
            for d in range(len(self.buffer)):
                mask = (delay_map == d)
                if np.any(mask):
                    out_np[mask] = self.buffer[-(d+1)][mask]

            return out_np
        except Exception as e:
            logger.error(f"Error in slit-scan: {e}")
            return img_np


class FeedbackSystem:
    """ 反應擴散（Reaction-Diffusion）迭代動力學反饋系統 (ndarray 高性能直通版)"""
    def __init__(self):
        self.feedback_img = None
        self._color_cache = None

    def apply(self, img_np, intensity, chord_name='N.C.', reverb_decay=0.15):
        if intensity < 0.05 or cv2 is None:
            return img_np

        h, w = img_np.shape[:2]
        if self.feedback_img is None or self.feedback_img.shape != (h, w):
            self.feedback_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            return img_np

        try:
            curr_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            blended = cv2.addWeighted(self.feedback_img, 1.0 - reverb_decay, curr_gray, reverb_decay, 0)
            
            # 擴散：微幅無感放大擴張
            scale = 1.01 + 0.005 * intensity
            rw, rh = int(w * scale), int(h * scale)
            diffused = cv2.resize(blended, (rw, rh), interpolation=cv2.INTER_LINEAR)
            
            # 居中裁切
            left = (rw - w) // 2
            top = (rh - h) // 2
            diffused = diffused[top:top+h, left:left+w]
            if diffused.shape != (h, w):
                diffused = cv2.resize(diffused, (w, h), interpolation=cv2.INTER_LINEAR)

            # 反應：高動態對比度激活
            mean_val = np.mean(diffused)
            diffused_float = diffused.astype(np.float32)
            contrast_factor = 1.3 + 0.3 * intensity
            diffused_enhanced = diffused_float * contrast_factor + mean_val * (1.0 - contrast_factor)
            diffused = np.clip(diffused_enhanced, 0, 255).astype(np.uint8)
            
            self.feedback_img = diffused

            chord_lower = chord_name.lower()
            is_minor = any(m in chord_lower for m in ('min', 'dim', 'aug')) or ('m' in chord_lower and 'maj' not in chord_lower)
            
            # 零分配快取：常駐莫蘭迪情緒色調層，防止每影格重複開闢內存
            if self._color_cache is None or self._color_cache[0] != (h, w) or self._color_cache[1] != is_minor:
                if is_minor:
                    morandi_rgb = np.array([110, 180, 200], dtype=np.float32) / 255.0
                else:
                    morandi_rgb = np.array([230, 170, 190], dtype=np.float32) / 255.0
                self._color_cache = ((h, w), is_minor, morandi_rgb)
            
            _, _, morandi_rgb = self._color_cache
            
            colored_feedback = (diffused[:, :, np.newaxis].astype(np.float32) * morandi_rgb).astype(np.uint8)
            
            return cv2.addWeighted(img_np, 1.0 - 0.25 * intensity, colored_feedback, 0.25 * intensity, 0)
        except Exception as e:
            logger.error(f"Error in reaction-diffusion feedback: {e}")
            return img_np


class VJAestheticEngine:
    """4K MV 全域 VJ 審美引擎 (整合 HSL 色調諧振、電影級暗角與色燈後處理)"""
    PRESETS = {
        'CYBERPUNK': {'primary_rgb': (0, 240, 255), 'secondary_rgb': (255, 0, 85), 'bg_rgb': (11, 14, 20)},
        'SYNTHWAVE': {'primary_rgb': (121, 40, 202), 'secondary_rgb': (255, 0, 128), 'bg_rgb': (15, 5, 29)},
        'FLUID': {'primary_rgb': (0, 223, 137), 'secondary_rgb': (3, 105, 161), 'bg_rgb': (30, 41, 59)},
        'MONOCHROME': {'primary_rgb': (245, 158, 11), 'secondary_rgb': (113, 113, 122), 'bg_rgb': (9, 9, 11)}
    }

    @staticmethod
    def get_harmonic_color(pitch_class=0, energy=0.5, is_minor=False):
        """計算符合音樂調性與能量的 HSL 諧和 RGB 向量 (0.0~1.0)"""
        base_hue = (pitch_class * 30 + 15) % 360
        sat = (0.35 + energy * 0.25) if is_minor else (0.65 + energy * 0.25)
        light = (0.25 + energy * 0.30) if is_minor else (0.45 + energy * 0.30)
        
        c = (1.0 - abs(2.0 * light - 1.0)) * sat
        x = c * (1.0 - abs((base_hue / 60.0) % 2 - 1.0))
        m = light - c / 2.0
        
        if base_hue < 60:
            r, g, b = c, x, 0.0
        elif base_hue < 120:
            r, g, b = x, c, 0.0
        elif base_hue < 180:
            r, g, b = 0.0, c, x
        elif base_hue < 240:
            r, g, b = 0.0, x, c
        elif base_hue < 300:
            r, g, b = x, 0.0, c
        else:
            r, g, b = c, 0.0, x
            
        return (float(r + m), float(g + m), float(b + m))


class FluidSimulator:
    """基於渦流場（Vortex Field）的即時流體平流平滑模擬器"""
    def __init__(self):
        self.vortices = [] 
        self._grid_cache = None

    def update_and_apply(self, img_np, t, is_beat, beat_energy, fluid_scale=1.0, spectral_centroid=0.2):
        """接收並返回 ndarray，消除 PIL 轉型"""
        new_vortices = []
        for v in self.vortices:
            v[4] -= 0.03  # 壽命衰減
            if v[4] > 0:
                new_vortices.append(v)
        self.vortices = new_vortices

        # 重拍觸發全新渦流
        if is_beat and len(self.vortices) < 4:
            cx = random.uniform(0.2, 0.8)
            cy = random.uniform(0.2, 0.8)
            rad = random.uniform(0.15, 0.3)
            strength = random.choice([-60.0, 60.0]) * (0.4 + 0.6 * beat_energy)
            self.vortices.append([cx, cy, rad, strength, 1.0])

        if not self.vortices:
            return img_np

        if cv2 is None:
            return img_np

        try:
            h, w = img_np.shape[:2]
            
            if self._grid_cache is None or self._grid_cache[0] != (w, h):
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                self._grid_cache = ((w, h), x, y)
            _, x, y = self._grid_cache

            dx = np.zeros_like(x)
            dy = np.zeros_like(y)

            for cx_r, cy_r, rad_r, strength, life in self.vortices:
                cx, cy = cx_r * w, cy_r * h
                # 動態應用頻譜質心與流體比例調製，而不永久改變基礎屬性避免指數級爆炸
                rad = (rad_r * fluid_scale) * min(w, h)
                v_strength = strength * (1.0 + spectral_centroid * 0.5)
                
                rx, ry = x - cx, y - cy
                r2 = rx*rx + ry*ry
                dist = np.sqrt(r2)
                
                # 高斯分佈能量衰減衰退場
                factor = np.exp(-r2 / (2.0 * rad * rad)) * v_strength * life
                dx += (-ry / (dist + 1.0)) * factor
                dy += (rx / (dist + 1.0)) * factor

            map_x = (x + dx).astype(np.float32)
            map_y = (y + dy).astype(np.float32)
            
            # FIX 3: 尺寸守護護欄 - 避免降採樣導致 Remap 崩潰
            if map_x.shape != img_np.shape[:2]:
                self._grid_cache = None  # 立即失效快取並回退
                return img_np
                
            return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception:
            return img_np


class PostProcessor:
    """工業級 4K VJ 多通道音視互動後製特效矩陣引擎 (高性能優化重構版)"""
    def __init__(self, seed_string=None, genre='generic', used_themes=None):
        self.time_displacement_buffer = TimeDisplacementBuffer(max_size=30)
        self.feedback_system = FeedbackSystem()
        self.fluid_simulator = FluidSimulator()
        self.damping_filters = {}
        self.baseline_adapters = {}
        self.percussive_history = []
        self.invert_frame_timer = 0
        self.last_t = 0.0
        self._grid_cache = None
        self._lut_cache = {}  # 增進：CRT 查表法高效快取

        # 零分配優化：預先建立靜態隨機噪點層，防止 CRT 濾波器重複開闢內存
        self._noise_buffer = np.random.randint(-25, 25, (2160, 3840, 1), dtype=np.int16)

        # 全域特效擴充快取
        self._sediment_buffer = None   # 質地沉澱專用環形畫布
        self._mosh_vector = None       # Data-moshing 向量快取
        self._fluid_scale = 1.0        # 流體模擬半徑動態縮放
        
        self.scanner_y = 0.0
        self.scanner_x = 0.0
        self._section_sig_cache = {}
        self._fx_cooldown = {}

        self.fx_active_states = {
            'spatial_warping': 0.0, 'fluid_noise': 0.0, 'temporal_feedback': 0.0,
            'color_spectral': 0.0, 'glow_illumination': 0.0, 'retro_degradation': 0.0,
            'pixel_sort': 0.0, 'kaleidoscope': 0.0, 'ambient_dsp': 0.0,
            # 全域空間維度重組通道
            'data_mosh': 0.0, 'sedimentation': 0.0, 'vector_scan': 0.0, 'temporal_fractal': 0.0,
            # 新增 VJ 特效
            'kuwahara_paint': 0.0, 'matrix_ascii': 0.0, 'reaction_diffusion': 0.0,
            # 自訂擴充特效
            'thermal_vision': 0.0, 'scanline_glitch': 0.0, 'frame_drop': 0.0,
            'dynamic_mosaic': 0.0, 'pixel_art': 0.0, 'handheld_camera': 0.0,
            'stylized_fade': 0.0, 'zoom_pulse': 0.0,
            # 新增創意濾鏡
            'photocopy_smear': 0.0, 'collage_cutout': 0.0,
            # 頂級全域後製特效擴充 (Global Post-FX Matrix)
            'film_burn': 0.0, 'blueprint_edge': 0.0, 'turing_pattern': 0.0,
            'point_cloud_depth': 0.0, 'vector_scope': 0.0, 'lowpass_muffle': 0.0,
            'infinity_tunnel': 0.0, 'dolly_zoom': 0.0
        }
        self._effect_variants = {}
        
        # 新特效快取狀態初始化
        self._frame_drop_cache = None
        self._frame_drop_last_t = 0.0
        self._cam_drift_x = 0.0
        self._cam_drift_y = 0.0
        self._turing_A = None
        self._turing_B = None

        # Time-Vessel Matrix (走馬燈時間卷軸矩陣，滾動歷史緩衝區，預設 2 秒 @ 30fps，16 個特徵維度)
        self.time_vessel_size = 60
        self.time_vessel_dim = 16
        self.time_vessel = np.zeros((self.time_vessel_size, self.time_vessel_dim), dtype=np.float32)

        # 歌曲專屬隨機引擎初始化
        import hashlib
        self.seed_string = seed_string
        if seed_string:
            hash_val = int(hashlib.md5(seed_string.encode('utf-8')).hexdigest(), 16)
            self.rng = random.Random(hash_val)
            logger.info(f"Initialized PostProcessor with seed string: {seed_string} (hash: {hash_val})")
        else:
            self.rng = random.Random()
            logger.info("Initialized PostProcessor without seed string (non-deterministic mode)")

        # 五大視覺美學主題風格包
        self.theme_pools = {
            'CyberGlitch': ['data_mosh', 'pixel_sort', 'scanline_glitch', 'matrix_ascii', 'phase_slit', 'centroid_glitch', 'film_burn', 'vector_scope'],
            'RetroAnalog': ['retro_degradation', 'vector_scan', 'frame_drop', 'handheld_camera', 'stylized_fade', 'photocopy_smear', 'blueprint_edge', 'lowpass_muffle'],
            'DreamyArtistic': ['glow_illumination', 'kuwahara_paint', 'temporal_feedback', 'sedimentation', 'fluid_noise', 'collage_cutout', 'turing_pattern', 'point_cloud_depth'],
            'Psychedelic': ['color_spectral', 'thermal_vision', 'kaleidoscope', 'reaction_diffusion', 'spatial_warping', 'infinity_tunnel'],
            'DigitalPixel': ['dynamic_mosaic', 'pixel_art', 'zoom_pulse', 'temporal_fractal', 'dolly_zoom']
        }
        
        # 建立跨主題全域特效集合（用於 is_sig 門控判斷）
        self._all_pool_effects = set()
        for pool in self.theme_pools.values():
            self._all_pool_effects.update(pool)

        # 根據 genre 篩選主題範圍
        genre_clean = genre.lower().strip() if isinstance(genre, str) else 'generic'
        if genre_clean in ('lo-fi', 'ambient', 'jazz', 'classical'):
            allowed_themes = ['DreamyArtistic', 'RetroAnalog']
        elif genre_clean in ('rock', 'metal', 'punk', 'electronic', 'dance', 'techno'):
            allowed_themes = ['CyberGlitch', 'Psychedelic', 'DigitalPixel']
        else:
            allowed_themes = list(self.theme_pools.keys())

        # 跨曲目主題去重：優先選擇批次中頻率最低的主題，確保 12 首歌均勻分佈
        if used_themes:
            counts = {t: used_themes.count(t) for t in allowed_themes}
            min_count = min(counts.values())
            allowed_themes = [t for t, c in counts.items() if counts[t] == min_count]
            
        self.selected_theme = self.rng.choice(allowed_themes)
        self.signature_pool = self.theme_pools[self.selected_theme]
        
        # 選擇 2 ~ 3 個招牌特效，限制在主題包內以降低跨曲目重複率
        num_sig = self.rng.randint(2, 3)
        self.signature_effects = set(self.rng.sample(self.signature_pool, num_sig))
        logger.info(f"Selected Theme: {self.selected_theme} | Signature effects: {sorted(list(self.signature_effects))}")

        # Generate a distinct color palette for data mosh blocks based on the song seed
        self.mosh_palette = []
        base_hue = self.rng.randint(0, 360)
        for i in range(5):
            hue = (base_hue + i * 24) % 360
            r, g, b = self._hue_to_rgb(hue)
            self.mosh_palette.append((r, g, b))

        # Generate song-specific effect modifiers based on self.rng (seeded per song)
        self.effect_modifiers = {}
        # Make sure all signature pool effects have modifiers
        for theme_fxs in self.theme_pools.values():
            for fx in theme_fxs:
                # 預設隨機選擇變種
                num_variants = self.rng.randint(2, 4)
                allowed_vars = self.rng.sample(range(5), num_variants)
                
                # 對高特徵/偏綠等特效進行特定限制，提升每首歌的獨特性
                if fx == 'pixel_art':
                    # 防止綠色 CRT(4) 和 GameBoy(0) 在同一首歌頻繁交替出現，且限制變種數為 2
                    allowed_vars = [1, 2, 3] # 非綠色基礎變種
                    green_var = self.rng.choice([0, 4])
                    if self.rng.random() < 0.4:
                        allowed_vars.append(green_var)
                    self.rng.shuffle(allowed_vars)
                    allowed_vars = allowed_vars[:2]
                elif fx == 'color_spectral':
                    # 熱成像(2)是強烈的 Psychedelic 風格，非此主題或 CyberGlitch 時避免出現
                    allowed_vars = [0, 1, 3, 4]
                    if self.selected_theme in ('Psychedelic', 'CyberGlitch'):
                        allowed_vars.append(2)
                    self.rng.shuffle(allowed_vars)
                    allowed_vars = allowed_vars[:self.rng.randint(2, 3)]
                elif fx in ('glow_illumination', 'handheld_camera'):
                    # 限制變種數為 2，使單首曲目的動態/發光風格更加聚焦且與其他曲目區隔
                    self.rng.shuffle(allowed_vars)
                    allowed_vars = allowed_vars[:2]

                self.effect_modifiers[fx] = {
                    'speed': self.rng.uniform(0.65, 1.45),      # Speed of variant switching
                    'intensity': self.rng.uniform(0.75, 1.35),  # Strength modifier
                    'variants': allowed_vars                    # Allowed variants subset
                }


    def get_variant_index(self, key, t, is_beat):
        """為指定的特效種類獲取並快取動態變種索引 (0~4)
        每 8 秒自動遞增切換；重拍時有 20% 的機率隨機切換以增加不可預測性。
        """
        if key not in self._effect_variants:
            # Initialize variant index and offset deterministically using self.rng
            self._effect_variants[key] = {
                'index': self.rng.randint(0, 4),
                'offset': self.rng.randint(0, 1000)
            }
        
        state = self._effect_variants[key]
        modifiers = getattr(self, 'effect_modifiers', {}).get(key, {})
        speed_mult = modifiers.get('speed', 1.0)
        
        prob = 0.05 if key in ('frame_drop', 'handheld_camera') else 0.2
        if is_beat and self.rng.random() < prob:
            state['index'] = (state['index'] + self.rng.randint(1, 4)) % 5
        else:
            state['index'] = int((t * speed_mult + state['offset']) / 8.0) % 5
            
        raw_idx = state['index']
        allowed_variants = modifiers.get('variants', [0, 1, 2, 3, 4])
        if allowed_variants:
            return allowed_variants[raw_idx % len(allowed_variants)]
        return raw_idx

    def get_smoothed_val(self, key, target, dt, lambda_attack=15.0, lambda_decay=2.5):
        if key not in self.damping_filters:
            self.damping_filters[key] = DampingFilter(target, lambda_attack, lambda_decay)
        return self.damping_filters[key].update(target, dt)

    def get_normalized_val(self, key, val):
        if key not in self.baseline_adapters:
            self.baseline_adapters[key] = DynamicBaselineAdapter()
        return self.baseline_adapters[key].update_and_normalize(val)
    def apply_pitch_ribbon(self, img_np, t, intensity, chord_hue):
        try:
            h, w = img_np.shape[:2]
            points = []
            num_points = 24
            base_y = h / 2.0
            
            r_c, g_c, b_c = self._hue_to_rgb(chord_hue)
            for i in range(num_points):
                x = (w / (num_points - 1)) * i
                y = base_y + math.sin(t * 3.0 + i * 0.4) * (70.0 * intensity) * math.cos(t * 1.2 + i * 0.1)
                points.append((int(x), int(y)))
                
            points_arr = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
            
            overlay = img_np.copy()
            for w_offset in range(5, 0, -1):
                cv2.polylines(overlay, [points_arr], isClosed=False, color=(r_c, g_c, b_c), thickness=w_offset * 3, lineType=cv2.LINE_AA)
            
            alpha = min(1.0, 45.0 * intensity / 255.0)
            return cv2.addWeighted(img_np, 1.0 - alpha, overlay, alpha, 0)
        except Exception as e:
            logger.error(f"Error in pitch ribbon: {e}")
            return img_np

    def apply_strange_attractor_ribbon(self, img_np, audio_samples, hue, intensity):
        """利用音訊時域訊號重構相空間，在畫面上原位繪製原生聲音幾何吸引子線條"""
        if cv2 is None or audio_samples is None or len(audio_samples) < 64: return img_np
        try:
            h, w = img_np.shape[:2]
            tau = 4  # 延遲採樣點數
            
            # 建立相空間重構坐標 (X_t, Y_t)
            x_signal = audio_samples[:-tau]
            y_signal = audio_samples[tau:]
            
            # 將訊號範圍 (-1.0 ~ 1.0) 映射至畫面中心區域
            cx, cy = w // 2, h // 2
            scale = min(w, h) * 0.3 * intensity
            
            pts_x = (cx + x_signal * scale).astype(np.int32)
            pts_y = (cy + y_signal * scale).astype(np.int32)
            
            points = np.stack([pts_x, pts_y], axis=1).reshape((-1, 1, 2))
            
            # 繪製由聲音原生波形勾勒出的優美幾何扭結
            r, g, b = self._hue_to_rgb(hue)
            overlay = img_np.copy()
            # 繪製多層寬度以產生輝光 (Glow) 效果
            for w_offset in range(3, 0, -1):
                cv2.polylines(overlay, [points], isClosed=False, color=(r, g, b), thickness=w_offset * 2, lineType=cv2.LINE_AA)
            
            alpha = min(1.0, 0.4 * intensity)
            return cv2.addWeighted(img_np, 1.0 - alpha, overlay, alpha, 0)
        except Exception as e:
            logger.error(f"Error in strange attractor ribbon: {e}")
            return img_np

    def _hue_to_rgb(self, hue):
        h_val = (hue / 360.0) if hue > 1.0 else float(hue)
        h_val = h_val % 1.0
        r = g = b = 0.0
        i = int(h_val * 6.0)
        f = h_val * 6.0 - i
        q, t_h = 1.0 - f, f
        i = i % 6
        if i == 0: r, g, b = 1.0, t_h, 0.0
        elif i == 1: r, g, b = q, 1.0, 0.0
        elif i == 2: r, g, b = 0.0, 1.0, t_h
        elif i == 3: r, g, b = 0.0, q, 1.0
        elif i == 4: r, g, b = t_h, 0.0, 1.0
        elif i == 5: r, g, b = 1.0, 0.0, q
        return (int(r * 255), int(g * 255), int(b * 255))

    def _get_audio_feature_mask(self, w, h, audio_feats, smoothed_sub_bass, smoothed_percussive, smoothed_roughness, smoothed_ethereal, beat_energy, anticipation_factor, fx_intensity, t):
        try:
            r0 = [smoothed_sub_bass, smoothed_percussive, smoothed_roughness, smoothed_ethereal]
            harmonic = audio_feats.get('harmonic', 0.5)
            chord_brightness = audio_feats.get('chord_brightness', 0.1)
            stereo_width = audio_feats.get('stereo_width', 0.5)
            centroid = audio_feats.get('centroid', 0.2)
            r1 = [harmonic, chord_brightness, stereo_width, centroid]
            r2 = [beat_energy, anticipation_factor, audio_feats.get('silence_fade', 0.0), fx_intensity]
            r3 = [
                smoothed_sub_bass * (0.5 + 0.5 * math.sin(t * 2.0)),
                smoothed_percussive * (0.5 + 0.5 * math.cos(t * 1.5)),
                1.0 - smoothed_roughness,
                (smoothed_ethereal + centroid) * 0.5
            ]
            audio_block = np.array([r0, r1, r2, r3], dtype=np.float32)
            audio_block = np.clip(audio_block, 0.0, 1.0)
            feature_mask = cv2.resize(audio_block, (w, h), interpolation=cv2.INTER_NEAREST)
            return feature_mask
        except Exception:
            return np.ones((h, w), dtype=np.float32) * 0.5

    def process(self, img, t, is_beat, beat_energy, audio_feats, fx_flags, fx_prob=0.25, fx_intensity=0.5, adaptive_modulation=True, section_name='Verse', section_progress=0.0, genre='Generic'):
        self.photosensitive_safe = True  # Mandatory full song photosensitive protection
        original_size = img.size
        w, h = original_size
        genre_clean = genre.lower().strip() if isinstance(genre, str) else 'generic'
        is_scaled = False
        bypass_downscale = fx_flags.get('bypass_downscale', False) if fx_flags else False
        if w > 1920 and not bypass_downscale:
            scale_ratio = 1920.0 / w
            w_target = 1920
            h_target = int(h * scale_ratio)
            img = img.resize((w_target, h_target), Image.Resampling.BICUBIC)
            is_scaled = True
            w, h = w_target, h_target

        dt = t - self.last_t
        if dt <= 0 or dt > 0.2: dt = 1.0 / 30.0
        self.last_t = t

        # 1. 取得或生成本分鏡的招牌特效
        if section_name not in self._section_sig_cache:
            section_seed = f"{self.seed_string or ''}_{section_name}"
            import hashlib
            hash_val = int(hashlib.md5(section_seed.encode('utf-8')).hexdigest(), 16)
            sect_rng = random.Random(hash_val)
            # 每個分鏡從本歌的主題包內挑選 2 ~ 3 個特效作為招牌
            num_sig = sect_rng.randint(2, 3)
            sect_sigs = set(sect_rng.sample(self.signature_pool, min(len(self.signature_pool), num_sig)))
            self._section_sig_cache[section_name] = sect_sigs
            logger.info(f"[PostProcessor] Song Theme: {self.selected_theme} | Section '{section_name}' effects: {sorted(list(sect_sigs))}")
            
        current_sig_effects = self._section_sig_cache[section_name]

        # 狀態閘門（Gating）：計算環境 persistent 特效水平
        base_level = max(0.0, (fx_prob - 0.25) / 0.75) if fx_prob > 0.25 else 0.0
        base_level = min(0.15, base_level)  # 限制常駐特效基線最大為 0.15
        
        # 瞬態特效（重度特效），完全不套用基線
        transient_only_effects = {
            'data_mosh', 'pixel_sort', 'matrix_ascii', 'reaction_diffusion', 
            'centroid_glitch', 'phase_slit', 'temporal_fractal', 'scanline_glitch', 
            'dynamic_mosaic', 'pixel_art', 'spatial_warping', 'fluid_noise', 
            'temporal_feedback', 'kaleidoscope', 'vector_scan', 'photocopy_smear', 'collage_cutout',
            'film_burn', 'blueprint_edge', 'turing_pattern', 'point_cloud_depth', 'vector_scope',
            'lowpass_muffle', 'infinity_tunnel', 'dolly_zoom'
        }

        for fx_name in self.fx_active_states:
            # 嚴格門控：屬於任何主題池的特效，若不在當前分鏡簽名中，則完全抑制
            # 只有不屬於任何主題池的公用特效 (如 ambient_dsp) 才免門控
            is_sig = fx_name in current_sig_effects or fx_name not in self._all_pool_effects
            if fx_name in transient_only_effects:
                eff_base = 0.0
            else:
                eff_base = base_level if is_sig else 0.0
            self.fx_active_states[fx_name] = max(eff_base, self.fx_active_states[fx_name] - dt * 1.5)

        # 2. 拍點冷卻處理
        for k in list(self._fx_cooldown.keys()):
            if self._fx_cooldown[k] > 0:
                self._fx_cooldown[k] -= 1

        if is_beat:
            if self.rng.random() < fx_prob:
                # 75% 機率選擇當前分鏡招牌，25% 選擇主題包 Wildcard
                pool_to_choose = current_sig_effects
                if self.rng.random() < 0.25:
                    pool_to_choose = self.signature_pool
                
                # 排除冷卻中特效
                available_fxs = [fx for fx in pool_to_choose if fx in self.fx_active_states and self._fx_cooldown.get(fx, 0) == 0]
                if not available_fxs:
                    available_fxs = [fx for fx in pool_to_choose if fx in self.fx_active_states]
                    
                if available_fxs:
                    num_to_trigger = 1 if self.rng.random() < 0.85 else 2
                    triggered_fxs = self.rng.sample(available_fxs, min(len(available_fxs), num_to_trigger))
                    for fx_name in triggered_fxs:
                        self.fx_active_states[fx_name] = max(
                            self.fx_active_states[fx_name],
                            min(1.0, 0.4 + 0.6 * beat_energy)
                        )
                        self._fx_cooldown[fx_name] = 3  # 設定 3 次拍點冷卻

        # 聲學特徵提取與基線自適應
        sub_bass = self.get_normalized_val('sub_bass', audio_feats.get('sub_bass', 0.0))
        percussive = self.get_normalized_val('percussive', audio_feats.get('percussive', 0.0))
        roughness = audio_feats.get('roughness', 0.0)
        ethereal = audio_feats.get('ethereal', 0.0)
        silence_fade = audio_feats.get('silence_fade', 0.0)
        harmonic = audio_feats.get('harmonic', 0.5)
        chord_brightness = audio_feats.get('chord_brightness', 0.1)
        chord_hue = audio_feats.get('chord_hue', 180.0)

        # 阻尼平滑緩衝
        smoothed_sub_bass = self.get_smoothed_val('sub_bass', sub_bass, dt, 15.0, 2.0)
        smoothed_roughness = self.get_smoothed_val('roughness', roughness, dt, 12.0, 2.5)
        smoothed_ethereal = self.get_smoothed_val('ethereal', ethereal, dt, 8.0, 1.8)
        smoothed_percussive = self.get_smoothed_val('percussive', percussive, dt, 18.0, 2.2)

        # 更新時間容器 (time_vessel) 歷史緩衝區
        curr_feats = np.array([
            smoothed_sub_bass,
            smoothed_percussive,
            smoothed_roughness,
            smoothed_ethereal,
            beat_energy,
            audio_feats.get('anticipation', 0.0),
            harmonic,
            chord_brightness,
            audio_feats.get('stereo_width', 0.5),
            audio_feats.get('centroid', 0.2),
            audio_feats.get('tempo', 120.0) / 200.0,
            silence_fade,
            fx_intensity,
            0.5 + 0.5 * math.sin(t),
            0.5 + 0.5 * math.cos(t * 1.5),
            0.0
        ], dtype=np.float32)
        self.time_vessel = np.roll(self.time_vessel, -1, axis=0)
        self.time_vessel[-1, :] = curr_feats

        # 建立並保存特徵映射遮罩層 (Feature Mapping Mask)
        self.feature_mask = self._get_audio_feature_mask(
            w, h, audio_feats, smoothed_sub_bass, smoothed_percussive,
            smoothed_roughness, smoothed_ethereal, beat_energy,
            audio_feats.get('anticipation', 0.0), fx_intensity, t
        )

        # 瞬態突變（Delta Onset）計算
        delta_percussive = 0.0
        if len(self.percussive_history) >= 3:
            delta_percussive = audio_feats.get('percussive', 0.0) - (sum(self.percussive_history) / 3)
        self.percussive_history.append(audio_feats.get('percussive', 0.0))
        if len(self.percussive_history) > 3: self.percussive_history.pop(0)

        # 瞬態色彩閃爍觸發 — 限定 CyberGlitch / Psychedelic 主題以降低跨曲目同質化
        if delta_percussive > 0.45 and genre_clean not in ('lo-fi', 'ambient', 'jazz'):
            if not self.photosensitive_safe and self.selected_theme in ('CyberGlitch', 'Psychedelic'):
                self.invert_frame_timer = 2

        # 搖滾樂特徵震鏡（Screen Shake）- 限定 CyberGlitch 主題，其他主題交由 handheld_camera 處理
        if (genre_clean in ('rock', 'metal', 'punk')) and self.selected_theme == 'CyberGlitch' and fx_flags.get('spatial_warping', True) and is_beat and beat_energy > 0.4:
            shake = int(12 * fx_intensity * beat_energy)
            if shake > 0: img = ImageChops.offset(img, self.rng.randint(-shake, shake), self.rng.randint(-shake, shake))

        # 旋律樂器絲帶（Pitch Ribbon）
        if (genre_clean in ('jazz', 'classical', 'ambient')) and fx_flags.get('spatial_warping', True) and section_name in ('Verse', 'Chorus', 'Bridge'):
            if smoothed_ethereal * fx_intensity > 0.05: img = self.apply_pitch_ribbon(img, t, smoothed_ethereal * fx_intensity, chord_hue)

        # 情緒自適應調製（Valence-Arousal Model - 亢奮蓄水池與和弦張力感知極限版）
        if not hasattr(self, 'arousal_reservoir'):
            self.arousal_reservoir = 0.0
        if not hasattr(self, 'last_chord_name'):
            self.last_chord_name = 'N.C.'
        if not hasattr(self, 'chord_tension'):
            self.chord_tension = 0.0
        
        # 1. 提取微觀音訊進階特徵
        stereo_width = audio_feats.get('stereo_width', 0.5)      # 0.0(Mono) ~ 1.0(Wide)
        spectral_centroid = audio_feats.get('centroid', 0.2)     # 0.0(Low-Fi) ~ 1.0(Bright)
        bpm = audio_feats.get('bpm', 120.0)
        
        # 2. 計算 BPM 實時相位與正拍預期心理 (Anticipation)
        beat_duration = 60.0 / max(1.0, bpm)
        beat_phase = (t % beat_duration) / beat_duration  # 0.0 ~ 1.0 的滾動鋸齒波
        
        # 預期因子：當接近正拍 (例如最後 15% 的時間) 時，開始蓄力
        anticipation_factor = max(0.0, (beat_phase - 0.85) / 0.15) if beat_phase > 0.85 else 0.0

        # 3. 頻譜質心驅動流體動力學（調製渦流質地）
        # 高頻時流體變敏銳、細碎；低頻時流體變巨大、黏稠
        target_fluid_scale = 0.3 + 1.7 * (1.0 - spectral_centroid)
        self._fluid_scale += (target_fluid_scale - self._fluid_scale) * (1.0 - math.exp(-10.0 * dt))

        # 1. 實時基礎情緒計算
        instant_arousal = smoothed_sub_bass * 0.4 + smoothed_percussive * 0.4 + (1.0 - beat_phase) * 0.2
        valence = harmonic * 0.6 + chord_brightness * 0.4
        
        # 計算 Arousal 一階加速度
        if not hasattr(self, '_last_arousal'):
            self._last_arousal = 0.0
        delta_arousal = max(0.0, instant_arousal - self._last_arousal)
        self._last_arousal = instant_arousal

        # 2. 亢奮蓄水池 (Arousal Reservoir) 非線性動力學
        decay_rate = 1.2 + 0.8 * audio_feats.get('ethereal', 0.0)
        self.arousal_reservoir = self.arousal_reservoir * math.exp(-decay_rate * dt) + delta_arousal * 1.5
        self.arousal_reservoir = max(instant_arousal, min(2.0, self.arousal_reservoir)) # 確保不低於實時能量

        # 結合蓄水池與瞬時能量作為最終調製使用的 arousal
        arousal = self.arousal_reservoir

        # 3. 和弦張力感知 (Harmonic Tension & Circle of Fifths Distance)
        circle_of_fifths = {
            'C': 0, 'G': 1, 'D': 2, 'A': 3, 'E': 4, 'B': 5, 'F#': 6, 'Gb': 6,
            'C#': 7, 'Db': 7, 'G#': 8, 'Ab': 8, 'D#': 9, 'Eb': 9,
            'A#': 10, 'Bb': 10, 'F': 11
        }
        
        # 基礎張力隨時間衰減
        self.chord_tension *= math.exp(-dt * 3.0)
        current_chord = audio_feats.get('chord_name', 'N.C.')
        
        def get_root(name):
            if not name or name == 'N.C.':
                return None
            r = name[:2] if len(name) > 1 and name[1] in ('#', 'b') else name[0]
            if len(r) > 1:
                r = r[0].upper() + r[1].lower()
            else:
                r = r.upper()
            return r if r in circle_of_fifths else None

        if current_chord != self.last_chord_name:
            curr_root = get_root(current_chord)
            prev_root = get_root(self.last_chord_name)
            curr_lower = current_chord.lower()
            
            new_tension = 0.0
            if curr_root and prev_root:
                curr_pos = circle_of_fifths[curr_root]
                prev_pos = circle_of_fifths[prev_root]
                dist = abs(curr_pos - prev_pos)
                dist = min(dist, 12 - dist)
                new_tension = dist / 6.0  # 最大對角線張力 1.0
                
                # 解決 (Resolution)：如果回到相鄰五度/同音協和和弦，且無張力字尾，張力立刻解決
                if dist <= 1 and not any(t in curr_lower for t in ('dim', 'aug', '7', '9', 'b5')):
                    self.chord_tension = 0.0
                    new_tension = 0.0
            
            # 疊加不協和字尾張力
            if any(t in curr_lower for t in ('dim', 'aug', '7', '9', 'b5')):
                suffix_tension = 0.6 + 0.4 * smoothed_roughness
                new_tension = max(new_tension, suffix_tension)
            
            if new_tension > 0.0:
                self.chord_tension = max(self.chord_tension, new_tension)
                
            self.last_chord_name = current_chord
            
        chord_tension = self.chord_tension
        base_mult = fx_intensity

        # 4. 樂器音色密度評估 (用於適應性調色)
        timbre_density = (sub_bass * 0.3 + percussive * 0.3 + roughness * 0.2 + ethereal * 0.2)

        if adaptive_modulation:
            # 5. 連續二維空間調製：引入蓄水池與和弦張力
            # 混亂度（加上和弦張力刺激）
            turbulence = self.arousal_reservoir * (1.0 - valence) + chord_tension * 0.5
            # 璀璨度
            brilliance = self.arousal_reservoir * valence
            # 空靈度
            ethereal_ambience = (1.0 - min(1.0, self.arousal_reservoir)) * valence

            # 6. 特效通道乘數映射 (Multipliers)
            # 幾何畸變由立體聲寬度支配
            m_dist = base_mult * (arousal * 0.7 + stereo_width * 0.8)
            m_mosh = base_mult * (turbulence * 1.0 + (1.0 - beat_phase) * 0.8)
            m_pixel = base_mult * (turbulence * 1.4 + smoothed_roughness * 0.6)
            m_color = base_mult * (brilliance * 1.0 + chord_tension * 1.2)
            m_sediment = base_mult * (ethereal_ambience * 1.5 + smoothed_sub_bass * 0.6)
            m_retro = base_mult * (smoothed_roughness * 1.3 + self.arousal_reservoir * 0.3)
            m_fluid = base_mult * (self.arousal_reservoir * 1.0 + turbulence * 0.4)
            
            m_glow = base_mult * (brilliance * 1.2 + arousal * 0.5 - anticipation_factor * 0.3)
            m_glow = max(0.0, m_glow)

            m_vscan = base_mult * (smoothed_percussive * 0.8 + brilliance * 0.6)
            
            m_kaleidoscope = base_mult * (self.fx_active_states['kaleidoscope'] * (0.5 + stereo_width * 0.5))
            self._k_cx_offset = int((stereo_width - 0.5) * 200.0 * base_mult)
            
            m_fractal = base_mult * (ethereal_ambience * 1.4 + stereo_width * 0.4)
            m_feed = base_mult * (ethereal_ambience * 1.3 + smoothed_ethereal * 0.5)
            if delta_arousal > 0.3:
                m_feed *= 0.2

            # 新特效乘數
            m_kuwahara = base_mult * (ethereal_ambience * 1.5 + smoothed_ethereal * 0.5)
            m_matrix = base_mult * (smoothed_percussive * 1.2 + smoothed_roughness * 0.6)
            m_reaction = base_mult * (self.arousal_reservoir * 1.2 + sub_bass * 0.8)
            
            # 自訂新增特效乘數
            m_thermal = base_mult * (brilliance * 1.1 + chord_brightness * 0.8)
            m_scanglitch = base_mult * (turbulence * 1.2 + smoothed_roughness * 0.6)
            m_framedrop = base_mult * (ethereal_ambience * 0.8 + (1.0 - beat_phase) * 0.6)
            m_mosaic = base_mult * (smoothed_sub_bass * 1.3 + turbulence * 0.5)
            m_pixelart = base_mult * (valence * 1.0 + smoothed_ethereal * 0.8)
            m_handheld = base_mult * (arousal * 0.9 + smoothed_roughness * 0.4)
            m_stylizedfade = base_mult * silence_fade
            m_zoompulse = base_mult * (smoothed_sub_bass * 1.2 + beat_energy * 0.8)
            
            # 新增影印掃描與拼貼濾鏡乘數
            m_photocopy = base_mult * (smoothed_percussive * 1.1 + smoothed_roughness * 0.5)
            m_collage = base_mult * (ethereal_ambience * 1.3 + (1.0 - beat_phase) * 0.6)

            # 頂級全域後製特效矩陣擴充乘數 (Global Post-FX Matrix)
            m_filmburn = base_mult * (smoothed_sub_bass * 1.2 + smoothed_roughness * 0.8)
            m_blueprint = base_mult * (harmonic * 1.1 + chord_brightness * 0.6)
            m_turing = base_mult * (smoothed_ethereal * 1.2 + smoothed_percussive * 0.6)
            m_pointcloud = base_mult * (smoothed_sub_bass * 1.1 + stereo_width * 0.7)
            m_vectorscope = base_mult * (stereo_width * 1.2 + chord_brightness * 0.5)
            m_lowpass = base_mult * (audio_feats.get('lowpass', 0.0) * 1.5)
            m_infinity = base_mult * (beat_energy * 1.2 + section_progress * 0.5)
            m_dollyzoom = base_mult * (anticipation_factor * 1.4 + beat_energy * 0.6)
        else:
            m_dist = m_fluid = m_feed = m_color = m_glow = m_retro = m_pixel = base_mult
            m_mosh = m_sediment = m_vscan = m_fractal = base_mult
            m_kaleidoscope = base_mult
            m_kuwahara = m_matrix = m_reaction = base_mult
            m_thermal = m_scanglitch = m_framedrop = m_mosaic = m_pixelart = m_handheld = m_stylizedfade = m_zoompulse = base_mult
            m_photocopy = m_collage = base_mult
            m_filmburn = m_blueprint = m_turing = m_pointcloud = m_vectorscope = m_lowpass = m_infinity = m_dollyzoom = base_mult
            self._k_cx_offset = int((stereo_width - 0.5) * 200.0 * base_mult)

        # 影片結構分鏡權重優化
        if section_name in ('Intro', 'Outro'):
            m_dist *= 0.15; m_fluid *= 0.5; m_feed *= 0.4; m_color *= 0.3; m_glow *= 1.1; m_retro *= 0.3; m_pixel *= 0.0
            m_mosh *= 0.0; m_sediment *= 0.6; m_vscan *= 0.2; m_fractal *= 0.3
            m_kaleidoscope *= 0.1
            m_kuwahara *= 1.2; m_matrix *= 0.1; m_reaction *= 0.3
            m_thermal *= 0.2; m_scanglitch *= 0.1; m_framedrop *= 1.2; m_mosaic *= 0.1; m_pixelart *= 0.3; m_handheld *= 0.4; m_zoompulse *= 0.2
            m_photocopy *= 0.1; m_collage *= 0.4
            m_filmburn *= 0.3; m_blueprint *= 0.8; m_turing *= 0.5; m_pointcloud *= 0.4; m_vectorscope *= 0.2; m_lowpass *= 1.2; m_infinity *= 0.3; m_dollyzoom *= 0.2
        elif section_name == 'Build-up':
            pf = 0.4 + 1.2 * section_progress
            m_dist *= 0.7*pf; m_fluid *= 0.6*pf; m_feed *= 0.8*pf; m_color *= 1.2*pf; m_glow *= 1.3*pf; m_retro *= 0.8*pf; m_pixel *= 0.7*pf
            m_mosh *= 0.5*pf; m_sediment *= 0.8*pf; m_vscan *= 1.0*pf; m_fractal *= 0.6*pf; m_kaleidoscope *= 0.8*pf
            m_kuwahara *= 0.7*pf; m_matrix *= 1.2*pf; m_reaction *= 1.1*pf
            m_thermal *= 0.8*pf; m_scanglitch *= 1.0*pf; m_framedrop *= 0.6*pf; m_mosaic *= 0.8*pf; m_pixelart *= 0.9*pf; m_handheld *= 0.9*pf; m_zoompulse *= 1.1*pf
            m_photocopy *= 0.9*pf; m_collage *= 0.8*pf
            m_filmburn *= 0.8*pf; m_blueprint *= 0.9*pf; m_turing *= 0.7*pf; m_pointcloud *= 0.9*pf; m_vectorscope *= 1.1*pf; m_lowpass *= 0.5*pf; m_infinity *= 1.0*pf; m_dollyzoom *= (1.0 + 0.8*anticipation_factor)
        elif section_name in ('Drop', 'Chorus'):
            ef = 1.3 + 0.6 * arousal
            m_dist *= 1.5*ef; m_fluid *= (0.8 + 0.6*smoothed_percussive); m_feed *= (0.7 + 0.6*smoothed_ethereal)
            m_color *= (1.2 + 0.8*smoothed_roughness); m_glow *= 1.3*ef; m_retro *= (1.0 + 0.4*smoothed_sub_bass); m_pixel *= (1.4 + 1.0 * smoothed_roughness)
            m_mosh *= (1.5 + 0.8*smoothed_roughness); m_sediment *= (0.6 + 0.4*smoothed_sub_bass); m_vscan *= 1.4*ef; m_fractal *= (1.0 + 0.5*smoothed_ethereal)
            m_kaleidoscope *= 1.4*ef
            m_kuwahara *= 0.5*ef; m_matrix *= 1.4*ef; m_reaction *= 1.5*ef
            m_thermal *= 1.3*ef; m_scanglitch *= (1.2 + 0.6*smoothed_roughness); m_framedrop *= (0.5 + 0.3*arousal); m_mosaic *= (1.4 + 0.8*smoothed_sub_bass); m_pixelart *= 1.1*ef; m_handheld *= (1.2 + 0.6*smoothed_roughness); m_zoompulse *= 1.5*ef
            m_photocopy *= (1.2 + 0.6*smoothed_percussive); m_collage *= (1.1 + 0.5*smoothed_ethereal)
            m_filmburn *= 1.4*ef; m_blueprint *= 0.6*ef; m_turing *= 1.2*ef; m_pointcloud *= 1.5*ef; m_vectorscope *= 1.4*ef; m_lowpass *= 0.2*ef; m_infinity *= 1.5*ef; m_dollyzoom *= 1.3*ef

        if genre_clean in ('lo-fi', 'ambient', 'jazz'):
            m_dist = 0.0; m_fluid = base_mult*0.7; m_feed = base_mult*0.8; m_color = base_mult*0.1; m_glow = base_mult*1.1; m_pixel = 0.0
            m_mosh = 0.0; m_sediment = base_mult*1.0; m_vscan = base_mult*0.4; m_fractal = base_mult*0.9; m_kaleidoscope = base_mult*0.5
            m_kuwahara *= 1.3; m_matrix *= 0.3; m_reaction *= 0.5
            m_thermal *= 0.4; m_scanglitch *= 0.2; m_framedrop *= 1.3; m_mosaic *= 0.2; m_pixelart *= 0.8; m_handheld *= 0.5; m_zoompulse *= 0.4
            m_photocopy *= 0.3; m_collage *= 0.8
            m_filmburn *= 0.6; m_blueprint *= 1.1; m_turing *= 1.2; m_pointcloud *= 0.7; m_vectorscope *= 0.3; m_lowpass *= 1.4; m_infinity *= 0.6; m_dollyzoom *= 0.4

        # 機率閘門動態相乘
        m_dist *= self.fx_active_states['spatial_warping']
        m_fluid *= self.fx_active_states['fluid_noise']
        m_feed *= self.fx_active_states['temporal_feedback']
        m_color *= self.fx_active_states['color_spectral']
        m_glow *= self.fx_active_states['glow_illumination']
        m_retro *= self.fx_active_states['retro_degradation']
        m_pixel *= self.fx_active_states['pixel_sort']
        m_mosh *= self.fx_active_states['data_mosh']
        m_sediment *= self.fx_active_states['sedimentation']
        m_vscan *= self.fx_active_states['vector_scan']
        m_fractal *= self.fx_active_states['temporal_fractal']
        m_kaleidoscope *= self.fx_active_states['kaleidoscope']
        m_kuwahara *= self.fx_active_states['kuwahara_paint']
        m_matrix *= self.fx_active_states['matrix_ascii']
        m_reaction *= self.fx_active_states['reaction_diffusion']
        # 新特效機率閘門
        m_thermal *= self.fx_active_states['thermal_vision']
        m_scanglitch *= self.fx_active_states['scanline_glitch']
        m_framedrop *= self.fx_active_states['frame_drop']
        m_mosaic *= self.fx_active_states['dynamic_mosaic']
        m_pixelart *= self.fx_active_states['pixel_art']
        m_handheld *= self.fx_active_states['handheld_camera']
        m_zoompulse *= self.fx_active_states['zoom_pulse']
        m_photocopy *= self.fx_active_states['photocopy_smear']
        m_collage *= self.fx_active_states['collage_cutout']
        m_filmburn *= self.fx_active_states['film_burn']
        m_blueprint *= self.fx_active_states['blueprint_edge']
        m_turing *= self.fx_active_states['turing_pattern']
        m_pointcloud *= self.fx_active_states['point_cloud_depth']
        m_vectorscope *= self.fx_active_states['vector_scope']
        m_lowpass *= self.fx_active_states['lowpass_muffle']
        m_infinity *= self.fx_active_states['infinity_tunnel']
        m_dollyzoom *= self.fx_active_states['dolly_zoom']

        # Apply song-specific dynamic intensity modifier adjustments
        modifiers = getattr(self, 'effect_modifiers', {})
        if modifiers:
            m_dist *= modifiers.get('spatial_warping', {}).get('intensity', 1.0)
            m_fluid *= modifiers.get('fluid_noise', {}).get('intensity', 1.0)
            m_feed *= modifiers.get('temporal_feedback', {}).get('intensity', 1.0)
            m_color *= modifiers.get('color_spectral', {}).get('intensity', 1.0)
            m_glow *= modifiers.get('glow_illumination', {}).get('intensity', 1.0)
            m_retro *= modifiers.get('retro_degradation', {}).get('intensity', 1.0)
            m_pixel *= modifiers.get('pixel_sort', {}).get('intensity', 1.0)
            m_mosh *= modifiers.get('data_mosh', {}).get('intensity', 1.0)
            m_sediment *= modifiers.get('sedimentation', {}).get('intensity', 1.0)
            m_vscan *= modifiers.get('vector_scan', {}).get('intensity', 1.0)
            m_fractal *= modifiers.get('temporal_fractal', {}).get('intensity', 1.0)
            m_kaleidoscope *= modifiers.get('kaleidoscope', {}).get('intensity', 1.0)
            m_kuwahara *= modifiers.get('kuwahara_paint', {}).get('intensity', 1.0)
            m_matrix *= modifiers.get('matrix_ascii', {}).get('intensity', 1.0)
            m_reaction *= modifiers.get('reaction_diffusion', {}).get('intensity', 1.0)
            # 自訂新增特效 modifiers 調整
            m_thermal *= modifiers.get('thermal_vision', {}).get('intensity', 1.0)
            m_scanglitch *= modifiers.get('scanline_glitch', {}).get('intensity', 1.0)
            m_framedrop *= modifiers.get('frame_drop', {}).get('intensity', 1.0)
            m_mosaic *= modifiers.get('dynamic_mosaic', {}).get('intensity', 1.0)
            m_pixelart *= modifiers.get('pixel_art', {}).get('intensity', 1.0)
            m_handheld *= modifiers.get('handheld_camera', {}).get('intensity', 1.0)
            m_stylizedfade *= modifiers.get('stylized_fade', {}).get('intensity', 1.0)
            m_zoompulse *= modifiers.get('zoom_pulse', {}).get('intensity', 1.0)
            m_photocopy *= modifiers.get('photocopy_smear', {}).get('intensity', 1.0)
            m_collage *= modifiers.get('collage_cutout', {}).get('intensity', 1.0)
            m_filmburn *= modifiers.get('film_burn', {}).get('intensity', 1.0)
            m_blueprint *= modifiers.get('blueprint_edge', {}).get('intensity', 1.0)
            m_turing *= modifiers.get('turing_pattern', {}).get('intensity', 1.0)
            m_pointcloud *= modifiers.get('point_cloud_depth', {}).get('intensity', 1.0)
            m_vectorscope *= modifiers.get('vector_scope', {}).get('intensity', 1.0)
            m_lowpass *= modifiers.get('lowpass_muffle', {}).get('intensity', 1.0)
            m_infinity *= modifiers.get('infinity_tunnel', {}).get('intensity', 1.0)
            m_dollyzoom *= modifiers.get('dolly_zoom', {}).get('intensity', 1.0)

        # ═══════════════════════════════════════════════════════════
        # 統一 NumPy 流水線入口：盡早轉入 ndarray，最大幅度減少 PIL↔NumPy 轉型
        # ═══════════════════════════════════════════════════════════
        img_np = np.array(img.convert('RGB'))
        self.time_displacement_buffer.push(img_np)

        # [NEW DERIVATIVE 1]: Stereo Phase Slit-Scan (立體聲相位差時空剪切)
        if fx_flags.get('phase_slit', True) and 'phase_slit' in self.signature_effects and stereo_width > 0.6:
            var_idx = self.get_variant_index('phase_slit', t, is_beat)
            img_np = self.apply_phase_slit_custom(img_np, stereo_width, fx_intensity, var_idx)

        # [NEW DERIVATIVE 2]: Centroid Resonance Glitch (頻譜質心共振高頻破碎)
        if fx_flags.get('centroid_glitch', True) and 'centroid_glitch' in self.signature_effects and spectral_centroid > 0.5:
            var_idx = self.get_variant_index('centroid_glitch', t, is_beat)
            img_np = self.apply_centroid_glitch_custom(img_np, spectral_centroid, smoothed_roughness, fx_intensity, var_idx)

        # ── 特效渲染核心管線（多通道流水線） ──

        # [NEW PASS A]: Data-Moshing 數位空間維度撕裂 (ndarray 通路)
        if fx_flags.get('data_mosh', True) and m_mosh > 0.01:
            if delta_percussive > 0.3 or smoothed_roughness > 0.5:
                var_idx = self.get_variant_index('data_mosh', t, is_beat)
                img_np = self.apply_data_mosh_custom(img_np, m_mosh * smoothed_roughness, var_idx)

        # [NEW PASS B]: Texture Sedimentation 質地時間流沙沉澱 (ndarray 通路)
        if fx_flags.get('sedimentation', True) and m_sediment > 0.01:
            var_idx = self.get_variant_index('sedimentation', t, is_beat)
            img_np = self.apply_sedimentation_custom(img_np, t, smoothed_sub_bass, smoothed_ethereal, m_sediment, chord_tension, var_idx)

        # Pass 1: 幾何畸變 (ndarray 通路)
        if fx_flags.get('spatial_warping', True) and m_dist > 0.01:
            var_idx = self.get_variant_index('spatial_warping', t, is_beat)
            img_np = self.apply_spatial_warping_custom(img_np, t, m_dist, smoothed_sub_bass, smoothed_percussive, is_beat, var_idx)

        # [自訂新增 8]: 縮放脈衝 (Zoom Pulse) (ndarray 通路)
        if fx_flags.get('zoom_pulse', True) and m_zoompulse > 0.01:
            var_idx = self.get_variant_index('zoom_pulse', t, is_beat)
            img_np = self.apply_zoom_pulse_custom(img_np, m_zoompulse, smoothed_sub_bass, t, var_idx)

        # Pass 2: 流體平流 (ndarray 通路)
        if fx_flags.get('fluid_noise', True) and self.fx_active_states['fluid_noise'] > 0.05:
            if m_fluid > 0.01:
                var_idx = self.get_variant_index('fluid_noise', t, is_beat)
                img_np = self.apply_fluid_noise_custom(img_np, t, m_fluid, smoothed_sub_bass, smoothed_percussive, is_beat, anticipation_factor, beat_energy, var_idx)

        # Pass 3: 時空反饋 (ndarray 通路)
        if fx_flags.get('temporal_feedback', True) and m_feed > 0.01:
            var_idx = self.get_variant_index('temporal_feedback', t, is_beat)
            img_np = self.apply_temporal_feedback_custom(img_np, t, m_feed, smoothed_ethereal, smoothed_roughness, audio_feats.get('chord_name', 'N.C.'), var_idx)

        # [自訂新增 6]: 手持相機 (Handheld Camera) (ndarray 通路)
        if fx_flags.get('handheld_camera', True) and m_handheld > 0.01:
            var_idx = self.get_variant_index('handheld_camera', t, is_beat)
            img_np = self.apply_handheld_camera_custom(img_np, t, m_handheld, smoothed_roughness, arousal, is_beat, var_idx)

        # Pass 4: 色彩光譜異常 (ndarray 通路)
        if fx_flags.get('color_spectral', True) and m_color > 0.01:
            var_idx = self.get_variant_index('color_spectral', t, is_beat)
            img_np = self.apply_color_spectral_custom(img_np, t, m_color, smoothed_roughness, smoothed_ethereal, audio_feats.get('chord_name', 'N.C.'), var_idx)

        # [自訂新增 1]: 熱成像 (Thermal Vision) (ndarray 通路)
        if fx_flags.get('thermal_vision', True) and m_thermal > 0.01:
            var_idx = self.get_variant_index('thermal_vision', t, is_beat)
            img_np = self.apply_thermal_custom(img_np, m_thermal, smoothed_sub_bass, smoothed_percussive, chord_hue, var_idx)

        # Pass 5: 發光與體積光 (ndarray 通路)
        if fx_flags.get('glow_illumination', True) and m_glow > 0.01:
            var_idx = self.get_variant_index('glow_illumination', t, is_beat)
            img_np = self.apply_glow_illumination_custom(img_np, t, m_glow, smoothed_sub_bass, smoothed_percussive, var_idx)

        # Pass 6: 訊號退化 (ndarray 通路) - 傳入音樂分析參數
        if fx_flags.get('retro_degradation', True) and m_retro > 0.01:
            var_idx = self.get_variant_index('retro_degradation', t, is_beat)
            img_np = self.apply_retro_degradation_custom(
                img_np, t, m_retro, smoothed_roughness, audio_feats, is_beat, beat_energy, genre_clean, var_idx
            )

        # Pass 6.5: Photocopy Smear 影印機掃描器拖移故障 (ndarray 通路)
        if fx_flags.get('photocopy_smear', True) and m_photocopy > 0.01:
            var_idx = self.get_variant_index('photocopy_smear', t, is_beat)
            img_np = self.apply_photocopy_smear_custom(img_np, t, m_photocopy, var_idx)

        # [自訂新增 2]: 掃描故障 (Scanline Glitch) (ndarray 通路)
        if fx_flags.get('scanline_glitch', True) and m_scanglitch > 0.01:
            var_idx = self.get_variant_index('scanline_glitch', t, is_beat)
            img_np = self.apply_scanline_glitch_custom(img_np, m_scanglitch, smoothed_sub_bass, smoothed_roughness, is_beat, var_idx)

        # [NEW PASS C]: Analog Scan Lines 雷射向量管與熱成像調製 (ndarray 通路)
        if fx_flags.get('vector_scan', True) and m_vscan > 0.01:
            var_idx = self.get_variant_index('vector_scan', t, is_beat)
            img_np = self.apply_vector_scan_custom(img_np, t, chord_hue, chord_brightness, m_vscan, m_mosh, smoothed_percussive, var_idx)

        # [自訂新增 4]: 動態馬賽克 (Dynamic Mosaic) (ndarray 通路)
        if fx_flags.get('dynamic_mosaic', True) and m_mosaic > 0.01:
            var_idx = self.get_variant_index('dynamic_mosaic', t, is_beat)
            img_np = self.apply_dynamic_mosaic_custom(img_np, m_mosaic, smoothed_sub_bass, chord_brightness, smoothed_roughness, var_idx)

        # Pass 7: 像素分選排序 (ndarray 通路)
        if fx_flags.get('pixel_sort', True) and m_pixel > 0.01:
            var_idx = self.get_variant_index('pixel_sort', t, is_beat)
            img_np = self.apply_pixel_sort_custom(img_np, m_pixel, smoothed_roughness, var_idx)

        # [自訂新增 5]: 像素畫 (Pixel Art) (ndarray 通路)
        if fx_flags.get('pixel_art', True) and m_pixelart > 0.01:
            var_idx = self.get_variant_index('pixel_art', t, is_beat)
            img_np = self.apply_pixel_art_custom(img_np, m_pixelart, smoothed_sub_bass, var_idx)

        # Pass 8: 對稱萬花筒 (ndarray 通路)
        if fx_flags.get('kaleidoscope', True) and m_kaleidoscope > 0.01:
            var_idx = self.get_variant_index('kaleidoscope', t, is_beat)
            img_np = self.apply_kaleidoscope_custom(img_np, t, m_kaleidoscope, smoothed_sub_bass, beat_energy, is_beat, self._k_cx_offset, var_idx)

        # [NEW PASS D]: Temporal Symmetry Fractal 時空對稱分形鏡 (ndarray 通路)
        if fx_flags.get('temporal_fractal', True) and m_fractal > 0.01:
            var_idx = self.get_variant_index('temporal_fractal', t, is_beat)
            img_np = self.apply_temporal_fractal_custom(img_np, audio_feats.get('stereo_width', 0.5), arousal, m_fractal, var_idx)

        # [NEW DERIVATIVE 3]: Anticipatory Vignette Pulse (正拍預期呼吸暗房)
        if fx_flags.get('vignette_pulse', True):
            var_idx = self.get_variant_index('vignette_pulse', t, is_beat)
            img_np = self.apply_vignette_pulse_custom(img_np, beat_phase, anticipation_factor, fx_intensity, var_idx)

        # [NEW DERIVATIVE 4]: Tension Exclusion Overlay (和弦張力互斥光譜層)
        if fx_flags.get('tension_overlay', True) and chord_tension > 0.1:
            var_idx = self.get_variant_index('tension_overlay', t, is_beat)
            img_np = self.apply_tension_overlay_custom(img_np, chord_tension, audio_feats.get('chord_hue', 0.0), fx_intensity, var_idx)

        # [新增 PASS 1]: Kuwahara 藝術彩繪 (ndarray 通路)
        if fx_flags.get('kuwahara_paint', True) and m_kuwahara > 0.01:
            var_idx = self.get_variant_index('kuwahara_paint', t, is_beat)
            img_np = self.apply_kuwahara_paint_custom(img_np, t, m_kuwahara, smoothed_roughness, smoothed_ethereal, var_idx)

        # [新增 PASS 2]: Matrix ASCII 數位字元雨 (ndarray 通路)
        if fx_flags.get('matrix_ascii', True) and m_matrix > 0.01:
            var_idx = self.get_variant_index('matrix_ascii', t, is_beat)
            img_np = self.apply_matrix_ascii_custom(img_np, t, m_matrix, audio_feats, is_beat, beat_energy, var_idx)

        # [新增 PASS 3]: Reaction Diffusion / 時空剪切 (ndarray 通路)
        if fx_flags.get('reaction_diffusion', True) and m_reaction > 0.01:
            var_idx = self.get_variant_index('reaction_diffusion', t, is_beat)
            img_np = self.apply_reaction_diffusion_custom(img_np, t, m_reaction, audio_feats, is_beat, beat_energy, var_idx)

        # [自訂新增 3]: 掉幀特效 (Frame Drop) (ndarray 通路)
        if fx_flags.get('frame_drop', True) and m_framedrop > 0.01:
            var_idx = self.get_variant_index('frame_drop', t, is_beat)
            img_np = self.apply_frame_drop_custom(img_np, m_framedrop, arousal, beat_phase, var_idx)

        # Pass 8.5: Collage Cutout 創意拼貼濾鏡 (ndarray 通路)
        if fx_flags.get('collage_cutout', True) and m_collage > 0.01:
            var_idx = self.get_variant_index('collage_cutout', t, is_beat)
            img_np = self.apply_collage_cutout_custom(img_np, m_collage, var_idx)

        # ═══════════════════════════════════════════════════════════
        # 全新維度全域後製特效矩陣 (Global Post-FX Matrix 8 大頂級特效)
        # ═══════════════════════════════════════════════════════════
        # Pass 9.1: Film Burn & Chemical Bleed (膠片腐蝕)
        if fx_flags.get('film_burn', True) and m_filmburn > 0.01:
            var_idx = self.get_variant_index('film_burn', t, is_beat)
            img_np = self.apply_film_burn_custom(img_np, t, m_filmburn, smoothed_sub_bass, smoothed_roughness, is_beat, var_idx)

        # Pass 9.2: Blueprint & CAD Wireframe (建築藍圖)
        if fx_flags.get('blueprint_edge', True) and m_blueprint > 0.01:
            var_idx = self.get_variant_index('blueprint_edge', t, is_beat)
            img_np = self.apply_blueprint_edge_custom(img_np, m_blueprint, harmonic, smoothed_roughness, var_idx)

        # Pass 9.3: Turing Pattern Reaction Diffusion (圖靈細胞)
        if fx_flags.get('turing_pattern', True) and m_turing > 0.01:
            var_idx = self.get_variant_index('turing_pattern', t, is_beat)
            img_np = self.apply_turing_pattern_custom(img_np, t, m_turing, smoothed_ethereal, is_beat, var_idx)

        # Pass 9.4: Depth-Map Point Cloud Projection (點雲深度)
        if fx_flags.get('point_cloud_depth', True) and m_pointcloud > 0.01:
            var_idx = self.get_variant_index('point_cloud_depth', t, is_beat)
            img_np = self.apply_point_cloud_depth_custom(img_np, m_pointcloud, smoothed_sub_bass, stereo_width, var_idx)

        # Pass 9.5: Stereo Phase Vector-Scope (聲相示波)
        if fx_flags.get('vector_scope', True) and m_vectorscope > 0.01:
            var_idx = self.get_variant_index('vector_scope', t, is_beat)
            audio_samples = audio_feats.get('audio_samples', None)
            img_np = self.apply_vector_scope_custom(img_np, t, m_vectorscope, stereo_width, chord_hue, audio_samples, var_idx)

        # Pass 9.6: Low-Pass Muffle & DoF Blur (悶音景深)
        if fx_flags.get('lowpass_muffle', True) and m_lowpass > 0.01:
            var_idx = self.get_variant_index('lowpass_muffle', t, is_beat)
            lowpass_val = audio_feats.get('lowpass', 0.0)
            img_np = self.apply_lowpass_muffle_custom(img_np, m_lowpass, lowpass_val, var_idx)

        # Pass 9.7: Anamorphic Infinity Tunnel (無限鏡廊)
        if fx_flags.get('infinity_tunnel', True) and m_infinity > 0.01:
            var_idx = self.get_variant_index('infinity_tunnel', t, is_beat)
            img_np = self.apply_infinity_tunnel_custom(img_np, t, m_infinity, beat_phase, beat_energy, var_idx)

        # Pass 9.8: Vertigo Dolly Zoom (眩暈推拉)
        if fx_flags.get('dolly_zoom', True) and m_dollyzoom > 0.01:
            var_idx = self.get_variant_index('dolly_zoom', t, is_beat)
            img_np = self.apply_dolly_zoom_custom(img_np, m_dollyzoom, anticipation_factor, is_beat, var_idx)

        # ═══════════════════════════════════════════════════════════
        # 電影級音樂情感調色與純色過渡 (Cinematic Mood Adaptation)
        # ═══════════════════════════════════════════════════════════
        exposure_mult = 1.0
        contrast_mult = 1.12
        saturation_mult = 1.15
        grayscale_blend = 0.0
        solid_color_blend = 0.0

        if section_name == 'Bridge':
            # Bridge (橋段)：暗調、低對比度與低飽和度
            exposure_mult = 0.5 + 0.4 * arousal
            contrast_mult = 0.8 + 0.2 * arousal
            saturation_mult = 0.5 + 0.5 * arousal
            if arousal < 0.25:
                # 能量極低時，漸變為黑白單色畫面
                grayscale_blend = (0.25 - arousal) / 0.25
        elif section_name in ('Intro', 'Outro'):
            # 起奏與尾奏段落：隨進度平滑漸變
            if section_name == 'Intro':
                exposure_mult = 0.6 + 0.4 * section_progress
                saturation_mult = 0.6 + 0.4 * section_progress
                contrast_mult = 0.9 + 0.22 * section_progress
            else:
                exposure_mult = 1.0 - 0.9 * section_progress
                saturation_mult = 1.0 - 0.8 * section_progress
                contrast_mult = 1.12 - 0.32 * section_progress
        elif section_name in ('Drop', 'Chorus'):
            # 副歌/高潮：鮮豔飽滿，重拍高亮度
            exposure_mult = 1.05 + 0.15 * beat_energy if is_beat else 1.0
            contrast_mult = 1.15 + 0.1 * arousal
            saturation_mult = 1.22 + 0.1 * arousal

        # 樂器音色稀疏性自適應控制
        if timbre_density < 0.15 and section_name not in ('Drop', 'Chorus'):
            sparsity_factor = (0.15 - timbre_density) / 0.15
            exposure_mult *= (1.0 - 0.6 * sparsity_factor)  # 最暗降至 40% 亮度
            saturation_mult *= (1.0 - 0.8 * sparsity_factor) # 色彩彩度大幅衰退至 20%
            contrast_mult *= (1.0 - 0.4 * sparsity_factor)  # 軟化對比度
            
            # 極限稀疏/極靜音段落過渡至和弦純色畫面
            if timbre_density < 0.05:
                solid_color_blend = (0.05 - timbre_density) / 0.05

        # 1. 情感調色 (曝光、S曲線對比、彩度與灰階)
        if fx_flags.get('color_boost', True):
            img_np = self.apply_color_enhancement(img_np, contrast=contrast_mult, saturation=saturation_mult, exposure=exposure_mult, grayscale_blend=grayscale_blend)

        # 2. 和弦純色/極限深藍色過渡
        if solid_color_blend > 0.01 and cv2 is not None:
            chord_rgb = self._hue_to_rgb(chord_hue)
            solid_color = np.array(chord_rgb, dtype=np.uint8) if current_chord != 'N.C.' else np.array([5, 5, 8], dtype=np.uint8)
            solid_canvas = np.zeros_like(img_np)
            solid_canvas[:, :] = solid_color
            img_np = cv2.addWeighted(img_np, 1.0 - solid_color_blend, solid_canvas, solid_color_blend, 0)

        # 3. 畫面終端細節重建 (Unsharp Mask 銳化)
        if fx_flags.get('sharpen', True):
            img_np = self.apply_sharpening(img_np, amount=0.75, radius=1.0)

        # ═══════════════════════════════════════════════════════════
        # 全域混合特效與後處理 (ndarray 100% 直通)
        # ═══════════════════════════════════════════════════════════
        # Pass 10: 空靈聲學模擬
        if fx_flags.get('ambient_dsp', True) and self.fx_active_states['ambient_dsp'] > 0.05:
            var_idx = self.get_variant_index('ambient_dsp', t, is_beat)
            img_np = self.apply_ambient_dsp_custom(img_np, t, fx_intensity * self.fx_active_states['ambient_dsp'], smoothed_ethereal, smoothed_percussive, var_idx)

        # 重拍閃白 / 溫和輝光 — 硬白閃僅限 glow_illumination 為本主題招牌特效
        glow_active = self.fx_active_states.get('glow_illumination', 0.0)
        is_glow_theme = 'glow_illumination' in self.signature_pool
        if fx_flags.get('glow_illumination', True) and cv2 is not None:
            if self.photosensitive_safe:
                if glow_active > 0.05:
                    alpha = min(0.05, glow_active * 0.05 * base_mult)
                    flash_canvas = np.zeros_like(img_np)
                    flash_canvas[:, :] = (150, 140, 130)  # 溫馨環境微光
                    img_np = cv2.addWeighted(img_np, 1.0 - alpha, flash_canvas, alpha, 0)
            elif is_glow_theme and is_beat and beat_energy > 0.15 and genre_clean not in ('lo-fi', 'ambient', 'jazz'):
                # 硬白閃：僅 DreamyArtistic 主題歌曲觸發，alpha 上限降至 0.2
                flash_color = (255, 255, 255) if int(t * audio_feats.get('bpm', 120.0) / 60.0) % 2 == 0 else (0, 0, 0)
                flash_canvas = np.zeros_like(img_np)
                flash_canvas[:, :] = flash_color
                alpha = min(0.20, beat_energy * 0.18 * base_mult * glow_active)
                img_np = cv2.addWeighted(img_np, 1.0 - alpha, flash_canvas, alpha, 0)
            elif not is_glow_theme and glow_active > 0.05:
                # 非 glow 主題：超柔和環境微光，不產生明顯閃爍
                alpha = min(0.04, glow_active * 0.03 * base_mult)
                flash_canvas = np.zeros_like(img_np)
                flash_canvas[:, :] = (140, 135, 128)
                img_np = cv2.addWeighted(img_np, 1.0 - alpha, flash_canvas, alpha, 0)

        # 瞬態反轉色彩
        if self.invert_frame_timer > 0:
            self.invert_frame_timer -= 1
            if fx_flags.get('retro_degradation', True) or fx_flags.get('glow_illumination', True):
                img_np = 255 - img_np

        # 安全靜音或自訂藝術淡入淡出
        if fx_flags.get('stylized_fade', True) and (silence_fade > 0.01 or m_stylizedfade > 0.01):
            var_idx = self.get_variant_index('stylized_fade', t, is_beat)
            img_np = self.apply_stylized_fade_custom(img_np, m_stylizedfade, silence_fade, var_idx)
        elif silence_fade > 0.01:
            fade_alpha = min(1.0, silence_fade)
            img_np = (img_np * (1.0 - fade_alpha)).astype(np.uint8)

        if is_scaled and cv2 is not None:
            img_np = cv2.resize(img_np, original_size, interpolation=cv2.INTER_LANCZOS4)
            
        return Image.fromarray(img_np)

    # ════════════════════════════════════════════════════════════════
    def apply_barrel_distortion(self, img_np, k1, k2):
        """桶型/枕型畸變 — 接收並返回 ndarray"""
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            f = min(w, h)
            K = np.array([[f, 0, w/2.0], [0, f, h/2.0], [0, 0, 1]], dtype=np.float32)
            D = np.array([k1, k2, 0, 0], dtype=np.float32)
            map1, map2 = cv2.initUndistortRectifyMap(K, D, None, K, (w, h), cv2.CV_32FC1)
            # 尺寸校驗自癒機制
            if map1.shape != img_np.shape[:2]: return img_np
            return cv2.remap(img_np, map1, map2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception: return img_np

    def apply_polar_mapping(self, img_np, log_polar=True):
        """極座標/對數極座標映射 — 接收並返回 ndarray"""
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            flags = cv2.WARP_FILL_OUTLIERS + (cv2.WARP_POLAR_LOG if log_polar else cv2.WARP_POLAR_LINEAR)
            return cv2.warpPolar(img_np, (w, h), (w/2.0, h/2.0), min(w, h)/2.0, flags)
        except Exception: return img_np

    def apply_domain_warping(self, img_np, t, intensity, anticipation=0.0):
        """域畸變（正弦波疊加場） — 接收並返回 ndarray，結合 time_vessel 歷史特徵調製"""
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            if self._grid_cache is None or self._grid_cache[0] != (w, h):
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                self._grid_cache = ((w, h), x, y)
            _, x, y = self._grid_cache
            
            # 從 time_vessel 映射歷史聲學特徵波浪
            # row_indices 對應 0~59 歷史索引
            row_indices = (np.arange(h) / max(1, h - 1) * (self.time_vessel_size - 1)).astype(np.int32)
            
            # 取 sub-bass 與 percussive 的時域歷史，廣播至 (h, 1)
            history_bass = self.time_vessel[row_indices, 0].reshape(h, 1)
            history_percussive = self.time_vessel[row_indices, 1].reshape(h, 1)
            
            # 基於歷史特徵的列波動調製因子
            ripple_freq = 0.006 + 0.01 * history_bass
            ripple_amp = 45.0 * intensity * (1.0 + 1.5 * history_percussive)
            
            # 【變種核心】：正拍預期負反饋調製
            if anticipation > 0.01:
                # 頻率乘以負數/反向收縮，強度加大
                freq_mult = 1.0 - 2.5 * anticipation
                cx, cy = w / 2.0, h / 2.0
                dx = np.sin((x - cx) * ripple_freq * freq_mult + t * 2.5) * np.cos((y - cy) * 0.01 - t * 1.5) * ripple_amp
                dy = np.cos((x - cx) * 0.01 - t * 2.0) * np.sin((y - cy) * ripple_freq * freq_mult + t * 2.2) * ripple_amp
            else:
                # FIX 1: 優化原位 NumPy 廣播運算，直接在 uint8 網格疊加，消除常駐型態轉換
                dx = np.sin(x * ripple_freq + t * 2.5) * np.cos(y * 0.01 - t * 1.5) * ripple_amp
                dy = np.cos(x * 0.01 - t * 2.0) * np.sin(y * ripple_freq + t * 2.2) * ripple_amp
            
            map_x = (x + dx).astype(np.float32)
            map_y = (y + dy).astype(np.float32)
            if map_x.shape != img_np.shape[:2]:
                self._grid_cache = None
                return img_np
            return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception: return img_np

    # ════════════════════════════════════════════════════════════════
    # 色彩光譜特效
    # ════════════════════════════════════════════════════════════════

    def apply_radial_chromatic_aberration_numpy(self, img_np, intensity):
        """極速色散核心：透過 OpenCV 仿射縮放與矩陣切片取代 PIL 通道拆分
        
        利用 cv2.getRotationMatrix2D 建立無旋轉的純縮放仿射矩陣，
        對紅、藍通道分別做 1±0.012×intensity 的中心縮放偏移，
        直接覆蓋原矩陣通道，完全規避 PIL split/resize/crop/merge 鏈條。
        """
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            # 計算縮放係數
            shift_r = 1.0 + 0.012 * intensity
            shift_b = 1.0 - 0.012 * intensity

            # 建立仿射矩陣原位縮放紅、藍通道
            M_r = cv2.getRotationMatrix2D((w/2.0, h/2.0), 0, shift_r)
            M_b = cv2.getRotationMatrix2D((w/2.0, h/2.0), 0, shift_b)

            out_r = cv2.warpAffine(img_np[:, :, 0], M_r, (w, h), borderMode=cv2.BORDER_REFLECT)
            out_b = cv2.warpAffine(img_np[:, :, 2], M_b, (w, h), borderMode=cv2.BORDER_REFLECT)
            
            # 直接覆蓋原矩陣通道，零額外記憶體分配
            img_np[:, :, 0] = out_r
            img_np[:, :, 2] = out_b
            return img_np
        except Exception:
            return img_np

    def apply_radial_chromatic_aberration(self, img, intensity):
        """原版 PIL 色散（保留向後相容）"""
        w, h = img.size
        bands = img.split()
        if len(bands) < 3: return img
        r, g, b = bands[0], bands[1], bands[2]
        a = bands[3] if len(bands) == 4 else None

        rw, rh = max(1, int(w * (1.0 + 0.015 * intensity))), max(1, int(h * (1.0 + 0.015 * intensity)))
        bw, bh = max(1, int(w * (1.0 - 0.015 * intensity))), max(1, int(h * (1.0 - 0.015 * intensity)))

        r_f = r.resize((rw, rh), Image.Resampling.BILINEAR).crop(((rw - w)//2, (rh - h)//2, (rw - w)//2 + w, (rh - h)//2 + h))
        b_f = Image.new("L", (w, h), 0)
        b_f.paste(b.resize((bw, bh), Image.Resampling.BILINEAR), ((w - bw)//2, (h - bh)//2))

        return Image.merge('RGBA', (r_f, g, b_f, a)) if a else Image.merge('RGB', (r_f, g, b_f))

    def apply_color_cycling(self, img_np, t, intensity, chord_name='N.C.'):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY) / 255.0
            phase = t * 0.4
            is_minor = any(m in chord_name.lower() for m in ('min', 'dim', 'aug')) or ('m' in chord_name.lower() and 'maj' not in chord_name.lower())
            
            # Inigo Quilez 餘弦漸層演算法（和弦色彩調製）
            a = np.array([0.4, 0.45, 0.5]) if is_minor else np.array([0.6, 0.5, 0.4])
            b = np.array([0.2, 0.3, 0.4]) if is_minor else np.array([0.4, 0.4, 0.3])
            c = np.array([1.2, 1.0, 0.8]) if is_minor else np.array([1.0, 1.0, 1.0])
            d = (np.array([0.0, 0.5, 0.67]) if is_minor else np.array([0.0, 0.1, 0.2])) + phase
            
            out = np.zeros((h, w, 3), dtype=np.float32)
            for i in range(3): out[:, :, i] = a[i] + b[i] * np.cos(2.0 * np.pi * (c[i] * gray + d[i]))
            
            out_uint8 = np.clip(out * 255.0, 0, 255).astype(np.uint8)
            return cv2.addWeighted(img_np, 1.0 - intensity, out_uint8, intensity, 0)
        except Exception: return img_np

    # ════════════════════════════════════════════════════════════════
    # 光效特效 (ndarray 直通最佳性能版)
    # ════════════════════════════════════════════════════════════════

    def apply_bloom(self, img_np, intensity, threshold_val=170):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            _, mask = cv2.threshold(gray, threshold_val, 255, cv2.THRESH_BINARY)
            bright_img = cv2.bitwise_and(img_np, img_np, mask=mask)

            # 雙軌多級快速降採樣金字塔，避開對大解析度圖像直接高斯模糊的硬體屏障
            ds1 = cv2.resize(bright_img, (w // 2, h // 2), interpolation=cv2.INTER_LINEAR)
            ds2 = cv2.resize(ds1, (w // 4, h // 4), interpolation=cv2.INTER_LINEAR)
            
            ds2_up = cv2.resize(ds2, (w // 2, h // 2), interpolation=cv2.INTER_LINEAR)
            us1_half = cv2.addWeighted(ds1, 0.5, ds2_up, 0.5, 0)
            us1 = cv2.resize(us1_half, (w, h), interpolation=cv2.INTER_LINEAR)

            sigma = 8.0 * intensity
            ksize = int(6 * sigma) | 1
            if ksize < 1: ksize = 1
            blurred = cv2.GaussianBlur(us1, (ksize, ksize), sigma)

            # Screen Blend
            img_f = img_np.astype(np.float32)
            blur_f = blurred.astype(np.float32)
            screen_f = 255.0 - ((255.0 - img_f) * (255.0 - blur_f) / 255.0)
            return np.clip(screen_f, 0, 255).astype(np.uint8)
        except Exception: return img_np

    def apply_god_rays(self, img_np, intensity):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            _, mask = cv2.threshold(gray, 195, 255, cv2.THRESH_BINARY)
            highlight = cv2.bitwise_and(img_np, img_np, mask=mask)

            accum = highlight.copy()
            for i in range(1, 4):  # 降級為 3 級疊加提升流暢度
                scale = 1.0 + 0.03 * i * intensity
                sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
                scaled = cv2.resize(highlight, (sw, sh), interpolation=cv2.INTER_LINEAR)
                
                left = max(0, (sw - w) // 2)
                top = max(0, (sh - h) // 2)
                cropped = scaled[top:top+h, left:left+w]
                if cropped.shape[:2] != (h, w):
                    cropped = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
                
                alpha = 0.75 / (i + 1)
                accum = cv2.addWeighted(accum, 1.0 - alpha, cropped, alpha, 0)

            # GaussianBlur with radius 4 (ksize 25)
            blurred = cv2.GaussianBlur(accum, (25, 25), 4.0)

            # Screen Blend
            img_f = img_np.astype(np.float32)
            blur_f = blurred.astype(np.float32)
            screen_f = 255.0 - ((255.0 - img_f) * (255.0 - blur_f) / 255.0)
            return np.clip(screen_f, 0, 255).astype(np.uint8)
        except Exception: return img_np

    # ════════════════════════════════════════════════════════════════
    # 訊號退化特效
    # ════════════════════════════════════════════════════════════════

    def apply_halftone(self, img_np, intensity):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            base_grid = max(16, w // 100)
            grid_size = int(base_grid + (base_grid * 0.5) * (1.0 - intensity))
            if grid_size < 1: grid_size = 1
            gw, gh = w // grid_size, h // grid_size
            if gw < 4 or gh < 4: return img_np

            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            small_arr = cv2.resize(gray, (gw, gh), interpolation=cv2.INTER_LINEAR)
            canvas = np.ones((h, w, 3), dtype=np.uint8) * 255

            half_grid = grid_size / 2.0
            for cy in range(gh):
                for cx in range(gw):
                    brightness = 1.0 - (small_arr[cy, cx] / 255.0)
                    if brightness < 0.08: continue
                    r = int(half_grid * brightness)
                    if r < 1: continue
                    px = int(cx * grid_size + half_grid)
                    py = int(cy * grid_size + half_grid)
                    cv2.circle(canvas, (px, py), r, (24, 24, 28), -1, lineType=cv2.LINE_AA)

            return cv2.addWeighted(img_np, 1.0 - intensity, canvas, intensity, 0)
        except Exception: return img_np

    def apply_crt_simulation(self, img_np, t, intensity):
        """CRT 模擬優化：利用靜態分配的隨機噪點與原位廣播運算 — 接收並返回 ndarray"""
        try:
            h, w, c = img_np.shape
            
            # FIX 2: 優化原位查表與動態查表（LUT），將 float 轉換徹底改成在 uint8 數組原位廣播運算
            # 建立動態 CRT 掃描線遮罩層
            y_indices = np.arange(h).reshape(h, 1, 1)
            scanline_weights = (255 - int(56 * intensity) + int(56 * intensity) * np.sin(y_indices * (np.pi * 2.0 / 3.0))).astype(np.uint8)
            
            # 利用 NumPy 高效廣播進行原位亮度折扣，避開轉型
            img_np = ((img_np.astype(np.uint16) * scanline_weights) // 255).astype(np.uint8)

            # 訊號滾動干擾橫條（零分配：從預置靜態噪點緩衝區切片）
            bar_y = int((t * 140.0) % (h * 1.5)) - (h // 2)
            bar_h = int(25 * intensity + 8)
            if 0 <= bar_y < h:
                h_slice = min(h, bar_y + bar_h) - bar_y
                # 隨機擷取靜態噪點層的一部分，不開闢新內存 (具備動態調整維度自愈功能)
                if self._noise_buffer.shape[0] < h_slice or self._noise_buffer.shape[1] < w:
                    new_h = max(self._noise_buffer.shape[0], h_slice)
                    new_w = max(self._noise_buffer.shape[1], w)
                    self._noise_buffer = np.random.randint(-25, 25, (new_h, new_w, 1), dtype=np.int16)
                noise_slice = self._noise_buffer[:h_slice, :w, :]
                if hasattr(self, 'feature_mask') and self.feature_mask is not None:
                    # 使用音訊特徵遮罩動態調製噪點干擾程度
                    f_slice = self.feature_mask[bar_y:bar_y+h_slice, :, np.newaxis]
                    noise_slice = (noise_slice * f_slice).astype(np.int16)
                img_np[bar_y:bar_y+h_slice, :, :3] = np.clip(img_np[bar_y:bar_y+h_slice, :, :3].astype(np.int16) + noise_slice, 0, 255).astype(np.uint8)

            return img_np
        except Exception: 
            return img_np

    def apply_pixel_sorting(self, img_np, intensity):
        """像素分選排序 — 接收並返回 ndarray，使用自適應特徵遮罩動態調製每像素塊閾值"""
        try:
            h, w, c = img_np.shape
            # 自行計算簡易亮度，避免回頭調用 PIL
            gray = (img_np[:, :, 0] * 0.299 + img_np[:, :, 1] * 0.587 + img_np[:, :, 2] * 0.114).astype(np.uint8)
            
            if hasattr(self, 'feature_mask') and self.feature_mask is not None:
                # 遮罩值越大，排序閥值越低，使音訊能量高的區域排序效果更明顯
                # 閾值映射至 [120, 255] 區間
                adaptive_intensity = intensity * self.feature_mask
                threshold_map = (255 - 135 * adaptive_intensity).astype(np.uint8)
            else:
                threshold_map = np.ones((h, w), dtype=np.uint8) * int(255 - 130 * intensity)

            for y in range(0, h, 2):
                mask = gray[y, :] > threshold_map[y, :]
                if not np.any(mask): continue
                indices = np.where(mask)[0]
                if len(indices) < 2: continue

                runs = np.split(indices, np.where(np.diff(indices) != 1)[0] + 1)
                for run in runs:
                    if len(run) > 5:
                        img_np[y, run, :3] = img_np[y, run[np.argsort(gray[y, run])], :3]

            return img_np
        except Exception: return img_np

    def apply_digital_blocks(self, img, intensity):
        try:
            if img.mode != "RGBA": img = img.convert("RGBA")
            w, h = img.size
            draw = ImageDraw.Draw(img)
            palette = getattr(self, 'mosh_palette', [])
            for _ in range(int(2 + 7 * intensity)):
                bx, by = random.randint(0, w - 80), random.randint(0, h - 50)
                bw, bh = random.randint(15, int(110 * intensity + 15)), random.randint(8, int(50 * intensity + 8))
                if palette:
                    r, g, b = random.choice(palette)
                    fill_color = (r, g, b, 110)
                else:
                    fill_color = random.choice([(255,0,128,110),(0,255,255,110),(255,255,0,110),(0,255,0,80),(0,0,255,80)])
                draw.rectangle([bx, by, bx + bw, by + bh], fill=fill_color)
            return img
        except Exception: return img

    def apply_kaleidoscope(self, img_np, segments, rotation_offset=0.0, cx_offset=0.0):
        """萬花筒 — 接收並返回 ndarray"""
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            cx, cy = w / 2.0 + cx_offset, h / 2.0
            
            cache_key = (w, h, cx_offset)
            if not hasattr(self, "_k_cache") or self._k_cache is None or self._k_cache[0] != cache_key:
                y, x = np.mgrid[0:h, 0:w]
                self._k_cache = (cache_key, np.sqrt((x - cx)**2 + (y - cy)**2), np.arctan2(y - cy, x - cx))
                
            _, r, theta = self._k_cache
            segment_angle = 2.0 * np.pi / max(2, segments)
            theta_mod = np.mod(theta + rotation_offset, segment_angle)
            
            mask = (theta_mod > (segment_angle / 2.0))
            theta_mod[mask] = segment_angle - theta_mod[mask]
            
            map_x = (cx + r * np.cos(theta_mod)).astype(np.float32)
            map_y = (cy + r * np.sin(theta_mod)).astype(np.float32)
            
            # FIX 3: 快取安全護欄 - 尺寸不符時立馬清除快取自癒，防止 cv2.remap 紅字崩潰
            if map_x.shape != img_np.shape[:2]:
                self._k_cache = None
                return img_np
                
            return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception: return img_np

    # ════════════════════════════════════════════════════════════════
    # 全域空間維度重組通道 (全新 ndarray 介面)
    # ════════════════════════════════════════════════════════════════

    def apply_data_mosh(self, img_np, intensity):
        """Data-Moshing 數位空間維度撕裂：利用偽運動向量場強行原位撕裂高對比度邊緣像素
        
        僅對 Canny 邊緣偵測到的高頻區域進行方向性位移拖曳，
        保留低頻背景完整性，產生極具未來主義 Glitch 藝術的非線性撕裂感。
        """
        if cv2 is None or intensity < 0.05:
            return img_np
        try:
            h, w = img_np.shape[:2]

            # 快取座標網格
            if self._mosh_vector is None or self._mosh_vector[0].shape != (h, w):
                y, x = np.mgrid[0:h, 0:w]
                self._mosh_vector = (x.astype(np.float32), y.astype(np.float32))

            x, y = self._mosh_vector

            # 建立帶有強烈音樂共振的方向性拉伸速度場
            shift_x = 25.0 * intensity * math.sin(intensity * 10.0)
            shift_y = 15.0 * intensity * math.cos(intensity * 5.0)

            map_x = np.clip(x - shift_x, 0, w - 1)
            map_y = np.clip(y - shift_y, 0, h - 1)

            # 只有高對比度/邊緣區域會被 Moshing 拖曳，保留低頻背景
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            edge_mask = cv2.Canny(gray, 80, 200).astype(bool)

            # 對邊緣像素做最近鄰插值位移（模擬 I-frame 丟失的區塊複製錯位）
            mosh_np = cv2.remap(img_np, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REFLECT)
            img_np[edge_mask] = mosh_np[edge_mask]
            return img_np
        except Exception:
            return img_np

    def apply_texture_sedimentation(self, img_np, t, sub_bass, ethereal, intensity, chord_tension=0.0):
        """質地時間流沙沉澱：提取畫面高光與邊緣顆粒，模擬化學底片沉澱的物理動態 (包含時空互斥流沙變種)"""
        if cv2 is None or intensity < 0.02:
            return img_np
        try:
            h, w, c = img_np.shape

            # 初始化或重新配置沉澱緩衝區
            if self._sediment_buffer is None or self._sediment_buffer.shape != (h, w, c):
                self._sediment_buffer = np.zeros((h, w, c), dtype=np.float32)

            # 1. 提取當前影格的高光與邊緣顆粒
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            edges = cv2.Canny(gray, 50, 150)
            particles_mask = (thresh > 0) | (edges > 0)

            # 2. 將新顆粒沉澱注入緩衝畫布（加權累積）
            self._sediment_buffer[particles_mask] += img_np[particles_mask].astype(np.float32) * 0.4

            # 3. 模擬重力下沉與 Sub-Bass 揚塵動力學
            gravity = 2.0 * (1.0 - sub_bass)
            bass_lift = int(20.0 * sub_bass * intensity)

            # 利用仿射平移矩陣模擬流沙的物理動態（微量橫向抖動 + 縱向重力/揚起）
            tx = random.uniform(-2.0, 2.0) * intensity
            ty = gravity - bass_lift
            M = np.float32([[1, 0, tx], [0, 1, ty]])
            self._sediment_buffer = cv2.warpAffine(
                self._sediment_buffer, M, (w, h),
                borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)
            )

            # 4. 隨時間消融（Ethereal 空靈度越高，沙塵消融越快）
            decay = 0.92 - (0.05 * ethereal)
            self._sediment_buffer *= max(0.8, min(0.98, decay))

            # 5. 與原圖混合：如果和弦張力高，沉澱層與原圖產生 absdiff 互斥，翻轉出緊繃色彩
            sediment_uint8 = np.clip(self._sediment_buffer * intensity, 0, 255).astype(np.uint8)
            if chord_tension > 0.3:
                excluded_sediment = cv2.absdiff(img_np, sediment_uint8)
                return cv2.addWeighted(img_np, 1.0 - (0.4 * chord_tension), excluded_sediment, 0.4 * chord_tension, 0)

            return cv2.addWeighted(img_np, 1.0, sediment_uint8, 0.7, 0)
        except Exception:
            return img_np

    def apply_vector_scan_lines(self, img_np, t, hue, brightness, intensity):
        """雷射向量管與熱成像調製：提取畫面亮度等高線並轉化為 RGB 向量線段
        
        模擬向量顯像管（Vector Scope）的掃描美學。
        Chord brightness 與 harmonic 調製光譜色彩，percussive 調製線段抽搐頻率。
        """
        if cv2 is None or intensity < 0.05:
            return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

            # 降採樣簡化畫面結構，形成大面積塊狀以提取穩定等高線
            scale_factor = 8
            sw, sh = max(1, w // scale_factor), max(1, h // scale_factor)
            small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_LINEAR)

            # 自適應閾值化以提取有意義的等高線
            small_thresh = cv2.adaptiveThreshold(
                small, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            # 提取等高線（Contours）模擬向量示波器線段
            contours, _ = cv2.findContours(small_thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            # 建立向量繪圖畫布
            vector_canvas = np.zeros_like(img_np)
            r, g, b = self._hue_to_rgb(hue + math.sin(t) * 30.0)

            # 動態隨機抽搐偏移（模擬射頻干擾）
            twitch_x = int(8.0 * intensity * math.sin(t * 50.0))

            line_thickness = max(1, int(2.0 * intensity))
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 10:
                    continue
                # 放大回原始尺寸並施加抽搐偏移
                contour_scaled = (contour * scale_factor).astype(np.int32)
                contour_scaled[:, :, 0] = np.clip(contour_scaled[:, :, 0] + twitch_x, 0, w - 1)
                cv2.drawContours(vector_canvas, [contour_scaled], -1, (r, g, b), line_thickness)

            # 與原圖以 Additive 模式混合
            scaled_canvas = (vector_canvas.astype(np.float32) * min(1.0, intensity)).astype(np.uint8)
            return cv2.add(img_np, scaled_canvas)
        except Exception:
            return img_np

    def apply_temporal_fractal(self, img_np, stereo_width, arousal, intensity):
        """時空對稱分形鏡：引入歷史影格與現時影格的對稱差值自我吞噬
        
        左半邊為現時影格，右半邊取自歷史影格（由 stereo_width 控制延遲跨度），
        中心交界處以 Difference/Exclusion 混合產生不斷演化的有機分形圖案。
        Arousal 控制分形分裂的擴散層級。
        """
        if cv2 is None or intensity < 0.05:
            return img_np
        try:
            buf_len = len(self.time_displacement_buffer.buffer)
            if buf_len < 6:
                return img_np

            h, w = img_np.shape[:2]
            mid = w // 2

            # 根據聲相立體寬度動態抓取過去第 N 影格
            delay_idx = max(1, int((buf_len - 1) * max(0.0, min(1.0, stereo_width))))
            past_idx = max(0, buf_len - 1 - delay_idx)
            past_np = self.time_displacement_buffer.buffer[past_idx]

            # 尺寸校驗：歷史影格與當前影格必須完全一致
            if past_np.shape != img_np.shape:
                return img_np

            # 執行左右時空鏡像對稱
            left_half = img_np[:, :mid].copy()
            past_right = past_np[:, mid:mid + left_half.shape[1]]

            # 安全校驗：確保兩半寬度一致（處理奇數寬度）
            min_w = min(left_half.shape[1], past_right.shape[1])
            left_half = left_half[:, :min_w]
            past_right = past_right[:, :min_w]

            # 水平翻轉歷史右半部
            past_right_flipped = cv2.flip(past_right, 1)

            # 核心融合：Difference 建立邊緣分形圖案
            fractal_core = cv2.absdiff(left_half, past_right_flipped)

            # 根據 arousal 控制分形擴散寬度
            spread = max(5, min(mid, int(mid * 0.15 * (0.5 + arousal))))

            # 在中心交界處疊加分形差值帶
            center_start = max(0, mid - spread)
            center_end = min(w, mid + spread)
            center_width = center_end - center_start

            # 從 fractal_core 擷取對應寬度的區域
            fc_w = fractal_core.shape[1]
            if fc_w >= center_width:
                fractal_strip = fractal_core[:, :center_width]
            else:
                # 鏡像延伸以填滿
                fractal_strip = np.concatenate([fractal_core, cv2.flip(fractal_core, 1)], axis=1)[:, :center_width]

            # 以 Arousal 調製的 alpha 進行疊加
            blend_alpha = min(0.85, intensity * (0.4 + 0.4 * arousal))
            img_np[:, center_start:center_end] = cv2.addWeighted(
                img_np[:, center_start:center_end], 1.0 - blend_alpha,
                fractal_strip, blend_alpha, 0
            )

            return img_np
        except Exception:
            return img_np

    # ════════════════════════════════════════════════════════════════
    # 聲音物理特徵衍生的高階特效種類實作
    # ════════════════════════════════════════════════════════════════

    def apply_stereo_phase_slit(self, img_np, stereo_width, intensity):
        """利用立體聲寬度差，將過去的歷史影格與當前影格在空間中左右非對稱剪切"""
        try:
            buf_len = len(self.time_displacement_buffer.buffer)
            if buf_len < 10: return img_np
            
            h, w, c = img_np.shape
            mid = w // 2
            
            # 立體聲越寬，右半邊抓取的歷史影格越久遠（時間錯位越深）
            history_idx = int((buf_len - 1) * stereo_width * intensity)
            past_np = self.time_displacement_buffer.buffer[max(0, buf_len - 1 - history_idx)]
            
            # 融合：左半邊保留現在，右半邊強行替換為歷史
            out_np = img_np.copy()
            out_np[:, mid:, :] = past_np[:, mid:, :]
            
            # 在交界處進行微幅的羽化（模糊邊緣），製造非線性時空拉伸質感
            blur_w = int(30 * intensity) + 2
            if mid - blur_w > 0 and mid + blur_w < w:
                cv2.GaussianBlur(out_np[:, mid-blur_w:mid+blur_w], (0, 0), sigmaX=5, 
                                 dst=out_np[:, mid-blur_w:mid+blur_w])
                
            return out_np
        except Exception:
            return img_np

    def apply_centroid_glitch(self, img_np, centroid, roughness, intensity):
        """根據高頻質心動量，動態將畫面橫向切片移位，完美共振電晶體脆質地"""
        try:
            h, w, c = img_np.shape
            # 質心與粗糙度越高，切片越細（數量越多）、移位幅度越大
            num_slices = int(10 + 40 * centroid * roughness)
            slice_h = h // num_slices
            if slice_h < 2: return img_np
            
            out_np = img_np.copy()
            max_shift = int(60 * intensity * roughness)
            
            for i in range(num_slices):
                # 隨機決定該切片是否受高頻雜訊波及
                if random.random() < (centroid * 0.7):
                    y_start = i * slice_h
                    y_end = (i + 1) * slice_h
                    
                    # 產生隨機左右橫移
                    shift = random.randint(-max_shift, max_shift)
                    out_np[y_start:y_end, :, :] = np.roll(out_np[y_start:y_end, :, :], shift, axis=1)
                    
            return out_np
        except Exception:
            return img_np

    def apply_anticipatory_vignette(self, img_np, beat_phase, anticipation, intensity):
        """正拍預期心理學：在重拍砸落前夕收緊暗角與對比度，砸落瞬間視覺大釋放"""
        try:
            h, w, c = img_np.shape
            
            # 建立快取暈影矩陣
            if not hasattr(self, '_vignette_mask') or self._vignette_mask.shape[:2] != (h, w):
                # 建立中心徑向漸層
                y, x = np.mgrid[0:h, 0:w]
                cx, cy = w / 2.0, h / 2.0
                dist = np.sqrt((x - cx)**2 + (y - cy)**2)
                max_dist = np.sqrt(cx**2 + cy**2)
                # 歸一化遮罩 (中心為1, 四周為0)
                self._vignette_mask = np.clip(1.0 - (dist / max_dist), 0, 1)
            
            # 只有在蓄力階段（anticipation > 0）或正拍剛砸落的殘留階段，才會觸發呼吸暗房
            if anticipation > 0.01:
                # 縮緊暗角：擴大邊緣變暗的範圍
                mask = np.power(self._vignette_mask, 0.5 + 1.5 * anticipation * intensity)
                mask = np.expand_dims(mask, axis=2) # 廣播至 3 通道
                
                # 同時抽離飽和度，營造重拍前的窒息感
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                gray_3ch = np.stack([gray, gray, gray], axis=2)
                
                # 融合當前影格與灰色影格（蓄力時畫面偏灰、偏暗）
                blended = cv2.addWeighted(img_np, 1.0 - (0.4 * anticipation), gray_3ch, 0.4 * anticipation, 0)
                img_np = (blended * mask).astype(np.uint8)
                
            return img_np
        except Exception:
            return img_np

    def apply_tension_exclusion(self, img_np, tension, hue, intensity):
        """和弦張力互斥：不協和和弦會與畫面產生數學互斥，翻轉出極具情緒張力的色彩"""
        try:
            h, w, c = img_np.shape
            r, g, b = self._hue_to_rgb(hue)
            
            # 零分配建立純色張力層
            tension_layer = np.zeros_like(img_np)
            tension_layer[:, :, 0] = int(r * tension * intensity)
            tension_layer[:, :, 1] = int(g * tension * intensity)
            tension_layer[:, :, 2] = int(b * tension * intensity)
            
            # 核心數學翻轉：利用絕對值差值（cv2.absdiff）實作 Exclusion 混合效果
            excluded_np = cv2.absdiff(img_np, tension_layer)
            
            # 根據張力平滑混合原圖與互斥圖
            return cv2.addWeighted(img_np, 1.0 - (0.5 * tension), excluded_np, 0.5 * tension, 0)
        except Exception:
            return img_np

    def apply_polar_pixel_sorting(self, img_np, intensity):
        """變種 2：先將畫面拉入極座標，執行分選排序後再拉回，創造全域徑向/螺旋拉絲"""
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            center = (w / 2.0, h / 2.0)
            max_radius = min(w, h) / 2.0

            # 1. 變換至極座標
            polar_img = cv2.warpPolar(img_np, (w, h), center, max_radius, cv2.WARP_POLAR_LINEAR)

            # 2. 在極座標系下執行並行像素分選 (此時的 Y 軸代表角度，X 軸代表半徑)
            gray = (polar_img[:, :, 0] * 0.299 + polar_img[:, :, 1] * 0.587 + polar_img[:, :, 2] * 0.114).astype(np.uint8)
            threshold = int(255 - 140 * intensity)

            for y in range(0, h, 2):
                mask = gray[y, :] > threshold
                if not np.any(mask): continue
                indices = np.where(mask)[0]
                if len(indices) < 2: continue
                runs = np.split(indices, np.where(np.diff(indices) != 1)[0] + 1)
                for run in runs:
                    if len(run) > 5:
                        polar_img[y, run, :3] = polar_img[y, run[np.argsort(gray[y, run])], :3]

            # 3. 反轉極座標拉回直角座標系
            return cv2.warpPolar(polar_img, (w, h), center, max_radius, cv2.WARP_POLAR_LINEAR + cv2.WARP_INVERSE_MAP)
        except Exception:
            return img_np

    def apply_mosh_contour_feedback(self, img_np, t, hue, brightness, m_vscan, m_mosh):
        """變種 1：將提取出的向量等高線直接注入 Data-Mosh 速度場，撕裂出非線性的雷射流體網格"""
        if cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

            # 1. 提取等高線畫布 (如同原本 of vector_scan)
            sw, sh = max(1, w // 8), max(1, h // 8)
            small = cv2.resize(gray, (sw, sh), interpolation=cv2.INTER_LINEAR)
            small_thresh = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            contours, _ = cv2.findContours(small_thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            vector_canvas = np.zeros_like(img_np)
            r, g, b = self._hue_to_rgb(hue + math.sin(t) * 30.0)
            
            for contour in contours:
                if cv2.contourArea(contour) > 10:
                    contour_scaled = (contour * 8).astype(np.int32)
                    cv2.drawContours(vector_canvas, [contour_scaled], -1, (r, g, b), max(1, int(2 * m_vscan)))

            # 2. 強行將這塊「純向量畫布」送入 Data-Mosh 畫布/場進行邊緣像素拉伸
            if self._mosh_vector is not None and self._mosh_vector[0].shape == (h, w):
                x, y = self._mosh_vector
                shift_x = 40.0 * m_mosh * math.sin(m_mosh * 12.0)
                shift_y = 20.0 * m_mosh * math.cos(m_mosh * 6.0)
                map_x = np.clip(x - shift_x, 0, w - 1).astype(np.float32)
                map_y = np.clip(y - shift_y, 0, h - 1).astype(np.float32)
                
                # 讓雷射向量線段產生撕裂
                vector_canvas = cv2.remap(vector_canvas, map_x, map_y, cv2.INTER_NEAREST)

            # 3. 疊加回原圖
            return cv2.add(img_np, (vector_canvas * min(1.0, m_vscan)).astype(np.uint8))
        except Exception:
            return img_np

    # ════════════════════════════════════════════════════════════════
    # 17種全域特效的 5 個變種自適應分發實作
    # ════════════════════════════════════════════════════════════════

    # 1. 幾何畸變 (spatial_warping) 5變種
    def apply_spatial_warping_custom(self, img_np, t, intensity, sub_bass, percussive, is_beat, variant):
        if cv2 is None or intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                return self.apply_barrel_distortion(img_np, -0.18 * sub_bass * intensity, 0.0)
            elif variant == 1:
                return self.apply_polar_mapping(img_np, log_polar=True)
            elif variant == 2:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dx = np.sin(y * 0.02 + t * 5.0) * (15.0 * intensity)
                dy = np.cos(x * 0.02 + t * 5.0) * (15.0 * intensity)
                return cv2.remap(img_np, x + dx, y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 3:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                cx, cy = w/2.0, h/2.0
                r = np.sqrt((x-cx)**2 + (y-cy)**2)
                theta = np.arctan2(y-cy, x-cx)
                theta = np.abs(np.mod(theta, np.pi/2.0) - np.pi/4.0)
                map_x = (cx + r * np.cos(theta)).astype(np.float32)
                map_y = (cy + r * np.sin(theta)).astype(np.float32)
                return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            else:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                cx, cy = w/2.0, h/2.0
                rx, ry = x - cx, y - cy
                r = np.sqrt(rx**2 + ry**2)
                angle = intensity * np.exp(-r / (min(w, h) * 0.4)) * 3.0
                map_x = cx + rx * np.cos(angle) - ry * np.sin(angle)
                map_y = cy + rx * np.sin(angle) + ry * np.cos(angle)
                return cv2.remap(img_np, map_x.astype(np.float32), map_y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception: return img_np

    # 2. 流體噪訊 (fluid_noise) 5變種
    def apply_fluid_noise_custom(self, img_np, t, intensity, sub_bass, percussive, is_beat, anticipation, beat_energy, variant):
        if cv2 is None or intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            img_np = self.fluid_simulator.update_and_apply(img_np, t, is_beat, beat_energy)
            
            if variant == 0:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dx = np.sin(x * 0.006 + t * 2.5) * np.cos(y * 0.01 - t * 1.5) * (45.0 * intensity * (sub_bass + 0.1))
                dy = np.cos(x * 0.01 - t * 2.0) * np.sin(y * 0.006 + t * 2.2) * (45.0 * intensity * (sub_bass + 0.1))
                return cv2.remap(img_np, x + dx, y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 1:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                noise_x = (np.sin(x * 0.01 + t) + 0.5 * np.sin(x * 0.02 - t * 1.3) + 0.25 * np.sin(y * 0.04)) * (30.0 * intensity)
                noise_y = (np.cos(y * 0.01 - t) + 0.5 * np.cos(y * 0.02 + t * 1.2) + 0.25 * np.cos(x * 0.04)) * (30.0 * intensity)
                return cv2.remap(img_np, x + noise_x, y + noise_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 2:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dy = np.sin(x * 0.005 + t * 4.0) * (25.0 * intensity) - t * 15.0
                dy = np.mod(dy, h)
                return cv2.remap(img_np, x, dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 3:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                grid = 80.0
                cell_x = (x // grid) * grid + grid/2.0
                cell_y = (y // grid) * grid + grid/2.0
                dx = (x - cell_x) * (0.25 * intensity)
                dy = (y - cell_y) * (0.25 * intensity)
                return cv2.remap(img_np, x - dx, y - dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            else:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dx = np.sin(np.sin(x * 0.008) * 4.0 + t) * (35.0 * intensity)
                dy = np.cos(np.cos(y * 0.008) * 4.0 - t) * (35.0 * intensity)
                return cv2.remap(img_np, x + dx, y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception: return img_np

    # 3. 時空反饋 (temporal_feedback) 5變種
    def apply_temporal_feedback_custom(self, img_np, t, intensity, ethereal, roughness, chord_name, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                img_np = self.time_displacement_buffer.apply(img_np, 0.7 * intensity)
                return self.feedback_system.apply(img_np, intensity * (ethereal + 0.1), chord_name=chord_name, reverb_decay=(0.05 if ethereal > 0.5 else 0.15))
            elif variant == 1:
                if len(self.time_displacement_buffer.buffer) < 5: return img_np
                buf = self.time_displacement_buffer.buffer
                out_np = img_np.copy()
                slice_h = h // len(buf)
                for i in range(len(buf)):
                    y_start = i * slice_h
                    y_end = min(h, (i + 1) * slice_h)
                    out_np[y_start:y_end, :, :] = buf[-(i + 1)][y_start:y_end, :, :]
                return out_np
            elif variant == 2:
                return self.feedback_system.apply(img_np, intensity * 1.5, chord_name=chord_name, reverb_decay=0.4)
            elif variant == 3:
                if len(self.time_displacement_buffer.buffer) < 5: return img_np
                past = self.time_displacement_buffer.buffer[-3]
                past_resized = cv2.resize(past, (int(w * 1.05), int(h * 1.05)), interpolation=cv2.INTER_LINEAR)
                px = (past_resized.shape[1] - w) // 2
                py = (past_resized.shape[0] - h) // 2
                past_crop = past_resized[py:py+h, px:px+w]
                return cv2.addWeighted(img_np, 1.0 - 0.4 * intensity, past_crop, 0.4 * intensity, 0)
            else:
                if len(self.time_displacement_buffer.buffer) < 5: return img_np
                past = self.time_displacement_buffer.buffer[-2]
                past_flipped = cv2.flip(past, 1)
                return cv2.addWeighted(img_np, 1.0 - 0.3 * intensity, past_flipped, 0.3 * intensity, 0)
        except Exception: return img_np

    # 4. 光譜色彩 (color_spectral) 5變種
    def apply_color_spectral_custom(self, img_np, t, intensity, roughness, ethereal, chord_name, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                if roughness * (0.3 + roughness * 1.2) > 0.3:
                    img_np = self.apply_radial_chromatic_aberration_numpy(img_np, 1.2 * roughness * (0.3 + roughness * 1.2) * intensity)
                if ethereal > 0.4:
                    img_pil = Image.fromarray(img_np)
                    img_pil = self.apply_color_cycling(img_pil, t, 0.45 * ethereal * intensity, chord_name=chord_name)
                    img_np = np.array(img_pil)
                return img_np
            elif variant == 1:
                shift = int(15.0 * intensity)
                out = img_np.copy()
                if shift > 0:
                    out[:, :, 0] = np.roll(out[:, :, 0], shift, axis=1)
                    out[:, :, 2] = np.roll(out[:, :, 2], -shift, axis=1)
                return out
            elif variant == 2:
                gray = (img_np[:, :, 0] * 0.299 + img_np[:, :, 1] * 0.587 + img_np[:, :, 2] * 0.114).astype(np.uint8)
                thermal = cv2.applyColorMap(gray, cv2.COLORMAP_JET)
                return cv2.addWeighted(img_np, 1.0 - intensity, thermal, intensity, 0)
            elif variant == 3:
                out = img_np.copy()
                if int(t) % 2 == 0:
                    out[:, :, 0], out[:, :, 1], out[:, :, 2] = img_np[:, :, 1], img_np[:, :, 2], img_np[:, :, 0]
                else:
                    out[:, :, 0], out[:, :, 1], out[:, :, 2] = img_np[:, :, 2], img_np[:, :, 0], img_np[:, :, 1]
                return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
            else:
                gray = (img_np[:, :, 0] * 0.299 + img_np[:, :, 1] * 0.587 + img_np[:, :, 2] * 0.114) / 255.0
                out = np.zeros_like(img_np)
                for i, (c1, c2) in enumerate(zip([10, 20, 60], [255, 20, 147])):
                    out[:, :, i] = (c1 + gray * (c2 - c1)).astype(np.uint8)
                return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
        except Exception: return img_np

    # 5. 高階光影 (glow_illumination) 5變種
    def apply_glow_illumination_custom(self, img_np, t, intensity, sub_bass, percussive, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            img_pil = Image.fromarray(img_np)
            if variant == 0:
                img_pil = self.apply_bloom(img_pil, intensity * (sub_bass * 0.7 + 0.3))
                if percussive > 0.5:
                    img_pil = self.apply_god_rays(img_pil, 0.8 * intensity * percussive)
                return np.array(img_pil.convert('RGB'))
            elif variant == 1:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
                flare_mask = cv2.resize(thresh, (w // 8, h), interpolation=cv2.INTER_LINEAR)
                flare_blur = cv2.GaussianBlur(flare_mask, (15, 1), 0)
                flare_large = cv2.resize(flare_blur, (w, h), interpolation=cv2.INTER_LINEAR)
                flare_color = np.zeros_like(img_np)
                flare_color[:, :, 0] = (flare_large * 0.1 * intensity).astype(np.uint8)
                flare_color[:, :, 1] = (flare_large * 0.6 * intensity).astype(np.uint8)
                flare_color[:, :, 2] = (flare_large * 1.0 * intensity).astype(np.uint8)
                return cv2.add(img_np, flare_color)
            elif variant == 2:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                edges_blur = cv2.GaussianBlur(edges, (9, 9), 0)
                neon = np.zeros_like(img_np)
                neon[:, :, 0] = (edges_blur * 1.0 * intensity).astype(np.uint8)
                neon[:, :, 2] = (edges_blur * 0.8 * intensity).astype(np.uint8)
                return cv2.add(img_np, neon)
            elif variant == 3:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                star_canvas = np.zeros_like(img_np)
                star_len = int(15 + 30 * intensity)
                for c in contours[:20]:
                    M = cv2.moments(c)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        cv2.line(star_canvas, (cx - star_len, cy), (cx + star_len, cy), (255, 255, 255), 2)
                        cv2.line(star_canvas, (cx, cy - star_len), (cx, cy + star_len), (255, 255, 255), 2)
                return cv2.add(img_np, star_canvas)
            else:
                mask = np.zeros((h, w), dtype=np.uint8)
                cv2.circle(mask, (w//2, h//2), int(min(w, h) * 0.3 * (1.0 + intensity)), 255, -1)
                mask_inv = cv2.bitwise_not(mask)
                shadow = np.zeros_like(img_np)
                shadow_intensity = int(120 * intensity)
                shadow[:, :, :] = shadow_intensity
                shadow_applied = cv2.bitwise_and(shadow, shadow, mask=mask_inv)
                return cv2.subtract(img_np, shadow_applied)
        except Exception: return img_np

    # 6. 訊號退化 (retro_degradation) 5變種
    def apply_retro_degradation_custom(self, img_np, t, intensity, roughness, audio_feats, is_beat, beat_energy, genre_clean, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                # RGB halftone screen with dynamic, music-modulated size, spacing, rotation
                sub_bass = audio_feats.get('sub_bass', 0.5)
                # Cell size (spacing) is modulated: lower bass -> larger cells/dots spacing
                cell_size = int(8 + 12 * (1.0 - sub_bass))
                if cell_size < 4: cell_size = 4
                
                # Base rotation rotates slowly over time, modulated by beat energy
                base_angle = t * 15.0 + beat_energy * 30.0
                
                # Create halftone screen for each R, G, B channel at different angles (offset grids)
                channels = [img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2]]
                out_channels = []
                angles = [base_angle + 15.0, base_angle + 45.0, base_angle + 75.0]
                
                for ch_idx, ch in enumerate(channels):
                    factor = cell_size
                    small_ch = cv2.resize(ch, (w // factor, h // factor), interpolation=cv2.INTER_AREA)
                    sh, sw = small_ch.shape
                    
                    dot_ch = np.zeros_like(ch)
                    # We draw a circle at each grid point
                    for cy in range(sh):
                        for cx in range(sw):
                            val = small_ch[cy, cx]
                            if val < 15: continue
                            px = cx * factor + factor // 2
                            py = cy * factor + factor // 2
                            # Dot radius is proportional to the pixel value, intensity, and beat energy
                            r_dot = (val / 255.0) * (factor / 2.0) * intensity * (1.2 + 0.3 * beat_energy)
                            r_dot = max(1, int(r_dot))
                            # Add time-based rotation wobble
                            offset_x = int(math.sin(t * 5.0 + cy) * 2.0 * beat_energy)
                            offset_y = int(math.cos(t * 5.0 + cx) * 2.0 * beat_energy)
                            cv2.circle(dot_ch, (px + offset_x, py + offset_y), r_dot, 255, -1)
                            
                    out_channels.append(dot_ch)
                    
                halftoned = cv2.merge(out_channels)
                # Blend with CRT simulation for retro feel
                return self.apply_crt_simulation(halftoned, t, 0.5 * intensity)
            elif variant == 1:
                return self.apply_crt_simulation(img_np, t, intensity)
            elif variant == 2:
                factor = max(4, int(32 - 28 * intensity))
                small = cv2.resize(img_np, (w // factor, h // factor), interpolation=cv2.INTER_NEAREST)
                bits = 4
                small = (small // (256 // bits)) * (256 // bits)
                return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
            elif variant == 3:
                out = img_np.copy()
                for _ in range(int(3 * intensity + 1)):
                    y_pos = self.rng.randint(0, h - 20)
                    h_block = self.rng.randint(5, 20)
                    shift = self.rng.randint(-40, 40)
                    out[y_pos:y_pos+h_block, :, :] = np.roll(out[y_pos:y_pos+h_block, :, :], shift, axis=1)
                for _ in range(int(2 * intensity)):
                    y_pos = self.rng.randint(0, h - 2)
                    out[y_pos:y_pos+2, :, :] = 255
                return out
            else:
                # 旋轉幾何水晶格柵 (Rotating Geometric Crystal Grid)
                # The angle, size, and brightness of grid lines are modulated by music
                sub_bass = audio_feats.get('sub_bass', 0.5)
                percussive = audio_feats.get('percussive', 0.5)
                
                # Grid size (spacing)
                grid_spacing = int(25 + 50 * (1.0 - sub_bass))
                if grid_spacing < 10: grid_spacing = 10
                
                # Rotation angle of lattice
                angle = t * 10.0 + percussive * 20.0
                
                # Make a grid canvas on a larger square canvas to allow rotation
                diag = int(math.sqrt(h*h + w*w))
                grid_tmp = np.zeros((diag, diag, 3), dtype=np.uint8)
                
                # Choose color based on chord_hue
                chord_hue = audio_feats.get('chord_hue', 180.0)
                r_c, g_c, b_c = self._hue_to_rgb(chord_hue)
                color = (r_c, g_c, b_c)
                
                thickness = max(1, int(1 + 3 * intensity * percussive))
                for x in range(0, diag, grid_spacing):
                    cv2.line(grid_tmp, (x, 0), (x, diag), color, thickness)
                for y in range(0, diag, grid_spacing):
                    cv2.line(grid_tmp, (0, y), (diag, y), color, thickness)
                    
                # Rotate the grid canvas
                center = (diag // 2, diag // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated_grid = cv2.warpAffine(grid_tmp, M, (diag, diag))
                
                # Crop to original size center
                x_start = (diag - w) // 2
                y_start = (diag - h) // 2
                cropped_grid = rotated_grid[y_start:y_start+h, x_start:x_start+w]
                
                # Glass refraction distortion underneath the grid lines:
                gray_grid = cv2.cvtColor(cropped_grid, cv2.COLOR_RGB2GRAY)
                dx, dy = cv2.spatialGradient(gray_grid)
                y_map, x_map = np.mgrid[0:h, 0:w].astype(np.float32)
                warp_intensity = 15.0 * intensity * (0.5 + 0.5 * sub_bass)
                map_x = np.clip(x_map + dx * 0.1 * warp_intensity, 0, w - 1)
                map_y = np.clip(y_map + dy * 0.1 * warp_intensity, 0, h - 1)
                distorted_img = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                
                out = cv2.addWeighted(distorted_img, 1.0, cropped_grid, 0.4 * intensity, 0)
                return out
        except Exception: return img_np

    # 7. 像素分選 (pixel_sort) 5變種
    def apply_pixel_sort_custom(self, img_np, intensity, roughness, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                return self.apply_pixel_sorting(img_np, intensity)
            elif variant == 1:
                return self.apply_polar_pixel_sorting(img_np, intensity)
            elif variant == 2:
                out = img_np.copy()
                grid = 60
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                for cy in range(0, h - grid, grid):
                    for cx in range(0, w - grid, grid):
                        block = gray[cy:cy+grid, cx:cx+grid]
                        if np.mean(block) > (255 - 130 * intensity):
                            for dy in range(grid):
                                line = out[cy+dy, cx:cx+grid, :3]
                                out[cy+dy, cx:cx+grid, :3] = line[np.argsort(block[dy, :]), :3]
                return out
            elif variant == 3:
                M = cv2.getRotationMatrix2D((w/2.0, h/2.0), 45, 1.0)
                rotated = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                rotated = self.apply_pixel_sorting(rotated, intensity)
                M_inv = cv2.getRotationMatrix2D((w/2.0, h/2.0), -45, 1.0)
                return cv2.warpAffine(rotated, M_inv, (w, h), borderMode=cv2.BORDER_REFLECT)
            else:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 60, 180)
                out = img_np.copy()
                for y in range(0, h, 4):
                    mask_indices = np.where(edges[y, :] > 0)[0]
                    if len(mask_indices) > 5:
                        out[y, mask_indices, :3] = out[y, mask_indices[np.argsort(gray[y, mask_indices])], :3]
                return out
        except Exception: return img_np

    # 8. 鏡像萬花筒 (kaleidoscope) 5變種
    def apply_kaleidoscope_custom(self, img_np, t, intensity, sub_bass, beat_energy, is_beat, cx_offset, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            k_segs = max(2, ((2 + int(sub_bass * 8.0) + (int(4.0 * beat_energy) if is_beat and beat_energy > 0.4 else 0)) // 2) * 2)
            if variant == 0:
                return self.apply_kaleidoscope(img_np, k_segs, t * 0.15, cx_offset=cx_offset)
            elif variant == 1:
                mid_x, mid_y = w // 2, h // 2
                out = img_np.copy()
                left_half = img_np[:, :mid_x]
                out[:, mid_x:] = cv2.flip(left_half, 1)
                top_half = out[:mid_y, :]
                out[mid_y:, :] = cv2.flip(top_half, 0)
                return out
            elif variant == 2:
                out = img_np.copy()
                for i in range(1, 4):
                    scale = 1.0 - 0.2 * i * intensity
                    sw, sh = int(w * scale), int(h * scale)
                    if sw < 10 or sh < 10: break
                    resized = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
                    px = (w - sw) // 2
                    py = (h - sh) // 2
                    out[py:py+sh, px:px+sw] = cv2.addWeighted(out[py:py+sh, px:px+sw], 0.4, resized, 0.6, 0)
                return out
            elif variant == 3:
                mid_x = w // 2
                out = img_np.copy()
                quarter = img_np[:h//2, :mid_x]
                flipped_x = cv2.flip(quarter, 1)
                flipped_y = cv2.flip(quarter, 0)
                flipped_xy = cv2.flip(flipped_x, 0)
                out[:h//2, :mid_x] = quarter
                out[:h//2, mid_x:] = flipped_x
                out[h//2:, :mid_x] = flipped_y
                out[h//2:, mid_x:] = flipped_xy
                return out
            else:
                shift_cx = int(math.sin(t * 2.0) * 150.0 * intensity)
                return self.apply_kaleidoscope(img_np, k_segs, t * 0.1, cx_offset=cx_offset + shift_cx)
        except Exception: return img_np

    # 9. 空靈聲學 (ambient_dsp) 5變種
    def apply_ambient_dsp_custom(self, img_np, t, intensity, ethereal, percussive, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                img = img_np.copy()
                if ethereal > 0.4 and percussive < 0.35:
                    blur_r = (ethereal - 0.4) * 6.0 * intensity
                    if blur_r > 0.5:
                        ksize = int(6 * blur_r) | 1
                        if ksize > 0:
                            img = cv2.GaussianBlur(img, (ksize, ksize), blur_r)
                if len(self.time_displacement_buffer.buffer) >= 10:
                    buf = self.time_displacement_buffer.buffer[-10]
                    img = cv2.addWeighted(img, 1.0 - 0.35 * intensity, buf, 0.35 * intensity, 0)
                
                factor = 1.0 - (0.20 * (1.0 - (0.5 + 0.5 * math.sin(t * 0.785))) * intensity)
                mean_val = np.mean(img)
                img_f = img.astype(np.float32)
                img_enhanced = img_f * factor + mean_val * (1.0 - factor)
                return np.clip(img_enhanced, 0, 255).astype(np.uint8)

            elif variant == 1:
                out = img_np.astype(np.float32)
                for i in range(1, 4):
                    scale = 1.0 + 0.05 * i * intensity
                    sw, sh = int(w * scale), int(h * scale)
                    resized = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
                    left = (sw - w) // 2
                    top = (sh - h) // 2
                    cropped = resized[top:top+h, left:left+w]
                    if cropped.shape[:2] != (h, w):
                        cropped = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
                    
                    alpha = (60.0 * intensity / i) / 255.0
                    out = out * (1.0 - alpha) + cropped.astype(np.float32) * alpha
                return np.clip(out, 0, 255).astype(np.uint8)

            elif variant == 2:
                blur_img = cv2.GaussianBlur(img_np, (25, 25), 0)
                y_indices = np.arange(h).reshape(h, 1, 1)
                mask = np.clip(1.0 - np.abs(y_indices - h/2.0) / (h/2.0), 0, 1)
                mask = np.power(mask, 3.0 * intensity)
                return (img_np * mask + blur_img * (1.0 - mask)).astype(np.uint8)

            elif variant == 3:
                blur_img = cv2.GaussianBlur(img_np, (31, 31), 15.0)
                mean_val = np.mean(blur_img)
                blur_f = blur_img.astype(np.float32)
                bright_blur = np.clip(blur_f * 1.5 + mean_val * (-0.5), 0, 255).astype(np.uint8)
                return cv2.addWeighted(img_np, 1.0 - 0.4 * intensity, bright_blur, 0.4 * intensity, 0)

            else:
                canvas = img_np.copy()
                for _ in range(int(5 + 10 * intensity)):
                    cx = random.randint(0, w - 1)
                    cy = random.randint(0, h - 1)
                    r = random.randint(15, int(40 * intensity + 15))
                    cv2.circle(canvas, (cx, cy), r, (255, 255, 255), -1)
                canvas_blur = cv2.GaussianBlur(canvas, (21, 21), 0)
                return cv2.addWeighted(img_np, 1.0 - 0.3 * intensity, canvas_blur, 0.3 * intensity, 0)
        except Exception:
            return img_np
    def apply_data_mosh_custom(self, img_np, intensity, variant):
        if cv2 is None or intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                return self.apply_data_mosh(img_np, intensity)
            elif variant == 1:
                out = img_np.copy()
                if len(self.time_displacement_buffer.buffer) > 5:
                    past = self.time_displacement_buffer.buffer[-4]
                    for _ in range(2):
                        y_pos = random.randint(0, h - 60)
                        h_block = random.randint(20, 60)
                        out[y_pos:y_pos+h_block, :, :] = past[y_pos:y_pos+h_block, :, :]
                return out
            elif variant == 2:
                if len(self.time_displacement_buffer.buffer) < 10: return img_np
                out = img_np.copy()
                buf = self.time_displacement_buffer.buffer
                for y in range(0, h, 8):
                    delay = int((y / h) * (len(buf) - 1) * intensity)
                    delay = max(0, min(len(buf) - 1, delay))
                    out[y:y+8, :, :] = buf[-(delay + 1)][y:y+8, :, :]
                return out
            elif variant == 3:
                out = img_np.copy()
                palette = getattr(self, 'mosh_palette', [])
                for _ in range(int(3 + 5 * intensity)):
                    bx = random.randint(0, w - 100)
                    by = random.randint(0, h - 100)
                    bw = random.randint(30, 100)
                    bh = random.randint(30, 100)
                    if palette:
                        r_base, g_base, b_base = random.choice(palette)
                        # Add slight local brightness variation for dynamic feel
                        v = random.randint(-20, 20)
                        r = max(0, min(255, r_base + v))
                        g = max(0, min(255, g_base + v))
                        b = max(0, min(255, b_base + v))
                    else:
                        r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
                    out[by:by+bh, bx:bx+bw, 0] = r
                    out[by:by+bh, bx:bx+bw, 1] = g
                    out[by:by+bh, bx:bx+bw, 2] = b
                return cv2.addWeighted(img_np, 1.0 - 0.4 * intensity, out, 0.4 * intensity, 0)
            else:
                if len(self.time_displacement_buffer.buffer) < 5: return img_np
                past = self.time_displacement_buffer.buffer[-3]
                gray_curr = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                gray_past = cv2.cvtColor(past, cv2.COLOR_RGB2GRAY)
                diff = cv2.absdiff(gray_curr, gray_past)
                _, diff_mask = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                diff_mask_bool = diff_mask > 0
                out = img_np.copy()
                out[diff_mask_bool] = cv2.addWeighted(img_np[diff_mask_bool], 1.0 - 0.6 * intensity, past[diff_mask_bool], 0.6 * intensity, 0)
                return out
        except Exception: return img_np

    # 11. 流沙沉澱 (sedimentation) 5變種
    def apply_sedimentation_custom(self, img_np, t, sub_bass, ethereal, intensity, chord_tension, variant):
        if cv2 is None or intensity < 0.01: return img_np
        try:
            h, w, c = img_np.shape
            if self._sediment_buffer is None or self._sediment_buffer.shape != (h, w, c):
                self._sediment_buffer = np.zeros((h, w, c), dtype=np.float32)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            edges = cv2.Canny(gray, 50, 150)
            particles_mask = (thresh > 0) | (edges > 0)
            self._sediment_buffer[particles_mask] += img_np[particles_mask].astype(np.float32) * 0.4
            decay = 0.92 - (0.05 * ethereal)
            self._sediment_buffer *= max(0.8, min(0.98, decay))
            sediment_uint8 = np.clip(self._sediment_buffer * intensity, 0, 255).astype(np.uint8)
            if variant == 0:
                gravity = 2.0 * (1.0 - sub_bass)
                bass_lift = int(20.0 * sub_bass * intensity)
                M = np.float32([[1, 0, random.uniform(-2.0, 2.0) * intensity], [0, 1, gravity - bass_lift]])
                self._sediment_buffer = cv2.warpAffine(self._sediment_buffer, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
                if chord_tension > 0.3:
                    excluded_sediment = cv2.absdiff(img_np, sediment_uint8)
                    return cv2.addWeighted(img_np, 1.0 - (0.4 * chord_tension), excluded_sediment, 0.4 * chord_tension, 0)
                return cv2.addWeighted(img_np, 1.0, sediment_uint8, 0.7, 0)
            elif variant == 1:
                M = np.float32([[1, 0, (8.0 + 15.0 * sub_bass) * intensity], [0, 1, random.uniform(-1.0, 1.0)]])
                self._sediment_buffer = cv2.warpAffine(self._sediment_buffer, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
                return cv2.addWeighted(img_np, 1.0, sediment_uint8, 0.7, 0)
            elif variant == 2:
                M = np.float32([[1, 0, random.uniform(-2.0, 2.0)], [0, 1, -4.0 * intensity]])
                self._sediment_buffer = cv2.warpAffine(self._sediment_buffer, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
                return cv2.addWeighted(img_np, 1.0, sediment_uint8, 0.7, 0)
            elif variant == 3:
                M = cv2.getRotationMatrix2D((w/2.0, h/2.0), 1.5 * intensity, 1.0)
                self._sediment_buffer = cv2.warpAffine(self._sediment_buffer, M, (w, h), borderMode=cv2.BORDER_CONSTANT)
                return cv2.addWeighted(img_np, 1.0, sediment_uint8, 0.7, 0)
            else:
                self._sediment_buffer = cv2.GaussianBlur(self._sediment_buffer, (5, 5), 0)
                return cv2.addWeighted(img_np, 1.0, sediment_uint8, 0.7, 0)
        except Exception: return img_np

    # 12. 雷射等高線 (vector_scan) 5變種
    def apply_vector_scan_custom(self, img_np, t, hue, brightness, intensity, m_mosh, percussive, variant):
        if cv2 is None or intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                if m_mosh > 0.1:
                    return self.apply_mosh_contour_feedback(img_np, t, hue, brightness, intensity, m_mosh)
                else:
                    return self.apply_vector_scan_lines(img_np, t, hue, brightness, intensity * percussive)
            elif variant == 1:
                grid_canvas = np.zeros_like(img_np)
                r, g, b = self._hue_to_rgb(hue)
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                step = 40
                for y in range(0, h, step):
                    points = []
                    for x in range(0, w, step):
                        val = gray[y, x]
                        offset_y = int((val / 255.0) * -80.0 * intensity)
                        points.append([x, y + offset_y])
                    if len(points) > 1:
                        cv2.polylines(grid_canvas, [np.array(points, dtype=np.int32)], False, (r, g, b), 1)
                return cv2.add(img_np, grid_canvas)
            elif variant == 2:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 60, 180)
                holo = np.zeros_like(img_np)
                holo[:, :, 1] = edges
                holo[:, :, 2] = edges
                if random.random() < 0.3:
                    holo = np.roll(holo, random.randint(-15, 15), axis=1)
                return cv2.addWeighted(img_np, 1.0, (holo * intensity).astype(np.uint8), 0.8, 0)
            elif variant == 3:
                r_c, g_c, b_c = self._hue_to_rgb(hue + 90.0)
                oscilloscope = np.zeros_like(img_np)
                cx, cy = w // 2, h // 2
                base_r = int(min(w, h) * 0.25)
                points = []
                for angle in range(0, 360, 5):
                    rad = math.radians(angle)
                    sample_x = int(cx + base_r * math.cos(rad))
                    sample_y = int(cy + base_r * math.sin(rad))
                    sample_x = max(0, min(w - 1, sample_x))
                    sample_y = max(0, min(h - 1, sample_y))
                    val = img_np[sample_y, sample_x, 0]
                    current_r = base_r + int((val / 255.0) * 100.0 * intensity)
                    px = int(cx + current_r * math.cos(rad + t))
                    py = int(cy + current_r * math.sin(rad + t))
                    points.append([px, py])
                if len(points) > 1:
                    cv2.polylines(oscilloscope, [np.array(points, dtype=np.int32)], True, (r_c, g_c, b_c), 2)
                return cv2.add(img_np, oscilloscope)
            else:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                small = cv2.resize(gray, (w // 8, h // 8))
                _, thresh = cv2.threshold(small, 150, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                vector = np.zeros_like(img_np)
                for i, c in enumerate(contours):
                    if cv2.contourArea(c) < 5: continue
                    r, g, b = self._hue_to_rgb((i * 25 + int(t * 50)) % 360)
                    cv2.drawContours(vector, [c * 8], -1, (r, g, b), 1)
                return cv2.add(img_np, (vector * intensity).astype(np.uint8))
        except Exception: return img_np

    # 13. 時空分形鏡 (temporal_fractal) 5變種
    def apply_temporal_fractal_custom(self, img_np, stereo_width, arousal, intensity, variant):
        if cv2 is None or intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                return self.apply_temporal_fractal(img_np, stereo_width, arousal, intensity)
            elif variant == 1:
                M = cv2.getRotationMatrix2D((w/2.0, h/2.0), 10.0 * intensity, 0.95)
                rotated = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                return cv2.absdiff(img_np, (rotated * intensity).astype(np.uint8))
            elif variant == 2:
                if len(self.time_displacement_buffer.buffer) < 5: return img_np
                past = self.time_displacement_buffer.buffer[-3]
                out = img_np.copy()
                grid_w, grid_h = w // 8, h // 8
                for cy in range(8):
                    for cx in range(8):
                        if (cx + cy) % 2 == 1:
                            x_start = cx * grid_w
                            x_end = (cx + 1) * grid_w
                            y_start = cy * grid_h
                            y_end = (cy + 1) * grid_h
                            out[y_start:y_end, x_start:x_end, :] = past[y_start:y_end, x_start:x_end, :]
                return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
            elif variant == 3:
                y, x = np.mgrid[-1.5:1.5:1j*h, -2.0:1.0:1j*w]
                c = x + 1j*y
                z = np.zeros_like(c)
                fractal_mask = np.zeros((h, w), dtype=np.uint8)
                for i in range(15):
                    z = z**2 + c
                    mask = np.abs(z) < 2.0
                    fractal_mask[mask] = i * 17
                mask_rgb = np.stack([fractal_mask, fractal_mask, fractal_mask], axis=2)
                return cv2.addWeighted(img_np, 1.0 - 0.4 * intensity, mask_rgb, 0.4 * intensity, 0)
            else:
                if len(self.time_displacement_buffer.buffer) < 6: return img_np
                buf = self.time_displacement_buffer.buffer
                out = img_np.copy()
                y, x = np.mgrid[0:h, 0:w]
                cx, cy = w/2.0, h/2.0
                dist = np.sqrt((x-cx)**2 + (y-cy)**2)
                max_d = min(w, h) / 2.0
                for r_idx in range(4):
                    r_start = (r_idx * max_d) / 4.0
                    r_end = ((r_idx + 1) * max_d) / 4.0
                    ring_mask = (dist >= r_start) & (dist < r_end)
                    if np.any(ring_mask):
                        delay = int(r_idx * 2 * intensity)
                        idx = max(0, min(len(buf) - 1, len(buf) - 1 - delay))
                        out[ring_mask] = buf[idx][ring_mask]
                return out
        except Exception: return img_np

    # 14. 相位剪切 (phase_slit) 5變種
    def apply_phase_slit_custom(self, img_np, stereo_width, intensity, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                return self.apply_stereo_phase_slit(img_np, stereo_width, intensity)
            elif variant == 1:
                shift = int(30 * stereo_width * intensity)
                out = img_np.copy()
                mid = w // 2
                out[:, :mid] = np.roll(img_np[:, :mid], -shift, axis=1)
                out[:, mid:] = np.roll(img_np[:, mid:], shift, axis=1)
                return out
            elif variant == 2:
                if len(self.time_displacement_buffer.buffer) < 5: return img_np
                past = self.time_displacement_buffer.buffer[-3]
                out = img_np.copy()
                out[0::2, :, :] = past[0::2, :, :]
                return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
            elif variant == 3:
                M_left = np.float32([[1, 0.05 * stereo_width * intensity, 0], [0, 1, 0]])
                M_right = np.float32([[1, -0.05 * stereo_width * intensity, 0], [0, 1, 0]])
                mid = w // 2
                left = cv2.warpAffine(img_np[:, :mid], M_left, (mid, h), borderMode=cv2.BORDER_REFLECT)
                right = cv2.warpAffine(img_np[:, mid:], M_right, (w - mid, h), borderMode=cv2.BORDER_REFLECT)
                out = img_np.copy()
                out[:, :mid] = left
                out[:, mid:] = right
                return out
            else:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                shift = int(12 * stereo_width * intensity)
                out = img_np.copy()
                if shift > 0:
                    edge_mask = edges > 0
                    out[edge_mask, 0] = np.roll(img_np[:, :, 0], shift, axis=1)[edge_mask]
                    out[edge_mask, 2] = np.roll(img_np[:, :, 2], -shift, axis=1)[edge_mask]
                return out
        except Exception: return img_np

    # 15. 高頻破碎 (centroid_glitch) 5變種
    def apply_centroid_glitch_custom(self, img_np, centroid, roughness, intensity, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                return self.apply_centroid_glitch(img_np, centroid, roughness, intensity)
            elif variant == 1:
                out = img_np.copy()
                grid_w, grid_h = w // 4, h // 4
                if grid_w > 10 and grid_h > 10:
                    cells = [(ix, iy) for ix in range(4) for iy in range(4)]
                    num_swaps = int(1 + 3 * centroid * intensity)
                    for _ in range(num_swaps):
                        c1, c2 = random.sample(cells, 2)
                        x1, y1 = c1[0]*grid_w, c1[1]*grid_h
                        x2, y2 = c2[0]*grid_w, c2[1]*grid_h
                        temp = out[y1:y1+grid_h, x1:x1+grid_w].copy()
                        out[y1:y1+grid_h, x1:x1+grid_w] = out[y2:y2+grid_h, x2:x2+grid_w]
                        out[y2:y2+grid_h, x2:x2+grid_w] = temp
                return out
            elif variant == 2:
                out = img_np.copy()
                shift_noise = np.random.randint(-int(10 * intensity + 1), int(10 * intensity + 2), (h, w), dtype=np.int16)
                y, x = np.mgrid[0:h, 0:w]
                map_x_r = np.clip(x + shift_noise, 0, w - 1).astype(np.float32)
                map_x_b = np.clip(x - shift_noise, 0, w - 1).astype(np.float32)
                out[:, :, 0] = cv2.remap(img_np[:, :, 0], map_x_r, y.astype(np.float32), cv2.INTER_LINEAR)
                out[:, :, 2] = cv2.remap(img_np[:, :, 2], map_x_b, y.astype(np.float32), cv2.INTER_LINEAR)
                return out
            elif variant == 3:
                mask = int(64 * intensity)
                if mask > 0:
                    out = cv2.bitwise_xor(img_np, (mask, mask, mask))
                    return cv2.addWeighted(img_np, 1.0 - 0.3 * intensity, out, 0.3 * intensity, 0)
                return img_np
            else:
                out = img_np.copy()
                num_lines = int(20 + 30 * centroid)
                lh = h // num_lines
                for i in range(num_lines):
                    y_start = i * lh
                    y_end = min(h, (i + 1) * lh)
                    shift = int(math.sin(i * 0.5 + centroid * 10.0) * 40.0 * intensity)
                    out[y_start:y_end, :, :] = np.roll(out[y_start:y_end, :, :], shift, axis=1)
                return out
        except Exception: return img_np

    # 16. 呼吸暗房 (vignette_pulse) 5變種
    def apply_vignette_pulse_custom(self, img_np, beat_phase, anticipation, intensity, variant):
        try:
            h, w = img_np.shape[:2]
            if not hasattr(self, '_vignette_mask') or self._vignette_mask.shape[:2] != (h, w):
                y, x = np.mgrid[0:h, 0:w]
                cx, cy = w / 2.0, h / 2.0
                dist = np.sqrt((x - cx)**2 + (y - cy)**2)
                max_dist = np.sqrt(cx**2 + cy**2)
                self._vignette_mask = np.clip(1.0 - (dist / max_dist), 0, 1)
            if variant == 0:
                return self.apply_anticipatory_vignette(img_np, beat_phase, anticipation, intensity)
            elif variant == 1:
                if getattr(self, 'photosensitive_safe', False):
                    return self.apply_anticipatory_vignette(img_np, beat_phase, anticipation, intensity)
                if anticipation > 0.05:
                    mask = np.expand_dims(self._vignette_mask, axis=2)
                    flash_layer = np.ones_like(img_np) * 255
                    img_np = cv2.addWeighted(img_np, 1.0, (flash_layer * mask * anticipation * intensity * 0.8).astype(np.uint8), 1.0, 0)
                return img_np
            elif variant == 2:
                if anticipation > 0.05:
                    mask = np.expand_dims(1.0 - self._vignette_mask, axis=2)
                    inverted = 255 - img_np
                    img_np = (img_np * (1.0 - mask * anticipation * intensity) + inverted * (mask * anticipation * intensity)).astype(np.uint8)
                return img_np
            elif variant == 3:
                if anticipation > 0.01:
                    y, x = np.mgrid[0:h, 0:w]
                    cx, cy = w/2.0, h/2.0
                    dist = np.sqrt((x-cx)**2 + (y-cy)**2)
                    wave_r = (anticipation * min(w, h)) * 0.6
                    wave_width = 30.0
                    wave_mask = np.clip(1.0 - np.abs(dist - wave_r) / wave_width, 0, 1)
                    wave_mask = np.expand_dims(wave_mask, axis=2)
                    img_np = (img_np * (1.0 - 0.4 * wave_mask * intensity)).astype(np.uint8)
                return img_np
            else:
                if beat_phase < 0.15 and intensity > 0.3:
                    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                    thresh_rgb = np.stack([thresh, thresh, thresh], axis=2)
                    blend = (1.0 - beat_phase / 0.15) * 0.6 * intensity
                    return cv2.addWeighted(img_np, 1.0 - blend, thresh_rgb, blend, 0)
                return img_np
        except Exception: return img_np

    # 17. 張力互斥 (tension_overlay) 5變種
    def apply_tension_overlay_custom(self, img_np, tension, hue, intensity, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            if variant == 0:
                if getattr(self, 'photosensitive_safe', False):
                    return self.apply_tension_overlay_custom(img_np, tension, hue, intensity, 3)
                return self.apply_tension_exclusion(img_np, tension, hue, intensity)
            elif variant == 1:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dx = np.sin(y * 0.03 + hue) * (30.0 * tension * intensity)
                dy = np.cos(x * 0.03 - hue) * (30.0 * tension * intensity)
                return cv2.remap(img_np, x + dx, y + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 2:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
                r_c, g_c, b_c = self._hue_to_rgb(hue)
                out = np.zeros_like(img_np)
                mask = thresh > 0
                out[mask] = (r_c, g_c, b_c)
                out[~mask] = (255 - r_c, 255 - g_c, 255 - b_c)
                return cv2.addWeighted(img_np, 1.0 - 0.5 * tension * intensity, out, 0.5 * tension * intensity, 0)
            elif variant == 3:
                r_ch = img_np[:, :, 0]
                b_ch = img_np[:, :, 2]
                r_blur = cv2.GaussianBlur(r_ch, (25, 25), 0)
                b_blur = cv2.GaussianBlur(b_ch, (25, 25), 0)
                bleed = img_np.copy()
                bleed[:, :, 0] = cv2.addWeighted(r_ch, 0.4, r_blur, 0.6 * intensity * tension, 0)
                bleed[:, :, 2] = cv2.addWeighted(b_ch, 0.4, b_blur, 0.6 * intensity * tension, 0)
                return bleed
            else:
                if len(self.time_displacement_buffer.buffer) < 3: return img_np
                past = self.time_displacement_buffer.buffer[-2]
                excluded = cv2.absdiff(img_np, past)
                return cv2.addWeighted(img_np, 1.0 - 0.4 * tension * intensity, excluded, 0.4 * tension * intensity, 0)
        except Exception: return img_np

    # ════════════════════════════════════════════════════════════════
    # 後製增強與全新 VJ 特效組件 (ndarray 介面)
    # ════════════════════════════════════════════════════════════════

    def apply_sharpening(self, img_np, amount=0.75, radius=1.0):
        if amount < 0.01: return img_np
        try:
            sigma = radius
            kernel_size = int(round(radius * 3)) * 2 + 1
            blurred = cv2.GaussianBlur(img_np, (kernel_size, kernel_size), sigma)
            sharpened = cv2.addWeighted(img_np, 1.0 + amount, blurred, -amount, 0)
            return np.clip(sharpened, 0, 255).astype(np.uint8)
        except Exception:
            return img_np

    def apply_color_enhancement(self, img_np, contrast=1.12, saturation=1.15, exposure=1.0, grayscale_blend=0.0):
        try:
            # 1. 曝光度調整 (Exposure)
            if abs(exposure - 1.0) > 0.01:
                img_np = np.clip(img_np * exposure, 0, 255).astype(np.uint8)
            
            # 2. 對比度調整 (S-curve LUT)
            if abs(contrast - 1.0) > 0.01:
                lut = np.zeros((256,), dtype=np.uint8)
                for i in range(256):
                    x = i / 255.0
                    factor = contrast
                    res = 0.5 + (x - 0.5) * factor
                    res = np.clip(res, 0.0, 1.0)
                    lut[i] = int(res * 255.0)
                img_np = cv2.LUT(img_np, lut)

            # 3. 飽和度與灰度調整 (Saturation & Grayscale blend)
            if abs(saturation - 1.0) > 0.01 or grayscale_blend > 0.01:
                hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV).astype(np.float32)
                if abs(saturation - 1.0) > 0.01:
                    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0.0, 255.0)
                if grayscale_blend > 0.01:
                    hsv[:, :, 1] = hsv[:, :, 1] * (1.0 - grayscale_blend)
                img_np = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
            
            return img_np
        except Exception:
            return img_np

    def _fast_kuwahara(self, img_np, r):
        # 快速向量化 Kuwahara 濾鏡 (使用 boxFilter 避免像素雙層 loop)
        img = img_np.astype(np.float32)
        h, w = img.shape[:2]
        
        pad_img = cv2.copyMakeBorder(img, r, r, r, r, cv2.BORDER_REFLECT)
        
        ksize = r + 1
        
        # 左上
        m0 = cv2.boxFilter(pad_img, -1, (ksize, ksize), anchor=(ksize-1, ksize-1))
        m20 = cv2.boxFilter(pad_img * pad_img, -1, (ksize, ksize), anchor=(ksize-1, ksize-1))
        v0 = m20 - m0 * m0
        
        # 右上
        m1 = cv2.boxFilter(pad_img, -1, (ksize, ksize), anchor=(0, ksize-1))
        m21 = cv2.boxFilter(pad_img * pad_img, -1, (ksize, ksize), anchor=(0, ksize-1))
        v1 = m21 - m1 * m1
        
        # 左下
        m2 = cv2.boxFilter(pad_img, -1, (ksize, ksize), anchor=(ksize-1, 0))
        m22 = cv2.boxFilter(pad_img * pad_img, -1, (ksize, ksize), anchor=(ksize-1, 0))
        v2 = m22 - m2 * m2
        
        # 右下
        m3 = cv2.boxFilter(pad_img, -1, (ksize, ksize), anchor=(0, 0))
        m23 = cv2.boxFilter(pad_img * pad_img, -1, (ksize, ksize), anchor=(0, 0))
        v3 = m23 - m3 * m3
        
        # 計算三個色彩通道的方差總和
        v0_s = np.sum(v0, axis=2)
        v1_s = np.sum(v1, axis=2)
        v2_s = np.sum(v2, axis=2)
        v3_s = np.sum(v3, axis=2)
        
        min_v = np.minimum(np.minimum(v0_s, v1_s), np.minimum(v2_s, v3_s))
        
        mask0 = (v0_s == min_v)[:, :, np.newaxis]
        mask1 = (v1_s == min_v)[:, :, np.newaxis]
        mask2 = (v2_s == min_v)[:, :, np.newaxis]
        mask3 = (v3_s == min_v)[:, :, np.newaxis]
        
        res = np.zeros_like(pad_img)
        res = np.where(mask0, m0, res)
        res = np.where(mask1, m1, res)
        res = np.where(mask2, m2, res)
        res = np.where(mask3, m3, res)
        
        res = res[r:-r, r:-r]
        return np.clip(res, 0, 255).astype(np.uint8)

    def apply_kuwahara_paint_custom(self, img_np, t, intensity, roughness, ethereal, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            # 性能防禦：大解析度先縮小處理再放大，確保流暢度
            scale = 1.0
            if w > 480:
                scale = 480.0 / w
                img_proc = cv2.resize(img_np, (480, int(h * scale)), interpolation=cv2.INTER_LINEAR)
            else:
                img_proc = img_np.copy()
                
            r = int(2 + 3 * intensity)
            res_proc = self._fast_kuwahara(img_proc, r)
            
            if scale < 1.0:
                res = cv2.resize(res_proc, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                res = res_proc
                
            return cv2.addWeighted(img_np, 1.0 - intensity, res, intensity, 0)
        except Exception as e:
            logger.error(f"Kuwahara error: {e}")
            return img_np

    def apply_matrix_ascii_custom(self, img_np, t, intensity, audio_feats, is_beat, beat_energy, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            cols = 80
            rows = 45
            cell_w = w // cols
            cell_h = h // rows
            if cell_w == 0 or cell_h == 0: return img_np
            
            if not hasattr(self, '_matrix_streams'):
                self._matrix_streams = [self.rng.randint(-20, 0) for _ in range(cols)]
                self._matrix_chars = [[chr(self.rng.randint(33, 126)) for _ in range(rows)] for _ in range(cols)]
            
            speed = 1.0 + 3.0 * audio_feats.get('percussive', 0.5)
            if is_beat:
                speed += 5.0 * beat_energy
                
            dt = 0.05
            for col in range(cols):
                self._matrix_streams[col] += speed * dt
                if self._matrix_streams[col] >= rows:
                    self._matrix_streams[col] = self.rng.randint(-20, 0)
                    self._matrix_chars[col] = [chr(self.rng.randint(33, 126)) for _ in range(rows)]
            
            matrix_overlay = np.zeros_like(img_np)
            for col in range(cols):
                pos = int(self._matrix_streams[col])
                if pos < 0: continue
                for r in range(max(0, pos - 15), min(rows, pos + 1)):
                    dist = pos - r
                    brightness = int(255 * (1.0 - dist / 15.0))
                    if brightness <= 0: continue
                    
                    char = self._matrix_chars[col][r]
                    x = col * cell_w + cell_w // 2
                    y = r * cell_h + cell_h
                    
                    if dist == 0:
                        color = (200, 255, 200)
                    else:
                        color = (0, brightness, 0)
                        
                    cv2.putText(matrix_overlay, char, (x, y), cv2.FONT_HERSHEY_PLAIN, 0.8, color, 1, cv2.LINE_AA)
                   
            if variant == 0:
                out = cv2.addWeighted(img_np, 1.0, matrix_overlay, intensity, 0)
            elif variant == 1:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                gray_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
                dark_bg = (gray_rgb * 0.25).astype(np.uint8)
                out = cv2.add(dark_bg, matrix_overlay)
                out = cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
            else:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                binary_edges = cv2.Canny(gray, 50, 150)
                binary_edges_rgb = cv2.cvtColor(binary_edges, cv2.COLOR_GRAY2RGB)
                binary_edges_rgb[:, :, 0] = 0
                binary_edges_rgb[:, :, 2] = 0
                out = cv2.add(binary_edges_rgb, matrix_overlay)
                out = cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
               
            return out
        except Exception as e:
            logger.error(f"Matrix ASCII error: {e}")
            return img_np

    def apply_reaction_diffusion_custom(self, img_np, t, intensity, audio_feats, is_beat, beat_energy, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            scale = 0.25
            small = cv2.resize(img_np, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
            
            if len(self.time_displacement_buffer.buffer) >= 3:
                past = cv2.resize(self.time_displacement_buffer.buffer[-2], (small.shape[1], small.shape[0]), interpolation=cv2.INTER_LINEAR)
            else:
                past = small.copy()
               
            diff = cv2.absdiff(small, past)
            blurred_diff = cv2.GaussianBlur(diff, (5, 5), 0)
            
            sub_bass = audio_feats.get('sub_bass', 0.5)
            feed = 0.0545 + 0.01 * sub_bass
            
            pattern = cv2.addWeighted(small, 1.0 - feed, blurred_diff, feed * 20.0, 0)
            pattern = cv2.threshold(pattern, 100 + int(20 * sub_bass), 255, cv2.THRESH_BINARY)[1]
            
            chord_hue = audio_feats.get('chord_hue', 120.0)
            r_c, g_c, b_c = self._hue_to_rgb(chord_hue)
            color_pattern = np.zeros_like(pattern)
            color_pattern[:, :] = [r_c, g_c, b_c]
            color_pattern = cv2.bitwise_and(color_pattern, pattern)
            
            res_proc = cv2.resize(color_pattern, (w, h), interpolation=cv2.INTER_LINEAR)
            
            if variant == 0:
                out = cv2.addWeighted(img_np, 1.0 - 0.5 * intensity, res_proc, 0.5 * intensity, 0)
            elif variant == 1:
                gray_pattern = cv2.cvtColor(res_proc, cv2.COLOR_RGB2GRAY)
                dx, dy = cv2.spatialGradient(gray_pattern)
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                map_x = np.clip(x + dx * 0.2 * intensity * beat_energy, 0, w - 1)
                map_y = np.clip(y + dy * 0.2 * intensity * beat_energy, 0, h - 1)
                out = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            else:
                out = img_np.copy()
                buf_len = len(self.time_displacement_buffer.buffer)
                if buf_len >= 8:
                    slice_h = h // 8
                    for i in range(8):
                        buf_idx = max(0, buf_len - 1 - i)
                        frame_slice = self.time_displacement_buffer.buffer[buf_idx]
                        y_start = i * slice_h
                        y_end = (i + 1) * slice_h if i < 7 else h
                        out[y_start:y_end, :, :] = frame_slice[y_start:y_end, :, :]
                out = cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
               
            return out
        except Exception as e:
            logger.error(f"Reaction Diffusion error: {e}")
            return img_np

    # ═══════════════════════════════════════════════════════════
    # 自訂擴充後製特效 (8大新增濾鏡)
    # ═══════════════════════════════════════════════════════════

    # 1. 熱成像 (Thermal Vision) 3變種
    def apply_thermal_custom(self, img_np, intensity, sub_bass, percussive, chord_hue, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = (img_np[:, :, 0] * 0.299 + img_np[:, :, 1] * 0.587 + img_np[:, :, 2] * 0.114).astype(np.uint8)
            
            if variant == 0:
                # Predator 鐵血戰士霓虹邊緣
                thermal = cv2.applyColorMap(gray, cv2.COLORMAP_JET)
                edges = cv2.Canny(gray, 40, 120)
                r_c, g_c, b_c = self._hue_to_rgb(chord_hue)
                edge_img = np.zeros_like(img_np)
                edge_img[edges > 0] = [r_c, g_c, b_c]
                edge_glow = cv2.GaussianBlur(edge_img, (5, 5), 0)
                edge_img = cv2.addWeighted(edge_img, 0.6, edge_glow, 0.4, 0)
                
                combined = cv2.addWeighted(thermal, 1.0, edge_img, 0.7 * intensity * percussive, 0)
                return cv2.addWeighted(img_np, 1.0 - intensity, combined, intensity, 0)
                
            elif variant == 1:
                # 頻譜自適應熱區
                lut = np.zeros((256, 1, 3), dtype=np.uint8)
                bass_shift = int(sub_bass * 50)
                for i in range(256):
                    if i < 80 - bass_shift:
                        lut[i, 0] = [120 + i, 0, 0]
                    elif i < 180:
                        lut[i, 0] = [0, 100 + (i-80), 0]
                    else:
                        lut[i, 0] = [0, 0, 150 + (i-180)]
                mapped = cv2.LUT(cv2.merge([gray, gray, gray]), lut)
                return cv2.addWeighted(img_np, 1.0 - intensity, mapped, intensity, 0)
                
            else:
                # 動態熱浪消融
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                t_val = self.last_t
                noise_x = np.sin(y * 0.05 + 1.2 * sub_bass + t_val) * 8.0 * intensity
                noise_y = np.cos(x * 0.05 + sub_bass + t_val) * 8.0 * intensity
                map_x = np.clip(x + noise_x, 0, w - 1)
                map_y = np.clip(y + noise_y, 0, h - 1)
                distorted = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                
                dist_gray = (distorted[:, :, 0] * 0.299 + distorted[:, :, 1] * 0.587 + distorted[:, :, 2] * 0.114).astype(np.uint8)
                thermal = cv2.applyColorMap(dist_gray, cv2.COLORMAP_JET)
                return cv2.addWeighted(img_np, 1.0 - intensity, thermal, intensity, 0)
        except Exception as e:
            logger.error(f"Thermal Vision error: {e}")
            return img_np

    # 2. 掃描故障 (Scanline Glitch) 3變種
    def apply_scanline_glitch_custom(self, img_np, intensity, sub_bass, roughness, is_beat, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            out = img_np.copy()
            t_val = self.last_t
            
            if variant == 0:
                # VHS 追軌同步漂移
                num_slices = int(3 + 5 * intensity)
                for _ in range(num_slices):
                    y_pos = random.randint(0, h - 30)
                    h_slice = random.randint(10, 40)
                    shift = int((random.randint(-50, 50) + (100 if is_beat else 0)) * intensity)
                    out[y_pos:y_pos+h_slice, :, :] = np.roll(out[y_pos:y_pos+h_slice, :, :], shift, axis=1)
                for _ in range(int(2 * intensity)):
                    y_noise = random.randint(0, h - 4)
                    out[y_noise:y_noise+2, :, :] = 200 + random.randint(0, 55)
                return out
                
            elif variant == 1:
                # 光譜色差故障掃描線
                for _ in range(int(2 + 4 * intensity)):
                    y_start = random.randint(0, h - 60)
                    h_band = random.randint(15, 60)
                    shift = int(25 * intensity)
                    if shift > 0:
                        band = out[y_start:y_start+h_band, :, :]
                        band_r = np.roll(band[:, :, 0], shift, axis=1)
                        band_b = np.roll(band[:, :, 2], -shift, axis=1)
                        out[y_start:y_start+h_band, :, 0] = band_r
                        out[y_start:y_start+h_band, :, 2] = band_b
                return out
                
            else:
                # 模擬訊號丟失
                shift_y = int((sub_bass * 0.3 + roughness * 0.7) * h * intensity)
                if shift_y > 5:
                    out = np.roll(out, shift_y, axis=0)
                for y in range(0, h, max(4, int(16 - 12 * intensity))):
                    if random.random() < (0.2 + 0.3 * roughness):
                        shift_x = int(random.randint(-15, 15) * intensity)
                        out[y:y+2, :, :] = np.roll(out[y:y+2, :, :], shift_x, axis=1)
                return out
        except Exception as e:
            logger.error(f"Scanline Glitch error: {e}")
            return img_np

    # 3. 掉幀 (Frame Drop) 3變種
    def apply_frame_drop_custom(self, img_np, intensity, arousal, beat_phase, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            curr_t = self.last_t
            
            if not hasattr(self, '_frame_drop_cache') or self._frame_drop_cache is None or self._frame_drop_cache.shape != img_np.shape:
                self._frame_drop_cache = img_np.copy()
                self._frame_drop_last_t = curr_t
                return img_np

            if variant == 0:
                # 動態定格動畫
                threshold_interval = 0.033 + 0.13 * (1.0 - arousal)
                if curr_t - self._frame_drop_last_t >= threshold_interval:
                    self._frame_drop_cache = img_np.copy()
                    self._frame_drop_last_t = curr_t
                return cv2.addWeighted(img_np, 1.0 - intensity, self._frame_drop_cache, intensity, 0)
                
            elif variant == 1:
                # 量化節奏定格
                quantized_gate = int(beat_phase * 8) % 2 == 0
                if quantized_gate or (curr_t - self._frame_drop_last_t > 0.3):
                    self._frame_drop_cache = img_np.copy()
                    self._frame_drop_last_t = curr_t
                return cv2.addWeighted(img_np, 1.0 - intensity, self._frame_drop_cache, intensity, 0)
                
            else:
                # 殘影殘像
                is_new_beat = (beat_phase < 0.08)
                if is_new_beat:
                    self._frame_drop_cache = img_np.copy()
                    self._frame_drop_last_t = curr_t
                
                blend_amt = intensity * max(0.1, 1.0 - beat_phase)
                return cv2.addWeighted(img_np, 1.0 - blend_amt, self._frame_drop_cache, blend_amt, 0)
        except Exception as e:
            logger.error(f"Frame Drop error: {e}")
            return img_np

    # 4. 動態馬賽克 (Dynamic Mosaic) 3變種
    def apply_dynamic_mosaic_custom(self, img_np, intensity, sub_bass, chord_brightness, roughness, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            
            if variant == 0:
                # 低音爆裂馬賽克
                block_size = int(6 + 50 * intensity * sub_bass)
                if block_size < 4: block_size = 4
                small = cv2.resize(img_np, (w // block_size, h // block_size), interpolation=cv2.INTER_LINEAR)
                mosaic = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                return cv2.addWeighted(img_np, 1.0 - intensity, mosaic, intensity, 0)
                
            elif variant == 1:
                # 旋轉斜切馬賽克
                angle = float(chord_brightness * 45.0 * intensity)
                if abs(angle) < 1.0: angle = 1.0
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                
                block_size = max(4, int(12 + 16 * intensity))
                small = cv2.resize(rotated, (w // block_size, h // block_size), interpolation=cv2.INTER_LINEAR)
                mosaic_rot = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                
                M_inv = cv2.getRotationMatrix2D(center, -angle, 1.0)
                restored = cv2.warpAffine(mosaic_rot, M_inv, (w, h), borderMode=cv2.BORDER_REFLECT)
                return cv2.addWeighted(img_np, 1.0 - intensity, restored, intensity, 0)
                
            else:
                # 漂移碎裂塊
                block_size = max(6, int(16 + 24 * intensity))
                sh, sw = h // block_size, w // block_size
                if sh < 2 or sw < 2: return img_np
                
                small = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
                if roughness > 0.3:
                    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
                    hsv[:, :, 0] = (hsv[:, :, 0].astype(np.int16) + int(roughness * 30 * intensity)) % 180
                    small = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
                
                out = img_np.copy()
                drift_range = int(10 * intensity * roughness)
                for y in range(sh):
                    for x in range(sw):
                        dx = random.randint(-drift_range, drift_range) if drift_range > 0 else 0
                        dy = random.randint(-drift_range, drift_range) if drift_range > 0 else 0
                        px_src = x * block_size
                        py_src = y * block_size
                        px_dst = np.clip(px_src + dx, 0, w - block_size)
                        py_dst = np.clip(py_src + dy, 0, h - block_size)
                        color = small[y, x]
                        out[py_dst:py_dst+block_size, px_dst:px_dst+block_size] = color
                return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
        except Exception as e:
            logger.error(f"Dynamic Mosaic error: {e}")
            return img_np

    # 5. 像素畫 (Pixel Art) 3變種
    def apply_pixel_art_custom(self, img_np, intensity, sub_bass, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            factor = max(4, int(16 - 10 * intensity))
            small = cv2.resize(img_np, (w // factor, h // factor), interpolation=cv2.INTER_LINEAR)
            sh, sw = small.shape[:2]
            
            if variant == 0:
                # GameBoy 復古液晶
                gray_small = (small[:, :, 0] * 0.299 + small[:, :, 1] * 0.587 + small[:, :, 2] * 0.114).astype(np.uint8)
                gb_palette = np.array([
                    [15, 56, 15],
                    [48, 98, 48],
                    [15, 172, 139],
                    [15, 188, 155]
                ], dtype=np.uint8)
                
                gb_img = np.zeros_like(small)
                for y in range(sh):
                    for x in range(sw):
                        val = gray_small[y, x]
                        idx = min(3, val // 64)
                        gb_img[y, x] = gb_palette[idx]
                
                restored = cv2.resize(gb_img, (w, h), interpolation=cv2.INTER_NEAREST)
                if factor > 6:
                    y_grid, x_grid = np.mgrid[0:h, 0:w]
                    mask = (y_grid % factor == 0) | (x_grid % factor == 0)
                    restored[mask] = (restored[mask].astype(np.uint16) * 7 // 10).astype(np.uint8)
                    
                return cv2.addWeighted(img_np, 1.0 - intensity, restored, intensity, 0)
                
            elif variant == 1:
                # 漫畫風格像素勾邊
                div = 64
                quant = (small // div) * div + div // 2
                quant = np.clip(quant, 0, 255).astype(np.uint8)
                
                gray_small = cv2.cvtColor(quant, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray_small, 30, 90)
                
                quant_big = cv2.resize(quant, (w, h), interpolation=cv2.INTER_NEAREST)
                edges_big = cv2.resize(edges, (w, h), interpolation=cv2.INTER_NEAREST)
                quant_big[edges_big > 0] = [0, 0, 0]
                return cv2.addWeighted(img_np, 1.0 - intensity, quant_big, intensity, 0)
                
            elif variant == 2:
                # 霓虹賽博朋克像素
                div = 85
                quant = (small // div) * div
                cym = np.zeros_like(quant)
                cym[:, :, 0] = np.where(quant[:, :, 0] > 120, 255, 0)
                cym[:, :, 1] = np.where(quant[:, :, 1] > 120, 255, 0)
                cym[:, :, 2] = np.where(quant[:, :, 2] > 120, 255, 0)
                restored = cv2.resize(cym, (w, h), interpolation=cv2.INTER_NEAREST)
                return cv2.addWeighted(img_np, 1.0 - intensity, restored, intensity, 0)
                
            elif variant == 3:
                # 復古 8-bit NES 經典色彩像素化
                nes_palette = np.array([
                    [240, 240, 240], [0, 120, 248], [0, 0, 252], [104, 0, 252],
                    [216, 0, 204], [228, 0, 88], [248, 120, 88], [228, 88, 16],
                    [200, 110, 0], [0, 168, 0], [0, 144, 0], [0, 136, 136],
                    [0, 0, 0], [255, 255, 0], [255, 0, 255]
                ], dtype=np.uint8)
                nes_img = np.zeros_like(small)
                for y in range(sh):
                    for x in range(sw):
                        color = small[y, x]
                        dists = np.sum((nes_palette.astype(np.int32) - color.astype(np.int32))**2, axis=1)
                        nes_img[y, x] = nes_palette[np.argmin(dists)]
                restored = cv2.resize(nes_img, (w, h), interpolation=cv2.INTER_NEAREST)
                return cv2.addWeighted(img_np, 1.0 - intensity, restored, intensity, 0)
                
            else:
                # 懷舊黑白/綠色磷光 CRT 像素 (Monochrome Green CRT)
                gray_small = (small[:, :, 0] * 0.299 + small[:, :, 1] * 0.587 + small[:, :, 2] * 0.114).astype(np.uint8)
                green_phosphor = np.zeros_like(small)
                green_phosphor[:, :, 1] = gray_small
                green_phosphor[:, :, 0] = (gray_small.astype(np.uint16) * 15 // 100).astype(np.uint8)
                green_phosphor[:, :, 2] = (gray_small.astype(np.uint16) * 10 // 100).astype(np.uint8)
                restored = cv2.resize(green_phosphor, (w, h), interpolation=cv2.INTER_NEAREST)
                
                # 疊加橫向掃描線
                y_grid, x_grid = np.mgrid[0:h, 0:w]
                mask = y_grid % factor == 0
                restored[mask] = 0
                return cv2.addWeighted(img_np, 1.0 - intensity, restored, intensity, 0)
        except Exception as e:
            logger.error(f"Pixel Art error: {e}")
            return img_np

    # 6. 手持相機 (Handheld Camera) 3變種
    def apply_handheld_camera_custom(self, img_np, t, intensity, roughness, arousal, is_beat, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            
            self._cam_drift_x += (math.sin(t * 1.5) * 4.0 + (random.uniform(-3, 3) if roughness > 0.4 else 0) - self._cam_drift_x) * 0.1
            self._cam_drift_y += (math.cos(t * 1.2) * 3.0 + (random.uniform(-3, 3) if roughness > 0.4 else 0) - self._cam_drift_y) * 0.1
            
            dx = int(self._cam_drift_x * intensity)
            dy = int(self._cam_drift_y * intensity)
            if is_beat:
                dx += int(random.randint(-15, 15) * intensity * arousal)
                dy += int(random.randint(-15, 15) * intensity * arousal)
                
            if variant == 0:
                # 有機呼吸漂移
                if abs(dx) > 0 or abs(dy) > 0:
                    shifted = ImageChops.offset(Image.fromarray(img_np), dx, dy)
                    return np.array(shifted)
                return img_np
                
            elif variant == 1:
                # CCTV / DV 錄影框資訊
                zoom = 1.0 + 0.03 * intensity * math.sin(t * 3.0)
                sw, sh = int(w * zoom), int(h * zoom)
                resized = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
                lx = (sw - w) // 2
                ly = (sh - h) // 2
                cropped = resized[ly:ly+h, lx:lx+w]
                if cropped.shape[:2] != (h, w):
                    cropped = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
                
                if roughness > 0.5:
                    cropped = cv2.GaussianBlur(cropped, (5, 5), 1.0)
                
                overlay = cropped.copy()
                rec_color = (255, 0, 0) if int(t * 2) % 2 == 0 else (100, 100, 100)
                cv2.circle(overlay, (80, 80), 10, rec_color, -1)
                cv2.putText(overlay, "REC", (105, 90), cv2.FONT_HERSHEY_DUPLEX, 0.8, (230, 230, 230), 2, cv2.LINE_AA)
                
                sec = int(t) % 60
                m_m = (int(t) // 60) % 60
                h_h = (int(t) // 3600) % 24
                time_str = f"{h_h:02d}:{m_m:02d}:{sec:02d}"
                cv2.putText(overlay, time_str, (80, h - 80), cv2.FONT_HERSHEY_PLAIN, 1.2, (220, 220, 220), 1, cv2.LINE_AA)
                
                line_color = (60, 60, 60)
                cv2.line(overlay, (w // 3, 0), (w // 3, h), line_color, 1)
                cv2.line(overlay, (2 * w // 3, 0), (2 * w // 3, h), line_color, 1)
                cv2.line(overlay, (0, h // 3), (w, h // 3), line_color, 1)
                cv2.line(overlay, (0, 2 * h // 3), (w, 2 * h // 3), line_color, 1)
                
                return cv2.addWeighted(img_np, 1.0 - intensity, overlay, intensity, 0)
                
            elif variant == 2:
                # 魚眼廣角 + 強烈震鏡
                k1 = -0.15 * intensity
                distorted = self.apply_barrel_distortion(img_np, k1, 0.0)
                dx_strong = int(dx * 2.5)
                dy_strong = int(dy * 2.5)
                if abs(dx_strong) > 0 or abs(dy_strong) > 0:
                    shifted = ImageChops.offset(Image.fromarray(distorted), dx_strong, dy_strong)
                    return np.array(shifted)
                return distorted
                
            elif variant == 3:
                # 錄影機自動對焦框 (AutoFocus View Finder)
                overlay = img_np.copy()
                cx, cy = w // 2, h // 2
                box_sz = int(80 + 30 * math.sin(t * 5.0))
                
                # 4 corners of focus box
                cv2.line(overlay, (cx - box_sz, cy - box_sz), (cx - box_sz + 20, cy - box_sz), (0, 255, 0), 2)
                cv2.line(overlay, (cx - box_sz, cy - box_sz), (cx - box_sz, cy - box_sz + 20), (0, 255, 0), 2)
                cv2.line(overlay, (cx + box_sz, cy - box_sz), (cx + box_sz - 20, cy - box_sz), (0, 255, 0), 2)
                cv2.line(overlay, (cx + box_sz, cy - box_sz), (cx + box_sz, cy - box_sz + 20), (0, 255, 0), 2)
                cv2.line(overlay, (cx - box_sz, cy + box_sz), (cx - box_sz + 20, cy + box_sz), (0, 255, 0), 2)
                cv2.line(overlay, (cx - box_sz, cy + box_sz), (cx - box_sz, cy + box_sz - 20), (0, 255, 0), 2)
                cv2.line(overlay, (cx + box_sz, cy + box_sz), (cx + box_sz - 20, cy + box_sz), (0, 255, 0), 2)
                cv2.line(overlay, (cx + box_sz, cy + box_sz), (cx + box_sz, cy + box_sz - 20), (0, 255, 0), 2)
                
                # Blinking green dot in center
                dot_color = (0, 255, 0) if int(t * 3) % 2 == 0 else (0, 80, 0)
                cv2.circle(overlay, (cx, cy), 4, dot_color, -1)
                
                # AF status text
                cv2.putText(overlay, "AF-C", (cx - 30, cy + box_sz + 30), cv2.FONT_HERSHEY_DUPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
                
                # Apply organic drift on top of autofocus overlay
                if abs(dx) > 0 or abs(dy) > 0:
                    overlay = np.array(ImageChops.offset(Image.fromarray(overlay), dx, dy))
                return cv2.addWeighted(img_np, 1.0 - intensity, overlay, intensity, 0)
                
            else:
                # 電影級 2.35:1 遮幅漂移與鏡頭傾角 (Cinematic Crop & Roll)
                angle = 1.6 * intensity * math.sin(t * 0.8)  # 鏡頭傾斜角度
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.02)  # 微幅放大防黑邊
                rotated = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                
                # 相機抖動
                if abs(dx) > 0 or abs(dy) > 0:
                    rotated = np.array(ImageChops.offset(Image.fromarray(rotated), dx, dy))
                
                # 疊加電影遮幅
                bar_h = int(h * 0.12)
                rotated[0:bar_h, :, :] = 0
                rotated[h-bar_h:h, :, :] = 0
                return cv2.addWeighted(img_np, 1.0 - intensity, rotated, intensity, 0)
        except Exception as e:
            logger.error(f"Handheld Camera error: {e}")
            return img_np

    # 7. 藝術淡入淡出 (Stylized Fade) 3變種
    def apply_stylized_fade_custom(self, img_np, intensity, silence_fade, variant):
        fade_amt = max(intensity, silence_fade)
        if fade_amt < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            
            if variant == 0:
                # 噪訊腐蝕沙化溶解
                if not hasattr(self, '_fade_noise_mask') or self._fade_noise_mask is None or self._fade_noise_mask.shape != (h, w):
                    self._fade_noise_mask = np.random.randint(0, 255, (h, w), dtype=np.uint8)
                
                threshold = int(fade_amt * 255)
                mask = self._fade_noise_mask > threshold
                
                out = img_np.copy()
                out[~mask] = [0, 0, 0]
                return out
                
            elif variant == 1:
                # 放射狀快門光圈
                center = (w // 2, h // 2)
                max_radius = int(math.sqrt(w*w + h*h) // 2)
                radius = int(max_radius * (1.0 - fade_amt))
                
                mask = np.zeros((h, w), dtype=np.uint8)
                if radius > 0:
                    cv2.circle(mask, center, radius, 255, -1)
                
                out = cv2.bitwise_and(img_np, img_np, mask=mask)
                return out
                
            else:
                # 光譜垂直融化
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                if not hasattr(self, '_melt_offsets') or self._melt_offsets is None or self._melt_offsets.shape[0] != w:
                    self._melt_offsets = np.random.uniform(0.1, 1.0, (w,)).astype(np.float32)
                
                offset_y = y - (self._melt_offsets[np.newaxis, :] * h * fade_amt * 1.5)
                map_y = np.clip(offset_y, 0, h - 1)
                melted = cv2.remap(img_np, x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                
                return cv2.addWeighted(melted, 1.0 - fade_amt, np.zeros_like(img_np), fade_amt, 0)
        except Exception as e:
            logger.error(f"Stylized Fade error: {e}")
            return img_np

    # 8. 縮放脈衝 (Zoom Pulse) 3變種
    def apply_zoom_pulse_custom(self, img_np, intensity, sub_bass, t, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            
            if variant == 0:
                # 低音砸拍縮放
                zoom = 1.0 + 0.15 * intensity * sub_bass
                sw, sh = int(w * zoom), int(h * zoom)
                resized = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
                lx = (sw - w) // 2
                ly = (sh - h) // 2
                cropped = resized[ly:ly+h, lx:lx+w]
                if cropped.shape[:2] != (h, w):
                    cropped = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
                return cropped
                
            elif variant == 1:
                # 旋轉縮放無限隧道
                if len(self.time_displacement_buffer.buffer) >= 3:
                    past = self.time_displacement_buffer.buffer[-2]
                else:
                    past = img_np.copy()
                
                zoom = 1.02 + 0.05 * intensity
                angle = 2.0 * intensity
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, zoom)
                warped_past = cv2.warpAffine(past, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                
                return cv2.addWeighted(img_np, 1.0 - 0.4 * intensity, warped_past, 0.4 * intensity, 0)
                
            else:
                # R/G/B 通道分離三維縮放
                zoom_r = 1.0 + 0.08 * intensity
                zoom_g = 1.0 + 0.04 * intensity
                zoom_b = 1.0
                
                out = img_np.copy()
                for ch_idx, zoom in enumerate([zoom_r, zoom_g, zoom_b]):
                    if zoom == 1.0: continue
                    sw, sh = int(w * zoom), int(h * zoom)
                    resized = cv2.resize(img_np[:, :, ch_idx], (sw, sh), interpolation=cv2.INTER_LINEAR)
                    lx = (sw - w) // 2
                    ly = (sh - h) // 2
                    cropped = resized[ly:ly+h, lx:lx+w]
                    if cropped.shape[:2] == (h, w):
                        out[:, :, ch_idx] = cropped
                return out
        except Exception as e:
            logger.error(f"Zoom Pulse error: {e}")
            return img_np

    # ════════════════════════════════════════════════════════════════
    # 10. 影印機掃描器拖移故障 (Photocopy Smear) 5變種
    # ════════════════════════════════════════════════════════════════
    def apply_photocopy_smear_custom(self, img_np, t, intensity, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            out = img_np.copy()
            
            # Update scanner position
            dt = t - getattr(self, '_scanner_last_t', t - 1.0/30.0)
            self._scanner_last_t = t
            if dt <= 0 or dt > 0.2: dt = 1.0 / 30.0
            
            speed = 220.0 * (1.0 + intensity)
            self.scanner_y = (self.scanner_y + speed * dt) % h
            self.scanner_x = (self.scanner_x + speed * dt) % w
            
            scan_y = int(self.scanner_y)
            scan_x = int(self.scanner_x)
            
            if variant == 0:
                # 橫向向下拖移故障 (Horizontal Smear Down)
                smear_h = int(180 * intensity)
                if smear_h > 0:
                    row = img_np[scan_y, :, :]
                    out[scan_y:min(h, scan_y + smear_h), :, :] = row
                    
                # 掃描器亮線 (Glow line)
                if 0 <= scan_y < h:
                    out[scan_y:min(h, scan_y+3), :, :] = np.clip(out[scan_y:min(h, scan_y+3), :, :].astype(np.int16) + 120, 0, 255).astype(np.uint8)
                    
            elif variant == 1:
                # 縱向向右拖移故障 (Vertical Smear Right)
                smear_w = int(240 * intensity)
                if smear_w > 0:
                    col = img_np[:, scan_x, :]
                    for dx in range(smear_w):
                        out[:, min(w - 1, scan_x + dx), :] = col
                        
                # 縱向亮線
                if 0 <= scan_x < w:
                    out[:, scan_x:min(w, scan_x+3), :] = np.clip(out[:, scan_x:min(w, scan_x+3), :].astype(np.int16) + 120, 0, 255).astype(np.uint8)
                    
            elif variant == 2:
                # 雙向十字掃描拖移 (Cross Smear)
                smear_h = int(100 * intensity)
                smear_w = int(120 * intensity)
                
                # 橫向拖移
                row = img_np[scan_y, :, :]
                out[scan_y:min(h, scan_y + smear_h), :, :] = row
                
                # 縱向拖移
                col = img_np[:, scan_x, :]
                for dx in range(smear_w):
                    out[:, min(w - 1, scan_x + dx), :] = col
                    
            elif variant == 3:
                # 隨機拍點行凍結 (Glitchy Beat Smear)
                if not hasattr(self, '_scanner_frozen_rows'):
                    self._scanner_frozen_rows = []
                
                # On beat, select 2 random rows to freeze and smear
                if int(t * 10) % 3 == 0:
                    self._scanner_frozen_rows = []
                    for _ in range(self.rng.randint(2, 4)):
                        self._scanner_frozen_rows.append((self.rng.randint(0, h - 30), self.rng.randint(10, int(80 * intensity) + 10)))
                
                for start_y, height_smear in self._scanner_frozen_rows:
                    if start_y < h:
                        row = img_np[start_y, :, :]
                        out[start_y:min(h, start_y + height_smear), :, :] = row
                        
            else:
                # 掃描器 RGB 色彩分離拖移 (RGB Split Smear)
                smear_h = int(150 * intensity)
                row_r = img_np[scan_y, :, 0]
                row_g = img_np[(scan_y + 30) % h, :, 1]
                row_b = img_np[(scan_y + 60) % h, :, 2]
                
                out[scan_y:min(h, scan_y + smear_h), :, 0] = row_r
                out[((scan_y + 30) % h):min(h, ((scan_y + 30) % h) + smear_h), :, 1] = row_g
                out[((scan_y + 60) % h):min(h, ((scan_y + 60) % h) + smear_h), :, 2] = row_b
                
            return out
        except Exception as e:
            logger.error(f"Photocopy Smear error: {e}")
            return img_np

    # ════════════════════════════════════════════════════════════════
    # 11. 創意拼貼濾鏡 (Collage Cutout) 5變種
    # ════════════════════════════════════════════════════════════════
    def apply_collage_cutout_custom(self, img_np, intensity, variant):
        if intensity < 0.01: return img_np
        try:
            h, w = img_np.shape[:2]
            out = img_np.copy()
            
            # We need past frames in the displacement buffer
            buf = self.time_displacement_buffer.buffer
            if len(buf) < 5 or cv2 is None:
                return img_np
                
            if variant == 0:
                # 經典報紙剪貼風格 (Classic Paper Cutouts)
                num_pieces = int(3 * intensity) + 1
                for _ in range(num_pieces):
                    past_img = self.rng.choice(buf)
                    pw = self.rng.randint(int(w * 0.18), int(w * 0.38))
                    ph = self.rng.randint(int(h * 0.18), int(h * 0.38))
                    
                    src_x = self.rng.randint(0, w - pw)
                    src_y = self.rng.randint(0, h - ph)
                    dst_x = self.rng.randint(0, w - pw)
                    dst_y = self.rng.randint(0, h - ph)
                    
                    patch = past_img[src_y:src_y+ph, src_x:src_x+pw].copy()
                    
                    # Add warm paper margin
                    border = max(2, int(w * 0.006))
                    cv2.copyMakeBorder(patch, border, border, border, border, cv2.BORDER_CONSTANT, value=(245, 243, 235))
                    
                    bpw, bph = pw + 2*border, ph + 2*border
                    ex = min(w, dst_x + bpw)
                    ey = min(h, dst_y + bph)
                    
                    patch_resized = cv2.resize(patch, (ex - dst_x, ey - dst_y))
                    out[dst_y:ey, dst_x:ex] = patch_resized
                    
            elif variant == 1:
                # 2x2 波普藝術格拼貼 (2x2 Pop-Art Grid Split)
                q_w, q_h = w // 2, h // 2
                idx1 = min(len(buf) - 1, 5)
                idx2 = min(len(buf) - 1, 15)
                idx3 = min(len(buf) - 1, 25)
                
                out[0:q_h, q_w:w] = buf[-idx1-1][0:q_h, q_w:w]
                out[q_h:h, 0:q_w] = buf[-idx2-1][q_h:h, 0:q_w]
                out[q_h:h, q_w:w] = buf[-idx3-1][q_h:h, q_w:w]
                
                # Add thick white margins
                border_color = (250, 248, 240)
                thickness = max(2, int(w * 0.008))
                cv2.line(out, (q_w, 0), (q_w, h), border_color, thickness)
                cv2.line(out, (0, q_h), (w, q_h), border_color, thickness)
                
            elif variant == 2:
                # 撕裂紙條拼貼 (Torn Paper Strips)
                num_strips = int(2 * intensity) + 1
                for _ in range(num_strips):
                    past_img = self.rng.choice(buf)
                    
                    strip_h = self.rng.randint(int(h * 0.08), int(h * 0.22))
                    src_y = self.rng.randint(0, h - strip_h)
                    dst_y = self.rng.randint(0, h - strip_h) if h - strip_h > 0 else 0
                    
                    strip = past_img[src_y:src_y+strip_h, :, :].copy()
                    
                    border = max(1, int(h * 0.005))
                    cv2.copyMakeBorder(strip, border, border, 0, 0, cv2.BORDER_CONSTANT, value=(245, 245, 240))
                    
                    ey = min(h, dst_y + strip_h + 2*border)
                    strip_resized = cv2.resize(strip, (w, ey - dst_y))
                    out[dst_y:ey, :, :] = strip_resized
                    
            elif variant == 3:
                # 偏心圓環切片拼貼 (Circular Lens Collage)
                past_img = self.rng.choice(buf)
                mask = np.zeros((h, w), dtype=np.uint8)
                
                for _ in range(self.rng.randint(2, 3)):
                    cx = self.rng.randint(int(w * 0.2), int(w * 0.8))
                    cy = self.rng.randint(int(h * 0.2), int(h * 0.8))
                    r = self.rng.randint(int(w * 0.1), int(w * 0.25))
                    cv2.circle(mask, (cx, cy), r, 255, -1)
                    cv2.circle(out, (cx, cy), r, (245, 243, 235), max(2, int(w * 0.004)))
                    
                idx = np.where(mask > 0)
                out[idx] = past_img[idx]
                
            else:
                # 動態時間壁畫 (Multi-Split Wall)
                col_w = w // 3
                idx_left = min(len(buf) - 1, 20)
                idx_right = min(len(buf) - 1, 10)
                
                out[:, 0:col_w] = buf[-idx_left-1][:, 0:col_w]
                out[:, 2*col_w:w] = buf[-idx_right-1][:, 2*col_w:w]
                
                border_color = (245, 243, 235)
                thickness = max(2, int(w * 0.005))
                cv2.line(out, (col_w, 0), (col_w, h), border_color, thickness)
                cv2.line(out, (2*col_w, 0), (2*col_w, h), border_color, thickness)
                
            return out
        except Exception as e:
            logger.error(f"Collage Cutout error: {e}")
            return img_np

    # ════════════════════════════════════════════════════════════════
    # 全新維度全域後製特效矩陣 (Global Post-FX Matrix 8 大頂級特效演算法)
    # ════════════════════════════════════════════════════════════════

    # 2.1 膠片燒灼與化學腐蝕 (Film Burn & Chemical Bleed) 5 變種
    def apply_film_burn_custom(self, img_np, t, intensity, sub_bass, roughness, is_beat, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            out = img_np.copy()
            
            # 高光遮罩
            _, high_mask = cv2.threshold(gray, 185, 255, cv2.THRESH_BINARY)
            
            # 邊緣燒灼擴散圖騰
            y_indices, x_indices = np.mgrid[0:h, 0:w]
            dist_edge = np.minimum(np.minimum(x_indices, w - 1 - x_indices),
                                   np.minimum(y_indices, h - 1 - y_indices)).astype(np.float32)
            edge_norm = 1.0 - np.clip(dist_edge / (min(w, h) * 0.35 * (1.0 + sub_bass)), 0.0, 1.0)
            
            burn_noise = np.sin(x_indices * 0.03 + t * 4.0) * np.cos(y_indices * 0.03 - t * 3.0) * 0.5 + 0.5
            burn_mask = np.clip(edge_norm * 1.2 + burn_noise * 0.3 * sub_bass, 0.0, 1.0) * intensity

            if variant == 0:
                # 35mm 暖色硝酸高光漏光 (Warm Amber Leak)
                burn_color = np.array([245, 120, 25], dtype=np.float32)
                boost = (high_mask.astype(np.float32) / 255.0)[:, :, None] * 1.5 * intensity
                burned = out.astype(np.float32) * (1.0 + burn_mask[:, :, None] * 0.6) + burn_color * burn_mask[:, :, None] * 0.8 + boost * 50.0
                out = np.clip(burned, 0, 255).astype(np.uint8)
                
            elif variant == 1:
                # 鹼蝕反轉邊緣 (Chemical Bleed Acid Wash)
                acid_color = np.array([20, 230, 180], dtype=np.float32)
                inv = 255 - out
                out = cv2.addWeighted(out, 1.0 - burn_mask.mean(), inv, burn_mask.mean() * intensity, 0)
                out = cv2.addWeighted(out, 0.8, (acid_color * burn_mask[:, :, None]).astype(np.uint8), 0.5 * intensity, 0)
                
            elif variant == 2:
                # 放映機光門過熱消融 (Projector Gate Melt)
                cx, cy = w // 2, h // 2
                dist_center = np.sqrt((x_indices - cx)**2 + (y_indices - cy)**2) / (min(w, h) * 0.5)
                center_burn = np.clip(1.0 - dist_center + sub_bass * 0.4, 0.0, 1.0) * intensity
                overexp = np.clip(out.astype(np.float32) * (1.0 + center_burn[:, :, None] * 2.0), 0, 255).astype(np.uint8)
                out = cv2.addWeighted(out, 1.0 - center_burn.mean(), overexp, center_burn.mean(), 0)
                
            elif variant == 3:
                # 側邊膠片齒孔漏光 (Super 8 Edge Sprocket Burn)
                sprocket_mask = np.zeros((h, w), dtype=np.float32)
                sprocket_mask[:, :int(w * 0.12)] = 1.0
                sprocket_mask[:, int(w * 0.88):] = 1.0
                leak_pulse = (np.sin(t * 12.0) * 0.5 + 0.5) * intensity
                out = cv2.addWeighted(out, 1.0, (np.ones_like(out) * np.array([255, 140, 40], dtype=np.uint8)), sprocket_mask.mean() * leak_pulse * 0.7, 0)
                
            else:
                # 硝酸銀極限曝光對比 (Solarized Nitrate Flare)
                solarized = np.where(out > 128, 255 - out, out * 2)
                out = cv2.addWeighted(out, 1.0 - intensity * 0.7, solarized, intensity * 0.7, 0)

            # 正拍底片跳齒與閃白漏光
            if is_beat and (sub_bass > 0.6 or roughness > 0.5):
                shift_y = int(h * 0.04 * (1.0 if t % 2 > 1 else -1.0))
                out = np.roll(out, shift_y, axis=0)
                flash = np.full_like(out, (255, 240, 210), dtype=np.uint8)
                out = cv2.addWeighted(out, 0.75, flash, 0.25 * intensity, 0)
                
            return out
        except Exception as e:
            logger.error(f"Film Burn error: {e}")
            return img_np

    # 2.2 建築藍圖與 CAD 線稿 (Cyanotype & Architectural Blueprint) 5 變種
    def apply_blueprint_edge_custom(self, img_np, intensity, harmonic, roughness, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            
            # 精細 Canny 邊緣提取 (由 harmonic 調製線條精細度)
            t1 = int(30 + 40 * (1.0 - harmonic))
            t2 = int(100 + 80 * harmonic)
            edges = cv2.Canny(gray, t1, t2)
            
            out = img_np.copy()
            
            if variant == 0:
                # 普魯士日光藍印 (Prussian Cyanotype Classic)
                bg = np.full((h, w, 3), [10, 35, 90], dtype=np.uint8)
                edge_img = np.full((h, w, 3), [210, 240, 255], dtype=np.uint8)
                blueprint = np.where(edges[:, :, None] > 0, edge_img, bg)
                out = cv2.addWeighted(out, 1.0 - intensity, blueprint, intensity, 0)
                
            elif variant == 1:
                # 漆黑科技 CAD 線稿 (Dark Mode CAD Wireframe)
                bg = np.full((h, w, 3), [15, 18, 24], dtype=np.uint8)
                edge_img = np.full((h, w, 3), [0, 240, 200], dtype=np.uint8)
                blueprint = np.where(edges[:, :, None] > 0, edge_img, bg)
                out = cv2.addWeighted(out, 1.0 - intensity, blueprint, intensity, 0)
                
            elif variant == 2:
                # 羊皮紙工程草圖 (Parchment Engineering Draft)
                bg = np.full((h, w, 3), [230, 215, 180], dtype=np.uint8)
                edge_img = np.full((h, w, 3), [60, 40, 20], dtype=np.uint8)
                blueprint = np.where(edges[:, :, None] > 0, edge_img, bg)
                out = cv2.addWeighted(out, 1.0 - intensity, blueprint, intensity, 0)
                
            elif variant == 3:
                # 全息霓虹網格 (Holographic Neon Grid)
                bg = np.full((h, w, 3), [40, 10, 50], dtype=np.uint8)
                edge_img = np.full((h, w, 3), [50, 250, 240], dtype=np.uint8)
                blueprint = np.where(edges[:, :, None] > 0, edge_img, bg)
                out = cv2.addWeighted(out, 1.0 - intensity, blueprint, intensity, 0)
                
            else:
                # 結構應力黃變位移 (Dynamic Structural Strain)
                yellow_bg = np.full((h, w, 3), [200, 180, 50], dtype=np.uint8) if roughness > 0.4 else np.full((h, w, 3), [10, 35, 90], dtype=np.uint8)
                edge_img = np.full((h, w, 3), [255, 255, 255], dtype=np.uint8)
                blueprint = np.where(edges[:, :, None] > 0, edge_img, yellow_bg)
                out = cv2.addWeighted(out, 1.0 - intensity, blueprint, intensity, 0)

            # 動態 CAD 網格與坐標標尺繪製
            grid_step = 80
            line_color = (180, 220, 255) if variant != 2 else (100, 80, 50)
            
            # 十字線與座標文字
            cv2.line(out, (w // 2, 0), (w // 2, h), line_color, 1)
            cv2.line(out, (0, h // 2), (w, h // 2), line_color, 1)
            
            # 刻度尺
            for x in range(0, w, grid_step):
                cv2.line(out, (x, 0), (x, 10), line_color, 1)
            for y in range(0, h, grid_step):
                cv2.line(out, (0, y), (10, y), line_color, 1)
                
            cad_info = f"CAD_REV: 4.2 | HARMONIC: {harmonic:.2f} | ROUGH: {roughness:.2f}"
            cv2.putText(out, cad_info, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, line_color, 1, cv2.LINE_AA)
            
            return out
        except Exception as e:
            logger.error(f"Blueprint Edge error: {e}")
            return img_np

    # 2.3 圖靈擴散與生物斑紋 (Turing Pattern / Reaction-Diffusion) 5 變種
    def apply_turing_pattern_custom(self, img_np, t, intensity, ethereal, is_beat, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            dh, dw = max(64, h // 4), max(64, w // 4)
            
            # 初始化 A/B 濃度陣列
            if self._turing_A is None or self._turing_A.shape != (dh, dw):
                self._turing_A = np.ones((dh, dw), dtype=np.float32)
                self._turing_B = np.zeros((dh, dw), dtype=np.float32)
                # 注入初始亂數種子
                self._turing_B[dh//4:3*dh//4, dw//4:3*dw//4] = np.random.rand(dh//2, dw//2) * 0.5

            # 拍點觸發突變核注入 B 物質
            if is_beat:
                rx = random.randint(10, dw - 20)
                ry = random.randint(10, dh - 20)
                rw = random.randint(5, 15)
                self._turing_B[ry:ry+rw, rx:rx+rw] = 0.9

            # 拉普拉斯擴散迭代 Step (Gray-Scott 模型)
            Da = 0.16 + 0.04 * ethereal
            Db = 0.08
            f, k = 0.055, 0.062
            
            A = self._turing_A
            B = self._turing_B
            
            lap_A = cv2.boxFilter(A, -1, (3, 3)) - A
            lap_B = cv2.boxFilter(B, -1, (3, 3)) - B
            
            abb = A * B * B
            self._turing_A = np.clip(A + (Da * lap_A - abb + f * (1.0 - A)) * 0.8, 0.0, 1.0)
            self._turing_B = np.clip(B + (Db * lap_B + abb - (k + f) * B) * 0.8, 0.0, 1.0)
            
            # 升頻放大至原圖尺寸
            turing_mask = cv2.resize(self._turing_B, (w, h), interpolation=cv2.INTER_LINEAR)
            turing_mask = np.clip(turing_mask * 2.5, 0.0, 1.0)
            
            out = img_np.copy()
            
            if variant == 0:
                # 珊瑚斑塊 (Coral Reef Growth)
                coral_color = np.array([230, 80, 120], dtype=np.uint8)
                blend = cv2.addWeighted(out, 1.0, np.full_like(out, coral_color), 0.6, 0)
                out = np.where(turing_mask[:, :, None] > 0.4, blend, out)
                
            elif variant == 1:
                # 斑馬分裂紋理 (Leopard Spot Cell Division)
                spots = (turing_mask[:, :, None] * 255).astype(np.uint8)
                out = cv2.subtract(out, spots)
                
            elif variant == 2:
                # 迷宮生物波紋 (Labyrinthine Bio-Maze)
                maze = cv2.applyColorMap((turing_mask * 255).astype(np.uint8), cv2.COLORMAP_OCEAN)
                out = cv2.addWeighted(out, 1.0 - intensity * 0.6, maze, intensity * 0.6, 0)
                
            elif variant == 3:
                # 暗黑寄生脈絡 (Alien Parasite Veins)
                dark_veins = (1.0 - turing_mask[:, :, None] * 0.8) * out.astype(np.float32)
                out = np.clip(dark_veins, 0, 255).astype(np.uint8)
                
            else:
                # 螢光浮游生物 (Bioluminescent Plankton Swarm)
                glow_color = np.array([30, 240, 220], dtype=np.float32)
                glow_layer = (glow_color * turing_mask[:, :, None] * intensity).astype(np.uint8)
                out = cv2.add(out, glow_layer)
                
            return out
        except Exception as e:
            logger.error(f"Turing Pattern error: {e}")
            return img_np

    # 2.4 點雲立體深度重構 (Depth-Map Point Cloud Projection) 5 變種
    def apply_point_cloud_depth_custom(self, img_np, intensity, bass_ratio, stereo_width, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            
            # Z 軸深度圖拉伸
            depth = (gray.astype(np.float32) / 255.0) * 40.0 * bass_ratio * intensity
            
            y, x = np.mgrid[0:h:8, 0:w:8]
            depth_sampled = depth[::8, ::8]
            
            # 視角微幅 Pitch/Yaw 旋轉點雲位移
            yaw_angle = (stereo_width - 0.5) * 0.4
            shift_x = depth_sampled * np.sin(yaw_angle)
            shift_y = depth_sampled * np.cos(yaw_angle) * 0.3
            
            pts_x = np.clip(x + shift_x, 0, w - 1).astype(np.int32)
            pts_y = np.clip(y + shift_y, 0, h - 1).astype(np.int32)
            
            out = img_np.copy()
            canvas = np.zeros_like(img_np)
            
            if variant == 0:
                # 賽博綠光點雲 (Cyberpunk Particle Matrix)
                canvas[pts_y, pts_x] = [0, 255, 120]
            elif variant == 1:
                # 光達體積掃描 (Volumetric Lidar Scanner)
                canvas[pts_y, pts_x] = [0, 200, 255]
                cv2.line(canvas, (0, int(h * (self.last_t % 1.0))), (w, int(h * (self.last_t % 1.0))), (0, 255, 255), 2)
            elif variant == 2:
                # 琥珀星塵粒子 (Celestial Dust Constellation)
                canvas[pts_y, pts_x] = [255, 180, 40]
            elif variant == 3:
                # 等高梯形 Voxels (Void Topographic Voxels)
                canvas[pts_y, pts_x] = [220, 100, 250]
            else:
                # 超光速穿梭點陣 (Hyperdrive Warp Particles)
                canvas[pts_y, pts_x] = [255, 255, 255]

            canvas = cv2.GaussianBlur(canvas, (3, 3), 0)
            return cv2.addWeighted(out, 1.0 - intensity * 0.7, canvas, intensity * 0.8, 0)
        except Exception as e:
            logger.error(f"Point Cloud Depth error: {e}")
            return img_np

    # 2.5 聲相向量示波鏡 (Stereo Phase Vector-Scope) 5 變種
    def apply_vector_scope_custom(self, img_np, t, intensity, stereo_width, chord_hue, audio_samples, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            cx, cy = w // 2, h // 2
            r_c, g_c, b_c = self._hue_to_rgb(chord_hue)
            
            # 生成 Lissajous 示波軌跡點
            if audio_samples is not None and len(audio_samples) >= 128:
                samples = audio_samples[:128]
                x_pts = (cx + samples * (w * 0.25 * stereo_width)).astype(np.int32)
                y_pts = (cy + np.roll(samples, 32) * (h * 0.25 * stereo_width)).astype(np.int32)
            else:
                pts_n = 100
                theta = np.linspace(0, 2 * np.pi, pts_n)
                x_pts = (cx + np.sin(2 * theta + t * 4.0) * (w * 0.2 * stereo_width)).astype(np.int32)
                y_pts = (cy + np.cos(3 * theta + t * 3.0) * (h * 0.2 * stereo_width)).astype(np.int32)
                
            pts = np.vstack((x_pts, y_pts)).T.reshape((-1, 1, 2))
            
            # 在發光 overlay 上繪製示波幾何
            scope_canvas = np.zeros_like(img_np)
            color = (r_c, g_c, b_c)
            cv2.polylines(scope_canvas, [pts], isClosed=True, color=color, thickness=2)
            glow = cv2.GaussianBlur(scope_canvas, (11, 11), 0)
            scope_canvas = cv2.addWeighted(scope_canvas, 1.0, glow, 0.8, 0)
            
            # 利用示波線條空間梯度對背景進行光學折射 (Refraction Distortion)
            gray_scope = cv2.cvtColor(scope_canvas, cv2.COLOR_RGB2GRAY)
            grad_x = cv2.Sobel(gray_scope, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray_scope, cv2.CV_32F, 0, 1, ksize=3)
            
            grid_y, grid_x = np.mgrid[0:h, 0:w].astype(np.float32)
            map_x = np.clip(grid_x + grad_x * 0.05 * intensity, 0, w - 1)
            map_y = np.clip(grid_y + grad_y * 0.05 * intensity, 0, h - 1)
            
            refracted = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            if variant == 0:
                # 霓虹陰極 Lissajous (Neon Cathode Lissajous)
                return cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
            elif variant == 1:
                # 量子向量雷達 (Quantum Vector Radar)
                cv2.circle(scope_canvas, (cx, cy), int(h * 0.3 * stereo_width), color, 1)
                return cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
            elif variant == 2:
                # 等離子電弧光譜 (Plasma Arc Spectrogram)
                plasma = cv2.applyColorMap(gray_scope, cv2.COLORMAP_MAGMA)
                return cv2.addWeighted(refracted, 1.0 - intensity * 0.5, plasma, intensity * 0.7, 0)
            elif variant == 3:
                # 賽博標尺 Target (Cyber-Grid Vector Target)
                cv2.line(scope_canvas, (cx - 40, cy), (cx + 40, cy), (255, 255, 255), 1)
                cv2.line(scope_canvas, (cx, cy - 40), (cx, cy + 40), (255, 255, 255), 1)
                return cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
            else:
                # 立體聲色散萬花筒 (Chromatic Stereo Kaleidoscope)
                split_r = np.roll(scope_canvas[:, :, 0], 5, axis=1)
                split_b = np.roll(scope_canvas[:, :, 2], -5, axis=1)
                scope_canvas[:, :, 0] = split_r
                scope_canvas[:, :, 2] = split_b
                return cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
        except Exception as e:
            logger.error(f"Vector Scope error: {e}")
            return img_np

    # 2.6 低通悶音景深遮罩 (Low-Pass Muffle & DoF Blur) 5 變種
    def apply_lowpass_muffle_custom(self, img_np, intensity, lowpass_val, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            eff = intensity * max(0.2, lowpass_val)
            
            # 多級景深高斯模糊 Kernel
            ksize = int(15 * eff) | 1
            ksize = max(3, min(51, ksize))
            blurred = cv2.GaussianBlur(img_np, (ksize, ksize), 0)
            
            # 呼吸暗角 Vignette Mask
            y, x = np.mgrid[0:h, 0:w].astype(np.float32)
            cx, cy = w / 2.0, h / 2.0
            dist = np.sqrt((x - cx)**2 + (y - cy)**2) / np.sqrt(cx**2 + cy**2)
            vignette = np.clip(1.0 - dist * eff * 1.2, 0.0, 1.0)[:, :, None]
            
            out = (blurred.astype(np.float32) * vignette).astype(np.uint8)
            
            if variant == 0:
                # 水下沉浸深藍 (Deep Underwater Submersion)
                tint = np.full_like(out, [10, 40, 80], dtype=np.uint8)
                return cv2.addWeighted(out, 0.7, tint, 0.3 * eff, 0)
            elif variant == 1:
                # 隔牆派對悶音 (Behind-The-Wall Club Muffle)
                tint = np.full_like(out, [50, 30, 20], dtype=np.uint8)
                return cv2.addWeighted(out, 0.75, tint, 0.25 * eff, 0)
            elif variant == 2:
                # 麻醉夢境白霧 (Anesthetic Dream Fog)
                fog = np.full_like(out, [220, 230, 240], dtype=np.uint8)
                return cv2.addWeighted(out, 1.0 - eff * 0.4, fog, eff * 0.4, 0)
            elif variant == 3:
                # 徑向隧道視角 (Temporal Tunnel Vision)
                rad_blur = cv2.blur(img_np, (ksize, ksize))
                return cv2.addWeighted(rad_blur, 0.8, out, 0.2, 0)
            else:
                # 真空高對比 (Vacuum Space Isolation)
                gray = cv2.cvtColor(out, cv2.COLOR_RGB2GRAY)
                mono = cv2.merge([gray, gray, gray])
                return cv2.addWeighted(out, 1.0 - eff, mono, eff, 0)
        except Exception as e:
            logger.error(f"Lowpass Muffle error: {e}")
            return img_np

    # 2.7 無限幾何鏡廊 (Anamorphic Infinity Tunnel) 5 變種
    def apply_infinity_tunnel_custom(self, img_np, t, intensity, beat_phase, beat_energy, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            out = img_np.copy()
            
            # N 階遞迴縮放複製 (Repeated Scale-Down)
            levels = int(3 + 3 * intensity)
            scale_step = 0.75 - 0.1 * beat_energy
            
            for i in range(1, levels + 1):
                s = scale_step ** i
                sw, sh = max(10, int(w * s)), max(10, int(h * s))
                scaled = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
                
                lx = (w - sw) // 2
                ly = (h - sh) // 2
                
                if variant == 1:
                    # 六角幾何稜鏡 (Hexagonal Cyber Prism)
                    rot_mat = cv2.getRotationMatrix2D((sw // 2, sh // 2), i * 15.0 * (1.0 if i % 2 == 0 else -1.0), 1.0)
                    scaled = cv2.warpAffine(scaled, rot_mat, (sw, sh))
                elif variant == 2:
                    # 對數漩渦黑洞 (Circular Wormhole Warp)
                    rot_mat = cv2.getRotationMatrix2D((sw // 2, sh // 2), t * 30.0 + i * 10, 1.0)
                    scaled = cv2.warpAffine(scaled, rot_mat, (sw, sh))
                elif variant == 3:
                    # 三角鏡像對稱 (Triangular Kaleidoscope Tunnel)
                    scaled = cv2.flip(scaled, 1)
                elif variant == 4:
                    # 無限殘影長廊 (Endless Corridor Echo)
                    scaled = cv2.addWeighted(scaled, 0.8, np.full_like(scaled, [255, 0, 120]), 0.2, 0)
                    
                out[ly:ly+sh, lx:lx+sw] = cv2.addWeighted(out[ly:ly+sh, lx:lx+sw], 0.3, scaled, 0.7, 0)
                
            return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
        except Exception as e:
            logger.error(f"Infinity Tunnel error: {e}")
            return img_np

    # 2.8 眩暈推拉變焦 (Vertigo Dolly Zoom / Hitchcock Effect) 5 變種
    def apply_dolly_zoom_custom(self, img_np, intensity, anticipation, is_beat, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            h, w = img_np.shape[:2]
            cx, cy = w // 2, h // 2
            
            # 主體保護與背景徑向縮放
            scale_bg = 1.0 + 0.35 * intensity * (1.0 + anticipation)
            if variant == 1:
                scale_bg = 1.0 / scale_bg
                
            sw, sh = int(w * scale_bg), int(h * scale_bg)
            scaled = cv2.resize(img_np, (sw, sh), interpolation=cv2.INTER_LINEAR)
            
            lx = (sw - w) // 2
            ly = (sh - h) // 2
            bg_cropped = scaled[ly:ly+h, lx:lx+w]
            if bg_cropped.shape[:2] != (h, w):
                bg_cropped = cv2.resize(bg_cropped, (w, h))

            # 中心主體保護 Mask (橢圓形)
            mask = np.zeros((h, w), dtype=np.float32)
            cv2.ellipse(mask, (cx, cy), (int(w * 0.25), int(h * 0.35)), 0, 0, 360, 1.0, -1)
            mask = cv2.GaussianBlur(mask, (51, 51), 0)[:, :, None]
            
            # 外圍徑向模糊 (Radial Motion Blur)
            blur_size = int(15 * intensity * (1.0 + anticipation)) | 1
            blur_size = max(3, min(31, blur_size))
            bg_blurred = cv2.GaussianBlur(bg_cropped, (blur_size, blur_size), 0)
            
            if variant == 2:
                # 拍點邊緣色散 (Pulsating Focal Snap)
                bg_blurred[:, :, 0] = np.roll(bg_blurred[:, :, 0], 8, axis=1)
                bg_blurred[:, :, 2] = np.roll(bg_blurred[:, :, 2], -8, axis=1)
            elif variant == 3:
                # 螺旋扭轉眩暈 (Spiral Vertigo Warp)
                rot_mat = cv2.getRotationMatrix2D((cx, cy), 8.0 * intensity, 1.0)
                bg_blurred = cv2.warpAffine(bg_blurred, rot_mat, (w, h))
            elif variant == 4:
                # 極限放射線 (Hyper-Speed Warp Zoom)
                bg_blurred = cv2.addWeighted(bg_blurred, 0.8, np.full_like(bg_blurred, [255, 255, 255]), 0.2, 0)
                
            out = (img_np.astype(np.float32) * mask + bg_blurred.astype(np.float32) * (1.0 - mask)).astype(np.uint8)
            
            if is_beat:
                # Snap back animation boost
                out = cv2.addWeighted(out, 0.85, img_np, 0.15, 0)
                
            return cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
        except Exception as e:
            logger.error(f"Dolly Zoom error: {e}")
            return img_np

def apply_advanced_transition(pil_a, pil_b, progress, trans_type='displacement', intensity=0.5, is_beat=False, beat_energy=0.0):
    """
    Apply advanced OpenCV/NumPy transition blending between two PIL Images.
    progress: 0.0 -> pil_a; 1.0 -> pil_b
    """
    # Safeguard bounds
    progress = float(np.clip(progress, 0.0, 1.0))
    if progress <= 0.001:
        return pil_a
    if progress >= 0.999:
        return pil_b
        
    # Convert to NumPy RGB arrays
    img_a = np.array(pil_a.convert("RGB"))
    img_b = np.array(pil_b.convert("RGB"))
    
    h, w = img_a.shape[:2]
    out_np = None
    
    try:
        if trans_type == 'displacement':
            # 1. Displacement (liquid warp)
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
            # 2. Zoom & Radial Blur
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
            # 3. Luma Matte Wipe
            y_grid, x_grid = np.mgrid[0:h, 0:w]
            matte = ((x_grid / w + y_grid / h) / 2.0 * 255.0).astype(np.float32)
            
            feather = 30.0
            threshold = progress * (255.0 + feather) - feather / 2.0
            
            mask = np.clip((matte - threshold) / feather + 0.5, 0.0, 1.0)
            mask = np.expand_dims(mask, axis=2)
            
            out_np = (img_a * mask + img_b * (1.0 - mask)).astype(np.uint8)
            
        elif trans_type == 'glitch':
            # 4. Glitch & Channel Split
            max_shift = 10.0 * intensity
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
            # 5. Slide Push
            dx = int(progress * w)
            
            out_np = np.zeros_like(img_a)
            out_np[:, :w - dx] = img_a[:, dx:]
            out_np[:, w - dx:] = img_b[:, :dx]
            
            blur_size = int(np.sin(progress * np.pi) * w * 0.04 * intensity)
            if blur_size > 1:
                if blur_size % 2 == 0:
                    blur_size += 1
                blur_size = min(31, blur_size)
                out_np = cv2.blur(out_np, (blur_size, 1))
                
        else:
            out_np = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
            
    except Exception as e:
        import logging
        logging.error(f"Advanced transition error: {e}")
        out_np = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
        
    pil_out = Image.fromarray(out_np.astype(np.uint8), "RGB").convert("RGBA")
    return pil_out
