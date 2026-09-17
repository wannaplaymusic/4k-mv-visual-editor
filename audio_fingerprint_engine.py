import os
import hashlib
import logging
import numpy as np
from typing import Optional, List, Union

logger = logging.getLogger("StandaloneInjector.AudioFingerprint")

try:
    import torch
    import laion_clap
    HAS_CLAP = True
except ImportError:
    HAS_CLAP = False
    logger.warning("laion_clap or torch not available, heuristic acoustic embedding will be used.")

HAS_UMAP = None

def _check_umap():
    global HAS_UMAP
    if HAS_UMAP is None:
        try:
            import umap
            HAS_UMAP = True
        except ImportError:
            HAS_UMAP = False
    return HAS_UMAP

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

# 16 大主流音樂風格本體庫與多模態 Prompt 集成
GENRE_REGISTRY = {
    "techno": {
        "display_name": "Techno / Industrial",
        "sub_genre": "Peak-Time Dark Acid Techno",
        "prompts": [
            "A dark hypnotic peak-time techno track with driving four-on-the-floor kick, rolling sub bass and modular synthesizer stabs",
            "Industrial underground techno music with aggressive percussive groove, distortion and relentless 130 bpm energy",
            "Dark warehouse techno with repetitive mechanical rhythms and resonant acid basslines"
        ],
        "default_valence": -0.45,
        "default_arousal": 0.85,
        "danceability": 0.88,
        "bpm_range": (124, 142),
        "ideal_bpm": 132
    },
    "trance": {
        "display_name": "Trance / Progressive",
        "sub_genre": "Euphoric Uplifting Trance",
        "prompts": [
            "An uplifting euphoric trance track with huge melodic supersaw leads, emotional pads and energetic rolling bass",
            "Psychedelic progressive trance with driving 138 bpm bassline, sweeping filters and hypnotic arpeggios",
            "Epic vocal trance with soaring melodies, dramatic crescendo build-ups and emotional release"
        ],
        "default_valence": 0.55,
        "default_arousal": 0.90,
        "danceability": 0.82,
        "bpm_range": (128, 142),
        "ideal_bpm": 136
    },
    "dnb": {
        "display_name": "Drum & Bass / Neurofunk",
        "sub_genre": "High-Energy Neurofunk",
        "prompts": [
            "A fast drum and bass track with complex amen breakbeats, heavy reese bass and intense energy around 174 bpm",
            "Aggressive neurofunk dnb with distorted modulated basslines, crisp syncopated snares and futuristic sound design",
            "Liquid drum and bass with smooth jazzy Rhodes chords, deep sub bass and rapid rolling breakbeats"
        ],
        "default_valence": 0.10,
        "default_arousal": 0.95,
        "danceability": 0.80,
        "bpm_range": (160, 182),
        "ideal_bpm": 174
    },
    "dubstep": {
        "display_name": "Dubstep / Bass Music",
        "sub_genre": "Heavy Riddim & Tearout",
        "prompts": [
            "Heavy dubstep track with aggressive growl bass drops, half-time syncopated drums and metallic sound effects at 140 bpm",
            "Riddim bass music with repetitive stomping sub kicks, mechanical screech synths and sub-heavy impact",
            "Melodic dubstep with emotional orchestral intro transitioning into a powerful vocal chops drop"
        ],
        "default_valence": -0.20,
        "default_arousal": 0.92,
        "danceability": 0.72,
        "bpm_range": (135, 150),
        "ideal_bpm": 140
    },
    "house": {
        "display_name": "House / Deep House",
        "sub_genre": "Groovy Club House",
        "prompts": [
            "A warm groovy house track with four-on-the-floor kick, swinging hi-hats, soulful vocal chops and bouncy bassline",
            "Deep house music with lush Rhodes electric piano chords, warm sub bass and sensual relaxed club groove",
            "Tech house with punchy minimal drums, infectious rolling percussive groove and quirky synth stabs"
        ],
        "default_valence": 0.50,
        "default_arousal": 0.75,
        "danceability": 0.92,
        "bpm_range": (120, 128),
        "ideal_bpm": 124
    },
    "synthwave": {
        "display_name": "Synthwave / Retrowave",
        "sub_genre": "80s Outrun & Chillwave",
        "prompts": [
            "1980s retro synthwave track with nostalgic analog synthesizer leads, gated reverb drums and driving arpeggiated bassline",
            "Outrun electronic music evoking neon highways, vintage VHS aesthetics, warm detuned pads and electric guitar solos",
            "Darksynth music with aggressive distorted cyber synths, heavy beats and dystopian cyberpunk horror atmosphere"
        ],
        "default_valence": 0.20,
        "default_arousal": 0.70,
        "danceability": 0.75,
        "bpm_range": (100, 130),
        "ideal_bpm": 116
    },
    "lo-fi": {
        "display_name": "Lo-Fi / Chillhop",
        "sub_genre": "Dusty Vinyl Chillhop",
        "prompts": [
            "Relaxing lo-fi hip hop beat with dusty vinyl surface noise, mellow electric piano chords, tape warble and lazy swing drums",
            "Chill study instrumental beat with warm acoustic guitar samples, soft sub bass and peaceful nostalgic atmosphere",
            "Jazzy downtempo lofi track with sleepy saxophone melodies and muffled drum kit"
        ],
        "default_valence": 0.25,
        "default_arousal": 0.25,
        "danceability": 0.45,
        "bpm_range": (70, 92),
        "ideal_bpm": 80
    },
    "ambient": {
        "display_name": "Ambient / Drone",
        "sub_genre": "Cinematic Soundscape",
        "prompts": [
            "Ethereal meditative ambient music with vast reverberant synth pads, gentle textural drones and no rhythmic drums",
            "Deep space cinematic soundscape with evolving shimmering chords, subtle frequency sweeps and timeless tranquility",
            "Dark ambient drone with resonant metallic vibrations, wind noises and ominous cavernous reverb"
        ],
        "default_valence": 0.0,
        "default_arousal": 0.15,
        "danceability": 0.10,
        "bpm_range": (40, 90),
        "ideal_bpm": 60
    },
    "hip-hop": {
        "display_name": "Hip-Hop / Trap",
        "sub_genre": "808 Trap & Boom Bap",
        "prompts": [
            "Modern trap beat with sliding 808 sub bass, rapid rolling hi-hats, punchy snare and dark atmospheric melody",
            "Boom bap 90s hip-hop groove with crispy sampled acoustic drums, scratching and soulful looped brass",
            "Melodic hip-hop instrumental with catchy 808 bass, autotuned vocal chops and clean piano progression"
        ],
        "default_valence": 0.15,
        "default_arousal": 0.70,
        "danceability": 0.85,
        "bpm_range": (65, 160),
        "ideal_bpm": 140
    },
    "rock": {
        "display_name": "Rock / Alternative",
        "sub_genre": "Modern Alternative Rock",
        "prompts": [
            "Dynamic alternative rock song with crunchy overdrive electric guitars, live acoustic drum kit, bass guitar and energetic vocals",
            "Indie rock with jangly guitar riffs, driving rhythm section and catchy anthemic chorus",
            "Classic hard rock track with searing electric guitar solos, heavy drums and raw acoustic power"
        ],
        "default_valence": 0.20,
        "default_arousal": 0.78,
        "danceability": 0.55,
        "bpm_range": (105, 145),
        "ideal_bpm": 125
    },
    "metal": {
        "display_name": "Metal / Hardcore",
        "sub_genre": "Djent & Heavy Metal",
        "prompts": [
            "Aggressive heavy metal track with down-tuned distorted guitars, rapid double-kick bass drums and intense harsh vocals",
            "Djent progressive metal with complex polyrhythmic guitar chugs, thundering bass and explosive breakdowns",
            "Thrash metal with fast galloping guitar riffs, intense blast beats and aggressive rebellious power"
        ],
        "default_valence": -0.60,
        "default_arousal": 0.98,
        "danceability": 0.35,
        "bpm_range": (120, 200),
        "ideal_bpm": 150
    },
    "jazz": {
        "display_name": "Jazz / Funk / Soul",
        "sub_genre": "Neo-Soul & Fusion Jazz",
        "prompts": [
            "Sophisticated jazz fusion instrumental with intricate chord changes, walking acoustic upright bass, saxophone and swung drums",
            "Upbeat funk music with slapping electric bass guitar, syncopated rhythm, wah-wah guitar and punchy brass horn section",
            "Warm neo-soul groove with lush extended chords on Rhodes piano and expressive vocal melodies"
        ],
        "default_valence": 0.60,
        "default_arousal": 0.50,
        "danceability": 0.72,
        "bpm_range": (85, 125),
        "ideal_bpm": 105
    },
    "classical": {
        "display_name": "Classical / Cinematic",
        "sub_genre": "Orchestral Soundtrack",
        "prompts": [
            "Epic orchestral cinematic score with sweeping symphonic strings, dramatic French horns, timpanis and choir",
            "Intimate solo acoustic grand piano performing emotive classical romantic sonata",
            "Contemporary neoclassical composition with minimalist string quartet and gentle piano arpeggios"
        ],
        "default_valence": 0.10,
        "default_arousal": 0.40,
        "danceability": 0.20,
        "bpm_range": (50, 140),
        "ideal_bpm": 85
    },
    "pop": {
        "display_name": "Pop / Electro-Pop",
        "sub_genre": "Radio Hit Electro-Pop",
        "prompts": [
            "Catchy modern electro-pop track with bright polished production, crisp dance drums, hooky vocal melodies and synth bass",
            "Upbeat dance-pop with infectious chorus, glittering synthesizer textures and radio-ready production",
            "Acoustic pop ballad with emotional vocals, acoustic guitar and soaring string accompaniment"
        ],
        "default_valence": 0.70,
        "default_arousal": 0.68,
        "danceability": 0.85,
        "bpm_range": (100, 130),
        "ideal_bpm": 120
    },
    "hardstyle": {
        "display_name": "Hardstyle / Hardcore",
        "sub_genre": "Rawstyle & Hardcore",
        "prompts": [
            "High energy hardstyle track with distorted reverse bass kick, pitch-bent screeches, epic euphoric melody at 150 bpm",
            "Hardcore techno with brutal gabber kick drums, rapid 175 bpm tempo and chaotic industrial distortion",
            "Rawstyle electronic dance music with aggressive punchy distorted kicks and dark atmospheric synths"
        ],
        "default_valence": -0.10,
        "default_arousal": 0.98,
        "danceability": 0.75,
        "bpm_range": (148, 175),
        "ideal_bpm": 150
    },
    "downtempo": {
        "display_name": "Downtempo / Trip-Hop",
        "sub_genre": "Atmospheric Trip-Hop",
        "prompts": [
            "Moody trip-hop track with slow heavy drum breaks, deep dub bassline, scratch effects and melancholic samples",
            "Warm downtempo electronica with gentle organic percussion, ambient synth pads and reflective relaxed mood",
            "Dub electronica with tape echo, spacious reverb, deep sub frequencies and slow skank rhythm"
        ],
        "default_valence": -0.10,
        "default_arousal": 0.35,
        "danceability": 0.50,
        "bpm_range": (75, 105),
        "ideal_bpm": 90
    }
}


