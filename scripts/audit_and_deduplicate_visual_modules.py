#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
4K MV 視覺整合編輯器 - 視覺模組全庫去重清查與隔離引擎
(Visual Module Audit & Safe Deduplication Engine)

核心職責：
1. 深度掃描 custom_visuals/ 目錄下所有模組，按實質規格化程式碼指紋（Normalized Code Fingerprint）分組。
2. 針對每組重複模組，依據影片歷史使用次數、星標、QC健康度、標準命名、縮圖完整度選出唯一「黃金主模組 (Canonical Master)」。
3. 執行「無損元數據融合」：將被剔除副本的 used_in_videos、used_count、is_starred、tags 完整注入主模組。
4. 將多餘重複的 .json 及 thumbnails/*.jpg 移動至專用隔離目錄 custom_visuals/audit_quarantine_duplicates_YYYYMMDD/，可隨時一鍵還原。
5. 同步更新 module_usage_history.json 與 module_expressive_db.json。
6. 產出詳細清查與去重審計報告 (audit_deduplication_report.txt / manifest.json)。
"""

import os
import re
import json
import shutil
import hashlib
import datetime
from collections import defaultdict

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
# If running inside scripts/ directory, go up one level
if os.path.basename(WORKSPACE_DIR) == "scripts":
    WORKSPACE_DIR = os.path.dirname(WORKSPACE_DIR)

CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
THUMBNAILS_DIR = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails")
USAGE_HISTORY_PATH = os.path.join(CUSTOM_VISUALS_DIR, "module_usage_history.json")
EXPRESSIVE_DB_PATH = os.path.join(WORKSPACE_DIR, "module_expressive_db.json")

def normalize_code(code_str: str) -> str:
    """去除單行與多行註解以及所有空白換行的實質代碼規格化"""
    if not code_str:
        return ""
    clean = re.sub(r'//.*', '', code_str)
    clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
    return "".join(clean.split())

def compute_code_hash(code: str, custom_html: str = "") -> str:
    nc = normalize_code(code) + "|||HTML|||" + normalize_code(custom_html)
    return hashlib.sha256(nc.encode("utf-8")).hexdigest()

def score_candidate(fname: str, info: dict, thumb_path: str) -> float:
    """
    評分演算法：
    1. 影片使用紀錄 (used_count / used_in_videos) -> 最高權重 (+100000 * count)
    2. 使用者星標 (is_starred) -> (+50000)
    3. QC 健康度 (無報錯/無黑屏) -> (+10000)
    4. 標準命名規範 (無 _1, _2 等臨時遞增尾綴) -> (+5000)
    5. 縮圖真實有效性 (大小 > 500 bytes) -> (+2000)
    6. 最早收錄時間 (加分)
    """
    score = 0.0
    used_count = info["used_count"]
    if used_count > 0:
        score += 100000.0 * used_count

    if info["is_starred"]:
        score += 50000.0

    if not info["needs_qc"]:
        score += 10000.0

    base_name = fname[:-5]
    if not re.search(r'_\d+$', base_name):
        score += 5000.0

    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 500:
        score += 2000.0

    # 偏好早期加入時間
    date_added = info["date_added"]
    if date_added:
        score += 100.0

    return score

def run_audit_and_deduplicate(dry_run: bool = False):
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_dirname = f"audit_quarantine_duplicates_{now_str}"
    quarantine_dir = os.path.join(CUSTOM_VISUALS_DIR, quarantine_dirname)
    quarantine_thumbs_dir = os.path.join(quarantine_dir, "thumbnails")

    print(f"🔍 [1/6] 正在全面掃描 custom_visuals/ 目錄下的所有視覺模組...")
    all_files = sorted([
        f for f in os.listdir(CUSTOM_VISUALS_DIR)
        if f.endswith(".json") and not f.startswith("manifest") and f not in ("modules_index.json", "module_usage_history.json")
    ])

    total_scanned = len(all_files)
    print(f"📦 總計檢索到 {total_scanned} 個視覺模組 JSON 檔案。")

    PLACEHOLDER_THUMB_MD5S = {
        'd2919f392258962ad55689de3b02c6f0',  # 4K MV blank placeholder
        'baae5a7c53682ba70206cac30c59c66e',  # generic OP placeholder
    }

    file_metadata_cache = {}
    code_map = defaultdict(list)
    visual_thumb_name_map = defaultdict(list)

    # Disjoint Set Union (並查集) 用於無縫融合程式碼指紋與視覺縮圖指紋分組
    parent = {f: f for f in all_files}
    def find_root(i):
        if parent[i] == i:
            return i
        parent[i] = find_root(parent[i])
        return parent[i]
    def union_nodes(i, j):
        root_i, root_j = find_root(i), find_root(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for fname in all_files:
        fpath = os.path.join(CUSTOM_VISUALS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as e:
            print(f"⚠️ 無法解析檔案 {fname}: {e}")
            continue

        code = data.get("code", "")
        custom_html = data.get("custom_html", "")
        used_in = data.get("used_in_videos", [])
        if not isinstance(used_in, list):
            used_in = []
        used_count = max(int(data.get("used_count", 0)), len(used_in))
        is_starred = bool(data.get("is_starred", False))
        needs_qc = bool(data.get("needs_qc_repair", False))
        date_added = data.get("date_added", "")
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        name = data.get("name", fname[:-5])
        url = data.get("url", "").strip()

        thumb_p = os.path.join(THUMBNAILS_DIR, f"{fname[:-5]}.jpg")
        t_md5 = ""
        if os.path.exists(thumb_p) and os.path.getsize(thumb_p) > 500:
            try:
                with open(thumb_p, "rb") as tfp:
                    t_md5 = hashlib.md5(tfp.read()).hexdigest()
            except Exception:
                pass

        info = {
            "data": data,
            "used_in": used_in,
            "used_count": used_count,
            "is_starred": is_starred,
            "needs_qc": needs_qc,
            "date_added": date_added,
            "tags": tags,
            "name": name,
            "url": url,
            "raw_len": len(code),
            "t_md5": t_md5
        }
        file_metadata_cache[fname] = info

        # 1. 程式碼實質規格化指紋 (Tier 1)
        fp_hash = compute_code_hash(code, custom_html)
        code_map[fp_hash].append(fname)

        # 2. 真實預覽縮圖 + 模組名稱指紋 (Tier 2: 攔截微調單一參數/註解作業 Fork，如 21)
        if t_md5 and t_md5 not in PLACEHOLDER_THUMB_MD5S:
            clean_name = re.sub(r'_\d+$', '', name.lower().strip())
            visual_thumb_name_map[(clean_name, t_md5)].append(fname)

    # 執行並查集合併
    for fp_hash, flist in code_map.items():
        for f in flist[1:]:
            union_nodes(flist[0], f)

    for key, flist in visual_thumb_name_map.items():
        for f in flist[1:]:
            union_nodes(flist[0], f)

    clusters = defaultdict(list)
    for fname in all_files:
        if fname in file_metadata_cache:
            clusters[find_root(fname)].append(fname)

    duplicate_groups = {k: v for k, v in clusters.items() if len(v) > 1}
    unique_clusters = len(clusters)
    total_redundant = sum(len(v) - 1 for v in duplicate_groups.values())

    print(f"\n📊 [2/6] 指紋分組分析完成 (Tier 1 程式碼指紋 + Tier 2 視覺畫面指紋)：")
    print(f"   - 獨立唯一視覺樣式數: {unique_clusters}")
    print(f"   - 存在重複收錄的組數: {len(duplicate_groups)}")
    print(f"   - 多餘重複檔案總數:   {total_redundant}")
    print(f"   - 預期去重後模組庫總數: {total_scanned - total_redundant}")

    if total_redundant == 0:
        print("✨ 模組庫內無任何重複視覺模組，完全合規！")
        return

    # 3. 制定精準保留與隔離清單
    print(f"\n🎯 [3/6] 正在進行智慧評分、黃金主模組仲裁與元數據融合...")
    manifest_records = []
    quarantine_files = [] # list of (dup_filename, canonical_filename)
    updated_canonical_files = {} # filename -> updated_data

    for fp_hash, group in duplicate_groups.items():
        # 對群組成員進行評分排序
        sorted_group = sorted(
            group,
            key=lambda fn: (
                score_candidate(
                    fn,
                    file_metadata_cache[fn],
                    os.path.join(THUMBNAILS_DIR, f"{fn[:-5]}.jpg")
                ),
                -1 if not file_metadata_cache[fn]["date_added"] else 0,
                -len(fn) # 偏好較短標準檔名
            ),
            reverse=True
        )

        canonical_fn = sorted_group[0]
        duplicates_fn = sorted_group[1:]

        # 執行元數據融合 (Metadata Merge)
        canonical_info = file_metadata_cache[canonical_fn]
        canonical_data = canonical_info["data"]

        merged_used_in = list(set(canonical_info["used_in"]))
        merged_used_count = canonical_info["used_count"]
        merged_starred = canonical_info["is_starred"]
        merged_tags = list(canonical_info["tags"])

        group_details = []

        for dup_fn in duplicates_fn:
            dup_info = file_metadata_cache[dup_fn]
            # 合併影片使用紀錄
            for v in dup_info["used_in"]:
                if v not in merged_used_in:
                    merged_used_in.append(v)
            merged_used_count = max(merged_used_count, len(merged_used_in), canonical_info["used_count"] + dup_info["used_count"])

            if dup_info["is_starred"]:
                merged_starred = True

            for t in dup_info["tags"]:
                if t not in merged_tags:
                    merged_tags.append(t)

            quarantine_files.append((dup_fn, canonical_fn))
            group_details.append({
                "duplicate_file": dup_fn,
                "name": dup_info["name"],
                "url": dup_info["url"],
                "used_count": dup_info["used_count"],
                "used_in": dup_info["used_in"],
                "needs_qc": dup_info["needs_qc"]
            })

        # 更新 canonical_data
        canonical_data["used_in_videos"] = merged_used_in
        canonical_data["used_count"] = max(merged_used_count, len(merged_used_in))
        canonical_data["is_starred"] = merged_starred
        canonical_data["tags"] = merged_tags

        # 若主模組原本是 15Red_1 但名字是 15Red，確保 name 乾淨
        if "name" not in canonical_data or not canonical_data["name"]:
            canonical_data["name"] = canonical_fn[:-5]

        updated_canonical_files[canonical_fn] = canonical_data

        manifest_records.append({
            "canonical_file": canonical_fn,
            "canonical_name": canonical_data["name"],
            "canonical_url": canonical_info["url"],
            "merged_used_in": merged_used_in,
            "merged_used_count": canonical_data["used_count"],
            "duplicates_quarantined": group_details
        })

    print(f"   ✅ 已完成 {len(duplicate_groups)} 組模組仲裁，即將保留 {len(updated_canonical_files)} 個主模組並融合元數據。")

    if dry_run:
        print("\n🔎 [DRY RUN 模式] 未寫入任何磁碟變更。")
        return

    # 4. 磁碟寫入與安全隔離搬移
    print(f"\n🚚 [4/6] 正在建立隔離備份目錄並移動重複檔案至：\n   {quarantine_dir}")
    os.makedirs(quarantine_thumbs_dir, exist_ok=True)

    # 寫回已更新的主模組
    for canonical_fn, cdata in updated_canonical_files.items():
        cpath = os.path.join(CUSTOM_VISUALS_DIR, canonical_fn)
        with open(cpath, "w", encoding="utf-8") as fp:
            json.dump(cdata, fp, indent=4, ensure_ascii=False)

    # 搬移重複檔案與縮圖
    quarantined_count = 0
    quarantined_thumbs_count = 0

    for dup_fn, canonical_fn in quarantine_files:
        src_json = os.path.join(CUSTOM_VISUALS_DIR, dup_fn)
        dst_json = os.path.join(quarantine_dir, dup_fn)
        if os.path.exists(src_json):
            shutil.move(src_json, dst_json)
            quarantined_count += 1

        base_name = dup_fn[:-5]
        src_thumb = os.path.join(THUMBNAILS_DIR, f"{base_name}.jpg")
        dst_thumb = os.path.join(quarantine_thumbs_dir, f"{base_name}.jpg")
        if os.path.exists(src_thumb):
            shutil.move(src_thumb, dst_thumb)
            quarantined_thumbs_count += 1

    print(f"   📦 成功安全隔離 {quarantined_count} 個重複 JSON 檔案與 {quarantined_thumbs_count} 張多餘預覽縮圖！")

    # 5. 更新全域使用紀錄與表現力特徵庫
    print(f"\n🔄 [5/6] 正在同步更新模組歷史庫與數據庫...")
    # 更新 module_usage_history.json
    if os.path.exists(USAGE_HISTORY_PATH):
        try:
            with open(USAGE_HISTORY_PATH, "r", encoding="utf-8") as fp:
                usage_history = json.load(fp)

            history_modified = False
            for dup_fn, canonical_fn in quarantine_files:
                dup_key = dup_fn[:-5]
                canonical_key = canonical_fn[:-5]
                if dup_key in usage_history:
                    count = usage_history.pop(dup_key)
                    usage_history[canonical_key] = usage_history.get(canonical_key, 0) + count
                    history_modified = True

            if history_modified:
                with open(USAGE_HISTORY_PATH, "w", encoding="utf-8") as fp:
                    json.dump(usage_history, fp, indent=4, ensure_ascii=False)
                print("   ✅ module_usage_history.json 已合併轉移完畢。")
        except Exception as e:
            print(f"⚠️ 更新 module_usage_history.json 時發生錯誤: {e}")

    # 更新 module_expressive_db.json
    if os.path.exists(EXPRESSIVE_DB_PATH):
        try:
            with open(EXPRESSIVE_DB_PATH, "r", encoding="utf-8") as fp:
                expressive_db = json.load(fp)

            exp_modified = False
            for dup_fn, canonical_fn in quarantine_files:
                dup_key = dup_fn[:-5]
                canonical_key = canonical_fn[:-5]
                if dup_key in expressive_db:
                    data_val = expressive_db.pop(dup_key)
                    if canonical_key not in expressive_db:
                        expressive_db[canonical_key] = data_val
                    exp_modified = True

            if exp_modified:
                with open(EXPRESSIVE_DB_PATH, "w", encoding="utf-8") as fp:
                    json.dump(expressive_db, fp, indent=4, ensure_ascii=False)
                print("   ✅ module_expressive_db.json 已合併更新完畢。")
        except Exception as e:
            print(f"⚠️ 更新 module_expressive_db.json 時發生錯誤: {e}")

    # 6. 產出清查報告與還原清單
    manifest_data = {
        "timestamp": now_str,
        "quarantine_directory": quarantine_dir,
        "total_scanned_before": total_scanned,
        "total_kept_unique": total_scanned - quarantined_count,
        "total_quarantined": quarantined_count,
        "total_quarantined_thumbnails": quarantined_thumbs_count,
        "duplicate_groups_count": len(duplicate_groups),
        "groups": manifest_records
    }

    manifest_file = os.path.join(quarantine_dir, "manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as fp:
        json.dump(manifest_data, fp, indent=4, ensure_ascii=False)

    report_text_path = os.path.join(WORKSPACE_DIR, "audit_deduplication_report.txt")
    with open(report_text_path, "w", encoding="utf-8") as fp:
        fp.write("=" * 80 + "\n")
        fp.write(f"4K MV Visual Integration Editor - 全庫視覺模組清查與去重隔離報告\n")
        fp.write(f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        fp.write(f"隔離備份目錄: {quarantine_dir}\n")
        fp.write("=" * 80 + "\n\n")
        fp.write(f"【核心統計】\n")
        fp.write(f"- 清查前總模組數:     {total_scanned} 個\n")
        fp.write(f"- 排除多餘重複模組:   {quarantined_count} 個\n")
        fp.write(f"- 保留精華主模組:     {total_scanned - quarantined_count} 個\n")
        fp.write(f"- 排除多餘縮圖:       {quarantined_thumbs_count} 張\n")
        fp.write(f"- 解決重複收錄組數:   {len(duplicate_groups)} 組\n\n")
        fp.write("【代表性重複案例清單（節錄）】\n")
        for rec in manifest_records[:30]:
            fp.write(f"▶ 保留主模組: {rec['canonical_file']} (名稱: {rec['canonical_name']})\n")
            fp.write(f"  來源: {rec['canonical_url']}\n")
            fp.write(f"  已使用影片: {rec['merged_used_in']} (累計使用次數: {rec['merged_used_count']})\n")
            fp.write(f"  已隔離的重複副本:\n")
            for d in rec['duplicates_quarantined']:
                fp.write(f"    - {d['duplicate_file']} (來源: {d['url']}, 使用: {d['used_count']} 次)\n")
            fp.write("\n")

    print(f"\n🎉 [6/6] 全庫清查與去重程序圓滿完成！")
    print(f"   📋 隔離清單記錄於: {manifest_file}")
    print(f"   📄 詳細審查報告於: {report_text_path}")
    print(f"   💡 現存於 custom_visuals/ 的模組數由 {total_scanned} 降至精準純淨的 {total_scanned - quarantined_count} 個！")

if __name__ == "__main__":
    import sys
    dry_run_flag = "--dry-run" in sys.argv
    run_audit_and_deduplicate(dry_run=dry_run_flag)
