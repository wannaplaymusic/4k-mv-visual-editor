# -*- coding: utf-8 -*-
"""
SENTINEL: Visual Module Expressive Ontology & Semantic Profile Data Models
定義模組心靈狀態、象徵意義、幾何拓撲與感知色彩的 Pydantic 規範
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

class ColorAesthetics(BaseModel):
    """ 色彩美學與心理感知分佈 """
    dominant_oklch_hues: List[float] = Field(
        default_factory=list, 
        description="主導感知色相角度 (0° ~ 360°)"
    )
    mean_lightness: float = Field(0.5, ge=0.0, le=1.0, description="平均明度 (0: 極暗 ~ 1: 極亮)")
    mean_chroma: float = Field(0.1, ge=0.0, le=0.4, description="平均感知彩度")
    contrast_level: str = Field(
        "analogous_subtle",
        description="色彩對比型態: monochrome_stark, analogous_subtle, complementary_clash, polychromatic_chaos"
    )
    emotional_temperature: str = Field(
        "sterile_neutral",
        description="色彩感知溫度: glacial_cold, sterile_neutral, feverish_warm, toxic_luminescent"
    )

class SpatiotemporalDynamics(BaseModel):
    """ 時空運動與動態光流特徵 """
    mean_velocity: float = Field(0.0, description="動態平均光流速度")
    curl_vorticity: float = Field(0.0, description="渦流旋度 (象徵掙扎、湍流或漩渦)")
    divergence: float = Field(0.0, description="散度 (<0: 向心坍縮吸積, >0: 離心爆散放射)")
    motion_energy_type: str = Field(
        "sinusoidal_breath",
        description="運動動能型態: inward_implosion, outward_explosion, sinusoidal_breath, chaotic_brownian, static_crystalline"
    )

class ExpressiveProfile(BaseModel):
    """ 心靈語義與象徵隱喻本體設定檔 """
    module_id: str = Field(..., description="模組唯一標識符")
    primary_psychological_state: str = Field(
        "hypnotic_trance",
        description="主要心理狀態: alienation_void, claustrophobic_dread, manic_hyperarousal, hypnotic_trance, sublime_catharsis, nostalgic_decay, existential_awe"
    )
    secondary_psychological_states: List[str] = Field(
        default_factory=list,
        description="次要心理情緒標籤"
    )
    symbolic_metaphors: List[str] = Field(
        default_factory=list,
        description="象徵隱喻 (如: ['坍縮黑洞', '神經突觸放電', '破碎鏡面', '生命之樹'])"
    )
    narrative_function: str = Field(
        "tension_accelerator",
        description="電影敘事功能: genesis_anchor(世界觀奠基), tension_accelerator(張力推進), climax_rupture(高潮爆發), aftermath_resonance(餘韻沉降)"
    )
    jungian_archetype: str = Field(
        "the_self",
        description="榮格心理原型: the_shadow(陰影), the_self(自性/覺醒), the_void(虛無), the_animus(動力/理性), the_trickster(顛覆/混沌)"
    )
    color_profile: ColorAesthetics = Field(default_factory=ColorAesthetics)
    dynamics: SpatiotemporalDynamics = Field(default_factory=SpatiotemporalDynamics)
    hydration_level: int = Field(0, description="水合等級: 0(代碼級), 1(數學特徵級), 2(VLM哲學靈魂級)")
    confidence_score: float = Field(0.8, ge=0.0, le=1.0, description="語義標註置信度")
    analyzed_engine: str = Field("heuristic_fallback", description="推論引擎: gemini-flash, qwen2-vl, heuristic_fallback")
    updated_at: str = Field("", description="標註更新時間戳")
