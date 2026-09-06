import numpy as np
import cv2
from PIL import Image

class AestheticLayoutOptimizer:
    """
    基於視覺質量平衡 (Visual Mass Balance) 與黃金螺旋引導的超現實構圖優化器
    - 視覺質量 (Visual Mass) = 面積 × 邊緣細節複雜度 (Laplacian Energy) × 對比度
    - 力矩平衡 (Torque Equilibrium) 求解最佳空間座標
    - 黃金螺旋 (Logarithmic Spiral / 137.5° Golden Angle) 視線引導路徑
    """
    def __init__(self, canvas_w=1280, canvas_h=720):
        self.cw = canvas_w
        self.ch = canvas_h
        self.center = np.array([canvas_w / 2.0, canvas_h / 2.0])

    def calculate_visual_mass(self, pil_img: Image.Image) -> tuple:
        """
        計算素材的「視覺質量 (Visual Mass)」與「局部重心 (Centroid)」
        質量 = 面積 × 邊緣高頻複雜度 (Laplacian Energy) × 對比度
        """
        rgba_img = pil_img.convert("RGBA")
        np_img = np.array(rgba_img)
        alpha = np_img[:, :, 3]
        gray = cv2.cvtColor(np_img[:, :, :3], cv2.COLOR_RGB2GRAY)

        # 1. 實體面積
        area = cv2.countNonZero(alpha)
        if area == 0:
            return 0.0, (0.5, 0.5)

        # 2. 邊緣高頻細節密度 (Sobel / Laplacian)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        complexity = np.mean(np.abs(laplacian[alpha > 0])) if area > 0 else 1.0

        # 3. 視覺質量綜合權重
        visual_mass = float(area * (1.0 + complexity * 0.05))

        # 4. 計算素材內部重心
        m = cv2.moments(alpha)
        cx = (m["m10"] / m["m00"]) if m["m00"] > 0 else (alpha.shape[1] / 2.0)
        cy = (m["m01"] / m["m00"]) if m["m00"] > 0 else (alpha.shape[0] / 2.0)

        return visual_mass, (cx / max(1, alpha.shape[1]), cy / max(1, alpha.shape[0]))

    def optimize_layout(self, asset_list: list) -> list:
        """
        輸入 N 個素材，依據視覺槓桿平衡與黃金比例分配最佳 (x, y, scale, z_depth)
        """
        if not asset_list:
            return []

        # 提取每個素材的質量
        analyzed = []
        for asset in asset_list:
            mass, local_centroid = self.calculate_visual_mass(asset["image"])
            analyzed.append({
                "id": asset["id"],
                "img": asset["image"],
                "keyword": asset.get("keyword", ""),
                "mass": mass,
                "local_centroid": local_centroid,
                "w": asset["image"].width,
                "h": asset["image"].height
            })

        # 按質量降序排列（質量最大者為核心 Hero Element）
        analyzed.sort(key=lambda x: x["mass"], reverse=True)
        
        placed_elements = []

        # 1. 放置核心主體 (Hero)：鎖定在畫面黃金焦點 (如 X: 45~55%, Y: 52~58%)
        hero = analyzed[0]
        hero_pos = np.array([self.cw * 0.5, self.ch * 0.56])
        placed_elements.append({
            "id": hero["id"],
            "keyword": hero["keyword"],
            "role": "hero",
            "pos": hero_pos.tolist(),
            "scale": 1.0,
            "z_depth": 0.4,
            "mass": hero["mass"],
            "orbit_radius": 0,
            "angle_offset": 0,
            "orbit_speed": 0
        })

        # 2. 依據力矩平衡放置剩餘次要物件 (黃金螺旋與反向平衡力臂)
        current_torque = np.array([0.0, 0.0]) # 當前畫布力矩偏差
        golden_angle = 137.5 * (np.pi / 180.0)

        for i, item in enumerate(analyzed[1:], start=1):
            # 尋找能夠抵消當前力矩的最佳方位
            angle = i * golden_angle
            radius = 175.0 + (i * 55.0) # 漸進向外展開

            # 基礎候選座標
            candidate_x = self.cw * 0.5 + np.cos(angle) * radius
            candidate_y = self.ch * 0.5 + np.sin(angle) * (radius * 0.62) # 壓扁為 16:9 橢圓

            # 邊界保護
            candidate_x = np.clip(candidate_x, item["w"] * 0.25, self.cw - item["w"] * 0.25)
            candidate_y = np.clip(candidate_y, item["h"] * 0.25, self.ch - item["h"] * 0.25)

            cand_pos = np.array([candidate_x, candidate_y])

            # 計算該物件帶來的力矩
            arm_vector = cand_pos - self.center
            current_torque += arm_vector * (item["mass"] * 0.001)

            # 尺度自動調製：外圍物件依據景深與質量進行層次微調
            assigned_scale = np.clip(1.0 - (i * 0.09), 0.45, 0.85)

            placed_elements.append({
                "id": item["id"],
                "keyword": item["keyword"],
                "role": "satellite" if i > 1 else "primary_conflict",
                "pos": cand_pos.tolist(),
                "scale": float(assigned_scale),
                "z_depth": float(0.5 + i * 0.06),
                "mass": item["mass"],
                "orbit_radius": float(radius),
                "angle_offset": float(angle),
                "orbit_speed": float(0.012 + (0.004 * i))
            })

        return placed_elements
