# -*- coding: utf-8 -*-
"""
SENTINEL: Hierarchical Semantic Soft Projector
層級化語義軟投影與死鎖消除器
- 解決冷門模組防連續使用 (Fatigue) 與特定心靈標籤剛性過濾之間的挑選死鎖
- 提供三級動態釋放機制: 
  Level 1: 精確心靈狀態匹配 (Exact Psychological Match)
  Level 2: 榮格原型拓撲鄰域放寬 (Archetype Neighborhood Relaxation)
  Level 3: OKLCH 色彩與動態幾何承接 (Geometric Continuity Fallback)
"""

from typing import List, Dict, Any, Optional

# 榮格原型空間與心靈狀態的拓撲鄰近圖
PSYCHOLOGICAL_NEIGHBORHOOD = {
    "alienation_void": ["existential_awe", "nostalgic_decay", "claustrophobic_dread"],
    "claustrophobic_dread": ["alienation_void", "hypnotic_trance", "manic_hyperarousal"],
    "manic_hyperarousal": ["climax_rupture", "sublime_catharsis", "claustrophobic_dread"],
    "hypnotic_trance": ["claustrophobic_dread", "alienation_void", "sublime_catharsis"],
    "sublime_catharsis": ["existential_awe", "manic_hyperarousal", "hypnotic_trance"],
    "nostalgic_decay": ["alienation_void", "hypnotic_trance", "the_void"],
    "existential_awe": ["sublime_catharsis", "alienation_void", "the_self"]
}

# 榮格原型的心理狀態聚合
ARCHETYPE_MAP = {
    "the_shadow": ["claustrophobic_dread", "alienation_void"],
    "the_void": ["alienation_void", "nostalgic_decay"],
    "the_self": ["sublime_catharsis", "existential_awe"],
    "the_animus": ["hypnotic_trance", "tension_accelerator"],
    "the_trickster": ["manic_hyperarousal", "climax_rupture"]
}

class SemanticSoftProjector:
    """
    語義軟投影器：在多重約束下保證永遠有最優候選模組可供挑選
    """

    @classmethod
    def calculate_semantic_affinity(
        cls,
        target_state: str,
        target_archetype: str,
        module_profile: Dict[str, Any]
    ) -> float:
        """
        計算模組與目標心靈狀態的連續型親和度得分 (0.0 ~ 1.0)
        """
        mod_state = module_profile.get("primary_psychological_state", "")
        mod_archetype = module_profile.get("jungian_archetype", "")

        # 1. 精確匹配 (Level 1)
        if mod_state and mod_state == target_state:
            return 1.0

        # 2. 原型一致 (Level 2a)
        if mod_archetype and target_archetype and mod_archetype == target_archetype:
            return 0.82

        # 3. 心靈鄰域拓撲相近 (Level 2b)
        neighbors = PSYCHOLOGICAL_NEIGHBORHOOD.get(target_state, [])
        if mod_state in neighbors:
            return 0.70

        # 4. 次要心理標籤重疊 (Level 2c)
        secondary = module_profile.get("secondary_psychological_states", [])
        if any(s in neighbors or s == target_state for s in secondary):
            return 0.55

        # 5. 通用基礎親和度 (Level 3 - 承接底線)
        return 0.25

    @classmethod
    def resolve_candidates_with_fallback(
        cls,
        target_state: str,
        target_archetype: str,
        available_modules: List[Dict[str, Any]],
        expressive_db: Dict[str, Any],
        min_affinity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        具有層級回退能力的候選池解析器
        若以高門檻篩選出的候選模組不足 3 個，自動沿拓撲階梯向下放寬，保證系統永不死鎖
        """
        thresholds = [min_affinity_threshold, 0.4, 0.2, 0.0]

        for th in thresholds:
            eligible = []
            for mod in available_modules:
                mod_id = mod.get("_filename_key") or mod.get("name")
                profile = mod.get("expressive_profile") or expressive_db.get(mod_id, {})
                affinity = cls.calculate_semantic_affinity(target_state, target_archetype, profile)
                if affinity >= th:
                    mod_with_aff = dict(mod)
                    mod_with_aff["_computed_semantic_affinity"] = affinity
                    eligible.append(mod_with_aff)

            if len(eligible) >= 3:
                return eligible

        return available_modules
