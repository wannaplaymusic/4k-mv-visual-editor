import os
import re
import tempfile
import logging
import hashlib
import time
import queue
import threading
import colorsys
import numpy as np
from scipy import signal
import librosa
import yt_dlp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Pitch class names
PITCH_CLASSES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def _get_chord_templates():
    templates = {}
    for i in range(12):
        # Major
        t_maj = np.zeros(12)
        t_maj[i] = 1.0; t_maj[(i + 4) % 12] = 1.0; t_maj[(i + 7) % 12] = 1.0
        templates[PITCH_CLASSES[i]] = t_maj / (np.linalg.norm(t_maj) + 1e-8)
        
        # Minor
        t_min = np.zeros(12)
        t_min[i] = 1.0; t_min[(i + 3) % 12] = 1.0; t_min[(i + 7) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}m"] = t_min / (np.linalg.norm(t_min) + 1e-8)

        # Augmented
        t_aug = np.zeros(12)
        t_aug[i] = 1.0; t_aug[(i + 4) % 12] = 1.0; t_aug[(i + 8) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}aug"] = t_aug / (np.linalg.norm(t_aug) + 1e-8)

        # Diminished
        t_dim = np.zeros(12)
        t_dim[i] = 1.0; t_dim[(i + 3) % 12] = 1.0; t_dim[(i + 6) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}dim"] = t_dim / (np.linalg.norm(t_dim) + 1e-8)
        
    return templates

CHORD_TEMPLATES = _get_chord_templates()

class ProceduralPaletteGenerator:
    """基於檔名與音樂結構的程序化確定性調色盤生成器"""
    def __init__(self, seed_string):
        import random
        if seed_string:
            hash_val = int(hashlib.md5(seed_string.encode('utf-8')).hexdigest(), 16)
            self.rng = random.Random(hash_val)
        else:
            self.rng = random.Random()
            
        self.style = self.rng.choice([
            'Vaporwave', 'Cyberpunk', 'Morandi', 'DeepOcean', 'Forest',
            'Complementary', 'Triadic', 'Tetradic', 'Analogous', 'GoldenLava'
        ])
        
        self.base_hue = self.rng.uniform(0.0, 360.0)
        self.hue_step = self.rng.choice([15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 150.0])
        self.direction = self.rng.choice([1, -1])
        self.sat_base = self.rng.uniform(0.5, 0.9)
        self.bright_base = self.rng.uniform(0.4, 0.7)
        
        self.chroma_colors = {}
        self._generate_chroma_colors()
        
    def _generate_chroma_colors(self):
        for root_idx in range(12):
            fifths_pos = (root_idx * 7) % 12
            
            if self.style == 'Vaporwave':
                h = (240.0 + fifths_pos * 8.33 + self.base_hue) % 360.0
                s = self.rng.uniform(0.65, 0.85)
                q_fac = 0.7
            elif self.style == 'Cyberpunk':
                if fifths_pos % 3 == 0:
                    h = self.rng.uniform(180.0, 200.0)
                elif fifths_pos % 3 == 1:
                    h = self.rng.uniform(300.0, 330.0)
                else:
                    h = self.rng.uniform(50.0, 65.0)
                s = self.rng.uniform(0.85, 1.0)
                q_fac = 0.9
            elif self.style == 'Morandi':
                h = (self.base_hue + fifths_pos * self.hue_step * self.direction) % 360.0
                s = self.rng.uniform(0.25, 0.40)
                q_fac = 0.5
            elif self.style == 'DeepOcean':
                h = (190.0 + fifths_pos * 10.0 + self.base_hue) % 360.0
                s = self.rng.uniform(0.55, 0.75)
                q_fac = 0.6
            elif self.style == 'Forest':
                h = (80.0 + fifths_pos * 8.0 + self.base_hue) % 360.0
                s = self.rng.uniform(0.45, 0.70)
                q_fac = 0.65
            elif self.style == 'GoldenLava':
                h = (10.0 + fifths_pos * 5.0 + self.base_hue) % 360.0
                s = self.rng.uniform(0.75, 0.95)
                q_fac = 0.8
            elif self.style == 'Complementary':
                h = (self.base_hue if fifths_pos % 2 == 0 else self.base_hue + 180.0) % 360.0
                s = self.sat_base
                q_fac = 0.75
            elif self.style == 'Triadic':
                h = (self.base_hue + (fifths_pos % 3) * 120.0) % 360.0
                s = self.sat_base
                q_fac = 0.75
            elif self.style == 'Tetradic':
                h = (self.base_hue + (fifths_pos % 4) * 90.0) % 360.0
                s = self.sat_base
                q_fac = 0.8
            else:
                h = (self.base_hue + fifths_pos * 4.0 * self.direction) % 360.0
                s = self.sat_base
                q_fac = 0.7
                
            self.chroma_colors[root_idx] = (float(h), float(s), float(q_fac))

    def get_chord_color(self, root_idx, quality_type):
        h, s, q_fac = self.chroma_colors.get(root_idx, (0.0, 0.0, 0.5))
        if quality_type == 'major':
            return h, min(1.0, s * 1.1), min(1.0, q_fac * 1.0)
        elif quality_type == 'minor':
            return h, s * 0.75, q_fac * 0.70
        return h, s, q_fac

