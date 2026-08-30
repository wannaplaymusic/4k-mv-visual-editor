#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_backgroundTexture;
uniform float u_time;
uniform float u_rainDensity;

vec2 hash22(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

void main() {
    vec2 st = vUv * vec2(10.0, 5.0) * u_rainDensity;
    vec2 id = floor(st); vec2 gv = fract(st) - 0.5;
    vec2 n = hash22(id);
    
    float t = u_time * 2.0 + n.x * 6.28;
    float y = -sin(t + sin(t + sin(t) * 0.5)) * 0.45;
    vec2 dropPos = gv - vec2((n.y - 0.5) * 0.6, y);
    
    float drop = smoothstep(0.15, 0.03, length(dropPos));
    vec2 distortedUv = vUv + dropPos * drop * 0.08;
    
    fragColor = vec4(texture(u_backgroundTexture, distortedUv).rgb, 1.0);
}
