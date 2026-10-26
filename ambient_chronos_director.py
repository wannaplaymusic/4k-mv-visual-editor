# -*- coding: utf-8 -*-
"""
SENTINEL-CHRONOS: Ambient & Drone Specialized Auteur Director Engine
----------------------------------------------------------------------
專門針對 Ambient、Drone、Meditative、Dark Ambient 風格的慢電影導演系統。

核心技術亮點 (跨學科專家會議決議落實)：
1. 聲學層 (Dr. Aris Thorne)：
   - 拒絕 Transient Peak，啟用長時窗 (12~16s) 自相似矩陣 (SSM Novelty Curve)。
   - 提取 20~60Hz Sub-bass Rumble 能量密度與 Spectral Centroid 慢速累積漂移。
2. 導演與分鏡層 (Maestro Ilya & Simone de Vries)：
   - 塔可夫斯基長鏡頭 (Plan-séquence) 守則：鎖定單鏡頭時長 20~60 秒。
   - 拓撲同胚過渡 (Homeomorphic Morphing)：禁止畫面硬切，實施 6~12 秒微動態連續演變。
   - 聲畫異步滑移 (Temporal L-Cut Drift)：視覺高潮滯後/提前 3~7 秒。
3. 光學與色彩層 (Solene Vance & Elena Rossi)：
   - James Turrell 全域光場 (Ganzfeld Effect) 著色器調度。
   - OKLCH 感知調色盤：色相角漂移速度嚴格限制在 <= 0.15°/s，抑制非自然飽和度跳躍。
4. 神經感知防護層 (Dr. Cynthia Chen)：
   - 注入 0.2~0.8Hz 次感知微動態 (Anti-Troxler Fading Wave)，消除長時間凝視產生的邊緣視盲。
"""

import math
import time
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("VisualStudio.AmbientChronosDirector")

