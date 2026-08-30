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
            # 轉換為低解析度 Numpy Array 以極低開銷做統計矩陣計算 (128x72)
            small_img = pil_img.resize((128, 72), Image.Resampling.NEAREST)
            img_np = np.array(small_img, dtype=np.float32)
            
            # --- 診斷 A: 黑畫面與低亮度異常檢測 (含合成器主旋律保底) ---
            rgb_mean = np.mean(img_np[:, :, :3])
            rgb_max = np.max(img_np[:, :, :3])
            is_synth_melody = audio_feats.get('synth_melody_active', False) if isinstance(audio_feats, dict) else False

            if sec_name.lower() != 'outro' and (rgb_max < 10.0 or (is_synth_melody and rgb_mean < 8.0)):
                self.black_screen_count += 1
                logger.warning(
                    f"⚠️ [QC Auditor] 影格 {frame_i} (t={t:.2f}s, section={sec_name}) 畫面極暗/純黑! "
                    f"(RGB Max: {rgb_max:.1f}, Mean: {rgb_mean:.1f}, SynthMelody: {is_synth_melody})"
                )
                if is_synth_melody:
                    # 主旋律活躍但畫面偏暗，主動要求提升 1.35x 對比與和弦微光
                    boost_fx['contrast_boost'] = 1.35
                else:
                    boost_fx['force_hold_previous'] = True

            # --- 診斷 B: 高潮段落 (Drop / Chorus / Build-up) 熱烈度驗證 ---
            is_climax_section = any(s in sec_name.lower() for s in ('drop', 'chorus', 'build'))
            if is_climax_section and music_energy > 0.55:
                # 計算色彩標準差 (Color Contrast & Saturation Variance)
                color_std = np.std(img_np[:, :, :3])
                if color_std < 18.0:  # 畫面過於平淡冷靜、缺少對比
                    self.heat_warning_count += 1
                    logger.info(
                        f"🔥 [QC Auditor] 影格 {frame_i} (t={t:.2f}s, section={sec_name}) 處於高潮段落但畫面熱烈度不足 "
                        f"(Color Std: {color_std:.1f} < 18.0)。自動啟動視覺熱烈度補強！"
                    )
                    # 自動補強熱烈度：提升 1.25x 色彩對比度與色散
                    boost_fx['contrast_boost'] = 1.25
                    boost_fx['strobe_flash'] = True if is_beat else False
                    boost_fx['chromatic_boost'] = 1.3

            # --- 診斷 C: 大鼓/小鼓/Hi-hat 節奏動態響應驗證 ---
            hihat_trig = audio_feats.get('hihat_trigger', False) if isinstance(audio_feats, dict) else False
            hihat_dens = audio_feats.get('hihat_density', 0.0) if isinstance(audio_feats, dict) else 0.0

            if (is_beat or hihat_trig or hihat_dens > 0.5) and self.prev_sampled_np is not None:
                # 計算與上一抽樣影格的像素極化動態差異 (Motion Differential)
                diff = np.abs(img_np[:, :, :3] - self.prev_sampled_np[:, :, :3])
                diff_mean = np.mean(diff)

                # 若拍點或 Hihat 爆發但畫面前後完全靜止 (diff_mean < 2.5)
                if diff_mean < 2.5:
                    self.response_warning_count += 1
                    logger.info(
                        f"🥁 [QC Auditor] 影格 {frame_i} (t={t:.2f}s) 檢測到大鼓/Hihat 響應，但畫面像素動態靜止 "
                        f"(Diff Mean: {diff_mean:.2f} < 2.5)。自動注入脈沖衝擊！"
                    )
                    boost_fx['camera_shake_boost'] = 1.5
                    boost_fx['edge_glow_burst'] = True

            # 更新前一次抽樣影格快取
            self.prev_sampled_np = img_np.copy()

        except Exception as e:
            logger.error(f"[QC Auditor] Audit error at frame {frame_i}: {e}")

        return pil_img, boost_fx
