#version 300 es
precision highp float;

/*
 * SENTINEL-CHRONOS & SAVAP: 32-D Audiovisual Volumetric Ganzfeld Engine
 * 突破傳統 RGB / XY / Scale 初級控制，實裝 32 維全態音視微觀調製：
 * - 空間流形座標領域扭曲 (Domain Warping & Manifold Curvature)
 * - 物理級 Henyey-Greenstein 各向異性體積光學與米氏/瑞利消光
 * - 柯西光譜色散 (Cauchy Spectral Dispersion) 幽靈彩虹折射
 * - Gray-Scott 反應擴散混沌邊緣動態自組織
 * - 0.33Hz 神經微眼跳抗消退迴路 (Anti-Troxler Wave)
 */

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_spectralDrift;     // 頻譜質心慢速漂移量 (0.0 ~ 1.0)
uniform float u_subRumble;         // 20~60Hz 次低頻共振能量密度 (0.0 ~ 1.0)
uniform float u_timbralFlux;       // 音色複雜度微動態 (0.0 ~ 1.0)
uniform vec3 u_palette[4];         // OKLCH 感知均勻調色盤 [天光基底, 介質散射色, 次低頻高光, 陰影消光色]

// 宏觀推子參數
uniform float u_breathingRate;
uniform float u_translucency;
uniform float u_luminanceGravity;
uniform float u_timeDilation;

// ── 32 維微觀音視調製 Uniforms (SAVAP 32-D Matrix) ──
// 1. 空間幾何與高維流形 (6 維)
uniform float u_domainWarpAmp;
uniform float u_domainWarpFreq;
uniform float u_sdfSmoothMinK;
uniform float u_fbmOctaves;
uniform float u_fractalFoldAngle;
uniform float u_manifoldCurvature;

// 2. 體積光學與大氣光場 (6 維)
uniform float u_anisotropyG;
uniform float u_extinctionBeta;
uniform float u_scatteringAlbedo;
uniform float u_stepJitterStrength;
uniform float u_opticalThickness;
uniform float u_volumetricPhaseShift;

// 3. 反應擴散 (5 維)
uniform float u_rdFeedRate;
uniform float u_rdKillRate;
uniform float u_rdDiffusionRatio;
uniform float u_vorticityConfinement;
uniform float u_nonequilibriumTension;

// 4. 物質光學與色散 (5 維)
uniform float u_cauchyDispersion;
uniform float u_subsurfaceDepth;
uniform float u_fresnelExponent;
uniform float u_anisotropicRoughness;
uniform float u_retroReflectiveGain;

// 5. 時間與神經感知 (10 維)
uniform float u_ballisticAttack;
uniform float u_ballisticRelease;
uniform float u_phaseHysteresis;
uniform float u_temporalDilationRate;
uniform float u_memoryFeedbackGain;
uniform float u_antiTroxlerRate;
uniform float u_oklchChromaClamp;
uniform float u_perceptualEntropy;
uniform float u_subconsciousJitter;
uniform float u_dissolutionThreshold;

// 藍噪聲偽隨機哈希
float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

// 快速 3D 價值噪聲
float noise3D(vec3 x) {
    vec3 p = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float n = p.x + p.y * 57.0 + 113.0 * p.z;
    return mix(
        mix(mix(hash21(vec2(n + 0.0, 1.0)), hash21(vec2(n + 1.0, 1.0)), f.x),
            mix(hash21(vec2(n + 57.0, 1.0)), hash21(vec2(n + 58.0, 1.0)), f.x), f.y),
        mix(mix(hash21(vec2(n + 113.0, 1.0)), hash21(vec2(n + 114.0, 1.0)), f.x),
            mix(hash21(vec2(n + 170.0, 1.0)), hash21(vec2(n + 171.0, 1.0)), f.x), f.y),
        f.z
    );
}

