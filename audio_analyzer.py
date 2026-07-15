import os
import re
import tempfile
import logging
import librosa
import yt_dlp
import numpy as np
import sounddevice as sd
import time
import queue
import threading
from scipy import signal

import colorsys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Pitch class names
PITCH_CLASSES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def _get_chord_templates():
    templates = {}
    for i in range(12):
        template = np.zeros(12)
        template[i] = 1.0
        template[(i + 4) % 12] = 1.0
        template[(i + 7) % 12] = 1.0
        templates[PITCH_CLASSES[i]] = template / (np.linalg.norm(template) + 1e-8)
        
    for i in range(12):
        template = np.zeros(12)
        template[i] = 1.0
        template[(i + 3) % 12] = 1.0
        template[(i + 7) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}m"] = template / (np.linalg.norm(template) + 1e-8)

    for i in range(12):
        template = np.zeros(12)
        template[i] = 1.0
        template[(i + 4) % 12] = 1.0
        template[(i + 8) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}aug"] = template / (np.linalg.norm(template) + 1e-8)

    for i in range(12):
        template = np.zeros(12)
        template[i] = 1.0
        template[(i + 3) % 12] = 1.0
        template[(i + 6) % 12] = 1.0
        templates[f"{PITCH_CLASSES[i]}dim"] = template / (np.linalg.norm(template) + 1e-8)
        
    return templates

CHORD_TEMPLATES = _get_chord_templates()

def parse_chord_name(chord_name):
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
    
    fifths_pos = (root_idx * 7) % 12
    hue = fifths_pos * 30
    
    if quality == '':
        quality_type = 'major'
        saturation = 0.95
        quality_factor = 0.8
    elif quality == 'm':
        quality_type = 'minor'
        saturation = 0.45
        quality_factor = 0.5
    elif quality == 'aug':
        quality_type = 'augmented'
        saturation = 1.0
        quality_factor = 0.95
    elif quality == 'dim':
        quality_type = 'diminished'
        saturation = 0.30
        quality_factor = 0.35
    else:
        quality_type = 'major'
        saturation = 0.95
        quality_factor = 0.8
        
    return root_idx, quality_type, float(hue), float(saturation), float(quality_factor)

def hsl_to_hex(h_deg, s_pct, l_pct):
    r, g, b = colorsys.hls_to_rgb(float(h_deg) / 360.0, float(l_pct), float(s_pct))
    return f"#{int(r*255.999):02x}{int(g*255.999):02x}{int(b*255.999):02x}"

