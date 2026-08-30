#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform float u_time;
uniform float u_clickPopTrigger;
uniform float u_gridScale;

float hash12(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

void main() {
    vec2 st = vUv * u_gridScale;
    vec2 ipos = floor(st); vec2 fpos = fract(st);
    float rnd = hash12(ipos);
    
    float dotRadius = 0.1 + 0.3 * sin(u_time * 2.0 + rnd * 6.28) + u_clickPopTrigger * 0.2;
    float circle = smoothstep(dotRadius, dotRadius - 0.05, length(fpos - 0.5));
    
    fragColor = vec4(vec3(circle * rnd), 1.0);
}
