#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

// 紋理緩衝
uniform sampler2D u_particlePos;      // 當前粒子位置 (RGB: xyz, A: 相態/生命週期)
uniform sampler2D u_particleVel;      // 當前粒子速度 (RGB: vx vy vz, A: 局部密度)
uniform sampler2D u_acousticGrid;     // 512x512 聲學衝擊波速度/壓力場 (RG: vel, B: pressure)

// 時間與步長
uniform float u_dt;
uniform float u_time;

// 導演系統參數 (Director Controls)
uniform int u_phaseMode;              // 0: 星塵, 1: 水銀, 2: 克拉尼砂, 3: 黏菌, 4: 賽博碎晶, 5: 黑洞, 6: 熔岩, 7: 量子波包
uniform float u_directorTension;      // 導演張力推子 (0.0 ~ 1.0)
uniform float u_vorticity;            // 渦量增益 (0.0 ~ 5.0)
uniform float u_inflowGravity;        // 引力/排斥力 (-5.0 ~ 5.0)
uniform float u_viscosity;            // 流體黏度 (0.0 ~ 1.0)

// 音訊特徵 (Ballistic-filtered)
uniform float u_bass;
uniform float u_mid;
uniform float u_high;
uniform float u_beatPulse;

// 免疫純色/除零安全常量
const float EPSILON = 1e-4;

// 3D 偽隨機雜訊
float hash31(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

// 簡易 3D 潛勢場旋度 (Curl of Vector Potential)
vec3 samplePotential(vec3 p) {
    float t = u_time * 0.15;
    return vec3(
        sin(p.y * 1.2 + t) + cos(p.z * 0.8 - t * 0.7),
        sin(p.z * 1.1 - t * 0.5) + cos(p.x * 1.3 + t),
        sin(p.x * 0.9 + t * 0.8) + cos(p.y * 1.0 - t * 0.6)
    );
}

vec3 curlNoise3D(vec3 p) {
    float e = 0.02;
    vec3 dx = vec3(e, 0.0, 0.0);
    vec3 dy = vec3(0.0, e, 0.0);
    vec3 dz = vec3(0.0, 0.0, e);

    vec3 p_x1 = samplePotential(p + dx);
    vec3 p_x0 = samplePotential(p - dx);
    vec3 p_y1 = samplePotential(p + dy);
    vec3 p_y0 = samplePotential(p - dy);
    vec3 p_z1 = samplePotential(p + dz);
    vec3 p_z0 = samplePotential(p - dz);

    float cx = (p_y1.z - p_y0.z) / (2.0 * e) - (p_z1.y - p_z0.y) / (2.0 * e);
    float cy = (p_z1.x - p_z0.x) / (2.0 * e) - (p_x1.z - p_x0.z) / (2.0 * e);
    float cz = (p_x1.y - p_x0.y) / (2.0 * e) - (p_y1.x - p_y0.x) / (2.0 * e);

    return vec3(cx, cy, cz);
}

void main() {
    vec4 posData = texture(u_particlePos, vUv);
    vec4 velData = texture(u_particleVel, vUv);

    vec3 pos = posData.rgb;
    vec3 vel = velData.rgb;
    float localDensity = velData.a;

    // 1. 3D Curl Noise 基礎無散度渦流場
    vec3 curl = curlNoise3D(pos * 0.08) * (1.0 + u_vorticity * 0.8);

    // 2. 引力/排斥力與中心距離防除零 (Zero-division Guard)
    vec3 centerDelta = -pos;
    float rSq = dot(centerDelta, centerDelta) + EPSILON;
    float r = sqrt(rSq);
    vec3 radialDir = centerDelta / r;

    // 導演系統引力調度 (負值為炸裂排斥，正值為黑洞聚集)
    vec3 gravityForce = radialDir * (u_inflowGravity * 2.0 / (rSq * 0.05 + 1.0));

    // 3. 防純色爆白: 局部密度過高時自適應排斥負反饋
    vec3 densityRepulsion = vec3(0.0);
    if (localDensity > 0.6) {
        float excess = (localDensity - 0.6) / 0.4;
        densityRepulsion = radialDir * (-excess * 3.5);
    }

    // 4. 8大相態力學特徵分流
    vec3 phaseForce = vec3(0.0);
    if (u_phaseMode == 0) {
        // 0: 超弦星塵 - 4D 纖維高速擾動
        phaseForce = curl * 1.5 + vec3(sin(pos.z * 2.0), cos(pos.x * 2.0), 0.0) * (u_high * 2.0);
    } else if (u_phaseMode == 1) {
        // 1: 水銀熔球 - 高表面張力凝聚 + 阻尼
        phaseForce = gravityForce * 1.5 - vel * (u_viscosity * 2.5);
    } else if (u_phaseMode == 2) {
        // 2: 克拉尼聲學砂 - 駐波幾何引力槽
        float chladni = sin(pos.x * 0.1) * sin(pos.y * 0.1) - sin(pos.y * 0.1) * sin(pos.z * 0.1);
        phaseForce = vec3(-chladni * pos.y, -chladni * pos.x, -pos.z * 0.5) * (1.0 + u_bass * 3.0);
    } else if (u_phaseMode == 3) {
        // 3: 生物黏菌 - 有機導向脈衝
        phaseForce = curl * 0.8 + normalize(pos + vec3(0.01)) * (sin(u_time * 2.0) * 0.5);
    } else if (u_phaseMode == 4) {
        // 4: 賽博碎晶 - 離散多面體跳躍 (斷裂力學)
        phaseForce = sign(pos) * (u_beatPulse * 4.0) + curl * 0.5;
    } else if (u_phaseMode == 5) {
        // 5: 黑洞吸積盤 - 強開普勒角動量
        vec3 orbit = cross(vec3(0.0, 0.0, 1.0), radialDir);
        phaseForce = orbit * (15.0 / (r + 0.5)) + gravityForce * 2.0;
    } else if (u_phaseMode == 6) {
        // 6: 黏稠熔岩 - Rayleigh-Bénard 垂直對流
        phaseForce = vec3(curl.xy * 0.4, sin(pos.x * 0.1 + u_time) * 1.5) - vel * 1.2;
    } else {
        // 7: 量子波包 - 薛丁格相位干涉擴散
        phaseForce = vec3(cos(pos.y * 0.2), sin(pos.z * 0.2), cos(pos.x * 0.2)) * (1.0 + u_mid * 2.0);
    }

    // 5. 綜合加速度與速度更新
    vec3 totalAcc = curl + gravityForce + densityRepulsion + phaseForce;
    
    // 非牛頓剪切稠化阻尼
    float damping = clamp(1.0 - (u_viscosity * 0.3 + u_bass * 0.2) * u_dt, 0.1, 0.99);
    vel = (vel + totalAcc * u_dt) * damping;

    // 6. 位置推進
    pos += vel * u_dt;

    // 邊界柔性回彈保護 (防止粒子飛散失蹤造成死黑)
    float maxBound = 250.0;
    if (length(pos) > maxBound) {
        pos = normalize(pos) * (maxBound - 2.0);
        vel = -vel * 0.5;
    }

    fragColor = vec4(pos, 1.0);
}