class AudioBeatDetector:
    """Analyzes local or YouTube audio sources to detect tempo (BPM) and beat timestamps."""
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
                    logger.info(f"Successfully downloaded and converted YouTube audio: {audio_path}")
                    self.downloaded_files.append(audio_path)
                    return audio_path
                else:
                    for file in os.listdir(self.temp_dir):
                        if file.startswith(os.path.basename(base)) and file.endswith('.mp3'):
                            found_path = os.path.join(self.temp_dir, file)
                            logger.info(f"Found converted audio at: {found_path}")
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
            
        logger.info(f"Analyzing audio: {audio_path} under genre mode: {genre}")
        
        try:
            y, sr = librosa.load(audio_path, sr=22050)
            duration = librosa.get_duration(y=y, sr=sr)
            
            logger.info("Detecting tempo and beats...")
            tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo_raw[0]) if hasattr(tempo_raw, '__len__') and len(tempo_raw) > 0 else float(tempo_raw)
            raw_beat_timestamps = [float(t) for t in librosa.frames_to_time(beat_frames, sr=sr)]
            
            logger.info(f"Estimated raw BPM: {bpm:.2f}. Raw beats: {len(raw_beat_timestamps)}")
            
            # Extract mid-high transients env
            S_trans = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
            low_cutoff_bin = int(150.0 / (sr / 2.0) * S_trans.shape[0])
            S_mid_high = S_trans.copy()
            S_mid_high[:low_cutoff_bin, :] = 0.0
            onset_env = librosa.onset.onset_strength(S=S_mid_high, sr=sr, hop_length=512)
            
            # Analyze filters & dynamics
            S = np.abs(librosa.stft(y, n_fft=2048, hop_length=1024))
            total_energy_per_frame = np.maximum(np.sum(S, axis=0), 1e-5)
            low_energy_per_frame = np.sum(S[:15, :], axis=0)
            high_energy_per_frame = np.sum(S[280:, :], axis=0)
            
            low_ratio = low_energy_per_frame / total_energy_per_frame
            high_ratio = high_energy_per_frame / total_energy_per_frame
            
            active_frames = total_energy_per_frame > (np.max(total_energy_per_frame) * 0.01)
            base_low_ratio = max(0.10, np.median(low_ratio[active_frames]) if np.sum(active_frames) > 0 else 0.25)
            base_high_ratio = max(0.03, np.median(high_ratio[active_frames]) if np.sum(active_frames) > 0 else 0.10)
            
            lp_intensity = np.clip((base_high_ratio * 0.20 - high_ratio) / (base_high_ratio * 0.20), 0, 1)
            hp_intensity = np.clip((base_low_ratio * 0.20 - low_ratio) / (base_low_ratio * 0.20), 0, 1)
            
            silent_frames = total_energy_per_frame < (np.max(total_energy_per_frame) * 0.01)
            lp_intensity[silent_frames] = 0.0
            hp_intensity[silent_frames] = 0.0
            
            times = librosa.frames_to_time(np.arange(len(total_energy_per_frame)), sr=sr, hop_length=1024)
            box = np.ones(5) / 5.0
            lp_smooth = np.convolve(lp_intensity, box, mode='same')
            hp_smooth = np.convolve(hp_intensity, box, mode='same')
            
            # Silence Fade
            dt = 1024.0 / 22050.0
            alpha_step = dt / 0.5
            silence_fade_alpha = np.zeros(len(silent_frames))
            curr_alpha = 0.0
            for f in range(len(silent_frames)):
                curr_alpha = min(1.0, curr_alpha + alpha_step) if silent_frames[f] else max(0.0, curr_alpha - alpha_step)
                silence_fade_alpha[f] = curr_alpha
            
            # Centroids & EAI
            freqs = np.arange(S.shape[0]) * (sr / 2.0 / S.shape[0])
            centroids_smooth = np.convolve(np.sum(freqs[:, np.newaxis] * S, axis=0) / (total_energy_per_frame + 1e-8), box, mode='same')
            
            flux_offline = np.zeros(S.shape[1])
            flux_offline[1:] = np.sum(np.maximum(0.0, S[:, 1:] - S[:, :-1]), axis=0)
            ethereal_idx = (1.0 - np.clip(low_ratio / 0.35, 0, 1)) * np.clip((np.sum(S[140:, :], axis=0) / total_energy_per_frame) / 0.05, 0, 1) * (1.0 - np.clip((flux_offline / (np.max(flux_offline) + 1e-8)) / 0.15, 0, 1))
            ethereal_smooth = np.convolve(ethereal_idx, box, mode='same')
            ethereal_smooth[silent_frames] = 0.0
            
            # HPSS
            try:
                y_harmonic, y_percussive = librosa.effects.hpss(y)
                rmse_p = librosa.feature.rms(y=y_percussive, frame_length=2048, hop_length=1024)[0]
                rmse_h = librosa.feature.rms(y=y_harmonic, frame_length=2048, hop_length=1024)[0]
                rmse_p = np.pad(rmse_p, (0, max(0, S.shape[1] - len(rmse_p))), 'edge')[:S.shape[1]]
                rmse_h = np.pad(rmse_h, (0, max(0, S.shape[1] - len(rmse_h))), 'edge')[:S.shape[1]]
                percussive_smooth = np.convolve(rmse_p / (np.max(rmse_p) + 1e-8), box, mode='same')
                harmonic_smooth = np.convolve(rmse_h / (np.max(rmse_h) + 1e-8), box, mode='same')
            except Exception:
                percussive_smooth = harmonic_smooth = np.zeros(S.shape[1])
                
            # Sub-bands
            sub_bass_ratio_smooth = np.convolve(np.sum(S[2:6, :], axis=0) / total_energy_per_frame, box, mode='same')
            bass_ratio_smooth = np.convolve(np.sum(S[6:23, :], axis=0) / total_energy_per_frame, box, mode='same')
            mid_ratio_smooth = np.convolve(np.sum(S[23:186, :], axis=0) / total_energy_per_frame, box, mode='same')
            high_ratio_smooth = np.convolve(np.sum(S[186:, :], axis=0) / total_energy_per_frame, box, mode='same')
            
            # Syncopation & Roughness
            onset_env_norm = onset_env / (np.max(onset_env) + 1e-8)
            onset_env_norm = np.pad(onset_env_norm, (0, max(0, S.shape[1] - len(onset_env_norm))), 'edge')[:S.shape[1]]
            syncopation_norm = np.sqrt(np.maximum(0.0, np.convolve(onset_env_norm**2, np.ones(64)/64.0, mode='same')))
            syncopation_norm_smooth = np.convolve(syncopation_norm / (np.max(syncopation_norm) + 1e-8), box, mode='same')
            
            try:
                flatness = librosa.feature.spectral_flatness(y=y, n_fft=2048, hop_length=1024)[0]
                flatness = np.pad(flatness, (0, max(0, S.shape[1] - len(flatness))), 'edge')[:S.shape[1]]
            except Exception: flatness = np.zeros(S.shape[1])
            
            high_diff = np.zeros(S.shape[1])
            high_diff[1:] = np.abs(high_energy_per_frame[1:] - high_energy_per_frame[:-1])
            roughness_norm = np.convolve(0.5 * flatness + 0.5 * (high_diff / (np.max(high_diff) + 1e-8)), box, mode='same')
            roughness_norm = roughness_norm / (np.max(roughness_norm) + 1e-8)
            
            # Stereo width calculation (Side energy / Total energy)
            try:
                y_stereo, _ = librosa.load(audio_path, sr=22050, mono=False)
                if y_stereo.ndim == 2 and y_stereo.shape[0] == 2:
                    L = y_stereo[0]
                    R = y_stereo[1]
                    mid = L + R
                    side = L - R
                    
                    frame_len = 2048
                    hop_len = 1024
                    
                    mid_frames = librosa.util.frame(mid, frame_length=frame_len, hop_length=hop_len)
                    side_frames = librosa.util.frame(side, frame_length=frame_len, hop_length=hop_len)
                    
                    mid_energy = np.sum(mid_frames**2, axis=0)
                    side_energy = np.sum(side_frames**2, axis=0)
                    
                    stereo_w = side_energy / (mid_energy + side_energy + 1e-8)
                    stereo_width_smooth = np.convolve(stereo_w, box, mode='same')
                    stereo_width_smooth = np.clip(stereo_width_smooth, 0.0, 1.0)
                else:
                    stereo_width_smooth = np.zeros(S.shape[1])
            except Exception as e:
                logger.warning(f"Failed to calculate stereo width: {e}")
                stereo_width_smooth = np.zeros(S.shape[1])
                
            if len(stereo_width_smooth) < S.shape[1]:
                stereo_width_smooth = np.pad(stereo_width_smooth, (0, S.shape[1] - len(stereo_width_smooth)), 'edge')
            else:
                stereo_width_smooth = stereo_width_smooth[:S.shape[1]]
            
            
            # MFCCs & Chroma Chords
            try:
                mfcc_mean = np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13), axis=1)
                rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
                rolloff_norm = np.convolve(np.pad(rolloff, (0, max(0, S.shape[1] - len(rolloff))), 'edge')[:S.shape[1]], box, mode='same')
                rolloff_norm /= (np.max(rolloff_norm) + 1e-8)
            except Exception:
                mfcc_mean, rolloff_norm = np.zeros(13), np.zeros(S.shape[1])
                
            try:
                chroma_stft = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=2048, hop_length=1024)
                chroma_stft = np.pad(chroma_stft, ((0, 0), (0, max(0, S.shape[1] - chroma_stft.shape[1]))), 'edge')[:, :S.shape[1]]
                chroma_smooth = np.array([np.convolve(chroma_stft[c_idx, :], np.ones(3)/3.0, mode='same') for c_idx in range(12)])
            except Exception:
                chroma_smooth = np.zeros((12, S.shape[1]))
                
            chord_names, chord_hues, chord_saturations, chord_brightnesses, chord_colors_hex = [], [], [], [], []
            centroid_norm = centroids_smooth / (np.max(centroids_smooth) + 1e-8)
            
            for f in range(S.shape[1]):
                chroma_vec = chroma_smooth[:, f]
                vec_norm = np.linalg.norm(chroma_vec)
                if vec_norm < 1e-4 or total_energy_per_frame[f] < (np.max(total_energy_per_frame) * 0.005):
                    chord_names.append("N.C."); chord_hues.append(0.0); chord_saturations.append(0.0); chord_brightnesses.append(0.1); chord_colors_hex.append("#0a0a0c")
                else:
                    best_chord = max(CHORD_TEMPLATES, key=lambda name: np.dot(chroma_vec / vec_norm, CHORD_TEMPLATES[name]))
                    root_idx, q_type, hue, sat, q_factor = parse_chord_name(best_chord)
                    c_bright = float(np.clip(0.6 * q_factor + 0.4 * centroid_norm[f], 0.1, 1.0))
                    
                    chord_names.append(best_chord)
                    chord_hues.append(float(hue))
                    chord_saturations.append(float(sat))
                    chord_brightnesses.append(c_bright)
                    # FIX 2: Type conversion shield for color generation
                    chord_colors_hex.append(hsl_to_hex(float(hue), float(sat), float(c_bright * 0.5)))
            
            total_energy_smooth = np.convolve(total_energy_per_frame / (np.max(total_energy_per_frame) + 1e-8), box, mode='same')
            
            filter_dynamics = {
                'times': [float(t) for t in times], 'lowpass': [float(v) for v in lp_smooth], 'highpass': [float(v) for v in hp_smooth],
                'silence_fade': [float(a) for a in silence_fade_alpha], 'centroid': [float(c) for c in centroids_smooth], 'centroid_norm': [float(c) for c in centroid_norm],
                'stereo_width': [float(sw) for sw in stereo_width_smooth],
                'ethereal_index': [float(e) for e in ethereal_smooth],
                'percussive': [float(p) for p in percussive_smooth], 'harmonic': [float(h) for h in harmonic_smooth], 'sub_bass_ratio': [float(sb) for sb in sub_bass_ratio_smooth],
                'bass_ratio': [float(b) for b in bass_ratio_smooth], 'mid_ratio': [float(m) for m in mid_ratio_smooth], 'high_ratio': [float(hi) for hi in high_ratio_smooth],
                'syncopation': [float(s) for s in syncopation_norm_smooth], 'roughness': [float(r) for r in roughness_norm], 'mfcc_mean': [float(x) for x in mfcc_mean],
                'rolloff': [float(ro) for ro in rolloff_norm], 'bass_energy': [float(v) for v in np.convolve((np.sum(S[:23, :], axis=0) / np.max(np.sum(S[:23, :], axis=0) + 1e-8)), box, mode='same')],
                'mid_energy': [float(v) for v in np.convolve((np.sum(S[23:186, :], axis=0) / np.max(np.sum(S[23:186, :], axis=0) + 1e-8)), box, mode='same')],
                'high_energy': [float(v) for v in np.convolve((np.sum(S[186:, :], axis=0) / np.max(np.sum(S[186:, :], axis=0) + 1e-8)), box, mode='same')],
                'total_energy': [float(v) for v in total_energy_smooth],
                'chord_name': chord_names, 'chord_hue': chord_hues, 'chord_saturation': chord_saturations, 'chord_brightness': chord_brightnesses, 'chord_color_hex': chord_colors_hex
            }
            
            resolved_genre = self.detect_genre(bpm, filter_dynamics) if genre in ('Auto (自動偵測)', 'auto') else genre.lower().replace(' ', '_').replace('pop', 'pop')
            
            # Genre-based constraint adjustments
            t_gap = 0.60 if resolved_genre == 'ambient' else (0.45 if resolved_genre == 'lo-fi' else (0.28 if resolved_genre == 'dub_techno' else 0.18))
            t_thresh_fact = 2.0 if resolved_genre == 'ambient' else (1.5 if resolved_genre == 'lo-fi' else (1.3 if resolved_genre == 'dub_techno' else 1.1))
            
            onset_frames_trans = np.where(onset_env > (np.mean(onset_env) + t_thresh_fact * np.std(onset_env)))[0]
            filtered_onset_frames, last_o_frame = [], -999
            for fr in onset_frames_trans:
                if (fr - last_o_frame) * (512.0 / sr) >= t_gap:
                    filtered_onset_frames.append(fr)
                    last_o_frame = fr
                    
            transient_timestamps = [float(t) for t in librosa.frames_to_time(filtered_onset_frames, sr=sr, hop_length=512)]
            beat_timestamps = []
            last_t = -999.0
            for evt in sorted(set(raw_beat_timestamps + transient_timestamps)):
                if evt - last_t >= t_gap:
                    beat_timestamps.append(evt)
                    last_t = evt
            
            # Resample spectrum to 64 bins
            bins_group = S.shape[0] // 64
            S_smooth = np.array([np.convolve(np.log1p((np.mean(S[i*bins_group:(i+1)*bins_group, :], axis=0) * (1.0 + (i / 64.0) * 3.5)) / (np.max(S) + 1e-8) * 9) / np.log1p(9), np.ones(3)/3.0, mode='same') for i in range(64)])
            S_smooth[:, silent_frames] = 0.0
            
            storyboard = self.generate_storyboard(duration, filter_dynamics, resolved_genre, beat_timestamps=beat_timestamps)
            rms_full = librosa.feature.rms(y=y, frame_length=2048, hop_length=1024)[0]
            
            return {
                'audio_path': audio_path, 'bpm': bpm, 'beat_timestamps': beat_timestamps, 'duration': duration, 'filter_dynamics': filter_dynamics,
                'spectrum': S_smooth.tolist(), 'storyboard': storyboard, 'genre': resolved_genre.capitalize(),
                'rms_mean': float(np.mean(rms_full)), 'rms_std': float(np.std(rms_full)), 'transient_timestamps': transient_timestamps
            }
        except Exception as e:
            logger.error(f"Error analyzing audio: {e}"); raise
 
    def detect_genre(self, bpm: float, filter_dynamics: dict) -> str:
        ethereal = filter_dynamics.get('ethereal_index', [])
        percussive = filter_dynamics.get('percussive', [])
        bass_ratio = filter_dynamics.get('bass_ratio', [])
        syncopation = filter_dynamics.get('syncopation', [])
        roughness = filter_dynamics.get('roughness', [])
        harmonic = filter_dynamics.get('harmonic', [])
        
        avg_eth = float(np.mean(ethereal)) if ethereal else 0.0
        avg_perc = float(np.mean(percussive)) if percussive else 0.0
        avg_bass = float(np.mean(bass_ratio)) if bass_ratio else 0.0
        avg_sync = float(np.mean(syncopation)) if syncopation else 0.0
        avg_rough = float(np.mean(roughness)) if roughness else 0.0
        avg_harm = float(np.mean(harmonic)) if harmonic else 0.5
        
        if avg_perc < 0.22 and avg_eth > 0.40: return 'ambient'
        if bpm >= 138 and avg_perc > 0.48 and avg_rough > 0.45: return 'hard_techno'
        if bpm >= 150: return 'dnb'
        if 90 <= bpm <= 140 and avg_sync > 0.50 and avg_rough > 0.50: return 'idm'
        if 115 <= bpm <= 138 and avg_perc > 0.45 and avg_bass > 0.35: return 'edm'
        if avg_harm > 0.55 and avg_perc < 0.30 and avg_eth > 0.35: return 'jazz'
        if avg_rough > 0.48 and avg_harm > 0.45 and avg_perc > 0.38: return 'rock'
        if 80 <= bpm <= 140 and avg_harm > 0.55 and avg_perc > 0.32: return 'pop'
        if bpm < 95: return 'lo-fi'
        if 100 <= bpm <= 140:
            return 'dub_techno' if avg_eth > 0.38 and avg_perc < 0.38 and avg_bass > 0.40 else 'techno'
        return 'generic'

    def generate_storyboard(self, duration: float, filter_dynamics: dict, genre: str = 'generic', beat_timestamps: list = None) -> list:
        times = filter_dynamics['times']
        lowpass = filter_dynamics.get('lowpass', [0.0] * len(times))
        percussive = filter_dynamics.get('percussive', [0.0] * len(times))
        ethereal = filter_dynamics.get('ethereal_index', [0.0] * len(times))
        syncopation = filter_dynamics.get('syncopation', [0.0] * len(times))
        harmonic = filter_dynamics.get('harmonic', [0.5] * len(times))
        total_energy = filter_dynamics.get('total_energy', [0.0] * len(times))
        bass_energy = filter_dynamics.get('bass_energy', [0.0] * len(times))
        
        raw_sections = []
        for i, t in enumerate(times):
            ratio = t / duration if duration > 0 else 0.0
            p_v, t_e, b_e, s_v, h_v = percussive[i], total_energy[i], bass_energy[i], syncopation[i], harmonic[i]
            
            if genre in ('dnb', 'hard_techno', 'edm'):
                sec = 'Intro' if ratio < 0.09 and p_v < 0.31 else ('Outro' if ratio > 0.91 and t_e < 0.26 else ('Drop' if t_e > 0.49 and (p_v > 0.37 or b_e > 0.45) else ('Build-up' if s_v > 0.38 or p_v > 0.38 else 'Verse')))
            elif genre in ('pop', 'rock'):
                sec = 'Intro' if ratio < 0.10 and p_v < 0.30 else ('Outro' if ratio > 0.90 and t_e < 0.30 else ('Chorus' if t_e > 0.48 and h_v > 0.50 else ('Bridge' if 0.65 <= ratio <= 0.85 and t_e < 0.45 else 'Verse')))
            else:
                sec = 'Intro' if ratio < 0.10 and p_v < 0.30 else ('Outro' if ratio > 0.90 and t_e < 0.30 else 'Verse')
            raw_sections.append(sec)
            
        sections_merged = []
        if len(times) > 0:
            curr_sec, start_t = raw_sections[0], times[0]
            for i in range(1, len(times)):
                if raw_sections[i] != curr_sec:
                    sections_merged.append({'start': start_t, 'end': times[i], 'section': curr_sec})
                    curr_sec, start_t = raw_sections[i], times[i]
            sections_merged.append({'start': start_t, 'end': duration, 'section': curr_sec})
            
        min_duration = 12.0 if genre in ('lo-fi', 'jazz', 'ambient') else (8.0 if genre in ('dub_techno', 'pop') else 3.0)
        smooth_sections = []
        for sec in sections_merged:
            c_min = 1.5 if sec['section'] == 'Drop' or (smooth_sections and smooth_sections[-1]['section'] == 'Drop') else min_duration
            if (sec['end'] - sec['start']) < c_min and smooth_sections:
                smooth_sections[-1]['end'] = sec['end']
            else:
                smooth_sections.append(sec)
                
        # Split overly-long segments at beat boundaries
        max_seg_dur = 24.0 if genre in ('lo-fi', 'jazz', 'ambient') else (20.0 if genre in ('dub_techno', 'pop') else 14.0)
        if beat_timestamps:
            import bisect
            split_sections = []
            for sec in smooth_sections:
                if (sec['end'] - sec['start']) <= max_seg_dur:
                    split_sections.append(sec); continue
                num_splits = int((sec['end'] - sec['start']) / max_seg_dur)
                sub_len = (sec['end'] - sec['start']) / (num_splits + 1)
                cursor = sec['start']
                for s_i in range(num_splits):
                    ideal_end = cursor + sub_len
                    idx = bisect.bisect_left(beat_timestamps, ideal_end)
                    candidates = [beat_timestamps[i] for i in (idx-1, idx) if 0 <= i < len(beat_timestamps)]
                    best_beat = min(candidates, key=lambda b: abs(b - ideal_end)) if candidates else ideal_end
                    best_beat = max(cursor + min_duration, min(best_beat, sec['end'] - min_duration))
                    if best_beat >= sec['end'] - min_duration: break
                    split_sections.append({'start': cursor, 'end': best_beat, 'section': sec['section']})
                    cursor = best_beat
                split_sections.append({'start': cursor, 'end': sec['end'], 'section': sec['section']})
            smooth_sections = split_sections

        genre_layouts = ['fullscreen', 'split_h'] if genre == 'lo-fi' else (['fullscreen', 'split_h', 'split_v'] if genre == 'ambient' else (['fullscreen', 'split_v'] if genre == 'jazz' else (['fullscreen', 'mirror', 'split_v'] if genre == 'dub_techno' else ['grid', 'mirror', 'split_h', 'fullscreen'])))
        for sec in smooth_sections:
            sec['recommended_layouts'] = ['fullscreen', 'grid', 'mirror', 'split_v', 'split_h'] if sec['section'] == 'Drop' else (['mirror', 'split_h', 'fullscreen'] if sec['section'] == 'Build-up' else genre_layouts)
            sec['recommended_filters'] = ['glitch', 'pixel_sort', 'rgb_feedback', 'flash', 'none'][:5]
        return smooth_sections

    def cleanup(self):
        for file_path in self.downloaded_files:
            if os.path.exists(file_path):
                try: os.remove(file_path)
                except Exception: pass
        self.downloaded_files.clear()
        if os.path.exists(self.temp_dir) and not os.listdir(self.temp_dir):
            try: os.rmdir(self.temp_dir)
            except Exception: pass


