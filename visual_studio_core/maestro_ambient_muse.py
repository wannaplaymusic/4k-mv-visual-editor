import time
import random
import logging

logger = logging.getLogger("VisualStudio.MaestroAmbientMuse")

class MaestroAmbientMuse:
    """
    心流守護者：靈感微光主動救場機制 (Ambient Muse)
    - 檢測創作者在同一界面的猶豫、反覆切換或長時間停頓
    - 在適當時機以非侵入式（Non-intrusive）呼吸微光提供破局靈感
    - 絕不彈窗阻斷，隨叫隨到，心流守護
    """

    MUSE_SUGGESTIONS = [
        "💡 似乎在猶豫幾何形態？試試將【Curl Noise 渦流】與【體積神光】疊加，能營造出夢幻星塵感。",
        "💡 當前音律重低音豐滿，若為 Sub-bass 掛接【反應擴散回授 (Reaction Diffusion)】，會有強烈的液態呼吸感。",
        "💡 想要在副歌高潮 (Drop) 達到極限衝擊嗎？嘗試拉高【幾何混沌度】並開啟【膠片色散】！",
        "💡 嘗試將色彩飽和度稍作降低，讓背景留白更多，能營造出北歐禪意極簡的空靈美感。",
        "💡 如果當前視覺偏向規則幾何，開啟【數位矩陣故障 (Glitch)】可瞬間打破死板，注入賽博龐克張力。"
    ]

    def __init__(self, idle_threshold_seconds: float = 35.0):
        self.idle_threshold = idle_threshold_seconds
        self.last_action_time = time.time()
        self.action_counter = 0
        self.is_hint_active = False

    def touch_action(self):
        """創作者有操作時重置計時器"""
        self.last_action_time = time.time()
        self.action_counter += 1
        self.is_hint_active = False

    def poll_for_muse_hint(self) -> str:
        """
        輪詢檢查是否應浮現靈感微光提示
        """
        now = time.time()
        idle_duration = now - self.last_action_time

        # 停頓超過閾值且尚未提示
        if idle_duration > self.idle_threshold and not self.is_hint_active:
            self.is_hint_active = True
            return random.choice(self.MUSE_SUGGESTIONS)

        return None
