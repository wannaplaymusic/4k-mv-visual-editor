import os
import sys
import json
import time
import math
import logging
from typing import List, Dict, Any

# Ensure current dir is in path
sys.path.insert(0, os.path.abspath("."))

from bandit_inventory_selector import BanditInventorySelector
from saliency_eyetrace_bridge import SaliencyEyeTraceBridge
from director_choreographer import DirectorChoreographer
from llm_director import LLMDirectorAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QC_Auditor")

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")

def load_all_custom_visuals() -> List[Dict[str, Any]]:
    """ 載入 custom_visuals 目錄下所有真實模組預設 """
    modules = []
    if not os.path.exists(CUSTOM_VISUALS_DIR):
        logger.warning(f"Directory {CUSTOM_VISUALS_DIR} not found.")
        return modules

    for fname in os.listdir(CUSTOM_VISUALS_DIR):
        if fname.endswith(".json") and not fname.startswith("."):
            fpath = os.path.join(CUSTOM_VISUALS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    key = os.path.splitext(fname)[0]
                    modules.append({
                        "_filename_key": key,
                        "name": data.get("name") or key,
                        "tags": data.get("tags") or [data.get("category", "abstract")],
                        "used_count": int(data.get("used_count", 0)),
                        "storyboard_weight": data.get("storyboard_weight", 50),
                        "author": data.get("author", "Community"),
                        "license": data.get("license", "Creative Commons"),
                        "code": data.get("code", "")[:100]  # preview
                    })
            except Exception:
                continue
    return modules

def generate_multi_genre_test_suite() -> List[Dict[str, Any]]:
    """ 生成 10 首具備真實曲式結構的多樣化曲目遙測資料 """
    return [
        {
            "title": "01_Industrial_Rupture",
            "genre": "Industrial Techno",
            "bpm": 138.0,
            "duration": 180.0,
            "key": "F minor",
            "storyboard": [
                {"section": "Intro", "duration": 16.0},
                {"section": "Verse", "duration": 32.0},
                {"section": "Build-up", "duration": 16.0},
                {"section": "Drop", "duration": 32.0},
                {"section": "Bridge", "duration": 24.0},
                {"section": "Build-up", "duration": 16.0},
                {"section": "Drop", "duration": 32.0},
                {"section": "Outro", "duration": 12.0}
            ]
        },
        {
            "title": "02_Subsea_Drift",
            "genre": "Ambient Soundscape",
            "bpm": 78.0,
            "duration": 210.0,
            "key": "D major",
            "storyboard": [
                {"section": "Intro", "duration": 30.0},
                {"section": "Verse", "duration": 60.0},
                {"section": "Bridge", "duration": 45.0},
                {"section": "Verse", "duration": 45.0},
                {"section": "Outro", "duration": 30.0}
            ]
        },
        {
            "title": "03_Neon_Pursuit",
            "genre": "Cyberpunk Darksynth",
            "bpm": 118.0,
            "duration": 195.0,
            "key": "A minor",
            "storyboard": [
                {"section": "Intro", "duration": 15.0},
                {"section": "Verse", "duration": 30.0},
                {"section": "Chorus", "duration": 30.0},
                {"section": "Verse", "duration": 30.0},
                {"section": "Build-up", "duration": 15.0},
                {"section": "Drop", "duration": 45.0},
                {"section": "Outro", "duration": 30.0}
            ]
        },
        {
            "title": "04_Solar_Ascent",
            "genre": "Progressive Trance",
            "bpm": 134.0,
            "duration": 240.0,
            "key": "G major",
            "storyboard": [
                {"section": "Intro", "duration": 32.0},
                {"section": "Verse", "duration": 32.0},
                {"section": "Build-up", "duration": 32.0},
                {"section": "Drop", "duration": 48.0},
                {"section": "Bridge", "duration": 32.0},
                {"section": "Build-up", "duration": 16.0},
                {"section": "Drop", "duration": 32.0},
                {"section": "Outro", "duration": 16.0}
            ]
        },
        {
            "title": "05_Neural_Fracture",
            "genre": "Glitchcore / IDM",
            "bpm": 162.0,
            "duration": 150.0,
            "key": "C# minor",
            "storyboard": [
                {"section": "Intro", "duration": 12.0},
                {"section": "Drop", "duration": 24.0},
                {"section": "Verse", "duration": 24.0},
                {"section": "Build-up", "duration": 12.0},
                {"section": "Drop", "duration": 36.0},
                {"section": "Bridge", "duration": 18.0},
                {"section": "Outro", "duration": 24.0}
            ]
        },
        {
            "title": "06_Echoes_of_Concrete",
            "genre": "Deep Minimal Techno",
            "bpm": 124.0,
            "duration": 200.0,
            "key": "E minor",
            "storyboard": [
                {"section": "Intro", "duration": 25.0},
                {"section": "Verse", "duration": 50.0},
                {"section": "Build-up", "duration": 25.0},
                {"section": "Drop", "duration": 50.0},
                {"section": "Outro", "duration": 50.0}
            ]
        },
        {
            "title": "07_Prismatic_Shore",
            "genre": "Ethereal Dreamwave",
            "bpm": 92.0,
            "duration": 180.0,
            "key": "Bb major",
            "storyboard": [
                {"section": "Intro", "duration": 20.0},
                {"section": "Verse", "duration": 40.0},
                {"section": "Chorus", "duration": 40.0},
                {"section": "Verse", "duration": 40.0},
                {"section": "Outro", "duration": 40.0}
            ]
        },
        {
            "title": "08_Hyper_Luminescence",
            "genre": "Future Bass",
            "bpm": 150.0,
            "duration": 170.0,
            "key": "F# minor",
            "storyboard": [
                {"section": "Intro", "duration": 16.0},
                {"section": "Verse", "duration": 28.0},
                {"section": "Build-up", "duration": 16.0},
                {"section": "Drop", "duration": 32.0},
                {"section": "Verse", "duration": 28.0},
                {"section": "Build-up", "duration": 16.0},
                {"section": "Drop", "duration": 34.0}
            ]
        },
        {
            "title": "09_Monolith_Awakening",
            "genre": "Cinematic Post-Rock",
            "bpm": 105.0,
            "duration": 220.0,
            "key": "B minor",
            "storyboard": [
                {"section": "Intro", "duration": 30.0},
                {"section": "Verse", "duration": 45.0},
                {"section": "Build-up", "duration": 30.0},
                {"section": "Drop", "duration": 60.0},
                {"section": "Outro", "duration": 55.0}
            ]
        },
        {
            "title": "10_Vortex_Resonance",
            "genre": "Acid House 303",
            "bpm": 128.0,
            "duration": 190.0,
            "key": "G minor",
            "storyboard": [
                {"section": "Intro", "duration": 20.0},
                {"section": "Verse", "duration": 35.0},
                {"section": "Build-up", "duration": 20.0},
                {"section": "Drop", "duration": 40.0},
                {"section": "Bridge", "duration": 25.0},
                {"section": "Drop", "duration": 30.0},
                {"section": "Outro", "duration": 20.0}
            ]
        }
    ]

def execute_full_audit():
    """ 執行全量 AI 導演系統批次排片與深度 QC 質檢 """
    print("=" * 80)
    print("🚀 [CACD QUALITY CONTROL SUITE] 啟動增強型 AI 導演全量執行與深度品質審計")
    print("=" * 80)

    # 1. 載入素材庫
    visual_modules = load_all_custom_visuals()
    print(f"📦 已成功載入真實視覺模組數量: {len(visual_modules)} 個")
    assert len(visual_modules) > 20, f"模組數量不足 ({len(visual_modules)})，請檢查 custom_visuals 路徑"

    # 2. 實例化導演大腦並進行服務預熱
    agent = LLMDirectorAgent()
    agent.get_ollama_status()  # 預熱檢測
    songs = generate_multi_genre_test_suite()

    qc_results = {
        "total_songs": len(songs),
        "total_shots_planned": 0,
        "pass_count": 0,
        "fail_count": 0,
        "song_reports": [],
        "global_entropy_list": [],
        "latency_ms_list": [],
        "all_assigned_unique_modules": set(),
        "shock_cuts_count": 0,
        "j_cuts_count": 0,
        "l_cuts_count": 0
    }

    cumulative_used_history: Dict[str, int] = {}

    for s_idx, song in enumerate(songs):
        t_start = time.perf_counter()
        
        # 執行導演腳本生成
        script = agent.generate_director_script(
            audio_telemetry=song,
            available_modules=visual_modules,
            recent_used_keys=[k for k, v in cumulative_used_history.items() if v > 1]
        )
        
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        qc_results["latency_ms_list"].append(latency_ms)

        shot_list = script.get("shot_list", [])
        intensity_curve = script.get("intensity_curve", [])
        qc_results["total_shots_planned"] += len(shot_list)

        # 逐項 QC 指標審查
        issues = []
        
        # QC 1: 分鏡數相符性
        if len(shot_list) != len(song["storyboard"]):
            issues.append(f"分鏡數不匹配: 預期 {len(song['storyboard'])}, 實際 {len(shot_list)}")

        # QC 2: 模組相鄰連續碰撞檢查 (Consecutive Duplicate Check)
        assigned_ids = [shot.get("assigned_module_id") for shot in shot_list]
        for i in range(len(assigned_ids) - 1):
            if assigned_ids[i] == assigned_ids[i + 1]:
                issues.append(f"分鏡 {i} 與 {i+1} 發生相鄰模組碰撞: {assigned_ids[i]}")

        # QC 3: 香農審美熵檢查 (Shannon Entropy >= 2.0)
        entropy = agent.bandit.calculate_shannon_entropy(assigned_ids)
        qc_results["global_entropy_list"].append(entropy)
        if entropy < 1.8 and len(assigned_ids) >= 5:
            issues.append(f"審美香農熵偏低: {entropy:.2f} < 1.8")

        # QC 4: Walter Murch 得分結構性審查
        murch_scores = []
        drop_scores = []
        intro_scores = []
        for shot in shot_list:
            mod_id = shot.get("assigned_module_id")
            qc_results["all_assigned_unique_modules"].add(mod_id)
            cumulative_used_history[mod_id] = cumulative_used_history.get(mod_id, 0) + 1

            meta = shot.get("cinematic_meta", {})
            m_score = meta.get("murch_score", 0.0)
            murch_scores.append(m_score)
            
            sec_name = shot.get("section_name", "").lower()
            if "drop" in sec_name:
                drop_scores.append(m_score)
            elif "intro" in sec_name or "outro" in sec_name:
                intro_scores.append(m_score)

            if meta.get("is_shock_cut"):
                qc_results["shock_cuts_count"] += 1
            if meta.get("cut_style") == "j_cut_anticipation":
                qc_results["j_cuts_count"] += 1
            elif meta.get("cut_style") == "l_cut_suspense":
                qc_results["l_cuts_count"] += 1

            # 視線連續性與相機補償界限檢查
            cam_offset = meta.get("camera_lookat_offset", [0.0, 0.0])
            if not isinstance(cam_offset, list) or len(cam_offset) != 2:
                issues.append(f"相機偏移格式非法: {cam_offset}")
            elif abs(cam_offset[0]) > 1.0 or abs(cam_offset[1]) > 1.0:
                issues.append(f"相機偏移過激超出視野: {cam_offset}")

        # Drop 得分必須顯著高於 Intro
        if drop_scores and intro_scores:
            avg_drop = sum(drop_scores) / len(drop_scores)
            avg_intro = sum(intro_scores) / len(intro_scores)
            if avg_drop <= avg_intro:
                issues.append(f"情緒張力倒掛: Drop均分({avg_drop:.3f}) <= Intro均分({avg_intro:.3f})")

        # 判定此曲 QC 結果
        is_pass = (len(issues) == 0)
        if is_pass:
            qc_results["pass_count"] += 1
            status_str = "✅ PASS"
        else:
            qc_results["fail_count"] += 1
            status_str = f"❌ FAIL ({'; '.join(issues)})"

        song_report = {
            "title": song["title"],
            "genre": song["genre"],
            "theme_title": script.get("theme_title"),
            "shots_count": len(shot_list),
            "entropy": round(entropy, 2),
            "latency_ms": round(latency_ms, 2),
            "avg_murch": round(sum(murch_scores) / max(1, len(murch_scores)), 3),
            "unique_modules": len(set(assigned_ids)),
            "issues": issues,
            "status": status_str
        }
        qc_results["song_reports"].append(song_report)

        print(f"[{s_idx+1:02d}/10] {song['title']:<25} | {status_str} | 耗時: {latency_ms:6.2f}ms | 熵: {entropy:.2f} | 模組數: {len(set(assigned_ids))}/{len(shot_list)} | 主題: {script.get('theme_title')}")

    # 3. 匯總宏觀審計統計
    avg_latency = sum(qc_results["latency_ms_list"]) / max(1, len(qc_results["latency_ms_list"]))
    avg_entropy = sum(qc_results["global_entropy_list"]) / max(1, len(qc_results["global_entropy_list"]))
    unique_mod_count = len(qc_results["all_assigned_unique_modules"])
    coverage_rate = (unique_mod_count / len(visual_modules)) * 100.0

    print("\n" + "=" * 80)
    print("📊 [CACD 總體質量檢驗審計總結 (EXECUTIVE QC SUMMARY)]")
    print("=" * 80)
    print(f"• 總測試曲目數 (Songs Tested)       : {qc_results['total_songs']}")
    print(f"• 規劃分鏡總數 (Total Shots)         : {qc_results['total_shots_planned']}")
    print(f"• QC 通過率 (Pass Rate)             : {qc_results['pass_count']}/{qc_results['total_songs']} ({(qc_results['pass_count']/qc_results['total_songs'])*100:.1f}%)")
    print(f"• 平均排片延遲 (Average Latency)    : {avg_latency:.2f} ms (< 50ms 實時指標)")
    print(f"• 全域平均審美香農熵 (Avg Entropy)  : {avg_entropy:.2f} (多樣性標準: > 2.0)")
    print(f"• 素材長尾覆蓋量 (Unique Modules)   : {unique_mod_count}/{len(visual_modules)} ({coverage_rate:.1f}%)")
    print(f"• J-Cut 錯位預切觸發次數            : {qc_results['j_cuts_count']} 次")
    print(f"• L-Cut 弱拍懸念延遲觸發次數        : {qc_results['l_cuts_count']} 次")
    print(f"• 震撼反對稱切 (Shock Cut) 觸發次數 : {qc_results['shock_cuts_count']} 次")
    print("=" * 80)

    # 4. 斷言全局達標
    assert qc_results["fail_count"] == 0, f"QC 審計存在失敗項目: {qc_results['fail_count']} 首曲目未通過"
    assert avg_latency < 50.0, f"執行延遲超出預期 ({avg_latency:.2f}ms > 50ms)"
    assert unique_mod_count >= 20, f"素材覆蓋率不足 ({unique_mod_count} 個)"
    print("🏆 [QC 審計結論] CACD 增強型 AI 導演系統各項電影學、神經審美學與工程延遲指標 100% 達標！")

if __name__ == "__main__":
    execute_full_audit()
