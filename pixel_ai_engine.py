import json
import logging
import re
from typing import Dict, Any, List, Optional
from ai_code_generator import AICodeGenerator

logger = logging.getLogger('StandaloneInjector.PixelAIEngine')

STYLE_MODE_MAP = {
    'block': 0, 'square': 0, '方塊': 0,
    'bayer4': 1, 'bayer 4': 1,
    'bayer8': 2, 'bayer 8': 2, 'bayer': 2, '抖動': 2,
    'blue_noise': 3, 'blue noise': 3, '藍噪': 3, '雜訊': 3,
    'halftone': 4, '半色調': 4, '波點': 4, '印刷': 4,
    'crosshatch': 5, '排線': 5, '素描': 5, '漫畫': 5,
    'crt_phosphor': 6, 'subpixel': 6, '螢光粉': 6,
    'diamond': 7, '菱形': 7,
    'ascii': 8, 'matrix': 8, '字符': 8, '代碼': 8,
    'glitch': 9, 'tear': 9, '故障': 9, '撕裂': 9,
    'voronoi': 10, 'crystal': 10, '水晶': 10, '多邊形': 10,
    'voxel': 11, '3d': 11, '浮雕': 11, '體積': 11,
    'amiga_ham': 12, 'ham6': 12, '流體油畫': 12,
    'life': 13, 'cellular': 13, '生命遊戲': 13,
    'thermal': 14, 'flir': 14, '熱成像': 14
}

PALETTE_MAP = {
    'cyberpunk': 0, 'neon': 0, '賽博': 0, '霓虹': 0,
    'gameboy': 1, 'game boy': 1, 'gb': 1, '初版': 1,
    'pocket': 2, '黑白': 2, '灰階': 2,
    'c64': 3, 'commodore': 3,
    'pico': 4, 'pico8': 4, 'pico-8': 4,
    'vaporwave': 5, 'pastel': 5, '蒸汽波': 5, '粉彩': 5,
    'tokyo': 6, '暗夜': 6,
    'matrix_green': 7, '駭客': 7, '數位綠': 7,
    'synthwave': 8, 'outrun': 8, '落日公路': 8,
    'amber': 9, 'apple2': 9, '琥珀': 9,
    'nord': 10, 'arctic': 10, '極地': 10, '冰原': 10,
    'dracula': 11, 'gothic': 11, '歌德': 11, '德古拉': 11,
    'acid': 12, '酸性': 12,
    'sepia': 13, 'vintage': 13, '老照片': 13, '復古': 13,
    'thermal_heat': 14, '紅外線': 14,
    'manga': 15, '二值': 15,
    'quantize': 16,
    'photo': 17,
    'sunset': 18, '金橙': 18,
    'space': 19, '深空': 19,
    'amiga': 20, 'copper': 20, '彩虹': 20
}

def np_clip(val, low, high):
    try:
        f = float(val)
        return max(low, min(high, f))
    except:
        return low

