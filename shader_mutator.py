import os
import random
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

SHADERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shaders")

# 33 個獨立動態特效（排除 final pass 的 postprocess）
ALL_POST_FX_KEYS = [
    'fluid_solver', 'particle_gpgpu', 'raymarching', 'ssfr_fluid_render',
    'thin_film_interference', 'attractor_field', 'gyroid_surface', 'reaction_diffusion',
    'voronoi_crystalline', 'acoustic_chladni', 'volumetric_godrays', 'volumetric_nebula',
    'drone_spectral_fog', 'caustic_refraction_flow', 'gravitational_lensing', 'marangoni_convection',
    'polarization_refraction', 'aurora_borealis_curtain', 'cloud_cumulus_raymarching', 'rain_window_refraction',
    'bioluminescence_marine', 'matrix_glitch_mosaic', 'ascii_dither_retro', 'anamorphic_lens_flare',
    'audio_kaleidoscope', 'colloidal_shockwave', 'hyperspace_warp', 'holographic_interference',
    'stochastic_bokeh_blur', 'dub_delay_feedback', 'analog_saturation_grain', 'deep_house_caustic_grid',
    'minimal_voronoi_dots'
]

# 每個 Shader 對應需要的特化 Audio Uniform 映射表
SHADER_AUDIO_UNIFORMS = {
    'fluid_solver': ['u_velocityTexture', 'u_densityTexture', 'u_resolution', 'u_dt', 'u_viscosity'],
    'particle_gpgpu': ['u_particlePos', 'u_particleVel', 'u_dt', 'u_time'],
    'raymarching': ['u_resolution', 'u_time', 'u_bassEnergy'],
    'ssfr_fluid_render': ['u_depthTexture', 'u_densityTexture', 'u_resolution', 'u_spectralCentroid', 'u_lightPos'],
    'thin_film_interference': ['u_normalTexture', 'u_time', 'u_filmThickness'],
    'attractor_field': ['u_resolution', 'u_time', 'u_energy', 'u_params'],
    'gyroid_surface': ['u_resolution', 'u_time', 'u_bassEnergy'],
    'reaction_diffusion': ['u_stateTexture', 'u_resolution', 'u_feedRate', 'u_killRate', 'u_dt'],
    'voronoi_crystalline': ['u_time', 'u_snareTrigger', 'u_scale'],
    'acoustic_chladni': ['u_nodeM', 'u_nodeN', 'u_time'],
    'volumetric_godrays': ['u_sceneTexture', 'u_lightScreenPos', 'u_godRayIntensity'],
    'volumetric_nebula': ['u_resolution', 'u_time', 'u_bassBoost', 'u_colorPalette'],
    'drone_spectral_fog': ['u_resolution', 'u_time', 'u_spectralFlux', 'u_droneResonance', 'u_palette'],
    'caustic_refraction_flow': ['u_time', 'u_spectralCentroid', 'u_primaryColor'],
    'gravitational_lensing': ['u_sceneTexture', 'u_center', 'u_subBassIntensity', 'u_aspectRatio'],
    'marangoni_convection': ['u_fluidState', 'u_resolution', 'u_spectralDrift'],
    'polarization_refraction': ['u_time', 'u_tonnetzAngle', 'u_crystalDensity'],
    'aurora_borealis_curtain': ['u_resolution', 'u_time', 'u_auroraIntensity', 'u_primaryColor', 'u_accentColor'],
    'cloud_cumulus_raymarching': ['u_resolution', 'u_time', 'u_sunLightDir'],
    'rain_window_refraction': ['u_backgroundTexture', 'u_time', 'u_rainDensity'],
    'bioluminescence_marine': ['u_resolution', 'u_time', 'u_bioPulse', 'u_glowColor'],
    'matrix_glitch_mosaic': ['u_inputTexture', 'u_time', 'u_glitchTrigger'],
    'ascii_dither_retro': ['u_sceneTexture', 'u_resolution', 'u_ditherAmount'],
    'anamorphic_lens_flare': ['u_sceneTexture', 'u_snareTrigger', 'u_distortionAmount'],
    'audio_kaleidoscope': ['u_inputTexture', 'u_segments', 'u_rotation'],
    'colloidal_shockwave': ['u_sceneTexture', 'u_resolution', 'u_time', 'u_kickTrigger', 'u_epicenter'],
    'hyperspace_warp': ['u_inputTexture', 'u_speedFactor'],
    'holographic_interference': ['u_time', 'u_chromaHue'],
    'stochastic_bokeh_blur': ['u_sceneTexture', 'u_resolution', 'u_apertureSize'],
    'dub_delay_feedback': ['u_currentFrame', 'u_feedbackBuffer', 'u_delayFeedback', 'u_stabTrigger'],
    'analog_saturation_grain': ['u_sceneTexture', 'u_time', 'u_hissLevel', 'u_drive'],
    'deep_house_caustic_grid': ['u_resolution', 'u_time', 'u_chordTrigger', 'u_bassDrive', 'u_primaryColor', 'u_secondaryColor'],
    'minimal_voronoi_dots': ['u_time', 'u_clickPopTrigger', 'u_gridScale'],
    'postprocess': ['u_mainScene', 'u_bloomTexture', 'u_bloomIntensity', 'u_vignetteStrength']
}


