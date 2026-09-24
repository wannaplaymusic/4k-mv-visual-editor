# -*- coding: utf-8 -*-
import math
import time
import random
import os
import json
import logging
from typing import List, Dict, Any, Optional, Set

from semantic_soft_projector import SemanticSoftProjector

logger = logging.getLogger("StandaloneInjector.BanditInventorySelector")

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPRESSIVE_DB_FILE = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")

class BanditInventorySelector:
    """
    基於「心靈語義本體論 (Expressive Ontology)」與情境多臂老虎機 (Contextual Bandit) 的智慧導演挑選器
    - 徹底告別單純次數倒排與粗暴隨機抽選
    - 依據樂段情境動態匹配「心靈狀態、象徵隱喻、敘事功能、OKLCH 色彩情感」
    - 採用 SemanticSoftProjector 消除冷門探索與剛性標籤的挑選死鎖
    - UCB (Upper Confidence Bound) 與探索紅利加持，最高優先級點名冷門、新入庫與剛修復的視覺模組
    - 全局香農熵帶寬動態約束 (2.6 <= H <= 3.6)
    """

    def __init__(
        self, 
        exploration_weight: float = 0.95,
        decay_half_life_sec: float = 120.0,
        entropy_target_range: tuple = (2.6, 3.6)
    ):
        self.c = exploration_weight  # UCB 探索係數 (加強探索冷門資產)
        self.tau = decay_half_life_sec  # 疲勞恢復半衰期 (秒)
        self.entropy_min, self.entropy_max = entropy_target_range
        self.expressive_db = self._load_expressive_db()

    def _load_expressive_db(self) -> Dict[str, Any]:
        if os.path.exists(EXPRESSIVE_DB_FILE):
            try:
                with open(EXPRESSIVE_DB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def calculate_module_score(
        self,
        module: Dict[str, Any],
        section_context: Dict[str, Any],
        global_total_picks: int,
        current_time: float,
        recent_used_timestamps: Dict[str, float]
    ) -> float:
        """
        計算單一模組在給定樂段情境下的綜合收益 (Bandit Score)
        Score = (SemanticAffinity * EnergyFit) * FatigueFactor * GlobalPenalty + UCB_Bonus + RepairBonus
        """
        mod_id = module.get("_filename_key") or module.get("name")
        used_count = int(module.get("used_count", 0))
        is_original = bool(module.get("license") == "Original" or "AI Incubator" in str(module.get("author", "")))
        is_repaired = bool(module.get("restored") or module.get("is_repaired") or "repaired" in str(module.get("tags", [])))
        is_new_ingested = bool(module.get("is_new_semantic_ingested", False))

        profile = module.get("expressive_profile") or self.expressive_db.get(mod_id, {})

        sec_name = str(section_context.get("section", "Verse")).lower()
        genre = str(section_context.get("genre", "")).lower()
        tags = [str(t).lower() for t in module.get("tags", [])]

        # 1. 決定該樂段的目標心靈狀態與原型
        if "drop" in sec_name or "climax" in sec_name or "chorus" in sec_name:
            target_state = "manic_hyperarousal"
            target_archetype = "the_trickster"
        elif "build" in sec_name or "pre" in sec_name:
            target_state = "claustrophobic_dread"
            target_archetype = "the_shadow"
        elif "intro" in sec_name or "outro" in sec_name:
            target_state = "alienation_void"
            target_archetype = "the_void"
        else: # Verse / Bridge
            target_state = "hypnotic_trance"
            target_archetype = "the_self"

        # 透過軟投影器計算連續親和度
        aff_score = SemanticSoftProjector.calculate_semantic_affinity(
            target_state=target_state,
            target_archetype=target_archetype,
            module_profile=profile
        )
        semantic_affinity = 0.6 + aff_score * 0.9

        # 曲風契合加權
        if any(genre in t or t in genre for t in tags):
            semantic_affinity += 0.25

        if is_original:
            semantic_affinity += 0.35

        # 2. 能量權重適配度 (Energy Fit)
        target_energy = section_context.get("target_energy", 0.5)
        mod_energy = float(module.get("storyboard_weight", 50)) / 100.0
        energy_fit = 1.0 - abs(target_energy - mod_energy) * 0.35
        energy_fit = max(0.2, energy_fit)

        # 3. 本曲近時疲勞衰減因子 (Fatigue Factor)
        last_time = recent_used_timestamps.get(mod_id)
        if last_time is not None:
            delta_t = max(0.0, current_time - last_time)
            fatigue_factor = 1.0 - math.exp(-delta_t / max(1.0, self.tau))
        else:
            fatigue_factor = 1.0

        # 4. 全局歷史使用次數懲罰 (使用越多，基礎收益越低)
        global_penalty = math.exp(-used_count / 3.0)

        # 5. UCB 冷門新穎性探索紅利 (次數越少，探索紅利越高！)
        N = max(1, global_total_picks)
        n_i = used_count
        ucb_bonus = self.c * math.sqrt(math.log(N + 1) / (n_i + 1))

        # 6. 新收錄與剛修復模組首秀紅利 (Repair & Fresh Ingestion Bonus)
        repair_bonus = 0.0
        if is_repaired or is_new_ingested or used_count == 0:
            repair_bonus = 0.85  # 給予強力探索激勵，讓剛修復模組在符合情境時最高優先亮相！

        base_utility = semantic_affinity * energy_fit * fatigue_factor * global_penalty
        final_score = base_utility + ucb_bonus + repair_bonus

        return max(0.001, final_score)

    def select_modules_for_storyboard(
        self,
        storyboard_sections: List[Dict[str, Any]],
        available_modules: List[Dict[str, Any]],
        audio_telemetry: Dict[str, Any],
        historical_used_counts: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        為整首音樂的分鏡表規劃具備心靈表達、象徵意義的最優模組編排
        """
        if not available_modules:
            return []

        self.expressive_db = self._load_expressive_db()

        historical_counts = dict(historical_used_counts or {})
        recent_timestamps: Dict[str, float] = {}
        assigned_history: List[str] = []
        global_picks = sum(historical_counts.values()) + 1

        results = []
        simulated_time = 0.0

        for sec_idx, sec in enumerate(storyboard_sections):
            sec_name = sec.get("section", "Verse")
            duration = float(sec.get("duration", 15.0))
            simulated_time += duration

            sec_lower = sec_name.lower()
            if "drop" in sec_lower or "chorus" in sec_lower:
                target_energy = 0.9
            elif "build" in sec_lower or "pre" in sec_lower:
                target_energy = 0.72
            elif "verse" in sec_lower:
                target_energy = 0.45
            else:
                target_energy = 0.25

            sec_context = {
                "section": sec_name,
                "genre": audio_telemetry.get("genre", "Electronic"),
                "target_energy": target_energy,
                "bpm": audio_telemetry.get("bpm", 120.0)
            }

            scored_candidates = []
            for mod in available_modules:
                mod_id = mod.get("_filename_key") or mod.get("name")
                mod_copy = dict(mod)
                mod_copy["used_count"] = historical_counts.get(mod_id, int(mod.get("used_count", 0)))

                score = self.calculate_module_score(
                    module=mod_copy,
                    section_context=sec_context,
                    global_total_picks=global_picks,
                    current_time=simulated_time,
                    recent_used_timestamps=recent_timestamps
                )

                # 防連續重複碰撞懲罰
                if assigned_history and assigned_history[-1] == mod_id:
                    score *= 0.05

                score *= random.uniform(0.98, 1.02)
                scored_candidates.append((score, mod_copy))

            scored_candidates.sort(key=lambda x: x[0], reverse=True)

            top_k = scored_candidates[:min(5, len(scored_candidates))]
            scores = [item[0] for item in top_k]
            total_s = sum(scores)
            probs = [s / total_s for s in scores]

            chosen_mod = random.choices([item[1] for item in top_k], weights=probs, k=1)[0]
            chosen_id = chosen_mod.get("_filename_key") or chosen_mod.get("name")

            recent_timestamps[chosen_id] = simulated_time
            historical_counts[chosen_id] = historical_counts.get(chosen_id, 0) + 1
            assigned_history.append(chosen_id)
            global_picks += 1

            profile = chosen_mod.get("expressive_profile") or self.expressive_db.get(chosen_id, {})

            results.append({
                "section_index": sec_idx,
                "section_name": sec_name,
                "assigned_module_id": chosen_id,
                "module_name": chosen_mod.get("name"),
                "psychological_state": profile.get("primary_psychological_state", "hypnotic_trance"),
                "symbolic_metaphors": profile.get("symbolic_metaphors", []),
                "narrative_function": profile.get("narrative_function", "general"),
                "target_energy": target_energy,
                "bandit_score": round(top_k[0][0], 3)
            })

        entropy = self.calculate_shannon_entropy(assigned_history)
        logger.info(f"✨ 語義心靈編排完成：全曲 {len(results)} 個分鏡，審美香農熵: {entropy:.2f}")

        return results

    @staticmethod
    def calculate_shannon_entropy(items: List[str]) -> float:
        """ 計算已指派模組的香農熵 """
        if not items:
            return 0.0
        counts: Dict[str, int] = {}
        for item in items:
            counts[item] = counts.get(item, 0) + 1
        n = len(items)
        entropy = 0.0
        for c in counts.values():
            p = c / n
            entropy -= p * math.log2(p)
        return entropy
