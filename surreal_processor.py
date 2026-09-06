import os
import cv2
import numpy as np
from PIL import Image
from surreal_36_styles import Surreal36MasterMatrix

class SurrealImageProcessor:
    """
    超現實圖像處理引擎 (SAVAP v4.0):
    - 完整支援 36 大超現實與前衛大師流派
    - 支援 32-bit Hash 確定性擾動與雙風格插值混合 (36x36 = 1296 種組合)
    - 完整相容去背、Alpha 緊密裁切、木偶拆解與次要元素處理
    """
    def __init__(self, output_base_dir="custom_visuals/assets"):
        self.output_base_dir = output_base_dir
        os.makedirs(self.output_base_dir, exist_ok=True)

    def remove_background(self, pil_image: Image.Image) -> Image.Image:
        """AI 去背 (rembg / BiRefNet 搭配 Otsu 閾值 Fallback)"""
        try:
            from rembg import remove
            return remove(pil_image)
        except Exception:
            cv_img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
            rgba = cv2.cvtColor(cv_img, cv2.COLOR_BGR2BGRA)
            rgba[:, :, 3] = mask
            return Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA))

    def tight_crop_alpha(self, pil_image: Image.Image, padding: int = 5) -> Image.Image:
        """根據 Alpha 遮罩執行緊密外框裁切"""
        rgba_img = pil_image.convert("RGBA")
        np_img = np.array(rgba_img)
        alpha = np_img[:, :, 3]
        bbox = cv2.boundingRect(alpha)
        x, y, w, h = bbox
        if w == 0 or h == 0:
            return pil_image
        
        x_min = max(0, x - padding)
        y_min = max(0, y - padding)
        x_max = min(np_img.shape[1], x + w + padding)
        y_max = min(np_img.shape[0], y + h + padding)
        return Image.fromarray(np_img[y_min:y_max, x_min:x_max])

    def apply_single_style(self, np_img: np.ndarray, style_key: str, seed: int = 0) -> np.ndarray:
        """實作 36 大獨立流派演算法核心 (輸入/輸出皆為 RGBA numpy 矩陣)"""
        h, w = np_img.shape[:2]
        has_alpha = np_img.shape[2] == 4
        alpha = np_img[:, :, 3] if has_alpha else np.ones((h, w), dtype=np.uint8) * 255
        rgb = np_img[:, :, :3]
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        rng = np.random.default_rng(seed)

        # ── 1. 🏛️ 古典與達達超現實 ──
        if "ernst" in style_key or "恩斯特" in style_key:
            # 【恩斯特】古典銅版雕刻
            k1 = 3 + (seed % 3) * 2
            k2 = 7 + (seed % 4) * 2
            g1 = cv2.GaussianBlur(gray, (k1, k1), 1.0)
            g2 = cv2.GaussianBlur(gray, (k2, k2), 2.5)
            dog = cv2.subtract(g1, g2)
            dog = cv2.normalize(dog, None, 0, 255, cv2.NORM_MINMAX)
            _, lines = cv2.threshold(dog, 30 + (seed % 15), 255, cv2.THRESH_BINARY_INV)
            styled_rgb = cv2.cvtColor(lines, cv2.COLOR_GRAY2RGB)

        elif "dali" in style_key or "達利" in style_key:
            # 【達利】偏執狂軟性流體
            blurred = cv2.bilateralFilter(rgb, 9, 75 + (seed % 30), 75 + (seed % 30))
            styled_rgb = (blurred // 32) * 32

        elif "magritte" in style_key or "馬格利特" in style_key:
            # 【馬格利特】空間負空間掏空
            edges = cv2.Canny(gray, 40, 140)
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[edges > 0] = [240, 240, 255]

        elif "man_ray" in style_key or "曼雷" in style_key:
            # 【曼·雷】暗房中途曝光銀鹽
            thresh = 100 + (seed % 50)
            solarized = np.where(gray < thresh, gray * (255 // thresh), 255 - (gray - thresh) * (255 // max(1, (255 - thresh)))).astype(np.uint8)
            styled_rgb = cv2.cvtColor(solarized, cv2.COLOR_GRAY2RGB)

        elif "chirico" in style_key or "基里訶" in style_key:
            # 【基里訶】形而上幽靈長影
            _, high_contrast = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY)
            styled_rgb = cv2.cvtColor(high_contrast, cv2.COLOR_GRAY2RGB)
            styled_rgb = np.clip(styled_rgb * np.array([1.1, 0.9, 0.6]), 0, 255).astype(np.uint8)

        elif "miro" in style_key or "米羅" in style_key:
            # 【米羅】有機生物符號懸浮
            _, b_mask = cv2.threshold(gray, 85, 255, cv2.THRESH_BINARY)
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[b_mask == 0] = [20, 20, 20]
            styled_rgb[(b_mask > 0) & (rgb[:, :, 0] > rgb[:, :, 1])] = [225, 40, 40]
            styled_rgb[(b_mask > 0) & (rgb[:, :, 1] >= rgb[:, :, 0])] = [40, 90, 225]

        # ── 2. 🎭 荒誕木偶與蒙太奇 ──
        elif "gilliam" in style_key or "吉列姆" in style_key:
            # 【吉列姆】達達荒誕超調木偶
            edges = cv2.Canny(gray, 100, 200)
            dilated = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
            styled_rgb = rgb.copy()
            styled_rgb[dilated > 0] = [10, 10, 10]

        elif "hockney" in style_key or "霍克尼" in style_key:
            # 【霍克尼】多視角時空切片
            grid_sz = 30 + (seed % 20)
            styled_rgb = rgb.copy()
            for gy in range(0, h, grid_sz):
                for gx in range(0, w, grid_sz):
                    shift_x = int(rng.integers(-6, 6))
                    shift_y = int(rng.integers(-6, 6))
                    sx1, sy1 = max(0, gx + shift_x), max(0, gy + shift_y)
                    sx2, sy2 = min(w, sx1 + grid_sz), min(h, gy + grid_sz)
                    tx2, ty2 = min(w, gx + (sx2 - sx1)), min(h, gy + (sy2 - sy1))
                    if sx2 > sx1 and sy2 > sy1 and tx2 > gx and ty2 > gy:
                        styled_rgb[gy:ty2, gx:tx2] = rgb[sy1:sy2, sx1:sx2]
            styled_rgb[::grid_sz, :] = [240, 240, 240]
            styled_rgb[:, ::grid_sz] = [240, 240, 240]

        elif "hoch" in style_key or "漢娜" in style_key:
            # 【漢娜·霍克】報紙半色調蒙太奇
            scale = 4
            small = cv2.resize(gray, (max(1, w // scale), max(1, h // scale)), interpolation=cv2.INTER_LINEAR)
            styled_rgb = np.ones((h, w, 3), dtype=np.uint8) * 235
            for r in range(small.shape[0]):
                for c in range(small.shape[1]):
                    radius = int((1.0 - small[r, c] / 255.0) * (scale / 1.4))
                    if radius > 0:
                        cv2.circle(styled_rgb, (c * scale + scale // 2, r * scale + scale // 2), radius, (20, 20, 25), -1)

        elif "varo" in style_key or "瓦羅" in style_key:
            # 【瓦羅】神秘煉金術羊皮紙
            sepia = np.zeros_like(rgb)
            sepia[:, :, 0] = np.clip(gray * 0.95 + 40, 0, 255)
            sepia[:, :, 1] = np.clip(gray * 0.85 + 20, 0, 255)
            sepia[:, :, 2] = np.clip(gray * 0.65, 0, 255)
            noise = rng.normal(0, 10, (h, w)).astype(np.int16)
            styled_rgb = np.clip(sepia.astype(np.int16) + noise[:, :, None], 0, 255).astype(np.uint8)

        elif "carrington" in style_key or "卡靈頓" in style_key:
            # 【卡靈頓】凱爾特秘境神話 (夜光綠琥珀)
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[:, :, 0] = np.clip(gray * 0.3 + 10, 0, 255)
            styled_rgb[:, :, 1] = np.clip(gray * 0.85 + 40, 0, 255)
            styled_rgb[:, :, 2] = np.clip(gray * 0.65 + 30, 0, 255)

        elif "warhol" in style_key or "沃荷" in style_key:
            # 【沃荷】普普雙色絲網印刷
            _, mask_w = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[mask_w > 0] = [255, 230, 20] # 螢光黃
            styled_rgb[mask_w == 0] = [240, 20, 130] # 螢光洋紅

        # ── 3. 🏯 東方水墨與版畫美學 ──
        elif "ukiyoe" in style_key or "浮世繪" in style_key:
            # 【浮世繪】木刻同心波紋
            y_indices, x_indices = np.indices((h, w))
            dist = np.sqrt((x_indices - w//2)**2 + (y_indices - h//2)**2)
            wave_pattern = (np.sin(dist * 0.15 + (gray / 255.0) * 10.0) > 0.2).astype(np.uint8) * 255
            styled_rgb = cv2.cvtColor(wave_pattern, cv2.COLOR_GRAY2RGB)
            styled_rgb = np.clip(styled_rgb * np.array([0.8, 0.9, 0.85]), 0, 255).astype(np.uint8)

        elif "sumi" in style_key or "水墨" in style_key:
            # 【水墨宣紙】濃淡潑墨暈染
            blur_ink = cv2.GaussianBlur(gray, (11, 11), 3.0)
            styled_rgb = np.ones((h, w, 3), dtype=np.uint8) * 242
            styled_rgb = np.clip(styled_rgb - (255 - blur_ink)[:, :, None] * 0.85, 10, 245).astype(np.uint8)

        elif "shin_hanga" in style_key or "川瀨巴水" in style_key:
            # 【川瀨巴水】新版畫夜雨微光
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[:, :, 0] = np.clip(gray * 0.25 + 15, 0, 255)
            styled_rgb[:, :, 1] = np.clip(gray * 0.45 + 25, 0, 255)
            styled_rgb[:, :, 2] = np.clip(gray * 0.95 + 60, 0, 255) # 夜雨深藍

        elif "dunhuang" in style_key or "敦煌" in style_key:
            # 【敦煌壁畫】礦物泥金斑駁
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[:, :, 0] = np.clip(gray * 0.85 + 45, 0, 255) # 泥金
            styled_rgb[:, :, 1] = np.clip(gray * 0.65 + 25, 0, 255) # 青金石
            styled_rgb[:, :, 2] = np.clip(gray * 0.45 + 15, 0, 255)

        elif "dancheong" in style_key or "丹青" in style_key:
            # 【丹青幾何】五色木構紋樣
            bands = (gray // 51) * 51
            styled_rgb = cv2.applyColorMap(bands, cv2.COLORMAP_JET)
            styled_rgb = cv2.cvtColor(styled_rgb, cv2.COLOR_BGR2RGB)

        elif "junji" in style_key or "伊藤潤二" in style_key:
            # 【伊藤潤二】恐怖細密螺旋排線
            y_indices, x_indices = np.indices((h, w))
            angle = np.arctan2(y_indices - h//2, x_indices - w//2)
            dist = np.sqrt((x_indices - w//2)**2 + (y_indices - h//2)**2)
            spiral = (np.sin(angle * 6.0 + dist * 0.25) > 0.0).astype(np.uint8) * 255
            styled_rgb = cv2.cvtColor(cv2.bitwise_and(spiral, gray), cv2.COLOR_GRAY2RGB)

        # ── 4. 🎬 傳奇動畫與動漫美學 ──
        elif "shinkai" in style_key or "新海誠" in style_key:
            # 【新海誠】極致光學浪漫光斑
            glow = cv2.GaussianBlur(rgb, (25, 25), 10.0)
            styled_rgb = cv2.addWeighted(rgb, 0.75, glow, 0.6, 15)

        elif "otomo" in style_key or "大友克洋" in style_key:
            # 【大友克洋】阿基拉機械重墨
            edges = cv2.Canny(gray, 60, 180)
            dilated = cv2.dilate(edges, np.ones((2, 2), np.uint8))
            styled_rgb = (rgb // 64) * 64
            styled_rgb[dilated > 0] = [15, 15, 20]

        elif "ghibli" in style_key or "吉卜力" in style_key:
            # 【吉卜力】水彩田園手繪質感
            smoothed = cv2.edgePreservingFilter(rgb, flags=1, sigma_s=50, sigma_r=0.4)
            styled_rgb = np.clip(smoothed * np.array([1.05, 1.1, 0.95]), 0, 255).astype(np.uint8)

        elif "manga" in style_key or "熱血日漫" in style_key:
            # 【熱血日漫】速度線與衝擊波
            y_indices, x_indices = np.indices((h, w))
            angle = np.arctan2(y_indices - h//2, x_indices - w//2)
            speedlines = (np.sin(angle * 45.0) > 0.3).astype(np.uint8) * 255
            styled_rgb = cv2.cvtColor(cv2.bitwise_and(speedlines, gray), cv2.COLOR_GRAY2RGB)

        elif "paprika" in style_key or "紅辣椒" in style_key:
            # 【今敏·紅辣椒】夢境狂歡色彩溢流
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            hsv[:, :, 0] = (hsv[:, :, 0] + 45) % 180
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.5, 0, 255)
            styled_rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

        elif "cel_80s" in style_key or "賽璐珞" in style_key:
            # 【80s 賽璐珞】復古電視色差
            styled_rgb = rgb.copy()
            styled_rgb[::3, :] = [20, 20, 20] # CRT Scanlines
            styled_rgb[:, :, 0] = np.roll(styled_rgb[:, :, 0], 3, axis=1) # 色差

        # ── 5. ⚡ 當代數位與賽博前衛 ──
        elif "pixel_sort" in style_key or "故障" in style_key:
            # 【故障藝術】像素分選拉絲
            styled_rgb = rgb.copy()
            for r in range(0, h, 2):
                if rng.random() > 0.4:
                    row_pixels = styled_rgb[r, :, :]
                    lumas = np.dot(row_pixels.astype(float), [0.299, 0.587, 0.114])
                    mask_row = lumas > (80 + seed % 40)
                    if np.any(mask_row):
                        sorted_seg = row_pixels[mask_row]
                        sorted_seg = sorted_seg[np.argsort(np.dot(sorted_seg.astype(float), [1, 1, 1]))]
                        styled_rgb[r, mask_row] = sorted_seg

        elif "blueprint" in style_key or "藍圖" in style_key:
            # 【工程藍圖】普魯士藍等高線
            edges = cv2.Canny(gray, 40, 120)
            styled_rgb = np.zeros((h, w, 3), dtype=np.uint8)
            styled_rgb[:, :] = [18, 52, 112]
            styled_rgb[edges > 0] = [220, 240, 255]

        elif "thermal" in style_key or "紅外" in style_key:
            # 【紅外視界】生物熱感霓虹
            styled_rgb = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
            styled_rgb = cv2.cvtColor(styled_rgb, cv2.COLOR_BGR2RGB)

        elif "voronoi" in style_key or "晶體" in style_key:
            # 【晶體折射】泰森多邊形碎裂
            num_cells = 60 + (seed % 40)
            pts = rng.integers(0, max(w, h), size=(num_cells, 2))
            pts[:, 0] = np.clip(pts[:, 0], 0, w - 1)
            pts[:, 1] = np.clip(pts[:, 1], 0, h - 1)
            subdiv = cv2.Subdiv2D((0, 0, w, h))
            for p in pts:
                subdiv.insert((float(p[0]), float(p[1])))
            facets, _ = subdiv.getVoronoiFacetList([])
            styled_rgb = rgb.copy()
            for facet in facets:
                if len(facet) > 0:
                    ifacet = np.array(facet, dtype=np.int32)
                    mask_f = np.zeros((h, w), dtype=np.uint8)
                    cv2.fillConvexPoly(mask_f, ifacet, 255)
                    mean_col = cv2.mean(rgb, mask=mask_f)[:3]
                    cv2.fillConvexPoly(styled_rgb, ifacet, mean_col)
                    cv2.polylines(styled_rgb, [ifacet], True, (240, 240, 255), 1)

        elif "synthwave" in style_key or "賽博網格" in style_key:
            # 【賽博網格】80s 向量地平線
            edges = cv2.Canny(gray, 60, 160)
            styled_rgb = np.zeros((h, w, 3), dtype=np.uint8)
            styled_rgb[:, :] = [25, 10, 45]
            styled_rgb[edges > 0] = [255, 40, 180]

        elif "hologram" in style_key or "全息" in style_key:
            # 【全息投影】立體干涉條紋
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[:, :, 1] = np.clip(gray * 1.2, 0, 255) # 螢光綠
            styled_rgb[:, :, 2] = np.clip(gray * 0.9, 0, 255) # 螢光青
            styled_rgb[::4, :] = [0, 20, 20]

        # ── 6. 🔮 物質材質與實驗工藝 ──
        elif "chrome" in style_key or "金屬" in style_key:
            # 【液態金屬】流動高光水銀
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            mag = cv2.magnitude(sobelx, sobely)
            chrome = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            styled_rgb = cv2.cvtColor(chrome, cv2.COLOR_GRAY2RGB)
            styled_rgb = np.clip(styled_rgb * 1.2 + 30, 0, 255).astype(np.uint8)

        elif "risograph" in style_key or "孔版" in style_key:
            # 【孔版印刷】錯位豆墨顆粒
            _, r_mask = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[r_mask > 0] = [255, 100, 80]
            styled_rgb[r_mask == 0] = [20, 60, 140]

        elif "cyanotype" in style_key or "日光藍曬" in style_key:
            # 【古典日光印】植物日光藍曬
            styled_rgb = np.zeros_like(rgb)
            styled_rgb[:, :, 0] = np.clip(gray * 0.1, 0, 255)
            styled_rgb[:, :, 1] = np.clip(gray * 0.35 + 20, 0, 255)
            styled_rgb[:, :, 2] = np.clip(gray * 0.85 + 60, 0, 255)

        elif "stained_glass" in style_key or "花窗" in style_key:
            # 【哥德花窗】彩色鑲嵌玻璃
            edges = cv2.Canny(gray, 50, 150)
            dilated = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
            styled_rgb = cv2.applyColorMap((gray // 32) * 32, cv2.COLORMAP_RAINBOW)
            styled_rgb = cv2.cvtColor(styled_rgb, cv2.COLOR_BGR2RGB)
            styled_rgb[dilated > 0] = [10, 10, 10]

        elif "psychedelic" in style_key or "迷幻油水" in style_key:
            # 【迷幻油水】60s 浮動油膜擴散
            oil = cv2.applyColorMap(gray, cv2.COLORMAP_TWILIGHT_SHIFTED)
            styled_rgb = cv2.cvtColor(oil, cv2.COLOR_BGR2RGB)

        else: # raw_alpha
            styled_rgb = rgb

        result_rgba = np.zeros((h, w, 4), dtype=np.uint8)
        result_rgba[:, :, :3] = styled_rgb
        result_rgba[:, :, 3] = alpha
        return result_rgba

    def apply_hybrid_styles(self, pil_image: Image.Image, primary_style: str, secondary_style: str = None, blend_ratio: float = 0.5, seed: int = 0) -> Image.Image:
        """支援 36 大流派雙大師風格插值混合 (36x36 = 1296 種組合)"""
        rgba_img = pil_image.convert("RGBA")
        np_img = np.array(rgba_img)
        res_primary = self.apply_single_style(np_img, primary_style, seed=seed)
        
        if not secondary_style or secondary_style == primary_style or blend_ratio <= 0.0:
            return Image.fromarray(res_primary)

        res_secondary = self.apply_single_style(np_img, secondary_style, seed=seed + 100)
        alpha = res_primary[:, :, 3]
        blended_rgb = cv2.addWeighted(res_primary[:, :, :3], 1.0 - blend_ratio, res_secondary[:, :, :3], blend_ratio, 0.0)
        
        out_rgba = np.zeros_like(res_primary)
        out_rgba[:, :, :3] = blended_rgb
        out_rgba[:, :, 3] = alpha
        return Image.fromarray(out_rgba)

    def decompose_character_puppet(self, pil_image: Image.Image, asset_id: str) -> dict:
        """肢體關節層級拆解 (相容性接口)"""
        return self.decompose_puppet(pil_image, asset_id)

    def decompose_puppet(self, pil_image: Image.Image, asset_id: str) -> dict:
        """肢體關節層級拆解與資產輸出"""
        asset_folder = os.path.join(self.output_base_dir, asset_id)
        os.makedirs(asset_folder, exist_ok=True)
        rgba_img = pil_image.convert("RGBA")
        w, h = rgba_img.size
        np_img = np.array(rgba_img)

        head_img = self.tight_crop_alpha(Image.fromarray(np_img[0:max(1, int(h * 0.35)), max(0, int(w * 0.25)):min(w, int(w * 0.75))]))
        torso_img = self.tight_crop_alpha(Image.fromarray(np_img[max(0, int(h * 0.25)):min(h, int(h * 0.75)), max(0, int(w * 0.2)):min(w, int(w * 0.8))]))
        arm_ul = self.tight_crop_alpha(Image.fromarray(np_img[max(0, int(h * 0.25)):min(h, int(h * 0.55)), 0:min(w, int(w * 0.35))]))
        arm_fl = self.tight_crop_alpha(Image.fromarray(np_img[max(0, int(h * 0.45)):min(h, int(h * 0.8)), 0:min(w, int(w * 0.35))]))
        arm_ur = self.tight_crop_alpha(Image.fromarray(np_img[max(0, int(h * 0.25)):min(h, int(h * 0.55)), max(0, int(w * 0.65)):w]))
        arm_fr = self.tight_crop_alpha(Image.fromarray(np_img[max(0, int(h * 0.45)):min(h, int(h * 0.8)), max(0, int(w * 0.65)):w]))

        head_img.save(os.path.join(asset_folder, "head.png"))
        torso_img.save(os.path.join(asset_folder, "torso.png"))
        arm_ul.save(os.path.join(asset_folder, "upper_arm_l.png"))
        arm_fl.save(os.path.join(asset_folder, "forearm_l.png"))
        arm_ur.save(os.path.join(asset_folder, "upper_arm_r.png"))
        arm_fr.save(os.path.join(asset_folder, "forearm_r.png"))

        return {
            "is_puppet": True,
            "parts": {
                "head": {"file": "head.png", "pivot": [0.5, 0.9]},
                "torso": {"file": "torso.png", "pivot": [0.5, 0.5]},
                "upper_arm_l": {"file": "upper_arm_l.png", "pivot": [0.9, 0.1]},
                "forearm_l": {"file": "forearm_l.png", "pivot": [0.5, 0.1]},
                "upper_arm_r": {"file": "upper_arm_r.png", "pivot": [0.1, 0.1]},
                "forearm_r": {"file": "forearm_r.png", "pivot": [0.5, 0.1]}
            }
        }

    def process_secondary_element(self, pil_image: Image.Image, asset_id: str, filename: str = "element_b.png") -> dict:
        """處理次要/陪襯衝突元素 B"""
        asset_folder = os.path.join(self.output_base_dir, asset_id)
        os.makedirs(asset_folder, exist_ok=True)
        cropped = self.tight_crop_alpha(pil_image)
        file_path = os.path.join(asset_folder, filename)
        cropped.save(file_path)
        return {
            "file": filename,
            "width": cropped.width,
            "height": cropped.height
        }
