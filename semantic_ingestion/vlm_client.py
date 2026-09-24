# -*- coding: utf-8 -*-
"""
SENTINEL: Multimodal VLM Inference Client
支援 Gemini 1.5 Flash (雲端旗艦)、Ollama/vLLM (本地端) 以及確定性數學啟發式回退引擎。
"""

import os
import re
import json
import base64
import logging
import io
from typing import Dict, Any, Optional
from PIL import Image
import urllib.request
import urllib.error

from .models import ExpressiveProfile, ColorAesthetics, SpatiotemporalDynamics

logger = logging.getLogger("StandaloneInjector.VLMClient")

SYSTEM_PROMPT = """你是一位精通榮格深度心理學、電影蒙太奇理論（Walter Murch & Eisenstein）與生成視覺藝術的導演大師。
你面前是一張動態生成藝術模組的 4-in-1 時序田字格截圖（左上: 1s初態, 右上: 3.5s鋪陳, 左下: 8s重拍衝擊, 右下: 15s穩態），以及客觀的色彩與運動物理指標。
請穿透幾何表象，剖析該視覺呈現對人類潛意識的心理衝擊、情緒喚醒度、精神投射與象徵隱喻。
嚴格輸出 JSON 格式，不要包含任何 markdown 標記或解釋性對話：
{
  "primary_psychological_state": "alienation_void | claustrophobic_dread | manic_hyperarousal | hypnotic_trance | sublime_catharsis | nostalgic_decay | existential_awe",
  "secondary_psychological_states": ["標籤1", "標籤2"],
  "symbolic_metaphors": ["隱喻1", "隱喻2", "隱喻3"],
  "narrative_function": "genesis_anchor | tension_accelerator | climax_rupture | aftermath_resonance",
  "jungian_archetype": "the_shadow | the_self | the_void | the_animus | the_trickster",
  "confidence_score": 0.92
}"""

