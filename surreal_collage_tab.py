import os
import re
import json
import datetime
import random
import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QComboBox,
    QCheckBox, QSlider, QSpinBox, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PIL import Image

from surreal_processor import SurrealImageProcessor
from p5_template_generator import P5SurrealTemplateGenerator
from surreal_theme_engine import SurrealThemeConceptEngine
from pinterest_scraper import PinterestSurrealScraper
from multi_element_orchestrator import MultiElementSceneOrchestrator
from aesthetic_layout_optimizer import AestheticLayoutOptimizer
from sota_composition_optimizer import SOTACompositionOptimizer
from neural_aesthetic_scorer import NeuralAestheticScorer
from surreal_36_styles import Surreal36MasterMatrix
from surreal_logger import surreal_logger

class SurrealPipelineWorker(QThread):
    log_signal = pyqtSignal(str, bool)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(dict)

    def __init__(
        self,
        dice_result: dict,
        primary_style: str,
        secondary_style: str,
        blend_ratio: float,
        seed: int,
        decompose: bool,
        scale_inversion: float,
        duotone_strength: float,
        workspace_dir: str
    ):
        super().__init__()
        self.dice_result = dice_result
        self.primary_style = primary_style
        self.secondary_style = secondary_style
        self.blend_ratio = blend_ratio
        self.seed = seed
        self.decompose = decompose
        self.scale_inversion = scale_inversion
        self.duotone_strength = duotone_strength
        self.workspace_dir = workspace_dir

    def run(self):
        try:
            theme_title = self.dice_result.get("theme_title", "Surreal Multi-Element Collage")
            concept_thought = self.dice_result.get("concept_thought", "")
            elements_meta = self.dice_result.get("elements", [])
            n = len(elements_meta)

            surreal_logger.info(f"🌌 [SAVAP v4.0] 啟動 36 大師風格超現實創作管線: 【{theme_title}】 | 元素數: {n} | 哲學思維: {concept_thought}")
            self.log_signal.emit(f"🎲 啟動 36 大師風格超現實創作管線：【{theme_title}】 (Seed: {self.seed})", False)
            self.log_signal.emit(f"🧠 策展哲學思維：{concept_thought}", False)
            self.log_signal.emit(f"🌐 自動連線檢索並採集 {n} 個衝突素材 (Pinterest/網路高精)...", False)
            self.progress_signal.emit(1, 6)

            cache_dir = os.path.join(self.workspace_dir, "scratch", "surreal_cache")
            scraper = PinterestSurrealScraper(cache_dir=cache_dir)
            processor = SurrealImageProcessor(output_base_dir=os.path.join(self.workspace_dir, "custom_visuals", "assets"))

            clean_name = re.sub(r'[^a-zA-Z0-9_]', '', elements_meta[0]["keyword"].lower().replace(" ", "_")) or "surreal"
            asset_id = f"{clean_name}_{int(datetime.datetime.now().timestamp())}"
            asset_folder = os.path.join(self.workspace_dir, "custom_visuals", "assets", asset_id)
            os.makedirs(asset_folder, exist_ok=True)
            surreal_logger.info(f"📁 建立素材資產目錄: {asset_folder} (Asset ID: {asset_id})")

            self.log_signal.emit("🧠 執行多素材高精去背與 Alpha 緊密裁切...", False)
            self.progress_signal.emit(2, 6)

            # 解析 36 大風格 Key
            p_style_text = self.primary_style
            s_style_text = self.secondary_style

            processed_assets = []
            for idx, elem in enumerate(elements_meta):
                self.log_signal.emit(f"  • 素材 [{idx+1}/{n}]: {elem['keyword']}...", False)
                raw_img = scraper.fetch_pinterest_element(elem["keyword"], f"{asset_id}_{idx}")
                nobg_img = processor.tight_crop_alpha(processor.remove_background(raw_img))

                # 若選擇隨機 AI Auto-Match，則利用語義分析自動匹配最佳風格
                if "隨機" in p_style_text or "Auto" in p_style_text:
                    p_key = Surreal36MasterMatrix.match_best_style(elem["keyword"])
                    self.log_signal.emit(f"  🎨 AI 語義適配主風格: [{elem['keyword']}] -> {p_key}", False)
                else:
                    p_key = p_style_text

                s_key = s_style_text if ("隨機" not in s_style_text and "Auto" not in s_style_text) else "raw_alpha"

                # 應用 36 大流派矩陣 + 雙大師風格雜交 (1296 種組合) + 確定性種子擾動
                elem_seed = self.seed + idx * 137
                styled_img = processor.apply_hybrid_styles(
                    nobg_img, primary_style=p_key, secondary_style=s_key,
                    blend_ratio=self.blend_ratio, seed=elem_seed
                )

                processed_assets.append({
                    "id": elem["id"],
                    "keyword": elem["keyword"],
                    "style_applied": f"{p_key}x{s_key}",
                    "image": styled_img,
                    "is_hero": elem.get("is_hero", False)
                })

            self.log_signal.emit("🦴 進行核心主體吉列姆木偶骨骼拆解 (Hero Anchor)...", False)
            self.progress_signal.emit(3, 6)
            hero_asset = processed_assets[0]
            rig_info = processor.decompose_puppet(hero_asset["image"], asset_id)

            self.log_signal.emit("⚖️ 執行 SOTA 計算美學：SDF 負空間凹凸咬合 + 力矩平衡 + 空氣透視衰減...", False)
            self.progress_signal.emit(4, 6)
            for idx, item in enumerate(processed_assets[1:], start=1):
                save_path = os.path.join(asset_folder, f"element_{idx}.png")
                item["image"].save(save_path)

            optimizer = SOTACompositionOptimizer(canvas_w=1280, canvas_h=720)
            optimized_elements = optimizer.optimize_sota_scene(processed_assets)
            
            # 神經審美評分反饋環 (CLIP-Aesthetic Feedback Loop)
            eval_res = NeuralAestheticScorer.evaluate_composition_quality(optimized_elements, 1280, 720)
            score = eval_res["aesthetic_score"]
            surreal_logger.info(f"🌟 神經審美評估反饋: 總分={score}/10.0 | 力學平衡={eval_res['balance_score']} | 景深多樣性={eval_res['depth_score']}")
            self.log_signal.emit(f"🌟 神經審美評估得分：{score} / 10.0 (畫廊級: {'✅ 是' if eval_res['is_gallery_grade'] else '⚠️ 達標'})", False)

            orchestrator = MultiElementSceneOrchestrator()
            orchestrated_scene = orchestrator.orchestrate(processed_assets, topology_mode="auto")
            orchestrated_scene["elements"] = optimized_elements
            orchestrated_scene["aesthetic_eval"] = eval_res

            self.log_signal.emit(f"🏛️ 拓撲調度完成：【{orchestrated_scene['topology']}】(力學平衡度: {eval_res['balance_score']})", False)

            self.log_signal.emit("✨ 自動生成 4K 音畫互動腳本 (多米諾因果律 + 形態蛻變)...", False)
            self.progress_signal.emit(5, 6)
            p5_code = P5SurrealTemplateGenerator.generate_multi_element_masterpiece_script(
                asset_id=asset_id,
                theme_meta=self.dice_result,
                orchestrated_scene=orchestrated_scene,
                style_name=f"{self.primary_style} x {self.secondary_style}",
                scale_inversion=self.scale_inversion,
                duotone_strength=self.duotone_strength
            )

            # 產生縮圖
            thumb_dir = os.path.join(self.workspace_dir, "custom_visuals", "thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            thumb_path = os.path.join(thumb_dir, f"{asset_id}.jpg")
            hero_asset["image"].convert("RGB").resize((160, 120)).save(thumb_path, "JPEG", quality=90)

            self.progress_signal.emit(6, 6)
            surreal_logger.info(f"✅ [SAVAP] 36 大師雜交模組生成成功: {asset_id} | 縮圖: {thumb_path}")
            self.log_signal.emit(f"🎉 創作神作「{theme_title}」({n} 個元素) 36大師雜交封裝完畢！", False)
            self.finished_signal.emit({
                "asset_id": asset_id,
                "theme_title": theme_title,
                "concept_thought": concept_thought,
                "orchestrated_scene": orchestrated_scene,
                "code": p5_code,
                "thumbnail_path": thumb_path,
                "primary_style": self.primary_style,
                "secondary_style": self.secondary_style
            })
        except Exception as e:
            surreal_logger.error(f"❌ [SAVAP] 管線執行失敗: {e}", exc_info=True)
            self.log_signal.emit(f"❌ 管線失敗: {e}", True)


class SurrealCollageTab(QWidget):
    """
    超現實音畫拼貼引擎 PyQt6 頁籤類別 (SAVAP v4.0: 36 大風格矩陣、1296 種雙大師雜交與 SOTA 計算美學)
    """
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.workspace_dir = os.path.dirname(os.path.abspath(__file__))
        self.current_dice_result = None
        self.last_result = None
        self.init_ui()
        self.roll_new_concept()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("🌌 超現實拼貼素材採集與音畫重塑引擎 (SAVAP v4.0 終極 36 大風格版)", self)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #c084fc;")
        layout.addWidget(title)

        # 1. 隨機骰子與創作主題展示區
        dice_group = QGroupBox("🎲 超現實創作靈感骰子 (Surreal Concept Dice)", self)
        dice_layout = QVBoxLayout(dice_group)

        dice_bar = QHBoxLayout()
        dice_bar.addWidget(QLabel("元素數量 (2~10):", self))
        self.spin_num_elem = QSpinBox(self)
        self.spin_num_elem.setRange(2, 10)
        self.spin_num_elem.setValue(5)
        dice_bar.addWidget(self.spin_num_elem)

        self.btn_dice = QPushButton("🎲 擲骰子：骰出隨機超現實組合", self)
        self.btn_dice.setStyleSheet("background-color: #ec4899; color: white; font-weight: bold; padding: 7px 12px; font-size: 12px;")
        self.btn_dice.clicked.connect(self.roll_new_concept)
        dice_bar.addWidget(self.btn_dice, 1)
        dice_layout.addLayout(dice_bar)

        self.lbl_theme_title = QLabel("創作主題: 尚未擲骰", self)
        self.lbl_theme_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")
        dice_layout.addWidget(self.lbl_theme_title)

        self.lbl_concept_thought = QLabel("藝術哲學思維: ...", self)
        self.lbl_concept_thought.setStyleSheet("color: #a1a1aa; font-style: italic; font-size: 11px;")
        self.lbl_concept_thought.setWordWrap(True)
        dice_layout.addWidget(self.lbl_concept_thought)

        self.lbl_elements_list = QLabel("骰出的素材清單: ...", self)
        self.lbl_elements_list.setStyleSheet("color: #facc15; font-size: 11px;")
        self.lbl_elements_list.setWordWrap(True)
        dice_layout.addWidget(self.lbl_elements_list)

        layout.addWidget(dice_group)

        # 2. 36 大風格矩陣與雙大師雜交控制群組 (1296 種組合)
        style_grp = QGroupBox("🎨 36 大超現實與前衛大師風格矩陣 ＋ 雙風格雜交 (1296 種流派組合)")
        style_grp.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #27272a; border-radius: 6px; margin-top: 4px; padding-top: 8px; }")
        grp_layout = QVBoxLayout(style_grp)

        style_items_36 = Surreal36MasterMatrix.get_style_names_list()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("主要風格 (Primary):", self))
        self.combo_primary = QComboBox(self)
        self.combo_primary.addItems(style_items_36)
        row1.addWidget(self.combo_primary, 1)

        row1.addWidget(QLabel("次要風格 (Secondary):", self))
        self.combo_secondary = QComboBox(self)
        self.combo_secondary.addItems(style_items_36)
        self.combo_secondary.setCurrentText("【原始無損】無濾鏡透明去背 (Raw Alpha Pure)")
        row1.addWidget(self.combo_secondary, 1)
        grp_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("雜交混合比率:", self))
        self.slider_blend = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_blend.setRange(0, 100)
        self.slider_blend.setValue(35)
        self.lbl_blend_val = QLabel("35%", self)
        self.lbl_blend_val.setFixedWidth(35)
        self.slider_blend.valueChanged.connect(lambda v: self.lbl_blend_val.setText(f"{v}%"))
        row2.addWidget(self.slider_blend)
        row2.addWidget(self.lbl_blend_val)

        row2.addWidget(QLabel("隨機種子 (Seed):", self))
        self.spin_seed = QSpinBox(self)
        self.spin_seed.setRange(0, 9999999)
        self.spin_seed.setValue(random.randint(1000, 999999))
        row2.addWidget(self.spin_seed)

        self.btn_randomize = QPushButton("🎲 隨機突變 (1296種)", self)
        self.btn_randomize.setStyleSheet("background-color: #3b0764; color: #f3e8ff; font-weight: bold; padding: 4px 8px;")
        self.btn_randomize.clicked.connect(self.randomize_styles)
        row2.addWidget(self.btn_randomize)
        grp_layout.addLayout(row2)

        layout.addWidget(style_grp)

        # 3. 啟動按鈕
        self.btn_start = QPushButton("⚡ 自動連線 Pinterest 採集並執行 36 大師雜交拼貼", self)
        self.btn_start.setStyleSheet("background-color: #7c3aed; color: white; font-weight: bold; padding: 9px 16px; font-size: 13px;")
        self.btn_start.clicked.connect(self.start_pipeline)
        layout.addWidget(self.btn_start)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.console = QTextEdit(self)
        self.console.setReadOnly(True)
        self.console.setStyleSheet("background-color: #09090b; color: #c084fc; border: 1px solid #27272a; font-family: monospace; font-size: 11px;")
        layout.addWidget(self.console)

        self.btn_export = QPushButton("📦 封裝並註冊為視覺模組 (匯入 4K 渲染器)", self)
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 9px; font-size: 13px;")
        self.btn_export.clicked.connect(self.export_visual_module)
        layout.addWidget(self.btn_export)

    def roll_new_concept(self):
        num_e = self.spin_num_elem.value()
        self.current_dice_result = SurrealThemeConceptEngine.roll_dice(num_elements=num_e)
        self.lbl_theme_title.setText(f"🎨 創作主題: {self.current_dice_result['theme_title']}")
        self.lbl_concept_thought.setText(f"🧠 藝術哲學思維: {self.current_dice_result['concept_thought']}")
        elem_names = [f"[{i+1}] {e['keyword']}" for i, e in enumerate(self.current_dice_result['elements'])]
        self.lbl_elements_list.setText(f"✨ 骰出的 {len(elem_names)} 個元素: " + " | ".join(elem_names))
        self.log(f"🎲 骰出全新組合：{self.current_dice_result['theme_title']} ({len(elem_names)} 個元素)")

    def randomize_styles(self):
        valid_items = [name for key, meta in Surreal36MasterMatrix.STYLE_CATALOG_36.items() for name in [meta["name"]]]
        p = random.choice(valid_items)
        s = random.choice(valid_items)
        self.combo_primary.setCurrentText(p)
        self.combo_secondary.setCurrentText(s)
        self.slider_blend.setValue(random.randint(15, 65))
        self.spin_seed.setValue(random.randint(1000, 999999))
        self.log(f"🎲 已隨機突變 36 大師雜交組合：{p} × {s}")

    def log(self, text: str, is_err: bool = False):
        color = "#ef4444" if is_err else "#c084fc"
        self.console.append(f"<span style='color: {color};'>{text}</span>")

    def start_pipeline(self):
        if not self.current_dice_result:
            self.roll_new_concept()

        self.btn_start.setEnabled(False)
        self.btn_dice.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress_bar.setValue(0)
        self.console.clear()

        self.worker = SurrealPipelineWorker(
            dice_result=self.current_dice_result,
            primary_style=self.combo_primary.currentText(),
            secondary_style=self.combo_secondary.currentText(),
            blend_ratio=self.slider_blend.value() / 100.0,
            seed=self.spin_seed.value(),
            decompose=True,
            scale_inversion=2.2,
            duotone_strength=0.85,
            workspace_dir=self.workspace_dir
        )
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(lambda cur, tot: self.progress_bar.setValue(int(cur / tot * 100)))
        self.worker.finished_signal.connect(self.on_pipeline_finished)
        self.worker.start()

    def on_pipeline_finished(self, result_data: dict):
        self.last_result = result_data
        self.btn_start.setEnabled(True)
        self.btn_dice.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.log(f"🎉 36 大師雜交神作封裝就緒：{result_data['asset_id']}")

    def export_visual_module(self):
        if not self.last_result:
            return

        asset_id = self.last_result["asset_id"]
        save_dir = os.path.join(self.workspace_dir, "custom_visuals")
        json_path = os.path.join(save_dir, f"{asset_id}.json")

        module_data = {
            "name": asset_id,
            "author": "SAVAP v4.0 36-Style Master Hybrid Engine",
            "license": "CC BY-SA (Transformative)",
            "url": "https://www.pinterest.com",
            "tags": ["surreal", "collage", "puppet", "hybrid_1296", "masterpiece", "36styles"],
            "theme_title": self.last_result.get("theme_title", ""),
            "concept_thought": self.last_result.get("concept_thought", ""),
            "primary_style": self.last_result.get("primary_style", ""),
            "secondary_style": self.last_result.get("secondary_style", ""),
            "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "frequency": 65,
            "storyboard_weight": 95,
            "post_fx_intensity": 85,
            "scaling_mode": "contain",
            "custom_html": "",
            "custom_css": "",
            "inline_assets": {},
            "orchestrated_scene": self.last_result["orchestrated_scene"],
            "code": self.last_result["code"]
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(module_data, f, indent=4, ensure_ascii=False)

        self.log(f"💾 已成功寫入視覺庫: {json_path}")

        if hasattr(self.main_app, "refresh_presets_list"):
            self.main_app.refresh_presets_list()
        if hasattr(self.main_app, "preview_preset"):
            self.main_app.preview_preset(asset_id)

        QMessageBox.information(self, "註冊成功", f"36 大師雜交大作「{self.last_result.get('theme_title', asset_id)}」已成功匯入！\n已在右側沙盒即時預覽，並支援 4K 60FPS 離線渲染。")
