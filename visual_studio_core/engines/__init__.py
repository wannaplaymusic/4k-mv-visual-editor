#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Studio Rack Engines Package
包含視覺發生器引擎協議、單例註冊表與三大核心引擎實作
"""

from visual_studio_core.engines.base_engine import BaseVisualEngine, EngineMetadata
from visual_studio_core.engines.engine_registry import EngineRegistry, get_engine_registry
from visual_studio_core.engines.engine_math_synth import MathSynthEngine
from visual_studio_core.engines.engine_pixel_art import PixelArtEngine
from visual_studio_core.engines.engine_surreal_collage import SurrealCollageEngine

__all__ = [
    "BaseVisualEngine",
    "EngineMetadata",
    "EngineRegistry",
    "get_engine_registry",
    "MathSynthEngine",
    "PixelArtEngine",
    "SurrealCollageEngine"
]
