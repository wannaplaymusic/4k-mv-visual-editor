"""
SAVAP (Surreal-AudioVisual Asset Pipeline) Universal Asset Schema
對齊 Google Antigravity SAVAP Technical Blueprint 第 9 頁之規範。

提供資產資料模型、驗證器、MediaPipe 33-point 骨骼層次管理、
Socket Affordance (幾何插槽) 與音視頻運動學預設 (Dynamics Preset)。
"""

import json
import uuid
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum


class DynamicsPresetEnum(str, Enum):
    SUB_BASS_MELT = "SUB_BASS_MELT"               # 20-60Hz 達利軟性液態融化
    KICK_SPRING_OVERSHOOT = "KICK_SPRING_OVERSHOOT" # Low-Mid/Kick 彈簧超調剪紙偶
    MID_ORBITAL_ROTATION = "MID_ORBITAL_ROTATION"   # 1-4kHz 天體軌道公轉
    HIHAT_SOLARIZATION = "HIHAT_SOLARIZATION"       # 8kHz+ 日光化金屬暴光閃爍
    STATIC_METAPHYSICAL = "STATIC_METAPHYSICAL"     # 形而上基里科靜態孤立本體


@dataclass
class SocketAffordance:
    """幾何插槽與旋轉錨點特徵"""
    cavity_centroid: Tuple[float, float] = (0.5, 0.5) # 正規化 (x, y) 凹陷或質心
    rotation_pivot: Tuple[float, float] = (0.5, 0.5)  # 物理旋轉錨點
    docking_angle: float = 0.0                       # 推薦咬合角度 (度)
    affordance_type: str = "cavity_socket"           # cavity_socket | protrusion_plug


@dataclass
class RiggingMetadata:
    """骨骼拓撲與 IK 關節階層 (對齊 MediaPipe 33 點)"""
    has_skeleton: bool = False
    landmarks_33: List[Tuple[float, float, float]] = field(default_factory=list) # (x, y, z)
    hierarchy: Dict[str, List[int]] = field(default_factory=lambda: {
        "head": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "torso": [11, 12, 23, 24],
        "upper_limbs": [11, 13, 15, 12, 14, 16],
        "lower_limbs": [23, 25, 27, 24, 26, 28]
    })
    socket_affordance: SocketAffordance = field(default_factory=SocketAffordance)


@dataclass
class ShaderUniforms:
    """WebGL Fragment Shader 動態調控參數"""
    u_hatch_density: float = 0.35      # 排線雕版密度 (Ernst)
    u_hatch_angle: float = 45.0        # 排線角度
    u_solarization_th: float = 0.85    # 中途感光白閃閾值 (Man Ray)
    u_grain_intensity: float = 0.08    # 膠卷噪訊強度
    u_dali_viscosity: float = 0.5      # 達利流體黏滯度
    u_halftone_scale: float = 0.15     # 網點縮放比例


@dataclass
class SAVAPUniversalAsset:
    """
    符合 SAVAP 規範的統一資產資料結構
    """
    asset_id: str = field(default_factory=lambda: f"savap_{uuid.uuid4().hex[:12]}")
    name: str = "untitled_asset"
    source_uri: str = ""
    source_hash: str = ""              # 32-bit 確定性雜湊種子
    category: str = "surreal_collage"
    composition_z: float = 0.4         # 景深座標 (0.0=最近前景, 1.0=最遠背景)
    dynamics_preset: str = DynamicsPresetEnum.KICK_SPRING_OVERSHOOT.value
    rigging_metadata: RiggingMetadata = field(default_factory=RiggingMetadata)
    shader_uniforms: ShaderUniforms = field(default_factory=ShaderUniforms)
    tags: List[str] = field(default_factory=list)
    custom_properties: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_from_image_path(cls, image_path: str, name: str = "", z_depth: float = 0.4) -> "SAVAPUniversalAsset":
        """根據圖片路徑自動計算確定性 Hash 並產生資產"""
        hasher = hashlib.sha256()
        with open(image_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        
        # 32-bit seed
        seed_32 = int(digest[:8], 16)
        
        # 依據 Hash 確定性決定預設排線角度與噪訊
        hatch_angle = float((seed_32 % 180))
        grain_density = 0.04 + float((seed_32 % 100)) / 1000.0

        uniforms = ShaderUniforms(
            u_hatch_angle=hatch_angle,
            u_grain_intensity=grain_density
        )

        return cls(
            asset_id=f"savap_{digest[:12]}",
            name=name or image_path.split("/")[-1],
            source_uri=image_path,
            source_hash=digest[:16],
            composition_z=z_depth,
            shader_uniforms=uniforms
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SAVAPUniversalAsset":
        """從字典反序列化"""
        rig_data = data.get("rigging_metadata", {})
        socket_data = rig_data.get("socket_affordance", {})
        socket_obj = SocketAffordance(**socket_data) if socket_data else SocketAffordance()
        
        rig_data_copy = dict(rig_data)
        if "socket_affordance" in rig_data_copy:
            rig_data_copy["socket_affordance"] = socket_obj
            
        rigging_obj = RiggingMetadata(**rig_data_copy) if rig_data else RiggingMetadata()
        uniforms_data = data.get("shader_uniforms", {})
        uniforms_obj = ShaderUniforms(**uniforms_data) if uniforms_data else ShaderUniforms()

        return cls(
            asset_id=data.get("asset_id", f"savap_{uuid.uuid4().hex[:12]}"),
            name=data.get("name", ""),
            source_uri=data.get("source_uri", ""),
            source_hash=data.get("source_hash", ""),
            category=data.get("category", "surreal_collage"),
            composition_z=float(data.get("composition_z", 0.4)),
            dynamics_preset=data.get("dynamics_preset", DynamicsPresetEnum.KICK_SPRING_OVERSHOOT.value),
            rigging_metadata=rigging_obj,
            shader_uniforms=uniforms_obj,
            tags=data.get("tags", []),
            custom_properties=data.get("custom_properties", {})
        )
