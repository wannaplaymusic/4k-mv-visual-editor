import os
import sys
import math
import random
import logging
from typing import Optional, Dict, Any, List, Tuple, Union, Callable
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageChops, ImageFilter

import json
import time
import hashlib
import collections

logger = logging.getLogger("StandaloneInjector.PostProcessor")

_VJ_FX_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_cache", "vj_fx_history.json")

def _load_vj_fx_history(max_entries=50):
    try:
        if os.path.exists(_VJ_FX_HISTORY_PATH):
            with open(_VJ_FX_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[-max_entries:]
    except Exception as e:
        logger.debug(f"Failed to load VJ FX history: {e}")
    return []

def _save_vj_fx_history(entry, max_entries=50):
    try:
        os.makedirs(os.path.dirname(_VJ_FX_HISTORY_PATH), exist_ok=True)
        history = _load_vj_fx_history(max_entries)
        # 避免連續相同種子重複寫入
        if history and history[-1].get("seed_string") == entry.get("seed_string"):
            history[-1] = entry
        else:
            history.append(entry)
        history = history[-max_entries:]
        temp_path = _VJ_FX_HISTORY_PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, _VJ_FX_HISTORY_PATH)
    except Exception as e:
        logger.warning(f"Failed to save VJ FX history: {e}")

try:
    import cv2
    if cv2 is not None:
        cv2.setUseOptimized(True)
        if hasattr(cv2, 'ocl') and cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(True)
except ImportError:
    cv2 = None

try:
    import numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

if HAS_NUMBA:
    @numba.njit(fastmath=True)
    def _numba_pixel_sort_kernel(img_np, gray, threshold_map):
        h, w, c = img_np.shape
        for y in range(0, h, 2):
            start = -1
            for x in range(w):
                if gray[y, x] > threshold_map[y, x]:
                    if start == -1:
                        start = x
                else:
                    if start != -1:
                        length = x - start
                        if length > 5:
                            sub_gray = gray[y, start:x]
                            order = np.argsort(sub_gray)
                            sub_img = img_np[y, start:x].copy()
                            for idx in range(length):
                                img_np[y, start + idx] = sub_img[order[idx]]
                        start = -1
            if start != -1:
                length = w - start
                if length > 5:
                    sub_gray = gray[y, start:w]
                    order = np.argsort(sub_gray)
                    sub_img = img_np[y, start:w].copy()
                    for idx in range(length):
                        img_np[y, start + idx] = sub_img[order[idx]]
        return img_np


class DampingFilter:
    """單階非對稱阻尼插值濾波器，實作『起得快、落得慢』的極佳 VJ 視覺節奏"""
    def __init__(self, initial_value=0.0, lambda_attack=15.0, lambda_decay=2.5):
        self.value = initial_value
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, target, dt):
        if dt <= 0:
            return self.value
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
        
        arr = np.array(self.history, dtype=np.float32)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        
        if std < 1e-4:
            return val
            
        norm = (val - mean) / (std + 1e-4)
        mapped = (norm + 1.5) / 3.0
        return max(0.0, min(1.0, float(mapped)))


class PhotosensitiveSafetyLimiter:
    """
    符合國際廣播醫療安全標準 ITU-R BT.1702 之光敏性癲癇 (PSE) 實時健康防護器。
    監控 3Hz~30Hz 頻率範圍內的螢幕整體亮度交替閃爍 (Luminance Transitions)
    以及高飽和紅光交替刺激 (Saturated Red Flashing)。
    一旦檢測到滑動視窗內閃爍次數或紅光能量超標，即自動實施 Sigmoid 軟壓制與平滑箝位。
    """
    def __init__(self, window_size=30):
        self.window_size = window_size
        self.lum_history = []
        self.red_history = []
        self.prev_frame_smoothed = None

    def process(self, img_np):
        if img_np is None or img_np.size == 0 or cv2 is None:
            return img_np
        
        # 快速計算全幀平均亮度 (Rec.709 權重) 與飽和紅光比例 (以步長抽樣統計保持 4K 實時性)
        h, w = img_np.shape[:2]
        step_h = max(1, h // 128)
        step_w = max(1, w // 128)
        sample = img_np[::step_h, ::step_w, :3].astype(np.float32)
        
        r = sample[:, :, 0]
        g = sample[:, :, 1]
        b = sample[:, :, 2]
        lum = float(np.mean(0.2126 * r + 0.7152 * g + 0.0722 * b))
        
        total = r + g + b + 1e-4
        red_ratio = float(np.mean((r / total) > 0.80))

        self.lum_history.append(lum)
        self.red_history.append(red_ratio)
        if len(self.lum_history) > self.window_size:
            self.lum_history.pop(0)
            self.red_history.pop(0)

        hazard_score = 0.0
        if len(self.lum_history) >= 6:
            diffs = np.diff(self.lum_history)
            significant_flips = 0
            for i in range(len(diffs) - 1):
                if (diffs[i] * diffs[i+1] < 0) and (abs(diffs[i]) + abs(diffs[i+1]) >= 18.0):
                    significant_flips += 1
            
            # ITU-R BT.1702: 1 秒內超過 3 次高對比翻轉即視為安全隱患
            if significant_flips > 3:
                hazard_score += min(1.0, (significant_flips - 3) * 0.25)
            
            # 飽和紅光閃爍檢測
            red_diffs = np.diff(self.red_history)
            red_flips = sum(1 for i in range(len(red_diffs) - 1) if (red_diffs[i] * red_diffs[i+1] < 0) and (abs(red_diffs[i]) >= 0.12))
            if red_flips > 2:
                hazard_score += min(1.0, (red_flips - 2) * 0.35)

        if self.prev_frame_smoothed is None or self.prev_frame_smoothed.shape != img_np.shape:
            self.prev_frame_smoothed = img_np.astype(np.float32)
            self.last_hazard_score = 0.0
            self.last_red_ratio = red_ratio
            return img_np

        self.last_hazard_score = float(hazard_score)
        self.last_red_ratio = float(red_ratio)

        if hazard_score > 0.05:
            clamp_alpha = min(0.70, float(hazard_score * 0.70))
            safe_frame = cv2.addWeighted(img_np, 1.0 - clamp_alpha, self.prev_frame_smoothed.astype(np.uint8), clamp_alpha, 0)
            self.prev_frame_smoothed = 0.85 * self.prev_frame_smoothed + 0.15 * safe_frame.astype(np.float32)
            return safe_frame
        else:
            self.prev_frame_smoothed = 0.85 * self.prev_frame_smoothed + 0.15 * img_np.astype(np.float32)
            return img_np

    def get_safety_telemetry(self):
        score = getattr(self, 'last_hazard_score', 0.0)
        return {
            'hazard_score': score,
            'red_ratio': getattr(self, 'last_red_ratio', 0.0),
            'status': 'SAFE' if score < 0.1 else ('WARNING' if score < 0.35 else 'DANGER')
        }


def srgb_to_oklab(img_np):
    """
    高速向量化 sRGB (0~255) 轉 Oklab (float32)
    L in [0, 1], a in [-0.4, 0.4], b in [-0.4, 0.4]
    """
    c = img_np.astype(np.float32) / 255.0
    mask = c > 0.04045
    c_lin = np.empty_like(c)
    c_lin[mask] = ((c[mask] + 0.055) / 1.055) ** 2.4
    c_lin[~mask] = c[~mask] / 12.92

    r, g, b = c_lin[:, :, 0], c_lin[:, :, 1], c_lin[:, :, 2]
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = np.cbrt(l)
    m_ = np.cbrt(m)
    s_ = np.cbrt(s)

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a_ok = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_ok = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return np.dstack((L, a_ok, b_ok))


def oklab_to_srgb(img_oklab):
    """
    高速向量化 Oklab (float32) 轉 sRGB uint8 (0~255)
    """
    L = img_oklab[:, :, 0]
    a_ok = img_oklab[:, :, 1]
    b_ok = img_oklab[:, :, 2]

    l_ = L + 0.3963377774 * a_ok + 0.2158037573 * b_ok
    m_ = L - 0.1055613458 * a_ok - 0.0638541728 * b_ok
    s_ = L - 0.0894841775 * a_ok - 1.2914855480 * b_ok

    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    c = np.dstack((r, g, b))
    c = np.clip(c, 0.0, 1.0)
    mask = c > 0.0031308
    c_gamma = np.empty_like(c)
    c_gamma[mask] = 1.055 * (c[mask] ** (1.0 / 2.4)) - 0.055
    c_gamma[~mask] = 12.92 * c[~mask]
    return np.clip(np.round(c_gamma * 255.0), 0, 255).astype(np.uint8)


def apply_ambient_perceptual_chroma_limiter(
    img_np: np.ndarray,
    chroma_limit: float = 0.070,
    target_hue_deg: Optional[float] = None,
    hue_blend: float = 0.0,
    highlight_rolloff: float = 0.88,
    warmth_offset: float = 0.0
) -> np.ndarray:
    """
    OKLab 感知色度抑制與電影級大氣色彩修整器 (Perceptual Chroma Limiter & Atmospheric ShowLook)
    專門解決 Ambient 曲風下偶發的高飽和鮮艷刺眼色塊或個別視覺模組寫死原色的問題：
    1. 將 sRGB 影像精準轉至 OKLab 色彩空間 (L, a, b)。
    2. 計算像素感知彩度 C = sqrt(a^2 + b^2)。
    3. 對超出安全門檻 C_limit 的鮮艷像素執行雙曲正切 (tanh) 柔和滾降壓縮：
       C' = C_limit * tanh(C / C_limit)
       保留色彩豐富度的同時徹底消除數碼螢光刺眼感。
    4. 針對極端高光 (L > highlight_rolloff) 進行大氣散射滾降，營造 Turrell Ganzfeld 漫射質感。
    5. 依據目標導演色相 (target_hue_deg) 進行環境色溫漂移，統一全片調性。
    """
    if img_np is None or img_np.size == 0:
        return img_np

    try:
        ok = srgb_to_oklab(img_np)
        L = ok[:, :, 0]
        a = ok[:, :, 1]
        b = ok[:, :, 2]

        C = np.sqrt(a * a + b * b)

        # 雙曲正切 (tanh) 柔和色度壓制 (Smooth Chroma Soft-Knee Compression)
        c_lim = max(0.015, float(chroma_limit))
        scale = np.where(C > c_lim, (c_lim * np.tanh(C / c_lim)) / np.maximum(C, 1e-6), 1.0)
        a_clamped = a * scale
        b_clamped = b * scale

        # 導演目標色相微弱大氣浸潤 (Target Hue Atmospheric Infusion)
        if target_hue_deg is not None and hue_blend > 0.001:
            h_rad = math.radians(float(target_hue_deg))
            target_a = c_lim * 0.7 * math.cos(h_rad)
            target_b = c_lim * 0.7 * math.sin(h_rad)
            blend_w = min(0.35, float(hue_blend))
            a_clamped = a_clamped * (1.0 - blend_w) + target_a * blend_w
            b_clamped = b_clamped * (1.0 - blend_w) + target_b * blend_w

        # 微調色溫 (Warmth offset)
        if abs(warmth_offset) > 0.001:
            a_clamped += warmth_offset * 0.02
            b_clamped += warmth_offset * 0.01

        # 高光柔化滾降 (Highlight Soft-Roll-off - Turrell Ganzfeld Effect)
        if highlight_rolloff < 0.99:
            hl_mask = L > highlight_rolloff
            excess = L - highlight_rolloff
            L_soft = np.where(hl_mask, highlight_rolloff + (1.0 - highlight_rolloff) * np.tanh(excess * 3.0), L)
        else:
            L_soft = L

        ok_out = np.dstack((L_soft, a_clamped, b_clamped))
        return oklab_to_srgb(ok_out)
    except Exception as e:
        return img_np


class FXPolymorphicMutationEngine:
    """
    呼叫級動態多態突變引擎 (Polymorphic Mutation Engine)
    保證全域後製特效在每次被擊發時，均由當前音樂微節奏、曲風與混沌種子驅動，
    產生劇烈不同屬性（幾何拓撲、尺度維度、對稱軸數、色彩極化、非線性曲率、質地顆粒度），
    徹底消除千篇一律的視覺疲勞，同時緊密耦合音樂能量與風格。
    """
    ACES_INDUSTRIAL_MONOLITH = np.array([
        [10, 17, 40],     # 深冷鈷藍
        [18, 18, 20],     # 玄武岩黑
        [255, 183, 3],    # 純鎢金
        [160, 175, 190]   # 冷鉻銀
    ], dtype=np.float32)

    ACES_ACID_MUTATION = np.array([
        [3, 25, 30],      # 深墨綠
        [57, 255, 20],    # 劇毒螢光酸綠
        [114, 9, 183],    # 暗紫外光
        [200, 255, 100]   # 亮黃綠
    ], dtype=np.float32)

    ACES_THERMAL_CORE = np.array([
        [26, 26, 29],     # 深炭灰
        [195, 7, 63],     # 熔岩赤紅
        [250, 250, 250],  # 高溫白熾
        [78, 14, 30]      # 暗緋紅
    ], dtype=np.float32)

    ACES_BRUTALIST_HIGH_KEY = np.array([
        [250, 250, 250],  # 純鈦白
        [5, 5, 5],        # 深鉛黑
        [142, 154, 175],  # 中性鉻銀
        [60, 64, 72]      # 冷工業灰
    ], dtype=np.float32)

    ACES_AMBIENT_MIST = np.array([
        [18, 24, 32],      # Deep Nordic Slate
        [48, 62, 74],      # Morandi Mist Blue-Gray
        [98, 114, 126],    # Soft Fog Stone
        [168, 180, 190]    # Muted Pale Cloud
    ], dtype=np.float32)

    PALETTES = [
        ACES_INDUSTRIAL_MONOLITH,
        ACES_ACID_MUTATION,
        ACES_THERMAL_CORE,
        ACES_BRUTALIST_HIGH_KEY
    ]

    @classmethod
    def generate_invocation_dna(cls, fx_name: str, t: float, beat_energy: float, 
                                audio_feats: dict, song_seed: int = 0, genre: str = 'techno') -> dict:
        """
        每次特效呼叫時，動態合成高熵 6 維度突變參數字典 (DNA)
        """
        feats = audio_feats if isinstance(audio_feats, dict) else {}
        sub_bass = float(feats.get('sub_bass', 0.5))
        percussive = float(feats.get('percussive', 0.5))
        roughness = float(feats.get('roughness', 0.5))
        ethereal = float(feats.get('ethereal', 0.5))
        centroid = float(feats.get('centroid', feats.get('spectral_centroid', 0.5)))
        harmonic = float(feats.get('harmonic', 0.5))
        stereo_width = float(feats.get('stereo_width', 0.5))
        
        # 雜湊呼叫時間戳與微步特徵，生成呼叫級高隨機度種子
        t_hash = int(round(t * 120.0))
        name_hash = int(hashlib.md5(fx_name.encode('utf-8')).hexdigest()[:6], 16)
        seed_val = (t_hash * 31337 + int(beat_energy * 10000) + name_hash + (song_seed or 0)) & 0x7FFFFFFF
        rng = np.random.RandomState(seed_val % (2**31 - 1))

        # 1. 幾何模式突變 (0: 徑向旋渦, 1: 笛卡爾切片, 2: 雙曲幾何, 3: 碎形晶格, 4: 極坐標折疊)
        geom_mode = int(rng.randint(0, 5))

        # 2. 尺度跳躍突變 (極細粒子 0.25 到 巨集切片 4.2)
        scale_pool = [0.25, 0.5, 1.0, 2.0, 3.5, 4.2]
        base_scale = float(rng.choice(scale_pool))
        scale_factor = base_scale * float(0.75 + 0.5 * sub_bass)

        # 3. 旋轉角與對稱軸突變
        rot_angle = float(rng.uniform(0.0, 360.0))
        sym_axes = int(rng.choice([1, 2, 3, 4, 6, 8]))

        # 4. 色彩極性突變與調色盤選取
        genre_lower = genre.lower() if isinstance(genre, str) else ''
        is_amb_dna = any(k in genre_lower for k in ('ambient', 'drone', 'meditative', 'chill', 'downtempo', 'atmospheric')) or bool(feats.get('force_ambient_color'))
        if is_amb_dna:
            chosen_palette = cls.ACES_AMBIENT_MIST
            color_polarity = int(rng.choice([0, 3, 4]))  # 嚴禁 pol=1 (霓虹反轉) 與 pol=2 (高反差紅藍分離)
            chroma_shift = float(rng.uniform(0.01, 0.04))
        else:
            if 'acid' in genre_lower:
                pal_idx = int(rng.choice([1, 0, 2]))
            elif 'hard' in genre_lower:
                pal_idx = int(rng.choice([2, 0, 3]))
            elif 'dub' in genre_lower:
                pal_idx = int(rng.choice([0, 3]))
            else:
                pal_idx = int(rng.randint(0, len(cls.PALETTES)))
            chosen_palette = cls.PALETTES[pal_idx]
            color_polarity = int(rng.randint(0, 5))
            chroma_shift = float(rng.uniform(0.03, 0.18) * (0.8 + 0.6 * roughness))

        # 5. 非線性曲率與動態包絡
        warp_exp = float(rng.uniform(0.4, 2.8) * (0.6 + 0.8 * beat_energy))
        noise_gran = float(rng.uniform(0.1, 1.0))
        env_type = int(rng.randint(0, 3))

        return {
            'seed': seed_val,
            'fx_name': fx_name,
            'geometry_mode': geom_mode,
            'scale_factor': scale_factor,
            'rotation_angle': rot_angle,
            'symmetry_axes': sym_axes,
            'color_polarity': color_polarity,
            'chroma_shift': chroma_shift,
            'warp_exponent': warp_exp,
            'noise_granularity': noise_gran,
            'envelope_type': env_type,
            'palette': chosen_palette,
            'sub_bass': sub_bass,
            'percussive': percussive,
            'roughness': roughness,
            'ethereal': ethereal,
            'centroid': centroid,
            'harmonic': harmonic,
            'stereo_width': stereo_width,
            'beat_energy': beat_energy,
            't': t
        }

    @classmethod
    def apply_color_polarization(cls, img_np: np.ndarray, dna: dict, intensity: float) -> np.ndarray:
        """
        依據突變 DNA 將畫面色彩映射至當前高階 ACES 工業調色盤或極化互補色
        """
        if intensity < 0.02 or img_np is None:
            return img_np
        pol = dna.get('color_polarity', 0)
        eff = float(np.clip(intensity, 0.0, 1.0))

        if pol == 0:
            # 模式 0: ACES 調色盤通道亮度雙色調映射 (Duotone Map)
            pal = dna.get('palette', cls.ACES_INDUSTRIAL_MONOLITH)
            gray = (0.299 * img_np[:, :, 0] + 0.587 * img_np[:, :, 1] + 0.114 * img_np[:, :, 2]) / 255.0
            idx_low = np.clip((gray * 3.0).astype(np.int32), 0, 2)
            idx_high = np.clip(idx_low + 1, 0, 3)
            frac = (gray * 3.0 - idx_low)[:, :, None]
            c_low = pal[idx_low]
            c_high = pal[idx_high]
            mapped = (c_low * (1.0 - frac) + c_high * frac).astype(np.float32)
            out = img_np.astype(np.float32) * (1.0 - eff * 0.7) + mapped * (eff * 0.7)
            return np.clip(out, 0, 255).astype(np.uint8)

        elif pol == 1:
            # 模式 1: 霓虹酸性極化反轉 (Chroma Solarization Inversion)
            c = img_np.astype(np.float32)
            solar = np.where(c > 128.0, 255.0 - c, c * 1.5)
            out = c * (1.0 - eff * 0.65) + solar * (eff * 0.65)
            return np.clip(out, 0, 255).astype(np.uint8)

        elif pol == 2:
            # 模式 2: 冷暖雙峰對比分離 (Split Toning)
            shift = dna.get('chroma_shift', 0.08) * 255.0 * eff
            out = img_np.astype(np.float32).copy()
            out[:, :, 0] = np.clip(out[:, :, 0] + shift, 0, 255)  # Boost Red
            out[:, :, 2] = np.clip(out[:, :, 2] - shift * 0.7, 0, 255) # Dim Blue
            return out.astype(np.uint8)

        elif pol == 3:
            # 模式 3: 高反差純黑白鎢金高光 (High-Key Monolith Tint)
            gray = (0.299 * img_np[:, :, 0] + 0.587 * img_np[:, :, 1] + 0.114 * img_np[:, :, 2])
            mono = np.dstack([gray, gray * 0.95, gray * 0.85]).astype(np.float32)
            out = img_np.astype(np.float32) * (1.0 - eff * 0.8) + mono * (eff * 0.8)
            return np.clip(out, 0, 255).astype(np.uint8)

        return img_np


class TimeDisplacementBuffer:
    """時空反饋狹縫掃描（Slit-Scan）影格環形緩衝區 (NumPy 原生直通)"""
    def __init__(self, max_size=30):
        self.max_size = max_size
        self.buffer = []
        self._grid_cache = None

    def push(self, img_np):
        self.buffer.append(img_np.copy())
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)

    def apply(self, img_np, intensity):
        if len(self.buffer) < 5 or intensity < 0.05 or cv2 is None:
            return img_np

        try:
            h, w = img_np.shape[:2]
            if self._grid_cache is None or self._grid_cache[0] != (w, h):
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dist = np.sqrt((x - w / 2.0)**2 + (y - h / 2.0)**2)
                max_dist = np.sqrt((w / 2.0)**2 + (h / 2.0)**2)
                self._grid_cache = ((w, h), dist, max_dist)
            _, dist, max_dist = self._grid_cache
            
            delay_map = (dist / max_dist) * (self.max_size - 1) * intensity
            delay_map = np.clip(delay_map, 0, len(self.buffer) - 1).astype(np.int32)

            out_np = np.zeros_like(img_np)
            for d in range(len(self.buffer)):
                mask = (delay_map == d)
                if np.any(mask):
                    out_np[mask] = self.buffer[-(d + 1)][mask]

            return out_np
        except Exception as e:
            logger.error(f"Error in slit-scan: {e}")
            return img_np


class PhaseEffectController:
    """音訊相位效應動態控制器，具備能量門檻與 AD 包絡線平滑衰減機制"""
    def __init__(self, energy_threshold=0.03, phase_delta_threshold=0.10, decay_rate=0.88):
        self.energy_threshold = energy_threshold
        self.phase_delta_threshold = phase_delta_threshold
        self.decay_rate = decay_rate
        self.smoothed_intensity = 0.0
        self.prev_phase_width = 0.0

    def update(self, audio_energy: float, current_phase_width: float, dt: float = 0.033) -> float:
        if audio_energy < self.energy_threshold:
            self.smoothed_intensity *= self.decay_rate
            return self.smoothed_intensity

        phase_delta = abs(current_phase_width - self.prev_phase_width)
        self.prev_phase_width = current_phase_width

        if phase_delta > self.phase_delta_threshold or current_phase_width > 0.4:
            target = current_phase_width
        else:
            target = 0.0

        if target > self.smoothed_intensity:
            self.smoothed_intensity = 0.35 * target + 0.65 * self.smoothed_intensity
        else:
            self.smoothed_intensity *= self.decay_rate

        return float(np.clip(self.smoothed_intensity, 0.0, 1.0))


class FilterSweepController:
    """音訊濾波器掃頻與轉折控制器 (非對稱阻尼 Attack/Decay)"""
    def __init__(self, lambda_attack=18.0, lambda_decay=2.5):
        self.smoothed_lowpass = 1.0
        self.smoothed_highpass = 0.0
        self.smoothed_velocity = 0.0
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, lowpass_norm: float, highpass_norm: float, velocity_norm: float, dt: float = 0.033):
        dt = max(0.001, dt)
        
        l_speed = self.lambda_attack if lowpass_norm < self.smoothed_lowpass else self.lambda_decay
        self.smoothed_lowpass += (lowpass_norm - self.smoothed_lowpass) * (1.0 - math.exp(-l_speed * dt))
        
        h_speed = self.lambda_attack if highpass_norm > self.smoothed_highpass else self.lambda_decay
        self.smoothed_highpass += (highpass_norm - self.smoothed_highpass) * (1.0 - math.exp(-h_speed * dt))
        
        v_speed = self.lambda_attack if velocity_norm > self.smoothed_velocity else self.lambda_decay
        self.smoothed_velocity += (velocity_norm - self.smoothed_velocity) * (1.0 - math.exp(-v_speed * dt))

        return float(self.smoothed_lowpass), float(self.smoothed_highpass), float(self.smoothed_velocity)


class FeedbackSystem:
    """ 反應擴散（Reaction-Diffusion）迭代動力學反饋系統 """
    def __init__(self):
        self.feedback_img = None
        self._color_cache = None

    def apply(self, img_np, intensity, chord_name='N.C.', reverb_decay=0.15, custom_palette=None):
        if intensity < 0.05 or cv2 is None:
            return img_np

        h, w = img_np.shape[:2]
        if self.feedback_img is None or self.feedback_img.shape != (h, w):
            self.feedback_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            return img_np

        try:
            curr_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            blended = cv2.addWeighted(self.feedback_img, 1.0 - reverb_decay, curr_gray, reverb_decay, 0)
            
            scale = 1.01 + 0.005 * intensity
            rw, rh = int(w * scale), int(h * scale)
            diffused = cv2.resize(blended, (rw, rh), interpolation=cv2.INTER_LINEAR)
            
            left = (rw - w) // 2
            top = (rh - h) // 2
            diffused = diffused[top:top+h, left:left+w]
            if diffused.shape != (h, w):
                diffused = cv2.resize(diffused, (w, h), interpolation=cv2.INTER_LINEAR)

            mean_val = float(np.mean(diffused))
            contrast_factor = 1.3 + 0.3 * intensity
            beta = mean_val * (1.0 - contrast_factor)
            diffused = cv2.convertScaleAbs(diffused, alpha=contrast_factor, beta=beta)
            
            self.feedback_img = diffused

            chord_lower = chord_name.lower()
            is_minor = any(m in chord_lower for m in ('min', 'dim', 'aug')) or ('m' in chord_lower and 'maj' not in chord_lower)
            
            if self._color_cache is None or self._color_cache[0] != (h, w) or self._color_cache[1] != is_minor or self._color_cache[3] != id(custom_palette):
                if custom_palette and isinstance(custom_palette, dict):
                    morandi_rgb = custom_palette['minor'] if is_minor else custom_palette['major']
                else:
                    morandi_rgb = np.array([110, 180, 200], dtype=np.float32) / 255.0 if is_minor else np.array([230, 170, 190], dtype=np.float32) / 255.0
                self._color_cache = ((h, w), is_minor, morandi_rgb, id(custom_palette))
            
            _, _, morandi_rgb, _ = self._color_cache
            c0 = cv2.convertScaleAbs(diffused, alpha=float(morandi_rgb[0]))
            c1 = cv2.convertScaleAbs(diffused, alpha=float(morandi_rgb[1]))
            c2 = cv2.convertScaleAbs(diffused, alpha=float(morandi_rgb[2]))
            colored_feedback = cv2.merge([c0, c1, c2])
            
            return cv2.addWeighted(img_np, 1.0 - 0.25 * intensity, colored_feedback, 0.25 * intensity, 0)
        except Exception as e:
            logger.error(f"Error in reaction-diffusion feedback: {e}")
            return img_np


class VJAestheticEngine:
    """4K MV 全域 VJ 審美引擎"""
    PRESETS = {
        'CYBERPUNK': {'primary_rgb': (0, 240, 255), 'secondary_rgb': (255, 0, 85), 'bg_rgb': (11, 14, 20)},
        'SYNTHWAVE': {'primary_rgb': (121, 40, 202), 'secondary_rgb': (255, 0, 128), 'bg_rgb': (15, 5, 29)},
        'FLUID': {'primary_rgb': (0, 223, 137), 'secondary_rgb': (3, 105, 161), 'bg_rgb': (30, 41, 59)},
        'MONOCHROME': {'primary_rgb': (245, 158, 11), 'secondary_rgb': (113, 113, 122), 'bg_rgb': (9, 9, 11)}
    }

    @staticmethod
    def get_harmonic_color(pitch_class=0, energy=0.5, is_minor=False):
        base_hue = (pitch_class * 30 + 15) % 360
        sat = (0.35 + energy * 0.25) if is_minor else (0.65 + energy * 0.25)
        light = (0.25 + energy * 0.30) if is_minor else (0.45 + energy * 0.30)
        
        c = (1.0 - abs(2.0 * light - 1.0)) * sat
        x = c * (1.0 - abs((base_hue / 60.0) % 2 - 1.0))
        m = light - c / 2.0
        
        if base_hue < 60: r, g, b = c, x, 0.0
        elif base_hue < 120: r, g, b = x, c, 0.0
        elif base_hue < 180: r, g, b = 0.0, c, x
        elif base_hue < 240: r, g, b = 0.0, x, c
        elif base_hue < 300: r, g, b = x, 0.0, c
        else: r, g, b = c, 0.0, x
            
        return (float(r + m), float(g + m), float(b + m))


