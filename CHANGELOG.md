# Git 更新日誌 (Changelog)

本文檔記載 **4K MV Visual Integration Editor** 專案的版本演進與 Git 變更歷史。

---

## 📌 [v1.2.1 / 6eba29d] - 2026-08-06
### 🧹 儲存庫清理、Git 規則與更新文件 (Repository Cleanup & Documentation)
- **版本控制精簡 (`069de5d`)**：
  - 更新 `.gitignore` 規則，精確過濾專案運行產生的暫存與輸出檔案。
  - 忽略大型運行日誌：`*.log`、`*.log.*`、`app_debug.log`、`op_import_errors.txt`
  - 忽略測試報告與預覽 HTML：`*.html`、`black_screen_report.*`、`abnormal_previews.*`、`repair_report.json`
  - 忽略依賴與快取資料夾：`node_modules/`、`models/`、`assets_cache/`、`temp_audio/`、`js_cache/`、`render_output/`
  - 忽略測試音訊與草稿檔：`*.mp3`、`*.wav`、`scratch/`
- **更新日誌建立 (`6eba29d`)**：
  - 建立專案官方 `CHANGELOG.md` 紀錄完整 Git commit 與版本發行日誌。

---

## 🚀 [v1.2.0 / afe0cc8] - 2026-07-28
### 🎨 後處理器強化與 LLM 導演協同 (Post-Processor Enhancement & LLM Synergy)
- **Canvas-First 繪圖保護機制 (`post_processor.py`)**：
  - 最佳化 Canvas 畫布保護邏輯，解決極端動態特效下的畫面坍塌問題。
- **Acid Techno 音樂風格支援**：
  - 增加對 Acid Techno 等高動態節奏風格的音訊響應與視覺過渡效果。
- **LLM 導演系統整合 (`llm_director.py`)**：
  - 提升大語言模型與視覺後處理器之間的指令調度效能，實作更平滑的曲式風格切換。
- **文件發布紀錄 (`eee4b4e`)**：
  - 更新 `README.md`，發布 v1.2.0 發行說明與說明文件。

---

## 🌈 [v1.1.0 / 0d3e569] - 2026-07-15
### 🎭 程序化調色盤、高級 VJ 過渡與光敏安全防護
- **OKLCH 程序化 12 音調色盤 (`procedural_palette_oklch.py`)**：
  - 基於和弦與音高導出和諧、漸層且富彩度的 HSL/OKLCH 視覺調色盤。
- **高階 VJ 切換與過渡系統 (`vj-transitions-and-modulation`)**：
  - 整合 Displacement, Zoom Blur, Luma Matte, Glitch 與 Slide Push 等高幀率相容過渡。
- **光敏性癲癇 (Photosensitive Seizure) 安全防護**：
  - 實作過度閃爍防護控制，自適應降低高頻強光衝擊，符合安全視覺播放標準。
- **文件與授權 (`775e98b`, `8402872`)**：
  - 補全英文版 `README.md` 並開源加入 MIT 授權條款。

---

## 📦 [v1.0.0 / 86505a0] - 2026-07-01
### 🎬 專案初始發行 (Initial Repository Release)
- **核心架構搭建 (`main.py`)**：
  - 建立基於 PyQt6 與 QWebEngineView 的混合型桌面端 MV 編輯器。
- **即時音訊分析矩陣 (`audio_analyzer.py`)**：
  - 支援 Librosa 音訊分析、BPM 追蹤、多頻段能量提取與和弦辨識。
- **Processing 至 p5.js 自動轉譯引擎 (`batch_importer.py` & `code_injector.py`)**：
  - 自動轉譯 Processing 代碼並注入沙盒防崩潰 Stubs。

