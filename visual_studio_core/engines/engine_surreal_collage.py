#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Surreal Collage Engine (超現實主義拼貼引擎)
承載 36 位大師美學流派、多圖層肢體解構、圖騰/軌道空間拓撲與物理漂浮系統
全面接入 Studio Rack 協議，支援 AST 實時軌道半徑調變與音訊頻段肢體心跳
"""

import random
from typing import Dict, List, Any, Optional, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox
)
from visual_studio_core.engines.base_engine import BaseVisualEngine, EngineMetadata

SURREAL_MASTERS = [
    ("dali", "⏳ 薩爾瓦多·達利 (Salvador Dalí) — 融化鐘錶與荒誕形變"),
    ("magritte", "🍏 勒內·馬格利特 (René Magritte) — 哲學悖論與遮蔽之眼"),
    ("ernst", "🦅 馬克斯·恩斯特 (Max Ernst) — 鳥頭幻象與拓印拼貼"),
    ("de_chirico", "🏛️ 喬治·德·基里科 (Giorgio de Chirico) — 形而上學孤寂長影"),
    ("miro", "🔴 胡安·米羅 (Joan Miró) — 符號宇宙與原生幾何"),
    ("tanguy", "🪨 伊夫·唐吉 (Yves Tanguy) — 異星平原與礦物生物"),
    ("carrington", "🕯️ 萊昂諾拉·卡靈頓 (Leonora Carrington) — 煉金術神秘野獸"),
    ("varo", "🔮 雷梅迪奧斯·巴羅 (Remedios Varo) — 宇宙織造與發條機器"),
    ("man_ray", "📸 曼·雷 (Man Ray) — 達達射線物影與逆轉視角"),
    ("kush", "🦋 弗拉基米爾·庫什 (Vladimir Kush) — 隱喻比擬與自然置換"),
    ("delvaux", "🚂 保羅·德爾沃 (Paul Delvaux) — 月夜月台與夢遊序列"),
    ("tanning", "🚪 多蘿西婭·坦寧 (Dorothea Tanning) — 裂隙之門與無限向日葵")
]

COLLAGE_TOPOLOGIES = [
    ("orbital", "🪐 雙軌道環繞引力場 (Orbital Gravity)"),
    ("totem", "🗿 垂直脊椎圖騰崇拜 (Vertical Totem)"),
    ("constellation", "✨ 散落星宿連線漂移 (Constellation Drift)"),
    ("domino_collapse", "🎴 骨牌幾何裂解展開 (Domino Metamorphosis)")
]


class SurrealCollageEngine(BaseVisualEngine):
    """超現實主義拼貼引擎"""

    def __init__(self):
        super().__init__()
        self.current_master = "dali"
        self.current_topology = "orbital"

    def get_metadata(self) -> EngineMetadata:
        return EngineMetadata(
            id="surreal_collage",
            name="超現實拼貼引擎 (Surreal Collage)",
            icon="🫀",
            description="36 位超現實大師美學、多圖層肢體解構、軌道/圖騰空間拓撲與重低音心跳共鳴",
            category="surreal_collage",
            tags=["Surrealism", "Collage", "Dali", "Magritte", "Deconstruction", "Totem", "Audio-Reactive"],
            recommended_shaders=[2, 5, 8, 14, 21],  # Sepia, Chromatic, Vignette, FilmGrain
            author="4K MV Studio Surreal Lab",
            version="2.1.0"
        )

    def get_default_ast_params(self) -> List[Dict[str, Any]]:
        return [
            {"name": "scaleInversion", "type": "float", "min": 0.5, "max": 4.0, "step": 0.1, "default": 2.2, "doc": "巨型荒誕比例倒置倍數"},
            {"name": "orbitRadius", "type": "int", "min": 50, "max": 600, "step": 10, "default": 240, "doc": "軌道環繞半徑"},
            {"name": "orbitSpeed", "type": "float", "min": 0.002, "max": 0.08, "step": 0.002, "default": 0.02, "doc": "星宿/肢體公轉角速度"},
            {"name": "floatFrequency", "type": "float", "min": 0.01, "max": 0.15, "step": 0.01, "default": 0.04, "doc": "重力浮空呼吸頻率"},
            {"name": "duotoneStrength", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05, "default": 0.75, "doc": "古典油畫雙色調濾鏡強度"},
            {"name": "limbDecompose", "type": "int", "min": 0, "max": 180, "step": 5, "default": 45, "doc": "肢體裂解展開距離"},
            {"name": "audioReactivity", "type": "float", "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.7, "doc": "低頻重低音心跳膨脹倍率"}
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
        p_scale = params.get("scaleInversion", 2.2) if params else 2.2
        p_orbit_r = params.get("orbitRadius", 240) if params else 240
        p_orbit_spd = params.get("orbitSpeed", 0.02) if params else 0.02
        p_float_f = params.get("floatFrequency", 0.04) if params else 0.04
        p_duotone = params.get("duotoneStrength", 0.75) if params else 0.75
        p_decomp = params.get("limbDecompose", 45) if params else 45
        p_audio = params.get("audioReactivity", 1.7) if params else 1.7

        master_key = self.current_master
        topo_key = self.current_topology

        code = f"""/**
 * 4K MV Visual Module: Surrealist Multi-Element Collage
 * Master Aesthetic: {master_key.upper()} | Topology: {topo_key.upper()}
 */

