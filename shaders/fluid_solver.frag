#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_velocityTexture;
uniform sampler2D u_densityTexture;
uniform vec2 u_resolution;
uniform float u_dt;
uniform float u_viscosity;

void main() {
    vec2 e = 1.0 / u_resolution;
    vec2 u = texture(u_velocityTexture, vUv).xy;
    vec2 coord = vUv - u * u_dt * e;
    
    vec4 density = texture(u_densityTexture, coord);
    fragColor = density * (1.0 - u_viscosity * u_dt);
}