@lru_cache(maxsize=64)
def _read_shader_disk_cached(filepath: str) -> str:
    """底層硬碟快取，避免重複讀取相同的 .frag 檔案"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


class ShaderMutator:
    def __init__(self, track_seed: int):
        self.track_seed = track_seed
        self.rng = random.Random(track_seed)

    def load_shader_code(self, shader_name: str) -> str:
        """從 shaders/ 資料夾讀取指定的 GLSL 片段著色器"""
        clean_name = shader_name.replace(".frag", "")
        filename = f"{clean_name}.frag"
        filepath = os.path.join(SHADERS_DIR, filename)

        if not os.path.exists(filepath):
            logger.warning(f"Shader file {filename} not found in {SHADERS_DIR}")
            return ""

        try:
            return _read_shader_disk_cached(filepath)
        except Exception as e:
            logger.error(f"Failed to read shader file {filepath}: {e}")
            return ""

    def get_shader_uniform_map(self, shader_name: str) -> list:
        """取得指定 Shader 需要傳遞的 Audio/System Uniform 名稱列表"""
        clean_name = shader_name.replace(".frag", "")
        return SHADER_AUDIO_UNIFORMS.get(clean_name, ['u_resolution', 'u_time'])

    def mutate_sdf_shader(self, base_glsl: str) -> str:
        """將 Track Seed 注入 GLSL 著色器，保證型別安全的 SDF 幾何結構突變"""
        k1 = round(self.rng.uniform(1.5, 8.5), 3)
        k2 = round(self.rng.uniform(2.0, 12.0), 3)

        # 型別嚴謹的 SDF 產生器字典
        sdf_shape_generators = [
            lambda: "sdTorus(p, vec2(1.2, 0.4))",
            lambda: "sdBox(p, vec3(0.8, 0.8, 0.8))",
            lambda: "sdOctahedron(p, 1.0)",
            lambda: "sdSphere(p, 1.1)",
            lambda: "sdGyroid(p, 1.5, 0.05, 0.1)"
        ]
        base_shape_expr = self.rng.choice(sdf_shape_generators)()

        mutation_block = f"""
// === Generated Procedural Shader Mutation [Seed: {self.track_seed}] ===
#define MUTATED_K1 {k1:.3f}
#define MUTATED_K2 {k2:.3f}

float mapCustomSDF(vec3 p, float audioLow) {{
    float baseShape = {base_shape_expr};
    float displacement = sin(p.x * MUTATED_K1) * cos(p.y * MUTATED_K2) * (0.2 + audioLow * 0.5);
    return baseShape + displacement;
}}
"""
        if "// [[MUTATION_POINT]]" in base_glsl:
            return base_glsl.replace("// [[MUTATION_POINT]]", mutation_block)
        return base_glsl + "\n" + mutation_block

    def get_signature_fx_recipe(self) -> list:
        """為每首歌專屬鎖定 C(33, 3) 組合中的 3 個 Signature Effects"""
        return self.rng.sample(ALL_POST_FX_KEYS, 3)
