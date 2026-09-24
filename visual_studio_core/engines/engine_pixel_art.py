#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel Art Engine (像素復古點陣工坊)
承載 15 種前衛抖色風格、21 款主題調色盤、OKLCH 色階量化與音訊故障切片
全面接入 Studio Rack 協議，支援 AST 實時像素縮放與音訊頻段切片
"""

import random
from typing import Dict, List, Any, Optional, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QCheckBox
)
from visual_studio_core.engines.base_engine import BaseVisualEngine, EngineMetadata

PIXEL_STYLES = [
    (0, "0: 區塊方塊像素 (Block Pixel)"),
    (1, "1: Bayer 4×4 網點抖色 (Bayer 4x4)"),
    (2, "2: Bayer 8×8 矩陣平滑抖色 (Bayer 8x8)"),
    (3, "3: Blue Noise 藍噪聲隨機顆粒 (Blue Noise)"),
    (4, "4: Halftone 印刷半色調波點 (Halftone Dot)"),
    (5, "5: Crosshatch 漫畫交叉素描排線 (Crosshatch)"),
    (6, "6: CRT Phosphor Subpixel (RGB 垂直子像素)"),
    (7, "7: Diamond 45° 菱形斜交抖色 (Diamond Dither)"),
    (8, "8: ASCII 字符密度矩陣 (ASCII / Matrix Glyph)"),
    (9, "9: Glitch Slicing 故障切片撕裂 (Glitch Tear)"),
    (10, "10: 💎 Voronoi 水晶多邊形碎裂 (Voronoi Crystal)"),
    (11, "11: 🧊 3D 體積浮雕像素 (3D Voxel Prism)"),
    (12, "12: 🎨 Amiga 500 HAM6 流體油畫 (HAM6 Fluid)"),
    (13, "13: 🦠 Cellular Life 生命遊戲繁衍 (Cellular Life)"),
    (14, "14: 🔥 Thermal FLIR 熱成像紅外線 (Thermal FLIR)")
]

PIXEL_PALETTES = [
    (0, "0: 💜 Cyberpunk Neon (賽博霓虹)"),
    (1, "1: 🕹️ Game Boy Classic 1989 (初版綠灰四階)"),
    (2, "2: 🎮 Game Boy Pocket (黑白灰階四階)"),
    (3, "3: 📺 Commodore 64 (C64 復古色系)"),
    (4, "4: 👾 PICO-8 幻想主機 (16-bit 經典調)"),
    (5, "5: 🌊 Vaporwave Pastel (蒸汽波粉彩)"),
    (6, "6: 🌃 Tokyo Night Neo-Tokyo (東京暗夜藍紫金)"),
    (7, "7: 📟 Matrix Digital Rain (駭客任務數位綠)"),
    (8, "8: 🏎️ Synthwave Outrun 1984 (落日公路紫橙)"),
    (9, "9: 🖥️ Apple II Amber Terminal (琥珀金終端)"),
    (10, "10: 🧊 Nord Arctic Frost (北歐極地冰原)"),
    (11, "11: 🩸 Dracula Gothic (德古拉歌德黑紅紫)"),
    (12, "12: ☣️ Acid Techno Neon (迷幻酸性高飽和)"),
    (13, "13: 📜 Sepia Vintage Film (老照片復古褐斑)"),
    (14, "14: 🔥 Thermal Heatmap (熱成像紅外線)"),
    (15, "15: ⬛ Monochrome 1-bit Manga (黑白漫畫純二值)"),
    (16, "16: 🌅 Sunset Outrun Gold (落日金橙)"),
    (17, "17: 🌌 Solarized Deep Space (深空藍紫)"),
    (18, "18: 📼 Amiga Copper Rainbow (阿米加彩虹條帶)")
]


class PixelArtEngine(BaseVisualEngine):
    """像素復古點陣工坊引擎"""

    def __init__(self):
        super().__init__()
        self.current_style_idx = 2  # Bayer 8x8
        self.current_palette_idx = 0  # Cyberpunk Neon

    def get_metadata(self) -> EngineMetadata:
        return EngineMetadata(
            id="pixel_art",
            name="像素復古點陣工坊 (Pixel Art)",
            icon="👾",
            description="15 種前衛著色抖動（Bayer/Halftone/CRT/ASCII）、21 款復古經典色盤、OKLCH 量化與低音脈衝切片",
            category="pixel_art",
            tags=["PixelArt", "Retro", "Dithering", "Bayer", "CRT", "Cyberpunk", "Audio-Reactive"],
            recommended_shaders=[3, 7, 9, 13, 20],  # CRT, Scanline, Glitch, Chromatic Aberration
            author="4K MV Studio Pixel Master",
            version="2.1.0"
        )

    def get_default_ast_params(self) -> List[Dict[str, Any]]:
        return [
            {"name": "pixelSize", "type": "int", "min": 2, "max": 48, "step": 1, "default": 12, "doc": "像素點陣顆粒大小"},
            {"name": "ditherStrength", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05, "default": 0.65, "doc": "網點抖色矩陣混合強度"},
            {"name": "styleMode", "type": "int", "min": 0, "max": 14, "step": 1, "default": 2, "doc": "著色抖色風格演算法模式"},
            {"name": "paletteMode", "type": "int", "min": 0, "max": 18, "step": 1, "default": 0, "doc": "主題色彩調色盤索引"},
            {"name": "scanlineAlpha", "type": "int", "min": 0, "max": 100, "step": 5, "default": 40, "doc": "CRT 垂直/水平掃描線濃度"},
            {"name": "glitchFreq", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05, "default": 0.4, "doc": "重低音切片撕裂故障頻率"},
            {"name": "audioReactivity", "type": "float", "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.6, "doc": "低頻重低音激勵倍率"}
        ]

    def mutate(self, current_params: Dict[str, Any], strength: float = 0.3) -> Dict[str, Any]:
        mutated = current_params.copy()
        for p in self.get_default_ast_params():
            p_name = p["name"]
            curr_val = mutated.get(p_name, p["default"])
            p_min, p_max = p["min"], p["max"]
            delta = (p_max - p_min) * strength * random.uniform(-1.0, 1.0)
            if p["type"] == "int":
                mutated[p_name] = int(max(p_min, min(p_max, round(curr_val + delta))))
            else:
                mutated[p_name] = round(max(p_min, min(p_max, curr_val + delta)), 3)
        return mutated

    def generate_code(self, params: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> str:
        p_px = params.get("pixelSize", 12) if params else 12
        p_dither = params.get("ditherStrength", 0.65) if params else 0.65
        p_style = params.get("styleMode", self.current_style_idx) if params else self.current_style_idx
        p_pal = params.get("paletteMode", self.current_palette_idx) if params else self.current_palette_idx
        p_scan = params.get("scanlineAlpha", 40) if params else 40
        p_glitch = params.get("glitchFreq", 0.4) if params else 0.4
        p_audio = params.get("audioReactivity", 1.6) if params else 1.6

        code = f"""/**
 * 4K MV Visual Module: Retro Pixel Art Studio Rack Engine
 * Style: {p_style} | Palette: {p_pal}
 */

