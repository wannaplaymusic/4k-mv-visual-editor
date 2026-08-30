import os
import sys
import math
import random
import logging
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageChops, ImageFilter

logger = logging.getLogger("StandaloneInjector.PostProcessor")

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

if HAS_NUMBA:
    @numba.njit(fastmath=True)
    def _numba_pixel_sort_kernel(img_np, gray, threshold_map):
        h, w, c = img_np.shape
        for y in range(0, h, 2):
            start = -1
            for x in range(w):
                if gray[y, x] > threshold_map[y, x]:
                    if start == -1:
                        start = x
                else:
                    if start != -1:
                        length = x - start
                        if length > 5:
                            sub_gray = gray[y, start:x]
                            order = np.argsort(sub_gray)
                            sub_img = img_np[y, start:x].copy()
                            for idx in range(length):
                                img_np[y, start + idx] = sub_img[order[idx]]
                        start = -1
            if start != -1:
                length = w - start
                if length > 5:
                    sub_gray = gray[y, start:w]
                    order = np.argsort(sub_gray)
                    sub_img = img_np[y, start:w].copy()
                    for idx in range(length):
                        img_np[y, start + idx] = sub_img[order[idx]]
        return img_np


class DampingFilter:
    """單階非對稱阻尼插值濾波器，實作『起得快、落得慢』的極佳 VJ 視覺節奏"""
    def __init__(self, initial_value=0.0, lambda_attack=15.0, lambda_decay=2.5):
        self.value = initial_value
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, target, dt):
        if dt <= 0:
            return self.value
        lambda_val = self.lambda_attack if target > self.value else self.lambda_decay
        self.value += (target - self.value) * (1.0 - math.exp(-lambda_val * dt))
        return self.value


class DynamicBaselineAdapter:
    """滾動歷史緩衝區，利用 Z-Score 演算法將實時聲學特徵自適應歸一化"""
    def __init__(self, window_size=150):
        self.window_size = window_size
        self.history = []

    def update_and_normalize(self, val):
        self.history.append(val)
        if len(self.history) > self.window_size:
            self.history.pop(0)
        
        arr = np.array(self.history, dtype=np.float32)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        
        if std < 1e-4:
            return val
            
        norm = (val - mean) / (std + 1e-4)
        mapped = (norm + 1.5) / 3.0
        return max(0.0, min(1.0, float(mapped)))


class TimeDisplacementBuffer:
    """時空反饋狹縫掃描（Slit-Scan）影格環形緩衝區 (NumPy 原生直通)"""
    def __init__(self, max_size=30):
        self.max_size = max_size
        self.buffer = []
        self._grid_cache = None

    def push(self, img_np):
        self.buffer.append(img_np.copy())
        if len(self.buffer) > self.max_size:
            self.buffer.pop(0)

    def apply(self, img_np, intensity):
        if len(self.buffer) < 5 or intensity < 0.05 or cv2 is None:
            return img_np

        try:
            h, w = img_np.shape[:2]
            if self._grid_cache is None or self._grid_cache[0] != (w, h):
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                dist = np.sqrt((x - w / 2.0)**2 + (y - h / 2.0)**2)
                max_dist = np.sqrt((w / 2.0)**2 + (h / 2.0)**2)
                self._grid_cache = ((w, h), dist, max_dist)
            _, dist, max_dist = self._grid_cache
            
            delay_map = (dist / max_dist) * (self.max_size - 1) * intensity
            delay_map = np.clip(delay_map, 0, len(self.buffer) - 1).astype(np.int32)

            out_np = np.zeros_like(img_np)
            for d in range(len(self.buffer)):
                mask = (delay_map == d)
                if np.any(mask):
                    out_np[mask] = self.buffer[-(d + 1)][mask]

            return out_np
        except Exception as e:
            logger.error(f"Error in slit-scan: {e}")
            return img_np


class PhaseEffectController:
    """音訊相位效應動態控制器，具備能量門檻與 AD 包絡線平滑衰減機制"""
    def __init__(self, energy_threshold=0.03, phase_delta_threshold=0.10, decay_rate=0.88):
        self.energy_threshold = energy_threshold
        self.phase_delta_threshold = phase_delta_threshold
        self.decay_rate = decay_rate
        self.smoothed_intensity = 0.0
        self.prev_phase_width = 0.0

    def update(self, audio_energy: float, current_phase_width: float, dt: float = 0.033) -> float:
        if audio_energy < self.energy_threshold:
            self.smoothed_intensity *= self.decay_rate
            return self.smoothed_intensity

        phase_delta = abs(current_phase_width - self.prev_phase_width)
        self.prev_phase_width = current_phase_width

        if phase_delta > self.phase_delta_threshold or current_phase_width > 0.4:
            target = current_phase_width
        else:
            target = 0.0

        if target > self.smoothed_intensity:
            self.smoothed_intensity = 0.35 * target + 0.65 * self.smoothed_intensity
        else:
            self.smoothed_intensity *= self.decay_rate

        return float(np.clip(self.smoothed_intensity, 0.0, 1.0))


