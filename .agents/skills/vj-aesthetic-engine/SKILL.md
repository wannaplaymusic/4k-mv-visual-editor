---
name: vj-aesthetic-engine
description: 專用 4K MV 視覺審美與 AI 生成評估規範模組。包含 HSL 調和配色演算法、音視動態呼吸感控制、極致畫面質感（Bloom, Vignette, Chromatic Aberration）與經典 VJ 風格庫。
---

# VJ Aesthetic Engine (4K MV 視覺審美引擎技能)

本 Skill 專門用於提升 4K MV 視覺編輯器中所有程序化畫面（p5.js / WebGL / OpenCV / Shaders）的審美質感與設計水準，確保 AI 生成或編修視覺模組時跳過「預設平庸感」，輸出具備商業級畫質與電影感的視覺效果。

---

## 1. 審美調色盤演算法（Harmonic HSL Palette Rules）

### ❌ 審美禁區（Anti-Patterns）
* **禁止原色/粗糙高飽和色**：嚴禁直接使用 `#FF0000` (純紅)、`#00FF00` (純綠)、`#0000FF` (純藍) 或 `#FFFF00` (純黃)。
* **禁止隨機無秩序閃爍**：禁止每影格使用 `random(255)` 生成顏色。

### ⭕ 最佳實踐：Chroma 音感與 HSL 諧振映射
根據 Chroma STFT 12 音階與音樂大/小調情緒，計算具備莫蘭迪 (Morandi) 或霓虹 (Neon) 調和感的配色：

```javascript
// p5.js / WebGL 審美調色盤生成函數
function getHarmonicColor(pitchClass, energy, isMinor = false) {
  // pitchClass: 0~11 (C, C#, D... B)
  // Base Hue 依 12 音階均分，帶入色相偏移
  let baseHue = (pitchClass * 30 + 15) % 360;
  
  // 大調偏暖色調/亮飽和，小調偏莫蘭迪低飽和/莫藍暗色
  let saturation = isMinor ? map(energy, 0, 1, 35, 60) : map(energy, 0, 1, 65, 90);
  let lightness = isMinor ? map(energy, 0, 1, 25, 55) : map(energy, 0, 1, 45, 75);
  
  return color(`hsl(${Math.round(baseHue)}, ${Math.round(saturation)}%, ${Math.round(lightness)}%)`);
}
```

---

## 2. 畫面動態與「呼吸感」規範（Dynamic Breathing & Motion Curves）

高質感 MV 的動態必須具有物理彈性與音訊能量共振，而非僵硬的線性運動。

1. **緩動曲線（Easing Curves）**：
   * 所有畫面變換、縮放與旋轉必須使用 Easing（如 Smoothstep、Ease-Out-Cubic），禁止 `x += speed` 的死板等速移動。
2. **音視雙向呼吸感 (Audio-Visual Breathing)**：
   * **Bass (重低音)**：驅動畫面 Central Geometry（核心幾何體）的 Scale 彈性縮放 (1.0 ~ 1.25) 與鏡頭微震。
   * **High (高音/切音)**：驅動粒子 Sparkles、線條發光強度與閃爍頻率。
   * **Mid (中音/人聲)**：驅動流體旋渦 (Vortex) 與波浪場形變。

```javascript
// 彈性緩動 (Elastic Easing) 計算範例
let targetScale = 1.0 + audioParams.bass * 0.3;
currentScale += (targetScale - currentScale) * 0.15; // 平滑平流緩動
```

---

## 3. 電影級後處理質感（Cinematic Post-Processing Suite）

任何 2D/3D 程序化繪圖在輸出前，必須套用後處理質感層，打造 4K 電影級視覺深度：

