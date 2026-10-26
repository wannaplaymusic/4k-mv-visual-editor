import logging
import numpy as np
from PIL import Image, ImageStat, ImageEnhance

logger = logging.getLogger("StandaloneInjector.RealtimeQCAuditor")

class RealtimeRenderQCAuditor:
    """
    4K MV 實時渲染品質與音視響應診斷器 (Real-time Render Quality & Audio-Visual Response Auditor)
    包含：
    1. 黑畫面抽幀檢測 (Black Screen & Anomaly Detection)
    2. 高潮段落 (Drop/Chorus) 畫面熱烈度與色彩對比度驗證 (Heat & Intensity Auditor)
    3. 大鼓 (Kick)、小鼓 (Snare)、Hi-hat 音視響應實時驗證 (Audio-Visual Response Auditor)
    """
    def __init__(self, sample_interval=30):
        self.sample_interval = sample_interval  # 每隔多少影格抽樣檢查 (預設 30 幀 = 約 1 秒)
        self.prev_sampled_np = None
        self.qc_history = []
        self.black_screen_count = 0
        self.consecutive_black_frames = 0
        self.consecutive_static_frames = 0
        self.heat_warning_count = 0
        self.response_warning_count = 0

    def audit_frame(self, frame_i, pil_img, t, is_beat, beat_energy, audio_feats, sec_name, music_energy):
        """
        對當前渲染產出的影格進行實時 QC 抽樣診斷與動態修正
        :return: (modified_pil_img, boost_params_dict)
        """
        boost_fx = {}

        # 1. 判斷是否執行本影格抽樣檢查 (或拍點強迫檢查)
        should_sample = (frame_i % self.sample_interval == 0) or is_beat
        if not should_sample:
            return pil_img, boost_fx

        try:
            # 使用 BILINEAR 區域積分降採樣 (160x90)，避免 NEAREST 1/225 跳點採樣漏失 4K 極細線框/粒子而誤報全黑
            small_img = pil_img.resize((160, 90), Image.Resampling.BILINEAR)
            img_np = np.array(small_img, dtype=np.float32)
            rgb_channels = img_np[:, :, :3]
            
            # --- 診斷 A: 黑畫面與低亮度異常檢測 (區分高反差極簡線框與真正黑屏/欠曝) ---
            rgb_mean = float(np.mean(rgb_channels))
            rgb_max = float(np.max(rgb_channels))
            pixel_luma_max = np.max(rgb_channels, axis=2)
            active_pixel_ratio = float(np.mean(pixel_luma_max > 28.0))
            is_synth_melody = audio_feats.get('synth_melody_active', False) if isinstance(audio_feats, dict) else False
            is_ambient_mode = bool(
                audio_feats.get('force_ambient_color') or audio_feats.get('ambient_color_policy')
            ) if isinstance(audio_feats, dict) else False

            # 若畫面具備高亮度線框/幾何結構 (rgb_max >= 145 且活躍像素佔比 >= 1.2%)，屬於正常高反差極簡視覺，不誤判為欠曝
            is_high_contrast_wireframe = (rgb_max >= 145.0 and active_pixel_ratio >= 0.012 and rgb_mean >= 1.2)
            if is_ambient_mode:
                # Ambient 豁免協議：Step 11 已注入 12~18 的 Ganzfeld 極光底光，僅當真正全黑 (rgb_max < 10.0) 才判定欠曝
                is_underexposed = (
                    sec_name.lower() != 'outro'
                    and rgb_max < 10.0
                    and rgb_mean < 1.0
                )
            else:
                is_underexposed = (
                    sec_name.lower() != 'outro'
                    and not is_high_contrast_wireframe
                    and (
                        rgb_max < 22.0
                        or (rgb_mean < 2.2 and active_pixel_ratio < 0.012)
                        or (is_synth_melody and rgb_mean < 6.5 and active_pixel_ratio < 0.035)
                    )
                )

            if is_underexposed:
                self.black_screen_count += 1
                self.consecutive_black_frames += 1
                logger.warning(
                    f"⚠️ [QC Auditor] 影格 {frame_i} (t={t:.2f}s, section={sec_name}) 畫面極暗/欠曝! "
                    f"(RGB Max: {rgb_max:.1f}, Mean: {rgb_mean:.1f}, ActiveRatio: {active_pixel_ratio:.3f}, "
                    f"SynthMelody: {is_synth_melody}, 連續次數: {self.consecutive_black_frames})"
                )
                if is_ambient_mode:
                    # Ambient 模式下嚴禁施加 1.45x 對比度拉升（避免破壞莫蘭迪柔和階調），僅溫和提亮
                    boost_fx['exposure_boost'] = 1.15
                    if self.consecutive_black_frames >= 8:
                        boost_fx['trigger_hotswap_fallback'] = True
                elif self.consecutive_black_frames >= 3:
                    # 連續檢測到黑屏/欠曝，發出強迫熱置換與氛圍保底
                    boost_fx['trigger_hotswap_fallback'] = True
                    boost_fx['contrast_boost'] = 1.45
                    boost_fx['exposure_boost'] = 1.50
                    boost_fx['ambient_glow_overlay'] = True
                elif is_synth_melody or rgb_max < 15.0:
                    # 主旋律活躍或整體極暗，主動要求提升對比與曝光並注入微光底層
                    boost_fx['contrast_boost'] = 1.35
                    boost_fx['exposure_boost'] = 1.35
                    if rgb_max < 12.0:
                        boost_fx['ambient_glow_overlay'] = True
                else:
                    boost_fx['exposure_boost'] = 1.25
            else:
                self.consecutive_black_frames = 0

            # --- 診斷 B: 高潮段落 (Drop / Chorus / Build-up) 熱烈度驗證 (Ambient 模式完全豁免) ---
            is_climax_section = any(s in sec_name.lower() for s in ('drop', 'chorus', 'build'))
            if (not is_ambient_mode) and is_climax_section and music_energy > 0.55:
                # 計算色彩標準差 (Color Contrast & Saturation Variance)
                color_std = float(np.std(rgb_channels))
                if color_std < 18.0 and not is_high_contrast_wireframe:  # 畫面過於平淡冷靜、缺少對比
                    self.heat_warning_count += 1
                    logger.info(
                        f"🔥 [QC Auditor] 影格 {frame_i} (t={t:.2f}s, section={sec_name}) 處於高潮段落但畫面熱烈度不足 "
                        f"(Color Std: {color_std:.1f} < 18.0)。自動啟動視覺熱烈度補強！"
                    )
                    # 自動補強熱烈度：提升 1.25x 色彩對比度與色散
                    boost_fx['contrast_boost'] = 1.25
                    boost_fx['strobe_flash'] = True if is_beat else False
                    boost_fx['chromatic_boost'] = 1.3

            # --- 診斷 C: 大鼓/小鼓/Hi-hat 節奏動態響應驗證 (Ambient 模式完全豁免) ---
            hihat_trig = audio_feats.get('hihat_trigger', False) if isinstance(audio_feats, dict) else False
            hihat_dens = audio_feats.get('hihat_density', 0.0) if isinstance(audio_feats, dict) else 0.0

            if (not is_ambient_mode) and (is_beat or hihat_trig or hihat_dens > 0.5) and self.prev_sampled_np is not None:
                # 計算與上一抽樣影格的像素動態差異 (Motion Differential)
                diff = np.abs(rgb_channels.astype(np.int16) - self.prev_sampled_np[:, :, :3].astype(np.int16))
                diff_mean = float(np.mean(diff))
                diff_max = float(np.max(diff))

                # 4K 高解析度畫面上大面積為深色/留白時，局部動態會被全局平均稀釋
                # 只有全局靜止且局部無顯著衝擊 (diff_max < 20.0 且 diff_mean < 1.5) 時才判定為死鎖凍結
                if diff_mean < 1.5 and diff_max < 20.0:
                    self.response_warning_count += 1
                    self.consecutive_static_frames += 1
                    logger.info(
                        f"🥁 [QC Auditor] 影格 {frame_i} (t={t:.2f}s) 檢測到大鼓/Hihat 響應，但畫面像素動態靜止 "
                        f"(Diff Mean: {diff_mean:.2f} < 1.5, Max: {diff_max:.1f} < 20, 連續靜止: {self.consecutive_static_frames})。自動注入脈沖衝擊！"
                    )
                    boost_fx['camera_shake_boost'] = 1.5
                    boost_fx['edge_glow_burst'] = True
                    if self.consecutive_static_frames >= 4:
                        boost_fx['trigger_hotswap_fallback'] = True
                else:
                    self.consecutive_static_frames = 0

            # 更新前一次抽樣影格快取
            self.prev_sampled_np = img_np.copy()

        except Exception as e:
            logger.error(f"[QC Auditor] Audit error at frame {frame_i}: {e}")

        return pil_img, boost_fx