class FilterSweepController:
    """音訊濾波器掃頻與轉折控制器 (非對稱阻尼 Attack/Decay)"""
    def __init__(self, lambda_attack=18.0, lambda_decay=2.5):
        self.smoothed_lowpass = 1.0
        self.smoothed_highpass = 0.0
        self.smoothed_velocity = 0.0
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, lowpass_norm: float, highpass_norm: float, velocity_norm: float, dt: float = 0.033):
        dt = max(0.001, dt)
        
        l_speed = self.lambda_attack if lowpass_norm < self.smoothed_lowpass else self.lambda_decay
        self.smoothed_lowpass += (lowpass_norm - self.smoothed_lowpass) * (1.0 - math.exp(-l_speed * dt))
        
        h_speed = self.lambda_attack if highpass_norm > self.smoothed_highpass else self.lambda_decay
        self.smoothed_highpass += (highpass_norm - self.smoothed_highpass) * (1.0 - math.exp(-h_speed * dt))
        
        v_speed = self.lambda_attack if velocity_norm > self.smoothed_velocity else self.lambda_decay
        self.smoothed_velocity += (velocity_norm - self.smoothed_velocity) * (1.0 - math.exp(-v_speed * dt))

        return float(self.smoothed_lowpass), float(self.smoothed_highpass), float(self.smoothed_velocity)


class FeedbackSystem:
    """ 反應擴散（Reaction-Diffusion）迭代動力學反饋系統 """
    def __init__(self):
        self.feedback_img = None
        self._color_cache = None

    def apply(self, img_np, intensity, chord_name='N.C.', reverb_decay=0.15, custom_palette=None):
        if intensity < 0.05 or cv2 is None:
            return img_np

        h, w = img_np.shape[:2]
        if self.feedback_img is None or self.feedback_img.shape != (h, w):
            self.feedback_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            return img_np

        try:
            curr_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            blended = cv2.addWeighted(self.feedback_img, 1.0 - reverb_decay, curr_gray, reverb_decay, 0)
            
            scale = 1.01 + 0.005 * intensity
            rw, rh = int(w * scale), int(h * scale)
            diffused = cv2.resize(blended, (rw, rh), interpolation=cv2.INTER_LINEAR)
            
            left = (rw - w) // 2
            top = (rh - h) // 2
            diffused = diffused[top:top+h, left:left+w]
            if diffused.shape != (h, w):
                diffused = cv2.resize(diffused, (w, h), interpolation=cv2.INTER_LINEAR)

            mean_val = np.mean(diffused)
            diffused_float = diffused.astype(np.float32)
            contrast_factor = 1.3 + 0.3 * intensity
            diffused_enhanced = diffused_float * contrast_factor + mean_val * (1.0 - contrast_factor)
            diffused = np.clip(diffused_enhanced, 0, 255).astype(np.uint8)
            
            self.feedback_img = diffused

            chord_lower = chord_name.lower()
            is_minor = any(m in chord_lower for m in ('min', 'dim', 'aug')) or ('m' in chord_lower and 'maj' not in chord_lower)
            
            if self._color_cache is None or self._color_cache[0] != (h, w) or self._color_cache[1] != is_minor or self._color_cache[3] != id(custom_palette):
                if custom_palette and isinstance(custom_palette, dict):
                    morandi_rgb = custom_palette['minor'] if is_minor else custom_palette['major']
                else:
                    morandi_rgb = np.array([110, 180, 200], dtype=np.float32) / 255.0 if is_minor else np.array([230, 170, 190], dtype=np.float32) / 255.0
                self._color_cache = ((h, w), is_minor, morandi_rgb, id(custom_palette))
            
            _, _, morandi_rgb, _ = self._color_cache
            colored_feedback = (diffused[:, :, np.newaxis].astype(np.float32) * morandi_rgb).astype(np.uint8)
            
            return cv2.addWeighted(img_np, 1.0 - 0.25 * intensity, colored_feedback, 0.25 * intensity, 0)
        except Exception as e:
            logger.error(f"Error in reaction-diffusion feedback: {e}")
            return img_np


