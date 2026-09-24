import os
import re
import math
import logging
import hashlib
import queue
import threading
import colorsys
from typing import Dict, List, Tuple, Optional, Union

import numpy as np
from scipy import signal
from scipy.ndimage import median_filter
import librosa
import yt_dlp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

# Standard 12 Pitch Classes
PITCH_CLASSES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# =====================================================================
# 1. 現代知覺均勻色彩引擎 (Oklab Color Space Generator)
# =====================================================================
def oklab_to_srgb(L: float, a: float, b: float) -> Tuple[int, int, int]:
    """
    將感知均勻的 Oklab 空間轉換至標準 sRGB (0-255)。
    Oklab 具有極佳的知覺線性與均勻明度特性，能徹底消除傳統 HSL
    在色相切換時造成的感知亮度劇烈跳躍 (Perceptual Luminance Strobing)。
    """
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_out = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def gamma_correct(c: float) -> int:
        c = np.clip(c, 0.0, 1.0)
        c = 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055
        return int(round(c * 255.0))

    return gamma_correct(r), gamma_correct(g), gamma_correct(b_out)


def hsl_to_hex(h_deg: float, s_pct: float, l_pct: float) -> str:
    """向後相容之標準 HSL 轉 Hex 輔助函數"""
    r, g, b = colorsys.hls_to_rgb(float(h_deg) / 360.0, float(l_pct), float(s_pct))
    return f"#{int(r * 255.999):02x}{int(g * 255.999):02x}{int(b * 255.999):02x}"


class AdvancedProceduralPalette:
    """
    基於 Oklab 與五度圈 (Circle of Fifths) 諧波映射的程序化調色盤。
    支援 Cyberpunk, Vaporwave, Abyssal, Ethereal, GoldenLava 等多種高審美風格。
    """
    def __init__(self, seed_string: Optional[str] = None):
        import random
        seed = int(hashlib.sha256(seed_string.encode('utf-8')).hexdigest(), 16) if seed_string else None
        self.rng = random.Random(seed)
        
        self.style = self.rng.choice([
            'Cyberpunk', 'Vaporwave', 'Abyssal', 'Ethereal', 'MonochromeNeon', 'GoldenLava', 'DeepOcean'
        ])
        self.base_angle = self.rng.uniform(0.0, 2.0 * math.pi)
        self.base_hue = math.degrees(self.base_angle) % 360.0
        self.chord_map = {}
        self._bake_palette()

    def _bake_palette(self):
        for root in range(12):
            fifths_order = (root * 7) % 12
            angle = self.base_angle + (fifths_order / 12.0) * 2.0 * math.pi
            
            if self.style == 'Cyberpunk':
                chroma = 0.24 if fifths_order % 2 == 0 else 0.28
                lightness = 0.65
            elif self.style == 'Vaporwave':
                chroma = 0.20
                lightness = 0.72
            elif self.style == 'Abyssal':
                chroma = 0.12
                lightness = 0.42
            elif self.style == 'GoldenLava':
                chroma = 0.22
                lightness = 0.60
            elif self.style == 'DeepOcean':
                chroma = 0.15
                lightness = 0.50
            else:  # Ethereal / Dream
                chroma = 0.16
                lightness = 0.78

            a = chroma * math.cos(angle)
            b = chroma * math.sin(angle)
            self.chord_map[root] = (lightness, a, b)

    def get_color(self, root_idx: int, quality: str = 'major') -> Tuple[float, float, str]:
        """
        返回: (hue_deg, saturation_proxy, hex_color)
        """
        if root_idx < 0 or root_idx >= 12:
            return 0.0, 0.0, "#0a0a0c"

        L, a, b = self.chord_map[root_idx]
        
        # 根據和弦性質動態調製知覺明度與色度
        if quality == 'minor':
            L *= 0.82
            a *= 0.75
            b *= 0.75
        elif quality == 'diminished':
            L *= 0.70
            a *= 0.50
            b *= 0.50
        elif quality == 'augmented':
            L = min(0.95, L * 1.15)
            a *= 1.10
            b *= 1.10
        elif quality == 'dominant':
            L = min(0.92, L * 1.05)

        r, g, b_val = oklab_to_srgb(L, a, b)
        hex_color = f"#{r:02x}{g:02x}{b_val:02x}"
        hue_deg = math.degrees(math.atan2(b, a)) % 360.0
        sat_proxy = float(np.clip(math.hypot(a, b) * 3.5, 0.0, 1.0))
        return float(hue_deg), sat_proxy, hex_color

    def get_chord_color(self, root_idx: int, quality_type: str = 'major') -> Tuple[float, float, float]:
        """相容舊版 ProceduralPaletteGenerator 接口: 返回 (hue, saturation, quality_factor)"""
        hue, sat, _ = self.get_color(root_idx, quality_type)
        q_fac = 0.9 if quality_type == 'major' else (0.6 if quality_type == 'minor' else 0.4)
        return hue, sat, q_fac


# 向下相容 Alias
ProceduralPaletteGenerator = AdvancedProceduralPalette


def parse_chord_name(chord_name: str, palette_gen: Optional[AdvancedProceduralPalette] = None) -> Tuple[int, str, float, float, float]:
    """解析和弦字串並映射色彩與品質 (向下相容)"""
    if chord_name == "N.C." or not chord_name:
        return 0, 'major', 0.0, 0.0, 0.5
    
    if chord_name.startswith(tuple(PITCH_CLASSES)):
        if len(chord_name) >= 2 and chord_name[1] == '#':
            root = chord_name[:2]
            quality = chord_name[2:]
        else:
            root = chord_name[:1]
            quality = chord_name[1:]
    else:
        return 0, 'major', 0.0, 0.0, 0.5

    try:
        root_idx = PITCH_CLASSES.index(root)
    except ValueError:
        return 0, 'major', 0.0, 0.0, 0.5
    
    if quality in ('', 'maj'):
        quality_type, default_sat, default_q = 'major', 0.95, 0.8
    elif quality == 'm':
        quality_type, default_sat, default_q = 'minor', 0.45, 0.5
    elif quality == '7':
        quality_type, default_sat, default_q = 'dominant', 0.85, 0.75
    elif quality == 'aug':
        quality_type, default_sat, default_q = 'augmented', 1.0, 0.95
    elif quality == 'dim':
        quality_type, default_sat, default_q = 'diminished', 0.30, 0.35
    else:
        quality_type, default_sat, default_q = 'major', 0.95, 0.8

    if palette_gen is not None:
        hue, sat, _ = palette_gen.get_color(root_idx, quality_type)
        quality_factor = default_q
    else:
        hue = ((root_idx * 7) % 12) * 30.0
        sat = default_sat
        quality_factor = default_q
        
    return root_idx, quality_type, float(hue), float(sat), float(quality_factor)


