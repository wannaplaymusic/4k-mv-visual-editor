#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform vec2 u_lightScreenPos;
uniform float u_godRayIntensity;

const int NUM_SAMPLES = 64;

void main() {
    vec2 deltaUv = (vUv - u_lightScreenPos) * (1.0 / float(NUM_SAMPLES)) * 0.4;
    vec2 currentUv = vUv;
    vec3 color = texture(u_sceneTexture, currentUv).rgb;
    float decay = 1.0;
    
    for (int i = 0; i < NUM_SAMPLES; i++) {
        currentUv -= deltaUv;
        color += texture(u_sceneTexture, currentUv).rgb * decay * u_godRayIntensity;
        decay *= 0.95;
    }
    fragColor = vec4(color, 1.0);
}
