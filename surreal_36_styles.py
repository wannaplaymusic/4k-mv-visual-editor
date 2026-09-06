import hashlib
import random
import cv2
import numpy as np
from PIL import Image

class Surreal36MasterMatrix:
    """
    SAVAP v4.0 終極 36 大超現實與前衛大師風格矩陣引擎
    - 涵蓋 6 大藝術維度 × 6 大流派 = 36 種獨立大師風格
    - 支援 32-bit 確定性 Hash 種子動態擾動（Parametric Jittering）
    - 雙大師風格雜交（36 × 36 = 1296 種混合流派）
    - 深度綁定光影法則（Lighting Logic）、音訊基因映射與多維標籤
    """

    STYLE_CATALOG_36 = {
        # ── 1. 🏛️ 古典與達達超現實 (Classical & Dada Surrealism) ──
        "ernst_engraving": {
            "name": "【恩斯特】古典銅版雕刻 (Max Ernst Engraving)",
            "category": "🏛️ 古典與達達超現實",
            "lighting": "High-contrast etched cross-hatch",
            "tags": ["style:ernst", "texture:engraving", "era:classical", "motion:grafting"]
        },
        "dali_soft_melting": {
            "name": "【達利】偏執狂軟性流體 (Dalí Soft Melting)",
            "category": "🏛️ 古典與達達超現實",
            "lighting": "Bilateral smooth liquefaction with gravity collapse",
            "tags": ["style:dali", "texture:soft_fluid", "era:classical", "motion:squash_melt"]
        },
        "magritte_negative_portal": {
            "name": "【馬格利特】空間負空間掏空 (Magritte Negative Portal)",
            "category": "🏛️ 古典與達達超現實",
            "lighting": "Canny silhouette portal mask to dynamic sky",
            "tags": ["style:magritte", "texture:portal_cloud", "era:classical", "motion:orbital_gravity"]
        },
        "man_ray_solarization": {
            "name": "【曼·雷】暗房中途曝光銀鹽 (Man Ray Solarization)",
            "category": "🏛️ 古典與達達超現實",
            "lighting": "Sabattier S-curve metallic inversion flash",
            "tags": ["style:man_ray", "texture:sabattier", "era:classical", "motion:high_flash"]
        },
        "chirico_deep_shadow": {
            "name": "【基里訶】形而上幽靈長影 (Chirico Deep Shadow)",
            "category": "🏛️ 古典與達達超現實",
            "lighting": "Metaphysical twilight harsh elongated shadows",
            "tags": ["style:chirico", "texture:deep_shadow", "era:classical", "motion:slow_drift"]
        },
        "miro_biomorphic": {
            "name": "【米羅】有機生物符號懸浮 (Miró Biomorphic)",
            "category": "🏛️ 古典與達達超現實",
            "lighting": "Flat primary color biomorphic quantization",
            "tags": ["style:miro", "texture:biomorphic_flat", "era:classical", "motion:satellite_orbit"]
        },

        # ── 2. 🎭 荒誕木偶與蒙太奇 (Absurdist & Collage Montages) ──
        "gilliam_puppetry": {
            "name": "【吉列姆】達達荒誕超調木偶 (Gilliam Puppetry)",
            "category": "🎭 荒誕木偶與蒙太奇",
            "lighting": "Heavy black cutout outline with mechanical springs",
            "tags": ["style:gilliam", "texture:renaissance_cutout", "era:montage", "motion:overshoot_spring"]
        },
        "hockney_joiners": {
            "name": "【霍克尼】多視角時空切片 (Hockney Joiners)",
            "category": "🎭 荒誕木偶與蒙太奇",
            "lighting": "Polaroid multi-angle fragmented photographic grid",
            "tags": ["style:hockney", "texture:photo_joiner", "era:montage", "motion:cubist_slice"]
        },
        "hoch_photomontage": {
            "name": "【漢娜·霍克】報紙半色調蒙太奇 (Höch Photomontage)",
            "category": "🎭 荒誕木偶與蒙太奇",
            "lighting": "Newsprint coarse Ben-Day / Halftone dot matrix",
            "tags": ["style:hoch", "texture:halftone_newsprint", "era:montage", "motion:mechanical_staccato"]
        },
        "varo_alchemy": {
            "name": "【瓦羅】神秘煉金術羊皮紙 (Varo Alchemy)",
            "category": "🎭 荒誕木偶與蒙太奇",
            "lighting": "Warm aged parchment with fine micro-scratches",
            "tags": ["style:varo", "texture:alchemical_vellum", "era:montage", "motion:subtle_levitation"]
        },
        "carrington_mystic": {
            "name": "【卡靈頓】凱爾特秘境神話 (Carrington Mystic)",
            "category": "🎭 荒誕木偶與蒙太奇",
            "lighting": "Nocturnal luminescent green-amber egg tempera",
            "tags": ["style:carrington", "texture:tempera_mystic", "era:montage", "motion:ghostly_orbit"]
        },
        "warhol_pop_screen": {
            "name": "【沃荷】普普雙色絲網印刷 (Warhol Pop Screen)",
            "category": "🎭 荒誕木偶與蒙太奇",
            "lighting": "Misaligned dual-color fluorescent silkscreen",
            "tags": ["style:warhol", "texture:pop_silkscreen", "era:montage", "motion:strobe_pulse"]
        },

        # ── 3. 🏯 東方水墨與版畫美學 (Eastern Ink & Woodblock) ──
        "ukiyoe_waves": {
            "name": "【浮世繪】木刻同心波紋 (Ukiyo-e Waves)",
            "category": "🏯 東方水墨與版畫美學",
            "lighting": "Hokusai concentric wave field contours",
            "tags": ["style:ukiyoe", "texture:woodblock_wave", "era:eastern", "motion:wave_ripple"]
        },
        "sumi_e_wash": {
            "name": "【水墨宣紙】濃淡潑墨暈染 (Sumi-e Wash)",
            "category": "🏯 東方水墨與版畫美學",
            "lighting": "Diffused atmospheric ink bleed on rice paper",
            "tags": ["style:sumie", "texture:ink_wash", "era:eastern", "motion:fluid_drift"]
        },
        "hasui_shin_hanga": {
            "name": "【川瀨巴水】新版畫夜雨微光 (Shin-Hanga Glow)",
            "category": "🏯 東方水墨與版畫美學",
            "lighting": "Misty nocturnal blue with warm lantern glow",
            "tags": ["style:shinhanga", "texture:woodcut_mist", "era:eastern", "motion:gentle_rain"]
        },
        "dunhuang_fresco": {
            "name": "【敦煌壁畫】礦物泥金斑駁 (Dunhuang Mineral Fresco)",
            "category": "🏯 東方水墨與版畫美學",
            "lighting": "Lapis lazuli and gold leaf cracked mineral patina",
            "tags": ["style:dunhuang", "texture:mineral_fresco", "era:eastern", "motion:floating_apsaras"]
        },
        "korean_dancheong": {
            "name": "【丹青幾何】五色木構紋樣 (Dancheong Pentachrome)",
            "category": "🏯 東方水墨與版畫美學",
            "lighting": "Architectural traditional pentachromatic bands",
            "tags": ["style:dancheong", "texture:pentachrome", "era:eastern", "motion:kaleidoscope"]
        },
        "ito_junji_spiral": {
            "name": "【伊藤潤二】恐怖細密螺旋排線 (Junji Ito Spiral)",
            "category": "🏯 東方水墨與版畫美學",
            "lighting": "Dense macabre pen-ink concentric whirlpools",
            "tags": ["style:junji_ito", "texture:macabre_spiral", "era:eastern", "motion:spiral_vortex"]
        },

        # ── 4. 🎬 傳奇動畫與動漫美學 (Anime & Cinematic Animation) ──
        "shinkai_radiant": {
            "name": "【新海誠】極致光學浪漫光斑 (Shinkai Radiant Lens)",
            "category": "🎬 傳奇動畫與動漫美學",
            "lighting": "Radial volumetric bloom and chromatic lens flare",
            "tags": ["style:shinkai", "texture:volumetric_bloom", "era:anime", "motion:lens_flare"]
        },
        "otomo_cyberpunk_ink": {
            "name": "【大友克洋】阿基拉機械重墨 (Akira Heavy Inking)",
            "category": "🎬 傳奇動畫與動漫美學",
            "lighting": "Dense mechanical crosshatch with hard shadow cuts",
            "tags": ["style:otomo", "texture:heavy_line_ink", "era:anime", "motion:kinetic_impact"]
        },
        "ghibli_pastoral": {
            "name": "【吉卜力】水彩田園手繪質感 (Ghibli Gouache)",
            "category": "🎬 傳奇動畫與動漫美學",
            "lighting": "Warm sunny gouache with soft painted edges",
            "tags": ["style:ghibli", "texture:gouache_handdrawn", "era:anime", "motion:wind_breeze"]
        },
        "manga_speedline": {
            "name": "【熱血日漫】速度線與衝擊波 (Manga Action Speedlines)",
            "category": "🎬 傳奇動畫與動漫美學",
            "lighting": "Explosive radial speedlines and comic screentones",
            "tags": ["style:manga", "texture:radial_speedlines", "era:anime", "motion:explosive_zoom"]
        },
        "paprika_parade": {
            "name": "【今敏·紅辣椒】夢境狂歡色彩溢流 (Kon Paprika Parade)",
            "category": "🎬 傳奇動畫與動漫美學",
            "lighting": "Surrealistic saturated color shift and kaleidoscopic warp",
            "tags": ["style:kon", "texture:color_overflow", "era:anime", "motion:parade_paranoia"]
        },
        "retro_cel_animation": {
            "name": "【80s 賽璐珞】復古電視色差 (80s TV Cel Animation)",
            "category": "🎬 傳奇動畫與動漫美學",
            "lighting": "CRT scanlines, chromatic aberration and analog tape noise",
            "tags": ["style:cel_80s", "texture:crt_chroma", "era:anime", "motion:analog_jitter"]
        },

        # ── 5. ⚡ 當代數位與賽博前衛 (Cyber & Digital Glitch) ──
        "pixel_sort_glitch": {
            "name": "【故障藝術】像素分選拉絲 (Data-Mosh & Pixel Sort)",
            "category": "⚡ 當代數位與賽博前衛",
            "lighting": "Brightness-sorted horizontal glitch displacement",
            "tags": ["style:glitch", "texture:pixel_sort", "era:cyber", "motion:data_mosh"]
        },
        "blueprint_cad": {
            "name": "【工程藍圖】普魯士藍等高線 (Cyanotype & Blueprint CAD)",
            "category": "⚡ 當代數位與賽博前衛",
            "lighting": "Prussian blue with glowing vector vector lines",
            "tags": ["style:blueprint", "texture:cyanotype_cad", "era:cyber", "motion:laser_scan"]
        },
        "thermal_infrared": {
            "name": "【紅外視界】生物熱感霓虹 (Thermal Infrared Spectrum)",
            "category": "⚡ 當代數位與賽博前衛",
            "lighting": "Inferno / Magma false-color thermal heatmaps",
            "tags": ["style:thermal", "texture:inferno_heat", "era:cyber", "motion:color_cycle"]
        },
        "voronoi_shatter": {
            "name": "【晶體折射】泰森多邊形碎裂 (Voronoi Crystal Shatter)",
            "category": "⚡ 當代數位與賽博前衛",
            "lighting": "Prismatic crystal facet refraction and edge glow",
            "tags": ["style:voronoi", "texture:crystal_prism", "era:cyber", "motion:shatter_burst"]
        },
        "synthwave_3d": {
            "name": "【賽博網格】80s 向量地平線 (Synthwave 3D Wireframe)",
            "category": "⚡ 當代數位與賽博前衛",
            "lighting": "Neon magenta edge glow against deep midnight purple",
            "tags": ["style:synthwave", "texture:wireframe_neon", "era:cyber", "motion:grid_scroll"]
        },
        "hologram_scanline": {
            "name": "【全息投影】立體干涉條紋 (Holographic Scanline)",
            "category": "⚡ 當代數位與賽博前衛",
            "lighting": "Cyan/green interference fringes with vertical scanlines",
            "tags": ["style:hologram", "texture:interference_fringe", "era:cyber", "motion:scan_pulse"]
        },

        # ── 6. 🔮 物質材質與實驗工藝 (Material & Experimental Textures) ──
        "liquid_chrome": {
            "name": "【液態金屬】流動高光水銀 (Liquid Metal Chrome)",
            "category": "🔮 物質材質與實驗工藝",
            "lighting": "Mirror specular reflection with mercury ripple",
            "tags": ["style:chrome", "texture:liquid_mercury", "era:material", "motion:mercury_flow"]
        },
        "risograph_riso": {
            "name": "【孔版印刷】錯位豆墨顆粒 (Risograph Print)",
            "category": "🔮 物質材質與實驗工藝",
            "lighting": "Soy ink stipple texture with slight registration error",
            "tags": ["style:riso", "texture:riso_grain", "era:material", "motion:print_stutter"]
        },
        "cyanotype_sunprint": {
            "name": "【古典日光印】植物日光藍曬 (Cyanotype Sunprint)",
            "category": "🔮 物質材質與實驗工藝",
            "lighting": "Iron-salt Prussian blue photogram transparency",
            "tags": ["style:cyanotype", "texture:sunprint_blue", "era:material", "motion:solar_fade"]
        },
        "stained_glass_gothic": {
            "name": "【哥德花窗】彩色鑲嵌玻璃 (Gothic Stained Glass)",
            "category": "🔮 物質材質與實驗工藝",
            "lighting": "Heavy black lead cames with radiant jewel-tone transmission",
            "tags": ["style:stained_glass", "texture:lead_came_glass", "era:material", "motion:light_refraction"]
        },
        "acid_psychedelic_oil": {
            "name": "【迷幻油水】60s 浮動油膜擴散 (Acid Liquid Light Show)",
            "category": "🔮 物質材質與實驗工藝",
            "lighting": "Organic immiscible dye swirl with rainbow dispersion",
            "tags": ["style:psychedelic", "texture:oil_swirl", "era:material", "motion:swirling_flow"]
        },
        "raw_alpha": {
            "name": "【原始無損】無濾鏡透明去背 (Raw Alpha Pure)",
            "category": "🔮 物質材質與實驗工藝",
            "lighting": "Pure unaltered photographic alpha transparency",
            "tags": ["style:raw", "texture:photographic", "era:material", "motion:natural"]
        }
    }

    @classmethod
    def get_style_names_list(cls) -> list:
        """獲取 36 大風格分組下拉選單清單"""
        items = ["🎲 隨機大師風格 (AI Auto-Match)"]
        curr_cat = None
        for k, v in cls.STYLE_CATALOG_36.items():
            if v["category"] != curr_cat:
                curr_cat = v["category"]
                items.append(f"─── {curr_cat} ───")
            items.append(v["name"])
        return items

    @classmethod
    def get_deterministic_params(cls, seed_string: str) -> dict:
        """32-bit Hash Seed 參數化微調 (Parametric Jittering)"""
        hash_val = int(hashlib.md5(seed_string.encode('utf-8')).hexdigest()[:8], 16)
        rng = random.Random(hash_val)
        return {
            "seed_int": hash_val % 1000000,
            "hatch_density": rng.randint(6, 32),
            "grain_amount": rng.uniform(0.08, 0.45),
            "edge_thresh1": rng.randint(20, 60),
            "edge_thresh2": rng.randint(90, 160),
            "bloom_intensity": rng.uniform(1.1, 1.6),
            "chroma_shift": rng.randint(2, 8),
            "tint_warmth": rng.uniform(0.85, 1.25)
        }

    @classmethod
    def match_best_style(cls, keyword: str) -> str:
        """AI 語義自動適配 36 大流派"""
        kw = keyword.lower()
        mapping_rules = [
            (["motor", "engine", "gear", "machine", "blueprint", "robot", "schematic"], "blueprint_cad"),
            (["bust", "statue", "sculpture", "marble", "classical", "column"], "dali_soft_melting"),
            (["apple", "hat", "birdcage", "window", "pipe", "curtain"], "magritte_negative_portal"),
            (["mannequin", "prism", "violin", "camera", "lens", "shadow"], "man_ray_solarization"),
            (["akira", "cyberpunk", "gun", "armor", "motorcycle", "blade"], "otomo_cyberpunk_ink"),
            (["sky", "cloud", "sunlight", "horizon", "radiant", "meteor", "star"], "shinkai_radiant"),
            (["ink", "bamboo", "dragon", "mountain", "ocean", "zen"], "sumi_e_wash"),
            (["wave", "fish", "woodblock", "tsunami", "koi"], "ukiyoe_waves"),
            (["spiral", "horror", "eye", "whirlpool", "spider"], "ito_junji_spiral"),
            (["fresco", "gold", "buddha", "temple", "gilded"], "dunhuang_fresco"),
            (["chrome", "mercury", "liquid", "metal", "silver", "fluid"], "liquid_chrome"),
            (["glass", "cathedral", "gothic", "saint", "church"], "stained_glass_gothic"),
            (["comic", "pop", "newspaper", "halftone", "poster"], "hoch_photomontage"),
            (["glitch", "pixel", "data", "cyber", "terminal", "code"], "pixel_sort_glitch")
        ]

        for keywords, style_key in mapping_rules:
            if any(w in kw for w in keywords):
                return style_key

        keys = list(cls.STYLE_CATALOG_36.keys())
        return keys[sum(ord(c) for c in kw) % (len(keys) - 1)]
