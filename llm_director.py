# -*- coding: utf-8 -*-
"""
SENTINEL: Cognitive Adaptive Cinematography Director (CACD 2.0)
雙層 AI 電影作者導演系統 (Auteur Director Engine)
- L1 宏觀大腦: 
  - 30ms 確定性專家作者樹 (Auteur Matrix Tree: 劇作原型、四幕辯證變奏、OKLCH色彩劇力曲線)
  - 4.5秒硬超時雙軌競爭機制 (Competitive Dual-Track with Hard Timeout & 0-latency Fallback)
- L2 微觀動態編舞器 (DirectorChoreographer):
  - Walter Murch 六法則情感連續性評估 (Emotion 51%)
  - 零顯存時間軸微移 J/L-Cut (Temporal Offset Nudge: 提前 150~350ms 弱拍切分)
  - 彈道生理阻尼濾波調變 (u_tension, u_chaos, u_sublime)
- 素材生態 (BanditInventorySelector & SemanticSoftProjector):
  - 語義心靈約束 + UCB 冷門與修復資產優先首秀
  - 全局香農熵動態帶寬控制 (2.6 <= H <= 3.6)
"""

import os
import re
import json
import logging
import time
import math
from typing import List, Dict, Any, Optional, Tuple
import urllib.request
import urllib.error

try:
    import requests
except ImportError:
    requests = None

from bandit_inventory_selector import BanditInventorySelector
from director_choreographer import DirectorChoreographer
from semantic_soft_projector import SemanticSoftProjector
from surreal_director_bridge import SurrealCognitiveDirectorBridge

logger = logging.getLogger("StandaloneInjector.LLMDirector")

# 四大心靈劇作母題
AUTEUR_THEMES = [
    {
        "id": "promethean_catharsis",
        "title": "普羅米修斯的救贖 (Promethean Catharsis)",
        "motif": "火種、神經元網格與自性重構",
        "progression": ["疏離囚籠 (Thesis)", "對抗掙扎 (Antithesis)", "毀滅臨界 (Crisis)", "意識覺醒與昇華 (Synthesis)"],
        "color_arc": "深冷靛藍 (240°) ➔ 警示琥珀 (45°) ➔ 爆裂洋紅 (320°) ➔ 熾白日光 (90°)",
        "ideal_valence_range": (-0.8, 0.6),
        "ideal_arousal_min": 0.55
    },
    {
        "id": "cosmic_awe_self_realization",
        "title": "宇宙敬畏與自性顯現 (Cosmic Awe & Self-Realization)",
        "motif": "星系漩渦、微觀粒子與曼陀羅",
        "progression": ["無盡虛空 (Thesis)", "重力吸積 (Antithesis)", "量子奇異點 (Crisis)", "天體合一 (Synthesis)"],
        "color_arc": "純黑虛無 (0°) ➔ 幽靈青綠 (180°) ➔ 冰封紫羅蘭 (270°) ➔ 純金耀斑 (80°)",
        "ideal_valence_range": (-0.2, 0.9),
        "ideal_arousal_min": 0.35
    },
    {
        "id": "cybernetic_paranoia",
        "title": "賽博異化與失控協議 (Cybernetic Paranoia)",
        "motif": "晶體破裂、時間齒輪與雜訊噪點",
        "progression": ["冰冷秩序 (Thesis)", "雜訊入侵 (Antithesis)", "系統過載 (Crisis)", "數位廢墟 (Synthesis)"],
        "color_arc": "單色單調 (0°) ➔ 劇毒螢光綠 (130°) ➔ 暴烈電光青 (195°) ➔ 灰燼殘彩 (0°)",
        "ideal_valence_range": (-1.0, 0.1),
        "ideal_arousal_min": 0.65
    },
    {
        "id": "hypnotic_zen_dissolution",
        "title": "禪意催眠與熵增消解 (Hypnotic Zen Dissolution)",
        "motif": "呼吸流體、波形干涉與自相似分形",
        "progression": ["寧靜水面 (Thesis)", "脈動漣漪 (Antithesis)", "意識漫散 (Crisis)", "無我消融 (Synthesis)"],
        "color_arc": "莫蘭迪灰藍 (220°) ➔ 溫潤玉綠 (150°) ➔ 暮色薄紫 (280°) ➔ 晨曦微光 (60°)",
        "ideal_valence_range": (-0.4, 0.7),
        "ideal_arousal_min": 0.10
    }
]