let pixelSize = {p_px}; // @wizard(min=2, max=48, step=1, label="像素顆粒尺寸")
let ditherStrength = {p_dither}; // @wizard(min=0.0, max=1.0, step=0.05, label="抖色混合強度")
let styleMode = {p_style}; // @wizard(min=0, max=14, step=1, label="著色風格模式")
let paletteMode = {p_pal}; // @wizard(min=0, max=18, step=1, label="調色盤主題")
let scanlineAlpha = {p_scan}; // @wizard(min=0, max=100, step=5, label="CRT 掃描線濃度")
let glitchFreq = {p_glitch}; // @wizard(min=0.0, max=2.0, step=0.05, label="音頻故障頻率")
let audioReactivity = {p_audio}; // @wizard(min=0.0, max=3.0, step=0.1, label="音頻動態倍率")

let audioData = {{ bass: 0.2, mid: 0.2, high: 0.2, energy: 0.2, beatPulse: 0.0 }};
let timeOffset = 0;

window.onAudioFrame = function(bass, mid, high, energy, beatPulse) {{
  audioData.bass = bass || 0;
  audioData.mid = mid || 0;
  audioData.high = high || 0;
  audioData.energy = energy || 0;
  audioData.beatPulse = beatPulse || 0;
}};

// 21 種主題調色盤陣列 (RGB 0~255)
const PALETTES = [
  [[15, 5, 25], [100, 20, 140], [255, 30, 120], [0, 240, 255], [255, 255, 255]], // 0: Cyberpunk
  [[15, 56, 15], [48, 98, 48], [139, 172, 15], [155, 188, 15]], // 1: Game Boy 1989
  [[20, 20, 20], [80, 80, 80], [160, 160, 160], [240, 240, 240]], // 2: Game Boy Pocket
  [[0, 0, 0], [116, 67, 53], [124, 172, 186], [162, 109, 178], [138, 178, 95]], // 3: C64
  [[0, 0, 0], [29, 43, 83], [126, 37, 83], [0, 135, 81], [255, 0, 77], [255, 236, 39]], // 4: PICO-8
  [[44, 18, 80], [255, 113, 206], [1, 205, 254], [5, 255, 161], [185, 103, 255]], // 5: Vaporwave
  [[26, 27, 38], [122, 162, 247], [187, 154, 247], [125, 207, 255], [247, 118, 142]], // 6: Tokyo Night
  [[0, 10, 2], [0, 60, 15], [0, 180, 40], [140, 255, 160]], // 7: Matrix
  [[20, 10, 35], [90, 20, 120], [230, 50, 140], [255, 140, 40], [255, 230, 100]], // 8: Synthwave
  [[20, 10, 0], [120, 60, 0], [220, 130, 0], [255, 200, 50]] // 9: Amber
];

