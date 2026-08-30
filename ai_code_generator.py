import json
import hashlib
import logging
import time
import requests
import subprocess
import os
import shutil
import datetime
import re

from ai_engine_config import load_ai_config, save_ai_config

logger = logging.getLogger("StandaloneInjector.AICodeGenerator")

class AICodeGenerator:
    """
    4K 視覺資產 AI 孵化器 - 原創代碼生成引擎
    
    支援混合雙引擎架構 (Hybrid Architecture)：
    - 本地 Ollama (llama3 / deepseek-r1 / gemma4 等) 零成本離線運行
    - 雲端大模型 Kimi (Moonshot AI) / DeepSeek Cloud 頂級 4K 幾何與藝術代碼秒級生成
    支援 25 種經典計算藝術數學模型模板，涵蓋混沌吸引子、流體模擬、碎形幾何等領域。
    """

    MATH_MODELS = {
        # Chaos & Attractors (chaos) - 6
        "lorenz_attractor": {
            "name": "Lorenz 吸引子",
            "name_en": "Lorenz Attractor",
            "category": "chaos",
            "category_name": "混沌系統 & 吸引子",
            "description": "經典氣象學蝴蝶效應 3D 混沌系統",
            "equations": "dx/dt = σ(y-x), dy/dt = x(ρ-y)-z, dz/dt = xy-βz",
            "prompt_hint": "Use a 3D coordinate array to store points. Update them in draw() using the Lorenz equations. Map the Z axis to color hue. Map audioEnergy.bass to the scale of the system or line thickness."
        },
        "rossler_attractor": {
            "name": "Rössler 吸引子",
            "name_en": "Rössler Attractor",
            "category": "chaos",
            "category_name": "混沌系統 & 吸引子",
            "description": "具備連續折疊拓樸特性的混沌系統",
            "equations": "dx/dt = -y-z, dy/dt = x+ay, dz/dt = b+z(x-c)",
            "prompt_hint": "Generate points iteratively. Use beginShape(POINTS) or LINE_STRIP. Audio reactivity should distort the 'c' parameter slightly."
        },
        "clifford_attractor": {
            "name": "Clifford 吸引子",
            "name_en": "Clifford Attractor",
            "category": "chaos",
            "category_name": "混沌系統 & 吸引子",
            "description": "2D 碎形點陣疊加混沌映射",
            "equations": "x_n+1 = sin(a*y_n) + c*cos(a*x_n), y_n+1 = sin(b*x_n) + d*cos(b*y_n)",
            "prompt_hint": "Render thousands of points per frame with low alpha. Use blendMode(ADD). Modulate parameters a,b,c,d with audioEnergy."
        },
        "de_jong_attractor": {
            "name": "De Jong 吸引子",
            "name_en": "De Jong Attractor",
            "category": "chaos",
            "category_name": "混沌系統 & 吸引子",
            "description": "Peter de Jong 2D 動態吸引子",
            "equations": "x_n+1 = sin(a*y_n) - cos(b*x_n), y_n+1 = sin(c*x_n) - cos(d*y_n)",
            "prompt_hint": "Draw densely plotted points. Let audio mid/high dictate the color palette."
        },
        "aizawa_attractor": {
            "name": "Aizawa 吸引子",
            "name_en": "Aizawa Attractor",
            "category": "chaos",
            "category_name": "混沌系統 & 吸引子",
            "description": "呈現球狀螺旋的 3D 吸引子",
            "equations": "dx/dt=(z-b)x-dy, dy/dt=dx+(z-b)y, dz/dt=c+az-z^3/3-(x^2+y^2)(1+ez)+f*z*x^3",
            "prompt_hint": "Rotate the 3D structure slowly. Link camera zoom or rotation speed to audioEnergy."
        },
        "halvorsen_attractor": {
            "name": "Halvorsen 吸引子",
            "name_en": "Halvorsen Attractor",
            "category": "chaos",
            "category_name": "混沌系統 & 吸引子",
            "description": "高度對稱的三維混沌映射",
            "equations": "dx/dt = -a*x - 4*y - 4*z - y^2, dy/dt = -a*y - 4*z - 4*x - z^2, dz/dt = -a*z - 4*x - 4*y - x^2",
            "prompt_hint": "Draw smooth trailing lines. Make line opacity react to audio high frequencies."
        },
        
        # Bio & Chemical (bio) - 5
        "reaction_diffusion": {
            "name": "反應擴散系統",
            "name_en": "Reaction Diffusion (Gray-Scott)",
            "category": "bio",
            "category_name": "生物與化學模擬",
            "description": "Gray-Scott 化學反應斑紋生成",
            "equations": "du/dt = Du*∇²u - u*v² + f*(1-u), dv/dt = Dv*∇²v + u*v² - (f+k)v",
            "prompt_hint": "Simulate using a 2D grid array. Optimize rendering using loadPixels()/updatePixels(). Map 'f' or 'k' feed rates slightly to audio sub_bass."
        },
        "boids_flocking": {
            "name": "Boids 群聚模擬",
            "name_en": "Boids Flocking",
            "category": "bio",
            "category_name": "生物與化學模擬",
            "description": "鳥群/魚群的自組織分離、對齊與凝聚",
            "equations": "separation, alignment, cohesion",
            "prompt_hint": "Create a Particle/Boid class. Apply the 3 rules. Increase max speed and alignment force when audioEnergy.bass peaks."
        },
        "slime_mold": {
            "name": "黏菌模擬",
            "name_en": "Physarum Slime Mold",
            "category": "bio",
            "category_name": "生物與化學模擬",
            "description": "基於代理人的化學物質追蹤與網路生長",
            "equations": "agent-based trail following, deposit, diffuse, decay",
            "prompt_hint": "Agents move based on sensor readings of a trail map. Diffuse and decay the trail map each frame. React to audio by changing sensor angle or trail deposit amount."
        },
        "l_system_plant": {
            "name": "L-System 植物生長",
            "name_en": "L-System Plant",
            "category": "bio",
            "category_name": "生物與化學模擬",
            "description": "字串替換規則生成的碎形植物",
            "equations": "recursive string rewriting rules (e.g., F->FF+[+F-F-F]-[-F+F+F])",
            "prompt_hint": "Grow the string sequentially. Use translate() and rotate() for rendering. Make branch angle jitter based on audio high/mid."
        },
        "game_of_life": {
            "name": "元胞自動機",
            "name_en": "Conway's Game of Life",
            "category": "bio",
            "category_name": "生物與化學模擬",
            "description": "經典的生命遊戲網格",
            "equations": "birth/survival rules (B3/S23)",
            "prompt_hint": "Use a 2D array grid. Map audio energy to randomize/spawn new living cells in symmetrical patterns."
        },

        # Fluid & Fields (fluid) - 4
        "noise_flow_field": {
            "name": "Simplex Noise 流場",
            "name_en": "Simplex Noise Flow Field",
            "category": "fluid",
            "category_name": "流體與場域",
            "description": "由噪聲驅動的無數粒子運動",
            "equations": "angle = noise(x*s, y*s, z*s) * TWO_PI * multiplier",
            "prompt_hint": "Emit thousands of particles. Their velocity vector is driven by noise(). Do not clear the background completely (use a low opacity rect) to create trails. React to audio mid for noise time progression speed."
        },
        "vortex_particle": {
            "name": "渦流粒子系統",
            "name_en": "Vortex Particle System",
            "category": "fluid",
            "category_name": "流體與場域",
            "description": "多個旋渦力場互動下的粒子軌跡",
            "equations": "Gaussian radial velocity vortices",
            "prompt_hint": "Define a few wandering vortex centers. Particles are pulled into orbit around them. Map vortex strength to audio bass."
        },
        "curl_noise": {
            "name": "Curl Noise 場",
            "name_en": "Curl Noise",
            "category": "fluid",
            "category_name": "流體與場域",
            "description": "無散度 (Divergence-free) 擬真流體流動",
            "equations": "curl of 3D noise for divergence-free flow",
            "prompt_hint": "Calculate the curl of a simplex noise field to get velocity. Yields very fluid-like swirls. Make line colors shift based on audio mid."
        },
        "fluid_solver": {
            "name": "流體模擬器",
            "name_en": "Fluid Solver",
            "category": "fluid",
            "category_name": "流體與場域",
            "description": "簡化版 Navier-Stokes 網格流體",
            "equations": "Navier-Stokes simplified (advection, diffusion, pressure)",
            "prompt_hint": "Implement a simplified grid-based fluid solver (density & velocity grids). Inject dye and velocity based on audio energies."
        },

        # Geometry & Fractals (geometry) - 6
        "voronoi_tessellation": {
            "name": "Voronoi 鑲嵌",
            "name_en": "Voronoi Tessellation",
            "category": "geometry",
            "category_name": "幾何與碎形",
            "description": "最近鄰網格分割算法",
            "equations": "nearest-neighbor cell partitioning based on seed points",
            "prompt_hint": "Animate seed points. Compute distances for pixels, or use geometric approaches. Map cell colors to audio."
        },
        "mandelbrot_julia": {
            "name": "Mandelbrot/Julia 碎形",
            "name_en": "Mandelbrot & Julia Sets",
            "category": "geometry",
            "category_name": "幾何與碎形",
            "description": "複數平面的無限迭代碎形",
            "equations": "z = z² + c iteration",
            "prompt_hint": "Render the Julia set using pixel shaders or optimized array processing. Make the complex parameter 'c' oscillate in sync with audio bass."
        },
        "sierpinski_triangle": {
            "name": "Sierpinski 三角碎形",
            "name_en": "Sierpinski Triangle",
            "category": "geometry",
            "category_name": "幾何與碎形",
            "description": "遞迴三角切分幾何",
            "equations": "recursive triangle subdivision or chaos game",
            "prompt_hint": "Use the chaos game method for particle rendering, or draw it recursively. Modulate the depth or rotation with audio."
        },
        "penrose_tiling": {
            "name": "Penrose 鋪磚",
            "name_en": "Penrose Tiling",
            "category": "geometry",
            "category_name": "幾何與碎形",
            "description": "非週期性的風箏與飛鏢鑲嵌",
            "equations": "aperiodic tiling with kite and dart (substitution rules)",
            "prompt_hint": "Implement L-system or substitution rules to generate Penrose tiles. Make tile colors throb with audio energy."
        },
        "phyllotaxis_spiral": {
            "name": "葉序螺旋",
            "name_en": "Phyllotaxis Spiral",
            "category": "geometry",
            "category_name": "幾何與碎形",
            "description": "黃金比例自然螺旋排列",
            "equations": "r = c * sqrt(n), θ = n * 137.508°",
            "prompt_hint": "Draw points expanding outward using the golden angle. Modulate 'c' and the radius with audio bass/mid."
        },
        "gyroid_surface": {
            "name": "Gyroid 三週期極小曲面",
            "name_en": "Gyroid Surface",
            "category": "geometry",
            "category_name": "幾何與碎形",
            "description": "自然界中的連通網狀結構",
            "equations": "sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x) = 0",
            "prompt_hint": "Raymarch a Gyroid SDF or draw pseudo-3D contour lines of the function. Make the phase shift with audio."
        },

        # Optics & Waves (optics) - 4
        "wave_interference": {
            "name": "波干涉圖案",
            "name_en": "Wave Interference",
            "category": "optics",
            "category_name": "光學與波場",
            "description": "多源同心波的疊加干涉",
            "equations": "sum of sin(dist - time * speed) for multiple sources",
            "prompt_hint": "Place several wave sources. Calculate the superposition of sine waves per pixel or using contour lines. React wave frequency to audio."
        },
        "chladni_plate": {
            "name": "Chladni 振動板",
            "name_en": "Chladni Plate",
            "category": "optics",
            "category_name": "光學與波場",
            "description": "金屬板共振沙粒圖案",
            "equations": "cos(n*pi*x/L)*cos(m*pi*y/L) - cos(m*pi*x/L)*cos(n*pi*y/L) = 0",
            "prompt_hint": "Simulate particles settling in the nodes of the Chladni 2D equation. Change n and m parameters smoothly based on audio peaks."
        },
        "moire_pattern": {
            "name": "莫爾條紋",
            "name_en": "Moiré Pattern",
            "category": "optics",
            "category_name": "光學與波場",
            "description": "週期性格線疊加產生的空間錯覺",
            "equations": "overlapping periodic patterns (grids, rings) with slight rotation/scale",
            "prompt_hint": "Draw two sets of dense concentric rings or lines. Rotate or translate one set based on audio energy to create dynamic Moiré effects."
        },
        "caustic_refraction": {
            "name": "焦散折射",
            "name_en": "Caustic Refraction",
            "category": "optics",
            "category_name": "光學與波場",
            "description": "光線透過波浪表面的聚集效應",
            "equations": "light concentration through curved surfaces (Voronoi-like)",
            "prompt_hint": "Create smooth, moving Voronoi-like web structures simulating underwater caustics. Use blendMode(ADD) and map intensity to audio high."
        }
    }

    SYSTEM_PROMPT = """You are a world-class computational artist and p5.js expert.
Your task is to generate ONLY valid ES6 p5.js code based on the provided prompt and mathematical models.
Follow these strict rules:
1. Generate ONLY valid ES6 p5.js code using the setup() and draw() pattern.
2. In setup(), you MUST use `createCanvas(windowWidth, windowHeight)` for full-screen rendering.
3. Include this function exactly: `function windowResized() { resizeCanvas(windowWidth, windowHeight); }`
4. Define audio-reactive global variables at the top of the file exactly like this:
   `let audioEnergy = {bass: 0, mid: 0, high: 0, sub_bass: 0};`
5. In draw(), read the audio data safely from the global window object if available:
   `if (window.__audioData) { audioEnergy = window.__audioData; }`
6. Use `background()` at the start of draw() to prevent infinite trails, unless trailing effects are explicitly desired.
7. NO DOM manipulation whatsoever (no createP, createDiv, createButton, createSlider). Do not use HTML.
8. NO external library dependencies (no Three.js, no Tone.js, no ml5). Rely entirely on standard p5.js built-ins.
9. Use HSB or HSL color mode for dynamic, smooth color transitions (e.g., `colorMode(HSB, 360, 100, 100)`).
10. The visual must look impressive at 4K resolution (3840x2160). Make numerical constants and stroke weights relative to `width` and `height` rather than hardcoding absolute pixel values.
11. Output ONLY pure JavaScript code. Do not wrap in markdown fences. Do not provide explanations or comments outside the code."""

    def __init__(self, api_url=None, model_name=None):
        self.config = load_ai_config()
        self.api_url = api_url or self.config.get("ollama", {}).get("api_url", "http://localhost:11434/api/generate")
        self.tags_url = self.api_url.rsplit('/', 1)[0] + "/tags"
        self.model_name = model_name or self.config.get("ollama", {}).get("model_name", "llama3")

    def reload_config(self):
        """ 重新載入 AI 配置 """
        self.config = load_ai_config()

    def get_active_provider(self) -> str:
        """ 取得當前生效的 AI 供應商 ('kimi', 'deepseek_cloud', 'ollama', 'openai') """
        self.reload_config()
        return self.config.get("provider", "kimi")

    def call_llm(self, prompt: str, system_prompt: str = None, json_mode: bool = False, timeout: int = 120) -> str:
        """
        統一多供應商 LLM 調用入口：
        - Kimi / Moonshot AI (雲端大師級，p5.js 最優選)
        - DeepSeek Cloud API
        - 本地 Ollama (llama3 / deepseek-r1 等)
        - OpenAI 自訂端點
        """
        self.reload_config()
        provider = self.config.get("provider", "kimi")

        # 1. 🌙 Kimi (Moonshot API)
        if provider == "kimi":
            kimi_cfg = self.config.get("kimi", {})
            api_key = kimi_cfg.get("api_key", "").strip()
            if api_key:
                api_url = kimi_cfg.get("api_url", "https://api.moonshot.cn/v1/chat/completions")
                model = kimi_cfg.get("model_name", "moonshot-v1-8k")
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}

                logger.info(f"🌙 正在透過 Kimi (Moonshot API - {model}) 生成視覺代碼...")
                res = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise RuntimeError(f"Kimi API 回傳異常 ({res.status_code}): {res.text}")
            else:
                logger.warning("Kimi API Key 未設定，自動切換至本機 Ollama 離線生成...")

        # 2. 🔮 DeepSeek Cloud API
        elif provider == "deepseek_cloud":
            ds_cfg = self.config.get("deepseek_cloud", {})
            api_key = ds_cfg.get("api_key", "").strip()
            if api_key:
                api_url = ds_cfg.get("api_url", "https://api.deepseek.com/chat/completions")
                model = ds_cfg.get("model_name", "deepseek-chat")
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}

                logger.info(f"🔮 正在透過 DeepSeek Cloud ({model}) 生成代碼...")
                res = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise RuntimeError(f"DeepSeek Cloud API 回傳異常 ({res.status_code}): {res.text}")
            else:
                logger.warning("DeepSeek Cloud API Key 未設定，自動切換至本機 Ollama 離線生成...")

        # 3. 🌐 OpenAI / Compatible
        elif provider == "openai":
            oa_cfg = self.config.get("openai", {})
            api_key = oa_cfg.get("api_key", "").strip()
            if api_key:
                api_url = oa_cfg.get("api_url", "https://api.openai.com/v1/chat/completions")
                model = oa_cfg.get("model_name", "gpt-4o")
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}

                res = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise RuntimeError(f"OpenAI API 回傳異常 ({res.status_code}): {res.text}")
            else:
                logger.warning("OpenAI API Key 未設定，自動切換至本機 Ollama 離線生成...")

        # 4. 🚀 本地 Ollama (預設 / 離線 Fallback)
        self.ensure_ollama_running()
        ollama_cfg = self.config.get("ollama", {})
        ollama_model = ollama_cfg.get("model_name") or self.model_name
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        payload = {
            "model": ollama_model,
            "prompt": full_prompt,
            "stream": False
        }
        if json_mode:
            payload["format"] = "json"

        logger.info(f"🚀 正在透過本地 Ollama ({ollama_model}) 生成代碼...")
        res = requests.post(self.api_url, json=payload, timeout=timeout)
        if res.status_code == 200:
            return res.json().get("response", "")
        else:
            raise RuntimeError(f"Ollama 本地生成失敗 ({res.status_code}): {res.text}")

    def ensure_ollama_running(self) -> bool:
        """ 檢查並自動於背景啟動 Ollama 本地服務 """
        try:
            res = requests.get(self.tags_url, timeout=1.5)
            if res.status_code == 200:
                return True
        except Exception:
            pass

        # 搜尋 ollama 可執行檔
        ollama_bin = shutil.which("ollama") or ("/usr/local/bin/ollama" if os.path.exists("/usr/local/bin/ollama") else None)
        if not ollama_bin:
            logger.info("Ollama binary not found on local machine.")
            return False

        try:
            logger.info(f"Auto-spawning background Ollama service via {ollama_bin}...")
            subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(5):
                time.sleep(0.5)
                try:
                    res = requests.get(self.tags_url, timeout=1.0)
                    if res.status_code == 200:
                        logger.info("Ollama service successfully auto-started in background.")
                        return True
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Failed to auto-spawn Ollama service: {e}")
        return False

    def generate_visual_module(self, user_prompt: str, math_model: str = None, style_hints: list = None, song_telemetry: dict = None) -> dict:
        """ 產生原創視覺模組代碼 (支援歌曲音訊動態上下文注入) """
        prompt_text = self._build_prompt(user_prompt, math_model, style_hints, song_telemetry)
        active_provider = self.get_active_provider()
        
        try:
            result_text = self.call_llm(prompt=prompt_text, system_prompt=self.SYSTEM_PROMPT, timeout=120)
            code = self._extract_code(result_text)
            
            if not code.strip():
                raise ValueError("Generated code is empty")
            
            tags = self.suggest_director_tags(code)
            suggested_name = self._suggest_name(user_prompt, math_model)
            fingerprint = self._generate_fingerprint(code)
            
            # 構建強化的 Visual DNA 結構
            model_info = self.MATH_MODELS.get(math_model, {}) if math_model else {}
            visual_dna = {
                "geometry": {
                    "type": model_info.get("category", "freeform"),
                    "topology": model_info.get("name_en", "Procedural")
                },
                "audio_binding": {
                    "sub_bass": { "target": "scale_and_expansion", "curve": "exponential" },
                    "bass": { "target": "particle_density", "curve": "sigmoid" },
                    "mid": { "target": "hue_rotation", "curve": "linear" },
                    "high": { "target": "glow_sparkle", "curve": "step" }
                }
            }
            
            provenance = {
                "origin": "ai_incubator",
                "generation_method": f"prompt_generated ({active_provider})",
                "provider": active_provider,
                "base_algorithm": math_model or "freeform",
                "user_prompt": user_prompt,
                "target_bpm": song_telemetry.get("bpm") if song_telemetry else None,
                "fingerprint_hash": fingerprint
            }
            
            return {
                "code": code,
                "suggested_name": suggested_name,
                "suggested_tags": tags,
                "visual_dna": visual_dna,
                "provenance": provenance
            }
        except Exception as e:
            logger.error(f"Failed to generate visual module via {active_provider}: {e}")
            
        fallback = self.get_fallback_code()
        fallback_fp = self._generate_fingerprint(fallback)
        return {
            "code": fallback,
            "suggested_name": "fallback_particle_system",
            "suggested_tags": {
                "section_fitness": {"intro": 0.8, "verse": 0.7, "chorus": 0.9, "buildup": 0.8, "outro": 0.6},
                "energy_level": 0.7,
                "style_tags": ["particles", "audio-reactive", "fallback"],
                "photosensitivity_risk": False
            },
            "visual_dna": {
                "geometry": { "type": "fluid", "topology": "Audio Particle System" },
                "audio_binding": {
                    "sub_bass": { "target": "radius", "curve": "linear" },
                    "bass": { "target": "expansion", "curve": "exponential" },
                    "mid": { "target": "hue", "curve": "linear" },
                    "high": { "target": "alpha", "curve": "step" }
                }
            },
            "provenance": {
                "origin": "ai_incubator",
                "generation_method": "fallback_template",
                "base_algorithm": "particle_system",
                "user_prompt": user_prompt,
                "fingerprint_hash": fallback_fp
            }
        }

    def _build_prompt(self, user_prompt: str, math_model: str, style_hints: list, song_telemetry: dict = None) -> str:
        prompt_parts = [self.SYSTEM_PROMPT]
        
        if math_model and math_model in self.MATH_MODELS:
            m = self.MATH_MODELS[math_model]
            prompt_parts.append(f"\n--- MATHEMATICAL MODEL ---\nYou must base your code on this model: {m['name_en']} ({m['name']})")
            prompt_parts.append(f"Description: {m['description']}")
            prompt_parts.append(f"Equations/Algorithm: {m['equations']}")
            prompt_parts.append(f"Implementation Hint: {m['prompt_hint']}")
            
        if style_hints and isinstance(style_hints, list):
            prompt_parts.append(f"\n--- STYLE HINTS ---\nPlease incorporate these stylistic elements: {', '.join(style_hints)}")
            
        if song_telemetry and isinstance(song_telemetry, dict):
            prompt_parts.append(f"\n--- TARGET SONG ACOUSTIC TELEMETRY ---")
            if "title" in song_telemetry:
                prompt_parts.append(f"Track Title: {song_telemetry['title']}")
            if "bpm" in song_telemetry:
                prompt_parts.append(f"BPM: {song_telemetry['bpm']} (Tailor motion speed and oscillations to match this tempo)")
            if "genre" in song_telemetry:
                prompt_parts.append(f"Genre: {song_telemetry['genre']}")
            if "color_mood" in song_telemetry:
                prompt_parts.append(f"Suggested Color Palette/Mood: {song_telemetry['color_mood']}")
            if "energy_profile" in song_telemetry:
                prompt_parts.append(f"Energy Profile: {song_telemetry['energy_profile']}")

        prompt_parts.append(f"\n--- USER PROMPT ---\n{user_prompt}")
        prompt_parts.append("\nReturn ONLY the p5.js code now:")
        
        return "\n".join(prompt_parts)

    def _extract_code(self, response_text: str) -> str:
        code = response_text.strip()
        
        # Strip DeepSeek-R1 <think>...</think> reasoning blocks
        code = re.sub(r'<think>[\s\S]*?<\/think>', '', code, flags=re.IGNORECASE).strip()
        
        # Regex to strip markdown fences (searches anywhere in text, not just anchored to start)
        fence_pattern = re.compile(r"```(?:javascript|js)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
        match = fence_pattern.search(code)
        if match:
            code = match.group(1).strip()
        else:
            # Maybe the whole thing is just JS, but let's remove dangling backticks if present
            code = code.replace("```javascript", "").replace("```js", "").replace("```", "").strip()
            
        # Optional: remove HTML wrapper if present
        if code.startswith("<html>") or code.startswith("<script>"):
            code = re.sub(r"<\/?(?:html|body|script|div)[^>]*>", "", code, flags=re.IGNORECASE).strip()
            
        return code

    def _generate_fingerprint(self, code: str) -> str:
        return f"sha256:{hashlib.sha256(code.encode('utf-8')).hexdigest()[:16]}"

    def _suggest_name(self, user_prompt: str, math_model: str) -> str:
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        
        if math_model and math_model in self.MATH_MODELS:
            base = math_model
        else:
            # take first few words of prompt
            words = re.findall(r'\w+', user_prompt.lower())
            base = "_".join(words[:3]) if words else "visual"
            
        return f"{base}_{timestamp}"

    def refine_code(self, current_code: str, user_instruction: str) -> str:
        prompt = f"""You are a p5.js expert.
Here is the existing p5.js code:
```javascript
{current_code}
```
Modify it according to the following instruction:
{user_instruction}
Return ONLY the modified p5.js code, no markdown fences, no explanations."""
        
        try:
            result_text = self.call_llm(prompt=prompt, system_prompt="You are a p5.js expert.", timeout=120)
            return self._extract_code(result_text)
        except Exception as e:
            logger.error(f"Failed to refine code: {e}")
        
        return current_code

    def cross_breed_modules(self, code_a: str, name_a: str, code_b: str, name_b: str, user_directive: str = None) -> dict:
        """ 視覺基因雜交：提取母體 A 的幾何/動力邏輯與母體 B 的音畫/色彩特徵，融合生成子模組 """
        prompt = f"""You are a computational genetics artist and p5.js master.
Perform a Genetic Cross-Breeding (Hybridization) of two p5.js visual modules:

--- PARENT A ({name_a}) ---
```javascript
{code_a[:2500]}
```

--- PARENT B ({name_b}) ---
```javascript
{code_b[:2500]}
```

INSTRUCTIONS FOR HYBRIDIZATION:
1. Extract Parent A's primary geometric structures, particle physics, or mathematical attractors.
2. Combine them with Parent B's audio-reactivity dynamics, color palette, or motion curves.
3. Produce a BRAND NEW, 100% functional p5.js script combining both genetic traits.
{f"User Directive: {user_directive}" if user_directive else ""}

Rules:
- Must use `createCanvas(windowWidth, windowHeight)`
- Must use `audioEnergy` object for audio reactivity
- NO DOM manipulation, NO external libraries
- Return ONLY the pure JavaScript code, no markdown fences."""

        child_name = f"hybrid_{name_a[:6]}_{name_b[:6]}_{int(time.time()) % 10000}"
        active_provider = self.get_active_provider()
        
        try:
            result_text = self.call_llm(prompt=prompt, system_prompt="You are a computational genetics artist and p5.js master.", timeout=120)
            code = self._extract_code(result_text)
            if code.strip():
                tags = self.suggest_director_tags(code)
                fp = self._generate_fingerprint(code)
                return {
                    "code": code,
                    "suggested_name": child_name,
                    "suggested_tags": tags,
                    "visual_dna": {
                        "geometry": { "type": "hybrid", "topology": f"{name_a} + {name_b}" },
                        "audio_binding": {
                            "sub_bass": { "target": "scale_expansion", "curve": "exponential" },
                            "bass": { "target": "particle_burst", "curve": "sigmoid" },
                            "mid": { "target": "color_drift", "curve": "linear" }
                        }
                    },
                    "provenance": {
                        "origin": "ai_incubator",
                        "generation_method": f"cross_breeding ({active_provider})",
                        "provider": active_provider,
                        "parent_modules": [name_a, name_b],
                        "user_directive": user_directive,
                        "fingerprint_hash": fp
                    }
                }
        except Exception as e:
            logger.error(f"Failed to cross-breed modules via {active_provider}: {e}")
            
        fallback = self.get_fallback_code()
        return {
            "code": fallback,
            "suggested_name": child_name,
            "suggested_tags": {"section_fitness": {"chorus": 0.9}, "energy_level": 0.8, "style_tags": ["hybrid", "fallback"]},
            "visual_dna": {"geometry": {"type": "hybrid", "topology": "Fallback Hybrid"}},
            "provenance": {
                "origin": "ai_incubator",
                "generation_method": "cross_breeding_fallback",
                "parent_modules": [name_a, name_b],
                "fingerprint_hash": self._generate_fingerprint(fallback)
            }
        }

    def mutate_visual_styles(self, base_code: str) -> list:
        """ 一鍵產生 4 種視覺變異風格 (Cyberpunk, Minimalist, Fluid, Glitch) """
        style_presets = [
            ("Cyberpunk Neon", "Modify color palette to vibrant neon pink/cyan (#ff0055, #00f0ff), add high contrast pulses on bass."),
            ("Monochrome Minimalist", "Modify color palette to elegant grayscale with high-contrast sharp geometric lines."),
            ("Organic Fluid Pastel", "Modify color palette to soft pastel tones (mint, lavender, peach) with smooth Perlin noise warping."),
            ("Heavy Glitch Industrial", "Add high-frequency spatial jitter, RGB-split offset simulation, and intense beat response.")
        ]
        
        mutations = []
        for style_name, instruction in style_presets:
            mutated_code = self.refine_code(base_code, instruction)
            mutations.append({
                "style_name": style_name,
                "code": mutated_code,
                "fingerprint": self._generate_fingerprint(mutated_code)
            })
            
        return mutations

    def suggest_director_tags(self, code: str) -> dict:
        prompt = f"""Analyze the following p5.js code and return a JSON object evaluating its suitability for different music video sections.
Code:
```javascript
{code[:2000]} // truncated for brevity
```
You MUST return ONLY a JSON object with this exact structure:
{{
  "section_fitness": {{"intro": 0.5, "verse": 0.5, "chorus": 0.5, "buildup": 0.5, "outro": 0.5}},
  "energy_level": 0.5,
  "style_tags": ["tag1", "tag2", "tag3"],
  "photosensitivity_risk": false
}}"""
        
        default_tags = {
            "section_fitness": {"intro": 0.5, "verse": 0.6, "chorus": 0.8, "buildup": 0.7, "outro": 0.4},
            "energy_level": 0.6,
            "style_tags": ["generative", "p5js"],
            "photosensitivity_risk": False
        }
        
        try:
            result_text = self.call_llm(prompt=prompt, json_mode=True, timeout=60)
            result_text = re.sub(r'<think>[\s\S]*?<\/think>', '', result_text, flags=re.IGNORECASE).strip()
            # If wrapped in ```json ... ```, extract it
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_text)
            if json_match:
                result_text = json_match.group(1).strip()
            data = json.loads(result_text)
            return data
        except Exception as e:
            logger.error(f"Failed to parse tags: {e}")
            
        return default_tags

    def get_model_categories(self) -> dict:
        categories = {}
        for key, model in self.MATH_MODELS.items():
            cat = model["category"]
            if cat not in categories:
                categories[cat] = {
                    "name": model["category_name"],
                    "models": []
                }
            categories[cat]["models"].append({
                "id": key,
                "name": model["name"],
                "name_en": model["name_en"],
                "description": model["description"]
            })
        return categories

    def get_fallback_code(self) -> str:
        return """let audioEnergy = {bass: 0, mid: 0, high: 0, sub_bass: 0};
let particles = [];

function setup() {
  createCanvas(windowWidth, windowHeight);
  colorMode(HSB, 360, 100, 100, 1);
  background(0);
  for (let i = 0; i < 200; i++) {
    particles.push(new Particle());
  }
}

function draw() {
  if (window.__audioData) {
    audioEnergy = window.__audioData;
  }
  
  // Create fading trails
  noStroke();
  fill(0, 0, 0, 0.1);
  rect(0, 0, width, height);
  
  translate(width / 2, height / 2);
  
  for (let p of particles) {
    p.update();
    p.display();
  }
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
}

class Particle {
  constructor() {
    this.angle = random(TWO_PI);
    this.radius = random(10, min(width, height) / 2);
    this.speed = random(0.01, 0.05);
    this.size = random(2, 5);
  }
  
  update() {
    // Rotate based on high frequencies
    this.angle += this.speed + (audioEnergy.high * 0.05);
    
    // Scale radius with bass
    let currentRadius = this.radius + (audioEnergy.bass * 200);
    this.x = cos(this.angle) * currentRadius;
    this.y = sin(this.angle) * currentRadius;
  }
  
  display() {
    // Color mapped to mid frequencies
    let hue = (frameCount + audioEnergy.mid * 100) % 360;
    
    // Sparkle size with highs
    let currentSize = this.size + (audioEnergy.high * 10);
    
    fill(hue, 80, 100, 0.8);
    noStroke();
    ellipse(this.x, this.y, currentSize);
  }
}
"""