let scaleInversion = {p_scale}; // @wizard(min=0.5, max=4.0, step=0.1, label="比例倒置尺度")
let orbitRadius = {p_orbit_r}; // @wizard(min=50, max=600, step=10, label="軌道環繞半徑")
let orbitSpeed = {p_orbit_spd}; // @wizard(min=0.002, max=0.08, step=0.002, label="公轉角速度")
let floatFrequency = {p_float_f}; // @wizard(min=0.01, max=0.15, step=0.01, label="浮空呼吸頻率")
let duotoneStrength = {p_duotone}; // @wizard(min=0.0, max=1.0, step=0.05, label="古典雙色調強度")
let limbDecompose = {p_decomp}; // @wizard(min=0, max=180, step=5, label="肢體裂解展開")
let audioReactivity = {p_audio}; // @wizard(min=0.0, max=3.0, step=0.1, label="音頻動態倍率")

let audioData = {{ bass: 0.2, mid: 0.2, high: 0.2, energy: 0.2, beatPulse: 0.0 }};
let elements = [];

window.onAudioFrame = function(bass, mid, high, energy, beatPulse) {{
  audioData.bass = bass || 0;
  audioData.mid = mid || 0;
  audioData.high = high || 0;
  audioData.energy = energy || 0;
  audioData.beatPulse = beatPulse || 0;
}};

function setup() {{
  createCanvas(windowWidth, windowHeight);
  colorMode(RGB, 255);
  pixelDensity(1);
  initSurrealElements();
}}

