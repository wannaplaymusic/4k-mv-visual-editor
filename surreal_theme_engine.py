import random

class SurrealThemeConceptEngine:
    """
    超現實主題與多元素思維策展引擎：
    - 提供「超現實靈感骰子 (Surreal Dice Roll)」
    - 隨機骰出 2~10 個具備哲學/超現實衝突美學的元素組合
    - 包含創作主題 (Concept Theme) 與 藝術哲學思考 (Manifesto/Rationale)
    """

    CURATED_THEMES = [
        {
            "theme_title": "⏳ 時間的液態塌陷與永恆紀念碑 (Liquid Time & The Eternal Monolith)",
            "concept_thought": "將古典永恆的石雕紀念碑與達利式融化時鐘、深海生物並置，解構時間作為剛性維度的幻覺，探討在聲波震盪下物質的流動性。",
            "hero_seed": "classical marble bust statue",
            "element_pool": [
                "melting brass grandfather clock",
                "luminescent deep sea jellyfish",
                "renaissance anatomical skull",
                "floating gilded keyhole",
                "ancient roman ionic column",
                "cosmic galaxy nebula crystal",
                "baroque feathered angel wing",
                "vintage mechanical astrolabe",
                "mystic third eye with teardrop"
            ]
        },
        {
            "theme_title": "🍎 符號的背叛與禁果之屋 (The Treachery of Symbols & The Forbidden Chamber)",
            "concept_thought": "向雷內·馬格利特致敬。透過將微觀果實與宏觀建築顛倒尺度，探討『這不是一個蘋果』的符號哲學，所有物件在引力失重中圍繞核心主體旋轉。",
            "hero_seed": "vintage bowler hat gentleman sculpture",
            "element_pool": [
                "giant green apple with crystal core",
                "floating wooden birdcage with lightning",
                "gothic cathedral window",
                "vintage antique key",
                "steampunk brass optical monocle",
                "porcelain teacup dripping clouds",
                "white dove with painted eye",
                "floating miniature chess castle",
                "vintage velvet curtain drape"
            ]
        },
        {
            "theme_title": "⚙️ 百頭女的異質機械繁衍 (The Hundred-Headed Machine & Ernst Grafting)",
            "concept_thought": "馬克斯·恩斯特的銅版拓印美學。工業革命機械齒輪與遠古生物、神話昆蟲進行外科手術式的異質嫁接，隨音樂中高頻產生抽搐生長。",
            "hero_seed": "steampunk mechanical humanoid torso",
            "element_pool": [
                "giant dragonfly brass wings",
                "clockwork mechanical gears cluster",
                "vintage anatomical heart illustration",
                "gothic gargoyle stone wings",
                "vintage microscope brass lenses",
                "spiral nautilus shell ammonite",
                "flaming branch with golden leaves",
                "ancient astrolabe dial plate",
                "antique apothecary poison bottle"
            ]
        },
        {
            "theme_title": "🌌 光學事故與銀鹽暗房夢境 (Solarized Accidents & Man Ray Darkroom Dream)",
            "concept_thought": "曼·雷的物影攝影（Rayograph）與中途曝光。在黑白灰階的反相金屬光澤中，神秘符號與超現實肢體交織，每次重音爆發即觸發銀鹽閃爍。",
            "hero_seed": "art deco porcelain mannequin face",
            "element_pool": [
                "violin f-holes stamped on body",
                "floating glass crystal prism",
                "rayogram chess piece silhouettes",
                "vintage chrome metallic sphere",
                "anatomical human eye with brass compass",
                "classical lyre harp with spiderwebs",
                "floating solar eclipse halo",
                "antique velvet jewelry box",
                "abstract spiraling film negative"
            ]
        },
        {
            "theme_title": "🎪 吉列姆的荒誕木偶劇場 (Terry Gilliam's Absurdist Puppet Theatre)",
            "concept_thought": "蒙提·派森式的荒誕木偶動態。關節超調脫臼、文藝復興名畫被肢解拼裝，重拍落下時天降巨物砸擊，在失序中建立奇異的節奏秩序。",
            "hero_seed": "renaissance monarch royal portrait",
            "element_pool": [
                "giant descending marble foot",
                "vintage military cannon firing flower",
                "victorian bicycle with giant wheel",
                "flapping parchment scroll",
                "screaming classical theater mask",
                "brass marching trumpet",
                "vintage steam locomotive front",
                "flying renaissance cupid with scissors",
                "royal golden crown on clockwork spring"
            ]
        }
    ]

    @classmethod
    def roll_dice(cls, num_elements: int = None) -> dict:
        """
        🎲 骰出一個隨機的超現實組合
        - 隨機選定 1 個核心創作主題與哲學思維
        - 隨機決定 2 ~ 10 個素材元素
        """
        theme = random.choice(cls.CURATED_THEMES)
        if num_elements is None:
            num_elements = random.randint(2, 9)
        num_elements = max(2, min(10, num_elements))

        hero = theme["hero_seed"]
        # 從元素池中隨機挑選 (num_elements - 1) 個次要元素
        selected_elements = random.sample(theme["element_pool"], min(num_elements - 1, len(theme["element_pool"])))

        all_elements = [
            {"id": "hero_element_0", "keyword": hero, "role": "hero_subject", "is_hero": True}
        ]
        for idx, elem in enumerate(selected_elements, start=1):
            all_elements.append({
                "id": f"conflict_element_{idx}",
                "keyword": elem,
                "role": "conflict_satellite" if idx > 1 else "primary_conflict",
                "is_hero": False
            })

        return {
            "theme_title": theme["theme_title"],
            "concept_thought": theme["concept_thought"],
            "num_elements": len(all_elements),
            "elements": all_elements
        }
