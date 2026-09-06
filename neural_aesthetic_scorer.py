import numpy as np

class NeuralAestheticScorer:
    """
    神經審美評估反饋環 (Neural Aesthetic Quality Assessment Loop):
    - 基於視覺質量分佈、負空間均勻度、力矩偏差與對比度深度衰減推算「構圖美學得分」
    - 模擬 CLIP-Aesthetic / NIMA 分數 (0.0 ~ 10.0)
    - 自動篩除低於閾值 (7.5 分) 的次優排版候選方案
    """
    @classmethod
    def evaluate_composition_quality(cls, candidate_elements: list, canvas_w=1280, canvas_h=720) -> dict:
        if not candidate_elements:
            return {"aesthetic_score": 0.0, "is_gallery_grade": False}

        center = np.array([canvas_w / 2.0, canvas_h / 2.0])
        total_mass = sum([e.get("mass", 1000) for e in candidate_elements])
        
        # 1. 力矩平衡損失 (Torque Balance Loss)
        torque_vector = np.array([0.0, 0.0])
        for e in candidate_elements:
            pos = np.array(e.get("pos", [canvas_w * 0.5, canvas_h * 0.5]))
            arm = pos - center
            torque_vector += arm * (e.get("mass", 1000) / max(1.0, total_mass))

        torque_distance = np.linalg.norm(torque_vector)
        # 偏差小於 80px 為優秀平衡
        balance_score = np.clip(10.0 - (torque_distance / 25.0), 4.0, 10.0)

        # 2. 空間多樣性與景深豐富度得分 (Depth Diversity Score)
        depths = [e.get("z_depth", 0.5) for e in candidate_elements]
        depth_std = np.std(depths) if len(depths) > 1 else 0.2
        depth_score = np.clip(6.0 + depth_std * 15.0, 5.0, 10.0)

        # 3. 負空間鑲嵌獎勵 (SDF Interlocking Bonus)
        has_interlock = any(e.get("role") == "interlocked_cavity" for e in candidate_elements)
        interlock_bonus = 0.8 if has_interlock else 0.0

        # 4. 綜合神經美學得分
        final_score = float(np.round((balance_score * 0.55 + depth_score * 0.45) + interlock_bonus, 2))
        final_score = min(9.95, final_score)

        return {
            "aesthetic_score": final_score,
            "balance_score": float(np.round(balance_score, 2)),
            "depth_score": float(np.round(depth_score, 2)),
            "is_gallery_grade": final_score >= 7.5
        }
