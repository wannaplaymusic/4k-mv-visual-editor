#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_bassEnergy;

float sdGyroid(vec3 p, float scale, float thickness, float bias) {
    p *= scale;
    float g = dot(sin(p), cos(p.zxy));
    return (abs(g + bias) - thickness) / scale;
}

float mapScene(vec3 p) {
    vec3 twistedP = p + sin(p.zxy * 2.0 + u_time) * (u_bassEnergy * 0.4);
    return sdGyroid(twistedP, 2.5, 0.05, 0.3);
}

void main() {
    vec2 st = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
    vec3 ro = vec3(0.0, 0.0, 3.0);
    vec3 rd = normalize(vec3(st, -1.2));
    
    float t = 0.0;
    for(int i = 0; i < 64; i++) {
        vec3 p = ro + rd * t;
        float d = mapScene(p);
        if(d < 0.001 || t > 10.0) break;
        t += d;
    }
    vec3 col = (t < 10.0) ? vec3(0.8, 0.9, 1.0) * (1.0 - t * 0.1) : vec3(0.0);
    fragColor = vec4(col, 1.0);
}
