#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_particlePos;
uniform sampler2D u_particleVel;
uniform float u_dt;
uniform float u_time;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

vec2 curlNoise(vec2 p) {
    float eps = 0.01;
    float n1 = hash(p + vec2(0.0, eps));
    float n2 = hash(p - vec2(0.0, eps));
    float n3 = hash(p + vec2(eps, 0.0));
    float n4 = hash(p - vec2(eps, 0.0));
    return vec2((n1 - n2) / (2.0 * eps), -(n3 - n4) / (2.0 * eps));
}

void main() {
    vec3 pos = texture(u_particlePos, vUv).rgb;
    vec2 vel = curlNoise(pos.xy * 2.0 + vec2(u_time * 0.1));
    pos.xy += vel * u_dt * 0.5;
    fragColor = vec4(pos, 1.0);
}
