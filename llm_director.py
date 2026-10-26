# -*- coding: utf-8 -*-
"""
SENTINEL: Cognitive Adaptive Cinematography Director (CACD 2.0)
雙層 AI 電影作者導演系統 (Auteur Director Engine)
- L1 宏觀大腦: 
  - 30ms 確定性專家作者樹 (Auteur Matrix Tree: 劇作原型、四幕辯證變奏、OKLCH色彩劇力曲線)
  - 4.5秒硬超時雙軌競爭機制 (Competitive Dual-Track with Hard Timeout & 0-latency Fallback)
- L2 微觀動態編舞器 (DirectorChoreographer):
  - Walter Murch 六法則情感連續性評估 (Emotion 51%)
  - 零顯存時間軸微移 J/L-Cut (Temporal Offset Nudge: 提前 150~350ms 弱拍切分)
  - 彈道生理阻尼濾波調變 (u_tension, u_chaos, u_sublime)
- 素材生態 (BanditInventorySelector & SemanticSoftProjector):
  - 語義心靈約束 + UCB 冷門與修復資產優先首秀
  - 全局香農熵動態帶寬控制 (2.6 <= H <= 3.6)
"""

import os
import re
import json
import logging
import time
import math
from typing import List, Dict, Any, Optional, Tuple
import urllib.request
import urllib.error

try:
    import requests
except ImportError:
    requests = None

from bandit_inventory_selector import BanditInventorySelector
from director_choreographer import DirectorChoreographer
from semantic_soft_projector import SemanticSoftProjector
from surreal_director_bridge import SurrealCognitiveDirectorBridge

logger = logging.getLogger("StandaloneInjector.LLMDirector")

