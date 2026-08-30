#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_energy;
uniform vec4 u_params;

vec3 computeCliffordAttractor(vec3 p, vec4 params) {
    float a = params.x, b = params.y, c = params.z, d = params.w;
    float xNext = sin(a * p.y) + c * cos(a * p.x);
    float yNext = sin(b * p.x) + d * cos(b * p.y);
    float zNext = sin(p.z) * cos(p.x);
    return (vec3(xNext, yNext, zNext) - p) * 2.0;
}

vec3 computeAizawaAttractor(vec3 p, float energy) {
    float a = 0.95, b = 0.7, c = 0.6, d = 3.5, e = 0.25, f = 0.1;
    float dx = (p.z - b) * p.x - d * p.y;
    float dy = d * p.x + (p.z - b) * p.y;
    float dz = c + a * p.z - (p.z * p.z * p.z) / 3.0 - (p.x * p.x + p.y * p.y) * (1.0 + e * p.z) + f * p.z * (p.x * p.x * p.x);
    return vec3(dx, dy, dz) * (1.0 + energy * 2.0);
}

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec3 p = vec3(st * 2.0, sin(u_time * 0.5));
    vec3 att = computeAizawaAttractor(p, u_energy);
    vec3 col = 0.5 + 0.5 * sin(att + vec3(0.0, 2.0, 4.0));
    fragColor = vec4(col, 1.0);
}
