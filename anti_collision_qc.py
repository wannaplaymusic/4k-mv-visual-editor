import os
import cv2
import json
import time
import numpy as np
from typing import List, Optional

class AntiCollisionQC:
    """
    4K MV 視覺防撞車與畫面重複度質檢器 (Anti-Collision Quality Control)
    - 採用輕量化高斯 SSIM 結構相似度演算法
    - 支援自動微縮採樣加速 (4K -> 256px)，避免 GPU/CPU 渲染管道卡頓
    - 支援色彩空間直方圖輔助判定與歷史指紋儲存
    """
    def __init__(self, db_history_dir: Optional[str] = None, ssim_threshold: float = 0.82):
        self.db_dir = db_history_dir
        self.ssim_threshold = ssim_threshold
        self.target_eval_size = (256, 144)  # 16:9 快速評估解析度
        
        # 預計算 11x11 高斯卷積核以提升迴圈執行效率
        self.kernel = cv2.getGaussianKernel(11, 1.5)
        self.window = np.outer(self.kernel, self.kernel.transpose())

        if self.db_dir and not os.path.exists(self.db_dir):
            try:
                os.makedirs(self.db_dir, exist_ok=True)
            except Exception:
                pass

    def _preprocess_frame(self, img_np: np.ndarray) -> np.ndarray:
        """ 快速縮小並轉為灰階 float64 格式 """
        if img_np is None:
            return None
        
        # 1. 快速雙線性縮放至微縮尺寸 (大幅降低空間卷積耗時)
        h, w = img_np.shape[:2]
        if (w, h) != self.target_eval_size:
            img_resized = cv2.resize(img_np, self.target_eval_size, interpolation=cv2.INTER_AREA)
        else:
            img_resized = img_np

        # 2. 轉灰階
        if len(img_resized.shape) == 3:
            if img_resized.shape[2] == 4:  # RGBA -> GRAY
                gray = cv2.cvtColor(img_resized, cv2.COLOR_RGBA2GRAY)
            else:  # RGB/BGR -> GRAY
                gray = cv2.cvtColor(img_resized, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_resized

        return gray.astype(np.float64)

    def calculate_ssim(self, img1_np: np.ndarray, img2_np: np.ndarray) -> float:
        """
        計算兩影格間之 SSIM 結構相似度 (範圍: 0.0 ~ 1.0)
        """
        if img1_np is None or img2_np is None:
            return 0.0

        g1 = self._preprocess_frame(img1_np)
        g2 = self._preprocess_frame(img2_np)

        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        mu1 = cv2.filter2D(g1, -1, self.window)
        mu2 = cv2.filter2D(g2, -1, self.window)

        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2

        sigma1_sq = cv2.filter2D(g1 ** 2, -1, self.window) - mu1_sq
        sigma2_sq = cv2.filter2D(g2 ** 2, -1, self.window) - mu2_sq
        sigma12 = cv2.filter2D(g1 * g2, -1, self.window) - mu1_mu2

        numerator = (2.0 * mu1_mu2 + C1) * (2.0 * sigma12 + C2)
        denominator = (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)

        # 避免分母極端為 0 的數值問題
        denominator = np.where(denominator == 0, 1e-6, denominator)
        ssim_map = numerator / denominator

        return float(np.clip(ssim_map.mean(), 0.0, 1.0))

    def calculate_color_histogram_similarity(self, img1_np: np.ndarray, img2_np: np.ndarray) -> float:
        """ 計算 HSV 空間色彩相似度（防止結構相似但色彩完全不同的畫面被誤殺） """
        if img1_np is None or img2_np is None:
            return 0.0

        hsv1 = cv2.cvtColor(cv2.resize(img1_np, (128, 72)), cv2.COLOR_RGB2HSV)
        hsv2 = cv2.cvtColor(cv2.resize(img2_np, (128, 72)), cv2.COLOR_RGB2HSV)

        hist1 = cv2.calcHist([hsv1], [0, 1], None, [30, 32], [0, 180, 0, 256])
        hist2 = cv2.calcHist([hsv2], [0, 1], None, [30, 32], [0, 180, 0, 256])

        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        return float(max(0.0, score))

    def validate_unique(self, sample_frames: List[np.ndarray], historical_samples: List[np.ndarray]) -> bool:
        """
        比對當前分鏡抽樣幀與歷史樣本：
        - 綜合評估 SSIM 結構與色彩直方圖
        - 若兩者均高於閥值，回傳 False 觸發導演系統重新挑選模組
        """
        if not sample_frames or not historical_samples:
            return True

        for s_frame in sample_frames:
            for h_frame in historical_samples:
                ssim_score = self.calculate_ssim(s_frame, h_frame)
                
                # 結構極度相似時，進一步核對色彩相關度
                if ssim_score > self.ssim_threshold:
                    color_score = self.calculate_color_histogram_similarity(s_frame, h_frame)
                    # 如果結構與色彩皆高度吻合 (同模組同色調撞車)，判定為非唯一
                    if color_score > 0.75:
                        return False
        return True

    def save_fingerprint(self, module_name: str, frame_np: np.ndarray):
        """ 將渲染樣本壓縮並保存為指紋檔案，供跨工作階段防撞比對 """
        if not self.db_dir or frame_np is None:
            return
        
        try:
            thumb = cv2.resize(frame_np, (160, 90))
            if len(thumb.shape) == 3 and thumb.shape[2] == 4:
                thumb = cv2.cvtColor(thumb, cv2.COLOR_RGBA2BGR)
            elif len(thumb.shape) == 3:
                thumb = cv2.cvtColor(thumb, cv2.COLOR_RGB2BGR)

            save_path = os.path.join(self.db_dir, f"qc_{module_name}_{int(time.time())}.jpg")
            cv2.imwrite(save_path, thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except Exception:
            pass
