#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_bioPulse;
uniform vec3 u_glowColor;

float noise(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec2 waterGrid = st * 8.0 + vec2(sin(u_time * 0.2 + st.y), cos(u_time * 0.3 + st.x));
    
    float rnd = noise(floor(waterGrid));
    float particle = smoothstep(0.48, 0.5, sin(rnd * 6.28 + u_time * 1.5));
    float glow = particle * (0.2 + u_bioPulse * 0.8) * (1.0 / (length(fract(waterGrid) - 0.5) + 0.1));
    
    fragColor = vec4(u_glowColor * glow * 0.4, glow * 0.7);
}
