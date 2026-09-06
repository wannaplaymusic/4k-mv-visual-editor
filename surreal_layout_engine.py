import os
import cv2
import numpy as np
from PIL import Image

class SurrealLayoutEngine:
    """
    超現實空間分層與尺度倒錯佈局引擎
    """
    def __init__(self, canvas_width=1280, canvas_height=720):
        self.cw = canvas_width
        self.ch = canvas_height

    def analyze_asset_features(self, pil_image: Image.Image) -> dict:
        """分析素材的幾何尺寸、縱橫比、重心與實體像素佔比"""
        rgba_img = pil_image.convert("RGBA")
        np_img = np.array(rgba_img)
        alpha = np_img[:, :, 3]
        
        non_zero = cv2.countNonZero(alpha)
        total_pixels = alpha.shape[0] * alpha.shape[1]
        density = non_zero / max(1, total_pixels)

        # 計算重心 (Centroid)
        m = cv2.moments(alpha)
        if m["m00"] > 0:
            cx = m["m10"] / m["m00"] / alpha.shape[1]
            cy = m["m01"] / m["m00"] / alpha.shape[0]
        else:
            cx, cy = 0.5, 0.5

        return {
            "aspect_ratio": alpha.shape[1] / max(1, alpha.shape[0]),
            "density": density,
            "centroid": (float(cx), float(cy)),
            "orig_size": (alpha.shape[1], alpha.shape[0])
        }

    def compose_scene(self, asset_list: list) -> dict:
        """
        將多個去背素材自動分配至 4 個空間深度層，並計算座標與倒錯比例
        """
        if not asset_list:
            return {}

        # 依據複雜度與縱橫比評估主體
        scored_assets = []
        for asset in asset_list:
            feat = self.analyze_asset_features(asset["image"])
            # 縱向、實體佔比高的物件優先成為主體焦點
            score = (1.0 / max(0.2, feat["aspect_ratio"])) * 0.6 + feat["density"] * 0.4
            scored_assets.append((score, asset, feat))

        scored_assets.sort(key=lambda x: x[0], reverse=True)

        scene_graph = {
            "layers": {
                "foreground_glitch": [],  # Z = 0.1
                "hero_subject": [],       # Z = 0.4
                "midground_conflict": [],  # Z = 0.7
                "background_void": []     # Z = 0.95
            }
        }

        # 1. 主體焦點層 (Hero Element)
        hero = scored_assets[0]
        scene_graph["layers"]["hero_subject"].append({
            "id": hero[1]["id"],
            "z_depth": 0.4,
            "target_scale": 1.0,
            "pos": [self.cw * 0.5, self.ch * 0.55],
            "physics_role": "puppet_or_anchor"
        })

        # 2. 中景衝突層 (套用尺度倒錯 Scale Inversion)
        if len(scored_assets) > 1:
            for idx, conflict in enumerate(scored_assets[1:], start=1):
                feat = conflict[2]
                # 超現實尺度倒錯：日常微觀物體隨機放大 1.8~2.8 倍，宏觀物體縮小 0.4~0.6 倍
                scale_inversion = 2.2 if feat["aspect_ratio"] > 1.0 else 0.55
                
                # 錯開擺放位置 (依據黃金分割配置)
                offset_x = self.cw * (0.25 if idx % 2 == 1 else 0.75)
                offset_y = self.ch * (0.35 if idx % 2 == 1 else 0.65)

                scene_graph["layers"]["midground_conflict"].append({
                    "id": conflict[1]["id"],
                    "z_depth": 0.7,
                    "target_scale": scale_inversion,
                    "pos": [offset_x, offset_y],
                    "physics_role": "floating_or_orbiting"
                })

        # 3. 遠景與前景環境參數
        scene_graph["layers"]["background_void"].append({
            "type": "procedural_engraved_sky",
            "z_depth": 0.95,
            "reactive_to": "sub_bass_and_chord"
        })
        scene_graph["layers"]["foreground_glitch"].append({
            "type": "reticle_and_particles",
            "z_depth": 0.1,
            "reactive_to": "hihat_transients"
        })

        return scene_graph
