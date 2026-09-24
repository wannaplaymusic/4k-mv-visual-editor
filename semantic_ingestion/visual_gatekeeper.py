# -*- coding: utf-8 -*-
"""
SENTINEL: Visual Gatekeeper (前置物理與數學特徵防火牆)
在影像送入 VLM 之前，以極低開銷的純數值方法篩除死黑屏、死白屏、OpenGL 報錯洋紅以及靜態凍結畫面。
相容累積生長型（Accumulative Drawing）生成藝術。
"""

import numpy as np
from typing import Tuple, List, Dict, Any

class VisualGatekeeper:
    """
    影像健全性門禁過濾器
    """
    
    @staticmethod
    def audit_frames(frames_bgr: List[np.ndarray]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        對抽樣的關鍵幀序列執行門禁審核
        回傳: (is_healthy, reject_reason, metrics)
        """
        if not frames_bgr or len(frames_bgr) == 0:
            return False, "NO_FRAMES_CAPTURED", {}

        metrics = {
            "variances": [],
            "mean_intensities": [],
            "magenta_ratios": [],
            "frame_diffs": []
        }

        # 1. 逐幀計算物理指標
        for idx, img in enumerate(frames_bgr):
            if img is None or img.size == 0:
                return False, f"CORRUPTED_FRAME_{idx}", metrics
            
            gray = np.mean(img, axis=2) if len(img.shape) == 3 else img
            var_val = float(np.var(gray))
            mean_val = float(np.mean(gray))
            metrics["variances"].append(var_val)
            metrics["mean_intensities"].append(mean_val)

            # 檢驗 OpenGL 洋紅報錯色 (#FF00FF)
            if len(img.shape) == 3:
                b = img[:, :, 0].astype(np.float32)
                g = img[:, :, 1].astype(np.float32)
                r = img[:, :, 2].astype(np.float32)
                magenta_mask = (r > 200) & (b > 200) & (g < 40)
                magenta_ratio = float(np.sum(magenta_mask)) / float(img.shape[0] * img.shape[1])
                metrics["magenta_ratios"].append(magenta_ratio)
                if magenta_ratio > 0.45:
                    return False, f"OPENGL_ERROR_MAGENTA_TEXTURE (Frame {idx} MagentaRatio={magenta_ratio:.2f})", metrics

        # 2. 全局方差綜合評定 (相容初始為純背景、隨時間累積畫圖的生成藝術)
        max_var = max(metrics["variances"])
        all_means = metrics["mean_intensities"]
        avg_mean = float(np.mean(all_means))

        if max_var < 0.05:
            # 所有幀都缺乏變化
            if avg_mean < 5.0:
                return False, f"PERSISTENT_BLACK_SCREEN (All Frames Mean={avg_mean:.2f})", metrics
            elif avg_mean > 250.0:
                return False, f"PERSISTENT_WHITE_SCREEN (All Frames Mean={avg_mean:.2f})", metrics
            else:
                return False, f"PERSISTENT_FLAT_COLOR_SCREEN (All Frames MaxVar={max_var:.2f})", metrics

        # 3. 檢驗時序動態性 (前後幀差異)
        if len(frames_bgr) >= 2:
            first_gray = np.mean(frames_bgr[0], axis=2).astype(np.float32)
            for idx in range(1, len(frames_bgr)):
                curr_gray = np.mean(frames_bgr[idx], axis=2).astype(np.float32)
                diff = float(np.mean(np.abs(curr_gray - first_gray)))
                metrics["frame_diffs"].append(diff)
            
            # 若所有後續幀與第一幀差異都為 0，視為無動態的純靜態模組
            if all(d < 0.05 for d in metrics["frame_diffs"]):
                return False, "STATIC_FREEZE_NO_TEMPORAL_DYNAMICS", metrics

        return True, "PASSED_HEALTHY", metrics
