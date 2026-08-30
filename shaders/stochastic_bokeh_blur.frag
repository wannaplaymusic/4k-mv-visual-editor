#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform vec2 u_resolution;
uniform float u_apertureSize;

const float GOLDEN_ANGLE = 2.39996323;
const int SAMPLES = 32;

void main() {
    vec2 delta = (1.0 / u_resolution) * u_apertureSize;
    vec3 col = vec3(0.0);
    float totalWeight = 0.0;

    for (int i = 0; i < SAMPLES; i++) {
        float r = sqrt(float(i)) / sqrt(float(SAMPLES));
        float theta = float(i) * GOLDEN_ANGLE;
        vec2 offset = vec2(cos(theta), sin(theta)) * r * delta;
        
        vec3 sampleCol = texture(u_sceneTexture, vUv + offset).rgb;
        float weight = dot(sampleCol, vec3(0.299, 0.587, 0.114)) + 0.1;
        col += sampleCol * weight;
        totalWeight += weight;
    }
    fragColor = vec4(col / totalWeight, 1.0);
}
