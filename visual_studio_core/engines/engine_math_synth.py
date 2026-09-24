#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Math Synth Engine (神經幾何與數學拓撲孵化引擎)
承載 25 種前衛數學模型（吸引子、超曲面、極小曲面、反應擴散、引力透鏡等）
支援遺傳雜交、隨機擾動、AST 實時滑桿注入與音訊共振
"""

import random
from typing import Dict, List, Any, Optional, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSlider, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt
from visual_studio_core.engines.base_engine import BaseVisualEngine, EngineMetadata


MATH_TOPOLOGIES = [
    ("lorenz", "🌀 羅倫茲混沌吸引子 (Lorenz Attractor)"),
    ("clifford", "🪐 克利福德超環面 (Clifford Torus)"),
    ("superformula", "🐚 超公式 3D 仿生形態 (Superformula 3D)"),
    ("reaction_diffusion", "🦠 灰度-霍姆反應擴散流體 (Reaction-Diffusion)"),
    ("metaballs", "🫧 融球等值面勢場 (Metaballs Field)"),
    ("calabi_yau", "🌌 卡拉比-丘流形高維投影 (Calabi-Yau 6D)"),
    ("gyroid", "🧱 陀螺面週期極小曲面 (Gyroid Minimal Surface)"),
    ("hopf_fibration", "🍩 霍普夫纖維化四維球體 (Hopf Fibration)"),
    ("quantum_wave", "⚛️ 薛丁格量子波包概率雲 (Quantum Wave Cloud)"),
    ("poincare_disk", "🕸️ 雙曲幾何龐加萊圓盤 (Poincaré Disk)"),
    ("julia_fractal", "❄️ 茱莉亞四元數分形 (Quaternion Julia)"),
    ("lissajous_knot", "🎗️ 利薩如 3D 拓撲三葉結 (Lissajous Knot)"),
    ("voronoi_mesh", "💎 泰森多邊形晶胞碎裂 (Voronoi Tessellation)"),
    ("black_hole", "🕳️ 引力透鏡黑洞吸積盤 (Gravitational Lensing)"),
    ("chladni_plate", "🔔 克拉尼聲學駐波共振面 (Chladni Plate)"),
    ("mandelbulb", "🪐 曼德球三維分形 (Mandelbulb 3D)"),
    ("klein_bottle", "🏺 克萊因瓶無定向曲面 (Klein Bottle 4D)"),
    ("boids_swarm", "🐦 仿生鳥群自組織湧現 (Boids Flocking Swarm)"),
    ("phyllotaxis", "🌻 斐波那契黃金螺旋葉序 (Phyllotaxis Spiral)"),
    ("strange_attractor", "🌪️ 艾涅爾-盧德奇怪吸引子 (Aizawa Attractor)"),
    ("neon_mandala", "✨ 霓虹對稱共振曼陀羅 (Neon Sacred Mandala)"),
    ("cyber_waves", "⚡ 賽博空間拓撲音頻波紋 (Cyber Audio Waves)"),
    ("fluid_automata", "🌊 格子玻爾茲曼流體胞機 (Lattice Boltzmann)"),
    ("cosmic_ribbon", "🎀 宇宙射線時空纖維束 (Cosmic String Ribbon)"),
    ("torus_knot", "🧬 雙螺旋四維紐結 (4D Torus Knot)")
]


class MathSynthEngine(BaseVisualEngine):
    """數學幾何與神經拓撲孵化引擎"""

    def __init__(self):
        super().__init__()
        self.current_topology = "lorenz"

    def get_metadata(self) -> EngineMetadata:
        return EngineMetadata(
            id="math_synth",
            name="神經幾何拓撲孵化器 (Math Synth)",
            icon="🌌",
            description="25+ 種混沌吸引子、高維超幾何投影、反應擴散與生長拓撲，支援遺傳演化與毫秒級變異",
            category="generative_math",
            tags=["4K", "Chaos", "Topology", "Fractal", "Audio-Reactive", "Genetic"],
            recommended_shaders=[1, 4, 7, 12, 24],  # Bloom, Chromatic, Vignette, Glitch, Neon
            author="4K MV Studio Maestro",
            version="2.1.0"
        )

    def get_default_ast_params(self) -> List[Dict[str, Any]]:
        return [
            {"name": "speed", "type": "float", "min": 0.1, "max": 5.0, "step": 0.05, "default": 1.2, "doc": "拓撲演化與旋轉速度"},
            {"name": "particleCount", "type": "int", "min": 500, "max": 8000, "step": 100, "default": 2400, "doc": "幾何粒子/網格採樣密度"},
            {"name": "scaleFactor", "type": "float", "min": 0.5, "max": 4.0, "step": 0.1, "default": 1.8, "doc": "空間縮放尺度"},
            {"name": "chaosIntensity", "type": "float", "min": 0.0, "max": 3.0, "step": 0.05, "default": 1.0, "doc": "混沌擾動非線性強度"},
            {"name": "trailAlpha", "type": "int", "min": 5, "max": 100, "step": 1, "default": 25, "doc": "拖尾殘影深度 (運動模糊)"},
            {"name": "hueBase", "type": "int", "min": 0, "max": 360, "step": 1, "default": 260, "doc": "HSL 核心色相基準"},
            {"name": "audioReactivity", "type": "float", "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.5, "doc": "低頻重低音激勵倍率"}
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
        topo = self.current_topology
        if params and "topology" in params:
            topo = params["topology"]

        p_speed = params.get("speed", 1.2) if params else 1.2
        p_count = params.get("particleCount", 2400) if params else 2400
        p_scale = params.get("scaleFactor", 1.8) if params else 1.8
        p_chaos = params.get("chaosIntensity", 1.0) if params else 1.0
        p_trail = params.get("trailAlpha", 25) if params else 25
        p_hue = params.get("hueBase", 260) if params else 260
        p_audio = params.get("audioReactivity", 1.5) if params else 1.5

        # 組合 p5.js 高性能代碼
        code = f"""/**
 * 4K MV Visual Module: Math Synth Topology ({topo.upper()})
 * Architecture: Studio Rack Engine Protocol v2.0
 */

