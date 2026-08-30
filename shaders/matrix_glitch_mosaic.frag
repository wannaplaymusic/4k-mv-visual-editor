#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_inputTexture;
uniform float u_time;
uniform float u_glitchTrigger;

float random2d(vec2 st) { return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec2 uv = vUv;
    if (u_glitchTrigger > 0.01) {
        float blockSize = mix(1000.0, 30.0, u_glitchTrigger);
        vec2 blockUv = floor(uv * blockSize) / blockSize;
        if (random2d(blockUv + floor(u_time * 20.0)) < u_glitchTrigger * 0.6) {
            uv.x += (random2d(vec2(u_time, blockUv.y)) - 0.5) * 0.1 * u_glitchTrigger;
        }
    }
    float split = u_glitchTrigger * 0.02;
    float r = texture(u_inputTexture, uv + vec2(split, 0.0)).r;
    float g = texture(u_inputTexture, uv).g;
    float b = texture(u_inputTexture, uv - vec2(split, 0.0)).b;
    fragColor = vec4(r, g, b, 1.0);
}