def parse_chord_name(chord_name, palette_gen=None):
    if chord_name == "N.C.":
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
    
    if quality == '':
        quality_type, default_saturation, default_quality_factor = 'major', 0.95, 0.8
    elif quality == 'm':
        quality_type, default_saturation, default_quality_factor = 'minor', 0.45, 0.5
    elif quality == 'aug':
        quality_type, default_saturation, default_quality_factor = 'augmented', 1.0, 0.95
    elif quality == 'dim':
        quality_type, default_saturation, default_quality_factor = 'diminished', 0.30, 0.35
    else:
        quality_type, default_saturation, default_quality_factor = 'major', 0.95, 0.8

    if palette_gen is not None:
        hue, saturation, quality_factor = palette_gen.get_chord_color(root_idx, quality_type)
    else:
        hue = ((root_idx * 7) % 12) * 30.0
        saturation = default_saturation
        quality_factor = default_quality_factor
        
    return root_idx, quality_type, float(hue), float(saturation), float(quality_factor)

def hsl_to_hex(h_deg, s_pct, l_pct):
    r, g, b = colorsys.hls_to_rgb(float(h_deg) / 360.0, float(l_pct), float(s_pct))
    return f"#{int(r*255.999):02x}{int(g*255.999):02x}{int(b*255.999):02x}"

