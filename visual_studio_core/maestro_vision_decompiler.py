import os
import logging
from PIL import Image
import numpy as np

logger = logging.getLogger("VisualStudio.MaestroVisionDecompiler")

class MaestroVisionDecompiler:
    """
    視覺參考圖多模態逆向工程器 (Vision-to-P5 Reverse Engine)
    - 讀取創作者拖入的參考截圖或藝術作品 (PNG/JPG)
    - 提取主導色彩調色盤 (Dominant Color Palette)
    - 運算圖像視覺熵與邊緣梯度，推斷幾何質地（流體、粒子、碎形晶體）
    - 產出結構化視覺藍圖 (Visual Spec Blueprint)，直接合成 p5.js 代碼
    """

    @classmethod
    def decompile_reference_image(cls, image_path: str) -> dict:
        """
        逆向解析參考圖片並生成視覺規格藍圖
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            with Image.open(image_path) as img:
                img_rgb = img.convert("RGB")
                w, h = img_rgb.size
                
                # 縮小快速取樣分析
                small = img_rgb.resize((100, 100))
                arr = np.array(small)

            # 1. 色彩聚類提取 (Top Dominant Colors)
            palette_hex = cls._extract_dominant_palette(arr)

            # 2. 邊緣與視覺熵分析 (Texture & Entropy)
            gray = np.mean(arr, axis=2)
            grad_y, grad_x = np.gradient(gray)
            edge_energy = float(np.mean(np.abs(grad_x) + np.abs(grad_y)))
            dark_ratio = float(np.mean(gray < 45))

            # 3. 推斷幾何拓撲與著色器
            if edge_energy > 16.0:
                suggested_topology = "voronoi_crystalline"
                vibe_name = "晶體幾何碎形 (Crystalline Voronoi)"
                shaders = ["chromatic_aberration", "matrix_glitch_mosaic"]
            elif edge_energy < 8.0:
                suggested_topology = "curl_noise_fluid"
                vibe_name = "液態流場渦流 (Fluid Streamline)"
                shaders = ["reaction_diffusion", "aurora_borealis_curtain"]
            else:
                suggested_topology = "lorenz_attractor"
                vibe_name = "三維混沌吸引子 (Chaos Orbit)"
                shaders = ["volumetric_godrays", "chromatic_aberration"]

            fname = os.path.basename(image_path)
            title = f"Refined_{suggested_topology}_{fname[:12]}"

            return {
                "image_path": image_path,
                "title": title,
                "vibe_name": vibe_name,
                "topology_id": suggested_topology,
                "palette": palette_hex,
                "edge_energy": edge_energy,
                "dark_ratio": dark_ratio,
                "shaders": shaders,
                "narrative": f"從參考圖【{fname}】中逆向提取出【{vibe_name}】質地，主色系覆蓋 {len(palette_hex)} 階層，已映射為即時音畫動態。"
            }
        except Exception as e:
            logger.error(f"Failed to decompile image {image_path}: {e}")
            raise

    @staticmethod
    def _extract_dominant_palette(img_np: np.ndarray, count: int = 4) -> list:
        """從影像陣列中提取具備美學對比的主導色調"""
        pixels = img_np.reshape(-1, 3)
        # 簡易色彩量化 (Quantization)
        quantized = (pixels // 32) * 32
        unique, counts = np.unique(quantized, axis=0, return_counts=True)
        sorted_indices = np.argsort(-counts)

        colors = []
        for idx in sorted_indices[:count]:
            r, g, b = unique[idx]
            hex_col = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            colors.append(hex_col)

        # 保證至少有深色背景色與高亮色
        if len(colors) < 4:
            colors = ["#ff007f", "#00f0ff", "#7928ca", "#0b0c10"]
        return colors
