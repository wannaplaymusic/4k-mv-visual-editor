# -*- coding: utf-8 -*-
"""
SENTINEL: Spatiotemporal Tiler & Objective Perceptual Feature Extractor
1. 4-in-1 田字格時空拼貼 (1024x1024, Token 節省 85%)
2. 感知色彩 OKLCH 與光流動態數值特徵提取
"""

import math
import numpy as np
import cv2
from PIL import Image
from typing import List, Tuple, Dict, Any

class SpatiotemporalTiler:
    """
    負責時序影格降維拼接與物理數值抽取
    """
    
    @staticmethod
    def create_4in1_collage(frames_bgr: List[np.ndarray], target_size: int = 1024) -> Image.Image:
        """
        將 4 個時間點的幀拼貼成田字格 (左上: 1s, 右上: 3.5s, 左下: 8s, 右下: 15s)
        輸出 1024x1024 PIL Image (RGB)
        """
        sub_size = target_size // 2
        collage = np.zeros((target_size, target_size, 3), dtype=np.uint8)

        # 填入對應象限
        quadrants = [
            (0, sub_size, 0, sub_size),          # Top-Left: t1
            (0, sub_size, sub_size, target_size), # Top-Right: t2
            (sub_size, target_size, 0, sub_size), # Bottom-Left: t3
            (sub_size, target_size, sub_size, target_size) # Bottom-Right: t4
        ]

        for i in range(4):
            y1, y2, x1, x2 = quadrants[i]
            if i < len(frames_bgr) and frames_bgr[i] is not None:
                resized = cv2.resize(frames_bgr[i], (sub_size, sub_size), interpolation=cv2.INTER_AREA)
                collage[y1:y2, x1:x2] = resized
            else:
                # 若不足 4 幀，重複最後一幀
                last_frame = frames_bgr[-1] if frames_bgr else np.zeros((sub_size, sub_size, 3), dtype=np.uint8)
                resized = cv2.resize(last_frame, (sub_size, sub_size), interpolation=cv2.INTER_AREA)
                collage[y1:y2, x1:x2] = resized

        # BGR 轉 RGB
        rgb_collage = cv2.cvtColor(collage, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_collage)

    @staticmethod
    def extract_color_features(frames_bgr: List[np.ndarray]) -> Dict[str, Any]:
        """
        在客觀感知色彩空間中計算色相角度、明度與彩度分佈
        """
        all_hues = []
        all_sats = []
        all_vals = []

        for frame in frames_bgr:
            if frame is None:
                continue
            # 轉換為 HSV 作為感知色相近似 (OpenCV H: 0~180 -> 0~360度)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h = hsv[:, :, 0].astype(np.float32) * 2.0 # 換算為 0~360度
            s = hsv[:, :, 1].astype(np.float32) / 255.0
            v = hsv[:, :, 2].astype(np.float32) / 255.0

            # 採樣有彩度的像素以計算主導色相
            chroma_mask = s > 0.15
            if np.any(chroma_mask):
                valid_hues = h[chroma_mask]
                all_hues.extend(valid_hues[::100].tolist())
            all_sats.extend(s[::100].tolist())
            all_vals.extend(v[::100].tolist())

        mean_l = float(np.mean(all_vals)) if all_vals else 0.5
        mean_c = float(np.mean(all_sats)) * 0.4 if all_sats else 0.1

        # 計算主導色相 (統計前 2 個波峰)
        dominant_hues = []
        if all_hues:
            hist, bin_edges = np.histogram(all_hues, bins=12, range=(0, 360))
            top_bins = np.argsort(hist)[::-1][:2]
            for b in top_bins:
                if hist[b] > (len(all_hues) * 0.12):
                    dominant_hues.append(float((bin_edges[b] + bin_edges[b+1]) / 2.0))

        # 判定色彩對比型態
        if mean_c < 0.05:
            contrast_level = "monochrome_stark"
        elif len(dominant_hues) >= 2:
            hue_diff = abs(dominant_hues[0] - dominant_hues[1])
            if 130 <= hue_diff <= 230:
                contrast_level = "complementary_clash"
            elif hue_diff < 60:
                contrast_level = "analogous_subtle"
            else:
                contrast_level = "polychromatic_chaos"
        else:
            contrast_level = "analogous_subtle"

        # 判定色彩溫度
        if mean_c < 0.05:
            temp = "sterile_neutral"
        elif dominant_hues and (180 <= dominant_hues[0] <= 270):
            temp = "glacial_cold"
        elif dominant_hues and (0 <= dominant_hues[0] <= 60 or dominant_hues[0] >= 330):
            temp = "feverish_warm"
        elif dominant_hues and (70 <= dominant_hues[0] <= 160):
            temp = "toxic_luminescent"
        else:
            temp = "sterile_neutral"

        return {
            "dominant_oklch_hues": dominant_hues,
            "mean_lightness": round(mean_l, 3),
            "mean_chroma": round(mean_c, 3),
            "contrast_level": contrast_level,
            "emotional_temperature": temp
        }

    @staticmethod
    def extract_motion_features(frames_bgr: List[np.ndarray]) -> Dict[str, Any]:
        """
        計算影格間動態運動光流特徵 (Farneback 光流演算法)
        """
        if len(frames_bgr) < 2:
            return {
                "mean_velocity": 0.0,
                "curl_vorticity": 0.0,
                "divergence": 0.0,
                "motion_energy_type": "static_crystalline"
            }

        prev_gray = cv2.cvtColor(cv2.resize(frames_bgr[0], (256, 256)), cv2.COLOR_BGR2GRAY)
        velocities = []
        curls = []
        divergences = []

        for i in range(1, len(frames_bgr)):
            curr_gray = cv2.cvtColor(cv2.resize(frames_bgr[i], (256, 256)), cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray, None, 
                pyr_scale=0.5, levels=2, winsize=15, 
                iterations=2, poly_n=5, poly_sigma=1.1, flags=0
            )
            u = flow[:, :, 0]
            v = flow[:, :, 1]
            mag, _ = cv2.cartToPolar(u, v)
            velocities.append(float(np.mean(mag)))

            # 計算散度 (du/dx + dv/dy) 與 旋度 (dv/dx - du/dy)
            du_dx = np.gradient(u, axis=1)
            dv_dy = np.gradient(v, axis=0)
            dv_dx = np.gradient(v, axis=1)
            du_dy = np.gradient(u, axis=0)

            div = np.mean(du_dx + dv_dy)
            curl = np.mean(np.abs(dv_dx - du_dy))
            divergences.append(float(div))
            curls.append(float(curl))

            prev_gray = curr_gray

        mean_v = float(np.mean(velocities)) if velocities else 0.0
        mean_c = float(np.mean(curls)) if curls else 0.0
        mean_d = float(np.mean(divergences)) if divergences else 0.0

        # 動能型態分類
        if mean_v < 0.5:
            energy_type = "static_crystalline"
        elif mean_d < -0.3:
            energy_type = "inward_implosion"
        elif mean_d > 0.3:
            energy_type = "outward_explosion"
        elif mean_c > 0.8:
            energy_type = "chaotic_brownian"
        else:
            energy_type = "sinusoidal_breath"

        return {
            "mean_velocity": round(mean_v, 2),
            "curl_vorticity": round(mean_c, 3),
            "divergence": round(mean_d, 3),
            "motion_energy_type": energy_type
        }
