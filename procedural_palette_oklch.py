import math
import random
import numpy as np

class OKLCHPaletteGenerator:
    def __init__(self, track_seed: int, dna_coord: np.ndarray, genre: str = 'generic'):
        self.rng = random.Random(track_seed)
        self.dna = dna_coord if dna_coord is not None else np.array([0.5, 0.5, 0.5])
        self.genre = str(genre).lower()

    def _oklch_to_rgb(self, l: float, c: float, h_deg: float) -> tuple:
        """ OKLCH -> OKLAB -> sRGB 轉換算子 """
        h_rad = math.radians(h_deg)
        a = c * math.cos(h_rad)
        b = c * math.sin(h_rad)
        
        # OKLAB to LMS
        l_ = l + 0.3963377774 * a + 0.2158037573 * b
        m_ = l - 0.1055613458 * a - 0.0638541728 * b
        s_ = l - 0.0894841775 * a - 1.2914855480 * b
        
        l3, m3, s3 = l_**3, m_**3, s_**3
        
        # LMS to Linear RGB
        r_l = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
        g_l = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
        b_l = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3
        
        # Gamma correction
        def gamma(x):
            x = max(0.0, min(1.0, x))
            return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1.0 / 2.4)) - 0.055
            
        r = int(gamma(r_l) * 255.99)
        g = int(gamma(g_l) * 255.99)
        b = int(gamma(b_l) * 255.99)
        return (r, g, b)

    def generate_palette(self) -> dict:
        base_h = self.rng.uniform(0.0, 360.0)
        
        if self.genre in ('ambient', 'dub_techno', 'lo-fi'):
            l_base = 0.20 + 0.20 * float(self.dna[0])
            c_base = 0.04 + 0.08 * float(self.dna[1])
            harmonies = [0.0, 30.0, 180.0]  # 鄰近色與微互補
        else:
            l_base = 0.45 + 0.35 * float(self.dna[0])
            c_base = 0.18 + 0.14 * float(self.dna[1])
            harmonies = [0.0, 120.0, 240.0] # 三分色彩對沖
            
        colors = []
        for offset in harmonies:
            h = (base_h + offset) % 360.0
            colors.append(self._oklch_to_rgb(l_base, c_base, h))
            
        return {
            "primary": colors[0],
            "secondary": colors[1],
            "accent": colors[2],
            "base_hue": base_h
        }
