#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_chordTrigger;
uniform float u_bassDrive;
uniform vec3 u_primaryColor;
uniform vec3 u_secondaryColor;

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec2 p = st * 4.0;
    
    for (int i = 1; i < 4; i++) {
        float fi = float(i);
        p.x += 0.3 / fi * sin(fi * p.y + u_time * 0.4 + u_chordTrigger * 0.5);
        p.y += 0.3 / fi * cos(fi * p.x + u_time * 0.4 + u_bassDrive * 0.3);
    }
    
    float grid = pow(abs(sin(p.x) * cos(p.y)), 2.5);
    vec3 col = mix(u_primaryColor, u_secondaryColor, grid) + vec3(grid * u_chordTrigger * 0.6);
    fragColor = vec4(col, 1.0);
}
