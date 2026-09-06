import os
import re
import json
import logging
import shutil
import subprocess
import time
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error

try:
    import requests
except ImportError:
    requests = None

try:
    import numpy as np
except ImportError:
    np = None

from surreal_director_bridge import SurrealCognitiveDirectorBridge
from bandit_inventory_selector import BanditInventorySelector
from saliency_eyetrace_bridge import SaliencyEyeTraceBridge
from director_choreographer import DirectorChoreographer

logger = logging.getLogger("StandaloneInjector.LLMDirector")

class LLMDirectorAgent:
    """
    4K MV 視覺整合雙層智慧導演系統 (CACD: Cognitive Adaptive Cinematography Director)
    - L1 宏觀大腦 (Local LLM via Ollama): 策展全曲世界觀、12音 HSL 色彩光譜演進與哲學隱喻
    - L2 微觀動態編舞器 (DirectorChoreographer): 落地 Walter Murch 六法則、J/L-Cut 錯位、視線引導 (Eye-Trace)
    - 素材生態 (BanditInventorySelector): 情境多臂老虎機與審美香農熵衰減，打破少數模組壟斷
    - 毫秒級確定性專家回退保障 (Fail-safe Heuristic Engine)
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
        self.bandit = BanditInventorySelector()
        self.choreographer = DirectorChoreographer()
        self._last_ollama_check = 0.0
        self._ollama_available = False

    def _http_get(self, url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """ 具備 requests 與 urllib 雙重降級的 HTTP GET 請求 """
        if requests:
            try:
                res = requests.get(url, timeout=timeout)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                return None
        else:
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode('utf-8'))
            except Exception:
                return None
        return None

    def _http_post(self, url: str, json_data: Dict[str, Any], timeout: float = 18.0) -> Optional[Dict[str, Any]]:
        """ 具備 requests 與 urllib 雙重降級的 HTTP POST 請求 """
        if requests:
            try:
                res = requests.post(url, json=json_data, timeout=timeout)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                return None
        else:
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(json_data).encode('utf-8'),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return json.loads(resp.read().decode('utf-8'))
            except Exception:
                return None
        return None

    def ensure_ollama_running(self) -> bool:
        """ 檢查並自動於背景啟動 Ollama 本地服務 (具備冷卻快取避免阻塞) """
        now = time.time()
        if (now - self._last_ollama_check) < 45.0:
            return self._ollama_available

        self._last_ollama_check = now

        # 極速探測在線狀態 (300ms 逾時)
        if self._http_get(self.tags_url, timeout=0.3) is not None:
            self._ollama_available = True
            return True

        ollama_bin = shutil.which("ollama") or ("/usr/local/bin/ollama" if os.path.exists("/usr/local/bin/ollama") else None)
        if not ollama_bin:
            self._ollama_available = False
            return False

        try:
            subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(2):
                time.sleep(0.2)
                if self._http_get(self.tags_url, timeout=0.2) is not None:
                    logger.info("Ollama 本地服務背景喚醒成功！")
                    self._ollama_available = True
                    return True
        except Exception:
            pass

        self._ollama_available = False
        return False

    def get_ollama_status(self) -> Dict[str, Any]:
        """ 探測 Ollama 服務狀態與可用模型 """
        self.ensure_ollama_running()
        try:
            data = self._http_get(self.tags_url, timeout=2.0)
            if data is not None:
                models_data = data.get("models", [])
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
        雙層導演決策流水線：
        1. 透過 BanditInventorySelector 預先評估與規劃模組多樣性與審美熵
        2. 若本地 LLM 可用，由 L1 宏觀模型賦予全曲世界觀敘事與電影概念
        3. 由 L2 DirectorChoreographer 進行微觀動態編舞 (Walter Murch 六法則、J/L-Cut、視線質心連續性)
        """
        storyboard_sections = audio_telemetry.get("storyboard", [])
        if not storyboard_sections:
            # 建立預設分鏡結構
            storyboard_sections = [
                {"section": "Intro", "duration": 15.0},
                {"section": "Verse", "duration": 30.0},
                {"section": "Build-up", "duration": 15.0},
                {"section": "Drop", "duration": 30.0},
                {"section": "Outro", "duration": 15.0}
            ]

        # 1. 建立歷史使用次數字典
        recent_set = set(recent_used_keys or [])
        historical_counts = {}
        for m in available_modules:
            k = m.get("_filename_key") or m.get("name")
            used = int(m.get("used_count", 0))
            if k in recent_set:
                used += 2
            historical_counts[k] = used

        # 2. 透過 Contextual Bandit 完成初始模組分配推薦
        bandit_assignments = self.bandit.select_modules_for_storyboard(
            storyboard_sections=storyboard_sections,
            available_modules=available_modules,
            audio_telemetry=audio_telemetry,
            historical_used_counts=historical_counts
        )

        status = self.get_ollama_status()
        if status["status"] != "ready":
            logger.info("⚡ 本地 LLM 處於離線狀態，啟用 L2 專家級確定性導演引擎 (<50ms)...")
            return self._fallback_heuristic_script(audio_telemetry, available_modules, bandit_assignments)

        model_name = status["model"]
        
        # 3. 構造向 L1 宏觀導演查詢的高階 Prompt
        modules_summary = []
        for b_item in bandit_assignments[:35]:
            modules_summary.append({
                "id": b_item["assigned_module_id"],
                "name": b_item["module_name"],
                "target_section": b_item["section_name"],
                "bandit_score": b_item["bandit_score"]
            })

        system_prompt = (
            "You are an avant-garde 4K Music Video Director and Creative Technologist following Walter Murch's Rule of Six. "
            "Direct visual narratives for electronic, techno, synthwave, and ambient music videos. "
            "Output STRICT JSON without conversational text or markdown formatting."
        )

        user_prompt = f"""Analyze this music telemetry and direct a cohesive 4K Music Video:
[Track Telemetry]
- Genre: {audio_telemetry.get('genre', 'Techno')}
- BPM: {audio_telemetry.get('bpm', 120):.1f}
- Key: {audio_telemetry.get('key', 'Unknown')}
- Storyboard: {[s.get('section') for s in storyboard_sections]}

[Contextual Bandit Pre-Allocated Module Recommendations]
{json.dumps(modules_summary, ensure_ascii=False)}

[Director Directives]
1. Define a high-concept aesthetic theme title & color mood palette.
2. Formulate a 1-2 sentence director artistic statement.
3. For each section, refine the assigned module ID, specify camera framing ('fill' for peak impact or 'contain' for counterpoint), and post-fx intensity (0.1 to 1.0).

[Required JSON Format]
{{
  "theme_title": "string",
  "color_palette_mood": "string",
  "director_statement": "string",
  "shot_list": [
    {{
      "section_index": 0,
      "section_name": "Intro",
      "assigned_module_id": "module_id",
      "framing_mode": "contain",
      "transition_style": "luma_wipe",
      "target_fx_intensity": 0.3
    }}
  ],
  "intensity_curve": [0.3, 0.5, 0.9, 0.4]
}}
"""

        try:
            full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}\n<|assistant|>"
            resp_data = self._http_post(
                f"{self.host}/api/generate",
                json_data={
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
            if resp_data is not None:
                raw_response = resp_data.get("response", "")
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
                    # 透過 L2 編舞器補全視線引導、J/L-Cut 與 Walter Murch 剪輯指標
                    enriched_shots, intensity_curve = self.choreographer.plan_cinematic_shots(
                        storyboard_sections=storyboard_sections,
                        audio_telemetry=audio_telemetry,
                        assigned_modules=result["shot_list"]
                    )
                    result["shot_list"] = enriched_shots
                    result["intensity_curve"] = intensity_curve
                    logger.info(f"✨ 成功透過本地 LLM ({model_name}) + L2 編舞器生成高階導演劇本: 「{result.get('theme_title')}」")
                    return result
        except Exception as e:
            logger.warning(f"LLM 宏觀生成超時或解析失敗 ({e})，平滑轉入 L2 確定性編舞引擎...")

        return self._fallback_heuristic_script(audio_telemetry, available_modules, bandit_assignments)

    def _fallback_heuristic_script(
        self, 
        audio_telemetry: Dict[str, Any], 
        available_modules: List[Dict[str, Any]], 
        pre_assigned: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        L2 專家級確定性回退機制：
        結合 Bandit 庫存探索、SAVAP 超現實概念策展、視線引導與 Walter Murch 六法則編舞
        在 < 50ms 內瞬間完成專業級電影劇本生成
        """
        storyboard = audio_telemetry.get("storyboard", [])
        if not storyboard:
            storyboard = [
                {"section": "Intro", "duration": 15.0},
                {"section": "Verse", "duration": 30.0},
                {"section": "Build-up", "duration": 15.0},
                {"section": "Drop", "duration": 30.0},
                {"section": "Outro", "duration": 15.0}
            ]

        genre = audio_telemetry.get("genre", "Electronic")
        
        # 若無預先指派，由 Bandit 即時求解
        if not pre_assigned:
            pre_assigned = self.bandit.select_modules_for_storyboard(
                storyboard_sections=storyboard,
                available_modules=available_modules,
                audio_telemetry=audio_telemetry
            )

        # L2 微觀動態編舞規劃
        shot_list, intensity_curve = self.choreographer.plan_cinematic_shots(
            storyboard_sections=storyboard,
            audio_telemetry=audio_telemetry,
            assigned_modules=pre_assigned
        )

        # 融入 SAVAP 超現實導演美學元數據
        for shot in shot_list:
            sec_name = shot["section_name"]
            surreal_meta = SurrealCognitiveDirectorBridge.evaluate_and_curate_surreal_scene(
                sec_name, audio_telemetry, num_elements=5
            )
            shot["surreal_topology"] = surreal_meta.get("topology_mode", "orbital")
            shot["curated_theme"] = surreal_meta.get("theme_title", "Procedural Universe")
            shot["aesthetic_score"] = surreal_meta.get("aesthetic_score", 0.85)

        first_shot_theme = shot_list[0].get("curated_theme", "Procedural Metamorphosis")

        return {
            "theme_title": f"{genre} · {first_shot_theme}",
            "color_palette_mood": "Deep OKLCH / Dynamic Phase Harmony",
            "director_statement": "L2 雙層確定性編舞劇本：依據 Walter Murch 六法則、J/L-Cut 錯位剪輯與視線連續性精準排片。",
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
            scale_factor = float(max(0.15, min(1.0, adjusted_budget / current_cost)))
            return {k: float(v * scale_factor) for k, v in active_fx_dict.items()}
        return active_fx_dict
