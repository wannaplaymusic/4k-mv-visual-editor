#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_spectralFlux;
uniform float u_droneResonance;
uniform vec3 u_palette[3];

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

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec3 ro = vec3(0.0, 0.0, -2.5);
    vec3 rd = normalize(vec3(st, 1.2));
    
    vec4 colSum = vec4(0.0);
    float t = 0.0;
    
    for (int i = 0; i < 40; i++) {
        vec3 p = ro + rd * t;
        float n = noise3D(p * 1.2 + vec3(0.0, 0.0, u_time * 0.02 + u_spectralFlux * 0.1));
        if (n > 0.35) {
            float density = (n - 0.35) * 0.6;
            vec3 c = mix(u_palette[0], u_palette[1], density * 2.0) + u_palette[2] * u_droneResonance * 1.5;
            vec4 val = vec4(c, density);
            val.rgb *= val.a;
            colSum += val * (1.0 - colSum.a);
        }
        t += 0.08;
        if (colSum.a > 0.95) break;
    }
    fragColor = vec4(colSum.rgb, 1.0);
}
