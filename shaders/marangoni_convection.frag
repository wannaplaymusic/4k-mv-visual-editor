#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_fluidState;
uniform vec2 u_resolution;
uniform float u_spectralDrift;

void main() {
    vec2 e = 1.0 / u_resolution;
    float cR = texture(u_fluidState, vUv + vec2(e.x, 0.0)).r;
    float cL = texture(u_fluidState, vUv - vec2(e.x, 0.0)).r;
    float cU = texture(u_fluidState, vUv + vec2(0.0, e.y)).r;
    float cD = texture(u_fluidState, vUv - vec2(0.0, e.y)).r;

    vec2 grad = vec2(cR - cL, cU - cD) * 0.5;
    vec2 sourceUv = vUv + grad * u_spectralDrift * 0.05;
    
    fragColor = vec4(texture(u_fluidState, sourceUv).rgb, 1.0);
}
