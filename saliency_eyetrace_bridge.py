import math
import logging
from typing import Dict, Any, Tuple, Optional, List

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger("StandaloneInjector.SaliencyEyeTraceBridge")

class SaliencyEyeTraceBridge:
    """
    視線引導 (Eye-Trace Continuity) 與視覺質心連續性橋接模組
    - 依據 Walter Murch「Rule of Six」之第 4 法則：尊重觀眾視線焦點位置與移動軌跡
    - 計算畫面顯著性/亮度/高頻拉普拉斯質心 (Centroid Cx, Cy) 與動勢慣性向量 (Vx, Vy)
    - 提供接鏡初始相機錨定補償、方向性光流置換轉場 (Displacement Direction) 與反對稱震撼切 (Shock Cut)
    """

    @classmethod
    def estimate_saliency_centroid(
        cls, 
        frame_rgb: Optional[np.ndarray] = None, 
        mock_elements: Optional[List[Dict[str, Any]]] = None,
        canvas_w: int = 1280, 
        canvas_h: int = 720
    ) -> Dict[str, Any]:
        """
        估算畫面的視覺顯著性焦點 (Normalized 0.0 ~ 1.0)
        若提供 frame_rgb (如 4K 降採樣幀)，使用亮度與邊緣梯度卷積；
        若為純幾何/模組預測模式，使用素材空間分佈與質量質心。
        """
        if frame_rgb is not None and frame_rgb.size > 0:
            try:
                # 轉灰階與降採樣至超輕量 64x36 進行向量化極速計算
                import cv2
                small = cv2.resize(frame_rgb, (64, 36))
                if len(small.shape) == 3:
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                else:
                    gray = small

                # 計算梯度幅值以代表高頻細節注意力
                grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
                grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
                grad_mag = cv2.magnitude(grad_x, grad_y)

                # 顯著圖 = 亮度 * (1 + 梯度)
                saliency = (gray.astype(np.float32) / 255.0) * (1.0 + grad_mag / 255.0)
                total_mass = np.sum(saliency)

                if total_mass > 1e-4:
                    y_indices, x_indices = np.indices(saliency.shape)
                    cx = float(np.sum(x_indices * saliency) / total_mass) / 64.0
                    cy = float(np.sum(y_indices * saliency) / total_mass) / 36.0
                else:
                    cx, cy = 0.5, 0.5

                return {
                    "cx": round(float(cx), 4),
                    "cy": round(float(cy), 4),
                    "confidence": 0.92,
                    "mode": "pixel_gradient"
                }
            except Exception as e:
                logger.debug(f"Pixel saliency computation fallback: {e}")

        # 幾何分佈質心估算 (Heuristic / SAVAP Mock)
        if mock_elements:
            total_mass = 0.0
            sum_x = 0.0
            sum_y = 0.0
            for el in mock_elements:
                pos = el.get("pos", [canvas_w / 2, canvas_h / 2])
                mass = float(el.get("mass", 10000.0))
                sum_x += pos[0] * mass
                sum_y += pos[1] * mass
                total_mass += mass
            if total_mass > 0:
                cx = (sum_x / total_mass) / canvas_w
                cy = (sum_y / total_mass) / canvas_h
                return {
                    "cx": round(float(cx), 4),
                    "cy": round(float(cy), 4),
                    "confidence": 0.78,
                    "mode": "geometric_mass"
                }

        # 預設黃金分割焦點
        return {"cx": 0.5, "cy": 0.45, "confidence": 0.5, "mode": "rule_of_thirds"}

    @classmethod
    def compute_cut_transition_continuity(
        cls,
        prev_centroid: Dict[str, Any],
        next_target_centroid: Optional[Dict[str, Any]] = None,
        is_high_tension_drop: bool = False
    ) -> Dict[str, Any]:
        """
        計算兩個連續鏡頭切換時的視線平滑過渡補償向量與推薦轉場樣式
        """
        p_cx = prev_centroid.get("cx", 0.5)
        p_cy = prev_centroid.get("cy", 0.5)

        if is_high_tension_drop:
            # 震撼切 (Shock Cut): 故意反轉質心，產生視神經電位反衝
            target_cx = 1.0 - p_cx
            target_cy = 1.0 - p_cy
            transition_style = "glitch_displacement_flash"
            camera_compensation = [0.0, 0.0]
            continuity_score = 0.35  # 刻意降低連續性以最大化情緒衝擊
        else:
            # 平滑動勢導引 (Smooth Eye-Trace Follow)
            if next_target_centroid:
                target_cx = next_target_centroid.get("cx", 0.5)
                target_cy = next_target_centroid.get("cy", 0.5)
            else:
                target_cx = p_cx
                target_cy = p_cy

            dx = target_cx - p_cx
            dy = target_cy - p_cy
            dist = math.sqrt(dx * dx + dy * dy)
            continuity_score = max(0.0, 1.0 - dist * 1.5)

            # 相機補償向量 (將新鏡頭初始 LookAt 朝上一鏡頭焦點微調偏移)
            camera_compensation = [round(-dx * 0.4, 4), round(-dy * 0.4, 4)]
            
            # 根據運動方向推薦轉場風格
            angle = math.atan2(dy, dx) * (180.0 / math.pi)
            if dist > 0.3:
                transition_style = "directional_wipe"
            elif dist > 0.15:
                transition_style = "zoom_blur"
            else:
                transition_style = "luma_matte"

        return {
            "source_centroid": [p_cx, p_cy],
            "target_centroid": [target_cx, target_cy],
            "camera_lookat_offset": camera_compensation,
            "recommended_transition": transition_style,
            "continuity_score": round(continuity_score, 3),
            "is_shock_cut": is_high_tension_drop
        }