class GenreSemanticClassifier:
    """
    多模態樂曲風格語意與情緒 (Valence-Arousal) 分類器
    - 支援 CLAP 零樣本 Prompt Ensemble 語意對齊
    - 支援 512D 物理聲學統計流形特徵比對 (無神經網路時零崩潰回退)
    - 依據 Russell 2D 環狀情緒模型輸出情感動態座標
    """
    def __init__(self, clap_model=None, device="cpu"):
        self.clap_model = clap_model
        self.device = device
        self._text_embeddings = {}
        self._precompute_text_anchors()

    def _precompute_text_anchors(self):
        """ 若 CLAP 模型存在，預先計算所有流派 Prompt Ensembles 的語意錨點中心向量 """
        if self.clap_model is None or not HAS_CLAP:
            return

        try:
            logger.info("⚡ 正在預計算 16 大風格 CLAP Prompt Ensembles 語意錨點...")
            for genre_key, info in GENRE_REGISTRY.items():
                prompts = info["prompts"]
                with torch.no_grad():
                    embeds = self.clap_model.get_text_embedding(prompts, use_tensor=False)
                    # 取 Prompt Ensemble 的平均質心向量並正規化
                    centroid = np.mean(embeds, axis=0)
                    norm = np.linalg.norm(centroid)
                    if norm > 1e-8:
                        centroid = centroid / norm
                    self._text_embeddings[genre_key] = centroid.astype(np.float32)
            logger.info("✅ 16 大風格 CLAP 語意錨點預計算完成！")
        except Exception as e:
            logger.warning(f"CLAP 文字錨點預計算異常: {e}，將啟用聲學流形模式。")
            self._text_embeddings.clear()

    def classify_vector(self, audio_vec: np.ndarray, bpm: float = 120.0, acoustic_meta: Optional[dict] = None, onnx_scores: Optional[dict] = None) -> dict:
        """
        結合 512D 向量 (CLAP 或 聲學特徵)、ONNX 深度學習分類與聲學物理特徵
        """
        scores = {}
        acoustic_meta = acoustic_meta or {}
        
        norm_audio = np.linalg.norm(audio_vec)
        normed_vec = audio_vec / (norm_audio + 1e-8) if norm_audio > 1e-8 else audio_vec

        # Mode A: 若有預計算好的 CLAP 語意文字錨點，計算餘弦相似度
        energy = acoustic_meta.get("total_energy", 0.5)
        perc = acoustic_meta.get("percussive", 0.5)
        bass = acoustic_meta.get("bass_ratio", 0.4)
        harmonic = acoustic_meta.get("harmonic", 0.4)

        # 節奏倍頻/半頻自適應校準
        eff_bpm = bpm
        if acoustic_meta.get('is_double_time') or (bpm >= 130 and energy < 0.45 and harmonic > 0.40):
            # 慢速音樂 (如 70-85 BPM Lo-Fi/Chillhop) 被 beat_track 識別為 2x BPM
            eff_bpm = bpm / 2.0
        elif acoustic_meta.get('is_half_time') or (75 <= bpm <= 95 and (perc > 0.45 or energy > 0.50)):
            # 高速碎拍音樂 (如 160-180 BPM DnB/Breakbeat) 被 beat_track 識別為 0.5x BPM
            eff_bpm = bpm * 2.0

        if len(self._text_embeddings) > 0:
            for genre_key, text_vec in self._text_embeddings.items():
                cosine_sim = float(np.dot(normed_vec, text_vec))
                scores[genre_key] = max(0.0, cosine_sim)
        else:
            # Mode B: 物理聲學啟發式流形評估 (依據 512D 特徵與聲學物理先驗)
            scores = self._score_by_acoustic_heuristics(audio_vec, eff_bpm, acoustic_meta)

        # 融合 Tier 1 YAMNet ONNX 深度模型預測
        if onnx_scores:
            for k, onnx_val in onnx_scores.items():
                if k in scores and onnx_val > 0.05:
                    scores[k] = scores[k] * 0.55 + onnx_val * 1.8

        # 融合 BPM 與節奏懲罰/獎勵權重
        for genre_key, info in GENRE_REGISTRY.items():
            b_min, b_max = info["bpm_range"]
            ideal = info["ideal_bpm"]
            
            # 若無節拍或拍速極低 (Ambient/Drone/Classical 特徵)
            if eff_bpm <= 45.0:
                if genre_key == "ambient":
                    bpm_weight = 1.0
                elif genre_key == "classical":
                    bpm_weight = 0.8
                else:
                    bpm_weight = 0.1
            else:
                # BPM 高斯衰減權重
                bpm_diff = abs(eff_bpm - ideal)
                bpm_weight = np.exp(- (bpm_diff ** 2) / (2 * (30.0 ** 2)))
                
                # 針對特殊拍速 (Half-time/Double-time) 修正
                if genre_key in ("hip-hop", "dubstep") and (65 <= eff_bpm <= 80 or 135 <= eff_bpm <= 155):
                    bpm_weight = max(bpm_weight, 0.85)
                elif genre_key == "dnb" and (160 <= eff_bpm <= 185):
                    bpm_weight = max(bpm_weight, 0.95)
                elif genre_key == "techno" and (124 <= eff_bpm <= 140):
                    bpm_weight = max(bpm_weight, 0.90)

            scores[genre_key] = scores.get(genre_key, 0.1) * (0.65 + 0.35 * bpm_weight)

        # 排序並歸一化概率
        sorted_candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_genre_key = sorted_candidates[0][0]
        top_score = sorted_candidates[0][1]
        
        sum_scores = sum(scores.values()) + 1e-8
        confidence = float(np.clip(top_score / (sorted_candidates[1][1] + 1e-8) * 0.5, 0.4, 0.98))

        top_info = GENRE_REGISTRY[top_genre_key]
        
        # 動態計算 Valence (情緒正負) 與 Arousal (能量喚醒度)
        energy = acoustic_meta.get("total_energy", 0.5)
        perc = acoustic_meta.get("percussive", 0.5)
        bass = acoustic_meta.get("bass_ratio", 0.4)
        
        arousal = float(np.clip(top_info["default_arousal"] * 0.5 + energy * 0.3 + perc * 0.2, 0.05, 0.99))
        valence = float(np.clip(top_info["default_valence"] * 0.7 + (1.0 - bass * 0.6) * 0.3, -0.95, 0.95))

        return {
            "primary_genre": top_info["display_name"],
            "genre_key": top_genre_key,
            "sub_genre": top_info["sub_genre"],
            "confidence": round(confidence, 3),
            "valence": round(valence, 3),
            "arousal": round(arousal, 3),
            "danceability": top_info["danceability"],
            "top_candidates": [(GENRE_REGISTRY[k]["display_name"], round(float(v / sum_scores), 3)) for k, v in sorted_candidates[:4]]
        }

    def _score_by_acoustic_heuristics(self, audio_vec: np.ndarray, bpm: float, meta: dict) -> dict:
        """ 物理聲學統計流形特徵打分器 """
        scores = {}
        perc = meta.get("percussive", 0.4)
        bass = meta.get("bass_ratio", 0.3)
        energy = meta.get("total_energy", 0.5)
        harmonic = meta.get("harmonic", 0.4)
        phr = perc / (harmonic + 1e-5) # 打擊-諧波比
        
        for k, info in GENRE_REGISTRY.items():
            base = 0.5
            if k == "ambient":
                base += (1.0 - perc) * 1.2 + (1.0 - energy) * 0.6 - phr * 0.5
                if perc < 0.15 or bpm < 45.0:
                    base += 1.2
            elif k == "lo-fi":
                base += (0.8 - abs(bpm - 80) / 40.0) + (1.0 - energy) * 0.5 + harmonic * 0.4
                if energy < 0.45 and harmonic > 0.35:
                    base += 0.7
            elif k == "techno":
                base += perc * 0.6 + bass * 0.4 + (0.6 if 125 <= bpm <= 138 else -0.3)
            elif k == "hardstyle":
                base += perc * 0.7 + energy * 0.5 + (0.6 if bpm >= 145 else -0.4)
            elif k == "dnb":
                base += perc * 0.6 + (0.8 if bpm >= 160 or (78 <= bpm <= 92 and perc > 0.45) else -0.5)
            elif k == "dubstep":
                base += bass * 0.6 + perc * 0.4 + (0.6 if 135 <= bpm <= 150 or 68 <= bpm <= 75 else -0.3)
                if energy < 0.45:
                    base *= 0.2
            elif k == "synthwave":
                base += harmonic * 0.4 + (0.5 if 105 <= bpm <= 128 else -0.2)
            elif k == "house":
                base += perc * 0.4 + (0.6 if 120 <= bpm <= 128 else -0.2)
            elif k == "hip-hop":
                base += bass * 0.5 + (0.5 if (65 <= bpm <= 95) or (130 <= bpm <= 155) else -0.2)
            elif k == "metal":
                base += energy * 0.6 + perc * 0.4 + (0.5 if bpm >= 130 else -0.2)
            elif k == "classical":
                base += harmonic * 0.6 + (1.0 - perc) * 0.5 - bass * 0.2
            elif k == "jazz":
                base += harmonic * 0.5 + (0.4 if 85 <= bpm <= 130 else -0.2)
            elif k == "rock":
                base += energy * 0.4 + harmonic * 0.4 + (0.4 if 110 <= bpm <= 145 else -0.1)
            elif k == "pop":
                if perc < 0.20 or bpm < 55:
                    base = 0.05
                else:
                    base += 0.3 + harmonic * 0.3 + perc * 0.3
            else:
                base += 0.2

            if (perc < 0.18 or bpm < 50.0) and k in ("techno", "house", "dnb", "hardstyle", "dubstep", "pop", "metal", "rock"):
                base *= 0.15

            scores[k] = max(0.02, float(base))
        return scores




