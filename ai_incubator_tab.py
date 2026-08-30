import os
import json
import logging
import hashlib
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QTextEdit, QLineEdit, QComboBox, QProgressBar, QCheckBox,
    QGroupBox, QScrollArea, QFrame, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from code_injector import CodeEditor
from ai_code_generator import AICodeGenerator
from ai_engine_config import load_ai_config, save_ai_config

logger = logging.getLogger("StandaloneInjector.AIIncubator")

class AIGenerationWorker(QThread):
    code_generated = pyqtSignal(dict)
    generation_failed = pyqtSignal(str)
    progress_update = pyqtSignal(str)

    def __init__(self, user_prompt, math_model, style_hints, generator):
        super().__init__()
        self.user_prompt = user_prompt
        self.math_model = math_model
        self.style_hints = style_hints
        self.generator = generator

    def run(self):
        try:
            self.progress_update.emit("正在呼叫 AI 模型生成視覺代碼...")
            result = self.generator.generate_visual_module(
                user_prompt=self.user_prompt,
                math_model=self.math_model,
                style_hints=self.style_hints
            )
            if "error" in result:
                self.generation_failed.emit(result["error"])
            else:
                self.code_generated.emit(result)
        except Exception as e:
            logger.error(f"Generation worker failed: {e}", exc_info=True)
            self.generation_failed.emit(str(e))


class AIRefineWorker(QThread):
    code_refined = pyqtSignal(str)
    refine_failed = pyqtSignal(str)

    def __init__(self, current_code, instruction, generator):
        super().__init__()
        self.current_code = current_code
        self.instruction = instruction
        self.generator = generator

    def run(self):
        try:
            result = self.generator.refine_code(self.current_code, self.instruction)
            if isinstance(result, dict) and "error" in result:
                self.refine_failed.emit(result["error"])
            else:
                if isinstance(result, dict) and "code" in result:
                    self.code_refined.emit(result["code"])
                elif isinstance(result, str):
                    self.code_refined.emit(result)
                else:
                    self.refine_failed.emit("非預期的回傳格式")
        except Exception as e:
            logger.error(f"Refine worker failed: {e}", exc_info=True)
            self.refine_failed.emit(str(e))


class AITagSuggestionWorker(QThread):
    tags_suggested = pyqtSignal(dict)

    def __init__(self, code, generator):
        super().__init__()
        self.code = code
        self.generator = generator

    def run(self):
        try:
            tags = self.generator.suggest_director_tags(self.code)
            self.tags_suggested.emit(tags)
        except Exception as e:
            logger.error(f"Tag suggestion failed: {e}")
            self.tags_suggested.emit({
                "style_tags": ["AI_Generated"],
                "section_scores": {"intro": 0.5, "verse": 0.5, "build": 0.5, "drop": 0.5, "outro": 0.5},
                "energy_level": "medium"
            })


class AIMutateWorker(QThread):
    mutate_completed = pyqtSignal(list)
    mutate_failed = pyqtSignal(str)

    def __init__(self, base_code, generator):
        super().__init__()
        self.base_code = base_code
        self.generator = generator

    def run(self):
        try:
            results = self.generator.mutate_visual_styles(self.base_code)
            self.mutate_completed.emit(results)
        except Exception as e:
            logger.error(f"Mutation failed: {e}")
            self.mutate_failed.emit(str(e))