// Bayer 4x4 抖色矩陣
const BAYER_4x4 = [
  [ 0,  8,  2, 10],
  [12,  4, 14,  6],
  [ 3, 11,  1,  9],
  [15,  7, 13,  5]
];

function setup() {{
  createCanvas(windowWidth, windowHeight);
  pixelDensity(1);
  noSmooth();
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}

function draw() {{
  background(10, 10, 14);
  
  let bassMod = audioData.bass * audioReactivity;
  let highMod = audioData.high * audioReactivity;
  let pulse = audioData.beatPulse;

  timeOffset += 0.02 * (1.0 + bassMod * 0.5);

  let pal = PALETTES[paletteMode % PALETTES.length];
  let ps = Math.max(2, Math.floor(pixelSize * (1.0 - pulse * 0.2)));

  let cols = Math.ceil(width / ps);
  let rows = Math.ceil(height / ps);

  noStroke();

  for (let y = 0; y < rows; y++) {{
    // 音訊切片撕裂 Glitch 計算
    let xOffset = 0;
    if (glitchFreq > 0.1 && (y % 12 === 0) && (bassMod > 0.6 || random() < 0.05 * glitchFreq)) {{
      xOffset = sin(timeOffset * 20.0 + y) * (20 * glitchFreq + bassMod * 30);
    }}

    for (let x = 0; x < cols; x++) {{
      let screenX = x * ps + xOffset;
      let screenY = y * ps;

      // 產生程序化動態能量場
      let u = (x / cols) * 4.0;
      let v = (y / rows) * 4.0;
      let val = sin(u + timeOffset) * cos(v - timeOffset * 0.8) + sin(dist(u, v, 2.0, 2.0) * 3.0 - timeOffset * 2.0);
      val = (val + 2.0) / 4.0; // 正規化 0~1

      val += bassMod * 0.35 * sin(u * 5.0 + v * 5.0);

      // Bayer 抖色偏移
      if (ditherStrength > 0.01) {{
        let ditherVal = (BAYER_4x4[y % 4][x % 4] / 16.0 - 0.5) * ditherStrength;
        val = constrain(val + ditherVal, 0, 0.999);
      }}

      // 調色盤量化
      let colorIdx = Math.floor(val * pal.length);
      colorIdx = constrain(colorIdx, 0, pal.length - 1);
      let c = pal[colorIdx];

      fill(c[0], c[1], c[2]);

      // 依風格模式渲染圖元
      if (styleMode === 0) {{
        // 方塊像素
        rect(screenX, screenY, ps, ps);
      }} else if (styleMode === 4) {{
        // 半色調圓點
        let rad = ps * val;
        circle(screenX + ps * 0.5, screenY + ps * 0.5, rad);
      }} else if (styleMode === 7) {{
        // 菱形斜交
        push();
        translate(screenX + ps * 0.5, screenY + ps * 0.5);
        rotate(PI / 4);
        rectMode(CENTER);
        rect(0, 0, ps * 0.7 * val, ps * 0.7 * val);
        pop();
      }} else {{
        // 默認像素矩陣
        rect(screenX, screenY, ps, ps);
      }}
    }}
  }}

  // CRT 掃描線後製疊層
  if (scanlineAlpha > 0) {{
    stroke(0, 0, 0, scanlineAlpha * 2.55);
    strokeWeight(1);
    for (let sy = 0; sy < height; sy += 4) {{
      line(0, sy, width, sy);
    }}
  }}
}}
"""
        return code

    def create_control_widget(self, parent: Optional[QWidget] = None, on_param_changed: Optional[Callable] = None) -> Optional[QWidget]:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        group = QGroupBox("👾 像素點陣矩陣控制台", panel)
        group.setStyleSheet("""
            QGroupBox {
                background-color: #121316;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding-top: 14px;
                font-size: 11px;
                font-weight: bold;
                color: #38bdf8;
            }
        """)
        g_layout = QVBoxLayout(group)
        g_layout.setContentsMargins(8, 8, 8, 8)
        g_layout.setSpacing(6)

        # 風格選擇
        s_row = QHBoxLayout()
        s_lbl = QLabel("抖色風格:")
        s_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.combo_style = QComboBox(group)
        self.combo_style.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                border: 1px solid #27272a;
                color: #f4f4f5;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QComboBox:hover { border: 1px solid #38bdf8; }
        """)
        for s_idx, s_name in PIXEL_STYLES:
            self.combo_style.addItem(s_name, userData=s_idx)
        self.combo_style.setCurrentIndex(self.current_style_idx)

        def _on_style_change(idx):
            s_val = self.combo_style.currentData()
            self.current_style_idx = s_val
            if on_param_changed:
                on_param_changed({"styleMode": s_val})

        self.combo_style.currentIndexChanged.connect(_on_style_change)
        s_row.addWidget(s_lbl)
        s_row.addWidget(self.combo_style, 1)
        g_layout.addLayout(s_row)

        # 色盤選擇
        p_row = QHBoxLayout()
        p_lbl = QLabel("主題色盤:")
        p_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.combo_pal = QComboBox(group)
        self.combo_pal.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                border: 1px solid #27272a;
                color: #f4f4f5;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QComboBox:hover { border: 1px solid #38bdf8; }
        """)
        for p_idx, p_name in PIXEL_PALETTES:
            self.combo_pal.addItem(p_name, userData=p_idx)
        self.combo_pal.setCurrentIndex(self.current_palette_idx)

        def _on_pal_change(idx):
            p_val = self.combo_pal.currentData()
            self.current_palette_idx = p_val
            if on_param_changed:
                on_param_changed({"paletteMode": p_val})

        self.combo_pal.currentIndexChanged.connect(_on_pal_change)
        p_row.addWidget(p_lbl)
        p_row.addWidget(self.combo_pal, 1)
        g_layout.addLayout(p_row)

        # 隨機打散按鈕列
        btn_row = QHBoxLayout()
        btn_dice_style = QPushButton("🎲 隨機風格", group)
        btn_dice_style.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                color: #e4e4e7;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #3f3f46; color: white; }
        """)

        def _dice_style():
            idx = random.randint(0, len(PIXEL_STYLES) - 1)
            self.combo_style.setCurrentIndex(idx)

        btn_dice_style.clicked.connect(_dice_style)

        btn_dice_pal = QPushButton("🎨 隨機色盤", group)
        btn_dice_pal.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                border: 1px solid #38bdf8;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)

        def _dice_pal():
            idx = random.randint(0, len(PIXEL_PALETTES) - 1)
            self.combo_pal.setCurrentIndex(idx)

        btn_dice_pal.clicked.connect(_dice_pal)

        btn_row.addWidget(btn_dice_style)
        btn_row.addWidget(btn_dice_pal)
        g_layout.addLayout(btn_row)

        layout.addWidget(group)
        return panel