class AudioFingerprintEngine:
    """
    音訊語意指紋與 3D 拓撲流形映射引擎
    - 支援 LAION-CLAP 512 維度音訊語意提取 (HTSAT-unfused)
    - 支援 Librosa 物理聲學統計特徵 Heuristic Fallback
    - 內建 .npz 特徵快取機制，避免批次重複計算
    - 支援 UMAP 3D 空間降維，輸出正規化 DNA 座標與 Track Seed
    """
    def __init__(self, cache_dir: Optional[str] = None):
        self.device = "cuda" if (HAS_CLAP and torch.cuda.is_available()) else (
            "mps" if (HAS_CLAP and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()) else "cpu"
        )
        self.model = None
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        if HAS_CLAP:
            try:
                self.model = laion_clap.CLAP_Module(enable_fusion=False, amlib='htsat')
                self.model.load_ckpt()
                self.model.eval().to(self.device)
                logger.info(f"✅ CLAP 模型加載成功，運算設備: {self.device}")
            except Exception as e:
                logger.warning(f"CLAP 初始化失敗 ({e})，將採用聲學統計特徵模式。")
                self.model = None

        self.reducer = None
        self._is_reducer_fitted = False
        self.classifier = GenreSemanticClassifier(clap_model=self.model, device=self.device)

    def _get_cache_path(self, audio_path: str) -> str:
        mtime = os.path.getmtime(audio_path) if os.path.exists(audio_path) else 0
        audio_id = hashlib.md5(f"{audio_path}_{mtime}".encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"clap_emb_{audio_id}.npz")

    def _extract_acoustic_heuristics(self, audio_path: str) -> np.ndarray:
        """ 當缺乏神經網路 CLAP 時，使用 Librosa 提取真實物理聲學統計特徵 (512D) """
        vec = np.zeros(512, dtype=np.float32)
        if not HAS_LIBROSA or not os.path.exists(audio_path):
            return vec

        try:
            y, sr = librosa.load(audio_path, sr=22050, duration=90)  # 採樣前 90 秒
            
            # 1. MFCC (1-40) 均值與變異數 -> 80 維
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40)
            mfcc_mean = np.mean(mfcc, axis=1)
            mfcc_std = np.std(mfcc, axis=1)
            
            # 2. Chroma STFT 統計 -> 24 維
            chroma = librosa.feature.chroma_stft(y=y, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            chroma_std = np.std(chroma, axis=1)
            
            # 3. Spectral Contrast -> 14 維
            contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
            contrast_mean = np.mean(contrast, axis=1)
            contrast_std = np.std(contrast, axis=1)
            
            # 4. Tonnetz (和聲特徵) -> 12 維
            tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
            tonnetz_mean = np.mean(tonnetz, axis=1)
            tonnetz_std = np.std(tonnetz, axis=1)
            
            # 5. 節奏與頻譜包絡
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
            spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
            spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
            zcr = np.mean(librosa.feature.zero_crossing_rate(y=y))
            
            # 拼接主要物理特徵
            features = np.concatenate([
                mfcc_mean, mfcc_std,
                chroma_mean, chroma_std,
                contrast_mean, contrast_std,
                tonnetz_mean, tonnetz_std,
                [spectral_centroid, spectral_bandwidth, spectral_rolloff, zcr]
            ]).astype(np.float32)
            
            l = min(len(features), 512)
            vec[:l] = features[:l]
            
            # 透過正弦頻率基底擴展填充剩餘維度以維持 512D 稠密流形
            if l < 512:
                t = np.linspace(0, 4 * np.pi, 512 - l)
                vec[l:] = np.sin(t * (np.sum(features) % 10.0 + 1.0)) * 0.1
                
            norm = np.linalg.norm(vec)
            if norm > 1e-8:
                vec /= norm
        except Exception as e:
            logger.warning(f"聲學特徵提取異常: {e}")

        return vec

    def extract_clap_vector(self, audio_path: str) -> np.ndarray:
        """
        提取 512 維 CLAP 音訊語意向量（優先命中本機快取）
        """
        if not os.path.exists(audio_path):
            return np.zeros(512, dtype=np.float32)

        cache_file = self._get_cache_path(audio_path)
        if os.path.exists(cache_file):
            try:
                data = np.load(cache_file)
                return data['vector']
            except Exception:
                pass

        vector = None
        if self.model is not None:
            try:
                with torch.no_grad():
                    embed = self.model.get_audio_embedding_from_filelist(x=[audio_path], use_tensor=False)
                    vector = embed[0].astype(np.float32)
            except Exception as e:
                logger.warning(f"CLAP 推論失敗 ({e})，切換至聲學特徵 fallback。")

        if vector is None:
            vector = self._extract_acoustic_heuristics(audio_path)

        # 寫入 .npz 快取
        try:
            np.savez_compressed(cache_file, vector=vector)
        except Exception:
            pass

        return vector

    def fit_and_project_batch(self, clap_vectors: np.ndarray) -> np.ndarray:
        """
        對曲目向量矩陣進行 UMAP 3D 拓撲映射，輸出 [0.0, 1.0] 的 3D DNA 座標
        """
        if clap_vectors.ndim == 1:
            clap_vectors = clap_vectors.reshape(1, -1)

        n_samples = clap_vectors.shape[0]
        has_umap = _check_umap()
        if has_umap and self.reducer is None:
            import umap
            self.reducer = umap.UMAP(n_components=3, n_neighbors=15, min_dist=0.1, metric='cosine', random_state=42)

        if has_umap and self.reducer is not None and n_samples >= 4:
            if hasattr(self.reducer, 'n_neighbors') and self.reducer.n_neighbors >= n_samples:
                self.reducer.n_neighbors = max(2, n_samples - 1)
            dna_coords = self.reducer.fit_transform(clap_vectors)
            self._is_reducer_fitted = True
        elif has_umap and self.reducer is not None and self._is_reducer_fitted:
            dna_coords = self.reducer.transform(clap_vectors)
        else:
            # 偽 3D 流形投影 (Deterministic Linear Projection)
            proj_matrix = np.sin(np.arange(clap_vectors.shape[1] * 3).reshape(clap_vectors.shape[1], 3) * 0.12)
            dna_coords = np.dot(clap_vectors, proj_matrix)

        dna_min = np.min(dna_coords, axis=0)
        dna_max = np.max(dna_coords, axis=0)
        range_val = dna_max - dna_min
        range_val[range_val < 1e-8] = 1.0
        normalized_dna = np.clip((dna_coords - dna_min) / range_val, 0.0, 1.0)
        return normalized_dna

    def generate_track_seed(self, audio_path: str, dna_coord: np.ndarray) -> int:
        """
        根據音訊頭部數據與 3D DNA 座標生成確定性 32-bit 隨機種子 (供 p5.js / WebGL 使用)
        """
        header_hash = "00000000"
        if os.path.exists(audio_path):
            try:
                with open(audio_path, "rb") as f:
                    header = f.read(1024 * 64)
                header_hash = hashlib.sha256(header).hexdigest()
            except Exception:
                pass
                
        coord_str = f"{dna_coord[0]:.5f}_{dna_coord[1]:.5f}_{dna_coord[2]:.5f}"
        final_hash = hashlib.sha256(f"{header_hash}_{coord_str}".encode('utf-8')).hexdigest()
        return int(final_hash[:8], 16)

    def _run_yamnet_onnx(self, audio_path: str) -> Optional[dict]:
        """ Tier 1: 執行本機 YAMNet ONNX (15MB) 深度音訊事件與音樂風格分類 """
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "yamnet.onnx")
        if not os.path.exists(model_path) or not HAS_LIBROSA or not os.path.exists(audio_path):
            return None
            
        try:
            import onnxruntime as ort
            if not hasattr(self, '_yamnet_session') or self._yamnet_session is None:
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                self._yamnet_session = ort.InferenceSession(model_path, opts, providers=['CPUExecutionProvider'])

            # 採樣 30 秒 (16kHz)
            duration = librosa.get_duration(path=audio_path)
            offset = max(0.0, (duration - 30.0) / 2.0) if duration > 30.0 else 0.0
            y, _ = librosa.load(audio_path, sr=16000, offset=offset, duration=min(30.0, duration))
            if len(y) < 1600:
                return None
                
            input_name = self._yamnet_session.get_inputs()[0].name
            outputs = self._yamnet_session.run(None, {input_name: y.astype(np.float32)})
            scores = np.mean(outputs[0], axis=0)

            yamnet_map = {
                238: 'techno',
                240: 'dnb',
                237: 'house',
                243: 'ambient',
                213: 'pop',
                214: 'hip-hop',
                216: 'rock',
                217: 'metal',
                218: 'metal',
                232: 'jazz'
            }
            res = {}
            for cls_idx, genre_k in yamnet_map.items():
                if cls_idx < len(scores):
                    res[genre_k] = max(res.get(genre_k, 0.0), float(scores[cls_idx]))
            return res
        except Exception as e:
            logger.debug(f"YAMNet ONNX 推論跳過: {e}")
            return None

    def classify_genre(self, audio_path: str, vector: Optional[np.ndarray] = None, bpm: float = 120.0, acoustic_meta: Optional[dict] = None) -> dict:
        """
        全維度樂曲風格分類入口：結合 ONNX (Tier 1) / CLAP (Tier 2) / 物理聲學 (Tier 0)
        """
        if vector is None:
            vector = self.extract_clap_vector(audio_path)
            
        onnx_scores = self._run_yamnet_onnx(audio_path)
        result = self.classifier.classify_vector(vector, bpm=bpm, acoustic_meta=acoustic_meta, onnx_scores=onnx_scores)
        
        # 寫入/更新快取
        cache_file = self._get_cache_path(audio_path)
        if os.path.exists(cache_file):
            try:
                data = dict(np.load(cache_file))
                data['genre_telemetry'] = result
                np.savez_compressed(cache_file, **data)
            except Exception:
                pass
                
        return result


