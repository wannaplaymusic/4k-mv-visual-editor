#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_bassBoost;
uniform vec3 u_colorPalette[3];

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

float fBm(vec3 p) {
    return noise3D(p) * 0.5 + noise3D(p * 2.0) * 0.25;
}

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec3 ro = vec3(0.0, 0.0, -2.0);
    vec3 rd = normalize(vec3(st, 1.0));
    
    vec4 sum = vec4(0.0);
    float t = 0.0;
    
    for (int i = 0; i < 45; i++) {
        vec3 p = ro + rd * t;
        float d = fBm(p * 1.5 + vec3(0.0, 0.0, u_time * 0.1));
        if (d > 0.3) {
            vec3 c = mix(u_colorPalette[0], u_colorPalette[1], d) + u_colorPalette[2] * u_bassBoost;
            vec4 col = vec4(c, (d - 0.3) * 0.8);
            col.rgb *= col.a;
            sum += col * (1.0 - sum.a);
        }
        t += 0.08;
        if (sum.a > 0.98) break;
    }
    fragColor = vec4(sum.rgb, 1.0);
}
