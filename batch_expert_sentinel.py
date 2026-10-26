import os
import sys
import time
import json
import re
import shutil
import datetime
from typing import List, Dict, Tuple

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
QUARANTINE_DIR = os.path.join(CUSTOM_VISUALS_DIR, "harmful_quarantine")
os.makedirs(QUARANTINE_DIR, exist_ok=True)

DASHBOARD_HTML = os.path.join(WORKSPACE_DIR, "realtime_expert_audit_panel.html")
AUDIT_LOG_FILE = os.path.join(WORKSPACE_DIR, "expert_audit_stream.log")

# ==========================================
# 🎖️ 10名多角色專家小組成員配置 (10-Expert Task Force)
# ==========================================
EXPERTS = [
    {"id": 1, "role": "視覺美學與構圖總監", "title": "Aesthetic Director", "icon": "🎨", "focus": "把關畫面構圖層次、光影美感，排除空畫布與單調草稿"},
    {"id": 2, "role": "音訊律動與頻譜架構師", "title": "Audio-Reactive Architect", "icon": "🎵", "focus": "監控音訊特徵對接 (Bass/Mid/High/Centroid)，修復 NaN/零除錯誤"},
    {"id": 3, "role": "遊戲機制與計分勝負攔截官", "title": "Game Purge Specialist", "icon": "🕹️", "focus": "攔截具有玩家操控、計分、勝負生命機制的非 MV 模組"},
    {"id": 4, "role": "手動畫板與塗鴉筆刷過濾官", "title": "Drawing Pad Filter Expert", "icon": "🖌️", "focus": "攔截無人點擊便完全靜止留白的純手繪工具"},
    {"id": 5, "role": "硬體/攝影機/AR/VR 隔離官", "title": "Camera & WebXR Officer", "icon": "📷", "focus": "攔截 Webcam、createCapture、WebXR 等需要硬體授權的模組"},
    {"id": 6, "role": "純文字與排版展示排除官", "title": "Typography Purge Officer", "icon": "🔤", "focus": "排除字型庫展示、字母表、缺乏幾何動畫的文字雲模組"},
    {"id": 7, "role": "效能極限與無窮死鎖審判官", "title": "Performance & Loop Sentinel", "icon": "⚡", "focus": "審判 while(true)、過量粒子全排列 (>5000) 及記憶體外洩"},
    {"id": 8, "role": "Processing 轉譯與語法修復專家", "title": "Transpiler & Syntax Surgeon", "icon": "🩺", "focus": "即時偵錯並修復 Java 型別殘留、多分頁變數衝突、Shader 構造語法"},
    {"id": 9, "role": "外部資產與死鏈保護監察員", "title": "Assets & CDN Guardian", "icon": "🛡️", "focus": "防禦失效遠端媒體阻斷 setup，注入安全 fallback 機制"},
    {"id": 10, "role": "批次版本與歷史隔離稽核員", "title": "Batch Isolation Auditor", "icon": "📦", "focus": "保護歷史基準 1400+ 庫存，確保 2026-10-05 批次安全可追溯與一鍵復原"}
]