class LiveAudioBeatDetector:
    """實時音訊輸入監聽與多指標前沿特徵分析器。"""
    def __init__(self, device_index=None, sample_rate=22050, block_size=1024, callback=None):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.callback = callback
        
        try:
            self.b, self.a = signal.butter(2, 150.0 / (self.sample_rate / 2.0), btype='low')
            self.filter_state = signal.lfilter_zi(self.b, self.a)
        except Exception as e:
            logger.error(f"Failed to initialize lowpass filter: {e}")
            self.b = self.a = self.filter_state = None
            
        self.energy_history = []
        self.history_size = int(self.sample_rate / self.block_size * 1.5)
        self.last_beat_time = 0.0
        self.min_beat_interval = 0.250
        
        self.threshold_factor = 1.35
        self.mid_high_energy_history = []
        self.mid_high_threshold_factor = 1.6
        
        self.is_running = False
        self.recorded_audio_blocks = []
        self.is_recording_audio = False
        self.record_lock = threading.Lock()
        self.stream = None
        self.audio_queue = queue.Queue()
        self.worker_thread = None
        self.lp_smooth = 0.0
        self.hp_smooth = 0.0
        self.live_spectrum = np.zeros(64)
        self.silence_fade = 0.0
        
        self.bass_flux_history = []
        self.mid_high_flux_history = []
        self.live_centroid = 1000.0
        self.live_ethereal_index = 0.0
        self.prev_fft = None
        
        self.live_percussive = 0.0
        self.live_harmonic = 0.5
        self.live_sub_bass_ratio = 0.0
        self.live_bass_ratio = 0.0
        self.live_mid_ratio = 0.0
        self.live_high_ratio = 0.0
        self.live_syncopation = 0.0
        self.live_roughness = 0.0
        self.live_flux_history = []
        
        self.sub_bass_ratio_history = []
        self.bass_ratio_history = []
        self.mid_ratio_history = []
        self.high_ratio_history = []
        self.agc_enabled = True
        self.rms_volume = 0.0
        self.is_silent_signal = True
        self.blocks_processed = 0

    def audio_callback(self, indata, frames, time_info, status):
        block_copy = indata[:, 0].copy()
        if self.audio_queue.qsize() > 20:
            try: self.audio_queue.get_nowait()
            except queue.Empty: pass

        self.audio_queue.put(block_copy)
        if getattr(self, "is_recording_audio", False):
            with self.record_lock:
                if self.is_recording_audio:
                    self.recorded_audio_blocks.append(block_copy)

    def start(self):
        if self.is_running: return
        self.is_running = True
        self.energy_history = []
        self.last_beat_time = time.time()
        self.blocks_processed = 0
        while not self.audio_queue.empty(): self.audio_queue.get()
            
        try:
            self.stream = sd.InputStream(device=self.device_index, channels=1, samplerate=self.sample_rate, blocksize=self.block_size, callback=self.audio_callback)
            self.stream.start()
            logger.info(f"Live audio stream started on device {self.device_index}")
        except Exception as e:
            self.is_running = False; logger.error(f"Failed to start stream: {e}"); raise e
            
        self.worker_thread = threading.Thread(target=self.process_audio, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.is_running = False
        if self.stream:
            try: self.stream.stop(); self.stream.close()
            except Exception: pass
            self.stream = None
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0); self.worker_thread = None
        logger.info("Live audio stream stopped.")

    def process_audio(self):
        zi = signal.lfilter_zi(self.b, self.a) if self.b is not None else None
        while self.is_running:
            try: block = self.audio_queue.get(timeout=0.1)
            except queue.Empty: continue
                
            block = block - np.mean(block)
            filtered_block, zi = signal.lfilter(self.b, self.a, block, zi=zi) if self.b is not None and zi is not None else (block, None)
                
            if getattr(self, "blocks_processed", 0) < 20:
                self.blocks_processed += 1; block = np.zeros_like(block); filtered_block = np.zeros_like(filtered_block)
            else:
                self.blocks_processed += 1
                
            energy = np.sum(filtered_block ** 2) / len(filtered_block)
            mid_high_block = block - filtered_block
            mid_high_energy = np.sum(mid_high_block ** 2) / len(mid_high_block)
            self.rms_volume = float(np.sqrt(np.mean(block ** 2)))
            
            fft_vals = np.abs(np.fft.rfft(block))
            fft_len = len(fft_vals)
            lp_val = hp_val = 0.0
            current_spectrum = np.zeros(64)
            is_silent, c_time, beat_triggered = True, time.time(), False
            time_since_last_beat = c_time - self.last_beat_time
            
            if fft_len > 0:
                total_energy = np.sum(fft_vals)
                if total_energy > 0.04:
                    is_silent = False
                    low_ratio = np.sum(fft_vals[:8]) / (total_energy + 1e-8)
                    high_ratio = np.sum(fft_vals[140:]) / (total_energy + 1e-8)
                    lp_val, hp_val = np.clip((0.015 - high_ratio) / 0.015, 0, 1), np.clip((0.04 - low_ratio) / 0.04, 0, 1)
                    
                    centroid = np.sum(np.arange(fft_len) * (self.sample_rate / 2.0 / fft_len) * fft_vals) / (total_energy + 1e-8)
                    self.live_centroid = 0.82 * self.live_centroid + 0.18 * centroid
                    
                    bass_energy_freq = np.sum(fft_vals[:13])
                    mid_high_ratio_freq = np.sum(fft_vals[46:187]) / (total_energy + 1e-8)
                    
                    if self.prev_fft is not None and len(self.prev_fft) == fft_len:
                        flux_pos = np.maximum(0.0, fft_vals - self.prev_fft)
                        bass_flux, m_h_flux = np.sum(flux_pos[:13]), np.sum(flux_pos[46:187])
                        
                        self.bass_flux_history.append(bass_flux)
                        self.mid_high_flux_history.append(m_h_flux)
                        for f_hist in (self.bass_flux_history, self.mid_high_flux_history):
                            if len(f_hist) > self.history_size: f_hist.pop(0)
                            
                        if bass_flux > 1.45 * np.mean(self.bass_flux_history) and time_since_last_beat > self.min_beat_interval:
                            self.last_beat_time = c_time; beat_triggered = True
                            if self.callback: self.callback()
                        elif m_h_flux > 1.6 * np.mean(self.mid_high_flux_history) and time_since_last_beat > self.min_beat_interval:
                            self.last_beat_time = c_time; beat_triggered = True
                            if self.callback: self.callback()
                                
                    self.live_ethereal_index = 0.90 * self.live_ethereal_index + 0.10 * ((1.0 - np.clip((bass_energy_freq / (total_energy + 1e-8)) / 0.35, 0, 1)) * np.clip(mid_high_ratio_freq / 0.05, 0, 1))
                    
                    flux_total = np.sum(np.maximum(0.0, fft_vals - (self.prev_fft if self.prev_fft is not None else fft_vals)))
                    percussive_est = np.clip(flux_total / (total_energy + 1e-8) * 1.5, 0.0, 1.0)
                    self.live_percussive = 0.85 * self.live_percussive + 0.15 * percussive_est
                    self.live_harmonic = 0.85 * self.live_harmonic + 0.15 * (1.0 - percussive_est)
                    
                    sub_bass_r = np.sum(fft_vals[1:3]) / (total_energy + 1e-8)
                    bass_r = np.sum(fft_vals[3:12]) / (total_energy + 1e-8)
                    mid_r = np.sum(fft_vals[12:93]) / (total_energy + 1e-8)
                    high_r = np.sum(fft_vals[93:]) / (total_energy + 1e-8)
                    
                    self.sub_bass_ratio_history.append(sub_bass_r)
                    self.bass_ratio_history.append(bass_r)
                    self.mid_ratio_history.append(mid_r)
                    self.high_ratio_history.append(high_r)
                    
                    h_max_len = int(self.sample_rate / self.block_size * 6.0)
                    for h_list, attr in ((self.sub_bass_ratio_history, 'live_sub_bass_ratio'), (self.bass_ratio_history, 'live_bass_ratio'), (self.mid_ratio_history, 'live_mid_ratio'), (self.high_ratio_history, 'live_high_ratio')):
                        if len(h_list) > h_max_len: h_list.pop(0)
                        p90 = max(1e-4, max(h_list) if len(h_list) > 10 else 0.15)
                        scaled_val = np.clip(h_list[-1] * (0.65 / p90), 0.0, 1.0) if self.agc_enabled else h_list[-1]
                        setattr(self, attr, 0.85 * getattr(self, attr, 0.0) + 0.15 * scaled_val)
                        
                    self.live_flux_history.append(flux_total)
                    if len(self.live_flux_history) > 40: self.live_flux_history.pop(0)
                    self.live_syncopation = 0.90 * self.live_syncopation + 0.10 * (np.clip((np.std(self.live_flux_history) / (np.mean(self.live_flux_history) + 1e-8) - 0.2) / 1.5, 0.0, 1.0) if len(self.live_flux_history) > 5 else 0.0)
                    self.live_roughness = 0.85 * self.live_roughness + 0.15 * np.clip(np.sum(np.abs(fft_vals[1:] - fft_vals[:-1])) / (total_energy + 1e-8) * 0.4, 0.0, 1.0)
                    
                    bins_g = fft_len // 64
                    fft_down = np.array([np.mean(fft_vals[i*bins_g:(i+1)*bins_g]) * (1.0 + (i / 64.0) * 3.5) for i in range(64)])
                    self.rolling_max = 0.99 * getattr(self, 'rolling_max', 1.0) + 0.01 * (np.max(fft_down) + 1e-5)
                    current_spectrum = np.log1p(np.clip(fft_down / self.rolling_max, 0, 1) * 9) / np.log1p(9)
            
            if not is_silent and not beat_triggered:
                if self.energy_history and energy > self.threshold_factor * np.mean(self.energy_history) and time_since_last_beat > self.min_beat_interval:
                    self.last_beat_time = c_time; beat_triggered = True
                    if self.callback: self.callback()
                elif self.mid_high_energy_history and mid_high_energy > self.mid_high_threshold_factor * np.mean(self.mid_high_energy_history) and time_since_last_beat > self.min_beat_interval:
                    self.last_beat_time = c_time
                    if self.callback: self.callback()
                    
            self.lp_smooth = 0.85 * self.lp_smooth + 0.15 * lp_val
            self.hp_smooth = 0.85 * self.hp_smooth + 0.15 * hp_val
            self.live_spectrum = 0.6 * self.live_spectrum + 0.4 * current_spectrum
            
            alpha_s = (len(block) / float(self.sample_rate)) / 0.5
            if is_silent:
                self.silence_fade = min(1.0, self.silence_fade + alpha_s); self.live_ethereal_index *= 0.90
                self.live_percussive *= 0.85; self.live_harmonic = 0.85 * self.live_harmonic + 0.15 * 0.5
                for attr in ('live_sub_bass_ratio', 'live_bass_ratio', 'live_mid_ratio', 'live_high_ratio', 'live_syncopation', 'live_roughness'):
                    setattr(self, attr, 0.85 * getattr(self, attr))
            else:
                self.silence_fade = max(0.0, self.silence_fade - alpha_s)
                
            self.energy_history.append(energy)
            if len(self.energy_history) > self.history_size: self.energy_history.pop(0)
            self.mid_high_energy_history.append(mid_high_energy)
            if len(self.mid_high_energy_history) > self.history_size: self.mid_high_energy_history.pop(0)
            self.is_silent_signal = is_silent
            if fft_len > 0:
                self.prev_fft = fft_vals.copy()

    def start_recording(self):
        with self.record_lock: self.recorded_audio_blocks = []; self.is_recording_audio = True
        logger.info("Live audio recording started.")

    def stop_recording(self, output_wav_path):
        with self.record_lock:
            self.is_recording_audio = False
            blocks_to_save = list(self.recorded_audio_blocks)
            self.recorded_audio_blocks = []
        if not blocks_to_save: return False
        try:
            import soundfile as sf
            sf.write(output_wav_path, np.concatenate(blocks_to_save), self.sample_rate)
            return True
        except Exception as e: logger.error(f"Failed to save live audio: {e}"); return False

    def get_filter_status(self):
        """
        FIX 1: 完美對接前沿 VJ 後製特效。
        同時輸出帶有前綴與無前綴標準鍵名，保證 PostProcessor.process() 完美讀取。
        """
        return {
            # 兼容原版格式
            'lowpass': self.lp_smooth,
            'highpass': self.hp_smooth,
            'spectrum': self.live_spectrum.tolist(),
            'silence_fade': self.silence_fade,
            'centroid': self.live_centroid,
            'ethereal_index': self.live_ethereal_index,
            'rms_volume': self.rms_volume,
            'is_silent': self.is_silent_signal,
            
            # 實時對接無前綴核心欄位 (對齊 PostProcessor.process 的讀取特徵)
            'sub_bass': self.live_sub_bass_ratio,
            'percussive': self.live_percussive,
            'harmonic': self.live_harmonic,
            'ethereal': self.live_ethereal_index,
            'roughness': self.live_roughness,
            'syncopation': self.live_syncopation,
            'bass_ratio': self.live_bass_ratio,
            'mid_ratio': self.live_mid_ratio,
            'high_ratio': self.live_high_ratio,
            
            # 預設和弦後備欄位 (防止實時未接入和弦分析時拋異常)
            'chord_name': 'N.C.',
            'chord_hue': 180.0,
            'chord_brightness': 0.5
        }