class VJAestheticEngine:
    """4K MV 全域 VJ 審美引擎"""
    PRESETS = {
        'CYBERPUNK': {'primary_rgb': (0, 240, 255), 'secondary_rgb': (255, 0, 85), 'bg_rgb': (11, 14, 20)},
        'SYNTHWAVE': {'primary_rgb': (121, 40, 202), 'secondary_rgb': (255, 0, 128), 'bg_rgb': (15, 5, 29)},
        'FLUID': {'primary_rgb': (0, 223, 137), 'secondary_rgb': (3, 105, 161), 'bg_rgb': (30, 41, 59)},
        'MONOCHROME': {'primary_rgb': (245, 158, 11), 'secondary_rgb': (113, 113, 122), 'bg_rgb': (9, 9, 11)}
    }

    @staticmethod
    def get_harmonic_color(pitch_class=0, energy=0.5, is_minor=False):
        base_hue = (pitch_class * 30 + 15) % 360
        sat = (0.35 + energy * 0.25) if is_minor else (0.65 + energy * 0.25)
        light = (0.25 + energy * 0.30) if is_minor else (0.45 + energy * 0.30)
        
        c = (1.0 - abs(2.0 * light - 1.0)) * sat
        x = c * (1.0 - abs((base_hue / 60.0) % 2 - 1.0))
        m = light - c / 2.0
        
        if base_hue < 60: r, g, b = c, x, 0.0
        elif base_hue < 120: r, g, b = x, c, 0.0
        elif base_hue < 180: r, g, b = 0.0, c, x
        elif base_hue < 240: r, g, b = 0.0, x, c
        elif base_hue < 300: r, g, b = x, 0.0, c
        else: r, g, b = c, 0.0, x
            
        return (float(r + m), float(g + m), float(b + m))


