#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_normalTexture;
uniform float u_time;
uniform float u_filmThickness;

vec3 calcIridescence(float cosTheta, float thickness) {
    vec3 waveLengths = vec3(650.0, 510.0, 475.0);
    float pathDiff = 2.0 * 1.33 * thickness * cosTheta;
    vec3 phase = (2.0 * 3.14159265 * pathDiff) / waveLengths;
    return 0.5 + 0.5 * cos(phase + vec3(0.0, 2.0, 4.0));
}

void main() {
    vec3 N = texture(u_normalTexture, vUv).rgb * 2.0 - 1.0;
    vec3 V = vec3(0.0, 0.0, 1.0);
    float cosTheta = max(dot(N, V), 0.0);
    
    float dynamicThickness = u_filmThickness + sin(vUv.x * 20.0 + u_time) * 100.0;
    vec3 iridColor = calcIridescence(cosTheta, dynamicThickness);
    fragColor = vec4(iridColor, 1.0);
}
