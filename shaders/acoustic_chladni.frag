#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform float u_nodeM;
uniform float u_nodeN;
uniform float u_time;

float chladni(vec2 p, float m, float n) {
    float pi = 3.14159265;
    float term1 = cos(pi * n * p.x / 2.0 + u_time) * cos(pi * m * p.y / 2.0 + u_time);
    float term2 = cos(pi * m * p.x / 2.0 + u_time) * cos(pi * n * p.y / 2.0 + u_time);
    return term1 - term2;
}

void main() {
    vec2 st = (vUv - 0.5) * 2.0;
    float pattern = chladni(st, u_nodeM, u_nodeN);
    float nodeLine = smoothstep(0.02, 0.0, abs(pattern));
    fragColor = vec4(mix(vec3(0.05), vec3(0.0, 1.0, 0.8), nodeLine), 1.0);
}
