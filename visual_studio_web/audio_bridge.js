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
    window.chordHue = 180;
    window.currentChordColor = '#0ea5e9';
    window.stereoWidth = 0.5;
    window.live_centroid = 1000;
    window.simulatedMouseX = 540;

    // 通用音訊參數代理 (Universal Audio Proxy)
    window.audioParams = new Proxy({}, {
        get: function(target, prop) {
            if (prop === 'bass' || prop === 'sub_bass' || prop === 'low') return window.sub_bass || window.bass || 0.5;
            if (prop === 'mid' || prop === 'voice' || prop === 'vocal') return window.mid || 0.5;
            if (prop === 'high' || prop === 'treble') return window.high || 0.5;
            if (prop === 'beat' || prop === 'isBeat') return window.isBeat || false;
            if (prop === 'energy' || prop === 'beatEnergy') return window.beatEnergy || 0.5;
            if (prop === 'chordColor' || prop === 'chordHex') return window.currentChordColor || '#0ea5e9';
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
        window.isBeat = Boolean(data.is_beat);
        window.beatEnergy = data.bass || 0.5;
        window.chordHue = (typeof data.chord_hue !== 'undefined') ? data.chord_hue : window.chordHue;
        window.currentChordColor = data.chord_color || window.currentChordColor;
        
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
