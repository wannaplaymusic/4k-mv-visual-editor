#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_depthTexture;
uniform sampler2D u_densityTexture;
uniform vec2 u_resolution;
uniform float u_spectralCentroid;
uniform vec3 u_lightPos;

vec3 calculateNormal(vec2 uv) {
    vec2 e = 1.0 / u_resolution;
    float d = texture(u_depthTexture, uv).r;
    float dRight = texture(u_depthTexture, uv + vec2(e.x, 0.0)).r;
    float dUp    = texture(u_depthTexture, uv + vec2(0.0, e.y)).r;
    
    vec3 dx = vec3(e.x, 0.0, dRight - d);
    vec3 dy = vec3(0.0, e.y, dUp - d);
    return normalize(cross(dx, dy));
}

void main() {
    float depth = texture(u_depthTexture, vUv).r;
    if (depth <= 0.0001) { fragColor = vec4(0.0); return; }
    
    vec3 N = calculateNormal(vUv);
    vec3 L = normalize(u_lightPos - vec3(vUv, depth));
    vec3 V = vec3(0.0, 0.0, 1.0);
    
    float spec = pow(max(dot(V, reflect(-L, N)), 0.0), 32.0);
    float ior = 1.33 + u_spectralCentroid * 0.2;
    vec2 refractUv = vUv + N.xy * (0.03 / ior);
    vec3 baseColor = texture(u_densityTexture, refractUv).rgb;
    
    float fresnel = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    vec3 finalColor = mix(baseColor, vec3(1.0), fresnel * 0.5) + vec3(spec);
    fragColor = vec4(finalColor, 1.0);
}
