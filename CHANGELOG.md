# Git 更新日誌 (Changelog)

本文檔記載 **4K MV Visual Integration Editor** 專案的版本演進與 Git 變更歷史。

---

## 🚀 [v1.5.0] - 2026-09-24
### 🎬 CINEDANCE 影視級鏡頭光學編譯系統、12 大旗艦 VJ 音畫特效矩陣、PSE 光敏健康防護、VisualStudio Pro 4K 神經創作工作站與批次收編時光機回溯

- **🎬 CINEDANCE 影視級鏡頭光學編譯系統 (`cinedance_compiler.py`, `director_choreographer.py`, `tests/`)**：
  - **核心理念對齊**：融合 Higgsfield CINEDANCE 影視級幾何光學編譯核心理念，為 AI 導演分鏡與 4K 即時渲染注入專業鏡頭光學約束。
  - **`ShotRiskAuditor` 鏡頭風險審計器**：靜態分析角速度、持續時間、運動對比與視場角，實施動態風險評級（低/中/高）與自動降級防翻車（Auto Mitigation），杜絕模型形變坍縮與渲染溢出。
  - **`DynamicFOVCompiler` 動態視場角與 Dolly Zoom 編譯器**：依據樂段張力與曲式演進即時求解水平視場角（H-FOV 24°~110°），並精確計算滑軌變焦反向補償比例，實現影視級滑軌變焦特效。
  - **`ElasticSpatialGrounder` NDC 空間幾何錨定**：支援前景、中景、遠景三層景深彈性拉簧幾何錨定與慣性阻尼，維持視覺質心（Eye-Trace）在切鏡時的連貫舒適度。
  - **`LightTriadSolver` 空間三元光學向量求解器**：計算主體、光源與相機三維空間朝向向量與菲涅爾視線夾角，精準傳遞至著色器與光影渲染。
  - **雙軌生成架構**：同步輸出 4K 即時渲染幾何矩陣參數與生成式 AI 視頻提示詞（Camera Prompt Ensembles）。

- **⚡ 12 大旗艦級 VJ 音畫特效矩陣 & Oklab 感知色彩空間 (`post_processor.py`)**：
  - **旗艦全域音視特效**：
    - `apply_chladni_cymatics_custom`（克拉尼聲波駐波紋）：聲學幾何共振與幾何節線發光沙紋。
    - `apply_ferrofluid_spikes_custom`（磁流體刺針湧動）：低音重拍爆發金屬磁針與漆黑液體流變。
    - `apply_volumetric_caustics_custom`（體積焦散光網）：水下折射聚焦光網與空靈和弦調色。
    - `apply_clifford_torus_warp_custom`（四維克利福德環面扭曲）：非歐幾何拓撲超曲面旋轉映射。
    - `apply_holographic_moire_custom`（全息莫爾干涉）：高頻打擊樂微米光柵干涉與彩色虹彩。
  - **生理光學與感知特效**：
    - `apply_lens_defocus_custom`（鏡頭失焦散景）：大光圈呼吸感散景、移軸徑向景深與電影黑柔焦。
    - `apply_ocular_tremor_custom`（微眼震顫眼動追蹤）：眼跳微幅抖動與注視點動態偏移。
    - `apply_quantum_decoherence_custom`（量子退相干時空噪斑）：相干性塌縮量子雜訊與時空裂痕。
    - `apply_latent_hallucination_custom`（神經潛在空間幻覺）：高維特徵向量流動與多重感知扭曲。
    - `apply_tape_head_drag_custom`（磁頭拖曳類比帶磁滯）：類比磁帶磁滯拖尾與音畫失真抖晃。
    - `apply_huffman_entropy_collapse_custom`（哈夫曼熵坍縮）：數位壓縮失真與資訊熵崩解撕裂。
    - `apply_spectral_fractal_shear_custom`（頻譜分形剪切）：聲音諧波驅動之分形幾何剪切拉伸。
  - **Oklab 感知一致性色彩空間**：全套原生 NumPy `srgb_to_oklab` 與 `oklab_to_srgb` 矩陣轉換。
  - **多樣性加權無放回抽樣與歷史種子追蹤**：實作 `_weighted_sample_no_replace` 與 `_save_vj_fx_history`，杜絕連貫影格效果重複並記錄隨機歷程。

