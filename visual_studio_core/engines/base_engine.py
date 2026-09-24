#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Visual Engine Protocol (IVisualEngine)
定義 VisualStudio Pro 動態設備機架規範中的生成器插件協議
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from PyQt6.QtWidgets import QWidget


@dataclass
class EngineMetadata:
    id: str
    name: str
    icon: str
    description: str
    category: str  # e.g., "generative_math", "pixel_art", "surreal_collage"
    tags: List[str] = field(default_factory=list)
    recommended_shaders: List[int] = field(default_factory=list)
    author: str = "4K MV Studio"
    version: str = "2.0.0"


class BaseVisualEngine(ABC):
    """視覺發生器引擎標準協議 (Visual Generator Engine Protocol)"""

    def __init__(self):
        self.params: Dict[str, Any] = {}

    @abstractmethod
    def get_metadata(self) -> EngineMetadata:
        """獲取引擎元數據"""
        pass

    @abstractmethod
    def generate_code(self, params: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> str:
        """
        生成標準化 p5.js / WebGL 視覺模組代碼。
        必須包含:
        1. 頂部 `@wizard` 標籤註釋供 AST 引擎解析實時滑桿。
        2. 全局 window.onAudioFrame(bass, mid, high, energy, beatPulse) 音訊生命週期勾子。
        3. 支援 4K (3840x2160) 高畫質自適應 Canvas。
        """
        pass

    @abstractmethod
    def get_default_ast_params(self) -> List[Dict[str, Any]]:
        """
        獲取該引擎預設的 AST 參數定義
        格式例如: [{"name": "speed", "type": "float", "min": 0.1, "max": 5.0, "step": 0.1, "default": 1.0, "doc": "速度"}]
        """
        pass

    def get_audio_reactive_spec(self) -> Dict[str, Any]:
        """定義音訊各頻段（Bass, Mid, High, Energy）對該模組的動態映射規範"""
        return {
            "bass": "低音能量調變",
            "mid": "中頻旋律流動",
            "high": "高頻瞬態粒子/閃爍",
            "energy": "整體動態呼吸與尺度"
        }

    def create_control_widget(self, parent: Optional[QWidget] = None, on_param_changed: Optional[Callable] = None) -> Optional[QWidget]:
        """
        為該引擎創建專屬的語境控制抽屜（Context-Aware Control Drawer）組件。
        若返回 None，則完全由 AST 自動解析的滑桿驅動。
        """
        return None

    def mutate(self, current_params: Dict[str, Any], strength: float = 0.3) -> Dict[str, Any]:
        """遺傳/隨機變異當前參數"""
        return current_params.copy()
