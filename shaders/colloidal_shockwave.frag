#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_kickTrigger;
uniform vec2 u_epicenter;

void main() {
    vec2 st = (gl_FragCoord.xy - u_epicenter * u_resolution) / u_resolution.y;
    float dist = length(st);
    
    float waveProgress = fract(u_time * 1.5) * u_kickTrigger;
    float ring = smoothstep(waveProgress - 0.08, waveProgress, dist) - 
                 smoothstep(waveProgress, waveProgress + 0.08, dist);
                 
    vec2 distortion = normalize(st) * ring * 0.08 * u_kickTrigger;
    
    float r = texture(u_sceneTexture, vUv + distortion * 1.2).r;
    float g = texture(u_sceneTexture, vUv + distortion).g;
    float b = texture(u_sceneTexture, vUv + distortion * 0.8).b;
    fragColor = vec4(r, g, b, 1.0);
}