class AudioBeatDetector:
    """離線音訊分析器：支援多頻段能量提取、和弦分析、三級風格辨識、分鏡排程與 .npz 快取"""
    def __init__(self, temp_dir=None):
        if temp_dir is None:
            workspace_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
            self.temp_dir = os.path.join(workspace_dir, "temp_audio")
        else:
            self.temp_dir = temp_dir
            
        os.makedirs(self.temp_dir, exist_ok=True)
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

    def analyze(self, path_or_url: str, genre: str = 'Auto (自動偵測)'):
        audio_path = path_or_url
        if self.is_youtube_url(path_or_url):
            audio_path = self.download_youtube_audio(path_or_url)
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        filename = os.path.basename(audio_path)
        palette_gen = ProceduralPaletteGenerator(filename)
        
        # 1. 檢查 .npz 快取 (Cache Lookup)
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_cache")
        os.makedirs(cache_dir, exist_ok=True)
        mtime = os.path.getmtime(audio_path) if os.path.exists(audio_path) else 0
        audio_hash = hashlib.md5(f"{audio_path}_{mtime}".encode('utf-8')).hexdigest()
        npz_cache_path = os.path.join(cache_dir, f"audio_feat_{audio_hash}.npz")

        if os.path.exists(npz_cache_path):
            try:
                cached_data = np.load(npz_cache_path, allow_pickle=True)
                analysis_result = cached_data['result'].item()
                logger.info(f"⚡ [Cache Hit] 成功載入音訊分析快取 (.npz): {filename}")
                return analysis_result
            except Exception as cache_err:
                logger.warning(f"快取載入失敗，重新分析: {cache_err}")

        # 2. 執行深度 Librosa 音訊特徵分析
        logger.info(f"Analyzing audio: {audio_path} under genre mode: {genre}")
        try:
            y, sr = librosa.load(audio_path, sr=22050)
            y = np.nan_to_num(y, nan=0.0, posinf=1.0, neginf=-1.0)
            duration = float(librosa.get_duration(y=y, sr=sr))
            
            tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo_raw[0]) if hasattr(tempo_raw, '__len__') and len(tempo_raw) > 0 else float(tempo_raw)
            raw_beat_timestamps = [float(t) for t in librosa.frames_to_time(beat_frames, sr=sr)]
            
            S_full = np.abs(librosa.stft(y, n_fft=2048, hop_length=1024))
            total_energy_per_frame = np.maximum(np.sum(S_full, axis=0), 1e-5)
            
            # 頻段分離
            sub_bass_energy = np.sum(S_full[0:6, :], axis=0)       # 0 - 64 Hz
            bass_energy = np.sum(S_full[6:23, :], axis=0)          # 64 - 250 Hz
            mid_energy = np.sum(S_full[23:186, :], axis=0)        # 250 - 2000 Hz
            high_energy = np.sum(S_full[186:, :], axis=0)         # 2000 - 11025 Hz
            
            box = np.ones(5) / 5.0
            times = librosa.frames_to_time(np.arange(len(total_energy_per_frame)), sr=sr, hop_length=1024)
            
            sub_bass_norm = np.convolve(sub_bass_energy / (np.max(sub_bass_energy) + 1e-8), box, mode='same')
            bass_norm = np.convolve(bass_energy / (np.max(bass_energy) + 1e-8), box, mode='same')
            mid_norm = np.convolve(mid_energy / (np.max(mid_energy) + 1e-8), box, mode='same')
            high_norm = np.convolve(high_energy / (np.max(high_energy) + 1e-8), box, mode='same')
            total_energy_norm = np.convolve(total_energy_per_frame / (np.max(total_energy_per_frame) + 1e-8), box, mode='same')
            
            # HPSS 與瞬態
            y_harmonic, y_percussive = librosa.effects.hpss(y)
            rmse_p = librosa.feature.rms(y=y_percussive, frame_length=2048, hop_length=1024)[0]
            rmse_h = librosa.feature.rms(y=y_harmonic, frame_length=2048, hop_length=1024)[0]
            rmse_p = np.pad(rmse_p, (0, max(0, S_full.shape[1] - len(rmse_p))), 'edge')[:S_full.shape[1]]
            rmse_h = np.pad(rmse_h, (0, max(0, S_full.shape[1] - len(rmse_h))), 'edge')[:S_full.shape[1]]
            
            percussive_smooth = np.convolve(rmse_p / (np.max(rmse_p) + 1e-8), box, mode='same')
            harmonic_smooth = np.convolve(rmse_h / (np.max(rmse_h) + 1e-8), box, mode='same')
            
            # 和弦辨識
            chroma_stft = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=2048, hop_length=1024)
            chroma_stft = np.pad(chroma_stft, ((0, 0), (0, max(0, S_full.shape[1] - chroma_stft.shape[1]))), 'edge')[:, :S_full.shape[1]]
            chroma_smooth = np.array([np.convolve(chroma_stft[c_idx, :], np.ones(3)/3.0, mode='same') for c_idx in range(12)])
            
            chord_names, chord_hues, chord_saturations, chord_colors_hex = [], [], [], []
            for f in range(S_full.shape[1]):
                chroma_vec = chroma_smooth[:, f]
                vec_norm = np.linalg.norm(chroma_vec)
                if vec_norm < 1e-4 or total_energy_per_frame[f] < (np.max(total_energy_per_frame) * 0.005):
                    chord_names.append("N.C.")
                    chord_hues.append(0.0)
                    chord_saturations.append(0.0)
                    chord_colors_hex.append("#0a0a0c")
                else:
                    best_chord = max(CHORD_TEMPLATES, key=lambda name: np.dot(chroma_vec / vec_norm, CHORD_TEMPLATES[name]))
                    root_idx, q_type, hue, sat, q_factor = parse_chord_name(best_chord, palette_gen)
                    chord_names.append(best_chord)
                    chord_hues.append(float(hue))
                    chord_saturations.append(float(sat))
                    chord_colors_hex.append(hsl_to_hex(float(hue), float(sat), float(q_factor * 0.5)))
            
            # 64-bin 頻譜下採樣
            bins_group = S_full.shape[0] // 64
            S_downsampled = np.array([
                np.convolve(np.log1p((np.mean(S_full[i*bins_group:(i+1)*bins_group, :], axis=0) * (1.0 + (i / 64.0) * 3.5)) / (np.max(S_full) + 1e-8) * 9) / np.log1p(9), np.ones(3)/3.0, mode='same')
                for i in range(64)
            ])

            # 提取物理音色與諧波/打擊特徵 (Tier 0 DSP)
            spectral_centroid_arr = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_centroid_mean = float(np.mean(spectral_centroid_arr))
            spectral_flatness_arr = librosa.feature.spectral_flatness(y=y)[0]
            spectral_flatness_mean = float(np.mean(spectral_flatness_arr))
            zcr_mean = float(np.mean(librosa.feature.zero_crossing_rate(y=y)))
            
            # Tempogram 節奏圖分析：檢測 Double-time / Half-time 律動
            is_half_time = False
            is_double_time = False
            try:
                tempogram = librosa.feature.tempogram(y=y, sr=sr, hop_length=1024)
                mean_tg = np.mean(tempogram, axis=1)
                tempo_freqs = librosa.tempo_frequencies(tempogram.shape[0], sr=sr, hop_length=1024)
                valid_idx = np.where((tempo_freqs >= 40) & (tempo_freqs <= 240))[0]
                if len(valid_idx) > 0:
                    half_target = bpm / 2.0
                    if half_target >= 55:
                        half_idx = np.argmin(np.abs(tempo_freqs - half_target))
                        if mean_tg[half_idx] > 0.75 * np.max(mean_tg[valid_idx]) and bpm >= 130:
                            is_half_time = True
                    double_target = bpm * 2.0
                    if double_target <= 190:
                        double_idx = np.argmin(np.abs(tempo_freqs - double_target))
                        if mean_tg[double_idx] > 0.75 * np.max(mean_tg[valid_idx]) and bpm <= 90:
                            is_double_time = True
            except Exception as tg_err:
                logger.debug(f"Tempogram 評估跳過: {tg_err}")

            acoustic_meta = {
                'total_energy': float(np.mean(total_energy_norm)),
                'percussive': float(np.mean(percussive_smooth)),
                'harmonic': float(np.mean(harmonic_smooth)),
                'bass_ratio': float(np.mean(bass_norm)),
                'spectral_centroid': spectral_centroid_mean,
                'spectral_flatness': spectral_flatness_mean,
                'zcr': zcr_mean,
                'is_half_time': is_half_time,
                'is_double_time': is_double_time
            }

            filter_dynamics = {
                'times': [float(t) for t in times],
                'sub_bass_ratio': [float(v) for v in sub_bass_norm],
                'bass_ratio': [float(v) for v in bass_norm],
                'mid_ratio': [float(v) for v in mid_norm],
                'high_ratio': [float(v) for v in high_norm],
                'bass_energy': [float(v) for v in bass_norm],
                'mid_energy': [float(v) for v in mid_norm],
                'high_energy': [float(v) for v in high_norm],
                'total_energy': [float(v) for v in total_energy_norm],
                'percussive': [float(v) for v in percussive_smooth],
                'harmonic': [float(v) for v in harmonic_smooth],
                'chord_name': chord_names,
                'chord_hue': chord_hues,
                'chord_saturation': chord_saturations,
                'chord_color_hex': chord_colors_hex,
                'palette_style': palette_gen.style,
                'palette_base_hue': palette_gen.base_hue,
                'acoustic_meta': acoustic_meta
            }

            genre_telemetry = self.detect_genre_full(bpm, filter_dynamics, audio_path=audio_path, acoustic_meta=acoustic_meta)
            resolved_genre = genre_telemetry['genre_key'] if genre in ('Auto (自動偵測)', 'auto') else genre.lower().replace(' ', '_')
            storyboard = self.generate_storyboard(duration, filter_dynamics, resolved_genre, beat_timestamps=raw_beat_timestamps, genre_telemetry=genre_telemetry)
            
            result = {
                'audio_path': audio_path,
                'bpm': bpm,
                'beat_timestamps': raw_beat_timestamps,
                'duration': duration,
                'filter_dynamics': filter_dynamics,
                'spectrum': S_downsampled.tolist(),
                'storyboard': storyboard,
                'genre': genre_telemetry.get('primary_genre', resolved_genre.capitalize()),
                'genre_key': resolved_genre,
                'genre_telemetry': genre_telemetry,
                'valence': genre_telemetry.get('valence', 0.0),
                'arousal': genre_telemetry.get('arousal', 0.5)
            }
            
            # 寫入 .npz 快取
            np.savez_compressed(npz_cache_path, result=result)
            return result
            
        except Exception as e:
            logger.error(f"音訊分析失敗: {e}")
            raise

    def detect_genre(self, bpm: float, filter_dynamics: dict, audio_path: str = None, acoustic_meta: dict = None) -> str:
        """
        向下相容的風格偵測函式，直接返回風格關鍵字 (如 'techno', 'synthwave', 'lo-fi')
        """
        telemetry = self.detect_genre_full(bpm, filter_dynamics, audio_path=audio_path, acoustic_meta=acoustic_meta)
        return telemetry.get('genre_key', 'techno')

    def detect_genre_full(self, bpm: float, filter_dynamics: dict, audio_path: str = None, acoustic_meta: dict = None) -> dict:
        """
        全維度樂曲風格與情緒遙測引擎 (三級漸進式架構)
        - 優先呼叫 AudioFingerprintEngine (CLAP 語意或 512D 聲學流形)
        - 若無外部引擎，無縫執行 Tier 0 + Tier 1 物理啟發式流形分析
        """
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

        # 嘗試從指紋引擎獲取高維語意/聲學流形
        engine = self.fingerprint_engine
        if engine is not None and audio_path and os.path.exists(audio_path):
            try:
                telemetry = engine.classify_genre(audio_path, bpm=bpm, acoustic_meta=meta)
                if telemetry and 'genre_key' in telemetry:
                    return telemetry
            except Exception as fe_err:
                logger.warning(f"指紋引擎風格分類異常，降級至本機聲學分析器: {fe_err}")

        # Tier 0/1 本地聲學流形打分回退
        try:
            from audio_fingerprint_engine import GenreSemanticClassifier
            classifier = GenreSemanticClassifier(clap_model=None)
            dummy_vec = np.zeros(512, dtype=np.float32)
            return classifier.classify_vector(dummy_vec, bpm=bpm, acoustic_meta=meta)
        except Exception:
            # 絕對安全保底：增強型啟發式
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
        times = np.array(filter_dynamics['times'])
        if len(times) == 0:
            return [{'start': 0.0, 'end': duration, 'section': 'Verse', 'arousal': 0.5, 'valence': 0.0, 'intensity': 0.5, 'style_hint': 'Normal Verse'}]
            
        total_energy = np.array(filter_dynamics.get('total_energy', [0.0] * len(times)))
        percussive = np.array(filter_dynamics.get('percussive', [0.0] * len(times)))
        harmonic = np.array(filter_dynamics.get('harmonic', [0.0] * len(times)))
        
        # 1. 寬視窗平滑化 (Temporal Window Smoothing - ~3 秒移動平均以消除高頻微抖動)
        win_size = max(5, int(3.0 / ((times[1] - times[0]) if len(times) > 1 else 0.046)))
        if win_size % 2 == 0:
            win_size += 1
        kernel = np.ones(win_size) / win_size
        smooth_energy = np.convolve(total_energy, kernel, mode='same')
        smooth_perc = np.convolve(percussive, kernel, mode='same')
        smooth_harm = np.convolve(harmonic, kernel, mode='same')
        
        # 2. 初始樂段狀態指派 (Initial Section State Classification)
        raw_sections = []
        for i, t in enumerate(times):
            ratio = t / duration if duration > 0 else 0.0
            p_v, t_e = smooth_perc[i], smooth_energy[i]
            
            if ratio < 0.07:
                sec = 'Intro'
            elif ratio > 0.93:
                sec = 'Outro'
            elif t_e > 0.58 and p_v > 0.38:
                sec = 'Drop'
            elif t_e > 0.40:
                sec = 'Build-up'
            elif t_e > 0.22:
                sec = 'Verse'
            else:
                sec = 'Bridge'
            raw_sections.append(sec)
            
        # 3. 初始段落合併 (Initial Run-Length Merging)
        initial_merged = []
        curr_sec, start_t = raw_sections[0], times[0]
        for i in range(1, len(times)):
            if raw_sections[i] != curr_sec:
                initial_merged.append({'start': float(start_t), 'end': float(times[i]), 'section': curr_sec})
                curr_sec, start_t = raw_sections[i], times[i]
        initial_merged.append({'start': float(start_t), 'end': float(duration), 'section': curr_sec})
        
        # 4. 最短段落長度約束 (Minimum Section Duration Constraint: 至少 5.0 秒，消除微片段)
        min_sec_dur = 5.0
        cleaned_sections = []
        for seg in initial_merged:
            dur = seg['end'] - seg['start']
            if not cleaned_sections:
                cleaned_sections.append(seg)
            else:
                if dur < min_sec_dur:
                    cleaned_sections[-1]['end'] = seg['end']
                else:
                    if cleaned_sections[-1]['section'] == seg['section']:
                        cleaned_sections[-1]['end'] = seg['end']
                    else:
                        cleaned_sections.append(seg)
                        
        if cleaned_sections:
            cleaned_sections[-1]['end'] = float(duration)
            
        # 5. 拍點對齊 (Beat Grid Snapping) - 若有拍點數據，將分鏡邊界貼齊至最接近的拍點
        if beat_timestamps and len(beat_timestamps) > 0:
            beats_arr = np.array(beat_timestamps)
            for idx in range(1, len(cleaned_sections)):
                boundary_t = cleaned_sections[idx]['start']
                nearest_idx = np.argmin(np.abs(beats_arr - boundary_t))
                snapped_t = float(beats_arr[nearest_idx])
                if abs(snapped_t - boundary_t) < 1.2 and snapped_t > cleaned_sections[idx - 1]['start'] + 2.0:
                    cleaned_sections[idx - 1]['end'] = snapped_t
                    cleaned_sections[idx]['start'] = snapped_t

        # 6. 時序動態風格與喚醒度調製 (Sectional Style & Arousal Modulation)
        base_valence = genre_telemetry.get('valence', 0.0) if genre_telemetry else 0.0
        display_genre = genre_telemetry.get('primary_genre', genre.capitalize()) if genre_telemetry else genre.capitalize()
        
        for seg in cleaned_sections:
            # 獲取該樂段的時間視窗掩碼
            s_t, e_t = seg['start'], seg['end']
            mask = (times >= s_t) & (times <= e_t)
            if np.any(mask):
                local_energy = float(np.mean(smooth_energy[mask]))
                local_perc = float(np.mean(smooth_perc[mask]))
                local_harm = float(np.mean(smooth_harm[mask]))
            else:
                local_energy, local_perc, local_harm = 0.5, 0.4, 0.4
                
            sec_type = seg['section']
            if sec_type == 'Intro':
                sec_arousal = min(0.40, local_energy * 0.6)
                sec_intensity = 0.25
                hint = f"Atmospheric / Ambient Intro ({display_genre})"
            elif sec_type == 'Build-up':
                sec_arousal = np.clip(local_energy * 0.8 + 0.2, 0.55, 0.85)
                sec_intensity = 0.75
                hint = f"Rising Energy Build-up ({display_genre})"
            elif sec_type == 'Drop':
                sec_arousal = np.clip(local_energy * 0.9 + local_perc * 0.2, 0.80, 1.0)
                sec_intensity = 1.0
                hint = f"Peak-Time Energy Drop ({display_genre})"
            elif sec_type == 'Bridge':
                sec_arousal = np.clip(local_energy * 0.5, 0.25, 0.55)
                sec_intensity = 0.40
                hint = f"Melodic Breakdown / Bridge ({display_genre})"
            elif sec_type == 'Outro':
                sec_arousal = max(0.15, local_energy * 0.4)
                sec_intensity = 0.20
                hint = f"Decay / Fadeout Outro ({display_genre})"
            else:
                sec_arousal = np.clip(local_energy * 0.7, 0.35, 0.65)
                sec_intensity = 0.55
                hint = f"Melodic Progression ({display_genre})"
                
            seg['arousal'] = round(float(sec_arousal), 3)
            seg['valence'] = round(float(base_valence), 3)
            seg['intensity'] = round(float(sec_intensity), 3)
            seg['style_hint'] = hint

        return cleaned_sections


    def cleanup(self):
        for file_path in self.downloaded_files:
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception: pass
        self.downloaded_files.clear()