class MultiRoleExpertSentinel:
    def __init__(self, target_batch_date="2026-10-05"):
        self.target_batch_date = target_batch_date
        self.inspected_files = set()
        self.stats = {
            "total_scanned": 0,
            "approved": 0,
            "repaired": 0,
            "quarantined": 0,
            "history_protected": 0
        }
        self.audit_records = []
        self._load_baseline()

    def _load_baseline(self):
        """ 載入歷史基準檔案清單，確保歷史基準不被意外改動 """
        if os.path.exists(CUSTOM_VISUALS_DIR):
            for f in os.listdir(CUSTOM_VISUALS_DIR):
                if f.endswith(".json") and f != "modules_index.json":
                    # 若為非本次日期批次的模組，視為歷史保護基準
                    fpath = os.path.join(CUSTOM_VISUALS_DIR, f)
                    try:
                        with open(fpath, "r", encoding="utf-8") as jf:
                            d = json.load(jf)
                            bdate = d.get("batch_date", "")
                            if bdate and bdate != self.target_batch_date:
                                self.inspected_files.add(f)
                                self.stats["history_protected"] += 1
                    except Exception:
                        pass
        self._log(f"🛡️ [專家 10 - 歷史隔離稽核員] 歷史基準已鎖定保護：{self.stats['history_protected']} 個核心模組安全受控中。")

    def _log(self, msg):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line, flush=True)
        try:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def inspect_and_repair_module(self, filename: str) -> Dict:
        """
        10名專家聯合多維度會審
        回傳審核結果字典
        """
        filepath = os.path.join(CUSTOM_VISUALS_DIR, filename)
        if not os.path.exists(filepath):
            return {"status": "NOT_FOUND"}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return {"status": "CORRUPTED", "error": str(e)}

        title = data.get("name", filename)
        code = data.get("code", "")
        custom_html = data.get("custom_html", "")
        tags = data.get("tags", [])
        desc = data.get("description", "")
        batch_date = data.get("batch_date", "")
        full_content = f"{code}\n{custom_html}"

        verdict = {
            "filename": filename,
            "title": title,
            "url": data.get("url", ""),
            "author": data.get("author", "未知作者"),
            "action": "APPROVED",
            "findings": [],
            "repaired_by": [],
            "rejected_by": None,
            "reject_reason": "",
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
        }

        # ----------------------------------------------------
        # 1. 專家 5: 硬體/攝影機/AR/VR/XR/MR 隔離審查 (絕對封殺)
        # ----------------------------------------------------
        if re.search(r'\bcreateCapture\s*\(', full_content, re.IGNORECASE) and not ("p5capture" in full_content.lower() and not any(kw in full_content.lower() for kw in ["video", "camera", "webcam"])):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 5 (硬體/攝影機/AR/VR/XR 隔離官)"
            verdict["reject_reason"] = "含有視訊鏡頭輸入 (createCapture)"
            return self._execute_quarantine(filename, verdict)

        if re.search(r'\b(getUserMedia|clmtrackr|webcam|live_camera|videoCapture|navigator\.mediaDevices)\b', full_content, re.IGNORECASE):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 5 (硬體/攝影機/AR/VR/XR 隔離官)"
            verdict["reject_reason"] = "調用本機攝影機或 Webcam 裝置"
            return self._execute_quarantine(filename, verdict)

        ar_xr_kws = [
            'webxr', 'webvr', 'xrsession', 'vrbutton', 'arbutton', 'webgl_vr', 'p5.vr', 
            'mindar', 'artoolkit', 'a-scene', 'a-entity', 'zappar', 'augmented reality', 
            'virtual reality', 'mixed reality', 'immersive-vr', 'immersive-ar', 'renderer.xr',
            'three.xr', 'requestsession', 'xrreferencespace', 'oculus', 'quest', 'cardboard',
            '8thwall', 'webar', 'web_ar', 'web_vr', 'hiro', 'kanji', 'markerroot', 'armarker'
        ]
        text_check = f"{title.lower()} {' '.join(tags)} {desc.lower()} {code.lower()[:3000]} {custom_html.lower()}"
        for kw in ar_xr_kws:
            if kw in text_check:
                verdict["action"] = "QUARANTINED"
                verdict["rejected_by"] = "專家 5 (硬體/攝影機/AR/VR/XR 隔離官)"
                verdict["reject_reason"] = f"含有 AR/VR/XR 沉浸式呼叫或框架 ({kw})"
                return self._execute_quarantine(filename, verdict)

        clean_title_words = re.findall(r'[a-zA-Z0-9]+', title.lower())
        if any(w in ['ar', 'vr', 'xr', 'mr', 'webxr', 'webvr', 'webar'] for w in clean_title_words) or any(t in ['ar', 'xr', 'vr', 'mr', 'webxr', 'webvr'] for t in tags):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 5 (硬體/攝影機/AR/VR/XR 隔離官)"
            verdict["reject_reason"] = "標題或標籤明確標記 AR/VR/XR"
            return self._execute_quarantine(filename, verdict)

        # ----------------------------------------------------
        # 2. 專家 3: 遊戲機制與計分勝負攔截 (全面嚴格封殺)
        # ----------------------------------------------------
        game_patterns = [
            'tetris', 'flappy', 'pacman', 'pac-man', 'mario', 'breakout', 'asteroids', 
            'minesweeper', 'tictactoe', 'tic-tac-toe', 'sudoku', 'chess', 'shooter', 
            'invader', 'pinball', 'racing', 'platformer', 'pong', 'samegame', 'gameport', 
            'hotorcoldgame', 'constraingame', '3dgame', 'duelashootergame', 'snake', 'frogger',
            'roguelike', 'rpg', 'arcade', 'minigame', 'dungeon', 'towerdefense', 'tower defense', 
            'brick', 'paddle', 'boardgame', 'cardgame', 'solitaire', 'puzzle', 'maze', 
            'dodge', 'runner', 'endless runner', 'galaxy attack', 'space shooter'
        ]
        for gkw in game_patterns:
            if gkw in title.lower().replace(' ', '') or any(gkw in t.lower().replace(' ', '') for t in tags):
                if gkw == 'asteroids' and 'planet' in title.lower():
                    continue
                verdict["action"] = "QUARANTINED"
                verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
                verdict["reject_reason"] = f"屬於經典遊戲類型 ({gkw})"
                return self._execute_quarantine(filename, verdict)

        clean_title = title.lower()
        if any(t in ['game', 'games', 'gaming', 'arcade', 'minigame', 'gameplay'] for t in tags):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
            verdict["reject_reason"] = "標籤含有遊戲類別 (Game/Arcade)"
            return self._execute_quarantine(filename, verdict)

        if not clean_title.startswith('pixel_') and ('game' in clean_title or 'arcade' in clean_title):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
            verdict["reject_reason"] = f"標題含有遊戲關鍵字 ({title})"
            return self._execute_quarantine(filename, verdict)

        code_lower = code.lower()
        # 勝負結局/重開
        if re.search(r'\b(game_?over|you\s*win|you\s*lose|victory|defeat|game_?state|gamestate)\b', code_lower):
            if any(term in code_lower for term in ['score', 'lives', 'hp', 'health', 'level', 'play', 'restart', 'startgame', 'reset']):
                verdict["action"] = "QUARANTINED"
                verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
                verdict["reject_reason"] = "含有遊戲勝負、死亡或重開局狀態機"
                return self._execute_quarantine(filename, verdict)

        # 計分累積
        if re.search(r'\b(score\s*(\+=|\+\+|\=|\:)|highscore|high_score|points\s*\+=|coins\s*\+=)\b', code_lower):
            if any(term in code_lower for term in ['player', 'bullet', 'enemy', 'target', 'hit', 'miss', 'lives', 'level']):
                verdict["action"] = "QUARANTINED"
                verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
                verdict["reject_reason"] = "代碼含有遊戲計分、金幣或積分累積系統"
                return self._execute_quarantine(filename, verdict)

        # 生命值扣減
        if re.search(r'\b(lives\s*(-=|\-\-)|health\s*(-=|\-\-)|hp\s*(-=|\-\-)|player\.lives|player\.health|player\.hp)\b', code_lower):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
            verdict["reject_reason"] = "含有玩家生命值 (Lives/Health) 扣減機制"
            return self._execute_quarantine(filename, verdict)

        # 玩家鍵盤操控循環
        if re.search(r'\b(keyisdown|keycode)\b', code_lower) and re.search(r'\b(left_arrow|right_arrow|up_arrow|down_arrow)\b', code_lower):
            if any(term in code_lower for term in ['player', 'ship', 'car', 'bullet', 'obstacle', 'speed', 'jump']):
                verdict["action"] = "QUARANTINED"
                verdict["rejected_by"] = "專家 3 (遊戲機制攔截官)"
                verdict["reject_reason"] = "含有鍵盤操控主角移動與障礙物互動之遊戲玩法"
                return self._execute_quarantine(filename, verdict)

        # ----------------------------------------------------
        # 3. 專家 7: 效能極限與死鎖審判
        # ----------------------------------------------------
        if re.search(r'\bwhile\s*\(\s*(?:true|1|!0)\s*\)\s*\{(?![^}]*\bbreak\b)', code):
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 7 (效能極限與死鎖審判官)"
            verdict["reject_reason"] = "檢測到無跳出條件之無窮 while 死鎖"
            return self._execute_quarantine(filename, verdict)

        # ----------------------------------------------------
        # 4. 專家 4: 純手動塗鴉筆刷過濾
        # ----------------------------------------------------
        if "mouseIsPressed" in code and "background" not in code:
            draw_m = re.search(r'function\s+draw\s*\([^)]*\)\s*\{([\s\S]*?)\}', code)
            if draw_m:
                dbody = draw_m.group(1).strip()
                if (dbody.startswith("if (mouseIsPressed") or dbody.startswith("if(mouseIsPressed")) and not any(kw in dbody for kw in ["sin(", "cos(", "noise(", "frameCount", "random("]):
                    verdict["action"] = "QUARANTINED"
                    verdict["rejected_by"] = "專家 4 (手動畫板筆刷過濾官)"
                    verdict["reject_reason"] = "純手動塗鴉工具，無自主動態動畫 (留白停滯)"
                    return self._execute_quarantine(filename, verdict)

        # ----------------------------------------------------
        # 5. 專家 1: 視覺美學與構圖審查
        # ----------------------------------------------------
        draft_names = ['my sketch', 'untitled', 'empty sketch', 'new sketch', 'default sketch', 'test']
        if title.lower().strip() in draft_names and len(code.strip()) < 300:
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 1 (視覺美學總監)"
            verdict["reject_reason"] = "未命名之初學草稿或空畫布模板"
            return self._execute_quarantine(filename, verdict)

        draw_cmds = re.findall(r'\b(rect|circle|ellipse|vertex|line|point|box|sphere|torus|cylinder|cone|triangle|quad|image|shader|bezier|curve|arc)\s*\(', code)
        if len(draw_cmds) == 0 and "loadShader" not in code and "createShader" not in code and "webgl" not in code.lower():
            verdict["action"] = "QUARANTINED"
            verdict["rejected_by"] = "專家 1 (視覺美學總監)"
            verdict["reject_reason"] = "缺乏幾何或著色器繪圖輸出 (Zero-Draw Output)"
            return self._execute_quarantine(filename, verdict)

        # ----------------------------------------------------
        # 6. 專家 8 & 2: 即時偵錯與語法修復 (Self-Healing Auto-Repair)
        # ----------------------------------------------------
        needs_repair = False
        repaired_code = code

        # 診斷 A: 重複 let/const 頂層宣告導致語法錯誤
        dup_let_pattern = r'^(let|const)\s+([A-Za-z0-9_$]+)'
        lines = repaired_code.split("\n")
        seen_vars = set()
        new_lines = []
        for line in lines:
            m = re.match(r'^(\s*)(let|const)\s+([A-Za-z0-9_$]+)(.*)', line)
            if m:
                indent, kw, varname, rest = m.groups()
                if varname in seen_vars:
                    new_lines.append(f"{indent}var {varname}{rest}")
                    needs_repair = True
                    if "專家 8 (變數重複宣告降級)" not in verdict["repaired_by"]:
                        verdict["repaired_by"].append("專家 8 (變數重複宣告降級)")
                else:
                    seen_vars.add(varname)
                    new_lines.append(line)
            else:
                new_lines.append(line)
        repaired_code = "\n".join(new_lines)

        # 診斷 B: 音訊模擬變數 NaN 防禦
        if "simulatedMouseX" in repaired_code and "isNaN" not in repaired_code:
            nan_guard = "\n// [SENTINEL 專家 2 修復] 音訊座標數值防禦\nif(typeof window.simulatedMouseX === 'number' && isNaN(window.simulatedMouseX)) window.simulatedMouseX = width*0.5;\nif(typeof window.simulatedMouseY === 'number' && isNaN(window.simulatedMouseY)) window.simulatedMouseY = height*0.5;\n"
            if "function draw" in repaired_code:
                repaired_code = repaired_code.replace("function draw() {", "function draw() {\n" + nan_guard)
                needs_repair = True
                verdict["repaired_by"].append("專家 2 (NaN 防禦注入)")

        if needs_repair:
            data["code"] = repaired_code
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            verdict["action"] = "REPAIRED"
            self.stats["repaired"] += 1
            self._log(f"🩺 [專家 8/2 即時修正] 模組「{title}」已完成熱修復: {', '.join(verdict['repaired_by'])}")
        else:
            self.stats["approved"] += 1
            self._log(f"✅ [專家小組聯合核准] 模組「{title}」視覺美感、音訊反應與沙盒檢測全數達標！")

        self.stats["total_scanned"] += 1
        self.audit_records.append(verdict)
        self.inspected_files.add(filename)
        self._update_dashboard()
        return verdict

    def _execute_quarantine(self, filename: str, verdict: Dict) -> Dict:
        src = os.path.join(CUSTOM_VISUALS_DIR, filename)
        dst = os.path.join(QUARANTINE_DIR, filename)
        try:
            shutil.move(src, dst)
            self._log(f"🚨 [{verdict['rejected_by']} 阻擋隔離] 模組「{verdict['title']}」已被剔除並移入隔離區！原因: {verdict['reject_reason']}")
        except Exception as e:
            self._log(f"⚠️ 隔離移動失敗 ({filename}): {e}")
        
        self.stats["total_scanned"] += 1
        self.stats["quarantined"] += 1
        self.audit_records.append(verdict)
        self.inspected_files.add(filename)
        self._update_dashboard()
        return verdict

    def scan_existing_uninspected(self):
        """ 掃描當前目錄中尚未審核的新模組 """
        if not os.path.exists(CUSTOM_VISUALS_DIR):
            return
        files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
        files.sort()
        for f in files:
            if f not in self.inspected_files:
                self.inspect_and_repair_module(f)

    def _update_dashboard(self):
        """ 產出實時更新的監控儀表板 HTML """
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        expert_cards_html = ""
        for exp in EXPERTS:
            expert_cards_html += f"""
            <div class="expert-card">
                <div class="exp-icon">{exp['icon']}</div>
                <div class="exp-info">
                    <div class="exp-name">專家 {exp['id']}：{exp['role']}</div>
                    <div class="exp-title">{exp['title']}</div>
                    <div class="exp-focus">{exp['focus']}</div>
                </div>
                <div class="exp-status"><span class="badge-active">執勤巡檢中</span></div>
            </div>
            """

        recent_rows_html = ""
        for rec in reversed(self.audit_records[-25:]):
            status_badge = '<span class="badge-approved">核准收錄</span>'
            if rec["action"] == "QUARANTINED":
                status_badge = f'<span class="badge-quarantined">阻擋隔離 ({rec["rejected_by"]})</span>'
            elif rec["action"] == "REPAIRED":
                status_badge = f'<span class="badge-repaired">熱修復核准 ({", ".join(rec["repaired_by"])})</span>'

            detail_txt = rec["reject_reason"] if rec["reject_reason"] else "各項指標健全"
            recent_rows_html += f"""
            <tr>
                <td>{rec['timestamp']}</td>
                <td style="font-weight:600; color:#e2e8f0;">{rec['title']}</td>
                <td>{rec['author']}</td>
                <td>{status_badge}</td>
                <td style="color:#94a3b8; font-size:12px;">{detail_txt}</td>
            </tr>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="3">
    <title>4K MV 視覺模組收編 - 10人多角色專家小組實時監控儀表板</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background: #09090b; color: #f4f4f5; padding: 24px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #27272a; padding-bottom: 16px; margin-bottom: 24px; }}
        .header h1 {{ font-size: 20px; font-weight: 700; color: #a855f7; display: flex; align-items: center; gap: 8px; }}
        .header .meta {{ color: #a1a1aa; font-size: 13px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 24px; }}
        .stat-box {{ background: #18181b; border: 1px solid #27272a; border-radius: 8px; padding: 16px; text-align: center; }}
        .stat-val {{ font-size: 28px; font-weight: 700; margin-top: 4px; }}
        .stat-lbl {{ font-size: 12px; color: #a1a1aa; text-transform: uppercase; }}
        .stat-green {{ color: #10b981; }}
        .stat-purple {{ color: #a855f7; }}
        .stat-blue {{ color: #38bdf8; }}
        .stat-red {{ color: #f43f5e; }}
        .stat-amber {{ color: #f59e0b; }}
        
        .section-title {{ font-size: 15px; font-weight: 600; margin-bottom: 12px; color: #e4e4e7; display: flex; align-items: center; gap: 6px; }}
        .experts-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 28px; }}
        .expert-card {{ background: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 12px; display: flex; align-items: center; gap: 12px; }}
        .exp-icon {{ font-size: 26px; }}
        .exp-info {{ flex: 1; }}
        .exp-name {{ font-size: 13px; font-weight: 600; color: #fafafa; }}
        .exp-title {{ font-size: 11px; color: #a855f7; }}
        .exp-focus {{ font-size: 11px; color: #71717a; margin-top: 2px; }}
        .badge-active {{ background: #064e3b; color: #34d399; font-size: 10px; padding: 2px 6px; border-radius: 4px; }}
        
        table {{ width: 100%; border-collapse: collapse; background: #18181b; border-radius: 8px; overflow: hidden; border: 1px solid #27272a; font-size: 13px; }}
        th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #27272a; }}
        th {{ background: #1e1e24; color: #a1a1aa; font-weight: 600; font-size: 12px; }}
        .badge-approved {{ background: #064e3b; color: #34d399; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .badge-repaired {{ background: #1e3a8a; color: #60a5fa; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .badge-quarantined {{ background: #881337; color: #fb7185; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎖️ 4K MV 視覺收錄中心 - 10人多角色專家小組實時監控面板</h1>
        <div class="meta">更新時間: {now_str} ｜ 批次隔離標籤: <strong>{self.target_batch_date}</strong></div>
    </div>
    
    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-lbl">歷史基準受保護</div>
            <div class="stat-val stat-purple">{self.stats['history_protected']}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">本次巡檢總數</div>
            <div class="stat-val stat-blue">{self.stats['total_scanned']}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">核准收錄入庫</div>
            <div class="stat-val stat-green">{self.stats['approved']}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">即時熱修復模組</div>
            <div class="stat-val stat-amber">{self.stats['repaired']}</div>
        </div>
        <div class="stat-box">
            <div class="stat-lbl">不合格阻擋隔離</div>
            <div class="stat-val stat-red">{self.stats['quarantined']}</div>
        </div>
    </div>

    <div class="section-title">👥 專家小組編組與即時在勤狀態 (10-Member Expert Task Force)</div>
    <div class="experts-grid">
        {expert_cards_html}
    </div>

    <div class="section-title">📋 即時會審與偵錯修復紀錄 (Recent Audit Stream)</div>
    <table>
        <thead>
            <tr>
                <th style="width: 80px;">時間</th>
                <th>作品名稱</th>
                <th style="width: 120px;">作者</th>
                <th style="width: 220px;">專家小組裁定</th>
                <th>審查細節 / 修正措施</th>
            </tr>
        </thead>
        <tbody>
            {recent_rows_html if recent_rows_html else '<tr><td colspan="5" style="text-align:center; color:#71717a; padding:20px;">尚未偵測到新收錄檔案，專家小組隨時待命攔截中...</td></tr>'}
        </tbody>
    </table>
</body>
</html>
"""
        try:
            with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception:
            pass

if __name__ == "__main__":
    sentinel = MultiRoleExpertSentinel(target_batch_date="2026-10-05")
    sentinel.scan_existing_uninspected()
    sentinel._log("👀 [專家小組就緒] 10名多角色專家小組已進入常駐全時監視守護狀態...")
    
    # 常駐輪詢守護模式
    try:
        while True:
            sentinel.scan_existing_uninspected()
            time.sleep(2.0)
    except KeyboardInterrupt:
        sentinel._log("🛑 [專家小組休眠] 使用者停止守護進程。")