# =====================================================================
# 2. 專業和弦識別器 (CQT + Extended Templates + Temporal Smooth)
# =====================================================================
class HarmonicChordAnalyzer:
    """採用常數 Q 變換 (CQT) 與多模板比對的和弦引擎，抗打擊噪聲與泛音干擾"""
    def __init__(self):
        self.templates = self._build_templates()

    def _build_templates(self) -> Dict[str, np.ndarray]:
        tmpl = {}
        for i in range(12):
            root = PITCH_CLASSES[i]
            # Major (1, 3, 5)
            maj = np.zeros(12); maj[[i, (i + 4) % 12, (i + 7) % 12]] = [1.0, 0.6, 0.8]
            tmpl[root] = maj / np.linalg.norm(maj)
            # Minor (1, b3, 5)
            min_ = np.zeros(12); min_[[i, (i + 3) % 12, (i + 7) % 12]] = [1.0, 0.6, 0.8]
            tmpl[f"{root}m"] = min_ / np.linalg.norm(min_)
            # Dominant 7th (1, 3, 5, b7)
            dom7 = np.zeros(12); dom7[[i, (i + 4) % 12, (i + 7) % 12, (i + 10) % 12]] = [1.0, 0.5, 0.7, 0.5]
            tmpl[f"{root}7"] = dom7 / np.linalg.norm(dom7)
            # Diminished (1, b3, b5)
            dim = np.zeros(12); dim[[i, (i + 3) % 12, (i + 6) % 12]] = [1.0, 0.6, 0.6]
            tmpl[f"{root}dim"] = dim / np.linalg.norm(dim)
            # Augmented (1, 3, #5)
            aug = np.zeros(12); aug[[i, (i + 4) % 12, (i + 8) % 12]] = [1.0, 0.6, 0.6]
            tmpl[f"{root}aug"] = aug / np.linalg.norm(aug)
        return tmpl

    def analyze(self, y_harmonic: np.ndarray, sr: int, hop_length: int) -> Tuple[List[str], List[str]]:
        """利用 Harmonic 音訊計算 CQT Chroma 並進行滑動中值濾波"""
        try:
            # 優先使用 CQT Chroma (對數音高解析度)
            chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, hop_length=hop_length, n_chroma=12)
        except Exception as e:
            logger.debug(f"CQT Chroma 計算回退至 STFT Chroma: {e}")
            chroma = librosa.feature.chroma_stft(y=y_harmonic, sr=sr, hop_length=hop_length, n_chroma=12)

        # 時間軸滑動中值濾波，消除瞬時雜音
        if chroma.shape[1] >= 5:
            chroma = median_filter(chroma, size=(1, 5))
        
        keys = list(self.templates.keys())
        matrix = np.array([self.templates[k] for k in keys])  # (N_templates, 12)
        
        # 餘弦相似度矩陣點積
        norms = np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-8
        chroma_normed = chroma / norms
        sims = np.dot(matrix, chroma_normed)  # (N_templates, frames)
        
        best_indices = np.argmax(sims, axis=0)
        chord_names = [keys[idx] for idx in best_indices]
        
        # 解析根音與質量
        qualities = []
        for name in chord_names:
            if 'm' in name and 'dim' not in name:
                q = 'minor'
            elif 'dim' in name:
                q = 'diminished'
            elif 'aug' in name:
                q = 'augmented'
            elif '7' in name:
                q = 'dominant'
            else:
                q = 'major'
            qualities.append(q)
            
        return chord_names, qualities


# =====================================================================
# 3. 彈簧式非對稱動態追蹤器 (Attack/Release Envelope Follower)
# =====================================================================
class BallisticFilter:
    """音畫互動必備的非對稱物理動態濾波器 (瞬態疾速觸發，平滑釋放)"""
    def __init__(self, attack_ms: float = 10.0, release_ms: float = 180.0, fps: float = 60.0):
        dt = 1.0 / max(fps, 1.0)
        self.alpha_attack = math.exp(-dt / (max(attack_ms, 1e-3) * 1e-3))
        self.alpha_release = math.exp(-dt / (max(release_ms, 1e-3) * 1e-3))
        self.state = 0.0

    def process(self, target: float) -> float:
        if target > self.state:
            self.state = target + self.alpha_attack * (self.state - target)
        else:
            self.state = target + self.alpha_release * (self.state - target)
        return float(self.state)

    def reset(self, initial_value: float = 0.0):
        self.state = float(initial_value)


# 向下相容之 DampingFilter
class DampingFilter:
    def __init__(self, initial_value: float = 0.0, lambda_attack: float = 15.0, lambda_decay: float = 2.5):
        self.val = initial_value
        self.lambda_attack = lambda_attack
        self.lambda_decay = lambda_decay

    def update(self, target: float, dt: float) -> float:
        lambda_val = self.lambda_attack if target > self.val else self.lambda_decay
        self.val += (target - self.val) * (1.0 - np.exp(-lambda_val * dt))
        return float(self.val)


