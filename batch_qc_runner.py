import os
import sys
import json
import time
import shutil
import platform
from PIL import Image

sys.path.insert(0, os.path.abspath("."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from main import StandaloneInjectorApp

def run_album_batch():
    album_dir = "/Users/unclerm/Desktop/音樂發行/AI音樂/Techno 2026-2/Distant Industrial Rain"
    screenshot_dir = "/Users/unclerm/.gemini/antigravity/brain/2615a4fe-c83f-4142-acf6-ce1423c09edd/screenshots"
    os.makedirs(screenshot_dir, exist_ok=True)
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
        
    print(f"🎬 [BATCH AGENT] Initializing StandaloneInjectorApp...")
    editor = StandaloneInjectorApp()
    
    # 設置界面參數與圖片一致
    editor.audio_dir_input.setText(album_dir)
    editor.res_select.setCurrentText("4K (3840x2160)")
    editor.fps_select.setCurrentText("30")
    editor.native_4k_cb.setChecked(False)
    editor.cpu_mode_select.setCurrentIndex(0) # 控溫模式
    editor.trans_slider.setValue(5) # 0.5s (5 / 10)
    editor.fx_prob_slider.setValue(25) # 25%
    editor.genre_select.setCurrentText("Auto (自動偵測)")
    editor.sort_select.setCurrentIndex(0) # ⭐ 我的最愛優先
    
    # 特效勾選矩陣與截圖完全一致
    fx_flags = {
        'spatial_warping': True,
        'fluid_noise': True,
        'temporal_feedback': True,
        'color_spectral': True,
        'glow_illumination': True,
        'retro_degradation': True,
        'pixel_sort': True,
        'kaleidoscope': True,
        'ambient_dsp': False,
        'adaptive_modulation': True,
        'data_mosh': True,
        'sedimentation': True,
        'vector_scan': True,
        'temporal_fractal': True,
        'phase_slit': True,
        'centroid_glitch': True,
        'vignette_pulse': False,
        'tension_overlay': False,
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
        'thermal_gradient': True,
        'matrix_rain': True,
        'chromatic_aberration': True,
        'cyber_grid': True,
        'bypass_downscale': False
    }
    
    # 掃描音軌
    audio_files = []
    for file in sorted(os.listdir(album_dir)):
        if file.lower().endswith(('.mp3', '.wav', '.flac', '.m4a')):
            audio_files.append(os.path.join(album_dir, file))
            
    total_songs = len(audio_files)
    print(f"📁 [BATCH AGENT] Found {total_songs} audio tracks in {album_dir}")
    
    # 注入截圖與實時監控 Hook
    orig_render_mv = editor.render_mv_frame_by_frame
    
    current_song_name = [""]
    
    def wrapped_render_mv(*args, **kwargs):
        # 攔截並包裝渲染過程以定期截圖
        return orig_render_mv(*args, **kwargs)
        
    editor._batch_used_themes = []
    editor._batch_used_module_counts = {}
    
    # 優先處理之前失敗或需要重新驗證的曲目
    # 讓我們檢查每個曲目
    import subprocess
    def get_duration(file_path):
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', file_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            dur = float(res.stdout.strip())
            if dur > 0:
                return dur
        except Exception:
            pass
        return 0.0
        
    for index, audio_path in enumerate(audio_files):
        filename = os.path.basename(audio_path)
        song_title = os.path.splitext(filename)[0]
        output_file = os.path.join(album_dir, f"{song_title}.mp4")
        
        print(f"\n=======================================================")
        print(f"🎵 [{index + 1}/{total_songs}] 檢查/準備渲染: {song_title}")
        print(f"=======================================================")
        
        audio_dur = get_duration(audio_path)
        video_dur = get_duration(output_file) if os.path.exists(output_file) else 0.0
        
        force_rerender = False
        if song_title in ["Distant Industrial Rain", "Airlock Reverie"]:
            force_rerender = True
            print(f"🔄 {song_title} 強制重新渲染以應用最新的視覺模組修復。")
        elif abs(video_dur - audio_dur) > 1.0 or video_dur < 10.0:
            force_rerender = True
            print(f"⚠️ {song_title} 影片不完整（影片 {video_dur:.1f}s vs 音訊 {audio_dur:.1f}s），將執行重新渲染。")
        
        if not force_rerender and video_dur > 0 and audio_dur > 0 and abs(video_dur - audio_dur) <= 1.0:
            print(f"⏩ [SKIP] 已存在完整影片（長度一致: {video_dur:.1f}s / {audio_dur:.1f}s）: {filename}")
            continue
            
        print(f"🚀 開始為 {song_title} 進行智能分鏡匹配與 4K 離線渲染...")
        
        # 智能分鏡配對
        selected_keys = editor.perform_smart_clip_matching(audio_path, show_popups=False, batch_used_keys=editor._batch_used_module_counts)
        if not selected_keys:
            print(f"❌ 智能匹配失敗: {filename}")
            continue
            
        selected_presets = list(selected_keys)
        for key in selected_presets:
            editor._batch_used_module_counts[key] = editor._batch_used_module_counts.get(key, 0) + 1
            
        print(f"🎯 選中 {len(selected_presets)} 個視覺模組: {selected_presets}")
        
        # 載入模組數據
        visuals_data = []
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_visuals")
        for vp in selected_presets:
            p_path = os.path.join(save_dir, f"{vp}.json")
            if os.path.exists(p_path):
                with open(p_path, "r", encoding="utf-8") as f:
                    preset_dict = json.load(f)
                    if isinstance(preset_dict, dict) and 'code' in preset_dict:
                        if 'name' not in preset_dict:
                            preset_dict['name'] = preset_dict.get('title', vp)
                        visuals_data.append(preset_dict)
                        
        w, h = 3840, 2160
        fps = 30
        trans_sec = 0.5
        fx_prob = 0.25
        genre = "Auto"
        
        start_t = time.time()
        success = editor.render_mv_frame_by_frame(
            audio_path=audio_path,
            genre=genre,
            visuals_data=visuals_data,
            output_file=output_file,
            w=w,
            h=h,
            fps=fps,
            trans_sec=trans_sec,
            fx_prob=fx_prob,
            fx_flags=fx_flags,
            show_popups=False,
            is_batch=True,
            used_themes=editor._batch_used_themes
        )
        
        cost_t = time.time() - start_t
        if success and os.path.exists(output_file):
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            print(f"✅ [SUCCESS] {song_title} 4K MV 渲染成功！耗時: {cost_t:.1f}s, 大小: {size_mb:.1f}MB")
        else:
            print(f"❌ [FAILED] {song_title} 渲染失敗！耗時: {cost_t:.1f}s")

if __name__ == "__main__":
    run_album_batch()
