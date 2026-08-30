#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform float u_time;
uniform float u_hissLevel;
uniform float u_drive;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
    vec3 col = texture(u_sceneTexture, vUv).rgb;
    col = col * (1.0 + u_drive * 0.5) / (1.0 + u_drive * 0.5 * length(col));
    
    float grain = (hash(vUv + u_time) - 0.5) * (0.05 + u_hissLevel * 0.1);
    col += vec3(grain);
    col *= smoothstep(0.8, 0.2, length(vUv - 0.5) * 0.6);
    fragColor = vec4(col, 1.0);
}