# =====================================================================
# 4. 強化版離線音訊分析核心 (AudioBeatDetector)
# =====================================================================
class AudioBeatDetector:
    """
    離線音訊分析核心：
    - 動態臨界頻帶 (Hz Masking 解耦採樣率)
    - CQT 諧波和弦識別器 + Oklab 感知調色盤
    - SSM (自我相似矩陣) 結構分鏡切分 + 拍點吸附
    - 全維度向後相容 `filter_dynamics` 與 `storyboard`
    """
    def __init__(self, temp_dir: Optional[str] = None):
        workspace_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
        self.temp_dir = temp_dir or os.path.join(workspace_dir, "temp_audio")
        self.cache_dir = os.path.join(workspace_dir, "assets_cache")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.chord_engine = HarmonicChordAnalyzer()
        self.downloaded_files = []
        self._fingerprint_engine = None

    @property
    def fingerprint_engine(self):
        if self._fingerprint_engine is None:
            try:
                from audio_fingerprint_engine import AudioFingerprintEngine
                self._fingerprint_engine = AudioFingerprintEngine()
            except Exception as e:
                logger.warning(f"AudioFingerprintEngine 延遲加載失敗或跳過: {e}")
                self._fingerprint_engine = False
        return self._fingerprint_engine if self._fingerprint_engine is not False else None

    def is_youtube_url(self, path_or_url: str) -> bool:
        yt_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$'
        return bool(re.match(yt_regex, path_or_url))

    def download_youtube_audio(self, url: str) -> str:
        logger.info(f"Starting YouTube audio download: {url}")
        output_template = os.path.join(self.temp_dir, "%(title)s.%(ext)s")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                base, _ = os.path.splitext(filename)
                audio_path = f"{base}.mp3"
                if os.path.exists(audio_path):
                    self.downloaded_files.append(audio_path)
                    return audio_path
                for file in os.listdir(self.temp_dir):
                    if file.startswith(os.path.basename(base)) and file.endswith('.mp3'):
                        found_path = os.path.join(self.temp_dir, file)
                        self.downloaded_files.append(found_path)
                        return found_path
                raise FileNotFoundError("Could not find downloaded MP3 file.")
        except Exception as e:
            logger.error(f"Failed to download YouTube audio: {e}")
            raise

    def _get_freq_mask(self, n_fft: int, sr: int, low_hz: float, high_hz: float) -> np.ndarray:
        """根據精確赫茲 (Hz) 動態建立 FFT Bin 遮罩，解耦採樣率與解析度"""
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
        return (freqs >= low_hz) & (freqs < high_hz)

    def analyze(self, path_or_url: str, genre: str = 'Auto (自動偵測)') -> dict:
        audio_path = path_or_url
        if self.is_youtube_url(path_or_url):
            audio_path = self.download_youtube_audio(path_or_url)
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file missing: {audio_path}")

        filename = os.path.basename(audio_path)
        mtime = os.path.getmtime(audio_path)
        clean_genre_tag = genre.strip().lower() if genre else 'auto'
        cache_key = hashlib.sha256(f"{audio_path}_{mtime}_v6_priorfix_{clean_genre_tag}".encode('utf-8')).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"audio_v6_{cache_key}.npz")

        # 1. 檢查快取
        if os.path.exists(cache_path):
            try:
                cached = np.load(cache_path, allow_pickle=True)
                logger.info(f"⚡ [Cache Hit] 成功載入現代化音訊分析快取: {filename} (風格: {genre})")
                return cached['result'].item()
            except Exception as e:
                logger.warning(f"快取損毀，重新計算: {e}")

        logger.info(f"🚀 開始高保真前沿音訊分析: {filename} (風格模式: {genre})")

        # 2. 載入音訊 (22050Hz 為音樂資訊檢索標準，兼顧計算效率與瞬態精度)
        sr = 22050
        hop_length = 1024
        n_fft = 2048

        y, _ = librosa.load(audio_path, sr=sr, mono=True)
        y = np.nan_to_num(y, nan=0.0, posinf=1.0, neginf=-1.0)
        duration = float(librosa.get_duration(y=y, sr=sr))

        # 3. 確定性動態調色盤 (Oklab + 五度圈)
        palette = AdvancedProceduralPalette(filename)

        # 4. 節奏與拍點提取 (標準 Librosa 節奏圖追蹤)
        tempo_raw, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
        bpm = float(np.atleast_1d(tempo_raw)[0])
        beat_times = [float(t) for t in librosa.frames_to_time(beats, sr=sr, hop_length=hop_length)]

        # 5. 頻譜與動態頻帶劃分 (精確 Hz 物理掩碼，解耦採樣率)
        S_complex = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
        S_mag = np.abs(S_complex)
        total_energy_raw = np.maximum(np.sum(S_mag, axis=0), 1e-5)

        masks = {
            'sub': self._get_freq_mask(n_fft, sr, 20.0, 60.0),
            'bass': self._get_freq_mask(n_fft, sr, 60.0, 250.0),
            'low_mid': self._get_freq_mask(n_fft, sr, 250.0, 800.0),
            'mid': self._get_freq_mask(n_fft, sr, 800.0, 3000.0),
            'high': self._get_freq_mask(n_fft, sr, 3000.0, sr / 2.0)
        }

        sub_energy = np.sum(S_mag[masks['sub'], :], axis=0) if np.any(masks['sub']) else np.zeros(S_mag.shape[1])
        bass_energy = np.sum(S_mag[masks['bass'], :], axis=0) if np.any(masks['bass']) else np.zeros(S_mag.shape[1])
        mid_energy = np.sum(S_mag[masks['mid'], :], axis=0) if np.any(masks['mid']) else np.zeros(S_mag.shape[1])
        high_energy = np.sum(S_mag[masks['high'], :], axis=0) if np.any(masks['high']) else np.zeros(S_mag.shape[1])
        total_energy_per_frame = total_energy_raw

        # 平滑濾波與標準化
        box = np.ones(5) / 5.0
        sub_norm = np.convolve(sub_energy / (np.max(sub_energy) + 1e-8), box, mode='same')
        bass_norm = np.convolve(bass_energy / (np.max(bass_energy) + 1e-8), box, mode='same')
        mid_norm = np.convolve(mid_energy / (np.max(mid_energy) + 1e-8), box, mode='same')
        high_norm = np.convolve(high_energy / (np.max(high_energy) + 1e-8), box, mode='same')
        total_energy_norm = np.convolve(total_energy_per_frame / (np.max(total_energy_per_frame) + 1e-8), box, mode='same')

        # 6. HPSS 諧波與打擊分離
        y_harm, y_perc = librosa.effects.hpss(y, margin=(1.2, 2.0))
        p_rms = librosa.feature.rms(y=y_perc, frame_length=n_fft, hop_length=hop_length)[0]
        h_rms = librosa.feature.rms(y=y_harm, frame_length=n_fft, hop_length=hop_length)[0]
        p_rms = np.pad(p_rms, (0, max(0, S_mag.shape[1] - len(p_rms))), 'edge')[:S_mag.shape[1]]
        h_rms = np.pad(h_rms, (0, max(0, S_mag.shape[1] - len(h_rms))), 'edge')[:S_mag.shape[1]]
        
        percussive_smooth = np.convolve(p_rms / (np.max(p_rms) + 1e-8), box, mode='same')
        harmonic_smooth = np.convolve(h_rms / (np.max(h_rms) + 1e-8), box, mode='same')

        # 7. CQT 和弦辨識
        raw_chords, chord_qualities = self.chord_engine.analyze(y_harm, sr, hop_length)

        # 8. Oklab 色彩映射
        chord_names, chord_hues, chord_saturations, chord_colors_hex = [], [], [], []
        chord_brightness = []
        for i, chord in enumerate(raw_chords):
            if i >= len(total_energy_norm) or total_energy_norm[i] < 0.04:
                chord_names.append("N.C.")
                chord_hues.append(0.0)
                chord_saturations.append(0.0)
                chord_brightness.append(0.05)
                chord_colors_hex.append("#0a0a0c")
            else:
                root_name = chord[:2] if len(chord) > 1 and chord[1] == '#' else chord[0]
                root_idx = PITCH_CLASSES.index(root_name) if root_name in PITCH_CLASSES else 0
                hue, sat, hex_c = palette.get_color(root_idx, chord_qualities[i])
                chord_names.append(chord)
                chord_hues.append(float(hue))
                chord_saturations.append(float(sat))
                chord_brightness.append(0.85 if chord_qualities[i] == 'major' else 0.65)
                chord_colors_hex.append(hex_c)

        # 9. 64-bin 頻譜下採樣 (供 UI 與波形視覺化使用)
        bins_group = max(1, S_mag.shape[0] // 64)
        S_downsampled = np.array([
            np.convolve(np.log1p((np.mean(S_mag[i*bins_group:(i+1)*bins_group, :], axis=0) * (1.0 + (i / 64.0) * 3.5)) / (np.max(S_mag) + 1e-8) * 9) / np.log1p(9), np.ones(3)/3.0, mode='same')
            for i in range(64)
        ])

        # 10. 聲學物理特性元數據 (Acoustic Meta)
        spectral_centroid_arr = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
        spectral_centroid_mean = float(np.mean(spectral_centroid_arr))
        spectral_flatness_arr = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]
        spectral_flatness_mean = float(np.mean(spectral_flatness_arr))
        zcr_mean = float(np.mean(librosa.feature.zero_crossing_rate(y=y, hop_length=hop_length)))

        # 瞬態擊發率檢測 (Onset Rate - 衡量每秒打擊事件數)
        try:
            onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)
            onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
            onset_rate = float(len(onset_frames) / max(duration, 0.1))
        except Exception:
            onset_rate = 3.0

        # Tempogram 分析 (檢測 Double-time / Half-time，徹底杜絕 DnB/Lo-Fi Octave Error)
        should_half_bpm, should_double_bpm = False, False
        try:
            tempogram = librosa.feature.tempogram(y=y, sr=sr, hop_length=hop_length)
            mean_tg = np.mean(tempogram, axis=1)
            tempo_freqs = librosa.tempo_frequencies(tempogram.shape[0], sr=sr, hop_length=hop_length)
            valid_idx = np.where((tempo_freqs >= 40) & (tempo_freqs <= 240))[0]
            if len(valid_idx) > 0:
                max_tg = np.max(mean_tg[valid_idx]) + 1e-8
                half_target = bpm / 2.0
                if half_target >= 55:
                    half_idx = np.argmin(np.abs(tempo_freqs - half_target))
                    if (mean_tg[half_idx] > 0.45 * max_tg or float(np.mean(percussive_smooth)) < 0.32) and bpm >= 135:
                        should_half_bpm = True
                double_target = bpm * 2.0
                if double_target <= 195:
                    double_idx = np.argmin(np.abs(tempo_freqs - double_target))
                    if 45.0 <= bpm <= 95 and (mean_tg[double_idx] > 0.25 * max_tg or onset_rate >= 3.6 or float(np.mean(percussive_smooth)) > 0.38):
                        should_double_bpm = True
        except Exception as tg_err:
            logger.debug(f"Tempogram 評估略過: {tg_err}")

        # 自適應校準 BPM (消除八度誤差)
        if should_double_bpm:
            logger.info(f"🔄 [MIR Octave Correction] 偵測到半頻誤差 (Half-time: {bpm:.1f} BPM -> 真正速度: {bpm*2.0:.1f} BPM)")
            bpm = bpm * 2.0
        elif should_half_bpm:
            logger.info(f"🔄 [MIR Octave Correction] 偵測到倍頻誤差 (Double-time: {bpm:.1f} BPM -> 真正速度: {bpm/2.0:.1f} BPM)")
            bpm = bpm / 2.0

        acoustic_meta = {
            'total_energy': float(np.mean(total_energy_norm)),
            'percussive': float(np.mean(percussive_smooth)),
            'harmonic': float(np.mean(harmonic_smooth)),
            'bass_ratio': float(np.mean(bass_norm)),
            'spectral_centroid': spectral_centroid_mean,
            'spectral_flatness': spectral_flatness_mean,
            'zcr': zcr_mean,
            'onset_rate': onset_rate,
            'should_half_bpm': should_half_bpm,
            'should_double_bpm': should_double_bpm,
            'is_half_time': should_half_bpm,
            'is_double_time': should_double_bpm
        }

        # 11. 時間軸與完整 filter_dynamics 構建 (完全相容 main.py 渲染管線)
        times = [float(t) for t in librosa.frames_to_time(np.arange(S_mag.shape[1]), sr=sr, hop_length=hop_length)]

        # 構建衍生指標
        silence_fade = [1.0 if e > 0.05 else float(np.clip(e / 0.05, 0.0, 1.0)) for e in total_energy_norm]
        roughness = [float(np.clip(spectral_flatness_arr[min(i, len(spectral_flatness_arr)-1)] * 2.0, 0.0, 1.0)) for i in range(len(times))]
        ethereal_index = [float(np.clip((1.0 - p) * 0.6 + h * 0.4, 0.0, 1.0)) for p, h in zip(percussive_smooth, harmonic_smooth)]
        centroid_norm = [float(np.clip(c / 5000.0, 0.0, 1.0)) for c in spectral_centroid_arr[:len(times)]]
        if len(centroid_norm) < len(times):
            centroid_norm += [0.2] * (len(times) - len(centroid_norm))
        stereo_width = [0.5] * len(times)

        # 12. 風格與情緒遙測 (尊重導演手動指定與自動偵測)
        from audio_fingerprint_engine import normalize_genre_key, get_genre_profile
        detected_telemetry = self.detect_genre_full(bpm, filter_dynamics={}, audio_path=audio_path, acoustic_meta=acoustic_meta)
        
        is_manual_override = genre not in ('Auto (自動偵測)', 'auto', 'Auto', '')
        if is_manual_override:
            resolved_genre_key = normalize_genre_key(genre)
            profile = get_genre_profile(resolved_genre_key)
            genre_telemetry = dict(detected_telemetry)
            genre_telemetry['primary_genre'] = profile['display_name']
            genre_telemetry['genre_key'] = resolved_genre_key
            genre_telemetry['sub_genre'] = profile.get('sub_genre', '')
            genre_telemetry['ballistic'] = profile.get('ballistic', {'attack_ms': 10.0, 'release_ms': 180.0})
            genre_telemetry['valence'] = profile.get('default_valence', detected_telemetry.get('valence', 0.0))
            genre_telemetry['arousal'] = float(np.clip(profile.get('default_arousal', 0.5) * 0.6 + acoustic_meta.get('total_energy', 0.5) * 0.4, 0.05, 0.99))
            genre_telemetry['is_manual_override'] = True
            genre_telemetry['detected_primary_genre'] = detected_telemetry.get('primary_genre', 'Unknown')
        else:
            resolved_genre_key = detected_telemetry.get('genre_key', 'techno')
            genre_telemetry = detected_telemetry
            genre_telemetry['is_manual_override'] = False

        ballistic_cfg = genre_telemetry.get('ballistic', {'attack_ms': 10.0, 'release_ms': 180.0})

        filter_dynamics = {
            'times': times,
            'sub_bass_ratio': [float(v) for v in sub_norm],
            'bass_ratio': [float(v) for v in bass_norm],
            'mid_ratio': [float(v) for v in mid_norm],
            'high_ratio': [float(v) for v in high_norm],
            'sub_bass': [float(v) for v in sub_norm],
            'bass': [float(v) for v in bass_norm],
            'mid': [float(v) for v in mid_norm],
            'high': [float(v) for v in high_norm],
            'bass_energy': [float(v) for v in bass_norm],
            'mid_energy': [float(v) for v in mid_norm],
            'high_energy': [float(v) for v in high_norm],
            'total_energy': [float(v) for v in total_energy_norm],
            'percussive': [float(v) for v in percussive_smooth],
            'harmonic': [float(v) for v in harmonic_smooth],
            'silence_fade': silence_fade,
            'roughness': roughness,
            'ethereal_index': ethereal_index,
            'centroid_norm': centroid_norm,
            'stereo_width': stereo_width,
            'chord_name': chord_names,
            'chord_hue': chord_hues,
            'chord_saturation': chord_saturations,
            'chord_brightness': chord_brightness,
            'chord_color_hex': chord_colors_hex,
            'palette_style': palette.style,
            'palette_base_hue': palette.base_hue,
            'acoustic_meta': acoustic_meta,
            'ballistic_attack_ms': ballistic_cfg.get('attack_ms', 10.0),
            'ballistic_release_ms': ballistic_cfg.get('release_ms', 180.0),
            'resolved_genre': resolved_genre_key
        }

        # 13. 基於 SSM (自我相似矩陣) 的結構分鏡演算法 (曲風感知文法)
        storyboard = self._segment_structure_ssm(
            S_mag=S_mag,
            times=times,
            duration=duration,
            dynamics=filter_dynamics,
            bpm=bpm,
            beat_times=beat_times,
            genre_telemetry=genre_telemetry
        )

        result = {
            'audio_path': audio_path,
            'duration': duration,
            'bpm': bpm,
            'beat_timestamps': beat_times,
            'filter_dynamics': filter_dynamics,
            'spectrum': S_downsampled.tolist(),
            'storyboard': storyboard,
            'palette_style': palette.style,
            'genre': genre_telemetry.get('primary_genre', resolved_genre_key.capitalize()),
            'genre_key': resolved_genre_key,
            'genre_telemetry': genre_telemetry,
            'valence': genre_telemetry.get('valence', 0.0),
            'arousal': genre_telemetry.get('arousal', 0.5),
            'ballistic': ballistic_cfg
        }

        # 寫入快取
        np.savez_compressed(cache_path, result=result)
        return result

        # 寫入快取
        np.savez_compressed(cache_path, result=result)
        return result

    def _segment_structure_ssm(
        self,
        S_mag: np.ndarray,
        times: List[float],
        duration: float,
        dynamics: dict,
        bpm: float,
        beat_times: Optional[List[float]] = None,
        genre_telemetry: Optional[dict] = None
    ) -> List[dict]:
        """
        利用自我相似矩陣 (Self-Similarity Matrix, SSM) 搭配 Foote 棋盤核尋找結構轉折點，
        並進行拍點格線吸附 (Beat Grid Snapping) 與標準分鏡命名。
        """
        if duration <= 6.0 or S_mag.shape[1] < 10:
            return [{
                'start': 0.0,
                'end': round(duration, 3),
                'section': 'Verse',
                'intensity': 0.5,
                'arousal': 0.5,
                'valence': 0.0,
                'style_hint': 'Standard Verse'
            }]

        # 1. 降採樣計算 SSM (Cosine Distance)
        hop = max(1, S_mag.shape[1] // 200)
        power_spec = librosa.power_to_db(S_mag[:, ::hop] + 1e-8)
        mfcc = librosa.feature.mfcc(S=power_spec, n_mfcc=13)
        mfcc_norm = librosa.util.normalize(mfcc, axis=1)
        ssm = np.dot(mfcc_norm.T, mfcc_norm)

        # 2. 計算 Foote Novelty 轉折曲線
        kernel_size = 10
        novelty = np.zeros(ssm.shape[0])
        for i in range(kernel_size, ssm.shape[0] - kernel_size):
            novelty[i] = np.sum(ssm[i-kernel_size:i, i:i+kernel_size]) - np.sum(ssm[i-kernel_size:i, i-kernel_size:i])

        # 3. 尋找轉折峰值
        peaks, _ = signal.find_peaks(-novelty, distance=12)
        step_time = duration / max(ssm.shape[0], 1)
        boundary_times = [0.0] + [float(p * step_time) for p in peaks] + [duration]
        boundary_times = sorted(list(set(boundary_times)))

        # 4. 最短長度約束 (曲風感知自適應時長)
        genre_k = genre_telemetry.get('genre_key', 'techno') if genre_telemetry else 'techno'
        from audio_fingerprint_engine import get_genre_profile
        profile = get_genre_profile(genre_k)
        lexicon = profile.get('lexicon', {})

        if genre_k in ('ambient', 'classical'):
            min_sec_dur = max(7.0, min(18.0, duration / 6.0))
        elif genre_k in ('dub_techno', 'downtempo', 'lo-fi'):
            min_sec_dur = 5.5
        elif genre_k in ('dnb', 'hard_techno', 'idm'):
            min_sec_dur = 3.0
        else:
            min_sec_dur = 4.5

        merged_boundaries = [0.0]
        for b in boundary_times[1:]:
            if b - merged_boundaries[-1] >= min_sec_dur:
                merged_boundaries.append(b)
        if duration - merged_boundaries[-1] < min_sec_dur and len(merged_boundaries) > 1:
            merged_boundaries[-1] = duration
        else:
            if merged_boundaries[-1] < duration:
                merged_boundaries.append(duration)

        # 5. 拍點格線吸附 (Beat Grid Snapping)
        if beat_times and len(beat_times) > 0 and genre_k != 'ambient':
            beats_arr = np.array(beat_times)
            for idx in range(1, len(merged_boundaries) - 1):
                bt = merged_boundaries[idx]
                nearest_idx = np.argmin(np.abs(beats_arr - bt))
                snapped_t = float(beats_arr[nearest_idx])
                if abs(snapped_t - bt) < 1.2 and snapped_t > merged_boundaries[idx - 1] + 2.5:
                    merged_boundaries[idx] = snapped_t

        sections = []
        tot_energy = np.array(dynamics['total_energy'])
        perc_energy = np.array(dynamics['percussive'])
        t_arr = np.array(times)
        display_genre = genre_telemetry.get('primary_genre', 'Electronic') if genre_telemetry else 'Electronic'
        base_valence = genre_telemetry.get('valence', 0.0) if genre_telemetry else 0.0

        for i in range(len(merged_boundaries) - 1):
            st, et = merged_boundaries[i], merged_boundaries[i+1]
            mask = (t_arr >= st) & (t_arr < et)
            mean_e = float(np.mean(tot_energy[mask])) if np.any(mask) else 0.5
            mean_p = float(np.mean(perc_energy[mask])) if np.any(mask) else 0.5

            prog_ratio = st / max(duration, 1e-5)

            if genre_k == 'ambient':
                # Ambient / Drone 專屬文法：無 Drop，呈現長鏡頭冥想與音色綻放
                if prog_ratio < 0.15 and mean_e < 0.45:
                    label = 'Intro'
                    hint = f"{lexicon.get('intro', 'Atmospheric Induction')} ({display_genre})"
                    sec_arousal = min(0.30, mean_e * 0.5)
                    sec_intensity = 0.20
                elif prog_ratio > 0.85 and mean_e < 0.45:
                    label = 'Outro'
                    hint = f"{lexicon.get('outro', 'Infinite Dissolve')} ({display_genre})"
                    sec_arousal = max(0.10, mean_e * 0.3)
                    sec_intensity = 0.15
                elif mean_e > 0.52:
                    label = 'Chorus'
                    hint = f"{lexicon.get('peak', 'Textural Bloom')} ({display_genre})"
                    sec_arousal = np.clip(mean_e * 0.6, 0.35, 0.65)
                    sec_intensity = 0.55
                elif mean_e > 0.35:
                    label = 'Build-up'
                    hint = f"{lexicon.get('build', 'Harmonic Swell')} ({display_genre})"
                    sec_arousal = np.clip(mean_e * 0.5 + 0.15, 0.30, 0.55)
                    sec_intensity = 0.40
                elif mean_e < 0.22:
                    label = 'Bridge'
                    hint = f"{lexicon.get('break', 'Ethereal Void')} ({display_genre})"
                    sec_arousal = 0.20
                    sec_intensity = 0.25
                else:
                    label = 'Verse'
                    hint = f"Ambient Soundscape Drift ({display_genre})"
                    sec_arousal = 0.30
                    sec_intensity = 0.35
            else:
                # 節奏音樂標準文法，結合流派專屬 Lexicon
                if prog_ratio < 0.12 and mean_e < 0.40:
                    label = 'Intro'
                    hint = f"{lexicon.get('intro', 'Atmospheric Intro')} ({display_genre})"
                    sec_arousal = min(0.40, mean_e * 0.6)
                    sec_intensity = 0.25
                elif prog_ratio > 0.88 and mean_e < 0.40:
                    label = 'Outro'
                    hint = f"{lexicon.get('outro', 'Decay / Fadeout Outro')} ({display_genre})"
                    sec_arousal = max(0.15, mean_e * 0.4)
                    sec_intensity = 0.20
                elif mean_e > 0.58 and mean_p > 0.38:
                    label = 'Drop'
                    hint = f"{lexicon.get('peak', 'Peak-Time Drop')} ({display_genre})"
                    sec_arousal = np.clip(mean_e * 0.85 + mean_p * 0.25, 0.75, 1.0)
                    sec_intensity = 1.0
                elif mean_e > 0.42:
                    label = 'Build-up'
                    hint = f"{lexicon.get('build', 'Rising Energy Build-up')} ({display_genre})"
                    sec_arousal = np.clip(mean_e * 0.8 + 0.2, 0.55, 0.85)
                    sec_intensity = 0.75
                elif mean_e < 0.28:
                    label = 'Bridge'
                    hint = f"{lexicon.get('break', 'Melodic Breakdown / Bridge')} ({display_genre})"
                    sec_arousal = np.clip(mean_e * 0.5, 0.25, 0.55)
                    sec_intensity = 0.40
                else:
                    label = 'Verse'
                    hint = f"Melodic Progression ({display_genre})"
                    sec_arousal = np.clip(mean_e * 0.7, 0.35, 0.65)
                    sec_intensity = 0.55

            sections.append({
                'start': round(st, 3),
                'end': round(et, 3),
                'section': label,
                'intensity': round(float(sec_intensity), 3),
                'arousal': round(float(sec_arousal), 3),
                'valence': round(float(base_valence), 3),
                'style_hint': hint
            })

        return sections if sections else [{'start': 0.0, 'end': duration, 'section': 'Verse', 'intensity': 0.5, 'arousal': 0.5, 'valence': 0.0, 'style_hint': 'Normal Verse'}]

    def detect_genre(self, bpm: float, filter_dynamics: dict, audio_path: str = None, acoustic_meta: dict = None) -> str:
        """向下相容的風格偵測函式，直接返回風格 key"""
        telemetry = self.detect_genre_full(bpm, filter_dynamics, audio_path=audio_path, acoustic_meta=acoustic_meta)
        return telemetry.get('genre_key', 'techno')

    def detect_genre_full(self, bpm: float, filter_dynamics: dict, audio_path: str = None, acoustic_meta: dict = None) -> dict:
        """全維度樂曲風格與情緒遙測引擎 (三級漸進式架構)"""
        meta = acoustic_meta or filter_dynamics.get('acoustic_meta', {})
        if not meta:
            percussive = filter_dynamics.get('percussive', [])
            bass_ratio = filter_dynamics.get('bass_ratio', [])
            total_energy = filter_dynamics.get('total_energy', [])
            harmonic = filter_dynamics.get('harmonic', [])
            meta = {
                'percussive': float(np.mean(percussive)) if percussive else 0.4,
                'bass_ratio': float(np.mean(bass_ratio)) if bass_ratio else 0.3,
                'total_energy': float(np.mean(total_energy)) if total_energy else 0.5,
                'harmonic': float(np.mean(harmonic)) if harmonic else 0.4
            }

        # 嘗試從指紋引擎獲取高維語意
        engine = self.fingerprint_engine
        if engine is not None and audio_path and os.path.exists(audio_path):
            try:
                telemetry = engine.classify_genre(audio_path, bpm=bpm, acoustic_meta=meta)
                if telemetry and 'genre_key' in telemetry:
                    return telemetry
            except Exception as fe_err:
                logger.warning(f"指紋引擎風格分類異常，降級至本地聲學分析器: {fe_err}")

        # 本地聲學分類回退
        try:
            from audio_fingerprint_engine import GenreSemanticClassifier
            classifier = GenreSemanticClassifier(clap_model=None)
            dummy_vec = np.zeros(512, dtype=np.float32)
            return classifier.classify_vector(dummy_vec, bpm=bpm, acoustic_meta=meta, audio_path=audio_path)
        except Exception:
            avg_perc = meta.get('percussive', 0.4)
            avg_bass = meta.get('bass_ratio', 0.3)
            avg_energy = meta.get('total_energy', 0.5)

            if bpm >= 155:
                key, name, sub = 'dnb', 'Drum & Bass / Neurofunk', 'High-Energy Neurofunk'
            elif bpm >= 142 and avg_perc > 0.45:
                key, name, sub = 'hardstyle', 'Hardstyle / Hardcore', 'Rawstyle & Hardcore'
            elif 124 <= bpm <= 140 and avg_bass > 0.30:
                key, name, sub = 'techno', 'Techno / Industrial', 'Peak-Time Dark Techno'
            elif 120 <= bpm <= 128 and avg_perc > 0.35:
                key, name, sub = 'house', 'House / Deep House', 'Groovy Club House'
            elif 105 <= bpm <= 125:
                key, name, sub = 'synthwave', 'Synthwave / Retrowave', '80s Outrun & Chillwave'
            elif bpm < 90 and avg_perc < 0.35:
                key, name, sub = 'lo-fi', 'Lo-Fi / Chillhop', 'Dusty Vinyl Chillhop'
            elif avg_perc < 0.25:
                key, name, sub = 'ambient', 'Ambient / Drone', 'Cinematic Soundscape'
            else:
                key, name, sub = 'techno', 'Techno / Industrial', 'Peak-Time Dark Techno'

            return {
                'primary_genre': name,
                'genre_key': key,
                'sub_genre': sub,
                'confidence': 0.75,
                'valence': 0.1,
                'arousal': float(np.clip(avg_energy * 0.7 + avg_perc * 0.3, 0.1, 0.95)),
                'danceability': 0.8,
                'top_candidates': [(name, 0.75)]
            }

    def generate_storyboard(self, duration: float, filter_dynamics: dict, genre: str = 'generic', beat_timestamps: list = None, genre_telemetry: dict = None) -> list:
        """向下相容接口，內部調用先進之 SSM 分割演算法"""
        times = filter_dynamics.get('times', [])
        fake_mag = np.zeros((128, max(len(times), 10)))
        return self._segment_structure_ssm(
            S_mag=fake_mag,
            times=times,
            duration=duration,
            dynamics=filter_dynamics,
            bpm=120.0,
            beat_times=beat_timestamps,
            genre_telemetry=genre_telemetry
        )

    def cleanup(self):
        for file_path in self.downloaded_files:
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception: pass
        self.downloaded_files.clear()


# =====================================================================
# 5. 低延遲即時 DSP 路由處理器 (LiveAudioBeatDetector)
# =====================================================================
class LiveAudioBeatDetector:
    """高精度即時音訊監聽：具備彈簧式動態平滑與即時頻譜解析與和弦估計"""
    def __init__(self, device_index=None, sample_rate: int = 44100, block_size: int = 1024, callback=None):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.callback = callback
        self.audio_queue = queue.Queue(maxsize=16)
        self.is_running = False
        self.worker_thread = None
        self.stream = None
        
        # 非對稱動態濾波器 (Attack 10ms 即時爆發 / Release 180ms 柔和過渡)
        self.sub_filter = BallisticFilter(attack_ms=10, release_ms=150)
        self.bass_filter = BallisticFilter(attack_ms=12, release_ms=180)
        self.mid_filter = BallisticFilter(attack_ms=15, release_ms=200)
        self.high_filter = BallisticFilter(attack_ms=8, release_ms=120)
        
        # 預計算頻段索引遮罩
        freqs = np.fft.rfftfreq(self.block_size, 1.0 / self.sample_rate)
        self.sub_mask = (freqs >= 20) & (freqs < 60)
        self.bass_mask = (freqs >= 60) & (freqs < 250)
        self.mid_mask = (freqs >= 250) & (freqs < 3000)
        self.high_mask = (freqs >= 3000) & (freqs < 16000)

        self.palette = AdvancedProceduralPalette("live_monitor_palette")
        self.latest_status = {
            'sub_bass': 0.0,
            'bass': 0.0,
            'mid': 0.0,
            'high': 0.0,
            'is_silent': True,
            'chord_name': 'N.C.',
            'chord_hue': 180.0,
            'chord_color_hex': '#0a0a0c'
        }

    def audio_callback(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        if self.audio_queue.full():
            try: self.audio_queue.get_nowait()
            except queue.Empty: pass
        self.audio_queue.put(block)

    def start(self):
        if self.is_running: return
        import sounddevice as sd
        self.is_running = True
        self.stream = sd.InputStream(
            device=self.device_index, channels=1, samplerate=self.sample_rate,
            blocksize=self.block_size, callback=self.audio_callback
        )
        self.stream.start()
        self.worker_thread = threading.Thread(target=self._dsp_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.is_running = False
        if self.stream:
            try: self.stream.stop(); self.stream.close()
            except Exception: pass
            self.stream = None
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)
            self.worker_thread = None

    def _dsp_loop(self):
        window = np.hanning(self.block_size)
        while self.is_running:
            try:
                block = self.audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            # 去除直流偏移並加窗
            clean_block = (block - np.mean(block)) * window
            fft_mag = np.abs(np.fft.rfft(clean_block))
            total_power = float(np.sum(fft_mag))

            if total_power < 1e-4:
                self.latest_status['is_silent'] = True
                self.latest_status['sub_bass'] = self.sub_filter.process(0.0)
                self.latest_status['bass'] = self.bass_filter.process(0.0)
                self.latest_status['mid'] = self.mid_filter.process(0.0)
                self.latest_status['high'] = self.high_filter.process(0.0)
                self.latest_status['chord_name'] = 'N.C.'
                self.latest_status['chord_color_hex'] = '#0a0a0c'
                continue

            self.latest_status['is_silent'] = False
            raw_sub = np.mean(fft_mag[self.sub_mask]) if np.any(self.sub_mask) else 0.0
            raw_bass = np.mean(fft_mag[self.bass_mask]) if np.any(self.bass_mask) else 0.0
            raw_mid = np.mean(fft_mag[self.mid_mask]) if np.any(self.mid_mask) else 0.0
            raw_high = np.mean(fft_mag[self.high_mask]) if np.any(self.high_mask) else 0.0

            # 彈簧式非對稱動態平滑
            self.latest_status['sub_bass'] = float(np.clip(self.sub_filter.process(raw_sub * 2.5), 0.0, 1.0))
            self.latest_status['bass'] = float(np.clip(self.bass_filter.process(raw_bass * 2.0), 0.0, 1.0))
            self.latest_status['mid'] = float(np.clip(self.mid_filter.process(raw_mid * 1.8), 0.0, 1.0))
            self.latest_status['high'] = float(np.clip(self.high_filter.process(raw_high * 2.2), 0.0, 1.0))

            # 即時簡易和弦估計
            try:
                chroma_live = librosa.feature.chroma_stft(y=clean_block, sr=self.sample_rate, n_fft=self.block_size, hop_length=self.block_size)
                vec = chroma_live[:, 0]
                vec_norm = np.linalg.norm(vec)
                if vec_norm > 1e-3:
                    best_pitch = int(np.argmax(vec))
                    pitch_name = PITCH_CLASSES[best_pitch]
                    hue, _, hex_c = self.palette.get_color(best_pitch, 'major')
                    self.latest_status['chord_name'] = pitch_name
                    self.latest_status['chord_hue'] = float(hue)
                    self.latest_status['chord_color_hex'] = hex_c
            except Exception:
                pass

    def get_filter_status(self) -> dict:
        return self.latest_status.copy()


# =====================================================================
# 6. 向下相容之 AudioAnalyzer 封裝類 (供 virtual_audio_deck.py 使用)
# =====================================================================
class AudioAnalyzer:
    """提供給 VirtualAudioDeck 等模組使用的物件導向音訊分析包裝器"""
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.detector = AudioBeatDetector()
        self.duration = 0.0
        self.bpm = 120.0
        self.y = np.zeros(0, dtype=np.float32)
        self.sr = 44100
        self.result = {}

    def analyze_full(self) -> dict:
        self.result = self.detector.analyze(self.file_path)
        self.duration = self.result.get('duration', 0.0)
        self.bpm = self.result.get('bpm', 120.0)
        
        # 載入波形以供 virtual_audio_deck 縮圖使用
        try:
            self.y, self.sr = librosa.load(self.file_path, sr=22050, mono=True)
        except Exception:
            self.y = np.zeros(int(self.duration * 22050), dtype=np.float32)
            self.sr = 22050
        return self.result
