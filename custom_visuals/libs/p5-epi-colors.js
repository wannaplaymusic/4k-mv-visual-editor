var EpiColorsPckg = (function (exports) {
	'use strict';

	/**
	 * EpiColors Class
	 * A class for managing color palettes and color manipulation.	
	 * 		palettes: Array of color palettes (array of arrays of hex strings)
	 * 		palette: The currently selected palette (array of hex strings)
	 * 		FG: The foreground color 
	 * 		BG: The background color
	 */

	class EpiColors {

		// ========== NetHID: Constructor & Palettes ==========
		constructor(palettes = null) {
			this.palettes = palettes || [
				["#8386f5", "#3d43b4", "#04134b", "#083e12", "#1afe49"],
				["#f887ff", "#de004e", "#860029", "#321450", "#29132e"],
				["#e96d5e", "#ff9760", "#ffe69d", "#6a7e6a", "#393f5f"],
				["#ff124f", "#ff00a0", "#fe75fe", "#7a04eb", "#120458"],
				["#ff6e27", "#fbf665", "#73fffe", "#6287f8", "#383e65"],
				["#7700a6", "#fe00fe", "#defe47", "#00b3fe", "#0016ee"],
				["#63345e", "#ac61b9", "#b7c1de", "#0b468c", "#092047"],
				["#af43be", "#fd8090", "#c4ffff", "#08deea", "#1261d1"],
				["#a0ffe3", "#65dc98", "#8d8980", "#575267", "#222035"],
				["#ff2a6d", "#d1f7ff", "#f5d9e8", "#005678", "#01012b"],
				["#490109", "#d40011", "#fd7495", "#5e4ef8", "#14029a"],
				["#8f704b", "#daae6d", "#89e3f6", "#4d9e9b", "#44786a"],
				["#fff69f", "#fdd870", "#d0902f", "#a15501", "#351409"],
				["#b0acb0", "#e2dddf", "#85ebd9", "#3d898d", "#2f404d"],
				["#ff184c", "#ff577d", "#ffccdc", "#0a9cf5", "#003062"]
			];
			this.getRandomPalette();
		}

	  /**
		 * sets random palette as current palette, defines FG and BG colors
	   * 	@param {boolean} randomize - Wheter to randomize the colors in the palette, dafault is no
		 */
		getRandomPalette(randomize = false) {
			// Select a random palette and convert all colors to p5 color objects
			this.palette = [...random(this.palettes)].map(clr => EpiColors.getColor(clr));
			if (randomize) this.randomizePalette();

			this.FG = random(this.palette);
			this.BG = EpiColors.getAdjustedBrightness(EpiColors.getAdjustedSaturation(this.FG, 1.5), 0.5);
			this.FG = EpiColors.getAdjustedBrightness(EpiColors.getAdjustedSaturation(this.FG, 0.75), 1.25);
		}
	  
	  /**
		 * Randomizes the order of colors in the current palette
		 */
		randomizePalette() {
			this.palette = shuffle(this.palette);
		}

		/**
		 * Converts a color input to a p5 color object if needed; adds alpha optionally
		 * @param {string|number|object} clr - Color value (hex string, int, or p5 color object)
		 * @param {number} alpha - Alpha value (0-255)
		 * @returns {object} p5 color object
		 */
		static getColor(clr, alpha = null) {
			if (typeof clr === 'string' || clr instanceof String || Number.isInteger(clr)) clr = color(clr);
			if (alpha !== null) clr.setAlpha(alpha);
			return clr;
		}

		/**
		 * Returns a random color from the current palette.
		 * @returns {object} p5 color object
		 */
		getRandomClr() {
			return random(this.palette);
		}

		/**
		 * Converts a p5 color object to a hex string (with alpha if not fully opaque).
		 * @param {object} clr - p5 color object
		 * @returns {string} Hex color string (e.g. #RRGGBB or #RRGGBBAA)
		 */
		static convertClr2HexStr(clr) {
			clr = EpiColors.getColor(clr);

			let r = red(clr);
			let g = green(clr);
			let b = blue(clr);
			let a = alpha(clr);

			// Always include RGB
			let hexString = "#" + hex(r, 2) + hex(g, 2) + hex(b, 2);

			// Append alpha only if not fully opaque
			if (a < 255) {
				hexString += hex(a, 2);
			}

			return hexString.toUpperCase();
		}


		/**
		 * Returns a color interpolated between two colors in the palette.
		 * @param {number} f - Interpolation factor (0-1)
		 * @param {Array<string|object>} [arr=null] - Palette array to use (defaults to this.palette)
		 * @returns {object} p5 color object
		 */
		getLerpedColorFromPalette(f, arr = null) {
			if (!arr) arr = this.palette;
			f *= arr.length;
			const c1i = ~~(f);
			const c2i = (c1i + 1) % arr.length;
			const c1 = EpiColors.getColor(arr[c1i]);
			const c2 = EpiColors.getColor(arr[c2i]);
			return lerpColor(c1, c2, fract(f));
		}


		/**
		 * Adjusts the saturation of a color.
		 * @param {string|number|object} clr - Color value (hex string, int, or p5 color object)
		 * @param {number} [f=1] - Saturation factor (0-1: less saturated, >1: more saturated)
		 * @returns {object} p5 color object
		 */
		static getAdjustedSaturation(clr, f = 1) {
			clr = EpiColors.getColor(clr);
			const br = brightness(clr);
			return color(
				constrain(lerp(br, red(clr), f), 0, 255),
				constrain(lerp(br, green(clr), f), 0, 255),
				constrain(lerp(br, blue(clr), f), 0, 255),
			);
		}

		/**
		 * Adjusts the brightness of a color.
		 * @param {string|number|object} clr - Color value (hex string, int, or p5 color object)
		 * @param {number} [f=1] - Brightness factor (0-1: darker, >1: brighter)
		 * @returns {object} p5 color object
		 */
		static getAdjustedBrightness(clr, f = 1) {
			clr = EpiColors.getColor(clr);
			return color(
				constrain(red(clr) * f, 0, 255),
				constrain(green(clr) * f, 0, 255),
				constrain(blue(clr) * f, 0, 255)
			);
		}


		/**
		 * Returns the average color of the current palette, optionally limiting the max channel value.
		 * @param {number} [lmt=255] - Maximum channel value
		 * @returns {object} p5 color object
		 */
		getAverageClr(lmt = 255) {
			const pal = this.palette;
			let s_r = 0, s_g = 0, s_b = 0, s_max;
			for (let clr of pal) {
				clr = EpiColors.getColor(clr);
				s_r += red(clr);
				s_g += green(clr);
				s_b += blue(clr);
			}
			s_r /= pal.length;
			s_g /= pal.length;
			s_b /= pal.length;
			s_max = max(s_r, max(s_g, s_b));
			if (s_max > lmt) {
				const f = lmt / s_max;
				s_r *= f;
				s_g *= f;
				s_b *= f;
			}
			push();
			colorMode(RGB);
			const clr = color(s_r, s_g, s_b);
			pop();
			return clr;
		}
	}

	exports.EpiColors = EpiColors;

	return exports;

})({});
