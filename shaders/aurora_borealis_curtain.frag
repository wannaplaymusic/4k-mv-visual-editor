#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_auroraIntensity;
uniform vec3 u_primaryColor;
uniform vec3 u_accentColor;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p); vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    float wave = noise(vec2(st.x * 3.0 + u_time * 0.1, u_time * 0.05));
    float curtain = pow(sin(st.x * 12.0 + wave * 6.0) * 0.5 + 0.5, 3.0);
    
    float fade = smoothstep(-0.5, 0.5, st.y) * smoothstep(0.8, -0.2, st.y);
    float aurora = curtain * fade * (1.0 + u_auroraIntensity);
    
    fragColor = vec4(mix(u_primaryColor, u_accentColor, st.y + 0.5) * aurora, aurora * 0.8);
}
