#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform float u_time;
uniform float u_chromaHue;

void main() {
    vec2 p = vUv * 10.0;
    float wave = sin(p.x + u_time) + sin(p.y + u_time) + sin(p.x + p.y + u_time) + sin(length(p) + u_time * 2.0);
    
    vec3 holoCol = 0.5 + 0.5 * cos(u_chromaHue + wave + vec3(0.0, 2.0, 4.0));
    float stripe = step(0.5, fract(wave * 2.0));
    fragColor = vec4(holoCol * stripe, 0.8);
}