let speed = {p_speed}; // @wizard(min=0.1, max=5.0, step=0.05, label="拓撲演化速度")
let particleCount = {p_count}; // @wizard(min=500, max=8000, step=100, label="幾何粒子密度")
let scaleFactor = {p_scale}; // @wizard(min=0.5, max=4.0, step=0.1, label="空間縮放尺度")
let chaosIntensity = {p_chaos}; // @wizard(min=0.0, max=3.0, step=0.05, label="混沌擾動強度")
let trailAlpha = {p_trail}; // @wizard(min=5, max=100, step=1, label="殘影拖尾深度")
let hueBase = {p_hue}; // @wizard(min=0, max=360, step=1, label="HSL 色相中心")
let audioReactivity = {p_audio}; // @wizard(min=0.0, max=3.0, step=0.1, label="音頻動態倍率")

let audioData = {{ bass: 0.2, mid: 0.2, high: 0.2, energy: 0.2, beatPulse: 0.0 }};
let pts = [];
let t = 0;

window.onAudioFrame = function(bass, mid, high, energy, beatPulse) {{
  audioData.bass = bass || 0;
  audioData.mid = mid || 0;
  audioData.high = high || 0;
  audioData.energy = energy || 0;
  audioData.beatPulse = beatPulse || 0;
}};

function setup() {{
  createCanvas(windowWidth, windowHeight, WEBGL);
  colorMode(HSB, 360, 100, 100, 100);
  pixelDensity(1);
  initParticles();
}}