class ProceduralCameraRig:
    """程序化虛擬鏡頭矩陣：Dolly Zoom、手持漂移、旋轉與漩渦"""
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.mode = self.rng.choice(['orbit_spin', 'dolly_zoom_pulse', 'handheld_drift', 'spiral_vortex'])
        self.speed = self.rng.uniform(0.6, 1.4)
        self.amplitude = self.rng.uniform(0.8, 1.2)

    def apply(self, img_np, t, beat_energy, section_name='Verse'):
        if cv2 is None: return img_np
        h, w = img_np.shape[:2]
        center = (w / 2.0, h / 2.0)

        sec = section_name.lower()
        if 'intro' in sec or 'outro' in sec: intensity_scale = 0.2
        elif 'verse' in sec or 'bridge' in sec: intensity_scale = 0.4
        elif 'build' in sec: intensity_scale = 1.2
        else: intensity_scale = 1.75
        
        if beat_energy > 0.6: intensity_scale *= 1.3

        scale, angle, tx, ty = 1.0, 0.0, 0.0, 0.0

        if self.mode == 'orbit_spin':
            angle = math.sin(t * 0.5 * self.speed) * 3.5 * self.amplitude * intensity_scale
            scale = 1.0 + (math.cos(t * 0.8 * self.speed) * 0.03 + beat_energy * 0.02) * intensity_scale
        elif self.mode == 'dolly_zoom_pulse':
            scale = 1.0 + (math.sin(t * 1.2 * self.speed) * 0.05 + beat_energy * 0.05) * intensity_scale
            tx = math.sin(t * 0.9) * 12.0 * intensity_scale
            ty = math.cos(t * 0.7) * 12.0 * intensity_scale
        elif self.mode == 'handheld_drift':
            tx = (math.sin(t * 1.5) * 15.0 + math.cos(t * 3.1) * 8.0) * self.amplitude * intensity_scale
            ty = (math.cos(t * 1.3) * 15.0 + math.sin(t * 2.7) * 8.0) * self.amplitude * intensity_scale
            angle = math.sin(t * 0.8) * 1.2 * intensity_scale
        elif self.mode == 'spiral_vortex':
            angle = (t * 2.0 * self.speed) % 360.0 * 0.05 * intensity_scale
            scale = 1.02 + (beat_energy * 0.04) * intensity_scale

        M = cv2.getRotationMatrix2D(center, angle, scale)
        M[0, 2] += tx
        M[1, 2] += ty

        return cv2.warpAffine(img_np, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


class AudioParticleFluidEngine:
    """程序化 8 維基因粒子流體系統"""
    GEOMETRY_MODES = ['SoftSphere', 'CrystallinePolyhedron', 'RingTorus', 'RibbonStrand', 'StarDustDot', 'VortexMesh', 'InkBlob', 'QuantumDot', 'VolumetricCloud', 'MistFog', 'DynamicSmoke', 'LiquidDroplet']
    TRAJECTORY_MODES = ['NavierStokesFluid', 'LogarithmicSpiral', 'BrownianDiffusion', 'GravitationalAttractors', 'LinearJet', 'SineWaveFlow', 'ThermalBuoyancy']
    SHADER_MODES = ['VolumetricGlow', 'FerrofluidMetallic', 'NeonFresnel', 'InkDispersion', 'RefractiveCrystal', 'SingularityLensing', 'GaussianSplatting', 'LiquidRefraction']
    EMISSION_PATTERNS = ['RadialBloom', 'SpiralHelix', 'DualAttractors', 'UpwardFountain', 'EdgeRingInward']

    def __init__(self, max_particles=300, seed_string=None):
        import hashlib
        self.max_particles = max_particles
        self.particles = []
        self.cooldown = 0
        
        hash_val = int(hashlib.md5((seed_string or "default_fluid").encode('utf-8')).hexdigest(), 16)
        rng = random.Random(hash_val)

        self.geom_mode = rng.choice(self.GEOMETRY_MODES)
        self.traj_mode = rng.choice(self.TRAJECTORY_MODES)
        self.shader_mode = rng.choice(self.SHADER_MODES)
        self.emission_pattern = rng.choice(self.EMISSION_PATTERNS)
        self.viscosity = rng.uniform(0.88, 0.98)
        self.glow_feather = rng.uniform(0.3, 0.9)
        self.blur_length = rng.uniform(5.0, 25.0)
        self.splat_eccentricity = rng.uniform(1.5, 4.0)

    def update_and_render(self, img_np, t, is_beat, beat_energy, audio_feats, intensity=0.5, custom_palette=None, section_name='Verse'):
        if cv2 is None or intensity < 0.05:
            return img_np

        sec = section_name.lower()
        if any(s in sec for s in ('intro', 'outro', 'verse', 'bridge')):
            self.particles.clear()
            return img_np

        if self.cooldown > 0:
            self.cooldown -= 1
            if not self.particles: return img_np

        h, w = img_np.shape[:2]
        sub_bass = audio_feats.get('sub_bass', 0.0)

        if (is_beat and beat_energy > 0.6) and len(self.particles) == 0:
            self.cooldown = 75
            num_to_spawn = int((15 + 35 * beat_energy + 25 * sub_bass) * intensity)
            
            if custom_palette and isinstance(custom_palette, dict):
                base_color = custom_palette['minor'] if sub_bass > 0.4 else custom_palette['major']
                r_b, g_b, b_b = [int(c * 255) for c in base_color]
            else:
                r_b, g_b, b_b = (100, 200, 240)

            for i in range(min(num_to_spawn, self.max_particles)):
                if self.emission_pattern == 'DualAttractors':
                    cx = (w * 0.3) if (i % 2 == 0) else (w * 0.7)
                    cy = h * 0.5 + math.sin(t) * (h * 0.1)
                    ang = random.uniform(0, math.tau)
                    spd = random.uniform(3.0, 15.0) * (0.8 + 1.2 * beat_energy)
                elif self.emission_pattern == 'UpwardFountain':
                    cx = w * 0.5 + random.uniform(-w * 0.2, w * 0.2)
                    cy = h * 0.95
                    ang = random.uniform(-math.pi * 0.8, -math.pi * 0.2)
                    spd = random.uniform(8.0, 22.0) * (0.8 + 1.2 * beat_energy)
                else:
                    cx, cy = w / 2.0, h / 2.0
                    ang = random.uniform(0, math.tau)
                    spd = random.uniform(2.0, 12.0) * (0.8 + 1.2 * beat_energy)

                vx, vy = math.cos(ang) * spd, math.sin(ang) * spd
                life = random.uniform(0.8, 2.2) if self.geom_mode in ('DynamicSmoke', 'LiquidDroplet') else random.uniform(0.6, 1.8)
                sz = random.uniform(8.0, 30.0) if self.geom_mode in ('VolumetricCloud', 'MistFog', 'DynamicSmoke') else random.uniform(4.0, 14.0)
                drift = random.randint(-15, 15)
                color = (
                    int(max(0, min(255, r_b + drift))),
                    int(max(0, min(255, g_b + drift))),
                    int(max(0, min(255, b_b + drift)))
                )
                self.particles.append([cx, cy, vx, vy, life, life, sz, color])

        if not self.particles:
            return img_np

        overlay = img_np.copy()
        new_particles = []

        for p in self.particles:
            x, y, vx, vy, life, max_life, sz, color = p
            dt = 1.0 / 30.0
            
            vx += math.sin(y * 0.015 + t * 2.0) * math.cos(x * 0.01) * 30.0 * dt
            vy += math.cos(x * 0.015 - t * 2.0) * math.sin(y * 0.01) * 30.0 * dt

            x += vx
            y += vy
            life -= dt

            if life > 0 and 0 <= x < w and 0 <= y < h:
                alpha = (life / max_life)
                cur_sz = max(1, int(sz * alpha))
                cv2.circle(overlay, (int(x), int(y)), cur_sz, color, -1, lineType=cv2.LINE_AA)
                new_particles.append([x, y, vx, vy, life, max_life, sz, color])

        self.particles = new_particles
        blend_alpha = min(0.25, 0.15 * intensity + 0.1 * beat_energy)
        return cv2.addWeighted(img_np, 1.0 - blend_alpha, overlay, blend_alpha, 0)


class FluidSimulator:
    """基於渦流場（Vortex Field）的即時流體平流模擬器"""
    def __init__(self):
        self.vortices = [] 
        self._grid_cache = None

    def update_and_apply(self, img_np, t, is_beat, beat_energy, fluid_scale=1.0, spectral_centroid=0.2):
        new_vortices = []
        for v in self.vortices:
            v[4] -= 0.03
            if v[4] > 0:
                new_vortices.append(v)
        self.vortices = new_vortices

        if is_beat and len(self.vortices) < 4:
            cx = random.uniform(0.2, 0.8)
            cy = random.uniform(0.2, 0.8)
            rad = random.uniform(0.15, 0.3)
            strength = random.choice([-60.0, 60.0]) * (0.4 + 0.6 * beat_energy)
            self.vortices.append([cx, cy, rad, strength, 1.0])

        if not self.vortices or cv2 is None:
            return img_np

        try:
            h, w = img_np.shape[:2]
            if self._grid_cache is None or self._grid_cache[0] != (w, h):
                y, x = np.mgrid[0:h, 0:w].astype(np.float32)
                self._grid_cache = ((w, h), x, y)
            _, x, y = self._grid_cache

            dx = np.zeros_like(x)
            dy = np.zeros_like(y)

            for cx_r, cy_r, rad_r, strength, life in self.vortices:
                cx, cy = cx_r * w, cy_r * h
                rad = (rad_r * fluid_scale) * min(w, h)
                v_strength = strength * (1.0 + spectral_centroid * 0.5)
                
                rx, ry = x - cx, y - cy
                r2 = rx*rx + ry*ry
                dist = np.sqrt(r2)
                
                factor = np.exp(-r2 / (2.0 * rad * rad + 1e-5)) * v_strength * life
                dx += (-ry / (dist + 1.0)) * factor
                dy += (rx / (dist + 1.0)) * factor

            map_x = (x + dx).astype(np.float32)
            map_y = (y + dy).astype(np.float32)
            
            if map_x.shape != img_np.shape[:2]:
                self._grid_cache = None
                return img_np
                
            return cv2.remap(img_np, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        except Exception:
            return img_np


class PostProcessor:
    """工業級 4K VJ 多通道音視互動後製特效矩陣引擎"""
    def __init__(self, seed_string=None, genre='generic', used_themes=None, **kwargs):
        import hashlib
        self.time_displacement_buffer = TimeDisplacementBuffer(max_size=30)
        self.feedback_system = FeedbackSystem()
        self.fluid_simulator = FluidSimulator()
        self.phase_controller = PhaseEffectController()
        self.filter_controller = FilterSweepController()
        self.damping_filters = {}
        self.baseline_adapters = {}
        self.percussive_history = []
        self.last_t = 0.0

        self._grid_cache = None
        self._sediment_buffer = None
        self._mosh_vector = None
        self._fluid_scale = 1.0
        self._section_sig_cache = {}
        self._fx_cooldown = {}

        self.fx_active_states = {
            'spatial_warping': 0.0, 'fluid_noise': 0.0, 'temporal_feedback': 0.0,
            'color_spectral': 0.0, 'glow_illumination': 0.0, 'retro_degradation': 0.0,
            'pixel_sort': 0.0, 'kaleidoscope': 0.0, 'ambient_dsp': 0.0,
            'data_mosh': 0.0, 'sedimentation': 0.0, 'vector_scan': 0.0, 'temporal_fractal': 0.0,
            'kuwahara_paint': 0.0, 'matrix_ascii': 0.0, 'reaction_diffusion': 0.0,
            'phase_chromatic': 0.0, 'phase_swirl': 0.0, 'underwater_blur': 0.0, 
            'weightless_warp': 0.0, 'filter_shockwave': 0.0,
            'film_burn': 0.0, 'blueprint_edge': 0.0, 'turing_pattern': 0.0,
            'point_cloud_depth': 0.0, 'vector_scope': 0.0, 'lowpass_muffle': 0.0,
            'infinity_tunnel': 0.0, 'dolly_zoom': 0.0,
            'hologram_glitch': 0.0, 'voronoi_shatter': 0.0, 'thermal_infrared': 0.0,
            'ascii_cyber_matrix': 0.0, 'chromatic_radial_zoom': 0.0, 'synthwave_grid_scan': 0.0
        }

        self.time_vessel_size = 60
        self.time_vessel_dim = 16
        self.time_vessel = np.zeros((self.time_vessel_size, self.time_vessel_dim), dtype=np.float32)

        self.seed_string = seed_string
        if seed_string:
            hash_val = int(hashlib.md5(seed_string.encode('utf-8')).hexdigest(), 16)
            self.rng = random.Random(hash_val)
        else:
            self.rng = random.Random()

        genre_clean = genre.lower().strip() if isinstance(genre, str) else 'generic'
        is_electronic_genre = any(g in genre_clean for g in ('techno', 'electronic', 'dance', 'acid', 'dnb', 'dubstep', 'house'))
        if is_electronic_genre or self.rng.random() < 0.40:
            self.audio_particle_fluid = AudioParticleFluidEngine(seed_string=seed_string)
        else:
            self.audio_particle_fluid = None

        self.theme_pools = {
            'ParticleFluidMV': ['fluid_noise', 'reaction_diffusion', 'turing_pattern', 'spatial_warping', 'glow_illumination', 'sedimentation', 'chromatic_radial_zoom', 'underwater_blur'],
            'CyberGlitch': ['data_mosh', 'pixel_sort', 'hologram_glitch', 'matrix_ascii', 'film_burn', 'vector_scope', 'ascii_cyber_matrix', 'phase_chromatic', 'filter_shockwave'],
            'RetroAnalog': ['retro_degradation', 'vector_scan', 'blueprint_edge', 'lowpass_muffle', 'synthwave_grid_scan', 'underwater_blur'],
            'DreamyArtistic': ['glow_illumination', 'kuwahara_paint', 'temporal_feedback', 'sedimentation', 'fluid_noise', 'turing_pattern', 'point_cloud_depth', 'voronoi_shatter', 'weightless_warp'],
            'Psychedelic': ['color_spectral', 'kaleidoscope', 'reaction_diffusion', 'spatial_warping', 'infinity_tunnel', 'thermal_infrared', 'phase_swirl', 'weightless_warp'],
            'DigitalPixel': ['dolly_zoom', 'ascii_cyber_matrix', 'voronoi_shatter', 'filter_shockwave', 'temporal_fractal'],
            'AcidPsychedelic': ['reaction_diffusion', 'color_spectral', 'infinity_tunnel', 'turing_pattern', 'vector_scan', 'spatial_warping', 'hologram_glitch', 'chromatic_radial_zoom', 'phase_swirl', 'filter_shockwave']
        }
        
        self._all_pool_effects = set(fx for pool in self.theme_pools.values() for fx in pool)

        allowed_themes = list(self.theme_pools.keys())
        if 'acid' in genre_clean: allowed_themes = ['AcidPsychedelic', 'Psychedelic', 'CyberGlitch']
        elif genre_clean in ('lo-fi', 'ambient', 'jazz', 'classical'): allowed_themes = ['DreamyArtistic', 'RetroAnalog']
        elif is_electronic_genre: allowed_themes = ['CyberGlitch', 'AcidPsychedelic', 'DigitalPixel', 'Psychedelic']

        if used_themes:
            counts = {t: used_themes.count(t) for t in allowed_themes}
            min_count = min(counts.values())
            allowed_themes = [t for t, c in counts.items() if counts[t] == min_count]
            
        self.selected_theme = self.rng.choice(allowed_themes)
        self.signature_pool = self.theme_pools[self.selected_theme]
        self.signature_effects = set(self.rng.sample(self.signature_pool, min(2, len(self.signature_pool))))
        self.camera_rig = ProceduralCameraRig(rng=self.rng)

    def _hue_to_rgb(self, hue):
        h_val = (hue / 360.0) % 1.0
        i = int(h_val * 6.0)
        f = h_val * 6.0 - i
        q, t_h = 1.0 - f, f
        i = i % 6
        if i == 0: r, g, b = 1.0, t_h, 0.0
        elif i == 1: r, g, b = q, 1.0, 0.0
        elif i == 2: r, g, b = 0.0, 1.0, t_h
        elif i == 3: r, g, b = 0.0, q, 1.0
        elif i == 4: r, g, b = t_h, 0.0, 1.0
        else: r, g, b = 1.0, 0.0, q
        return (int(r * 255), int(g * 255), int(b * 255))

    def get_smoothed_val(self, key, target, dt, lambda_attack=15.0, lambda_decay=2.5):
        if key not in self.damping_filters:
            self.damping_filters[key] = DampingFilter(target, lambda_attack, lambda_decay)
        return self.damping_filters[key].update(target, dt)

    def get_normalized_val(self, key, val):
        if key not in self.baseline_adapters:
            self.baseline_adapters[key] = DynamicBaselineAdapter()
        return self.baseline_adapters[key].update_and_normalize(val)

    def process(self, img, t, is_beat, beat_energy, audio_feats, fx_flags, fx_prob=0.25, fx_intensity=0.5, adaptive_modulation=True, section_name='Verse', section_progress=0.0, genre='Generic'):
        original_size = img.size
        w, h = original_size
        genre_clean = genre.lower().strip() if isinstance(genre, str) else 'generic'
        is_scaled = False

        if w > 1920:
            scale_ratio = 1920.0 / w
            w_target, h_target = 1920, int(h * scale_ratio)
            img = img.resize((w_target, h_target), Image.Resampling.BICUBIC)
            is_scaled = True
            w, h = w_target, h_target

        dt = t - self.last_t
        if dt <= 0 or dt > 0.2: dt = 1.0 / 30.0
        self.last_t = t

        sec_clean = section_name.lower()
        section_fx_scale = 1.0
        if 'intro' in sec_clean or 'outro' in sec_clean: section_fx_scale = 0.25
        elif 'verse' in sec_clean or 'bridge' in sec_clean: section_fx_scale = 0.5
        elif 'chorus' in sec_clean or 'drop' in sec_clean: section_fx_scale = 1.2
        elif 'build' in sec_clean: section_fx_scale = 0.85

        is_anticipation = ('build' in sec_clean) and (section_progress > 0.85)
        if is_anticipation:
            section_fx_scale *= 0.15
            fx_intensity *= 0.15

        sub_bass_ch = audio_feats.get('sub_bass', beat_energy)
        fx_intensity = fx_intensity * section_fx_scale * (0.8 + 0.4 * sub_bass_ch)

        # 1. 虛擬相機微動
        try:
            img_np = np.array(img.convert('RGB'))
            img_np = self.camera_rig.apply(img_np, t, beat_energy, section_name=section_name)
            if self.audio_particle_fluid is not None and not is_anticipation:
                img_np = self.audio_particle_fluid.update_and_render(
                    img_np, t, is_beat, beat_energy, audio_feats, intensity=fx_intensity, section_name=section_name
                )
        except Exception:
            img_np = np.array(img.convert('RGB'))

        self.time_displacement_buffer.push(img_np)

        # 2. 拍點與音訊特徵調變
        sub_bass = self.get_normalized_val('sub_bass', audio_feats.get('sub_bass', 0.0))
        percussive = self.get_normalized_val('percussive', audio_feats.get('percussive', 0.0))
        ethereal = audio_feats.get('ethereal', 0.0)

        smoothed_sub_bass = self.get_smoothed_val('sub_bass', sub_bass, dt, 15.0, 2.0)
        smoothed_ethereal = self.get_smoothed_val('ethereal', ethereal, dt, 8.0, 1.8)

        # 3. 核心濾鏡效果 Pass（NumPy 零拷貝鏈）
        if fx_flags.get('spatial_warping', True) and self.selected_theme in ('Psychedelic', 'AcidPsychedelic', 'CyberGlitch'):
            if cv2 is not None:
                shift_val = int(math.sin(t * 3.0) * 15.0 * fx_intensity * smoothed_sub_bass)
                if abs(shift_val) > 0:
                    img_np = np.roll(img_np, shift_val, axis=1)

        if fx_flags.get('glow_illumination', True) and is_beat and beat_energy > 0.4:
            if cv2 is not None:
                # 安全溫和光暈 (Photosensitive Safe Bloom)
                alpha = min(0.08, 0.05 * beat_energy * fx_intensity)
                flash_canvas = np.zeros_like(img_np)
                flash_canvas[:, :] = (180, 170, 160)
                img_np = cv2.addWeighted(img_np, 1.0 - alpha, flash_canvas, alpha, 0)

        if fx_flags.get('color_spectral', True) and sub_bass > 0.4:
            # 輕微色差色散
            shift_px = max(1, int(10 * fx_intensity * sub_bass))
            img_np[:, :, 0] = np.roll(img_np[:, :, 0], shift_px, axis=1)
            img_np[:, :, 2] = np.roll(img_np[:, :, 2], -shift_px, axis=1)

        # 4. 顏色增強與終端銳化
        if fx_flags.get('color_boost', True):
            exposure = 1.05 + 0.1 * beat_energy if is_beat else 1.0
            img_np = self.apply_color_enhancement(img_np, contrast=1.12, saturation=1.15, exposure=exposure)

        if fx_flags.get('sharpen', True):
            img_np = self.apply_sharpening(img_np, amount=0.6, radius=1.0)

        if is_scaled and cv2 is not None:
            img_np = cv2.resize(img_np, original_size, interpolation=cv2.INTER_LANCZOS4)

        return Image.fromarray(img_np)

    def apply_color_enhancement(self, img_np, contrast=1.12, saturation=1.15, exposure=1.0):
        if cv2 is None: return img_np
        try:
            if abs(exposure - 1.0) > 0.01:
                img_np = np.clip(img_np * exposure, 0, 255).astype(np.uint8)
            if abs(saturation - 1.0) > 0.01:
                hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV).astype(np.float32)
                hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0.0, 255.0)
                img_np = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
            return img_np
        except Exception:
            return img_np

    def apply_sharpening(self, img_np, amount=0.6, radius=1.0):
        if cv2 is None or amount < 0.01: return img_np
        try:
            blurred = cv2.GaussianBlur(img_np, (3, 3), radius)
            sharpened = cv2.addWeighted(img_np, 1.0 + amount, blurred, -amount, 0)
            return np.clip(sharpened, 0, 255).astype(np.uint8)
        except Exception:
            return img_np