class AIIncubatorTab(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.app = parent_app
        self.generator = AICodeGenerator()
        self.current_tags = None
        self.current_model = None
        self.current_prompt = ""
        self.init_tab()

    def init_tab(self):
        if self.layout() is not None:
            return
        self.setStyleSheet("background-color: #0b0b0e; color: #e4e4e7;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(8)

        # Main Scroll Area Container
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #0b0b0e; }
            QWidget { background-color: #0b0b0e; }
            QScrollBar:vertical { width: 8px; background: #121215; }
            QScrollBar::handle:vertical { background: #3f3f46; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #a855f7; }
        """)
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #0b0b0e;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # Standard GroupBox Style
        group_style = """
            QGroupBox {
                background-color: #121215;
                border: 1px solid #27272a;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 12px;
                font-weight: bold;
                color: #c084fc;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
                background-color: #121215;
            }
        """

        # 1. Header Title
        title_lbl = QLabel("🚀 4K 視覺資產 AI 孵化器 — 100% 原創生成", self)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #c084fc; margin-bottom: 2px;")
        layout.addWidget(title_lbl)

        # 1.5 AI Hybrid Engine Selector
        engine_box = QGroupBox("⚡ AI 混合雙引擎設置 (Hybrid Architecture)", self)
        engine_box.setStyleSheet(group_style)
        engine_layout = QVBoxLayout(engine_box)
        engine_layout.setContentsMargins(10, 10, 10, 10)
        engine_layout.setSpacing(6)

        prov_row = QHBoxLayout()
        prov_row.setSpacing(6)
        prov_lbl = QLabel("生成引擎：")
        prov_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        prov_lbl.setFixedWidth(65)

        self.combo_engine_provider = QComboBox(self)
        self.combo_engine_provider.setStyleSheet("""
            QComboBox { background-color: #18181b; border: 1px solid #27272a; color: #f4f4f5; border-radius: 4px; padding: 4px 8px; font-size: 11px; min-height: 26px; }
            QComboBox:hover { border: 1px solid #a855f7; }
        """)
        self.combo_engine_provider.addItem("🚀 本地 Ollama (離線免費，llama3 / deepseek)", userData="ollama")
        self.combo_engine_provider.addItem("🌙 Kimi / Moonshot AI (雲端大師級 4K p5.js 代碼)", userData="kimi")
        self.combo_engine_provider.addItem("🔮 DeepSeek Cloud API (雲端極速)", userData="deepseek_cloud")
        self.combo_engine_provider.addItem("🌐 OpenAI 相容端點 (GPT-4o 等)", userData="openai")
        self.combo_engine_provider.currentIndexChanged.connect(self._on_engine_provider_changed)

        prov_row.addWidget(prov_lbl)
        prov_row.addWidget(self.combo_engine_provider, 1)
        engine_layout.addLayout(prov_row)

        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        key_lbl = QLabel("API 金鑰：")
        key_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        key_lbl.setFixedWidth(65)

        self.input_api_key = QLineEdit(self)
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_api_key.setPlaceholderText("請輸入 Moonshot (Kimi) API Key (例如 sk-...)")
        self.input_api_key.setStyleSheet("QLineEdit { background-color: #18181b; border: 1px solid #27272a; color: #f4f4f5; padding: 4px 8px; border-radius: 4px; font-size: 11px; }")

        self.btn_toggle_key = QPushButton("👁️", self)
        self.btn_toggle_key.setFixedWidth(32)
        self.btn_toggle_key.setStyleSheet("QPushButton { background-color: #27272a; color: #e4e4e7; border-radius: 4px; padding: 4px; font-size: 11px; }")
        self.btn_toggle_key.clicked.connect(self._toggle_api_key_visibility)

        self.btn_save_engine = QPushButton("💾 儲存配置", self)
        self.btn_save_engine.setStyleSheet("QPushButton { background-color: #4f46e5; color: white; font-weight: bold; border-radius: 4px; padding: 4px 10px; font-size: 11px; } QPushButton:hover { background-color: #4338ca; }")
        self.btn_save_engine.clicked.connect(self._save_engine_settings)

        key_row.addWidget(key_lbl)
        key_row.addWidget(self.input_api_key, 1)
        key_row.addWidget(self.btn_toggle_key)
        key_row.addWidget(self.btn_save_engine)
        engine_layout.addLayout(key_row)

        layout.addWidget(engine_box)

        # 2. Prompt Section
        prompt_box = QGroupBox("💬 AI 創作指令", self)
        prompt_box.setStyleSheet(group_style)
        prompt_layout = QVBoxLayout(prompt_box)
        prompt_layout.setContentsMargins(10, 10, 10, 10)
        prompt_layout.setSpacing(8)

        # Math Model Selection Row
        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        model_lbl = QLabel("數學模型：")
        model_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: normal;")
        model_lbl.setFixedWidth(65)

        self.model_combo = QComboBox(self)
        self.model_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.model_combo.setMinimumWidth(40)
        self.model_combo.setStyleSheet("""
            QComboBox { background-color: #18181b; border: 1px solid #27272a; color: #f4f4f5; border-radius: 4px; padding: 4px 8px; font-size: 11px; min-height: 26px; }
            QComboBox:hover { border: 1px solid #a855f7; }
        """)
        self.model_combo.addItem("🎲 自由創作 (不指定模型)", userData=None)
        try:
            categories = self.generator.get_model_categories()
            for cat_key, cat_data in categories.items():
                self.model_combo.addItem(f"--- {cat_data['name']} ---")
                idx = self.model_combo.count() - 1
                self.model_combo.setItemData(idx, 0, Qt.ItemDataRole.UserRole - 1)
                for m in cat_data["models"]:
                    self.model_combo.addItem(f"  {m['name']}", userData=m['id'])
        except Exception as e:
            logger.warning(f"Failed to load model categories: {e}")

        model_row.addWidget(model_lbl)
        model_row.addWidget(self.model_combo, 1)
        prompt_layout.addLayout(model_row)

        # Prompt Input Text Area
        self.prompt_input = QTextEdit(self)
        self.prompt_input.setPlaceholderText("描述你想要的視覺效果...\n例如：『帶有引力透鏡效果的 4K 粒子黑洞，重低音時粒子加速噴發，高音時產生霓虹光暈』")
        self.prompt_input.setMinimumHeight(60)
        self.prompt_input.setMaximumHeight(90)
        self.prompt_input.setStyleSheet("""
            QTextEdit {
                background-color: #18181b; 
                border: 1px solid #27272a; 
                color: #f4f4f5; 
                border-radius: 6px; 
                padding: 6px; 
                font-size: 11px;
            }
            QTextEdit:focus { border: 1px solid #a855f7; }
        """)
        prompt_layout.addWidget(self.prompt_input)

        # Generate Button
        self.btn_generate = QPushButton("🚀 【AI 生成原創視覺模組】", self)
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed; 
                border: 1px solid #8b5cf6; 
                color: white; 
                font-weight: bold; 
                font-size: 12px; 
                padding: 7px 14px; 
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #6d28d9; border: 1px solid #c084fc; }
        """)
        self.btn_generate.clicked.connect(self.start_generation)
        prompt_layout.addWidget(self.btn_generate)

        layout.addWidget(prompt_box)

        # 3. 12-Dimensional Assembly Matrix
        self.builder_box = QGroupBox("🧩 12 維微觀組詞器 (相容 1000+ 樂曲類型，可點選下拉或載入曲風配方)", self)
        self.builder_box.setStyleSheet(group_style)
        builder_layout = QVBoxLayout(self.builder_box)
        builder_layout.setContentsMargins(8, 8, 8, 8)
        builder_layout.setSpacing(6)

        combo_style = """
            QComboBox { 
                background-color: #18181b; 
                border: 1px solid #27272a; 
                color: #f4f4f5; 
                border-radius: 4px; 
                padding: 2px 4px; 
                font-size: 10px; 
                min-height: 24px; 
            } 
            QComboBox:hover { border: 1px solid #a855f7; }
        """

        # Genre Quick Preset Bar
        genre_row = QHBoxLayout()
        genre_lbl = QLabel("🎵 曲風快套:")
        genre_lbl.setStyleSheet("color: #a855f7; font-weight: bold; font-size: 10px;")
        genre_lbl.setFixedWidth(60)
        self.combo_genre_recipe = QComboBox(self)
        self.combo_genre_recipe.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.combo_genre_recipe.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.combo_genre_recipe.setMinimumWidth(40)
        self.combo_genre_recipe.setStyleSheet("QComboBox { background-color: #1f192f; border: 1px solid #7c3aed; color: #f3e8ff; border-radius: 4px; padding: 2px 4px; font-size: 10px; font-weight: bold; min-height: 24px; }")
        self.combo_genre_recipe.addItems([
            "⭐ 選擇曲風快套配方 (相容 1000+ 樂曲)",
            "⚡ Electronic / Cyberpunk Techno (高能重拍賽博)",
            "🌊 Ambient / Downtempo (抒情深海夢幻)",
            "🎹 Pop / Commercial Dance (流行輕快粉紫)",
            "🎸 Rock / Heavy Metal (硬核幾何色差)",
            "📻 Lo-Fi / Chillhop (復古溫暖膠片)",
            "🔮 Synthwave / Vaporwave (80s霓虹全息)",
            "🎼 Classical / Cinematic (尊爵黑金交響)",
            "💥 Dubstep / Riddim (重低音拓撲爆裂)",
            "🌌 Trance / Progressive (空間幾何流場)",
            "🎧 Hip-Hop / Trap (低音衝擊震動)",
            "🌴 Reggae / Tropical (熱帶莫蘭迪柔調)",
            "👾 Chiptune / 8-Bit (像素幾何復古)",
            "🔥 Hardstyle / Frenchcore (極速脈衝殘影)",
            "🧪 Industrial / Noise (工業金屬黑白)",
            "☯️ Minimal Techno / Deep House (極簡單色脈衝)"
        ])
        self.combo_genre_recipe.currentIndexChanged.connect(self._apply_genre_recipe)
        genre_row.addWidget(genre_lbl)
        genre_row.addWidget(self.combo_genre_recipe, 1)
        builder_layout.addLayout(genre_row)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(4)

        def _make_grid_cell(label_text, combo_widget):
            box = QHBoxLayout()
            box.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #a1a1aa; font-size: 10px;")
            lbl.setFixedWidth(55)
            combo_widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
            combo_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            combo_widget.setMinimumWidth(40)
            combo_widget.setStyleSheet(combo_style)
            box.addWidget(lbl)
            box.addWidget(combo_widget, 1)
            return box

        self.combo_geo = QComboBox(self)
        self.combo_geo.addItems([
            "🎲 自由發揮形態", "💥 宇宙大爆炸與超新星爆裂", "🌀 蟲洞與無盡時空光速隧道", "🪞 千花幾何萬花筒與對稱陣列",
            "🕳️ 黑洞重力引力透鏡與光環", "🌌 璀璨星雲與銀河星系旋臂", "⚡ 雷電交加與等離子電弧網", "🌿 樹木植物與藤蔓遞迴分枝",
            "🌸 花朵幾何綻放與葉序演化", "❄️ 雪花結晶與冰晶擴散", "🧫 細胞分裂與生物能量網", "🧬 DNA 雙螺旋旋轉",
            "🏛️ 哥德式幾何穹頂與教堂花窗", "🏙️ 參數化巨型未來自適應都市", "2D 經典柱狀動態頻譜", "2D 放射狀環形圓形頻譜",
            "3D 粒子風暴與中心能量核", "生物反應擴散流體", "3D 幾何吸引子 (Lorenz Chaos)"
        ])

        self.combo_motion = QComboBox(self)
        self.combo_motion.addItems([
            "自由隨機動態", "漩渦吸附與旋轉力場", "波浪式推進與起伏", "爆發性震波擴散",
            "物理彈簧振盪與回彈", "引力坍縮與幾何扭曲", "布朗隨機漫步", "莫爾圖案重疊錯覺",
            "網格漸進式擴散", "螺旋向心收縮", "流體剪切流變動", "空間維度旋轉展向"
        ])

        self.combo_bass = QComboBox(self)
        self.combo_bass.addItems([
            "預設低音反應", "重低音 (Bass) 時粒子倍增並向外爆發", "重低音時幾何體劇烈膨脹",
            "重低音時產生畫面衝擊震動", "重低音時脈衝式發光與閃爍", "重低音時形體幾何扭曲",
            "重低音時顏色瞬間反相爆裂", "重低音時產生重影殘影疊加"
        ])

        self.combo_mid = QComboBox(self)
        self.combo_mid.addItems([
            "預設中頻反應", "聽到人聲/中音 (Mid) 時色彩在青藍與金黃間轉換", "聽到旋律時流體速度滑順調變",
            "聽到中頻時線條流暢度提升", "中音來時產生溫柔的色相旋轉", "中音響應時圖案層次展開"
        ])

        self.combo_high = QComboBox(self)
        self.combo_high.addItems([
            "預設高頻反應", "高音拍點 (High) 時產生粒子火花閃爍", "高音拍點時觸發色差偏色 (Chromatic Aberration)",
            "高音拍點時銳利線條快閃", "高音拍點時幾何邊緣輝光突亮", "高音拍點時拓撲結構瞬間 Snap 變換"
        ])

        self.combo_style = QComboBox(self)
        self.combo_style.addItems([
            "賽博朋克霓虹 (深紫/電光青藍/霓虹粉)", "極簡單色高對比 (極簡黑白/金屬光澤)",
            "深海夢幻藍調 (海藍/金黃/發光霧氣)", "莫蘭迪柔和調色盤 (薄荷綠/薰衣草紫/蜜桃粉)",
            "酸性迷幻光譜漸層 (Acid Spectrum)", "黑金尊爵高貴質感 (Gold/Dark Slate)",
            "復古膠片溫暖暖陽 (Analog Film Warmth)", "80s 蒸汽波全息 sunset"
        ])

        self.combo_av_logic = QComboBox(self)
        self.combo_av_logic.addItems([
            "🎲 自由智慧調變邏輯", "⚡ 臨界門檻瞬間爆發", "➰ 物理彈簧阻尼平滑跟隨",
            "📈 指數級幾何/能量縮放", "🎨 OKLCH 12音和弦轉調", "🎆 振幅驅動動態輝光殘影"
        ])

        self.combo_physics = QComboBox(self)
        self.combo_physics.addItems([
            "🎲 預設物理與生命週期", "物理重力沉降與地面反彈", "微重力浮力向上飄散",
            "有限生命週期與透明度淡出衰滅", "新生-成長-衰老形體演化", "高阻尼黏滯空氣摩擦力"
        ])

        self.combo_stems = QComboBox(self)
        self.combo_stems.addItems([
            "🎲 自由分軌獨立互動", "🎤 人聲驅動前景主體與發光", "🥁 爵士鼓驅動粒子爆發與震動",
            "🎸 低音貝斯驅動脈衝與坍縮", "🎹 合成器驅動色相滑移與和弦流體"
        ])

        self.combo_harmonic_emotion = QComboBox(self)
        self.combo_harmonic_emotion.addItems([
            "🎲 預設樂理與情緒能量", "💖 熱烈渴望與狂喜激昂", "🥀 孤獨哀傷與心碎撕裂",
            "🧘 寧靜冥想與治癒氛圍", "⚡ 焦慮不安與心理張力", "🎼 五度圈和弦轉調"
        ])

        self.combo_color_gradient = QComboBox(self)
        self.combo_color_gradient.addItems([
            "🎲 自由色彩漸變", "🌈 OKLCH 感官均勻雙色線性漸變", "🔄 三色相環動態旋轉漸變",
            "🌌 霓虹至暗黑背景徑向漸層衰減", "✨ 金屬金銀高光光澤漸變"
        ])

        self.combo_param_morphing = QComboBox(self)
        self.combo_param_morphing.addItems([
            "🎲 預設參數漸變與內插", "➰ Lerp 數值線性滑順內插", "📈 Ease-InOut 貝茲曲線緩動漸變",
            "🧬 幾何拓撲多邊形光滑漸變形變", "🌫️ 低通濾波參數平滑衰減"
        ])

        grid_layout.addLayout(_make_grid_cell("1.幾何形態:", self.combo_geo), 0, 0)
        grid_layout.addLayout(_make_grid_cell("7.調變邏輯:", self.combo_av_logic), 0, 1)
        grid_layout.addLayout(_make_grid_cell("2.動態動作:", self.combo_motion), 1, 0)
        grid_layout.addLayout(_make_grid_cell("8.物理生命:", self.combo_physics), 1, 1)
        grid_layout.addLayout(_make_grid_cell("3.重低音:", self.combo_bass), 2, 0)
        grid_layout.addLayout(_make_grid_cell("9.分軌獨立:", self.combo_stems), 2, 1)
        grid_layout.addLayout(_make_grid_cell("4.中頻人聲:", self.combo_mid), 3, 0)
        grid_layout.addLayout(_make_grid_cell("10.樂理情緒:", self.combo_harmonic_emotion), 3, 1)
        grid_layout.addLayout(_make_grid_cell("5.高頻拍點:", self.combo_high), 4, 0)
        grid_layout.addLayout(_make_grid_cell("11.色彩漸變:", self.combo_color_gradient), 4, 1)
        grid_layout.addLayout(_make_grid_cell("6.美學風格:", self.combo_style), 5, 0)
        grid_layout.addLayout(_make_grid_cell("12.參數形變:", self.combo_param_morphing), 5, 1)

        builder_layout.addLayout(grid_layout)
        layout.addWidget(self.builder_box)

        for cb in [self.combo_geo, self.combo_motion, self.combo_bass, self.combo_mid, self.combo_high, self.combo_style, self.combo_av_logic, self.combo_physics, self.combo_stems, self.combo_harmonic_emotion, self.combo_color_gradient, self.combo_param_morphing]:
            cb.currentIndexChanged.connect(self._assemble_prompt_from_combos)

        # 4. Code Editor Section
        editor_lbl = QLabel("📝 AI 生成 ES6 p5.js 原創代碼 (可即時編輯與修訂):")
        editor_lbl.setStyleSheet("color: #c084fc; font-weight: bold; font-size: 12px; margin-top: 4px;")
        layout.addWidget(editor_lbl)

        self.incubator_editor = CodeEditor(self)
        self.incubator_editor.setMinimumHeight(240)
        self.incubator_editor.setPlainText("// 🧬 AI 孵化器 — 在上方輸入創作指令後點擊生成\n// 生成的原創 p5.js 代碼將顯示在此處\n")
        layout.addWidget(self.incubator_editor)

        # Natural Language Refine Strip
        refine_row = QHBoxLayout()
        refine_row.setSpacing(6)
        self.refine_input = QLineEdit()
        self.refine_input.setPlaceholderText("✨ 自然語言修訂指令，例如：『把背景改為深海藍，粒子改為金色』")
        self.refine_input.setStyleSheet("""
            QLineEdit {
                background-color: #18181b; 
                border: 1px solid #27272a; 
                color: #f4f4f5; 
                padding: 6px; 
                border-radius: 4px; 
                font-size: 11px;
            }
            QLineEdit:focus { border: 1px solid #a855f7; }
        """)
        self.btn_refine = QPushButton("✨ AI 修訂")
        self.btn_refine.setStyleSheet("""
            QPushButton {
                background-color: #1e1b4b; 
                border: 1px solid #312e81; 
                color: #e0e7ff; 
                font-weight: bold; 
                font-size: 11px; 
                padding: 6px 12px; 
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #312e81; border: 1px solid #6366f1; }
        """)
        self.btn_refine.clicked.connect(self.start_refinement)

        refine_row.addWidget(self.refine_input, 1)
        refine_row.addWidget(self.btn_refine)
        layout.addLayout(refine_row)

        # 5. Metadata & Tags Group
        meta_box = QGroupBox("📊 模組屬性與分析標籤", self)
        meta_box.setStyleSheet(group_style)
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel("原創模組名稱:")
        name_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        name_lbl.setFixedWidth(80)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如: lorenz_neon_storm")
        self.name_input.setStyleSheet("QLineEdit { background-color: #18181b; border: 1px solid #27272a; color: #f4f4f5; padding: 4px 8px; border-radius: 4px; font-size: 11px; }")
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_input, 1)
        meta_layout.addLayout(name_row)

        tags_row = QHBoxLayout()
        tags_row.setSpacing(8)
        tags_lbl = QLabel("AI 建議標籤:")
        tags_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        tags_lbl.setFixedWidth(80)
        self.ai_tags_display = QLabel("(生成代碼後自動分析)")
        self.ai_tags_display.setStyleSheet("color: #71717a; font-style: italic; font-size: 11px;")
        tags_row.addWidget(tags_lbl)
        tags_row.addWidget(self.ai_tags_display, 1)
        meta_layout.addLayout(tags_row)

        self.section_fitness_display = QLabel("")
        self.section_fitness_display.hide()
        self.energy_display = QLabel("")
        self.energy_display.hide()

        layout.addWidget(meta_box)

        # 6. Progress & Actions Deck
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setStyleSheet("""
            QProgressBar { height: 4px; background-color: #18181b; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #a855f7; border-radius: 2px; }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就緒 — 輸入 AI 創作指令或點擊【AI 生成原創視覺模組】")
        self.status_label.setStyleSheet("color: #71717a; font-size: 11px; padding-left: 2px;")
        layout.addWidget(self.status_label)

        action_grid = QGridLayout()
        action_grid.setSpacing(4)

        self.btn_preview = QPushButton("▶ 執行即時預覽", self)
        self.btn_preview.setStyleSheet("""
            QPushButton { background-color: #18181b; border: 1px solid #3f3f46; color: #f4f4f5; font-weight: bold; font-size: 10px; padding: 5px 8px; border-radius: 4px; }
            QPushButton:hover { border: 1px solid #a855f7; color: #a855f7; }
        """)
        self.btn_preview.clicked.connect(self.preview_in_sandbox)

        self.btn_mutate = QPushButton("🎲 風格變異 (4分身)", self)
        self.btn_mutate.setStyleSheet("""
            QPushButton { background-color: #065f46; border: 1px solid #059669; color: #a7f3d0; font-weight: bold; font-size: 10px; padding: 5px 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #047857; border: 1px solid #34d399; }
        """)
        self.btn_mutate.clicked.connect(self.start_mutation)

        self.btn_qc = QPushButton("🛡️ AI 品控", self)
        self.btn_qc.setStyleSheet("""
            QPushButton { background-color: #1e3a5f; border: 1px solid #2563eb; color: #93c5fd; font-weight: bold; font-size: 10px; padding: 5px 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        self.btn_qc.clicked.connect(self.run_qc_check)

        self.btn_send_to_pixel = QPushButton("👾 傳送至像素合成器", self)
        self.btn_send_to_pixel.setStyleSheet("""
            QPushButton { background-color: #3b0764; border: 1px solid #7c3aed; color: #f3e8ff; font-weight: bold; font-size: 10px; padding: 5px 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #6d28d9; border-color: #a855f7; }
        """)
        self.btn_send_to_pixel.clicked.connect(self.send_to_pixel_generator)

        action_grid.addWidget(self.btn_preview, 0, 0)
        action_grid.addWidget(self.btn_mutate, 0, 1)
        action_grid.addWidget(self.btn_qc, 1, 0)
        action_grid.addWidget(self.btn_send_to_pixel, 1, 1)
        layout.addLayout(action_grid)

        self.btn_save = QPushButton("💾 【儲存為原創 4K 資產】", self)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("""
            QPushButton:enabled { background-color: #7c3aed; color: white; font-size: 13px; font-weight: bold; padding: 10px; border-radius: 6px; border: 1px solid #8b5cf6; }
            QPushButton:enabled:hover { background-color: #6d28d9; }
            QPushButton:disabled { background-color: #18181b; color: #52525b; font-size: 13px; font-weight: bold; padding: 10px; border-radius: 6px; border: 1px solid #27272a; }
        """)
        self.btn_save.clicked.connect(self.save_as_original_asset)
        layout.addWidget(self.btn_save)

        # Initialize AI Engine Settings
        self._init_engine_settings()

    def _init_engine_settings(self):
        cfg = load_ai_config()
        active_prov = cfg.get("provider", "kimi")
        idx = self.combo_engine_provider.findData(active_prov)
        if idx >= 0:
            self.combo_engine_provider.setCurrentIndex(idx)
        self._update_api_key_field(active_prov, cfg)

    def _update_api_key_field(self, provider: str, cfg: dict = None):
        if cfg is None:
            cfg = load_ai_config()
        prov_cfg = cfg.get(provider, {})
        key = prov_cfg.get("api_key", "")
        self.input_api_key.setText(key)
        if provider == "kimi":
            self.input_api_key.setPlaceholderText("請輸入 Moonshot (Kimi) API Key (例如 sk-...)")
            self.input_api_key.setEnabled(True)
        elif provider == "deepseek_cloud":
            self.input_api_key.setPlaceholderText("請輸入 DeepSeek API Key (例如 sk-...)")
            self.input_api_key.setEnabled(True)
        elif provider == "openai":
            self.input_api_key.setPlaceholderText("請輸入 OpenAI API Key (例如 sk-...)")
            self.input_api_key.setEnabled(True)
        elif provider == "ollama":
            self.input_api_key.setPlaceholderText("本機 Ollama 離線運行，無需 API Key")
            self.input_api_key.setEnabled(False)

    def _on_engine_provider_changed(self, index: int):
        prov = self.combo_engine_provider.currentData()
        if not prov:
            return
        cfg = load_ai_config()
        cfg["provider"] = prov
        save_ai_config(cfg)
        self._update_api_key_field(prov, cfg)
        if hasattr(self, 'generator'):
            self.generator.reload_config()
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console(f"[AI 孵化器] 已切換生成引擎為: {self.combo_engine_provider.currentText()}")

    def _toggle_api_key_visibility(self):
        if self.input_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self.input_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key.setText("👁️")

    def _save_engine_settings(self):
        prov = self.combo_engine_provider.currentData() or "kimi"
        key = self.input_api_key.text().strip()
        cfg = load_ai_config()
        cfg["provider"] = prov
        if prov in cfg and isinstance(cfg[prov], dict):
            cfg[prov]["api_key"] = key
        save_ai_config(cfg)
        if hasattr(self, 'generator'):
            self.generator.reload_config()
        QMessageBox.information(self, "成功", f"AI 引擎配置已儲存！\n當前核心引擎: {self.combo_engine_provider.currentText()}")

    def _apply_genre_recipe(self, index: int):
        if index <= 0:
            return
        text = self.combo_genre_recipe.currentText()
        if "Techno" in text or "Electronic" in text:
            self.combo_geo.setCurrentIndex(1)
            self.combo_motion.setCurrentIndex(1)
            self.combo_bass.setCurrentIndex(1)
            self.combo_mid.setCurrentIndex(1)
            self.combo_high.setCurrentIndex(1)
            self.combo_style.setCurrentIndex(0)
        elif "Ambient" in text or "Downtempo" in text:
            self.combo_geo.setCurrentIndex(3)
            self.combo_motion.setCurrentIndex(2)
            self.combo_bass.setCurrentIndex(2)
            self.combo_mid.setCurrentIndex(2)
            self.combo_high.setCurrentIndex(4)
            self.combo_style.setCurrentIndex(2)
        elif "Pop" in text:
            self.combo_geo.setCurrentIndex(8)
            self.combo_motion.setCurrentIndex(2)
            self.combo_bass.setCurrentIndex(4)
            self.combo_mid.setCurrentIndex(1)
            self.combo_high.setCurrentIndex(1)
            self.combo_style.setCurrentIndex(3)
        elif "Rock" in text or "Metal" in text:
            self.combo_geo.setCurrentIndex(5)
            self.combo_motion.setCurrentIndex(3)
            self.combo_bass.setCurrentIndex(3)
            self.combo_mid.setCurrentIndex(3)
            self.combo_high.setCurrentIndex(2)
            self.combo_style.setCurrentIndex(1)
        elif "Lo-Fi" in text:
            self.combo_geo.setCurrentIndex(10)
            self.combo_motion.setCurrentIndex(6)
            self.combo_bass.setCurrentIndex(4)
            self.combo_mid.setCurrentIndex(4)
            self.combo_high.setCurrentIndex(3)
            self.combo_style.setCurrentIndex(6)
        elif "Synthwave" in text or "Vaporwave" in text:
            self.combo_geo.setCurrentIndex(6)
            self.combo_motion.setCurrentIndex(7)
            self.combo_bass.setCurrentIndex(1)
            self.combo_mid.setCurrentIndex(1)
            self.combo_high.setCurrentIndex(2)
            self.combo_style.setCurrentIndex(7)
        elif "Classical" in text or "Cinematic" in text:
            self.combo_geo.setCurrentIndex(2)
            self.combo_motion.setCurrentIndex(4)
            self.combo_bass.setCurrentIndex(2)
            self.combo_mid.setCurrentIndex(5)
            self.combo_high.setCurrentIndex(4)
            self.combo_style.setCurrentIndex(5)
        elif "Dubstep" in text or "Riddim" in text:
            self.combo_geo.setCurrentIndex(1)
            self.combo_motion.setCurrentIndex(5)
            self.combo_bass.setCurrentIndex(6)
            self.combo_mid.setCurrentIndex(1)
            self.combo_high.setCurrentIndex(5)
            self.combo_style.setCurrentIndex(4)
        self._assemble_prompt_from_combos()

    def _assemble_prompt_from_combos(self):
        parts = []
        style = self.combo_style.currentText()
        if style and "預設" not in style: parts.append(f"{style}風格")
        geo = self.combo_geo.currentText()
        if geo and "預設" not in geo and "自由" not in geo: parts.append(f"包含{geo}")
        motion = self.combo_motion.currentText()
        if motion and "預設" not in motion and "自由" not in motion: parts.append(f"具有{motion}")
        bass = self.combo_bass.currentText()
        if bass and "預設" not in bass: parts.append(f"，{bass}")
        mid = self.combo_mid.currentText()
        if mid and "預設" not in mid: parts.append(f"，{mid}")
        high = self.combo_high.currentText()
        if high and "預設" not in high: parts.append(f"，{high}")
        logic = self.combo_av_logic.currentText()
        if logic and "預設" not in logic and "自由" not in logic: parts.append(f"，音畫互動邏輯採用{logic}")
        physics = self.combo_physics.currentText()
        if physics and "預設" not in physics: parts.append(f"，粒子與物體具備{physics}")
        stems = self.combo_stems.currentText()
        if stems and "預設" not in stems and "自由" not in stems: parts.append(f"，分軌綁定：{stems}")
        emotion = self.combo_harmonic_emotion.currentText()
        if emotion and "預設" not in emotion: parts.append(f"，樂理情緒表達為{emotion}")
        gradient = self.combo_color_gradient.currentText()
        if gradient and "預設" not in gradient and "自由" not in gradient: parts.append(f"，色彩漸變採用{gradient}")
        morphing = self.combo_param_morphing.currentText()
        if morphing and "預設" not in morphing: parts.append(f"，參數演化採用{morphing}")

        if parts:
            assembled = "".join(parts) + "。畫面需達到 4K 超高畫質，動態流暢。"
            self.prompt_input.setText(assembled)

    def start_generation(self):
        prompt_text = self.prompt_input.toPlainText().strip()
        if not prompt_text:
            QMessageBox.warning(self, "警告", "請輸入創作指令！")
            return
            
        model_data = self.model_combo.currentData()
        self.current_model = model_data if model_data else "freeform"
        self.current_prompt = prompt_text
        
        self.btn_generate.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("🧠 AI 正在生成原創視覺模組...")
        
        self.worker = AIGenerationWorker(prompt_text, self.current_model, "", self.generator)
        self.worker.code_generated.connect(self.on_generation_complete)
        self.worker.generation_failed.connect(self.on_generation_failed)
        self.worker.progress_update.connect(lambda s: self.status_label.setText(s))
        self.worker.start()

    def on_generation_complete(self, result: dict):
        code = result.get("code", "")
        self.incubator_editor.setPlainText(code)
        
        if not self.name_input.text().strip():
            suggested_name = result.get("suggested_name") or f"ai_{int(time.time())}"
            self.name_input.setText(suggested_name)
            
        self.btn_save.setEnabled(True)
        self.progress_bar.hide()
        self.btn_generate.setEnabled(True)
        self.status_label.setText("✅ 代碼生成完成 — 可預覽或直接儲存")
        
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console("[AI 孵化器] 生成成功。")
            
        self.request_ai_tags()

    def on_generation_failed(self, error: str):
        self.progress_bar.hide()
        self.btn_generate.setEnabled(True)
        self.status_label.setText(f"❌ 生成失敗: {error}")
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console(f"[AI 孵化器] 生成錯誤: {error}", is_err=True)

    def start_refinement(self):
        current_code = self.incubator_editor.toPlainText().strip()
        instruction = self.refine_input.text().strip()
        
        if not current_code or current_code.startswith("// 🧬"):
            QMessageBox.warning(self, "警告", "沒有可修訂的代碼！")
            return
            
        if not instruction:
            QMessageBox.warning(self, "警告", "請輸入修訂指令！")
            return
            
        self.btn_refine.setEnabled(False)
        self.status_label.setText("✨ AI 正在修訂代碼...")
        
        self.refine_worker = AIRefineWorker(current_code, instruction, self.generator)
        self.refine_worker.code_refined.connect(self.on_refinement_complete)
        self.refine_worker.refine_failed.connect(lambda e: self.status_label.setText(f"❌ 修訂失敗: {e}"))
        self.refine_worker.finished.connect(lambda: self.btn_refine.setEnabled(True))
        self.refine_worker.start()

    def on_refinement_complete(self, code: str):
        self.incubator_editor.setPlainText(code)
        self.status_label.setText("✅ 代碼修訂完成")
        self.refine_input.clear()

    def preview_in_sandbox(self):
        code_text = self.incubator_editor.toPlainText()
        if not code_text or code_text.startswith("// 🧬"):
            return
            
        stubs = self._get_immunity_stubs()
        
        if hasattr(self.app, 'get_html_content'):
            from main import get_local_base_url
            html = self.app.get_html_content(code_text + "\n" + stubs, "", "", {})
            self.app.web_view.setHtml(html, get_local_base_url())
            
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console("🧬 [AI 孵化器] 即時預覽已載入")

    def run_qc_check(self):
        self.status_label.setText("🛡️ 正在執行品控檢測...")
        def callback(result):
            if result and (isinstance(result, int) or isinstance(result, float)) and result > 10:
                self.status_label.setText("✅ 品控檢測通過: 畫面正常渲染")
            else:
                self.status_label.setText("⚠️ 品控檢測失敗: 疑似黑屏或無渲染")
                
        js = """
        (function() {
            if (typeof window.__drawCount !== 'undefined') return window.__drawCount;
            return 0;
        })();
        """
        self.app.web_view.page().runJavaScript(js, callback)

    def send_to_pixel_generator(self):
        """將 AI 孵化器產生的代碼/名稱直接傳送至第 4 頁籤（像素生成器）"""
        name = self.name_input.text().strip() or f"ai_pixel_{int(time.time())}"
        if hasattr(self.app, 'left_tabs') and hasattr(self.app, 'pixel_generator'):
            # 切換至像素生成器 Tab
            self.app.left_tabs.setCurrentWidget(self.app.pixel_generator)
            # 填入建議名稱
            if hasattr(self.app.pixel_generator, 'folder_input'):
                if hasattr(self.app, 'log_to_console'):
                    self.app.log_to_console(f"👾 已將資產「{name}」傳送至像素視覺模組生成器，請選擇照片來源資料夾啟動生成！")

    def request_ai_tags(self):
        code = self.incubator_editor.toPlainText()
        if not code or code.startswith("// 🧬"):
            return
            
        self.status_label.setText("🏷️ AI 正在分析視覺特徵與標籤...")
        
        self.tag_worker = AITagSuggestionWorker(code, self.generator)
        self.tag_worker.tags_suggested.connect(self.on_tags_suggested)
        self.tag_worker.start()

    def on_tags_suggested(self, tags: dict):
        style_tags = tags.get("style_tags", [])
        self.ai_tags_display.setText(", ".join(style_tags) if style_tags else "無")
        self.current_tags = tags
        self.status_label.setText("✅ 分析完成")

    def save_as_original_asset(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "錯誤", "請輸入模組名稱！")
            return
            
        code = self.incubator_editor.toPlainText()
        if not code or code.startswith("// 🧬"):
            return
            
        immunity_stubs = self._get_immunity_stubs()
        full_code = code + "\n" + immunity_stubs
        
        prompt_text = self.current_prompt
        selected_model = self.current_model or "freeform"
        
        defaults = {
            "style_tags": ["AI_Generated", "Original"],
            "section_scores": {"intro": 0.5, "verse": 0.5, "build": 0.5, "drop": 0.5, "outro": 0.5},
            "energy_level": "medium"
        }
        tags = self.current_tags or defaults
        sha256_hash = hashlib.sha256(full_code.encode()).hexdigest()
        
        preset = {
            "id": f"ai_gen_{int(time.time())}",
            "title": name,
            "name": name,
            "code": full_code,
            "custom_html": "",
            "custom_css": "/* Auto-hidden controls */\ninput, select, button, textarea, label, fieldset, .dg, .lil-gui { display: none !important; visibility: hidden !important; }",
            "author": "AI Incubator",
            "license": "Original",
            "license_mode": "Original",
            "scaling_mode": "auto",
            "visual_dna": tags,
            "director_tags": tags,
            "provenance": {
                "origin": "ai_incubator",
                "generation_method": "prompt_generated",
                "base_algorithm": selected_model,
                "user_prompt": prompt_text,
                "parent_modules": [],
                "fingerprint_hash": sha256_hash
            },
            "used_in_videos": [],
            "used_count": 0,
            "date_added": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)
        
        save_path = os.path.join(save_dir, f"{name}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(preset, f, indent=4, ensure_ascii=False)
            
        if hasattr(self.app, 'refresh_presets_list'):
            self.app.cached_presets = None
            self.app.refresh_presets_list()
                
        self.status_label.setText("💾 原創資產已儲存")
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console(f"🧬 [AI 孵化器] 原創資產已儲存: {name}")
            
        QMessageBox.information(self, "儲存成功", f"原創資產 '{name}' 已成功儲存！可在 4K 離線渲染器中調用。")

    def start_mutation(self):
        current_code = self.incubator_editor.toPlainText().strip()
        if not current_code or "AI 孵化器" in current_code:
            QMessageBox.warning(self, "警告", "請先生成或提供基礎代碼再進行風格變異！")
            return
            
        self.btn_mutate.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("🎲 AI 正在生成 4 種視覺變異風格 (Cyberpunk / Minimalist / Fluid / Glitch)...")
        
        self.mutate_worker = AIMutateWorker(current_code, self.generator)
        self.mutate_worker.mutate_completed.connect(self.on_mutation_complete)
        self.mutate_worker.mutate_failed.connect(self.on_generation_failed)
        self.mutate_worker.start()

    def on_mutation_complete(self, results: list):
        self.progress_bar.hide()
        self.btn_mutate.setEnabled(True)
        self.status_label.setText(f"✅ 已成功生成 {len(results)} 種變異風格！")
        
        base_name = self.name_input.text().strip() or "mutated_asset"
        saved_count = 0
        
        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(workspace_dir, "custom_visuals")
        os.makedirs(save_dir, exist_ok=True)

        for item in results:
            style_name = item["style_name"].lower().replace(" ", "_")
            mutated_name = f"{base_name}_{style_name}_{int(time.time()) % 1000}"
            mutated_code = item["code"] + self._get_immunity_stubs()
            
            preset = {
                "id": f"ai_mut_{int(time.time())}_{saved_count}",
                "title": mutated_name,
                "name": mutated_name,
                "code": mutated_code,
                "custom_html": "",
                "custom_css": "/* Auto-hidden controls */\ninput, select, button, textarea, label, fieldset, .dg, .lil-gui { display: none !important; visibility: hidden !important; }",
                "author": "AI Incubator",
                "license": "Original",
                "license_mode": "Original",
                "scaling_mode": "auto",
                "visual_dna": { "geometry": { "type": "mutation", "topology": item["style_name"] } },
                "director_tags": { "style_tags": ["AI_Mutation", item["style_name"]] },
                "provenance": {
                    "origin": "ai_incubator",
                    "generation_method": "style_mutation",
                    "style_variant": item["style_name"],
                    "fingerprint_hash": item.get("fingerprint", "")
                },
                "used_in_videos": [],
                "used_count": 0,
                "date_added": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(os.path.join(save_dir, f"{mutated_name}.json"), "w", encoding="utf-8") as f:
                json.dump(preset, f, indent=4, ensure_ascii=False)
            saved_count += 1
            
        if hasattr(self.app, 'refresh_presets_list'):
            self.app.cached_presets = None
            self.app.refresh_presets_list()
            
        if hasattr(self.app, 'log_to_console'):
            self.app.log_to_console(f"🎲 [AI 孵化器] 一鍵生成並儲存了 {saved_count} 種視覺變異風格！")
            
        QMessageBox.information(self, "變異完成", f"已自動生成並儲存 {saved_count} 種獨特變異風格（Cyberpunk / Minimalist / Fluid / Glitch）至模組庫！")

    def _get_immunity_stubs(self) -> str:
        return """
// --- p5.js Immunity Stubs (AI Incubator) ---
(function() {
    if (typeof window.createP === 'undefined') window.createP = function() { return stubElement(); };
    if (typeof window.createDiv === 'undefined') window.createDiv = function() { return stubElement(); };
    if (typeof window.createButton === 'undefined') window.createButton = function() { return stubElement(); };
    if (typeof window.createSlider === 'undefined') window.createSlider = function() { return stubElement(); };
    if (typeof window.select === 'undefined') window.select = function() { return stubElement(); };
    if (typeof window.selectAll === 'undefined') window.selectAll = function() { return [stubElement()]; };
    
    function stubElement() {
        return {
            html: function() { return this; },
            position: function() { return this; },
            style: function() { return this; },
            class: function() { return this; },
            id: function() { return this; },
            value: function() { return 0; },
            mouseClicked: function() { return this; },
            mousePressed: function() { return this; },
            mouseReleased: function() { return this; },
            hide: function() { return this; },
            show: function() { return this; },
            size: function() { return this; },
            parent: function() { return this; },
            child: function() { return this; }
        };
    }
    
    if (typeof window.loadImage !== 'undefined') {
        const _origLoadImage = window.loadImage;
        window.loadImage = function(path, successCallback, failureCallback) {
            try {
                return _origLoadImage(path, successCallback, failureCallback);
            } catch(e) {
                let img = createImage(1, 1);
                if (successCallback) setTimeout(() => successCallback(img), 10);
                return img;
            }
        };
    }
    
    window.Tone = window.Tone || {
        Player: function() { return { toDestination: function(){ return this; }, start: function(){} }; },
        Buffer: function() { return { onload: function(){} }; },
        start: function() { return Promise.resolve(); }
    };
    
    window.THREE = window.THREE || {
        Scene: function() {}, PerspectiveCamera: function() {}, WebGLRenderer: function() { 
            return { setSize: function(){}, render: function(){}, domElement: document.createElement('canvas') }; 
        }
    };
    
    window.ml5 = window.ml5 || {
        poseNet: function() { return { on: function(){} }; },
        imageClassifier: function() { return { classify: function(){} }; }
    };

    if (typeof p5 !== 'undefined' && p5.Vector) {
        if (!p5.Vector.prototype.limit) p5.Vector.prototype.limit = function(m) {
            let s = this.magSq();
            if (s > m * m) {
                this.div(Math.sqrt(s)).mult(m);
            }
            return this;
        };
    }

    if (typeof window.beginGeometry === 'undefined') window.beginGeometry = function() {};
    if (typeof window.endGeometry === 'undefined') window.endGeometry = function() {};

    window.addEventListener('keydown', function(e) {
        if (!window.__audioData) window.__audioData = { bass: 0.1, mid: 0.1, high: 0.1, sub_bass: 0.1 };
        var k = e.key ? e.key.toLowerCase() : '';
        if (k === 'b') { window.__audioData.bass = 1.0; window.__audioData.sub_bass = 1.0; }
        if (k === 'm') { window.__audioData.mid = 1.0; }
        if (k === 'h') { window.__audioData.high = 1.0; }
    });
    window.addEventListener('keyup', function(e) {
        if (window.__audioData) {
            var k = e.key ? e.key.toLowerCase() : '';
            if (k === 'b') { window.__audioData.bass = 0.1; window.__audioData.sub_bass = 0.1; }
            if (k === 'm') { window.__audioData.mid = 0.1; }
            if (k === 'h') { window.__audioData.high = 0.1; }
        }
    });

    var _decayInterval = setInterval(function() {
        if (window.__audioData) {
            window.__audioData.bass = Math.max(0.05, window.__audioData.bass * 0.92);
            window.__audioData.sub_bass = Math.max(0.05, window.__audioData.sub_bass * 0.92);
            window.__audioData.mid = Math.max(0.05, window.__audioData.mid * 0.92);
            window.__audioData.high = Math.max(0.05, window.__audioData.high * 0.92);
        }
    }, 30);
})();
"""
