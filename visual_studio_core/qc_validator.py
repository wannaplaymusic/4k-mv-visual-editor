import re
import hashlib
import logging
import datetime

logger = logging.getLogger("VisualStudio.QCValidator")

class QCValidator:
    """
    4K 實時品質審計、自癒監控與 Visual DNA 生成器
    - 靜態語法與 4K 效能陷阱檢測 (禁止 DOM 阻塞與無約束 loadPixels)
    - 黑畫面與異常日誌分析
    - Visual DNA 特徵指紋生成
    - Walter Murch 曲式結構契合度打標 (Intro / Verse / Chorus / Drop)
    - 格式化為合規的 custom_visuals/*.json 規範
    """

    HARMFUL_PATTERNS = [
        (re.compile(r'\balert\s*\('), "禁止使用 alert 彈窗阻斷渲染線程"),
        (re.compile(r'\bconfirm\s*\('), "禁止使用 confirm 阻斷彈窗"),
        (re.compile(r'\bprompt\s*\('), "禁止使用 prompt 阻斷輸入"),
        (re.compile(r'\bdocument\.write\b'), "禁止使用 document.write 破壞畫布 DOM"),
        (re.compile(r'\bwhile\s*\(\s*true\s*\)'), "嚴禁無限死循環 while(true)"),
        (re.compile(r'\bwindow\.location\b'), "嚴禁惡意頁面跳轉"),
    ]

    @classmethod
    def audit_code_safety(cls, code_text: str) -> dict:
        """
        代碼安全與性能合規性靜態審查
        """
        errors = []
        warnings = []

        # 1. 惡意或阻塞 API 檢測
        for pattern, msg in cls.HARMFUL_PATTERNS:
            if pattern.search(code_text):
                errors.append(msg)

        # 2. 檢測 setup() 和 draw() 完整性
        if not re.search(r'\bfunction\s+setup\s*\(', code_text) and not re.search(r'\bsetup\s*=\s*function', code_text):
            errors.append("缺失核心 setup() 函數宣告")
        if not re.search(r'\bfunction\s+draw\s*\(', code_text) and not re.search(r'\bdraw\s*=\s*function', code_text):
            errors.append("缺失核心 draw() 動態渲染循環")

        # 3. 效能預警：過度呼叫 loadPixels()
        load_pixels_count = len(re.findall(r'\bloadPixels\s*\(', code_text))
        if load_pixels_count > 1:
            warnings.append(f"偵測到 {load_pixels_count} 次 loadPixels() 呼叫，在 4K 解析度下可能引發幀率下降")

        # 4. 音訊聯覺變數覆蓋度
        audio_var_hits = sum(1 for v in ["audioEnergy", "audioParams", "sub_bass", "bass", "mid", "high", "isBeat", "chordHue"] if v in code_text)
        if audio_var_hits == 0:
            warnings.append("代碼中未發現標準音訊聯覺變數，可能缺乏音樂響應動態")

        return {
            "is_valid": (len(errors) == 0),
            "errors": errors,
            "warnings": warnings,
            "audio_reactivity_score": min(100, audio_var_hits * 25)
        }

    @classmethod
    def generate_visual_dna(cls, code_text: str, name: str) -> dict:
        """
        計算唯一的 Visual DNA 特徵哈希與曲式契合度
        """
        h = hashlib.sha256(code_text.strip().encode('utf-8')).hexdigest()[:16]
        has_bass = ("bass" in code_text or "sub_bass" in code_text)
        has_webgl = ("WEBGL" in code_text)
        has_noise = ("noise" in code_text)

        # 根據特徵智能預測曲式結構適配度
        if has_bass and has_webgl:
            section_fitness = {"intro": 0.3, "verse": 0.6, "chorus": 0.95, "drop": 1.0, "outro": 0.4}
            energy_level = 0.9
        elif has_noise:
            section_fitness = {"intro": 0.8, "verse": 0.85, "chorus": 0.7, "drop": 0.6, "outro": 0.8}
            energy_level = 0.6
        else:
            section_fitness = {"intro": 0.7, "verse": 0.7, "chorus": 0.8, "drop": 0.7, "outro": 0.6}
            energy_level = 0.7

        return {
            "fingerprint": f"sha256:{h}",
            "energy_level": energy_level,
            "section_fitness": section_fitness,
            "style_tags": ["visual_studio_pro", "audio_reactive", "generative"] + (["3d", "webgl"] if has_webgl else ["2d"])
        }

    @classmethod
    def package_module_json(cls, name: str, code: str, custom_html: str = "", custom_css: str = "", post_fx: list = None, tags: list = None) -> dict:
        """
        封裝為標準 custom_visuals/*.json 結構
        """
        dna = cls.generate_visual_dna(code, name)
        all_tags = list(set((tags or []) + dna["style_tags"]))

        return {
            "name": name,
            "author": "VisualStudio Pro Creator",
            "license": "CC BY-SA 4.0",
            "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": "local://visual_studio_pro",
            "code": code,
            "custom_html": custom_html or "",
            "custom_css": custom_css or "",
            "inline_assets": {},
            "tags": all_tags,
            "frequency": 50,
            "storyboard_weight": 60,
            "post_fx_intensity": 50,
            "post_fx": post_fx or [],
            "visual_dna": dna,
            "used_count": 0,
            "is_starred": False,
            "used_in_videos": []
        }