class PixelAIEngine:
    """
    像素化視覺模組專用 AI 智慧調校與生成引擎：
    1. 自然語言指令 -> Shader 參數解析 (Prompt-to-Shader)
    2. 音樂情緒自適應 16-Bit RGB 原創調色盤生成 (Harmonic Palette Synthesizer)
    3. 像素模組 Visual DNA 與章節適合度打分 (Director Tagging)
    """
    def __init__(self, generator: Optional[AICodeGenerator] = None):
        self.generator = generator or AICodeGenerator()

    def decode_prompt_to_params(self, user_prompt: str) -> Dict[str, Any]:
        """ 將自然語言描述解析為精確的像素 Shader 參數 """
        prompt = f"""You are an expert retro graphics & GLSL shader designer.
Translate this user prompt for a 4K Audio-Reactive Pixel Shader into precise JSON parameters:
Prompt: "{user_prompt}"

Available Options:
- grid_size: 8 (fine), 10 (recommended), 12 (standard), 16 (retro 8-bit), 24 (chunky), 32 (extreme pixel)
- style_mode (0..14):
  0: Block Pixel, 1: Bayer 4x4, 2: Bayer 8x8, 3: Blue Noise, 4: Halftone Dot,
  5: Crosshatch, 6: CRT Phosphor, 7: Diamond, 8: ASCII Matrix, 9: Glitch Slicing,
  10: Voronoi Crystal, 11: 3D Voxel Prism, 12: Amiga HAM6, 13: Cellular Life, 14: Thermal FLIR
- palette_id (0..20):
  0: Cyberpunk Neon, 1: GameBoy Classic 1989, 2: GameBoy Pocket, 3: C64, 4: PICO-8,
  5: Vaporwave Pastel, 6: Tokyo Night, 7: Matrix Green, 8: Synthwave Outrun, 9: Apple II Amber,
  10: Nord Arctic, 11: Dracula Gothic, 12: Acid Techno, 13: Sepia Vintage, 14: Thermal FLIR,
  15: 1-bit Manga, 16: Quantized, 18: Sunset Gold, 19: Deep Space, 20: Amiga Copper Rainbow
- crt: boolean (true for retro tube scanlines & vignette, false for clean digital)
- chromatic: float (0.0 to 1.0, RGB chromatic aberration intensity)
- audio_gain: float (0.5 to 3.0, audio reactivity multiplier)
- suggested_name: lowercase alphanumeric with underscore (e.g. "gameboy_lofi_cyber")

Respond ONLY with a valid JSON object matching this structure:
{{
  "grid_size": 12,
  "style_mode": 2,
  "palette_id": 0,
  "crt": true,
  "chromatic": 0.4,
  "audio_gain": 1.0,
  "suggested_name": "pixel_custom"
}}"""

        try:
            raw_text = self.generator.call_llm(prompt=prompt, system_prompt="Output ONLY valid JSON.", json_mode=True, timeout=60)
            raw_text = re.sub(r'<think>[\s\S]*?<\/think>', '', raw_text, flags=re.IGNORECASE).strip()
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_text)
            if json_match:
                raw_text = json_match.group(1).strip()
            data = json.loads(raw_text)
            
            grid = int(data.get("grid_size", 12))
            if grid not in [8, 10, 12, 16, 24, 32]:
                grid = min([8, 10, 12, 16, 24, 32], key=lambda x: abs(x - grid))
                
            style = int(np_clip(data.get("style_mode", 2), 0, 14))
            pal = int(np_clip(data.get("palette_id", 0), 0, 20))
            crt = bool(data.get("crt", True))
            chroma = float(np_clip(data.get("chromatic", 0.4), 0.0, 1.0))
            gain = float(np_clip(data.get("audio_gain", 1.0), 0.1, 3.0))
            name = str(data.get("suggested_name", "ai_pixel_synth"))
            name = re.sub(r'[^a-zA-Z0-9_]', '_', name)[:32]

            return {
                "grid_size": grid,
                "style_mode": style,
                "palette_id": pal,
                "crt": crt,
                "chromatic": chroma,
                "audio_gain": gain,
                "suggested_name": name
            }
        except Exception as e:
            logger.warning(f"AI 參數解析失敗 ({e})，使用關鍵字規則解析...")
            return self._rule_based_fallback(user_prompt)

    def _rule_based_fallback(self, prompt: str) -> Dict[str, Any]:
        p = prompt.lower()
        grid = 12
        if "粗" in p or "8bit" in p or "8-bit" in p: grid = 16
        elif "極限" in p or "大" in p: grid = 24
        elif "細" in p or "精細" in p: grid = 8

        style = 2
        for k, v in STYLE_MODE_MAP.items():
            if k in p:
                style = v
                break

        pal = 0
        for k, v in PALETTE_MAP.items():
            if k in p:
                pal = v
                break

        crt = not ("無crt" in p or "關閉crt" in p or "乾淨" in p)
        chroma = 0.6 if ("色散" in p or "色差" in p or "glitch" in p) else 0.35
        gain = 1.5 if ("強烈" in p or "重低音" in p or "炸" in p) else 1.0

        return {
            "grid_size": grid,
            "style_mode": style,
            "palette_id": pal,
            "crt": crt,
            "chromatic": chroma,
            "audio_gain": gain,
            "suggested_name": f"ai_pixel_{style}_{pal}"
        }

    def generate_harmonic_palette(self, genre: str = "Cyberpunk", mood: str = "Dark Energetic") -> Dict[str, Any]:
        """ 依據音樂調性與情緒，生成專屬的 4 色 OKLCH/RGB 像素調色盤 """
        prompt = f"""Generate a beautiful, harmonious 4-color retro pixel art palette for this music genre: {genre}, mood: {mood}.
Return 4 RGB colors in float format (0.0 to 1.0) ordered from darkest (background/shadow) to lightest (highlight).

Respond ONLY with valid JSON:
{{
  "name": "Palette Name",
  "color1": [0.05, 0.02, 0.12],
  "color2": [0.45, 0.10, 0.55],
  "color3": [0.05, 0.85, 0.90],
  "color4": [0.98, 0.95, 0.98]
}}"""
        try:
            raw_text = self.generator.call_llm(prompt=prompt, system_prompt="Output ONLY valid JSON.", json_mode=True, timeout=45)
            raw_text = re.sub(r'<think>[\s\S]*?<\/think>', '', raw_text, flags=re.IGNORECASE).strip()
            data = json.loads(raw_text)
            return data
        except Exception as e:
            logger.warning(f"生成原創調色盤失敗: {e}")
            return {
                "name": "Cyber Neon Fallback",
                "color1": [0.05, 0.02, 0.12],
                "color2": [0.92, 0.05, 0.55],
                "color3": [0.05, 0.92, 0.85],
                "color4": [0.98, 0.95, 0.98]
            }

    def generate_director_tags(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """ 為像素模組生成 Visual DNA 與曲式章節適合度評分 """
        style_idx = config_data.get("style_idx", 2)
        pal_idx = config_data.get("palette_idx", 0)
        gain = config_data.get("audio_gain", 1.0)

        scores = {"intro": 0.5, "verse": 0.6, "buildup": 0.7, "drop": 0.8, "outro": 0.5}
        
        if style_idx in [8, 9, 10, 12]:
            scores["drop"] = 0.95
            scores["buildup"] = 0.85
            scores["intro"] = 0.3
        elif style_idx in [1, 2, 4, 5]:
            scores["verse"] = 0.9
            scores["intro"] = 0.7
            scores["outro"] = 0.7
        elif style_idx in [6, 14, 3]:
            scores["intro"] = 0.85
            scores["outro"] = 0.8

        dna = {
            "geometry": {"type": "pixel_shader", "topology": f"StyleMode_{style_idx}"},
            "audio_binding": {
                "bass": {"target": "grid_distortion", "multiplier": gain},
                "mid": {"target": "dither_threshold", "multiplier": gain},
                "high": {"target": "chromatic_glitch", "multiplier": gain}
            },
            "section_fitness": scores
        }
        return dna
