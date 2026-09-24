import os
import json
import logging
from collections import Counter

logger = logging.getLogger("VisualStudio.MaestroTasteProfiler")

class MaestroTasteProfiler:
    """
    創作者專屬口味圖譜與審美記憶庫 (Creator Taste Profiler)
    - 追蹤並持久化創作者的審美偏好 (creator_taste_profile.json)
    - 學習正向收編（Published/Starred）與負向跳過（Skipped/Rejected）行為
    - 保留 20% 驚喜探索因子 (Serendipity Factor)，防止風格固化
    - 為 ScenarioMaestro 提供個人化機率加權
    """

    def __init__(self, workspace_dir: str = None):
        self.workspace_dir = workspace_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.profile_path = os.path.join(self.workspace_dir, "creator_taste_profile.json")
        self.profile_data = self._load_profile()

    def _load_profile(self) -> dict:
        default_profile = {
            "version": "2.0",
            "total_creations": 0,
            "topology_weights": {},
            "shader_weights": {},
            "genre_weights": {},
            "color_preferences": {
                "dark_background_ratio": 0.9,
                "preferred_hues": [195, 270, 320]  # 預設青、紫、品紅
            },
            "recent_published": []
        }
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_profile.update(data)
            except Exception as e:
                logger.warning(f"Failed to read taste profile, using default: {e}")
        return default_profile

    def save_profile(self):
        try:
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.profile_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save creator taste profile: {e}")

    def record_published_module(self, name: str, topology_id: str, genre_id: str, active_shaders: list = None):
        """創作者發布入庫：強正向權重激勵"""
        self.profile_data["total_creations"] += 1

        # 1. 拓撲權重 +3
        if topology_id:
            w = self.profile_data["topology_weights"].get(topology_id, 0)
            self.profile_data["topology_weights"][topology_id] = w + 3

        # 2. 流派權重 +2
        if genre_id:
            w = self.profile_data["genre_weights"].get(genre_id, 0)
            self.profile_data["genre_weights"][genre_id] = w + 2

        # 3. 著色器權重 +2
        if active_shaders:
            for s in active_shaders:
                sid = s.get("id") if isinstance(s, dict) else str(s)
                w = self.profile_data["shader_weights"].get(sid, 0)
                self.profile_data["shader_weights"][sid] = w + 2

        # 4. 記錄最近入庫
        self.profile_data["recent_published"].insert(0, {
            "name": name,
            "topology": topology_id,
            "genre": genre_id
        })
        self.profile_data["recent_published"] = self.profile_data["recent_published"][:20]
        self.save_profile()
        logger.info(f"Updated taste profile for published module: {name}")

    def record_rejected_choice(self, item_type: str, item_id: str):
        """創作者快速刷掉或跳過：輕微負向權重"""
        weights_key = f"{item_type}_weights"
        if weights_key in self.profile_data:
            w = self.profile_data[weights_key].get(item_id, 0)
            self.profile_data[weights_key][item_id] = max(-5, w - 1)
            self.save_profile()

    def get_weighted_choice(self, candidates: list, item_type: str, serendipity: float = 0.20):
        """
        結合創作者歷史偏好進行加權抽樣（保留 serendipity 探索機率）
        """
        import random
        if not candidates:
            return None

        # 20% 機率直接純隨機探索，防止審美固化
        if random.random() < serendipity or not self.profile_data.get(f"{item_type}_weights"):
            return random.choice(candidates)

        weights_dict = self.profile_data.get(f"{item_type}_weights", {})
        scored_candidates = []
        for c in candidates:
            cid = c.get("id") if isinstance(c, dict) else str(c)
            # 基準分 5 分 + 歷史正向權重
            score = max(1, 5 + weights_dict.get(cid, 0))
            scored_candidates.append(score)

        return random.choices(candidates, weights=scored_candidates, k=1)[0]

    def get_taste_summary(self) -> str:
        """回傳創作者審美口味簡述"""
        if self.profile_data["total_creations"] == 0:
            return "尚在建立專屬審美檔案（探索階段）"

        top_topo = Counter(self.profile_data["topology_weights"]).most_common(1)
        top_genre = Counter(self.profile_data["genre_weights"]).most_common(1)
        top_sh = Counter(self.profile_data["shader_weights"]).most_common(1)

        t_str = top_topo[0][0] if top_topo else "多元"
        g_str = top_genre[0][0] if top_genre else "多元"
        s_str = top_sh[0][0] if top_sh else "全光譜"

        return f"偏好【{g_str}】氛圍，熱衷【{t_str}】拓撲，常配【{s_str}】著色器（已創作 {self.profile_data['total_creations']} 件）"
