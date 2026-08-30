#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_mainScene;
uniform sampler2D u_bloomTexture;
uniform float u_bloomIntensity;
uniform float u_vignetteStrength;

vec3 acesFilm(vec3 x) {
    float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec3 color = texture(u_mainScene, vUv).rgb;
    vec3 bloom = texture(u_bloomTexture, vUv).rgb;
    
    color += bloom * u_bloomIntensity;
    color = acesFilm(color);
    
    float vig = smoothstep(0.8, 0.2, length(vUv - 0.5) * u_vignetteStrength);
    fragColor = vec4(color * vig, 1.0);
}