class LLMDirectorAgent:
    """
    SOTA 雙層電影作者導演管線
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

    def get_ollama_status(self) -> Dict[str, Any]:
        """ 快速探測本地 LLM 狀態 (超時 1 秒) """
        try:
            req = urllib.request.Request(self.tags_url)
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    active_model = self.default_model if self.default_model in models else (models[0] if models else "")
                    return {"status": "ready", "model": active_model, "available": models}
        except Exception:
            pass
        return {"status": "offline", "model": self.default_model, "available": []}

    def generate_director_script(
        self, 
        audio_telemetry: Dict[str, Any], 
        available_modules: List[Dict[str, Any]], 
        recent_used_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        SOTA 雙軌電影作者決策流程：
        1. 30ms 確定性專家作者樹 (Auteur Matrix Tree) 即時產出高品質劇作草案 (零等待保證)
        2. 透過 Contextual Bandit 完成初始模組分配 (語義約束 + UCB 冷門與修復優先)
        3. 若本地 LLM 可用，發起 4.5 秒硬超時競爭查詢，融合同化高階哲學描述
        4. 由 L2 DirectorChoreographer 完成微觀動態編舞 (Murch 51% 心靈對齊、J/L-Cut 錯位、彈道阻尼)
        """
        storyboard_sections = audio_telemetry.get("storyboard", [])
        if not storyboard_sections:
            storyboard_sections = [
                {"section": "Intro", "duration": 15.0},
                {"section": "Verse", "duration": 30.0},
                {"section": "Build-up", "duration": 15.0},
                {"section": "Drop", "duration": 30.0},
                {"section": "Outro", "duration": 15.0}
            ]

        # 1. 30ms 確定性專家作者大腦決策
        auteur_theme = self._resolve_auteur_theme(audio_telemetry)
        
        # 2. 構建歷史次數字典
        recent_set = set(recent_used_keys or [])
        historical_counts = {}
        for m in available_modules:
            k = m.get("_filename_key") or m.get("name")
            used = int(m.get("used_count", 0))
            if k in recent_set:
                used += 2
            historical_counts[k] = used

        # 3. 語義約束 + UCB 冷門優先 Bandit 選模組
        bandit_assignments = self.bandit.select_modules_for_storyboard(
            storyboard_sections=storyboard_sections,
            available_modules=available_modules,
            audio_telemetry=audio_telemetry,
            historical_used_counts=historical_counts
        )

        # 4. 探測 LLM 競爭雙軌 (4.5 秒硬上限)
        ollama_status = self.get_ollama_status()
        llm_enhanced_meta = None

        if ollama_status["status"] == "ready":
            try:
                llm_enhanced_meta = self._query_llm_with_timeout(
                    audio_telemetry=audio_telemetry,
                    bandit_assignments=bandit_assignments,
                    auteur_theme=auteur_theme,
                    model_name=ollama_status["model"],
                    timeout_sec=4.5
                )
            except Exception as e:
                logger.warning(f"⚠️ LLM 查詢超時或異常 ({str(e)})，0 延遲無縫採納確定性專家作者大腦。")

        # 5. 微觀動態編舞 (L2 Choreographer)
        shot_list, intensity_curve = self.choreographer.plan_cinematic_shots(
            storyboard_sections=storyboard_sections,
            audio_telemetry=audio_telemetry,
            assigned_modules=bandit_assignments
        )

        # 6. 整合母題與四幕辯證標籤
        num_shots = len(shot_list)
        for i, shot in enumerate(shot_list):
            # 依時間比例指派四幕辯證階段
            progress = i / max(1, num_shots - 1)
            stage_idx = min(3, int(progress * 4))
            shot["dialectical_stage"] = auteur_theme["progression"][stage_idx]
            shot["symbolic_motif"] = auteur_theme["motif"]

        theme_title = llm_enhanced_meta.get("theme_title") if llm_enhanced_meta else auteur_theme["title"]
        director_statement = llm_enhanced_meta.get("director_statement") if llm_enhanced_meta else (
            f"電影作者劇本：圍繞「{auteur_theme['motif']}」母題，落地四幕辯證演進與 Walter Murch 情感切分。"
        )

        return {
            "theme_title": theme_title,
            "soul_theme": auteur_theme["id"],
            "symbolic_motif": auteur_theme["motif"],
            "chromatic_narrative": auteur_theme["color_arc"],
            "color_palette_mood": auteur_theme["color_arc"],
            "director_statement": director_statement,
            "shot_list": shot_list,
            "intensity_curve": intensity_curve or [0.3, 0.5, 0.9, 0.4]
        }

    def _resolve_auteur_theme(self, audio_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """ 30ms 確定性專家作者樹：根據音樂 Valence/Arousal/Tension 映射最佳心靈劇作母題 """
        genre_tel = audio_telemetry.get('genre_telemetry', {})
        valence = float(audio_telemetry.get('valence', genre_tel.get('valence', 0.0)))
        arousal = float(audio_telemetry.get('arousal', genre_tel.get('arousal', 0.5)))
        genre = str(audio_telemetry.get('genre', 'Electronic')).lower()

        if "ambient" in genre or "chill" in genre or arousal < 0.35:
            return AUTEUR_THEMES[3] # 禪意催眠與熵增消解
        elif "cyber" in genre or "glitch" in genre or (valence < -0.3 and arousal > 0.6):
            return AUTEUR_THEMES[2] # 賽博異化與失控協議
        elif valence >= 0.2:
            return AUTEUR_THEMES[1] # 宇宙敬畏與自性顯現
        else:
            return AUTEUR_THEMES[0] # 普羅米修斯的救贖

    def _query_llm_with_timeout(
        self,
        audio_telemetry: Dict[str, Any],
        bandit_assignments: List[Dict[str, Any]],
        auteur_theme: Dict[str, Any],
        model_name: str,
        timeout_sec: float = 4.5
    ) -> Optional[Dict[str, Any]]:
        """ 4.5 秒硬超時約束查詢，防止卡死 UI """
        prompt = f"""You are a master 4K Music Video Film Director following Walter Murch's Rule of Six.
Music Affect: Genre={audio_telemetry.get('genre')}, BPM={audio_telemetry.get('bpm')}.
Auteur Theme: {auteur_theme['title']} (Motif: {auteur_theme['motif']}).

Output strictly valid JSON with no markdown:
{{
  "theme_title": "Short poetic title (max 6 words)",
  "director_statement": "Concise auteur vision statement explaining the psychological journey"
}}"""

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            raw_response = data.get("response", "{}")
            return json.loads(raw_response)

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
