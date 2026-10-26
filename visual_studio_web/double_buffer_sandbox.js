/**
 * VisualStudio Pro Double Buffer Sandbox & Protective Runtime
 * A/B 雙緩衝無縫切換沙盒與防崩潰執行環境
 */

(function() {
    window.__sandboxErrors = [];
    window.__fpsCounter = { frames: 0, lastTime: performance.now(), currentFps: 60 };

    // 實時 FPS 檢測
    function calcFps() {
        window.__fpsCounter.frames++;
        const now = performance.now();
        if (now - window.__fpsCounter.lastTime >= 1000) {
            window.__fpsCounter.currentFps = Math.round((window.__fpsCounter.frames * 1000) / (now - window.__fpsCounter.lastTime));
            window.__fpsCounter.frames = 0;
            window.__fpsCounter.lastTime = now;
        }
        requestAnimationFrame(calcFps);
    }
    requestAnimationFrame(calcFps);

    // 黑畫面與純色填充 (Monochrome / Solid Fill / NaN) 熵值看門狗
    let solidColorFrameCount = 0;
    setInterval(function() {
        const canvas = document.querySelector('canvas');
        if (!canvas) return;
        try {
            const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
            if (gl) {
                // WebGL 像素採樣 (9 點多方位取樣防死色)
                const pixels = new Uint8Array(4 * 9);
                const w = canvas.width, h = canvas.height;
                const samplePts = [
                    [Math.floor(w*0.5), Math.floor(h*0.5)],
                    [Math.floor(w*0.2), Math.floor(h*0.2)],
                    [Math.floor(w*0.8), Math.floor(h*0.2)],
                    [Math.floor(w*0.2), Math.floor(h*0.8)],
                    [Math.floor(w*0.8), Math.floor(h*0.8)]
                ];
                let isSolid = true;
                let firstR = -1, firstG = -1, firstB = -1;
                for (let i = 0; i < samplePts.length; i++) {
                    const p = new Uint8Array(4);
                    gl.readPixels(samplePts[i][0], samplePts[i][1], 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, p);
                    if (firstR === -1) {
                        firstR = p[0]; firstG = p[1]; firstB = p[2];
                    } else {
                        // 若各採樣點顏色差異大於閾值，代表具備豐富紋理
                        if (Math.abs(p[0] - firstR) > 12 || Math.abs(p[1] - firstG) > 12 || Math.abs(p[2] - firstB) > 12) {
                            isSolid = false;
                            break;
                        }
                    }
                }
                if (isSolid) {
                    solidColorFrameCount++;
                    if (solidColorFrameCount >= 5) {
                        console.warn("[Anti-Monochrome Guard] 偵測到連續純色畫面/死黑/爆白！觸發自適應動態擾動恢復...");
                        if (window.initParticles) window.initParticles();
                        if (window.__resetCamera) window.__resetCamera();
                        solidColorFrameCount = 0;
                    }
                } else {
                    solidColorFrameCount = 0;
                }
            }
        } catch(e) {
            // 靜默處理上下文保護
        }
    }, 400);

    // 全域異常防護攔截
    window.addEventListener('error', function(event) {
        console.error("[Sandbox Error Caught]", event.message, "at line", event.lineno);
        window.__sandboxErrors.push({ message: event.message, line: event.lineno });
    });

    window.addEventListener('unhandledrejection', function(event) {
        console.error("[Sandbox Promise Rejection]", event.reason);
    });

    // 著色器機架管線 (WebGL 2.0 / Canvas Post-FX Pipeline)
    let glPostCanvas = null;
    let glPostContext = null;
    let glQuadProgram = null;
    let glSceneTexture = null;
    let glPostAnimationId = null;
    let activeShaderList = [];

    function initWebGLPostPipeline() {
        if (glPostCanvas && glPostContext) return true;
        try {
            const viewport = document.getElementById('sandbox-viewport');
            if (!viewport) return false;

            glPostCanvas = document.createElement('canvas');
            glPostCanvas.id = 'webgl-postfx-overlay';
            glPostCanvas.style.position = 'absolute';
            glPostCanvas.style.top = '0';
            glPostCanvas.style.left = '0';
            glPostCanvas.style.width = '100%';
            glPostCanvas.style.height = '100%';
            glPostCanvas.style.pointerEvents = 'none';
            glPostCanvas.style.zIndex = '100';
            glPostCanvas.style.display = 'none';
            viewport.appendChild(glPostCanvas);

            glPostContext = glPostCanvas.getContext('webgl2') || glPostCanvas.getContext('webgl');
            if (!glPostContext) return false;

            const gl = glPostContext;
            const vsSource = `
                attribute vec2 position;
                varying vec2 vUv;
                void main() {
                    vUv = (position + 1.0) * 0.5;
                    gl_Position = vec4(position, 0.0, 1.0);
                }
            `;
            const fsSource = `
                precision highp float;
                varying vec2 vUv;
                uniform sampler2D u_sceneTexture;
                uniform float u_time;
                uniform float u_bass;
                uniform float u_drums;
                uniform float u_godrays;
                uniform float u_chroma;
                uniform float u_glitch;
                uniform vec2 u_resolution;

                float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

                void main() {
                    vec2 uv = vUv;
                    // Glitch displacement
                    if (u_glitch > 0.05) {
                        float slice = step(0.92, sin(uv.y * 40.0 + u_time * 15.0));
                        uv.x += slice * (hash(vec2(u_time, uv.y)) - 0.5) * 0.05 * u_glitch;
                    }

                    // Chromatic aberration (RGB Split)
                    float split = (0.003 + u_drums * 0.008) * u_chroma;
                    vec3 col;
                    col.r = texture2D(u_sceneTexture, uv + vec2(split, 0.0)).r;
                    col.g = texture2D(u_sceneTexture, uv).g;
                    col.b = texture2D(u_sceneTexture, uv - vec2(split, 0.0)).b;

                    // Volumetric Godray radial blur approximation
                    if (u_godrays > 0.05) {
                        vec2 lightPos = vec2(0.5, 0.5);
                        vec2 delta = (uv - lightPos) * 0.015;
                        vec2 cur = uv;
                        vec3 rayCol = vec3(0.0);
                        for (int i = 0; i < 8; i++) {
                            cur -= delta;
                            rayCol += texture2D(u_sceneTexture, cur).rgb * (0.8 / 8.0);
                        }
                        col += rayCol * u_godrays * (1.0 + u_bass * 0.5);
                    }

                    // Analog film grain
                    float grain = (hash(uv + fract(u_time * 1.618)) - 0.5) * 0.04;
                    col += grain;

                    // Vignette
                    col *= smoothstep(0.9, 0.25, length(uv - 0.5) * 0.85);

                    gl_FragColor = vec4(col, 1.0);
                }
            `;

            function createShader(gl, type, source) {
                const s = gl.createShader(type);
                gl.shaderSource(s, source);
                gl.compileShader(s);
                return s;
            }

            const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
            const fs = createShader(gl, gl.FRAGMENT_SHADER, fsSource);
            glQuadProgram = gl.createProgram();
            gl.attachShader(glQuadProgram, vs);
            gl.attachShader(glQuadProgram, fs);
            gl.linkProgram(glQuadProgram);

            const quadBuffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
                -1, -1,  1, -1, -1,  1,
                -1,  1,  1, -1,  1,  1
            ]), gl.STATIC_DRAW);

            glSceneTexture = gl.createTexture();
            gl.bindTexture(gl.TEXTURE_2D, glSceneTexture);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

            return true;
        } catch(e) {
            console.warn("[ShaderRack] WebGL2 Post-pipeline init fallback:", e);
            return false;
        }
    }

    function renderPostFxLoop() {
        if (!glPostContext || !glQuadProgram || activeShaderList.length === 0) {
            if (glPostCanvas) glPostCanvas.style.display = 'none';
            return;
        }

        const sourceCanvas = document.querySelector('#shader-overlay-container canvas');
        if (!sourceCanvas || sourceCanvas.width === 0 || sourceCanvas.height === 0) {
            glPostAnimationId = requestAnimationFrame(renderPostFxLoop);
            return;
        }

        const gl = glPostContext;
        if (glPostCanvas.width !== sourceCanvas.width || glPostCanvas.height !== sourceCanvas.height) {
            glPostCanvas.width = sourceCanvas.width;
            glPostCanvas.height = sourceCanvas.height;
            gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
        }

        gl.useProgram(glQuadProgram);

        // Upload source canvas to texture
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, glSceneTexture);
        try {
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, sourceCanvas);
        } catch (e) {
            // Context might be tainted or busy
            glPostAnimationId = requestAnimationFrame(renderPostFxLoop);
            return;
        }

        let godrayVal = 0.0;
        let chromaVal = 0.0;
        let glitchVal = 0.0;
        for (let s of activeShaderList) {
            const intensity = (typeof s.intensity !== 'undefined') ? s.intensity : 0.6;
            if (s.id === 'volumetric_godrays') godrayVal = intensity;
            if (s.id === 'chromatic_aberration' || s.id === 'analog_saturation_grain') chromaVal = intensity;
            if (s.id === 'matrix_glitch_mosaic') glitchVal = intensity;
        }

        const uScene = gl.getUniformLocation(glQuadProgram, 'u_sceneTexture');
        const uTime = gl.getUniformLocation(glQuadProgram, 'u_time');
        const uBass = gl.getUniformLocation(glQuadProgram, 'u_bass');
        const uDrums = gl.getUniformLocation(glQuadProgram, 'u_drums');
        const uGodrays = gl.getUniformLocation(glQuadProgram, 'u_godrays');
        const uChroma = gl.getUniformLocation(glQuadProgram, 'u_chroma');
        const uGlitch = gl.getUniformLocation(glQuadProgram, 'u_glitch');
        const uRes = gl.getUniformLocation(glQuadProgram, 'u_resolution');

        gl.uniform1i(uScene, 0);
        gl.uniform1f(uTime, performance.now() * 0.001);
        gl.uniform1f(uBass, window.sub_bass || window.bass || 0.5);
        gl.uniform1f(uDrums, window.drums || 0.5);
        gl.uniform1f(uGodrays, godrayVal);
        gl.uniform1f(uChroma, chromaVal);
        gl.uniform1f(uGlitch, glitchVal);
        gl.uniform2f(uRes, gl.drawingBufferWidth, gl.drawingBufferHeight);

        const posLoc = gl.getAttribLocation(glQuadProgram, 'position');
        gl.enableVertexAttribArray(posLoc);
        gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

        gl.drawArrays(gl.TRIANGLES, 0, 6);
        glPostCanvas.style.display = 'block';

        glPostAnimationId = requestAnimationFrame(renderPostFxLoop);
    }

    // 著色器機架管線外掛
    window.setPostShaders = function(shaderConfigs) {
        console.log("[ShaderRack WebGL2] Applied shaders:", shaderConfigs);
        activeShaderList = Array.isArray(shaderConfigs) ? shaderConfigs : [];
        const container = document.getElementById('shader-overlay-container');
        
        if (activeShaderList.length > 0 && initWebGLPostPipeline()) {
            if (container) container.style.filter = 'none';
            if (!glPostAnimationId) {
                renderPostFxLoop();
            }
        } else {
            if (glPostCanvas) glPostCanvas.style.display = 'none';
            if (glPostAnimationId) {
                cancelAnimationFrame(glPostAnimationId);
                glPostAnimationId = null;
            }
            // 輕量 CSS 降級
            if (container) {
                let hasGlow = false;
                let hasGrain = false;
                for (let s of activeShaderList) {
                    if (s.id === 'volumetric_godrays') hasGlow = true;
                    if (s.id === 'chromatic_aberration') hasGrain = true;
                }
                container.style.filter = (hasGlow ? 'drop-shadow(0 0 25px rgba(168, 85, 247, 0.6)) ' : '') +
                                         (hasGrain ? 'contrast(1.15) brightness(1.05)' : '');
            }
        }
    };

    // Preload Watchdog
    setTimeout(function() {
        if (window._p5Instance && window._p5Instance._preloadCount > 0) {
            console.warn('[Watchdog] Auto unsticking stalled p5._preloadCount');
            window._p5Instance._preloadCount = 0;
            if (typeof window.setup === 'function') {
                try { window.setup(); } catch(e) { console.error(e); }
            }
        }
    }, 1500);

    console.log("[DoubleBufferSandbox] Runtime shield loaded.");
})();
