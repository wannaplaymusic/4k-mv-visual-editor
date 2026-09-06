import math
import time
import random
import logging
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger("StandaloneInjector.BanditInventorySelector")

class BanditInventorySelector:
    """
    基於情境多臂老虎機 (Contextual Bandit) 與審美熵 (Aesthetic Entropy) 的素材庫存動態選擇器
    - 解決單純 used_count 階梯排序的機械化缺點
    - 結合語意曲風相關性 (Semantic Affinity)、疲勞半衰期衰減 (Fatigue Half-life Recovery)、
      UCB (Upper Confidence Bound) 新穎性探索紅利與全局審美香農熵約束
    """

    def __init__(
        self, 
        exploration_weight: float = 0.65,
        decay_half_life_sec: float = 120.0,
        entropy_target_range: tuple = (2.2, 3.8)
    ):
        self.c = exploration_weight  # UCB 探索係數
        self.tau = decay_half_life_sec  # 疲勞恢復半衰期 (秒或虛擬時間步)
        self.entropy_min, self.entropy_max = entropy_target_range

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
        Score = (Affinity * EnergyFit) * FatigueFactor * GlobalPenalty + UCB_Bonus
        """
        mod_id = module.get("_filename_key") or module.get("name")
        used_count = int(module.get("used_count", 0))
        is_original = bool(module.get("license") == "Original" or "AI Incubator" in str(module.get("author", "")))

        # 1. 語意與曲風相關性 (Semantic Affinity)
        genre = str(section_context.get("genre", "")).lower()
        sec_name = str(section_context.get("section", "Verse")).lower()
        tags = [str(t).lower() for t in module.get("tags", [])]
        name = str(module.get("name", "")).lower()

        affinity = 1.0
        # 曲風與標籤匹配
        if any(genre in t or t in genre for t in tags):
            affinity += 0.4
        
        # 樂段專屬偏好 (如 Drop 喜好粒子、強烈、3d、glitch；Intro 喜好 ambient、fluid、wave)
        if "drop" in sec_name or "chorus" in sec_name:
            if any(t in ["glitch", "3d", "reactive", "kinetic", "audio", "high-energy", "neon"] for t in tags):
                affinity += 0.5
        elif "intro" in sec_name or "outro" in sec_name:
            if any(t in ["ambient", "fluid", "minimal", "wave", "ethereal", "slow"] for t in tags):
                affinity += 0.5
        
        if is_original:
            affinity += 0.35  # 優先鼓勵原創與孵化器成果

        # 2. 能量權重適配度 (Energy Fit)
        target_energy = section_context.get("target_energy", 0.5)
        mod_energy = float(module.get("storyboard_weight", 50)) / 100.0
        energy_fit = 1.0 - abs(target_energy - mod_energy) * 0.4
        energy_fit = max(0.2, energy_fit)

        # 3. 本曲近時疲勞衰減因子 (Fatigue Factor via Exponential Recovery)
        last_time = recent_used_timestamps.get(mod_id)
        if last_time is not None:
            delta_t = max(0.0, current_time - last_time)
            # 距離上次使用越近，衰減因子越接近 0；隨時間推移按半衰期恢復到 1.0
            fatigue_factor = 1.0 - math.exp(-delta_t / max(1.0, self.tau))
        else:
            fatigue_factor = 1.0

        # 4. 全局歷史使用次數懲罰 (Global Usage Penalty)
        global_penalty = math.exp(-used_count / 3.5)

        # 5. UCB 新穎性探索紅利 (Upper Confidence Bound Bonus)
        N = max(1, global_total_picks)
        n_i = used_count
        ucb_bonus = self.c * math.sqrt(math.log(N + 1) / (n_i + 1))

        # 綜合得分
        base_utility = affinity * energy_fit * fatigue_factor * global_penalty
        final_score = base_utility + ucb_bonus

        return max(0.001, final_score)

    def select_modules_for_storyboard(
        self,
        storyboard_sections: List[Dict[str, Any]],
        available_modules: List[Dict[str, Any]],
        audio_telemetry: Dict[str, Any],
        historical_used_counts: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        為整首音樂的分鏡表規劃最優模組分配
        保證：
        1. 每個樂段匹配風格與張力
        2. 全曲避免同一模組連續出現
        3. 長尾低使用率模組獲得合理探索
        4. 審美熵維持在最佳動態區間
        """
        if not available_modules:
            return []

        historical_counts = dict(historical_used_counts or {})
        recent_timestamps: Dict[str, float] = {}
        assigned_history: List[str] = []
        global_picks = sum(historical_counts.values()) + 1

        # 若模組總數過大 (如 1000+)，預先篩選階梯探索池 (保證極低使用率優先，並保留隨機新穎性)
        pool = available_modules
        if len(pool) > 160:
            pool = sorted(
                pool, 
                key=lambda m: (
                    historical_counts.get(m.get("_filename_key") or m.get("name"), int(m.get("used_count", 0))),
                    random.random()
                )
            )[:120]

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
            for mod in pool:
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

                # 剛在上一個分鏡用過的模組施加防連續碰撞懲罰
                if assigned_history and assigned_history[-1] == mod_id:
                    score *= 0.1

                # 加上微量隨機抖動避免完全確定性
                score *= random.uniform(0.95, 1.05)
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

            results.append({
                "section_index": sec_idx,
                "section_name": sec_name,
                "assigned_module_id": chosen_id,
                "module_name": chosen_mod.get("name"),
                "target_energy": target_energy,
                "bandit_score": round(top_k[0][0], 3)
            })

        entropy = self.calculate_shannon_entropy(assigned_history)
        logger.info(f"Bandit 素材選擇完成，全曲分鏡數: {len(results)}, 審美香農熵: {entropy:.2f}")

        return results

    @staticmethod
    def calculate_shannon_entropy(items: List[str]) -> float:
        """ 計算已指派模組的香農熵 (評估視覺多樣性) """
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
