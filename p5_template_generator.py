class P5SurrealTemplateGenerator:
    """
    SAVAP v3.0 旗艦級 p5.js 多元素音畫互動腳本生成器：
    - 支援 2 ~ 10 個多元素空間拓撲 (Totem / Orbital / Constellation)
    - 包含創作主題與思維宣言 (Concept Manifesto)
    - 頻段分流解耦、多米諾衝擊波、動態形態蛻變
    """
    @staticmethod
    def generate_multi_element_masterpiece_script(
        asset_id: str,
        theme_meta: dict,
        orchestrated_scene: dict,
        style_name: str,
        scale_inversion: float = 2.2,
        duotone_strength: float = 0.85
    ) -> str:
        topology = orchestrated_scene.get("topology", "orbital")
        elements = orchestrated_scene.get("elements", [])
        num_elements = len(elements)

        # 生成素材加載宣告
        image_var_decls = ["imgHeroHead, imgHeroTorso, imgHeroArmUL, imgHeroArmFL, imgHeroArmUR, imgHeroArmFR;"]
        preload_loaders = [
            f'  let base = "custom_visuals/assets/{asset_id}/";',
            '  imgHeroHead = loadImage(base + "head.png");',
            '  imgHeroTorso = loadImage(base + "torso.png");',
            '  imgHeroArmUL = loadImage(base + "upper_arm_l.png");',
            '  imgHeroArmFL = loadImage(base + "forearm_l.png");',
            '  imgHeroArmUR = loadImage(base + "upper_arm_r.png");',
            '  imgHeroArmFR = loadImage(base + "forearm_r.png");'
        ]

        for i in range(1, num_elements):
            image_var_decls.append(f"imgElement_{i};")
            preload_loaders.append(f'  imgElement_{i} = loadImage(base + "element_{i}.png");')

        var_decl_str = "let " + ", ".join(image_var_decls)
        preload_str = "\n".join(preload_loaders)

        # 次要元素繪製邏輯
        elem_draw_functions = []
        for i in range(1, num_elements):
            elem_meta = elements[i] if i < len(elements) else {}
            role = elem_meta.get("role", "satellite")
            z_depth = elem_meta.get("z_depth", 0.6)
            orbit_r = elem_meta.get("orbit_radius", 180 + i * 45)
            ang_offset = elem_meta.get("angle_offset", i * 0.8)
            spd = elem_meta.get("orbit_speed", 0.015 + i * 0.005)

            elem_draw_functions.append(f"""
function drawElement_{i}(bass, mid, high, chordColorHex) {{
  if (!imgElement_{i}) return;
  let c = color(chordColorHex);

  // 拓撲位置計算
  let totemX = width * 0.5 + sin(frameCount * 0.03 + {i}) * 18;
  let totemY = height * 0.3 - ({i - 1} * 75) + (bass - 0.5) * 20;

  let orbitalAngle = frameCount * {spd} + {ang_offset} + mid * 0.04;
  let orbitalX = width * 0.5 + cos(orbitalAngle) * ({orbit_r});
  let orbitalY = height * 0.5 + sin(orbitalAngle * 1.5) * ({orbit_r * 0.55}) + (bass - 0.5) * 35;

  let posX = lerp(totemX, orbitalX, topologyMorph);
  let posY = lerp(totemY, orbitalY, topologyMorph);

  push();
  translate(posX, posY);
  rotate(sin(frameCount * 0.02 + {i}) * 0.25);

  let elemScale = {scale_inversion} * {0.45 + (1.0 - z_depth) * 0.5} + (bass - 0.5) * 0.2;
  scale(elemScale);

  // 錯位投影
  push();
  translate(16, 22);
  tint(0, 0, 0, 130);
  image(imgElement_{i}, 0, 0);
  pop();

  // 雙色調著色
  tint(lerp(220, red(c), {duotone_strength}), lerp(220, green(c), {duotone_strength}), lerp(220, blue(c), {duotone_strength}), 240);
  image(imgElement_{i}, 0, 0);
  pop();
}}
""")

        all_elem_draw_calls = "\n  ".join([f"drawElement_{i}(bass, mid, high, chordColorHex);" for i in range(1, num_elements)])

        return f"""// ============================================================================
// 🌌 超現實音畫拼貼神作 (SAVAP v3.0 Masterpiece): {asset_id}
// 🎨 創作主題: {theme_meta.get('theme_title', 'Surreal Multi-Element Collage')}
// 🧠 哲學思維: {theme_meta.get('concept_thought', 'Surrealist juxtaposition of subconscious symbols.')}
// 🏛️ 空間拓撲: {topology} | 元素數量: {num_elements}
// ============================================================================

{var_decl_str}

let headOffsetY = 0, headVelY = 0;
let shockwaves = [];
let topologyMorph = 0.0;
let flashOpacity = 0;
let dustParticles = [];

function preload() {{
{preload_str}
}}

function setup() {{
  createCanvas(windowWidth, windowHeight);
  imageMode(CENTER);
  noStroke();

  for (let i = 0; i < 50; i++) {{
    dustParticles.push({{
      x: random(width),
      y: random(height),
      size: random(1.5, 4.0),
      speedY: random(-0.4, -1.2),
      seed: random(1000)
    }});
  }}
}}

function draw() {{
  let bass = (typeof window.audioLow !== 'undefined') ? window.audioLow : 0.5;
  let mid = (typeof window.audioMid !== 'undefined') ? window.audioMid : 0.5;
  let high = (typeof window.audioHigh !== 'undefined') ? window.audioHigh : 0.5;
  let isBeat = (typeof window.isBeat !== 'undefined') ? window.isBeat : false;
  let beatEnergy = (typeof window.beatEnergy !== 'undefined') ? window.beatEnergy : 0.0;
  let chordColorHex = window.currentChordColor || "#6366f1";

  let targetMorph = (bass > 0.65 || (isBeat && beatEnergy > 0.7)) ? 1.0 : 0.0;
  topologyMorph = lerp(topologyMorph, targetMorph, 0.06);

  // 1. 遠景大氣流體
  drawAtmosphere(bass, chordColorHex);

  // 2. 多米諾衝擊波
  if (isBeat) {{
    headVelY = -32.0 * (1.0 + beatEnergy);
    shockwaves.push({{
      x: width * 0.5,
      y: height * 0.58,
      radius: 15,
      maxRadius: width * 0.9,
      energy: 1.0 + beatEnergy,
      speed: 18 + bass * 25
    }});
    if (high > 0.75 || beatEnergy > 0.8) flashOpacity = 160;
  }}

  headVelY += 2.8;
  headOffsetY += headVelY;
  if (headOffsetY > 0) {{ headOffsetY = 0; headVelY = 0; }}

  drawShockwaves(chordColorHex);

  // 3. 次要衝突多元素 (2 ~ {num_elements})
  {all_elem_draw_calls}

  // 4. 核心焦點主體 (Hero Subject)
  drawHeroSubject(bass, mid, high, chordColorHex);

  // 5. 前景粒子與曼雷中途曝光
  drawForegroundDust(high);
  if (flashOpacity > 0) {{
    fill(255, 255, 255, flashOpacity);
    rect(0, 0, width, height);
    flashOpacity -= 14;
  }}
}}

function drawAtmosphere(bass, chordColorHex) {{
  let c = color(chordColorHex);
  background(red(c) * 0.08, green(c) * 0.08, blue(c) * 0.12, 220);
  
  let skySteps = 7;
  for (let s = skySteps; s > 0; s--) {{
    let alphaVal = map(s, 0, skySteps, 12, 80);
    fill(red(c) * 0.75, green(c) * 0.65, blue(c) * 0.95, alphaVal * (0.3 + bass * 0.7));
    beginShape();
    for (let x = 0; x <= width; x += 40) {{
      let y = height * 0.36 + sin(x * 0.004 + frameCount * 0.02 + s) * 45 * s * (0.5 + bass);
      vertex(x, y);
    }}
    vertex(width, height);
    vertex(0, height);
    endShape(CLOSE);
  }}
}}

function drawShockwaves(chordColorHex) {{
  let c = color(chordColorHex);
  for (let i = shockwaves.length - 1; i >= 0; i--) {{
    let sw = shockwaves[i];
    noFill();
    let alphaSw = map(sw.radius, 0, sw.maxRadius, 230, 0);
    stroke(red(c), green(c), blue(c), alphaSw);
    strokeWeight(2 + sw.energy * 2);
    ellipse(sw.x, sw.y, sw.radius * 2);
    sw.radius += sw.speed;
    if (sw.radius > sw.maxRadius) {{
      shockwaves.splice(i, 1);
    }}
  }}
}}

function drawHeroSubject(bass, mid, high, chordColorHex) {{
  let lfoX = cos(frameCount * 0.017) * 16;
  let lfoY = sin(frameCount * 0.027) * 18;

  let heroTargetX = lerp(width * 0.5, width * 0.44, topologyMorph);
  let heroTargetY = lerp(height * 0.64, height * 0.58, topologyMorph);

  push();
  translate(heroTargetX + lfoX, heroTargetY + lfoY);

  let squash = 1.0 + (bass - 0.5) * 0.32;
  let stretch = 1.0 - (bass - 0.5) * 0.24;
  scale(squash, stretch);

  push();
  translate(sin(frameCount * 0.03) * 18, 24);
  tint(0, 0, 0, 140);
  if (imgHeroTorso) image(imgHeroTorso, 0, 0);
  pop();

  let c = color(chordColorHex);
  tint(lerp(255, red(c), {duotone_strength} * 0.55), lerp(255, green(c), {duotone_strength} * 0.55), lerp(255, blue(c), {duotone_strength} * 0.55), 255);

  if (imgHeroTorso) image(imgHeroTorso, 0, 0);

  push();
  translate(0, -135 + headOffsetY);
  rotate(sin(frameCount * 0.05) * 0.12 * mid);
  if (imgHeroHead) image(imgHeroHead, 0, 0);
  pop();

  push();
  translate(-75, -60);
  rotate(sin(frameCount * 0.04) * 0.7 + (mid * 1.0));
  if (imgHeroArmUL) image(imgHeroArmUL, 0, 40);
  translate(0, 75);
  rotate(cos(frameCount * 0.08) * 0.9 + (high * 1.8));
  if (imgHeroArmFL) image(imgHeroArmFL, 0, 40);
  pop();

  push();
  translate(75, -60);
  rotate(-sin(frameCount * 0.04) * 0.7 - (mid * 1.0));
  if (imgHeroArmUR) image(imgHeroArmUR, 0, 40);
  translate(0, 75);
  rotate(-cos(frameCount * 0.08) * 0.9 - (high * 1.8));
  if (imgHeroArmFR) image(imgHeroArmFR, 0, 40);
  pop();

  pop();
}}

{"".join(elem_draw_functions)}

function drawForegroundDust(high) {{
  fill(240, 240, 255, 120 + high * 80);
  for (let p of dustParticles) {{
    p.y += p.speedY * (1.0 + high * 1.6);
    p.x += sin(frameCount * 0.02 + p.seed) * 0.4;
    if (p.y < 0) p.y = height;
    ellipse(p.x, p.y, p.size, p.size);
  }}
}}

function windowResized() {{
  resizeCanvas(windowWidth, windowHeight);
}}
"""
