#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform float u_time;
uniform float u_tonnetzAngle;
uniform float u_crystalDensity;

void main() {
    vec2 p = vUv * u_crystalDensity - vec2(u_crystalDensity * 0.5);
    float theta = u_tonnetzAngle + u_time * 0.01;
    mat2 rot = mat2(cos(theta), -sin(theta), sin(theta), cos(theta));
    vec2 rotP = rot * p;
    
    float retardation = sin(rotP.x * 3.0) * cos(rotP.y * 3.0) * 4.0;
    vec3 col = 0.5 + 0.5 * sin(retardation + vec3(0.0, 2.094, 4.188));
    fragColor = vec4(col, 0.9);
}