class VLMInferenceClient:
    def __init__(self, api_key: Optional[str] = None, ollama_host: str = "http://localhost:11434"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.ollama_host = ollama_host.rstrip("/")

    def analyze_module(
        self,
        module_id: str,
        collage_img: Image.Image,
        color_feats: Dict[str, Any],
        motion_feats: Dict[str, Any],
        code_snippet: str = ""
    ) -> ExpressiveProfile:
        """
        對模組執行多模態感知分析 (雲端優先 -> 本地次之 -> 數學啟發式兜底)
        """
        # 1. 嘗試 Gemini Flash
        if self.api_key:
            try:
                res = self._call_gemini_flash(module_id, collage_img, color_feats, motion_feats)
                if res:
                    return res
            except Exception as e:
                logger.warning(f"⚠️ Gemini VLM 呼叫失敗 ({str(e)})，嘗試降級...")

        # 2. 嘗試本地 Ollama 視覺模型
        try:
            res = self._call_ollama_vlm(module_id, collage_img, color_feats, motion_feats)
            if res:
                return res
        except Exception:
            pass

        # 3. 確定性啟發式回退引擎 (Level 1 數學+代碼特徵合成)
        return self._heuristic_fallback(module_id, color_feats, motion_feats, code_snippet)

    def _call_gemini_flash(
        self, 
        module_id: str, 
        collage_img: Image.Image, 
        color_feats: Dict[str, Any], 
        motion_feats: Dict[str, Any]
    ) -> Optional[ExpressiveProfile]:
        """ 使用 Gemini 1.5 Flash REST API 進行結構化視覺解讀 """
        buffer = io.BytesIO()
        collage_img.save(buffer, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        prompt_text = f"""模組 ID: {module_id}
客觀物理特徵測量真值:
- OKLCH 主導色相: {color_feats.get('dominant_oklch_hues', [])}
- 色彩對比型態: {color_feats.get('contrast_level', '')}
- 色彩溫度: {color_feats.get('emotional_temperature', '')}
- 平均光流速度: {motion_feats.get('mean_velocity', 0.0)}
- 散度/向心收縮: {motion_feats.get('divergence', 0.0)}
- 運動動能型態: {motion_feats.get('motion_energy_type', '')}

請依據圖像與數據剖析其心靈語義與象徵意義。"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT + "\n\n" + prompt_text},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_b64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.4
            }
        }

        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            candidate = res_data.get("candidates", [])[0]
            raw_text = candidate.get("content", {}).get("parts", [])[0].get("text", "")
            parsed = json.loads(raw_text)

            return ExpressiveProfile(
                module_id=module_id,
                primary_psychological_state=parsed.get("primary_psychological_state", "hypnotic_trance"),
                secondary_psychological_states=parsed.get("secondary_psychological_states", []),
                symbolic_metaphors=parsed.get("symbolic_metaphors", []),
                narrative_function=parsed.get("narrative_function", "tension_accelerator"),
                jungian_archetype=parsed.get("jungian_archetype", "the_self"),
                color_profile=ColorAesthetics(**color_feats),
                dynamics=SpatiotemporalDynamics(**motion_feats),
                hydration_level=2,
                confidence_score=float(parsed.get("confidence_score", 0.9)),
                analyzed_engine="gemini-1.5-flash"
            )

    def _call_ollama_vlm(
        self, module_id: str, collage_img: Image.Image, color_feats: Dict[str, Any], motion_feats: Dict[str, Any]
    ) -> Optional[ExpressiveProfile]:
        """ 呼叫本地 Ollama 多模態模型 (如 minicpm-v, llava, qwen2-vl) """
        buffer = io.BytesIO()
        collage_img.save(buffer, format="JPEG", quality=80)
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        payload = {
            "model": "qwen2-vl",
            "prompt": SYSTEM_PROMPT + f"\nModule: {module_id}, Features: {json.dumps(color_feats)}",
            "images": [img_b64],
            "stream": False,
            "format": "json"
        }
        req = urllib.request.Request(
            f"{self.ollama_host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            res = json.loads(response.read().decode("utf-8"))
            parsed = json.loads(res.get("response", "{}"))
            return ExpressiveProfile(
                module_id=module_id,
                primary_psychological_state=parsed.get("primary_psychological_state", "hypnotic_trance"),
                secondary_psychological_states=parsed.get("secondary_psychological_states", []),
                symbolic_metaphors=parsed.get("symbolic_metaphors", []),
                narrative_function=parsed.get("narrative_function", "tension_accelerator"),
                jungian_archetype=parsed.get("jungian_archetype", "the_self"),
                color_profile=ColorAesthetics(**color_feats),
                dynamics=SpatiotemporalDynamics(**motion_feats),
                hydration_level=2,
                confidence_score=0.85,
                analyzed_engine="ollama-qwen2-vl"
            )

    def _heuristic_fallback(
        self,
        module_id: str,
        color_feats: Dict[str, Any],
        motion_feats: Dict[str, Any],
        code_snippet: str = ""
    ) -> ExpressiveProfile:
        """
        確定性啟發式合成引擎 (Level 1: 結合客觀數學特徵與代碼關鍵字拓撲)
        """
        temp = color_feats.get("emotional_temperature", "sterile_neutral")
        contrast = color_feats.get("contrast_level", "analogous_subtle")
        mean_l = color_feats.get("mean_lightness", 0.5)
        energy = motion_feats.get("motion_energy_type", "sinusoidal_breath")
        div = motion_feats.get("divergence", 0.0)
        vel = motion_feats.get("mean_velocity", 0.0)

        # 心理狀態推導
        if mean_l < 0.2:
            psy = "alienation_void"
            archetype = "the_void"
            metaphors = ["宇宙深淵", "存在的孤寂", "冷色虛空"]
            narrative = "genesis_anchor"
        elif energy == "inward_implosion" or div < -0.2:
            psy = "claustrophobic_dread"
            archetype = "the_shadow"
            metaphors = ["坍縮黑洞", "無法逃脫的重力", "收緊的囚籠"]
            narrative = "tension_accelerator"
        elif energy == "outward_explosion" or vel > 8.0:
            psy = "manic_hyperarousal"
            archetype = "the_trickster"
            metaphors = ["超新星爆發", "神經元過載", "秩序解構"]
            narrative = "climax_rupture"
        elif temp == "glacial_cold" and contrast == "monochrome_stark":
            psy = "alienation_void"
            archetype = "the_shadow"
            metaphors = ["冰封理性", "機械疏離", "無機生命"]
            narrative = "genesis_anchor"
        elif mean_l > 0.7 or temp == "feverish_warm":
            psy = "sublime_catharsis"
            archetype = "the_self"
            metaphors = ["破曉昇華", "意識覺醒", "光芒滌蕩"]
            narrative = "aftermath_resonance"
        else:
            psy = "hypnotic_trance"
            archetype = "the_animus"
            metaphors = ["時間之流", "自相似分形", "脈動波紋"]
            narrative = "tension_accelerator"

        # 代碼特徵微調
        code_lower = code_snippet.lower()
        if "particle" in code_lower or "attractor" in code_lower:
            metaphors.append("微觀粒子雲")
        if "tree" in code_lower or "branch" in code_lower:
            metaphors.append("生命遞迴之樹")

        return ExpressiveProfile(
            module_id=module_id,
            primary_psychological_state=psy,
            secondary_psychological_states=[temp, energy],
            symbolic_metaphors=metaphors[:3],
            narrative_function=narrative,
            jungian_archetype=archetype,
            color_profile=ColorAesthetics(**color_feats),
            dynamics=SpatiotemporalDynamics(**motion_feats),
            hydration_level=1,
            confidence_score=0.75,
            analyzed_engine="heuristic_fallback"
        )
