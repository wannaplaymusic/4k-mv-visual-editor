#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

// 深度與背景貼圖
uniform sampler2D u_depthTexture;       // 粒子渲染出的原始深度圖
uniform sampler2D u_colorTexture;       // 原始渲染顏色
uniform vec2 u_resolution;
uniform float u_fluidRadius;            // 雙邊濾波核半徑
uniform float u_depthThreshold;         // 保邊深度閾值

// 光照與水銀/液態材質參數
uniform vec3 u_lightDir;                // 主光源方向
uniform vec3 u_fluidColor;              // 流體基底顏色 (RGB)
uniform float u_metallic;               // 金屬度 (水銀=1.0)
uniform float u_roughness;              // 粗糙度
uniform float u_refractionIndex;        // 折射率 (如 1.333 水, 1.62 水銀)
uniform float u_emissiveGain;           // 發光增益

// ACES Tone Mapping
vec3 acesFilm(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec2 texel = 1.0 / u_resolution;
    float depth = texture(u_depthTexture, vUv).r;

    // 若深度為背景極限值 (無粒子)，直接透傳背景色
    if (depth <= 0.001 || depth >= 0.999) {
        fragColor = texture(u_colorTexture, vUv);
        return;
    }

    // 1. 雙邊保邊深度濾波 (Bilateral Depth Filter - 將離散球融合成光滑流體)
    float filteredDepth = 0.0;
    float totalWeight = 0.0;
    int filterSize = int(clamp(u_fluidRadius, 2.0, 8.0));

    for (int x = -filterSize; x <= filterSize; x++) {
        for (int y = -filterSize; y <= filterSize; y++) {
            vec2 offset = vec2(float(x), float(y)) * texel;
            float sampleDepth = texture(u_depthTexture, vUv + offset).r;
            if (sampleDepth > 0.001 && sampleDepth < 0.999) {
                // 空間高斯權重
                float spatialDist = length(vec2(float(x), float(y)));
                float spatialWeight = exp(-spatialDist * spatialDist / (2.0 * float(filterSize) * float(filterSize)));

                // 深度差保邊權重 (避免跨物體邊緣模糊)
                float depthDiff = abs(sampleDepth - depth);
                float depthWeight = exp(-depthDiff * depthDiff / (2.0 * u_depthThreshold * u_depthThreshold + 0.0001));

                float w = spatialWeight * depthWeight;
                filteredDepth += sampleDepth * w;
                totalWeight += w;
            }
        }
    }

    if (totalWeight > 0.0) {
        filteredDepth /= totalWeight;
    } else {
        filteredDepth = depth;
    }

    // 2. 從平滑深度場重建法線向量 (Screen-Space Normal Reconstruction)
    float dL = texture(u_depthTexture, vUv - vec2(texel.x, 0.0)).r;
    float dR = texture(u_depthTexture, vUv + vec2(texel.x, 0.0)).r;
    float dD = texture(u_depthTexture, vUv - vec2(0.0, texel.y)).r;
    float dU = texture(u_depthTexture, vUv + vec2(0.0, texel.y)).r;

    vec3 normal;
    normal.x = (dL - dR);
    normal.y = (dD - dU);
    normal.z = 2.0 * texel.x; // 縱向深度縮放
    normal = normalize(normal);

    // 3. 菲涅爾反射 (Schlick's approximation)
    vec3 viewDir = vec3(0.0, 0.0, 1.0);
    float NdotV = max(dot(normal, viewDir), 0.0);
    float f0 = mix(0.04, 0.95, u_metallic); // 水銀等金屬高 F0
    float fresnel = f0 + (1.0 - f0) * pow(1.0 - NdotV, 5.0);

    // 4. 光照與高光反射
    vec3 light = normalize(u_lightDir);
    vec3 halfVec = normalize(light + viewDir);
    float NdotL = max(dot(normal, light), 0.0);
    float NdotH = max(dot(normal, halfVec), 0.0);
    float spec = pow(NdotH, (1.0 - u_roughness) * 128.0 + 4.0);

    // 5. 折射偏移 (Refraction distortion)
    vec2 refractOffset = normal.xy * (0.04 * (1.0 - u_metallic));
    vec3 bgColor = texture(u_colorTexture, vUv + refractOffset).rgb;

    // 6. 綜合材質色彩合成
    vec3 fluidBase = u_fluidColor * (0.2 + 0.8 * NdotL);
    vec3 finalColor = mix(bgColor * fluidBase, vec3(1.0, 0.95, 0.85) * spec * 2.0, fresnel);
    finalColor += u_fluidColor * u_emissiveGain * spec;

    // 7. ACES Tone Mapping (防純白死色)
    vec3 mapped = acesFilm(finalColor);

    fragColor = vec4(mapped, 1.0);
}
