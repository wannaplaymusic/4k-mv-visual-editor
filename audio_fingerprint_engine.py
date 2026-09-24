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

# 18 大主流音樂風格本體庫與多模態 Prompt 集成 (SOTA 統一註冊表)
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
        "ideal_bpm": 132,
        "ballistic": {"attack_ms": 2.0, "release_ms": 80.0},
        "oklch": {"l_base": 0.40, "c_base": 0.16, "harmonies": [0.0, 90.0, 180.0, 270.0]},
        "lexicon": {"intro": "Atmospheric Intro", "build": "Modular Build-up", "peak": "Peak-Time Drop", "break": "Dark Breakdown", "outro": "Industrial Fadeout"}
    },
    "dub_techno": {
        "display_name": "Dub Techno / Minimal Deep",
        "sub_genre": "Echospace Berlin Sub-Bass",
        "prompts": [
            "Deep atmospheric dub techno with echoing tape delay synthesizer stabs, deep sub bass, vast reverb and minimal hypnotic rhythm",
            "Subterranean minimal techno track with cavernous dub delay effects, warm analog hiss and steady four on the floor kick",
            "Ethereal Detroit dub techno with deep chords drowned in tape echo and subtle filtered noise sweeps"
        ],
        "default_valence": -0.15,
        "default_arousal": 0.45,
        "danceability": 0.70,
        "bpm_range": (112, 128),
        "ideal_bpm": 120,
        "ballistic": {"attack_ms": 40.0, "release_ms": 400.0},
        "oklch": {"l_base": 0.25, "c_base": 0.05, "harmonies": [0.0, 30.0, 180.0, 210.0]},
        "lexicon": {"intro": "Subterranean Intro", "build": "Minimal Echo Loop", "peak": "Deep Spatial Bloom", "break": "Cavernous Breakdown", "outro": "Tape Decay Outro"}
    },
    "hard_techno": {
        "display_name": "Hard Techno / Schranz",
        "sub_genre": "Industrial Rave & Schranz",
        "prompts": [
            "Relentless hard techno track with aggressive distorted kick drums, ferocious industrial percussion at 155 bpm",
            "Schranz hard techno with blistering 160 bpm tempo, distorted metallic claps and dark warehouse energy",
            "Raw industrial hard techno with pounding distorted bass, screeching synths and driving rave energy"
        ],
        "default_valence": -0.55,
        "default_arousal": 0.98,
        "danceability": 0.85,
        "bpm_range": (145, 168),
        "ideal_bpm": 155,
        "ballistic": {"attack_ms": 1.0, "release_ms": 50.0},
        "oklch": {"l_base": 0.60, "c_base": 0.24, "harmonies": [0.0, 90.0, 180.0, 270.0]},
        "lexicon": {"intro": "Industrial Siren Intro", "build": "Relentless Build", "peak": "Ferocious Schranz Drop", "break": "Metallic Shock Break", "outro": "Abrupt Strobe Outro"}
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
        "ideal_bpm": 136,
        "ballistic": {"attack_ms": 4.0, "release_ms": 110.0},
        "oklch": {"l_base": 0.55, "c_base": 0.22, "harmonies": [0.0, 120.0, 240.0, 60.0]},
        "lexicon": {"intro": "Celestial Induction", "build": "Supersaw Crescendo", "peak": "Euphoric Anthem Drop", "break": "Melodic Floating Break", "outro": "Atmospheric Outro"}
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
        "bpm_range": (160, 185),
        "ideal_bpm": 174,
        "ballistic": {"attack_ms": 1.0, "release_ms": 45.0},
        "oklch": {"l_base": 0.50, "c_base": 0.20, "harmonies": [0.0, 90.0, 180.0, 270.0]},
        "lexicon": {"intro": "Amen Roller Intro", "build": "High-Tension Acceleration", "peak": "Neurofunk Reese Drop", "break": "Liquid Breakbeat Switch", "outro": "Rapid Decay Outro"}
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
        "ideal_bpm": 140,
        "ballistic": {"attack_ms": 2.0, "release_ms": 95.0},
        "oklch": {"l_base": 0.45, "c_base": 0.22, "harmonies": [0.0, 120.0, 240.0, 60.0]},
        "lexicon": {"intro": "Tension Buildup Intro", "build": "Pre-Drop Vocal Silence", "peak": "Heavy Growl Bass Drop", "break": "Melodic Orchestral Break", "outro": "Impact Sub Outro"}
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
        "ideal_bpm": 124,
        "ballistic": {"attack_ms": 5.0, "release_ms": 120.0},
        "oklch": {"l_base": 0.50, "c_base": 0.15, "harmonies": [0.0, 120.0, 240.0, 60.0]},
        "lexicon": {"intro": "Groovy Beat Induction", "build": "Snare Roll Transition", "peak": "Deep Bouncy Club Drop", "break": "Soulful Vocal Breakdown", "outro": "Filter Sweep Outro"}
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
        "ideal_bpm": 116,
        "ballistic": {"attack_ms": 8.0, "release_ms": 150.0},
        "oklch": {"l_base": 0.55, "c_base": 0.20, "harmonies": [0.0, 140.0, 210.0, 320.0]},
        "lexicon": {"intro": "Neon Highway Intro", "build": "Arpeggiator Surge", "peak": "Gated Snare Outrun Peak", "break": "Nostalgic Solo Break", "outro": "Sunset Horizon Fadeout"}
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
        "ideal_bpm": 80,
        "ballistic": {"attack_ms": 40.0, "release_ms": 320.0},
        "oklch": {"l_base": 0.65, "c_base": 0.09, "harmonies": [0.0, 35.0, 190.0, 220.0]},
        "lexicon": {"intro": "Dusty Vinyl Needle Intro", "build": "Warm Rhodes Progression", "peak": "Chill Mellow Groove", "break": "Raindrop Melancholy Bridge", "outro": "Tape Stop Fadeout"}
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
        "ideal_bpm": 60,
        "ballistic": {"attack_ms": 300.0, "release_ms": 1600.0},
        "oklch": {"l_base": 0.35, "c_base": 0.06, "harmonies": [0.0, 40.0, 180.0, 220.0]},
        "lexicon": {"intro": "Atmospheric Induction", "build": "Harmonic Swell", "peak": "Textural Bloom", "break": "Ethereal Void", "outro": "Infinite Dissolve"}
    },
    "edm": {
        "display_name": "EDM / Festival Electro",
        "sub_genre": "Big Room & Future Rave",
        "prompts": [
            "High energy festival EDM track with massive supersaw chord build-up, punchy four on the floor kick and explosive stadium drop",
            "Big room electro house with pounding sub drops, epic melodic breakdowns and energetic festival atmosphere",
            "Future rave dance anthem with soaring lead synthesizers, driving basslines and euphoric crowd energy at 128 bpm"
        ],
        "default_valence": 0.65,
        "default_arousal": 0.95,
        "danceability": 0.92,
        "bpm_range": (124, 132),
        "ideal_bpm": 128,
        "ballistic": {"attack_ms": 3.0, "release_ms": 90.0},
        "oklch": {"l_base": 0.65, "c_base": 0.26, "harmonies": [0.0, 120.0, 240.0, 60.0]},
        "lexicon": {"intro": "Festival Vocal Hook Intro", "build": "Stadium Snare Riser", "peak": "Mainstage Explosive Drop", "break": "Crowd Singalong Break", "outro": "Pyrotechnic Outro"}
    },
    "idm": {
        "display_name": "IDM / Braindance / Glitch",
        "sub_genre": "Algorithmic Glitch & Braindance",
        "prompts": [
            "Complex intelligent dance music with fractured glitch percussion, algorithmic drill and bass patterns and delicate synth melodies",
            "Experimental braindance electronica with intricate polyrhythmic drum programming, modular synthesis and sudden time signature shifts",
            "Glitch hop and IDM track with micro-edited sound design, warm melodic pads and hyperactive syncopated beats"
        ],
        "default_valence": 0.10,
        "default_arousal": 0.75,
        "danceability": 0.60,
        "bpm_range": (90, 175),
        "ideal_bpm": 135,
        "ballistic": {"attack_ms": 2.0, "release_ms": 60.0},
        "oklch": {"l_base": 0.45, "c_base": 0.18, "harmonies": [0.0, 120.0, 210.0, 300.0]},
        "lexicon": {"intro": "Generative Start", "build": "Algorithmic Glitch Mutation", "peak": "Fractured Polyrhythm Peak", "break": "Microtonal Ambient Bridge", "outro": "Deconstructive Disintegration"}
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
        "ideal_bpm": 140,
        "ballistic": {"attack_ms": 4.0, "release_ms": 110.0},
        "oklch": {"l_base": 0.40, "c_base": 0.15, "harmonies": [0.0, 90.0, 180.0, 270.0]},
        "lexicon": {"intro": "808 Sub Induction", "build": "Hi-Hat Roll Riser", "peak": "Heavy 808 Bass Drop", "break": "Soul Sample Loop Bridge", "outro": "Faded Hook Outro"}
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
        "bpm_range": (105, 150),
        "ideal_bpm": 125,
        "ballistic": {"attack_ms": 5.0, "release_ms": 120.0},
        "oklch": {"l_base": 0.50, "c_base": 0.16, "harmonies": [0.0, 120.0, 240.0, 60.0]},
        "lexicon": {"intro": "Guitar Riff Intro", "build": "Driving Pre-Chorus", "peak": "Anthemic Chorus Blast", "break": "Guitar Solo Bridge", "outro": "Crash Cymbal Outro"}
    },
    "metal": {
        "display_name": "Metal / Heavy Hardcore",
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
        "ideal_bpm": 150,
        "ballistic": {"attack_ms": 2.0, "release_ms": 70.0},
        "oklch": {"l_base": 0.30, "c_base": 0.18, "harmonies": [0.0, 90.0, 180.0, 270.0]},
        "lexicon": {"intro": "Distorted Feedback Intro", "build": "Double-Kick Acceleration", "peak": "Crushing Breakdown Peak", "break": "Polyrhythmic Chug Bridge", "outro": "Screaming Feedback Outro"}
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
        "bpm_range": (85, 130),
        "ideal_bpm": 105,
        "ballistic": {"attack_ms": 15.0, "release_ms": 220.0},
        "oklch": {"l_base": 0.55, "c_base": 0.12, "harmonies": [0.0, 60.0, 180.0, 240.0]},
        "lexicon": {"intro": "Head-In Theme Intro", "build": "Rhythm Section Comping", "peak": "Solo Improvisation Climax", "break": "Bass & Drum Interlude", "outro": "Head-Out Final Tag"}
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
        "ideal_bpm": 85,
        "ballistic": {"attack_ms": 80.0, "release_ms": 500.0},
        "oklch": {"l_base": 0.45, "c_base": 0.08, "harmonies": [0.0, 45.0, 180.0, 225.0]},
        "lexicon": {"intro": "Exposition Motif Intro", "build": "Symphonic Crescendo", "peak": "Tutti Orchestral Climax", "break": "Solo Adagio Interlude", "outro": "Maestoso Finale Outro"}
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
        "ideal_bpm": 120,
        "ballistic": {"attack_ms": 8.0, "release_ms": 140.0},
        "oklch": {"l_base": 0.70, "c_base": 0.18, "harmonies": [0.0, 120.0, 240.0, 60.0]},
        "lexicon": {"intro": "Catchy Hook Intro", "build": "Pre-Chorus Lift", "peak": "Anthemic Chorus Drop", "break": "Stripped-Back Bridge", "outro": "Fadeout Hook Outro"}
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
        "ideal_bpm": 90,
        "ballistic": {"attack_ms": 30.0, "release_ms": 260.0},
        "oklch": {"l_base": 0.40, "c_base": 0.08, "harmonies": [0.0, 40.0, 180.0, 220.0]},
        "lexicon": {"intro": "Sub-Heavy Trip Intro", "build": "Slow Breakbeat Groove", "peak": "Moody Bass Climax", "break": "Dub Echo Interlude", "outro": "Atmospheric Drift Outro"}
    }
}

