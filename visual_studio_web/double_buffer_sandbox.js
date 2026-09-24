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

    // 黑畫面檢測探針
    let blackFrameCount = 0;
    setInterval(function() {
        const canvas = document.querySelector('canvas');
        if (!canvas) return;
        try {
            const ctx = canvas.getContext('2d');
            if (ctx) {
                // 取樣中心 5x5 像素
                const cx = Math.floor(canvas.width / 2);
                const cy = Math.floor(canvas.height / 2);
                const imgData = ctx.getImageData(cx, cy, 5, 5).data;
                let isBlack = true;
                for (let i = 0; i < imgData.length; i += 4) {
                    if (imgData[i] > 10 || imgData[i+1] > 10 || imgData[i+2] > 10) {
                        isBlack = false;
                        break;
                    }
                }
                if (isBlack) {
                    blackFrameCount++;
                } else {
                    blackFrameCount = 0;
                }
            }
        } catch(e) {
            // WebGL context 可能禁止 getImageData，略過
        }
    }, 500);

    // 全域異常防護攔截
    window.addEventListener('error', function(event) {
        console.error("[Sandbox Error Caught]", event.message, "at line", event.lineno);
        window.__sandboxErrors.push({ message: event.message, line: event.lineno });
    });

    window.addEventListener('unhandledrejection', function(event) {
        console.error("[Sandbox Promise Rejection]", event.reason);
    });

    // 著色器機架管線外掛
    window.setPostShaders = function(shaderConfigs) {
        console.log("[ShaderRack] Applied shaders:", shaderConfigs);
        const container = document.getElementById('shader-overlay-container');
        if (!container) return;

        let hasGlow = false;
        let hasGrain = false;
        for (let s of shaderConfigs) {
            if (s.id === 'volumetric_godrays') hasGlow = true;
            if (s.id === 'chromatic_aberration') hasGrain = true;
        }

        container.style.filter = (hasGlow ? 'drop-shadow(0 0 25px rgba(168, 85, 247, 0.6)) ' : '') +
                                 (hasGrain ? 'contrast(1.15) brightness(1.05)' : '');
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
