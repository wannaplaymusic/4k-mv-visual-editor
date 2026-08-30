#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_inputTexture;
uniform float u_speedFactor;

const int SAMPLES = 20;

void main() {
    vec2 ray = vUv - vec2(0.5);
    vec3 col = vec3(0.0);
    float blurStrength = u_speedFactor * 0.05;
    
    for (int i = 0; i < SAMPLES; i++) {
        vec2 sampleUv = vec2(0.5) + ray * (1.0 - blurStrength * (float(i) / float(SAMPLES)));
        col += texture(u_inputTexture, sampleUv).rgb;
    }
    fragColor = vec4(col / float(SAMPLES), 1.0);
}