| 後處理效果 | 作用與參數規範 | 審美效益 |
| :--- | :--- | :--- |
| **Bloom (柔光發光)** | 門檻值 Threshold: `0.65`, 模糊半徑 Blur: `12px` | 去除矢量數位感，創造霓虹光霧感 |
| **Vignette (邊角暗角)** | 強度 Intensity: `0.35 ~ 0.5` | 將視覺焦點聚焦至畫面中心，增強沉浸感 |
| **Chromatic Aberration (色散)** | 偏移 Offset: `2px ~ 5px` (隨 Beat 能量激增) | 模擬老舊膠片與高級鏡頭光學色偏 |
| **Feedback Reaction-Diffusion** | 衰減 Decay: `0.12`, 放大率 Scale: `1.01` | 創造殘影與夢幻軌跡 |

---

## 4. 四大預設審美主題風格（Curated Style Presets）

在生成與編修畫面時，可直接指定以下四大經典 VJ 視覺主題：

1. **Neo-Tokyo Cyberpunk（新東京賽博朋克）**
   * *主色系*：電光藍 (`#00F0FF`) + 毒性粉紅 (`#FF0055`) + 暗灰背景 (`#0B0E14`)
   * *視覺特徵*：高對比網格、脈衝線條、強烈色光斑。
2. **Analog Synthwave 80s（復古黑膠波浪）**
   * *主色系*：日落紫 (`#7928CA`) + 暖陽橙 (`#FF0080`) + 鉻銀 (`#E2E8F0`)
   * *視覺特徵*：透視地平線、太陽暈光、掃描線 (Scanlines)。
3. **Cyber Organic Fluid（數位有機流體）**
   * *主色系*：珍珠翡翠 (`#00DF89`) + 深海青 (`#0369A1`) + 莫蘭迪灰 (`#1E293B`)
   * *視覺特徵*：渦流場平移、反應擴散細胞、平滑慢速演化。
4. **Minimalist Kinetic Monochrome（極簡動態黑白金）**
   * *主色系*：香檳金 (`#F59E0B`) + 純黑 (`#09090B`) + 霧灰 (`#71717A`)
   * *視覺特徵*：極簡幾何、銳利字體與線條、極大化留白。

---

## 5. 自適應曲式導演系統對應（Director System Section Modulation）

視覺審美必須與音樂曲式結構同步。導演系統會在不同樂段自動調變特效切換與審美強迫度：

| 曲式段落 (Section) | 導演視覺調度策略 | 特效與色調強度 | 建議過渡演算法 |
| :--- | :--- | :--- | :--- |
| **Intro / Outro** | 漸進式登場/淡出、水墨暈染、柔和暗角 | 光暈極高、流體動態慢速 | `luma_wipe` |
| **Verse (主歌)** | 保持穩定幾何敘事感、低對比背景、微幅 HSL 色相漂移 | 莫蘭迪低飽和色系、中等緩動 | `displacement` |
| **Build-up (副歌前爬升)** | 視覺頻率加快、色散抖動激增、閃爍發光密度上升 | 銳利高對比、色散頻率 `4~8px` | `glitch` |
| **Chorus / Drop (副歌爆發)** | 全色域高對比霓虹開滿、爆發性粒子與極致 Bloom | 強烈對比、高飽和霓虹、動態鏡頭縮放 | `zoom_blur` / `glitch` |
| **Bridge (橋段/轉折)** | 空間感橫移、極簡留白、單色調金/灰切換 | 香檳金/深海青單色系、平滑推移 | `slide_push` |

---

## 6. Agent 視覺修復與審美驗收 Checklist

當 Agent 進行程式碼審查或自動修復時，必須檢視：
- [ ] 畫面是否具備至少一層音訊能量 (Bass/Mid/High) 耦合？
- [ ] 是否避免了純原色與隨機色？
- [ ] 幾何運動是否有緩動曲線 (Easing) 而非硬連線？
- [ ] 畫面邊緣是否有防黑屏/防切邊與適當的畫面留白？
- [ ] 是否已載入後處理與疊加層？
- [ ] 是否符合當前曲式段落 (Intro/Verse/Chorus/Bridge) 的導演調度強弱？