GENRE_KEY_ALIASES = {
    "techno": "techno",
    "dub techno": "dub_techno",
    "dub_techno": "dub_techno",
    "hard techno": "hard_techno",
    "hard_techno": "hard_techno",
    "trance": "trance",
    "dnb": "dnb",
    "drum and bass": "dnb",
    "drum & bass": "dnb",
    "dubstep": "dubstep",
    "house": "house",
    "synthwave": "synthwave",
    "lo-fi": "lo-fi",
    "lofi": "lo-fi",
    "chillhop": "lo-fi",
    "ambient": "ambient",
    "edm": "edm",
    "electronic dance music": "edm",
    "idm": "idm",
    "hip-hop": "hip-hop",
    "hip hop": "hip-hop",
    "trap": "hip-hop",
    "rock": "rock",
    "metal": "metal",
    "hardcore": "metal",
    "jazz": "jazz",
    "classical": "classical",
    "pop": "pop",
    "downtempo": "downtempo",
    "trip-hop": "downtempo"
}

def normalize_genre_key(genre_str: str) -> str:
    """將任意格式的風格字串標準化為註冊表標準 Key (長度降序最長匹配)"""
    if not genre_str or not isinstance(genre_str, str):
        return "techno"
    clean = genre_str.strip().lower()
    if clean in GENRE_REGISTRY:
        return clean
    if clean in GENRE_KEY_ALIASES:
        return GENRE_KEY_ALIASES[clean]

    clean_normalized = clean.replace("_", " ").replace("-", " ")
    if clean_normalized in GENRE_KEY_ALIASES:
        return GENRE_KEY_ALIASES[clean_normalized]

    # 按別名長度降序比對 (最長關鍵詞優先，防止 "techno" 攔截 "dub techno" / "hard techno")
    sorted_aliases = sorted(GENRE_KEY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias_pattern, canonical in sorted_aliases:
        alias_clean = alias_pattern.replace("_", " ").replace("-", " ")
        if alias_clean in clean_normalized or alias_pattern in clean:
            return canonical
    return "techno"

def get_genre_profile(genre_key: str) -> dict:
    """安全獲取風格專屬 SOTA 規格配置"""
    canonical = normalize_genre_key(genre_key)
    return GENRE_REGISTRY.get(canonical, GENRE_REGISTRY["techno"])



def extract_path_genre_prior(audio_path: Optional[str]) -> Optional[str]:
    """從檔案路徑與目錄中提取風格先驗（例如 /Techno 2026-2/ -> techno）"""
    if not audio_path or not isinstance(audio_path, str):
        return None
    path_lower = audio_path.lower().replace("_", " ").replace("-", " ")
    
    candidates = [
        ("hard techno", "hard_techno"),
        ("dub techno", "dub_techno"),
        ("techno", "techno"),
        ("drum and bass", "dnb"),
        ("drum & bass", "dnb"),
        ("dnb", "dnb"),
        ("ambient", "ambient"),
        ("drone", "ambient"),
        ("lo fi", "lo-fi"),
        ("lofi", "lo-fi"),
        ("chillhop", "lo-fi"),
        ("synthwave", "synthwave"),
        ("retrowave", "synthwave"),
        ("trance", "trance"),
        ("deep house", "house"),
        ("house", "house"),
        ("dubstep", "dubstep"),
        ("edm", "edm"),
        ("electro", "edm"),
        ("idm", "idm"),
        ("glitch", "idm"),
        ("jazz", "jazz"),
        ("metal", "metal"),
        ("rock", "rock"),
        ("classical", "classical"),
        ("hip hop", "hip-hop"),
        ("trap", "hip-hop"),
        ("downtempo", "downtempo"),
    ]
    import re
    for kw, genre_key in candidates:
        if re.search(r'(?:^|[\\/ \-_])' + re.escape(kw) + r'(?:$|[\\/ \-_])', path_lower):
            return genre_key
    return None


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

    def classify_vector(self, audio_vec: np.ndarray, bpm: float = 120.0, acoustic_meta: Optional[dict] = None, onnx_scores: Optional[dict] = None, audio_path: Optional[str] = None) -> dict:
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

        # 節奏倍頻/半頻自適應校準 (徹底解決 Octave Error)
        # 注意：若 audio_analyzer 已經校準過，bpm 已是精確速度，嚴禁在此重複乘 2！
        eff_bpm = bpm
        onset_rate = acoustic_meta.get('onset_rate', 0.0)
        # 僅當當前 bpm 處於慢速區間 (<= 95 BPM) 且具有高速特徵，且尚未被倍頻時才翻倍
        if eff_bpm <= 95.0 and (acoustic_meta.get('should_double_bpm') or acoustic_meta.get('is_double_time') or (75 <= bpm <= 95 and (perc > 0.35 or energy > 0.45 or onset_rate >= 3.6))):
            eff_bpm = bpm * 2.0
        # 僅當當前 bpm 處於高速區間 (>= 135 BPM) 且具有慢速平滑特徵，且尚未被減半時才減半
        elif eff_bpm >= 135.0 and not acoustic_meta.get('should_double_bpm') and (acoustic_meta.get('should_half_bpm') or acoustic_meta.get('is_half_time') or (energy < 0.42 and harmonic > 0.38 and onset_rate < 3.2)):
            eff_bpm = bpm / 2.0

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
                    scores[k] = scores[k] * 0.50 + onnx_val * 2.0

        # 融合路徑目錄先驗 (Path Semantic Prior)
        target_path = audio_path or acoustic_meta.get('audio_path')
        path_prior = extract_path_genre_prior(target_path)
        if path_prior and path_prior in scores:
            scores[path_prior] = scores[path_prior] * 3.5
            # 若為衍生子風格 (例如 techno -> hard_techno, dub_techno)，同步增益並抑制互斥風格
            if path_prior == "techno":
                if "hard_techno" in scores:
                    scores["hard_techno"] *= 3.0
                if "dub_techno" in scores:
                    scores["dub_techno"] *= 2.8
                if "ambient" in scores:
                    scores["ambient"] *= 0.05
            elif path_prior == "ambient":
                if "techno" in scores:
                    scores["techno"] *= 0.1

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
                bpm_weight = np.exp(- (bpm_diff ** 2) / (2 * (28.0 ** 2)))
                
                # 針對特殊拍速修正
                if genre_key in ("hip-hop", "dubstep") and (65 <= eff_bpm <= 80 or 135 <= eff_bpm <= 155):
                    bpm_weight = max(bpm_weight, 0.85)
                elif genre_key == "dnb" and (160 <= eff_bpm <= 185):
                    bpm_weight = max(bpm_weight, 0.95)
                elif genre_key in ("techno", "hard_techno") and (124 <= eff_bpm <= 165):
                    bpm_weight = max(bpm_weight, 0.90)
                elif genre_key == "dub_techno" and (112 <= eff_bpm <= 128):
                    bpm_weight = max(bpm_weight, 0.92)

            scores[genre_key] = scores.get(genre_key, 0.1) * (0.60 + 0.40 * bpm_weight)

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
            "ballistic": top_info.get("ballistic", {"attack_ms": 10.0, "release_ms": 180.0}),
            "top_candidates": [(GENRE_REGISTRY[k]["display_name"], round(float(v / sum_scores), 3)) for k, v in sorted_candidates[:4]]
        }

    def _score_by_acoustic_heuristics(self, audio_vec: np.ndarray, bpm: float, meta: dict) -> dict:
        """ 物理聲學統計流形特徵打分器 (涵蓋 18 大風格) """
        scores = {}
        perc = meta.get("percussive", 0.4)
        bass = meta.get("bass_ratio", 0.3)
        energy = meta.get("total_energy", 0.5)
        harmonic = meta.get("harmonic", 0.4)
        centroid = meta.get("spectral_centroid", 3000.0)
        phr = perc / (harmonic + 1e-5) # 打擊-諧波比
        
        for k, info in GENRE_REGISTRY.items():
            base = 0.5
            if k == "ambient":
                base += (1.0 - perc) * 1.5 + (1.0 - energy) * 0.8 - phr * 0.8
                if perc < 0.18 or bpm < 45.0:
                    base += 1.4
                # 高拍速 (BPM >= 120) 或密集音符擊發 (onset_rate >= 2.8) 絕非 Ambient/Drone，施加強衰減
                if bpm >= 120.0 or meta.get('onset_rate', 0) >= 2.8:
                    base *= 0.15
            elif k == "dub_techno":
                base += bass * 0.8 + (0.8 - perc * 0.4) + (0.7 if 114 <= bpm <= 128 else -0.3)
                if centroid < 2800.0:
                    base += 0.5
            elif k == "hard_techno":
                base += perc * 0.8 + energy * 0.7 + (0.8 if bpm >= 145 else -0.4)
            elif k == "lo-fi":
                base += (0.8 - abs(bpm - 80) / 35.0) + (1.0 - energy) * 0.6 + harmonic * 0.5
                if centroid < 3200.0 and energy < 0.50:
                    base += 0.7
                if centroid > 4000.0 or perc > 0.42 or meta.get('onset_rate', 0) > 3.8 or bpm > 115:
                    base *= 0.1 # 高頻明亮、劇烈打擊、高速擊發率或高速拍速絕不可為 Lo-Fi
            elif k == "techno":
                base += perc * 0.6 + bass * 0.5 + (0.6 if 124 <= bpm <= 138 else -0.3)
            elif k == "dnb":
                base += perc * 0.8 + (1.2 if (160 <= bpm <= 185) else (-0.6 if bpm < 140 else 0.2))
                if centroid > 3200.0:
                    base += 0.4
                if meta.get('onset_rate', 0) >= 3.6:
                    base += 0.5
            elif k == "idm":
                base += phr * 0.4 + perc * 0.6 + (0.5 if (90 <= bpm <= 175 and perc > 0.38) else -0.2)
            elif k == "edm":
                base += energy * 0.8 + perc * 0.6 + (0.7 if 124 <= bpm <= 132 else -0.3)
                if centroid > 3000.0:
                    base += 0.4
            elif k == "dubstep":
                base += bass * 0.7 + perc * 0.5 + (0.7 if 135 <= bpm <= 150 or 68 <= bpm <= 75 else -0.3)
                if energy < 0.40:
                    base *= 0.2
            elif k == "trance":
                base += harmonic * 0.6 + energy * 0.5 + (0.7 if 132 <= bpm <= 142 else -0.3)
            elif k == "synthwave":
                base += harmonic * 0.5 + (0.6 if 105 <= bpm <= 128 else -0.2)
            elif k == "house":
                base += perc * 0.5 + (0.6 if 120 <= bpm <= 128 else -0.2)
            elif k == "hip-hop":
                base += bass * 0.6 + (0.5 if (65 <= bpm <= 95) or (130 <= bpm <= 155) else -0.2)
            elif k == "metal":
                base += energy * 0.7 + perc * 0.5 + (0.6 if bpm >= 130 else -0.2)
            elif k == "classical":
                base += harmonic * 0.7 + (1.0 - perc) * 0.6 - bass * 0.2
            elif k == "jazz":
                base += harmonic * 0.6 + (0.5 if 85 <= bpm <= 130 else -0.2)
            elif k == "rock":
                base += energy * 0.5 + harmonic * 0.4 + (0.5 if 110 <= bpm <= 145 else -0.1)
            elif k == "pop":
                if perc < 0.20 or bpm < 55:
                    base = 0.05
                else:
                    base += 0.3 + harmonic * 0.4 + perc * 0.3
            elif k == "downtempo":
                base += bass * 0.5 + (1.0 - energy) * 0.4 + (0.5 if 75 <= bpm <= 105 else -0.2)
            else:
                base += 0.2

            if ((perc < 0.18 and meta.get('onset_rate', 0) < 2.6) or bpm < 50.0) and k in ("techno", "hard_techno", "house", "dnb", "dubstep", "pop", "metal", "rock", "edm"):
                base *= 0.12

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
                220: 'metal',
                232: 'jazz',
                226: 'jazz',
                239: 'dubstep',
                244: 'trance',
                242: 'edm',
                236: 'edm',
                234: 'classical',
                241: 'idm'
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
        result = self.classifier.classify_vector(vector, bpm=bpm, acoustic_meta=acoustic_meta, onnx_scores=onnx_scores, audio_path=audio_path)
        
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


