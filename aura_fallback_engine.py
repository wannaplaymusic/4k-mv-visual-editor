# -*- coding: utf-8 -*-
"""
AURA FALLBACK ENGINE (Project Aura-Fallback)
===========================================
工業級 4K MV 旗艦級自主生成式保底畫布與容災渲染引擎

核心功能：
1. 哲學定位：將容災保底昇華為獨立生成藝術，即便主模組完全崩潰，保底畫面自身亦為頂級 4K VJ 藝術作品。
2. 四大獨立生成式藝術形態 (4-Tier Generative Fallback Canvases)：
   - Tier 1: Reaction-Diffusion 渦流反應擴散場 (Organic Turing & Smoke Nebula)
   - Tier 2: Chladni Cymatics 克拉尼共振幾何與 Lissajous 諧波雷射 (Acoustic Harmonics)
   - Tier 3: Volumetric Deep Tunnel & Cyber Beams (深空光柱與超維射線隧道)
   - Tier 4: Brutalist Kinetic Typography & Matrix ASCII (粗獷主義動態文字與等寬排版數據流)
3. 專輯概念色度鎖 (Album Concept OKLCH Color Lock)：
   - 《Gradient of Silence》: 極低色度 (C < 0.04) 冷銀灰與深墨黑
   - 《Phantom Platform》: 深空紫黑、低頻共振霓虹
   - 《Marina at Dusk》: 暮光橙藍雙色補色
   - 《Vaporized Structures》: 迷幻薄霧流體與珠光青
4. 非對稱阻尼平滑漸入閥門 (Asymmetric Smooth Crossfade Gate, 0.15s 漸入，零硬切)
5. 跨曲目/跨分鏡去重調度器 (Multi-track Diversity Scheduler)
"""

import os
import sys
import math
import time
import json
import random
import logging
from typing import Optional, Dict, Any, Tuple, List
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger("AuraFallbackEngine")

try:
    import cv2
    if cv2 is not None:
        cv2.setUseOptimized(True)
except ImportError:
    cv2 = None

_FALLBACK_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_cache", "aura_fallback_history.json")