def apply_advanced_transition(pil_a, pil_b, progress, trans_type='displacement', intensity=0.5, is_beat=False, beat_energy=0.0, wipe_pattern='auto', chord_color_hex='#0a0a0c'):
    """高階轉場混合引擎"""
    progress = float(np.clip(progress, 0.0, 1.0))
    if progress <= 0.001: return pil_a
    if progress >= 0.999: return pil_b
        
    img_a = np.array(pil_a.convert("RGB"))
    img_b = np.array(pil_b.convert("RGB"))
    h, w = img_a.shape[:2]

    if cv2 is None:
        out_np = (img_a * (1.0 - progress) + img_b * progress).astype(np.uint8)
        return Image.fromarray(out_np, "RGB").convert("RGBA")

    try:
        if trans_type == 'displacement':
            y_grid, x_grid = np.mgrid[0:h, 0:w].astype(np.float32)
            wave_len = w * 0.15
            wave_amp = intensity * 40.0
            disp_strength = float(np.sin(progress * np.pi) * wave_amp)
            
            dx = np.sin(y_grid / wave_len * 2.0 * np.pi) * disp_strength
            dy = np.cos(x_grid / wave_len * 2.0 * np.pi) * disp_strength
            
            map_x_a = (x_grid + dx * (1.0 - progress)).astype(np.float32)
            map_y_a = (y_grid + dy * (1.0 - progress)).astype(np.float32)
            warped_a = cv2.remap(img_a, map_x_a, map_y_a, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            map_x_b = (x_grid - dx * progress).astype(np.float32)
            map_y_b = (y_grid - dy * progress).astype(np.float32)
            warped_b = cv2.remap(img_b, map_x_b, map_y_b, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            
            out_np = cv2.addWeighted(warped_a, 1.0 - progress, warped_b, progress, 0.0)
        else:
            out_np = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
    except Exception:
        out_np = cv2.addWeighted(img_a, 1.0 - progress, img_b, progress, 0.0)
        
    return Image.fromarray(out_np.astype(np.uint8), "RGB").convert("RGBA")


class SongProceduralFluidEngine:
    """
    歌曲專屬 16-Gene Visual DNA 程序化流體與粒子保底演算法
    - 以全曲時間戳 t 作為自變數，進行常數級 O(1) 時間連續演化，絕不因分鏡切換從 0 幀重算。
    """
    def __init__(self, song_key: str = "default_track"):
        import hashlib
        self.song_key = song_key or "default_track"
        hash_val = int(hashlib.md5(self.song_key.encode('utf-8')).hexdigest(), 16)
        rng = random.Random(hash_val)

        self.gene_hue_base = rng.uniform(0.0, 360.0)
        self.gene_viscosity = rng.choice(['LiquidMetals', 'GasNebula', 'QuantumPlasma', 'GoldenLava', 'CyberMercury'])
        self.gene_fluid_scale = rng.uniform(0.2, 2.0)
        self.gene_turbulence_freq = rng.uniform(0.2, 5.0)
        self.gene_bloom_radius = rng.uniform(0.3, 1.2)
        self.phase_seed = rng.uniform(0.0, 5000.0)

    def render_emergency_frame(self, w: int, h: int, t: float, beat_energy: float = 0.5, sub_bass: float = 0.5, chord_hex: str = "#a855f7"):
        try:
            hex_c = chord_hex.lstrip('#')
            r_base = int(hex_c[0:2], 16) if len(hex_c) == 6 else 168
            g_base = int(hex_c[2:4], 16) if len(hex_c) == 6 else 85
            b_base = int(hex_c[4:6], 16) if len(hex_c) == 6 else 247

            img_np = np.zeros((h, w, 3), dtype=np.uint8)
            evolve_time = t * self.gene_turbulence_freq + self.phase_seed
            
            cx1 = int(w * 0.5 + np.sin(evolve_time * 0.7) * (w * 0.25 * self.gene_fluid_scale))
            cy1 = int(h * 0.5 + np.cos(evolve_time * 0.9) * (h * 0.20 * self.gene_fluid_scale))
            
            cx2 = int(w * 0.5 + np.cos(evolve_time * 1.1) * (w * 0.30 * self.gene_fluid_scale))
            cy2 = int(h * 0.5 + np.sin(evolve_time * 0.6) * (h * 0.25 * self.gene_fluid_scale))

            radius1 = max(5, int(min(w, h) * (0.20 + beat_energy * 0.15)))
            radius2 = max(5, int(min(w, h) * (0.16 + sub_bass * 0.20)))

            if cv2 is not None:
                cv2.circle(img_np, (cx1, cy1), radius1, (b_base, g_base, r_base), -1)
                cv2.circle(img_np, (cx2, cy2), radius2, (r_base, b_base, g_base), -1)
                blur_kernel = max(3, int(min(w, h) * 0.06 * self.gene_bloom_radius) | 1)
                img_np = cv2.GaussianBlur(img_np, (blur_kernel, blur_kernel), 0)

            return Image.fromarray(img_np, "RGB").convert("RGBA")
        except Exception:
            return Image.new("RGBA", (w, h), (10, 10, 15, 255))
