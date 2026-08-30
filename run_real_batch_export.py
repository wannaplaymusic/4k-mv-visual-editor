import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath("."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from main import VJAestheticEditor

def contains_target_modules(visuals_data, target_mods_set):
    """檢查歌曲使用的視覺效果是否包含目標模組"""
    if isinstance(visuals_data, list):
        for item in visuals_data:
            name = item.get("name") if isinstance(item, dict) else str(item)
            if name in target_mods_set:
                return True
    elif isinstance(visuals_data, dict):
        for key in visuals_data.keys():
            if key in target_mods_set:
                return True
    return False

def run_real_batch_render(overwrite=False):
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    editor = VJAestheticEditor()
    output_dir = os.path.abspath("render_output")
    os.makedirs(output_dir, exist_ok=True)
    print(f"🎬 [REAL RENDER] Output directory set to: {output_dir}")

    progress_file = "batch_test_progress.json"
    if not os.path.exists(progress_file):
        print(f"❌ [ERROR] Progress file '{progress_file}' not found!")
        return

    with open(progress_file, "r", encoding="utf-8") as f:
        batch_data = json.load(f)

    target_mods = {
        'BionicLimbCrusher', 'IonCannonChieftain', 'PlasmaStormLegionnaire',
        'Codeisinthebin', 'CanCrusher', 'CyberpunkFlowFieldLines',
        'ColorSmoke', 'Colorsmoke_3', 'DashingCity_1', 'DeepForest_1',
        'DiscoBall_1', 'InfiniteTruchet', 'FluidSimulation', '210523_1',
        'GenerativeGenuary26day21BauhausKineticPoster'
    }

    # 精確篩選命中目標模組的音軌
    targets = []
    for song_path, info in batch_data.items():
        visuals_data = info.get("visuals_data") or info.get("used_visuals") or []
        # 同時支援結構化比對與降級字串檢索
        if contains_target_modules(visuals_data, target_mods) or any(m in json.dumps(info, ensure_ascii=False) for m in target_mods):
            targets.append((song_path, info))

    total_tasks = len(targets)
    print(f"🎬 [REAL RENDER] Total songs queue: {total_tasks}")

    passed_count = 0
    failed_count = 0
    skipped_count = 0

    for idx, (song_path, info) in enumerate(targets, 1):
        song_name = os.path.basename(song_path)
        out_filename = os.path.splitext(song_name)[0] + "_fixed.mp4"
        out_path = os.path.join(output_dir, out_filename)
        
        # 1. 檢查音訊路徑是否存在
        if not os.path.exists(song_path):
            print(f"\n⚠️ [{idx}/{total_tasks}] Skip (Audio Not Found): {song_path}")
            failed_count += 1
            continue

        # 2. 斷點續傳檢查
        if not overwrite and os.path.exists(out_path) and os.path.getsize(out_path) > 1024 * 1024:
            print(f"\n⏩ [{idx}/{total_tasks}] Skip Existing: {song_name}")
            skipped_count += 1
            continue

        print(f"\n▶ [{idx}/{total_tasks}] Start Rendering: {song_name}")
        print(f"   Target MP4: {out_path}")
        
        visuals_data = info.get("visuals_data", []) or info.get("used_visuals", []) or []
        start_time = time.time()

        try:
            success = editor.render_mv_frame_by_frame(
                audio_path=song_path,
                genre=info.get("genre", "Techno"),
                visuals_data=visuals_data,
                output_file=out_path,
                w=1280,
                h=720,
                fps=30,
                trans_sec=2.0,
                show_popups=False,
                is_batch=True
            )

            # 強制處理殘餘 Qt 事件，清理記憶體
            QCoreApplication.processEvents()

            cost = round(time.time() - start_time, 1)
            if success and os.path.exists(out_path):
                passed_count += 1
                size_mb = round(os.path.getsize(out_path) / (1024 * 1024), 2)
                print(f"   Result: ✅ SUCCESS ({cost}s, {size_mb} MB)")
            else:
                failed_count += 1
                print(f"   Result: ❌ FAILED ({cost}s)")

        except Exception as e:
            failed_count += 1
            print(f"   ❌ Exception during rendering {song_name}: {e}")

    print("\n" + "=" * 50)
    print(f"🎉 Batch Finished: Passed: {passed_count}, Failed: {failed_count}, Skipped: {skipped_count}, Total: {total_tasks}")
    print("=" * 50)

if __name__ == "__main__":
    run_real_batch_render(overwrite=False)
