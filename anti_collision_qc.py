import cv2
import numpy as np

class AntiCollisionQC:
    def __init__(self, db_history_dir: str = None):
        self.db_dir = db_history_dir

    def calculate_ssim(self, img1_np: np.ndarray, img2_np: np.ndarray) -> float:
        """ 計算兩影格間之 SSIM 結構相似度 """
        if img1_np is None or img2_np is None:
            return 0.0
        if img1_np.shape != img2_np.shape:
            img2_np = cv2.resize(img2_np, (img1_np.shape[1], img1_np.shape[0]))

        g1 = cv2.cvtColor(img1_np, cv2.COLOR_RGB2GRAY) if len(img1_np.shape) == 3 else img1_np
        g2 = cv2.cvtColor(img2_np, cv2.COLOR_RGB2GRAY) if len(img2_np.shape) == 3 else img2_np
        
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        g1 = g1.astype(np.float64)
        g2 = g2.astype(np.float64)
        
        kernel = cv2.getGaussianKernel(11, 1.5)
        window = np.outer(kernel, kernel.transpose())

        mu1 = cv2.filter2D(g1, -1, window)
        mu2 = cv2.filter2D(g2, -1, window)

        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2

        sigma1_sq = cv2.filter2D(g1 ** 2, -1, window) - mu1_sq
        sigma2_sq = cv2.filter2D(g2 ** 2, -1, window) - mu2_sq
        sigma12 = cv2.filter2D(g1 * g2, -1, window) - mu1_mu2

        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
        return float(ssim_map.mean())

    def validate_unique(self, sample_frames: list, historical_samples: list) -> bool:
        """ 比對樣本影格，若高於 0.85 相似度則回傳 False 觸發重挑 """
        for s_frame in sample_frames:
            for h_frame in historical_samples:
                score = self.calculate_ssim(s_frame, h_frame)
                if score > 0.85:
                    return False
        return True