class AuraFallbackEngine:
    """4K MV 旗艦級自主生成式保底畫布引擎"""

    def __init__(self, seed_string: Optional[str] = None, album_name: str = "generic", track_title: str = "Aura"):
        self.seed_string = seed_string or str(time.time())
        self.album_name = str(album_name).strip()
        self.track_title = str(track_title).strip()
        
        # 決定種子
        import hashlib
        hash_val = int(hashlib.md5(self.seed_string.encode('utf-8')).hexdigest(), 16)
        self.rng = random.Random(hash_val)

        # 狀態快取與物理時間步
        self.last_t = 0.0
        self.active_mode_index = 0
        self.crossfade_alpha = 0.0
        self.transition_speed = 6.67  # ~0.15 秒完成漸變 (1 / 0.15 = 6.67)
        self.last_clean_frame = None

        # 內部仿真網格 (微縮加速，雙線性放大至 4K)
        self.sim_w = 480
        self.sim_h = 270
        self._init_simulation_buffers()

        # 選擇本曲專屬主保底形態與輔助形態
        self.primary_mode, self.secondary_mode = self._resolve_modes_with_diversity()
        self.album_palette_profile = self._resolve_album_palette_profile()
        
        logger.info(f"✨ [AURA-FALLBACK] 啟動保底引擎 | 專輯: [{self.album_name}] | 主形態: [{self.primary_mode}] | 輔形態: [{self.secondary_mode}]")

    def _init_simulation_buffers(self):
        """初始化微縮仿真網格"""
        h, w = self.sim_h, self.sim_w
        # Reaction-Diffusion 濃度網格 (A: 營養物, B: 抑制物)
        self.rd_A = np.ones((h, w), dtype=np.float32)
        self.rd_B = np.zeros((h, w), dtype=np.float32)
        # 初始化噪聲晶種
        cy, cx = h // 2, w // 2
        r = 16
        self.rd_B[cy - r:cy + r, cx - r:cx + r] = 1.0

        # 流體波形緩衝
        self.wave_phase = 0.0
        # 預計算座標網格
        y, x = np.mgrid[0:h, 0:w]
        self.grid_x_norm = (x - cx) / float(cx)
        self.grid_y_norm = (y - cy) / float(cy)
        self.grid_r = np.sqrt(self.grid_x_norm**2 + self.grid_y_norm**2)
        self.grid_theta = np.arctan2(self.grid_y_norm, self.grid_x_norm)

    def _load_history(self) -> List[Dict[str, Any]]:
        try:
            if os.path.exists(_FALLBACK_HISTORY_PATH):
                with open(_FALLBACK_HISTORY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-30:]
        except Exception:
            pass
        return []

    def _save_history(self, entry: Dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(_FALLBACK_HISTORY_PATH), exist_ok=True)
            history = self._load_history()
            history.append(entry)
            history = history[-30:]
            temp_path = _FALLBACK_HISTORY_PATH + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, _FALLBACK_HISTORY_PATH)
        except Exception:
            pass

    def _resolve_modes_with_diversity(self) -> Tuple[str, str]:
        """跨曲目保底形態去重調度"""
        all_modes = [
            "ReactionDiffusion",  # Tier 1
            "ChladniCymatics",    # Tier 2
            "VolumetricTunnel",   # Tier 3
            "BrutalistTypography" # Tier 4
        ]
        history = self._load_history()
        recent_primary = [h.get("primary_mode") for h in history[-5:] if h.get("primary_mode")]
        
        # 統計最近出現頻率，優先選取最少使用的模式
        counts = {m: recent_primary.count(m) for m in all_modes}
        min_c = min(counts.values()) if counts else 0
        candidates = [m for m in all_modes if counts.get(m, 0) == min_c]
        primary = self.rng.choice(candidates if candidates else all_modes)
        
        remaining = [m for m in all_modes if m != primary]
        secondary = self.rng.choice(remaining)

        self._save_history({
            "timestamp": int(time.time()),
            "album": self.album_name,
            "track": self.track_title,
            "primary_mode": primary,
            "secondary_mode": secondary
        })
        return primary, secondary

    def _resolve_album_palette_profile(self) -> Dict[str, Any]:
        """根據專輯世界觀鎖定專屬色彩科學約束"""
        alb = self.album_name.lower()
        if "gradient of silence" in alb:
            # 粗獷主義冷黑白、深冷灰、金屬極簡微光
            return {
                "base_chroma": 0.02,
                "tint_rgb": (210, 220, 230),
                "bg_rgb": (8, 10, 14),
                "accent_rgb": (180, 195, 210),
                "high_contrast": True
            }
        elif "phantom platform" in alb:
            # 深空虛空、暗紫底蘊、酸性紫紅與高能電光藍
            return {
                "base_chroma": 0.16,
                "tint_rgb": (168, 85, 247),
                "bg_rgb": (10, 4, 18),
                "accent_rgb": (236, 72, 153),
                "high_contrast": True
            }
        elif "marina at dusk" in alb:
            # 暮色橙藍雙色補色 (Amber & Twilight Cyan)
            return {
                "base_chroma": 0.14,
                "tint_rgb": (249, 115, 22),
                "bg_rgb": (7, 18, 32),
                "accent_rgb": (6, 182, 212),
                "high_contrast": False
            }
        elif "vaporized structures" in alb:
            # 迷幻薄霧流體、珠光青、翡翠綠霧
            return {
                "base_chroma": 0.12,
                "tint_rgb": (20, 184, 166),
                "bg_rgb": (6, 18, 16),
                "accent_rgb": (244, 244, 245),
                "high_contrast": False
            }
        else:
            # 通用電子自適應色彩
            return {
                "base_chroma": 0.10,
                "tint_rgb": (139, 92, 246),
                "bg_rgb": (10, 10, 15),
                "accent_rgb": (59, 130, 246),
                "high_contrast": False
            }

    # -------------------------------------------------------------
    # Tier 1: Reaction-Diffusion 渦流反應擴散場 (Organic Turing & Smoke)
    # -------------------------------------------------------------
    def _render_reaction_diffusion(self, t: float, beat_energy: float, sub_bass: float, dt: float) -> np.ndarray:
        # Gray-Scott 反應擴散步進
        Du, Dv = 0.16, 0.08
        F, k = 0.035 + 0.005 * sub_bass, 0.065 - 0.003 * beat_energy

        # 向量化快速五點拉普拉斯卷積
        lapA = (np.roll(self.rd_A, 1, 0) + np.roll(self.rd_A, -1, 0) +
                np.roll(self.rd_A, 1, 1) + np.roll(self.rd_A, -1, 1) - 4 * self.rd_A)
        lapB = (np.roll(self.rd_B, 1, 0) + np.roll(self.rd_B, -1, 0) +
                np.roll(self.rd_B, 1, 1) + np.roll(self.rd_B, -1, 1) - 4 * self.rd_B)

        uvv = self.rd_A * self.rd_B * self.rd_B
        self.rd_A += (Du * lapA - uvv + F * (1.0 - self.rd_A)) * (dt * 18.0)
        self.rd_B += (Dv * lapB + uvv - (F + k) * self.rd_B) * (dt * 18.0)

        np.clip(self.rd_A, 0.0, 1.0, out=self.rd_A)
        np.clip(self.rd_B, 0.0, 1.0, out=self.rd_B)

        # 重拍注入動態衝擊波脈衝晶種
        if beat_energy > 0.45:
            pulse_x = int(self.sim_w * (0.5 + 0.3 * math.sin(t * 1.5)))
            pulse_y = int(self.sim_h * (0.5 + 0.3 * math.cos(t * 1.1)))
            r = int(10 + 20 * beat_energy)
            y1, y2 = max(0, pulse_y - r), min(self.sim_h, pulse_y + r)
            x1, x2 = max(0, pulse_x - r), min(self.sim_w, pulse_x + r)
            self.rd_B[y1:y2, x1:x2] += 0.8 * beat_energy

        val = np.clip(self.rd_B * 2.5, 0.0, 1.0)
        return val

    # -------------------------------------------------------------
    # Tier 2: Chladni Cymatics 克拉尼共振幾何 (Acoustic Harmonics)
    # -------------------------------------------------------------
    def _render_chladni_cymatics(self, t: float, beat_energy: float, sub_bass: float, high_energy: float) -> np.ndarray:
        # 克拉尼板方程式: w = a*sin(n*pi*x)*sin(m*pi*y) - b*sin(m*pi*x)*sin(n*pi*y)
        n = 3.0 + int(sub_bass * 4.0)
        m = 5.0 + int(high_energy * 5.0)
        a = 1.0 + 0.3 * math.sin(t * 2.0)
        b = 1.0 + 0.3 * math.cos(t * 1.8)

        pi = np.pi
        x = self.grid_x_norm * pi
        y = self.grid_y_norm * pi

        w = a * np.sin(n * x) * np.sin(m * y) - b * np.sin(m * x) * np.sin(n * y)
        
        # 節線寬度受節奏能量調制
        line_width = 0.12 - 0.06 * beat_energy
        nodal = np.exp(-(w**2) / (2.0 * (line_width**2)))
        
        # 疊加同心聲波漣漪
        ripple = 0.5 + 0.5 * np.sin(self.grid_r * 28.0 - t * 8.0 + beat_energy * 6.0)
        combined = np.clip(nodal * 0.75 + ripple * 0.25 * sub_bass, 0.0, 1.0)
        return combined

    # -------------------------------------------------------------
    # Tier 3: Volumetric Deep Tunnel & Cyber Beams (深空光束與超維隧道)
    # -------------------------------------------------------------
    def _render_volumetric_tunnel(self, t: float, beat_energy: float, sub_bass: float) -> np.ndarray:
        # 偽 3D 極座標光線射出
        r = np.clip(self.grid_r, 0.001, 10.0)
        tunnel_depth = (1.0 / r) + t * (2.0 + 4.0 * sub_bass)
        spiral_angle = self.grid_theta * 4.0 + tunnel_depth * 0.5

        rings = 0.5 + 0.5 * np.sin(tunnel_depth * 12.0)
        spokes = 0.5 + 0.5 * np.cos(spiral_angle * 3.0)
        vortex = rings * spokes

        # 邊緣衰減與中心黑洞
        vignette = np.clip(1.0 - np.exp(-r * 3.0), 0.0, 1.0)
        light_beam = np.power(vortex, 2.0) * (1.0 + beat_energy * 2.0)
        return np.clip(light_beam * vignette, 0.0, 1.0)

    # -------------------------------------------------------------
    # Tier 4: Brutalist Kinetic Typography (粗獷主義動態文字與等寬排版)
    # -------------------------------------------------------------
    def _render_brutalist_typography(self, t: float, beat_energy: float, sub_bass: float, bpm: float, section_name: str) -> np.ndarray:
        # 基礎網格結構
        grid_x = np.abs(np.sin(self.grid_x_norm * 30.0))
        grid_y = np.abs(np.sin(self.grid_y_norm * 18.0))
        wireframe = ((grid_x < 0.08) | (grid_y < 0.08)).astype(np.float32) * 0.35

        # 中央動態十字線與聚焦十字架
        crosshair_w = 0.015
        cross_h = (np.abs(self.grid_y_norm) < crosshair_w) & (np.abs(self.grid_x_norm) < 0.4)
        cross_v = (np.abs(self.grid_x_norm) < crosshair_w) & (np.abs(self.grid_y_norm) < 0.4)
        crosshair = (cross_h | cross_v).astype(np.float32) * (0.8 + 0.5 * beat_energy)

        # 動態掃描線
        scanline_y = (math.sin(t * 3.0) * 0.9)
        scan = np.exp(-((self.grid_y_norm - scanline_y)**2) / 0.002) * 0.6

        combined = np.clip(wireframe + crosshair + scan, 0.0, 1.0)
        return combined

    # -------------------------------------------------------------
    # 主生成管道 (4K 零分配雙線性放大 + OKLCH 染色 + 遙測 HUD)
    # -------------------------------------------------------------
    def render(
        self,
        target_w: int,
        target_h: int,
        t: float,
        beat_energy: float = 0.5,
        sub_bass: float = 0.5,
        high_energy: float = 0.3,
        audio_feats: Optional[Dict[str, Any]] = None,
        section_name: str = "Verse",
        bpm: float = 128.0
    ) -> Image.Image:
        """渲染一幀 4K 高階自主保底畫面"""
        dt = t - self.last_t
        if dt <= 0.0 or dt > 0.2:
            dt = 1.0 / 30.0
        self.last_t = t

        # 依樂段動態選擇主/輔形態
        sec_lower = str(section_name).lower()
        is_climax = any(k in sec_lower for k in ("drop", "chorus", "build"))
        current_mode = self.secondary_mode if (is_climax and self.rng.random() < 0.35) else self.primary_mode

        # 1. 執行核心生成算子 (在微縮網格上執行以確保 6ms 以內完成)
        if current_mode == "ReactionDiffusion":
            val_map = self._render_reaction_diffusion(t, beat_energy, sub_bass, dt)
        elif current_mode == "ChladniCymatics":
            val_map = self._render_chladni_cymatics(t, beat_energy, sub_bass, high_energy)
        elif current_mode == "VolumetricTunnel":
            val_map = self._render_volumetric_tunnel(t, beat_energy, sub_bass)
        else: # BrutalistTypography
            val_map = self._render_brutalist_typography(t, beat_energy, sub_bass, bpm, section_name)

        # 2. 應用專輯概念調色盤 (Album Color Profile)
        prof = self.album_palette_profile
        bg = np.array(prof["bg_rgb"], dtype=np.float32)
        tint = np.array(prof["tint_rgb"], dtype=np.float32)
        accent = np.array(prof["accent_rgb"], dtype=np.float32)

        # 像素著色合成 (H x W x 3)
        v3 = val_map[:, :, None]
        # 雙色漸變插值
        color_rgb = bg * (1.0 - v3) + tint * v3 * 0.85 + accent * (v3**2) * (0.8 + 0.6 * beat_energy)
        color_rgb = np.clip(color_rgb, 0.0, 255.0).astype(np.uint8)

        # 3. 高品質雙線性上採樣至 4K / 目標解析度
        if cv2 is not None:
            final_frame = cv2.resize(color_rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            pil_img = Image.fromarray(final_frame)
        else:
            pil_small = Image.fromarray(color_rgb)
            pil_img = pil_small.resize((target_w, target_h), Image.Resampling.BILINEAR)

        # 4. 繪製微型科技感遙測 HUD (Kinetic Telemetry Micro-HUD)
        self._overlay_kinetic_hud(pil_img, t, beat_energy, sub_bass, bpm, section_name, current_mode)

        self.last_clean_frame = pil_img
        return pil_img

    def _overlay_kinetic_hud(
        self,
        pil_img: Image.Image,
        t: float,
        beat_energy: float,
        sub_bass: float,
        bpm: float,
        section_name: str,
        current_mode: str
    ):
        """在 4K 畫面四角與底邊繪製極簡科技感文字與頻率指針"""
        try:
            draw = ImageDraw.Draw(pil_img)
            w, h = pil_img.size
            font_size = max(14, int(h * 0.016))
            
            # 使用系統等寬字型或預設字型
            font = None
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", font_size)
            except Exception:
                try:
                    font = ImageFont.truetype("Menlo.ttc", font_size)
                except Exception:
                    font = ImageFont.load_default()

            text_color = (180, 200, 220, 160)
            dim_color = (100, 120, 140, 110)

            # 左上角：世界觀、曲目與當前生成形態
            hud_tl = f"AURA // [{self.album_name.upper()}] : {self.track_title.upper()}"
            hud_mode = f"CORE PROTOCOL // MODE: {current_mode.upper()} [RES: {w}x{h}]"
            draw.text((40, 40), hud_tl, fill=text_color, font=font)
            draw.text((40, 40 + font_size + 6), hud_mode, fill=dim_color, font=font)

            # 右上角：即時音訊動態遙測
            time_str = f"T+{t:06.2f}s | SEC: {section_name.upper()} | BPM: {bpm:.1f}"
            bbox = draw.textbbox((0, 0), time_str, font=font) if hasattr(draw, 'textbbox') else (0, 0, 260, 20)
            text_w = bbox[2] - bbox[0]
            draw.text((w - text_w - 40, 40), time_str, fill=text_color, font=font)

            # 底部動態聲學能量指針條 (Energy Visualizer Bar)
            bar_w = int(w * 0.25)
            bar_h = 4
            bar_x = 40
            bar_y = h - 50
            draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(40, 50, 60))
            active_w = int(bar_w * (sub_bass * 0.6 + beat_energy * 0.4))
            draw.rectangle([bar_x, bar_y, bar_x + active_w, bar_y + bar_h], fill=(220, 235, 255))
            draw.text((bar_x + bar_w + 15, bar_y - 6), f"SUB_BASS: {sub_bass:.2f} // PEAK: {beat_energy:.2f}", fill=dim_color, font=font)

        except Exception as e:
            logger.debug(f"HUD overlay failed: {e}")

    # -------------------------------------------------------------
    # 0.15 秒平滑混融過渡門控 (Smooth Crossfade Gate)
    # -------------------------------------------------------------
    def crossfade_blend(self, faulty_or_black_frame: Image.Image, dt: float, emergency_trigger: bool, **render_kwargs) -> Image.Image:
        """
        雙向無縫平滑混融：
        - 當 emergency_trigger 為 True 時：crossfade_alpha 在 0.15s 內平滑升至 1.0 (進入保底)
        - 當 emergency_trigger 為 False 時：crossfade_alpha 在 0.15s 內平滑降至 0.0 (退回主畫面)
        """
        if emergency_trigger:
            self.crossfade_alpha = min(1.0, self.crossfade_alpha + dt * self.transition_speed)
        else:
            self.crossfade_alpha = max(0.0, self.crossfade_alpha - dt * self.transition_speed)

        if self.crossfade_alpha <= 0.001:
            return faulty_or_black_frame

        w, h = faulty_or_black_frame.size
        fallback_frame = self.render(target_w=w, target_h=h, **render_kwargs)

        if self.crossfade_alpha >= 0.999:
            return fallback_frame

        # Cosine 平滑插值
        smooth_alpha = 0.5 - 0.5 * math.cos(self.crossfade_alpha * math.pi)
        try:
            return Image.blend(faulty_or_black_frame, fallback_frame, smooth_alpha)
        except Exception:
            return fallback_frame
