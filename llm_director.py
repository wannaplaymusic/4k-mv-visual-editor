import os
import re
import json
import logging
import shutil
import subprocess
import time
import requests
import numpy as np
from typing import List, Dict, Any, Optional

logger = logging.getLogger("StandaloneInjector.LLMDirector")

class LLMDirectorAgent:
    """
    4K MV 視覺整合智慧導演 Agent (Llama3 / DeepSeek-R1 via Ollama)
    - 傳入音樂遙測數據與模組庫存 DNA，由本地 LLM 撰寫全曲分鏡劇本與世界觀
    - 生成各段落專屬視覺模組指派、構圖模式 (fill/contain) 與動態後製強度曲線 (intensity_curve)
    - 具備防重複疲勞衰減與全自動專家規則回退 (Fallback) 機制
    """

    def __init__(
        self, 
        host: str = "http://localhost:11434", 
        default_model: str = "llama3", 
        model_name: Optional[str] = None, 
        api_url: Optional[str] = None
    ):
        if api_url:
            self.host = api_url.rsplit('/', 1)[0]
        else:
            self.host = host.rstrip("/")
        self.api_url = f"{self.host}/api/generate"
        self.tags_url = f"{self.host}/api/tags"
        self.default_model = model_name or default_model
        self.model_name = self.default_model

    def ensure_ollama_running(self) -> bool:
        """ 檢查並自動於背景啟動 Ollama 本地服務 """
        try:
            res = requests.get(self.tags_url, timeout=1.2)
            if res.status_code == 200:
                return True
        except Exception:
            pass

        ollama_bin = shutil.which("ollama") or ("/usr/local/bin/ollama" if os.path.exists("/usr/local/bin/ollama") else None)
        if not ollama_bin:
            logger.info("本機未偵測到 Ollama 執行檔，將啟用專家規則導播引擎。")
            return False

        try:
            logger.info(f"正在背景拉起 Ollama 服務進程 ({ollama_bin})...")
            subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(6):
                time.sleep(0.5)
                try:
                    res = requests.get(self.tags_url, timeout=1.0)
                    if res.status_code == 200:
                        logger.info("Ollama 本地服務背景喚醒成功！")
                        return True
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"自動啟動 Ollama 失敗: {e}")
        return False

    def get_ollama_status(self) -> Dict[str, Any]:
        """ 探測 Ollama 服務狀態與可用模型 """
        self.ensure_ollama_running()
        try:
            resp = requests.get(self.tags_url, timeout=2.0)
            if resp.status_code == 200:
                models_data = resp.json().get("models", [])
                models = [m.get("name", "") for m in models_data]
                
                # 優先選取常用導演模型
                active_model = self.default_model
                found = False
                for candidate in ["llama3:latest", "llama3", "deepseek-r1:8b", "deepseek-r1:latest", "deepseek-r1", "mistral"]:
                    if any(candidate == m or candidate in m for m in models):
                        active_model = candidate
                        found = True
                        break
                if not found and models:
                    active_model = models[0]

                return {
                    "status": "ready",
                    "message": f"AI 導演引擎就緒 ({active_model})",
                    "model": active_model,
                    "available": models
                }
            return {"status": "offline", "message": "Ollama 服務無回應", "model": self.default_model, "available": []}
        except Exception as e:
            return {"status": "offline", "message": f"AI 引擎離線 ({str(e)})", "model": self.default_model, "available": []}

    def generate_director_script(
        self, 
        audio_telemetry: Dict[str, Any], 
        available_modules: List[Dict[str, Any]], 
        recent_used_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        傳入音訊特徵與可用模組庫存，由本地 LLM 撰寫分鏡劇本、美學世界觀與後製調製曲線
        """
        status = self.get_ollama_status()
        if status["status"] != "ready":
            logger.warning("Local LLM not available. Fallback to expert heuristics.")
            return self._fallback_heuristic_script(audio_telemetry, available_modules, recent_used_keys)

        model_name = status["model"]
        
        # 1. 嚴格階梯化篩選最少使用次數的候選池 (優先曝光 0 次與最低次數模組)
        import random
        sorted_modules = sorted(
            available_modules, 
            key=lambda m: (int(m.get("used_count", 0)), int(m.get("_history_used", 0)) if isinstance(m.get("_history_used"), (int, float)) else 0)
        )
        
        min_used = int(sorted_modules[0].get("used_count", 0)) if sorted_modules else 0
        # 取得最低使用次數階梯 (例如 0次 與 1次)
        tier_pool = [m for m in sorted_modules if int(m.get("used_count", 0)) <= min_used + 1]
        if len(tier_pool) < 40:
            tier_pool = sorted_modules[:60]
            
        # 在最低階梯內隨機均勻打散，確保每批次曝光不同模組
        random.shuffle(tier_pool)
        candidate_selection = tier_pool[:45]

        modules_summary = []
        recent_set = set(recent_used_keys or [])
        for m in candidate_selection:
            m_key = m.get("_filename_key") or m.get("name")
            modules_summary.append({
                "id": m_key,
                "name": m.get("name"),
                "tags": m.get("tags", [])[:5],
                "used_count": int(m.get("used_count", 0)),
                "energy_weight": m.get("storyboard_weight", 50),
                "is_original": m.get("license") == "Original" or "AI Incubator" in str(m.get("author", "")),
                "fatigued": m_key in recent_set or int(m.get("used_count", 0)) > 1
            })

        storyboard_sections = audio_telemetry.get("storyboard", [])
        
        # 2. 構造高維導演 Prompt
        system_prompt = (
            "You are an avant-garde 4K Music Video Director and Creative Technologist. "
            "You direct visual narratives for electronic, techno, synthwave, ambient and rock music videos using modular visual shaders. "
            "Always output STRICT JSON without any conversational text or markdown explanation."
        )

        user_prompt = f"""Analyze this music track telemetry and direct a cohesive 4K Music Video:
[Track Telemetry]
- Genre: {audio_telemetry.get('genre', 'Techno')}
- BPM: {audio_telemetry.get('bpm', 120):.1f}
- Key/Harmonics: {audio_telemetry.get('key', 'Unknown')}
- Total Duration: {audio_telemetry.get('duration', 180):.1f}s
- Storyboard Sections: {[s.get('section') for s in storyboard_sections]}

[Available Visual Modules in Library (Tier: Least Used Priority)]
{json.dumps(modules_summary, ensure_ascii=False)}

[Director Guidelines]
1. Select one cohesive aesthetic visual theme (e.g. Cyberpunk Noir, Deep Ocean Ambient, Acid Glitch, Industrial Minimal, Retro 8-bit Neon).
2. For each section, select the most fitting module ID from the Available Library. Give strong priority to lowest 'used_count' and 'is_original: true', and avoid 'fatigued: true'.
3. Assign a camera framing mode for each section: 'fill' (90% for high tension / drop), or 'contain' (calm / intro).
4. Provide a continuous dynamic post-fx intensity curve (0.0 to 1.0) matching each section tension.

[Required JSON Format]
{{
  "theme_title": "string (e.g., Tokyo Neon Horizon)",
  "color_palette_mood": "string (e.g., Cold Cyan / Deep Violet)",
  "director_statement": "string (1-2 sentences on creative concept)",
  "shot_list": [
    {{
      "section_index": 0,
      "section_name": "Intro",
      "assigned_module_id": "module_id_from_library",
      "framing_mode": "fill",
      "transition_style": "luma_wipe",
      "target_fx_intensity": 0.3
    }}
  ],
  "intensity_curve": [0.3, 0.5, 0.9, 0.4]
}}
"""

        try:
            full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}\n<|assistant|>"
            resp = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.35,
                        "num_predict": 1200
                    }
                },
                timeout=18.0
            )
            if resp.status_code == 200:
                raw_response = resp.json().get("response", "")
                cleaned_text = raw_response.strip()
                if "```json" in cleaned_text:
                    cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned_text:
                    cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
                else:
                    brace_match = re.search(r'\{[\s\S]*\}', cleaned_text)
                    if brace_match:
                        cleaned_text = brace_match.group(0)
                
                result = json.loads(cleaned_text)
                if "shot_list" in result and len(result["shot_list"]) > 0:
                    logger.info(f"✨ 成功透過本地 LLM ({model_name}) 生成導演劇本: 主題「{result.get('theme_title')}」")
                    return result
        except Exception as e:
            logger.warning(f"LLM generation failed ({e}), switching to expert heuristics...")

        return self._fallback_heuristic_script(audio_telemetry, available_modules, recent_used_keys)

    def _fallback_heuristic_script(
        self, 
        audio_telemetry: Dict[str, Any], 
        available_modules: List[Dict[str, Any]], 
        recent_used_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """ 啟發式專家規則回退機制 (嚴格最低使用次數優先，全曲去重) """
        import random
        storyboard = audio_telemetry.get("storyboard", [])
        shot_list = []
        intensity_curve = []
        recent_set = set(recent_used_keys or [])
        
        # 嚴格按使用次數升序排序
        sorted_mods = sorted(
            available_modules, 
            key=lambda m: (int(m.get("used_count", 0)), 1 if (m.get("_filename_key") or m.get("name")) in recent_set else 0, random.random())
        )
        
        fallback_keys = [
            m.get("_filename_key") or m.get("name") 
            for m in sorted_mods 
            if (m.get("_filename_key") or m.get("name")) not in recent_set
        ]
        if not fallback_keys:
            fallback_keys = [m.get("_filename_key") or m.get("name") for m in sorted_mods]
        if not fallback_keys:
            fallback_keys = ["pixel_synth_default"]

        genre = audio_telemetry.get("genre", "Electronic")

        # 為了確保同一首歌各分鏡不重複，從最少使用的模組中依序分配獨特模組
        used_in_this_mv = set()
        for idx, sec in enumerate(storyboard):
            sec_name = sec.get("section", "Verse")
            
            assigned_id = None
            for k in fallback_keys:
                if k not in used_in_this_mv:
                    assigned_id = k
                    used_in_this_mv.add(k)
                    break
            if not assigned_id:
                assigned_id = fallback_keys[idx % len(fallback_keys)]
            
            intensity = 0.92 if sec_name in ["Drop", "Chorus"] else (0.70 if sec_name == "Build-up" else (0.45 if sec_name == "Verse" else 0.25))
            shot_list.append({
                "section_index": idx,
                "section_name": sec_name,
                "assigned_module_id": assigned_id,
                "framing_mode": "contain" if sec_name in ["Intro", "Outro"] else "fill",
                "transition_style": "glitch" if sec_name == "Drop" else "luma_wipe",
                "target_fx_intensity": intensity
            })
            intensity_curve.append(intensity)

        return {
            "theme_title": f"{genre} Procedural Symphony",
            "color_palette_mood": "Cyber Neon / Analog Grain",
            "director_statement": "專家啟發式回退劇本：依據頻譜能量包絡與樂段張力自主排片。",
            "shot_list": shot_list,
            "intensity_curve": intensity_curve or [0.3, 0.5, 0.9, 0.4]
        }

    def generate_shot_list(self, song_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """ 向後相容接口 """
        script = self.generate_director_script(song_telemetry, [])
        return {
            "aesthetic_theme": script.get("theme_title", "CyberGlitch"),
            "signature_fx": ["bayer_dither", "crt_scanline", "chromatic_aberration"],
            "color_mood": script.get("color_palette_mood", "Cyberpunk Neon"),
            "camera_framing": ["WIDE_ENV", "MEDIUM_MAIN", "MACRO_DETAIL", "WHIP_PAN_GLITCH", "ZOOM_BURST"],
            "intensity_curve": script.get("intensity_curve", [0.3, 0.5, 0.9, 0.6, 0.3]),
            "fullscreen_fit_mode": "fill"
        }

    def rank_presets_for_director(
        self, 
        presets_list: List[Dict[str, Any]], 
        target_section: str = "verse",
        track_dna: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        scored_presets = []
        target_section_lower = target_section.lower()

        for preset in presets_list:
            score = 50.0
            provenance = preset.get("provenance", {})
            license_mode = str(preset.get("license_mode", ""))
            author = str(preset.get("author", ""))
            if (isinstance(provenance, dict) and provenance.get("origin") == "ai_incubator") or license_mode == "Original" or "AI Incubator" in author:
                score += 25.0
                
            director_tags = preset.get("director_tags", {})
            if isinstance(director_tags, dict):
                section_fit = director_tags.get("section_fitness") or director_tags.get("section_scores") or {}
                if isinstance(section_fit, dict) and target_section_lower in section_fit:
                    try:
                        score += float(section_fit.get(target_section_lower, 0.5)) * 20.0
                    except (ValueError, TypeError):
                        pass

            used_count = preset.get("used_count", 0)
            # 嚴格階梯扣分：已使用過模組大幅扣分 (每次使用 -50分)，確保 0次/低次數模組絕對優先
            if isinstance(used_count, (int, float)) and used_count > 0:
                score -= (used_count * 50.0)
                
            scored_presets.append((score, preset))
            
        scored_presets.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_presets]

class VIRController:
    def __init__(self, vir_budget: float = 1.0, target_fps: float = 60.0):
        self.vir_budget = vir_budget
        self.target_fps = target_fps
        self.ideal_frame_time_ms = 1000.0 / target_fps

    def clamp_fx_intensities(
        self, 
        active_fx_dict: Dict[str, float], 
        current_entropy: float = 0.5, 
        last_frame_time_ms: float = 16.0
    ) -> Dict[str, float]:
        fps_penalty = max(1.0, last_frame_time_ms / self.ideal_frame_time_ms)
        adjusted_budget = self.vir_budget / fps_penalty
        current_cost = (current_entropy * 0.35) + (sum(active_fx_dict.values()) * 0.65)
        
        if current_cost > adjusted_budget and current_cost > 0.001:
            scale_factor = float(np.clip(adjusted_budget / current_cost, 0.15, 1.0))
            return {k: float(v * scale_factor) for k, v in active_fx_dict.items()}
        return active_fx_dict
