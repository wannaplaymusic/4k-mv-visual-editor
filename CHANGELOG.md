# Git 更新日誌 (Changelog)

## 📌 [069de5d] - 2026-08-05
### 🧹 儲存庫清理與忽略規則最佳化 (Repository Cleanup & Gitignore Update)
- **版本控制精簡**：
  - 更新 `.gitignore` 規則，精確過濾專案運行產生的暫存與輸出檔案。
- **忽律無效與暫存檔案**：
  - 忽略大型運行日誌檔：`*.log`、`*.log.*`、`app_debug.log`、`op_import_errors.txt`
  - 忽略測試報告與預覽 HTML：`*.html`、`black_screen_report.*`、`abnormal_previews.*`、`repair_report.json`
  - 忽略快取與資料夾：`node_modules/`、`models/`、`assets_cache/`、`temp_audio/`、`js_cache/`、`render_output/`
  - 忽略測試音訊與草稿檔：`*.mp3`、`*.wav`、`scratch/`

---

## 🚀 [afe0cc8] - 2026-07-28
### 🎨 後處理器強化與 LLM 導演協同 (Post-Processor Enhancement & LLM Synergy)
- **Canvas-First 繪圖保護機制**：
  - 最佳化 `post_processor.py` 中的 Canvas 畫布保護邏輯，解決極端動態特效下的畫面坍塌問題。
- **Acid Techno 音樂風格支援**：
  - 增加對 Acid Techno 等高動態節奏風格的音訊響應與視覺過渡效果。
- **LLM 導演系統整合 (`llm_director.py`)**：
  - 提升大語言模型與視覺後處理器之間的指令調度效能，實作更平滑的曲式風格切換。

---

## 📝 [eee4b4e] - 2026-07-28
### 📄 文件更新 (Documentation)
- **v1.2.0 Release Notes**：更新 `README.md`，記載 v1.2.0 的全新後處理與導演系統功能說明。
