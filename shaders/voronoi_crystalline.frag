#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform float u_time;
uniform float u_snareTrigger;
uniform float u_scale;

vec2 hash22(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453);
}

void main() {
    vec2 st = vUv * u_scale;
    vec2 n = floor(st); vec2 f = fract(st);
    float md = 8.0;

    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 g = vec2(float(i), float(j));
            vec2 o = hash22(n + g);
            o = 0.5 + 0.5 * sin(u_time * 2.0 + 6.2831 * o + u_snareTrigger * 3.0);
            vec2 r = g + o - f;
            md = min(md, dot(r, r));
        }
    }
    vec3 col = vec3(sqrt(md));
    fragColor = vec4(col, 1.0);
}
