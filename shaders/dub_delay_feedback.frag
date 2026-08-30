#version 300 es
precision highp float;

out vec4 fragColor;
in vec2 vUv;

uniform sampler2D u_currentFrame;
uniform sampler2D u_feedbackBuffer;
uniform float u_delayFeedback;
uniform float u_stabTrigger;

void main() {
    vec2 echoUv = vec2(0.5) + (vUv - vec2(0.5)) * 0.985;
    vec3 current = texture(u_currentFrame, vUv).rgb;
    
    vec3 feedback;
    feedback.r = texture(u_feedbackBuffer, echoUv + vec2(0.002, 0.0)).r;
    feedback.g = texture(u_feedbackBuffer, echoUv).g;
    feedback.b = texture(u_feedbackBuffer, echoUv - vec2(0.002, 0.0)).b;
    
    vec3 finalCol = current + feedback * u_delayFeedback * (1.0 + u_stabTrigger * 0.5);
    fragColor = vec4(finalCol, 1.0);
}
