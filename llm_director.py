import json
import logging
import requests

logger = logging.getLogger("StandaloneInjector.LLMDirector")

class LLMDirectorAgent:
    def __init__(self, api_url="http://localhost:11434/api/generate", model_name="llama3"):
        self.api_url = api_url
        self.model_name = model_name

    def generate_shot_list(self, song_telemetry: dict) -> dict:
        """ 生成導演劇本 JSON """
        prompt = f"""
        You are a world-class MV Director. Generate a JSON shot list for this track:
        Title: {song_telemetry.get('title', 'Untitled')}
        BPM: {song_telemetry.get('bpm', 120)}
        Genre: {song_telemetry.get('genre', 'electronic')}
        Sections: {json.dumps(song_telemetry.get('storyboard', []))}

        Return ONLY a JSON dictionary specifying:
        1. "aesthetic_theme" (CyberGlitch, RetroAnalog, DreamyArtistic, Psychedelic, or DigitalPixel)
        2. "signature_fx" (List 3 distinct FX keys)
        3. "color_mood" (Description)
        """
        try:
            response = requests.post(self.api_url, json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }, timeout=5)
            if response.status_code == 200:
                return json.loads(response.json()["response"])
        except Exception as e:
            logger.info(f"LLM API unavailable ({e}), fallback rule-based script generated.")

        # Heuristic Rule-Based Fallback Shot List
        genre = str(song_telemetry.get('genre', 'electronic')).lower()
        if 'techno' in genre or 'cyber' in genre:
            theme = "CyberGlitch"
            fx = ["data_mosh", "pixel_sort", "scanline_glitch"]
        elif 'ambient' in genre or 'chill' in genre:
            theme = "DreamyArtistic"
            fx = ["turing_pattern", "spatial_warping", "color_spectral"]
        else:
            theme = "RetroAnalog"
            fx = ["film_burn", "vector_scope", "lowpass_muffle"]

        return {
            "aesthetic_theme": theme,
            "signature_fx": fx,
            "color_mood": f"Adaptive {theme} palette"
        }


class VIRController:
    def __init__(self, vir_budget: float = 1.0):
        self.vir_budget = vir_budget

    def clamp_fx_intensities(self, active_fx_dict: dict, current_entropy: float) -> dict:
        """ 若總資訊量超出預算，自動鎖定降級非核心特效 """
        current_cost = current_entropy * 0.4 + sum(active_fx_dict.values()) * 0.6
        if current_cost > self.vir_budget and current_cost > 0.001:
            scale_factor = self.vir_budget / current_cost
            return {k: float(v * scale_factor) for k, v in active_fx_dict.items()}
        return active_fx_dict
