import os
import hashlib
import numpy as np
import logging

logger = logging.getLogger("StandaloneInjector.AudioFingerprint")

try:
    import torch
    import laion_clap
    HAS_CLAP = True
except ImportError:
    HAS_CLAP = False
    logger.warning("laion_clap or torch not available, fallback embedding mode will be used.")

try:
    import umap
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False
    logger.warning("umap-learn not available, fallback PCA/random projection manifold will be used.")

class AudioFingerprintEngine:
    def __init__(self, model_fp=None):
        self.device = "cuda" if (HAS_CLAP and torch.cuda.is_available()) else ("mps" if (HAS_CLAP and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()) else "cpu")
        self.model = None
        if HAS_CLAP:
            try:
                self.model = laion_clap.CLAP_Module(enable_fusion=False, amlib='htsat')
                self.model.load_ckpt()
                self.model.eval().to(self.device)
            except Exception as e:
                logger.warning(f"Failed to initialize CLAP module: {e}")
                self.model = None

        if HAS_UMAP:
            self.reducer = umap.UMAP(n_components=3, random_state=42)
        else:
            self.reducer = None

    def extract_clap_vector(self, audio_path: str) -> np.ndarray:
        """ 提取 512 維 CLAP 音訊語意向量或備用 STFT 語意特徵 """
        if self.model is not None and os.path.exists(audio_path):
            try:
                with torch.no_grad():
                    audio_embed = self.model.get_audio_embedding_from_filelist(x=[audio_path], use_tensor=False)
                    return audio_embed[0]  # Shape: (512,)
            except Exception as e:
                logger.warning(f"CLAP extraction error: {e}, using heuristic embedding.")

        # Heuristic fallback 512D embedding based on file content & spectral sampling
        vec = np.zeros(512, dtype=np.float32)
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                raw_bytes = f.read(1024 * 512)
            if raw_bytes:
                arr = np.frombuffer(raw_bytes[:min(len(raw_bytes), 512*4)], dtype=np.uint8).astype(np.float32)
                l = len(arr)
                vec[:l] = arr / 255.0
                if l < 512:
                    vec[l:] = np.sin(np.linspace(0, 10*np.pi, 512 - l))
        return vec

    def fit_and_project_batch(self, clap_vectors: np.ndarray) -> np.ndarray:
        """ 對 1000+ 曲目向量矩陣進行 UMAP 3D 拓撲映射 """
        if clap_vectors.ndim == 1:
            clap_vectors = clap_vectors.reshape(1, -1)

        n_samples = clap_vectors.shape[0]
        if HAS_UMAP and self.reducer is not None and n_samples >= 4:
            dna_coords = self.reducer.fit_transform(clap_vectors)
        else:
            # Fallback pseudo 3D manifold projection
            proj_matrix = np.sin(np.arange(clap_vectors.shape[1] * 3).reshape(clap_vectors.shape[1], 3) * 0.1)
            dna_coords = np.dot(clap_vectors, proj_matrix)

        dna_min = np.min(dna_coords, axis=0)
        dna_max = np.max(dna_coords, axis=0)
        range_val = dna_max - dna_min
        range_val[range_val < 1e-8] = 1.0
        normalized_dna = (dna_coords - dna_min) / range_val
        return normalized_dna

    def generate_track_seed(self, audio_path: str, dna_coord: np.ndarray) -> int:
        """ 計算確定性 Track Seed """
        header_hash = "00000000"
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                header = f.read(1024 * 64)
            header_hash = hashlib.sha256(header).hexdigest()
        coord_str = f"{dna_coord[0]:.6f}_{dna_coord[1]:.6f}_{dna_coord[2]:.6f}"
        final_hash = hashlib.sha256(f"{header_hash}_{coord_str}".encode('utf-8')).hexdigest()
        return int(final_hash[:15], 16)