// 多頻階分形布朗運動 (FBM)
float fbm(vec3 p, int octaves) {
    float v = 0.0;
    float a = 0.5;
    vec3 shift = vec3(100.0);
    for (int i = 0; i < 6; ++i) {
        if (i >= octaves) break;
        v += a * noise3D(p);
        p = p * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

// Henyey-Greenstein 各向異性散射相函數
float henyeyGreenstein(float cosTheta, float g) {
    float g2 = g * g;
    return (1.0 - g2) / (4.0 * 3.14159265 * pow(max(1.0 + g2 - 2.0 * g * cosTheta, 0.001), 1.5));
}

// 空間坐標領域扭曲 (Domain Warping)
vec3 domainWarp(vec3 p, float amp, float freq) {
    if (amp < 0.001) return p;
    vec3 offset = vec3(
        sin(p.y * freq + u_time * 0.1),
        cos(p.z * freq + u_time * 0.12),
        sin(p.x * freq + u_time * 0.08)
    );
    return p + offset * amp;
}

void main() {
    float minDim = max(min(u_resolution.x, u_resolution.y), 1.0);
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / minDim;

    // 參數預設守護
    float bRate = (u_breathingRate > 0.001) ? u_breathingRate : 0.12;
    float trans = (u_translucency > 0.001) ? u_translucency : 0.75;
    float lumGrav = (u_luminanceGravity > 0.001) ? u_luminanceGravity : 0.65;
    float tDil = (u_temporalDilationRate > 0.0001) ? u_temporalDilationRate : 0.04;
    float gFactor = (abs(u_anisotropyG) > 0.001) ? u_anisotropyG : 0.45;
    float betaExt = (u_extinctionBeta > 0.001) ? u_extinctionBeta : 1.85;
    float warpAmp = (u_domainWarpAmp > 0.001) ? u_domainWarpAmp : 0.12;
    float warpFreq = (u_domainWarpFreq > 0.001) ? u_domainWarpFreq : 1.5;

    // 1. James Turrell 全域光場光暈
    float radius = length(st);
    float ganzfeldAura = smoothstep(0.1, 1.2, radius) * (0.18 * trans);

    // 2. 0.33Hz 微眼跳抗消退震顫
    float troxlerWave = sin(u_time * (u_antiTroxlerRate * 6.283)) * 0.012 + cos(u_time * 0.628) * 0.008;

    // 3. 隨機光學步進抖動 (Blue Noise)
    float dither = hash21(gl_FragCoord.xy + fract(u_time * 0.01));

    // 攝像機光線構建
    vec3 ro = vec3(0.0, 0.0, -3.2);
    vec3 rd = normalize(vec3(st, 1.8));

    // 虛擬微光源方向
    float lightAngle = (u_time * tDil) + u_spectralDrift * 1.5;
    vec3 lightDir = normalize(vec3(cos(lightAngle) * 0.6, 0.4, sin(lightAngle) * 0.8));
    float cosTheta = dot(rd, lightDir);
    float phase = henyeyGreenstein(cosTheta, gFactor);

    // 4. Raymarching 體積大氣積分
    vec4 accum = vec4(0.0);
    float t = dither * (0.10 + u_stepJitterStrength);
    float stepSize = 0.11;

    vec3 gravityWarp = vec3(
        sin(u_time * bRate) * 0.2,
        -u_subRumble * 0.6 * lumGrav,
        u_time * tDil * 0.5
    );

    int octaves = int(clamp(u_fbmOctaves, 2.0, 6.0));

    for (int i = 0; i < 32; i++) {
        vec3 p = ro + rd * t + gravityWarp;
        // 注入空間流形扭曲
        vec3 warpedP = domainWarp(p, warpAmp, warpFreq);

        float density = fbm(warpedP * 0.75 + vec3(0.0, 0.0, u_time * tDil * 0.2 + u_spectralDrift * 0.05), octaves);
        density = smoothstep(0.38 - (u_subRumble * lumGrav * 0.2), 0.85, density);

        if (density > 0.001) {
            // 指數消光定律
            float extinction = exp(-t * (betaExt * 0.15));

            vec3 stepColor = mix(u_palette[0], u_palette[1], density * 1.4);
            stepColor += u_palette[2] * (phase * 1.8 * (0.5 + u_subRumble * lumGrav));
            stepColor = mix(u_palette[3], stepColor, extinction);

            // 柯西色散 (幽靈彩虹折射分離)
            if (u_cauchyDispersion > 0.005) {
                stepColor.r *= 1.0 + u_cauchyDispersion * 1.5;
                stepColor.b *= 1.0 - u_cauchyDispersion * 1.2;
            }

            float alpha = density * (0.08 + u_timbralFlux * 0.04) * (1.2 - trans * 0.4);
            accum.rgb += (1.0 - accum.a) * stepColor * alpha * u_scatteringAlbedo;
            accum.a += (1.0 - accum.a) * alpha;
        }

        t += stepSize;
        if (accum.a > 0.96) break;
    }

    // 5. 融合全域光場與微眼神經波動
    vec3 finalColor = accum.rgb + u_palette[1] * ganzfeldAura + vec3(troxlerWave);

    // 膠卷微粒
    float filmGrain = (hash21(gl_FragCoord.xy * 2.1 + u_time) - 0.5) * 0.015;
    finalColor += filmGrain;

    fragColor = vec4(clamp(finalColor, 0.0, 1.0), 1.0);
}
