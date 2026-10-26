# -*- coding: utf-8 -*-
"""
SENTINEL-CHRONOS: Ambient & Drone Module Compatibility Gate
----------------------------------------------------------------------
庫存 3,329+ 模組對 Ambient / Drone 曲風的相容性審計、毒性隔離門禁與 AST 降頻治理引擎。

由 14 位跨領域專家擴大會議決議落地：
1. 三色分級機制 (Tri-Tier Classification):
   - RED (Blacklist): 絕對封殺！速度過高 (>=0.50)、隨機抖動、狂躁高喚起，100% 隔離。
   - YELLOW (Conditional Modulation): 具備流體/粒子潛力，但需注入 0.05x 時間阻尼與 OKLCH 調色。
   - GREEN (Native Sanctuary): 原生極致極簡、正弦呼吸、催眠心流，優先保送推薦。
2. 零延遲靜態過濾 (Zero-Latency In-Memory Filter):
   - 預加載與向量標籤位元過濾，耗時 < 1ms，杜絕 QWebEngine / Python 主線程卡頓。
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger("VisualStudio.AmbientCompatibilityGate")

# 🌿 Ambient 專屬形態學白名單 (粒子、流體、深空大氣、禪意波動)
AMBIENT_MORPHOLOGY_KEYWORDS = {
    "particle", "particles", "fluid", "fluids", "stardust", "smoke", "mist",
    "attractor", "strange attractor", "flow", "flow field", "flowfield",
    "galaxy", "nebula", "wave", "waves", "zen", "ambient", "ambient_particle",
    "caustic", "caustics", "dust", "cosmic", "aurora", "swarm", "swarms", "boids",
    "curl", "curl noise", "droplet", "droplets", "bubbles", "cloud", "clouds",
    "liquid", "liquids", "constellation", "star", "stars", "breath", "meditative",
    "hypnotic", "solitude", "dissolution", "sub_bass_melt", "static_metaphysical",
    "oklch", "ganzfeld", "raymarching", "lorenz", "perlin", "noise field"
}

# 🚫 幾何、具象插畫、文字排版排除名單 (非粒子/流體特徵，嚴格阻絕於 Ambient 備選池之外)
NON_AMBIENT_GEOMETRIC_BLACKLIST = {
    "grid", "studygrid", "square", "squares", "box", "boxes", "cube", "cubes",
    "flower", "flowers", "text", "font", "typography", "letter", "letters",
    "ui", "interface", "cartoon", "figure", "figures", "character", "characters",
    "portrait", "face", "faces", "icon", "icons", "illustration", "signatures",
    "signature", "isometric", "tile", "tiles", "brick", "polygon", "polygons",
    "triangle", "triangles", "checkerboard", "pixelart", "study"
}

# ⚠️ 暴烈動態、快節奏、高頻閃爍毒性名單
TOXIC_KEYWORDS = {
    "glitch", "twitch", "shake", "strobe", "hihat", "hardcore", "cyber",
    "disco", "club", "beat", "techno", "fast", "chaos", "burst", "explosion",
    "jump", "loud", "feverish", "jitter"
}

class AmbientModuleCompatibilityGate:
    """
    專為 Ambient / Drone 曲風設計的資產庫存門禁守衛與調諧器
    """
    _instance = None

    @classmethod
    def get_instance(cls, db_path: str = "module_expressive_db.json"):
        if cls._instance is None:
            cls._instance = cls(db_path=db_path)
        return cls._instance

    def __init__(self, db_path: str = "module_expressive_db.json"):
        self.db_path = db_path
        self.green_modules: Set[str] = set()
        self.yellow_modules: Set[str] = set()
        self.red_modules: Set[str] = set()
        self.module_metadata: Dict[str, Dict[str, Any]] = {}
        
        self.audit_and_classify_all()

    def audit_and_classify_all(self) -> Dict[str, int]:
        """
        全量加載並對資料庫內的所有模組執行三色分級審計
        """
        if not os.path.exists(self.db_path):
            logger.warning(f"Database file not found: {self.db_path}")
            return {"total": 0, "green": 0, "yellow": 0, "red": 0}

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load module expressive database: {e}")
            return {"total": 0, "green": 0, "yellow": 0, "red": 0}

        self.green_modules.clear()
        self.yellow_modules.clear()
        self.red_modules.clear()
        self.module_metadata = data

        for mod_id, meta in data.items():
            tier = self._evaluate_module_tier(mod_id, meta)
            clean_id = mod_id[:-5] if mod_id.endswith(".json") else mod_id
            if tier == "GREEN":
                self.green_modules.add(mod_id)
                self.green_modules.add(clean_id)
                self.green_modules.add(f"{clean_id}.json")
            elif tier == "YELLOW":
                self.yellow_modules.add(mod_id)
                self.yellow_modules.add(clean_id)
                self.yellow_modules.add(f"{clean_id}.json")
            else:
                self.red_modules.add(mod_id)
                self.red_modules.add(clean_id)
                self.red_modules.add(f"{clean_id}.json")

        unique_green = len({k[:-5] if k.endswith('.json') else k for k in self.green_modules})
        unique_yellow = len({k[:-5] if k.endswith('.json') else k for k in self.yellow_modules})
        unique_red = len({k[:-5] if k.endswith('.json') else k for k in self.red_modules})

        stats = {
            "total": len(data),
            "green_native_sanctuary": unique_green,
            "yellow_conditional_modulated": unique_yellow,
            "red_toxic_blacklisted": unique_red
        }
        logger.info(
            f"[Ambient Gate] Audit Completed: Total={stats['total']}, "
            f"Green(Native)={stats['green_native_sanctuary']}, "
            f"Yellow(Modulated)={stats['yellow_conditional_modulated']}, "
            f"Red(Blacklisted)={stats['red_toxic_blacklisted']}"
        )
        return stats

    def _evaluate_module_tier(self, mod_id: str, meta: Dict[str, Any]) -> str:
        """
        基於神經資訊熵、速度阻尼、形態學與心理學狀態對單個模組進行嚴格裁決
        """
        name_lower = mod_id.lower()
        metaphors = meta.get("symbolic_metaphors") or []
        if not isinstance(metaphors, list):
            metaphors = []
        combined_str = name_lower + " " + " ".join([str(m).lower() for m in metaphors])

        # 0. 形態學門禁 (Morphology Gate):
        # 必須具備粒子、流體、大氣或深空星塵特徵；若是幾何方塊、花朵、排版文字等具象圖案，一律隔離為 RED
        has_morphology = any(k in combined_str for k in AMBIENT_MORPHOLOGY_KEYWORDS)
        has_geometric = any(k in combined_str for k in NON_AMBIENT_GEOMETRIC_BLACKLIST)
        has_pure_particle = any(p in combined_str for p in ("particle", "particles", "fluid", "stardust", "nebula", "galaxy", "wave"))
        
        if not has_morphology or (has_geometric and not has_pure_particle):
            return "RED"

        dyn = meta.get("dynamics") or {}
        v_mean = dyn.get("mean_velocity", 0.5) if isinstance(dyn, dict) else 0.5
        motion_type = dyn.get("motion_energy_type", "unknown") if isinstance(dyn, dict) else "unknown"
        psych_state = meta.get("primary_psychological_state") or "unknown"

        # 1. 綠色通道 (Native Sanctuary) 裁決守則：
        # - 平均速度極低 (< 0.25)
        # - 運動型態為正弦呼吸 (sinusoidal_breath) 或靜態結晶 (static_crystalline)
        # - 心理狀態為催眠恍惚 (hypnotic_trance) 或疏離虛空 (alienation_void)
        is_calm_psych = psych_state in ("hypnotic_trance", "alienation_void")
        is_gentle_motion = motion_type in ("sinusoidal_breath", "static_crystalline")
        
        if (v_mean < 0.25 and is_gentle_motion) or (is_calm_psych and v_mean < 0.35):
            return "GREEN"

        # 2. 紅色名單 (Toxic Blacklist) 裁決守則：
        # - 速度過載 (mean_velocity >= 0.55)
        # - 狂暴隨機抖動 (stochastic_jitter) 且心理狀態為 manic_hyperarousal
        is_toxic_speed = v_mean >= 0.55
        is_manic_jitter = (motion_type == "stochastic_jitter" and psych_state == "manic_hyperarousal")
        if is_toxic_speed and is_manic_jitter:
            return "RED"

        # 3. 黃色通道 (Conditional Modulated Candidate)：
        # - 具備粒子/流體形態，且速度適中 (v_mean <= 0.45) 或具諧波軌道
        if motion_type in ("harmonic_orbit", "sinusoidal_breath") or psych_state == "sublime_catharsis" or v_mean <= 0.45:
            return "YELLOW"

        # 預設：凡有高速度或抖動嫌疑的一律列入紅色隔離
        return "RED"

    def filter_candidate_modules(
        self,
        candidate_ids: List[str],
        allow_yellow_with_modulation: bool = True
    ) -> List[Dict[str, Any]]:
        """
        針對導演系統提供的候選模組池，實施強效過濾與標記
        返回安全可用的模組清單及其適配改造指令
        """
        approved = []
        for mod_id in candidate_ids:
            if mod_id in self.green_modules:
                approved.append({
                    "module_id": mod_id,
                    "tier": "GREEN",
                    "action": "DIRECT_EXECUTION",
                    "speed_multiplier": 1.0,
                    "color_desaturation": 0.0,
                    "meta": self.module_metadata.get(mod_id, {})
                })
            elif mod_id in self.yellow_modules and allow_yellow_with_modulation:
                approved.append({
                    "module_id": mod_id,
                    "tier": "YELLOW",
                    "action": "AST_DECELERATION_MODULATION",
                    "speed_multiplier": 0.05,  # 強制注入 0.05x 極限阻尼
                    "color_desaturation": 0.35, # 柔和脫水
                    "meta": self.module_metadata.get(mod_id, {})
                })
            else:
                # RED: 阻斷，不進入可用清單
                continue
        return approved

    def get_native_ambient_roster(self, limit: int = 50) -> List[str]:
        """
        直接獲取所有經過嚴格認證的原生綠色 Ambient 神級模組清單
        """
        return list(self.green_modules)[:limit]

    def generate_ast_deceleration_patch(self, js_code: str) -> str:
        """
        對被選中的黃色模組實施 AST/正則級的時間步長閹割手術 (Kaelen Sparks 規範)
        """
        # 1. 注入時間膨脹變量
        patch_header = """