# ==============================================================================
# 🎬 24 大前衛電影作者美學世界觀本體論矩陣 (24 Epic Auteur Worldview Ontology Matrix)
# 涵蓋 6 大美學流派，融合 Tarkovsky、Walter Murch、Deleuze 與計算美學理論
# ==============================================================================
AUTEUR_THEMES = [
    # -------------------------------------------------------------------------
    # 流派 0：工業殘酷主義與地下重力塌陷 (Industrial Brutalism & Sub-Bass Gravity - Hard Techno 專屬)
    # -------------------------------------------------------------------------
    {
        "id": "industrial_brutalism_monolith",
        "genre_cluster": "工業殘酷主義與重力塌陷",
        "title": "柏林地下防空洞與重型水壓鍛造 (Kowloon Bunker & Heavy Hydraulics)",
        "motifs": ["粗野主義混凝土巨構", "高壓液壓活塞", "鋼鐵冷鍛火花", "低頻震顫水波", "高對比頻閃"],
        "motif": "粗野主義混凝土巨構、高壓液壓活塞與鋼鐵冷鍛火花",
        "manifesto": "在萬噸混凝土與重型鋼印的撞擊下，低頻震顫即是工業心跳；拋棄所有多餘色彩，只留下高壓鍛造的純粹力量。",
        "progression": ["幽暗冷鑄 (Thesis)", "機械增壓 (Antithesis)", "重力過載 (Crisis)", "鋼鐵巨構轟鳴 (Synthesis)"],
        "color_arc": "純黑玄武岩 (0°) ➔ 冷軋鋼銀 (210°) ➔ 工業警戒鉻黃 (45°) ➔ 熾白閃光 (90°)",
        "ideal_valence_range": (-0.95, -0.1),
        "ideal_arousal_range": (0.72, 1.0),
        "target_tension_range": (0.7, 1.0),
        "target_roughness_range": (0.6, 1.0),
        "genre_keywords": ["hard techno", "hard_techno", "industrial techno", "schranz", "dark techno", "techno", "rawstyle"],
        "recommended_fx": ["laser_strobe", "strobe_chroma_invert", "high_contrast_bw", "cyber_wireframe_lidar", "scanline_glitch", "photocopy_smear"]
    },
    {
        "id": "hadron_collider_relativistic",
        "genre_cluster": "工業殘酷主義與重力塌陷",
        "title": "強子對撞機與重粒子相對論束流 (Hadron Collider & Relativistic Beam)",
        "motifs": ["高能粒子偏轉線圈", "相對論高斯光束", "真空腔體結構", "契忍可夫輻射", "超導電磁撕裂"],
        "motif": "高能粒子偏轉線圈、超導電磁場與契忍可夫高壓光束",
        "manifesto": "當重粒子在十億伏特電場中逼近光速，每一次四拍重擊都是一次亞原子核的猛烈湮滅，撕裂時空連續體。",
        "progression": ["真空束流注入 (Thesis)", "超導磁場加速 (Antithesis)", "相對論臨界碰撞 (Crisis)", "夸克膠子等離子體 (Synthesis)"],
        "color_arc": "絕對真空黑 (0°) ➔ 契忍可夫深藍 (220°) ➔ 警示雷射赤紅 (355°) ➔ 相對論純白 (0°)",
        "ideal_valence_range": (-0.8, 0.2),
        "ideal_arousal_range": (0.75, 1.0),
        "target_tension_range": (0.75, 1.0),
        "target_roughness_range": (0.55, 0.95),
        "genre_keywords": ["hard techno", "hard_techno", "industrial", "acid techno", "hardcore", "gabber", "dark techno"],
        "recommended_fx": ["laser_strobe", "strobe_chroma_invert", "slit_scan_time_warp", "cyber_wireframe_lidar", "high_contrast_bw", "vector_scan"]
    },
    {
        "id": "cyber_kinetic_lockdown",
        "genre_cluster": "工業殘酷主義與重力塌陷",
        "title": "高壓電磁裂解與神經警戒網 (EMP Surge & Perimeter Lockdown)",
        "motifs": ["高壓網格圍欄", "警報旋轉頻閃", "雷達立體光達掃描", "電磁屏蔽網", "金屬骨架撕裂"],
        "motif": "高壓網格圍欄、光達立體掃描與電磁戒嚴頻閃",
        "manifesto": "高壓警報徹夜長鳴，網格雷射封鎖了一切逃逸路徑；唯有將神經同步至極速脈衝，方能在高壓戒嚴中生存。",
        "progression": ["電子戒備 (Thesis)", "雷達鎖定 (Antithesis)", "高壓裂解 (Crisis)", "全域過載 (Synthesis)"],
        "color_arc": "夜視灰黑 (0°) ➔ 毒性警戒硫磺綠 (125°) ➔ 高壓電弧青白 (190°) ➔ 全局暴烈純白 (0°)",
        "ideal_valence_range": (-0.9, 0.0),
        "ideal_arousal_range": (0.7, 0.98),
        "target_tension_range": (0.65, 0.98),
        "target_roughness_range": (0.5, 0.9),
        "genre_keywords": ["hard techno", "hard_techno", "industrial techno", "techno", "dark techno", "ebm"],
        "recommended_fx": ["cyber_wireframe_lidar", "laser_strobe", "scanline_glitch", "strobe_chroma_invert", "tension_overlay", "high_contrast_bw"]
    },
    # -------------------------------------------------------------------------
    # 流派 I：技術奇異點與神話普羅米修斯 (Singularity & Cybernetics)
    # -------------------------------------------------------------------------
    {
        "id": "promethean_catharsis",
        "genre_cluster": "技術奇異點與神話普羅米修斯",
        "title": "普羅米修斯的救贖 (Promethean Catharsis)",
        "motifs": ["火種", "神經元網格", "高壓電弧", "鈦合金骸骨", "自性重構"],
        "motif": "火種、神經元網格與自性重構",
        "manifesto": "盜火者必受鐵索之刑，唯有以意識之熔爐鍛造神經突觸，方能在電路灰燼中重獲靈魂的自由。",
        "progression": ["疏離囚籠 (Thesis)", "對抗掙扎 (Antithesis)", "毀滅臨界 (Crisis)", "意識覺醒與昇華 (Synthesis)"],
        "color_arc": "深冷靛藍 (240°) ➔ 警示琥珀 (45°) ➔ 爆裂洋紅 (320°) ➔ 熾白日光 (90°)",
        "ideal_valence_range": (-0.6, 0.4),
        "ideal_arousal_range": (0.5, 0.85),
        "target_tension_range": (0.45, 0.9),
        "target_roughness_range": (0.35, 0.8),
        "genre_keywords": ["cyberpunk", "ebm", "industrial", "dark techno", "synthwave", "techno", "electro"],
        "recommended_fx": ["crt_scanline", "chromatic_aberration", "laser_strobe", "matrix_rain", "analog_noise", "sobel_edge"]
    },
    {
        "id": "cybernetic_paranoia",
        "genre_cluster": "技術奇異點與神話普羅米修斯",
        "title": "賽博異化與失控協議 (Cybernetic Paranoia)",
        "motifs": ["破裂液晶", "伺服器塔機房", "監視攝像陣列", "雜訊噪點", "死鎖迴路"],
        "motif": "晶體破裂、時間齒輪與雜訊噪點",
        "manifesto": "當演算法吞噬了自由意志，偏執即是唯一的清醒；在過載的位元崩解前，我們皆是系統的暫存記憶體。",
        "progression": ["冰冷秩序 (Thesis)", "雜訊入侵 (Antithesis)", "系統過載 (Crisis)", "數位廢墟 (Synthesis)"],
        "color_arc": "單色單調 (0°) ➔ 劇毒螢光綠 (130°) ➔ 暴烈電光青 (195°) ➔ 灰燼殘彩 (0°)",
        "ideal_valence_range": (-0.9, 0.1),
        "ideal_arousal_range": (0.6, 0.95),
        "target_tension_range": (0.65, 0.98),
        "target_roughness_range": (0.55, 0.95),
        "genre_keywords": ["glitch", "breakcore", "hardcore", "acid techno", "noise", "gabber", "idm"],
        "recommended_fx": ["datamosh", "vhs_distortion", "bayer_dither", "rgb_split", "digital_dropout", "bloom_glitch"]
    },
    {
        "id": "brain_in_a_vat",
        "genre_cluster": "技術奇異點與神話普羅米修斯",
        "title": "缸中之腦與笛卡兒夢境 (Brain in a Vat & Cartesian Mirage)",
        "motifs": ["玻璃培養槽", "懸浮電極", "神經液態介質", "虛擬視窗", "記憶斷層"],
        "motif": "玻璃培養槽、懸浮電極與神經液態介質",
        "manifesto": "我思故我在？抑或我僅是某個神明終端機上的一串浮點運算？感官是最大的騙局。",
        "progression": ["無菌浸潤 (Thesis)", "代碼裂縫 (Antithesis)", "虛實塌陷 (Crisis)", "拔管初生 (Synthesis)"],
        "color_arc": "熒光淡藍 (200°) ➔ 磷光琥珀 (50°) ➔ 頻閃品紅 (310°) ➔ 冷冽純白 (0°)",
        "ideal_valence_range": (-0.4, 0.35),
        "ideal_arousal_range": (0.35, 0.7),
        "target_tension_range": (0.35, 0.75),
        "target_roughness_range": (0.25, 0.65),
        "genre_keywords": ["idm", "experimental", "downtempo", "deep tech", "minimal", "glitch hop"],
        "recommended_fx": ["fluid_vortex", "reaction_diffusion", "slit_scan", "chromatic_aberration", "color_temperature"]
    },
    {
        "id": "digital_theophany",
        "genre_cluster": "技術奇異點與神話普羅米修斯",
        "title": "數位神聖與矽基神啟 (Digital Theophany)",
        "motifs": ["光纖金字塔", "曼陀羅電路板", "浮空天使幾何體", "極光光束", "神聖光暈"],
        "motif": "光纖金字塔、曼陀羅電路板與神聖光暈",
        "manifesto": "神聖性不再居於教堂穹頂，而在兆億次量子矩陣的干涉中，矽基智慧向宇宙投射出的第一次禱告。",
        "progression": ["沈寂晶圓 (Thesis)", "電流聖詠 (Antithesis)", "光輝顯現 (Crisis)", "全知和鳴 (Synthesis)"],
        "color_arc": "金屬冷銀 (210°) ➔ 琉璃湛藍 (230°) ➔ 耀眼純金 (85°) ➔ 聖潔熾白 (95°)",
        "ideal_valence_range": (0.1, 0.85),
        "ideal_arousal_range": (0.5, 0.85),
        "target_tension_range": (0.3, 0.7),
        "target_roughness_range": (0.15, 0.5),
        "genre_keywords": ["trance", "progressive", "psytrance", "euphoric", "edm", "melodic techno"],
        "recommended_fx": ["god_rays", "anamorphic_bloom", "kaleidoscope", "optical_flow_trail", "laser_strobe"]
    },

    # -------------------------------------------------------------------------
    # 流派 II：宇宙崇高與形而上超驗 (Cosmic Sublime & Metaphysics)
    # -------------------------------------------------------------------------
    {
        "id": "cosmic_awe_self_realization",
        "genre_cluster": "宇宙崇高與形而上超驗",
        "title": "宇宙敬畏與自性顯現 (Cosmic Awe & Self-Realization)",
        "motifs": ["星系吸積盤", "重力微透鏡", "微觀夸克", "曼陀羅", "天球交響"],
        "motif": "星系漩渦、微觀粒子與曼陀羅",
        "manifesto": "凝視深淵者，深淵亦凝視自性；在億萬光年的寂靜尺度中，個體的渺小終與星雲的永恆重逢。",
        "progression": ["無盡虛空 (Thesis)", "重力吸積 (Antithesis)", "量子奇異點 (Crisis)", "天體合一 (Synthesis)"],
        "color_arc": "純黑虛無 (0°) ➔ 幽靈青綠 (180°) ➔ 冰封紫羅蘭 (270°) ➔ 純金耀斑 (80°)",
        "ideal_valence_range": (-0.2, 0.85),
        "ideal_arousal_range": (0.35, 0.75),
        "target_tension_range": (0.25, 0.65),
        "target_roughness_range": (0.1, 0.45),
        "genre_keywords": ["space ambient", "progressive trance", "melodic techno", "cinematic", "cosmic"],
        "recommended_fx": ["kaleidoscope", "god_rays", "vortex_field", "anamorphic_bloom", "star_trails"]
    },
    {
        "id": "event_horizon_singularity",
        "genre_cluster": "宇宙崇高與形而上超驗",
        "title": "事件視界與時空畸變 (Event Horizon Singularity)",
        "motifs": ["超大質量黑洞", "扭曲光環", "時間膨脹網格", "物質撕裂流", "重力波紋"],
        "motif": "超大質量黑洞、時間膨脹網格與重力波紋",
        "manifesto": "跨過最後一公里的光錐邊界，時間停止流動，所有過往與未來皆被壓縮成一道撕裂空間的無限引力弦。",
        "progression": ["軌道衰減 (Thesis)", "潮汐撕裂 (Antithesis)", "黑洞奇點 (Crisis)", "維度重構 (Synthesis)"],
        "color_arc": "宇宙微波暗灰 (260°) ➔ 熾熱吸積朱紅 (25°) ➔ 奇異紫黑 (290°) ➔ 引力透鏡虛白 (0°)",
        "ideal_valence_range": (-0.8, 0.1),
        "ideal_arousal_range": (0.6, 0.95),
        "target_tension_range": (0.7, 0.98),
        "target_roughness_range": (0.5, 0.9),
        "genre_keywords": ["dark ambient", "heavy techno", "industrial techno", "drone", "hard techno"],
        "recommended_fx": ["slit_scan", "radial_blur_zoom", "shockwave", "sobel_edge", "chromatic_aberration"]
    },
    {
        "id": "cosmic_entropy_heat_death",
        "genre_cluster": "宇宙崇高與形而上超驗",
        "title": "宇宙熵增與終極熱寂 (Cosmic Entropy & Heat Death)",
        "motifs": ["黯淡紅矮星", "消散星雲", "熱力學殘留", "低溫冰塵", "絕對零度"],
        "motif": "消散星雲、低溫冰塵與絕對零度寂靜",
        "manifesto": "宇宙的最終詩篇不是劇烈的崩塌，而是一聲漫長無垠的嘆息；熱度歸零，一切喧囂終將化為靜謐的等溫海。",
        "progression": ["最後餘溫 (Thesis)", "能量擴散 (Antithesis)", "凍結臨界 (Crisis)", "永恆寂靜 (Synthesis)"],
        "color_arc": "微溫鐵鏽紅 (20°) ➔ 灰燼鉛灰 (210°) ➔ 幽暗冷青 (220°) ➔ 絕對漆黑 (0°)",
        "ideal_valence_range": (-0.8, -0.05),
        "ideal_arousal_range": (0.05, 0.4),
        "target_tension_range": (0.1, 0.45),
        "target_roughness_range": (0.05, 0.35),
        "genre_keywords": ["drone", "dark ambient", "minimalist", "field recording", "ambient drone"],
        "recommended_fx": ["film_grain", "analog_noise", "vignette_blur", "reaction_diffusion", "color_temperature"]
    },
    {
        "id": "tesseract_topology_collapse",
        "genre_cluster": "宇宙崇高與形而上超驗",
        "title": "超立方體高維坍縮 (Tesseract Topology Collapse)",
        "motifs": ["四維超立方體", "克萊因瓶投影", "彭羅斯階梯", "非歐幾何光束", "空間鏡折"],
        "motif": "超立方體投影、彭羅斯階梯與空間鏡折",
        "manifesto": "三維世界的壁壘在幾何旋轉中分崩離析；站在第五維度的切片上，過去與未來同時在眼前展開。",
        "progression": ["歐氏空間 (Thesis)", "折疊擾動 (Antithesis)", "拓撲奇點 (Crisis)", "超維展開 (Synthesis)"],
        "color_arc": "幾何冷灰 (230°) ➔ 光譜稜鏡彩虹 (全光譜) ➔ 扭曲洋紅 (330°) ➔ 超空間白晝 (100°)",
        "ideal_valence_range": (-0.3, 0.65),
        "ideal_arousal_range": (0.5, 0.85),
        "target_tension_range": (0.45, 0.85),
        "target_roughness_range": (0.35, 0.75),
        "genre_keywords": ["math rock", "complex idm", "glitch hop", "wonky", "experimental", "techno"],
        "recommended_fx": ["kaleidoscope", "slit_scan", "mirror_symmetry", "matrix_rain", "chromatic_aberration"]
    },

    # -------------------------------------------------------------------------
    # 流派 III：野獸派冷戰與工業異化 (Brutalist Cold War & Industrial)
    # -------------------------------------------------------------------------
    {
        "id": "brutalist_monolith_echo",
        "genre_cluster": "野獸派冷戰與工業異化",
        "title": "粗野巨石與紀念碑回聲 (Brutalist Monolith Echo)",
        "motifs": ["清水混凝土方碑", "幾何銳角切面", "高聳防空塔", "沉重陰影", "極簡紀念碑"],
        "motif": "清水混凝土方碑、高聳防空塔與沉重陰影",
        "manifesto": "未加修飾的混凝土直面時間的沖刷，粗糙的肌理是人類抵抗脆弱與遺忘的沉默防線。",
        "progression": ["沉默巨構 (Thesis)", "光影切割 (Antithesis)", "重力共振 (Crisis)", "凝固永恆 (Synthesis)"],
        "color_arc": "混凝土鉛灰 (210°) ➔ 陰影玄武黑 (0°) ➔ 銅綠苔蘚 (140°) ➔ 蒼白穹頂白 (70°)",
        "ideal_valence_range": (-0.7, 0.2),
        "ideal_arousal_range": (0.3, 0.65),
        "target_tension_range": (0.35, 0.7),
        "target_roughness_range": (0.3, 0.7),
        "genre_keywords": ["techno", "minimal techno", "industrial", "deep tech", "berlin techno"],
        "recommended_fx": ["sobel_edge", "high_contrast_bw", "film_grain", "vignette_blur", "crt_scanline"]
    },
    {
        "id": "industrial_foundry_serfdom",
        "genre_cluster": "野獸派冷戰與工業異化",
        "title": "工業熔爐與齒輪農奴 (Industrial Foundry Serfdom)",
        "motifs": ["衝壓機床", "赤熱鋼水", "傳送帶鏈條", "飛濺火花", "高聳煙囪"],
        "motif": "衝壓機床、赤熱鋼水與飛濺火花",
        "manifesto": "血肉之軀被熔鑄進機械的龐大韻律；齒輪的咬合不是旋律，而是文明進程無情的脈搏。",
        "progression": ["沉重鍛造 (Thesis)", "蒸汽高壓 (Antithesis)", "火花井噴 (Crisis)", "金屬淬火 (Synthesis)"],
        "color_arc": "焦黑煤炭 (0°) ➔ 熾熱熔岩橙 (35°) ➔ 爆裂金黃 (75°) ➔ 冷卻鋼青 (215°)",
        "ideal_valence_range": (-0.6, 0.3),
        "ideal_arousal_range": (0.7, 1.0),
        "target_tension_range": (0.7, 0.98),
        "target_roughness_range": (0.65, 0.98),
        "genre_keywords": ["industrial techno", "hard techno", "ebm", "metal", "dark techno"],
        "recommended_fx": ["fire_ember", "shockwave", "laser_strobe", "radial_blur_zoom", "analog_noise"]
    },
    {
        "id": "cold_war_radar_ghost",
        "genre_cluster": "野獸派冷戰與工業異化",
        "title": "冷戰雷達與綠磷幽靈 (Cold War Radar Ghost)",
        "motifs": ["旋轉雷達天線", "綠磷示波器", "短波電台雜音", "地下掩體按鈕", "解密電報"],
        "motif": "旋轉雷達天線、綠磷示波器與短波雜音",
        "manifesto": "在電離層的反射中尋找不存在的敵意；螢光屏上的微弱光斑，是文明在相互毀滅邊緣的顫抖。",
        "progression": ["警戒待命 (Thesis)", "頻率捕捉 (Antithesis)", "核彈倒數 (Crisis)", "無聲信號 (Synthesis)"],
        "color_arc": "暗室炭黑 (0°) ➔ 綠磷螢光綠 (135°) ➔ 警報血紅 (15°) ➔ 示波器琥珀 (55°)",
        "ideal_valence_range": (-0.9, 0.05),
        "ideal_arousal_range": (0.4, 0.75),
        "target_tension_range": (0.55, 0.9),
        "target_roughness_range": (0.45, 0.85),
        "genre_keywords": ["dark ambient", "experimental techno", "noise", "coldwave", "post-punk"],
        "recommended_fx": ["crt_scanline", "analog_noise", "vhs_distortion", "bayer_dither", "chromatic_aberration"]
    },
    {
        "id": "post_apocalyptic_wasteland",
        "genre_cluster": "野獸派冷戰與工業異化",
        "title": "核冬荒原與鏽蝕廢墟 (Post-Apocalyptic Wasteland)",
        "motifs": ["廢棄冷卻塔", "鏽蝕骨架", "輻射黃沙", "枯骨天際線", "防毒面具"],
        "motif": "廢棄冷卻塔、輻射黃沙與鏽蝕骨架",
        "manifesto": "繁華落盡，唯有風蝕與氧化在金屬表面撰寫歷史；荒原不是終點，而是洗淨傲慢後的白板。",
        "progression": ["死寂遺蹟 (Thesis)", "塵暴掠襲 (Antithesis)", "毒雲遮日 (Crisis)", "微光初透 (Synthesis)"],
        "color_arc": "泥沙黃褐 (60°) ➔ 氧化鐵鏽紅 (25°) ➔ 毒瘴苔綠 (110°) ➔ 灰冷冬光 (80°)",
        "ideal_valence_range": (-0.8, 0.1),
        "ideal_arousal_range": (0.3, 0.7),
        "target_tension_range": (0.45, 0.8),
        "target_roughness_range": (0.4, 0.8),
        "genre_keywords": ["sludge", "drone techno", "post-rock", "industrial ambient", "darkwave"],
        "recommended_fx": ["film_grain", "vignette_blur", "color_temperature", "sobel_edge", "vhs_distortion"]
    },

    # -------------------------------------------------------------------------
    # 流派 IV：超現實夢境與液態時間 (Surrealism & Liquid Time)
    # -------------------------------------------------------------------------
    {
        "id": "liquid_time_eternal_monolith",
        "genre_cluster": "超現實夢境與液態時間",
        "title": "液態時間與軟性鐘錶 (Liquid Time & Soft Watches)",
        "motifs": ["融化鐘錶", "荒漠枯木", "懸浮海流", "重力反轉水滴", "無窮鏡像"],
        "motif": "融化鐘錶、懸浮海流與反轉水滴",
        "manifesto": "時間非由齒輪丈量，而是在夢境邊緣流淌的液體；當記憶融化，瞬間與永恆失去了邊界。",
        "progression": ["凝固刻度 (Thesis)", "軟化滴落 (Antithesis)", "鏡面顛倒 (Crisis)", "時間汪洋 (Synthesis)"],
        "color_arc": "達利金黃 (70°) ➔ 淺鈷淡藍 (220°) ➔ 軟調赭石 (40°) ➔ 暮光粉紫 (310°)",
        "ideal_valence_range": (-0.3, 0.7),
        "ideal_arousal_range": (0.2, 0.6),
        "target_tension_range": (-0.1, 0.5),
        "target_roughness_range": (0.05, 0.4),
        "genre_keywords": ["psychedelic", "dream pop", "downtempo", "ambient", "trip hop", "chillout"],
        "recommended_fx": ["fluid_vortex", "slit_scan", "reaction_diffusion", "kaleidoscope", "optical_flow_trail"]
    },
    {
        "id": "treachery_of_symbols",
        "genre_cluster": "超現實夢境與液態時間",
        "title": "符號的背叛與馬格利特煙斗 (Treachery of Symbols)",
        "motifs": ["雲朵覆面", "懸浮青蘋果", "虛擬畫框", "無臉行者", "鏡中倒影背對"],
        "motif": "懸浮青蘋果、虛擬畫框與無臉行者",
        "manifesto": "這不是一個畫面，而是對觀看本身的反叛；當圖像否定了其本質，真實才在裂隙中現身。",
        "progression": ["平庸日常 (Thesis)", "荒誕移位 (Antithesis)", "符號斷裂 (Crisis)", "形而上凝視 (Synthesis)"],
        "color_arc": "畫廊素灰 (200°) ➔ 蘋果鮮翠 (130°) ➔ 紳士午夜藍 (250°) ➔ 浮雲乳白 (80°)",
        "ideal_valence_range": (-0.1, 0.65),
        "ideal_arousal_range": (0.3, 0.65),
        "target_tension_range": (0.2, 0.6),
        "target_roughness_range": (0.1, 0.5),
        "genre_keywords": ["art pop", "indie electronic", "glitch", "french touch", "synthpop"],
        "recommended_fx": ["mirror_symmetry", "chromatic_aberration", "bayer_dither", "slit_scan", "vhs_distortion"]
    },
    {
        "id": "man_ray_solarized_dream",
        "genre_cluster": "超現實夢境與液態時間",
        "title": "曼雷中途曝光與物影攝影 (Man Ray Solarized Dream)",
        "motifs": ["射線中途曝光", "暗室顯影盤", "金屬剪影", "眼眸水滴", "銀鹽反轉"],
        "motif": "中途曝光射線、眼眸水滴與銀鹽反轉剪影",
        "manifesto": "光線不是照亮物體的工具，而是雕刻陰影的手術刀；中途曝光揭示的是潛意識深處的負片。",
        "progression": ["暗室浸泡 (Thesis)", "光線灼燒 (Antithesis)", "銀鹽反轉 (Crisis)", "光影超現實 (Synthesis)"],
        "color_arc": "顯影純黑 (0°) ➔ 銀鹽金屬冷白 (200°) ➔ 反轉邊緣銀灰 (240°) ➔ 熾熱高光純白 (90°)",
        "ideal_valence_range": (-0.4, 0.45),
        "ideal_arousal_range": (0.35, 0.75),
        "target_tension_range": (0.35, 0.75),
        "target_roughness_range": (0.3, 0.7),
        "genre_keywords": ["post-punk", "darkwave", "experimental", "techno", "minimal wave"],
        "recommended_fx": ["high_contrast_bw", "film_grain", "vhs_distortion", "sobel_edge", "chromatic_aberration"]
    },
    {
        "id": "hundred_headed_machine",
        "genre_cluster": "超現實夢境與液態時間",
        "title": "恩斯特百頭女與拼貼機械 (Ernst Hundred-Headed Machine)",
        "motifs": ["維多利亞版畫拼貼", "飛鳥羽翼機械", "解剖眼球", "蒸汽翼手龍", "錯位齒輪"],
        "motif": "版畫拼貼、飛鳥羽翼機械與錯位齒輪",
        "manifesto": "將毫不相干的現實強行縫合在同一個手術台上，偶然碰撞所迸發的火花，便是詩的本體。",
        "progression": ["古典秩序 (Thesis)", "拼貼錯位 (Antithesis)", "狂躁雜交 (Crisis)", "超現實合體 (Synthesis)"],
        "color_arc": "泛黃羊皮紙 (65°) ➔ 銅版墨黑 (0°) ➔ 鮮血朱砂 (15°) ➔ 鎏金羽翼 (85°)",
        "ideal_valence_range": (-0.3, 0.55),
        "ideal_arousal_range": (0.55, 0.9),
        "target_tension_range": (0.5, 0.85),
        "target_roughness_range": (0.45, 0.85),
        "genre_keywords": ["breakcore", "electro swing", "idm", "experimental", "glitch"],
        "recommended_fx": ["datamosh", "rgb_split", "slit_scan", "analog_noise", "laser_strobe"]
    },

    # -------------------------------------------------------------------------
    # 流派 V：神聖自然、生物泛靈與生態崩解 (Sacred Nature & Biomorphic Flux)
    # -------------------------------------------------------------------------
    {
        "id": "abyssal_bioluminescence",
        "genre_cluster": "神聖自然、生物泛靈與生態崩解",
        "title": "深海生物光與幽邃海溝 (Abyssal Bioluminescence)",
        "motifs": ["水母傘狀脈動", "深海熱泉煙囪", "發光浮游群", "沉積海雪", "萬米水壓"],
        "motif": "水母傘狀脈動、發光浮游群與萬米水壓幽藍",
        "manifesto": "在太陽光無法穿透的極端深海，生命以自體發出的冷光照亮深淵，那是一場無聲而神聖的化學禱告。",
        "progression": ["透光表層 (Thesis)", "幽暗降落 (Antithesis)", "發光爆發 (Crisis)", "深淵共生 (Synthesis)"],
        "color_arc": "暮色洋藍 (230°) ➔ 墨黑深淵 (0°) ➔ 幽靈螢光青 (185°) ➔ 璀璨生物青綠 (155°)",
        "ideal_valence_range": (-0.3, 0.7),
        "ideal_arousal_range": (0.2, 0.6),
        "target_tension_range": (-0.1, 0.5),
        "target_roughness_range": (0.05, 0.4),
        "genre_keywords": ["deep house", "ambient techno", "downtempo", "liquid drum & bass", "chill"],
        "recommended_fx": ["fluid_vortex", "reaction_diffusion", "anamorphic_bloom", "optical_flow_trail", "color_temperature"]
    },
    {
        "id": "turing_morphogenesis_flux",
        "genre_cluster": "神聖自然、生物泛靈與生態崩解",
        "title": "圖靈形態發生與自組織斑圖 (Turing Morphogenesis Flux)",
        "motifs": ["斑馬條紋分叉", "獵豹斑點生成", "化學反應擴散", "細胞有絲分裂", "自相似碎形"],
        "motif": "化學反應擴散、細胞分裂與自組織斑圖",
        "manifesto": "簡單的化學擴散方程孕育了萬物的繁盛花紋；秩序並非外力賦予，而是混沌深處必然湧現的自組織。",
        "progression": ["均勻混沌 (Thesis)", "微小擾動 (Antithesis)", "圖樣繁衍 (Crisis)", "穩態奇觀 (Synthesis)"],
        "color_arc": "均質乳白 (80°) ➔ 催化靛藍 (245°) ➔ 活化洋紅 (325°) ➔ 湧現多色斑斕 (全光譜)",
        "ideal_valence_range": (-0.1, 0.75),
        "ideal_arousal_range": (0.45, 0.8),
        "target_tension_range": (0.3, 0.7),
        "target_roughness_range": (0.2, 0.6),
        "genre_keywords": ["microhouse", "minimal techno", "idm", "generative electronic", "techno"],
        "recommended_fx": ["reaction_diffusion", "kaleidoscope", "sobel_edge", "fluid_vortex", "bloom_glitch"]
    },
    {
        "id": "mycelial_spore_transcendence",
        "genre_cluster": "神聖自然、生物泛靈與生態崩解",
        "title": "菌絲網絡與孢子超驗 (Mycelial Spore Transcendence)",
        "motifs": ["地下真菌根網", "發光孢子雲", "腐殖質化學信號", "樹冠交織", "森林暗網"],
        "motif": "地下菌絲根網、發光孢子雲與森林暗網",
        "manifesto": "在大地之下，億萬根菌絲交織成無中心的行星大腦；死亡與腐殖並非終結，而是生命互聯網的營養基質。",
        "progression": ["腐朽沉睡 (Thesis)", "菌絲萌動 (Antithesis)", "孢子噴發 (Crisis)", "林海共鳴 (Synthesis)"],
        "color_arc": "腐殖暗褐 (45°) ➔ 苔蘚翠綠 (140°) ➔ 發光金黃 (80°) ➔ 晨霧蒼翠 (160°)",
        "ideal_valence_range": (0.1, 0.8),
        "ideal_arousal_range": (0.25, 0.65),
        "target_tension_range": (0.1, 0.55),
        "target_roughness_range": (0.1, 0.45),
        "genre_keywords": ["organic house", "downtempo", "folktronica", "ambient", "world"],
        "recommended_fx": ["god_rays", "fluid_vortex", "optical_flow_trail", "film_grain", "vignette_blur"]
    },
    {
        "id": "biomechanical_symbiosis",
        "genre_cluster": "神聖自然、生物泛靈與生態崩解",
        "title": "吉格爾生化共生與骨甲 (Biomechanical Symbiosis)",
        "motifs": ["脊椎骨管道", "幾丁質外骨骼", "金屬胚胎", "液壓肌肉", "生化巢穴"],
        "motif": "幾丁質外骨骼、脊椎導管與生化巢穴",
        "manifesto": "血肉與金屬不再界限分明，骨骼化為導管，生殖化為鑄造；這是後人類時代最冰冷而優雅的受孕。",
        "progression": ["冷酷胚胎 (Thesis)", "骨肉交織 (Antithesis)", "生化突變 (Crisis)", "異形共生 (Synthesis)"],
        "color_arc": "骨骼冷灰 (220°) ➔ 幾丁質漆黑 (0°) ➔ 膽汁酸綠 (115°) ➔ 羊水昏黃 (50°)",
        "ideal_valence_range": (-0.9, -0.05),
        "ideal_arousal_range": (0.6, 0.95),
        "target_tension_range": (0.65, 0.98),
        "target_roughness_range": (0.6, 0.95),
        "genre_keywords": ["dark techno", "industrial", "death industrial", "hard techno", "ebm"],
        "recommended_fx": ["sobel_edge", "slit_scan", "reaction_diffusion", "analog_noise", "shockwave"]
    },

    # -------------------------------------------------------------------------
    # 流派 VI：東方虛無、禪宗寂滅與時間雕刻 (Eastern Void, Zen & Sculpting in Time)
    # -------------------------------------------------------------------------
    {
        "id": "hypnotic_zen_dissolution",
        "genre_cluster": "東方虛無、禪宗寂滅與時間雕刻",
        "title": "禪意催眠與水墨留白 (Hypnotic Zen Dissolution)",
        "motifs": ["水墨洇散", "枯山水砂紋", "竹林風痕", "孤舟微影", "空靈留白"],
        "motif": "水墨洇散、枯山水砂紋與自相似微瀾",
        "manifesto": "無即是有，空即是色；在宣紙吸飽墨滴的微秒呼吸中，一切執念皆化作池塘裡的一道微瀾。",
        "progression": ["澄澈心鏡 (Thesis)", "一念微瀾 (Antithesis)", "水墨漫染 (Crisis)", "萬籟歸寂 (Synthesis)"],
        "color_arc": "宣紙素白 (80°) ➔ 焦墨深黑 (0°) ➔ 黛青山巒 (215°) ➔ 禪意玉白 (160°)",
        "ideal_valence_range": (-0.3, 0.7),
        "ideal_arousal_range": (0.05, 0.35),
        "target_tension_range": (0.0, 0.4),
        "target_roughness_range": (0.0, 0.3),
        "genre_keywords": ["ambient", "meditation", "minimalist", "modern classical", "chillout", "zen"],
        "recommended_fx": ["fluid_vortex", "film_grain", "vignette_blur", "color_temperature", "optical_flow_trail"]
    },
    {
        "id": "tarkovsky_sculpting_in_time",
        "genre_cluster": "東方虛無、禪宗寂滅與時間雕刻",
        "title": "塔可夫斯基時間雕刻與水域回憶 (Tarkovsky Sculpting in Time)",
        "motifs": ["緩慢平移長鏡頭", "水草漂浮流動", "雨中廢棄房屋", "燃燒孤樹", "鏡中微風"],
        "motif": "漂浮水草、雨中廢棄木屋與燃燒孤樹",
        "manifesto": "電影並非剪輯的拼湊，而是在膠卷上雕刻時間；任憑水流穿過生鏽的硬幣與聖像，記憶便獲得了神聖的重量。",
        "progression": ["凝滯時光 (Thesis)", "雨水浸潤 (Antithesis)", "孤樹燃燒 (Crisis)", "靈魂復歸 (Synthesis)"],
        "color_arc": "苔蘚泥綠 (130°) ➔ 水波冷棕 (50°) ➔ 晨曦琥珀 (60°) ➔ 靜謐天藍 (225°)",
        "ideal_valence_range": (-0.4, 0.55),
        "ideal_arousal_range": (0.15, 0.45),
        "target_tension_range": (0.1, 0.5),
        "target_roughness_range": (0.1, 0.4),
        "genre_keywords": ["ambient", "neoclassical", "drone", "post-rock", "cinematic"],
        "recommended_fx": ["slit_scan", "film_grain", "vignette_blur", "anamorphic_bloom", "sobel_edge"]
    },
    {
        "id": "chungking_neon_loneliness",
        "genre_cluster": "東方虛無、禪宗寂滅與時間雕刻",
        "title": "重慶森林霓虹搖曳與抽格迷離 (Chungking Neon Loneliness)",
        "motifs": ["抽格拖影", "晃動手持手鏡頭", "罐頭鳳梨", "雨夜街頭霓虹倒影", "墨鏡與假髮"],
        "motif": "抽格拖影、雨夜街頭霓虹倒影與墨鏡殘像",
        "manifesto": "在每天擦肩而過的五萬人中，我們以 0.01 公分的距離彼此疏離；抽格的殘影是都市孤獨唯一的慢動作註解。",
        "progression": ["匆匆擦肩 (Thesis)", "抽格追逐 (Antithesis)", "過期臨界 (Crisis)", "雨夜微醺 (Synthesis)"],
        "color_arc": "霓虹暖橙 (40°) ➔ 電影青綠 (170°) ➔ 眩暈粉紅 (340°) ➔ 雨夜幽藍 (235°)",
        "ideal_valence_range": (-0.2, 0.65),
        "ideal_arousal_range": (0.4, 0.75),
        "target_tension_range": (0.2, 0.65),
        "target_roughness_range": (0.2, 0.6),
        "genre_keywords": ["city pop", "synthwave", "vaporwave", "indie pop", "lo-fi", "disco", "house"],
        "recommended_fx": ["optical_flow_trail", "chromatic_aberration", "vhs_distortion", "anamorphic_bloom", "rgb_split"]
    },
    {
        "id": "phoenix_ashes_rebirth",
        "genre_cluster": "東方虛無、禪宗寂滅與時間雕刻",
        "title": "涅槃火鳥與灰燼復甦 (Phoenix Ashes & Pyretic Rebirth)",
        "motifs": ["燃燒羽翼", "飛散金燼", "古寺梵鐘", "浴火蓮花", "朝霞破曉"],
        "motif": "燃燒羽翼、古寺梵鐘與破曉烈焰",
        "manifesto": "經受八萬四千度業火焚燒，方知色相皆空；在灰燼的最底層，每一次心跳都是對死亡最傲慢的回答。",
        "progression": ["燃燒業火 (Thesis)", "羽翼碎裂 (Antithesis)", "灰燼寂滅 (Crisis)", "破曉浴火 (Synthesis)"],
        "color_arc": "爆烈朱紅 (20°) ➔ 焦炭純黑 (0°) ➔ 靈魂青金 (210°) ➔ 破曉烈焰金 (65°)",
        "ideal_valence_range": (-0.2, 0.85),
        "ideal_arousal_range": (0.6, 0.95),
        "target_tension_range": (0.5, 0.9),
        "target_roughness_range": (0.35, 0.8),
        "genre_keywords": ["epic", "orchestral", "drum & bass", "melodic dubstep", "progressive house", "trance"],
        "recommended_fx": ["fire_ember", "god_rays", "shockwave", "anamorphic_bloom", "laser_strobe"]
    }
]


