#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform vec3 u_sunLightDir;

float hash(float n) { return fract(sin(n) * 43758.5453); }
float noise3D(vec3 x) {
    vec3 p = floor(x); vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float n = p.x + p.y * 57.0 + 113.0 * p.z;
    return mix(mix(mix(hash(n + 0.0), hash(n + 1.0), f.x),
                   mix(hash(n + 57.0), hash(n + 58.0), f.x), f.y),
               mix(mix(hash(n + 113.0), hash(n + 114.0), f.x),
                   mix(hash(n + 170.0), hash(n + 171.0), f.x), f.y), f.z);
}

float cloudMap(vec3 p) {
    vec3 q = p + vec3(0.0, 0.0, u_time * 0.05);
    return smoothstep(0.35, 0.7, noise3D(q * 0.8) * 0.5 + noise3D(q * 1.6) * 0.25);
}

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec3 ro = vec3(0.0, 1.0, -2.0);
    vec3 rd = normalize(vec3(st, 1.0));
    
    vec4 sum = vec4(0.0);
    float t = 0.0;
    
    for (int i = 0; i < 35; i++) {
        vec3 p = ro + rd * t;
        float den = cloudMap(p);
        if (den > 0.01) {
            float dif = clamp((den - cloudMap(p + u_sunLightDir * 0.1)) / 0.1, 0.0, 1.0);
            vec3 lin = vec3(0.6, 0.65, 0.75) * 1.5 + vec3(1.0, 0.6, 0.3) * dif * 2.0;
            vec4 col = vec4(lin * den, den);
            sum += col * (1.0 - sum.a);
        }
        t += 0.08;
        if (sum.a > 0.98) break;
    }
    fragColor = vec4(sum.rgb, sum.a);
}
