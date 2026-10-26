#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch Render Engine for 'Aurora Borealis Flash'
==============================================
Renders all 10 tracks in 4K (3840x2160@30fps, Ambient genre) using the exact
same flagship aesthetic settings, Smart Clip Matching, and 48-track post-FX matrix.
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
workspace_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, workspace_dir)

if "--no-sandbox" not in sys.argv:
    sys.argv.append("--no-sandbox")
if "--disable-web-security" not in sys.argv:
    sys.argv.append("--disable-web-security")

ALBUM_DIR = "/Users/unclerm/Desktop/音樂發行/AI音樂/Ambient-2026-2/Aurora Borealis Flash"
LOG_FILE = os.path.join(workspace_dir, "logs", "batch_aurora.log")
os.makedirs(os.path.join(workspace_dir, "logs"), exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def get_duration(file_path):
    """取得音訊或影片的精確秒數"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json', file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        dur = float(data.get('format', {}).get('duration', 0.0))
        if dur > 0:
            return dur
    except Exception:
        pass
    
    # 音訊 fallback
    if file_path.lower().endswith(('.wav', '.mp3', '.flac')):
        try:
            import soundfile as sf
            info = sf.info(file_path)
            return float(info.duration)
        except Exception:
            pass
    return 0.0

def verify_video_validity(mp4_path, wav_path):
    """驗證 MP4 影片是否完整可用（非損毀、長度與音訊吻合、moov atom 完整）"""
    if not os.path.exists(mp4_path) or os.path.getsize(mp4_path) < 10 * 1024 * 1024:
        return False, 0.0, 0.0, "檔案不存在或小於 10MB"
    
    # 檢查 ffprobe 解析度與長度
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height:format=duration',
            '-of', 'json', mp4_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        v_dur = float(data.get('format', {}).get('duration', 0.0))
        streams = data.get('streams', [])
        vw = int(streams[0].get('width', 0)) if streams else 0
        vh = int(streams[0].get('height', 0)) if streams else 0
    except Exception as e:
        return False, 0.0, 0.0, f"ffprobe 讀取失敗 (可能損毀或缺少 moov atom: {e})"
    
    a_dur = get_duration(wav_path)
    if v_dur <= 0 or a_dur <= 0:
        return False, v_dur, a_dur, f"時長讀取異常 (影片 {v_dur:.1f}s vs 音訊 {a_dur:.1f}s)"
    
    if abs(v_dur - a_dur) > 2.0:
        return False, v_dur, a_dur, f"長度不一致 (影片 {v_dur:.1f}s vs 音訊 {a_dur:.1f}s)"
    
    return True, v_dur, a_dur, "完整可用"

def scan_album(album_dir):
    """掃描專輯資料夾，識別待渲染與已完成清單"""
    wav_files = sorted([f for f in os.listdir(album_dir) if f.lower().endswith('.wav')])
    completed = []
    pending = []

    for wav_file in wav_files:
        base_name = os.path.splitext(wav_file)[0]
        wav_path = os.path.join(album_dir, wav_file)
        mp4_path = os.path.join(album_dir, f"{base_name}.mp4")

        is_valid, v_dur, a_dur, reason = verify_video_validity(mp4_path, wav_path)
        if is_valid:
            completed.append((wav_file, v_dur, a_dur))
        else:
            pending.append((wav_file, wav_path, mp4_path, reason))

    return completed, pending

def run_aurora_batch_render():
    log("=" * 70)
    log(f"🎬 [Aurora Borealis Flash 4K 批次渲染任務啟動]")
    log(f"📁 專輯路徑: {ALBUM_DIR}")
    log("=" * 70)

    completed, pending = scan_album(ALBUM_DIR)
    log(f"📊 初始掃描結果: 已完成 {len(completed)} 首 / 待渲染 {len(pending)} 首 (共 {len(completed) + len(pending)} 首)")
    for f, vd, ad in completed:
        log(f"   ✅ [已完成跳過] {f} ({vd:.1f}s)")
    for f, wp, mp, reason in pending:
        log(f"   ⏳ [待處理曲目] {f} (原因: {reason})")

    if not pending:
        log("🎉 專輯中所有曲目均已渲染完成，無須補跑！")
        return

    # 延遲導入 PyQt6 模組以確保環境乾淨
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QCoreApplication
    from main import StandaloneInjectorApp

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    editor = StandaloneInjectorApp()

    # 與前台 GUI 相同之渲染配置
    w, h = 3840, 2160
    fps = 30
    genre = "ambient"
    trans_sec = 0.5   # 融合時間 0.5s
    fx_prob = 0.25    # 特效出現機率 25%

    # 啟用 48 軌旗艦後製特效矩陣
    fx_flags = {
        'spatial_warping': True,
        'fluid_noise': True,
        'temporal_feedback': True,
        'color_spectral': True,
        'glow_illumination': True,
        'retro_degradation': True,
        'pixel_sort': True,
        'kaleidoscope': True,
        'ambient_dsp': True,
        'adaptive_modulation': True,
        'data_mosh': True,
        'sedimentation': True,
        'vector_scan': True,
        'temporal_fractal': True,
        'phase_slit': True,
        'centroid_glitch': True,
        'vignette_pulse': True,
        'tension_overlay': True,
        'photosensitive_safe': True,
        'thermal_vision': True,
        'scanline_glitch': True,
        'frame_drop': True,
        'dynamic_mosaic': True,
        'pixel_art': True,
        'handheld_camera': True,
        'stylized_fade': True,
        'zoom_pulse': True,
        'film_burn': True,
        'blueprint_edge': True,
        'turing_pattern': True,
        'point_cloud_depth': True,
        'vector_scope': True,
        'lowpass_muffle': True,
        'infinity_tunnel': True,
        'dolly_zoom': True,
        'hologram_glitch': True,
        'voronoi_shatter': True,
        'thermal_infrared': True,
        'ascii_cyber_matrix': True,
        'chromatic_radial_zoom': True,
        'synthwave_grid_scan': True,
        'chladni_cymatics': True,
        'ferrofluid_spikes': True,
        'volumetric_caustics': True,
        'clifford_torus': True,
        'holographic_moire': True,
        'lens_defocus': True,
        'ocular_tremor': True,
        'quantum_decoherence': True,
        'latent_hallucination': True,
        'tape_head_drag': True,
        'huffman_entropy_collapse': True,
        'spectral_fractal_shear': True,
        'bypass_downscale': False  # 輕溫降頻模式 (1080p 擷取 + lanczos 4K 放大)
    }

    # 讀取審計隔離清單
    known_quarantine_modules = set()
    for q_rep in ['audit_quarantine_report_20260925.json', 'audit_quarantine_latest_batches_report.json', 'audit_quarantine_batch_165248_report.json', 'audit_quarantine_batch_20261009_153406_report.json']:
        q_path = os.path.join(workspace_dir, q_rep)
        if os.path.exists(q_path):
            try:
                with open(q_path, 'r', encoding='utf-8') as qf:
                    qd = json.load(qf)
                    for it in qd.get('quarantined_items', []):
                        fn = it.get('filename', '')
                        if fn.endswith('.json'):
                            known_quarantine_modules.add(fn[:-5])
            except Exception:
                pass

    save_dir = os.path.join(workspace_dir, "custom_visuals")
    batch_used_counts = {}
    batch_used_themes = []

    total_pending = len(pending)
    success_count = 0
    failed_files = []

    for idx, (wav_file, wav_path, mp4_path, reason) in enumerate(pending, 1):
        log("\n" + "=" * 60)
        log(f"🚀 [{idx}/{total_pending}] 開始渲染曲目: {wav_file}")
        log(f"   狀態原因: {reason}")
        log(f"   來源音訊: {wav_path}")
        log(f"   目標輸出: {mp4_path}")
        log("=" * 60)

        # 清除先前殘留或損毀的舊檔與暫存目錄
        if os.path.exists(mp4_path):
            try:
                os.remove(mp4_path)
                log(f"   🗑️ 已安全移除舊/損毀 MP4 檔案: {mp4_path}")
            except Exception as e:
                log(f"   ⚠️ 無法刪除舊檔: {e}")

        # 清理可能殘留的 temp_frames
        base_name = os.path.splitext(wav_file)[0]
        for f in os.listdir(ALBUM_DIR):
            if f.startswith(f"{base_name}.mp4_") and f.endswith(".temp_frames"):
                temp_dir_path = os.path.join(ALBUM_DIR, f)
                try:
                    import shutil
                    shutil.rmtree(temp_dir_path, ignore_errors=True)
                    log(f"   🧹 已清理殘留暫存影格目錄: {temp_dir_path}")
                except Exception:
                    pass

        # 智能剪輯配對 (具備跨曲目多樣性懲罰)
        log("   🔍 正在執行智能剪輯分析與分鏡排程...")
        selected_keys = editor.perform_smart_clip_matching(
            wav_path, show_popups=False, batch_used_keys=batch_used_counts
        )
        if not selected_keys:
            log(f"   ❌ 智能剪輯匹配失敗，跳過: {wav_file}")
            failed_files.append((wav_file, "智能匹配失敗"))
            continue

        selected_presets = list(selected_keys)
        for key in selected_presets:
            batch_used_counts[key] = batch_used_counts.get(key, 0) + 1

        visuals_data = []
        for vp in selected_presets:
            if vp == "modules_index" or vp in known_quarantine_modules:
                continue
            p_path = os.path.join(save_dir, f"{vp}.json")
            if os.path.exists(p_path):
                with open(p_path, "r", encoding="utf-8") as f:
                    preset_dict = json.load(f)
                    if isinstance(preset_dict, dict) and 'code' in preset_dict:
                        if 'name' not in preset_dict:
                            preset_dict['name'] = preset_dict.get('title', vp)
                        visuals_data.append(preset_dict)

        if not visuals_data:
            log(f"   ❌ 無可用視覺模組，跳過: {wav_file}")
            failed_files.append((wav_file, "無有效模組"))
            continue

        log(f"   🎨 已載入 {len(visuals_data)} 個視覺模組: {[v.get('name') for v in visuals_data]}")

        # 開始逐幀離線渲染
        start_time = time.time()
        try:
            success = editor.render_mv_frame_by_frame(
                audio_path=wav_path,
                genre=genre,
                visuals_data=visuals_data,
                output_file=mp4_path,
                w=w,
                h=h,
                fps=fps,
                trans_sec=trans_sec,
                fx_prob=fx_prob,
                fx_flags=fx_flags,
                show_popups=False,
                is_batch=True,
                used_themes=batch_used_themes
            )

            QCoreApplication.processEvents()
            elapsed = round(time.time() - start_time, 1)

            if success and os.path.exists(mp4_path):
                size_mb = round(os.path.getsize(mp4_path) / (1024 * 1024), 2)
                success_count += 1
                if hasattr(editor, '_last_post_processor') and editor._last_post_processor:
                    used_t = editor._last_post_processor.selected_theme
                    batch_used_themes.append(used_t)
                log(f"   ✅ [曲目渲染完工] {wav_file} | 耗時: {elapsed}s | 檔案大小: {size_mb} MB")
            else:
                log(f"   ❌ [曲目渲染失敗或被中斷] {wav_file} (耗時: {elapsed}s)")
                failed_files.append((wav_file, "渲染未成功"))

        except Exception as e:
            log(f"   ❌ [執行異常] {wav_file}: {e}")
            failed_files.append((wav_file, f"異常: {e}"))

    log("\n" + "=" * 70)
    log(f"🏁 [Aurora Borealis Flash 專輯批次渲染完工報告]")
    log(f"   成功: {success_count} / {total_pending} 首")
    if failed_files:
        log(f"   ⚠️ 未成功曲目: {failed_files}")
    log("=" * 70)

if __name__ == "__main__":
    if "--scan-only" in sys.argv:
        comp, pend = scan_album(ALBUM_DIR)
        print(f"掃描完畢: 已完成 {len(comp)} 首, 待處理 {len(pend)} 首")
        for f, vd, ad in comp:
            print(f"  [完成] {f} ({vd:.1f}s)")
        for f, wp, mp, r in pend:
            print(f"  [待跑] {f} ({r})")
    else:
        run_aurora_batch_render()
