import os
import json
import random
import logging
import datetime
import re

from ai_engine_config import load_ai_config
from .maestro_acoustic_mirror import MaestroAcousticMirror
from .maestro_taste_profiler import MaestroTasteProfiler
from .maestro_metaphor_alchemist import MaestroMetaphorAlchemist
from .maestro_vision_decompiler import MaestroVisionDecompiler
from .maestro_ambient_muse import MaestroAmbientMuse

logger = logging.getLogger("VisualStudio.ScenarioMaestro")

class ScenarioMaestro:
    """
    AI 智能情景描述大師 Pro (V2)
    - 雙層架構：自然語言意象 -> 結構化物理規格書 (Rigid Spec) -> 可執行 p5.js 代碼
    - 聲學情感鏡像 (CLAP-VA Mirror)：將音樂特徵投影為情緒座標
    - 創作者專屬審美記憶 (Taste Profiler)：越用越懂創作者偏好
    - 概念隱喻解構與 4 大語意方向推子 (Metaphor Alchemist & Semantic Steer)
    - 視覺參考圖多模態逆向工程器 (Vision Decompiler)
    - 心流守護與靈感微光主動救場機制 (Ambient Muse)
    """

    MOODS = [
        {"id": "cyberpunk_solitude", "name": "賽博孤獨", "desc": "霓虹冷雨穿透幽暗街區，低頻律動迴盪於鋼鐵虛空"},
        {"id": "cosmic_genesis", "name": "宇宙創生", "desc": "星雲崩解重組，引力奇點在重拍時爆發耀眼光錐"},
        {"id": "deep_sea_abyss", "name": "深海沉潛", "desc": "生物發光水母游弋於海溝，水壓隨著和弦起伏波動"},
        {"id": "hyper_kinetic", "name": "極限動能", "desc": "重金屬幾何瘋狂撕裂位移，高頻踩鑔觸發量子色散"},
        {"id": "organic_bloom", "name": "有機繁衍", "desc": "黏菌與孢子網絡隨旋律自然生長，呼吸般柔和回彈"},
        {"id": "zen_minimalism", "name": "禪意極簡", "desc": "水墨黑白留白，單一線條在極限空靈中震顫"},
        {"id": "glitch_dystopia", "name": "反烏托邦故障", "desc": "訊號受阻與顯存撕裂，類比 CRT 噪點在節拍時過載"}
    ]

    GENRES = [
        {"id": "synthwave", "name": "Synthwave / Cyberpunk", "bpm": 120, "palette": ["#ff007f", "#00f0ff", "#7928ca", "#0b0c10"]},
        {"id": "melodic_techno", "name": "Melodic Techno", "bpm": 126, "palette": ["#0ea5e9", "#6366f1", "#1e1b4b", "#030712"]},
        {"id": "drum_and_bass", "name": "Drum & Bass / Jungle", "bpm": 174, "palette": ["#f59e0b", "#ef4444", "#84cc16", "#18181b"]},
        {"id": "ambient_drone", "name": "Ambient / Meditative", "bpm": 70, "palette": ["#a78bfa", "#38bdf8", "#34d399", "#0f172a"]},
        {"id": "lofi_hiphop", "name": "Lo-Fi Hip Hop", "bpm": 85, "palette": ["#f97316", "#eab308", "#854d0e", "#1c1917"]},
        {"id": "industrial_glitch", "name": "Industrial / Glitch", "bpm": 135, "palette": ["#e11d48", "#ffffff", "#475569", "#000000"]}
    ]

    MATHEMATICAL_TOPOLOGIES = [
        {
            "id": "lorenz_attractor",
            "name": "Lorenz 混沌吸引子",
            "category": "chaos",
            "desc": "經典氣象學蝴蝶效應三維混沌空間軌跡",
            "recommended_shaders": ["volumetric_godrays", "chromatic_aberration"]
        },
        {
            "id": "curl_noise_fluid",
            "name": "Curl Noise 渦流場",
            "category": "fluid",
            "desc": "無散度流體力學粒子運動，絲滑如液態絲綢",
            "recommended_shaders": ["reaction_diffusion", "analog_saturation_grain"]
        },
        {
            "id": "gyroid_surface",
            "name": "Gyroid 三週期極小曲面",
            "category": "geometry",
            "desc": "自然界肥皂泡膜連通極小曲面拓撲",
            "recommended_shaders": ["ssfr_fluid_render", "caustic_refraction_flow"]
        },
        {
            "id": "chladni_plate",
            "name": "Chladni 聲學共振板",
            "category": "optics",
            "desc": "金屬板在音頻共振下的幾何沙粒節線圖案",
            "recommended_shaders": ["acoustic_chladni", "matrix_glitch_mosaic"]
        },
        {
            "id": "physarum_slime",
            "name": "Physarum 黏菌網絡",
            "category": "bio",
            "desc": "生物自組織覓食路徑網絡，具備強烈有機生命感",
            "recommended_shaders": ["bioluminescence_marine", "drone_spectral_fog"]
        },
        {
            "id": "voronoi_crystalline",
            "name": "Voronoi 幾何晶體動態",
            "category": "geometry",
            "desc": "空間最近鄰多面體切分，重音爆發時晶體碎裂",
            "recommended_shaders": ["voronoi_crystalline", "anamorphic_lens_flare"]
        }
    ]

    def __init__(self, workspace_dir: str = None):
        self.config = load_ai_config()
        self.workspace_dir = workspace_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 初始化四大神經升級外掛
        self.acoustic_mirror = MaestroAcousticMirror
        self.taste_profiler = MaestroTasteProfiler(self.workspace_dir)
        self.metaphor_alchemist = MaestroMetaphorAlchemist
        self.vision_decompiler = MaestroVisionDecompiler
        self.ambient_muse = MaestroAmbientMuse()

    def spin_inspiration_slot(self, acoustic_meta: dict = None) -> dict:
        """
        靈感老虎機 (整合創作者審美口味 + 聲學情感鏡像)
        """
        # 1. 若有傳入當前音樂特徵，先進行聲學情感映射
        va_result = None
        if acoustic_meta:
            va_result = self.acoustic_mirror.project_to_va_space(acoustic_meta)

        # 2. 結合創作者歷史偏好進行加權抽樣 (保留 20% 探索驚喜)
        mood = self.taste_profiler.get_weighted_choice(self.MOODS, "genre") or random.choice(self.MOODS)
        genre = self.taste_profiler.get_weighted_choice(self.GENRES, "genre") or random.choice(self.GENRES)
        topology = self.taste_profiler.get_weighted_choice(self.MATHEMATICAL_TOPOLOGIES, "topology") or random.choice(self.MATHEMATICAL_TOPOLOGIES)

        # 若聲學情緒明確，給予拓撲建議偏向
        if va_result and va_result["quadrant_info"]["preferred_topologies"]:
            favored = va_result["quadrant_info"]["preferred_topologies"]
            for t in self.MATHEMATICAL_TOPOLOGIES:
                if t["id"] in favored:
                    topology = t
                    break

        title = f"{mood['name']} · {topology['name']} ({genre['name']})"
        taste_desc = self.taste_profiler.get_taste_summary()

        narrative = (
            f"在 {genre['name']} ({genre['bpm']} BPM) 的動態韻律下，"
            f"呈現「{mood['name']}」的視聽意象：{mood['desc']}。\n"
            f"幾何核心：基於「{topology['name']}」構建，{topology['desc']}。\n"
            f"推薦著色器：{', '.join(topology['recommended_shaders'])}。\n"
            f"<i>[審美記憶] {taste_desc}</i>"
        )

        return {
            "title": title,
            "mood": mood,
            "genre": genre,
            "topology": topology,
            "narrative": narrative,
            "suggested_shaders": topology["recommended_shaders"],
            "va_result": va_result
        }

    def generate_rigid_spec(self, user_prompt: str, target_genre: str = None, acoustic_meta: dict = None, semantic_steer: dict = None) -> dict:
        """
        將用戶意象/音樂/語意推子編譯為結構化物理規格書
        """
        user_prompt_lower = user_prompt.lower()

        # 1. 概念隱喻解構
        metaphor_meta = self.metaphor_alchemist.deconstruct_metaphor(user_prompt)

        # 2. 聲學情感鏡像
        va_meta = None
        if acoustic_meta:
            va_meta = self.acoustic_mirror.project_to_va_space(acoustic_meta)

        # 3. 匹配拓撲
        matched_topo = self.MATHEMATICAL_TOPOLOGIES[0]
        for topo in self.MATHEMATICAL_TOPOLOGIES:
            if topo["id"] in user_prompt_lower or topo["name"].lower() in user_prompt_lower:
                matched_topo = topo
                break
            if topo["category"] in user_prompt_lower:
                matched_topo = topo
                break

        # 4. 匹配流派
        matched_genre = self.GENRES[0]
        if target_genre:
            for g in self.GENRES:
                if g["id"] == target_genre or g["name"].lower() in target_genre.lower():
                    matched_genre = g
                    break
        else:
            for g in self.GENRES:
                if g["id"] in user_prompt_lower or g["name"].lower() in user_prompt_lower:
                    matched_genre = g
                    break

        # 5. 語意推子計算 (Chaos, Organic, Aggression, Depth)
        steer = semantic_steer or {}
        steer_mods = self.metaphor_alchemist.compute_semantic_modulation(
            chaos=steer.get("chaos", 0.5),
            organic=steer.get("organic", 0.5),
            aggression=steer.get("aggression", 0.5),
            depth=steer.get("depth", 0.5)
        )

        spec = {
            "title": f"{matched_topo['name']} - {matched_genre['name']}",
            "topology_id": matched_topo["id"],
            "genre": matched_genre["name"],
            "bpm": matched_genre["bpm"],
            "palette": matched_genre["palette"],
            "metaphor": metaphor_meta,
            "va_meta": va_meta,
            "steer_mods": steer_mods,
            "params": {
                "speed": 0.02 * (va_meta["recommended_physics"]["speed_multiplier"] if va_meta else 1.0),
                "scaleMultiplier": 1.2 * steer_mods["bass_power_multiplier"],
                "particleCount": int((va_meta["recommended_physics"]["particle_density"] if va_meta else 1200) * (1.0 + (steer.get("chaos", 0.5) - 0.5))),
                "damping": 18.0 * (1.0 / max(0.2, steer_mods["spring_decay_time"]))
            },
            "audio_bindings": {
                "sub_bass": "scaleMultiplier",
                "bass": "particleJitter",
                "mid": "colorHueDrift",
                "high": "particleSparkle"
            },
            "shaders": matched_topo["recommended_shaders"]
        }
        return spec

    def route_engine(self, prompt: str) -> str:
        """
        AI 總導演智能引擎路由器 (Engine Director Routing)
        分析提示詞語意特徵，推薦最佳渲染引擎 (math_synth / pixel_art / surreal_collage)
        """
        p_lower = prompt.lower()
        
        # 1. 像素點陣關鍵字
        pixel_keywords = ["pixel", "8bit", "16bit", "retro", "gameboy", "dither", "bayer", "crt", "halftone", "像素", "點陣", "紅白機", "復古遊戲", "網點", "掃描線"]
        if any(k in p_lower for k in pixel_keywords):
            return "pixel_art"
            
        # 2. 超現實拼貼關鍵字
        surreal_keywords = ["surreal", "collage", "dali", "magritte", "dream", "floating", "totem", "deconstruct", "拼貼", "超現實", "達利", "馬格利特", "夢境", "解構", "肢體", "圖騰", "眼球"]
        if any(k in p_lower for k in surreal_keywords):
            return "surreal_collage"
            
        # 3. 預設為神經數學拓撲
        return "math_synth"

    def recommend_engine_and_spec(self, prompt: str, emotion_va: tuple = None, steer_sliders: dict = None) -> dict:
        """
        AI 總導演全域調度方案：輸出引擎選擇、專屬參數建議、推薦著色器與音訊配置
        """
        engine_id = self.route_engine(prompt)
        base_spec = self.generate_rigid_spec(
            user_prompt=prompt,
            acoustic_meta={"bpm": 128},
            semantic_steer=steer_sliders or {}
        )
        
        engine_spec = {
            "engine_id": engine_id,
            "prompt": prompt,
            "scene_spec": base_spec,
            "recommended_params": {},
            "shaders": base_spec.get("shaders", [1, 7, 12])
        }
        
        if engine_id == "pixel_art":
            engine_spec["recommended_params"] = {
                "pixelSize": 10 if "8bit" in prompt.lower() else 14,
                "ditherStrength": 0.75 if "dither" in prompt.lower() else 0.5,
                "styleMode": 1 if "bayer" in prompt.lower() else (4 if "halftone" in prompt.lower() else 2),
                "paletteMode": 0 if "cyber" in prompt.lower() else (1 if "gameboy" in prompt.lower() else 8)
            }
            engine_spec["shaders"] = [3, 7, 9]  # CRT, Scanline, Glitch
        elif engine_id == "surreal_collage":
            engine_spec["recommended_params"] = {
                "scaleInversion": 2.5,
                "orbitRadius": 220,
                "orbitSpeed": 0.025,
                "floatFrequency": 0.05,
                "duotoneStrength": 0.8
            }
            engine_spec["shaders"] = [2, 5, 14]  # Sepia, Chromatic, Vignette
        else:
            engine_spec["recommended_params"] = base_spec.get("params", {})
            
        return engine_spec

    def decompile_image_reference(self, image_path: str) -> dict:
        """多模態視覺參考圖逆向拆解"""
        return self.vision_decompiler.decompile_reference_image(image_path)

    def synthesize_p5_code(self, spec: dict) -> str:
        """根據規格書合成具備 @wizard 標籤的高質量 p5.js 代碼"""
        topo_id = spec.get("topology_id", "lorenz_attractor")
        palette = spec.get("palette", ["#ff007f", "#00f0ff", "#7928ca", "#0b0c10"])
        c1, c2, c3, c_bg = palette[0], palette[1], palette[2], palette[3]
        steer = spec.get("steer_mods", {})

        # 語意推子動態係數
        bass_pow = steer.get("bass_power_multiplier", 1.4)
        noise_f = steer.get("noise_frequency", 0.003)
        particle_c = spec.get("params", {}).get("particleCount", 1500)

        if topo_id == "curl_noise_fluid":
            return f"""// ============================================================================
// 🌌 視界引導精靈生成模組: Curl Noise 渦流流體 (Maestro V2 Enhanced)
// 🎨 主色調: {c1} | 輔色: {c2} | 背景: {c_bg}
// ============================================================================

let particleCount = {particle_c}; // @wizard(min=200, max=4000, step=100, label="粒子數量")
let flowSpeed = 0.015;    // @wizard(min=0.002, max=0.05, step=0.001, label="流動速率")
let noiseScale = {noise_f:.4f};   // @wizard(min=0.0005, max=0.01, step=0.0005, label="流場渦流頻率")
let bassPower = {bass_pow:.1f};      // @wizard(min=0.5, max=3.0, step=0.1, label="重低音爆發倍率")
let trailDecay = 25;      // @wizard(min=5, max=60, step=5, label="殘影尾跡長度")

let particles = [];
let audioEnergy = {{ bass: 0, mid: 0, high: 0, sub_bass: 0 }};

function setup() {{
  createCanvas(windowWidth, windowHeight);
  colorMode(RGB, 255);
  background("{c_bg}");
  
  for (let i = 0; i < 4000; i++) {{
    particles.push({{
      x: random(width),
      y: random(height),
      vx: 0,
      vy: 0,
      age: random(100),
      seed: random(1000)
    }});
  }}
}}

function draw() {{
  if (window.audioParams) {{
    audioEnergy.bass = window.audioParams.bass || 0;
    audioEnergy.sub_bass = window.audioParams.sub_bass || 0;
    audioEnergy.mid = window.audioParams.mid || 0;
    audioEnergy.high = window.audioParams.high || 0;
  }}

  push();
  noStroke();
  fill(11, 12, 16, trailDecay);
  rect(0, 0, width, height);
  pop();

  let activeCount = min(particleCount, particles.length);
  let time = frameCount * flowSpeed;
  let dynamicScale = noiseScale * (1.0 + audioEnergy.mid * 0.5);
  let currentBass = (1.0 + (audioEnergy.sub_bass || audioEnergy.bass) * bassPower);

  strokeWeight(1.2 + audioEnergy.high * 2.0);

  for (let i = 0; i < activeCount; i++) {{
    let p = particles[i];
    let n1 = noise(p.x * dynamicScale, p.y * dynamicScale, time);
    let n2 = noise(p.x * dynamicScale + 5.2, p.y * dynamicScale + 1.3, time);
    
    let angle = n1 * TWO_PI * 2.0;
    p.vx = cos(angle) * 2.5 * currentBass;
    p.vy = sin(angle) * 2.5 * currentBass;

    p.x += p.vx;
    p.y += p.vy;
    p.age++;

    if (p.x < 0) p.x = width;
    if (p.x > width) p.x = 0;
    if (p.y < 0) p.y = height;
    if (p.y > height) p.y = 0;

    let t = (i / activeCount + frameCount * 0.005) % 1.0;
    if (t < 0.5) {{
      stroke(lerpColor(color("{c1}"), color("{c2}"), t * 2.0));
    }} else {{
      stroke(lerpColor(color("{c2}"), color("{c3}"), (t - 0.5) * 2.0));
    }}

    point(p.x, p.y);
  }}
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}
"""
        elif topo_id == "gyroid_surface":
            return f"""// ============================================================================
// 🌌 視界引導精靈生成模組: Gyroid 極小曲面拓撲 (Maestro V2 Enhanced)
// 🎨 主色調: {c1} | 輔色: {c2} | 背景: {c_bg}
// ============================================================================

let gridResolution = 28;  // @wizard(min=12, max=50, step=2, label="曲面網格解析度")
let morphSpeed = 0.02;    // @wizard(min=0.005, max=0.08, step=0.005, label="相位演化速率")
let gyroidScale = 0.12;   // @wizard(min=0.05, max=0.3, step=0.01, label="空間頻率尺度")
let pulseStrength = {bass_pow:.1f};  // @wizard(min=0.2, max=3.0, step=0.1, label="重低音脈衝衝擊")

let audioEnergy = {{ bass: 0, mid: 0, high: 0, sub_bass: 0 }};

function setup() {{
  createCanvas(windowWidth, windowHeight, WEBGL);
  colorMode(RGB, 255);
}}

function draw() {{
  if (window.audioParams) {{
    audioEnergy.bass = window.audioParams.bass || 0;
    audioEnergy.sub_bass = window.audioParams.sub_bass || 0;
    audioEnergy.mid = window.audioParams.mid || 0;
    audioEnergy.high = window.audioParams.high || 0;
  }}

  background("{c_bg}");
  orbitControl(1, 1, 0.1);

  let bassPulse = 1.0 + (audioEnergy.sub_bass || audioEnergy.bass) * pulseStrength;
  scale(1.0 * bassPulse);

  rotateX(frameCount * 0.005);
  rotateY(frameCount * 0.008);

  let phase = frameCount * morphSpeed;
  let step = 380 / gridResolution;
  let s = gyroidScale;

  noFill();
  strokeWeight(1.5 + audioEnergy.high * 1.5);

  for (let x = -gridResolution/2; x < gridResolution/2; x++) {{
    let worldX = x * step;
    let tColor = map(x, -gridResolution/2, gridResolution/2, 0, 1);
    stroke(lerpColor(color("{c1}"), color("{c2}"), tColor));

    beginShape(LINES);
    for (let y = -gridResolution/2; y < gridResolution/2; y++) {{
      let worldY = y * step;
      let val = sin(worldX * s + phase) * cos(worldY * s) +
                sin(worldY * s + phase) * cos(phase) +
                sin(phase) * cos(worldX * s);
      let worldZ = val * 65.0;
      vertex(worldX, worldY, worldZ);
      vertex(worldX + step, worldY, worldZ);
    }}
    endShape();
  }}
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}
"""
        else:
            zoom_l = steer.get("camera_zoom", 8.5)
            return f"""// ============================================================================
// 🌌 視界引導精靈生成模組: Lorenz 混沌吸引子 (Maestro V2 Enhanced)
// 🎨 主色調: {c1} | 輔色: {c2} | 背景: {c_bg}
// ============================================================================

let pointCount = {particle_c};    // @wizard(min=500, max=5000, step=100, label="軌跡點數量")
let dt = 0.008;           // @wizard(min=0.001, max=0.02, step=0.001, label="迭代時間步長")
let rotSpeed = 0.012;     // @wizard(min=0.002, max=0.05, step=0.002, label="空間旋轉速度")
let bassScale = {bass_pow:.1f};      // @wizard(min=0.5, max=3.5, step=0.1, label="低頻震盪幅度")
let zoomLevel = {zoom_l:.1f};      // @wizard(min=3.0, max=16.0, step=0.5, label="鏡頭縮放焦距")

let x = 0.01, y = 0, z = 0;
let a = 10, b = 28, c = 8/3;
let points = [];
let audioEnergy = {{ bass: 0, mid: 0, high: 0, sub_bass: 0 }};

function setup() {{
  createCanvas(windowWidth, windowHeight, WEBGL);
  colorMode(RGB, 255);
  background("{c_bg}");
}}

function draw() {{
  if (window.audioParams) {{
    audioEnergy.bass = window.audioParams.bass || 0;
    audioEnergy.sub_bass = window.audioParams.sub_bass || 0;
    audioEnergy.mid = window.audioParams.mid || 0;
    audioEnergy.high = window.audioParams.high || 0;
  }}

  background("{c_bg}");
  orbitControl(1, 1, 0.1);

  let dynamicZoom = zoomLevel * (1.0 + (audioEnergy.sub_bass || audioEnergy.bass) * 0.3);
  scale(dynamicZoom);

  rotateX(frameCount * rotSpeed * 0.6);
  rotateY(frameCount * rotSpeed);

  let currentDt = dt * (1.0 + audioEnergy.mid * 0.4);
  let dx = (a * (y - x)) * currentDt;
  let dy = (x * (b - z) - y) * currentDt;
  let dz = (x * y - c * z) * currentDt;
  x += dx;
  y += dy;
  z += dz;

  points.push(createVector(x, y, z));
  if (points.length > pointCount) {{
    points.splice(0, points.length - pointCount);
  }}

  noFill();
  strokeWeight(1.4 + audioEnergy.high * 2.0);

  beginShape();
  for (let i = 0; i < points.length; i++) {{
    let p = points[i];
    let t = i / points.length;
    let col = lerpColor(color("{c1}"), color("{c2}"), t);
    stroke(col);
    vertex(p.x, p.y, p.z - 25);
  }}
  endShape();
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}
"""
