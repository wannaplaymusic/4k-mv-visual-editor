import random
import itertools

ALL_POST_FX_KEYS = [
    'film_burn', 'blueprint_edge', 'turing_pattern', 'point_cloud_depth', 'vector_scope',
    'lowpass_muffle', 'infinity_tunnel', 'dolly_zoom', 'data_mosh', 'pixel_sort',
    'scanline_glitch', 'matrix_ascii', 'phase_slit', 'centroid_glitch', 'spatial_warping',
    'domain_warping', 'color_spectral', 'sedimentation', 'handheld_camera', 'photocopy_smear',
    'tension_overlay', 'vignette_pulse', 'fluid_noise', 'kaleidoscope', 'temporal_feedback'
]

class ShaderMutator:
    def __init__(self, track_seed: int):
        self.track_seed = track_seed
        self.rng = random.Random(track_seed)

    def mutate_sdf_shader(self, base_glsl: str) -> str:
        """ 將 Track Seed 注入 GLSL 著色器，改變 3D 幾何結構與扭曲公式 """
        k1 = round(self.rng.uniform(1.5, 8.5), 3)
        k2 = round(self.rng.uniform(2.0, 12.0), 3)
        shape_type = self.rng.choice(["sdTorus", "sdBox", "sdOctahedron", "sdFractal"])
        
        mutation_block = f"""
        // === Generated Procedural Shader Mutation ===
        #define MUTATED_K1 {k1}
        #define MUTATED_K2 {k2}
        
        float mapCustomSDF(vec3 p, float audioLow) {{
            float baseShape = {shape_type}(p, vec2(1.2, 0.4));
            float displacement = sin(p.x * MUTATED_K1) * cos(p.y * MUTATED_K2) * (0.2 + audioLow * 0.5);
            return baseShape + displacement;
        }}
        """
        if "// [[MUTATION_POINT]]" in base_glsl:
            return base_glsl.replace("// [[MUTATION_POINT]]", mutation_block)
        return base_glsl + "\n" + mutation_block

    def get_signature_fx_recipe(self) -> list:
        """ 為每首歌專屬鎖定 C(25, 3) 組合中的 3 個 Signature Effects """
        # 從 25 種全域後製特效中選取 3 種作為該音軌的極致視覺標籤
        selected_fx = self.rng.sample(ALL_POST_FX_KEYS, 3)
        return selected_fx
