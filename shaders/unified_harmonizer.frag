// SAVAP Unified Harmonizer Shader (GLSL ES 1.00 / WebGL)
// 依據 Google Antigravity SAVAP Technical Blueprint 第 7 頁規範實作：
// 1. Duotone Chord Assimilation: Luminance -> window.currentChordColor (uChordColor)
// 2. Paradoxical Independent Shadows: Detached silhouette shadows with harmonic phase lag
// 3. Rayleigh Atmospheric Perspective: C_final = C_obj * exp(-beta * Z) + C_chord * (1.0 - exp(-beta * Z))

precision highp float;

uniform sampler2D uTexture;
uniform vec2 uResolution;
uniform float uTime;

// 樂理與和弦色彩同化
uniform vec3 uChordColor;          // 當前小節/和弦目標光譜色
uniform vec3 uShadowColor;         // 悖論陰影基準底色 (預設深墨青藍)
uniform float uDuotoneBlend;       // 同化強度 (0.0 ~ 1.0)

// 瑞利大氣透視深度
uniform float uDepthZ;             // 物件在場景中的深度 Z (0.0 ~ 1.0)
uniform float uRayleighBeta;       // 散射係數 beta (預設 1.85)

// 音訊遙測能量注入
uniform float uSubBass;            // 20-60Hz 達利液態擾動
uniform float uKick;               // Low-Mid 衝擊超調
uniform float uMidLead;            // 1-4kHz 諧波公轉
uniform float uHiHat;              // 8kHz+ 負片日光化暴光 (Sabattier)

// 悖論陰影參數
uniform vec2 uShadowOffset;        // 基礎投影向量
uniform float uShadowPhaseLag;     // 相位延遲量

varying vec2 vUv;

// 偽隨機噪波產生器
float savap_random(vec2 st) {
    return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
}

// 達利液態融化 (Simplex 代理擾動)
vec2 calculate_dali_melt(vec2 uv, float bass) {
    if (bass < 0.1) return uv;
    float waveX = sin(uv.y * 18.0 + uTime * 3.5) * (bass * 0.025);
    float waveY = cos(uv.x * 12.0 + uTime * 2.8) * (bass * 0.035);
    return uv + vec2(waveX, waveY);
}

void main() {
    // 1. 音訊液態網格融化微調
    vec2 distortedUv = calculate_dali_melt(vUv, uSubBass);

    // 2. 採樣主紋理與 Alpha
    vec4 src = texture2D(uTexture, distortedUv);

    // 3. 計算獨立悖論陰影 (Paradoxical Independent Shadows)
    // 影子帶有 deliberate harmonic phase lag
    float phaseLag = sin(uTime * 2.0 + uShadowPhaseLag) * 0.015;
    vec2 shadowUv = distortedUv - (uShadowOffset + vec2(phaseLag, phaseLag * 0.5));
    vec4 shadowSrc = texture2D(uTexture, shadowUv);
    float shadowMask = shadowSrc.a * (1.0 - src.a) * 0.65; // 本體透明處露出獨立影子

    // 4. 計算相對明度 (Relative Luminance: Rec. 709)
    float luma = dot(src.rgb, vec3(0.2126, 0.7152, 0.0722));

    // 5. Duotone Chord Assimilation (雙色和弦同化)
    // 將不同異質素材的 RGB 強制重構為符合當前和弦的光譜階調
    vec3 toneShadow = mix(uShadowColor, uChordColor * 0.25, 0.3);
    vec3 toneHighlight = mix(vec3(0.96, 0.94, 0.88), uChordColor, 0.65);
    vec3 duotoneColor = mix(toneShadow, toneHighlight, luma);
    
    // 微粒膠卷顆粒 (Film Grain)
    float grain = (savap_random(distortedUv * uResolution + fract(uTime)) - 0.5) * 0.06;
    duotoneColor = clamp(duotoneColor + grain, 0.0, 1.0);

    // 混合原始素材與同化色
    vec3 colorAssimilated = mix(src.rgb, duotoneColor, uDuotoneBlend);

    // 6. 瑞利大氣透視深度霧化 (Rayleigh Atmospheric Perspective)
    // C_final = C_obj * exp(-beta * Z) + C_chord * (1.0 - exp(-beta * Z))
    float beta = max(0.1, uRayleighBeta);
    float transFactor = exp(-beta * uDepthZ);
    vec3 finalColor = colorAssimilated * transFactor + uChordColor * (1.0 - transFactor);

    // 7. 曼·雷中途曝光金屬負片暴光 (Man Ray Sabattier Solarization)
    if (uHiHat > 0.75) {
        float flareIntensity = (uHiHat - 0.75) * 3.5;
        finalColor = abs(finalColor - vec3(flareIntensity));
    }

    // 8. 疊加獨立悖論陰影
    if (src.a < 0.05 && shadowMask > 0.05) {
        gl_FragColor = vec4(uShadowColor * 0.2, shadowMask);
    } else {
        if (src.a < 0.02) discard;
        gl_FragColor = vec4(finalColor, src.a);
    }
}
