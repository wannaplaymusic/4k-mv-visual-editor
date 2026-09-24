import logging
from .scenario_maestro import ScenarioMaestro

logger = logging.getLogger("VisualStudio.CreationWizard")

class CreationWizard:
    """
    視界引導精靈 (Creation Wizard)
    - 5 步闖關狀態機 (Five-Step Finite State Machine)
    - 非破壞性時間旅行 (Non-destructive Step Travel)
    - 管理各階段配置快照與選項推薦
    - 與 ScenarioMaestro 協同工作
    """

    STEPS = [
        {"step": 1, "id": "mood_anchor", "name": "氣質定錨", "desc": "確立音樂流派、氛圍基調與和聲色彩風格"},
        {"step": 2, "id": "geometry_math", "name": "幾何骨架", "desc": "選擇空間拓撲、物理運動動力學與主體形態"},
        {"step": 3, "id": "audio_reactivity", "name": "聲畫通感", "desc": "配置大鼓重低音、和弦漂移與高頻閃爍映射"},
        {"step": 4, "id": "shader_aesthetics", "name": "光影質感", "desc": "掛接 GPU 著色器機架（體積光、色散、反應擴散）"},
        {"step": 5, "id": "qc_and_publish", "name": "驗收收編", "desc": "4K 60FPS 審計、曲式標籤評分與一鍵入庫發布"}
    ]

    def __init__(self, maestro: ScenarioMaestro = None):
        self.maestro = maestro or ScenarioMaestro()
        self.current_step = 1
        self.session_data = {
            "mood": None,
            "genre": None,
            "topology": None,
            "audio_bindings": {
                "sub_bass": "scale",
                "bass": "jitter",
                "mid": "color_drift",
                "high": "sparkle"
            },
            "active_shaders": [],
            "module_name": "New_Visual_Module",
            "code": ""
        }
        self.step_snapshots = {}

    def get_current_step_info(self) -> dict:
        return self.STEPS[self.current_step - 1]

    def go_to_step(self, step_number: int) -> dict:
        if 1 <= step_number <= len(self.STEPS):
            self.current_step = step_number
        return self.get_current_step_info()

    def next_step(self) -> dict:
        if self.current_step < len(self.STEPS):
            self.current_step += 1
        return self.get_current_step_info()

    def prev_step(self) -> dict:
        if self.current_step > 1:
            self.current_step -= 1
        return self.get_current_step_info()

    def get_step_options(self) -> dict:
        """
        獲取當前步驟可供用戶點選的卡片式選項
        """
        if self.current_step == 1:
            return {
                "title": "步驟 1：選擇音樂流派與氛圍基調",
                "genres": self.maestro.GENRES,
                "moods": self.maestro.MOODS
            }
        elif self.current_step == 2:
            return {
                "title": "步驟 2：挑選幾何拓撲與動態骨架",
                "topologies": self.maestro.MATHEMATICAL_TOPOLOGIES
            }
        elif self.current_step == 3:
            return {
                "title": "步驟 3：配置聲畫聯覺通感矩陣",
                "frequency_bands": [
                    {
                        "band": "Sub-bass (重低音 / 大鼓)",
                        "options": ["中心爆炸衝擊 (Radial Shockwave)", "幾何整體縮放 (Global Scale Pulse)", "空間扭曲 (Spatial Warp)"]
                    },
                    {
                        "band": "Mid (中頻旋律 / 和弦)",
                        "options": ["五度圈 HSL 色彩漂移 (Harmonic Hue Drift)", "流場旋轉速度 (Angular Velocity)", "多面體相位形變 (Phase Morph)"]
                    },
                    {
                        "band": "High (高頻踩鑔 / 砂槌)",
                        "options": ["粒子細微閃爍與光芒 (Sparkle & Jitter)", "線條粗細激化 (Stroke Thickness)", "高頻噪聲震顫 (Glitch Shiver)"]
                    }
                ]
            }
        elif self.current_step == 4:
            return {
                "title": "步驟 4：為畫面加載電影級 GLSL 著色器外掛",
                "shader_presets": [
                    {"id": "volumetric_godrays", "name": "體積丁達爾神光 (Godrays)", "desc": "耀眼的光芒自中心穿透粒子"},
                    {"id": "chromatic_aberration", "name": "光學色散與膠片感 (RGB Split)", "desc": "重音時產生紅青邊緣色差與顆粒"},
                    {"id": "reaction_diffusion", "name": "反應擴散回授 (Feedback)", "desc": "動態有機殘影擴散流動"},
                    {"id": "matrix_glitch_mosaic", "name": "數位矩陣故障 (Glitch)", "desc": "賽博龐克數位信號位移"}
                ]
            }
        else:
            return {
                "title": "步驟 5：品質自檢、曲式適配與入庫發布",
                "suggested_name": self.session_data.get("module_name", "Visual_Module"),
                "auto_qc_checks": [
                    "4K 渲染管線 60FPS 平滑度檢測",
                    "黑畫面 (Black Screen) 盲區審計",
                    "Walter Murch 曲式結構契合度打標"
                ]
            }

    def compile_step_code(self) -> str:
        """
        根據當前累積的 session_data 自動編譯代碼
        """
        genre_id = self.session_data.get("genre", "synthwave")
        topo_id = self.session_data.get("topology", "lorenz_attractor")

        spec = self.maestro.generate_rigid_spec(f"{topo_id} {genre_id}", target_genre=genre_id)
        code = self.maestro.synthesize_p5_code(spec)
        self.session_data["code"] = code
        return code
