// WebGL Fragment Shader: SAVAP SOTA Unified Harmonizer & Atmospheric Perspective
precision highp float;

uniform sampler2D uTexture;
uniform vec2 uResolution;
uniform float uTime;
uniform vec3 uChordColor;      // window.currentChordColor
uniform float uBassEnergy;     // 低頻能量
uniform float uHihatEnergy;    // 高頻能量
uniform float uDepthZ;         // 當前圖層深度 Z (0.1 ~ 1.0)
uniform float uTensionFactor;  // 樂理/時間軸緊張度 (0.0 ~ 1.0)

varying vec2 vUv;

// 偽隨機噪波產生器 (用於印刷網點與膠卷顆粒)
float random2d(vec2 st) {
    return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
}

void main() {
    vec2 uv = vUv;

    // -------------------------------------------------------------
    // 【維度 4：時間軸動態張力微擾 (Temporal Tension Micro-Displacement)】
    // -------------------------------------------------------------
    float tensionDisplace = sin(uTime * 4.0 + uv.y * 10.0) * (uTensionFactor * 0.015);
    uv.x += tensionDisplace;

    // 採樣原圖 Alpha 與 RGB
    vec4 mainTex = texture2D(uTexture, uv);
    if (mainTex.a < 0.05) discard;

    // -------------------------------------------------------------
    // 【維度 3：物質真實感 - 復古印刷網點與版畫拓印 (Halftone & Frottage)】
    // -------------------------------------------------------------
    float luma = dot(mainTex.rgb, vec3(0.299, 0.587, 0.114));
    // 膠卷底片微顆粒 (Micro-Grain)
    float grain = (random2d(uv * uResolution + fract(uTime)) - 0.5) * 0.08;
    luma = clamp(luma + grain, 0.0, 1.0);

    // 印刷網點 (Halftone Dots)
    vec2 dotGrid = fract(uv * uResolution * 0.15) - 0.5;
    float dotDist = length(dotGrid);
    if (dotDist > (1.0 - luma) * 0.6) {
        luma *= 0.92;
    }

    // -------------------------------------------------------------
    // 【維度 5：空氣透視與瑞利散射衰減 (Atmospheric Perspective & Fog)】
    // -------------------------------------------------------------
    // Z 越大，對比度指數級衰減: exp(-alpha * Z)
    float depthContrast = exp(-1.2 * uDepthZ);
    luma = mix(0.5, luma, depthContrast);

    // 雙色調與和弦光學同化
    vec3 darkInk = vec3(0.03, 0.03, 0.05); // 復古墨黑
    vec3 paperBase = mix(vec3(0.94, 0.91, 0.82), uChordColor, 0.4); // 羊皮紙底色 + 和弦染光
    vec3 finalColor = mix(darkInk, paperBase, luma);

    // 遠景大氣環境光散射 (Rayleigh Scattering Tint)
    vec3 atmosphericHaze = mix(vec3(0.1, 0.08, 0.15), uChordColor, 0.35);
    finalColor = mix(finalColor, atmosphericHaze, clamp((uDepthZ - 0.3) * 0.7, 0.0, 0.85));

    // -------------------------------------------------------------
    // 【曼·雷瞬時曝光白閃 (Solarization Glitch)】
    // -------------------------------------------------------------
    if (uHihatEnergy > 0.72) {
        finalColor = abs(finalColor - vec3(uHihatEnergy * 0.75));
    }

    gl_FragColor = vec4(finalColor, mainTex.a);
}
