#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform float u_snareTrigger;
uniform float u_distortionAmount;

vec2 barrelDistortion(vec2 uv, float amt) {
    vec2 st = uv - 0.5;
    return uv + st * (dot(st, st) * amt);
}

void main() {
    vec2 uv = barrelDistortion(vUv, u_distortionAmount * 0.3);
    vec3 color = texture(u_sceneTexture, uv).rgb;
    vec3 flare = vec3(0.0);
    
    for (int i = -10; i <= 10; i++) {
        vec2 offset = vec2(float(i) * 0.003 * (1.0 + u_snareTrigger), 0.0);
        vec3 sampleCol = max(texture(u_sceneTexture, uv + offset).rgb - vec3(0.6), vec3(0.0));
        flare += sampleCol * vec3(0.2, 0.5, 1.2);
    }
    fragColor = vec4(color + flare * 0.15 * u_snareTrigger, 1.0);
}
