/**
 * VisualStudio Pro Universal Audio-Reactive Bridge
 * 兼容專案中 1496 個模組的所有音訊聯覺變數
 */

(function() {
    window.isBeat = false;
    window.beatEnergy = 0.5;
    window.audioLow = 0.5;
    window.audioMid = 0.5;
    window.audioHigh = 0.5;
    window.sub_bass = 0.5;
    window.bass = 0.5;
    window.mid = 0.5;
    window.high = 0.5;
    // 4-Stem 獨立神經/物理音軌
    window.drums = 0.5;
    window.vocals = 0.5;
    window.stem_bass = 0.5;
    window.other = 0.5;
    // OKLCH 感知均勻色彩與五度圈
    window.chordHue = 180;
    window.currentChordColor = '#0ea5e9';
    window.oklchPrimary = '#38bdf8';
    window.oklchAccent = '#f43f5e';
    window.stereoWidth = 0.5;
    window.live_centroid = 1000;
    window.simulatedMouseX = 540;

    // 通用音訊參數代理 (Universal Audio Proxy)
    window.audioParams = new Proxy({}, {
        get: function(target, prop) {
            if (prop === 'bass' || prop === 'sub_bass' || prop === 'low') return window.sub_bass || window.bass || 0.5;
            if (prop === 'mid' || prop === 'voice' || prop === 'vocal') return window.vocals || window.mid || 0.5;
            if (prop === 'high' || prop === 'treble') return window.high || 0.5;
            if (prop === 'drums' || prop === 'drum' || prop === 'perc') return window.drums || 0.5;
            if (prop === 'vocals' || prop === 'lead') return window.vocals || window.mid || 0.5;
            if (prop === 'other' || prop === 'ambient') return window.other || 0.5;
            if (prop === 'beat' || prop === 'isBeat') return window.isBeat || false;
            if (prop === 'energy' || prop === 'beatEnergy') return window.beatEnergy || 0.5;
            if (prop === 'chordColor' || prop === 'chordHex') return window.currentChordColor || window.oklchPrimary || '#0ea5e9';
            if (prop === 'oklchPrimary') return window.oklchPrimary || '#38bdf8';
            if (prop === 'oklchAccent') return window.oklchAccent || '#f43f5e';
            if (prop === 'chordHue') return window.chordHue || 180;
            return target[prop] || 0.5;
        }
    });

    // 提供給 Python 調用的即時聲學特徵更新函數
    window.updateAudioTelemetry = function(data) {
        if (!data) return;
        window.sub_bass = (typeof data.sub_bass !== 'undefined') ? data.sub_bass : window.sub_bass;
        window.bass = (typeof data.bass !== 'undefined') ? data.bass : window.bass;
        window.mid = (typeof data.mid !== 'undefined') ? data.mid : window.mid;
        window.high = (typeof data.high !== 'undefined') ? data.high : window.high;
        // 4-Stem 注入
        window.drums = (typeof data.drums !== 'undefined') ? data.drums : window.drums;
        window.vocals = (typeof data.vocals !== 'undefined') ? data.vocals : window.vocals;
        window.stem_bass = (typeof data.stem_bass !== 'undefined') ? data.stem_bass : window.stem_bass;
        window.other = (typeof data.other !== 'undefined') ? data.other : window.other;
        window.isBeat = Boolean(data.is_beat);
        window.beatEnergy = (typeof data.drums !== 'undefined') ? (data.drums * 0.6 + (data.bass || 0.5) * 0.4) : (data.bass || 0.5);
        window.chordHue = (typeof data.chord_hue !== 'undefined') ? data.chord_hue : window.chordHue;
        window.currentChordColor = data.chord_color || window.currentChordColor;
        window.oklchPrimary = data.oklch_primary || window.oklchPrimary;
        window.oklchAccent = data.oklch_accent || window.oklchAccent;
        
        window.audioLow = window.sub_bass;
        window.audioMid = window.mid;
        window.audioHigh = window.high;
        window.simulatedMouseX = (window.sub_bass || 0.5) * (window.innerWidth || 1080);
    };

    // AST 熱修補支援函數
    window.updateVisualParam = function(paramName, paramVal) {
        window[paramName] = paramVal;
    };

    // 輔助聯覺函數
    window.getHarmonicColor = function(offsetDeg, alpha) {
        offsetDeg = offsetDeg || 0;
        alpha = (typeof alpha !== 'undefined') ? alpha : 1.0;
        let h = ((window.chordHue || 0) + offsetDeg) % 360;
        return `hsla(${Math.round(h)}, 80%, 55%, ${alpha})`;
    };

    window.getAudioPulse = function(scale) {
        scale = (typeof scale !== 'undefined') ? scale : 1.0;
        return 1.0 + (window.sub_bass || 0.5) * 0.4 * scale + (window.isBeat ? 0.3 * scale : 0.0);
    };

    // 重拍手動觸發
    window.triggerBeat = function() {
        window.isBeat = true;
        window.sub_bass = 1.0;
        window.bass = 1.0;
        setTimeout(function() {
            window.isBeat = false;
        }, 120);
    };

    console.log("[AudioBridge] Universal Audio-Reactive Bridge Initialized.");
})();
