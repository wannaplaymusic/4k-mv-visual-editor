#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_stateTexture;
uniform vec2 u_resolution;
uniform float u_feedRate;
uniform float u_killRate;
uniform float u_dt;

void main() {
    vec2 e = 1.0 / u_resolution;
    vec2 state = texture(u_stateTexture, vUv).rg;
    
    vec2 lap = texture(u_stateTexture, vUv + vec2(-e.x, 0.0)).rg +
               texture(u_stateTexture, vUv + vec2( e.x, 0.0)).rg +
               texture(u_stateTexture, vUv + vec2(0.0, -e.y)).rg +
               texture(u_stateTexture, vUv + vec2(0.0,  e.y)).rg -
               4.0 * state;
               
    float uvv = state.r * state.g * state.g;
    float newU = state.r + (1.0 * lap.r - uvv + u_feedRate * (1.0 - state.r)) * u_dt;
    float newV = state.g + (0.5 * lap.g + uvv - (u_killRate + u_feedRate) * state.g) * u_dt;
    
    fragColor = vec4(clamp(newU, 0.0, 1.0), clamp(newV, 0.0, 1.0), 0.0, 1.0);
}