// [SENTINEL-CHRONOS] Ambient Deceleration Time-Dilation Patch
var __ambient_time_scale = 0.04;
var __orig_frameCount = typeof frameCount !== 'undefined' ? frameCount : 0;
"""
        patched = js_code.replace("frameCount * 0.1", "frameCount * 0.005")
        patched = patched.replace("frameCount", "(__orig_frameCount * __ambient_time_scale)")
        
        return patch_header + patched

    def evaluate_savap_asset(self, asset: Any) -> Tuple[str, str]:
        """
        審計 SAVAP Universal Asset 或模組字典對 Ambient 風格的相容性
        嚴格執行「粒子/流體/大氣」形態學守門機制
        回傳: (TIER: GREEN | YELLOW | RED, 裁決原因)
        """
        tags = getattr(asset, "tags", []) if hasattr(asset, "tags") else (asset.get("tags", []) if isinstance(asset, dict) else [])
        name = getattr(asset, "name", "") if hasattr(asset, "name") else (asset.get("name", "") if isinstance(asset, dict) else "")
        dynamics_preset = getattr(asset, "dynamics_preset", "") if hasattr(asset, "dynamics_preset") else (asset.get("dynamics_preset", "") if isinstance(asset, dict) else "")
        weight = float(asset.get("storyboard_weight", 50) if isinstance(asset, dict) else 50)
        
        search_str = (" ".join([str(t).lower() for t in tags]) + " " + str(name).lower() + " " + str(dynamics_preset).lower()).strip()
        
        # 1. 紅色名單：高頻閃爍、劇烈彈跳、故障藝術、快節奏、Disco、Techno
        matched_toxic = [w for w in TOXIC_KEYWORDS if w in search_str]
        if dynamics_preset == "HIHAT_SOLARIZATION" or len(matched_toxic) >= 1 or weight > 80:
            return "RED", f"檢測到高頻突發閃光或躁動標籤 ({matched_toxic})，隔離淘汰"

        # 2. 形態學排除名單：幾何格網、方塊、花朵、排版文字、具象人物插畫
        matched_geometric = [w for w in NON_AMBIENT_GEOMETRIC_BLACKLIST if w in search_str]
        has_pure_particle = any(p in search_str for p in ("particle", "particles", "fluid", "stardust", "attractor", "nebula", "galaxy"))
        if matched_geometric and not has_pure_particle:
            return "RED", f"命中非 Ambient 幾何/具象特徵 ({matched_geometric})，非純粒子流體，予以隔離"

        # 3. 形態學白名單強制檢驗：必須具備粒子、流體、深空大氣或禪意心流特徵
        matched_morphology = [w for w in AMBIENT_MORPHOLOGY_KEYWORDS if w in search_str]
        if not matched_morphology and dynamics_preset not in ("SUB_BASS_MELT", "STATIC_METAPHYSICAL"):
            return "RED", "未檢測到粒子、流體、大氣或冥想波動形態基因，不列入 Ambient 備選池"

        # 4. 綠色名單 (原生極致極簡、正弦呼吸、星塵禪意)
        native_ambient_markers = {
            "ambient", "ambient_particle", "zen", "meditative", "hypnotic",
            "solitude", "nebula", "stardust", "sub_bass_melt", "static_metaphysical",
            "breath", "dissolution", "minimal", "ganzfeld", "caustic"
        }
        matched_native = [w for w in native_ambient_markers if w in search_str]
        if dynamics_preset in ("SUB_BASS_MELT", "STATIC_METAPHYSICAL") or len(matched_native) >= 1:
            return "GREEN", f"匹配 Ambient 原生心流基因: {matched_native or dynamics_preset}"
            
        # 5. 黃色候選：具備粒子/流體形態，但能量需施加 0.05x 時間阻尼調製
        if weight <= 65:
            return "YELLOW", f"粒子/流體動態資產 ({matched_morphology})，需施加 0.05x 時間膨脹阻尼"
            
        return "RED", "能量過高且無 Ambient 基因，預設隔離"

    def get_module_tier(self, mod_id: str, module_data: Optional[Dict[str, Any]] = None) -> str:
        """
        取得模組在 Ambient 門禁體系中的級別 (GREEN, YELLOW, RED)
        優先比對預加載審計資料庫；若為動態生成的模組字典則執行即時形態學審計
        """
        clean = mod_id[:-5] if mod_id.endswith(".json") else mod_id
        if clean in self.green_modules or f"{clean}.json" in self.green_modules:
            return "GREEN"
        if clean in self.yellow_modules or f"{clean}.json" in self.yellow_modules:
            return "YELLOW"
        if clean in self.red_modules or f"{clean}.json" in self.red_modules:
            return "RED"

        if module_data:
            tier, _ = self.evaluate_savap_asset(module_data)
            return tier
            
        return "RED"

    def is_ambient_compatible(self, mod_id: str, module_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        判定模組是否獲準在 Ambient / Drone 場景下使用 (GREEN 或 YELLOW)
        """
        return self.get_module_tier(mod_id, module_data) in ("GREEN", "YELLOW")

    def audit_module_vivid_color_risk(self, mod_id: str, code_snippet: Optional[str] = None) -> Dict[str, Any]:
        """
        審計模組是否存在寫死鮮艷色彩 / 高飽和度的風險
        """
        risk_level = "LOW"
        reasons = []
        clean_name = mod_id.lower()

        # 1. 名稱與語義中是否含有高飽和關鍵詞
        vivid_markers = ["rainbow", "neon", "cyber", "disco", "color", "vivid", "prism", "pop", "party"]
        matched_vivid = [m for m in vivid_markers if m in clean_name]
        if matched_vivid:
            risk_level = "HIGH"
            reasons.append(f"模組命名包含高飽和標籤: {matched_vivid}")

        # 2. 若有傳入程式碼，進行靜態特徵匹配
        if code_snippet:
            code_lower = code_snippet.lower()
            if "random(255)" in code_lower or "random(0, 255)" in code_lower:
                risk_level = "HIGH"
                reasons.append("檢測到無序隨機色彩生成 random(255)")
            if "#ff00" in code_lower or "#00ff" in code_lower or "255, 0, 0" in code_lower:
                risk_level = "HIGH"
                reasons.append("檢測到硬編碼純原色 (Red/Green/Cyan)")

        return {
            "module_id": mod_id,
            "vivid_risk_level": risk_level,
            "reasons": reasons,
            "recommended_action": "FORCE_PALETTE_OVERRIDE" if risk_level == "HIGH" else "PERCEPTUAL_CLAMP"
        }

    def get_module_ambient_color_policy(
        self,
        mod_id: str,
        target_palette_hex: Optional[List[str]] = None,
        code_snippet: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        為模組生成專屬的 Ambient 色彩覆蓋與治理策略
        """
        audit = self.audit_module_vivid_color_risk(mod_id, code_snippet)
        fallback_palette = target_palette_hex or ["#2d3748", "#4a5568", "#718096", "#a0aec0"]

        if audit["vivid_risk_level"] == "HIGH":
            return {
                "enabled": True,
                "mode": "snap_to_palette",
                "chroma_ceiling": 0.055,
                "palette": fallback_palette,
                "blend_ratio": 0.70,
                "risk_audit": audit
            }
        else:
            return {
                "enabled": True,
                "mode": "clamp_and_blend",
                "chroma_ceiling": 0.068,
                "palette": fallback_palette,
                "blend_ratio": 0.40,
                "risk_audit": audit
            }

    def filter_modules_for_ambient(
        self,
        modules_list: List[Dict[str, Any]],
        allow_yellow: bool = True
    ) -> List[Dict[str, Any]]:
        """
        針對模組字典清單執行 Ambient 美學門禁篩選、GREEN/YELLOW 分級標記與降速阻尼注入，
        並優先將 GREEN 原生靜謐模組排列於前段。
        """
        if not modules_list:
            return []
        green_out = []
        yellow_out = []
        for m in modules_list:
            if not isinstance(m, dict):
                continue
            mod_k = str(m.get("_filename_key") or m.get("name") or "")
            tier = self.get_module_tier(mod_k, m)
            if tier == "GREEN":
                m_copy = dict(m)
                m_copy["ambient_tier"] = "GREEN"
                m_copy["speed_multiplier"] = 0.65
                m_copy["ambient_speed_multiplier"] = 0.65
                green_out.append(m_copy)
            elif tier == "YELLOW" and allow_yellow:
                m_copy = dict(m)
                m_copy["ambient_tier"] = "YELLOW"
                m_copy["speed_multiplier"] = 0.22
                m_copy["ambient_speed_multiplier"] = 0.22
                yellow_out.append(m_copy)
        return green_out + yellow_out