class LiveAudioBeatDetector:
    """實時音訊輸入監聽與 DSP 能量路由器"""
    def __init__(self, device_index=None, sample_rate=22050, block_size=1024, callback=None):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.callback = callback
        
        self.is_running = False
        self.audio_queue = queue.Queue()
        self.worker_thread = None
        self.stream = None
        
        self.live_sub_bass = 0.0
        self.live_bass = 0.0
        self.live_mid = 0.0
        self.live_high = 0.0
        self.live_spectrum = np.zeros(64)
        self.is_silent_signal = True

    def audio_callback(self, indata, frames, time_info, status):
        block = indata[:, 0].copy()
        if self.audio_queue.qsize() > 10:
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
        self.worker_thread = threading.Thread(target=self._process_loop, daemon=True)
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

    def _process_loop(self):
        while self.is_running:
            try:
                block = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
                
            block = block - np.mean(block)
            fft_vals = np.abs(np.fft.rfft(block))
            tot = np.sum(fft_vals)
            
            if tot > 0.05:
                self.is_silent_signal = False
                sb = np.sum(fft_vals[1:3]) / (tot + 1e-8)
                b = np.sum(fft_vals[3:12]) / (tot + 1e-8)
                m = np.sum(fft_vals[12:93]) / (tot + 1e-8)
                h = np.sum(fft_vals[93:]) / (tot + 1e-8)
                
                self.live_sub_bass = 0.8 * self.live_sub_bass + 0.2 * np.clip(sb * 4.0, 0, 1)
                self.live_bass = 0.8 * self.live_bass + 0.2 * np.clip(b * 3.0, 0, 1)
                self.live_mid = 0.8 * self.live_mid + 0.2 * np.clip(m * 2.5, 0, 1)
                self.live_high = 0.8 * self.live_high + 0.2 * np.clip(h * 3.0, 0, 1)
            else:
                self.is_silent_signal = True
                self.live_sub_bass *= 0.85
                self.live_bass *= 0.85
                self.live_mid *= 0.85
                self.live_high *= 0.85

    def get_filter_status(self):
        return {
            'sub_bass': float(self.live_sub_bass),
            'bass': float(self.live_bass),
            'mid': float(self.live_mid),
            'high': float(self.live_high),
            'is_silent': self.is_silent_signal,
            'chord_name': 'N.C.',
            'chord_hue': 180.0,
            'chord_color_hex': '#0a0a0c'
        }
