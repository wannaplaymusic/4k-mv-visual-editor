import math
import random
import numpy as np

class OKLCHPaletteGenerator:
    """
    OKLCH 感知均勻色彩生成器 (Perceptually Uniform Palette Generator)
    - 結合 track_seed、3D DNA 座標與 genre 自動衍生視覺色系
    - 支援主副調 (Major / Minor) 模式與 sRGB 色域安全壓縮
    """
    def __init__(self, track_seed: int, dna_coord: np.ndarray, genre: str = 'generic'):
        self.rng = random.Random(track_seed)
        self.dna = dna_coord if dna_coord is not None else np.array([0.5, 0.5, 0.5], dtype=np.float32)
        self.genre = str(genre).lower()

    def _oklch_to_rgb(self, l: float, c: float, h_deg: float) -> tuple:
        """ OKLCH -> OKLAB -> sRGB 轉換算子 (內建 sRGB 色域安全邊界夾具) """
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
        """ 生成完整的歌曲專屬多維色票包 (含 Major/Minor 雙模組與 Hex 格式) """
        base_h = self.rng.uniform(0.0, 360.0)
        
        # 依據音樂曲風調整明度與彩度基底
        if self.genre in ('ambient', 'dub_techno', 'lo-fi', 'classical', 'jazz'):
            l_base = 0.22 + 0.18 * float(self.dna[0])
            c_base = 0.05 + 0.07 * float(self.dna[1])
            harmonies = [0.0, 35.0, 190.0, 220.0]  # 鄰近色與微互補
        elif self.genre in ('hard_techno', 'dnb', 'dubstep', 'acid'):
            l_base = 0.55 + 0.30 * float(self.dna[0])
            c_base = 0.20 + 0.12 * float(self.dna[1])
            harmonies = [0.0, 90.0, 180.0, 270.0]  # 高張力四分對沖
        else:
            l_base = 0.45 + 0.35 * float(self.dna[0])
            c_base = 0.15 + 0.15 * float(self.dna[1])
            harmonies = [0.0, 120.0, 240.0, 60.0]  # 三分色彩對沖
            
        rgb_colors = []
        for offset in harmonies:
            h = (base_h + offset) % 360.0
            rgb_colors.append(self._oklch_to_rgb(l_base, c_base, h))
            
        # 衍生出 Minor（較低明度與彩度）與 Major（高光亮彩）版本供 PostProcessor 使用
        rgb_minor = self._oklch_to_rgb(max(0.15, l_base * 0.7), c_base * 0.8, base_h)
        rgb_major = self._oklch_to_rgb(min(0.95, l_base * 1.2), min(0.25, c_base * 1.2), (base_h + 40.0) % 360.0)

        def to_hex(rgb):
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

        return {
            "primary": rgb_colors[0],
            "secondary": rgb_colors[1],
            "accent": rgb_colors[2],
            "highlight": rgb_colors[3] if len(rgb_colors) > 3 else rgb_colors[0],
            "minor": np.array(rgb_minor, dtype=np.float32) / 255.0,
            "major": np.array(rgb_major, dtype=np.float32) / 255.0,
            "primary_hex": to_hex(rgb_colors[0]),
            "accent_hex": to_hex(rgb_colors[2]),
            "base_hue": float(base_h)
        }
