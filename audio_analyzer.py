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
    """離線音訊分析器：支援多頻段能量提取、和弦分析、分鏡排程與 .npz 快取"""
    def __init__(self, temp_dir=None):
        if temp_dir is None:
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in locals() else os.getcwd()
            self.temp_dir = os.path.join(workspace_dir, "temp_audio")
        else:
            self.temp_dir = temp_dir
            
        os.makedirs(self.temp_dir, exist_ok=True)
        self.downloaded_files = []

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
                'palette_base_hue': palette_gen.base_hue
            }

            resolved_genre = self.detect_genre(bpm, filter_dynamics) if genre in ('Auto (自動偵測)', 'auto') else genre.lower().replace(' ', '_')
            storyboard = self.generate_storyboard(duration, filter_dynamics, resolved_genre, beat_timestamps=raw_beat_timestamps)
            
            result = {
                'audio_path': audio_path,
                'bpm': bpm,
                'beat_timestamps': raw_beat_timestamps,
                'duration': duration,
                'filter_dynamics': filter_dynamics,
                'spectrum': S_downsampled.tolist(),
                'storyboard': storyboard,
                'genre': resolved_genre.capitalize()
            }
            
            # 寫入 .npz 快取
            np.savez_compressed(npz_cache_path, result=result)
            return result
            
        except Exception as e:
            logger.error(f"音訊分析失敗: {e}")
            raise

    def detect_genre(self, bpm: float, filter_dynamics: dict) -> str:
        percussive = filter_dynamics.get('percussive', [])
        bass_ratio = filter_dynamics.get('bass_ratio', [])
        avg_perc = float(np.mean(percussive)) if percussive else 0.0
        avg_bass = float(np.mean(bass_ratio)) if bass_ratio else 0.0

        if bpm >= 138 and avg_perc > 0.45: return 'hard_techno'
        if bpm >= 150: return 'dnb'
        if 115 <= bpm <= 135 and avg_bass > 0.35: return 'techno'
        if bpm < 95: return 'lo-fi'
        return 'ambient' if avg_perc < 0.25 else 'generic'

    def generate_storyboard(self, duration: float, filter_dynamics: dict, genre: str = 'generic', beat_timestamps: list = None) -> list:
        times = np.array(filter_dynamics['times'])
        if len(times) == 0:
            return [{'start': 0.0, 'end': duration, 'section': 'Verse'}]
            
        total_energy = np.array(filter_dynamics.get('total_energy', [0.0] * len(times)))
        percussive = np.array(filter_dynamics.get('percussive', [0.0] * len(times)))
        
        # 1. 寬視窗平滑化 (Temporal Window Smoothing - ~3 秒移動平均以消除高頻微抖動)
        win_size = max(5, int(3.0 / ((times[1] - times[0]) if len(times) > 1 else 0.046)))
        if win_size % 2 == 0:
            win_size += 1
        kernel = np.ones(win_size) / win_size
        smooth_energy = np.convolve(total_energy, kernel, mode='same')
        smooth_perc = np.convolve(percussive, kernel, mode='same')
        
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
                    # 過短片段併入前一段落
                    cleaned_sections[-1]['end'] = seg['end']
                else:
                    if cleaned_sections[-1]['section'] == seg['section']:
                        cleaned_sections[-1]['end'] = seg['end']
                    else:
                        cleaned_sections.append(seg)
                        
        # 再次確認最後一個段落覆蓋至 duration
        if cleaned_sections:
            cleaned_sections[-1]['end'] = float(duration)
            
        # 5. 拍點對齊 (Beat Grid Snapping) - 若有拍點數據，將分鏡邊界貼齊至最接近的拍點
        if beat_timestamps and len(beat_timestamps) > 0:
            beats_arr = np.array(beat_timestamps)
            for idx in range(1, len(cleaned_sections)):
                boundary_t = cleaned_sections[idx]['start']
                # 尋找最近拍點
                nearest_idx = np.argmin(np.abs(beats_arr - boundary_t))
                snapped_t = float(beats_arr[nearest_idx])
                # 僅在偏移小於 1.2 秒時貼齊，避免過大偏位
                if abs(snapped_t - boundary_t) < 1.2 and snapped_t > cleaned_sections[idx - 1]['start'] + 2.0:
                    cleaned_sections[idx - 1]['end'] = snapped_t
                    cleaned_sections[idx]['start'] = snapped_t
                    
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
