import random

class SurrealDialecticsGenerator:
    """
    超現實對立詞智慧碰撞引擎：基於達利、馬格利特、恩斯特等大師符號學庫
    自動根據輸入的主體詞生成極端對立、具戲劇衝突的陪襯元素
    """
    # 經典超現實符號對立庫
    OPPOSING_SYMBOL_DATABASE = {
        # 剛性建築/雕像/人體 -> 軟性流體/有機生命/荒誕自然
        "rigid_organic": [
            "giant floating jellyfish with golden clock tentacles",
            "melting vintage mechanical pocket watch",
            "biological anatomy heart entwined with brass gears",
            "hyper-realistic giant green apple with glass butterfly wings",
            "flaming giraffe with cosmic nebula plumage",
            "ancient marble bust sprouting blooming coral reefs",
            "classical greek column dissolving into fluid mercury",
            "antlered mechanical moth carrying miniature cathedral"
        ],
        # 微觀日常生活 -> 宏觀宇宙/宏大建築
        "micro_macro": [
            "porcelain teacup containing infinite storming ocean",
            "floating keyhole revealing rotating galaxy nebula",
            "surreal umbrella dripping glowing planetary system",
            "vintage birdcage trapping thunderous storm cloud",
            "wooden chess king crowned with blazing solar eclipse"
        ],
        # 現代科技/機械 -> 遠古化石/宗教神話
        "tech_mythic": [
            "steampunk motorcycle grafted with dragonfly wings",
            "cybernetic skull surrounded by rennaissance halo",
            "retro television screen displaying living botanical forest",
            "monolithic obsidian obelisk orbiting with brass astrolabe"
        ]
    }

    CROSS_HATCH_PROMPTS = [
        "vintage copperplate engraving",
        "detailed 19th century cross-hatch frottage",
        "renaissance anatomical etching",
        "woodcut linocut surrealist illustration"
    ]

    @classmethod
    def suggest_opposing_element(cls, subject_keyword: str) -> str:
        """根據主體關鍵詞，智慧匹配極端衝突對立的第二素材"""
        kw = subject_keyword.lower()
        if any(w in kw for w in ["bust", "sculpture", "statue", "column", "building", "motor", "machine"]):
            candidates = cls.OPPOSING_SYMBOL_DATABASE["rigid_organic"]
        elif any(w in kw for w in ["cup", "clock", "apple", "eye", "key", "feather"]):
            candidates = cls.OPPOSING_SYMBOL_DATABASE["micro_macro"]
        else:
            candidates = cls.OPPOSING_SYMBOL_DATABASE["tech_mythic"]
        
        return random.choice(candidates)

    @classmethod
    def enrich_aesthetic_prompt(cls, keyword: str) -> str:
        """為素材附加 19 世紀古典銅版版畫與超現實風格修飾詞"""
        hatch = random.choice(cls.CROSS_HATCH_PROMPTS)
        return f"{keyword}, {hatch}, high contrast, clean transparent background, master composition"