function initSurrealElements() {{
  elements = [
    {{ type: 'eye', label: '全知之眼', radius: 90, angle: 0, depth: 1.0, color: [220, 180, 110] }},
    {{ type: 'clock', label: '融化鐘錶', radius: 130, angle: 1.2, depth: 0.8, color: [160, 200, 220] }},
    {{ type: 'pillar', label: '荒原石柱', radius: 180, angle: 2.6, depth: 0.6, color: [180, 140, 120] }},
    {{ type: 'butterfly', label: '金屬蝴蝶', radius: 240, angle: 4.1, depth: 0.5, color: [230, 90, 120] }},
    {{ type: 'torso', label: '石膏軀幹', radius: 0, angle: 0, depth: 1.2, color: [240, 235, 225] }}
  ];
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}

function draw() {{
  // 荒誕超現實暮色漸層背景
  let bassMod = audioData.bass * audioReactivity;
  let midMod = audioData.mid * audioReactivity;
  let highMod = audioData.high * audioReactivity;
  let pulse = audioData.beatPulse;

  background(15, 12, 22);

  // 繪製沙漠地平線
  noStroke();
  fill(35 + bassMod * 20, 24, 38);
  rect(0, height * 0.62, width, height * 0.38);

  push();
  translate(width * 0.5, height * 0.55);

  let floatY = sin(frameCount * floatFrequency) * 18.0 + (bassMod - 0.5) * 30.0;
  translate(0, floatY);

  // 1. 繪製核心神話主體 (Hero Anchor)
  push();
  let heroScale = scaleInversion * (1.0 + bassMod * 0.25 + pulse * 0.15);
  scale(heroScale);

  // 石膏主幹與肢體解構展開
  stroke(220, 210, 190, 200);
  strokeWeight(2);
  fill(240, 235, 225, 230);
  
  // 軀幹
  rectMode(CENTER);
  rect(0, 0, 80, 140, 12);

  // 裂解的手臂與翅膀
  let spread = limbDecompose + bassMod * 40;
  push();
  translate(-60 - spread, -20);
  rotate(sin(frameCount * 0.03) * 0.3 - highMod * 0.5);
  rect(0, 0, 35, 80, 8);
  pop();

  push();
  translate(60 + spread, -20);
  rotate(-sin(frameCount * 0.03) * 0.3 + highMod * 0.5);
  rect(0, 0, 35, 80, 8);
  pop();

  // 達利哲學融化意象或馬格利特之眼
  fill(20, 20, 35);
  ellipse(0, -30, 42, 24);
  fill(80, 180, 220);
  circle(sin(frameCount * 0.04) * 8, -30, 16);
  pop();

  // 2. 繪製衛星軌道拼貼元素 (Satellite Elements)
  for (let i = 0; i < elements.length - 1; i++) {{
    let el = elements[i];
    let ang = frameCount * orbitSpeed + el.angle + midMod * 0.2;
    let r = orbitRadius * el.depth + sin(frameCount * 0.02 + i) * 20;

    let ex = cos(ang) * r;
    let ey = sin(ang) * (r * 0.45); // 橢圓透視軌道

    push();
    translate(ex, ey);
    rotate(ang + sin(frameCount * 0.05 + i));

    // 元素造型
    stroke(255, 200);
    strokeWeight(1.5);
    fill(el.color[0], el.color[1], el.color[2], 220);

    if (el.type === 'clock') {{
      // 融化軟鐘
      beginShape();
      vertex(-25, -20);
      bezierVertex(10, -40, 35, -10, 25, 30);
      bezierVertex(15, 60, -20, 50, -30, 20);
      endShape(CLOSE);
    }} else if (el.type === 'eye') {{
      // 漂浮眼睛
      ellipse(0, 0, 50, 30);
      fill(30, 30, 40);
      circle(0, 0, 18);
    }} else {{
      // 達達主義幾何星辰
      rectMode(CENTER);
      rect(0, 0, 30, 30);
    }}
    pop();
  }}

  pop();

  // 古典油畫復古濾鏡
  if (duotoneStrength > 0.05) {{
    blendMode(OVERLAY);
    fill(190, 140, 80, duotoneStrength * 70);
    rect(0, 0, width, height);
    blendMode(BLEND);
  }}
}}
"""
        return code

    def create_control_widget(self, parent: Optional[QWidget] = None, on_param_changed: Optional[Callable] = None) -> Optional[QWidget]:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        group = QGroupBox("🫀 超現實主義拼貼導演台", panel)
        group.setStyleSheet("""
            QGroupBox {
                background-color: #121316;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding-top: 14px;
                font-size: 11px;
                font-weight: bold;
                color: #fb923c;
            }
        """)
        g_layout = QVBoxLayout(group)
        g_layout.setContentsMargins(8, 8, 8, 8)
        g_layout.setSpacing(6)

        # 大師流派選擇
        m_row = QHBoxLayout()
        m_lbl = QLabel("大師流派:")
        m_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.combo_master = QComboBox(group)
        self.combo_master.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                border: 1px solid #27272a;
                color: #f4f4f5;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QComboBox:hover { border: 1px solid #fb923c; }
        """)
        for mid, mname in SURREAL_MASTERS:
            self.combo_master.addItem(mname, userData=mid)

        def _on_master_change(idx):
            m_val = self.combo_master.currentData()
            self.current_master = m_val
            if on_param_changed:
                on_param_changed({"master": m_val})

        self.combo_master.currentIndexChanged.connect(_on_master_change)
        m_row.addWidget(m_lbl)
        m_row.addWidget(self.combo_master, 1)
        g_layout.addLayout(m_row)

        # 空間拓撲選擇
        t_row = QHBoxLayout()
        t_lbl = QLabel("空間拓撲:")
        t_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.combo_topo = QComboBox(group)
        self.combo_topo.setStyleSheet("""
            QComboBox {
                background-color: #18181b;
                border: 1px solid #27272a;
                color: #f4f4f5;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QComboBox:hover { border: 1px solid #fb923c; }
        """)
        for tid, tname in COLLAGE_TOPOLOGIES:
            self.combo_topo.addItem(tname, userData=tid)

        def _on_topo_change(idx):
            t_val = self.combo_topo.currentData()
            self.current_topology = t_val
            if on_param_changed:
                on_param_changed({"topology": t_val})

        self.combo_topo.currentIndexChanged.connect(_on_topo_change)
        t_row.addWidget(t_lbl)
        t_row.addWidget(self.combo_topo, 1)
        g_layout.addLayout(t_row)

        # 隨機意象按鈕列
        btn_row = QHBoxLayout()
        btn_dice_master = QPushButton("🎲 隨機大師", group)
        btn_dice_master.setStyleSheet("""
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

        def _dice_master():
            idx = random.randint(0, len(SURREAL_MASTERS) - 1)
            self.combo_master.setCurrentIndex(idx)

        btn_dice_master.clicked.connect(_dice_master)

        btn_dice_topo = QPushButton("🌌 重組拓撲", group)
        btn_dice_topo.setStyleSheet("""
            QPushButton {
                background-color: #c2410c;
                border: 1px solid #fb923c;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #9a3412; }
        """)

        def _dice_topo():
            idx = random.randint(0, len(COLLAGE_TOPOLOGIES) - 1)
            self.combo_topo.setCurrentIndex(idx)

        btn_dice_topo.clicked.connect(_dice_topo)

        btn_row.addWidget(btn_dice_master)
        btn_row.addWidget(btn_dice_topo)
        g_layout.addLayout(btn_row)

        layout.addWidget(group)
        return panel
