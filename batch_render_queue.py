#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch Render Queue for Techno 2026-2
===================================
Automatically checks and completes missing or corrupted 4K MV visual renders:
1. Marina at Dusk
2. Vaporized Structures
3. 待上傳/Gradient of Silence
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

# Add project root to path
workspace_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, workspace_dir)

TARGET_FOLDERS = [
    "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Marina at Dusk",
    "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Vaporized Structures",
    "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/待上傳/Gradient of Silence"
]

def get_duration(file_path):
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json', file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return float(data.get('format', {}).get('duration', 0.0))
    except Exception:
        return 0.0

def scan_target_folders():
    """掃描目標資料夾，列出已完成與待補渲染的曲目清單"""
    summary = {}
    pending_tasks = []

    for folder in TARGET_FOLDERS:
        folder_name = os.path.basename(folder)
        summary[folder_name] = {
            "path": folder,
            "completed": [],
            "pending": [],
            "corrupted": []
        }

        if not os.path.exists(folder):
            continue

        wav_files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.wav')])
        for wav_file in wav_files:
            base_name = os.path.splitext(wav_file)[0]
            wav_path = os.path.join(folder, wav_file)
            mp4_path = os.path.join(folder, f"{base_name}.mp4")
            credits_path = os.path.join(folder, f"{base_name}_credits.txt")

            if not os.path.exists(mp4_path):
                summary[folder_name]["pending"].append(wav_file)
                pending_tasks.append((folder, wav_file, wav_path, mp4_path, "missing"))
            else:
                v_dur = get_duration(mp4_path)
                a_dur = get_duration(wav_path)
                if v_dur <= 0 or abs(v_dur - a_dur) > 1.5:
                    summary[folder_name]["corrupted"].append((wav_file, v_dur, a_dur))
                    pending_tasks.append((folder, wav_file, wav_path, mp4_path, "corrupted"))
                else:
                    summary[folder_name]["completed"].append(wav_file)

    return summary, pending_tasks

def print_scan_report(summary, pending_tasks):
    print("=" * 70)
    print("📋 [4K MV 批次補跑掃描報告]")
    print("=" * 70)
    total_completed = 0
    total_pending = 0

    for folder_name, data in summary.items():
        comp_count = len(data["completed"])
        pend_count = len(data["pending"])
        corr_count = len(data["corrupted"])
        total_completed += comp_count
        total_pending += pend_count + corr_count

        print(f"\n📁 【{folder_name}】")
        print(f"   路徑: {data['path']}")
        print(f"   ✅ 已完成 ({comp_count} 首):")
        for f in data["completed"]:
            print(f"      - {f}")
        if data["corrupted"]:
            print(f"   ⚠️ 渲染中斷/損毀 ({corr_count} 首):")
            for f, vd, ad in data["corrupted"]:
                print(f"      - {f} (影片 {vd:.1f}s vs 音訊 {ad:.1f}s)")
        if data["pending"]:
            print(f"   ⏳ 尚未渲染 ({pend_count} 首):")
            for f in data["pending"]:
                print(f"      - {f}")

    print("\n" + "=" * 70)
    print(f"📊 總結: 已完成 {total_completed} 首 | 待補渲染 {total_pending} 首")
    print("=" * 70)

