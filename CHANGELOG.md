# Git 更新日誌 (Changelog)

本文檔記載 **4K MV Visual Integration Editor** 專案的版本演進與 Git 變更歷史。

---

## 🚀 [v1.4.0] - 2026-09-06
### 🎨 超現實主義動態拼貼創作、AI 導演編舞與 YouTube 智慧自動上傳管線

- **🖼️ 超現實主義動態拼貼生成器 (Surreal Collage Studio)**：
  - 新增專屬分頁 `surreal_collage_tab.py`，支援智慧去背人體肢體切分（頭部、軀幹、手臂等部件）與異質素材幾何解構。
  - **36 種超現實主義藝術風格矩陣 (`surreal_style_matrix.py` & `surreal_36_styles.py`)**：深度整合達利時鐘、馬格利特青蘋果、古典石膏像、蒸汽波幾何等跨維度概念語意庫。
  - **超現實辯證概念與主題引擎 (`surreal_dialectics.py` & `surreal_theme_engine.py`)**：將音訊情緒與概念衝突映射為視覺張力，實現動態隱喻拼貼佈局。
  - **SOTA 構圖與美學佈局優化器 (`sota_composition_optimizer.py` & `aesthetic_layout_optimizer.py`)**：實作黃金分割比、三分法則、動態平衡度與畫面層次智慧校準。
  - **神經美學評分與視覺注視追蹤 (`neural_aesthetic_scorer.py` & `saliency_eyetrace_bridge.py`)**：結合視覺顯著性 (Saliency) 預測人眼注視焦點，指導動態元素空間排布。
  - **多臂老虎機素材排定演算法 (`bandit_inventory_selector.py`)**：利用 Multi-Armed Bandit (MAB) 平衡素材探索 (Exploration) 與利用 (Exploitation)。
  - **多元素圖層編排與物理漂浮 (`multi_element_orchestrator.py`)**：模擬多層超現實物件的重力懸浮、旋轉與音訊驅動擺動。
  - **專屬 GLSL 氛圍調和著色器 (`shaders/surreal_atmospheric_harmonizer.frag` & `shaders/surreal_harmonizer.frag`)**：提供色調統整、暗角、噪點與膠片光暈質感。
  - **Pinterest 視覺靈感探針 (`pinterest_scraper.py`)**：自動化收集高品質參考視覺意象。

- **📺 YouTube 智慧自動排程與上傳發布套件 (YouTube Auto Uploader Suite)**：
  - 新增專屬分頁 `youtube_uploader_tab.py`，具備視覺化批量上傳佇列、即時進度條、狀態回饋與標籤/說明欄動態管理。
  - **YouTube Data API v3 引擎 (`youtube_uploader_engine.py`)**：支援 Google OAuth 2.0 授權、分塊斷點續傳 (Resumable Chunked Upload)、配額 (Quota) 智慧監控與頻率限流重試機制。
  - **無縫自動上傳整合 (`youtube_auto_upload.py`)**：與 Shorts Exporter 緊密連動，可在 9:16 短片渲染完成後自動加入上傳佇列並完成發布。
  - **API 安全與配置指南 (`YOUTUBE_API_SETUP_GUIDE.md`)**：提供 Google Cloud Console OAuth 2.0 Client 憑證設定、配額防超額機制之詳盡教學。
  - **安全防護強化**：將 `youtube_credentials/` 與 `logs/` 列入 `.gitignore`，徹底杜絕金鑰與 OAuth Token 意外洩漏。

- **🎬 AI 導演曲式編舞與系統深度集成**：
  - **超現實 AI 導演橋接器 (`surreal_director_bridge.py` & `director_choreographer.py`)**：將動態拼貼無縫納入曲式章節（Intro, Verse, Chorus, Drop）與動態編舞。
  - **主程式統合升級 (`main.py`)**：新增 Surreal Collage 與 YouTube Uploader 導航與信號路由，優化全系統多執行緒生命週期。
  - **LLM 導演語意擴展 (`llm_director.py`)**：支援超現實藝術流派提示詞生成與曲式通告單調度。
  - **短片導出聯動 (`shorts_exporter_tab.py`)**：增強豎屏短片導出管線並銜接自動上傳。
  - **AI 導演全流程質檢腳本 (`run_full_ai_director_qc.py`)**：提供完整的通告單執行與渲染 QC 檢驗。
  - **視覺模組庫持續修復**：修復並優化數十個自訂視覺腳本的相容性與語法錯誤。

---

## 🌟 [v1.3.0] - 2026-08-30
### 👾 像素視覺生成器、Shorts 豎屏匯出、AI 導演通告單與全能 QC 審核
- **👾 像素視覺模組生成器 (`pixel_generator_tab.py` & `pixel_ai_engine.py`)**：
  - 新增專屬像素視覺生成器 Tab，支援 15 種經典復古像素與點陣風格（Block 方塊、Bayer4/Bayer8 抖動、Blue Noise 藍噪、Halftone 半色調、Crosshatch 漫畫素描、CRT 螢光粉、Diamond 菱形、ASCII 字符矩陣、Glitch 故障撕裂、Voronoi 水晶多邊形、Voxel 3D 浮雕、Amiga HAM6 流體油畫、Life Game 生命遊戲、FLIR 熱成像）。
  - 整合 WebGL/p5.js 即時沙盒預覽、參數動態微調、調色盤映射以及一鍵存檔收編為標準視覺模組。
- **📱 YouTube Shorts 豎屏短影音批量匯出 (`shorts_exporter_tab.py`)**：
  - 新增專屬短影音批量匯出 Tab，支援 9:16 (1080x1920) 智慧豎屏比例裁切與中心焦點對齊。
  - 支援多曲目、多模組智慧排程與隊列式離線渲染匯出，結合硬體加速與高品質音視壓制。
- **🎬 AI 導演曲式通告單排程系統 (`AIDirectorCallSheetWidget` & `AIDirectorOrchestrationThread`)**：
  - 深度結合曲式段落結構（Intro, Verse, Chorus, Bridge, Drop, Outro），自動排定場景通告單（Call Sheet）。
  - 模組影格智慧快取管理器 (`ModuleFrameCacheManager`) 與降級平滑過渡保護 (`apply_graceful_fallback`)，杜絕切換鏡頭時的卡頓與黑畫面。
- **🛡️ 實時渲染品質與音視響應診斷器 (`realtime_qc_auditor.py`)**：
  - 實時抽幀黑畫面檢測、Drop/Chorus 高潮熱烈度與色彩對比度驗證。
  - 大鼓 (Kick)、小鼓 (Snare)、Hi-hat 動態音視響應審核與自動補償機制。
- **🎨 現代 GLSL 著色器庫 (`shaders/`)**：
  - 新增 34 種高效能 GLSL 後處理與視覺著色器（Raymarching, Volumetric Godrays, SSFR Fluid, Reaction Diffusion, Caustic Grid, Gyroid Surface, Attractor Field, Holographic Interference 等）。
- **🧹 模組庫全面淨化、修復與標準化**：
  - 排查並隔離攝像頭 (Camera/Webcam) 與 WebXR/AR/VR 等硬體相依異常模組，保證運行環境純粹與安全。
  - 強化 p5.js 沙盒免疫 Stubs（DOM 方法、gifProperties、P3D/OPENGL 常數代理）。
  - 修復並標準化數千個視覺模組，補齊縮圖與分類星標管理。
- **⚙️ 儲存庫體積最佳化與 Git 追蹤規則校正**：
  - 修正 `.gitignore` 中的全域通配符規則，確保模組 JSON 與核心相依正確被追蹤，移除非必要日誌與修復報告。

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