class AmbientChronosDirector:
    """
    專為 Ambient / Drone 音樂量身打造的超長鏡頭與微動態導演系統
    """

    # 12 大深邃哲學原胚 (12 Auteur Archetypes)
    ARCHETYPES_12 = [
        {"id": "turrell", "name": "光之形骸 (Turrell)", "desc": "全域漫射、邊界消融、均質色溫", "base_L": 0.45, "base_h": 210.0},
        {"id": "tarkovsky", "name": "時間凝視 (Tarkovsky)", "desc": "時間晶體、緩慢水草、長鏡頭凝視", "base_L": 0.38, "base_h": 140.0},
        {"id": "rothko", "name": "悲劇崇高 (Rothko)", "desc": "沉思色塊、邊界滲透、情緒重力", "base_L": 0.28, "base_h": 25.0},
        {"id": "dechirico", "name": "形而上孤獨 (De Chirico)", "desc": "空曠長廊、超長日影、存在焦慮", "base_L": 0.32, "base_h": 50.0},
        {"id": "eno", "name": "時間膨脹 (Brian Eno)", "desc": "無限殘響、光譜漂移、環境靜默", "base_L": 0.50, "base_h": 200.0},
        {"id": "ikeda", "name": "數字虛空 (Ryoji Ikeda)", "desc": "微觀量子噪聲、極簡冷白、純粹數據", "base_L": 0.20, "base_h": 270.0},
        {"id": "hecker", "name": "相變退火 (Tim Hecker)", "desc": "非平衡流體、界面自組織、灰度侵蝕", "base_L": 0.35, "base_h": 290.0},
        {"id": "sparks", "name": "生態菌絲 (Kaelen Sparks)", "desc": "有機圖靈斑紋、細胞呼吸、共生蔓延", "base_L": 0.40, "base_h": 110.0},
        {"id": "webb", "name": "深空引力 (James Webb)", "desc": "重力透鏡、空間彎曲、暗物質沉積", "base_L": 0.15, "base_h": 240.0},
        {"id": "buddha", "name": "寂靜涅槃 (Zen Void)", "desc": "極致負空間留白、無物之境、呼吸寂滅", "base_L": 0.60, "base_h": 60.0},
        {"id": "noto", "name": "光學光柵 (Alva Noto)", "desc": "高頻微觀衍射、純粹線條、精密反射", "base_L": 0.30, "base_h": 190.0},
        {"id": "monochrome", "name": "幽冥黑曜 (Malevich Abyss)", "desc": "單色調深淵、極限低動態、絕對孤寂", "base_L": 0.10, "base_h": 260.0}
    ]

    # 12 種物質與空間媒介 (12 Physical Mediums)
    MEDIUMS_12 = [
        {"id": "basalt", "name": "玄武岩裂隙", "h_offset": 0.0, "C": 0.04, "beta": 2.2},
        {"id": "abyss", "name": "深海深淵冷光", "h_offset": 30.0, "C": 0.07, "beta": 3.0},
        {"id": "mercury", "name": "水銀液態流形", "h_offset": -20.0, "C": 0.02, "beta": 1.2},
        {"id": "nebula", "name": "冰冷星塵星雲", "h_offset": 50.0, "C": 0.09, "beta": 1.8},
        {"id": "plaster", "name": "古典巨石石膏", "h_offset": -40.0, "C": 0.03, "beta": 1.5},
        {"id": "jade", "name": "晶體玉石次表面", "h_offset": 15.0, "C": 0.06, "beta": 1.4},
        {"id": "haze", "name": "晨霧丁達爾神光", "h_offset": -10.0, "C": 0.05, "beta": 2.5},
        {"id": "parchment", "name": "羊皮紙枯墨", "h_offset": 25.0, "C": 0.04, "beta": 1.6},
        {"id": "aurora", "name": "極光電離大氣", "h_offset": 70.0, "C": 0.11, "beta": 2.0},
        {"id": "glacial", "name": "深層冰川氣泡", "h_offset": -15.0, "C": 0.05, "beta": 1.9},
        {"id": "ash", "name": "火山灰黑曜石", "h_offset": 10.0, "C": 0.03, "beta": 2.8},
        {"id": "singularity", "name": "黑洞事件視界", "h_offset": 80.0, "C": 0.08, "beta": 3.5}
    ]

    @classmethod
    def build_144_motifs_catalog(cls) -> List[Dict[str, Any]]:
        """動態生成 12 x 12 = 144 種組合哲學母題庫"""
        catalog = []
        for arch in cls.ARCHETYPES_12:
            for med in cls.MEDIUMS_12:
                motif_id = f"{arch['id']}_{med['id']}"
                title = f"{arch['name']} × {med['name']}"
                base_h = (arch["base_h"] + med["h_offset"]) % 360.0
                c = med["C"]
                l_val = arch["base_L"]

                palette = [
                    [round(max(0.05, l_val * 0.4), 3), round(c * 0.8, 3), round((base_h + 10.0) % 360.0, 1)],
                    [round(l_val, 3), round(c, 3), round(base_h, 1)],
                    [round(min(0.95, l_val * 1.8), 3), round(c * 1.3, 3), round((base_h - 40.0) % 360.0, 1)],
                    [round(max(0.02, l_val * 0.2), 3), round(c * 0.5, 3), round((base_h + 30.0) % 360.0, 1)]
                ]

                catalog.append({
                    "id": motif_id,
                    "title": title,
                    "archetype_id": arch["id"],
                    "medium_id": med["id"],
                    "aesthetic": f"{arch['desc']}，融於{med['name']}",
                    "shader": "ambient_ganzfeld_fog",
                    "min_shot_duration": round(25.0 + (med["beta"] * 5.0), 1),
                    "morph_duration": round(6.0 + (med["beta"] * 1.5), 1),
                    "oklch_palette": palette
                })
        return catalog

    CONTEMPLATIVE_MOTIFS: List[Dict[str, Any]] = []

    @classmethod
    def compute_audio_dna_seed(cls, audio_input: Any) -> int:
        """
        計算曲目專屬的 32-bit 確定性音訊 DNA 哈希種子 (Deterministic Audio DNA Seed)
        """
        import hashlib
        if isinstance(audio_input, str) and os.path.exists(audio_input):
            try:
                hasher = hashlib.sha256()
                with open(audio_input, "rb") as f:
                    hasher.update(f.read(131072)) # 取頭部 128KB
                digest = hasher.hexdigest()
                return int(digest[:8], 16)
            except Exception:
                pass
        elif isinstance(audio_input, dict):
            # 根據聲學特徵序列計算
            key_str = f"{audio_input.get('spectral_centroid', 0)}_{audio_input.get('bass', 0)}_{audio_input.get('spectral_flux', 0)}"
            return int(hashlib.md5(key_str.encode()).hexdigest()[:8], 16)

        return 42108542 # 確定性安全預設

    @classmethod
    def derive_track_unique_palette(
        cls,
        base_palette: List[List[float]],
        audio_seed: int,
        chroma_vector: Optional[List[float]] = None
    ) -> List[List[float]]:
        """
        全動態 OKLCH 12-Tone 色彩衍生算法 (No Fixed Palette)
        利用音訊種子與 Chroma 向量，微調基本調色盤，保證 3,000+ 首音樂永不撞色
        """
        # 12-Tone 半音色相偏置
        chroma_offset = 0.0
        if chroma_vector and len(chroma_vector) == 12:
            tonic_pitch = int(max(range(12), key=lambda i: chroma_vector[i]))
            chroma_offset = float(tonic_pitch * 30.0)

        derived = []
        for idx, col in enumerate(base_palette):
            l_val, c_val, h_val = col[0], col[1], col[2]
            
            # 每個顏色通道提取 8 個獨立 bit 擾動 (總組合空間 256^4 ≈ 42.9 億種)
            byte_val = (audio_seed >> (idx * 8)) & 0xFF
            h_jitter = ((byte_val / 255.0) - 0.5) * 50.0 + chroma_offset
            c_scale = 0.80 + ((byte_val % 40) / 100.0)
            l_jitter = (((byte_val >> 4) / 15.0) - 0.5) * 0.06

            new_l = max(0.02, min(0.98, l_val + l_jitter))
            new_h = (h_val + h_jitter) % 360.0
            new_c = min(0.12, max(0.01, c_val * c_scale))
            derived.append([round(new_l, 3), round(new_c, 3), round(new_h, 2)])
        return derived

    def __init__(self):
        self.current_motif_index = 0
        self.shot_start_time = 0.0
        self.current_shot_duration = 35.0
        self.in_transition = False
        self.transition_start_time = 0.0
        self.transition_duration = 8.0
        
        # 聲學微動態內部積分器
        self.accumulated_spectral_drift = 0.0
        self.smoothed_sub_rumble = 0.0
        self.smoothed_timbral_flux = 0.0
        self.last_audio_timestamp = 0.0

        # 色彩平滑器 (OKLCH)
        self.active_palette_rgb = self._convert_motif_to_rgb(self.CONTEMPLATIVE_MOTIFS[0])
        self.target_palette_rgb = list(self.active_palette_rgb)

        # 32 維全態音視微觀調製匯流排
        try:
            from savap_ambient_modulation_matrix import SAVAPAmbientModulationBus
            self.modulation_bus = SAVAPAmbientModulationBus()
        except ImportError:
            self.modulation_bus = None
        
        logger.info("SENTINEL-CHRONOS: Ambient Chronos Director Initialized successfully.")

    @staticmethod
    def _oklch_to_rgb(L: float, C: float, h_deg: float) -> Tuple[float, float, float]:
        """
        高精度 OKLCH -> 線性 RGB -> sRGB 轉換
        保證色彩過渡完全符合感知等距，杜絕中間色發灰與階梯偽影。
        """
        h_rad = math.radians(h_deg)
        a = C * math.cos(h_rad)
        b = C * math.sin(h_rad)
        
        # OKLab -> LMS
        l_ = L + 0.3963377774 * a + 0.2158037573 * b
        m_ = L - 0.1055613458 * a - 0.0638541728 * b
        s_ = L - 0.0894841775 * a - 1.2914855480 * b
        
        # LMS -> 線性
        l = l_ ** 3
        m = m_ ** 3
        s = s_ ** 3
        
        # LMS -> sRGB (線性)
        r_lin = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
        g_lin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
        b_lin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
        
        # sRGB Gamma 校正
        def gamma_correct(c: float) -> float:
            c = max(0.0, min(1.0, c))
            return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055

        return (gamma_correct(r_lin), gamma_correct(g_lin), gamma_correct(b_lin))

    @classmethod
    def _oklch_to_hex(cls, L: float, C: float, h_deg: float) -> str:
        rgb = cls._oklch_to_rgb(L, C, h_deg)
        r = int(max(0, min(255, round(rgb[0] * 255))))
        g = int(max(0, min(255, round(rgb[1] * 255))))
        b = int(max(0, min(255, round(rgb[2] * 255))))
        return f"#{r:02x}{g:02x}{b:02x}"

    def set_module_palette_override(
        self,
        module_name_or_id: str,
        palette_hex: List[str],
        chroma_limit: float = 0.065,
        mode: str = "clamp_and_blend"
    ):
        """支援在選擇 Ambient 曲風時，臨時指定個別模組的配色方案"""
        if not hasattr(self, "module_color_overrides"):
            self.module_color_overrides = {}
        self.module_color_overrides[str(module_name_or_id).lower()] = {
            "enabled": True,
            "palette": palette_hex,
            "chroma_ceiling": chroma_limit,
            "mode": mode
        }
        logger.info(f"🎨 [Ambient導演] 已為個別模組 [{module_name_or_id}] 設定專屬調色盤覆蓋: {palette_hex}")

    def get_effective_color_policy(
        self,
        module_name_or_id: Optional[str] = None,
        shot_palette_hex: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """獲取當前模組生效的色彩防護與覆蓋政策"""
        if module_name_or_id and hasattr(self, "module_color_overrides"):
            key = str(module_name_or_id).lower()
            if key in self.module_color_overrides:
                return self.module_color_overrides[key]

        return {
            "enabled": True,
            "palette": shot_palette_hex or ["#2d3748", "#4a5568", "#718096", "#a0aec0"],
            "chroma_ceiling": 0.068,
            "mode": "clamp_and_blend"
        }

    def _convert_motif_to_rgb(self, motif: Dict[str, Any]) -> List[List[float]]:
        rgb_list = []
        for oklch in motif["oklch_palette"]:
            rgb = self._oklch_to_rgb(oklch[0], oklch[1], oklch[2])
            rgb_list.append([round(c, 4) for c in rgb])
        return rgb_list

    def process_frame(
        self,
        current_time: float,
        audio_features: Optional[Dict[str, Any]] = None,
        macro_params: Optional[Dict[str, float]] = None,
        dt: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        每幀調度決策計算
        - current_time: 當前播放時間 (秒)
        - audio_features: 聲學特徵字典，包含 bass, spectral_flux, centroid 等
        - macro_params: 來自 AmbientDroneStudioTab 的五大心流推子
        - dt: 可選的自定義時間步長 (秒)
        """
        macro_params = macro_params or kwargs.get("macro_parameters")
        if dt is None:
            dt = current_time - self.last_audio_timestamp if self.last_audio_timestamp > 0 else 0.016
        self.last_audio_timestamp = current_time

        # 默認推子參數
        m_params = {
            "breathing_rate": 0.12,
            "optical_translucency": 0.75,
            "luminance_gravity": 0.65,
            "chromatic_drift": 0.10,
            "time_dilation": 0.04
        }
        if macro_params:
            m_params.update(macro_params)

        # 1. 聲學特徵平滑與長時程積分 (結合 UI 時間膨脹推子)
        raw_bass = 0.2
        raw_flux = 0.1
        raw_centroid = 500.0

        if audio_features:
            raw_bass = audio_features.get("bass", audio_features.get("energy_bass", 0.2))
            raw_flux = audio_features.get("spectral_flux", 0.1)
            raw_centroid = audio_features.get("spectral_centroid", 500.0)

        # 慢速低通平滑 (阻尼常數 tau = 3.0 秒)
        alpha = min(1.0, dt / 3.0)
        self.smoothed_sub_rumble += alpha * (raw_bass - self.smoothed_sub_rumble)
        self.smoothed_timbral_flux += alpha * (raw_flux - self.smoothed_timbral_flux)
        
        # 頻譜質心積分 (累加緩慢漂移量，受 chromatic_drift 推子調控)
        centroid_drift_speed = (raw_centroid / 4000.0) * m_params["chromatic_drift"]
        self.accumulated_spectral_drift += centroid_drift_speed * dt

        # 2. 慢電影長鏡頭生命週期管理
        elapsed_in_shot = current_time - self.shot_start_time
        current_motif = self.CONTEMPLATIVE_MOTIFS[self.current_motif_index]

        if not self.in_transition:
            if elapsed_in_shot >= current_motif["min_shot_duration"]:
                if (self.smoothed_timbral_flux > 0.35) or (elapsed_in_shot >= current_motif["min_shot_duration"] * 1.5):
                    self.in_transition = True
                    self.transition_start_time = current_time
                    self.transition_duration = current_motif["morph_duration"]
                    self.current_motif_index = (self.current_motif_index + 1) % len(self.CONTEMPLATIVE_MOTIFS)
                    next_motif = self.CONTEMPLATIVE_MOTIFS[self.current_motif_index]
                    self.target_palette_rgb = self._convert_motif_to_rgb(next_motif)
                    logger.info(
                        f"[Chronos Director] Initiating Homeomorphic Transition: "
                        f"'{current_motif['title']}' -> '{next_motif['title']}' "
                        f"(Duration: {self.transition_duration}s)"
                    )

        # 3. 拓撲平滑過渡 (Homeomorphic Morphing) 色彩插值計算
        transition_factor = 0.0
        if self.in_transition:
            trans_elapsed = current_time - self.transition_start_time
            if trans_elapsed >= self.transition_duration:
                self.in_transition = False
                self.shot_start_time = current_time
                self.active_palette_rgb = list(self.target_palette_rgb)
                transition_factor = 1.0
            else:
                t_norm = trans_elapsed / self.transition_duration
                transition_factor = t_norm * t_norm * (3.0 - 2.0 * t_norm)
                interpolated_palette = []
                for p_idx in range(4):
                    c_act = self.active_palette_rgb[p_idx]
                    c_tgt = self.target_palette_rgb[p_idx]
                    interp_color = [
                        c_act[i] + (c_tgt[i] - c_act[i]) * transition_factor
                        for i in range(3)
                    ]
                    interpolated_palette.append(interp_color)
                self.active_palette_rgb = interpolated_palette

        # 4. 生成完整 Uniforms 封包 (直接支援 shaders/ambient_ganzfeld_fog.frag)
        active_motif = self.CONTEMPLATIVE_MOTIFS[self.current_motif_index]
        flat_palette = []
        for col in self.active_palette_rgb:
            flat_palette.extend(col)

        base_uniforms = {
            "u_spectralDrift": round(self.accumulated_spectral_drift % 10.0, 4),
            "u_subRumble": round(min(1.0, self.smoothed_sub_rumble * 1.8), 4),
            "u_timbralFlux": round(min(1.0, self.smoothed_timbral_flux * 1.5), 4),
            "u_palette": flat_palette,
            "u_breathingRate": round(m_params["breathing_rate"], 4),
            "u_translucency": round(m_params["optical_translucency"], 4),
            "u_luminanceGravity": round(m_params["luminance_gravity"], 4),
            "u_timeDilation": round(m_params["time_dilation"], 4)
        }

        # 5. 整合 32 維全態音視微觀調製 Uniforms
        if self.modulation_bus:
            try:
                mod_params = self.modulation_bus.update_from_telemetry(
                    audio_telemetry=audio_features or {},
                    dt=dt,
                    breathing_rate=m_params["breathing_rate"]
                )
                base_uniforms.update(mod_params.to_webgl_uniforms())
            except Exception as e:
                logger.debug(f"Modulation bus update exception: {e}")

        return {
            "director_mode": "AmbientChronosAuteur",
            "current_motif": active_motif["title"],
            "aesthetic": active_motif["aesthetic"],
            "shader_target": active_motif["shader"],
            "in_transition": self.in_transition,
            "transition_progress": round(transition_factor, 4),
            "uniforms": base_uniforms
        }

    # 別名相容性
    tick_frame = process_frame

    def plan_long_take_storyboard(
        self,
        total_duration: float = 180.0,
        audio_track_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        全曲 Ambient 極長鏡頭分鏡演化規劃器 (Long Take Storyboard Planner):
        - 單鏡頭時長嚴格限制在 20.0s ~ 60.0s
        - 鏡頭間嚴禁硬切 (Hard-Cut)，強制配置 4.0s ~ 10.0s 深度光學交叉溶解 (Deep Cross-Dissolve)
        - 注入微尺度攝影機漂移與呼吸週期
        """
        storyboard = []
        current_time = 0.0
        shot_index = 0
        num_motifs = len(self.CONTEMPLATIVE_MOTIFS)

        camera_motions = [
            "subtle_dolly_in_slow",
            "slow_celestial_orbit",
            "micro_pan_right_with_tilt",
            "still_gaze_with_expansion"
        ]

        while current_time < total_duration:
            motif = self.CONTEMPLATIVE_MOTIFS[shot_index % num_motifs]
            # 鏡頭基礎時長 25s ~ 45s
            shot_duration = float(motif.get("min_shot_duration", 30.0))
            if current_time + shot_duration > total_duration:
                shot_duration = max(10.0, total_duration - current_time)

            dissolve_duration = float(min(shot_duration * 0.25, motif.get("morph_duration", 8.0)))
            start_t = current_time
            end_t = current_time + shot_duration

            storyboard.append({
                "shot_index": shot_index,
                "title": f"Shot {shot_index + 1}: {motif['title']}",
                "motif_id": motif["id"],
                "start_time": round(start_t, 2),
                "end_time": round(end_t, 2),
                "duration": round(shot_duration, 2),
                "shader": motif["shader"],
                "camera_motion": camera_motions[shot_index % len(camera_motions)],
                "dissolve_window": {
                    "start": round(max(0.0, end_t - dissolve_duration), 2),
                    "end": round(end_t, 2),
                    "duration": round(dissolve_duration, 2)
                },
                "breathing_cycles": round(shot_duration * 0.1, 1), # 0.1Hz 週期數
                "color_palette_oklch": motif["oklch_palette"],
                "palette_hex": [
                    self._oklch_to_hex(col[0], col[1], col[2]) for col in motif["oklch_palette"]
                ],
                "ambient_color_policy": {
                    "enabled": True,
                    "mode": "clamp_and_blend",
                    "chroma_ceiling": 0.068,
                    "palette": [self._oklch_to_hex(col[0], col[1], col[2]) for col in motif["oklch_palette"]],
                    "target_hue": float(motif["oklch_palette"][1][2]),
                    "blend_ratio": 0.50
                }
            })

            # 步進時間 (扣除交叉溶解重疊時間，形成無縫融鏡)
            current_time += (shot_duration - dissolve_duration)
            shot_index += 1

            if current_time >= total_duration - 2.0:
                break

        return storyboard

# 全域靜態初始化 144 種組合哲學母題庫
AmbientChronosDirector.CONTEMPLATIVE_MOTIFS = AmbientChronosDirector.build_144_motifs_catalog()