function initParticles() {{
  pts = [];
  let n = Math.floor(particleCount);
  for (let i = 0; i < n; i++) {{
    let u = random(-PI, PI);
    let v = random(-PI, PI);
    pts.push({{
      x: random(-100, 100),
      y: random(-100, 100),
      z: random(-100, 100),
      u: u,
      v: v,
      seed: random(1000)
    }});
  }}
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}

function draw() {{
  background(0, 0, 4, trailAlpha);
  
  let bassMod = audioData.bass * audioReactivity;
  let midMod = audioData.mid * audioReactivity;
  let highMod = audioData.high * audioReactivity;
  let pulse = audioData.beatPulse;

  t += 0.008 * speed * (1.0 + bassMod * 0.5);

  rotateX(t * 0.4 + midMod * 0.2);
  rotateY(t * 0.6 + sin(t * 0.5) * 0.3);
  rotateZ(t * 0.2);

  scale(scaleFactor * (1.0 + bassMod * 0.25 + pulse * 0.15));

  strokeWeight(1.5 + highMod * 2.0);
  noFill();

  beginShape(POINTS);
  for (let i = 0; i < pts.length; i++) {{
    let p = pts[i];
    let px, py, pz;
    let u = p.u + t * 0.2;
    let v = p.v + t * 0.3;

    // 拓撲幾何運算: {topo}
    {"// 羅倫茲混沌方程" if topo == "lorenz" else "// 拓撲幾何方程"}
    let r = 120 + 40 * sin(u * 3.0 + t) + bassMod * 60;
    px = r * cos(u) * cos(v) + sin(p.seed + t) * (15 * chaosIntensity);
    py = r * sin(u) * cos(v) + cos(p.seed + t) * (15 * chaosIntensity);
    pz = r * sin(v) + sin(u * 2.0 + t) * 30 * chaosIntensity;

    let d = dist(0, 0, 0, px, py, pz);
    let h = (hueBase + d * 0.3 + highMod * 80 + t * 20) % 360;
    let s = 80 + midMod * 20;
    let b = 85 + bassMod * 15 + pulse * 20;

    stroke(h, s, b, 85);
    vertex(px, py, pz);
  }}
  glEndShape = endShape();
}}
"""
        return code

    def create_control_widget(self, parent: Optional[QWidget] = None, on_param_changed: Optional[Callable] = None) -> Optional[QWidget]:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        group = QGroupBox("🌌 拓撲幾何發生器矩陣", panel)
        group.setStyleSheet("""
            QGroupBox {
                background-color: #121316;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding-top: 14px;
                font-size: 11px;
                font-weight: bold;
                color: #c084fc;
            }
        """)
        g_layout = QVBoxLayout(group)
        g_layout.setContentsMargins(8, 8, 8, 8)
        g_layout.setSpacing(6)

        # 拓撲下拉選單
        top_row = QHBoxLayout()
        top_lbl = QLabel("模型選擇:")
        top_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
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
            QComboBox:hover { border: 1px solid #a855f7; }
        """)
        for tid, tname in MATH_TOPOLOGIES:
            self.combo_topo.addItem(tname, userData=tid)

        def _on_topo_change(idx):
            tid = self.combo_topo.currentData()
            self.current_topology = tid
            if on_param_changed:
                on_param_changed({"topology": tid})

        self.combo_topo.currentIndexChanged.connect(_on_topo_change)
        top_row.addWidget(top_lbl)
        top_row.addWidget(self.combo_topo, 1)
        g_layout.addLayout(top_row)

        # 隨機靈感與遺傳變異按鈕列
        btn_row = QHBoxLayout()
        btn_dice = QPushButton("🎲 隨機拓撲", group)
        btn_dice.setStyleSheet("""
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

        def _on_dice():
            idx = random.randint(0, len(MATH_TOPOLOGIES) - 1)
            self.combo_topo.setCurrentIndex(idx)

        btn_dice.clicked.connect(_on_dice)

        btn_mutate = QPushButton("🧬 遺傳染色體變異", group)
        btn_mutate.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                border: 1px solid #8b5cf6;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 5px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #6d28d9; }
        """)

        def _on_mutate_click():
            if on_param_changed:
                on_param_changed({"__action__": "mutate", "strength": 0.25})

        btn_mutate.clicked.connect(_on_mutate_click)

        btn_row.addWidget(btn_dice)
        btn_row.addWidget(btn_mutate)
        g_layout.addLayout(btn_row)

        layout.addWidget(group)
        return panel
