// OpenSimplexNoise Safe Fallback Stub
if (typeof OpenSimplexNoise === 'undefined') {
    window.OpenSimplexNoise = class {
        constructor(seed = 0) { this.seed = seed; }
        eval2D(x, y) { return Math.sin(x * 0.1) * Math.cos(y * 0.1); }
        eval3D(x, y, z) { return Math.sin(x * 0.1 + z) * Math.cos(y * 0.1); }
        eval4D(x, y, z, w) { return Math.sin(x * 0.1 + w) * Math.cos(y * 0.1 + z); }
    };
}