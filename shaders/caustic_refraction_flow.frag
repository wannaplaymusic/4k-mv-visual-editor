#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform float u_time;
uniform float u_spectralCentroid;
uniform vec3 u_primaryColor;

void main() {
    vec2 p = vUv * 6.0 - vec2(3.0);
    vec2 i = vec2(p);
    float c = 1.0;

    for (int n = 0; n < 5; n++) {
        float t = u_time * (0.05 + u_spectralCentroid * 0.02);
        i = p + vec2(cos(t - i.x) + sin(t + i.y), sin(t - i.y) + cos(t + i.x));
        c += 1.0 / length(vec2(p.x / (sin(i.x + t) / 0.005), p.y / (cos(i.y + t) / 0.005)));
    }

    c = 1.17 - pow(c / 5.0, 1.4);
    vec3 color = clamp(vec3(pow(abs(c), 8.0)) + u_primaryColor * 0.4, 0.0, 1.0);
    fragColor = vec4(color, 1.0);
}