def run_render_queue():
    summary, pending_tasks = scan_target_folders()
    print_scan_report(summary, pending_tasks)

    if not pending_tasks:
        print("\n🎉 所有曲目皆已渲染完成，無須補跑！")
        return

    print(f"\n🚀 即將開始依序渲染 {len(pending_tasks)} 首待補曲目...")
    
    # 延遲導入 PyQt 模組
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QCoreApplication
    from main import StandaloneInjectorApp as VJAestheticEditor

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    editor = VJAestheticEditor()

    w, h = 3840, 2160
    fps = 30
    trans_sec = 2.0
    fx_prob = 1.0

    fx_flags = {
        'spatial_warping': editor.fx_cb_distortion.isChecked(),
        'fluid_noise': editor.fx_cb_fluid_noise.isChecked(),
        'temporal_feedback': editor.fx_cb_feedback_dynamics.isChecked(),
        'color_spectral': editor.fx_cb_color_aberration.isChecked(),
        'glow_illumination': editor.fx_cb_glow_illumination.isChecked(),
        'retro_degradation': editor.fx_cb_retro_degradation.isChecked(),
        'pixel_sort': editor.fx_cb_pixel_sort.isChecked(),
        'kaleidoscope': editor.fx_cb_kaleidoscope.isChecked(),
        'ambient_dsp': editor.fx_cb_ambient_dsp.isChecked(),
        'adaptive_modulation': editor.fx_cb_adaptive.isChecked(),
        'data_mosh': editor.fx_cb_data_mosh.isChecked(),
        'sedimentation': editor.fx_cb_sedimentation.isChecked(),
        'vector_scan': editor.fx_cb_vector_scan.isChecked(),
        'temporal_fractal': editor.fx_cb_temporal_fractal.isChecked(),
        'phase_slit': editor.fx_cb_phase_slit.isChecked(),
        'centroid_glitch': editor.fx_cb_centroid_glitch.isChecked(),
        'vignette_pulse': editor.fx_cb_vignette_pulse.isChecked(),
        'tension_overlay': editor.fx_cb_tension_overlay.isChecked(),
        'photosensitive_safe': editor.fx_cb_photosensitive_safe.isChecked(),
        'thermal_vision': editor.fx_cb_thermal_vision.isChecked(),
        'scanline_glitch': editor.fx_cb_scanline_glitch.isChecked(),
        'frame_drop': editor.fx_cb_frame_drop.isChecked(),
        'dynamic_mosaic': editor.fx_cb_dynamic_mosaic.isChecked(),
        'pixel_art': editor.fx_cb_pixel_art.isChecked(),
        'handheld_camera': editor.fx_cb_handheld_camera.isChecked(),
        'stylized_fade': editor.fx_cb_stylized_fade.isChecked(),
        'zoom_pulse': editor.fx_cb_zoom_pulse.isChecked(),
        'film_burn': editor.fx_cb_film_burn.isChecked(),
        'blueprint_edge': editor.fx_cb_blueprint.isChecked(),
        'turing_pattern': editor.fx_cb_turing.isChecked(),
        'point_cloud_depth': editor.fx_cb_point_cloud.isChecked(),
        'vector_scope': editor.fx_cb_vector_scope.isChecked(),
        'lowpass_muffle': editor.fx_cb_lowpass_muffle.isChecked(),
        'infinity_tunnel': editor.fx_cb_infinity_tunnel.isChecked(),
        'dolly_zoom': editor.fx_cb_dolly_zoom.isChecked(),
        'hologram_glitch': editor.fx_cb_hologram_glitch.isChecked(),
        'voronoi_shatter': editor.fx_cb_voronoi_shatter.isChecked(),
        'thermal_infrared': editor.fx_cb_thermal_infrared.isChecked(),
        'ascii_cyber_matrix': editor.fx_cb_ascii_cyber_matrix.isChecked(),
        'chromatic_radial_zoom': editor.fx_cb_chromatic_radial_zoom.isChecked(),
        'synthwave_grid_scan': editor.fx_cb_synthwave_grid_scan.isChecked(),
        'chladni_cymatics': editor.fx_cb_chladni_cymatics.isChecked(),
        'ferrofluid_spikes': editor.fx_cb_ferrofluid_spikes.isChecked(),
        'volumetric_caustics': editor.fx_cb_volumetric_caustics.isChecked(),
        'clifford_torus': editor.fx_cb_clifford_torus.isChecked(),
        'holographic_moire': editor.fx_cb_holographic_moire.isChecked(),
        'lens_defocus': editor.fx_cb_lens_defocus.isChecked(),
        'ocular_tremor': editor.fx_cb_ocular_tremor.isChecked(),
        'quantum_decoherence': editor.fx_cb_quantum_decoherence.isChecked(),
        'latent_hallucination': editor.fx_cb_latent_hallucination.isChecked(),
        'tape_head_drag': editor.fx_cb_tape_head_drag.isChecked(),
        'huffman_entropy_collapse': editor.fx_cb_huffman_entropy_collapse.isChecked(),
        'spectral_fractal_shear': editor.fx_cb_spectral_fractal_shear.isChecked(),
        'bypass_downscale': False
    }

    batch_used_counts = {}
    batch_used_themes = []
    save_dir = os.path.join(workspace_dir, "custom_visuals")

    while True:
        summary, pending_tasks = scan_target_folders()
        if not pending_tasks:
            print("\n" + "=" * 70)
            print("🎉 恭喜！三大目標資料夾所有曲目均已 100% 渲染完成，無任何遺漏！")
            print("=" * 70)
            break

        total_tasks = len(pending_tasks)
        print(f"\n🚀 本輪發現 {total_tasks} 首待渲染曲目，開始執行...")
        passed_count = 0
        failed_count = 0

        for idx, (folder, wav_file, wav_path, mp4_path, reason) in enumerate(pending_tasks, 1):
            print(f"\n" + "-" * 60)
            print(f"🎬 [{idx}/{total_tasks}] 處理中: {wav_file} ({reason})")
            print(f"   來源: {wav_path}")
            print(f"   輸出: {mp4_path}")

            # 若是中斷損壞的檔案，先安全移除
            if reason == "corrupted" and os.path.exists(mp4_path):
                try:
                    os.remove(mp4_path)
                    print(f"   🗑️ 已移除損壞的舊檔案: {mp4_path}")
                except Exception as e:
                    print(f"   ⚠️ 無法刪除損壞檔案: {e}")

            # 智能剪輯配對
            selected_keys = editor.perform_smart_clip_matching(
                wav_path, show_popups=False, batch_used_keys=batch_used_counts
            )
            if not selected_keys:
                print(f"   ❌ 智能剪輯匹配失敗，跳過此曲目！")
                failed_count += 1
                continue

            selected_presets = list(selected_keys)
            for key in selected_presets:
                batch_used_counts[key] = batch_used_counts.get(key, 0) + 1

            visuals_data = []
            for vp in selected_presets:
                if vp == "modules_index":
                    continue
                p_path = os.path.join(save_dir, f"{vp}.json")
                if os.path.exists(p_path):
                    with open(p_path, "r", encoding="utf-8") as f:
                        preset_dict = json.load(f)
                        if isinstance(preset_dict, dict) and 'code' in preset_dict:
                            if 'name' not in preset_dict:
                                preset_dict['name'] = preset_dict.get('title', vp)
                            visuals_data.append(preset_dict)

            start_time = time.time()
            try:
                success = editor.render_mv_frame_by_frame(
                    audio_path=wav_path,
                    genre="techno",
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
                cost = round(time.time() - start_time, 1)

                if success and os.path.exists(mp4_path):
                    passed_count += 1
                    size_mb = round(os.path.getsize(mp4_path) / (1024 * 1024), 2)
                    if hasattr(editor, '_last_post_processor') and editor._last_post_processor:
                        used_t = editor._last_post_processor.selected_theme
                        batch_used_themes.append(used_t)
                    print(f"   ✅ 渲染成功！耗時: {cost}s, 大小: {size_mb} MB")
                else:
                    failed_count += 1
                    print(f"   ❌ 渲染失敗或被中止 (耗時: {cost}s)")

            except Exception as e:
                failed_count += 1
                print(f"   ❌ 渲染過程發生異常: {e}")

        print(f"\n本輪完成：成功 {passed_count}/{total_tasks}，重新掃描是否有新刪除或遺漏的曲目...")
        time.sleep(2)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--scan-only":
        summary, pending = scan_target_folders()
        print_scan_report(summary, pending)
    else:
        run_render_queue()
