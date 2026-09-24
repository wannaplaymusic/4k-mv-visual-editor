#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Engine Registry & Dynamic Discovery
負責動態發現、註冊與生命週期管理所有視覺生成器引擎
"""

import os
import sys
import importlib
import logging
from typing import Dict, List, Optional
from visual_studio_core.engines.base_engine import BaseVisualEngine, EngineMetadata

logger = logging.getLogger("VisualStudioPro.EngineRegistry")


class EngineRegistry:
    """視覺引擎單例註冊表"""
    _instance: Optional["EngineRegistry"] = None

    def __init__(self):
        self._engines: Dict[str, BaseVisualEngine] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "EngineRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.discover_and_register_all()
        return cls._instance

    def register(self, engine: BaseVisualEngine):
        meta = engine.get_metadata()
        self._engines[meta.id] = engine
        logger.info(f"✨ 成功註冊視覺生成器引擎: [{meta.name}] (ID: {meta.id}, 分類: {meta.category})")

    def get_engine(self, engine_id: str) -> Optional[BaseVisualEngine]:
        return self._engines.get(engine_id)

    def list_engines(self) -> List[EngineMetadata]:
        return [engine.get_metadata() for engine in self._engines.values()]

    def get_default_engine_id(self) -> str:
        if "math_synth" in self._engines:
            return "math_synth"
        if self._engines:
            return next(iter(self._engines.keys()))
        return ""

    def discover_and_register_all(self):
        """自動掃描 engines/ 目錄下的所有 engine_*.py 模組"""
        if self._initialized:
            return
        self._initialized = True

        current_dir = os.path.dirname(os.path.abspath(__file__))
        for fname in sorted(os.listdir(current_dir)):
            if fname.startswith("engine_") and fname.endswith(".py"):
                module_name = fname[:-3]
                full_module = f"visual_studio_core.engines.{module_name}"
                try:
                    mod = importlib.import_module(full_module)
                    # 搜尋模組中是否有繼承 BaseVisualEngine 的類別
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseVisualEngine)
                            and attr is not BaseVisualEngine
                        ):
                            engine_instance = attr()
                            self.register(engine_instance)
                except Exception as e:
                    logger.error(f"❌ 加載引擎模組 {full_module} 失敗: {e}", exc_info=True)


def get_engine_registry() -> EngineRegistry:
    return EngineRegistry.get_instance()
