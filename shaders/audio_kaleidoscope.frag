#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_inputTexture;
uniform float u_segments;
uniform float u_rotation;

void main() {
    vec2 st = vUv - 0.5;
    float r = length(st);
    float a = atan(st.y, st.x) + u_rotation;
    
    float segmentAngle = 6.2831853 / u_segments;
    a = abs(mod(a, segmentAngle) - segmentAngle * 0.5);
    
    vec2 kUv = vec2(cos(a), sin(a)) * r + 0.5;
    kUv = abs(fract(kUv * 0.5 + 0.5) * 2.0 - 1.0);
    
    fragColor = vec4(texture(u_inputTexture, kUv).rgb, 1.0);
}
