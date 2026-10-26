/**
 * Ambient Color Guard (SAVAP v3.2 Auteur Visual Sandbox Color Proxy)
 * ====================================================================
 * 專為 Ambient / Drone / Meditative 曲風打造的運行時色彩攔截與重塑代理：
 * 1. 攔截 p5.js 與 Canvas 2D 底層繪圖 API (fill, stroke, background, color, fillStyle, strokeStyle)
 * 2. 杜絕個別視覺模組中寫死的高飽和原色、螢光色與刺眼閃爍
 * 3. 支援分鏡級別臨時指定調色盤 (Per-Shot Module Palette Dynamic Override)
 * 4. 具備純淨莫蘭迪 (Morandi) 柔化、Turrell 光場色溫調和與感知色度夾持
 */

(function(window) {
  'use strict';

  if (window.__ambientColorGuardInjected) {
    return;
  }
  window.__ambientColorGuardInjected = true;

  // 全域 Ambient 色彩守護組態
  const config = {
    enabled: false,             // 預設關閉，由 Ambient 曲風或導演系統動態激活
    chromaLimit: 0.075,         // 感知等距色度上限 (約相當於 HSL S <= 38%)
    maxSaturation: 0.38,        // HSL 飽和度上限 (0.0 ~ 1.0)
    maxLightness: 0.88,         // 抑制爆發性純白高光 (0.0 ~ 1.0)
    minLightness: 0.08,         // 抑制死黑 (0.0 ~ 1.0)
    palette: null,              // 導演系統指派的當前調色盤 (Hex 色系陣列)
    paletteRgb: null,           // 解析後的 RGB 陣列
    targetHue: null,            // 導演指定的主色相 (0 ~ 360)
    mode: 'clamp_and_blend',    // 'clamp_only' | 'clamp_and_blend' | 'snap_to_palette' | 'monochrome'
    blendRatio: 0.45            // 模組原色與導演調色盤的混合權重
  };

  window.__AMBIENT_COLOR_GUARD = config;

  // 1. 色彩解析與轉換小工具 (RGB <-> HSL)
  function parseRgbFromArgs(args) {
    if (!args || args.length === 0) return null;
    let r = 0, g = 0, b = 0, a = 255;

    if (args.length === 1) {
      const v = args[0];
      if (typeof v === 'number') {
        r = g = b = v;
      } else if (typeof v === 'string') {
        const parsed = parseCssColor(v);
        if (parsed) return parsed;
      } else if (typeof v === 'object' && v !== null && v.levels) {
        // p5.Color 物件
        return { r: v.levels[0], g: v.levels[1], b: v.levels[2], a: v.levels[3] };
      }
    } else if (args.length === 2) {
      if (typeof args[0] === 'number') {
        r = g = b = args[0];
        a = args[1];
      }
    } else if (args.length >= 3) {
      if (typeof args[0] === 'number') {
        r = args[0];
        g = args[1];
        b = args[2];
        if (args.length >= 4 && typeof args[3] === 'number') {
          a = args[3];
        }
      }
    }
    return { r, g, b, a };
  }

  function parseCssColor(str) {
    str = String(str).trim();
    if (str.startsWith('#')) {
      let hex = str.slice(1);
      if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
      if (hex.length === 6) {
        const num = parseInt(hex, 16);
        return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255, a: 255 };
      }
    } else if (str.startsWith('rgb')) {
      const match = str.match(/rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s\/]+([\d.]+))?\)/);
      if (match) {
        return {
          r: parseInt(match[1], 10),
          g: parseInt(match[2], 10),
          b: parseInt(match[3], 10),
          a: match[4] !== undefined ? parseFloat(match[4]) * (match[4].includes('%') ? 2.55 : (parseFloat(match[4]) <= 1 ? 255 : 1)) : 255
        };
      }
    }
    return null;
  }

  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0, l = (max + min) / 2;

    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r: h = (g - b) / d + (g < b ? 6 : 0); break;
        case g: h = (b - r) / d + 2; break;
        case b: h = (r - g) / d + 4; break;
      }
      h /= 6;
    }
    return { h: h * 360, s, l };
  }

  function hslToRgb(h, s, l) {
    h = (h % 360 + 360) % 360 / 360;
    let r, g, b;
    if (s === 0) {
      r = g = b = l;
    } else {
      const hue2rgb = (p, q, t) => {
        if (t < 0) t += 1;
        if (t > 1) t -= 1;
        if (t < 1/6) return p + (q - p) * 6 * t;
        if (t < 1/2) return q;
        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
        return p;
      };
      const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
      const p = 2 * l - q;
      r = hue2rgb(p, q, h + 1/3);
      g = hue2rgb(p, q, h);
      b = hue2rgb(p, q, h - 1/3);
    }
    return {
      r: Math.round(r * 255),
      g: Math.round(g * 255),
      b: Math.round(b * 255)
    };
  }

  // 2. 核心重塑函數：明度分層雙色溫景深重映射 (Luminance-Stratified Dual-Pole Chromatic Depth v2.0)
  function transformColorForAmbient(r, g, b, a, isBackground) {
    if (!config.enabled) return { r, g, b, a };

    const hsl = rgbToHsl(r, g, b);

    // 飽和度壓制至莫蘭迪/霧化安全邊界
    let targetS = Math.min(hsl.s, isBackground ? 0.18 : config.maxSaturation);
    let targetL = Math.max(config.minLightness, Math.min(config.maxLightness, hsl.l));
    let targetH = hsl.h;

    // 若導演系統指派了調色盤 (Luminance-Stratified Dual-Pole Palette Blend)
    if (config.paletteRgb && config.paletteRgb.length > 0) {
      if (config.mode === 'snap_to_palette' || config.mode === 'clamp_and_blend') {
        const palLen = config.paletteRgb.length;
        const isShadowLayer = Boolean(isBackground || targetL < 0.45);
        // 暗部/背景錨定調色盤前半深邃冷色極 (Shadow Pole)，亮部前景錨定調色盤後半溫潤霧光極 (Highlight Pole)
        const startIdx = isShadowLayer ? 0 : Math.floor(palLen / 2);
        const endIdx = isShadowLayer ? Math.max(1, Math.ceil(palLen / 2)) : palLen;

        let bestColor = config.paletteRgb[startIdx];
        let minDiff = 999;
        for (let i = startIdx; i < endIdx; i++) {
          const palHsl = config.paletteRgb[i].hsl;
          const diff = Math.abs(palHsl.l - targetL);
          if (diff < minDiff) {
            minDiff = diff;
            bestColor = config.paletteRgb[i];
          }
        }

        if (config.mode === 'snap_to_palette') {
          return { r: bestColor.r, g: bestColor.g, b: bestColor.b, a };
        } else {
          // 明度分層雙權重插值：背景/暗部強融合 (0.68/0.62) 退後至深邃背景，前景高光溫柔融合 (0.48) 保留立體空氣景深
          const ratio = isBackground ? 0.68 : (isShadowLayer ? 0.62 : 0.48);
          const blendedR = Math.round(r * (1 - ratio) + bestColor.r * ratio);
          const blendedG = Math.round(g * (1 - ratio) + bestColor.g * ratio);
          const blendedB = Math.round(b * (1 - ratio) + bestColor.b * ratio);
          // 再次安全夾取以防原色過強
          const reHsl = rgbToHsl(blendedR, blendedG, blendedB);
          const clamped = hslToRgb(reHsl.h, Math.min(reHsl.s, isBackground ? 0.18 : config.maxSaturation), Math.min(config.maxLightness, reHsl.l));
          return { r: clamped.r, g: clamped.g, b: clamped.b, a };
        }
      }
    }

    // 若設定了目標色相微漂移
    if (config.targetHue !== null) {
      targetH = targetH * 0.4 + config.targetHue * 0.6;
    }

    const clampedRgb = hslToRgb(targetH, targetS, targetL);
    return { r: clampedRgb.r, g: clampedRgb.g, b: clampedRgb.b, a };
  }

  // 3. Monkey-Patching p5.js 色彩 API（支援 RGB 與 HSB / HSL 模式無損攔截）
  function patchP5ColorAPI() {
    if (typeof p5 === 'undefined' || !p5.prototype) return;

    const _origColor = p5.prototype.color;
    const _origFill = p5.prototype.fill;
    const _origStroke = p5.prototype.stroke;
    const _origBackground = p5.prototype.background;

    function resolveAndTransformP5Color(ctx, args, isBackground) {
      if (_origColor) {
        try {
          const c = _origColor.apply(ctx, args);
          if (c && Array.isArray(c.levels) && c.levels.length >= 3) {
            const trans = transformColorForAmbient(c.levels[0], c.levels[1], c.levels[2], c.levels[3] !== undefined ? c.levels[3] : 255, isBackground);
            c.levels[0] = trans.r;
            c.levels[1] = trans.g;
            c.levels[2] = trans.b;
            if (Array.isArray(c._array) && c._array.length >= 3) {
              c._array[0] = trans.r / 255;
              c._array[1] = trans.g / 255;
              c._array[2] = trans.b / 255;
            }
            return { p5Color: c, trans };
          }
        } catch (e) {}
      }
      const parsed = parseRgbFromArgs(args);
      if (parsed) {
        const trans = transformColorForAmbient(parsed.r, parsed.g, parsed.b, parsed.a, isBackground);
        return { p5Color: null, trans };
      }
      return null;
    }

    p5.prototype.fill = function(...args) {
      if (!config.enabled && !window.isAmbientMode) return _origFill.apply(this, args);
      const res = resolveAndTransformP5Color(this, args, false);
      if (res) {
        if (res.p5Color) return _origFill.call(this, res.p5Color);
        return _origFill.call(this, res.trans.r, res.trans.g, res.trans.b, res.trans.a);
      }
      return _origFill.apply(this, args);
    };

    p5.prototype.stroke = function(...args) {
      if (!config.enabled && !window.isAmbientMode) return _origStroke.apply(this, args);
      const res = resolveAndTransformP5Color(this, args, false);
      if (res) {
        if (res.p5Color) return _origStroke.call(this, res.p5Color);
        return _origStroke.call(this, res.trans.r, res.trans.g, res.trans.b, res.trans.a);
      }
      return _origStroke.apply(this, args);
    };

    p5.prototype.background = function(...args) {
      if (!config.enabled && !window.isAmbientMode) return _origBackground.apply(this, args);
      const res = resolveAndTransformP5Color(this, args, true);
      if (res) {
        if (res.p5Color) return _origBackground.call(this, res.p5Color);
        return _origBackground.call(this, res.trans.r, res.trans.g, res.trans.b, res.trans.a);
      }
      return _origBackground.apply(this, args);
    };

    p5.prototype.color = function(...args) {
      if (!config.enabled && !window.isAmbientMode) return _origColor.apply(this, args);
      const res = resolveAndTransformP5Color(this, args, false);
      if (res) {
        if (res.p5Color) return res.p5Color;
        return _origColor.call(this, res.trans.r, res.trans.g, res.trans.b, res.trans.a);
      }
      return _origColor.apply(this, args);
    };
  }

  // 4. Monkey-Patching Canvas 2D API (守護非 p5.js 或混合原生 Canvas 繪圖、漸層與陰影發光)
  function patchCanvas2DAPI() {
    if (typeof CanvasRenderingContext2D !== 'undefined' && CanvasRenderingContext2D.prototype) {
      ['fillStyle', 'strokeStyle', 'shadowColor'].forEach(propName => {
        const desc = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, propName);
        if (desc && desc.set) {
          const _origSet = desc.set;
          Object.defineProperty(CanvasRenderingContext2D.prototype, propName, {
            set: function(val) {
              if ((config.enabled || window.isAmbientMode) && typeof val === 'string') {
                const parsed = parseCssColor(val);
                if (parsed) {
                  const trans = transformColorForAmbient(parsed.r, parsed.g, parsed.b, parsed.a, false);
                  val = `rgba(${trans.r}, ${trans.g}, ${trans.b}, ${(trans.a / 255).toFixed(3)})`;
                }
              }
              return _origSet.call(this, val);
            },
            get: desc.get,
            configurable: true
          });
        }
      });
    }

    if (typeof CanvasGradient !== 'undefined' && CanvasGradient.prototype && CanvasGradient.prototype.addColorStop) {
      const _origAddColorStop = CanvasGradient.prototype.addColorStop;
      CanvasGradient.prototype.addColorStop = function(offset, colorStr) {
        if ((config.enabled || window.isAmbientMode) && typeof colorStr === 'string') {
          const parsed = parseCssColor(colorStr);
          if (parsed) {
            const trans = transformColorForAmbient(parsed.r, parsed.g, parsed.b, parsed.a, false);
            colorStr = `rgba(${trans.r}, ${trans.g}, ${trans.b}, ${(trans.a / 255).toFixed(3)})`;
          }
        }
        return _origAddColorStop.call(this, offset, colorStr);
      };
    }
  }

  // 5. 對外介面：供 Qt Python 或導演系統隨時呼叫
  window.setAmbientColorOverride = function(opts) {
    if (!opts) return;
    if (typeof opts.enabled === 'boolean') config.enabled = opts.enabled;
    if (typeof opts.maxSaturation === 'number') config.maxSaturation = opts.maxSaturation;
    if (typeof opts.chromaLimit === 'number') config.chromaLimit = opts.chromaLimit;
    if (typeof opts.mode === 'string') config.mode = opts.mode;
    if (typeof opts.targetHue === 'number') config.targetHue = opts.targetHue;
    if (typeof opts.blendRatio === 'number') config.blendRatio = opts.blendRatio;

    if (Array.isArray(opts.palette)) {
      config.palette = opts.palette;
      config.paletteRgb = opts.palette.map(c => {
        const rgb = parseCssColor(c) || { r: 120, g: 140, b: 160, a: 255 };
        return {
          ...rgb,
          hsl: rgbToHsl(rgb.r, rgb.g, rgb.b)
        };
      });
    }
  };

  // 立即掛載補丁
  patchP5ColorAPI();
  patchCanvas2DAPI();

  // 若 DOM 載入時 p5 尚未初始化，再次嘗試掛載
  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
      patchP5ColorAPI();
      patchCanvas2DAPI();
    });
  }
})(typeof window !== 'undefined' ? window : this);