- **🛡️ 國際廣播醫療標準 PSE 光敏性癲癇健康防護器 (`post_processor.py`)**：
  - **`PhotosensitiveSafetyLimiter`**：嚴格依循 ITU-R BT.1702 國際廣播安全標準。
  - 實時監控 3Hz~30Hz 頻率範圍內的螢幕整體亮度劇烈翻轉（Luminance Transitions）與飽和紅光閃爍（Saturated Red Flashing）。
  - 當連續翻轉或紅光能量超標時，自動觸發 Sigmoid 軟壓制與平滑箝位，從根本上杜絕引發光敏性癲癇風險。

- **🧠 有機心靈著色器調變與層級化語義軟投影 (`expressive_modulator.py`, `semantic_soft_projector.py`, `module_expressive_db.json`)**：
  - **`ExpressiveModulator`**：引入彈道非對稱阻尼動態濾波（Attack 25ms / Release 350ms），將狂暴高頻打擊轉化為深具電影感呼吸節奏的心跳律動；輸出 `u_tension`, `u_chaos`, `u_sublime`, `u_dissolution` 心靈著色器參數。
  - **`SemanticSoftProjector`**：消除冷門模組防疲勞限制與心靈標籤剛性過濾間的挑選死鎖，建立精確心靈狀態、榮格原型拓撲鄰域放寬與 OKLCH 色彩/幾何承接三級防禦回退機制。

- **🚀 全新 VisualStudio Pro 4K 視覺神經創作工作站 (`visual_studio.py`, `visual_studio_core/`, `visual_studio_web/`)**：
  - **桌面工作站深度整合**：主界面一鍵啟動獨立進程工作站（`launch_visual_studio_pro`）。
  - **模組化動態設備機架**：提供動態設備機架（Device Rack）、AST 參數即時抽取與雙向調試。
  - **大師美學核心（Maestro Engine）**：聲學鏡像、氛圍繆斯、隱喻煉金、品味分析、視覺反編譯。
  - **雙緩衝沙盒**：雙緩衝 WebGL/p5.js 沙盒與實時雙向音訊 WebBridge 橋接。

- **⏳ 批次收編歷史與時光機回溯系統 (`batch_history_manager.py`, `main.py`)**：
  - **歷史基準不可變（Legacy Baseline Protection）**：現有 1400+ 個既有模組永久受只讀屏障保護，任何回溯操作絕不波及歷史基準。
  - **原子交易快照（Atomic Snapshot Transactions）**：每次批次收編任務均記錄獨立 batch_id、日期時間、檔案清單與過濾設定 (`.batch_manifest/history.json`)。
  - **非破壞性雙向回溯**：回溯時安全保存至 `rollback_backup`，可隨時一鍵復原。
  - **GUI 交互直達**：主界面新增【收編時光機】與【試運行日誌】一鍵直達按鈕與彈出對話框。

- **🎶 18 大主流風格本體庫與音訊遙測防中毒升級 (`director_choreographer.py`, `test_genre_enhancement.py`)**：
  - 擴充至 18 大風格本體註冊表（完整包含 Prompt Ensembles、Ballistic 阻尼、OKLCH 色彩與曲式文法先驗）。
  - 導演手動指定風格覆寫與快取隔離機制，徹底防禦 Cache Key Poisoning。
  - 強化 DnB（174 BPM）抗折半識別能力，嚴格保證 Ambient 樂曲分鏡絕不出現 Drop 標籤。

