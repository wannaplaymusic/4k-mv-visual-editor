#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform vec2 u_center;
uniform float u_subBassIntensity;
uniform float u_aspectRatio;

void main() {
    vec2 st = vUv - u_center;
    st.x *= u_aspectRatio;
    
    float dist = length(st);
    float einsteinRadius = 0.15 * u_subBassIntensity;
    float distortion = dist / (dist + (einsteinRadius * einsteinRadius) / (dist + 0.001));
    
    vec2 warpedSt = normalize(st) * distortion;
    warpedSt.x /= u_aspectRatio;
    
    vec3 col = texture(u_sceneTexture, u_center + warpedSt).rgb;
    if (dist < einsteinRadius * 0.3) {
        col *= smoothstep(0.0, einsteinRadius * 0.3, dist);
    }
    fragColor = vec4(col, 1.0);
}