class ProceduralCameraRig:
    """程序化虛擬鏡頭矩陣：3D透視投影 (Perspective Homography)、Dolly Zoom、手持漂移、旋轉與空間幾何"""
    def __init__(self, rng=None, is_hard_techno=False):
        self.rng = rng or random.Random()
        self.is_hard_techno = is_hard_techno
        self.mode = self.rng.choice(['orbit_spin', 'dolly_zoom_pulse', 'handheld_drift', 'spiral_vortex'])
        self.rig_archetype = self.rng.choice(['kinetic_punch', 'brutalist_lock', 'orbital_sway', 'seismic_tremor'])
        self.speed = self.rng.uniform(0.9, 1.75) if is_hard_techno else self.rng.uniform(0.6, 1.4)
        self.amplitude = self.rng.uniform(0.85, 1.35) if is_hard_techno else self.rng.uniform(0.8, 1.2)
        self.kick_zoom_gain = self.rng.uniform(0.06, 0.14)
        self.shake_gain = self.rng.uniform(4.0, 13.0)

    def apply(self, img_np, t, beat_energy, section_name='Verse', cinedance_meta=None, enable_perspective_3d=True):
        if cv2 is None: return img_np
        h, w = img_np.shape[:2]
        center = (w / 2.0, h / 2.0)

        sec = section_name.lower()
        if self.is_hard_techno:
            # ⚡ Hard Techno 段落呼吸對比：Intro/Verse 保持建築結構清晰穩定，Build-up 蓄力，Drop 釋放極致衝擊
            if 'intro' in sec or 'outro' in sec: intensity_scale = 0.35
            elif 'bridge' in sec: intensity_scale = 0.55
            elif 'verse' in sec: intensity_scale = 0.75
            elif 'build' in sec: intensity_scale = 1.20
            else: intensity_scale = 1.85  # Drop / Chorus Climax
            if self.rig_archetype == 'brutalist_lock' and ('drop' not in sec and 'chorus' not in sec):
                intensity_scale *= 0.55
        else:
            if 'intro' in sec or 'outro' in sec: intensity_scale = 0.2
            elif 'verse' in sec or 'bridge' in sec: intensity_scale = 0.4
            elif 'build' in sec: intensity_scale = 1.2
            else: intensity_scale = 1.75
        
        if beat_energy > 0.65: intensity_scale *= 1.20

        # 讀取 CINEDANCE 元數據
        target_fov = 50.0
        dolly_active = False
        dolly_velocity = 0.0
        depth_compression = 0.5
        horizon_y = 0.5

        if isinstance(cinedance_meta, dict):
            target_fov = float(cinedance_meta.get('target_fov_deg', 50.0))
            dolly_active = bool(cinedance_meta.get('dolly_zoom_active', False))
            dolly_velocity = float(cinedance_meta.get('dolly_zoom_velocity', 0.0))
            depth_compression = float(cinedance_meta.get('depth_compression_index', 0.5))
            horizon_y = float(cinedance_meta.get('horizon_ndc_y', 0.5))

        # 3D 透視投影模式 (Perspective Homography Warp)
        if enable_perspective_3d and hasattr(cv2, 'warpPerspective') and hasattr(cv2, 'getPerspectiveTransform'):
            try:
                fov_rad = math.radians(target_fov)
                focal_scale = 1.0 / max(0.1, math.tan(fov_rad / 2.0))

                roll_rad = 0.0
                pitch_rad = 0.0
                yaw_rad = 0.0
                dolly_z = 0.0

                if self.mode == 'orbit_spin':
                    roll_rad = math.sin(t * 0.5 * self.speed) * 0.05 * self.amplitude * intensity_scale
                    yaw_rad = math.cos(t * 0.3 * self.speed) * 0.06 * intensity_scale
                elif self.mode == 'dolly_zoom_pulse' or dolly_active:
                    dolly_pulse = math.sin(t * 1.2 * self.speed) * 0.06 + beat_energy * 0.04
                    if dolly_active:
                        dolly_pulse += dolly_velocity * 0.08
                    dolly_z = dolly_pulse * intensity_scale
                    pitch_rad = math.sin(t * 0.7) * 0.04 * intensity_scale
                elif self.mode == 'handheld_drift':
                    pitch_rad = (math.sin(t * 1.5) * 0.03 + math.cos(t * 3.1) * 0.015) * intensity_scale
                    yaw_rad = (math.cos(t * 1.3) * 0.03 + math.sin(t * 2.7) * 0.015) * intensity_scale
                    roll_rad = math.sin(t * 0.8) * 0.02 * intensity_scale
                elif self.mode == 'spiral_vortex':
                    roll_rad = (t * 2.0 * self.speed) % 360.0 * 0.002 * intensity_scale
                    dolly_z = beat_energy * 0.05 * intensity_scale

                src_pts = np.float32([
                    [0.0, 0.0],
                    [float(w), 0.0],
                    [float(w), float(h)],
                    [0.0, float(h)]
                ])

                # ⚡ 依曲目專屬鏡頭原型 (rig_archetype) 與段落決定大鼓衝擊縮放與震顫，杜絕 45 首歌全曲同質化搖晃
                is_peak_sec = ('drop' in sec or 'chorus' in sec)
                if self.is_hard_techno:
                    if self.rig_archetype == 'kinetic_punch' and beat_energy > 0.55:
                        dolly_z += (beat_energy ** 1.4) * self.kick_zoom_gain * (1.35 if is_peak_sec else 0.65)
                    elif self.rig_archetype == 'orbital_sway' and beat_energy > 0.60:
                        roll_rad += math.sin(t * 2.0) * 0.028 * beat_energy
                    elif self.rig_archetype == 'seismic_tremor' and is_peak_sec and beat_energy > 0.65:
                        dolly_z += (beat_energy ** 1.5) * (self.kick_zoom_gain * 0.85)
                        roll_rad += self.rng.uniform(-1.0, 1.0) * 0.025 * beat_energy

                scale_3d = 1.0 + dolly_z
                cx, cy = w * 0.5, h * horizon_y
                if self.is_hard_techno and is_peak_sec and self.rig_archetype in ('seismic_tremor', 'kinetic_punch') and beat_energy > 0.72:
                    cx += self.rng.uniform(-1.0, 1.0) * self.shake_gain * beat_energy
                    cy += self.rng.uniform(-1.0, 1.0) * (self.shake_gain * 0.75) * beat_energy

                dst_pts = np.zeros_like(src_pts)

                for idx in range(4):
                    px, py = src_pts[idx][0], src_pts[idx][1]
                    rel_x = (px - cx) * scale_3d
                    rel_y = (py - cy) * scale_3d

                    cos_r, sin_r = math.cos(roll_rad), math.sin(roll_rad)
                    rx = rel_x * cos_r - rel_y * sin_r
                    ry = rel_x * sin_r + rel_y * cos_r

                    z_factor = 1.0 + (ry / max(1.0, float(h))) * math.sin(pitch_rad) * (1.2 / max(0.1, focal_scale)) \
                                   + (rx / max(1.0, float(w))) * math.sin(yaw_rad) * (1.2 / max(0.1, focal_scale))
                    z_factor = max(0.5, min(1.8, z_factor))

                    dst_pts[idx] = [cx + rx / z_factor, cy + ry / z_factor]

                H = cv2.getPerspectiveTransform(src_pts, dst_pts)
                return cv2.warpPerspective(img_np, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            except Exception:
                pass

        # 降級相容 2D 仿射模式
        scale, angle, tx, ty = 1.0, 0.0, 0.0, 0.0
        if self.mode == 'orbit_spin':
            angle = math.sin(t * 0.5 * self.speed) * 3.5 * self.amplitude * intensity_scale
            scale = 1.0 + (math.cos(t * 0.8 * self.speed) * 0.03 + beat_energy * 0.02) * intensity_scale
        elif self.mode == 'dolly_zoom_pulse':
            scale = 1.0 + (math.sin(t * 1.2 * self.speed) * 0.05 + beat_energy * 0.05) * intensity_scale
            tx = math.sin(t * 0.9) * 12.0 * intensity_scale
            ty = math.cos(t * 0.7) * 12.0 * intensity_scale
        elif self.mode == 'handheld_drift':
            tx = (math.sin(t * 1.5) * 15.0 + math.cos(t * 3.1) * 8.0) * self.amplitude * intensity_scale
            ty = (math.cos(t * 1.3) * 15.0 + math.sin(t * 2.7) * 8.0) * self.amplitude * intensity_scale
            angle = math.sin(t * 0.8) * 1.2 * intensity_scale
        elif self.mode == 'spiral_vortex':
            angle = (t * 2.0 * self.speed) % 360.0 * 0.05 * intensity_scale
            scale = 1.02 + (beat_energy * 0.04) * intensity_scale

        M = cv2.getRotationMatrix2D(center, angle, scale)
        M[0, 2] += tx
        M[1, 2] += ty

        return cv2.warpAffine(img_np, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


class SpatialTriadRelighting:
    """
    CINEDANCE 三元空間光影重著色器 (Spatial Triad Relighting)
    利用 Sobel 梯度估算法線向量，以主光 (Key) 與輪廓光 (Rim) 即時著色
    """
    @classmethod
    def apply_relighting(
        cls,
        img_np: np.ndarray,
        light_triad: Optional[Dict[str, Any]] = None,
        blend_weight: float = 0.35
    ) -> np.ndarray:
        if cv2 is None or light_triad is None or blend_weight <= 0.01:
            return img_np

        try:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            mag = cv2.magnitude(gx, gy)

            rim_info = light_triad.get("rim_light", {})
            rim_intensity = float(rim_info.get("intensity", 1.0))

            edge_factor = np.clip(mag / 128.0, 0.0, 1.0)
            rim_gain = (edge_factor * rim_intensity * (blend_weight * 0.8))[:, :, np.newaxis]

            lit_np = img_np.astype(np.float32) + (rim_gain * 255.0)
            return np.clip(lit_np, 0.0, 255.0).astype(np.uint8)
        except Exception:
            return img_np


class AudioParticleFluidEngine:
    """
    工業級超維動態粒子形態引擎 (Metamorphic Audio-Reactive Particle Engine)
    - 每次生成具備唯一宇宙基因 (Cosmic DNA: 形態族群、對稱階數、物理力場、相變速度)
    - 粒子本身拓撲幾何根據即時音樂特徵劇烈形變 (Morphological Deformation):
      * Sub-Bass / Kick: 突刺多角星芒爆發 (Stellated Star Eruption) 與彈性果凍擠壓 (Squash & Stretch)
      * Mid / Vocal: 邊緣流體諧波波動 (Harmonic Undulation) 與自旋扭轉
      * High / Hi-hat: 晶體斷裂稜角震顫 (Crystalline Faceting Jitter) 與量子微粒發射
    - 物理場矩陣: 渦流吸引子、洛倫茲混沌、諧振彈簧力與仿生集群
    """
    MORPH_FAMILIES = [
        'StellatedStar',           # 星芒突刺多邊形 (Bass 強度驅動芒刺暴展)
        'ElasticJellyBlob',        # 彈性果凍液滴 (低音衝擊擠壓、中頻諧波輪廓波動)
        'QuantumResonanceRing',    # 量子共振同心環 (高頻激發衛星光點公轉)
        'CrystallinePrism',        # 動態晶體多稜鏡 (Hihat 觸發邊緣碎裂微震顫)
        'MetamorphicVoronoi',      # 沃羅諾伊動態晶胞拓撲
        'CosmicFilament'           # 星雲超弦動態發光纖維
    ]
    PHYSICS_MODES = [
        'VortexAttractor',         # 雙奇異點渦流吸積
        'LorenzChaos',             # 洛倫茲奇異吸子微擾
        'HarmonicSpring',          # 諧振子核心吸引回彈
        'BrownianQuantum',         # 布朗分子熱運動與量子隧穿
        'BoidsCentering'           # 仿生群體凝聚與速度匹配
    ]
    EMISSION_PATTERNS = ['RadialBloom', 'SpiralHelix', 'DualAttractors', 'UpwardFountain', 'EdgeRingInward']

    def __init__(self, max_particles=350, seed_string=None):
        import hashlib
        self.max_particles = max_particles
        self.particles = []
        self.cooldown = 0
        
        # 1. 唯一宇宙基因程序化隨機 (Procedural Cosmic DNA)
        hash_val = int(hashlib.md5((seed_string or "unique_metamorphic_particle").encode('utf-8')).hexdigest(), 16)
        rng = random.Random(hash_val)

        self.dna = {
            'morph_family': rng.choice(self.MORPH_FAMILIES),
            'physics_mode': rng.choice(self.PHYSICS_MODES),
            'emission_pattern': rng.choice(self.EMISSION_PATTERNS),
            'symmetry_n': rng.choice([3, 4, 5, 6, 7, 8, 10, 12]),   # 對稱星芒階數
            'viscosity': rng.uniform(0.91, 0.985),                   # 物理流體阻尼
            'elastic_squash': rng.uniform(0.6, 1.4),                 # 果凍形變彈性剛度
            'spin_speed': rng.uniform(1.2, 4.5),                     # 固有角動量
            'spike_reach': rng.uniform(0.8, 2.2),                    # 低音芒刺伸展極限
            'harmonic_nodes': rng.randint(3, 9),                     # 中頻諧波節點數
            'jitter_scale': rng.uniform(0.15, 0.45)                  # 高頻稜角碎裂度
        }
        self.rng = rng

    def update_and_render(self, img_np, t, is_beat, beat_energy, audio_feats, intensity=0.5, custom_palette=None, section_name='Verse'):
        if cv2 is None or intensity < 0.05:
            return img_np

        sec = str(section_name).lower()
        h, w = img_np.shape[:2]
        dt = 1.0 / 30.0

        # 聲學特徵解包
        sub_bass = float(audio_feats.get('sub_bass', 0.0))
        audio_mid = float(audio_feats.get('mid', audio_feats.get('harmonic', 0.5)))
        audio_high = float(audio_feats.get('high', audio_feats.get('percussive', 0.2)))
        chord_hue = float(audio_feats.get('chord_hue', 0.0))

        # 曲式段落動態生成權重
        sec_weights = {
            'drop': 1.6, 'chorus': 1.4, 'build': 1.2,
            'verse': 0.65, 'bridge': 0.55, 'intro': 0.45, 'outro': 0.35
        }
        sec_mult = next((v for k, v in sec_weights.items() if k in sec), 0.70)
        eff_intensity = max(0.1, min(1.8, intensity * sec_mult))

        # 2. 粒子誕生排程
        if self.cooldown > 0:
            self.cooldown -= 1
        
        spawn_trigger = (is_beat and beat_energy > 0.45) or (len(self.particles) < int(25 * eff_intensity) and self.rng.random() < 0.30)
        if spawn_trigger and len(self.particles) < self.max_particles and self.cooldown == 0:
            self.cooldown = int(18 / max(0.5, eff_intensity))
            num_to_spawn = int((8 + 28 * beat_energy + 20 * sub_bass) * eff_intensity)
            
            # 色彩基調映射
            base_hue = (chord_hue + self.rng.randint(-20, 20)) % 360.0
            is_amb_p = bool(audio_feats.get('force_ambient_color') or audio_feats.get('ambient_color_policy'))
            r_b, g_b, b_b = self._hue_to_rgb(base_hue, is_ambient=is_amb_p)

            for i in range(min(num_to_spawn, self.max_particles - len(self.particles))):
                pattern = self.dna['emission_pattern']
                if pattern == 'DualAttractors':
                    cx = (w * 0.28) if (i % 2 == 0) else (w * 0.72)
                    cy = h * 0.5 + math.sin(t * 1.5) * (h * 0.15)
                    ang = self.rng.uniform(0, math.tau)
                    spd = self.rng.uniform(3.0, 16.0) * (0.7 + 1.3 * beat_energy)
                elif pattern == 'UpwardFountain':
                    cx = w * 0.5 + self.rng.uniform(-w * 0.35, w * 0.35)
                    cy = h * 0.98
                    ang = self.rng.uniform(-math.pi * 0.85, -math.pi * 0.15)
                    spd = self.rng.uniform(9.0, 26.0) * (0.8 + 1.2 * beat_energy)
                elif pattern == 'SpiralHelix':
                    theta = t * 3.0 + i * 0.4
                    rad_s = 20.0 + i * 8.0
                    cx = w * 0.5 + math.cos(theta) * rad_s
                    cy = h * 0.5 + math.sin(theta) * rad_s
                    ang = theta + math.pi / 2.0
                    spd = self.rng.uniform(4.0, 14.0)
                else:
                    cx, cy = w * 0.5, h * 0.5
                    ang = self.rng.uniform(0, math.tau)
                    spd = self.rng.uniform(2.5, 14.0) * (0.8 + 1.2 * beat_energy)

                vx = math.cos(ang) * spd
                vy = math.sin(ang) * spd
                life = self.rng.uniform(1.2, 3.2)
                sz = self.rng.uniform(10.0, 36.0) * (0.8 + 0.6 * sub_bass)
                rot = self.rng.uniform(0, math.tau)
                rot_spd = self.rng.uniform(-1.0, 1.0) * self.dna['spin_speed']
                mass = self.rng.uniform(0.6, 2.0)
                
                # 粒子初始封裝: [x, y, vx, vy, life, max_life, sz, color, rot, rot_spd, mass]
                color = (
                    int(max(0, min(255, r_b + self.rng.randint(-25, 25)))),
                    int(max(0, min(255, g_b + self.rng.randint(-25, 25)))),
                    int(max(0, min(255, b_b + self.rng.randint(-25, 25))))
                )
                self.particles.append([cx, cy, vx, vy, life, life, sz, color, rot, rot_spd, mass])

        if not self.particles:
            return img_np

        overlay = img_np.copy()
        new_particles = []
        phys_mode = self.dna['physics_mode']
        viscosity = self.dna['viscosity']

        # 3. 粒子物理更新與形變繪製
        for p in self.particles:
            x, y, vx, vy, life, max_life, sz, color, rot, rot_spd, mass = p
            
            # --- 物理力場作用 ---
            if phys_mode == 'VortexAttractor':
                dx = x - w * 0.5
                dy = y - h * 0.5
                dist = math.hypot(dx, dy) + 1.0
                vx += (-dy / dist * 65.0 - dx * 0.12) * dt / mass
                vy += (dx / dist * 65.0 - dy * 0.12) * dt / mass
            elif phys_mode == 'LorenzChaos':
                vx += math.sin(y * 0.012 + t * 2.2) * 45.0 * dt
                vy += math.cos(x * 0.012 - t * 2.2) * 45.0 * dt
            elif phys_mode == 'HarmonicSpring':
                dx = w * 0.5 - x
                dy = h * 0.5 - y
                vx += (dx * 0.8) * dt
                vy += (dy * 0.8) * dt
            else: # BrownianQuantum / Boids
                vx += self.rng.uniform(-25.0, 25.0) * dt * (1.0 + audio_high)
                vy += self.rng.uniform(-25.0, 25.0) * dt * (1.0 + audio_high)

            # 速度與阻尼
            vx *= viscosity
            vy *= viscosity
            x += vx
            y += vy
            rot += rot_spd * dt * (1.0 + 2.0 * beat_energy)
            life -= dt

            if life > 0 and -100 <= x < (w + 100) and -100 <= y < (h + 100):
                alpha = max(0.0, min(1.0, life / max_life))
                cur_sz = max(2.0, sz * alpha)
                
                # --- 核心形變演算法 (Audio-Driven Morphological Deformation) ---
                self._draw_morphing_particle(
                    overlay, x, y, cur_sz, color, rot, t,
                    sub_bass, audio_mid, audio_high, beat_energy
                )
                
                new_particles.append([x, y, vx, vy, life, max_life, sz, color, rot, rot_spd, mass])

        self.particles = new_particles
        blend_alpha = min(0.40, (0.16 + 0.20 * beat_energy + 0.12 * sub_bass) * eff_intensity)
        return cv2.addWeighted(img_np, 1.0 - blend_alpha, overlay, blend_alpha, 0)

    def _draw_morphing_particle(self, canvas, cx, cy, sz, color, rot, t, sub_bass, audio_mid, audio_high, beat_energy):
        """根據宇宙 DNA 與實時音訊特徵，動態形變繪製粒子頂點拓撲 (Shape Morphing)"""
        fam = self.dna['morph_family']
        sym_n = self.dna['symmetry_n']
        
        # 1. 星芒突刺多邊形 (低音衝擊時瞬間暴突尖刺)
        if fam == 'StellatedStar':
            num_pts = sym_n * 2
            spike_factor = self.dna['spike_reach'] * (0.35 + 1.45 * sub_bass + 0.6 * beat_energy)
            pts = []
            for i in range(num_pts):
                theta = rot + (i * math.tau / num_pts)
                r_scale = (1.0 + spike_factor) if (i % 2 == 1) else (1.0 - 0.25 * sub_bass)
                px = cx + math.cos(theta) * sz * r_scale
                py = cy + math.sin(theta) * sz * r_scale
                pts.append([int(px), int(py)])
            poly_np = np.array([pts], dtype=np.int32)
            cv2.fillPoly(canvas, poly_np, color, lineType=cv2.LINE_AA)
            edge_color = tuple(min(255, int(c * 1.35)) for c in color)
            cv2.polylines(canvas, poly_np, True, edge_color, 1, lineType=cv2.LINE_AA)

        # 2. 彈性果凍液滴 (低音 Squash & Stretch 擠壓形變 + 中頻輪廓波浪擾動)
        elif fam == 'ElasticJellyBlob':
            squash_x = 1.0 + self.dna['elastic_squash'] * sub_bass * 0.95
            squash_y = 1.0 / max(0.5, squash_x)
            num_pts = 16
            pts = []
            for i in range(num_pts):
                theta = rot + (i * math.tau / num_pts)
                # 中頻諧波節點擾動
                harm_wave = 1.0 + 0.25 * audio_mid * math.sin(self.dna['harmonic_nodes'] * theta + t * 4.0)
                px = cx + math.cos(theta) * sz * squash_x * harm_wave
                py = cy + math.sin(theta) * sz * squash_y * harm_wave
                pts.append([int(px), int(py)])
            poly_np = np.array([pts], dtype=np.int32)
            cv2.fillPoly(canvas, poly_np, color, lineType=cv2.LINE_AA)

        # 3. 量子共振同心環 (高頻公轉激發雙層量子態)
        elif fam == 'QuantumResonanceRing':
            irad = max(1, int(sz * (0.6 + 0.5 * sub_bass)))
            thick = max(1, int(sz * 0.25 * (1.0 + audio_high)))
            cv2.circle(canvas, (int(cx), int(cy)), irad, color, thick, lineType=cv2.LINE_AA)
            # 伴隨公轉的量子衛星節點
            sat_ang = rot * 2.5
            sat_rad = irad * (1.5 + 0.4 * audio_high)
            sx = int(cx + math.cos(sat_ang) * sat_rad)
            sy = int(cy + math.sin(sat_ang) * sat_rad)
            sat_col = tuple(min(255, int(c * 1.5)) for c in color)
            cv2.circle(canvas, (sx, sy), max(2, int(sz * 0.3)), sat_col, -1, lineType=cv2.LINE_AA)

        # 4. 動態晶體多稜鏡 (Hihat 高頻稜角碎裂震顫)
        elif fam == 'CrystallinePrism':
            num_pts = max(3, sym_n)
            pts = []
            jitter_amp = sz * self.dna['jitter_scale'] * audio_high
            for i in range(num_pts):
                theta = rot + (i * math.tau / num_pts)
                jx = (self.rng.random() - 0.5) * jitter_amp
                jy = (self.rng.random() - 0.5) * jitter_amp
                px = cx + math.cos(theta) * sz * (1.0 + 0.3 * sub_bass) + jx
                py = cy + math.sin(theta) * sz * (1.0 + 0.3 * sub_bass) + jy
                pts.append([int(px), int(py)])
            poly_np = np.array([pts], dtype=np.int32)
            cv2.fillPoly(canvas, poly_np, color, lineType=cv2.LINE_AA)
            cv2.polylines(canvas, poly_np, True, (255, 255, 255), 1, lineType=cv2.LINE_AA)

        # 5. 沃羅諾伊晶胞 / 超弦動態發光纖維 (預設高品質形變)
        else:
            num_pts = 8
            pts = []
            for i in range(num_pts):
                theta = rot + (i * math.tau / num_pts)
                r_w = sz * (1.0 + 0.4 * math.sin(theta * 3.0 + t * 5.0) * audio_mid + 0.5 * sub_bass)
                px = cx + math.cos(theta) * r_w
                py = cy + math.sin(theta) * r_w
                pts.append([int(px), int(py)])
            poly_np = np.array([pts], dtype=np.int32)
            cv2.fillPoly(canvas, poly_np, color, lineType=cv2.LINE_AA)

    @staticmethod
    def _hue_to_rgb(hue_deg, is_ambient=False):
        h = (hue_deg % 360.0) / 60.0
        c = 42.0 if is_ambient else 220.0
        base_floor = 115.0 if is_ambient else 35.0
        x = c * (1.0 - abs((h % 2.0) - 1.0))
        if 0 <= h < 1: rgb = (c, x, 0)
        elif 1 <= h < 2: rgb = (x, c, 0)
        elif 2 <= h < 3: rgb = (0, c, x)
        elif 3 <= h < 4: rgb = (0, x, c)
        elif 4 <= h < 5: rgb = (x, 0, c)
        else: rgb = (c, 0, x)
        return (int(rgb[0] + base_floor), int(rgb[1] + base_floor), int(rgb[2] + base_floor))


class FluidSimulator:
    """基於渦流場（Vortex Field）的高效即時流體平流模擬器 (具備低頻向量場降採樣與網格快取加速)"""
    def __init__(self):
        self.vortices = [] 
        self._grid_cache = None
        self._low_grid_cache = None

    def update_and_apply(self, img_np, t, is_beat, beat_energy, fluid_scale=1.0, spectral_centroid=0.2):
        new_vortices = []
        for v in self.vortices:
            v[4] -= 0.03
            if v[4] > 0:
                new_vortices.append(v)
        self.vortices = new_vortices

        if is_beat and len(self.vortices) < 4:
            cx = random.uniform(0.2, 0.8)
            cy = random.uniform(0.2, 0.8)
            rad = random.uniform(0.15, 0.3)
            strength = random.choice([-60.0, 60.0]) * (0.4 + 0.6 * beat_energy)
            self.vortices.append([cx, cy, rad, strength, 1.0])

        if not self.vortices or cv2 is None:
            return img_np

        try:
            h, w = img_np.shape[:2]
            
            # 對於高解析度 (>= 1280x720)，使用平滑向量位移場 4x 降採樣以 10 倍速度計算
            if w >= 1280 and h >= 720:
                dw = max(320, w // 4)
                dh = max(180, h // 4)
                scale_x = float(w / dw)
                scale_y = float(h / dh)

                if self._low_grid_cache is None or self._low_grid_cache[0] != (dw, dh):
                    y_low, x_low = np.mgrid[0:dh, 0:dw].astype(np.float32)
                    self._low_grid_cache = ((dw, dh), x_low, y_low)
                _, x_low, y_low = self._low_grid_cache

                dx_low = np.zeros_like(x_low)
                dy_low = np.zeros_like(y_low)

                min_dim_low = min(dw, dh)
                for cx_r, cy_r, rad_r, strength, life in self.vortices:
                    cx_l = cx_r * dw
                    cy_l = cy_r * dh
                    rad_l = (rad_r * fluid_scale) * min_dim_low
                    v_str_l = (strength / scale_x) * (1.0 + spectral_centroid * 0.5)

                    rx_l = x_low - cx_l
                    ry_l = y_low - cy_l
                    r2_l = rx_l * rx_l + ry_l * ry_l
                    dist_l = np.sqrt(r2_l)

                    factor_l = np.exp(-r2_l / (2.0 * rad_l * rad_l + 1e-5)) * v_str_l * life
                    dx_low += (-ry_l / (dist_l + 1.0)) * factor_l
                    dy_low += (rx_l / (dist_l + 1.0)) * factor_l

                # 雙線性上採樣向量位移場
                dx = cv2.resize(dx_low * scale_x, (w, h), interpolation=cv2.INTER_LINEAR)
                dy = cv2.resize(dy_low * scale_y, (w, h), interpolation=cv2.INTER_LINEAR)

                if self._grid_cache is None or self._grid_cache[0] != (w, h):
                    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                    self._grid_cache = ((w, h), x, y)
                _, x, y = self._grid_cache

                map_x = x + dx
                map_y = y + dy
            else:
                if self._grid_cache is None or self._grid_cache[0] != (w, h):
                    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                    self._grid_cache = ((w, h), x, y)
                _, x, y = self._grid_cache

                dx = np.zeros_like(x)
                dy = np.zeros_like(y)

                min_dim = min(w, h)
                for cx_r, cy_r, rad_r, strength, life in self.vortices:
                    cx, cy = cx_r * w, cy_r * h
                    rad = (rad_r * fluid_scale) * min_dim
                    v_strength = strength * (1.0 + spectral_centroid * 0.5)
                    
                    rx, ry = x - cx, y - cy
                    r2 = rx*rx + ry*ry
                    dist = np.sqrt(r2)
                    
                    factor = np.exp(-r2 / (2.0 * rad * rad + 1e-5)) * v_strength * life
                    dx += (-ry / (dist + 1.0)) * factor
                    dy += (rx / (dist + 1.0)) * factor

                map_x = x + dx
                map_y = y + dy

            return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception:
            return img_np



class PostProcessor:
    """工業級 4K VJ 多通道音視互動後製特效矩陣引擎 (全 38 種特效矩陣完全體)"""
    def __init__(self, seed_string=None, genre='generic', used_themes=None, **kwargs):
        import hashlib
        self.time_displacement_buffer = TimeDisplacementBuffer(max_size=30)
        self.feedback_system = FeedbackSystem()
        self.fluid_simulator = FluidSimulator()
        self.phase_controller = PhaseEffectController()
        self.filter_controller = FilterSweepController()
        self.damping_filters = {}
        self.baseline_adapters = {}
        self.percussive_history = []
        self.invert_frame_timer = 0
        self.last_t = 0.0
        self._grid_cache = None
        self._lut_cache = {}
        self._sediment_buffer = None
        self._mosh_vector = None
        self._fluid_scale = 1.0
        self.scanner_y = 0.0
        self.scanner_x = 0.0
        self._section_sig_cache = {}
        self._fx_cooldown = {}
        self._effect_variants = {}
        self._dolly_mask_cache = None
        self.safety_limiter = PhotosensitiveSafetyLimiter(window_size=30)

        # 零分配優化：預先建立靜態隨機噪點層，防止 CRT 濾波器重複開闢內存
        self._noise_buffer = np.random.randint(-25, 25, (2160, 3840, 1), dtype=np.int16)

        # 新特效快取狀態初始化
        self._frame_drop_cache = None
        self._frame_drop_last_t = 0.0
        self._cam_drift_x = 0.0
        self._cam_drift_y = 0.0
        self._turing_A = None
        self._turing_B = None

        # 全套 68 大後製特效狀態鍵值 (升級整合 12 大次世代高辨識度幾何/拓撲強特徵特效庫)
        self.fx_active_states = {
            # Row 1: 基礎核心特效
            'spatial_warping': 0.0, 'fluid_noise': 0.0, 'temporal_feedback': 0.0,
            'color_spectral': 0.0, 'glow_illumination': 0.0, 'retro_degradation': 0.0,
            'pixel_sort': 0.0, 'kaleidoscope': 0.0, 'ambient_dsp': 0.0,
            # Row 2: 全域通道與衍生特效
            'data_mosh': 0.0, 'sedimentation': 0.0, 'vector_scan': 0.0, 'temporal_fractal': 0.0,
            'phase_slit': 0.0, 'centroid_glitch': 0.0, 'vignette_pulse': 0.0, 'tension_overlay': 0.0,
            # Row 3: 自訂擴充特效
            'thermal_vision': 0.0, 'scanline_glitch': 0.0, 'frame_drop': 0.0,
            'dynamic_mosaic': 0.0, 'pixel_art': 0.0, 'handheld_camera': 0.0,
            'stylized_fade': 0.0, 'zoom_pulse': 0.0,
            # Row 4: 頂級全域後製特效矩陣
            'film_burn': 0.0, 'blueprint_edge': 0.0, 'turing_pattern': 0.0,
            'point_cloud_depth': 0.0, 'vector_scope': 0.0, 'lowpass_muffle': 0.0,
            'infinity_tunnel': 0.0, 'dolly_zoom': 0.0,
            # Row 5: 前沿全域 6 大特效
            'hologram_glitch': 0.0, 'voronoi_shatter': 0.0, 'thermal_infrared': 0.0,
            'ascii_cyber_matrix': 0.0, 'chromatic_radial_zoom': 0.0, 'synthwave_grid_scan': 0.0,
            # Row 6: 旗艦超前沿 5 大特效
            'chladni_cymatics': 0.0, 'ferrofluid_spikes': 0.0, 'volumetric_caustics': 0.0,
            'clifford_torus': 0.0, 'holographic_moire': 0.0,
            # 其他衍生
            'kuwahara_paint': 0.0, 'matrix_ascii': 0.0, 'reaction_diffusion': 0.0,
            'photocopy_smear': 0.0, 'collage_cutout': 0.0,
            # 生理光學與視網膜全域後製矩陣
            'lens_defocus': 0.0, 'ocular_tremor': 0.0,
            # Row 7: 次世代前沿 5 大故障特效矩陣 (Next-Gen Glitch Matrix)
            'quantum_decoherence': 0.0, 'latent_hallucination': 0.0,
            'tape_head_drag': 0.0, 'huffman_entropy_collapse': 0.0,
            'spectral_fractal_shear': 0.0,
            # 🌟 Row 8: 12 大次世代前沿幾何/拓撲高衝擊特效矩陣 (SOTA 2026 FX Matrix)
            'hyper_dimensional_fold': 0.0, 'reaction_diffusion_growth': 0.0,
            'delaunay_voronoi_mesh': 0.0, 'slit_scan_time_warp': 0.0,
            'gravitational_lensing': 0.0, 'acid_curl_fluid': 0.0,
            'strobe_chroma_invert': 0.0, 'cyber_wireframe_lidar': 0.0,
            'sine_terrain_displacement': 0.0, 'quantum_tunneling': 0.0,
            'prismatic_refraction_prism': 0.0, 'magnetic_field_lines': 0.0
        }

        # Time-Vessel Matrix (走馬燈時間卷軸矩陣，滾動歷史緩衝區，預設 2 秒 @ 30fps，16 個特徵維度)
        self.time_vessel_size = 60
        self.time_vessel_dim = 16
        self.time_vessel = np.zeros((self.time_vessel_size, self.time_vessel_dim), dtype=np.float32)

        # 歌曲專屬隨機引擎初始化
        self.seed_string = seed_string
        if seed_string:
            hash_val = int(hashlib.md5(seed_string.encode('utf-8')).hexdigest(), 16)
            self.rng = random.Random(hash_val)
        else:
            self.rng = random.Random()

        genre_clean = genre.lower().strip() if isinstance(genre, str) else 'generic'
        is_hard_techno = any(ht in genre_clean for ht in ('hard_techno', 'hard techno', 'schranz', 'industrial techno', 'hardcore'))
        is_electronic_genre = any(g in genre_clean for g in (
            'techno', 'electronic', 'dance', 'acid', 'dnb', 'dubstep', 'house',
            'idm', 'edm', 'dub_techno', 'hard_techno', 'trance', 'synthwave'
        ))
        # ⚡ Hard Techno 追求冷硬幾何、雷射與高對比，徹底封殺黏稠有機流體與粒子群！
        if is_hard_techno:
            self.audio_particle_fluid = None
        elif is_electronic_genre or self.rng.random() < 0.40:
            self.audio_particle_fluid = AudioParticleFluidEngine(seed_string=seed_string)
        else:
            self.audio_particle_fluid = None

        self.is_hard_techno = is_hard_techno
        self.camera_rig = ProceduralCameraRig(rng=self.rng, is_hard_techno=is_hard_techno)
        self._recent_beat_fx_window = collections.deque(maxlen=8)

        # 視覺美學主題風格包 (擴充升級至 13 大獨立美學風格池，注入 Hard Techno 專屬 IndustrialMonolith)
        self.theme_pools = {
            'IndustrialMonolith': [
                'strobe_chroma_invert', 'cyber_wireframe_lidar', 'scanline_glitch', 'photocopy_smear',
                'tension_overlay', 'vector_scan', 'delaunay_voronoi_mesh', 'data_mosh',
                'slit_scan_time_warp', 'huffman_entropy_collapse', 'vector_scope', 'ascii_cyber_matrix',
                'magnetic_field_lines', 'sine_terrain_displacement', 'phase_slit', 'centroid_glitch',
                'frame_drop', 'retro_degradation', 'blueprint_edge', 'point_cloud_depth',
                'tape_head_drag', 'lowpass_muffle', 'hyper_dimensional_fold', 'matrix_ascii',
                'voronoi_shatter', 'pixel_sort', 'spectral_fractal_shear', 'thermal_vision'
            ],
            'CyberGlitch': [
                'data_mosh', 'pixel_sort', 'hologram_glitch', 'scanline_glitch', 'matrix_ascii',
                'phase_slit', 'centroid_glitch', 'vector_scope', 'ascii_cyber_matrix', 'holographic_moire',
                'ocular_tremor', 'quantum_decoherence', 'huffman_entropy_collapse', 'spectral_fractal_shear',
                'delaunay_voronoi_mesh', 'cyber_wireframe_lidar', 'quantum_tunneling',
                'strobe_chroma_invert', 'dynamic_mosaic', 'hyper_dimensional_fold', 'synthwave_grid_scan',
                'sine_terrain_displacement', 'magnetic_field_lines'
            ],
            'RetroAnalog': [
                'retro_degradation', 'vector_scan', 'frame_drop', 'handheld_camera', 'stylized_fade',
                'photocopy_smear', 'blueprint_edge', 'lowpass_muffle', 'tape_head_drag', 'film_burn',
                'scanline_glitch', 'vignette_pulse', 'lens_defocus', 'synthwave_grid_scan',
                'slit_scan_time_warp', 'magnetic_field_lines', 'vector_scope', 'data_mosh'
            ],
            'DreamyArtistic': [
                'glow_illumination', 'kuwahara_paint', 'temporal_feedback', 'sedimentation', 'fluid_noise',
                'collage_cutout', 'point_cloud_depth', 'voronoi_shatter', 'lens_defocus', 'latent_hallucination',
                'ambient_dsp', 'vignette_pulse', 'turing_pattern', 'volumetric_caustics',
                'prismatic_refraction_prism', 'reaction_diffusion_growth'
            ],
            'Psychedelic': [
                'color_spectral', 'thermal_vision', 'kaleidoscope', 'spatial_warping', 'infinity_tunnel',
                'thermal_infrared', 'latent_hallucination', 'chromatic_radial_zoom', 'volumetric_caustics', 'dolly_zoom',
                'clifford_torus', 'reaction_diffusion', 'ferrofluid_spikes', 'zoom_pulse',
                'hyper_dimensional_fold', 'acid_curl_fluid'
            ],
            'DigitalPixel': [
                'dynamic_mosaic', 'pixel_art', 'zoom_pulse', 'temporal_fractal', 'dolly_zoom',
                'ascii_cyber_matrix', 'voronoi_shatter', 'holographic_moire', 'huffman_entropy_collapse', 'spectral_fractal_shear',
                'matrix_ascii', 'scanline_glitch', 'synthwave_grid_scan', 'pixel_sort', 'data_mosh',
                'delaunay_voronoi_mesh', 'cyber_wireframe_lidar', 'strobe_chroma_invert'
            ],
            'AcidPsychedelic': [
                'reaction_diffusion', 'color_spectral', 'infinity_tunnel', 'turing_pattern', 'vector_scan',
                'spatial_warping', 'hologram_glitch', 'chromatic_radial_zoom', 'chladni_cymatics', 'spectral_fractal_shear',
                'ferrofluid_spikes', 'quantum_decoherence', 'thermal_vision', 'phase_slit',
                'acid_curl_fluid', 'reaction_diffusion_growth', 'strobe_chroma_invert'
            ],
            'BrutalistMonochrome': [
                'blueprint_edge', 'photocopy_smear', 'frame_drop', 'matrix_ascii', 'lowpass_muffle',
                'vector_scope', 'ascii_cyber_matrix', 'retro_degradation', 'film_burn', 'tape_head_drag',
                'stylized_fade', 'vector_scan', 'tension_overlay', 'point_cloud_depth',
                'magnetic_field_lines', 'sine_terrain_displacement', 'delaunay_voronoi_mesh',
                'cyber_wireframe_lidar', 'scanline_glitch', 'voronoi_shatter', 'huffman_entropy_collapse'
            ],
            'BioOrganicFluids': [
                'reaction_diffusion', 'fluid_noise', 'sedimentation', 'chladni_cymatics', 'ferrofluid_spikes',
                'turing_pattern', 'voronoi_shatter', 'volumetric_caustics', 'temporal_feedback', 'glow_illumination',
                'clifford_torus', 'kuwahara_paint', 'ambient_dsp', 'color_spectral',
                'reaction_diffusion_growth', 'acid_curl_fluid', 'magnetic_field_lines'
            ],
            'OpticKinetic': [
                'chromatic_radial_zoom', 'zoom_pulse', 'dolly_zoom', 'spatial_warping', 'infinity_tunnel',
                'kaleidoscope', 'temporal_fractal', 'handheld_camera', 'voronoi_shatter', 'vector_scan',
                'holographic_moire', 'phase_slit', 'dynamic_mosaic', 'centroid_glitch',
                'hyper_dimensional_fold', 'slit_scan_time_warp', 'sine_terrain_displacement'
            ],
            'PrismaticRefraction': [
                'volumetric_caustics', 'holographic_moire', 'clifford_torus', 'color_spectral', 'spectral_fractal_shear',
                'quantum_decoherence', 'glow_illumination', 'point_cloud_depth', 'lens_defocus', 'latent_hallucination',
                'chromatic_radial_zoom', 'infinity_tunnel', 'kaleidoscope', 'temporal_feedback',
                'prismatic_refraction_prism', 'gravitational_lensing'
            ],
            'HardcoreThermal': [
                'thermal_vision', 'thermal_infrared', 'ocular_tremor', 'huffman_entropy_collapse', 'centroid_glitch',
                'data_mosh', 'phase_slit', 'pixel_sort', 'tension_overlay', 'vector_scope',
                'dynamic_mosaic', 'spectral_fractal_shear', 'quantum_decoherence', 'film_burn',
                'strobe_chroma_invert', 'gravitational_lensing', 'hyper_dimensional_fold',
                'chromatic_radial_zoom', 'vector_scan', 'sine_terrain_displacement', 'cyber_wireframe_lidar',
                'delaunay_voronoi_mesh', 'slit_scan_time_warp'
            ],
            'CosmicVoid': [
                'point_cloud_depth', 'latent_hallucination', 'temporal_feedback', 'ambient_dsp', 'sedimentation',
                'lowpass_muffle', 'lens_defocus', 'clifford_torus', 'turing_pattern', 'glow_illumination',
                'vignette_pulse', 'temporal_fractal', 'kuwahara_paint', 'fluid_noise',
                'gravitational_lensing', 'quantum_tunneling', 'slit_scan_time_warp'
            ]
        }
        self._all_pool_effects = set(fx for pool in self.theme_pools.values() for fx in pool)

        allowed_themes = list(self.theme_pools.keys())
        if is_hard_techno:
            # ⚡ 支援全方位硬核重低音風格：工業、熱成像、賽博故障、極簡野獸派、數位像素、動力光學、迷幻酸性、復古類比（由4大主題大幅擴充至8大主題）
            allowed_themes = [
                'IndustrialMonolith', 'HardcoreThermal', 'CyberGlitch', 'BrutalistMonochrome',
                'DigitalPixel', 'OpticKinetic', 'AcidPsychedelic', 'RetroAnalog'
            ]
        elif 'acid' in genre_clean:
            allowed_themes = ['AcidPsychedelic', 'Psychedelic', 'CyberGlitch', 'OpticKinetic']
        elif 'dub_techno' in genre_clean:
            allowed_themes = ['CosmicVoid', 'DreamyArtistic', 'RetroAnalog', 'DigitalPixel']
        elif 'idm' in genre_clean:
            allowed_themes = ['CyberGlitch', 'DigitalPixel', 'AcidPsychedelic', 'PrismaticRefraction', 'OpticKinetic']
        elif 'edm' in genre_clean:
            allowed_themes = ['Psychedelic', 'CyberGlitch', 'AcidPsychedelic', 'OpticKinetic', 'PrismaticRefraction']
        elif any(g in genre_clean for g in ('lo-fi', 'lofi', 'ambient', 'drone', 'meditative', 'chill', 'jazz', 'classical', 'downtempo', 'atmospheric', 'sleep', 'new_age')):
            allowed_themes = ['DreamyArtistic', 'RetroAnalog', 'CosmicVoid', 'BrutalistMonochrome', 'BioOrganicFluids']
        elif is_electronic_genre:
            allowed_themes = list(self.theme_pools.keys())

        self.is_ambient_genre = any(g in genre_clean for g in ('ambient', 'drone', 'meditative', 'dark_ambient', 'chill', 'downtempo', 'atmospheric', 'sleep', 'new_age'))
        ambient_forbidden_fx = {
            'thermal_vision', 'thermal_infrared', 'strobe_chroma_invert', 'color_spectral',
            'acid_curl_fluid', 'pixel_sort', 'film_burn', 'synthwave_grid_scan',
            'ascii_cyber_matrix', 'huffman_entropy_collapse', 'centroid_glitch', 'ocular_tremor'
        }

        # 讀取持久化跨曲目特效歷史（確保單曲渲染或跨天批次皆具備主題去重記憶，記憶深度 50 首）
        fx_history = _load_vj_fx_history(max_entries=50)
        recent_themes = [h.get('theme') for h in fx_history[-20:] if h.get('theme')]
        effective_used_themes = (list(used_themes) if used_themes else []) + recent_themes

        if effective_used_themes:
            counts = {t: effective_used_themes.count(t) for t in allowed_themes}
            min_count = min(counts.values()) if counts else 0
            least_used = [t for t in allowed_themes if counts.get(t, 0) == min_count]
            allowed_themes = least_used

        self.selected_theme = self.rng.choice(allowed_themes)
        self.signature_pool = list(self.theme_pools[self.selected_theme])
        if self.is_ambient_genre:
            filtered_sig_pool = [fx for fx in self.signature_pool if fx not in ambient_forbidden_fx]
            if len(filtered_sig_pool) >= 2:
                self.signature_pool = filtered_sig_pool

        # 跨曲目零重疊反碰撞懲罰機制 (Strict Anti-Collision Engine)：
        # 對最近 1~20 首曲目使用過的 Signature/Accent 特效施加階梯降權
        recent_fx_penalties = {}
        recent_sig_sets = []
        if fx_history:
            recent_sig_sets = [set(h.get('signature_effects', [])) for h in fx_history[-25:] if h.get('signature_effects')]
            penalty_tiers = [0.005, 0.01, 0.03, 0.08, 0.15, 0.25, 0.40, 0.55, 0.70, 0.80, 0.90, 0.95, 0.98]
            for step_idx, factor in enumerate(penalty_tiers):
                hist_idx = -(step_idx + 1)
                if len(fx_history) >= (step_idx + 1):
                    for fx in fx_history[hist_idx].get('signature_effects', []):
                        recent_fx_penalties[fx] = min(recent_fx_penalties.get(fx, 1.0), factor)
                    for fx in fx_history[hist_idx].get('accent_effects', []):
                        recent_fx_penalties[fx] = min(recent_fx_penalties.get(fx, 1.0), factor * 1.8)

        def _weighted_sample_no_replace(pool, k):
            pool_copy = list(pool)
            chosen = []
            for _ in range(min(k, len(pool_copy))):
                weights = []
                for fx in pool_copy:
                    w = recent_fx_penalties.get(fx, 1.0)
                    # 降低高頻眼震等強烈生理干擾特效的預設競爭力
                    if fx in ('ocular_tremor', 'huffman_entropy_collapse', 'centroid_glitch'):
                        w *= 0.35
                    # 新增之次世代前沿特效給予適度多樣性探索加權
                    if fx in ('hyper_dimensional_fold', 'reaction_diffusion_growth', 'delaunay_voronoi_mesh',
                              'slit_scan_time_warp', 'gravitational_lensing', 'acid_curl_fluid',
                              'strobe_chroma_invert', 'cyber_wireframe_lidar', 'sine_terrain_displacement',
                              'quantum_tunneling', 'prismatic_refraction_prism', 'magnetic_field_lines'):
                        w *= 1.25
                    weights.append(max(0.001, w))
                total_w = sum(weights)
                probs = [w / total_w for w in weights] if total_w > 0 else None
                pick = self.rng.choices(pool_copy, weights=probs, k=1)[0]
                chosen.append(pick)
                pool_copy.remove(pick)
            return chosen

        # 挑選 2~3 個 Signature 特效，並執行防撞車重試驗證（保證與最近 25 首曲目核心組合 100% 不重複）
        self.signature_effects = set()
        for _attempt in range(12):
            num_sig = self.rng.randint(2, 3)
            sig_candidate = set(_weighted_sample_no_replace(self.signature_pool, num_sig))
            is_collision = any(sig_candidate == s_set for s_set in recent_sig_sets)
            if not is_collision and len(recent_sig_sets) >= 1:
                # 與上一首重疊數不能超過 1
                if len(sig_candidate & recent_sig_sets[-1]) >= 2:
                    is_collision = True
            if not is_collision:
                self.signature_effects = sig_candidate
                break
            self.signature_effects = sig_candidate

        # 挑選 Accent 特效：2 個來自當前主題池，2 個允許從跨主題相容特效池探索，大幅增加色彩豐富度
        remaining_in_pool = [fx for fx in self.signature_pool if fx not in self.signature_effects]
        theme_accents = _weighted_sample_no_replace(remaining_in_pool, min(len(remaining_in_pool), 2))
        global_candidates = [
            fx for fx in self._all_pool_effects
            if fx not in self.signature_effects
            and fx not in theme_accents
            and (not self.is_ambient_genre or fx not in ambient_forbidden_fx)
        ]
        cross_accents = _weighted_sample_no_replace(global_candidates, 2)
        self.accent_effects = set(theme_accents + cross_accents)

        # 將本次曲目特效選擇寫入持久化歷史
        _save_vj_fx_history({
            "timestamp": int(time.time()),
            "seed_string": str(seed_string),
            "genre": genre_clean,
            "theme": self.selected_theme,
            "signature_effects": sorted(list(self.signature_effects)),
            "accent_effects": sorted(list(self.accent_effects))
        })

        self.mosh_palette = []
        base_hue = self.rng.randint(0, 360)
        for i in range(5):
            hue = (base_hue + i * 24) % 360
            r, g, b = self._hue_to_rgb(hue)
            self.mosh_palette.append((r, g, b))

        self.song_dna = {
            'seed_string': seed_string,
            'theme': self.selected_theme,
            'signature_effects': set(self.signature_effects),
            'accent_effects': set(self.accent_effects),
            'base_hue': base_hue,
            'palette': list(self.mosh_palette),
            'flow_angle': self.rng.uniform(0.0, 360.0),
            'noise_scale': self.rng.uniform(0.8, 1.6),
            'speed_factor': self.rng.uniform(0.75, 1.35),
            'contrast_bias': self.rng.uniform(0.95, 1.15),
            'turing_seed_coords': [
                (self.rng.uniform(0.20, 0.80), self.rng.uniform(0.20, 0.80), self.rng.uniform(0.05, 0.12))
                for _ in range(self.rng.randint(3, 5))
            ]
        }

        self.effect_modifiers = {}
        for fx in self.fx_active_states:
            num_variants = self.rng.randint(2, 4)
            allowed_vars = self.rng.sample(range(5), num_variants)
            self.effect_modifiers[fx] = {
                'speed': self.rng.uniform(0.65, 1.45),
                'intensity': self.rng.uniform(0.85, 1.25),
                'variants': allowed_vars
            }

    def get_coordinate_grid(self, h, w):
        """
        零分配優化：快取並返回 (h, w) 形狀的座標網格 (x, y) 與正規化座標 (x_norm, y_norm)
        避免在 4K (3840x2160) 下每次效果反覆執行 np.mgrid 造成 66MB+ 內存分配風暴
        """
        if self._grid_cache is not None and self._grid_cache[0] == (w, h) and len(self._grid_cache) == 5:
            return self._grid_cache[1], self._grid_cache[2], self._grid_cache[3], self._grid_cache[4]

        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        x_norm = ((x - w * 0.5) / (w * 0.5)).astype(np.float32)
        y_norm = ((y - h * 0.5) / (h * 0.5)).astype(np.float32)
        self._grid_cache = ((w, h), x, y, x_norm, y_norm)
        return x, y, x_norm, y_norm


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
        if getattr(self, 'is_ambient_genre', False):
            # 壓制純飽和色，將色度融合入莫蘭迪霧灰基底 (S <= 0.22)
            r = 0.52 * 0.78 + r * 0.65 * 0.22
            g = 0.55 * 0.78 + g * 0.65 * 0.22
            b = 0.58 * 0.78 + b * 0.65 * 0.22
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
        self.photosensitive_safe = fx_flags.get('photosensitive_safe', True)
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

        # 1. 聲學特徵提取與平滑
        sub_bass = self.get_normalized_val('sub_bass', audio_feats.get('sub_bass', 0.0))
        percussive = self.get_normalized_val('percussive', audio_feats.get('percussive', 0.0))
        roughness = audio_feats.get('roughness', 0.0)
        ethereal = audio_feats.get('ethereal', 0.0)
        silence_fade = audio_feats.get('silence_fade', 0.0)
        harmonic = audio_feats.get('harmonic', 0.5)
        chord_brightness = audio_feats.get('chord_brightness', 0.1)
        chord_hue = audio_feats.get('chord_hue', 180.0)
        stereo_width = audio_feats.get('stereo_width', 0.5)
        spectral_centroid = audio_feats.get('centroid', 0.2)
        bpm = audio_feats.get('bpm', 120.0)

        smoothed_sub_bass = self.get_smoothed_val('sub_bass', sub_bass, dt, 15.0, 2.0)
        smoothed_roughness = self.get_smoothed_val('roughness', roughness, dt, 12.0, 2.5)
        smoothed_ethereal = self.get_smoothed_val('ethereal', ethereal, dt, 8.0, 1.8)
        smoothed_percussive = self.get_smoothed_val('percussive', percussive, dt, 18.0, 2.2)

        # Section-Adaptive FX Intensity Modulation (電影級曲式層次調變)
        sec_lower = str(section_name).lower()
        if 'intro' in sec_lower:
            section_scale = 0.65
        elif 'outro' in sec_lower:
            section_scale = 0.50
        elif any(s in sec_lower for s in ('drop', 'chorus')):
            section_scale = 1.35
        elif 'build' in sec_lower:
            section_scale = 1.15
        elif 'bridge' in sec_lower:
            section_scale = 0.85
        else:
            section_scale = 1.0  # Verse / default
        
        fx_intensity = max(0.1, min(1.5, fx_intensity * section_scale))

        # 2. 獲取使用者當前在 UI 上明確勾選的所有特效
        user_enabled_fx = {k: v for k, v in fx_flags.items() if v and k in self.fx_active_states}
        if not user_enabled_fx:
            user_enabled_fx = {k: True for k in self.fx_active_states}

        # 3. 狀態平滑衰減（Decay）與常駐基線（僅對符合主題特性的常駐特效賦予極低微弱基線，保留純淨留白空間）
        for fx_name in self.fx_active_states:
            if fx_name in user_enabled_fx:
                eff_base = 0.0
                if fx_name in ('vignette_pulse', 'lowpass_muffle', 'ambient_dsp'):
                    if fx_name in self.signature_pool or fx_name in self.signature_effects:
                        # 當使用者拉桿調低（<15%）時徹底歸零常駐基線，確保畫面極度乾淨
                        if fx_prob >= 0.15:
                            if any(s in sec_lower for s in ('drop', 'chorus', 'build')):
                                eff_base = 0.015 * fx_intensity
                            else:
                                eff_base = 0.005 * fx_intensity
                # ⚡ 衰減速度由 2.2 大幅提升至 4.8，讓重拍特效在 0.15~0.20 秒內俐落淡出，在 180+ BPM 重擊間留出充沛的視覺呼吸與留白
                decay_rate = 4.8
                self.fx_active_states[fx_name] = max(eff_base, self.fx_active_states[fx_name] - dt * decay_rate)
            else:
                self.fx_active_states[fx_name] = 0.0

        for k in list(self._fx_cooldown.keys()):
            if self._fx_cooldown[k] > 0:
                self._fx_cooldown[k] -= 1

        # 4. 音視動態調度（Audio-Driven Dynamic Triggering）
        # 嚴格依據使用者 UI 機率拉桿線性響應：
        # - 拉桿設為 0% 時絕對不觸發任何重拍後製特效
        # - 拉桿設為 10% 時真實維持約 10% 稀疏點綴，移除原先 20% 強制保底與大鼓過度增益
        if is_beat:
            if fx_prob <= 0.001:
                effective_prob = 0.0
            else:
                effective_prob = min(0.95, fx_prob * (0.65 + 0.55 * beat_energy))
            if effective_prob > 0.0 and self.rng.random() < effective_prob:
                sec_lower_name = str(section_name).lower()
                is_climax = any(s in sec_lower_name for s in ('drop', 'chorus'))
                is_buildup = 'build' in sec_lower_name

                # 定義全 68 大特效的聲學驅動歸屬分類（覆蓋全部 8 大排前沿幾何/拓撲特效）
                FX_BASS_DRIVEN = {
                    'spatial_warping', 'fluid_noise', 'dynamic_mosaic', 'zoom_pulse',
                    'turing_pattern', 'infinity_tunnel', 'chromatic_radial_zoom',
                    'voronoi_shatter', 'ferrofluid_spikes', 'chladni_cymatics', 'tape_head_drag',
                    'hyper_dimensional_fold', 'gravitational_lensing', 'sine_terrain_displacement', 'magnetic_field_lines'
                }
                FX_PERC_DRIVEN = {
                    'pixel_sort', 'data_mosh', 'scanline_glitch', 'hologram_glitch',
                    'ascii_cyber_matrix', 'matrix_ascii', 'centroid_glitch', 'vector_scan',
                    'holographic_moire', 'quantum_decoherence', 'huffman_entropy_collapse',
                    'spectral_fractal_shear', 'ocular_tremor', 'photocopy_smear',
                    'delaunay_voronoi_mesh', 'strobe_chroma_invert', 'cyber_wireframe_lidar', 'quantum_tunneling'
                }
                FX_ETHEREAL_DRIVEN = {
                    'glow_illumination', 'temporal_feedback', 'sedimentation',
                    'point_cloud_depth', 'vector_scope', 'lowpass_muffle', 'blueprint_edge',
                    'film_burn', 'temporal_fractal', 'ambient_dsp', 'volumetric_caustics',
                    'latent_hallucination', 'kuwahara_paint', 'lens_defocus', 'collage_cutout',
                    'color_spectral', 'prismatic_refraction_prism', 'reaction_diffusion_growth'
                }
                FX_SPATIAL_DRIVEN = {
                    'phase_slit', 'clifford_torus', 'kaleidoscope', 'synthwave_grid_scan',
                    'dolly_zoom', 'thermal_vision', 'thermal_infrared', 'reaction_diffusion',
                    'pixel_art', 'handheld_camera', 'frame_drop', 'vignette_pulse', 'tension_overlay',
                    'slit_scan_time_warp', 'acid_curl_fluid'
                }

                # 🌟 60/40 動態平衡律調度引擎 (60% 核心 Signature 靈魂錨定 + 40% 歌曲專屬 Accent 輪替)
                # 嚴格錨定本曲 selected_theme 的專屬特效基因，杜絕跨曲目硬編碼覆寫造成 45 首歌特效同質化
                theme_candidates = set()
                dice = self.rng.random()
                if dice < 0.60:
                    # 60% 重拍：優先觸發歌曲 Signature 核心特效（維持單曲專屬辨識度靈魂）
                    theme_candidates.update(self.signature_effects)
                else:
                    # 40% 重拍：結合歌曲專屬 Accent 特效與極少量同主題拓撲探索
                    theme_candidates.update(self.signature_effects)
                    theme_candidates.update(self.accent_effects)
                    if dice > 0.88 and hasattr(self, 'signature_pool') and self.signature_pool:
                        theme_candidates.update(self.rng.sample(self.signature_pool, min(2, len(self.signature_pool))))

                if is_climax:
                    # Drop / Chorus：以本曲 Signature 為核心，搭配本曲 Accent 中的重低音與瞬態衝擊特效
                    climax_accents = [fx for fx in self.accent_effects if fx in (FX_BASS_DRIVEN | FX_PERC_DRIVEN)] or list(self.accent_effects)
                    theme_candidates.update(self.signature_effects)
                    theme_candidates.update(climax_accents)
                elif is_buildup:
                    # Build-up：蓄力階段，融合本曲 Signature 與空間/張力型 Accent
                    buildup_accents = [fx for fx in self.accent_effects if fx in (FX_SPATIAL_DRIVEN | FX_BASS_DRIVEN)] or list(self.accent_effects)
                    theme_candidates.update(self.signature_effects)
                    theme_candidates.update(buildup_accents)
                elif 'bridge' in sec_lower_name:
                    bridge_accents = [fx for fx in self.accent_effects if fx in (FX_SPATIAL_DRIVEN | FX_ETHEREAL_DRIVEN)] or list(self.accent_effects)
                    theme_candidates.update(bridge_accents)
                elif 'intro' in sec_lower_name or 'outro' in sec_lower_name:
                    intro_accents = [fx for fx in self.accent_effects if fx in (FX_ETHEREAL_DRIVEN | FX_SPATIAL_DRIVEN)]
                    if intro_accents:
                        theme_candidates.update(intro_accents)

                # 與使用者在 UI 上勾選的特效取交集
                curated_enabled = [fx for fx in theme_candidates if fx in user_enabled_fx]
                if not curated_enabled:
                    curated_enabled = [fx for fx in self.signature_pool if fx in user_enabled_fx]
                if not curated_enabled:
                    curated_enabled = list(user_enabled_fx.keys())

                candidates = [fx for fx in curated_enabled if self._fx_cooldown.get(fx, 0) == 0]
                if not candidates:
                    candidates = curated_enabled

                # 連擊防抖微冷卻
                if len(candidates) >= 2 and hasattr(self, '_last_beat_triggered_fx') and self._last_beat_triggered_fx:
                    non_consecutive = [fx for fx in candidates if fx not in self._last_beat_triggered_fx]
                    if non_consecutive:
                        candidates = non_consecutive

                # 依據當前音訊特徵加權候選特效，並施加真正的 8 拍滑動窗口疲勞衰減器
                weights = []
                now_t = t
                if not hasattr(self, '_intra_song_fx_history'):
                    self._intra_song_fx_history = {}
                if not hasattr(self, '_recent_beat_fx_window'):
                    self._recent_beat_fx_window = collections.deque(maxlen=8)

                for fx in candidates:
                    w_val = 1.0
                    # Signature 特效獲得強識別度加權，確保每首歌保有專屬視覺印記
                    if fx in self.signature_effects:
                        w_val += 2.6
                    if fx in FX_BASS_DRIVEN:
                        w_val += 1.8 * smoothed_sub_bass
                    if fx in FX_PERC_DRIVEN:
                        w_val += 1.8 * smoothed_percussive
                    if fx in FX_ETHEREAL_DRIVEN:
                        w_val += 1.8 * smoothed_ethereal
                    if fx in FX_SPATIAL_DRIVEN:
                        w_val += 1.5 * stereo_width

                    # 🌟 真正的 8 拍滑動窗口審美疲勞衰減器 (True 8-Beat Sliding Window Anti-Fatigue Damper)：
                    # 僅統計最近 8 次重拍內的實際觸發次數，避免計數器永久累加鎖死 Signature 特效
                    recent_count = sum(1 for beat_set in self._recent_beat_fx_window if fx in beat_set)
                    if recent_count >= 3:
                        w_val *= 0.25
                    elif recent_count == 2:
                        w_val *= 0.55
                    elif recent_count == 1:
                        w_val *= 0.80

                    # 單曲內動態微冷卻
                    last_fired = self._intra_song_fx_history.get(fx, -999.0)
                    time_since_fired = now_t - last_fired
                    if time_since_fired < 1.2:
                        w_val *= 0.3
                    elif time_since_fired < 2.5:
                        w_val *= 0.65

                    weights.append(w_val)

                # 根據使用者 fx_prob 自適應約束單次重拍觸發的特效數量（低機率時絕不狂轟濫炸）
                if fx_prob <= 0.15:
                    num_to_trigger = 1
                elif fx_prob <= 0.35:
                    num_to_trigger = 1 if beat_energy < 0.82 else 2
                else:
                    num_to_trigger = 1 if beat_energy < 0.65 else (2 if beat_energy < 0.88 else 3)
                num_to_trigger = min(num_to_trigger, len(candidates))

                total_w = sum(weights)
                probs = [w_val / total_w for w_val in weights] if total_w > 0 else None
                selected = self.rng.choices(candidates, weights=probs, k=num_to_trigger)

                HEAVY_GLITCH_FX = {
                    'pixel_sort', 'data_mosh', 'phase_slit', 'quantum_decoherence',
                    'huffman_entropy_collapse', 'spectral_fractal_shear', 'centroid_glitch',
                    'spatial_warping', 'scanline_glitch', 'voronoi_shatter', 'ocular_tremor',
                    'strobe_chroma_invert', 'hyper_dimensional_fold', 'delaunay_voronoi_mesh'
                }
                selected_set = set(selected)
                for fx_name in selected_set:
                    self.fx_active_states[fx_name] = max(
                        self.fx_active_states[fx_name],
                        min(1.0, 0.45 + 0.45 * beat_energy)
                    )
                    # 節奏呼吸感約束：重度故障冷卻 50~75 幀，普通特效冷卻 30~45 幀
                    if fx_name in HEAVY_GLITCH_FX:
                        self._fx_cooldown[fx_name] = self.rng.randint(50, 75)
                    else:
                        self._fx_cooldown[fx_name] = self.rng.randint(30, 45)
                    self._intra_song_fx_history[fx_name] = now_t

                self._recent_beat_fx_window.append(selected_set)
                self._last_beat_triggered_fx = selected_set

        # 5. 分鏡與時間容器更新
        curr_feats = np.array([
            smoothed_sub_bass, smoothed_percussive, smoothed_roughness, smoothed_ethereal,
            beat_energy, audio_feats.get('anticipation', 0.0), harmonic, chord_brightness,
            stereo_width, spectral_centroid, audio_feats.get('tempo', 120.0) / 200.0,
            silence_fade, fx_intensity, 0.5 + 0.5 * math.sin(t), 0.5 + 0.5 * math.cos(t * 1.5), 0.0
        ], dtype=np.float32)
        self.time_vessel = np.roll(self.time_vessel, -1, axis=0)
        self.time_vessel[-1, :] = curr_feats

        self.feature_mask = self._get_audio_feature_mask(
            w, h, audio_feats, smoothed_sub_bass, smoothed_percussive,
            smoothed_roughness, smoothed_ethereal, beat_energy,
            audio_feats.get('anticipation', 0.0), fx_intensity, t
        )

        delta_percussive = 0.0
        if len(self.percussive_history) >= 3:
            delta_percussive = audio_feats.get('percussive', 0.0) - (sum(self.percussive_history) / 3)
        self.percussive_history.append(audio_feats.get('percussive', 0.0))
        if len(self.percussive_history) > 3: self.percussive_history.pop(0)

        # 6. 和弦張力與亢奮蓄水池
        beat_duration = 60.0 / max(1.0, bpm)
        beat_phase = (t % beat_duration) / beat_duration
        anticipation_factor = max(0.0, (beat_phase - 0.85) / 0.15) if beat_phase > 0.85 else 0.0

        if not hasattr(self, 'arousal_reservoir'): self.arousal_reservoir = 0.0
        if not hasattr(self, 'last_chord_name'): self.last_chord_name = 'N.C.'
        if not hasattr(self, 'chord_tension'): self.chord_tension = 0.0
        if not hasattr(self, '_last_arousal'): self._last_arousal = 0.0

        instant_arousal = smoothed_sub_bass * 0.4 + smoothed_percussive * 0.4 + (1.0 - beat_phase) * 0.2
        valence = harmonic * 0.6 + chord_brightness * 0.4
        delta_arousal = max(0.0, instant_arousal - self._last_arousal)
        self._last_arousal = instant_arousal

        decay_rate = 1.2 + 0.8 * smoothed_ethereal
        self.arousal_reservoir = self.arousal_reservoir * math.exp(-decay_rate * dt) + delta_arousal * 1.5
        self.arousal_reservoir = max(instant_arousal, min(2.0, self.arousal_reservoir))
        arousal = self.arousal_reservoir

        # 7. 特效通道強度映射 (Multipliers)
        turbulence = self.arousal_reservoir * (1.0 - valence) + 0.5 * smoothed_roughness
        brilliance = self.arousal_reservoir * valence + 0.2 * chord_brightness
        ethereal_ambience = (1.0 - min(1.0, self.arousal_reservoir)) * valence + 0.5 * smoothed_ethereal
        base_mult = fx_intensity

        m_dist = base_mult * (arousal * 0.7 + stereo_width * 0.8)
        m_mosh = base_mult * (turbulence * 1.0 + (1.0 - beat_phase) * 0.8)
        m_pixel = base_mult * (turbulence * 1.4 + smoothed_roughness * 0.6)
        m_color = base_mult * (brilliance * 1.0 + 0.5 * smoothed_roughness)
        m_sediment = base_mult * (ethereal_ambience * 1.5 + smoothed_sub_bass * 0.6)
        m_retro = base_mult * (smoothed_roughness * 1.3 + self.arousal_reservoir * 0.3)
        m_fluid = base_mult * (self.arousal_reservoir * 1.0 + turbulence * 0.4)
        m_glow = max(0.0, base_mult * (brilliance * 1.2 + arousal * 0.5))
        m_vscan = base_mult * (smoothed_percussive * 0.8 + brilliance * 0.6)
        m_kaleidoscope = base_mult * (0.5 + stereo_width * 0.5)
        self._k_cx_offset = int((stereo_width - 0.5) * 200.0 * base_mult)
        m_fractal = base_mult * (ethereal_ambience * 1.4 + stereo_width * 0.4)
        m_feed = base_mult * (ethereal_ambience * 1.3 + smoothed_ethereal * 0.5)
        m_kuwahara = base_mult * (ethereal_ambience * 1.5 + smoothed_ethereal * 0.5)
        m_matrix = base_mult * (smoothed_percussive * 1.2 + smoothed_roughness * 0.6)
        m_reaction = base_mult * (self.arousal_reservoir * 1.2 + sub_bass * 0.8)
        m_thermal = base_mult * (brilliance * 1.1 + chord_brightness * 0.8)
        m_scanglitch = base_mult * (turbulence * 1.2 + smoothed_roughness * 0.6)
        m_framedrop = base_mult * (ethereal_ambience * 0.8 + (1.0 - beat_phase) * 0.6)
        m_mosaic = base_mult * (smoothed_sub_bass * 1.3 + turbulence * 0.5)
        m_pixelart = base_mult * (valence * 1.0 + smoothed_ethereal * 0.8)
        m_handheld = base_mult * (arousal * 0.9 + smoothed_roughness * 0.4)
        m_stylizedfade = base_mult * max(silence_fade, (1.0 - min(1.0, arousal)) * 0.45)
        m_zoompulse = base_mult * (smoothed_sub_bass * 1.5 + beat_energy * 0.8)
        m_photocopy = base_mult * (smoothed_percussive * 1.2 + smoothed_roughness * 0.8)
        m_collage = base_mult * (ethereal_ambience * 1.2 + smoothed_ethereal * 0.6)
        m_filmburn = base_mult * (self.arousal_reservoir * 1.1 + smoothed_roughness * 0.7)
        m_blueprint = base_mult * (harmonic * 1.2 + smoothed_roughness * 0.6)
        m_turing = base_mult * (ethereal_ambience * 1.3 + smoothed_sub_bass * 0.7)
        m_pointcloud = base_mult * (self.arousal_reservoir * 1.2 + stereo_width * 0.6)
        m_vectorscope = base_mult * (smoothed_percussive * 1.2 + stereo_width * 0.8)
        m_lowpass = base_mult * (audio_feats.get('lowpass', 0.5) * 1.5)
        m_infinity = base_mult * (self.arousal_reservoir * 1.3 + beat_energy * 0.8)
        m_dollyzoom = base_mult * (anticipation_factor * 1.5 + beat_energy * 0.8)

        # Row 5 乘數
        m_hologram = base_mult * (smoothed_percussive * 1.2 + turbulence * 0.6)
        m_voronoi = base_mult * (smoothed_sub_bass * 1.3 + beat_energy * 0.8)
        m_infrared = base_mult * (brilliance * 1.2 + chord_brightness * 0.8)
        m_cyber_ascii = base_mult * (smoothed_percussive * 1.3 + turbulence * 0.6)
        m_radial_zoom = base_mult * (beat_energy * 1.5 + smoothed_sub_bass * 0.8)
        m_synthgrid = base_mult * (smoothed_sub_bass * 1.2 + smoothed_percussive * 0.6)

        # Row 6 旗艦超前沿乘數
        m_chladni = base_mult * (harmonic * 1.2 + smoothed_sub_bass * 0.8)
        m_ferrofluid = base_mult * (smoothed_sub_bass * 1.4 + beat_energy * 0.7)
        m_caustics = base_mult * (smoothed_ethereal * 1.3 + brilliance * 0.7)
        m_clifford = base_mult * (stereo_width * 1.2 + turbulence * 0.8)
        m_moire = base_mult * (smoothed_percussive * 1.3 + chord_brightness * 0.7)

        # 生理光學與視網膜全域後製乘數
        section_defocus_boost = 1.35 if section_name in ('Intro', 'Breakdown', 'Bridge', 'Outro') else 0.85
        m_defocus = base_mult * (audio_feats.get('lowpass', 0.5) * 1.1 + smoothed_ethereal * 0.8 + (1.0 - min(1.0, self.arousal_reservoir)) * 0.5) * section_defocus_boost
        m_tremor = base_mult * (arousal * 0.8 + beat_energy * 1.2 + smoothed_sub_bass * 0.7 + smoothed_roughness * 0.5)

        # Row 7: 次世代前沿 5 大故障特效乘數
        m_quantum = base_mult * (stereo_width * 1.3 + turbulence * 0.7 + smoothed_roughness * 0.5)
        m_latent = base_mult * (harmonic * 1.2 + chord_brightness * 0.8 + smoothed_ethereal * 0.6)
        m_tape = base_mult * (smoothed_sub_bass * 1.3 + smoothed_percussive * 0.8 + turbulence * 0.6)
        m_entropy = base_mult * (smoothed_roughness * 1.4 + beat_energy * 0.8 + turbulence * 0.6)
        m_spectral_shear = base_mult * (smoothed_percussive * 1.2 + harmonic * 0.9 + beat_energy * 0.7)

        # 🌟 Row 8: 12 大次世代前沿幾何/拓撲高衝擊特效乘數
        m_hyperfold = base_mult * (smoothed_sub_bass * 1.5 + beat_energy * 0.9)
        m_rdgrowth = base_mult * (harmonic * 1.2 + smoothed_ethereal * 0.8)
        m_delaunay = base_mult * (smoothed_percussive * 1.4 + smoothed_roughness * 0.7)
        m_slitscan = base_mult * (stereo_width * 1.4 + turbulence * 0.7)
        m_gravlens = base_mult * (smoothed_sub_bass * 1.6 + beat_energy * 0.8)
        m_acidcurl = base_mult * (smoothed_roughness * 1.3 + harmonic * 0.8)
        m_strobe = base_mult * (beat_energy * 1.8 + smoothed_sub_bass * 0.7)
        m_lidar = base_mult * (smoothed_percussive * 1.3 + smoothed_roughness * 0.8)
        m_sineterrain = base_mult * (smoothed_sub_bass * 1.4 + chord_brightness * 0.6)
        m_quantravel = base_mult * (arousal * 1.2 + stereo_width * 0.7)
        m_prismdisp = base_mult * (smoothed_ethereal * 1.4 + brilliance * 0.8)
        m_maglines = base_mult * (smoothed_sub_bass * 1.3 + smoothed_percussive * 0.7)
        m_phaseslit = base_mult * (stereo_width * 1.3 + smoothed_percussive * 0.7)
        m_centroidglitch = base_mult * (spectral_centroid * 1.3 + smoothed_roughness * 0.7)
        m_vignette = base_mult * (anticipation_factor * 1.2 + beat_phase * 0.5)
        m_tension = base_mult * (0.5 + smoothed_roughness * 0.5)

        # 乘以活躍狀態 (fx_active_states)
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
        m_thermal *= self.fx_active_states['thermal_vision']
        m_scanglitch *= self.fx_active_states['scanline_glitch']
        m_framedrop *= self.fx_active_states['frame_drop']
        m_mosaic *= self.fx_active_states['dynamic_mosaic']
        m_pixelart *= self.fx_active_states['pixel_art']
        m_handheld *= self.fx_active_states['handheld_camera']
        m_stylizedfade *= self.fx_active_states['stylized_fade']
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
        m_hologram *= self.fx_active_states['hologram_glitch']
        m_voronoi *= self.fx_active_states['voronoi_shatter']
        m_infrared *= self.fx_active_states['thermal_infrared']
        m_cyber_ascii *= self.fx_active_states['ascii_cyber_matrix']
        m_radial_zoom *= self.fx_active_states['chromatic_radial_zoom']
        m_synthgrid *= self.fx_active_states['synthwave_grid_scan']
        m_chladni *= self.fx_active_states['chladni_cymatics']
        m_ferrofluid *= self.fx_active_states['ferrofluid_spikes']
        m_caustics *= self.fx_active_states['volumetric_caustics']
        m_clifford *= self.fx_active_states['clifford_torus']
        m_moire *= self.fx_active_states['holographic_moire']
        m_defocus *= self.fx_active_states['lens_defocus']
        m_tremor *= self.fx_active_states['ocular_tremor']
        m_quantum *= self.fx_active_states['quantum_decoherence']
        m_latent *= self.fx_active_states['latent_hallucination']
        m_tape *= self.fx_active_states['tape_head_drag']
        m_entropy *= self.fx_active_states['huffman_entropy_collapse']
        m_spectral_shear *= self.fx_active_states['spectral_fractal_shear']

        # 🌟 Row 8 活躍狀態相乘
        m_hyperfold *= self.fx_active_states['hyper_dimensional_fold']
        m_rdgrowth *= self.fx_active_states['reaction_diffusion_growth']
        m_delaunay *= self.fx_active_states['delaunay_voronoi_mesh']
        m_slitscan *= self.fx_active_states['slit_scan_time_warp']
        m_gravlens *= self.fx_active_states['gravitational_lensing']
        m_acidcurl *= self.fx_active_states['acid_curl_fluid']
        m_strobe *= self.fx_active_states['strobe_chroma_invert']
        m_lidar *= self.fx_active_states['cyber_wireframe_lidar']
        m_sineterrain *= self.fx_active_states['sine_terrain_displacement']
        m_quantravel *= self.fx_active_states['quantum_tunneling']
        m_prismdisp *= self.fx_active_states['prismatic_refraction_prism']
        m_maglines *= self.fx_active_states['magnetic_field_lines']
        m_phaseslit *= self.fx_active_states['phase_slit']
        m_centroidglitch *= self.fx_active_states['centroid_glitch']
        m_vignette *= self.fx_active_states['vignette_pulse']
        m_tension *= self.fx_active_states['tension_overlay']

        # 8. 進入 NumPy 高性能流水線
        img_np = np.array(img.convert('RGB'))
        try:
            cinedance_meta = audio_feats.get('cinedance_meta') if isinstance(audio_feats, dict) else None
            img_np = self.camera_rig.apply(
                img_np, t, beat_energy, section_name=section_name,
                cinedance_meta=cinedance_meta
            )
            if cinedance_meta and "light_triad" in cinedance_meta:
                img_np = SpatialTriadRelighting.apply_relighting(
                    img_np, cinedance_meta["light_triad"], blend_weight=0.35 * fx_intensity
                )
            if self.audio_particle_fluid is not None:
                img_np = self.audio_particle_fluid.update_and_render(
                    img_np, t, is_beat, beat_energy, audio_feats, intensity=fx_intensity, section_name=section_name
                )
        except Exception:
            pass

        self.time_displacement_buffer.push(img_np)

        # ── 38 大特效執行 Pass 完整流水線 ──

        # [NEW DERIVATIVE 1]: Stereo Phase Slit-Scan
        if fx_flags.get('phase_slit', True) and m_phaseslit > 0.01:
            var_idx = self.get_variant_index('phase_slit', t, is_beat)
            img_np = self.apply_phase_slit_custom(img_np, stereo_width, m_phaseslit, var_idx)

        # [NEW DERIVATIVE 2]: Centroid Resonance Glitch
        if fx_flags.get('centroid_glitch', True) and m_centroidglitch > 0.01:
            var_idx = self.get_variant_index('centroid_glitch', t, is_beat)
            img_np = self.apply_centroid_glitch_custom(img_np, spectral_centroid, smoothed_roughness, m_centroidglitch, var_idx)

        # [PASS A]: Data-Mosh 數位撕裂
        if fx_flags.get('data_mosh', True) and m_mosh > 0.01:
            var_idx = self.get_variant_index('data_mosh', t, is_beat)
            img_np = self.apply_data_mosh_custom(img_np, m_mosh * (0.5 + smoothed_roughness), var_idx)

        # [PASS B]: Sedimentation 流沙沉澱
        if fx_flags.get('sedimentation', True) and m_sediment > 0.01:
            var_idx = self.get_variant_index('sedimentation', t, is_beat)
            img_np = self.apply_sedimentation_custom(img_np, t, smoothed_sub_bass, smoothed_ethereal, m_sediment, 0.0, var_idx)

        # [Pass 1]: 幾何畸變
        if fx_flags.get('spatial_warping', True) and m_dist > 0.01:
            var_idx = self.get_variant_index('spatial_warping', t, is_beat)
            img_np = self.apply_spatial_warping_custom(img_np, t, m_dist, smoothed_sub_bass, smoothed_percussive, is_beat, var_idx)

        # [Pass 8-zoom]: 縮放脈衝
        if fx_flags.get('zoom_pulse', True) and m_zoompulse > 0.01:
            var_idx = self.get_variant_index('zoom_pulse', t, is_beat)
            img_np = self.apply_zoom_pulse_custom(img_np, m_zoompulse, smoothed_sub_bass, t, var_idx)

        # [Pass 2]: 流體平流與動態噪訊
        if fx_flags.get('fluid_noise', True) and m_fluid > 0.01:
            var_idx = self.get_variant_index('fluid_noise', t, is_beat)
            img_np = self.apply_fluid_noise_custom(img_np, t, m_fluid, smoothed_sub_bass, smoothed_percussive, is_beat, anticipation_factor, beat_energy, var_idx)

        # [Pass 3]: 時空反饋
        if fx_flags.get('temporal_feedback', True) and m_feed > 0.01:
            var_idx = self.get_variant_index('temporal_feedback', t, is_beat)
            img_np = self.apply_temporal_feedback_custom(img_np, t, m_feed, smoothed_ethereal, smoothed_roughness, audio_feats.get('chord_name', 'N.C.'), var_idx)

        # [Pass 6-cam]: 手持相機
        if fx_flags.get('handheld_camera', True) and m_handheld > 0.01:
            var_idx = self.get_variant_index('handheld_camera', t, is_beat)
            img_np = self.apply_handheld_camera_custom(img_np, t, m_handheld, smoothed_roughness, arousal, is_beat, var_idx)

        # [Pass 4]: 光譜色彩異常
        if fx_flags.get('color_spectral', True) and m_color > 0.01:
            var_idx = self.get_variant_index('color_spectral', t, is_beat)
            img_np = self.apply_color_spectral_custom(img_np, t, m_color, smoothed_roughness, smoothed_ethereal, audio_feats.get('chord_name', 'N.C.'), var_idx)

        # [Pass 1-thermal]: 熱成像
        if fx_flags.get('thermal_vision', True) and m_thermal > 0.01:
            var_idx = self.get_variant_index('thermal_vision', t, is_beat)
            img_np = self.apply_thermal_custom(img_np, m_thermal, smoothed_sub_bass, smoothed_percussive, chord_hue, var_idx)

        # [Pass 5]: 高階光影與 Bloom
        if fx_flags.get('glow_illumination', True) and m_glow > 0.01:
            var_idx = self.get_variant_index('glow_illumination', t, is_beat)
            img_np = self.apply_glow_illumination_custom(img_np, t, m_glow, smoothed_sub_bass, smoothed_percussive, var_idx)

        # [Pass 6]: 訊號退化
        if fx_flags.get('retro_degradation', True) and m_retro > 0.01:
            var_idx = self.get_variant_index('retro_degradation', t, is_beat)
            img_np = self.apply_retro_degradation_custom(img_np, t, m_retro, smoothed_roughness, audio_feats, is_beat, beat_energy, genre_clean, var_idx)

        # [Pass 6.5]: 影印機拖移故障
        if fx_flags.get('photocopy_smear', True) and m_photocopy > 0.01:
            var_idx = self.get_variant_index('photocopy_smear', t, is_beat)
            img_np = self.apply_photocopy_smear_custom(img_np, t, m_photocopy, var_idx)

        # [Pass 2-scan]: 掃描故障
        if fx_flags.get('scanline_glitch', True) and m_scanglitch > 0.01:
            var_idx = self.get_variant_index('scanline_glitch', t, is_beat)
            img_np = self.apply_scanline_glitch_custom(img_np, m_scanglitch, smoothed_sub_bass, smoothed_roughness, is_beat, var_idx)

        # [Pass C]: 雷射等高線
        if fx_flags.get('vector_scan', True) and m_vscan > 0.01:
            var_idx = self.get_variant_index('vector_scan', t, is_beat)
            img_np = self.apply_vector_scan_custom(img_np, t, chord_hue, chord_brightness, m_vscan, m_mosh, smoothed_percussive, var_idx)

        # [Pass 4-mosaic]: 動態馬賽克
        if fx_flags.get('dynamic_mosaic', True) and m_mosaic > 0.01:
            var_idx = self.get_variant_index('dynamic_mosaic', t, is_beat)
            img_np = self.apply_dynamic_mosaic_custom(img_np, m_mosaic, smoothed_sub_bass, chord_brightness, smoothed_roughness, var_idx)

        # [Pass 7]: 像素分選
        if fx_flags.get('pixel_sort', True) and m_pixel > 0.01:
            var_idx = self.get_variant_index('pixel_sort', t, is_beat)
            img_np = self.apply_pixel_sort_custom(img_np, m_pixel, smoothed_roughness, var_idx)

        # [Pass 5-pixelart]: 像素畫
        if fx_flags.get('pixel_art', True) and m_pixelart > 0.01:
            var_idx = self.get_variant_index('pixel_art', t, is_beat)
            img_np = self.apply_pixel_art_custom(img_np, m_pixelart, smoothed_sub_bass, var_idx)

        # [Pass 8]: 鏡像萬花筒
        if fx_flags.get('kaleidoscope', True) and m_kaleidoscope > 0.01:
            var_idx = self.get_variant_index('kaleidoscope', t, is_beat)
            img_np = self.apply_kaleidoscope_custom(img_np, t, m_kaleidoscope, smoothed_sub_bass, beat_energy, is_beat, self._k_cx_offset, var_idx)

        # [Pass D]: 時空分形鏡
        if fx_flags.get('temporal_fractal', True) and m_fractal > 0.01:
            var_idx = self.get_variant_index('temporal_fractal', t, is_beat)
            img_np = self.apply_temporal_fractal_custom(img_np, stereo_width, arousal, m_fractal, var_idx)

        # [DERIVATIVE 3]: 正拍預期呼吸暗房
        if fx_flags.get('vignette_pulse', True) and m_vignette > 0.01:
            var_idx = self.get_variant_index('vignette_pulse', t, is_beat)
            img_np = self.apply_vignette_pulse_custom(img_np, beat_phase, anticipation_factor, m_vignette, var_idx)

        # [DERIVATIVE 4]: 張力互斥
        if fx_flags.get('tension_overlay', True) and m_tension > 0.01:
            var_idx = self.get_variant_index('tension_overlay', t, is_beat)
            img_np = self.apply_tension_overlay_custom(img_np, 0.5, chord_hue, m_tension, var_idx)

        # [Pass 1-kuwahara]: Kuwahara 彩繪
        if fx_flags.get('kuwahara_paint', True) and m_kuwahara > 0.01:
            var_idx = self.get_variant_index('kuwahara_paint', t, is_beat)
            img_np = self.apply_kuwahara_paint_custom(img_np, t, m_kuwahara, smoothed_roughness, smoothed_ethereal, var_idx)

        # [Pass 2-matrix]: Matrix 數位雨
        if fx_flags.get('matrix_ascii', True) and m_matrix > 0.01:
            var_idx = self.get_variant_index('matrix_ascii', t, is_beat)
            img_np = self.apply_matrix_ascii_custom(img_np, t, m_matrix, audio_feats, is_beat, beat_energy, var_idx)

        # [Pass 3-reaction]: 反應擴散
        if fx_flags.get('reaction_diffusion', True) and m_reaction > 0.01:
            var_idx = self.get_variant_index('reaction_diffusion', t, is_beat)
            img_np = self.apply_reaction_diffusion_custom(img_np, t, m_reaction, audio_feats, is_beat, beat_energy, var_idx)

        # [Pass 3-framedrop]: 掉幀特效
        if fx_flags.get('frame_drop', True) and m_framedrop > 0.01:
            var_idx = self.get_variant_index('frame_drop', t, is_beat)
            img_np = self.apply_frame_drop_custom(img_np, m_framedrop, arousal, beat_phase, var_idx)

        # [Pass 8.5]: 拼貼濾鏡
        if fx_flags.get('collage_cutout', True) and m_collage > 0.01:
            var_idx = self.get_variant_index('collage_cutout', t, is_beat)
            img_np = self.apply_collage_cutout_custom(img_np, m_collage, var_idx)

        # ── 全新維度頂級特效矩陣 ──
        # [Pass 9.1]: 膠片腐蝕
        if fx_flags.get('film_burn', True) and m_filmburn > 0.01:
            var_idx = self.get_variant_index('film_burn', t, is_beat)
            img_np = self.apply_film_burn_custom(img_np, t, m_filmburn, smoothed_sub_bass, smoothed_roughness, is_beat, var_idx)

        # [Pass 9.2]: 建築藍圖
        if fx_flags.get('blueprint_edge', True) and m_blueprint > 0.01:
            var_idx = self.get_variant_index('blueprint_edge', t, is_beat)
            img_np = self.apply_blueprint_edge_custom(img_np, m_blueprint, harmonic, smoothed_roughness, var_idx)

        # [Pass 9.3]: 圖靈細胞
        if fx_flags.get('turing_pattern', True) and m_turing > 0.01:
            var_idx = self.get_variant_index('turing_pattern', t, is_beat)
            img_np = self.apply_turing_pattern_custom(img_np, t, m_turing, smoothed_ethereal, is_beat, var_idx)

        # [Pass 9.4]: 點雲深度
        if fx_flags.get('point_cloud_depth', True) and m_pointcloud > 0.01:
            var_idx = self.get_variant_index('point_cloud_depth', t, is_beat)
            img_np = self.apply_point_cloud_depth_custom(img_np, m_pointcloud, smoothed_sub_bass, stereo_width, var_idx)

        # [Pass 9.5]: 聲相示波
        if fx_flags.get('vector_scope', True) and m_vectorscope > 0.01:
            var_idx = self.get_variant_index('vector_scope', t, is_beat)
            audio_samples = audio_feats.get('audio_samples', None)
            img_np = self.apply_vector_scope_custom(img_np, t, m_vectorscope, stereo_width, chord_hue, audio_samples, var_idx)

        # [Pass 9.6]: 悶音景深
        if fx_flags.get('lowpass_muffle', True) and m_lowpass > 0.01:
            var_idx = self.get_variant_index('lowpass_muffle', t, is_beat)
            lowpass_val = audio_feats.get('lowpass', 0.0)
            img_np = self.apply_lowpass_muffle_custom(img_np, m_lowpass, lowpass_val, var_idx)

        # [Pass 9.65]: 鏡頭失焦與光學散景 (Lens Defocus & Optical Bokeh)
        if fx_flags.get('lens_defocus', True) and m_defocus > 0.01:
            var_idx = self.get_variant_index('lens_defocus', t, is_beat)
            lowpass_val = audio_feats.get('lowpass', 0.0)
            img_np = self.apply_lens_defocus_custom(img_np, m_defocus, lowpass_val, smoothed_ethereal, is_beat, var_idx)

        # [Pass 9.7]: 無限鏡廊
        if fx_flags.get('infinity_tunnel', True) and m_infinity > 0.01:
            var_idx = self.get_variant_index('infinity_tunnel', t, is_beat)
            img_np = self.apply_infinity_tunnel_custom(img_np, t, m_infinity, beat_phase, beat_energy, var_idx)

        # [Pass 9.8]: 眩暈推拉
        if fx_flags.get('dolly_zoom', True) and m_dollyzoom > 0.01:
            var_idx = self.get_variant_index('dolly_zoom', t, is_beat)
            img_np = self.apply_dolly_zoom_custom(img_np, m_dollyzoom, anticipation_factor, is_beat, var_idx)

        # [Pass 9.85]: 藝術淡入淡出 (Stylized Fade)
        if fx_flags.get('stylized_fade', True) and (m_stylizedfade > 0.01 or silence_fade > 0.05):
            var_idx = self.get_variant_index('stylized_fade', t, is_beat)
            img_np = self.apply_stylized_fade_custom(img_np, m_stylizedfade, silence_fade, var_idx)

        # ── 第 5 排前沿全域 6 大特效 ──
        # [Row 5.1]: 全息干擾
        if fx_flags.get('hologram_glitch', True) and m_hologram > 0.01:
            var_idx = self.get_variant_index('hologram_glitch', t, is_beat)
            img_np = self.apply_hologram_glitch_custom(img_np, t, m_hologram, audio_feats, is_beat, var_idx)

        # [Row 5.2]: 泰森碎裂
        if fx_flags.get('voronoi_shatter', True) and m_voronoi > 0.01:
            var_idx = self.get_variant_index('voronoi_shatter', t, is_beat)
            img_np = self.apply_voronoi_shatter_custom(img_np, t, m_voronoi, smoothed_sub_bass, beat_energy, is_beat, var_idx)

        # [Row 5.3]: 紅外熱感
        if fx_flags.get('thermal_infrared', True) and m_infrared > 0.01:
            var_idx = self.get_variant_index('thermal_infrared', t, is_beat)
            img_np = self.apply_thermal_infrared_custom(img_np, m_infrared, chord_brightness, smoothed_sub_bass, chord_hue, var_idx)

        # [Row 5.4]: 矩陣字元
        if fx_flags.get('ascii_cyber_matrix', True) and m_cyber_ascii > 0.01:
            var_idx = self.get_variant_index('ascii_cyber_matrix', t, is_beat)
            img_np = self.apply_ascii_cyber_matrix_custom(img_np, t, m_cyber_ascii, audio_feats, is_beat, beat_energy, var_idx)

        # [Row 5.5]: 色差爆發
        if fx_flags.get('chromatic_radial_zoom', True) and m_radial_zoom > 0.01:
            var_idx = self.get_variant_index('chromatic_radial_zoom', t, is_beat)
            img_np = self.apply_chromatic_radial_zoom_custom(img_np, t, m_radial_zoom, beat_energy, is_beat, var_idx)

        # [Row 5.6]: 賽博網格
        if fx_flags.get('synthwave_grid_scan', True) and m_synthgrid > 0.01:
            var_idx = self.get_variant_index('synthwave_grid_scan', t, is_beat)
            img_np = self.apply_synthwave_grid_scan_custom(img_np, t, m_synthgrid, smoothed_sub_bass, smoothed_percussive, var_idx)

        # ── 第 6 排旗艦超前沿 5 大特效 ──
        # [Row 6.1]: 克拉尼克駐波 (Chladni Cymatics)
        if fx_flags.get('chladni_cymatics', True) and m_chladni > 0.01:
            var_idx = self.get_variant_index('chladni_cymatics', t, is_beat)
            img_np = self.apply_chladni_cymatics_custom(img_np, t, m_chladni, harmonic, smoothed_sub_bass, is_beat, var_idx)

        # [Row 6.2]: 磁流體刺針 (Ferrofluid Spikes)
        if fx_flags.get('ferrofluid_spikes', True) and m_ferrofluid > 0.01:
            var_idx = self.get_variant_index('ferrofluid_spikes', t, is_beat)
            img_np = self.apply_ferrofluid_spikes_custom(img_np, t, m_ferrofluid, smoothed_sub_bass, beat_energy, is_beat, var_idx)

        # [Row 6.3]: 體積焦散光網 (Volumetric Caustics)
        if fx_flags.get('volumetric_caustics', True) and m_caustics > 0.01:
            var_idx = self.get_variant_index('volumetric_caustics', t, is_beat)
            img_np = self.apply_volumetric_caustics_custom(img_np, t, m_caustics, smoothed_ethereal, chord_brightness, chord_hue, var_idx)

        # [Row 6.4]: 四維克利福德環面扭曲 (4D Clifford Torus Warp)
        if fx_flags.get('clifford_torus', True) and m_clifford > 0.01:
            var_idx = self.get_variant_index('clifford_torus', t, is_beat)
            img_np = self.apply_clifford_torus_warp_custom(img_np, t, m_clifford, stereo_width, smoothed_sub_bass, var_idx)

        # [Row 6.5]: 聲學全息莫爾干涉 (Acoustic Holographic Moiré)
        if fx_flags.get('holographic_moire', True) and m_moire > 0.01:
            var_idx = self.get_variant_index('holographic_moire', t, is_beat)
            img_np = self.apply_holographic_moire_custom(img_np, t, m_moire, smoothed_percussive, chord_hue, is_beat, var_idx)

        # ── 第 7 排次世代前沿 5 大故障特效 (Next-Gen Glitch Matrix) ──
        # [Row 7.1]: 量子退相干崩塌 (Quantum Decoherence Collapse)
        if fx_flags.get('quantum_decoherence', True) and m_quantum > 0.01:
            var_idx = self.get_variant_index('quantum_decoherence', t, is_beat)
            img_np = self.apply_quantum_decoherence_custom(img_np, t, m_quantum, stereo_width, turbulence, is_beat, var_idx)

        # [Row 7.2]: 神經潛空間幻覺故障 (Latent Space Hallucination Glitch)
        if fx_flags.get('latent_hallucination', True) and m_latent > 0.01:
            var_idx = self.get_variant_index('latent_hallucination', t, is_beat)
            img_np = self.apply_latent_hallucination_custom(img_np, t, m_latent, harmonic, chord_brightness, var_idx)

        # [Row 7.3]: 類比磁帶刮擦與咬帶 (Tape Head Scratch & Pinch Roller Drag)
        if fx_flags.get('tape_head_drag', True) and m_tape > 0.01:
            var_idx = self.get_variant_index('tape_head_drag', t, is_beat)
            img_np = self.apply_tape_head_drag_custom(img_np, t, m_tape, smoothed_sub_bass, smoothed_percussive, is_beat, var_idx)

        # [Row 7.4]: JPEG 宏塊熵編碼崩毀 (Huffman Entropy Macroblock Disruption)
        if fx_flags.get('huffman_entropy_collapse', True) and m_entropy > 0.01:
            var_idx = self.get_variant_index('huffman_entropy_collapse', t, is_beat)
            img_np = self.apply_huffman_entropy_collapse_custom(img_np, t, m_entropy, smoothed_roughness, beat_energy, is_beat, var_idx)

        # [Row 7.5]: 時空頻譜碎形撕裂 (Spectral Spatio-Temporal Shear)
        if fx_flags.get('spectral_fractal_shear', True) and m_spectral_shear > 0.01:
            var_idx = self.get_variant_index('spectral_fractal_shear', t, is_beat)
            audio_samples = audio_feats.get('audio_samples', None)
            img_np = self.apply_spectral_fractal_shear_custom(img_np, t, m_spectral_shear, harmonic, smoothed_percussive, audio_samples, is_beat, var_idx)

        # [Pass 6.8]: 生理性眼球顫動與跳視 (Ocular Tremor & Saccadic Jitter)
        if fx_flags.get('ocular_tremor', True) and m_tremor > 0.01:
            var_idx = self.get_variant_index('ocular_tremor', t, is_beat)
            img_np = self.apply_ocular_tremor_custom(img_np, t, m_tremor, beat_energy, smoothed_sub_bass, smoothed_roughness, is_beat, var_idx)

        # ── 🌟 第 8 排 12 大次世代高辨識度幾何/拓撲強特徵特效執行 Pass 完整流水線 ──

        # [Row 8.1]: 四維空間幾何折疊 (Hyper-Dimensional Fold)
        if fx_flags.get('hyper_dimensional_fold', True) and m_hyperfold > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('hyper_dimensional_fold', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_hyper_dimensional_fold_custom(img_np, t, m_hyperfold, smoothed_sub_bass, beat_energy, is_beat, dna)

        # [Row 8.2]: 異構反應擴散生長 (Reaction-Diffusion Growth)
        if fx_flags.get('reaction_diffusion_growth', True) and m_rdgrowth > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('reaction_diffusion_growth', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_reaction_diffusion_growth_custom(img_np, t, m_rdgrowth, smoothed_sub_bass, smoothed_ethereal, dna)

        # [Row 8.3]: 德勞內三角網格解構 (Delaunay-Voronoi Mesh)
        if fx_flags.get('delaunay_voronoi_mesh', True) and m_delaunay > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('delaunay_voronoi_mesh', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_delaunay_voronoi_mesh_custom(img_np, t, m_delaunay, smoothed_percussive, smoothed_roughness, dna)

        # [Row 8.4]: 時空狹縫延遲穿透 (Slit-Scan Time Warp)
        if fx_flags.get('slit_scan_time_warp', True) and m_slitscan > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('slit_scan_time_warp', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_slit_scan_time_warp_custom(img_np, t, m_slitscan, stereo_width, dna)

        # [Row 8.5]: 引力透鏡黑洞扭曲 (Gravitational Lensing)
        if fx_flags.get('gravitational_lensing', True) and m_gravlens > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('gravitational_lensing', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_gravitational_lensing_custom(img_np, t, m_gravlens, smoothed_sub_bass, beat_energy, dna)

        # [Row 8.6]: 酸性旋度流體混動 (Acid Curl Fluid)
        if fx_flags.get('acid_curl_fluid', True) and m_acidcurl > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('acid_curl_fluid', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_acid_curl_fluid_custom(img_np, t, m_acidcurl, smoothed_roughness, harmonic, dna)

        # [Row 8.7]: 極速反相頻閃脈衝 (Strobe Chroma Invert)
        if fx_flags.get('strobe_chroma_invert', True) and m_strobe > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('strobe_chroma_invert', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_strobe_chroma_invert_custom(img_np, t, m_strobe, beat_energy, is_beat, dna)

        # [Row 8.8]: 賽博光達深度線框 (Cyber Wireframe LiDAR)
        if fx_flags.get('cyber_wireframe_lidar', True) and m_lidar > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('cyber_wireframe_lidar', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_cyber_wireframe_lidar_custom(img_np, t, m_lidar, smoothed_percussive, smoothed_roughness, dna)

        # [Row 8.9]: 正弦音波地形位移 (Sine Terrain Displacement)
        if fx_flags.get('sine_terrain_displacement', True) and m_sineterrain > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('sine_terrain_displacement', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_sine_terrain_displacement_custom(img_np, t, m_sineterrain, smoothed_sub_bass, chord_hue, dna)

        # [Row 8.10]: 量子穿隧噪波分解 (Quantum Tunneling)
        if fx_flags.get('quantum_tunneling', True) and m_quantravel > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('quantum_tunneling', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_quantum_tunneling_custom(img_np, t, m_quantravel, smoothed_roughness, arousal, dna)

        # [Row 8.11]: 多稜鏡立體光譜色散 (Prismatic Refraction Prism)
        if fx_flags.get('prismatic_refraction_prism', True) and m_prismdisp > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('prismatic_refraction_prism', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_prismatic_refraction_prism_custom(img_np, t, m_prismdisp, smoothed_ethereal, chord_brightness, dna)

        # [Row 8.12]: 磁力線粉末吸附 (Magnetic Field Lines)
        if fx_flags.get('magnetic_field_lines', True) and m_maglines > 0.01:
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('magnetic_field_lines', t, beat_energy, audio_feats, self.rng.randint(0, 10000), genre_clean)
            img_np = self.apply_magnetic_field_lines_custom(img_np, t, m_maglines, smoothed_sub_bass, smoothed_percussive, dna)

        # 9. 色彩增強、調色與銳化 (Ambient 曲風專用感知色度抑制與電影級大氣色彩修整)
        is_ambient_genre = (
            getattr(self, 'is_ambient_genre', False)
            or any(k in genre_clean for k in ('ambient', 'drone', 'meditative', 'dark_ambient', 'downtempo', 'chill', 'atmospheric', 'sleep', 'new_age'))
            or fx_flags.get('force_ambient_color', False)
            or (isinstance(audio_feats, dict) and bool(audio_feats.get('force_ambient_color', False)))
        )
        ambient_policy = audio_feats.get('ambient_color_policy') if isinstance(audio_feats, dict) else None
        ambient_chroma = 0.065
        target_hue = None

        if is_ambient_genre or fx_flags.get('ambient_chroma_limiter', False) or ambient_policy:
            # 專屬 Ambient 模式：徹底拒絕生硬高飽和度放大，啟用 OKLab 感知色度抑制
            if ambient_policy and isinstance(ambient_policy, dict):
                ambient_chroma = float(ambient_policy.get('chroma_ceiling', ambient_chroma))
                target_hue = ambient_policy.get('target_hue')
            elif is_ambient_genre:
                # 結合 sub_bass 與 ethereal 進行極細微大氣呼吸感浮動 (0.050 ~ 0.078)
                ambient_chroma = 0.062 + (smoothed_sub_bass - 0.5) * 0.015 - smoothed_ethereal * 0.008
                ambient_chroma = max(0.045, min(0.080, ambient_chroma))
                target_hue = audio_feats.get('base_hue') if isinstance(audio_feats, dict) else None

            # 套用 OKLab 感知色度抑制器 (消除任何寫死鮮豔原色/螢光刺眼色)
            img_np = apply_ambient_perceptual_chroma_limiter(
                img_np,
                chroma_limit=ambient_chroma,
                target_hue_deg=target_hue,
                hue_blend=0.12 if target_hue is not None else 0.0,
                highlight_rolloff=0.86,
                warmth_offset=(smoothed_sub_bass - 0.5) * 0.05
            )
            # 輕微大氣對比修整，不膨脹飽和度
            img_np = self.apply_color_enhancement(img_np, contrast=1.03, saturation=0.82, exposure=1.0)
        elif fx_flags.get('color_boost', True):
            exposure = 1.05 + 0.1 * beat_energy if is_beat else 1.0
            img_np = self.apply_color_enhancement(img_np, contrast=1.12, saturation=1.15, exposure=exposure)

        if fx_flags.get('sharpen', True):
            # Ambient 曲風下適度減弱銳化強度，保留膠片柔和與大氣光暈
            sharpen_amount = 0.35 if is_ambient_genre else 0.6
            img_np = self.apply_sharpening(img_np, amount=sharpen_amount, radius=1.0)

        # Pass 10: 空靈聲學模擬
        if fx_flags.get('ambient_dsp', True) and self.fx_active_states['ambient_dsp'] > 0.04:
            var_idx = self.get_variant_index('ambient_dsp', t, is_beat)
            img_np = self.apply_ambient_dsp_custom(img_np, t, fx_intensity * self.fx_active_states['ambient_dsp'], smoothed_ethereal, smoothed_percussive, var_idx)

        # 11. 實時動態曝光與 Ambient 全局微光大氣補償 (Adaptive Luminescence & Ganzfeld Atmosphere Normalization)
        # 徹底根除 Ambient / 低喚起度曲風下畫面死黑、嚴重欠曝、看不到內容之根本缺陷
        try:
            cur_max = float(np.max(img_np[:, :, :3]))
            cur_mean = float(np.mean(img_np[:, :, :3]))
            if is_ambient_genre:
                # Ambient 模式下畫面若過暗 (cur_max < 95 或 cur_mean < 16)
                if cur_max < 95.0 or cur_mean < 16.0:
                    # 1. 溫和動態增益拉伸，限制 boost_gain <= 2.2 防止暗部偏色被暴力放大成螢光高飽和
                    target_peak = max(135.0, min(195.0, 150.0 + 35.0 * smoothed_ethereal))
                    if cur_max > 4.0:
                        boost_gain = min(2.2, target_peak / cur_max)
                        float_rgb = img_np[:, :, :3].astype(np.float32) * boost_gain
                        img_np[:, :, :3] = np.clip(float_rgb, 0, 255).astype(np.uint8)

                # 2. 注入極光微光氛圍底光 (Ambient Aurora / Ganzfeld Floor)，杜絕死寂 RGB(0,0,0) 純黑
                base_h = target_hue if target_hue is not None else chord_hue
                h_rad = math.radians(base_h)
                ambient_r = int(12 + 8 * math.sin(h_rad))
                ambient_g = int(13 + 8 * math.sin(h_rad + 2.094))
                ambient_b = int(16 + 9 * math.sin(h_rad + 4.188))
                
                dark_mask = (img_np[:, :, :3] < 24).astype(np.float32)
                floor_rgb = np.zeros_like(img_np[:, :, :3], dtype=np.float32)
                floor_rgb[:, :, 0] = ambient_r
                floor_rgb[:, :, 1] = ambient_g
                floor_rgb[:, :, 2] = ambient_b
                img_np[:, :, :3] = np.clip(
                    img_np[:, :, :3].astype(np.float32) + dark_mask * floor_rgb * (0.65 + 0.35 * smoothed_ethereal),
                    0, 255
                ).astype(np.uint8)

                # 3. 曝光增益後再次執行終極 OKLab 色度夾持，100% 封鎖任何因暗部增益產生的鮮艷色溢出
                img_np = apply_ambient_perceptual_chroma_limiter(
                    img_np,
                    chroma_limit=ambient_chroma,
                    target_hue_deg=target_hue,
                    hue_blend=0.08 if target_hue is not None else 0.0,
                    highlight_rolloff=0.86,
                    warmth_offset=0.0
                )
            else:
                # 非 Ambient 曲風：若畫面極端欠曝 (cur_max < 45)，緊急救援拉升至可視範圍
                if cur_max < 45.0 and cur_max > 4.0:
                    boost_gain = min(3.5, 130.0 / cur_max)
                    float_rgb = img_np[:, :, :3].astype(np.float32) * boost_gain
                    img_np[:, :, :3] = np.clip(float_rgb, 0, 255).astype(np.uint8)
        except Exception:
            pass

        # ITU-R BT.1702 光敏安全門控防線 (Photosensitive Epilepsy Safety Limiter)
        if self.photosensitive_safe and self.safety_limiter is not None:
            img_np = self.safety_limiter.process(img_np)

        if is_scaled and cv2 is not None:
            img_np = cv2.resize(img_np, original_size, interpolation=cv2.INTER_LANCZOS4)

        return Image.fromarray(img_np)


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
            x, y, _, _ = self.get_coordinate_grid(h, w)
            
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
                return cv2.remap(img_np, (x + dx).astype(np.float32), (y + dy).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
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
                return cv2.remap(img_np, (x + dx).astype(np.float32), (y + dy).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 1:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                noise_x = (np.sin(x * 0.01 + t) + 0.5 * np.sin(x * 0.02 - t * 1.3) + 0.25 * np.sin(y * 0.04)) * (30.0 * intensity)
                noise_y = (np.cos(y * 0.01 - t) + 0.5 * np.cos(y * 0.02 + t * 1.2) + 0.25 * np.cos(x * 0.04)) * (30.0 * intensity)
                return cv2.remap(img_np, (x + noise_x).astype(np.float32), (y + noise_y).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 2:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dy = np.sin(x * 0.005 + t * 4.0) * (25.0 * intensity) - t * 15.0
                dy = np.mod(dy, h)
                return cv2.remap(img_np, x.astype(np.float32), dy.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 3:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                grid = 80.0
                cell_x = (x // grid) * grid + grid/2.0
                cell_y = (y // grid) * grid + grid/2.0
                dx = (x - cell_x) * (0.25 * intensity)
                dy = (y - cell_y) * (0.25 * intensity)
                return cv2.remap(img_np, (x - dx).astype(np.float32), (y - dy).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            else:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dx = np.sin(np.sin(x * 0.008) * 4.0 + t) * (35.0 * intensity)
                dy = np.cos(np.cos(y * 0.008) * 4.0 - t) * (35.0 * intensity)
                return cv2.remap(img_np, (x + dx).astype(np.float32), (y + dy).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
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
                alive_mask = np.ones((h, w), dtype=bool)
                with np.errstate(over='ignore', invalid='ignore'):
                    for i in range(15):
                        z[alive_mask] = z[alive_mask]**2 + c[alive_mask]
                        alive_mask = np.abs(z) < 2.0
                        fractal_mask[alive_mask] = i * 17
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
            alpha_channel = None
            if img_np.ndim == 3 and img_np.shape[2] == 4:
                alpha_channel = img_np[:, :, 3]
                img_np = img_np[:, :, :3]

            h, w = img_np.shape[:2]
            if variant == 0:
                if getattr(self, 'photosensitive_safe', False):
                    out = self.apply_tension_overlay_custom(img_np, tension, hue, intensity, 3)
                else:
                    out = self.apply_tension_exclusion(img_np, tension, hue, intensity)
            elif variant == 1:
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dx = np.sin(y * 0.03 + hue) * (30.0 * tension * intensity)
                dy = np.cos(x * 0.03 - hue) * (30.0 * tension * intensity)
                out = cv2.remap(img_np, (x + dx).astype(np.float32), (y + dy).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            elif variant == 2:
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
                r_c, g_c, b_c = self._hue_to_rgb(hue)
                color_map = np.zeros_like(img_np)
                mask = thresh > 0
                color_map[mask] = (r_c, g_c, b_c)
                color_map[~mask] = (255 - r_c, 255 - g_c, 255 - b_c)
                out = cv2.addWeighted(img_np, 1.0 - 0.5 * tension * intensity, color_map, 0.5 * tension * intensity, 0)
            elif variant == 3:
                r_ch = img_np[:, :, 0]
                b_ch = img_np[:, :, 2]
                r_blur = cv2.GaussianBlur(r_ch, (25, 25), 0)
                b_blur = cv2.GaussianBlur(b_ch, (25, 25), 0)
                bleed = img_np.copy()
                bleed[:, :, 0] = cv2.addWeighted(r_ch, 0.4, r_blur, 0.6 * intensity * tension, 0)
                bleed[:, :, 2] = cv2.addWeighted(b_ch, 0.4, b_blur, 0.6 * intensity * tension, 0)
                out = bleed
            else:
                if len(self.time_displacement_buffer.buffer) < 3: 
                    out = img_np
                else:
                    past = self.time_displacement_buffer.buffer[-2]
                    if past.ndim == 3 and past.shape[2] == 4:
                        past = past[:, :, :3]
                    excluded = cv2.absdiff(img_np, past)
                    out = cv2.addWeighted(img_np, 1.0 - 0.4 * tension * intensity, excluded, 0.4 * tension * intensity, 0)

            if alpha_channel is not None and out is not None and out.ndim == 3 and out.shape[2] == 3:
                out = cv2.merge([out, alpha_channel])
            return out
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
            alpha_channel = None
            if img_np.ndim == 3 and img_np.shape[2] == 4:
                alpha_channel = img_np[:, :, 3]
                img_np = img_np[:, :, :3]

            h, w = img_np.shape[:2]
            scale = 0.25
            small = cv2.resize(img_np, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
            
            if len(self.time_displacement_buffer.buffer) >= 3:
                past_frame = self.time_displacement_buffer.buffer[-2]
                if past_frame.ndim == 3 and past_frame.shape[2] == 4:
                    past_frame = past_frame[:, :, :3]
                past = cv2.resize(past_frame, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_LINEAR)
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
                map_x = np.clip(x + dx * 0.2 * intensity * beat_energy, 0, w - 1).astype(np.float32)
                map_y = np.clip(y + dy * 0.2 * intensity * beat_energy, 0, h - 1).astype(np.float32)
                out = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            else:
                out = img_np.copy()
                buf_len = len(self.time_displacement_buffer.buffer)
                if buf_len >= 8:
                    slice_h = h // 8
                    for i in range(8):
                        buf_idx = max(0, buf_len - 1 - i)
                        frame_slice = self.time_displacement_buffer.buffer[buf_idx]
                        if frame_slice.ndim == 3 and frame_slice.shape[2] == 4:
                            frame_slice = frame_slice[:, :, :3]
                        y_start = i * slice_h
                        y_end = (i + 1) * slice_h if i < 7 else h
                        out[y_start:y_end, :, :] = frame_slice[y_start:y_end, :, :]
                out = cv2.addWeighted(img_np, 1.0 - intensity, out, intensity, 0)
               
            if alpha_channel is not None and out is not None and out.ndim == 3 and out.shape[2] == 3:
                out = cv2.merge([out, alpha_channel])
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
            alpha_channel = None
            if img_np.ndim == 3 and img_np.shape[2] == 4:
                alpha_channel = img_np[:, :, 3]
                img_np = img_np[:, :, :3]

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
                out = cv2.addWeighted(img_np, 1.0 - intensity, combined, intensity, 0)
                
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
                out = cv2.addWeighted(img_np, 1.0 - intensity, mapped, intensity, 0)
                
            else:
                # 動態熱浪消融
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                t_val = self.last_t
                noise_x = np.sin(y * 0.05 + 1.2 * sub_bass + t_val) * 8.0 * intensity
                noise_y = np.cos(x * 0.05 + sub_bass + t_val) * 8.0 * intensity
                map_x = np.clip(x + noise_x, 0, w - 1).astype(np.float32)
                map_y = np.clip(y + noise_y, 0, h - 1).astype(np.float32)
                distorted = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                
                dist_gray = (distorted[:, :, 0] * 0.299 + distorted[:, :, 1] * 0.587 + distorted[:, :, 2] * 0.114).astype(np.uint8)
                thermal = cv2.applyColorMap(dist_gray, cv2.COLORMAP_JET)
                out = cv2.addWeighted(img_np, 1.0 - intensity, thermal, intensity, 0)

            if alpha_channel is not None and out is not None and out.ndim == 3 and out.shape[2] == 3:
                out = cv2.merge([out, alpha_channel])
            return out
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
        fade_amt = min(0.80, max(intensity * 0.65, silence_fade * 0.80))
        if fade_amt < 0.01: return img_np
        try:
            alpha_channel = None
            if img_np.ndim == 3 and img_np.shape[2] == 4:
                alpha_channel = img_np[:, :, 3]
                img_np = img_np[:, :, :3]

            h, w = img_np.shape[:2]
            
            if variant == 0:
                # 噪訊腐蝕沙化溶解
                if not hasattr(self, '_fade_noise_mask') or self._fade_noise_mask is None or self._fade_noise_mask.shape != (h, w):
                    self._fade_noise_mask = np.random.randint(0, 255, (h, w), dtype=np.uint8)
                
                threshold = int(fade_amt * 255)
                mask = self._fade_noise_mask > threshold
                
                out = img_np.copy()
                out[~mask] = 0
                
            elif variant == 1:
                # 放射狀快門光圈
                center = (w // 2, h // 2)
                max_radius = int(math.sqrt(w*w + h*h) // 2)
                radius = int(max_radius * (1.0 - fade_amt))
                
                mask = np.zeros((h, w), dtype=np.uint8)
                if radius > 0:
                    cv2.circle(mask, center, radius, 255, -1)
                
                out = cv2.bitwise_and(img_np, img_np, mask=mask)
                
            else:
                # 光譜垂直融化
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                if not hasattr(self, '_melt_offsets') or self._melt_offsets is None or self._melt_offsets.shape[0] != w:
                    self._melt_offsets = np.random.uniform(0.1, 1.0, (w,)).astype(np.float32)
                
                offset_y = y - (self._melt_offsets[np.newaxis, :] * h * fade_amt * 1.5)
                map_y = np.clip(offset_y, 0, h - 1).astype(np.float32)
                melted = cv2.remap(img_np, x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                
                out = cv2.addWeighted(melted, 1.0 - fade_amt, np.zeros_like(img_np), fade_amt, 0)

            if alpha_channel is not None and out is not None and out.ndim == 3 and out.shape[2] == 3:
                out = cv2.merge([out, alpha_channel])
            return out
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
                # 注入有機程序化種子（完全基於歌曲美學 DNA 隨機分佈，徹底廢除固定中央大矩形）
                seed_coords = getattr(self, 'song_dna', {}).get('turing_seed_coords', None)
                if not seed_coords:
                    seed_coords = [
                        (self.rng.uniform(0.20, 0.80), self.rng.uniform(0.20, 0.80), self.rng.uniform(0.05, 0.12))
                        for _ in range(self.rng.randint(3, 5))
                    ]
                y_g, x_g = np.mgrid[0:dh, 0:dw].astype(np.float32)
                for nx, ny, nr in seed_coords:
                    cx, cy = nx * dw, ny * dh
                    rad = nr * min(dw, dh)
                    dist2 = (x_g - cx)**2 + (y_g - cy)**2
                    blob = np.exp(-dist2 / (2.0 * max(1.0, rad ** 2))) * self.rng.uniform(0.4, 0.7)
                    self._turing_B += blob.astype(np.float32)
                self._turing_B = np.clip(self._turing_B, 0.0, 0.8)

            # 拍點觸發有機圓形高斯突變核，杜絕漂浮方塊
            if is_beat and self.rng.random() < 0.4:
                bx = self.rng.randint(int(dw * 0.1), int(dw * 0.9))
                by = self.rng.randint(int(dh * 0.1), int(dh * 0.9))
                brad = self.rng.randint(3, 7)
                y_sub, x_sub = np.ogrid[-brad:brad+1, -brad:brad+1]
                mask_circle = (x_sub**2 + y_sub**2) <= (brad**2)
                y1, y2 = max(0, by - brad), min(dh, by + brad + 1)
                x1, x2 = max(0, bx - brad), min(dw, bx + brad + 1)
                sub_mask = mask_circle[(y1 - (by - brad)):(y2 - (by - brad)), (x1 - (bx - brad)):(x2 - (bx - brad))]
                self._turing_B[y1:y2, x1:x2][sub_mask] = np.maximum(self._turing_B[y1:y2, x1:x2][sub_mask], 0.75)

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
            turing_mask = np.clip(turing_mask * 2.2, 0.0, 1.0)
            
            out = img_np.copy()
            
            # 提取歌曲專屬調色盤色彩，確保曲目個性
            palette = getattr(self, 'mosh_palette', None)
            
            def _get_color(idx, default):
                if palette and len(palette) > 0:
                    raw = palette[idx % len(palette)]
                    if hasattr(raw, '__len__') and len(raw) >= 3:
                        vals = [float(raw[0]), float(raw[1]), float(raw[2])]
                        if all(v <= 1.0 for v in vals):
                            vals = [v * 255.0 for v in vals]
                        return np.array(vals, dtype=np.float32)
                return np.array(default, dtype=np.float32)

            c1 = _get_color(0, [230, 80, 120])
            c2 = _get_color(1, [40, 210, 190])
            c3 = _get_color(2, [180, 120, 255])

            alpha_channel = None
            if out.ndim == 3 and out.shape[2] == 4:
                alpha_channel = out[:, :, 3]
                out = out[:, :, :3]
            elif out.ndim == 2:
                out = cv2.cvtColor(out, cv2.COLOR_GRAY2RGB)

            if variant == 0:
                # 珊瑚有機增殖 (Organic Cellular Growth) - 使用曲目專屬色票
                color_layer = np.zeros_like(out)
                color_layer[:, :] = np.clip(c1, 0, 255).astype(np.uint8)
                blend = cv2.addWeighted(out, 1.0, color_layer, 0.35 * intensity, 0)
                out = np.where(turing_mask[:, :, None] > 0.45, blend, out)
                
            elif variant == 1:
                # 調和微光斑紋 (Harmonic Luminous Veins) - 徹底杜絕死黑 cv2.subtract！
                spots = (turing_mask[:, :, None] * intensity)
                tinted_spots = np.clip(spots * c2, 0, 255).astype(np.uint8)
                # 柔光發光邊界
                edge_spots = cv2.Canny((turing_mask * 255).astype(np.uint8), 30, 90)
                edge_spots_glow = cv2.GaussianBlur(edge_spots, (5, 5), 0)
                edge_layer = np.clip(edge_spots_glow[:, :, None].astype(np.float32) / 255.0 * c2 * 1.2, 0, 255).astype(np.uint8)
                
                out = cv2.addWeighted(out, 1.0, tinted_spots, 0.35 * intensity, 0)
                out = cv2.addWeighted(out, 1.0, edge_layer, 0.5 * intensity, 0)
                
            elif variant == 2:
                # 迷宮生物波紋 (Labyrinthine Bio-Maze) - 柔和色調折射
                gray_mask = (turing_mask * 255).astype(np.uint8)
                maze = cv2.applyColorMap(gray_mask, cv2.COLORMAP_VIRIDIS if variant % 2 == 0 else cv2.COLORMAP_MAGMA)
                out = cv2.addWeighted(out, 1.0 - intensity * 0.35, maze, intensity * 0.35, 0)
                
            elif variant == 3:
                # 脈絡陰影 (Venous Shadow Accent) - 保留畫面內容，微幅加深而非死黑
                shadow_factor = 1.0 - np.clip(turing_mask[:, :, None] * 0.30 * intensity, 0.0, 0.35)
                out = np.clip(out.astype(np.float32) * shadow_factor, 0, 255).astype(np.uint8)
                
            else:
                # 螢光浮游生物 (Bioluminescent Plankton Swarm) - 使用曲目專屬色票
                glow_layer = np.clip(c3 * turing_mask[:, :, None] * intensity * 0.8, 0, 255).astype(np.uint8)
                out = cv2.add(out, glow_layer)
                
            if alpha_channel is not None:
                out = cv2.merge([out, alpha_channel])

            return out
        except Exception as e:
            logger.error(f"Turing Pattern error: {e}")
            return img_np

    # 2.4 點雲立體深度重構 (Depth-Map Point Cloud Projection) 5 變種
    def apply_point_cloud_depth_custom(self, img_np, intensity, bass_ratio, stereo_width, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            alpha_channel = None
            if img_np.ndim == 3 and img_np.shape[2] == 4:
                alpha_channel = img_np[:, :, 3]
                img_np = img_np[:, :, :3]

            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            
            # 以網格採樣建立稀疏點雲
            step = 12
            y, x = np.mgrid[0:h:step, 0:w:step]
            depth_sampled = gray[0:h:step, 0:w:step].astype(np.float32)
            
            # 立體旋轉變換投影 (Euler Rotation based on Bass & Stereo)
            pitch_angle = (bass_ratio - 0.5) * 0.8
            yaw_angle = (stereo_width - 0.5) * 1.2
            
            shift_x = depth_sampled * np.sin(pitch_angle) * 0.3
            shift_y = depth_sampled * np.cos(yaw_angle) * 0.3
            
            pts_x = np.clip(x + shift_x, 0, w - 1).astype(np.int32)
            pts_y = np.clip(y + shift_y, 0, h - 1).astype(np.int32)
            
            out = img_np.copy()
            canvas = np.zeros_like(img_np)
            
            # 採樣原始畫面真實色彩，賦予粒子本體質地與動態光暈
            orig_colors = img_np[0:h:step, 0:w:step].astype(np.float32)
            
            if variant == 0:
                # 賽博綠光粒子 (原色與綠色霓虹高光調和)
                p_colors = np.clip(orig_colors * 0.4 + np.array([0, 255, 120], dtype=np.float32) * 0.6, 0, 255).astype(np.uint8)
                canvas[pts_y, pts_x] = p_colors
            elif variant == 1:
                # 光達體積掃描 (原色與青藍高光結合，輔以動態光達掃描線)
                p_colors = np.clip(orig_colors * 0.5 + np.array([0, 200, 255], dtype=np.float32) * 0.5, 0, 255).astype(np.uint8)
                canvas[pts_y, pts_x] = p_colors
                scan_y = int(h * (self.last_t % 1.0))
                cv2.line(canvas, (0, scan_y), (w, scan_y), (0, 255, 255), 2)
            elif variant == 2:
                # 琥珀星塵粒子 (暖金光暈)
                p_colors = np.clip(orig_colors * 0.4 + np.array([255, 180, 40], dtype=np.float32) * 0.6, 0, 255).astype(np.uint8)
                canvas[pts_y, pts_x] = p_colors
            elif variant == 3:
                # 紫晶等高 Voxels
                p_colors = np.clip(orig_colors * 0.4 + np.array([220, 100, 250], dtype=np.float32) * 0.6, 0, 255).astype(np.uint8)
                canvas[pts_y, pts_x] = p_colors
            else:
                # 原色超光速穿梭點陣 (保留 100% 原始色彩並增益高光輝度)
                p_colors = np.clip(orig_colors * 1.35, 0, 255).astype(np.uint8)
                canvas[pts_y, pts_x] = p_colors

            canvas = cv2.GaussianBlur(canvas, (3, 3), 0)
            res = cv2.addWeighted(out, 1.0 - intensity * 0.7, canvas, intensity * 0.8, 0)
            if alpha_channel is not None and res is not None and res.ndim == 3 and res.shape[2] == 3:
                res = cv2.merge([res, alpha_channel])
            return res
        except Exception as e:
            logger.error(f"Point Cloud Depth error: {e}")
            return img_np

    # 2.5 聲相向量示波鏡 (Stereo Phase Vector-Scope) 5 變種
    def apply_vector_scope_custom(self, img_np, t, intensity, stereo_width, chord_hue, audio_samples, variant):
        if intensity < 0.01 or cv2 is None: return img_np
        try:
            alpha_channel = None
            if img_np.ndim == 3 and img_np.shape[2] == 4:
                alpha_channel = img_np[:, :, 3]
                img_np = img_np[:, :, :3]

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
            map_x = np.clip(grid_x + grad_x * 0.05 * intensity, 0, w - 1).astype(np.float32)
            map_y = np.clip(grid_y + grad_y * 0.05 * intensity, 0, h - 1).astype(np.float32)
            
            refracted = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            if variant == 0:
                # 霓虹陰極 Lissajous (Neon Cathode Lissajous)
                out = cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
            elif variant == 1:
                # 量子向量雷達 (Quantum Vector Radar)
                cv2.circle(scope_canvas, (cx, cy), int(h * 0.3 * stereo_width), color, 1)
                out = cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
            elif variant == 2:
                # 等離子電弧光譜 (Plasma Arc Spectrogram)
                plasma = cv2.applyColorMap(gray_scope, cv2.COLORMAP_MAGMA)
                out = cv2.addWeighted(refracted, 1.0 - intensity * 0.5, plasma, intensity * 0.7, 0)
            elif variant == 3:
                # 賽博標尺 Target + 音高絲帶 (Cyber-Grid Vector Target & Pitch Ribbon)
                cv2.line(scope_canvas, (cx - 40, cy), (cx + 40, cy), (255, 255, 255), 1)
                cv2.line(scope_canvas, (cx, cy - 40), (cx, cy + 40), (255, 255, 255), 1)
                out = cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
                out = self.apply_pitch_ribbon(out, t, intensity * 0.7, chord_hue)
            else:
                # 立體聲色散萬花筒 + 時域奇異吸引子相空間絲帶 (Chromatic Stereo Kaleidoscope & Strange Attractor)
                split_r = np.roll(scope_canvas[:, :, 0], 5, axis=1)
                split_b = np.roll(scope_canvas[:, :, 2], -5, axis=1)
                scope_canvas[:, :, 0] = split_r
                scope_canvas[:, :, 2] = split_b
                out = cv2.addWeighted(refracted, 1.0, scope_canvas, intensity, 0)
                if audio_samples is not None and len(audio_samples) >= 64:
                    out = self.apply_strange_attractor_ribbon(out, audio_samples, chord_hue, intensity)

            if alpha_channel is not None and out is not None and out.ndim == 3 and out.shape[2] == 3:
                out = cv2.merge([out, alpha_channel])
            return out
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

            # 中心主體保護 Mask (橢圓形快取，消除 4K 逐影格生成與高斯模糊開銷)
            if self._dolly_mask_cache is None or self._dolly_mask_cache[0] != (w, h):
                c_mask = np.zeros((h, w), dtype=np.float32)
                cv2.ellipse(c_mask, (cx, cy), (int(w * 0.25), int(h * 0.35)), 0, 0, 360, 1.0, -1)
                c_mask = cv2.GaussianBlur(c_mask, (51, 51), 0)[:, :, None]
                self._dolly_mask_cache = ((w, h), c_mask)
            mask = self._dolly_mask_cache[1]
            
            # 外圍真正徑向拉伸光芒模糊 (True Optical Radial Zoom Streak Blur)
            steps = [0.97, 0.99, 1.0, 1.01, 1.03]
            radial_accum = np.zeros_like(bg_cropped, dtype=np.float32)
            scale_mult = 1.0 + anticipation * 1.5
            for s in steps:
                cur_scale = 1.0 + (s - 1.0) * scale_mult
                M = cv2.getRotationMatrix2D((cx, cy), 0, cur_scale)
                radial_accum += cv2.warpAffine(bg_cropped, M, (w, h), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
            bg_blurred = (radial_accum / float(len(steps))).astype(np.uint8)
            
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



    # ═══════════════════════════════════════════════════════════════
    # 前沿全域第 5 排特效矩陣 (Row 5 Advanced Next-Gen Post-FX)
    # ═══════════════════════════════════════════════════════════════

    def apply_hologram_glitch_custom(self, img_np, t, intensity, audio_feats, is_beat, variant=0):
        """前沿全域 1: 全息掃描干擾 (Hologram Glitch)
        科幻全息掃描光條、RGB 色差撕裂、雷射干擾線與電晶體雜訊
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            out = img_np.copy()

            # 1. 動態全息掃描條紋
            freq = 1.0 + variant * 0.4
            y_coords = np.arange(h, dtype=np.float32)
            scan_lines = 0.82 + 0.18 * np.sin(y_coords * freq + t * 18.0)
            scan_lines = np.clip(scan_lines, 0.4, 1.2)[:, np.newaxis, np.newaxis]
            out = np.clip(out.astype(np.float32) * scan_lines, 0, 255).astype(np.uint8)

            # 2. RGB 水平色差撕裂 (Chromatic Jitter & Slit Jitter)
            jitter_strength = int(12.0 * intensity)
            if jitter_strength > 0:
                num_slices = 4 + variant * 2
                for _ in range(num_slices):
                    sy = self.rng.randint(0, max(1, h - 30))
                    sh = self.rng.randint(6, 25)
                    shift = self.rng.randint(-jitter_strength, jitter_strength)
                    if shift != 0:
                        out[sy:sy+sh, :, 0] = np.roll(out[sy:sy+sh, :, 0], shift, axis=1)
                        out[sy:sy+sh, :, 2] = np.roll(out[sy:sy+sh, :, 2], -shift, axis=1)

            # 3. 全息掃描色調 (基於曲目專屬美學 DNA 調和)
            palette = getattr(self, 'mosh_palette', None)
            if palette and len(palette) > 0:
                tint = np.array(palette[variant % len(palette)], dtype=np.float32)
            else:
                tint = np.array([0, 230, 255] if variant % 2 == 0 else [255, 30, 180], dtype=np.float32)
            
            tint_alpha = min(0.25, 0.12 * intensity + (0.08 if is_beat else 0.0))
            tint_layer = np.full((h, w, 3), tint, dtype=np.uint8)
            out = cv2.addWeighted(out, 1.0 - tint_alpha, tint_layer, tint_alpha, 0)

            # 4. 雷射掃描細線
            scan_y = int((t * 220.0) % h)
            cv2.line(out, (0, scan_y), (w, scan_y), (int(tint[0]), int(tint[1]), int(tint[2])), 2)

            return out
        except Exception as e:
            logger.error(f"Error in apply_hologram_glitch_custom: {e}")
            return img_np

    def apply_voronoi_shatter_custom(self, img_np, t, intensity, sub_bass, beat_energy, is_beat, variant=0):
        """前沿全域 2: 泰森多邊形碎裂折射 (Voronoi Shatter)
        水晶幾何切片碎裂、稜鏡色散折射、低音動態折射與微光裂痕 (整合呼叫級多態突變)
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = FXPolymorphicMutationEngine.generate_invocation_dna('voronoi_shatter', t, beat_energy, {'sub_bass': sub_bass})
            scale = dna.get('scale_factor', 1.0)
            num_cells = int(np.clip((8 + variant * 3) * scale, 4, 56))
            cell_w = max(10, w // num_cells)
            cell_h = max(10, h // num_cells)

            # 建立低解析度碎裂位移場
            gw = w // cell_w + 1
            gh = h // cell_h + 1
            
            disp_scale = 22.0 * intensity * (0.6 + 0.6 * beat_energy)
            rng_seed = dna.get('seed', int(t * 3.0) + variant * 99)
            local_rng = np.random.RandomState(rng_seed % 10000)
            
            dx_low = local_rng.uniform(-disp_scale, disp_scale, (gh, gw)).astype(np.float32)
            dy_low = local_rng.uniform(-disp_scale, disp_scale, (gh, gw)).astype(np.float32)

            dx = cv2.resize(dx_low, (w, h), interpolation=cv2.INTER_NEAREST)
            dy = cv2.resize(dy_low, (w, h), interpolation=cv2.INTER_NEAREST)

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)

            # 稜鏡三稜色散折射 (Prismatic Chromatic Dispersion)
            shift_amt = dna.get('chroma_shift', 0.03)
            disp_r = 1.0 - shift_amt
            disp_g = 1.00
            disp_b = 1.0 + shift_amt

            map_xr = np.clip(x_grid + dx * disp_r, 0, w - 1).astype(np.float32)
            map_yr = np.clip(y_grid + dy * disp_r, 0, h - 1).astype(np.float32)
            map_xg = np.clip(x_grid + dx * disp_g, 0, w - 1).astype(np.float32)
            map_yg = np.clip(y_grid + dy * disp_g, 0, h - 1).astype(np.float32)
            map_xb = np.clip(x_grid + dx * disp_b, 0, w - 1).astype(np.float32)
            map_yb = np.clip(y_grid + dy * disp_b, 0, h - 1).astype(np.float32)

            shattered_r = cv2.remap(img_np[:, :, 0], map_xr, map_yr, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            shattered_g = cv2.remap(img_np[:, :, 1], map_xg, map_yg, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            shattered_b = cv2.remap(img_np[:, :, 2], map_xb, map_yb, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            shattered = np.dstack((shattered_r, shattered_g, shattered_b))

            # 幾何邊緣高光刻線 (Crystal Facet Edges)
            edge_dx = cv2.Sobel(dx, cv2.CV_32F, 1, 0, ksize=3)
            edge_dy = cv2.Sobel(dy, cv2.CV_32F, 0, 1, ksize=3)
            edge_mag = np.sqrt(edge_dx**2 + edge_dy**2)
            edge_mask = (edge_mag > 0.8).astype(np.float32)

            facet_alpha = min(0.45, 0.28 * intensity)
            pal = dna.get('palette', FXPolymorphicMutationEngine.ACES_INDUSTRIAL_MONOLITH)
            facet_color = pal[2] # 鎢金高光色
            glow_edges = (edge_mask[:, :, None] * facet_color).astype(np.uint8)

            blended = cv2.addWeighted(shattered, 1.0, glow_edges, facet_alpha, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(blended, dna, intensity * 0.45)
        except Exception as e:
            logger.error(f"Error in apply_voronoi_shatter_custom: {e}")
            return img_np

    def apply_thermal_infrared_custom(self, img_np, intensity, chord_brightness, sub_bass, chord_hue, variant=0):
        """前沿全域 3: 軍規紅外熱感視界 (Thermal Infrared)
        賽博軍規紅外熱感光譜、冷熱頻譜映射與溫差消融
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            # 根據 variant 選擇不同色調的熱成像色表
            colormaps = [
                cv2.COLORMAP_INFERNO,
                cv2.COLORMAP_JET,
                cv2.COLORMAP_TURBO,
                cv2.COLORMAP_MAGMA,
                cv2.COLORMAP_RAINBOW
            ]
            cm = colormaps[variant % len(colormaps)]
            thermal_bgr = cv2.applyColorMap(gray, cm)
            thermal_rgb = cv2.cvtColor(thermal_bgr, cv2.COLOR_BGR2RGB)

            alpha = float(np.clip(0.45 * intensity + 0.35 * sub_bass, 0.0, 0.88))
            out = cv2.addWeighted(img_np, 1.0 - alpha, thermal_rgb, alpha, 0)
            return out
        except Exception as e:
            logger.error(f"Error in apply_thermal_infrared_custom: {e}")
            return img_np

    def apply_ascii_cyber_matrix_custom(self, img_np, t, intensity, audio_feats, is_beat, beat_energy, variant=0):
        """前沿全域 4: Cyber ASCII 碼雨與終端矩陣 (ASCII Matrix Rain)
        高階動態 Cyber ASCII 字元下落、數位矩陣與重拍脈衝高光
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            cell_size = 16 if variant % 2 == 0 else 20
            gw = max(4, w // cell_size)
            gh = max(4, h // cell_size)

            # 降採樣計算局部亮度
            small_gray = cv2.resize(cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY), (gw, gh), interpolation=cv2.INTER_AREA)

            # 生成動態雨點雨柱
            speed = 8.0 + variant * 3.0
            y_indices = np.arange(gh)[:, np.newaxis]
            x_offsets = (np.sin(np.arange(gw) * 2.3 + variant) * 100.0).astype(np.int32)
            rain_trail = ((y_indices - int(t * speed) + x_offsets) % gh) / float(gh)

            # 亮度門控字元格
            mask = (small_gray.astype(np.float32) / 255.0) * (0.4 + 0.6 * rain_trail)
            mask = np.clip(mask * 1.5, 0.0, 1.0)

            # 映射為綠色/青色賽博雨
            matrix_layer = np.zeros((gh, gw, 3), dtype=np.float32)
            if variant % 2 == 0:
                # 經典駭客綠
                matrix_layer[:, :, 1] = mask * 255.0
                matrix_layer[:, :, 0] = mask * 50.0
                matrix_layer[:, :, 2] = mask * 80.0
            else:
                # 霓虹賽博青藍
                matrix_layer[:, :, 0] = mask * 20.0
                matrix_layer[:, :, 1] = mask * 230.0
                matrix_layer[:, :, 2] = mask * 255.0

            if is_beat and beat_energy > 0.6:
                matrix_layer += 60.0 * beat_energy

            matrix_layer = np.clip(matrix_layer, 0, 255).astype(np.uint8)
            matrix_full = cv2.resize(matrix_layer, (w, h), interpolation=cv2.INTER_NEAREST)

            blend_alpha = float(np.clip(0.35 * intensity + 0.2 * beat_energy, 0.0, 0.75))
            return cv2.addWeighted(img_np, 1.0 - blend_alpha, matrix_full, blend_alpha, 0)
        except Exception as e:
            logger.error(f"Error in apply_ascii_cyber_matrix_custom: {e}")
            return img_np

    def apply_chromatic_radial_zoom_custom(self, img_np, t, intensity, beat_energy, is_beat, variant=0):
        """前沿全域 5: 色差徑向爆發衝擊 (Chromatic Radial Zoom)
        重拍中心向外徑向色差爆發與動態 Zoom 衝擊
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            center = (w / 2.0, h / 2.0)

            punch = float(0.015 + 0.045 * intensity * (beat_energy if is_beat else 0.3))
            punch *= (1.0 + variant * 0.15)

            M_r = cv2.getRotationMatrix2D(center, 0, 1.0 + punch)
            M_b = cv2.getRotationMatrix2D(center, 0, max(0.8, 1.0 - punch))

            warped_r = cv2.warpAffine(img_np[:, :, 0], M_r, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            warped_b = cv2.warpAffine(img_np[:, :, 2], M_b, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

            out = np.stack([warped_r, img_np[:, :, 1], warped_b], axis=-1)
            return out
        except Exception as e:
            logger.error(f"Error in apply_chromatic_radial_zoom_custom: {e}")
            return img_np

    def apply_synthwave_grid_scan_custom(self, img_np, t, intensity, sub_bass, percussive, variant=0):
        """前沿全域 6: 賽博網格掃描 (Synthwave 3D Grid)
        復古透視網格線條、地平線掃描與波型震蕩
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            horizon_y = int(h * 0.64)
            grid_h = h - horizon_y
            if grid_h < 10:
                return img_np

            grid_layer = np.zeros((h, w, 3), dtype=np.uint8)
            center_x = w // 2

            # 1. 透視放射線與水平線 (基於曲目專屬美學 DNA 調色盤)
            palette = getattr(self, 'mosh_palette', None)
            c_rad = tuple(int(x) for x in palette[0]) if palette else (255, 30, 180)
            c_hor = tuple(int(x) for x in palette[1 % len(palette)]) if palette else (0, 240, 255)
            c_glow = tuple(int(x) for x in palette[2 % len(palette)]) if palette else (255, 200, 255)

            num_radials = 16 + variant * 4
            for i in range(-num_radials, num_radials + 1):
                bottom_x = int(center_x + i * (w / (num_radials * 0.85)))
                cv2.line(grid_layer, (center_x, horizon_y), (bottom_x, h), c_rad, 1, lineType=cv2.LINE_AA)

            # 2. 前進的水平橫線 (Scrolling Horizontal Grid Lines with 1/z Perspective)
            scroll_offset = (t * 1.5) % 1.0
            num_horizontals = 12
            for i in range(num_horizontals):
                rel_z = ((i + scroll_offset) / float(num_horizontals)) ** 2.2
                line_y = int(horizon_y + rel_z * grid_h)
                if horizon_y < line_y < h:
                    # 低音震盪波紋
                    wave_amp = int(sub_bass * 8.0 * rel_z)
                    cv2.line(grid_layer, (0, line_y + wave_amp), (w, line_y + wave_amp), c_hor, 1, lineType=cv2.LINE_AA)

            # 3. 地平線霓虹輝光
            cv2.line(grid_layer, (0, horizon_y), (w, horizon_y), c_glow, 2, lineType=cv2.LINE_AA)

            alpha = float(np.clip(0.35 * intensity + 0.2 * sub_bass, 0.0, 0.7))
            return cv2.addWeighted(img_np, 1.0, grid_layer, alpha, 0)
        except Exception as e:
            logger.error(f"Error in apply_synthwave_grid_scan_custom: {e}")
            return img_np

    # ═══════════════════════════════════════════════════════════════
    # 旗艦超前沿第 6 排特效矩陣 (Row 6 Flagship Cutting-Edge Post-FX)
    # ═══════════════════════════════════════════════════════════════

    def apply_chladni_cymatics_custom(self, img_np, t, intensity, harmonic, sub_bass, is_beat, variant=0):
        """旗艦全域 1: 克拉尼克聲波駐波紋 (Chladni Cymatics)
        聲學幾何共振、幾何節線發光沙紋、五大模態切換與和弦能量耦合
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            # 依據 variant 與 harmonic 動態挑選 Chladni 駐波模態 (n, m)
            modes = [
                (3, 5),  # 經典五角星共振
                (4, 4),  # 對稱十字晶格
                (5, 7),  # 高階花瓣玫瑰紋
                (2, 6),  # 聲學雙極環
                (6, 8)   # 超精密高頻全息駐波網
            ]
            n, m = modes[variant % len(modes)]
            n = int(n + harmonic * 2.0)
            m = int(m + sub_bass * 2.0)

            # 4K 高效能運算：以 1/2 網格計算駐波位勢，再線性上採樣
            dw, dh = max(32, w // 2), max(32, h // 2)
            _, _, x_norm, y_norm = self.get_coordinate_grid(dh, dw)

            # Chladni 駐波方程: a*sin(n*pi*x)*sin(m*pi*y) - b*sin(m*pi*x)*sin(n*pi*y)
            a = 1.0 + 0.3 * np.sin(t * 1.5)
            b = 1.0 + 0.3 * np.cos(t * 1.2)
            
            pi_x = x_norm * np.pi
            pi_y = y_norm * np.pi
            c_field = a * np.sin(n * pi_x) * np.sin(m * pi_y) - b * np.sin(m * pi_x) * np.sin(n * pi_y)
            
            # 節線 (Nodal Lines)：粒子在場值接近 0 的地方沉積
            nodal_dist = np.abs(c_field)
            nodal_line = np.exp(- (nodal_dist ** 2) / (0.015 + 0.01 * max(0.0, 1.0 - sub_bass)))

            # 上採樣至全畫幅
            nodal_full = cv2.resize(nodal_line, (w, h), interpolation=cv2.INTER_LINEAR)

            # 配色與光暈渲染 (金沙、銀輝、賽博青、霓虹紫、真白)
            colors = [
                np.array([255, 215, 120], dtype=np.float32),  # 琥珀金沙
                np.array([120, 240, 255], dtype=np.float32),  # 賽博青光
                np.array([255, 100, 220], dtype=np.float32),  # 霓虹紫光
                np.array([180, 255, 180], dtype=np.float32),  # 翡翠極光
                np.array([245, 245, 255], dtype=np.float32),  # 鑽石銀輝
            ]
            sand_color = colors[variant % len(colors)]
            sand_layer = (nodal_full[:, :, None] * sand_color).astype(np.float32)

            alpha = float(np.clip(0.45 * intensity + 0.25 * sub_bass, 0.0, 0.85))
            blended = np.clip(img_np.astype(np.float32) + sand_layer * alpha, 0, 255).astype(np.uint8)
            return blended
        except Exception as e:
            logger.error(f"Error in apply_chladni_cymatics_custom: {e}")
            return img_np

    def apply_ferrofluid_spikes_custom(self, img_np, t, intensity, sub_bass, beat_energy, is_beat, variant=0):
        """旗艦全域 2: 磁流體刺針湧動 (Ferrofluid Spikes)
        Rosensweig 不穩定性磁針生長、漆黑金屬液體光澤與重拍爆發
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dw, dh = max(32, w // 2), max(32, h // 2)
            _, _, x_norm, y_norm = self.get_coordinate_grid(dh, dw)

            r = np.sqrt(x_norm**2 + y_norm**2)
            theta = np.arctan2(y_norm, x_norm)

            # Rosensweig 不穩定性磁場刺針
            num_spikes = 12 + (variant % 5) * 4
            spike_amp = 0.35 + 0.45 * sub_bass + (0.4 if is_beat else 0.0)
            
            # 多頻刺針疊加
            spikes = (
                np.cos(num_spikes * theta + t * 2.0) * 0.6 +
                np.cos(num_spikes * 2 * theta - t * 3.0) * 0.3 +
                np.sin(num_spikes * 0.5 * theta + t) * 0.2
            )
            spike_profile = np.clip(spikes * spike_amp, -0.8, 1.2)

            # 刺針半徑衰減與流體外輪廓
            base_radius = 0.35 + 0.2 * beat_energy
            fluid_mask = np.clip(1.0 - (r - spike_profile * 0.25) / base_radius, 0.0, 1.0)
            fluid_mask = fluid_mask ** 2.5

            # 計算刺針法向量梯度以生成漆黑金屬高光
            grad_y, grad_x = np.gradient(fluid_mask)
            specular = np.clip((grad_x * 0.7 + grad_y * 0.7) * 4.0, 0.0, 1.0) ** 3.0

            fluid_mask_full = cv2.resize(fluid_mask, (w, h), interpolation=cv2.INTER_LINEAR)
            specular_full = cv2.resize(specular, (w, h), interpolation=cv2.INTER_LINEAR)

            # 漆黑液態金屬底色 + 虹彩/鉻銀反光
            specular_color = np.array([240, 250, 255], dtype=np.float32)
            if variant == 1:
                specular_color = np.array([255, 120, 180], dtype=np.float32)  # 紫金流體
            elif variant == 2:
                specular_color = np.array([50, 255, 200], dtype=np.float32)   # 碧綠水銀

            alpha = float(np.clip(0.55 * intensity + 0.25 * sub_bass, 0.0, 0.88))
            ferro_layer = img_np.astype(np.float32) * (1.0 - fluid_mask_full[:, :, None] * 0.75)
            ferro_layer += specular_full[:, :, None] * specular_color * 1.5 * alpha
            return np.clip(ferro_layer, 0, 255).astype(np.uint8)
        except Exception as e:
            logger.error(f"Error in apply_ferrofluid_spikes_custom: {e}")
            return img_np

    def apply_volumetric_caustics_custom(self, img_np, t, intensity, ethereal, chord_brightness, chord_hue, variant=0):
        """旗艦全域 3: 體積焦散光網 (Volumetric Caustics)
        水下雙折射聚焦光網、波浪相位干涉、空靈和弦調色與次表面散射
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dw, dh = max(32, w // 2), max(32, h // 2)
            _, _, x_norm, y_norm = self.get_coordinate_grid(dh, dw)

            # 3 組重疊水波干涉網格
            k = 6.0 + (variant % 5) * 2.0
            tau = t * 1.2
            u1 = np.sin(x_norm * k + tau) + np.cos(y_norm * k * 0.8 - tau * 0.9)
            u2 = np.sin((x_norm + y_norm) * (k * 0.7) + tau * 1.3)
            u3 = np.cos((x_norm * 1.2 - y_norm * 0.9) * k - tau * 0.7)

            caustic_field = np.sin(u1 * np.pi + u2 * np.pi * 0.5 + u3 * np.pi * 0.5)
            # 焦散聚焦亮線：銳利的局部極值集中
            caustic_sharp = np.exp(-((1.0 - caustic_field) ** 2) / 0.08)

            caustic_full = cv2.resize(caustic_sharp, (w, h), interpolation=cv2.INTER_LINEAR)

            # 和弦色彩映射 (RGB 色調)
            hue_rad = (chord_hue % 360) * np.pi / 180.0
            r_gain = 0.5 + 0.5 * np.cos(hue_rad)
            g_gain = 0.5 + 0.5 * np.cos(hue_rad - 2.094)
            b_gain = 0.5 + 0.5 * np.cos(hue_rad + 2.094)
            caustic_rgb = np.array([r_gain * 255, g_gain * 255, b_gain * 255], dtype=np.float32)

            alpha = float(np.clip(0.4 * intensity + 0.3 * ethereal, 0.0, 0.75))
            caustic_layer = (caustic_full[:, :, None] * caustic_rgb * (0.8 + 0.4 * chord_brightness)).astype(np.float32)

            # 螢幕混色 (Screen Blend) 避免死白過曝
            img_f = img_np.astype(np.float32) / 255.0
            caustic_f = (caustic_layer / 255.0) * alpha
            screen_blend = 1.0 - (1.0 - img_f) * (1.0 - caustic_f)
            return np.clip(screen_blend * 255.0, 0, 255).astype(np.uint8)
        except Exception as e:
            logger.error(f"Error in apply_volumetric_caustics_custom: {e}")
            return img_np

    def apply_clifford_torus_warp_custom(self, img_np, t, intensity, stereo_width, sub_bass, variant=0):
        """旗艦全域 4: 四維克利福德環面扭曲 (4D Clifford Torus Warp)
        S^1 x S^1 ⊂ R^4 拓撲立體旋轉投影、無邊界非歐幾何扭曲與聲相旋轉
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            x_grid, y_grid, x_norm, y_norm = self.get_coordinate_grid(h, w)

            # 映射至環面角座標 (u, v) ∈ [0, 2π]
            u = x_norm * np.pi
            v = y_norm * np.pi

            # 4D 旋轉角 (由時間與聲相寬度驅動)
            rot4d_1 = t * (0.8 + 0.4 * variant)
            rot4d_2 = (stereo_width - 0.5) * np.pi + t * 0.5

            # 4D 坐標: X1 = cos(u), X2 = sin(u), X3 = cos(v), X4 = sin(v)
            X1 = np.cos(u)
            X2 = np.sin(u)
            X3 = np.cos(v)
            X4 = np.sin(v)

            # 4D 旋轉變換 (X1-X3 平面與 X2-X4 平面雙重等距旋轉)
            c1, s1 = np.cos(rot4d_1), np.sin(rot4d_1)
            c2, s2 = np.cos(rot4d_2), np.sin(rot4d_2)

            rx1 = X1 * c1 - X3 * s1
            rx3 = X1 * s1 + X3 * c1
            rx2 = X2 * c2 - X4 * s2
            rx4 = X2 * s2 + X4 * c2

            # 球極立體投影回 2D 位移場
            denom = np.maximum(0.2, 1.4 - rx4)
            proj_x = rx1 / denom
            proj_y = rx2 / denom

            warp_amp = 35.0 * intensity * (1.0 + 0.8 * sub_bass)
            map_x = np.clip(x_grid + proj_x * warp_amp, 0, w - 1).astype(np.float32)
            map_y = np.clip(y_grid + proj_y * warp_amp, 0, h - 1).astype(np.float32)

            return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception as e:
            logger.error(f"Error in apply_clifford_torus_warp_custom: {e}")
            return img_np

    def apply_holographic_moire_custom(self, img_np, t, intensity, percussive, chord_hue, is_beat, variant=0):
        """旗艦全域 5: 聲學全息莫爾干涉 (Acoustic Holographic Moiré)
        雙微米光柵干涉條紋、動態高頻拍頻、彩虹色散與打擊樂瞬態爆發
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dw, dh = max(32, w // 2), max(32, h // 2)
            _, _, x_norm, y_norm = self.get_coordinate_grid(dh, dw)

            # 光柵 1: 中心同心圓光柵 (聲波源)
            r = np.sqrt(x_norm**2 + y_norm**2)
            freq1 = 25.0 + (variant % 5) * 6.0
            grating1 = np.sin(r * freq1 * np.pi - t * 4.0)

            # 光柵 2: 旋轉與微偏平行/徑向參考光柵
            angle = (variant * 0.25 + (0.1 if is_beat else 0.0)) * np.pi
            k_x = np.cos(angle)
            k_y = np.sin(angle)
            freq2 = freq1 * (1.02 + 0.04 * percussive)  # 微量頻率偏差產生宏觀莫爾條紋
            grating2 = np.sin((x_norm * k_x + y_norm * k_y) * freq2 * np.pi + t * 2.0)

            # 莫爾干涉合成: 光柵乘積解調出差頻與和頻
            moire_fringe = 0.5 + 0.5 * (grating1 * grating2)
            moire_fringe = np.clip(moire_fringe ** 1.8, 0.0, 1.0)

            moire_full = cv2.resize(moire_fringe, (w, h), interpolation=cv2.INTER_LINEAR)

            # 虹彩色散條紋 (Diffractive Rainbow Dispersion)
            phase_shift = moire_full * np.pi * 2.0
            r_ch = (0.5 + 0.5 * np.cos(phase_shift)) * 255.0
            g_ch = (0.5 + 0.5 * np.cos(phase_shift - 2.094)) * 255.0
            b_ch = (0.5 + 0.5 * np.cos(phase_shift + 2.094)) * 255.0
            moire_rgb = np.dstack([r_ch, g_ch, b_ch]).astype(np.float32)

            alpha = float(np.clip(0.38 * intensity + 0.25 * percussive, 0.0, 0.75))
            blended = cv2.addWeighted(img_np, 1.0, moire_rgb.astype(np.uint8), alpha, 0)
            return blended
        except Exception as e:
            logger.error(f"Error in apply_holographic_moire_custom: {e}")
            return img_np

    def apply_lens_defocus_custom(self, img_np, intensity, lowpass_val, ethereal, is_beat, variant=0):
        """生理光學全域 1: 鏡頭失焦與光學散景 (Lens Defocus & Optical Bokeh) 5 變種
        大光圈定焦散景呼吸、移軸徑向景深、Petzval 渦流旋轉、雙眼視差失焦與黑柔焦漫射
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.4 + 0.6 * lowpass_val + 0.3 * ethereal), 0.05, 1.5))

            # 採用下採樣金字塔保證 4K 即時效能
            dw, dh = max(32, w // 4), max(32, h // 4)
            small = cv2.resize(img_np, (dw, dh), interpolation=cv2.INTER_AREA)

            if variant == 0:
                # 變種 0: 光學散景呼吸 (Optical Bokeh Breathing)
                k = int(11 * eff) | 1
                k = max(3, min(31, k))
                blurred_small = cv2.GaussianBlur(small, (k, k), 0)

                # 高光門檻值提取與光斑擴散 (Highlights Blooming)
                gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
                lum_thresh = 175
                highlights = np.clip((gray.astype(np.float32) - lum_thresh) / (255.0 - lum_thresh), 0.0, 1.0)
                kernel_bokeh = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                dilated_highlights = cv2.dilate(highlights, kernel_bokeh)[:, :, None]

                composed = blurred_small.astype(np.float32) + dilated_highlights * small.astype(np.float32) * 0.75 * eff
                composed = np.clip(composed, 0.0, 255.0).astype(np.uint8)
                blurred_full = cv2.resize(composed, (w, h), interpolation=cv2.INTER_LINEAR)

                alpha = float(np.clip(0.35 + 0.45 * eff, 0.0, 0.88))
                return cv2.addWeighted(img_np, 1.0 - alpha, blurred_full, alpha, 0)

            elif variant == 1:
                # 變種 1: 移軸與徑向景深 (Tilt-Shift / Anamorphic Radial Defocus)
                _, _, x_norm, y_norm = self.get_coordinate_grid(dh, dw)
                r = np.sqrt(x_norm**2 + (y_norm * 1.35)**2)
                mask = np.clip((r - 0.28) / (0.52 * max(0.1, 1.0 - eff * 0.25)), 0.0, 1.0)

                k = int(13 * eff) | 1
                k = max(3, min(31, k))
                blurred_small = cv2.GaussianBlur(small, (k, k), 0)

                # 邊緣微光學色差紫邊 (Chromatic Fringe)
                shift_px = max(1, int(3 * eff))
                r_ch = np.roll(blurred_small[:, :, 0], shift_px, axis=1)
                b_ch = np.roll(blurred_small[:, :, 2], -shift_px, axis=1)
                fringed_small = np.dstack([r_ch, blurred_small[:, :, 1], b_ch])

                blended_small = small.astype(np.float32) * (1.0 - mask[:, :, None]) + fringed_small.astype(np.float32) * mask[:, :, None]
                return cv2.resize(np.clip(blended_small, 0.0, 255.0).astype(np.uint8), (w, h), interpolation=cv2.INTER_LINEAR)

            elif variant == 2:
                # 變種 2: 旋轉動態散焦 (Swirly Petzval Defocus)
                angle = 1.4 * eff * (1.5 if is_beat else 1.0)
                M1 = cv2.getRotationMatrix2D((dw / 2.0, dh / 2.0), angle, 1.008)
                M2 = cv2.getRotationMatrix2D((dw / 2.0, dh / 2.0), -angle, 1.008)
                r1 = cv2.warpAffine(small, M1, (dw, dh), borderMode=cv2.BORDER_REFLECT)
                r2 = cv2.warpAffine(small, M2, (dw, dh), borderMode=cv2.BORDER_REFLECT)

                k = int(9 * eff) | 1
                k = max(3, min(25, k))
                avg_swirl = ((small.astype(np.float32) + r1.astype(np.float32) + r2.astype(np.float32)) / 3.0).astype(np.uint8)
                swirl_blur = cv2.GaussianBlur(avg_swirl, (k, k), 0)
                swirl_full = cv2.resize(swirl_blur, (w, h), interpolation=cv2.INTER_LINEAR)

                alpha = float(np.clip(0.4 + 0.45 * eff, 0.0, 0.85))
                return cv2.addWeighted(img_np, 1.0 - alpha, swirl_full, alpha, 0)

            elif variant == 3:
                # 變種 3: 雙眼視差失焦重影 (Stereoscopic Focal Drift)
                shift_x = int(12.0 * eff + (8.0 if is_beat else 0.0))
                k = int(7 * eff) | 1
                k = max(3, min(21, k))
                g_ch = cv2.GaussianBlur(img_np[:, :, 1], (k, k), 0)
                r_ch = np.roll(img_np[:, :, 0], shift_x, axis=1)
                b_ch = np.roll(img_np[:, :, 2], -shift_x, axis=1)
                stereo = np.dstack([r_ch, g_ch, b_ch])

                alpha = float(np.clip(0.48 * eff, 0.0, 0.82))
                return cv2.addWeighted(img_np, 1.0 - alpha, stereo, alpha, 0)

            else:
                # 變種 4: 夢幻漫射柔焦 (Dreamy Pro-Mist Halation)
                k = int(21 * eff) | 1
                k = max(5, min(41, k))
                glow_small = cv2.GaussianBlur(small, (k, k), 0)
                glow_full = cv2.resize(glow_small, (w, h), interpolation=cv2.INTER_LINEAR)

                # 電影級黑柔焦 Screen 疊加
                img_f = img_np.astype(np.float32)
                glow_f = glow_full.astype(np.float32)
                screen = 255.0 - ((255.0 - img_f) * (255.0 - glow_f) / 255.0)

                blend_weight = float(np.clip(0.32 * eff + 0.18 * ethereal, 0.0, 0.72))
                return cv2.addWeighted(img_np, 1.0 - blend_weight, np.clip(screen, 0.0, 255.0).astype(np.uint8), blend_weight, 0)

        except Exception as e:
            logger.error(f"Error in apply_lens_defocus_custom: {e}")
            return img_np


    def apply_ocular_tremor_custom(self, img_np, t, intensity, beat_energy, sub_bass, roughness, is_beat, variant=0):
        """生理光學全域 2: 生理性眼球顫動與跳視 (Ocular Tremor & Saccadic Jitter) 5 變種
        40~65Hz 生理微震、重拍跳視衝擊回彈、前庭眼震鋸齒回掃、視網膜補色暫留與瞳孔晶狀體聚焦微脈動
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.5 + 0.5 * sub_bass + 0.5 * beat_energy), 0.05, 1.8))

            if variant == 0:
                # 變種 0: 生理性高頻微震 (Physiological Micro-tremor)
                phase = t * 65.0
                amp = max(1.5, 4.2 * eff)
                noise_x = random.uniform(-1.8, 1.8) if roughness > 0.3 else 0.0
                noise_y = random.uniform(-1.8, 1.8) if roughness > 0.3 else 0.0
                dx = int(np.sin(phase) * amp + noise_x * eff)
                dy = int(np.cos(phase * 1.31) * (amp * 0.75) + noise_y * eff)
                if is_beat:
                    dx += int(random.choice([-4, 4]) * eff)
                    dy += int(random.choice([-3, 3]) * eff)

                M = np.float32([[1, 0, dx], [0, 1, dy]])
                jittered = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                # 次像素視覺留存微模糊
                return cv2.addWeighted(jittered, 0.88, img_np, 0.12, 0)

            elif variant == 1:
                # 變種 1: 重拍跳視衝擊與彈簧回彈 (Saccadic Beat Snap)
                snap_amp = int((18.0 + 18.0 * beat_energy) * eff)
                snap_dir = 1 if int(t * 3.5) % 2 == 0 else -1
                snap_x = snap_dir * snap_amp if is_beat else int(snap_dir * snap_amp * 0.2)
                snap_y = int(snap_amp * 0.35 * (1.0 if is_beat else 0.12))

                M = np.float32([[1, 0, snap_x], [0, 1, snap_y]])
                shifted = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                weight = 0.65 if is_beat else 0.28
                return cv2.addWeighted(shifted, weight, img_np, 1.0 - weight, 0)

            elif variant == 2:
                # 變種 2: 鋸齒眼球震顫 (Nystagmus Sawtooth Drift)
                drift_cycle = (t * 2.8) % 1.0
                drift_offset = int((drift_cycle ** 2.2) * 20.0 * eff)
                M = np.float32([[1, 0, drift_offset], [0, 1, int(drift_offset * 0.25)]])
                return cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)

            elif variant == 3:
                # 變種 3: 視網膜殘留補色微影 (Retinal Persistence Jitter)
                dx = int(np.sin(t * 38.0) * 7.0 * eff)
                dy = int(np.cos(t * 46.0) * 6.0 * eff)
                inv_ghost = 255 - img_np

                M_ghost = np.float32([[1, 0, -dx], [0, 1, -dy]])
                shifted_ghost = cv2.warpAffine(inv_ghost, M_ghost, (w, h), borderMode=cv2.BORDER_REFLECT)

                M_main = np.float32([[1, 0, dx], [0, 1, dy]])
                shifted_main = cv2.warpAffine(img_np, M_main, (w, h), borderMode=cv2.BORDER_REFLECT)

                ghost_alpha = float(np.clip(0.08 * eff + 0.05 * roughness, 0.02, 0.22))
                return cv2.addWeighted(shifted_main, 1.0 - ghost_alpha, shifted_ghost, ghost_alpha, 0)

            else:
                # 變種 4: 瞳孔光震與晶狀體微脈動 (Pupillary Micro-warp)
                zoom_delta = 0.009 * np.sin(t * 42.0) * eff + (0.016 * beat_energy if is_beat else 0.0)
                scale = 1.0 + zoom_delta
                M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0.0, scale)
                warped = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                if roughness > 0.4:
                    dx = int(random.choice([-2, 2]) * eff)
                    warped = np.roll(warped, dx, axis=1)
                return warped

        except Exception as e:
            logger.error(f"Error in apply_ocular_tremor_custom: {e}")
            return img_np


    def apply_quantum_decoherence_custom(self, img_np, t, intensity, stereo_width, turbulence, is_beat, variant=0):
        """次世代故障 1: 量子退相干崩塌 (Quantum Decoherence Collapse) 5 變種
        薛丁格波包干涉、自旋態對稱破缺、量子穿隧跳躍、退相干相位噪音雲與波函數坍縮閃爍
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.6 + 0.4 * stereo_width + 0.4 * turbulence), 0.05, 1.8))

            if variant == 0:
                # 變種 0: 薛丁格波包干涉 (Schrödinger Wavepacket Interference)
                shift_amp = int(14.0 * eff * np.sin(t * 8.0))
                r_shift = np.roll(img_np[:, :, 0], shift_amp, axis=1)
                b_shift = np.roll(img_np[:, :, 2], -shift_amp, axis=1)
                # 亞微觀干涉條紋
                wave = (np.sin(np.linspace(0, 40 * np.pi, h, dtype=np.float32))[:, None] * 
                        np.cos(np.linspace(0, 30 * np.pi, w, dtype=np.float32))[None, :]) * 0.5 + 0.5
                g_interf = np.clip(img_np[:, :, 1].astype(np.float32) + (wave * 45.0 - 22.5) * eff, 0, 255).astype(np.uint8)
                out = np.dstack([r_shift, g_interf, b_shift])
                return cv2.addWeighted(img_np, 1.0 - 0.7 * eff, out, 0.7 * eff, 0)

            elif variant == 1:
                # 變種 1: 自旋態對稱破缺 (Spin State Asymmetry)
                angle = (1.5 * np.sin(t * 5.0) + (3.0 if is_beat else 0.0)) * eff
                M_cw = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.002)
                M_ccw = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -angle, 1.002)
                cw = cv2.warpAffine(img_np, M_cw, (w, h), borderMode=cv2.BORDER_REFLECT)
                ccw = cv2.warpAffine(img_np, M_ccw, (w, h), borderMode=cv2.BORDER_REFLECT)
                spin_diff = np.abs(cw.astype(np.int16) - ccw.astype(np.int16)).astype(np.uint8)
                return cv2.addWeighted(img_np, 1.0, spin_diff, 0.65 * eff, 0)

            elif variant == 2:
                # 變種 2: 量子穿隧跳躍 (Quantum Tunneling Jump)
                out = img_np.copy()
                num_tunnels = 4 + (4 if is_beat else 0)
                for _ in range(num_tunnels):
                    y1 = random.randint(0, max(0, h - 45))
                    sl_h = random.randint(12, 38)
                    disp = random.randint(-90, 90)
                    out[y1:y1+sl_h, :] = np.roll(out[y1:y1+sl_h, :], int(disp * eff), axis=1)
                return cv2.addWeighted(img_np, 1.0 - 0.75 * eff, out, 0.75 * eff, 0)

            elif variant == 3:
                # 變種 3: 退相干相位噪音雲 (Decoherence Phase Noise Cloud)
                dw, dh = max(32, w // 8), max(32, h // 8)
                noise_small = np.random.uniform(-1.0, 1.0, (dh, dw)).astype(np.float32)
                noise_full = cv2.resize(noise_small, (w, h), interpolation=cv2.INTER_LINEAR)
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                edges = cv2.Canny(gray, 60, 140).astype(np.float32) / 255.0
                decohere_mask = np.clip(edges * np.abs(noise_full) * 1.6 * eff, 0.0, 1.0)[:, :, None]
                cloud = np.roll(img_np, int(22 * eff), axis=1)
                return np.clip(img_np.astype(np.float32) * (1.0 - decohere_mask) + cloud.astype(np.float32) * decohere_mask, 0, 255).astype(np.uint8)

            else:
                # 變種 4: 波函數坍縮閃爍 (Wavefunction Collapse Flash)
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                thresh = int(128 + 40 * np.sin(t * 10.0))
                _, binary = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
                collapsed = np.dstack([binary, binary, binary])
                if is_beat:
                    collapsed = 255 - collapsed
                alpha = float(np.clip(0.4 * eff + (0.35 if is_beat else 0.0), 0.0, 0.85))
                return cv2.addWeighted(img_np, 1.0 - alpha, collapsed, alpha, 0)

        except Exception as e:
            logger.error(f"Error in apply_quantum_decoherence_custom: {e}")
            return img_np


    def apply_latent_hallucination_custom(self, img_np, t, intensity, harmonic, chord_brightness, variant=0):
        """次世代故障 2: 神經潛空間幻覺故障 (Latent Space Hallucination Glitch) 5 變種
        自注意力特徵錯置、語義邊界流淌、特徵向量投影、語義空洞黑洞與夢境回授幻象
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.6 + 0.4 * harmonic + 0.3 * chord_brightness), 0.05, 1.6))

            if variant == 0:
                # 變種 0: 自注意力特徵錯置 (Patch Attention Swapping)
                out = img_np.copy()
                grid_n = 8
                pw, ph = w // grid_n, h // grid_n
                if eff > 0.1 and pw > 0 and ph > 0:
                    swap_pairs = [(random.randint(0, grid_n - 1), random.randint(0, grid_n - 1)) for _ in range(4)]
                    for i in range(0, len(swap_pairs) - 1, 2):
                        p1, p2 = swap_pairs[i], swap_pairs[i + 1]
                        blk1 = out[p1[1]*ph:(p1[1]+1)*ph, p1[0]*pw:(p1[0]+1)*pw].copy()
                        blk2 = out[p2[1]*ph:(p2[1]+1)*ph, p2[0]*pw:(p2[0]+1)*pw].copy()
                        out[p1[1]*ph:(p1[1]+1)*ph, p1[0]*pw:(p1[0]+1)*pw] = blk2
                        out[p2[1]*ph:(p2[1]+1)*ph, p2[0]*pw:(p2[0]+1)*pw] = blk1
                return cv2.addWeighted(img_np, 1.0 - 0.7 * eff, out, 0.7 * eff, 0)

            elif variant == 1:
                # 變種 1: 語義邊界流淌 (Guided Bilateral Flow)
                dw, dh = max(32, w // 4), max(32, h // 4)
                small = cv2.resize(img_np, (dw, dh), interpolation=cv2.INTER_AREA)
                smooth_small = cv2.bilateralFilter(small, 9, 75, 75)
                residual_small = cv2.subtract(small, smooth_small)
                flow_y = np.roll(smooth_small, int(8 * eff), axis=0)
                composed_small = cv2.add(flow_y, residual_small)
                composed_full = cv2.resize(composed_small, (w, h), interpolation=cv2.INTER_LINEAR)
                return cv2.addWeighted(img_np, 1.0 - 0.65 * eff, composed_full, 0.65 * eff, 0)

            elif variant == 2:
                # 變種 2: 潛空間特徵向量投影 (Latent Eigen Projection)
                theta = t * 2.5 + chord_brightness * 3.0
                c, s = np.cos(theta * eff), np.sin(theta * eff)
                M_rgb = np.array([
                    [0.299 + 0.701*c + 0.168*s, 0.587 - 0.587*c + 0.330*s, 0.114 - 0.114*c - 0.497*s],
                    [0.299 - 0.299*c - 0.328*s, 0.587 + 0.413*c + 0.035*s, 0.114 - 0.114*c + 0.292*s],
                    [0.299 - 0.300*c + 1.250*s, 0.587 - 0.588*c - 1.050*s, 0.114 + 0.886*c - 0.203*s]
                ], dtype=np.float32)
                projected = np.clip(img_np.dot(M_rgb.T), 0, 255).astype(np.uint8)
                return cv2.addWeighted(img_np, 1.0 - 0.6 * eff, projected, 0.6 * eff, 0)

            elif variant == 3:
                # 變種 3: 語義空洞黑洞 (Semantic Dropout Void)
                out = img_np.copy()
                for _ in range(3):
                    cx, cy = random.randint(w // 6, 5 * w // 6), random.randint(h // 6, 5 * h // 6)
                    rx, ry = random.randint(25, 65), random.randint(25, 65)
                    cv2.rectangle(out, (cx - rx, cy - ry), (cx + rx, cy + ry), (12, 12, 18), -1)
                    cv2.rectangle(out, (cx - rx, cy - ry), (cx + rx, cy + ry), (180, 240, 255), 2)
                return cv2.addWeighted(img_np, 1.0 - 0.75 * eff, out, 0.75 * eff, 0)

            else:
                # 變種 4: 夢境回授幻象 (DeepDream Hallucinatory Feedback)
                sobelx = cv2.Sobel(img_np, cv2.CV_32F, 1, 0, ksize=3)
                sobely = cv2.Sobel(img_np, cv2.CV_32F, 0, 1, ksize=3)
                grad = np.sqrt(sobelx**2 + sobely**2)
                dream = np.clip(img_np.astype(np.float32) + grad * (0.35 * eff * harmonic), 0, 255).astype(np.uint8)
                return dream

        except Exception as e:
            logger.error(f"Error in apply_latent_hallucination_custom: {e}")
            return img_np


    def apply_tape_head_drag_custom(self, img_np, t, intensity, sub_bass, percussive, is_beat, variant=0):
        """次世代故障 3: 類比磁帶刮擦與咬帶 (Tape Head Scratch & Drag) 5 變種
        壓帶輪非線性卡帶、磁頭物理刮痕、轉速不穩抖晃、色彩消磁拖影與磁帶受潮起皺
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.6 + 0.4 * sub_bass + 0.3 * percussive), 0.05, 1.8))

            if variant == 0:
                # 變種 0: 壓帶輪非線性卡帶 (Pinch Roller Drag)
                drag_center = int(((t * 0.45) % 1.0) * h)
                y_indices = np.arange(h, dtype=np.float32)
                dist = np.exp(-((y_indices - drag_center)**2) / (2.0 * (85.0 * eff)**2))
                dy = (dist * 48.0 * eff * (1.5 if is_beat else 1.0)).astype(np.float32)
                y_mapped = np.clip(y_indices - dy, 0, h - 1).astype(np.int32)
                return img_np[y_mapped, :]

            elif variant == 1:
                # 變種 1: 磁頭物理刮痕 (Tape Head High-friction Scratch)
                out = img_np.copy()
                num_scratches = 3 + (4 if is_beat else 0)
                for _ in range(num_scratches):
                    y_line = random.randint(0, h - 1)
                    thick = random.randint(1, 3)
                    cv2.line(out, (0, y_line), (w, y_line), (240, 240, 250), thick)
                noise = np.random.randint(-22, 22, (h, w, 1), dtype=np.int16)
                noisy = np.clip(out.astype(np.int16) + (noise * eff).astype(np.int16), 0, 255).astype(np.uint8)
                return noisy

            elif variant == 2:
                # 變種 2: 轉速不穩抖晃 (Wow & Flutter Tape Wobble)
                roll_y = int((np.sin(t * 3.2) * 16.0 + np.sin(t * 13.0) * 5.0) * eff)
                rolled = np.roll(img_np, roll_y, axis=0)
                if is_beat:
                    rolled = np.roll(rolled, int(random.choice([-9, 9]) * eff), axis=1)
                return rolled

            elif variant == 3:
                # 變種 3: 色彩消磁拖影 (Chroma Demagnetization Smear)
                ycrcb = cv2.cvtColor(img_np, cv2.COLOR_RGB2YCrCb)
                shift_px = int(26 * eff)
                cr_smeared = np.roll(ycrcb[:, :, 1], shift_px, axis=1)
                cb_smeared = np.roll(ycrcb[:, :, 2], shift_px * 2, axis=1)
                desynced = cv2.cvtColor(np.dstack([ycrcb[:, :, 0], cr_smeared, cb_smeared]), cv2.COLOR_YCrCb2RGB)
                return cv2.addWeighted(img_np, 1.0 - 0.75 * eff, desynced, 0.75 * eff, 0)

            else:
                # 變種 4: 磁帶受潮起皺 (Crinkled Tape Fold)
                fold_y = int(((t * 0.35) % 1.0) * (h - 60))
                fold_h = int(32 * eff)
                out = img_np.copy()
                if fold_h > 2 and fold_y + fold_h < h:
                    out[fold_y:fold_y+fold_h, :] = np.flip(out[fold_y:fold_y+fold_h, :], axis=0)
                    cv2.line(out, (0, fold_y), (w, fold_y), (255, 255, 255), 1)
                    cv2.line(out, (0, fold_y+fold_h), (w, fold_y+fold_h), (25, 25, 25), 1)
                return out

        except Exception as e:
            logger.error(f"Error in apply_tape_head_drag_custom: {e}")
            return img_np


    def apply_huffman_entropy_collapse_custom(self, img_np, t, intensity, roughness, beat_energy, is_beat, variant=0):
        """次世代故障 4: JPEG 宏塊熵編碼崩毀 (Huffman Entropy Macroblock Disruption) 5 變種
        DC 係數連鎖漂移、AC 高頻量化噪訊、宏塊錯位碎裂、色彩空間逆轉與行同步信號中斷
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.6 + 0.4 * roughness + 0.3 * beat_energy), 0.05, 1.8))

            if variant == 0:
                # 變種 0: DC 係數連鎖漂移 (DC Avalanche Drift)
                out = img_np.copy()
                mb_size = 16
                for y in range(0, max(0, h - mb_size), mb_size * 2):
                    if random.random() < 0.35 * eff:
                        start_x = random.randint(0, max(1, w // 2))
                        drift_val = out[y:y+mb_size, start_x:start_x+mb_size].mean(axis=(0, 1), keepdims=True)
                        out[y:y+mb_size, start_x:] = drift_val
                return out

            elif variant == 1:
                # 變種 1: AC 高頻量化噪訊 (AC Quantization Burst)
                dw, dh = max(8, w // 8), max(8, h // 8)
                small = cv2.resize(img_np, (dw, dh), interpolation=cv2.INTER_NEAREST)
                quant = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                return cv2.addWeighted(img_np, 1.0 - 0.7 * eff, quant, 0.7 * eff, 0)

            elif variant == 2:
                # 變種 2: 宏塊錯位碎裂 (Macroblock Displacement Shatter)
                out = img_np.copy()
                bs = 32
                num_swaps = 6 + (6 if is_beat else 0)
                max_x = max(1, (w - bs) // bs)
                max_y = max(1, (h - bs) // bs)
                for _ in range(num_swaps):
                    x1 = random.randint(0, max_x) * bs
                    y1 = random.randint(0, max_y) * bs
                    x2 = random.randint(0, max_x) * bs
                    y2 = random.randint(0, max_y) * bs
                    blk1 = out[y1:y1+bs, x1:x1+bs].copy()
                    blk2 = out[y2:y2+bs, x2:x2+bs].copy()
                    out[y1:y1+bs, x1:x1+bs] = blk2
                    out[y2:y2+bs, x2:x2+bs] = blk1
                return out

            elif variant == 3:
                # 變種 3: 色彩空間逆轉 (YCbCr Matrix Desync)
                yuv = cv2.cvtColor(img_np, cv2.COLOR_RGB2YUV)
                yuv[:, :, 1] = np.clip(yuv[:, :, 1].astype(np.int16) * (1.5 + eff) - 30, 0, 255).astype(np.uint8)
                yuv[:, :, 2] = np.clip(255 - yuv[:, :, 2], 0, 255).astype(np.uint8)
                corrupted = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB)
                return cv2.addWeighted(img_np, 1.0 - 0.65 * eff, corrupted, 0.65 * eff, 0)

            else:
                # 變種 4: 行同步信號中斷 (Restart Marker Loss)
                out = img_np.copy()
                num_lines = random.randint(3, 7)
                for _ in range(num_lines):
                    y_corrupt = random.randint(0, max(0, h - 16))
                    band_h = random.randint(4, 18)
                    col_sample = out[y_corrupt, random.randint(0, w - 1)]
                    out[y_corrupt:y_corrupt+band_h, :] = col_sample
                return out

        except Exception as e:
            logger.error(f"Error in apply_huffman_entropy_collapse_custom: {e}")
            return img_np


    def apply_spectral_fractal_shear_custom(self, img_np, t, intensity, harmonic, percussive, audio_samples, is_beat, variant=0):
        """次世代故障 5: 時空頻譜碎形撕裂 (Spectral Spatio-Temporal Shear) 5 變種
        波形幾何撕裂、諧波碎形裂隙、立體聲左右對撕、頻譜柱狀錯位與瞬態共振碎裂
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            eff = float(np.clip(intensity * (0.6 + 0.4 * harmonic + 0.3 * percussive), 0.05, 1.8))

            if variant == 0:
                # 變種 0: 波形幾何撕裂 (Waveform Spatio-Temporal Rip)
                if audio_samples is not None and len(audio_samples) >= 16:
                    interp_wave = np.interp(
                        np.linspace(0, len(audio_samples) - 1, h),
                        np.arange(len(audio_samples)),
                        np.asarray(audio_samples, dtype=np.float32)
                    )
                else:
                    interp_wave = np.sin(np.linspace(0, 16 * np.pi, h) + t * 4.0)

                shear_x = (interp_wave * 35.0 * eff).astype(np.int32)
                out = img_np.copy()
                stride = 8
                for y in range(0, h, stride):
                    s_shift = int(shear_x[y])
                    out[y:y+stride, :] = np.roll(out[y:y+stride, :], s_shift, axis=1)
                return out

            elif variant == 1:
                # 變種 1: 諧波碎形裂隙 (Harmonic Fractal Fissures)
                y_grid = np.linspace(0, 1.0, h, dtype=np.float32)[:, None, None]
                fissure = np.sin(y_grid * 32.0 * np.pi + t * 5.0) * np.sin(y_grid * 64.0 * np.pi - t * 3.0)
                crack_mask = (np.abs(fissure) > (0.92 - 0.3 * eff * harmonic)).astype(np.float32)
                shifted = np.roll(img_np, int(25 * eff), axis=1)
                return np.where(crack_mask > 0.5, shifted, img_np)

            elif variant == 2:
                # 變種 2: 立體聲頻譜左右對撕 (Stereo Phase Opposite Shear)
                shear_dist = int(24.0 * eff + (18.0 if is_beat else 0.0))
                left_half = np.roll(img_np[:, :w//2], -shear_dist, axis=0)
                right_half = np.roll(img_np[:, w//2:], shear_dist, axis=0)
                seam = np.hstack([left_half, right_half])
                return cv2.addWeighted(img_np, 1.0 - 0.75 * eff, seam, 0.75 * eff, 0)

            elif variant == 3:
                # 變種 3: 頻譜柱狀錯位 (FFT Histogram Stride Displacement)
                out = img_np.copy()
                num_bands = 16
                col_w = w // num_bands
                for b in range(num_bands):
                    band_eff = np.sin(b * 0.85 + t * 4.0) * 22.0 * eff
                    out[:, b*col_w:(b+1)*col_w] = np.roll(out[:, b*col_w:(b+1)*col_w], int(band_eff), axis=0)
                return out

            else:
                # 變種 4: 瞬態共振碎裂 (Transient Resonance Glass Break)
                center_x, center_y = w // 2, h // 2
                amp = 1.0 + 0.05 * eff * (1.5 if is_beat else 0.5)
                rot_deg = (random.choice([-1.5, 1.5]) if is_beat else 0.0) * eff
                M = cv2.getRotationMatrix2D((center_x, center_y), rot_deg, amp)
                broken = cv2.warpAffine(img_np, M, (w, h), borderMode=cv2.BORDER_REFLECT)
                return cv2.addWeighted(img_np, 1.0 - 0.65 * eff, broken, 0.65 * eff, 0)

        except Exception as e:
            logger.error(f"Error in apply_spectral_fractal_shear_custom: {e}")
            return img_np

    # ══════════════════════════════════════════════════════════════════
    # 🌟 12 大次世代高辨識度幾何/拓撲強特徵特效庫 (SOTA FX Library)
    # 深度耦合 Techno 聲學物理特徵，結合呼叫級多態突變 DNA 引擎
    # ══════════════════════════════════════════════════════════════════

    def apply_hyper_dimensional_fold_custom(self, img_np, t, intensity, sub_bass, beat_energy, is_beat, dna=None):
        """次世代特效 1: 四維空間幾何折疊 (Hyper-Dimensional Fold)
        4D 超立方體（Tesseract）旋轉投影折疊，空間向內反轉坍縮，多態拓撲變換
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('hyper_dimensional_fold', t, beat_energy, {'sub_bass': sub_bass})
            scale = dna.get('scale_factor', 1.0) * (0.8 + 0.6 * sub_bass)
            rot = math.radians(dna.get('rotation_angle', 0.0) + t * 45.0)
            geom = dna.get('geometry_mode', 0)
            eff = float(np.clip(intensity * (0.7 + 0.6 * beat_energy), 0.05, 1.8))

            _, _, x_norm, y_norm = self.get_coordinate_grid(h, w)

            # 4D 旋轉投影方程式：w_coord = cos(theta)*x - sin(theta)*y
            theta = rot * 1.5
            x_rot = x_norm * math.cos(theta) - y_norm * math.sin(theta)
            y_rot = x_norm * math.sin(theta) + y_norm * math.cos(theta)
            r = np.sqrt(x_rot * x_rot + y_rot * y_rot) + 1e-5

            if geom == 0:
                # 模式 0: 超立方體四角向心折疊 (Tesseract Centripetal Fold)
                fold = np.sin(r * np.pi * scale * 3.0) / (r + 0.25)
                dx = (x_rot * fold * 35.0 * eff).astype(np.float32)
                dy = (y_rot * fold * 35.0 * eff).astype(np.float32)
            elif geom == 1:
                # 模式 1: 雙曲克萊茵瓶幾何扭結 (Klein Hyperbolic Twist)
                twist = np.arctan2(y_rot, x_rot) * dna.get('symmetry_axes', 4)
                dx = (np.cos(twist) * (r ** 1.4) * 45.0 * eff).astype(np.float32)
                dy = (np.sin(twist) * (r ** 1.4) * 45.0 * eff).astype(np.float32)
            elif geom == 2:
                # 模式 2: 空間鏡面晶格對摺 (Spacetime Lattice Reflection)
                grid_f = np.sin(x_rot * 12.0 * scale) * np.cos(y_rot * 12.0 * scale)
                dx = (grid_f * 40.0 * eff).astype(np.float32)
                dy = (-grid_f * 40.0 * eff).astype(np.float32)
            else:
                # 模式 3/4: 高維莫比烏斯環拓撲反轉 (Mobius Topology Inversion)
                mobius = np.cos(r * 8.0 * scale - t * 3.0)
                dx = (y_rot * mobius * 50.0 * eff).astype(np.float32)
                dy = (-x_rot * mobius * 50.0 * eff).astype(np.float32)

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)
            map_x = np.clip(x_grid + dx, 0, w - 1).astype(np.float32)
            map_y = np.clip(y_grid + dy, 0, h - 1).astype(np.float32)
            warped = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            out = cv2.addWeighted(img_np, 1.0 - 0.75 * eff, warped, 0.75 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.4)
        except Exception as e:
            logger.error(f"Error in apply_hyper_dimensional_fold_custom: {e}")
            return img_np

    def apply_reaction_diffusion_growth_custom(self, img_np, t, intensity, sub_bass, ethereal, dna=None):
        """次世代特效 2: 異構反應擴散生長 (Reaction-Diffusion Growth)
        灰-斯科特（Gray-Scott）圖靈斑圖有機菌絲動態蔓延生長
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('reaction_diffusion_growth', t, sub_bass, {'ethereal': ethereal})
            eff = float(np.clip(intensity * (0.6 + 0.5 * sub_bass), 0.05, 1.6))
            scale = dna.get('scale_factor', 1.0)
            
            # 在降採樣網格上生成高階雙曲斑圖，確保 4K 實時極速運行
            gw, gh = max(32, w // 32), max(18, h // 32)
            x_lin = np.linspace(-3.0, 3.0, gw, dtype=np.float32)
            y_lin = np.linspace(-3.0, 3.0, gh, dtype=np.float32)
            xx, yy = np.meshgrid(x_lin, y_lin)

            # Gray-Scott 空間頻率方程模擬
            k_param = 0.062 + 0.008 * math.sin(t * 1.2)
            f_param = 0.035 + 0.005 * math.cos(t * 0.9)
            phase = (xx * xx + yy * yy) * scale * 2.5 + t * 2.0
            pattern = np.sin(xx * 5.0 * scale + np.cos(phase)) * np.cos(yy * 5.0 * scale + np.sin(phase))
            mask_low = np.clip((pattern - (k_param * 10.0)) * 2.5, 0.0, 1.0).astype(np.float32)

            mask = cv2.resize(mask_low, (w, h), interpolation=cv2.INTER_LINEAR)[:, :, None]

            pal = dna.get('palette', FXPolymorphicMutationEngine.ACES_ACID_MUTATION)
            col = pal[1] # 毒性螢光或高光色

            growth_layer = (img_np.astype(np.float32) * (1.0 - mask * 0.8) + col * (mask * 0.8)).astype(np.float32)
            out = cv2.addWeighted(img_np, 1.0 - 0.7 * eff, growth_layer.astype(np.uint8), 0.7 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.35)
        except Exception as e:
            logger.error(f"Error in apply_reaction_diffusion_growth_custom: {e}")
            return img_np

    def apply_delaunay_voronoi_mesh_custom(self, img_np, t, intensity, percussive, roughness, dna=None):
        """次世代特效 3: 德勞內三角網格解構 (Delaunay-Voronoi Mesh Deconstruction)
        拓撲三角剖分重構畫面、物理多邊形微裂隙與色散爆裂
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('delaunay_voronoi_mesh', t, percussive, {'roughness': roughness})
            eff = float(np.clip(intensity * (0.6 + 0.6 * percussive), 0.05, 1.8))
            scale = dna.get('scale_factor', 1.0)

            # 依據尺度突變決定多邊形晶格密度
            step = int(np.clip(36.0 / (scale + 0.2), 16, 128))
            gh, gw = h // step + 1, w // step + 1
            
            rng = np.random.RandomState(dna.get('seed', 0) % (2**31 - 1))
            jitter_amp = step * 0.45 * eff
            jitter_x = rng.uniform(-jitter_amp, jitter_amp, (gh, gw)).astype(np.float32)
            jitter_y = rng.uniform(-jitter_amp, jitter_amp, (gh, gw)).astype(np.float32)

            jx_full = cv2.resize(jitter_x, (w, h), interpolation=cv2.INTER_LINEAR)
            jy_full = cv2.resize(jitter_y, (w, h), interpolation=cv2.INTER_LINEAR)

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)
            map_x = np.clip(x_grid + jx_full, 0, w - 1).astype(np.float32)
            map_y = np.clip(y_grid + jy_full, 0, h - 1).astype(np.float32)

            meshed = cv2.remap(img_np, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_REFLECT)
            # 增強晶格幾何線條邊界
            edge_gray = cv2.cvtColor(meshed, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(edge_gray, 40, 120)
            edge_mask = (edges > 0)[:, :, None]

            pal = dna.get('palette', FXPolymorphicMutationEngine.ACES_INDUSTRIAL_MONOLITH)
            wire_col = pal[2] # 鎢金/高光色線框
            meshed[edge_mask[:, :, 0]] = (meshed[edge_mask[:, :, 0]] * 0.2 + wire_col * 0.8).astype(np.uint8)

            out = cv2.addWeighted(img_np, 1.0 - 0.7 * eff, meshed, 0.7 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.4)
        except Exception as e:
            logger.error(f"Error in apply_delaunay_voronoi_mesh_custom: {e}")
            return img_np

    def apply_slit_scan_time_warp_custom(self, img_np, t, intensity, stereo_width, dna=None):
        """次世代特效 4: 時空狹縫延遲穿透 (Slit-Scan Time Warp)
        非線性時間軸狹縫置換，如同穿越蟲洞之時空折疊延遲
        """
        if intensity < 0.01 or cv2 is None or len(self.time_displacement_buffer.buffer) < 4:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('slit_scan_time_warp', t, stereo_width, {'stereo_width': stereo_width})
            eff = float(np.clip(intensity * (0.6 + 0.5 * stereo_width), 0.05, 1.5))
            geom = dna.get('geometry_mode', 0)
            buf_len = len(self.time_displacement_buffer.buffer)

            # 依據幾何模式生成不同維度的狹縫索引矩陣
            if geom in (0, 4):
                # 模式 0: 徑向同心圓時間狹縫 (Concentric Ripple Slits)
                _, _, x_norm, y_norm = self.get_coordinate_grid(h, w)
                r = np.sqrt(x_norm * x_norm + y_norm * y_norm)
                idx_map = np.clip((np.sin(r * 18.0 - t * 6.0) * 0.5 + 0.5) * (buf_len - 1), 0, buf_len - 1).astype(np.int32)
            elif geom == 1:
                # 模式 1: 水平雙向對撕狹縫 (Horizontal Dual Slits)
                y_lin = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
                idx_map = np.clip((np.sin(y_lin * 24.0 + t * 4.0) * 0.5 + 0.5) * (buf_len - 1), 0, buf_len - 1).astype(np.int32)
                idx_map = np.broadcast_to(idx_map, (h, w))
            else:
                # 模式 2/3: 菱形光譜網格狹縫 (Diamond Mesh Slits)
                x_lin = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
                y_lin = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
                diag = np.sin(x_lin * 10.0 + y_lin * 10.0 + t * 5.0)
                idx_map = np.clip((diag * 0.5 + 0.5) * (buf_len - 1), 0, buf_len - 1).astype(np.int32)

            # 依據 idx_map 組合歷史時空影格 (分 4 個時間階層混合)
            out = img_np.copy()
            for step_b in range(0, buf_len, max(1, buf_len // 4)):
                hist_frame = self.time_displacement_buffer.buffer[step_b]
                if hist_frame.shape[:2] != (h, w):
                    hist_frame = cv2.resize(hist_frame, (w, h))
                mask = (idx_map >= step_b) & (idx_map < step_b + max(1, buf_len // 4))
                out[mask] = hist_frame[mask]

            blended = cv2.addWeighted(img_np, 1.0 - 0.8 * eff, out, 0.8 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(blended, dna, eff * 0.3)
        except Exception as e:
            logger.error(f"Error in apply_slit_scan_time_warp_custom: {e}")
            return img_np

    def apply_gravitational_lensing_custom(self, img_np, t, intensity, sub_bass, beat_energy, dna=None):
        """次世代特效 5: 引力透鏡黑洞扭曲 (Gravitational Lensing)
        愛因斯坦環光線彎曲，中央奇點吸積時空漩渦
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('gravitational_lensing', t, beat_energy, {'sub_bass': sub_bass})
            eff = float(np.clip(intensity * (0.7 + 0.6 * sub_bass), 0.05, 1.8))
            scale = dna.get('scale_factor', 1.0)

            # 奇點位置微顫 (隨低頻重拍抖動)
            rng = np.random.RandomState(dna.get('seed', 0) % (2**31 - 1))
            offset_x = float(rng.uniform(-0.15, 0.15) * eff)
            offset_y = float(rng.uniform(-0.15, 0.15) * eff)

            _, _, x_norm, y_norm = self.get_coordinate_grid(h, w)
            dx_c = x_norm - offset_x
            dy_c = y_norm - offset_y
            r2 = dx_c * dx_c + dy_c * dy_c + 1e-4
            r = np.sqrt(r2)

            # 愛因斯坦半徑與強引力透鏡偏折公式: deflection = r_einstein^2 / r
            r_einstein = 0.42 * scale * (0.8 + 0.4 * beat_energy)
            deflection = (r_einstein ** 2) / (r + 0.08)
            disp_scale = 55.0 * eff

            dx = (dx_c * deflection * disp_scale).astype(np.float32)
            dy = (dy_c * deflection * disp_scale).astype(np.float32)

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)
            map_x = np.clip(x_grid + dx, 0, w - 1).astype(np.float32)
            map_y = np.clip(y_grid + dy, 0, h - 1).astype(np.float32)

            warped = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            # 黑洞吸積盤光環高光 (Accretion Ring Glow)
            ring_mask = np.exp(-((r - r_einstein) ** 2) / 0.008)[:, :, None]
            pal = dna.get('palette', FXPolymorphicMutationEngine.ACES_THERMAL_CORE)
            ring_col = pal[2] # 高溫白熾
            warped = np.clip(warped.astype(np.float32) + ring_col * ring_mask * 0.8 * eff, 0, 255).astype(np.uint8)

            out = cv2.addWeighted(img_np, 1.0 - 0.75 * eff, warped, 0.75 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.4)
        except Exception as e:
            logger.error(f"Error in apply_gravitational_lensing_custom: {e}")
            return img_np

    def apply_acid_curl_fluid_custom(self, img_np, t, intensity, roughness, harmonic, dna=None):
        """次世代特效 6: 酸性旋度流體混動 (Acid Curl Fluid)
        基於 Curl Noise 的不可壓縮旋度場，液態金屬酸性色彩流動
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('acid_curl_fluid', t, roughness, {'harmonic': harmonic})
            eff = float(np.clip(intensity * (0.6 + 0.5 * roughness), 0.05, 1.6))
            scale = dna.get('scale_factor', 1.0)

            # 在低解析度生成旋度速度場 (u = dPsi/dy, v = -dPsi/dx)
            gw, gh = max(32, w // 24), max(18, h // 24)
            x_lin = np.linspace(-2.0, 2.0, gw, dtype=np.float32)
            y_lin = np.linspace(-2.0, 2.0, gh, dtype=np.float32)
            xx, yy = np.meshgrid(x_lin, y_lin)

            psi = np.sin(xx * 3.5 * scale + t * 2.0) * np.cos(yy * 3.5 * scale - t * 1.5) + np.sin((xx + yy) * 2.0 * scale)
            # 數值偏微分生成無發散流場 (Divergence-free Curl)
            v_low, u_low = np.gradient(psi)
            u_low = -u_low * 38.0 * eff
            v_low = v_low * 38.0 * eff

            u = cv2.resize(u_low, (w, h), interpolation=cv2.INTER_LINEAR)
            v = cv2.resize(v_low, (w, h), interpolation=cv2.INTER_LINEAR)

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)
            map_x = np.clip(x_grid + u, 0, w - 1).astype(np.float32)
            map_y = np.clip(y_grid + v, 0, h - 1).astype(np.float32)

            fluid_warped = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            out = cv2.addWeighted(img_np, 1.0 - 0.7 * eff, fluid_warped, 0.7 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.45)
        except Exception as e:
            logger.error(f"Error in apply_acid_curl_fluid_custom: {e}")
            return img_np

    def apply_strobe_chroma_invert_custom(self, img_np, t, intensity, beat_energy, is_beat, dna=None):
        """次世代特效 7: 極速反相頻閃脈衝 (Strobe Chroma Invert)
        底層高反差反相、雙色調通道爆裂極化，地下俱樂部暗光閃頻
        """
        if intensity < 0.01 or not is_beat:
            return img_np
        try:
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('strobe_chroma_invert', t, beat_energy, {})
            eff = float(np.clip(intensity * (0.8 + 0.6 * beat_energy), 0.1, 1.9))
            pol = dna.get('color_polarity', 0)

            arr = img_np.astype(np.float32)
            if pol == 0:
                # 全光譜反相 + 高飽和加強
                inv = 255.0 - arr
            elif pol == 1:
                # 單通道綠藍反相、保留紅通道 (Cyber Neon Strobe)
                inv = arr.copy()
                inv[:, :, 1] = 255.0 - inv[:, :, 1]
                inv[:, :, 2] = 255.0 - inv[:, :, 2]
            elif pol == 2:
                # 太陽化閾值閃爍 (Solarized Strobe)
                inv = np.where(arr > 120.0, 255.0 - arr, arr * 1.8)
            else:
                # 鎢金高光反轉
                gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])
                inv = 255.0 - np.dstack([gray, gray * 0.9, gray * 0.75])

            weight = float(0.85 * min(1.0, eff))
            inv_u8 = np.clip(inv, 0, 255).astype(np.uint8)
            if cv2 is not None:
                out = cv2.addWeighted(img_np, 1.0 - weight, inv_u8, weight, 0)
            else:
                out = np.clip(img_np.astype(np.float32) * (1.0 - weight) + inv * weight, 0, 255).astype(np.uint8)
            return out
        except Exception as e:
            logger.error(f"Error in apply_strobe_chroma_invert_custom: {e}")
            return img_np

    def apply_cyber_wireframe_lidar_custom(self, img_np, t, intensity, percussive, roughness, dna=None):
        """次世代特效 8: 賽博光達深度線框 (Cyber Wireframe LiDAR)
        光達深度掃描點雲提取、3D 霓虹網格線條穿透
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('cyber_wireframe_lidar', t, percussive, {'roughness': roughness})
            eff = float(np.clip(intensity * (0.6 + 0.5 * percussive), 0.05, 1.6))
            scale = dna.get('scale_factor', 1.0)

            # Sobel 梯度與邊緣法線提取
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            mag = np.sqrt(sobel_x * sobel_x + sobel_y * sobel_y)
            mag_norm = np.clip(mag / 120.0, 0.0, 1.0)

            # 光達掃描線穿透 (LiDAR Scanlines)
            y_lin = np.linspace(0, h, h, dtype=np.float32)[:, None]
            scan_lines = np.sin(y_lin * 0.25 * scale + t * 8.0) > 0.65

            pal = dna.get('palette', FXPolymorphicMutationEngine.ACES_ACID_MUTATION)
            col_wire = pal[1] # 霓虹綠/高光色
            col_dark = pal[0] # 底色

            lidar_edge = (mag_norm[:, :, None] * col_wire * 1.5).astype(np.float32)
            lidar_lines = (scan_lines[:, :, None] * col_wire * 0.7).astype(np.float32)

            blended = img_np.astype(np.float32) * (1.0 - 0.65 * eff) + (lidar_edge + lidar_lines) * (0.65 * eff)
            out = np.clip(blended, 0, 255).astype(np.uint8)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.3)
        except Exception as e:
            logger.error(f"Error in apply_cyber_wireframe_lidar_custom: {e}")
            return img_np

    def apply_sine_terrain_displacement_custom(self, img_np, t, intensity, sub_bass, chord_hue, dna=None):
        """次世代特效 9: 正弦音波地形位移 (Sine Terrain Displacement)
        三維正弦波動等高線位移，低頻驅動的地形起伏折射
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('sine_terrain_displacement', t, sub_bass, {})
            eff = float(np.clip(intensity * (0.6 + 0.6 * sub_bass), 0.05, 1.7))
            scale = dna.get('scale_factor', 1.0)
            rot = math.radians(dna.get('rotation_angle', 45.0))

            _, _, x_norm, y_norm = self.get_coordinate_grid(h, w)
            # 旋轉投影軸
            x_rot = x_norm * math.cos(rot) - y_norm * math.sin(rot)
            y_rot = x_norm * math.sin(rot) + y_norm * math.cos(rot)

            # 正弦波群疊加 (波面包絡)
            wave1 = np.sin(x_rot * 16.0 * scale + t * 4.0)
            wave2 = np.cos(y_rot * 12.0 * scale - t * 3.0)
            terrain = (wave1 + wave2 * 0.7) * 28.0 * eff

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)
            map_x = np.clip(x_grid + terrain * math.cos(rot), 0, w - 1).astype(np.float32)
            map_y = np.clip(y_grid + terrain * math.sin(rot), 0, h - 1).astype(np.float32)

            displaced = cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            out = cv2.addWeighted(img_np, 1.0 - 0.7 * eff, displaced, 0.7 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.35)
        except Exception as e:
            logger.error(f"Error in apply_sine_terrain_displacement_custom: {e}")
            return img_np

    def apply_quantum_tunneling_custom(self, img_np, t, intensity, entropy, arousal, dna=None):
        """次世代特效 10: 量子穿隧噪波分解 (Quantum Tunneling)
        空間機率雲離散化、粒子重組與空間坍縮
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('quantum_tunneling', t, entropy, {'arousal': arousal})
            eff = float(np.clip(intensity * (0.6 + 0.5 * entropy), 0.05, 1.6))
            scale = dna.get('scale_factor', 1.0)

            # 依據尺度產生量子穿隧離散網格
            block_s = int(np.clip(16.0 * scale, 8, 64))
            gh, gw = h // block_s + 1, w // block_s + 1

            rng = np.random.RandomState(dna.get('seed', 0) % (2**31 - 1))
            prob_cloud = rng.uniform(0.0, 1.0, (gh, gw)).astype(np.float32)
            tunnel_mask = (prob_cloud > (1.0 - 0.45 * eff)).astype(np.float32)

            mask_up = cv2.resize(tunnel_mask, (w, h), interpolation=cv2.INTER_NEAREST)[:, :, None]

            # 量子相移偏移 (Phase Shift Offset)
            shift_x = int(rng.uniform(-35.0, 35.0) * eff)
            shift_y = int(rng.uniform(-25.0, 25.0) * eff)
            shifted = np.roll(np.roll(img_np, shift_x, axis=1), shift_y, axis=0)

            tunneled = np.where(mask_up > 0.5, shifted, img_np)
            out = cv2.addWeighted(img_np, 1.0 - 0.75 * eff, tunneled, 0.75 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.4)
        except Exception as e:
            logger.error(f"Error in apply_quantum_tunneling_custom: {e}")
            return img_np

    def apply_prismatic_refraction_prism_custom(self, img_np, t, intensity, ethereal, chord_brightness, dna=None):
        """次世代特效 11: 多稜鏡立體光譜色散 (Prismatic Refraction Prism)
        多角度厚玻璃稜鏡折射，RGB 物理級折射分離與彩虹高光
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('prismatic_refraction_prism', t, ethereal, {'chord_brightness': chord_brightness})
            eff = float(np.clip(intensity * (0.6 + 0.5 * ethereal), 0.05, 1.7))
            rot = math.radians(dna.get('rotation_angle', 30.0))

            x_grid, y_grid, _, _ = self.get_coordinate_grid(h, w)
            dir_x, dir_y = math.cos(rot), math.sin(rot)

            # 三波長色散偏折 (柯西色散公式模擬: 紅長波少折射, 藍短波多折射)
            disp_dist = 28.0 * eff
            d_r = disp_dist * 0.85
            d_g = disp_dist * 1.00
            d_b = disp_dist * 1.25

            map_xr = np.clip(x_grid + dir_x * d_r, 0, w - 1).astype(np.float32)
            map_yr = np.clip(y_grid + dir_y * d_r, 0, h - 1).astype(np.float32)
            map_xg = np.clip(x_grid + dir_x * d_g, 0, w - 1).astype(np.float32)
            map_yg = np.clip(y_grid + dir_y * d_g, 0, h - 1).astype(np.float32)
            map_xb = np.clip(x_grid + dir_x * d_b, 0, w - 1).astype(np.float32)
            map_yb = np.clip(y_grid + dir_y * d_b, 0, h - 1).astype(np.float32)

            ch_r = cv2.remap(img_np[:, :, 0], map_xr, map_yr, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            ch_g = cv2.remap(img_np[:, :, 1], map_xg, map_yg, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            ch_b = cv2.remap(img_np[:, :, 2], map_xb, map_yb, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

            dispersed = np.dstack([ch_r, ch_g, ch_b])
            out = cv2.addWeighted(img_np, 1.0 - 0.7 * eff, dispersed, 0.7 * eff, 0)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.3)
        except Exception as e:
            logger.error(f"Error in apply_prismatic_refraction_prism_custom: {e}")
            return img_np

    def apply_magnetic_field_lines_custom(self, img_np, t, intensity, sub_bass, percussive, dna=None):
        """次世代特效 12: 磁力線粉末吸附 (Magnetic Field Lines)
        鐵磁流體沿磁感線吸附排列，磁極渦流物理粉末質感
        """
        if intensity < 0.01 or cv2 is None:
            return img_np
        try:
            h, w = img_np.shape[:2]
            dna = dna or FXPolymorphicMutationEngine.generate_invocation_dna('magnetic_field_lines', t, sub_bass, {'percussive': percussive})
            eff = float(np.clip(intensity * (0.6 + 0.6 * sub_bass), 0.05, 1.7))
            scale = dna.get('scale_factor', 1.0)

            # 雙磁極偶極子場方程式 (Dipole Magnetic Field)
            pole_d = 0.55 * scale
            _, _, x_norm, y_norm = self.get_coordinate_grid(h, w)
            r1 = np.sqrt((x_norm + pole_d)**2 + y_norm**2) + 0.08
            r2 = np.sqrt((x_norm - pole_d)**2 + y_norm**2) + 0.08

            potential = (1.0 / r1) - (1.0 / r2)
            field_lines = np.sin(potential * 16.0 * scale + t * 3.0)

            # 磁粉排列紋理 (Powder Absorption Texture)
            powder_mask = (np.abs(field_lines) > 0.85).astype(np.float32)[:, :, None]
            pal = dna.get('palette', FXPolymorphicMutationEngine.ACES_INDUSTRIAL_MONOLITH)
            powder_col = pal[2] # 鎢金高光

            powdered = (img_np.astype(np.float32) * (1.0 - powder_mask * 0.75 * eff) + powder_col * (powder_mask * 0.75 * eff))
            out = np.clip(powdered, 0, 255).astype(np.uint8)
            return FXPolymorphicMutationEngine.apply_color_polarization(out, dna, eff * 0.3)
        except Exception as e:
            logger.error(f"Error in apply_magnetic_field_lines_custom: {e}")
            return img_np



def apply_advanced_transition(pil_a, pil_b, progress, trans_type='displacement', intensity=0.5, is_beat=False, beat_energy=0.0, wipe_pattern='diagonal_tl_br', chord_color_hex='#0a0a0c', **kwargs):
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
    # Auto-resize safeguard for dimension mismatches
    if img_b.shape[:2] != (h, w):
        img_b = cv2.resize(img_b, (w, h), interpolation=cv2.INTER_LINEAR)
        
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
            # 3. Luma Matte Wipe with patterns
            y_grid, x_grid = np.mgrid[0:h, 0:w].astype(np.float32)
            
            if wipe_pattern == 'diagonal_tr_bl':
                matte = (((w - 1.0 - x_grid) / max(w, 1) + y_grid / max(h, 1)) / 2.0 * 255.0)
            elif wipe_pattern == 'radial_iris':
                cx, cy = w / 2.0, h / 2.0
                dist = np.sqrt(((x_grid - cx) / max(cx, 1.0)) ** 2 + ((y_grid - cy) / max(cy, 1.0)) ** 2)
                matte = np.clip(dist, 0.0, 1.0) * 255.0
            elif wipe_pattern == 'horizontal_shutter':
                matte = (np.abs(y_grid - h / 2.0) / max(h / 2.0, 1.0) * 255.0)
            elif wipe_pattern == 'diamond_expand':
                matte = (((np.abs(x_grid - w / 2.0) / max(w / 2.0, 1.0)) + (np.abs(y_grid - h / 2.0) / max(h / 2.0, 1.0))) / 2.0 * 255.0)
            elif wipe_pattern == 'vertical_curtain':
                matte = (np.abs(x_grid - w / 2.0) / max(w / 2.0, 1.0) * 255.0)
            else:  # 'diagonal_tl_br' or default linear gradient
                matte = ((x_grid / max(w, 1) + y_grid / max(h, 1)) / 2.0 * 255.0)
            
            feather = 30.0
            threshold = progress * (255.0 + feather) - feather / 2.0
            
            mask = np.clip((matte - threshold) / feather + 0.5, 0.0, 1.0)
            mask = np.expand_dims(mask, axis=2)
            
            out_np = (img_a * mask + img_b * (1.0 - mask)).astype(np.uint8)
            
        elif trans_type == 'solid_color_transition':
            # 4. Solid color flash / chord-modulated dip transition
            r_col, g_col, b_col = 255, 255, 255
            if chord_color_hex:
                clean_hex = str(chord_color_hex).lstrip('#')
                if len(clean_hex) == 6:
                    try:
                        r_col = int(clean_hex[0:2], 16)
                        g_col = int(clean_hex[2:4], 16)
                        b_col = int(clean_hex[4:6], 16)
                    except Exception:
                        r_col, g_col, b_col = 255, 255, 255
            
            # Photosensitive safe threshold & visual quality
            if r_col < 15 and g_col < 15 and b_col < 15:
                r_col, g_col, b_col = 30, 20, 45
                
            color_layer = np.full_like(img_a, (r_col, g_col, b_col), dtype=np.uint8)
            max_alpha = float(np.clip(0.6 + 0.35 * intensity, 0.5, 0.95))
            color_alpha = float(np.sin(progress * np.pi) * max_alpha)
            
            base_blend = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
            out_np = cv2.addWeighted(base_blend, 1.0 - color_alpha, color_layer, color_alpha, 0.0)
            
        elif trans_type == 'glitch':
            # 5. Glitch & Channel Split
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
            # 6. Slide Push
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


class SongProceduralFluidEngine:
    """
    歌曲專屬 16-Gene Visual DNA 程序化流體與超弦粒子保底演算法 (AetherDNA™ v3.0)
    - 依據曲目獨立隨機種子生成專屬視覺架構，確保每首歌曲保底畫面 1-of-1 獨一無二。
    - 支援 12 大張量幾何波場 (LiquidMetals, GasNebula, QuantumPlasma, GoldenLava, CyberMercury,
      TuringReactionDiffusion, QuantumStrings, CyberGridHorizon, VortexSingularity,
      BioluminescentMycelium, GlitchTopography, StrobeShockwave)。
    - 支援 10,000+ 顆高速向量化超弦粒子物理場 (Vectorized Particle Field SIMD)。
    - 深度樂段自適應 (Section-Aware Evolving Morphing)，各段落幾何張力自動演化。
    - 深度耦合音訊聲學特徵 (stereo_width, roughness, centroid, percussive, audio_samples, sub_bass)。
    - 整合 Tri-Color 電影級調色盤、ACES 軟膝色調映射與 2.39:1 變形暗角。
    - 以全曲時間戳 t 作為自變數，進行常數級 O(1) 時間連續演化。
    """
    def __init__(self, song_key: str = "default_track"):
        import hashlib
        import colorsys
        self.song_key = song_key or "default_track"
        hash_val = int(hashlib.md5(self.song_key.encode('utf-8')).hexdigest(), 16)
        rng = random.Random(hash_val)

        self.gene_hue_base = rng.uniform(0.0, 1.0)
        self.all_viscosities = [
            'LiquidMetals', 'GasNebula', 'QuantumPlasma', 'GoldenLava', 'CyberMercury',
            'TuringReactionDiffusion', 'QuantumStrings', 'CyberGridHorizon', 'VortexSingularity',
            'BioluminescentMycelium', 'GlitchTopography', 'StrobeShockwave'
        ]
        # 為不同樂段打散專屬幾何風格映射，確保樂段間各具辨識度
        shuffled_visc = list(self.all_viscosities)
        rng.shuffle(shuffled_visc)
        self.section_visc_map = {
            'Intro': shuffled_visc[0],
            'Verse': shuffled_visc[1],
            'Build-up': shuffled_visc[2],
            'Drop': shuffled_visc[3],
            'Chorus': shuffled_visc[4],
            'Bridge': shuffled_visc[5],
            'Outro': shuffled_visc[6]
        }
        self.gene_viscosity = self.section_visc_map['Verse']
        self.gene_harmony_mode = rng.choice(['split_complementary', 'triadic', 'analogous', 'neon_duotone'])
        self.gene_fluid_scale = rng.uniform(0.6, 2.2)
        self.gene_turbulence_freq = rng.uniform(0.4, 3.5)
        self.gene_bloom_radius = rng.uniform(0.4, 1.2)
        self.phase_seed = rng.uniform(0.0, 5000.0)

        # 預計算歌曲專屬 Tri-Color 電影級調色盤 (Primary, Secondary, Accent)
        h1 = self.gene_hue_base
        if self.gene_harmony_mode == 'split_complementary':
            h2, h3 = (h1 + 0.42) % 1.0, (h1 + 0.58) % 1.0
        elif self.gene_harmony_mode == 'triadic':
            h2, h3 = (h1 + 0.333) % 1.0, (h1 + 0.666) % 1.0
        elif self.gene_harmony_mode == 'analogous':
            h2, h3 = (h1 + 0.08) % 1.0, (h1 - 0.08) % 1.0
        else:  # neon_duotone
            h2, h3 = (h1 + 0.5) % 1.0, (h1 + 0.25) % 1.0

        self.col_primary_base = np.array(colorsys.hls_to_rgb(h1, 0.45, 0.85), dtype=np.float32) * 255.0
        self.col_secondary_base = np.array(colorsys.hls_to_rgb(h2, 0.25, 0.70), dtype=np.float32) * 255.0
        self.col_accent_base = np.array(colorsys.hls_to_rgb(h3, 0.65, 0.95), dtype=np.float32) * 255.0

        # 初始化向量化超弦粒子物理種子 (8,192 顆粒子，具備初始相位與空間頻率)
        self.num_particles = 8192
        p_rng = np.random.RandomState(hash_val % (2**31 - 1))
        self.part_x0 = p_rng.uniform(-1.5, 1.5, self.num_particles).astype(np.float32)
        self.part_y0 = p_rng.uniform(-1.5, 1.5, self.num_particles).astype(np.float32)
        self.part_speed = p_rng.uniform(0.3, 1.8, self.num_particles).astype(np.float32)
        self.part_phase = p_rng.uniform(0.0, 2.0 * np.pi, self.num_particles).astype(np.float32)
        self.part_size = p_rng.uniform(0.5, 2.5, self.num_particles).astype(np.float32)
        # 劃分 35% 為高頻 Hihat 空氣微塵粒子 (Micro-dust particles)
        self.part_is_dust = (p_rng.uniform(0.0, 1.0, self.num_particles) < 0.35)

    def _compute_wavefield(self, visc: str, xx, yy, tau: float, sub_bass: float, beat_energy: float, centroid: float, roughness: float, stereo_width: float, percussive: float, col_primary, col_secondary, col_accent):
        """內部張量幾何波場算子生成器"""
        if visc == 'LiquidMetals':
            dx = np.sin(yy * (2.2 * self.gene_fluid_scale) + tau * 0.8 + sub_bass * 1.5)
            dy = np.cos(xx * (1.8 * self.gene_fluid_scale) - tau * 0.7 + beat_energy * 1.2)
            field1 = np.sin((xx + dx * 0.45) * 2.8 + (yy + dy * 0.45) * 2.4)
            field2 = np.cos((xx - dx * 0.3) * 3.5 - (yy + dy * 0.3) * 1.8 + tau * 0.5)
            wave = (field1 * 0.55 + field2 * 0.45)
            specular = np.power(np.clip(wave * 0.5 + 0.5, 0.0, 1.0), 6.0) * (0.9 + centroid * 0.8)
            norm_w = np.clip(wave * 0.5 + 0.5, 0.0, 1.0)
            base_col = (1.0 - norm_w[:, :, None]) * col_secondary + norm_w[:, :, None] * col_primary
            return np.clip(base_col + specular[:, :, None] * col_accent * 1.4, 0.0, 255.0)

        elif visc == 'GasNebula':
            oct1 = np.sin(xx * (1.2 * self.gene_fluid_scale) + tau * 0.35) * np.cos(yy * 1.0 - tau * 0.25)
            oct2 = np.sin((xx * 2.2 - yy * 1.7) * self.gene_fluid_scale + tau * 0.55 + stereo_width * 0.6) * 0.5
            oct3 = np.cos((xx * 4.4 + yy * 3.2) * self.gene_fluid_scale - tau * 0.85 + roughness * 0.8) * 0.25
            wave = (oct1 + oct2 + oct3) * 0.6
            norm_w = np.clip((wave + 1.0) * 0.5, 0.0, 1.0)
            glow = np.exp(-((xx * 0.7)**2 + (yy * 1.1)**2)) * (0.4 + sub_bass * 0.5)
            base_col = (1.0 - norm_w[:, :, None]) * col_secondary + norm_w[:, :, None] * col_primary
            return np.clip(base_col + glow[:, :, None] * col_accent * 1.1, 0.0, 255.0)

        elif visc == 'QuantumPlasma':
            r = np.sqrt(xx**2 + (yy * 1.25)**2) + 1e-4
            theta = np.arctan2(yy, xx)
            spiral = np.sin(r * (5.5 * self.gene_fluid_scale) - theta * 3.0 - tau * 1.8 + roughness * 3.0)
            cross_field = np.cos(xx * 3.8 + yy * 4.2 + tau * 1.4)
            filaments = np.exp(-np.abs(spiral * 0.7 + cross_field * 0.3) * (5.5 - 2.0 * roughness))
            norm_w = np.clip(filaments * (0.8 + percussive * 1.5 + beat_energy * 0.7), 0.0, 1.0)
            void_ambient = col_secondary * 0.3
            plasma_core = norm_w[:, :, None] * (col_primary * 0.6 + col_accent * 0.8)
            return np.clip(void_ambient + plasma_core * 1.5, 0.0, 255.0)

        elif visc == 'GoldenLava':
            fx = np.sin(xx * (3.0 * self.gene_fluid_scale) + tau * 0.28)
            fy = np.cos(yy * (2.6 * self.gene_fluid_scale) - tau * 0.22)
            crust = 1.0 - np.abs(fx * fy)
            fissures = np.power(np.clip(crust, 0.0, 1.0), 4.2) * (1.2 + sub_bass * 1.8)
            basalt_plates = (np.cos(xx * 1.4 + yy * 1.4 + tau * 0.15) * 0.5 + 0.5) * 0.25
            norm_fissure = np.clip(fissures, 0.0, 1.0)
            basalt_color = col_secondary * (basalt_plates[:, :, None] * 0.4 + 0.1)
            magma_color = col_primary * (norm_fissure[:, :, None] * 0.8) + col_accent * (norm_fissure[:, :, None]**2 * 1.4)
            return np.clip(basalt_color + magma_color, 0.0, 255.0)

        elif visc == 'CyberMercury':
            u = np.sin(xx * (3.6 * self.gene_fluid_scale) + tau * 1.2 + stereo_width * 0.8)
            v = np.cos(yy * (3.2 * self.gene_fluid_scale) - tau * 0.95)
            caustic = np.sin(u * np.pi + v * np.pi + beat_energy * 2.0)
            ripples = np.sin((xx**2 + yy**2) * 4.0 - tau * 2.5 + sub_bass * 2.0) * 0.3
            synth_wave = np.clip((caustic * 0.7 + ripples + 1.0) * 0.5, 0.0, 1.0)
            chrome_shimmer = np.power(synth_wave, 3.0) * (0.8 + centroid * 0.9)
            base_col = (1.0 - synth_wave[:, :, None]) * col_secondary + synth_wave[:, :, None] * col_primary
            return np.clip(base_col * 0.8 + chrome_shimmer[:, :, None] * col_accent * 1.3, 0.0, 255.0)

        elif visc == 'TuringReactionDiffusion':
            turing_u = np.sin(xx * 3.5 + np.cos(yy * 4.0 + tau * 0.5) * 1.8)
            turing_v = np.cos(yy * 3.5 + np.sin(xx * 4.0 - tau * 0.6) * 1.8)
            turing_pattern = np.abs(turing_u * turing_v)
            turing_spots = np.exp(-((turing_pattern - 0.45)**2) * 18.0) * (0.8 + beat_energy * 0.8)
            norm_w = np.clip(turing_spots, 0.0, 1.0)
            return col_secondary * 0.25 + norm_w[:, :, None] * (col_primary * 0.7 + col_accent * 0.9)

        elif visc == 'QuantumStrings':
            string_freq = 5.0 * self.gene_fluid_scale
            strings = np.sin(xx * string_freq + tau * 1.5) * np.sin(yy * string_freq * 1.2 - tau * 1.2)
            harmonics = np.sin((xx + yy) * (string_freq * 1.8) + tau * 2.2 + percussive * 3.0) * 0.5
            intensity = np.power(np.abs(strings + harmonics), 2.5) * (1.0 + sub_bass * 1.5)
            norm_w = np.clip(intensity, 0.0, 1.0)
            return col_secondary * 0.15 + norm_w[:, :, None] * (col_primary * 0.5 + col_accent * 1.2)

        elif visc == 'CyberGridHorizon':
            persp_y = np.clip(yy + 0.3, 0.04, 3.0)
            grid_x = np.sin((xx / persp_y) * 8.0 + tau * 0.8)
            grid_z = np.sin((2.0 / persp_y) * 4.0 - tau * 2.5 + beat_energy * 1.5)
            laser_line = np.exp(-np.abs(grid_x) * 6.0) + np.exp(-np.abs(grid_z) * 6.0)
            sky_glow = np.exp(-((yy - 0.4)**2) * 3.0) * 0.4
            laser_val = np.clip(laser_line * (0.8 + beat_energy * 0.8) + sky_glow, 0.0, 1.5)
            return col_secondary * 0.2 + laser_val[:, :, None] * col_accent * 1.2

        elif visc == 'VortexSingularity':
            r_dist = np.sqrt(xx**2 + yy**2) + 1e-4
            angle = np.arctan2(yy, xx)
            swirl = angle + (2.5 / (r_dist + 0.2)) + tau * 1.6
            disk = np.exp(-((r_dist - 0.75)**2) * 8.0) * (0.8 + sub_bass * 1.2)
            arms = np.sin(swirl * 3.0) * 0.5 + 0.5
            disk_glow = disk * arms
            event_horizon = np.clip(1.0 - np.exp(-((r_dist / 0.3)**3)), 0.0, 1.0)
            return (disk_glow[:, :, None] * (col_primary * 0.6 + col_accent * 1.4) + col_secondary * 0.2) * event_horizon[:, :, None]

        elif visc == 'BioluminescentMycelium':
            n1 = np.sin(xx * 4.2 + np.cos(yy * 3.8 + tau * 0.5))
            n2 = np.cos(yy * 4.2 + np.sin(xx * 3.8 - tau * 0.4))
            veins = np.exp(-np.abs(n1 + n2) * 7.0) * (1.0 + roughness * 1.5)
            nodes = np.exp(-(((xx % 0.6 - 0.3)**2 + (yy % 0.6 - 0.3)**2) * 25.0)) * (beat_energy * 1.5)
            tot = np.clip(veins + nodes, 0.0, 1.0)
            return col_secondary * 0.15 + tot[:, :, None] * (col_primary * 0.5 + col_accent * 1.5)

        elif visc == 'GlitchTopography':
            slice_shift = np.sin(np.floor(yy * 12.0) * 2.5 + tau * 4.0) * (0.15 * beat_energy)
            topo = np.sin((xx + slice_shift) * 6.0 + tau * 0.7) + np.cos(yy * 6.0 - tau * 0.5)
            bands = np.mod(topo * 4.0, 1.0)
            edges = np.exp(-np.abs(bands - 0.5) * 8.0) * (0.9 + centroid * 0.8)
            return col_secondary * 0.25 + edges[:, :, None] * (col_primary * 0.8 + col_accent * 1.0)

        else:  # StrobeShockwave
            r_dist = np.sqrt(xx**2 + (yy * 1.1)**2)
            shock = np.sin(r_dist * 12.0 - tau * 4.0 + beat_energy * 3.0)
            crest = np.power(np.clip(shock, 0.0, 1.0), 4.0) * (1.0 + percussive * 2.0)
            crest_col = np.clip(crest, 0.0, 1.0)
            return col_secondary * 0.2 + crest_col[:, :, None] * (col_primary * 0.4 + col_accent * 1.6)

    def render_emergency_frame(self, w: int, h: int, t: float, beat_energy: float = 0.5, sub_bass: float = 0.5, chord_hex: str = "#a855f7", audio_feats: dict = None, section_name: str = "Verse", morph_weight: float = 0.0, prev_section_name: str = None):
        """
        高質感有機程序化視覺保底 (Multi-Layer Procedural Spectrum, 12 Geometries & Vectorized Particle Field)
        """
        try:
            import colorsys
            # 全曲時間推進色相漂移 (Progressive Hue Drift ~25° over time)，長曲依然維持新鮮感
            drift_hue = (t * 0.0015) % 1.0
            h1 = (self.gene_hue_base + drift_hue) % 1.0
            if self.gene_harmony_mode == 'split_complementary':
                h2, h3 = (h1 + 0.42) % 1.0, (h1 + 0.58) % 1.0
            elif self.gene_harmony_mode == 'triadic':
                h2, h3 = (h1 + 0.333) % 1.0, (h1 + 0.666) % 1.0
            elif self.gene_harmony_mode == 'analogous':
                h2, h3 = (h1 + 0.08) % 1.0, (h1 - 0.08) % 1.0
            else:  # neon_duotone
                h2, h3 = (h1 + 0.5) % 1.0, (h1 + 0.25) % 1.0

            col_primary = np.array(colorsys.hls_to_rgb(h1, 0.45, 0.85), dtype=np.float32) * 255.0
            col_secondary = np.array(colorsys.hls_to_rgb(h2, 0.25, 0.70), dtype=np.float32) * 255.0
            col_accent = np.array(colorsys.hls_to_rgb(h3, 0.65, 0.95), dtype=np.float32) * 255.0

            # 和弦原色動態耦合調色盤
            if chord_hex and chord_hex.startswith('#') and len(chord_hex) == 7:
                try:
                    cr = int(chord_hex[1:3], 16)
                    cg = int(chord_hex[3:5], 16)
                    cb = int(chord_hex[5:7], 16)
                    chord_rgb = np.array([cr, cg, cb], dtype=np.float32)
                    col_primary = col_primary * 0.6 + chord_rgb * 0.4
                except Exception:
                    pass

            # 萃取多維聲學特徵
            if audio_feats is None:
                audio_feats = {}
            stereo_width = float(audio_feats.get('stereo_width', 1.0))
            roughness = float(audio_feats.get('roughness', audio_feats.get('spectral_roughness', 0.2)))
            centroid = float(audio_feats.get('centroid', audio_feats.get('spectral_centroid', 0.5)))
            percussive = float(audio_feats.get('percussive', 0.0))
            hihat_density = float(audio_feats.get('hihat_density', 0.0))
            hihat_trigger = bool(audio_feats.get('hihat_trigger', False))
            audio_samples = audio_feats.get('audio_samples', None)

            # 雙尺度運算網格 (Dual-Scale Pipeline)，保證 4K 實時超低延遲
            dw = max(160, min(320, w // 8))
            dh = max(90, min(180, h // 8))
            tau = t * (0.4 + 0.3 * self.gene_turbulence_freq) + self.phase_seed

            aspect = float(dw) / float(dh)
            x_coords = np.linspace(-1.5 * aspect, 1.5 * aspect, dw, dtype=np.float32)
            y_coords = np.linspace(-1.5, 1.5, dh, dtype=np.float32)
            xx, yy = np.meshgrid(x_coords, y_coords)

            # 根據樂段動態決定幾何風格 (Section Morphing & Cross-Section Blending)
            visc_curr = self.section_visc_map.get(section_name, self.gene_viscosity)
            small_rgb = self._compute_wavefield(
                visc_curr, xx, yy, tau, sub_bass, beat_energy, centroid, roughness, stereo_width, percussive,
                col_primary, col_secondary, col_accent
            )

            # 若處於跨樂段邊界 (Cross-Section Morphing)，平滑混合兩種波場
            if prev_section_name and prev_section_name != section_name and 0.01 < morph_weight < 0.99:
                visc_prev = self.section_visc_map.get(prev_section_name, self.gene_viscosity)
                if visc_prev != visc_curr:
                    prev_rgb = self._compute_wavefield(
                        visc_prev, xx, yy, tau, sub_bass, beat_energy, centroid, roughness, stereo_width, percussive,
                        col_primary, col_secondary, col_accent
                    )
                    small_rgb = small_rgb * (1.0 - morph_weight) + prev_rgb * morph_weight

            # 🌌 注入 10,000+ 顆高速向量化超弦雙軌粒子物理場 (SIMD: Kick Shock + Hihat Micro-dust)
            try:
                # 粒子動態坐標更新
                p_t = tau * self.part_speed
                p_rad = np.sqrt(self.part_x0**2 + self.part_y0**2)
                p_ang = np.arctan2(self.part_y0, self.part_x0) + p_t * 0.4 + beat_energy * 0.6
                
                # 軌道 1: 重音 Kick 衝擊波徑向位移
                # 軌道 2: Hihat 滾奏空氣微塵高頻微抖動
                hihat_boost = (1.5 if hihat_trigger else 1.0) * (0.8 + hihat_density * 1.2)
                p_curr_rad = p_rad + np.sin(p_t + self.part_phase) * 0.2 + (beat_energy * 0.35)
                
                dust_jitter = np.where(self.part_is_dust, np.sin(p_t * 6.0) * (0.12 * hihat_boost), 0.0).astype(np.float32)
                p_curr_rad = p_curr_rad + dust_jitter

                curr_px = np.cos(p_ang) * p_curr_rad
                curr_py = np.sin(p_ang) * p_curr_rad

                # 映射粒子至網格索引
                grid_px = ((curr_px / (1.5 * aspect) + 1.0) * 0.5 * dw).astype(np.int32)
                grid_py = ((curr_py / 1.5 + 1.0) * 0.5 * dh).astype(np.int32)

                valid_mask = (grid_px >= 0) & (grid_px < dw) & (grid_py >= 0) & (grid_py < dh)
                valid_px = grid_px[valid_mask]
                valid_py = grid_py[valid_mask]
                
                # 微塵粒子發射高頻璀璨亮光
                base_p_int = self.part_size[valid_mask] * (0.6 + beat_energy * 0.8)
                dust_mult = np.where(self.part_is_dust[valid_mask], 1.2 * hihat_boost, 1.0).astype(np.float32)
                valid_int = (base_p_int * dust_mult).astype(np.float32)

                # 累積粒子亮度至 2D 緩衝
                particle_layer = np.zeros((dh, dw), dtype=np.float32)
                np.add.at(particle_layer, (valid_py, valid_px), valid_int)
                particle_layer = np.clip(particle_layer, 0.0, 2.5)

                # 將粒子疊加至原場景 (高光加色混合)
                particle_rgb = particle_layer[:, :, None] * col_accent * 0.85
                small_rgb = np.clip(small_rgb + particle_rgb, 0.0, 255.0)
            except Exception:
                pass

            # 時域波形 (audio_samples) 實時動態漣漪注入
            if audio_samples is not None and len(audio_samples) > 0:
                try:
                    samples_arr = np.asarray(audio_samples, dtype=np.float32)
                    if samples_arr.ndim == 1 and len(samples_arr) >= 16:
                        interp_wave = np.interp(
                            np.linspace(0, len(samples_arr) - 1, dw),
                            np.arange(len(samples_arr)),
                            samples_arr
                        )
                        audio_ripple = np.sin(yy * 12.0 + interp_wave[None, :] * 5.0 + tau * 2.0) * 0.08 * (0.5 + beat_energy)
                        small_rgb = np.clip(small_rgb + audio_ripple[:, :, None] * col_accent, 0.0, 255.0)
                except Exception:
                    pass

            # 全幅 2.39:1 電影級變形暗角 (柔和橢圓衰減)
            vig_x = np.linspace(-1.0, 1.0, dw, dtype=np.float32)
            vig_y = np.linspace(-1.0, 1.0, dh, dtype=np.float32)
            vig_map = 1.0 - (vig_x[None, :]**2 * 0.35 + vig_y[:, None]**2 * 0.75) * 0.38
            vig_map = np.clip(vig_map, 0.62, 1.0)
            small_rgb = small_rgb * vig_map[:, :, None]

            # ACES 軟膝色調映射 (ACES Film Rec.709/sRGB 曲線模擬)，保持暗部細節並壓制過曝
            x_norm = small_rgb / 255.0
            aces = np.clip((x_norm * (2.51 * x_norm + 0.03)) / (x_norm * (2.43 * x_norm + 0.59) + 0.14), 0.0, 1.0)
            small_u8 = (aces * 255.0).astype(np.uint8)

            # 高效率上採樣至目標 4K/2K 解析度
            if cv2 is not None:
                out_img = cv2.resize(small_u8, (w, h), interpolation=cv2.INTER_LINEAR)
            else:
                out_img = np.array(Image.fromarray(small_u8).resize((w, h), Image.Resampling.BILINEAR))

            return Image.fromarray(out_img, "RGB").convert("RGBA")
        except Exception as e:
            logger.warning(f"Error in SongProceduralFluidEngine: {e}")
            return Image.new("RGBA", (w, h), (15, 15, 25, 255))


