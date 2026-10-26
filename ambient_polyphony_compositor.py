"""
SENTINEL-CHRONOS: Tri-Layer Visual Polyphony Compositor for Ambient / Drone Systems
依據《AI 導演系統介入 Ambient 視覺模組挑選與變化操控架構計劃書》實作：

三層視覺複調合成器 (Tri-Layer Visual Polyphony Compositor):
- Layer 1: 全域體積光場底層 (Turrell Ganzfeld 32-D Atmospheric Light Field)
- Layer 2: 空間物質流體中層 (Fluid / Topological Wave Manifold)
- Layer 3: 懸浮星塵粒子頂層 (Ethereal Particulate / Stardust)

支援：
1. 高動態範圍多層混合模式 (Soft Screen, Tonemapped Additive Glow, Luma Key)
2. 長鏡頭同胚慢速融鏡 (Homeomorphic Deep Cross-Dissolve, 6s~10s)
3. 4K 高性能 NumPy / OpenCV 影格加速合成
4. WebGL / Canvas 多層複合渲染 HTML 架構輸出
"""

import math
import logging
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2

from ambient_ai_director_bridge import VisualPolyphonyTrio

logger = logging.getLogger("VisualStudio.AmbientPolyphonyCompositor")


class AmbientPolyphonyCompositor:
    """
    Ambient 三層視覺複調合成器
    專為 4K 慢速環境冥想視覺打造的低刺激、高和諧度合成引擎
    """

    def __init__(self, default_weights: Tuple[float, float, float] = (1.0, 0.65, 0.45)):
        self.default_weights = default_weights

    def composite_frame(
        self,
        layer1_atmospheric: np.ndarray,
        layer2_fluid: Optional[np.ndarray] = None,
        layer3_particulate: Optional[np.ndarray] = None,
        weights: Optional[Tuple[float, float, float]] = None,
        blend_mode: str = "soft_screen",
        exposure: float = 1.0
    ) -> np.ndarray:
        """
        合成三層視覺複調影像 (4K / 1080p BGR 或 BGRA NumPy 矩陣)
        :param layer1_atmospheric: 光場底層 (uint8, shape [H, W, 3] or [H, W, 4])
        :param layer2_fluid: 流體/拓撲中層 (可為 None)
        :param layer3_particulate: 星塵粒子頂層 (可為 None)
        :param weights: 三層各自的透明度/權重 (w1, w2, w3)
        :param blend_mode: "soft_screen", "additive_glow", 或 "luma_key"
        :param exposure: 曝光補償係數 (0.5 ~ 2.0)
        :return: 合成後的 uint8 影格
        """
        w1, w2, w3 = weights if weights is not None else self.default_weights

        # 確保 float32 正規化至 0.0 ~ 1.0 區間進行精密光學計算
        h, w = layer1_atmospheric.shape[:2]
        
        # 轉換為 3 通道 float32
        base = self._ensure_bgr_float(layer1_atmospheric)
        if w1 != 1.0:
            base *= float(w1)

        result = base

        # 1. 疊加 Layer 2 (流體物質)
        if layer2_fluid is not None:
            l2 = self._ensure_bgr_float(layer2_fluid, target_shape=(h, w))
            result = self._blend_layers(result, l2, weight=w2, mode=blend_mode)

        # 2. 疊加 Layer 3 (星塵微粒)
        if layer3_particulate is not None:
            l3 = self._ensure_bgr_float(layer3_particulate, target_shape=(h, w))
            result = self._blend_layers(result, l3, weight=w3, mode=blend_mode)

        # 3. 曝光與色調映射 (Reinhard Tonemapping 避免高光死白硬邊)
        if exposure != 1.0:
            result = result * exposure
        
        # Reinhard 色調映射: C_mapped = C / (1 + C)
        result = result / (1.0 + result * 0.25)

        # 輸出 8-bit BGR
        final_uint8 = np.clip(result * 255.0, 0, 255).astype(np.uint8)
        return final_uint8

    def cross_dissolve(
        self,
        frame_a: np.ndarray,
        frame_b: np.ndarray,
        progress: float,
        halation_boost: float = 0.20
    ) -> np.ndarray:
        """
        同胚慢速融鏡 (Homeomorphic Cross-Dissolve):
        透過 Smoothstep 演算法與中間過渡光暈 (Halation) 達成如呼吸般的有機溶解
        :param frame_a: 前一分鏡畫面 (uint8)
        :param frame_b: 後一分鏡畫面 (uint8)
        :param progress: 溶解進度 (0.0 ~ 1.0)
        :param halation_boost: 融鏡中段的光學光暈強度
        """
        p = float(np.clip(progress, 0.0, 1.0))
        # 3 次方 Hermite Smoothstep: 3p^2 - 2p^3
        smooth_p = p * p * (3.0 - 2.0 * p)

        fa = frame_a.astype(np.float32)
        fb = frame_b.astype(np.float32)

        if fa.shape != fb.shape:
            fb = cv2.resize(fb, (fa.shape[1], fa.shape[0]), interpolation=cv2.INTER_LINEAR)

        # 線性插值
        blended = fa * (1.0 - smooth_p) + fb * smooth_p

        # 在中段 (p ≈ 0.5) 注入夢境般的柯西光暈 (Halation Bloom)
        if halation_boost > 0.0:
            mid_factor = math.sin(p * math.pi) * halation_boost
            if mid_factor > 0.01:
                # 軟模糊光暈
                blur = cv2.GaussianBlur(blended, (0, 0), sigmaX=15.0, sigmaY=15.0)
                blended = blended + blur * mid_factor

        return np.clip(blended, 0.0, 255.0).astype(np.uint8)

    def _ensure_bgr_float(
        self,
        img: np.ndarray,
        target_shape: Optional[Tuple[int, int]] = None
    ) -> np.ndarray:
        """確保影格為 [0.0, 1.0] float32 且為 BGR 3 通道"""
        if img.dtype == np.uint8:
            f = img.astype(np.float32) / 255.0
        else:
            f = img.astype(np.float32)

        # 若有 Alpha 通道，先進行預乘
        if len(f.shape) == 3 and f.shape[2] == 4:
            alpha = f[:, :, 3:4]
            f = f[:, :, :3] * alpha

        if target_shape is not None:
            target_h, target_w = target_shape
            if f.shape[0] != target_h or f.shape[1] != target_w:
                f = cv2.resize(f, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        return f

    def _blend_layers(
        self,
        base: np.ndarray,
        layer: np.ndarray,
        weight: float,
        mode: str = "soft_screen"
    ) -> np.ndarray:
        """
        執行單一圖層光學混合
        """
        w = max(0.0, min(1.0, weight))
        if w <= 0.001:
            return base

        l_weighted = layer * w

        if mode == "soft_screen":
            # 軟濾色: 1 - (1 - A) * (1 - B * w)
            return 1.0 - (1.0 - base) * (1.0 - l_weighted)
        elif mode == "additive_glow":
            # 加色疊加
            return base + l_weighted
        elif mode == "luma_key":
            # 依據圖層自身亮度進行遮罩混合
            luma = np.mean(l_weighted, axis=2, keepdims=True)
            return base * (1.0 - luma) + l_weighted
        else:
            # 預設為線性 Alpha 混合
            return base * (1.0 - w) + layer * w

    def generate_polyphony_canvas_html(
        self,
        trio: VisualPolyphonyTrio,
        vertex_shader_code: str,
        fragment_shader_code: str,
        uniforms_32d_dict: Dict[str, Any]
    ) -> str:
        """
        生成具備三層視覺複調能力之 WebGL2 / Canvas 整合 HTML 模板
        Layer 1: 體積光場 WebGL2 片元著色器
        Layer 2: 綠色物質流體圖層 (Canvas 2D / WebGL 疊加)
        Layer 3: 懸浮星塵微粒圖層 (Canvas 2D 動態粒子)
        """
        import json
        uniforms_json = json.dumps(uniforms_32d_dict)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Ambient Tri-Layer Visual Polyphony Canvas</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; }}
        body, html {{ width: 100%; height: 100%; background: #000; }}
        #container {{ position: relative; width: 100%; height: 100%; }}
        canvas {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; }}
        #layer1_webgl {{ z-index: 1; }}
        #layer2_fluid {{ z-index: 2; mix-blend-mode: screen; opacity: {trio.blend_weights[1]}; pointer-events: none; }}
        #layer3_particles {{ z-index: 3; mix-blend-mode: screen; opacity: {trio.blend_weights[2]}; pointer-events: none; }}
    </style>
</head>
<body>
    <div id="container">
        <canvas id="layer1_webgl"></canvas>
        <canvas id="layer2_fluid"></canvas>
        <canvas id="layer3_particles"></canvas>
    </div>

    <script id="vs" type="x-shader/x-vertex">
        {vertex_shader_code}
    </script>
    <script id="fs" type="x-shader/x-fragment">
        {fragment_shader_code}
    </script>

    <script>
        // 1. 初始化 Layer 1 (WebGL2 32-D Atmospheric Light Field)
        const c1 = document.getElementById("layer1_webgl");
        const gl = c1.getContext("webgl2", {{ alpha: false, depth: false, antialias: true, powerPreference: "high-performance" }});
        
        function compileShader(gl, type, source) {{
            const s = gl.createShader(type);
            gl.shaderSource(s, source);
            gl.compileShader(s);
            if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {{
                console.error("Shader Compile Error:", gl.getShaderInfoLog(s));
                return null;
            }}
            return s;
        }}

        const vs = compileShader(gl, gl.VERTEX_SHADER, document.getElementById("vs").text.trim());
        const fs = compileShader(gl, gl.FRAGMENT_SHADER, document.getElementById("fs").text.trim());
        const prog = gl.createProgram();
        gl.attachShader(prog, vs);
        gl.attachShader(prog, fs);
        gl.linkProgram(prog);

        const posBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
            -1, -1,  1, -1, -1,  1,
            -1,  1,  1, -1,  1,  1
        ]), gl.STATIC_DRAW);

        const aPos = gl.getAttribLocation(prog, "position");
        gl.enableVertexAttribArray(aPos);
        gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

        window.ambientParams = {uniforms_json};
        window.uLocations = {{}};
        const uniformNames = [
            "u_resolution", "u_time", "u_breathingRate", "u_translucency", "u_luminanceGravity", "u_timeDilation",
            "u_domainWarpAmp", "u_domainWarpFreq", "u_warpLacunarity", "u_rayleighScattering", "u_mieScattering",
            "u_anisotropyG", "u_extinctionBeta", "u_cauchyDispersion", "u_wavelengthCenter", "u_spectralBandwidth",
            "u_subBassGravity", "u_lowMidWarmth", "u_airSheen", "u_harmonicPhaseSync", "u_spectralCentroidNorm",
            "u_roughnessVariance", "u_scatteringAlbedo", "u_attenuationDistance", "u_spatialDilation", "u_manifoldFlowRate",
            "u_phaseEntropy", "u_zenithLuminance", "u_horizonDarkening", "u_ditherQuantization", "u_chromaVariance", "u_cameraDriftVelocity"
        ];
        gl.useProgram(prog);
        uniformNames.forEach(name => {{
            window.uLocations[name] = gl.getUniformLocation(prog, name);
        }});
        window.uPaletteLoc = gl.getUniformLocation(prog, "u_palette");

        // 2. 初始化 Layer 2 流體模擬畫布
        const c2 = document.getElementById("layer2_fluid");
        const ctx2 = c2.getContext("2d");

        // 3. 初始化 Layer 3 星塵粒子畫布
        const c3 = document.getElementById("layer3_particles");
        const ctx3 = c3.getContext("2d");
        const particles = [];
        for (let i = 0; i < 90; i++) {{
            particles.push({{
                x: Math.random() * 800,
                y: Math.random() * 450,
                radius: Math.random() * 1.8 + 0.4,
                vx: (Math.random() - 0.5) * 0.15,
                vy: (Math.random() - 0.5) * 0.15,
                alpha: Math.random() * 0.6 + 0.2
            }});
        }}

        function resize() {{
            const w = window.innerWidth;
            const h = window.innerHeight;
            [c1, c2, c3].forEach(c => {{
                if (c.width !== w || c.height !== h) {{
                    c.width = w;
                    c.height = h;
                }}
            }});
            gl.viewport(0, 0, w, h);
        }}
        window.addEventListener("resize", resize);
        resize();

        window.updateAllUniforms = function(data) {{
            Object.assign(window.ambientParams, data);
        }};

        let startTime = performance.now();
        function render(now) {{
            const t = (now - startTime) * 0.001;
            
            // Render Layer 1 (WebGL2 32-D)
            gl.useProgram(prog);
            gl.uniform2f(window.uLocations["u_resolution"], c1.width, c1.height);
            gl.uniform1f(window.uLocations["u_time"], t);
            for (let name of uniformNames) {{
                if (name === "u_resolution" || name === "u_time") continue;
                const loc = window.uLocations[name];
                if (loc !== null && window.ambientParams[name] !== undefined) {{
                    gl.uniform1f(loc, window.ambientParams[name]);
                }}
            }}
            if (window.uPaletteLoc !== null && window.ambientParams.palette) {{
                gl.uniform3fv(window.uPaletteLoc, new Float32Array(window.ambientParams.palette));
            }}
            gl.drawArrays(gl.TRIANGLES, 0, 6);

            // Render Layer 2 (Fluid wave flow)
            ctx2.clearRect(0, 0, c2.width, c2.height);
            const wRate = window.ambientParams.u_manifoldFlowRate || 0.08;
            ctx2.strokeStyle = "rgba(180, 215, 255, 0.25)";
            ctx2.lineWidth = 1.2;
            ctx2.beginPath();
            const cy = c2.height * 0.5;
            for (let x = 0; x < c2.width; x += 6) {{
                const y = cy + Math.sin(x * 0.004 + t * wRate * 2.0) * 45.0 + Math.cos(x * 0.008 - t * 0.1) * 20.0;
                if (x === 0) ctx2.moveTo(x, y);
                else ctx2.lineTo(x, y);
            }}
            ctx2.stroke();

            // Render Layer 3 (Stardust drift)
            ctx3.clearRect(0, 0, c3.width, c3.height);
            ctx3.fillStyle = "rgba(235, 245, 255, 0.6)";
            for (let p of particles) {{
                p.x += p.vx;
                p.y += p.vy;
                if (p.x < 0) p.x = c3.width;
                if (p.x > c3.width) p.x = 0;
                if (p.y < 0) p.y = c3.height;
                if (p.y > c3.height) p.y = 0;

                ctx3.beginPath();
                ctx3.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
                ctx3.fill();
            }}

            requestAnimationFrame(render);
        }}
        requestAnimationFrame(render);
    </script>
</body>
</html>"""
        return html
