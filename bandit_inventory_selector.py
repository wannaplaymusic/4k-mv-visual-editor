# -*- coding: utf-8 -*-
import math
import time
import random
import os
import json
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

from semantic_soft_projector import SemanticSoftProjector

logger = logging.getLogger("StandaloneInjector.BanditInventorySelector")

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPRESSIVE_DB_FILE = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")
PHENOTYPE_CLUSTERS_FILE = os.path.join(WORKSPACE_DIR, "assets_cache", "module_phenotype_clusters.json")

import re

def extract_base_family(key_or_name: str) -> str:
    """提取模組基礎家族名，將變體與序號歸一化 (例如 Magicaltrailshader_48 -> magicaltrailshader)"""
    if not key_or_name:
        return ""
    clean = re.sub(r'(_\d+|\d+)$', '', str(key_or_name))
    clean = re.sub(r'(_fork|fork|dom|_dom|patchy|remix|_remix|gold|cenizasremix|bysculdy|cjkoedit|victor).*$', '', clean, flags=re.IGNORECASE)
    clean = clean.strip('_').lower()
    return clean if clean else str(key_or_name).lower()


class BanditInventorySelector:
    """
    基於「心靈語義本體論 (Expressive Ontology)」與情境多臂老虎機 (Contextual Bandit) 的智慧導演挑選器
    - 徹底告別單純次數倒排與粗暴隨機抽選
    - 依據樂段情境動態匹配「心靈狀態、象徵隱喻、敘事功能、OKLCH 色彩情感」
    - 採用 SemanticSoftProjector 消除冷門探索與剛性標籤的挑選死鎖
    - UCB (Upper Confidence Bound) 與探索紅利加持，最高優先級點名冷門、新入庫與剛修復的視覺模組
    - 全局香農熵帶寬動態約束 (2.6 <= H <= 3.6)
    - 具備家族級 (Family-level) 與視覺表現型簇群 (Phenotype Cluster) 去重抑制，防止變體換皮與同質畫面重複
    """

    def __init__(
        self, 
        exploration_weight: float = 1.35,
        decay_half_life_sec: float = 120.0,
        entropy_target_range: tuple = (2.6, 3.6)
    ):
        self.c = exploration_weight  # UCB 探索係數 (加強探索冷門資產)
        self.tau = decay_half_life_sec  # 疲勞恢復半衰期 (秒)
        self.entropy_min, self.entropy_max = entropy_target_range
        self.expressive_db = self._load_expressive_db()
        self.phenotype_clusters, self.module_to_cluster = self._load_phenotype_clusters()

    def _load_expressive_db(self) -> Dict[str, Any]:
        if os.path.exists(EXPRESSIVE_DB_FILE):
            try:
                with open(EXPRESSIVE_DB_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "modules" in data and isinstance(data["modules"], dict):
                    return data["modules"]
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        return {}

    def _load_phenotype_clusters(self) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
        clusters: Dict[str, List[str]] = {}
        mod_map: Dict[str, str] = {}
        if os.path.exists(PHENOTYPE_CLUSTERS_FILE):
            try:
                with open(PHENOTYPE_CLUSTERS_FILE, "r", encoding="utf-8") as f:
                    raw_clusters = json.load(f)
                for cluster_id, mod_list in raw_clusters.items():
                    # 若單一簇群超過 60 個模組（如通用 AST 雜湊桶），結合語義心靈狀態與原型進行細粒度二次分群，
                    # 防止單一巨型簇群一被選中就連坐壓制上千個不相關模組
                    if len(mod_list) > 60 and self.expressive_db:
                        for mod_key in mod_list:
                            prof = self.expressive_db.get(mod_key, {})
                            p_state = prof.get("primary_psychological_state", "gen")[:4]
                            p_arch = prof.get("primary_archetype", "arch")[:4]
                            p_func = prof.get("narrative_function", "fn")[:4]
                            sub_bucket = abs(hash(extract_base_family(mod_key))) % 8
                            refined_cid = f"{cluster_id[:8]}_{p_state}_{p_arch}_{p_func}_{sub_bucket}"
                            clusters.setdefault(refined_cid, []).append(mod_key)
                            mod_map[mod_key] = refined_cid
                    else:
                        clusters[cluster_id] = list(mod_list)
                        for mod_key in mod_list:
                            mod_map[mod_key] = cluster_id
            except Exception:
                pass
        return clusters, mod_map

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
        clean_mod_id = mod_id[:-5] if str(mod_id).endswith(".json") else str(mod_id)
        mod_name = str(module.get("name") or mod_id).strip()
        mod_fam = extract_base_family(mod_id)

        fam_used = int(module.get("_family_used_count", 0))
        name_used = int(module.get("_name_used_count", 0))
        raw_used = int(module.get("used_count", 0))
        used_count = max(raw_used, fam_used, name_used)

        is_original = bool(module.get("license") == "Original" or "AI Incubator" in str(module.get("author", "")))
        is_repaired = bool(module.get("restored") or module.get("is_repaired") or "repaired" in str(module.get("tags", [])))
        is_new_ingested = bool(module.get("is_new_semantic_ingested", False))

        profile = (
            module.get("expressive_profile")
            or self.expressive_db.get(mod_id)
            or self.expressive_db.get(clean_mod_id)
            or {}
        )

        sec_name = str(section_context.get("section", "Verse")).lower()
        genre = str(section_context.get("genre", "")).lower()
        tags = [str(t).lower() for t in module.get("tags", [])]

        # 1. 決定該樂段的目標心靈狀態與原型
        is_ambient_mode = "ambient" in genre or "drone" in genre
        is_hard_techno_mode = any(k in genre for k in ("hard_techno", "hard techno", "industrial", "schranz", "rave", "acid"))
        if is_ambient_mode:
            if "drop" in sec_name or "climax" in sec_name or "chorus" in sec_name:
                target_state = "sublime_catharsis"
                target_archetype = "the_self"
            elif "build" in sec_name or "pre" in sec_name:
                target_state = "hypnotic_trance"
                target_archetype = "the_self"
            else:
                target_state = "alienation_void"
                target_archetype = "the_void"
        else:
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

        # Ambient 門禁相容性審計與一票否決 (100% 阻斷 RED)
        if is_ambient_mode:
            from ambient_module_compatibility_gate import AmbientModuleCompatibilityGate
            if not hasattr(self, "_ambient_gate") or self._ambient_gate is None:
                self._ambient_gate = AmbientModuleCompatibilityGate()
            tier = module.get("ambient_tier") or self._ambient_gate.get_module_tier(clean_mod_id, module)
            if tier == "RED":
                return -9999.0  # 絕對隔離！非 Ambient 模組不得入選
            elif tier == "GREEN":
                semantic_affinity += 2.5  # 原生心流模組極致保送推薦
            elif tier == "YELLOW":
                semantic_affinity += 1.0  # 阻尼適配候選模組
        elif is_hard_techno_mode:
            from hard_techno_compatibility_gate import HardTechnoModuleCompatibilityGate
            if not hasattr(self, "_hard_techno_gate") or self._hard_techno_gate is None:
                self._hard_techno_gate = HardTechnoModuleCompatibilityGate.get_instance()
            tier = module.get("hard_techno_tier") or self._hard_techno_gate.get_module_tier(clean_mod_id, module)
            if tier == "RED":
                return -9999.0  # 絕對隔離！故障/不合適模組不得入選 Hard Techno
            elif tier == "GREEN":
                semantic_affinity += 1.25  # 硬核幾何/工業結構優先推薦
            elif tier == "YELLOW":
                semantic_affinity += 0.35

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

        # 4. 全局歷史使用次數嚴格懲罰 (使用越多，基礎收益越呈指數暴跌，杜絕常客霸榜)
        global_penalty = math.exp(-used_count * 1.5)

        # 5. UCB 冷門新穎性探索紅利 (次數越少，探索紅利越高！)
        N = max(1, global_total_picks)
        n_i = used_count
        ucb_bonus = self.c * math.sqrt(math.log(N + 1) / (n_i + 1))

        # 6. 新收錄、剛修復與從未亮相 (used_count == 0) 首秀探索激勵
        # 關鍵硬性防護：若該家族或同名模組已在歷史上亮相過，嚴禁發放首秀紅利！防止同模組多副本換皮吸分
        repair_bonus = 0.0
        if used_count == 0 and fam_used == 0 and name_used == 0:
            repair_bonus = 2.2  # 只有家族與名稱從未亮相過的真正全新庫存，才給予最高探索激勵！
        elif (is_repaired or is_new_ingested) and used_count <= 1:
            repair_bonus = 1.2

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
        
        # 預先統計全庫中各家族 (extract_base_family) 與顯示名稱 (name) 的全局已用次數
        family_counts: Dict[str, int] = {}
        name_counts: Dict[str, int] = {}
        for mod in available_modules:
            m_id = mod.get("_filename_key") or mod.get("name")
            m_fam = extract_base_family(m_id)
            m_name = str(mod.get("name") or m_id).strip()
            c = historical_counts.get(m_id, int(mod.get("used_count", 0)))
            if c > 0:
                if m_fam:
                    family_counts[m_fam] = family_counts.get(m_fam, 0) + c
                if m_name:
                    name_counts[m_name] = name_counts.get(m_name, 0) + c

        recent_timestamps: Dict[str, float] = {}
        assigned_history: List[str] = []
        assigned_families: List[str] = []
        assigned_names: List[str] = []
        assigned_clusters: List[str] = []
        global_picks = sum(historical_counts.values()) + 1

        genre_str = str(audio_telemetry.get("genre", "Electronic")).lower()
        is_ambient_genre = any(k in genre_str for k in ("ambient", "drone", "meditation"))
        # 🌿 Ambient 極簡一體性約束：全曲核心視覺模組數嚴格收斂至 1~2 款 (至多 3 款)，維持冥想沉浸心流
        max_ambient_distinct_modules = 2 if len(storyboard_sections) <= 7 else 3

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
                mod_name = str(mod.get("name") or mod_id).strip()
                mod_fam = extract_base_family(mod_id)

                mod_copy = dict(mod)
                mod_copy["used_count"] = historical_counts.get(mod_id, int(mod.get("used_count", 0)))
                mod_copy["_family_used_count"] = family_counts.get(mod_fam, 0)
                mod_copy["_name_used_count"] = name_counts.get(mod_name, 0)

                score = self.calculate_module_score(
                    module=mod_copy,
                    section_context=sec_context,
                    global_total_picks=global_picks,
                    current_time=simulated_time,
                    recent_used_timestamps=recent_timestamps
                )

                if is_ambient_genre:
                    # 🌿 Ambient 專用導演規則：
                    # 1. 粒子/星塵視覺偏好獎勵 (崇高靜謐心流)
                    mod_tags = [str(t).lower() for t in mod.get("tags", [])]
                    if any(t in mod_tags for t in ("particle", "particles", "ambient_particle")):
                        score *= 1.45

                    # 2. 全曲模組數嚴格收斂 (全曲僅使用 1~2 款核心視覺，至多 3 款，杜絕割裂)
                    distinct_chosen_ids = list(dict.fromkeys(assigned_history))
                    if len(distinct_chosen_ids) >= max_ambient_distinct_modules:
                        if mod_id not in distinct_chosen_ids:
                            score = 0.0  # 已達全曲上限，嚴禁引進新模組，強制在已選核心模組中複用演進
                    else:
                        # 尚未達上限時，平緩樂段鼓勵沿用上一模組以加深冥想心流
                        if assigned_history and mod_id == assigned_history[-1]:
                            score *= 1.6
                else:
                    # 1. 單曲模組全域無放回強約束 (Strict Non-replacement across the song)
                    # 徹底防護：只要 ID、顯示名稱 或 家族 曾在本曲中指派過，直接歸零排除！
                    if len(available_modules) >= len(storyboard_sections):
                        if mod_id in assigned_history or mod_name in assigned_names:
                            score = 0.0  # 單曲內同 ID 與同名模組絕對不重複
                        elif mod_fam and mod_fam in assigned_families:
                            score = 0.0  # 單曲內同家族不同變體副本亦絕對排除
                    else:
                        times_in_song = assigned_history.count(mod_id) + assigned_names.count(mod_name)
                        if times_in_song > 0:
                            score *= (0.001 ** times_in_song)
                        if assigned_history and (assigned_history[-1] == mod_id or assigned_names[-1] == mod_name):
                            score *= 0.0001
                        if mod_fam and mod_fam in assigned_families:
                            score *= 0.001

                    # 2. 模組家族去重約束 (Family-level Deduplication)
                    if mod_fam:
                        fam_times = assigned_families.count(mod_fam)
                        if fam_times > 0:
                            score = 0.0

                    # 3. 視覺表現型簇群去重約束 (Phenotype Cluster Divergence, M3.2)
                    # 防止即使家族名不同，但視覺形態（如都是高頻粒子或都是流體）連續出現在相鄰分鏡
                    clean_mid = mod_id[:-5] if str(mod_id).endswith(".json") else str(mod_id)
                    mod_cluster = self.module_to_cluster.get(mod_id) or self.module_to_cluster.get(clean_mid)
                    if mod_cluster and assigned_clusters:
                        # 若上一分鏡屬於同一視覺形態，施加 80% 降權以保證相鄰分鏡視覺反差感
                        if assigned_clusters[-1] == mod_cluster:
                            score *= 0.20
                        # 若全曲中同一形態已出現 >= 3 次，進一步降權促使風格輪替
                        c_count = assigned_clusters.count(mod_cluster)
                        if c_count >= 3:
                            score *= (0.5 ** c_count)

                score *= random.uniform(0.96, 1.04)
                scored_candidates.append((score, mod_copy))

            # 若非零候選存在，僅保留非零項
            non_zero_candidates = [c for c in scored_candidates if c[0] > 0]
            pool_to_pick = non_zero_candidates if non_zero_candidates else scored_candidates
            pool_to_pick.sort(key=lambda x: x[0], reverse=True)

            # 擴大 top_k 候選池至 15~20 個，提高採樣隨機多樣性與探索深度
            top_k_size = min(15, len(pool_to_pick))
            top_k = pool_to_pick[:top_k_size]
            scores = [item[0] for item in top_k]
            total_s = sum(scores)
            probs = [s / total_s for s in scores] if total_s > 0 else None

            chosen_mod = random.choices([item[1] for item in top_k], weights=probs, k=1)[0]
            chosen_id = chosen_mod.get("_filename_key") or chosen_mod.get("name")
            clean_chosen_id = chosen_id[:-5] if str(chosen_id).endswith(".json") else str(chosen_id)
            chosen_name = str(chosen_mod.get("name") or chosen_id).strip()
            chosen_fam = extract_base_family(chosen_id)
            chosen_cluster = self.module_to_cluster.get(chosen_id) or self.module_to_cluster.get(clean_chosen_id)

            recent_timestamps[chosen_id] = simulated_time
            historical_counts[chosen_id] = historical_counts.get(chosen_id, 0) + 1
            if chosen_fam:
                family_counts[chosen_fam] = family_counts.get(chosen_fam, 0) + 1
            if chosen_name:
                name_counts[chosen_name] = name_counts.get(chosen_name, 0) + 1

            assigned_history.append(chosen_id)
            if chosen_name:
                assigned_names.append(chosen_name)
            if chosen_fam:
                assigned_families.append(chosen_fam)
            if chosen_cluster:
                assigned_clusters.append(chosen_cluster)
            global_picks += 1

            profile = (
                chosen_mod.get("expressive_profile")
                or self.expressive_db.get(chosen_id)
                or self.expressive_db.get(clean_chosen_id)
                or {}
            )

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

        # 全局香農熵帶寬動態約束 (self.entropy_min <= H <= self.entropy_max)
        entropy = self.calculate_shannon_entropy(assigned_history)
        if not is_ambient_genre and len(results) >= 4 and len(available_modules) > len(results):
            effective_min_h = min(self.entropy_min, math.log2(len(results)) * 0.92)
            if entropy < effective_min_h:
                # 找出重複指派的分鏡並替換為未使用高分候選以拉升香農熵至目標區間
                seen_ids = set()
                unused_mods = [
                    m for m in available_modules
                    if (m.get("_filename_key") or m.get("name")) not in assigned_history
                ]
                for idx_r, r_item in enumerate(results):
                    mid = r_item["assigned_module_id"]
                    if mid in seen_ids and unused_mods:
                        alt_mod = unused_mods.pop(0)
                        alt_id = alt_mod.get("_filename_key") or alt_mod.get("name")
                        clean_alt = alt_id[:-5] if str(alt_id).endswith(".json") else str(alt_id)
                        alt_prof = alt_mod.get("expressive_profile") or self.expressive_db.get(alt_id) or self.expressive_db.get(clean_alt) or {}
                        r_item["assigned_module_id"] = alt_id
                        r_item["module_name"] = alt_mod.get("name")
                        r_item["psychological_state"] = alt_prof.get("primary_psychological_state", r_item["psychological_state"])
                        assigned_history[idx_r] = alt_id
                    seen_ids.add(r_item["assigned_module_id"])
                entropy = self.calculate_shannon_entropy(assigned_history)

        logger.info(
            f"✨ 語義心靈編排完成：全曲 {len(results)} 個分鏡，審美香農熵: {entropy:.2f} "
            f"(目標帶寬: [{self.entropy_min:.2f}, {self.entropy_max:.2f}])"
        )

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
