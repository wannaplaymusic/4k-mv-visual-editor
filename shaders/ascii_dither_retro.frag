#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_sceneTexture;
uniform vec2 u_resolution;
uniform float u_ditherAmount;

const mat4 bayerMatrix = mat4(
     0.0/16.0,  8.0/16.0,  2.0/16.0, 10.0/16.0,
    12.0/16.0,  4.0/16.0, 14.0/16.0,  6.0/16.0,
     3.0/16.0, 11.0/16.0,  1.0/16.0,  9.0/16.0,
    15.0/16.0,  7.0/16.0, 13.0/16.0,  5.0/16.0
);

void main() {
    vec3 rawColor = texture(u_sceneTexture, vUv).rgb;
    float luma = dot(rawColor, vec3(0.299, 0.587, 0.114));
    
    ivec2 pixelCoord = ivec2(gl_FragCoord.xy) % 4;
    float dithered = step(bayerMatrix[pixelCoord.x][pixelCoord.y], luma);
    float scanline = sin(vUv.y * u_resolution.y * 1.5) * 0.15;
    
    fragColor = vec4(mix(rawColor, vec3(dithered), u_ditherAmount) - scanline, 1.0);
}