- **🎼 神經 / 物理 4-Stem 音訊分離回退管線 (`audio_stem_separator.py`)**：
  - 支援 ONNXRuntime 載入輕量化神經分軌模型（Drums, Bass, Vocals, Other）。
  - 內建零外部神經模型依賴之物理聲學 HPSS + Filterbank 高保真回退分離管線。

- **👁️ 語意多模態攝取與 VLM 守門員架構 (`semantic_ingestion/`)**：
  - 建立模組多模態特徵提取與語意排程管線，整合時空切片 (`spatiotemporal_tiler.py`)、視覺守門員 (`visual_gatekeeper.py`) 與 VLM 客戶端。

- **🌐 沙盒防護與模組庫元資料同步 (`headless_qc_repair.py`, `custom_visuals/`)**：
  - `headless_qc_repair.py` 增強 `p5.prototype.setup` 與 `p5.prototype.draw` try-catch 攔截樁。
  - 全面更新 1400+ 視覺模組元資料、標籤分類與使用歷程檔案。

---

## 🚀 [v1.4.2] - 2026-09-19
### 🛡️ blendMode/randomColor 沙盒安全防護、4K 環形快取記憶體精簡與導演分鏡獨立性強化

- **🛡️ WebGL / p5.js 沙盒崩潰免疫與相容性強化 (`main.py`)**：
  - **`blendMode` 全生命週期安全護欄**：全面攔截 `p5.prototype.blendMode`、`p5.Graphics.prototype.blendMode`、`p5.Renderer2D`、`p5.RendererGL`、`window.blendMode` 以及 `p5.prototype.filter`，防禦 `_renderer` 未建立或已銷毀時拋出 `Cannot read properties of undefined (reading 'blendMode')`，自動降級至底層 2D Canvas `globalCompositeOperation`。
  - **`randomColor` 全功能 Polyfill 與 CommonJS 模組導出橋接**：針對使用 `randomColor()` / `randomcolor` 的視覺腳本，實作支援 `hue`、`luminosity`、`format` (hex, rgb, hsl) 與 `count` 之原生 Polyfill，並在 Node/CommonJS `module.exports` 與全域作用域間雙向自動綁定。
  - **`c2` 幾何演算庫與 `blendMode*` 全域變數防護**：注入 `c2`（`Point`、`Vector`、`Polygon` 等）防護樁，並修正 `blendModebackground`、`blendModefill` 等變數未宣告錯誤。
  - **OPC 控制面板代理簡化**：優化 `window.OPC` 代理封裝，精簡屬性定義邏輯。

- **⚡ 4K 渲染管線記憶體深度精簡與畫質防撕裂保護 (`main.py`)**：
  - **環形影格快取池 (Ring Buffer Cache) 體積精簡**：將 `ModuleFrameCacheManager` 的每模組快取幀數 `max_frames_per_module` 由 15 幀縮減為 2 幀，最大模組快取數由 30 調降為 20，大幅降低 4K 渲染期間的 RAM/VRAM 峰值記憶體開銷（減少 80% 以上快取記憶體佔用）。
  - **同模組平滑保底 (Same-Module Fallback Blend)**：在黑畫面/白畫面/純色死鎖保底機制中，引入 `last_valid_module_name` 鎖定校驗，確保跨模組過渡時絕不將前一模組的歷史殘影混合至新模組，杜絕視覺撕裂與鬼影疊加。
  - **黑畫面告警噪音過濾**：調整 `consecutive_black_frames` 警告門檻至連續 2 幀以上，消除分鏡快速切換時單幀刻意全黑的日誌誤報。

- **🎬 AI 導演分鏡鎖定與樂段獨立性保障 (`main.py`)**：
  - **徹底杜絕高能量模組覆蓋死鎖**：重構 `get_energy_adapted_visual`，移除過去音訊能量大於 0.6 時自動將 Verse/Bridge 強制置換為 Drop/Chorus 模組的過激啟發式邏輯。嚴格尊重導演分鏡指派與樂段風格獨立性，徹底根除高節奏 Techno 曲目因持續高能量而導致全曲被單一模組霸佔的問題。

