// WebGL Fragment Shader: Surreal Unified Harmonizer & Paradoxical Shadow
precision highp float;

uniform sampler2D uTexture;
uniform vec2 uResolution;
uniform float uTime;
uniform vec3 uChordColor;      // 由 window.currentChordColor 傳入的當前和弦色彩
uniform float uBassEnergy;     // 低頻能量
uniform float uHihatEnergy;    // 高頻能量
uniform float uShadowPhaseLag; // 錯位陰影的相位延遲

varying vec2 vUv;

void main() {
    vec2 uv = vUv;
    
    // 1. 計算錯位陰影的非物理偏移 (隨低頻與時間產生獨立漂移)
    vec2 shadowOffset = vec2(
        sin(uTime * 1.5 + uShadowPhaseLag) * (0.03 + uBassEnergy * 0.05),
        cos(uTime * 1.2 + uShadowPhaseLag) * 0.04 + 0.03
    );
    
    // 採樣陰影層 Alpha
    vec4 shadowTex = texture2D(uTexture, uv - shadowOffset);
    float shadowMask = shadowTex.a;

    // 採樣主體圖層
    vec4 mainTex = texture2D(uTexture, uv);
    
    // 2. 光學同化：將原圖轉為灰階明度 (Luminance)
    float luma = dot(mainTex.rgb, vec3(0.299, 0.587, 0.114));
    
    // 銅版畫雕刻對比增強 (DoG Contrast Boost)
    luma = smoothstep(0.15, 0.85, luma);
    
    // 3. 雙色調漸層映射 (Duotone Color Grading)
    vec3 darkTone = vec3(0.04, 0.04, 0.06);     // 復古墨黑底色
    vec3 lightTone = mix(vec3(0.92, 0.88, 0.78), uChordColor, 0.45); // 和弦光譜漸層
    vec3 harmonizedColor = mix(darkTone, lightTone, luma);

    // 【多物件自動聚焦法則 (Surreal Selective Lighting)】
    // 非焦點狀態自動降低 30% 對比與飽和度
    float totalActivity = uBassEnergy + uHihatEnergy;
    if (totalActivity < 0.35) {
        harmonizedColor = mix(harmonizedColor, darkTone * 1.5, 0.3);
    }

    // 4. 【曼·雷】高頻打擊瞬時中途曝光 (Solarization Glitch / Transient Spotlighting)
    if (uHihatEnergy > 0.65) {
        harmonizedColor = abs(harmonizedColor - vec3(uHihatEnergy * 0.8));
    }

    // 5. 合成錯位陰影與實體
    vec4 finalColor = vec4(0.0);
    
    // 繪製半透明錯位剪影
    if (shadowMask > 0.05 && mainTex.a < 0.1) {
        finalColor = vec4(darkTone * 0.5, shadowMask * 0.65);
    }
    
    // 覆蓋主體實體
    if (mainTex.a >= 0.1) {
        finalColor = vec4(harmonizedColor, mainTex.a);
    }

    // 丟棄全透明無效像素
    if (finalColor.a < 0.02) discard;

    gl_FragColor = finalColor;
}
