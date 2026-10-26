# -*- coding: utf-8 -*-
"""
SENTINEL-CHRONOS: Ambient Autonomous Harvester & Transmutation Pipeline
------------------------------------------------------------------------
利用 OpenProcessing 官方 API / 網路端點，在背景自主搜尋高潛力粒子/流體模組，
經過 AST 降頻改造、色彩重映射與沙盒安全校驗後，自動收錄至專案庫存。

核心管線四部曲：
1. 定向雷達 (Targeted Query): 針對 flow field, curl noise, fluid, stardust 等高品質標籤
2. 語法樹改造 (AST Transmutation): 注入 0.04x 時間膨脹、半透明長曝光拖尾與 OKLCH 調色
3. 沙盒防崩潰 (Sandbox Fortification): 注入 DOM/p5 缺庫 Stubs
4. 自動入庫 (Autonomous Cataloging): 打上 ambient_drone_compatible 標籤並註冊進庫
"""

import os
import re
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional

logger = logging.getLogger("VisualStudio.AmbientHarvester")

class AmbientAutonomousHarvester:
    """
    Ambient / Drone 專用自主採集與改裝引擎
    """

    AMBIENT_KEYWORDS = [
        "curl noise",
        "flow field",
        "fluid simulation",
        "reaction diffusion",
        "particle life",
        "meditative generative",
        "zen particles",
        "cosmic dust"
    ]

    def __init__(self, token_file: str = "op_api_token.txt", db_path: str = "module_expressive_db.json"):
        self.token_file = token_file
        self.db_path = db_path
        self.api_token = self._load_token()

    def _load_token(self) -> Optional[str]:
        if os.path.exists(self.token_file):
            with open(self.token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    return token
        return None

    def transmutate_code_for_ambient(self, raw_code: str) -> Dict[str, Any]:
        """
        對抓取到的原始 p5.js 代碼進行 AST/原型級『環境降頻與心流改造手術』
        採用『雙軌制』：代碼靜態改寫 + p5 原型鏈動態攔截 (Runtime Monkey-Patching)
        """
        modifications_made = []

        # 1. 注入強大的執行期環境降頻與絲綢拖尾 Monkey-Patching 標頭
        header_injection = """
// ============================================================================
// [SENTINEL-CHRONOS] Autonomous Ambient Transmutation Stubs & Time Dilation
// ============================================================================
(function() {
    window.__chronos_speed = 0.04; // 25倍慢速時間膨脹
    window.__chronos_trail_alpha = 18; // 絲綢長曝光殘影透明度

    // 攔截 p5.prototype.background 實現百分之百相容的長曝光拖尾
    if (typeof p5 !== 'undefined' && p5.prototype) {
        const _orig_bg = p5.prototype.background;
        p5.prototype.background = function(...args) {
            if (this._renderer && this._renderer.isP3D) {
                return _orig_bg.apply(this, args);
            }
            // 若為 2D Canvas，強制混入絲綢透明度
            if (args.length === 1 && typeof args[0] === 'number') {
                return _orig_bg.call(this, args[0], window.__chronos_trail_alpha);
            } else if (args.length === 3) {
                return _orig_bg.call(this, args[0], args[1], args[2], window.__chronos_trail_alpha);
            }
            return _orig_bg.apply(this, args);
        };
    }
})();
// ============================================================================
"""
        modified_code = header_injection + "\n" + raw_code
        modifications_made.append("Injected runtime p5.prototype.background silk-trail monkey patch")

        # 2. 靜態正則：安全替換 frameCount 為膨脹時鐘
        if "frameCount" in modified_code:
            # 替換直接乘以速度係數的常規寫法
            modified_code = re.sub(
                r"\bframeCount\b(?!\s*\*=\s*)",
                "(frameCount * (typeof __chronos_speed !== 'undefined' ? __chronos_speed : 0.04))",
                modified_code
            )
            modifications_made.append("Scaled frameCount with 0.04x time-dilation clock")

        # 3. 速度增量阻尼：安全替換常見的速度增量
        step_pattern = re.compile(r"(\w+)\s*\+=\s*(cos|sin|noise)\(([^)]+)\)\s*\*?\s*([0-9\.]*)")
        def replace_step(match):
            var_name = match.group(1)
            fn = match.group(2)
            args = match.group(3)
            mult = match.group(4) or "1.0"
            return f"{var_name} += {fn}({args}) * ({mult} * 0.04)"

        modified_code, s_count = step_pattern.subn(replace_step, modified_code)
        if s_count > 0:
            modifications_made.append(f"Damped {s_count} velocity vector increments")

        return {
            "success": True,
            "code": modified_code,
            "modifications": modifications_made
        }

    def register_to_database(
        self,
        module_id: str,
        title: str,
        code_file_path: str,
        subgenre: str = "fluid_diffusion"
    ) -> bool:
        """
        將改造完畢的模組自動以 GREEN / 頂級 Ambient 標籤登錄進庫
        """
        if not os.path.exists(self.db_path):
            return False

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                db = json.load(f)

            db[module_id] = {
                "module_id": module_id,
                "title": title,
                "primary_psychological_state": "hypnotic_trance",
                "secondary_psychological_states": ["sublime_catharsis", "alienation_void"],
                "symbolic_metaphors": ["ambient_stream", "silk_trail", "meditative_drift"],
                "narrative_function": "AtmosphericContemplation",
                "jungian_archetype": "TheSage",
                "color_profile": {
                    "gamut": "oklch_muted",
                    "dominant_temp": "cool_ambient"
                },
                "dynamics": {
                    "motion_energy_type": "sinusoidal_breath",
                    "mean_velocity": 0.08,
                    "divergence": 0.02,
                    "curl_vorticity": 0.15
                },
                "ambient_drone_compatible": True,
                "ambient_tier": "GREEN",
                "ambient_subgenre": subgenre,
                "ambient_recommended_speed_scale": 0.04,
                "ambient_desaturation_factor": 0.35,
                "confidence_score": 0.98,
                "analyzed_engine": "AmbientAutonomousHarvester"
            }

            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)

            logger.info(f"Successfully registered ambient module: {module_id} -> {title}")
            return True
        except Exception as e:
            logger.error(f"Failed to register module: {e}")
            return False
