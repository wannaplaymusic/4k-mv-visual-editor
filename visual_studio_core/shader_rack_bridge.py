import os
import glob
import logging

logger = logging.getLogger("VisualStudio.ShaderRackBridge")

class ShaderRackBridge:
    """
    36 款 GLSL 著色器外掛機架橋接器
    - 掃描並載入 shaders/*.frag 著色器元數據
    - 為 WebGL / p5.js 畫布生成後製疊加管線 (Post-FX Pipeline)
    - 支援序列化存入 custom_visuals/*.json 的 post_fx 欄位
    """

    POPULAR_SHADERS = [
        {
            "id": "volumetric_godrays",
            "name": "體積丁達爾神光 (Godrays)",
            "file": "volumetric_godrays.frag",
            "default_intensity": 0.75,
            "category": "light",
            "desc": "以視覺中心為放射源穿透粒子的體積射線光斑"
        },
        {
            "id": "chromatic_aberration",
            "name": "類比膠片色散 (RGB Split)",
            "file": "analog_saturation_grain.frag",
            "default_intensity": 0.60,
            "category": "optics",
            "desc": "重低音激發時邊緣產生紅青光學色散與底片噪點"
        },
        {
            "id": "reaction_diffusion",
            "name": "反應擴散回授 (Reaction Diffusion)",
            "file": "reaction_diffusion.frag",
            "default_intensity": 0.80,
            "category": "bio",
            "desc": "畫面動態反饋並生成類似化學斑紋的液態擴散"
        },
        {
            "id": "matrix_glitch_mosaic",
            "name": "數位矩陣故障 (Glitch Mosaic)",
            "file": "matrix_glitch_mosaic.frag",
            "default_intensity": 0.50,
            "category": "cyber",
            "desc": "隨高頻節奏撕裂畫面產生賽博龐克馬賽克條紋"
        },
        {
            "id": "caustic_refraction_flow",
            "name": "焦散流體折射 (Caustics)",
            "file": "caustic_refraction_flow.frag",
            "default_intensity": 0.70,
            "category": "optics",
            "desc": "如陽光穿透波動水面的網狀聚焦折射光影"
        },
        {
            "id": "aurora_borealis_curtain",
            "name": "極光天幕 (Aurora Borealis)",
            "file": "aurora_borealis_curtain.frag",
            "default_intensity": 0.85,
            "category": "atmospheric",
            "desc": "大氣層電離色帶在背景中柔和飄盪"
        }
    ]

    def __init__(self, workspace_dir: str = None):
        self.workspace_dir = workspace_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.shaders_dir = os.path.join(self.workspace_dir, "shaders")
        self.available_shaders = self._discover_shaders()

    def _discover_shaders(self) -> list:
        """掃描 shaders 目錄並結合熱門預設"""
        discovered = list(self.POPULAR_SHADERS)
        if not os.path.exists(self.shaders_dir):
            return discovered

        frag_files = glob.glob(os.path.join(self.shaders_dir, "*.frag"))
        known_files = {s["file"] for s in discovered}

        for f in frag_files:
            fname = os.path.basename(f)
            if fname not in known_files:
                sid = fname.replace(".frag", "")
                discovered.append({
                    "id": sid,
                    "name": sid.replace("_", " ").title(),
                    "file": fname,
                    "default_intensity": 0.5,
                    "category": "misc",
                    "desc": f"專案自定義 GLSL 著色器: {fname}"
                })

        return discovered

    def get_rack_presets(self) -> list:
        return self.available_shaders

    def generate_webgl_fx_script(self, active_shaders: list) -> str:
        """
        生成注入前端的 Post-FX 著色器管線呼叫
        """
        items = []
        for s in active_shaders:
            sid = s.get("id")
            intensity = s.get("intensity", 0.5)
            items.append(f"{{ id: '{sid}', intensity: {intensity} }}")
        
        arr_str = ", ".join(items)
        return f"""(function() {{
            if (window.setPostShaders) {{
                window.setPostShaders([{arr_str}]);
            }}
        }})();"""