- **🎨 超現實主義拼貼模組收編與模組使用歷史同步 (`custom_visuals/`)**：
  - **收編全新超現實主義視覺模組**：收編 `surreal_demo_1789737433` (含肢體切分去背素材與預覽縮圖)，正式納入視覺模組庫。
  - **同步視覺模組使用計數與影片歷程**：更新 `module_usage_history.json` 與所有相關視覺模組 JSON 之 `used_count` 與 `used_in_videos` 歷程紀錄。

---

## 🚀 [v1.4.1] - 2026-09-17
### 🛡️ 全專案多角色審核修復、4K 渲染管線記憶體優化與 YouTube 金鑰池自動輪換

- **🔴 YouTube 金鑰池自動輪換續傳 (`youtube_uploader_tab.py`)**：
  - 徹底修復配額耗盡時直接中斷的缺陷，全面啟用 `cred_manager.rotate_to_next()` 自動輪替金鑰池內的 7 組 Google OAuth Client Secret 專案。
  - 當遇到 Quota Exceeded 錯誤時，自動無感切換專案憑證並重新連線，不中斷批次佇列上傳流程。
  - 新增多平台發布引擎 (`social_uploader_engine.py`)，支援 TikTok 與 Instagram Reels 批量排程與狀態矩陣管理。

- **🔴 像素視覺生成器草稿重複類別清理 (`pixel_generator_tab.py`)**：
  - 清理重複定義且被後續覆蓋的舊版 `PixelModuleGeneratorTab` 類別草稿，消除類別遮蔽與冗餘死碼。

- **🟡 4K 渲染管線記憶體與色彩管線優化 (`main.py`)**：
  - **色彩格式原生對接**：FFmpeg rawvideo 輸入像素格式由 `rgba` 升級為 `rgb24`，移除 Python 端每幀 33.1MB 的 RGBA 冗餘記憶體拷貝（在 4K 60FPS 下每秒釋放約 2GB/s 記憶體頻寬）。
  - **真·記憶體釋放**：將渲染迴圈末尾無效的 `del locals()[_v]` 偽釋放升級為顯式 `None` 賦值，解除 CPython 局部槽位物件參照，防止長時間批量渲染記憶體洩漏。
  - **快照路徑標準化**：修正硬編碼歷史 Antigravity Session 快照路徑，標準化重定向至專案內 `render_output/snapshots`。
  - **動態 Import 提取**：將迴圈內部的 `RealtimeRenderQCAuditor` 與 `ImageEnhance` 提取至渲染前預先初始化，消除每幀重複 import 尋址開銷。

- **🟡 音訊分析器工作目錄修正 (`audio_analyzer.py`)**：
  - 修正路徑計算中的雙重 `dirname`，確保 `temp_audio` 精確建立於專案根目錄內，避免專案外部目錄污染。

- **🟡 Python 3.12+ 正則 SyntaxWarning 徹底清零 (`code_injector.py` & `main.py`)**：
  - 轉義 JS 模板中的 `\s`、`\w` 與 `\.`，全專案 `python3 -m py_compile *.py` 達成 0 語法警告、0 報錯。

- **🟡 Shorts 豎屏匯出穩定性強化 (`shorts_exporter_tab.py`)**：
  - 在 FFmpeg 子行程加入 `timeout=300` 超時保護與 `stderr=subprocess.PIPE` 管道，杜絕硬體編碼器卡死掛起，並精確捕獲匯出失敗原因。

- **🟢 死碼清理與巨型歷史日誌瘦身**：
  - 刪除完全未被引用的重複檔案 `procedural_palette_oklch.py`。
  - 截斷 94MB 巨型 `op_import_errors.txt` 至 8.5KB，大幅釋放儲存空間。

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