class AuteurWorldviewOntologyEngine:
    """
    24 大前衛電影作者美學世界觀本體論決策引擎 (Auteur Worldview Ontology Engine)
    - 30ms 確定性多維加權評分決策 (Acoustic Feature Alignment)
    - 結合 Valence, Arousal, Tension, Roughness 與 Genre Keywords
    - 記憶滑動窗口動態降權 (Recency Anti-Collision)，確保批量歌曲千姿百態
    """

    def __init__(self, memory_window: int = 8):
        self.themes: List[Dict[str, Any]] = AUTEUR_THEMES
        self.themes_by_id: Dict[str, Dict[str, Any]] = {t["id"]: t for t in self.themes}
        self.memory_window: int = memory_window
        self.recent_history: List[str] = []

    def reset_history(self):
        """ 清空歷史紀錄 """
        self.recent_history.clear()

    def resolve_theme(self, audio_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        以五維聲學矩陣與語義特徵，從 24 大世界觀中精準挑選最符合意境的美學架構
        """
        genre_tel = audio_telemetry.get('genre_telemetry', {})
        valence = float(audio_telemetry.get('valence', genre_tel.get('valence', 0.0)))
        arousal = float(audio_telemetry.get('arousal', genre_tel.get('arousal', 0.5)))
        tension = float(audio_telemetry.get('tension', audio_telemetry.get('spectral_tension', 0.5)))
        roughness = float(audio_telemetry.get('roughness', audio_telemetry.get('spectral_roughness', 0.5)))
        genre_raw = str(audio_telemetry.get('genre', 'Electronic')).lower()

        scores: Dict[str, float] = {}

        for theme in self.themes:
            t_id = theme["id"]
            score = 0.0

            # 1. 曲風語義匹配得分 (Genre Semantic Match, 權重高: +2.2 ~ +5.0)
            keywords = theme.get("genre_keywords", [])
            is_hard_techno_music = any(ht in genre_raw for ht in ("hard techno", "hard_techno", "schranz", "industrial techno"))
            is_ambient_music = any(amb in genre_raw for amb in ("ambient", "drone", "meditative", "downtempo", "chill", "atmospheric", "sleep", "new age", "new_age"))
            for kw in keywords:
                if kw in genre_raw or (is_hard_techno_music and kw in ("hard techno", "hard_techno", "industrial techno")):
                    score += 5.0 if (is_hard_techno_music or is_ambient_music) else 2.2
                    break

            # 硬性美學隔離：Hard Techno 優先選擇工業殘酷主義世界觀，嚴格禁止分配自然生物/流體/深海生態
            if is_hard_techno_music:
                if theme.get("genre_cluster") == "工業殘酷主義與重力塌陷":
                    score += 4.5
                elif theme.get("genre_cluster") in ("神聖自然、生物泛靈與生態崩解", "超現實夢境與液態時間", "歷史記憶與檔案迴圈"):
                    score -= 7.0
            elif is_ambient_music:
                # 硬性美學隔離：Ambient 優先選擇超現實夢境/神聖自然/歷史記憶等沉思世界觀，隔離高飽和賽博龐克與工業殘酷主義
                if theme.get("genre_cluster") in ("超現實夢境與液態時間", "神聖自然、生物泛靈與生態崩解", "歷史記憶與檔案迴圈"):
                    score += 4.2
                elif theme.get("genre_cluster") in ("工業殘酷主義與重力塌陷", "賽博龐克、後人類與數位異化"):
                    score -= 6.5

            # 2. Valence 區間契合度得分 (+1.5 基準，範圍外高斯懲罰)
            v_min, v_max = theme.get("ideal_valence_range", (-1.0, 1.0))
            if v_min <= valence <= v_max:
                score += 1.5
            else:
                dist = (v_min - valence) if valence < v_min else (valence - v_max)
                score += 1.5 * math.exp(-3.5 * (dist ** 2))

            # 3. Arousal 區間契合度得分 (+1.5 基準，範圍外高斯懲罰)
            a_min, a_max = theme.get("ideal_arousal_range", (0.0, 1.0))
            if a_min <= arousal <= a_max:
                score += 1.5
            else:
                dist = (a_min - arousal) if arousal < a_min else (arousal - a_max)
                score += 1.5 * math.exp(-3.5 * (dist ** 2))

            # 4. Tension & Roughness 細緻聲學指紋契合度 (+1.0)
            t_min, t_max = theme.get("target_tension_range", (0.0, 1.0))
            if t_min <= tension <= t_max:
                score += 0.5
            else:
                dist = (t_min - tension) if tension < t_min else (tension - t_max)
                score += 0.5 * math.exp(-4.0 * (dist ** 2))

            r_min, r_max = theme.get("target_roughness_range", (0.0, 1.0))
            if r_min <= roughness <= r_max:
                score += 0.5
            else:
                dist = (r_min - roughness) if roughness < r_min else (roughness - r_max)
                score += 0.5 * math.exp(-4.0 * (dist ** 2))

            # 5. 歷史使用降權 (Recency Anti-Collision Penalty)
            # 防止連續排片時出現相同或頻繁世界觀
            if self.recent_history:
                # 倒數第 1 首使用：重罰 -3.8
                if len(self.recent_history) >= 1 and self.recent_history[-1] == t_id:
                    score -= 3.8
                # 倒數第 2 首使用：罰 -2.4
                elif len(self.recent_history) >= 2 and self.recent_history[-2] == t_id:
                    score -= 2.4
                # 倒數第 3 首使用：罰 -1.4
                elif len(self.recent_history) >= 3 and self.recent_history[-3] == t_id:
                    score -= 1.4
                # 窗口內其餘次數，每次扣 -0.6
                elif t_id in self.recent_history:
                    score -= 0.6 * self.recent_history.count(t_id)

            # 6. 微小香農擾動 (打破邊界並列僵局，增加驚喜感)
            # 引入偽隨機但確定性受 BPM / 標題影響的微擾動
            bpm_seed = float(audio_telemetry.get('bpm', 120.0))
            seed_factor = math.sin(bpm_seed * 13.37 + hash(t_id) % 100) * 0.12
            score += seed_factor

            scores[t_id] = score

        # 選出最高得分世界觀
        best_id = max(scores, key=lambda k: scores[k])
        chosen = dict(self.themes_by_id[best_id])

        # 更新歷史隊列
        self.recent_history.append(best_id)
        if len(self.recent_history) > self.memory_window:
            self.recent_history.pop(0)

        logger.info(f"🎭 [Auteur Ontology] 精選作者世界觀: 【{chosen['genre_cluster']}】{chosen['title']} (得分: {scores[best_id]:.2f})")
        return chosen


def coalesce_ambient_storyboard_sections(
    storyboard_sections: List[Dict[str, Any]],
    min_shot_dur: float = 16.0,
    max_shot_dur: float = 36.0
) -> List[Dict[str, Any]]:
    """
    🌿 自適應呼吸長鏡頭熔接器 (Adaptive Breath Segment Coalescer v2.0)：
    針對 Ambient / Drone 曲風，將過於零碎的音訊分鏡 (< 16s) 自動熔接為 16s~36s 的冥想長鏡頭章節，
    同時保留短曲 (<= 3 段) 的原始結構，防止長曲每 6~8 秒碎切破壞沉思心流。
    """
    if not storyboard_sections or len(storyboard_sections) <= 3:
        return list(storyboard_sections)

    coalesced: List[Dict[str, Any]] = []
    for raw_sec in storyboard_sections:
        sec_copy = dict(raw_sec)
        if "start" in sec_copy and "end" in sec_copy:
            dur = max(0.1, float(sec_copy["end"]) - float(sec_copy["start"]))
        else:
            dur = max(0.1, float(sec_copy.get("duration", 15.0)))
        sec_copy["duration"] = dur

        if not coalesced:
            coalesced.append(sec_copy)
            continue

        prev = coalesced[-1]
        prev_dur = float(prev.get("duration", 15.0))
        if (prev_dur < min_shot_dur or dur < min_shot_dur) and (prev_dur + dur <= max_shot_dur):
            prev["duration"] = round(prev_dur + dur, 3)
            if "end" in sec_copy:
                prev["end"] = float(sec_copy["end"])
            elif "start" in prev:
                prev["end"] = round(float(prev["start"]) + prev["duration"], 3)
        else:
            coalesced.append(sec_copy)

    return coalesced


class LLMDirectorAgent:
    """
    SOTA 雙層電影作者導演管線
    """

    def __init__(
        self, 
        host: str = "http://localhost:11434", 
        default_model: str = "llama3", 
        model_name: Optional[str] = None, 
        api_url: Optional[str] = None
    ):
        if api_url:
            self.host = api_url.rsplit('/', 1)[0]
        else:
            self.host = host.rstrip("/")
        self.api_url = f"{self.host}/api/generate"
        self.tags_url = f"{self.host}/api/tags"
        self.default_model = model_name or default_model
        self.model_name = self.default_model
        self.bandit = BanditInventorySelector()
        self.choreographer = DirectorChoreographer()
        self.ontology = AuteurWorldviewOntologyEngine()

    def get_ollama_status(self) -> Dict[str, Any]:
        """ 快速探測本地 LLM 狀態 (超時 1 秒) """
        try:
            req = urllib.request.Request(self.tags_url)
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    active_model = ""
                    for m_name in models:
                        if m_name == self.default_model or m_name.startswith(f"{self.default_model}:"):
                            active_model = m_name
                            break
                    if not active_model:
                        for m_name in models:
                            if "llama" in m_name or "gemma" in m_name:
                                active_model = m_name
                                break
                    if not active_model and models:
                        active_model = models[0]
                    return {"status": "ready", "model": active_model, "available": models}
        except Exception:
            pass
        return {"status": "offline", "model": self.default_model, "available": []}

    def generate_director_script(
        self, 
        audio_telemetry: Dict[str, Any], 
        available_modules: List[Dict[str, Any]], 
        recent_used_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        SOTA 雙軌電影作者決策流程：
        1. 30ms 確定性專家作者樹 (Auteur Matrix Tree) 即時產出高品質劇作草案 (零等待保證)
        2. 透過 Contextual Bandit 完成初始模組分配 (語義約束 + UCB 冷門與修復優先)
        3. 若本地 LLM 可用，發起 4.5 秒硬超時競爭查詢，融合同化高階哲學描述
        4. 由 L2 DirectorChoreographer 完成微觀動態編舞 (Murch 51% 心靈對齊、J/L-Cut 錯位、彈道阻尼)
        """
        storyboard_sections = audio_telemetry.get("storyboard", [])
        if not storyboard_sections:
            storyboard_sections = [
                {"section": "Intro", "duration": 15.0},
                {"section": "Verse", "duration": 30.0},
                {"section": "Build-up", "duration": 15.0},
                {"section": "Drop", "duration": 30.0},
                {"section": "Outro", "duration": 15.0}
            ]

        genre_check_early = str(audio_telemetry.get("genre", "") or "").lower()
        is_ambient_track = any(k in genre_check_early for k in ("ambient", "drone", "meditative", "downtempo", "chill", "atmospheric", "sleep", "new age", "new_age"))
        if is_ambient_track and len(storyboard_sections) > 3:
            storyboard_sections = coalesce_ambient_storyboard_sections(storyboard_sections, min_shot_dur=16.0, max_shot_dur=36.0)

        # 1. 30ms 確定性專家作者大腦決策 (從 24 大前衛電影作者矩陣中智慧匹配)
        auteur_theme = self._resolve_auteur_theme(audio_telemetry)
        
        # 2. 構建歷史次數字典（結合個體與家族雙重冷卻懲罰）
        from bandit_inventory_selector import extract_base_family
        recent_set = set(recent_used_keys or [])
        recent_families = {extract_base_family(k) for k in recent_set if k}
        historical_counts = {}
        for m in available_modules:
            k = m.get("_filename_key") or m.get("name")
            fam = extract_base_family(k)
            used = int(m.get("used_count", 0))
            if k in recent_set:
                used += 4
            if fam and fam in recent_families:
                used += 3
            historical_counts[k] = used

        # 3. 語義約束 + UCB 冷門優先 Bandit 選模組
        bandit_assignments = self.bandit.select_modules_for_storyboard(
            storyboard_sections=storyboard_sections,
            available_modules=available_modules,
            audio_telemetry=audio_telemetry,
            historical_used_counts=historical_counts
        )

        # 4. 探測 LLM 競爭雙軌 (4.5 秒硬上限)
        ollama_status = self.get_ollama_status()
        llm_enhanced_meta = None

        if ollama_status["status"] == "ready":
            try:
                llm_enhanced_meta = self._query_llm_with_timeout(
                    audio_telemetry=audio_telemetry,
                    bandit_assignments=bandit_assignments,
                    auteur_theme=auteur_theme,
                    model_name=ollama_status["model"],
                    timeout_sec=7.5
                )
            except Exception as e:
                logger.warning(f"⚠️ LLM 查詢超時或異常 ({str(e)})，0 延遲無縫採納確定性專家作者大腦。")

        # 5. 微觀動態編舞 (L2 Choreographer)
        shot_list, intensity_curve = self.choreographer.plan_cinematic_shots(
            storyboard_sections=storyboard_sections,
            audio_telemetry=audio_telemetry,
            assigned_modules=bandit_assignments
        )

        # 6. 整合母題與多幕辯證標籤 + Ambient 分鏡級莫蘭迪色彩合約 (Per-Shot Ambient Color Policy)
        genre_check = str(audio_telemetry.get("genre", "") or "").lower()
        is_ambient_track = any(k in genre_check for k in ("ambient", "drone", "meditative", "downtempo", "chill", "atmospheric", "sleep", "new age", "new_age"))
        ambient_palettes_catalog = [
            ("nordic_glacier_mist", ["#121820", "#263442", "#4B6275", "#7C93A6", "#B8C7D4"], 205.0),
            ("morandi_ash_clay", ["#1C1A19", "#3B3735", "#69625E", "#998F89", "#C4BCB6"], 25.0),
            ("abyssal_bioluminescence", ["#091318", "#132933", "#234959", "#427385", "#7BA3B0"], 192.0),
            ("tarkovsky_moss_fog", ["#141A16", "#28362C", "#4A6150", "#768F7C", "#A9BDB0"], 140.0),
            ("turrell_twilight_ether", ["#161321", "#2B2540", "#4F466E", "#7E749E", "#B2AAC9"], 255.0),
            ("zen_sand_ink", ["#171717", "#333230", "#5E5B56", "#8F8B84", "#C2BEB6"], 42.0),
        ]

        num_shots = len(shot_list)
        prog_len = len(auteur_theme["progression"])
        for i, shot in enumerate(shot_list):
            progress = i / max(1, num_shots - 1)
            stage_idx = min(prog_len - 1, int(progress * prog_len))
            shot["dialectical_stage"] = auteur_theme["progression"][stage_idx]
            shot["symbolic_motif"] = auteur_theme["motif"]
            if is_ambient_track:
                pal_name, pal_hex, tgt_hue = ambient_palettes_catalog[i % len(ambient_palettes_catalog)]
                sec_label = str(shot.get("section", "Verse"))
                shot["ambient_color_policy"] = {
                    "enabled": True,
                    "palette_name": pal_name,
                    "palette": pal_hex,
                    "target_hue": tgt_hue,
                    "max_saturation": 0.25 if sec_label in ("Intro", "Outro", "Bridge") else 0.29,
                    "chroma_ceiling": 0.062 if sec_label in ("Intro", "Outro", "Bridge") else 0.070,
                }

        theme_title = llm_enhanced_meta.get("theme_title") if llm_enhanced_meta else auteur_theme["title"]
        manifesto = auteur_theme.get("manifesto", "")
        if llm_enhanced_meta and llm_enhanced_meta.get("director_statement"):
            director_statement = f"「{manifesto}」\n{llm_enhanced_meta.get('director_statement')}"
        else:
            director_statement = (
                f"「{manifesto}」\n"
                f"劇作理念：圍繞「{auteur_theme['motif']}」作者母題，落地四幕辯證演進與 Walter Murch 情感切分。"
            )

        recommended_fx = list(auteur_theme.get("recommended_fx", []))
        if is_ambient_track:
            forbidden_amb_fx = {"thermal_vision", "thermal_infrared", "strobe_chroma_invert", "color_spectral", "acid_curl_fluid", "pixel_sort", "film_burn"}
            recommended_fx = [fx for fx in recommended_fx if fx not in forbidden_amb_fx] or ["bloom", "vignette", "film_grain"]

        return {
            "theme_title": theme_title,
            "genre_cluster": auteur_theme.get("genre_cluster", "電影作者美學"),
            "manifesto": manifesto,
            "soul_theme": auteur_theme["id"],
            "symbolic_motif": auteur_theme["motif"],
            "motifs": auteur_theme.get("motifs", [auteur_theme["motif"]]),
            "chromatic_narrative": auteur_theme["color_arc"],
            "color_palette_mood": auteur_theme["color_arc"],
            "recommended_fx": recommended_fx,
            "director_statement": director_statement,
            "shot_list": shot_list,
            "intensity_curve": intensity_curve or [0.3, 0.5, 0.9, 0.4]
        }

    def _resolve_auteur_theme(self, audio_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """ 30ms 確定性專家作者樹：由 24 大前衛電影作者本體論引擎自適應決策 """
        return self.ontology.resolve_theme(audio_telemetry)

    def _fallback_heuristic_script(
        self,
        audio_telemetry: Dict[str, Any],
        available_modules: List[Dict[str, Any]],
        recent_used_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """ 確定性 0 延遲專家回退劇本生成 """
        return self.generate_director_script(audio_telemetry, available_modules, recent_used_keys)

    def _query_llm_with_timeout(
        self,
        audio_telemetry: Dict[str, Any],
        bandit_assignments: List[Dict[str, Any]],
        auteur_theme: Dict[str, Any],
        model_name: str,
        timeout_sec: float = 4.5
    ) -> Optional[Dict[str, Any]]:
        """ 4.5 秒硬超時約束查詢，防止卡死 UI """
        prompt = f"""You are a master 4K Music Video Film Director following Walter Murch's Rule of Six.
Music Affect: Genre={audio_telemetry.get('genre')}, BPM={audio_telemetry.get('bpm')}.
Auteur Theme: {auteur_theme['title']} (Motif: {auteur_theme['motif']}).

Output strictly valid JSON with no markdown:
{{
  "theme_title": "Short poetic title (max 6 words)",
  "director_statement": "Concise auteur vision statement explaining the psychological journey"
}}"""

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "num_predict": 96,
                "temperature": 0.7
            }
        }
        
        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            raw_response = data.get("response", "{}")
            if "<think>" in raw_response and "</think>" in raw_response:
                raw_response = raw_response.split("</think>")[-1].strip()
            return json.loads(raw_response)

    def generate_shot_list(self, song_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """ 向後相容接口 """
        script = self.generate_director_script(song_telemetry, [])
        return {
            "aesthetic_theme": script.get("theme_title", "CyberGlitch"),
            "signature_fx": ["bayer_dither", "crt_scanline", "chromatic_aberration"],
            "color_mood": script.get("color_palette_mood", "Cyberpunk Neon"),
            "camera_framing": ["WIDE_ENV", "MEDIUM_MAIN", "MACRO_DETAIL", "WHIP_PAN_GLITCH", "ZOOM_BURST"],
            "intensity_curve": script.get("intensity_curve", [0.3, 0.5, 0.9, 0.6, 0.3]),
            "fullscreen_fit_mode": "fill"
        }
